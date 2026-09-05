#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: DUCKDNS_TOKEN=... $0 SUBDOMAIN IPV4_ADDRESS" >&2
  exit 2
fi

: "${DUCKDNS_TOKEN:?DUCKDNS_TOKEN must be set}"
subdomain=$1
ipv4_address=$2

if [[ ! "$subdomain" =~ ^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$ ]]; then
  echo "SUBDOMAIN must be a lowercase DuckDNS label" >&2
  exit 2
fi

if [[ ! "$ipv4_address" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
  echo "IPV4_ADDRESS must be an IPv4 address" >&2
  exit 2
fi

IFS=. read -r octet1 octet2 octet3 octet4 <<<"$ipv4_address"
for octet in "$octet1" "$octet2" "$octet3" "$octet4"; do
  if ((10#$octet > 255)); then
    echo "IPV4_ADDRESS must be an IPv4 address" >&2
    exit 2
  fi
done

response=$(curl --fail --silent --show-error --get \
  --data-urlencode "domains=$subdomain" \
  --data-urlencode "token=$DUCKDNS_TOKEN" \
  --data-urlencode "ip=$ipv4_address" \
  https://www.duckdns.org/update)

if [[ "$response" != "OK" ]]; then
  echo "DuckDNS rejected the A-record update" >&2
  exit 1
fi

printf 'Updated %s.duckdns.org to %s\n' "$subdomain" "$ipv4_address"
