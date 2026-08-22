# Data Flow

## Phase 1 ingestion flow

```mermaid
sequenceDiagram
    actor Dev as Developer
    participant CLI as ragctl
    participant V as Validator
    participant E as Extractor
    participant C as Cleaner/Chunker
    participant DB as SQLite Catalog
    participant FS as Local Document Store

    Dev->>CLI: ragctl ingest document.pdf
    CLI->>V: validate signature, encryption, pages
    V-->>CLI: metadata + validation issues
    CLI->>DB: create RECEIVED record
    CLI->>DB: status PARSING
    CLI->>E: extract page text
    E-->>CLI: page-aware text
    CLI->>C: clean and chunk
    C-->>CLI: deterministic chunks
    CLI->>DB: persist chunks + issues
    CLI->>DB: status VALIDATING
    CLI->>FS: copy canonical local PDF
    CLI->>DB: status ACTIVE
    CLI-->>Dev: document ID + chunk count
```

## Failure path

A hard validation or extraction failure is persisted as an explicit issue and the document enters `FAILED_PARSE`. Low text density is currently a warning because sparse diagrams/manuals can still be valid.

## Future question flow

```mermaid
sequenceDiagram
    actor User
    participant UI as Next.js
    participant API as FastAPI
    participant Auth as Authorization
    participant R as Retrieval
    participant G as Generation

    User->>UI: ask question
    UI->>API: authenticated request
    API->>Auth: resolve tenant/user/document ACL
    Auth-->>API: authorized document scope
    API->>R: search only authorized scope
    R-->>API: ranked chunks
    API->>G: prompt + retrieved chunks
    G-->>API: grounded answer + citations
    API-->>UI: streamed response
```

Unauthorized chunks must be excluded before the retrieval context is built.
