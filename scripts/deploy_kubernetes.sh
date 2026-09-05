#!/usr/bin/env bash
set -euo pipefail

operation="${1:-application}"
if [[ ! "${operation}" =~ ^(platform|application|all)$ ]]; then
  echo "Operation must be platform, application, or all" >&2
  exit 1
fi

required=(AWS_REGION EKS_CLUSTER_NAME GITHUB_REPOSITORY)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Required deployment setting ${name} is missing" >&2
    exit 1
  fi
done

aws eks update-kubeconfig --name "${EKS_CLUSTER_NAME}" --region "${AWS_REGION}" >/dev/null
kubectl version --client
kubectl --request-timeout=15s get --raw=/readyz >/dev/null

if [[ "${operation}" == "platform" || "${operation}" == "all" ]]; then
  : "${GRAFANA_ADMIN_SECRET_ARN:?Set GRAFANA_ADMIN_SECRET_ARN}"
  if ! grafana_secret="$(aws secretsmanager get-secret-value \
    --secret-id "${GRAFANA_ADMIN_SECRET_ARN}" --query SecretString --output text 2>/dev/null)"; then
    grafana_secret="$(jq -n --arg user admin --arg password "$(openssl rand -hex 32)" \
      '{"admin-user":$user,"admin-password":$password}')"
    aws secretsmanager put-secret-value --secret-id "${GRAFANA_ADMIN_SECRET_ARN}" \
      --secret-string "${grafana_secret}" >/dev/null
  fi
  grafana_user="$(jq -er '."admin-user"' <<<"${grafana_secret}")"
  grafana_password="$(jq -er '."admin-password"' <<<"${grafana_secret}")"
  kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  kubectl --namespace monitoring create secret generic grafana-admin \
    --from-literal=admin-user="${grafana_user}" \
    --from-literal=admin-password="${grafana_password}" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  unset grafana_secret grafana_user grafana_password

  : "${VPC_ID:?Set VPC_ID}"
  : "${TELEMETRY_BUCKET:?Set TELEMETRY_BUCKET}"
  : "${SNS_TOPIC_ARN:?Set SNS_TOPIC_ARN}"
  make kubernetes-platform-install
fi

if [[ "${operation}" == "application" || "${operation}" == "all" ]]; then
  environment="${DEPLOY_ENVIRONMENT:?Set DEPLOY_ENVIRONMENT}"
  image_values="gitops/environments/${environment}/images.yaml"
  if [[ ! -f "${image_values}" ]]; then
    echo "Missing reviewed image overlay ${image_values}" >&2
    exit 1
  fi
  environment_values="$(mktemp)"
  trap 'rm -f "${environment_values}"' EXIT
  scripts/render_environment_values.sh "${environment_values}"

  helm lint helm/rag-platform --values "${environment_values}" --values "${image_values}"
  helm upgrade --install rag-platform helm/rag-platform \
    --namespace rag-platform --create-namespace \
    --values "${environment_values}" \
    --values "${image_values}" \
    --atomic --wait --timeout 30m --history-max 10

  kubectl --namespace rag-platform rollout status deployment/rag-platform-frontend --timeout=10m
  kubectl --namespace rag-platform rollout status deployment/rag-platform-api --timeout=10m
  kubectl --namespace rag-platform get deployments,statefulsets,pods,externalsecrets,targetgroupbindings
fi
