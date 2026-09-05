#!/usr/bin/env bash
set -euo pipefail

rendered_file="${1:?Pass the rendered platform manifest}"
report_file="$(mktemp)"
actual_file="$(mktemp)"
expected_file="$(mktemp)"
trap 'rm -f "${report_file}" "${actual_file}" "${expected_file}"' EXIT

trivy config --severity HIGH,CRITICAL --format json "${rendered_file}" >"${report_file}" 2>/dev/null || true
jq -r '[.Results[]?.Misconfigurations[]?.ID] | group_by(.)[] | "\(.[0]) \(length)"' \
  "${report_file}" | sort >"${actual_file}"

printf '%s\n' \
  'KSV-0005 5' \
  'KSV-0009 3' \
  'KSV-0010 1' \
  'KSV-0014 14' \
  'KSV-0017 3' \
  'KSV-0024 9' \
  'KSV-0041 5' \
  'KSV-0046 3' \
  'KSV-0056 3' \
  'KSV-0109 1' \
  'KSV-0114 4' \
  'KSV-0118 19' \
  'KSV-0119 1' \
  'KSV-0120 4' \
  'KSV-0121 1' >"${expected_file}"

if ! diff -u "${expected_file}" "${actual_file}"; then
  jq -r '.Results[] | .Misconfigurations[]? | select(.Severity == "HIGH" or .Severity == "CRITICAL") | "\(.ID): \(.Message)"' \
    "${report_file}" | sort >&2
  echo "Platform manifests contain an unexpected high/critical finding set" >&2
  exit 1
fi

echo "Only the reviewed CNI, controller, and device-plugin findings are present"
