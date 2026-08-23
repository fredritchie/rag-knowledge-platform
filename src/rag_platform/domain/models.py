from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from rag_platform.domain.states import DocumentStatus, IssueCode, IssueSeverity


def utc_now() -> datetime:
    return datetime.now(UTC)


class ValidationIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: IssueCode
    severity: IssueSeverity
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class DocumentRecord(BaseModel):
    document_id: str
    tenant_id: str = "default"
    filename: str
    source: str = "manual"
    source_file_id: str | None = None
    source_version: str | None = None
    document_version: int = 1
    checksum_sha256: str
    content_type: str = "application/pdf"
    file_size_bytes: int
    page_count: int = 0
    extracted_characters: int = 0
    average_chars_per_page: float = 0.0
    title: str | None = None
    author: str | None = None
    subject: str | None = None
    keywords: str | None = None
    status: DocumentStatus = DocumentStatus.RECEIVED
    parser: str = "pymupdf"
    parser_version: str
    chunker_version: str = "paragraph-char-v1"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ChunkRecord(BaseModel):
    chunk_id: str
    tenant_id: str = "default"
    document_id: str
    filename: str
    page: int
    chunk_index: int
    page_chunk_index: int
    text: str
    source: str
    document_version: int
    checksum_sha256: str
    chunker_version: str
    char_start: int
    char_end: int
    created_at: datetime = Field(default_factory=utc_now)


class SearchResult(BaseModel):
    chunk_id: str
    tenant_id: str
    document_id: str
    document_version: int
    source: str
    page: int
    filename: str
    chunk_index: int
    embedding_model_version: str
    chunker_version: str
    text: str
    score: float
    dense_score: float | None = None
    lexical_score: float | None = None
    reranker_score: float | None = None


class Citation(BaseModel):
    document_id: str
    filename: str
    page: int
    chunk_id: str
    score: float


class RAGResponse(BaseModel):
    answer: str
    sources: list[Citation]
    model: str
    prompt_version: str
    latency_ms: float
    retrieval_latency_ms: float
    generation_latency_ms: float
    retrieved_chunk_ids: list[str]
    generation_parameters: dict[str, Any]


class RetrievalEvaluationItem(BaseModel):
    question: str
    expected_document: str
    expected_pages: list[int] = Field(default_factory=list)
    expected_answer: str | None = None
    should_answer: bool = True
