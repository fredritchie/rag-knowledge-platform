# Operations Foundation

The local Phase 1 runtime is intentionally simple:

- SQLite catalog: `.rag_data/catalog.sqlite3`
- Canonical local copies: `.rag_data/documents/`
- Configuration: environment variables or CLI flags

Use `ragctl list`, `ragctl inspect`, and `ragctl chunks` as the first operational inspection tools.
