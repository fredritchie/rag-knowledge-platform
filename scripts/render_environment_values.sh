#!/usr/bin/env bash
set -euo pipefail

output_path="${1:?Usage: render_environment_values.sh OUTPUT_PATH}"
required=(
  AWS_REGION APPLICATION_URL DOCUMENT_BUCKET DOCUMENT_KMS_KEY_ARN INGESTION_QUEUE_URL
  AURORA_ENDPOINT AURORA_SECRET_ARN RUNTIME_SECRET_ARN COGNITO_USER_POOL_ID
  COGNITO_CLIENT_ID COGNITO_AUTHORIZE_URL COGNITO_TOKEN_URL COGNITO_LOGOUT_URL
  ALB_TARGET_GROUP_ARN PUBLIC_SUBNET_CIDRS_JSON PRIVATE_SUBNET_CIDRS_JSON
  QDRANT_DIGEST GITHUB_REPOSITORY
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Required deployment setting ${name} is missing" >&2
    exit 1
  fi
done

jq -n \
  --arg region "${AWS_REGION}" \
  --arg app_url "${APPLICATION_URL}" \
  --arg queue_url "${INGESTION_QUEUE_URL}" \
  --arg bucket "${DOCUMENT_BUCKET}" \
  --arg bucket_key "${DOCUMENT_KMS_KEY_ARN}" \
  --arg issuer "https://cognito-idp.${AWS_REGION}.amazonaws.com/${COGNITO_USER_POOL_ID}" \
  --arg pool_id "${COGNITO_USER_POOL_ID}" \
  --arg client_id "${COGNITO_CLIENT_ID}" \
  --arg authorize_url "${COGNITO_AUTHORIZE_URL}" \
  --arg token_url "${COGNITO_TOKEN_URL}" \
  --arg logout_url "${COGNITO_LOGOUT_URL}" \
  --arg database_host "${AURORA_ENDPOINT}" \
  --arg runtime_secret "${RUNTIME_SECRET_ARN}" \
  --arg database_secret "${AURORA_SECRET_ARN}" \
  --arg target_group "${ALB_TARGET_GROUP_ARN}" \
  --arg qdrant_digest "${QDRANT_DIGEST}" \
  --arg certificate_identity "https://github.com/${GITHUB_REPOSITORY}/.github/workflows/supply-chain.yml@refs/heads/main" \
  --argjson public_cidrs "${PUBLIC_SUBNET_CIDRS_JSON}" \
  --argjson private_cidrs "${PRIVATE_SUBNET_CIDRS_JSON}" \
  '{
    config: {
      awsRegion: $region,
      ingestionQueueUrl: $queue_url,
      appUrl: $app_url,
      documentBucket: $bucket,
      documentKmsKeyArn: $bucket_key,
      cognitoIssuer: $issuer,
      cognitoUserPoolId: $pool_id,
      cognitoClientId: $client_id,
      cognitoAuthorizeUrl: $authorize_url,
      cognitoTokenUrl: $token_url,
      cognitoLogoutUrl: $logout_url
    },
    networkPolicy: {
      postgresqlCidrs: $private_cidrs,
      s3EndpointCidrs: $private_cidrs,
      albSourceCidrs: $public_cidrs,
      ciliumFqdnEgress: {
        enabled: true,
        postgresqlHost: $database_host,
        apiHosts: [("cognito-idp." + $region + ".amazonaws.com")],
        frontendHosts: [($authorize_url | capture("https://(?<host>[^/]+)").host)],
        workerHosts: [
          ("*.s3." + $region + ".amazonaws.com"),
          ("sqs." + $region + ".amazonaws.com"),
          "www.googleapis.com",
          "oauth2.googleapis.com"
        ]
      }
    },
    externalSecrets: {
      enabled: true,
      runtimeSecretArn: $runtime_secret,
      databaseSecretArn: $database_secret
    },
    keda: {enabled: true},
    targetGroupBinding: {enabled: true, targetGroupARN: $target_group},
    admissionPolicy: {enabled: true, certificateIdentity: $certificate_identity},
    images: {
      qdrant: {repository: "qdrant/qdrant", digest: $qdrant_digest}
    }
  }' > "${output_path}"

chmod 600 "${output_path}"
