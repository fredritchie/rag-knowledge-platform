from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pymupdf

from rag_platform.config import Settings
from rag_platform.domain.models import DocumentRecord, ValidationIssue
from rag_platform.domain.state_machine import ensure_transition
from rag_platform.domain.states import DocumentStatus, IssueCode, IssueSeverity
from rag_platform.ingestion.chunker import ChunkingConfig, build_chunks
from rag_platform.ingestion.extractor import extract_pages
from rag_platform.ingestion.quality import assess_extracted_text
from rag_platform.ingestion.validator import preflight_validate, sha256_file
from rag_platform.storage.sqlite import SQLiteCatalog


class IngestionError(RuntimeError):
    pass


class DocumentNotFoundError(IngestionError):
    pass


class DuplicateDocumentError(IngestionError):
    def __init__(self, existing_document_id: str):
        self.existing_document_id = existing_document_id
        super().__init__(f"Duplicate PDF; already ingested as {existing_document_id}")


class IngestionRejected(IngestionError):
    def __init__(self, document_id: str | None, issues: list[ValidationIssue]):
        self.document_id = document_id
        self.issues = issues
        codes = ", ".join(
            issue.code.value for issue in issues if issue.severity == IssueSeverity.ERROR
        )
        super().__init__(f"Document rejected: {codes or 'validation error'}")


@dataclass(slots=True)
class IngestionResult:
    document: DocumentRecord
    chunk_count: int
    issues: list[ValidationIssue]
    stored_path: Path


