#!/usr/bin/env bash
set -euo pipefail

rendered_file="${1:?Pass the rendered observability manifest}"
report_file="$(mktemp)"
actual_file="$(mktemp)"
expected_file="$(mktemp)"
trap 'rm -f "${report_file}" "${actual_file}" "${expected_file}"' EXIT

trivy config --severity HIGH,CRITICAL --format json "${rendered_file}" >"${report_file}" 2>/dev/null || true
jq -r '[.Results[]?.Misconfigurations[]?.ID] | group_by(.)[] | "\(.[0]) \(length)"' \
  "${report_file}" | sort >"${actual_file}"

printf '%s\n' \
  'KSV-0009 1' \
  'KSV-0010 1' \
  'KSV-0041 1' \
  'KSV-0045 2' \
  'KSV-0056 2' \
  'KSV-0114 1' \
  'KSV-0121 1' >"${expected_file}"

if ! diff -u "${expected_file}" "${actual_file}"; then
  echo "Observability manifests contain an unexpected high/critical finding set" >&2
  exit 1
fi

echo "Only the reviewed Prometheus Operator and node-exporter findings are present"
