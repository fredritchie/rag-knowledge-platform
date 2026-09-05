# Phase Documentation

This directory contains implementation-level operating guides for the document-processing,
retrieval, generation, and quality-engineering phases.

- [Phase 1 — Development Dataset and PDF Processing Foundation](phase-1-development-dataset-pdf-processing/README.md)
- [Phase 2 — Embeddings and Basic Vector Retrieval](phase-2-embeddings-vector-retrieval/README.md)
- [Phase 3 — RAG Generation and Citations](phase-3-rag-generation-citations/README.md)
- [Phase 4 — RAG Quality Engineering](phase-4-rag-quality-engineering/README.md)
- [Phase 5 — Backend Application and PostgreSQL](phase-5-backend-postgresql/README.md)
- [Phase 6 — Next.js Production Frontend](phase-6-nextjs-frontend/README.md)
- [Phase 7 — Authentication, RBAC and Multi-Tenancy](phase-7-auth-rbac-multitenancy/README.md)
- [Phase 8 — Document Lifecycle and Manual Upload](phase-8-document-lifecycle-upload/README.md)
- [Phase 9 — Event-Driven S3 Ingestion](phase-9-event-driven-s3-ingestion/README.md)
- [Phase 10 — Google Drive Integration](phase-10-google-drive-integration/README.md)
- [Phase 12 — Containerization and Supply-Chain Security](phase-12-container-supply-chain/README.md)
- [Phase 13 — AWS Infrastructure with Terraform](phase-13-aws-infrastructure/README.md)
- [Phase 14 — Kubernetes](phase-14-kubernetes/README.md)
- [Phase 15 — Observability](phase-15-observability/README.md)
- [Phase 16 — CI/CD and AI Quality Gates](phase-16-cicd-ai-quality-gates/README.md)

Each guide describes the current source code rather than an aspirational architecture. When a
guide calls out a limitation, it is intentional: operators and evaluators should not mistake a
heuristic, development interface, or local implementation for a production guarantee.

The shared runtime configuration is [`config/rag.yaml`](../../config/rag.yaml). Any YAML field can
be overridden through an environment variable using `RAG__SECTION__FIELD`. For example,
`RAG__RETRIEVAL__TOP_K=10` overrides `retrieval.top_k`.
