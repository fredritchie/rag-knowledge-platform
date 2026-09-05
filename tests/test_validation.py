from pathlib import Path

import pytest

from rag_platform.config import Settings
from rag_platform.domain.states import IssueCode, IssueSeverity
from rag_platform.ingestion.extractor import ExtractedPage
from rag_platform.ingestion.quality import assess_extracted_text
from rag_platform.ingestion.service import IngestionService
from rag_platform.ingestion.validator import preflight_validate
from tests.conftest import (
    make_encrypted_pdf,
    make_image_only_pdf,
    make_table_pdf,
    make_text_pdf,
    make_zero_page_pdf,
)


def _codes(issues):
    return {issue.code for issue in issues}


def test_non_pdf_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "fake.pdf"
    path.write_text("not a pdf", encoding="utf-8")
    result = preflight_validate(path, max_pages=1000)
    assert IssueCode.NOT_PDF in _codes(result.issues)


def test_corrupted_pdf_is_classified(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.7\nthis is not a valid pdf structure")
    result = preflight_validate(path, max_pages=1000)
    assert IssueCode.CORRUPTED_PDF in _codes(result.issues)


def test_password_protected_pdf_is_rejected(tmp_path: Path) -> None:
    path = make_encrypted_pdf(tmp_path / "encrypted.pdf")
    result = preflight_validate(path, max_pages=1000)
    assert IssueCode.PASSWORD_PROTECTED in _codes(result.issues)


def test_zero_page_pdf_is_rejected(tmp_path: Path) -> None:
    path = make_zero_page_pdf(tmp_path / "zero-pages.pdf")
    result = preflight_validate(path, max_pages=1000)
    assert IssueCode.EMPTY_PDF in _codes(result.issues)


def test_table_pdf_extracts_searchable_text(tmp_path: Path) -> None:
    path = make_table_pdf(tmp_path / "table.pdf")
    service = IngestionService(Settings(data_dir=tmp_path / "table-data", min_avg_chars_per_page=1))
    issues, details = service.validate(path)
    assert not [issue for issue in issues if issue.severity == IssueSeverity.ERROR]
    assert details["extracted_characters"] > 20


def test_image_only_pdf_is_zero_text(tmp_path: Path) -> None:
    path = make_image_only_pdf(tmp_path / "image-only.pdf")
    service = IngestionService(Settings(data_dir=tmp_path / "data"))
    issues, _ = service.validate(path)
    assert IssueCode.ZERO_EXTRACTED_TEXT in _codes(issues)


def test_low_text_density_is_warning_not_error(tmp_path: Path) -> None:
    path = make_text_pdf(tmp_path / "sparse.pdf", text="tiny")
    settings = Settings(data_dir=tmp_path / "data", min_avg_chars_per_page=100)
    service = IngestionService(settings)
    issues, _ = service.validate(path)
    low_density = [issue for issue in issues if issue.code == IssueCode.LOW_TEXT_DENSITY]
    assert low_density
    assert low_density[0].severity == IssueSeverity.WARNING


def test_suspicious_replacement_character_ratio_is_rejected() -> None:
    issues, _, _ = assess_extracted_text(
        [ExtractedPage(1, "\ufffd" * 100 + "normal")],
        min_avg_chars_per_page=1,
        max_replacement_char_ratio=0.02,
    )
    assert IssueCode.UNSUPPORTED_ENCODING in _codes(issues)


@pytest.mark.slow
def test_500_page_pdf_can_be_classified_as_excessive(tmp_path: Path) -> None:
    path = make_text_pdf(tmp_path / "500-pages.pdf", pages=500, text="page")
    result = preflight_validate(path, max_pages=499)
    assert result.page_count == 500
    assert IssueCode.EXCESSIVE_PAGE_COUNT in _codes(result.issues)
