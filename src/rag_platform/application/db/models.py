from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("ten"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE", index=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("usr"))
    external_subject: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE", index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TenantMembership(Base, TimestampMixin):
    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_memberships_tenant_user"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("mem"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="VIEWER", index=True)
    groups: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("doc"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    current_version_id: Mapped[str | None] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="manual", index=True)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RECEIVED", index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentVersion(Base, TimestampMixin):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "version_number", name="uq_document_versions_document_version"
        ),
        UniqueConstraint(
            "tenant_id", "checksum_sha256", name="uq_document_versions_tenant_checksum"
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("ver"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(255))
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING_UPLOAD", index=True
    )
    parser_version: Mapped[str | None] = mapped_column(String(100))
    chunker_version: Mapped[str | None] = mapped_column(String(100))
    embedding_version: Mapped[str | None] = mapped_column(String(200))
    active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentPermission(Base, TimestampMixin):
    __tablename__ = "document_permissions"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "principal_type",
            "principal_id",
            "capability",
            name="uq_document_permissions_document_principal_capability",
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("acl"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    principal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    capability: Mapped[str] = mapped_column(String(32), nullable=False, default="QUERY")


class DocumentSource(Base, TimestampMixin):
    __tablename__ = "document_sources"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_type",
            "source_file_id",
            name="uq_document_sources_tenant_source_file",
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("src"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_file_id: Mapped[str] = mapped_column(String(512), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(255))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class IngestionJob(Base, TimestampMixin):
    __tablename__ = "ingestion_jobs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("job"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    job_type: Mapped[str] = mapped_column(String(32), nullable=False, default="INGEST")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED", index=True)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="RECEIVED")
    progress_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    worker_id: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IngestionEvent(Base):
    __tablename__ = "ingestion_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("evt"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    progress_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    message: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class IngestionReceipt(Base, TimestampMixin):
    """Durable inbox record used to make at-least-once queue delivery idempotent."""

    __tablename__ = "ingestion_receipts"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_ingestion_receipts_provider_event_id"),
        UniqueConstraint(
            "provider",
            "bucket",
            "object_key",
            "object_version",
            "event_type",
            name="uq_ingestion_receipts_provider_object_version_event",
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("rcp"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="AWS_S3")
    event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    object_version: Mapped[str] = mapped_column(String(1024), nullable=False, default="unversioned")
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    ingestion_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("ingestion_jobs.id", ondelete="SET NULL"), index=True
    )
    sqs_message_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RECEIVED", index=True)
    receive_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("chat"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="New conversation")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("msg"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class AnswerTrace(Base):
    __tablename__ = "answer_traces"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("trace"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[str] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), unique=True
    )
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(200), nullable=False)
    embedding_version: Mapped[str | None] = mapped_column(String(200))
    retrieved_chunk_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_metadata: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    generation_parameters: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    retrieval_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    generation_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    total_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DriveConnection(Base, TimestampMixin):
    __tablename__ = "drive_connections"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("drv"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="GOOGLE_DRIVE")
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    secret_reference: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")


class DriveSyncState(Base, TimestampMixin):
    __tablename__ = "drive_sync_state"
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("drive_connections.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    cursor: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="IDLE")
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class DriveCheckpoint(Base, TimestampMixin):
    """Phase 10 checkpoint; kept separate to preserve the Phase 5 schema."""

    __tablename__ = "drive_checkpoints"
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("drive_connections.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    last_change_token: Mapped[str | None] = mapped_column(Text)
    last_success_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="IDLE", index=True)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credentials_reference: Mapped[str] = mapped_column(String(1024), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)


class DriveChangeEvent(Base, TimestampMixin):
    __tablename__ = "drive_change_events"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "change_key", name="uq_drive_change_events_connection_change"
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("dch"))
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("drive_connections.id", ondelete="CASCADE"), index=True
    )
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    change_key: Mapped[str] = mapped_column(String(512), nullable=False)
    file_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("aud"))
    tenant_id: Mapped[str | None] = mapped_column(String(64), index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(100), index=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class ModelVersion(Base, TimestampMixin):
    __tablename__ = "model_versions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("mdl"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_embedding_profiles_name_version"),
    )


class PromptVersion(Base, TimestampMixin):
    __tablename__ = "prompt_versions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("prm"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (UniqueConstraint("name", "version", name="uq_parser_profiles_name_version"),)


class EmbeddingVersion(Base, TimestampMixin):
    __tablename__ = "embedding_versions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("emb"))
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(200), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    collection: Mapped[str] = mapped_column(String(200), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (
        UniqueConstraint(
            "model", "version", "collection", name="uq_vector_collections_model_version_collection"
        ),
    )


Index(
    "ix_documents_tenant_status_updated", Document.tenant_id, Document.status, Document.updated_at
)
Index("ix_jobs_status_created", IngestionJob.status, IngestionJob.created_at)
Index("ix_receipts_status_created", IngestionReceipt.status, IngestionReceipt.created_at)
Index("ix_drive_checkpoint_due", DriveCheckpoint.status, DriveCheckpoint.next_sync_at)
Index("ix_audit_tenant_created", AuditEvent.tenant_id, AuditEvent.created_at)
