# Deployment Architecture

## Phase 0/1

Phase 0/1 is intentionally local.

```text
Developer workstation
│
├── Python 3.11+
├── ragctl
├── PyMuPDF
├── SQLite
├── .rag_data/
└── local PDF corpus
```

There is no Kubernetes cluster, AWS VPC, load balancer, queue, managed database, or external identity provider in these phases.

## Target progression

1. Local document processing.
2. Local embeddings/vector retrieval.
3. RAG generation/evaluation.
4. FastAPI + Next.js.
5. Authentication/authorization.
6. S3/SQS event-driven ingestion.
7. Multi-source synchronization.
8. Containerization.
9. AWS/Terraform.
10. Kubernetes/GitOps/observability.

This sequencing is a deliberate architecture constraint: intelligence and data correctness must be proven before platform complexity is introduced.
