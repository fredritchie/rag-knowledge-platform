#!/usr/bin/env bash
set -euo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly RESULTS_DIR="${ROOT_DIR}/security-results"
readonly PLACEHOLDER_DIGEST="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
readonly OLLAMA_IMAGE="rag/ollama-runtime:0.33.2"
readonly OLLAMA_EXCEPTION_EXPIRY="2026-10-02"
readonly OLLAMA_IGNORE_FILE="${ROOT_DIR}/security/trivy/ollama-runtime-v0.33.2.trivyignore"

mkdir -p "${RESULTS_DIR}"
if [[ -n "${RAG_SECURITY_TMPDIR:-}" ]]; then
  mkdir -p "${RAG_SECURITY_TMPDIR}"
fi
cd "${ROOT_DIR}"

syft_with_tmpdir() {
  if [[ -n "${RAG_SECURITY_TMPDIR:-}" ]]; then
    TMPDIR="${RAG_SECURITY_TMPDIR}" syft "$@"
  else
    syft "$@"
  fi
}

required_tools=(gitleaks bandit pip-audit npm checkov tflint helm kubeconform trivy syft cosign)
missing_tools=()
for tool in "${required_tools[@]}"; do
  command -v "${tool}" >/dev/null 2>&1 || missing_tools+=("${tool}")
done
if ((${#missing_tools[@]})); then
  echo "Missing required security tools: ${missing_tools[*]}" >&2
  exit 2
fi

gitleaks detect --source . --no-git --redact --no-banner
bandit -q -r src
site_packages=(.venv/lib/python*/site-packages)
if [[ -d "${site_packages[0]}" ]]; then
  pip-audit --path "${site_packages[0]}"
else
  pip-audit
fi
npm --prefix apps/web audit --audit-level=high
checkov -d . --framework terraform dockerfile --quiet --skip-path .venv --skip-path security-env
tflint --recursive
helm lint helm/rag-platform \
  --set-string images.frontend.digest="${PLACEHOLDER_DIGEST}" \
  --set-string images.api.digest="${PLACEHOLDER_DIGEST}" \
  --set-string images.ingestionWorker.digest="${PLACEHOLDER_DIGEST}" \
  --set-string images.driveSync.digest="${PLACEHOLDER_DIGEST}" \
  --set-string images.ollamaRuntime.digest="${PLACEHOLDER_DIGEST}" \
  --set-string images.qdrant.digest="${PLACEHOLDER_DIGEST}"
helm template rag-platform helm/rag-platform \
  --set-string images.frontend.digest="${PLACEHOLDER_DIGEST}" \
  --set-string images.api.digest="${PLACEHOLDER_DIGEST}" \
  --set-string images.ingestionWorker.digest="${PLACEHOLDER_DIGEST}" \
  --set-string images.driveSync.digest="${PLACEHOLDER_DIGEST}" \
  --set-string images.ollamaRuntime.digest="${PLACEHOLDER_DIGEST}" \
  --set-string images.qdrant.digest="${PLACEHOLDER_DIGEST}" \
  > "${RESULTS_DIR}/rendered.yaml"
helm lint helm/observability
helm template rag-observability helm/observability --namespace monitoring \
  > "${RESULTS_DIR}/observability-rendered.yaml"
kubeconform -strict -summary -ignore-missing-schemas "${RESULTS_DIR}/rendered.yaml"
kubeconform -strict -summary -ignore-missing-schemas "${RESULTS_DIR}/observability-rendered.yaml"
trivy fs --skip-dirs .venv --skip-dirs security-env --scanners vuln,secret,misconfig --severity HIGH,CRITICAL --exit-code 1 .
syft_with_tmpdir dir:. --exclude './.venv/**' --exclude './security-env/**' \
  -o cyclonedx-json="${RESULTS_DIR}/source.cdx.json"

images=(rag/frontend:dev rag/api:dev rag/ingestion-worker:dev rag/drive-sync:dev "${OLLAMA_IMAGE}")
for image in "${images[@]}"; do
  if docker image inspect "${image}" >/dev/null 2>&1; then
    safe_name="${image//[\/:]/-}"
    syft_with_tmpdir "${image}" -o cyclonedx-json="${RESULTS_DIR}/${safe_name}.cdx.json"
    if [[ "${image}" == "${OLLAMA_IMAGE}" ]]; then
      if [[ "$(date -u +%F)" > "${OLLAMA_EXCEPTION_EXPIRY}" ]]; then
        echo "Ollama vulnerability exception expired on ${OLLAMA_EXCEPTION_EXPIRY}" >&2
        exit 1
      fi
      trivy image --ignore-unfixed --ignorefile "${OLLAMA_IGNORE_FILE}" \
        --severity HIGH,CRITICAL --exit-code 1 "${image}"
    else
      trivy image --ignore-unfixed --severity HIGH,CRITICAL --exit-code 1 "${image}"
    fi
  fi
done

if [[ -n "${COSIGN_VERIFY_REFS:-}" ]]; then
  for reference in ${COSIGN_VERIFY_REFS}; do
    cosign verify "${reference}" \
      --certificate-identity-regexp="${COSIGN_CERTIFICATE_IDENTITY_REGEXP:?required}" \
      --certificate-oidc-issuer="${COSIGN_CERTIFICATE_OIDC_ISSUER:-https://token.actions.githubusercontent.com}"
  done
fi
