from __future__ import annotations

import hashlib
from dataclasses import dataclass

from rag_platform.domain.models import ChunkRecord, DocumentRecord
from rag_platform.ingestion.cleaner import clean_text
from rag_platform.ingestion.extractor import ExtractedPage


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    chunk_size: int = 1200
    overlap: int = 200

    def __post_init__(self) -> None:
        if self.chunk_size < 100:
            raise ValueError("chunk_size must be at least 100 characters")
        if self.overlap < 0:
            raise ValueError("overlap must be non-negative")
        if self.overlap >= self.chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")


def _breakpoint(text: str, start: int, proposed_end: int) -> int:
    if proposed_end >= len(text):
        return len(text)

    lower_bound = start + max(1, int((proposed_end - start) * 0.65))
    candidates = [
        text.rfind("\n\n", lower_bound, proposed_end),
        text.rfind(". ", lower_bound, proposed_end),
        text.rfind("; ", lower_bound, proposed_end),
        text.rfind(" ", lower_bound, proposed_end),
    ]
    best = max(candidates)
    if best <= start:
        return proposed_end
    return best + (2 if text[best : best + 2] in {". ", "; "} else 1)


def _chunk_page(text: str, config: ChunkingConfig) -> list[tuple[int, int, str]]:
    chunks: list[tuple[int, int, str]] = []
    start = 0
    length = len(text)

    while start < length:
        end = _breakpoint(text, start, min(length, start + config.chunk_size))
        if end <= start:
            end = min(length, start + config.chunk_size)
        piece = text[start:end].strip()
        if piece:
            chunks.append((start, end, piece))
        if end >= length:
            break
        next_start = max(0, end - config.overlap)
        if next_start <= start:
            next_start = end
        start = next_start

    return chunks


def build_chunks(
    document: DocumentRecord,
    pages: list[ExtractedPage],
    config: ChunkingConfig,
) -> list[ChunkRecord]:
    records: list[ChunkRecord] = []
    global_index = 0

    for page in pages:
        cleaned = clean_text(page.text)
        if not cleaned:
            continue
        for page_index, (start, end, text) in enumerate(_chunk_page(cleaned, config)):
            fingerprint = f"{document.document_id}:{page.page_number}:{page_index}:{text}".encode()
            chunk_id = "chk_" + hashlib.sha256(fingerprint).hexdigest()[:24]
            records.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    tenant_id=document.tenant_id,
                    document_id=document.document_id,
                    filename=document.filename,
                    page=page.page_number,
                    chunk_index=global_index,
                    page_chunk_index=page_index,
                    text=text,
                    source=document.source,
                    document_version=document.document_version,
                    checksum_sha256=document.checksum_sha256,
                    chunker_version=document.chunker_version,
                    char_start=start,
                    char_end=end,
                )
            )
            global_index += 1

    return records
