from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest


def make_text_pdf(path: Path, *, pages: int = 1, text: str | None = None) -> Path:
    doc = pymupdf.open()
    body = (
        text
        or (
            "Production RAG knowledge platform test document. "
            "This paragraph contains enough text to exercise extraction and chunking. "
            "Document processing must preserve page numbers and deterministic metadata. "
        )
        * 8
    )
    for index in range(pages):
        page = doc.new_page()
        page.insert_textbox(
            pymupdf.Rect(50, 50, 545, 792),
            f"Page {index + 1}\n\n{body}",
            fontsize=10,
        )
    doc.save(path)
    doc.close()
    return path


def make_table_pdf(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    x0, y0 = 60, 80
    cell_w, cell_h = 145, 32
    rows = [
        ["Control", "Owner", "Status"],
        ["AC-1", "Security", "Active"],
        ["AU-2", "Platform", "Planned"],
        ["IR-4", "SRE", "Active"],
    ]
    for row_index, row in enumerate(rows):
        for col_index, value in enumerate(row):
            rect = pymupdf.Rect(
                x0 + col_index * cell_w,
                y0 + row_index * cell_h,
                x0 + (col_index + 1) * cell_w,
                y0 + (row_index + 1) * cell_h,
            )
            page.draw_rect(rect, width=0.7)
            page.insert_text((rect.x0 + 5, rect.y0 + 20), value, fontsize=9)
    page.insert_text(
        (60, 250), "Table 1: Example security control ownership and status.", fontsize=10
    )
    doc.save(path)
    doc.close()
    return path


def make_image_only_pdf(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    page.draw_rect(pymupdf.Rect(100, 100, 400, 400), width=2)
    page.draw_circle(pymupdf.Point(250, 250), 80, width=2)
    doc.save(path)
    doc.close()
    return path


def make_encrypted_pdf(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Secret encrypted document")
    doc.save(
        path,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner-secret",
        user_pw="user-secret",
    )
    doc.close()
    return path


def make_zero_page_pdf(path: Path) -> Path:
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n",
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(content))
        content.extend(obj)
    xref = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.write_bytes(content)
    return path


@pytest.fixture
def text_pdf(tmp_path: Path) -> Path:
    return make_text_pdf(tmp_path / "valid.pdf", pages=2)
