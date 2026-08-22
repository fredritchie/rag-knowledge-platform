# Runbook: Reset Local Phase 1 State

To remove all locally ingested documents, chunks, and metadata:

```bash
rm -rf .rag_data
```

Then re-ingest a controlled corpus slice:

```bash
ragctl ingest-dir rag_pdf_corpus --limit 10
```

Do not use this reset pattern against future shared PostgreSQL/S3 environments.
