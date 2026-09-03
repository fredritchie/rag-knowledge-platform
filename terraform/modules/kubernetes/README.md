# Kubernetes module

Creates a private-endpoint EKS cluster spanning three private subnets. It has isolated general, Qdrant, and NVIDIA GPU managed node groups; Qdrant and GPU groups are tainted to prevent accidental scheduling. Kubernetes secrets are KMS-encrypted and all control-plane logs are enabled.
