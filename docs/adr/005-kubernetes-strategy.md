# ADR 005: Kubernetes Strategy

## Status
Accepted and implemented for AWS in Phase 13.

## Decision
Do not introduce Kubernetes until document processing, retrieval, RAG evaluation, application APIs, and asynchronous ingestion are proven.

AWS environments use EKS because its managed control plane reduces operational burden. The API endpoint is private-only, and managed node groups are separated into general application, Qdrant, and NVIDIA GPU pools. Dedicated Qdrant and GPU taints prevent unrelated workloads from consuming specialized capacity.

## Consequence
Terraform owns the EKS control plane and compute pools. Workload installation, persistent-volume definitions, autoscaling components, and private ALB target binding remain deployment/GitOps responsibilities rather than infrastructure-foundation concerns.
