# Evaluation Reports

Generated retrieval/RAG benchmark reports will live here in later phases. Keep generated large artifacts out of Git unless they are intentionally curated evidence.

## Curated Phase 4 evidence

- [`phase4-initial-validation.md`](phase4-initial-validation.md) explains the initial
  single-case, CPU-only validation and its limitations.
- [`dense-c500-v2.json`](dense-c500-v2.json) records the dense retrieval baseline.
- [`hybrid-c500-v2.json`](hybrid-c500-v2.json) records hybrid retrieval.
- [`hybrid-rerank-c500-v2.json`](hybrid-rerank-c500-v2.json) records hybrid retrieval with
  cross-encoder reranking.
- [`rag-adversarial-evaluator-fix.json`](rag-adversarial-evaluator-fix.json) records the
  unsupported-question rejection result after source-handling and evaluator fixes.

These reports are functional evidence only. Each dataset contained one case, so they must not be
presented as production accuracy measurements or used alone to complete the Phase 4 acceptance
checklist.
