from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path = Path(os.getenv("RAG_DATA_DIR", ".rag_data"))
    max_pages: int = int(os.getenv("RAG_MAX_PAGES", "1000"))
    chunk_size: int = int(os.getenv("RAG_CHUNK_SIZE", "1200"))
    chunk_overlap: int = int(os.getenv("RAG_CHUNK_OVERLAP", "200"))
    min_avg_chars_per_page: int = int(os.getenv("RAG_MIN_AVG_CHARS_PER_PAGE", "40"))
    max_replacement_char_ratio: float = float(os.getenv("RAG_MAX_REPLACEMENT_CHAR_RATIO", "0.02"))

    @property
    def database_path(self) -> Path:
        return self.data_dir / "catalog.sqlite3"

    @property
    def documents_dir(self) -> Path:
        return self.data_dir / "documents"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.documents_dir.mkdir(parents=True, exist_ok=True)
