# Application Architecture

## Boundary map

The target system is separated conceptually before it is split physically.

| Boundary | Owns | Phase 0/1 implementation |
|---|---|---|
| Identity | authentication identities, sessions, claims | contract only |
| Documents | document identity, metadata, versions, permissions | local document records |
| Ingestion | validation, extraction, cleaning, chunking, indexing jobs | implemented through chunk creation |
| Retrieval | search, filters, Top-K, reranking | future |
| Generation | prompts, model calls, streaming, citations | future |
| Chat | sessions/messages/orchestration | contract only |
| Administration | users, tenants, jobs, health | contract only |
| Evaluation | golden datasets and quality metrics | folder/docs foundation |
| Observability | logs, metrics, traces | conventions only |

## Why a modular application first

Phase 0 does not create seven networked microservices. Distributed boundaries will only be introduced when independent scaling, reliability, ownership, or deployment requirements justify them.

The first production application is expected to start as a modular FastAPI service plus separate asynchronous worker processes. This prevents network contracts and operational overhead from dominating before the RAG behavior is proven.

## Current Python modules

```text
src/rag_platform/
├── config.py
├── cli.py
├── domain/
│   ├── models.py
│   ├── states.py
│   └── state_machine.py
├── ingestion/
│   ├── validator.py
│   ├── extractor.py
│   ├── cleaner.py
│   ├── quality.py
│   ├── chunker.py
│   └── service.py
└── storage/
    └── sqlite.py
```

## Data ownership

- The ingestion boundary may read source files and create extraction/chunk outputs.
- The document catalog owns document identity, processing status, metadata, and validation issues.
- Chunks are derived data and can be regenerated from the canonical file plus versioned processing configuration.
- Future embeddings are also derived data and must never become the only durable representation of a document.
