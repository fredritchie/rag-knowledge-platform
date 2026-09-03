# Phase 12 — Containerization and Supply-Chain Security

The application is packaged as five images: `rag/frontend`, `rag/api`, `rag/ingestion-worker`,
`rag/drive-sync`, and `rag/ollama-runtime`. The three Python roles intentionally reuse one tested
multi-stage Dockerfile while retaining distinct release identities and ECR repositories.

## Local stack

`make services-up` builds and health-gates PostgreSQL, Qdrant, Ollama, the migration job, API,
ingestion worker, Drive sync worker, and frontend. Local overrides disable Cognito and real SQS
consumption, use deterministic embeddings, and disable EC2 metadata credential discovery.

```bash
make services-up
make services-ps
docker compose exec ollama-runtime ollama pull llama3.2:3b
make services-down
```

Application containers run as non-root, drop all Linux capabilities, use no-new-privileges and a
read-only root filesystem, and expose only loopback-bound development ports. Persistent or scratch
paths are explicit volumes/tmpfs mounts.

## Release gates

The supply-chain workflow gates images in this order: source secret/SAST/dependency/IaC checks,
tests, multi-stage build, CycloneDX SBOM, Trivy image scan, keyless Cosign signing of the local image
artifact, ECR push, then digest signing and SBOM attestation. ECR repositories must exist and the
`AWS_ECR_ROLE_ARN` secret plus `AWS_REGION` variable must authorize GitHub OIDC publishing.

The local `make security-scan` target runs Gitleaks, Bandit, pip-audit, npm audit, Checkov, TFLint,
Helm lint, kubeconform, Trivy, Syft, and optional Cosign verification. CodeQL runs in GitHub Actions.
On hosts where Docker storage is relocated to a separate filesystem, set `RAG_SECURITY_TMPDIR` to a
writable directory on that filesystem so Syft does not extract image layers under a full `/tmp`.

## Ollama vulnerability exception

The upstream `ollama/ollama:0.33.2` binary contains fixable Go dependency vulnerabilities that cannot
be remediated without maintaining a custom Ollama build. The narrowly scoped exception is recorded
in `security/trivy/ollama-runtime-v0.33.2.trivyignore`, applies only to the Ollama image, and expires
on 2026-10-02. All images continue to fail on fixable High/Critical findings; unfixed upstream
findings are reported but do not block release. Re-evaluate the exception when Ollama releases a
patched image, or at expiry, whichever is earlier.

## Immutable deployment

The Helm chart has no image tag values. All five digests are required and images render only as:

```text
repository@sha256:digest
```

The optional Kyverno policy verifies the workflow's keyless Cosign identity at admission. Replace
the placeholder repositories and certificate identity before enabling it.
