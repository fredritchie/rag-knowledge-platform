from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    page_number: int
    text: str


def extract_pages(path: Path) -> list[ExtractedPage]:
    pages: list[ExtractedPage] = []
    doc = pymupdf.open(path)
    try:
        for index, page in enumerate(doc):
            text = page.get_text("text", sort=True) or ""
            pages.append(ExtractedPage(page_number=index + 1, text=text))
    finally:
        doc.close()
    return pages
