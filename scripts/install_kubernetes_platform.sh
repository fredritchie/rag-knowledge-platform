#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
platform_dir="${root_dir}/helm/platform"

# shellcheck disable=SC1091
source "${platform_dir}/versions.env"

: "${EKS_CLUSTER_NAME:?Set EKS_CLUSTER_NAME}"
: "${AWS_REGION:?Set AWS_REGION}"
: "${VPC_ID:?Set VPC_ID}"
: "${TELEMETRY_BUCKET:?Set TELEMETRY_BUCKET to the Terraform telemetry_bucket output}"
: "${SNS_TOPIC_ARN:?Set SNS_TOPIC_ARN to the Terraform sns_topic_arn output}"

kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f - >/dev/null
if ! kubectl --namespace monitoring get secret grafana-admin >/dev/null 2>&1; then
  echo "Create monitoring/grafana-admin with admin-user and admin-password keys before installation" >&2
  exit 1
fi

helm repo add cilium https://helm.cilium.io/
helm repo add eks https://aws.github.io/eks-charts
helm repo add external-secrets https://charts.external-secrets.io
helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/
helm repo add kedacore https://kedacore.github.io/charts
helm repo add kyverno https://kyverno.github.io/kyverno/
helm repo add nvdp https://nvidia.github.io/k8s-device-plugin
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo add grafana-community https://grafana-community.github.io/helm-charts
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo add gpu-helm-charts https://nvidia.github.io/dcgm-exporter/helm-charts
helm repo update

helm upgrade --install cilium cilium/cilium --version "${CILIUM_VERSION}" \
  --namespace kube-system --values "${platform_dir}/cilium-values.yaml" --wait
helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller \
  --version "${AWS_LOAD_BALANCER_CONTROLLER_VERSION}" --namespace kube-system \
  --values "${platform_dir}/aws-load-balancer-controller-values.yaml" \
  --set clusterName="${EKS_CLUSTER_NAME}" --set region="${AWS_REGION}" --set vpcId="${VPC_ID}" --wait
helm upgrade --install external-secrets external-secrets/external-secrets \
  --version "${EXTERNAL_SECRETS_VERSION}" --namespace external-secrets --create-namespace \
  --values "${platform_dir}/external-secrets-values.yaml" --wait
helm upgrade --install metrics-server metrics-server/metrics-server \
  --version "${METRICS_SERVER_VERSION}" --namespace kube-system \
  --values "${platform_dir}/metrics-server-values.yaml" --wait
helm upgrade --install keda kedacore/keda --version "${KEDA_VERSION}" \
  --namespace keda --create-namespace --values "${platform_dir}/keda-values.yaml" --wait
helm upgrade --install kyverno kyverno/kyverno --version "${KYVERNO_VERSION}" \
  --namespace kyverno --create-namespace --values "${platform_dir}/kyverno-values.yaml" --wait
helm upgrade --install nvidia-device-plugin nvdp/nvidia-device-plugin \
  --version "${NVIDIA_DEVICE_PLUGIN_VERSION}" --namespace kube-system \
  --values "${platform_dir}/nvidia-device-plugin-values.yaml" --wait

helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --version "${KUBE_PROMETHEUS_STACK_VERSION}" --namespace monitoring --create-namespace \
  --values "${platform_dir}/kube-prometheus-stack-values.yaml" \
  --set-string "alertmanager.config.receivers[0].sns_configs[0].topic_arn=${SNS_TOPIC_ARN}" \
  --set-string "alertmanager.config.receivers[0].sns_configs[0].sigv4.region=${AWS_REGION}" \
  --set-string "grafana.additionalDataSources[2].jsonData.defaultRegion=${AWS_REGION}" --wait
helm upgrade --install loki grafana-community/loki --version "${LOKI_VERSION}" \
  --namespace monitoring --values "${platform_dir}/loki-values.yaml" \
  --set-string loki.storage.bucketNames.chunks="${TELEMETRY_BUCKET}" \
  --set-string loki.storage.bucketNames.ruler="${TELEMETRY_BUCKET}" \
  --set-string loki.storage.bucketNames.admin="${TELEMETRY_BUCKET}" \
  --set-string loki.storage.s3.region="${AWS_REGION}" --wait
helm upgrade --install tempo grafana-community/tempo --version "${TEMPO_VERSION}" \
  --namespace monitoring --values "${platform_dir}/tempo-values.yaml" \
  --set-string tempo.storage.trace.s3.bucket="${TELEMETRY_BUCKET}" \
  --set-string tempo.storage.trace.s3.region="${AWS_REGION}" --wait
helm upgrade --install opentelemetry-collector open-telemetry/opentelemetry-collector \
  --version "${OPENTELEMETRY_COLLECTOR_VERSION}" --namespace monitoring \
  --values "${platform_dir}/opentelemetry-collector-values.yaml" --wait
helm upgrade --install alloy grafana/alloy --version "${ALLOY_VERSION}" \
  --namespace monitoring --values "${platform_dir}/alloy-values.yaml" --wait
helm upgrade --install dcgm-exporter gpu-helm-charts/dcgm-exporter \
  --version "${DCGM_EXPORTER_VERSION}" --namespace monitoring \
  --values "${platform_dir}/dcgm-exporter-values.yaml" --wait
helm upgrade --install rag-observability "${root_dir}/helm/observability" \
  --namespace monitoring --wait
