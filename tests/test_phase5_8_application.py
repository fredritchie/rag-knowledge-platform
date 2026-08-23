from __future__ import annotations

import asyncio
import base64
import time
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from rag_platform.api.app import create_application
from rag_platform.api.auth import CognitoJWTVerifier, RequestContext, request_context
from rag_platform.api.errors import ForbiddenError
from rag_platform.application.db.models import (
    Base,
    Document,
    DocumentPermission,
    DocumentVersion,
    IngestionJob,
    Tenant,
    TenantMembership,
    User,
)
from rag_platform.application.db.session import Database
from rag_platform.config import Settings
from rag_platform.workers.ingestion import IngestionWorker, ProcessingResult


class FakeStorage:
    def create_upload(self, storage_key: str, content_type: str):
        return {
            "url": "https://uploads.example.test",
            "fields": {"key": storage_key, "Content-Type": content_type},
        }


class FakeResult:
    def __init__(self, document_id: str):
        self.document_id = document_id

    def model_dump(self):
        return {"document_id": self.document_id, "chunk_id": "chk_allowed", "score": 1.0}


class CapturingRetrieval:
    def __init__(self):
        self.document_ids: set[str] | None = None

    def search(self, query, *, top_k=None, mode=None, document_ids=None):
        self.document_ids = document_ids
        return [FakeResult(next(iter(document_ids)))], 1.0


class SuccessfulProcessor:
    async def process(self, job, document, version):
        return ProcessingResult(10, 20, "pymupdf-test", "chunk-v1", "embed-v1")

    async def delete(self, job, document, version):
        return None


def _settings(tmp_path: Path) -> Settings:
    return Settings.model_validate(
        {
            "data_dir": tmp_path / "local",
            "database": {"url": f"sqlite+aiosqlite:///{tmp_path / 'app.sqlite3'}"},
            "health": {
                "check_database": True,
                "check_qdrant": False,
                "check_ollama": False,
            },
            "api": {"rate_limit_enabled": False},
            "auth": {
                "issuer": "https://issuer.example.test/pool",
                "audience": "client-id",
            },
            "storage": {"bucket": "test-bucket"},
        }
    )


async def _prepare(database: Database) -> None:
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with database.sessions() as session:
        tenant_a = Tenant(id="ten_a", name="Tenant A", slug="tenant-a")
        tenant_b = Tenant(id="ten_b", name="Tenant B", slug="tenant-b")
        user = User(id="usr_a", external_subject="subject-a", email="a@example.test")
        session.add_all([tenant_a, tenant_b, user])
        session.add(
            TenantMembership(
                id="mem_a", tenant_id="ten_a", user_id="usr_a", role="VIEWER", groups=[]
            )
        )
        await session.commit()


def _context(role: str = "VIEWER") -> RequestContext:
    return RequestContext(
        user_id="usr_a",
        external_subject="subject-a",
        tenant_id="ten_a",
        email="a@example.test",
        role=role,
        groups=[],
    )


def _application(tmp_path: Path, role: str = "VIEWER"):
    settings = _settings(tmp_path)
    database = Database(settings.database)
    asyncio.run(_prepare(database))
    app = create_application(settings, database=database, storage=FakeStorage())
    app.dependency_overrides[request_context] = lambda: _context(role)
    return app, database


def test_liveness_openapi_request_ids_and_readiness(tmp_path: Path) -> None:
    app, _ = _application(tmp_path)
    with TestClient(app) as client:
        live = client.get("/live", headers={"X-Request-ID": "req_test"})
        assert live.status_code == 200
        assert live.headers["X-Request-ID"] == "req_test"
        assert client.get("/ready").status_code == 200
        schema = client.get("/openapi.json").json()
        assert "/api/v1/documents/uploads" in schema["paths"]


