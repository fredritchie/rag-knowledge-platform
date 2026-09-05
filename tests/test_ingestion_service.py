from pathlib import Path

import pytest

from rag_platform.config import Settings
from rag_platform.domain.states import DocumentStatus, IssueCode
from rag_platform.ingestion.service import (
    DuplicateDocumentError,
    IngestionRejected,
    IngestionService,
)
from tests.conftest import make_image_only_pdf

pytestmark = pytest.mark.integration


def test_ingest_persists_document_and_chunks(text_pdf: Path, tmp_path: Path) -> None:
    service = IngestionService(Settings(data_dir=tmp_path / "catalog"))
    result = service.ingest(text_pdf, chunk_size=300, chunk_overlap=50)

    assert result.document.status == DocumentStatus.ACTIVE
    assert result.document.page_count == 2
    assert result.chunk_count > 0
    assert result.stored_path.exists()

    document, issues, chunk_count, stored_path = service.inspect(result.document.document_id)
    assert document.document_id == result.document.document_id
    assert document.status == DocumentStatus.ACTIVE
    assert chunk_count == result.chunk_count
    assert stored_path == str(result.stored_path)
    assert not [issue for issue in issues if issue.severity.value == "ERROR"]


def test_duplicate_ingestion_is_rejected(text_pdf: Path, tmp_path: Path) -> None:
    service = IngestionService(Settings(data_dir=tmp_path / "catalog"))
    first = service.ingest(text_pdf)
    with pytest.raises(DuplicateDocumentError) as error:
        service.ingest(text_pdf)
    assert error.value.existing_document_id == first.document.document_id


def test_image_only_ingestion_persists_failed_state(tmp_path: Path) -> None:
    path = make_image_only_pdf(tmp_path / "image-only.pdf")
    service = IngestionService(Settings(data_dir=tmp_path / "catalog"))

    with pytest.raises(IngestionRejected) as error:
        service.ingest(path)

    assert error.value.document_id is not None
    document = service.catalog.get_document(error.value.document_id)
    assert document is not None
    assert document.status == DocumentStatus.FAILED_PARSE
    assert IssueCode.ZERO_EXTRACTED_TEXT in {issue.code for issue in error.value.issues}


def test_delete_removes_chunks_and_marks_deleted(text_pdf: Path, tmp_path: Path) -> None:
    service = IngestionService(Settings(data_dir=tmp_path / "catalog"))
    result = service.ingest(text_pdf)
    stored = result.stored_path

    deleted = service.delete(result.document.document_id)
    assert deleted.status == DocumentStatus.DELETED
    assert service.catalog.get_chunks(deleted.document_id) == []
    assert not stored.exists()
