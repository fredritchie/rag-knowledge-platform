#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
digest="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
args=()
for image in frontend api ingestionWorker driveSync ollamaRuntime qdrant; do
  args+=(--set-string "images.${image}.digest=${digest}")
done

helm lint "${root_dir}/helm/rag-platform" "${args[@]}"
helm template rag-platform "${root_dir}/helm/rag-platform" \
  --namespace rag-platform "${args[@]}" > "${TMPDIR:-/tmp}/rag-platform-rendered.yaml"
kubeconform -strict -summary -ignore-missing-schemas "${TMPDIR:-/tmp}/rag-platform-rendered.yaml"
