# Helm

`rag-platform/` packages the five application images. Every image value requires an immutable
`sha256:` digest; templates intentionally fail when a digest is omitted, and no tag value is
accepted. Create the runtime Secret separately with a `database-url` key, then deploy with the
five ECR repositories and digests supplied through an environment-specific values file.

Enable `admissionPolicy.enabled` only where Kyverno is installed. The policy verifies keyless
Cosign signatures for `rag/*` ECR images and rejects unsigned or digest-mismatched Pods.
