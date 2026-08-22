from __future__ import annotations

from rag_platform.domain.models import ValidationIssue
from rag_platform.domain.states import IssueCode, IssueSeverity
from rag_platform.ingestion.extractor import ExtractedPage


def replacement_character_ratio(text: str) -> float:
    if not text:
        return 0.0
    return text.count("\ufffd") / len(text)


def assess_extracted_text(
    pages: list[ExtractedPage],
    *,
    min_avg_chars_per_page: int,
    max_replacement_char_ratio: float,
) -> tuple[list[ValidationIssue], int, float]:
    combined = "".join(page.text for page in pages)
    useful_chars = sum(1 for char in combined if not char.isspace())
    page_count = max(len(pages), 1)
    average = useful_chars / page_count
    issues: list[ValidationIssue] = []

    if useful_chars == 0:
        issues.append(
            ValidationIssue(
                code=IssueCode.ZERO_EXTRACTED_TEXT,
                severity=IssueSeverity.ERROR,
                message="PDF contains pages but no extractable text. OCR may be required.",
            )
        )
        return issues, useful_chars, average

    if average < min_avg_chars_per_page:
        issues.append(
            ValidationIssue(
                code=IssueCode.LOW_TEXT_DENSITY,
                severity=IssueSeverity.WARNING,
                message=(
                    f"Average extractable text is {average:.1f} non-whitespace characters/page; "
                    f"warning threshold is {min_avg_chars_per_page}."
                ),
                details={"average_chars_per_page": average},
            )
        )

    ratio = replacement_character_ratio(combined)
    if ratio > max_replacement_char_ratio:
        issues.append(
            ValidationIssue(
                code=IssueCode.UNSUPPORTED_ENCODING,
                severity=IssueSeverity.ERROR,
                message=(
                    f"Replacement-character ratio {ratio:.3%} exceeds configured maximum "
                    f"{max_replacement_char_ratio:.3%}."
                ),
                details={"replacement_character_ratio": ratio},
            )
        )

    return issues, useful_chars, average