class IngestionService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.settings.ensure_directories()
        self.catalog = SQLiteCatalog(self.settings.database_path)

    def validate(self, path: Path) -> tuple[list[ValidationIssue], dict[str, object]]:
        result = preflight_validate(path, max_pages=self.settings.max_pages)
        details: dict[str, object] = {
            "checksum_sha256": result.checksum_sha256,
            "file_size_bytes": result.file_size_bytes,
            "page_count": result.page_count,
            "metadata": result.metadata,
        }
        if result.has_errors:
            return result.issues, details

        try:
            pages = extract_pages(path)
        except Exception as exc:
            return [
                *result.issues,
                ValidationIssue(
                    code=IssueCode.EXTRACTION_ERROR,
                    severity=IssueSeverity.ERROR,
                    message="Text extraction failed.",
                    details={"error": str(exc)},
                ),
            ], details

        quality_issues, useful_chars, average = assess_extracted_text(
            pages,
            min_avg_chars_per_page=self.settings.min_avg_chars_per_page,
            max_replacement_char_ratio=self.settings.max_replacement_char_ratio,
        )
        details.update(
            extracted_characters=useful_chars,
            average_chars_per_page=average,
        )
        return [*result.issues, *quality_issues], details

    def ingest(
        self,
        path: Path,
        *,
        source: str = "manual",
        document_version: int = 1,
        document_id: str | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> IngestionResult:
        path = path.expanduser().resolve()
        # Hash early so duplicate detection avoids parsing an already-known document.
        if path.exists() and path.is_file() and path.stat().st_size > 0:
            checksum = sha256_file(path)
            existing = self.catalog.find_by_checksum(checksum, tenant_id=self.settings.tenant_id)
            if existing:
                if document_id and existing.document_id == document_id:
                    issues = self.catalog.get_issues(document_id)
                    chunks = self.catalog.get_chunks(document_id)
                    stored_path = self.catalog.get_stored_path(document_id)
                    if stored_path:
                        return IngestionResult(
                            document=existing,
                            chunk_count=len(chunks),
                            issues=issues,
                            stored_path=Path(stored_path),
                        )
                raise DuplicateDocumentError(existing.document_id)

        preflight = preflight_validate(path, max_pages=self.settings.max_pages)
        if (
            not preflight.checksum_sha256
            and path.exists()
            and path.is_file()
            and path.stat().st_size > 0
        ):
            preflight.checksum_sha256 = sha256_file(path)

        document_id = document_id or "doc_" + uuid.uuid4().hex[:20]
        now = datetime.now(UTC)
        document = DocumentRecord(
            document_id=document_id,
            tenant_id=self.settings.tenant_id,
            filename=path.name,
            source=source,
            document_version=document_version,
            checksum_sha256=preflight.checksum_sha256 or "unavailable",
            file_size_bytes=preflight.file_size_bytes,
            page_count=preflight.page_count,
            title=preflight.metadata.get("title"),
            author=preflight.metadata.get("author"),
            subject=preflight.metadata.get("subject"),
            keywords=preflight.metadata.get("keywords"),
            parser_version=pymupdf.__version__,
            chunker_version=self.settings.chunking.version,
            created_at=now,
            updated_at=now,
        )
        self.catalog.upsert_document(document)
        self.catalog.replace_issues(document_id, preflight.issues)

        if preflight.has_errors:
            ensure_transition(document.status, DocumentStatus.FAILED_PARSE)
            document.status = DocumentStatus.FAILED_PARSE
            document.updated_at = datetime.now(UTC)
            self.catalog.upsert_document(document)
            raise IngestionRejected(document_id, preflight.issues)

        ensure_transition(document.status, DocumentStatus.PARSING)
        document.status = DocumentStatus.PARSING
        document.updated_at = datetime.now(UTC)
        self.catalog.upsert_document(document)

        try:
            pages = extract_pages(path)
        except Exception as exc:
            issue = ValidationIssue(
                code=IssueCode.EXTRACTION_ERROR,
                severity=IssueSeverity.ERROR,
                message="Text extraction failed.",
                details={"error": str(exc)},
            )
            all_issues = [*preflight.issues, issue]
            self.catalog.replace_issues(document_id, all_issues)
            ensure_transition(document.status, DocumentStatus.FAILED_PARSE)
            document.status = DocumentStatus.FAILED_PARSE
            document.updated_at = datetime.now(UTC)
            self.catalog.upsert_document(document)
            raise IngestionRejected(document_id, all_issues) from exc

        quality_issues, useful_chars, average = assess_extracted_text(
            pages,
            min_avg_chars_per_page=self.settings.min_avg_chars_per_page,
            max_replacement_char_ratio=self.settings.max_replacement_char_ratio,
        )
        all_issues = [*preflight.issues, *quality_issues]
        document.extracted_characters = useful_chars
        document.average_chars_per_page = average
        document.updated_at = datetime.now(UTC)
        self.catalog.upsert_document(document)
        self.catalog.replace_issues(document_id, all_issues)

        if any(issue.severity == IssueSeverity.ERROR for issue in all_issues):
            ensure_transition(document.status, DocumentStatus.FAILED_PARSE)
            document.status = DocumentStatus.FAILED_PARSE
            document.updated_at = datetime.now(UTC)
            self.catalog.upsert_document(document)
            raise IngestionRejected(document_id, all_issues)

        ensure_transition(document.status, DocumentStatus.CHUNKING)
        document.status = DocumentStatus.CHUNKING
        document.updated_at = datetime.now(UTC)
        self.catalog.upsert_document(document)

        config = ChunkingConfig(
            chunk_size=chunk_size or self.settings.chunk_size,
            overlap=self.settings.chunk_overlap if chunk_overlap is None else chunk_overlap,
        )
        chunks = build_chunks(document, pages, config)
        if not chunks:
            issue = ValidationIssue(
                code=IssueCode.ZERO_EXTRACTED_TEXT,
                severity=IssueSeverity.ERROR,
                message="No chunks were created from the extracted document text.",
            )
            all_issues.append(issue)
            self.catalog.replace_issues(document_id, all_issues)
            ensure_transition(document.status, DocumentStatus.FAILED_PARSE)
            document.status = DocumentStatus.FAILED_PARSE
            document.updated_at = datetime.now(UTC)
            self.catalog.upsert_document(document)
            raise IngestionRejected(document_id, all_issues)

        self.catalog.replace_chunks(document_id, chunks)

        ensure_transition(document.status, DocumentStatus.VALIDATING)
        document.status = DocumentStatus.VALIDATING
        document.updated_at = datetime.now(UTC)
        self.catalog.upsert_document(document)

        target_dir = self.settings.documents_dir / document_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{document.checksum_sha256}.pdf"
        shutil.copy2(path, target)
        self.catalog.upsert_document(document, stored_path=str(target))

        ensure_transition(document.status, DocumentStatus.ACTIVE)
        document.status = DocumentStatus.ACTIVE
        document.updated_at = datetime.now(UTC)
        self.catalog.upsert_document(document, stored_path=str(target))

        return IngestionResult(
            document=document,
            chunk_count=len(chunks),
            issues=all_issues,
            stored_path=target,
        )

    def inspect(
        self, document_id: str
    ) -> tuple[DocumentRecord, list[ValidationIssue], int, str | None]:
        document = self.catalog.get_document(document_id)
        if not document or document.tenant_id != self.settings.tenant_id:
            raise DocumentNotFoundError(document_id)
        issues = self.catalog.get_issues(document_id)
        chunk_count = len(self.catalog.get_chunks(document_id))
        stored_path = self.catalog.get_stored_path(document_id)
        return document, issues, chunk_count, stored_path

    def delete(self, document_id: str, *, purge_file: bool = True) -> DocumentRecord:
        document = self.catalog.get_document(document_id)
        if not document or document.tenant_id != self.settings.tenant_id:
            raise DocumentNotFoundError(document_id)
        if document.status == DocumentStatus.DELETED:
            return document

        ensure_transition(document.status, DocumentStatus.DELETING)
        document.status = DocumentStatus.DELETING
        document.updated_at = datetime.now(UTC)
        self.catalog.upsert_document(document)
        self.catalog.delete_chunks(document_id)

        stored_path = self.catalog.get_stored_path(document_id)
        if purge_file and stored_path:
            path = Path(stored_path)
            if path.exists():
                path.unlink()
            try:
                path.parent.rmdir()
            except OSError:
                pass

        ensure_transition(document.status, DocumentStatus.DELETED)
        document.status = DocumentStatus.DELETED
        document.updated_at = datetime.now(UTC)
        self.catalog.upsert_document(document)
        if purge_file:
            self.catalog.clear_stored_path(document_id)
        return document
