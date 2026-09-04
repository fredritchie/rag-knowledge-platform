from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

import boto3
import httpx
from sqlalchemy import delete, select

from rag_platform.application.db.models import (
    Document,
    DocumentPermission,
    DocumentSource,
    DocumentVersion,
    DriveChangeEvent,
    DriveCheckpoint,
    DriveConnection,
    IngestionJob,
    TenantMembership,
    User,
)
from rag_platform.application.db.session import Database
from rag_platform.config import Settings, load_settings
from rag_platform.observability import (
    DRIVE_SYNC_LAST_SUCCESS,
    DRIVE_SYNC_RUNS,
    configure_observability,
    service_var,
)

logger = logging.getLogger("rag_platform.drive_sync_worker")


@dataclass(frozen=True, slots=True)
class DrivePage:
    changes: list[dict[str, Any]]
    next_page_token: str | None
    new_start_page_token: str | None


class DriveClient(Protocol):
    async def start_page_token(self, connection: DriveConnection) -> str: ...

    async def list_changes(self, connection: DriveConnection, token: str) -> DrivePage: ...

    async def download(self, connection: DriveConnection, file: dict[str, Any]) -> bytes: ...


class CredentialsResolver(Protocol):
    async def access_token(self, reference: str) -> str: ...


class SecretsManagerCredentialsResolver:
    """Resolve an access token or refresh-token bundle from Secrets Manager."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.secrets = boto3.client(
            "secretsmanager", region_name=settings.drive.secrets_region or settings.storage.region
        )

    async def access_token(self, reference: str) -> str:
        response = await asyncio.to_thread(self.secrets.get_secret_value, SecretId=reference)
        secret = json.loads(response["SecretString"])
        if secret.get("access_token"):
            return str(secret["access_token"])
        required = ("refresh_token", "client_id", "client_secret")
        if not all(secret.get(key) for key in required):
            raise ValueError("Drive secret must contain access_token or OAuth refresh credentials")
        async with httpx.AsyncClient(timeout=30) as client:
            token = await client.post(
                self.settings.drive.oauth_token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": secret["refresh_token"],
                    "client_id": secret["client_id"],
                    "client_secret": secret["client_secret"],
                },
            )
            token.raise_for_status()
            return str(token.json()["access_token"])


class GoogleDriveClient:
    FILE_FIELDS = (
        "id,name,mimeType,modifiedTime,md5Checksum,size,parents,permissionIds,"
        "permissions(id,type,emailAddress,domain,role),trashed"
    )

    def __init__(self, settings: Settings, credentials: CredentialsResolver):
        self.settings = settings
        self.credentials = credentials

    async def _headers(self, connection: DriveConnection) -> dict[str, str]:
        token = await self.credentials.access_token(connection.secret_reference)
        return {"Authorization": f"Bearer {token}"}

    async def start_page_token(self, connection: DriveConnection) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self.settings.drive.api_base_url}/changes/startPageToken",
                headers=await self._headers(connection),
                params={
                    "supportsAllDrives": str(self.settings.drive.include_shared_drives).lower()
                },
            )
            response.raise_for_status()
            return str(response.json()["startPageToken"])

    async def list_changes(self, connection: DriveConnection, token: str) -> DrivePage:
        params = {
            "pageToken": token,
            "pageSize": self.settings.drive.page_size,
            "includeRemoved": "true",
            "includeItemsFromAllDrives": str(self.settings.drive.include_shared_drives).lower(),
            "supportsAllDrives": str(self.settings.drive.include_shared_drives).lower(),
            "fields": (
                "nextPageToken,newStartPageToken,"
                f"changes(fileId,removed,time,file({self.FILE_FIELDS}))"
            ),
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(
                f"{self.settings.drive.api_base_url}/changes",
                headers=await self._headers(connection),
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        return DrivePage(
            changes=body.get("changes", []),
            next_page_token=body.get("nextPageToken"),
            new_start_page_token=body.get("newStartPageToken"),
        )

    async def download(self, connection: DriveConnection, file: dict[str, Any]) -> bytes:
        mime_type = str(file["mimeType"])
        file_id = quote(str(file["id"]), safe="")
        export_type = self.settings.drive.export_mime_types.get(mime_type)
        if export_type:
            url = f"{self.settings.drive.api_base_url}/files/{file_id}/export"
            params = {"mimeType": export_type}
        else:
            url = f"{self.settings.drive.api_base_url}/files/{file_id}"
            params = {"alt": "media", "supportsAllDrives": "true"}
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.get(url, headers=await self._headers(connection), params=params)
            response.raise_for_status()
            return response.content


class DriveSyncService:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        client: DriveClient,
        *,
        s3_client: Any | None = None,
        sqs_client: Any | None = None,
    ):
        self.settings = settings
        self.database = database
        self.client = client
        self.s3 = s3_client or boto3.client(
            "s3", region_name=settings.storage.region, endpoint_url=settings.storage.endpoint_url
        )
        self.sqs = sqs_client or boto3.client("sqs", region_name=settings.storage.region)

    async def sync(self, connection_id: str) -> int:
        async with self.database.sessions() as session:
            connection = await session.get(DriveConnection, connection_id)
            checkpoint = await session.get(DriveCheckpoint, connection_id)
            if connection is None or checkpoint is None or connection.status != "ACTIVE":
                return 0
            checkpoint.status = "RUNNING"
            await session.commit()
        try:
            token = checkpoint.last_change_token
            if token is None:
                token = await self.client.start_page_token(connection)
                await self._complete(connection_id, token)
                return 0
            processed = 0
            while token:
                page = await self.client.list_changes(connection, token)
                for change in page.changes:
                    if await self._apply_change(connection, change):
                        processed += 1
                if page.next_page_token:
                    token = page.next_page_token
                    continue
                token = page.new_start_page_token or token
                break
            await self._complete(connection_id, token)
            return processed
        except Exception as exc:
            async with self.database.sessions() as session:
                current = await session.get(DriveCheckpoint, connection_id)
                if current:
                    current.status = "FAILED"
                    current.error_count += 1
                    current.last_error = str(exc)[:4000]
                    current.next_sync_at = datetime.now(UTC) + timedelta(
                        seconds=self.settings.drive.sync_interval_seconds
                    )
                    await session.commit()
            raise

    async def _complete(self, connection_id: str, token: str) -> None:
        async with self.database.sessions() as session:
            current = await session.get(DriveCheckpoint, connection_id)
            current.last_change_token = token
            current.last_success_time = datetime.now(UTC)
            current.next_sync_at = datetime.now(UTC) + timedelta(
                seconds=self.settings.drive.sync_interval_seconds
            )
            current.status = "IDLE"
            current.error_count = 0
            current.last_error = None
            await session.commit()

    async def _apply_change(self, connection: DriveConnection, change: dict[str, Any]) -> bool:
        file_id = str(change.get("fileId") or "")
        if not file_id:
            return False
        file = change.get("file") or {}
        change_key = hashlib.sha256(
            json.dumps(change, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        async with self.database.sessions() as session:
            seen = await session.scalar(
                select(DriveChangeEvent).where(
                    DriveChangeEvent.connection_id == connection.id,
                    DriveChangeEvent.change_key == change_key,
                )
            )
            if seen and seen.status != "FAILED":
                return False
            source = await session.scalar(
                select(DocumentSource).where(
                    DocumentSource.tenant_id == connection.tenant_id,
                    DocumentSource.source_type == "google_drive",
                    DocumentSource.source_file_id == file_id,
                )
            )
            action = _classify_change(change, source.metadata_json if source else None)
            if seen:
                event = seen
                event.action = action
                event.source_version = file.get("modifiedTime")
                event.details = {"file": file}
                event.status = "PENDING"
                event.last_error = None
            else:
                event = DriveChangeEvent(
                    connection_id=connection.id,
                    tenant_id=connection.tenant_id,
                    change_key=change_key,
                    file_id=file_id,
                    action=action,
                    source_version=file.get("modifiedTime"),
                    details={"file": file},
                )
                session.add(event)
                await session.flush()
            try:
                if (
                    action != "DELETE"
                    and file.get("mimeType") not in self.settings.drive.allowed_mime_types
                ):
                    event.status = "SKIPPED"
                    event.details = {**event.details, "reason": "UNSUPPORTED_MIME_TYPE"}
                elif action == "DELETE":
                    await self._publish_delete(session, connection, source, event)
                elif action in {"MOVE", "PERMISSION_CHANGE"} and source is not None:
                    document = await session.get(Document, source.document_id)
                    if document is None:
                        raise ValueError("Drive source points to a missing document")
                    source.source_version = file.get("modifiedTime")
                    source.metadata_json = file
                    document.filename = Path(str(file.get("name") or file_id)).name
                    await self._replace_permissions(session, document, file.get("permissions", []))
                else:
                    await self._publish_upsert(session, connection, source, file)
                if event.status != "SKIPPED":
                    event.status = "PUBLISHED"
                event.processed_at = datetime.now(UTC)
                await session.commit()
                return True
            except Exception as exc:
                event.status = "FAILED"
                event.last_error = str(exc)[:4000]
                await session.commit()
                raise

    async def _publish_upsert(self, session, connection, source, file) -> None:
        content = await self.client.download(connection, file)
        checksum = hashlib.sha256(content).hexdigest()
        duplicate = await session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.tenant_id == connection.tenant_id,
                DocumentVersion.checksum_sha256 == checksum,
            )
        )
        if duplicate:
            # Checksums are unique per tenant. A Drive file can legitimately be
            # connected after an identical manual upload, so attach the new
            # source to that canonical document instead of creating a version
            # that violates the tenant-wide duplicate-content constraint.
            document = await session.get(Document, duplicate.document_id)
            if document is None:
                raise ValueError("Duplicate document version points to a missing document")
            if source is None:
                source = DocumentSource(
                    tenant_id=connection.tenant_id,
                    document_id=document.id,
                    source_type="google_drive",
                    source_file_id=str(file["id"]),
                )
                session.add(source)
            source.source_version = file.get("modifiedTime")
            source.metadata_json = file
            await self._replace_permissions(session, document, file.get("permissions", []))
            return
        if source:
            document = await session.get(Document, source.document_id)
            maximum = await session.scalar(
                select(DocumentVersion.version_number)
                .where(DocumentVersion.document_id == source.document_id)
                .order_by(DocumentVersion.version_number.desc())
                .limit(1)
            )
            version_number = (maximum or 0) + 1
        else:
            owner_id = await session.scalar(
                select(TenantMembership.user_id)
                .where(TenantMembership.tenant_id == connection.tenant_id)
                .order_by(TenantMembership.created_at)
                .limit(1)
            )
            if not owner_id:
                raise ValueError("Drive tenant has no member to own synchronized documents")
            document = Document(
                tenant_id=connection.tenant_id,
                owner_id=owner_id,
                filename=Path(str(file.get("name") or file["id"])).name,
                source="google_drive",
                content_type=self.settings.drive.export_mime_types.get(
                    str(file.get("mimeType")),
                    str(file.get("mimeType") or "application/octet-stream"),
                ),
                status="PENDING_UPLOAD",
            )
            session.add(document)
            await session.flush()
            source = DocumentSource(
                tenant_id=connection.tenant_id,
                document_id=document.id,
                source_type="google_drive",
                source_file_id=str(file["id"]),
            )
            session.add(source)
            version_number = 1
        if document is None:
            raise ValueError("Drive source points to a missing document")
        version = DocumentVersion(
            tenant_id=connection.tenant_id,
            document_id=document.id,
            version_number=version_number,
            source_version=file.get("modifiedTime"),
            checksum_sha256=checksum,
            storage_key="pending",
            file_size_bytes=len(content),
            status="WAITING_EVENT",
        )
        session.add(version)
        await session.flush()
        safe_name = Path(str(file.get("name") or file["id"])).name.replace("/", "_")
        prefix = self.settings.drive.canonical_prefix.format(
            tenant_id=connection.tenant_id, connection_id=connection.id
        ).strip("/")
        version.storage_key = f"{prefix}/{document.id}/versions/{version.id}/{safe_name}"
        session.add(
            IngestionJob(
                tenant_id=connection.tenant_id,
                document_id=document.id,
                document_version_id=version.id,
                status="WAITING_EVENT",
                stage="RECEIVED",
            )
        )
        source.source_version = file.get("modifiedTime")
        source.metadata_json = file
        await self._replace_permissions(session, document, file.get("permissions", []))
        await session.flush()
        put_args = {
            "Bucket": self.settings.storage.bucket,
            "Key": version.storage_key,
            "Body": content,
            "ContentType": document.content_type,
            "ServerSideEncryption": self.settings.storage.server_side_encryption,
            "Metadata": {
                "tenant-id": connection.tenant_id,
                "document-version-id": version.id,
                "drive-file-id": str(file["id"]),
                "sha256": checksum,
            },
        }
        if self.settings.storage.server_side_encryption == "aws:kms":
            put_args["SSEKMSKeyId"] = self.settings.storage.kms_key_id
        await asyncio.to_thread(self.s3.put_object, **put_args)

    async def _replace_permissions(self, session, document, permissions) -> None:
        await session.execute(
            delete(DocumentPermission).where(DocumentPermission.document_id == document.id)
        )
        for permission in permissions:
            principal_type, principal_id = _permission_principal(permission, document.tenant_id)
            if principal_type == "USER" and principal_id:
                principal_id = await session.scalar(
                    select(User.id)
                    .join(TenantMembership, TenantMembership.user_id == User.id)
                    .where(
                        TenantMembership.tenant_id == document.tenant_id,
                        User.email == principal_id,
                        User.status == "ACTIVE",
                    )
                )
            if principal_id:
                session.add(
                    DocumentPermission(
                        tenant_id=document.tenant_id,
                        document_id=document.id,
                        principal_type=principal_type,
                        principal_id=principal_id,
                        capability="QUERY",
                    )
                )

    async def _publish_delete(self, session, connection, source, event) -> None:
        if source is None:
            return
        document = await session.get(Document, source.document_id)
        if document is None or document.current_version_id is None:
            return
        version = await session.get(DocumentVersion, document.current_version_id)
        if version is None:
            return
        document.status = "DELETING"
        document.deleted_at = datetime.now(UTC)
        session.add(
            IngestionJob(
                tenant_id=document.tenant_id,
                document_id=document.id,
                document_version_id=version.id,
                job_type="DELETE",
                status="WAITING_EVENT",
                stage="DELETING",
            )
        )
        await session.flush()
        payload = {
            "version": "0",
            "id": event.id,
            "detail-type": "Object Deleted",
            "source": "aws.s3",
            "time": datetime.now(UTC).isoformat(),
            "detail": {
                "bucket": {"name": self.settings.storage.bucket},
                "object": {"key": version.storage_key, "version-id": event.change_key},
            },
        }
        await asyncio.to_thread(
            self.sqs.send_message,
            QueueUrl=self.settings.event_ingestion.queue_url,
            MessageBody=json.dumps(payload),
        )


def _classify_change(change: dict[str, Any], previous: dict[str, Any] | None) -> str:
    file = change.get("file") or {}
    if change.get("removed") or file.get("trashed"):
        return "DELETE"
    if previous is None:
        return "CREATE"
    if sorted(file.get("parents", [])) != sorted(previous.get("parents", [])):
        return "MOVE"
    if sorted(file.get("permissionIds", [])) != sorted(previous.get("permissionIds", [])):
        return "PERMISSION_CHANGE"
    return "UPDATE"


def _permission_principal(permission: dict[str, Any], tenant_id: str) -> tuple[str, str | None]:
    kind = permission.get("type")
    if kind == "anyone":
        return "TENANT", tenant_id
    if kind == "group":
        return "GROUP", permission.get("emailAddress") or permission.get("id")
    if kind == "user":
        return "USER", permission.get("emailAddress")
    if kind == "domain":
        return "GROUP", permission.get("domain")
    return "USER", None


class SyncWorker:
    def __init__(self, settings: Settings, database: Database, service: DriveSyncService):
        self.settings = settings
        self.database = database
        self.service = service

    async def run_once(self) -> int:
        now = datetime.now(UTC)
        async with self.database.sessions() as session:
            connection_ids = list(
                (
                    await session.scalars(
                        select(DriveCheckpoint.connection_id)
                        .join(DriveConnection, DriveConnection.id == DriveCheckpoint.connection_id)
                        .where(
                            DriveConnection.status == "ACTIVE",
                            DriveCheckpoint.status.in_(["IDLE", "PENDING", "FAILED"]),
                            (
                                DriveCheckpoint.next_sync_at.is_(None)
                                | (DriveCheckpoint.next_sync_at <= now)
                            ),
                        )
                        .limit(self.settings.worker.batch_size)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
        for connection_id in connection_ids:
            try:
                await self.service.sync(connection_id)
                DRIVE_SYNC_RUNS.labels(service_var.get(), "succeeded").inc()
                DRIVE_SYNC_LAST_SUCCESS.labels(service_var.get()).set_to_current_time()
            except Exception:
                DRIVE_SYNC_RUNS.labels(service_var.get(), "failed").inc()
                logger.exception("Drive sync failed for %s", connection_id)
        return len(connection_ids)

    async def run_forever(self) -> None:
        while True:
            count = await self.run_once()
            if count == 0:
                await asyncio.sleep(self.settings.worker.poll_interval_seconds)


async def _main() -> None:
    settings = load_settings()
    configure_observability(settings.observability, "drive-sync")
    if not settings.drive.enabled:
        raise RuntimeError("drive.enabled must be true")
    database = Database(settings.database)
    credentials = SecretsManagerCredentialsResolver(settings)
    client = GoogleDriveClient(settings, credentials)
    service = DriveSyncService(settings, database, client)
    try:
        await SyncWorker(settings, database, service).run_forever()
    finally:
        await database.dispose()


def run() -> None:
    asyncio.run(_main())
