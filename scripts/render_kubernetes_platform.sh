#!/usr/bin/env bash
set -euo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly OUTPUT_DIR="${1:?Usage: render_kubernetes_platform.sh OUTPUT_DIR}"
readonly PLATFORM_DIR="${ROOT_DIR}/helm/platform"

# shellcheck disable=SC1091
source "${PLATFORM_DIR}/versions.env"
mkdir -p "${OUTPUT_DIR}"

helm repo add cilium https://helm.cilium.io/ --force-update
helm repo add eks https://aws.github.io/eks-charts --force-update
helm repo add external-secrets https://charts.external-secrets.io --force-update
helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/ --force-update
helm repo add kedacore https://kedacore.github.io/charts --force-update
helm repo add kyverno https://kyverno.github.io/kyverno/ --force-update
helm repo add nvdp https://nvidia.github.io/k8s-device-plugin --force-update
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update
helm repo add grafana https://grafana.github.io/helm-charts --force-update
helm repo add grafana-community https://grafana-community.github.io/helm-charts --force-update
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts --force-update
helm repo add gpu-helm-charts https://nvidia.github.io/dcgm-exporter/helm-charts --force-update
helm repo update

platform_output="${OUTPUT_DIR}/platform.yaml"
observability_output="${OUTPUT_DIR}/observability.yaml"

helm template rag-platform-storage "${ROOT_DIR}/helm/storage" -n kube-system \
  > "${platform_output}"
helm template cilium cilium/cilium --version "${CILIUM_VERSION}" -n kube-system \
  -f "${PLATFORM_DIR}/cilium-values.yaml" >> "${platform_output}"
helm template aws-load-balancer-controller eks/aws-load-balancer-controller \
  --version "${AWS_LOAD_BALANCER_CONTROLLER_VERSION}" -n kube-system \
  -f "${PLATFORM_DIR}/aws-load-balancer-controller-values.yaml" >> "${platform_output}"
helm template external-secrets external-secrets/external-secrets \
  --version "${EXTERNAL_SECRETS_VERSION}" -n external-secrets \
  -f "${PLATFORM_DIR}/external-secrets-values.yaml" >> "${platform_output}"
helm template metrics-server metrics-server/metrics-server --version "${METRICS_SERVER_VERSION}" \
  -n kube-system -f "${PLATFORM_DIR}/metrics-server-values.yaml" >> "${platform_output}"
helm template keda kedacore/keda --version "${KEDA_VERSION}" -n keda \
  -f "${PLATFORM_DIR}/keda-values.yaml" >> "${platform_output}"
helm template kyverno kyverno/kyverno --version "${KYVERNO_VERSION}" -n kyverno \
  -f "${PLATFORM_DIR}/kyverno-values.yaml" >> "${platform_output}"
helm template nvidia-device-plugin nvdp/nvidia-device-plugin \
  --version "${NVIDIA_DEVICE_PLUGIN_VERSION}" -n kube-system \
  -f "${PLATFORM_DIR}/nvidia-device-plugin-values.yaml" >> "${platform_output}"

helm template kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --version "${KUBE_PROMETHEUS_STACK_VERSION}" -n monitoring \
  -f "${PLATFORM_DIR}/kube-prometheus-stack-values.yaml" > "${observability_output}"
helm template loki grafana-community/loki --version "${LOKI_VERSION}" -n monitoring \
  -f "${PLATFORM_DIR}/loki-values.yaml" >> "${observability_output}"
helm template tempo grafana-community/tempo --version "${TEMPO_VERSION}" -n monitoring \
  -f "${PLATFORM_DIR}/tempo-values.yaml" >> "${observability_output}"
helm template opentelemetry-collector open-telemetry/opentelemetry-collector \
  --version "${OPENTELEMETRY_COLLECTOR_VERSION}" -n monitoring \
  -f "${PLATFORM_DIR}/opentelemetry-collector-values.yaml" >> "${observability_output}"
helm template alloy grafana/alloy --version "${ALLOY_VERSION}" -n monitoring \
  -f "${PLATFORM_DIR}/alloy-values.yaml" >> "${observability_output}"
helm template dcgm-exporter gpu-helm-charts/dcgm-exporter \
  --version "${DCGM_EXPORTER_VERSION}" -n monitoring \
  -f "${PLATFORM_DIR}/dcgm-exporter-values.yaml" >> "${observability_output}"
helm template rag-observability "${ROOT_DIR}/helm/observability" -n monitoring \
  >> "${observability_output}"
