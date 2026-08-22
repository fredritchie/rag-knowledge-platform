# Phase 0/1 Acceptance Checklist

## Phase 0

- [x] Product goal documented.
- [x] Actors documented.
- [x] Target capabilities documented.
- [x] Conceptual application boundaries documented.
- [x] Initial `/api/v1` resource contract documented.
- [x] Complete document lifecycle state machine coded.
- [x] Data ownership documented.
- [x] S3/Qdrant/PostgreSQL/Cognito/Kubernetes ADRs written.
- [x] Local-only deployment constraint documented.

## Phase 1 implementation

- [x] `ragctl validate`.
- [x] `ragctl ingest`.
- [x] `ragctl ingest-dir`.
- [x] `ragctl inspect`.
- [x] `ragctl chunks`.
- [x] `ragctl delete`.
- [x] `ragctl list`.
- [x] PDF signature validation.
- [x] Corrupted-PDF detection.
- [x] Password-protected-PDF detection.
- [x] Empty/zero-text detection.
- [x] Low-text-density warning.
- [x] Excessive-page-count rejection.
- [x] Suspicious replacement-character/encoding detection.
- [x] SHA-256 duplicate detection.
- [x] Metadata extraction.
- [x] Page-aware extraction.
- [x] Cleaning.
- [x] Page-aware chunking with overlap.
- [x] Local SQLite catalog.
- [x] Canonical local PDF copy.
- [x] Persisted validation issues.
- [x] Failure states persisted.

## Corpus gates

Run these explicitly rather than assuming success:

```bash
ragctl ingest-dir rag_pdf_corpus --limit 10
ragctl ingest-dir rag_pdf_corpus --limit 20
ragctl ingest-dir rag_pdf_corpus --limit 50
```

For each gate record accepted/rejected PDFs and investigate every rejection. Do not tune validators merely to force a 100% pass rate; determine whether the document is bad, sparse, encrypted, parser-incompatible, or needs OCR.
