from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import unquote_plus

import boto3
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from rag_platform.application.db.models import (
    DocumentVersion,
    IngestionEvent,
    IngestionJob,
    IngestionReceipt,
)
from rag_platform.application.db.session import Database
from rag_platform.config import Settings, load_settings
from rag_platform.ingestion.service import IngestionService
from rag_platform.retrieval.service import RetrievalService
from rag_platform.security.rag import analyze_content
from rag_platform.workers.ingestion import IngestionWorker, ProcessingResult

logger = logging.getLogger("rag_platform.s3_event_worker")


class InvalidStorageEvent(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StorageEvent:
    event_id: str
    event_type: str
    bucket: str
    object_key: str
    object_version: str
    event_time: str | None

    @classmethod
    def from_eventbridge(cls, body: str | dict[str, Any]) -> StorageEvent:
        payload = json.loads(body) if isinstance(body, str) else body
        detail = payload.get("detail") or {}
        bucket = (detail.get("bucket") or {}).get("name")
        object_detail = detail.get("object") or {}
        event_id = payload.get("id")
        event_type = payload.get("detail-type")
        object_key = object_detail.get("key")
        if payload.get("source") != "aws.s3" or not all([event_id, event_type, bucket, object_key]):
            raise InvalidStorageEvent("Message is not a valid S3 EventBridge event")
        return cls(
            event_id=str(event_id),
            event_type=str(event_type),
            bucket=str(bucket),
            object_key=unquote_plus(str(object_key)),
            object_version=str(object_detail.get("version-id") or "unversioned"),
            event_time=payload.get("time"),
        )


@dataclass(frozen=True, slots=True)
class QueueMessage:
    message_id: str
    receipt_handle: str
    body: str
    receive_count: int


class QueueClient(Protocol):
    async def receive(self) -> list[QueueMessage]: ...

    async def acknowledge(self, receipt_handle: str) -> None: ...

    async def extend_visibility(self, receipt_handle: str) -> None: ...

    async def dlq_message_count(self) -> int: ...


class SQSQueueClient:
    def __init__(self, settings: Settings):
        self.config = settings.event_ingestion
        self.settings = settings
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client(
                "sqs",
                region_name=self.settings.storage.region,
                endpoint_url=self.settings.storage.endpoint_url,
            )
        return self._client

    async def receive(self) -> list[QueueMessage]:
        response = await asyncio.to_thread(
            self.client.receive_message,
            QueueUrl=self.config.queue_url,
            MaxNumberOfMessages=self.config.max_messages,
            WaitTimeSeconds=self.config.wait_time_seconds,
            VisibilityTimeout=self.config.visibility_timeout_seconds,
            AttributeNames=["ApproximateReceiveCount"],
        )
        return [
            QueueMessage(
                message_id=item["MessageId"],
                receipt_handle=item["ReceiptHandle"],
                body=item["Body"],
                receive_count=int(item.get("Attributes", {}).get("ApproximateReceiveCount", "1")),
            )
            for item in response.get("Messages", [])
        ]

    async def acknowledge(self, receipt_handle: str) -> None:
        await asyncio.to_thread(
            self.client.delete_message,
            QueueUrl=self.config.queue_url,
            ReceiptHandle=receipt_handle,
        )

    async def extend_visibility(self, receipt_handle: str) -> None:
        await asyncio.to_thread(
            self.client.change_message_visibility,
            QueueUrl=self.config.queue_url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=self.config.visibility_timeout_seconds,
        )

    async def dlq_message_count(self) -> int:
        if not self.config.dlq_url:
            return 0
        result = await asyncio.to_thread(
            self.client.get_queue_attributes,
            QueueUrl=self.config.dlq_url,
            AttributeNames=["ApproximateNumberOfMessages"],
        )
        return int(result.get("Attributes", {}).get("ApproximateNumberOfMessages", "0"))


class S3PipelineProcessor:
    """Concrete adapter joining S3 download to the existing parser and indexer."""

    def __init__(self, settings: Settings, s3_client: Any | None = None):
        self.settings = settings
        self.s3 = s3_client or boto3.client(
            "s3", region_name=settings.storage.region, endpoint_url=settings.storage.endpoint_url
        )

    async def process(self, job, document, version) -> ProcessingResult:
        with tempfile.TemporaryDirectory(prefix="rag-s3-") as directory:
            target = Path(directory) / "document.pdf"
            args: dict[str, Any] = {
                "Bucket": self.settings.storage.bucket,
                "Key": version.storage_key,
                "Filename": str(target),
            }
            if version.source_version:
                args["ExtraArgs"] = {"VersionId": version.source_version}
            await asyncio.to_thread(self.s3.download_file, **args)
            checksum = await asyncio.to_thread(_sha256, target)
            if checksum != version.checksum_sha256:
                raise ValueError(
                    f"Checksum mismatch: expected {version.checksum_sha256}, received {checksum}"
                )
            tenant_settings = self.settings.model_copy(update={"tenant_id": job.tenant_id})
            ingestion = IngestionService(tenant_settings)
            result = await asyncio.to_thread(
                ingestion.ingest,
                target,
                source=document.source,
                document_version=version.version_number,
                document_id=document.id,
            )
            chunks = ingestion.catalog.get_chunks(document.id)
            suspicious = [
                analysis for chunk in chunks if (analysis := analyze_content(chunk.text)).suspicious
            ]
            if suspicious:
                logger.warning(
                    "Security analysis flagged %s/%s chunks for document %s; "
                    "content remains untrusted and is isolated before generation",
                    len(suspicious),
                    len(chunks),
                    document.id,
                )
            retrieval = RetrievalService(tenant_settings, catalog=ingestion.catalog)
            indexed = await asyncio.to_thread(retrieval.index_document, document.id)
            if indexed != result.chunk_count or indexed < 1:
                raise ValueError("Post-index validation failed")
            return ProcessingResult(
                page_count=result.document.page_count,
                chunk_count=indexed,
                parser_version=result.document.parser_version or "unknown",
                chunker_version=result.document.chunker_version,
                embedding_version=tenant_settings.embedding.model_version,
            )

    async def delete(self, job, document, version) -> None:
        tenant_settings = self.settings.model_copy(update={"tenant_id": job.tenant_id})
        retrieval = RetrievalService(tenant_settings)
        await asyncio.to_thread(
            retrieval.vector_store.delete_document, document.id, document.tenant_id
        )
        if retrieval.catalog.get_document(document.id):
            await asyncio.to_thread(retrieval.catalog.delete_chunks, document.id)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class S3EventWorker:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        queue: QueueClient,
        processor: Any,
    ):
        self.settings = settings
        self.database = database
        self.queue = queue
        self.worker = IngestionWorker(settings, database, processor)

    async def _heartbeat(self, receipt_handle: str, stopped: asyncio.Event) -> None:
        interval = self.settings.event_ingestion.visibility_heartbeat_seconds
        while not stopped.is_set():
            try:
                await asyncio.wait_for(stopped.wait(), timeout=interval)
            except TimeoutError:
                await self.queue.extend_visibility(receipt_handle)

    async def _register(self, message: QueueMessage, event: StorageEvent) -> tuple[str, str]:
        if event.event_type not in self.settings.event_ingestion.accepted_event_types:
            raise InvalidStorageEvent(f"Unsupported event type: {event.event_type}")
        if event.bucket != self.settings.storage.bucket:
            raise InvalidStorageEvent("Event bucket does not match configured canonical bucket")
        if not event.object_key.startswith(self.settings.event_ingestion.accepted_prefix):
            raise InvalidStorageEvent("Object key is outside the accepted canonical prefix")
        async with self.database.sessions() as session:
            existing = await session.scalar(
                select(IngestionReceipt).where(
                    IngestionReceipt.provider == "AWS_S3",
                    IngestionReceipt.event_id == event.event_id,
                )
            )
            if existing:
                existing.receive_count = max(existing.receive_count, message.receive_count)
                await session.commit()
                return existing.id, existing.status
            version = await session.scalar(
                select(DocumentVersion).where(DocumentVersion.storage_key == event.object_key)
            )
            if version is None:
                raise InvalidStorageEvent("No document version owns this canonical object key")
            expected_job_type = "DELETE" if event.event_type == "Object Deleted" else "INGEST"
            job = await session.scalar(
                select(IngestionJob)
                .where(
                    IngestionJob.document_version_id == version.id,
                    IngestionJob.job_type == expected_job_type,
                )
                .order_by(IngestionJob.created_at.desc())
                .limit(1)
            )
            if job is None:
                raise InvalidStorageEvent("Document version has no ingestion job")
            receipt = IngestionReceipt(
                tenant_id=version.tenant_id,
                event_id=event.event_id,
                event_type=event.event_type,
                bucket=event.bucket,
                object_key=event.object_key,
                object_version=event.object_version,
                document_version_id=version.id,
                ingestion_job_id=job.id,
                sqs_message_id=message.message_id,
                receive_count=message.receive_count,
            )
            session.add(receipt)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                duplicate = await session.scalar(
                    select(IngestionReceipt).where(
                        IngestionReceipt.provider == "AWS_S3",
                        IngestionReceipt.bucket == event.bucket,
                        IngestionReceipt.object_key == event.object_key,
                        IngestionReceipt.object_version == event.object_version,
                        IngestionReceipt.event_type == event.event_type,
                    )
                )
                if duplicate is None:
                    raise
                return duplicate.id, duplicate.status
            version.source_version = (
                event.object_version if event.object_version != "unversioned" else None
            )
            if event.event_type == "Object Created":
                version.status = "RECEIVED"
            job.status = "QUEUED"
            job.stage = "RECEIVED" if event.event_type == "Object Created" else "DELETING"
            job.job_type = "INGEST" if event.event_type == "Object Created" else "DELETE"
            session.add(
                IngestionEvent(
                    tenant_id=version.tenant_id,
                    job_id=job.id,
                    stage=job.stage,
                    status="QUEUED",
                    message=f"Accepted S3 event {event.event_id}",
                    details={"object_version": event.object_version},
                )
            )
            await session.commit()
            return receipt.id, receipt.status

    async def process_message(self, message: QueueMessage) -> bool:
        try:
            event = StorageEvent.from_eventbridge(message.body)
            receipt_id, status = await self._register(message, event)
            if status == "PROCESSED":
                await self.queue.acknowledge(message.receipt_handle)
                return True
            async with self.database.sessions() as session:
                receipt = await session.get(IngestionReceipt, receipt_id)
                job_id = receipt.ingestion_job_id if receipt else None
            if not job_id:
                raise InvalidStorageEvent("Receipt has no ingestion job")
            async with self.database.sessions() as session:
                job = await session.get(IngestionJob, job_id)
                if job is None or job.attempts >= self.settings.worker.max_attempts:
                    return False
                job.status = "RUNNING"
                job.attempts += 1
                job.started_at = job.started_at or datetime.now(UTC)
                await session.commit()
            stopped = asyncio.Event()
            heartbeat = asyncio.create_task(self._heartbeat(message.receipt_handle, stopped))
            try:
                await self.worker.process_job(job_id)
            finally:
                stopped.set()
                await heartbeat
            async with self.database.sessions() as session:
                receipt = await session.get(IngestionReceipt, receipt_id)
                job = await session.get(IngestionJob, job_id)
                if receipt is None or job is None:
                    return False
                if job.status != "SUCCEEDED":
                    receipt.status = "RETRYING"
                    receipt.last_error = job.error_message
                    await session.commit()
                    return False
                receipt.status = "PROCESSED"
                receipt.processed_at = datetime.now(UTC)
                receipt.last_error = None
                await session.commit()
            await self.queue.acknowledge(message.receipt_handle)
            return True
        except Exception as exc:
            logger.exception("S3 event message failed: %s", exc)
            return False

    async def run_once(self) -> int:
        messages = await self.queue.receive()
        for message in messages:
            await self.process_message(message)
        return len(messages)

    async def run_forever(self) -> None:
        while True:
            await self.run_once()


async def _main() -> None:
    settings = load_settings()
    if not settings.event_ingestion.enabled or not settings.event_ingestion.queue_url:
        raise RuntimeError("event_ingestion.enabled and event_ingestion.queue_url are required")
    database = Database(settings.database)
    try:
        await S3EventWorker(
            settings, database, SQSQueueClient(settings), S3PipelineProcessor(settings)
        ).run_forever()
    finally:
        await database.dispose()


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
