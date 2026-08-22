from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from rag_platform.domain.models import ChunkRecord, DocumentRecord, ValidationIssue
from rag_platform.domain.states import DocumentStatus


class SQLiteCatalog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row

        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")

            yield connection

            connection.commit()

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_file_id TEXT,
                    source_version TEXT,
                    document_version INTEGER NOT NULL,
                    checksum_sha256 TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    file_size_bytes INTEGER NOT NULL,
                    page_count INTEGER NOT NULL,
                    extracted_characters INTEGER NOT NULL,
                    average_chars_per_page REAL NOT NULL,
                    title TEXT,
                    author TEXT,
                    subject TEXT,
                    keywords TEXT,
                    status TEXT NOT NULL,
                    parser TEXT NOT NULL,
                    parser_version TEXT NOT NULL,
                    chunker_version TEXT NOT NULL,
                    stored_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_documents_checksum ON documents(checksum_sha256);
                CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);

                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    page INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    page_chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    source TEXT NOT NULL,
                    document_version INTEGER NOT NULL,
                    checksum_sha256 TEXT NOT NULL,
                    chunker_version TEXT NOT NULL,
                    char_start INTEGER NOT NULL,
                    char_end INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id, chunk_index);
                CREATE INDEX IF NOT EXISTS idx_chunks_page ON chunks(document_id, page);

                CREATE TABLE IF NOT EXISTS validation_issues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
                    code TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_issues_document ON validation_issues(document_id);
                """
            )

    def upsert_document(self, document: DocumentRecord, stored_path: str | None = None) -> None:
        values = document.model_dump(mode="json")
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT stored_path FROM documents WHERE document_id = ?", (document.document_id,)
            ).fetchone()
            resolved_path = (
                stored_path if stored_path is not None else (existing[0] if existing else None)
            )
            conn.execute(
                """
                INSERT INTO documents (
                    document_id, filename, source, source_file_id, source_version,
                    document_version, checksum_sha256, content_type,
                    file_size_bytes, page_count, extracted_characters,
                    average_chars_per_page, title, author, 
                    subject, keywords, status, parser,
                    parser_version, chunker_version,
                    stored_path, created_at, updated_at
                ) VALUES (
                    :document_id, :filename, :source, :source_file_id,
                    :source_version, :document_version,
                    :checksum_sha256, :content_type, :file_size_bytes,
                    :page_count, :extracted_characters,
                    :average_chars_per_page, :title, :author, :subject,
                    :keywords, :status, :parser,
                    :parser_version, :chunker_version, :stored_path, :created_at, :updated_at
                )
                ON CONFLICT(document_id) DO UPDATE SET
                    filename=excluded.filename,
                    source=excluded.source,
                    source_file_id=excluded.source_file_id,
                    source_version=excluded.source_version,
                    document_version=excluded.document_version,
                    checksum_sha256=excluded.checksum_sha256,
                    content_type=excluded.content_type,
                    file_size_bytes=excluded.file_size_bytes,
                    page_count=excluded.page_count,
                    extracted_characters=excluded.extracted_characters,
                    average_chars_per_page=excluded.average_chars_per_page,
                    title=excluded.title,
                    author=excluded.author,
                    subject=excluded.subject,
                    keywords=excluded.keywords,
                    status=excluded.status,
                    parser=excluded.parser,
                    parser_version=excluded.parser_version,
                    chunker_version=excluded.chunker_version,
                    stored_path=excluded.stored_path,
                    updated_at=excluded.updated_at
                """,
                {**values, "stored_path": resolved_path},
            )

    def update_status(self, document_id: str, status: DocumentStatus) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE documents SET status = ?, updated_at = ? WHERE document_id = ?",
                (status.value, now, document_id),
            )

    def get_document(self, document_id: str) -> DocumentRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE document_id = ?", (document_id,)
            ).fetchone()
        return self._row_to_document(row) if row else None

    def get_stored_path(self, document_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT stored_path FROM documents WHERE document_id = ?", (document_id,)
            ).fetchone()
        return row[0] if row else None

    def clear_stored_path(self, document_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE documents SET stored_path = NULL WHERE document_id = ?", (document_id,)
            )

    def find_by_checksum(self, checksum_sha256: str) -> DocumentRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM documents
                WHERE checksum_sha256 = ? AND status != ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (checksum_sha256, DocumentStatus.DELETED.value),
            ).fetchone()
        return self._row_to_document(row) if row else None

    def list_documents(self, *, include_deleted: bool = False) -> list[DocumentRecord]:
        query = "SELECT * FROM documents"
        params: tuple[str, ...] = ()
        if not include_deleted:
            query += " WHERE status != ?"
            params = (DocumentStatus.DELETED.value,)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_document(row) for row in rows]

    def replace_chunks(self, document_id: str, chunks: Iterable[ChunkRecord]) -> None:
        rows = [chunk.model_dump(mode="json") for chunk in chunks]
        with self._connect() as conn:
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            conn.executemany(
                """
                INSERT INTO chunks (
                    chunk_id, document_id, filename, page, chunk_index, page_chunk_index, text,
                    source, document_version, checksum_sha256, chunker_version, char_start,
                    char_end, created_at
                ) VALUES (
                    :chunk_id, :document_id, :filename, :page, :chunk_index, :page_chunk_index, 
                    :text, :source, :document_version, :checksum_sha256, :chunker_version,
                    :char_start, :char_end, :created_at
                )
                """,
                rows,
            )

    def get_chunks(
        self, document_id: str, *, page: int | None = None, limit: int | None = None
    ) -> list[ChunkRecord]:
        query = "SELECT * FROM chunks WHERE document_id = ?"
        params: list[object] = [document_id]
        if page is not None:
            query += " AND page = ?"
            params.append(page)
        query += " ORDER BY chunk_index"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [ChunkRecord.model_validate(dict(row)) for row in rows]

    def delete_chunks(self, document_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))

    def replace_issues(self, document_id: str, issues: list[ValidationIssue]) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute("DELETE FROM validation_issues WHERE document_id = ?", (document_id,))
            conn.executemany(
                """
                INSERT INTO validation_issues (
                    document_id, code, severity, message, details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        document_id,
                        issue.code.value,
                        issue.severity.value,
                        issue.message,
                        json.dumps(issue.details, sort_keys=True),
                        now,
                    )
                    for issue in issues
                ],
            )

    def get_issues(self, document_id: str) -> list[ValidationIssue]:
        with self._connect() as conn:
            rows = conn.execute(
                (
                    "SELECT code, severity, message, details_json "
                    "FROM validation_issues "
                    "WHERE document_id = ?"
                ),
                (document_id,),
            ).fetchall()
        return [
            ValidationIssue(
                code=row["code"],
                severity=row["severity"],
                message=row["message"],
                details=json.loads(row["details_json"]),
            )
            for row in rows
        ]

    @staticmethod
    def _row_to_document(row: sqlite3.Row) -> DocumentRecord:
        data = dict(row)
        data.pop("stored_path", None)
        return DocumentRecord.model_validate(data)
