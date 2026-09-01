from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict[str, Any] = Field(default_factory=dict)


class PageMeta(BaseModel):
    limit: int
    offset: int
    total: int


class TenantOut(ORMModel):
    id: str
    name: str
    slug: str
    status: str
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=3, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class UserOut(ORMModel):
    id: str
    external_subject: str
    email: str
    display_name: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class MembershipOut(ORMModel):
    id: str
    tenant_id: str
    user_id: str
    role: str
    groups: list[str]
    active: bool


class MembershipCreate(BaseModel):
    external_subject: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)
    display_name: str | None = Field(None, max_length=200)
    role: Literal["ADMIN", "EDITOR", "VIEWER"] = "VIEWER"
    groups: list[str] = Field(default_factory=list)


class UserInvitationCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str | None = Field(None, max_length=200)
    role: Literal["ADMIN", "EDITOR", "VIEWER"] = "VIEWER"


class CurrentUser(BaseModel):
    user_id: str
    external_subject: str
    tenant_id: str
    email: str | None
    role: str
    groups: list[str]


class UploadAuthorizationRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=512)
    content_type: str = Field(default="application/pdf", max_length=255)
    file_size_bytes: int = Field(gt=0)
    checksum_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    source: str = Field(default="manual", max_length=64)
    source_file_id: str | None = Field(None, max_length=512)
    source_version: str | None = Field(None, max_length=255)
    document_id: str | None = None


class UploadAuthorizationResponse(BaseModel):
    document_id: str
    document_version_id: str
    version_number: int
    ingestion_job_id: str
    storage_key: str
    upload_url: str
    upload_fields: dict[str, str]
    expires_in_seconds: int


class UploadCompleteRequest(BaseModel):
    document_version_id: str


class DocumentOut(ORMModel):
    id: str
    tenant_id: str
    owner_id: str
    current_version_id: str | None
    filename: str
    source: str
    content_type: str
    status: str
    created_at: datetime
    updated_at: datetime


class DocumentVersionOut(ORMModel):
    id: str
    document_id: str
    version_number: int
    checksum_sha256: str
    storage_key: str
    file_size_bytes: int
    page_count: int
    chunk_count: int
    status: str
    parser_version: str | None
    chunker_version: str | None
    embedding_version: str | None
    created_at: datetime
    updated_at: datetime


class DocumentList(BaseModel):
    items: list[DocumentOut]
    page: PageMeta


class DocumentDetail(BaseModel):
    document: DocumentOut
    versions: list[DocumentVersionOut]
    permissions: list[dict[str, Any]]
    ingestion_jobs: list[dict[str, Any]]


class PermissionCreate(BaseModel):
    principal_type: Literal["TENANT", "USER", "GROUP"]
    principal_id: str = Field(min_length=1, max_length=255)
    capability: Literal["QUERY", "MANAGE"] = "QUERY"


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int | None = Field(None, ge=1, le=100)
    mode: Literal["dense", "hybrid", "hybrid_rerank"] | None = None


class SearchResponse(BaseModel):
    query: str
    latency_ms: float
    authorized_document_count: int
    results: list[dict[str, Any]]


class ChatSessionCreate(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=300)


class ChatSessionOut(ORMModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=16000)


class ChatMessageOut(ORMModel):
    id: str
    role: str
    content: str
    created_at: datetime


class ChatAnswer(BaseModel):
    user_message: ChatMessageOut
    assistant_message: ChatMessageOut
    answer: dict[str, Any]


class DashboardSummary(BaseModel):
    total_documents: int
    indexed_documents: int
    failed_documents: int
    recent_queries: int
    recent_uploads: int
    drive_sync_status: str
    system_status: str


class DriveConnectionCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    credentials_reference: str = Field(min_length=1, max_length=1024)


class DriveConnectionOut(BaseModel):
    connection_id: str
    display_name: str
    status: str
    sync_status: str
    last_change_token_present: bool
    last_success_time: datetime | None
    next_sync_at: datetime | None
    error_count: int
    last_error: str | None


class DriveErrorOut(BaseModel):
    id: str
    file_id: str
    action: str
    error: str
    created_at: datetime


class QueueHealthOut(BaseModel):
    enabled: bool
    dlq_messages: int | None
    alert: bool
    receipt_counts: dict[str, int]


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, str] = Field(default_factory=dict)
