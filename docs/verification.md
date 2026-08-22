# Phase 0/1 Verification

## Automated test result

```text
19 passed
```

The suite covers:

- lifecycle transition validation
- text cleaning
- deterministic, page-aware chunking
- non-PDF rejection
- corrupted PDF classification
- password-protected PDF classification
- valid zero-page/empty PDF classification
- table-text extraction
- image/diagram-only zero-text classification
- low-text-density warning behavior
- suspicious replacement-character/encoding detection
- 500-page excessive-page classification
- successful ingestion/persistence
- duplicate detection
- failed-ingestion persistence
- deletion/chunk cleanup
- CLI ingest/inspect/chunk operations

## Manual CLI smoke path

Validated in sequence:

```text
validate -> ingest -> inspect -> chunks -> delete
```

The smoke PDF reached `ACTIVE`, created page-aware chunks, persisted metadata and a canonical local copy, then transitioned to `DELETED` with chunks/file removed.

## Environment limitation

The curated 50-PDF manifest and downloader are included, but the real 10/20/50 corpus gate was not executed in the build environment because the corpus directory contained no downloaded PDFs and outbound internet access was unavailable.

Run locally:

```bash
make corpus
ragctl ingest-dir rag_pdf_corpus --limit 10
```

Then repeat with 20 and 50 after reviewing each gate.