def test_missing_jwt_is_rejected(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    database = Database(settings.database)
    asyncio.run(_prepare(database))
    app = create_application(settings, database=database, storage=FakeStorage())
    with TestClient(app) as client:
        response = client.get("/api/v1/auth/me")
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_viewer_cannot_delete_or_manage_users(tmp_path: Path) -> None:
    app, database = _application(tmp_path, "VIEWER")

    async def seed():
        async with database.sessions() as session:
            session.add(
                Document(
                    id="doc_a",
                    tenant_id="ten_a",
                    owner_id="usr_a",
                    filename="a.pdf",
                    content_type="application/pdf",
                    status="ACTIVE",
                )
            )
            await session.commit()

    asyncio.run(seed())
    with TestClient(app) as client:
        assert client.delete("/api/v1/documents/doc_a").status_code == 403
        assert client.get("/api/v1/users").status_code == 403


def test_editor_cannot_manage_users(tmp_path: Path) -> None:
    app, _ = _application(tmp_path, "EDITOR")
    with TestClient(app) as client:
        assert client.get("/api/v1/users").status_code == 403


def test_acl_is_applied_before_vector_search(tmp_path: Path) -> None:
    app, database = _application(tmp_path)

    async def seed():
        async with database.sessions() as session:
            allowed = Document(
                id="doc_allowed",
                tenant_id="ten_a",
                owner_id="someone_else",
                filename="allowed.pdf",
                content_type="application/pdf",
                status="ACTIVE",
            )
            denied = Document(
                id="doc_denied",
                tenant_id="ten_a",
                owner_id="someone_else",
                filename="denied.pdf",
                content_type="application/pdf",
                status="ACTIVE",
            )
            other = Document(
                id="doc_other_tenant",
                tenant_id="ten_b",
                owner_id="someone_else",
                filename="other.pdf",
                content_type="application/pdf",
                status="ACTIVE",
            )
            session.add_all([allowed, denied, other])
            session.add(
                DocumentPermission(
                    tenant_id="ten_a",
                    document_id="doc_allowed",
                    principal_type="TENANT",
                    principal_id="ten_a",
                    capability="QUERY",
                )
            )
            await session.commit()

    asyncio.run(seed())
    retrieval = CapturingRetrieval()
    app.state.get_retrieval = lambda tenant_id: retrieval
    with TestClient(app) as client:
        response = client.post("/api/v1/search", json={"query": "allowed"})
    assert response.status_code == 200, response.text
    assert retrieval.document_ids == {"doc_allowed"}
    assert response.json()["authorized_document_count"] == 1


def test_upload_update_keeps_old_version_active_until_worker_success(tmp_path: Path) -> None:
    app, database = _application(tmp_path, "EDITOR")
    payload = {
        "filename": "policy.pdf",
        "content_type": "application/pdf",
        "file_size_bytes": 100,
        "checksum_sha256": "a" * 64,
    }
    with TestClient(app) as client:
        first = client.post("/api/v1/documents/uploads", json=payload)
        assert first.status_code == 201, first.text
        created = first.json()
        completed = client.post(
            f"/api/v1/documents/{created['document_id']}/upload-complete",
            json={"document_version_id": created["document_version_id"]},
        )
        assert completed.status_code == 202

        async def activate_first():
            async with database.sessions() as session:
                doc = await session.get(Document, created["document_id"])
                version = await session.get(DocumentVersion, created["document_version_id"])
                doc.current_version_id = version.id
                doc.status = "ACTIVE"
                version.status = "ACTIVE"
                await session.commit()

        asyncio.run(activate_first())
        payload.update(checksum_sha256="b" * 64, document_id=created["document_id"])
        second = client.post("/api/v1/documents/uploads", json=payload)
        assert second.status_code == 201, second.text

        async def verify_pending():
            async with database.sessions() as session:
                doc = await session.get(Document, created["document_id"])
                new_version = await session.get(
                    DocumentVersion, second.json()["document_version_id"]
                )
                return doc.current_version_id, new_version.status

        current_id, new_status = asyncio.run(verify_pending())
        assert current_id == created["document_version_id"]
        assert new_status == "PENDING_UPLOAD"


def test_worker_atomically_activates_successful_replacement(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    database = Database(settings.database)
    asyncio.run(_prepare(database))

    async def seed():
        async with database.sessions() as session:
            document = Document(
                id="doc_update",
                tenant_id="ten_a",
                owner_id="usr_a",
                current_version_id="ver_old",
                filename="policy.pdf",
                content_type="application/pdf",
                status="ACTIVE",
            )
            old = DocumentVersion(
                id="ver_old",
                tenant_id="ten_a",
                document_id="doc_update",
                version_number=1,
                checksum_sha256="1" * 64,
                storage_key="old",
                file_size_bytes=1,
                status="ACTIVE",
            )
            new = DocumentVersion(
                id="ver_new",
                tenant_id="ten_a",
                document_id="doc_update",
                version_number=2,
                checksum_sha256="2" * 64,
                storage_key="new",
                file_size_bytes=2,
                status="RECEIVED",
            )
            job = IngestionJob(
                id="job_update",
                tenant_id="ten_a",
                document_id="doc_update",
                document_version_id="ver_new",
                status="QUEUED",
            )
            session.add_all([document, old, new, job])
            await session.commit()

    asyncio.run(seed())
    worker = IngestionWorker(settings, database, SuccessfulProcessor())
    assert asyncio.run(worker.run_once()) == 1

    async def verify():
        async with database.sessions() as session:
            doc = await session.get(Document, "doc_update")
            old = await session.get(DocumentVersion, "ver_old")
            new = await session.get(DocumentVersion, "ver_new")
            job = await session.get(IngestionJob, "job_update")
            return doc, old, new, job

    doc, old, new, job = asyncio.run(verify())
    assert doc.current_version_id == "ver_new"
    assert old.status == "INACTIVE"
    assert new.status == "ACTIVE"
    assert new.chunk_count == 20
    assert job.status == "SUCCEEDED"
    asyncio.run(database.dispose())


def _b64(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def test_expired_and_modified_jwts_are_rejected(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()
    jwk = {"kty": "RSA", "kid": "test", "use": "sig", "n": _b64(numbers.n), "e": _b64(numbers.e)}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"keys": [jwk]}))
    client = httpx.AsyncClient(transport=transport)
    verifier = CognitoJWTVerifier(settings.auth, client)
    now = int(time.time())
    claims = {
        "sub": "subject-a",
        "aud": settings.auth.audience,
        "iss": settings.auth.issuer,
        "iat": now - 120,
        "exp": now - 60,
        "custom:tenant_id": "ten_a",
    }
    expired = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test"})
    with pytest.raises(ForbiddenError):
        asyncio.run(verifier.verify(expired))
    valid = jwt.encode(
        {**claims, "iat": now, "exp": now + 300},
        key,
        algorithm="RS256",
        headers={"kid": "test"},
    )
    modified = valid[:-2] + ("aa" if valid[-2:] != "aa" else "bb")
    with pytest.raises(ForbiddenError):
        asyncio.run(verifier.verify(modified))
    asyncio.run(client.aclose())
