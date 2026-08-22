# Production RAG Knowledge Platform

Phase 0 and Phase 1 implementation of a production-oriented RAG knowledge platform.

This repository intentionally stops before embeddings, Qdrant, LLM generation, AWS, and Kubernetes. The goal of these phases is to establish the product architecture and prove that PDFs can be validated, extracted, cleaned, chunked, inspected, and lifecycle-managed deterministically.

## What is implemented

### Phase 0

- Product capabilities, actors, application boundaries, API contract, and data ownership documented.
- Full document lifecycle state machine defined.
- Architecture Decision Records for S3, Qdrant, PostgreSQL, Cognito, and Kubernetes strategy.
- Security, operations, evaluation, and runbook documentation foundations.
- Repository conventions and future component boundaries.

### Phase 1

- `ragctl` developer CLI.
- PDF signature and parser validation.
- SHA-256 duplicate detection.
- Password-protected, corrupted, empty, zero-text, excessive-page, low-text-density, and suspicious-encoding detection.
- PDF metadata extraction.
- Page-aware text extraction with PyMuPDF.
- Unicode and whitespace cleaning.
- Page-preserving deterministic chunking with overlap.
- SQLite local development catalog for documents, chunks, and validation issues.
- Soft-delete lifecycle and local canonical file copy.
- Batch ingestion for 10 -> 20 -> 50 PDF development progression.
- 50-PDF development corpus manifest and downloader.
- Unit/integration/CLI tests.

## Quick start

```bash
./scripts/bootstrap_dev.sh
source .venv/bin/activate
```

Or install directly:

```bash
python3 -m pip install -e '.[dev]'
```

### Validate a PDF

```bash
ragctl validate ./rag_pdf_corpus/ai-rag/01_attention_is_all_you_need.pdf
```

### Ingest one PDF

```bash
ragctl ingest ./rag_pdf_corpus/ai-rag/01_attention_is_all_you_need.pdf
```

Output includes a generated `document_id`. Use it for later commands:

```bash
ragctl inspect doc_xxxxxxxxxxxxxxxxxxxx
ragctl chunks doc_xxxxxxxxxxxxxxxxxxxx
ragctl chunks doc_xxxxxxxxxxxxxxxxxxxx --page 2 --full
ragctl delete doc_xxxxxxxxxxxxxxxxxxxx
```

### Batch ingest the corpus progressively

Download the curated corpus:

```bash
make corpus
```

Then:

```bash
rm -rf .rag_data
ragctl ingest-dir rag_pdf_corpus --limit 10
ragctl list
```

After validating the first 10, reset or continue with the next development gate:

```bash
rm -rf .rag_data
ragctl ingest-dir rag_pdf_corpus --limit 20
```

Finally:

```bash
rm -rf .rag_data
ragctl ingest-dir rag_pdf_corpus --limit 50
```

## Local Phase 1 data

By default runtime data lives in:

```text
.rag_data/
├── catalog.sqlite3
└── documents/
    └── doc_<id>/
        └── <sha256>.pdf
```

Change it with:

```bash
export RAG_DATA_DIR=/tmp/rag-dev-data
```

or per command:

```bash
ragctl ingest document.pdf --data-dir /tmp/rag-dev-data
```

## Document lifecycle

The complete target lifecycle is defined now even though Phase 1 only executes the parsing/chunking subset:

```text
RECEIVED
  -> DOWNLOADING
  -> PARSING
  -> CHUNKING
  -> EMBEDDING
  -> INDEXING
  -> VALIDATING
  -> ACTIVE

Failure states:
FAILED_DOWNLOAD
FAILED_PARSE
FAILED_EMBEDDING
FAILED_INDEXING
FAILED_VALIDATION

Deletion:
DELETING -> DELETED
```

For local Phase 1 ingestion, the path is:

```text
RECEIVED -> PARSING -> CHUNKING -> VALIDATING -> ACTIVE
```

`ACTIVE` in Phase 1 means the document has passed local parsing/chunk validation and is available to the development catalog. Vector indexing begins in Phase 2.

## Failure classification

The validator emits machine-readable issue codes:

```text
NOT_FOUND
NOT_A_FILE
NOT_PDF
CORRUPTED_PDF
PASSWORD_PROTECTED
EMPTY_PDF
ZERO_EXTRACTED_TEXT
LOW_TEXT_DENSITY
DUPLICATE_DOCUMENT
EXCESSIVE_PAGE_COUNT
UNSUPPORTED_ENCODING
EXTRACTION_ERROR
```

`LOW_TEXT_DENSITY` is a warning rather than a hard failure because diagram-heavy or sparse technical PDFs may still be legitimate. OCR is deliberately deferred to a later phase.

## Tests

Fast suite:

```bash
make test
```

All tests, including the intentionally large 500-page fixture:

```bash
make test-all
```

Lint + tests:

```bash
make check
```

## Phase 0/1 exit criteria

Phase 0 is complete when the component responsibilities, ownership boundaries, API surface, document lifecycle, and future deployment decisions can be explained from the docs without relying on tribal knowledge.

Phase 1 is complete when the development corpus can be processed deterministically and bad documents fail with explicit classifications, while valid documents produce page-aware chunks and persisted metadata that can be inspected through `ragctl`.

See `docs/phase-0-1-acceptance.md` for the exact checklist.
