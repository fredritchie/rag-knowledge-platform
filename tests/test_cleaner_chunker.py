from datetime import UTC, datetime

from rag_platform.domain.models import DocumentRecord
from rag_platform.ingestion.chunker import ChunkingConfig, build_chunks
from rag_platform.ingestion.cleaner import clean_text
from rag_platform.ingestion.extractor import ExtractedPage


def _document() -> DocumentRecord:
    return DocumentRecord(
        document_id="doc_test",
        filename="test.pdf",
        checksum_sha256="a" * 64,
        file_size_bytes=100,
        page_count=2,
        parser_version="test",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_cleaner_normalizes_hyphenated_line_breaks() -> None:
    raw = "retriev-\nal system\nwith   spaces\n\n\nsecond paragraph"
    cleaned = clean_text(raw)
    assert "retrieval system with spaces" in cleaned
    assert "\n\nsecond paragraph" in cleaned


def test_chunks_preserve_page_numbers_and_order() -> None:
    pages = [
        ExtractedPage(1, ("Alpha paragraph about retrieval. " * 40)),
        ExtractedPage(2, ("Beta paragraph about citations. " * 40)),
    ]
    chunks = build_chunks(_document(), pages, ChunkingConfig(chunk_size=300, overlap=50))

    assert len(chunks) > 2
    assert chunks[0].page == 1
    assert chunks[-1].page == 2
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.chunk_id.startswith("chk_") for chunk in chunks)


def test_chunk_ids_are_deterministic() -> None:
    pages = [ExtractedPage(1, "Deterministic chunking content. " * 30)]
    config = ChunkingConfig(chunk_size=250, overlap=25)
    first = build_chunks(_document(), pages, config)
    second = build_chunks(_document(), pages, config)
    assert [item.chunk_id for item in first] == [item.chunk_id for item in second]
