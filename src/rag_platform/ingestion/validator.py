from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from rag_platform.domain.models import ValidationIssue
from rag_platform.domain.states import IssueCode, IssueSeverity


@dataclass(slots=True)
class PreflightResult:
    checksum_sha256: str = ""
    file_size_bytes: int = 0
    page_count: int = 0
    metadata: dict[str, str | None] = field(default_factory=dict)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == IssueSeverity.ERROR for issue in self.issues)


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def _issue(
    code: IssueCode, severity: IssueSeverity, message: str, **details: object
) -> ValidationIssue:
    return ValidationIssue(code=code, severity=severity, message=message, details=details)


def preflight_validate(path: Path, *, max_pages: int) -> PreflightResult:
    result = PreflightResult()

    if not path.exists():
        result.issues.append(
            _issue(IssueCode.NOT_FOUND, IssueSeverity.ERROR, "File does not exist.")
        )
        return result
    if not path.is_file():
        result.issues.append(
            _issue(IssueCode.NOT_A_FILE, IssueSeverity.ERROR, "Path is not a file.")
        )
        return result

    result.file_size_bytes = path.stat().st_size
    if result.file_size_bytes == 0:
        result.issues.append(_issue(IssueCode.EMPTY_PDF, IssueSeverity.ERROR, "File is empty."))
        return result

    try:
        with path.open("rb") as handle:
            signature = handle.read(5)
        if signature != b"%PDF-":
            result.issues.append(
                _issue(
                    IssueCode.NOT_PDF,
                    IssueSeverity.ERROR,
                    "File does not start with the PDF signature %PDF-.",
                    signature=signature.hex(),
                )
            )
            return result
    except OSError as exc:
        result.issues.append(
            _issue(
                IssueCode.CORRUPTED_PDF, IssueSeverity.ERROR, "Unable to read file.", error=str(exc)
            )
        )
        return result

    result.checksum_sha256 = sha256_file(path)

    try:
        doc = pymupdf.open(path)
    except Exception as exc:  # PyMuPDF exposes several parser-specific exception types.
        result.issues.append(
            _issue(
                IssueCode.CORRUPTED_PDF,
                IssueSeverity.ERROR,
                "PDF parser could not open the document.",
                error=str(exc),
            )
        )
        return result

    try:
        if doc.needs_pass:
            result.issues.append(
                _issue(
                    IssueCode.PASSWORD_PROTECTED,
                    IssueSeverity.ERROR,
                    "PDF is encrypted and requires a password.",
                )
            )
            return result

        result.page_count = doc.page_count
        if result.page_count == 0:
            result.issues.append(
                _issue(IssueCode.EMPTY_PDF, IssueSeverity.ERROR, "PDF contains zero pages.")
            )
            return result

        if result.page_count > max_pages:
            result.issues.append(
                _issue(
                    IssueCode.EXCESSIVE_PAGE_COUNT,
                    IssueSeverity.ERROR,
                    f"PDF has {result.page_count} pages; configured maximum is {max_pages}.",
                    page_count=result.page_count,
                    max_pages=max_pages,
                )
            )

        raw_metadata = doc.metadata or {}
        result.metadata = {
            "title": raw_metadata.get("title") or None,
            "author": raw_metadata.get("author") or None,
            "subject": raw_metadata.get("subject") or None,
            "keywords": raw_metadata.get("keywords") or None,
        }
    finally:
        doc.close()

    return result
