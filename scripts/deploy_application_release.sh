#!/usr/bin/env bash
set -euo pipefail

environment_values="${1:?Pass rendered environment values}"
image_values="${2:?Pass reviewed image values}"
common=(rag-platform helm/rag-platform
  --namespace rag-platform --create-namespace
  --values "${environment_values}" --values "${image_values}"
  --atomic --wait --timeout 30m --history-max 10)

# An authentication/network failure must not be mistaken for a missing release.
if status_output="$(helm status rag-platform --namespace rag-platform --output json 2>&1)"; then
  status="$(jq -er '.info.status' <<<"${status_output}")"
  case "${status}" in
    deployed|failed) ;;
    *) echo "Refusing deployment while Helm release is ${status}" >&2; exit 1 ;;
  esac
elif [[ "${status_output}" == *"release: not found"* ]]; then
  # --wait runs BEFORE post-install hooks. Keep every application deployment at
  # zero until the post-install migration succeeds. KEDA must not scale it up.
  # The chart still creates the SecretStore/ExternalSecret, service account,
  # network policies, and other dependencies needed by the migration Job.
  echo "==> Bootstrap: create prerequisites and migrate before starting application pods"
  helm upgrade --install "${common[@]}" \
    --set replicaCount.frontend=0 \
    --set replicaCount.api=0 \
    --set replicaCount.ingestionWorker=0 \
    --set replicaCount.driveSync=0 \
    --set keda.enabled=false
else
  echo "Cannot determine Helm release status: ${status_output}" >&2
  exit 1
fi

# Explicitly discard bootstrap overrides, including KEDA=false and zero replicas.
# pre-upgrade migrations remain enabled for normal upgrades and retries.
echo "==> Deploy application after migrations"
helm upgrade --install "${common[@]}" --reset-values
for component in frontend api ingestion-worker drive-sync; do
  kubectl --namespace rag-platform rollout status \
    "deployment/rag-platform-${component}" --timeout=10m
done
