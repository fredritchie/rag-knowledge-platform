# Container images

- `frontend.Dockerfile` tests and builds the standalone Next.js frontend.
- `python.Dockerfile` tests once and builds the shared non-root API/worker runtime.
- `ollama.Dockerfile` verifies and hardens the pinned Ollama runtime.

Compose assigns the shared Python runtime to distinct `rag/api`, `rag/ingestion-worker`, and
`rag/drive-sync` image identities. CI generates and scans an SBOM for each identity before ECR
publication and Cosign digest signing.
