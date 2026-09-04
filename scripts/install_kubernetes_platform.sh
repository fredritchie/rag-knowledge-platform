#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
platform_dir="${root_dir}/helm/platform"

# shellcheck disable=SC1091
source "${platform_dir}/versions.env"

: "${EKS_CLUSTER_NAME:?Set EKS_CLUSTER_NAME}"
: "${AWS_REGION:?Set AWS_REGION}"
: "${VPC_ID:?Set VPC_ID}"

helm repo add cilium https://helm.cilium.io/
helm repo add eks https://aws.github.io/eks-charts
helm repo add external-secrets https://charts.external-secrets.io
helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/
helm repo add kedacore https://kedacore.github.io/charts
helm repo add kyverno https://kyverno.github.io/kyverno/
helm repo add nvdp https://nvidia.github.io/k8s-device-plugin
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
