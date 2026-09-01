# Production RAG Knowledge Platform

Configurable, local-first implementation of a production-oriented RAG knowledge platform.
It covers deterministic PDF ingestion, dense and hybrid retrieval, reranking, grounded Ollama
generation, page-level citations, golden-dataset evaluation, and a developer search UI.

Detailed implementation and operating guides:

- [Phase 1 — Development Dataset and PDF Processing Foundation](docs/phases/phase-1-development-dataset-pdf-processing/README.md)
- [Phase 2 — Embeddings and Basic Vector Retrieval](docs/phases/phase-2-embeddings-vector-retrieval/README.md)
- [Phase 3 — RAG Generation and Citations](docs/phases/phase-3-rag-generation-citations/README.md)
- [Phase 4 — RAG Quality Engineering](docs/phases/phase-4-rag-quality-engineering/README.md)
- [Phase 5 — Backend Application and PostgreSQL](docs/phases/phase-5-backend-postgresql/README.md)
- [Phase 6 — Next.js Production Frontend](docs/phases/phase-6-nextjs-frontend/README.md)
- [Phase 7 — Authentication, RBAC and Multi-Tenancy](docs/phases/phase-7-auth-rbac-multitenancy/README.md)
- [Phase 8 — Document Lifecycle and Manual Upload](docs/phases/phase-8-document-lifecycle-upload/README.md)
- [Phase 9 — Event-Driven S3 Ingestion](docs/phases/phase-9-event-driven-s3-ingestion/README.md)
- [Phase 10 — Google Drive Integration](docs/phases/phase-10-google-drive-integration/README.md)
- [Phase 12 — Containerization and Supply-Chain Security](docs/phases/phase-12-container-supply-chain/README.md)

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

### Phase 2–4

- BGE embeddings behind a provider interface and batched Qdrant indexing.
- Tenant-filtered Qdrant payloads with document, page, version, model, and chunker metadata.
- Dense search, local BM25, configurable weighted/RRF fusion, and cross-encoder reranking.
- Versioned YAML prompts, context token budgeting, Ollama calls/streaming, and citations.
- Persisted prompt/model/chunk/generation metadata for reproducibility.
- Retrieval metrics: Hit@1, Hit@3, Hit@5, MRR, and latency percentiles.
- RAG metrics: groundedness proxy, faithfulness proxy, citation correctness, rejection, latency.
- FastAPI developer UI and JSON search/answer endpoints.

### Phase 5–8

- Modular versioned FastAPI application with structured errors, request IDs, OpenAPI, pagination,
  filtering, sorting, rate-limit hooks, CORS, liveness, and dependency readiness.
- Async SQLAlchemy application model and Alembic migrations for PostgreSQL.
- Tenants, Cognito users/memberships, versioned documents and ACLs, jobs/events, chats/traces,
  Drive sync state, audits, and model/prompt/embedding lineage.
- Cognito RS256/JWKS verification and Admin/Editor/Viewer capability enforcement.
- Tenant and document ACL filters applied inside Qdrant and SQL before retrieval or generation.
- Encrypted direct-to-S3 upload authorization and safe replacement-version orchestration.
- Separate ingestion and synchronization worker processes with row locking and retry state.
- Next.js TypeScript application for login, dashboard, cited chat, documents, upload, pipeline
  status, document details, and administration.

### Phase 9–10

- S3 EventBridge envelope validation, encrypted SQS consumption, durable PostgreSQL receipts,
  duplicate suppression, retry-safe ACK behavior, DLQ health, alarm-ready Terraform, and a concrete
  S3/checksum/parser/index processor.
- Google Drive Changes API checkpoints, scheduled incremental paging, OAuth secret references,
  CREATE/UPDATE/DELETE/MOVE/PERMISSION CHANGE handling, canonical S3 publication, permission sync,
  and audited admin controls in FastAPI and Next.js.

### Run the application stack

Build and start the complete local container stack, including migrations, API, workers, Ollama,
and the frontend:

```bash
make services-up
make services-ps
```

The local Compose profile is isolated from the configured AWS queue and uses deterministic
embeddings. To install the default local model:

```bash
docker compose exec ollama-runtime ollama pull llama3.2:3b
```

The production API is available on `http://127.0.0.1:8080`, OpenAPI on `/docs`, and Next.js on
`http://localhost:3000`. The legacy developer search UI remains on its separately configured port.

## Quick start

```bash
./scripts/bootstrap_dev.sh
source .venv/bin/activate
```

Or install directly:

```bash
python3 -m pip install -e '.[dev]'
```

Install the local embedding and reranking models, then start Qdrant and Ollama:

```bash
make install-ml
make services-up
docker compose exec ollama-runtime ollama pull llama3.2:3b
```

All runtime choices live in `config/rag.yaml`. Override any value without editing Python by
using double-underscore environment paths, for example:

```bash
export RAG__RETRIEVAL__TOP_K=10
export RAG__RETRIEVAL__MODE=hybrid
export RAG__GENERATION__MODEL=llama3.2:3b
ragctl config-show
```

### Index and search

Ingestion uses the configured 500-character chunks with 75-character overlap by default:

```bash
ragctl ingest ./document.pdf
ragctl index --all
ragctl search "What is zero trust?"
ragctl search "RFC-9110 status code semantics" --mode hybrid_rerank --json
```

Before permanently removing an indexed document, remove its tenant-scoped vectors and then
delete its catalog/file record:

```bash
ragctl deindex doc_xxxxxxxxxxxxxxxxxxxx
ragctl delete doc_xxxxxxxxxxxxxxxxxxxx
```

Generate a grounded answer with page-level source metadata:

```bash
ragctl ask "What is zero trust?"
```

Run the temporary developer UI at <http://127.0.0.1:8000>:

```bash
ragctl serve
```

### Evaluate retrieval and RAG

Replace the example rows under `evaluation/datasets/` with known questions from your corpus,
then run:

```bash
ragctl evaluate retrieval
ragctl evaluate rag
```

JSON reports are written to `evaluation/reports/`. Compare configurations by overriding
`retrieval.mode`, chunking values, and `top_k`; re-ingest and re-index whenever chunking or the
embedding model changes. A different embedding dimension should use a new Qdrant collection.

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

For ingestion without immediate indexing, the path is:

```text
RECEIVED -> PARSING -> CHUNKING -> VALIDATING -> ACTIVE
```

`ACTIVE` means the document passed local parsing/chunk validation and is available to index.
`ragctl index` performs embedding and idempotent vector upserts separately so corpus rebuilds are
explicit and measurable.

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
