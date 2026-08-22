# ADR 005: Kubernetes Strategy

## Status
Deferred implementation; architecture decision recorded now.

## Decision
Do not introduce Kubernetes until document processing, retrieval, RAG evaluation, application APIs, and asynchronous ingestion are proven.

For portfolio learning, a self-managed Kubernetes environment can demonstrate control-plane lifecycle, etcd backup, node pools, and scheduling. For commercial AWS production, EKS must be evaluated because managed control planes reduce operational burden.

## Phase 0/1 consequence
No Kubernetes manifests are required to run or test the current implementation.
