from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from rag_platform.api.app import create_application
from rag_platform.api.auth import RequestContext, request_context
from rag_platform.application.db.models import (
    Base,
    Document,
    DocumentVersion,
    IngestionJob,
    IngestionReceipt,
    Tenant,
    TenantMembership,
    User,
)
from rag_platform.application.db.session import Database
from rag_platform.config import Settings
from rag_platform.workers.ingestion import ProcessingResult
from rag_platform.workers.s3_events import QueueMessage, S3EventWorker, StorageEvent
from rag_platform.workers.sync import _classify_change


class FakeStorage:
    def create_upload(self, storage_key: str, content_type: str):
        return {"url": "https://upload.test", "fields": {"key": storage_key}}


class FakeQueue:
    def __init__(self):
        self.acknowledged: list[str] = []

    async def receive(self):
        return []

    async def acknowledge(self, receipt_handle: str):
        self.acknowledged.append(receipt_handle)

    async def extend_visibility(self, receipt_handle: str):
        return None

    async def dlq_message_count(self):
        return 0


class CountingProcessor:
    def __init__(self):
        self.calls = 0

    async def process(self, job, document, version):
        self.calls += 1
        return ProcessingResult(2, 4, "parser-v1", "chunk-v1", "embed-v1")

    async def delete(self, job, document, version):
        self.calls += 1


def _settings(tmp_path: Path) -> Settings:
    return Settings.model_validate(
        {
            "data_dir": tmp_path / "local",
            "database": {"url": f"sqlite+aiosqlite:///{tmp_path / 'events.sqlite3'}"},
            "storage": {"bucket": "canonical-bucket"},
            "event_ingestion": {"enabled": True, "queue_url": "queue"},
            "api": {"rate_limit_enabled": False},
            "health": {"check_qdrant": False, "check_ollama": False},
        }
    )


async def _seed(database: Database) -> None:
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with database.sessions() as session:
        session.add_all(
            [
                Tenant(id="ten_a", name="Tenant", slug="tenant"),
                User(id="usr_a", external_subject="sub", email="admin@example.test"),
                TenantMembership(
                    id="mem_a", tenant_id="ten_a", user_id="usr_a", role="ADMIN", groups=[]
                ),
                Document(
                    id="doc_a",
                    tenant_id="ten_a",
                    owner_id="usr_a",
                    filename="policy.pdf",
                    content_type="application/pdf",
                    status="PENDING_UPLOAD",
                ),
                DocumentVersion(
                    id="ver_a",
                    tenant_id="ten_a",
                    document_id="doc_a",
                    version_number=1,
                    checksum_sha256="a" * 64,
                    storage_key="tenants/ten_a/documents/doc_a/policy.pdf",
                    file_size_bytes=10,
                    status="WAITING_EVENT",
                ),
                IngestionJob(
                    id="job_a",
                    tenant_id="ten_a",
                    document_id="doc_a",
                    document_version_id="ver_a",
                    status="WAITING_EVENT",
                ),
            ]
        )
        await session.commit()


def _event(event_id: str = "event-1") -> str:
    return json.dumps(
        {
            "version": "0",
            "id": event_id,
            "detail-type": "Object Created",
            "source": "aws.s3",
            "time": "2026-08-23T00:00:00Z",
            "detail": {
                "bucket": {"name": "canonical-bucket"},
                "object": {
                    "key": "tenants/ten_a/documents/doc_a/policy.pdf",
                    "version-id": "s3-version-1",
                },
            },
        }
    )


def test_eventbridge_parser_preserves_idempotency_fields() -> None:
    event = StorageEvent.from_eventbridge(_event())
    assert event.event_id == "event-1"
    assert event.object_version == "s3-version-1"
    assert event.object_key.endswith("policy.pdf")


def test_duplicate_s3_event_is_acknowledged_without_reprocessing(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    database = Database(settings.database)
    asyncio.run(_seed(database))
    queue = FakeQueue()
    processor = CountingProcessor()
    worker = S3EventWorker(settings, database, queue, processor)
    first = QueueMessage("msg-1", "handle-1", _event(), 1)
    duplicate = QueueMessage("msg-2", "handle-2", _event(), 2)
    assert asyncio.run(worker.process_message(first)) is True
    assert asyncio.run(worker.process_message(duplicate)) is True
    assert processor.calls == 1
    assert queue.acknowledged == ["handle-1", "handle-2"]

    async def receipt_state():
        async with database.sessions() as session:
            receipt = await session.get(IngestionReceipt, "rcp_missing")
            rows = list((await session.scalars(IngestionReceipt.__table__.select())).all())
            return receipt, rows

    _, rows = asyncio.run(receipt_state())
    assert len(rows) == 1
    asyncio.run(database.dispose())


def test_drive_change_classification_handles_all_required_actions() -> None:
    previous = {"parents": ["old"], "permissionIds": ["one"]}
    assert _classify_change({"removed": True}, previous) == "DELETE"
    assert _classify_change({"file": {"id": "1"}}, None) == "CREATE"
    assert _classify_change({"file": {"parents": ["new"]}}, previous) == "MOVE"
    permission = {"file": {"parents": ["old"], "permissionIds": ["two"]}}
    assert _classify_change(permission, previous) == "PERMISSION_CHANGE"
    unchanged = {"file": {"parents": ["old"], "permissionIds": ["one"]}}
    assert _classify_change(unchanged, previous) == "UPDATE"


def test_admin_can_control_drive_connection_and_view_queue_health(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    database = Database(settings.database)
    asyncio.run(_seed(database))
    app = create_application(settings, database=database, storage=FakeStorage())
    app.dependency_overrides[request_context] = lambda: RequestContext(
        user_id="usr_a",
        external_subject="sub",
        tenant_id="ten_a",
        email="admin@example.test",
        role="ADMIN",
        groups=[],
    )
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/admin/drive/connections",
            json={"display_name": "Standards", "credentials_reference": "secret/drive"},
        )
        assert created.status_code == 201, created.text
        connection_id = created.json()["connection_id"]
        assert client.post(
            f"/api/v1/admin/drive/connections/{connection_id}/pause"
        ).json()["status"] == "PAUSED"
        assert client.post(
            f"/api/v1/admin/drive/connections/{connection_id}/resume"
        ).json()["status"] == "ACTIVE"
        deleted = client.delete(f"/api/v1/admin/drive/connections/{connection_id}/link")
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["status"] == "DELETED"
        assert client.get("/api/v1/admin/drive/connections").json() == []
        health = client.get("/api/v1/admin/ingestion/queue-health")
        assert health.status_code == 200
        assert health.json()["enabled"] is True
