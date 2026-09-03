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

## Phase 13 AWS foundation

```text
Internet -> WAF -> public ALB
                    |
                    v
          private EKS node groups
          | general | Qdrant | GPU |
                    |
                    v
            private Aurora PostgreSQL

S3 canonical store -> encrypted SQS -> DLQ
```

The VPC spans three availability zones. Public subnets contain the ALB and NAT gateways; private subnets contain all compute and data services. Route53 and ACM terminate public HTTPS at the ALB, while the EKS control-plane endpoint is private.
