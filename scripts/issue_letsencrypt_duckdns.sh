#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: DUCKDNS_TOKEN=... $0 EMAIL SUBDOMAIN [ACM_CERTIFICATE_ARN]" >&2
  exit 2
fi

: "${DUCKDNS_TOKEN:?DUCKDNS_TOKEN must be set}"
email=$1
subdomain=$2
existing_certificate_arn=${3:-}
aws_region=${AWS_REGION:-ap-south-1}
propagation_seconds=${DUCKDNS_PROPAGATION_SECONDS:-90}
fqdn="${subdomain}.duckdns.org"

if [[ ! "$subdomain" =~ ^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$ ]]; then
  echo "SUBDOMAIN must be a lowercase DuckDNS label" >&2
  exit 2
fi

for command in aws certbot curl; do
  command -v "$command" >/dev/null || {
    echo "$command is required" >&2
    exit 1
  }
done

work_dir=$(mktemp -d /tmp/rag-platform-letsencrypt.XXXXXX)
trap 'rm -rf "$work_dir"' EXIT

auth_hook="$work_dir/duckdns-auth.sh"
cleanup_hook="$work_dir/duckdns-cleanup.sh"

cat >"$auth_hook" <<'AUTH_HOOK'
#!/usr/bin/env bash
set -Eeuo pipefail
response=$(curl --fail --silent --show-error --get \
  --data-urlencode "domains=$DUCKDNS_SUBDOMAIN" \
  --data-urlencode "token=$DUCKDNS_TOKEN" \
  --data-urlencode "txt=$CERTBOT_VALIDATION" \
  https://www.duckdns.org/update)
[[ "$response" == "OK" ]]
sleep "$DUCKDNS_PROPAGATION_SECONDS"
AUTH_HOOK

cat >"$cleanup_hook" <<'CLEANUP_HOOK'
#!/usr/bin/env bash
set -Eeuo pipefail
curl --fail --silent --show-error --get \
  --data-urlencode "domains=$DUCKDNS_SUBDOMAIN" \
  --data-urlencode "token=$DUCKDNS_TOKEN" \
  --data-urlencode "txt=" \
  --data-urlencode "clear=true" \
  https://www.duckdns.org/update >/dev/null
CLEANUP_HOOK

chmod 0700 "$auth_hook" "$cleanup_hook"
export DUCKDNS_SUBDOMAIN="$subdomain" DUCKDNS_PROPAGATION_SECONDS="$propagation_seconds"

certbot certonly \
  --manual \
  --preferred-challenges dns \
  --manual-auth-hook "$auth_hook" \
  --manual-cleanup-hook "$cleanup_hook" \
  --non-interactive \
  --agree-tos \
  --email "$email" \
  --key-type ecdsa \
  --elliptic-curve secp256r1 \
  --domain "$fqdn" \
  --config-dir "$work_dir/config" \
  --work-dir "$work_dir/work" \
  --logs-dir "$work_dir/logs" >&2

certificate_dir="$work_dir/config/live/$fqdn"
import_arguments=(
  --region "$aws_region"
  --certificate "fileb://$certificate_dir/cert.pem"
  --private-key "fileb://$certificate_dir/privkey.pem"
  --certificate-chain "fileb://$certificate_dir/chain.pem"
)

if [[ -n "$existing_certificate_arn" ]]; then
  import_arguments+=(--certificate-arn "$existing_certificate_arn")
else
  import_arguments+=(
    --tags "Key=Project,Value=rag-platform" "Key=ManagedBy,Value=letsencrypt-duckdns"
  )
fi

aws acm import-certificate "${import_arguments[@]}" \
  --query CertificateArn --output text
