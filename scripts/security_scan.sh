#!/usr/bin/env bash
set -euo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly RESULTS_DIR="${ROOT_DIR}/security-results"
readonly PLACEHOLDER_DIGEST="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

mkdir -p "${RESULTS_DIR}"
cd "${ROOT_DIR}"

required_tools=(gitleaks bandit pip-audit npm checkov tflint helm kubeconform trivy syft cosign)
missing_tools=()
for tool in "${required_tools[@]}"; do
  command -v "${tool}" >/dev/null 2>&1 || missing_tools+=("${tool}")
done
if ((${#missing_tools[@]})); then
  echo "Missing required security tools: ${missing_tools[*]}" >&2
  exit 2
fi

gitleaks detect --source . --redact --no-banner
bandit -q -r src
pip-audit
npm --prefix apps/web audit --audit-level=high
checkov -d . --framework terraform dockerfile --quiet
tflint --recursive
helm lint helm/rag-platform \
  --set-string images.frontend.digest="${PLACEHOLDER_DIGEST}" \
  --set-string images.api.digest="${PLACEHOLDER_DIGEST}" \
  --set-string images.ingestionWorker.digest="${PLACEHOLDER_DIGEST}" \
  --set-string images.driveSync.digest="${PLACEHOLDER_DIGEST}" \
  --set-string images.ollamaRuntime.digest="${PLACEHOLDER_DIGEST}"
helm template rag-platform helm/rag-platform \
  --set-string images.frontend.digest="${PLACEHOLDER_DIGEST}" \
  --set-string images.api.digest="${PLACEHOLDER_DIGEST}" \
  --set-string images.ingestionWorker.digest="${PLACEHOLDER_DIGEST}" \
  --set-string images.driveSync.digest="${PLACEHOLDER_DIGEST}" \
  --set-string images.ollamaRuntime.digest="${PLACEHOLDER_DIGEST}" \
  > "${RESULTS_DIR}/rendered.yaml"
kubeconform -strict -summary -ignore-missing-schemas "${RESULTS_DIR}/rendered.yaml"
trivy fs --scanners vuln,secret,misconfig --severity HIGH,CRITICAL --exit-code 1 .
syft dir:. -o cyclonedx-json="${RESULTS_DIR}/source.cdx.json"

images=(rag/frontend:dev rag/api:dev rag/ingestion-worker:dev rag/drive-sync:dev rag/ollama-runtime:0.11.4)
for image in "${images[@]}"; do
  if docker image inspect "${image}" >/dev/null 2>&1; then
    safe_name="${image//[\/:]/-}"
    syft "${image}" -o cyclonedx-json="${RESULTS_DIR}/${safe_name}.cdx.json"
    trivy image --severity HIGH,CRITICAL --exit-code 1 "${image}"
  fi
done

if [[ -n "${COSIGN_VERIFY_REFS:-}" ]]; then
  for reference in ${COSIGN_VERIFY_REFS}; do
    cosign verify "${reference}" \
      --certificate-identity-regexp="${COSIGN_CERTIFICATE_IDENTITY_REGEXP:?required}" \
      --certificate-oidc-issuer="${COSIGN_CERTIFICATE_OIDC_ISSUER:-https://token.actions.githubusercontent.com}"
  done
fi
