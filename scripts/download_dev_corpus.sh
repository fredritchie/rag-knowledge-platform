#!/usr/bin/env bash
set -u

ROOT="${1:-rag_pdf_corpus}"
MANIFEST="$(cd "$(dirname "$0")" && pwd)/manifest.csv"
mkdir -p "$ROOT"/{ai-rag,security-standards,networking-rfc,reports-manuals,failed}

command -v curl >/dev/null 2>&1 || { echo "curl is required"; exit 1; }

success=0
failed=0

# Python's csv module safely handles commas and quoted fields in the manifest.
python3 - "$MANIFEST" <<'PY' | while IFS=$'\t' read -r number category title filename url; do
import csv, sys
with open(sys.argv[1], newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        print("\t".join([row['number'], row['category'], row['title'], row['filename'], row['url']]))
PY
  case "$category" in
    AI-RAG) dir="$ROOT/ai-rag" ;;
    Security-Standards) dir="$ROOT/security-standards" ;;
    Networking-RFC) dir="$ROOT/networking-rfc" ;;
    Reports-Manuals) dir="$ROOT/reports-manuals" ;;
    *) dir="$ROOT" ;;
  esac

  out="$dir/$filename"
  tmp="$out.part"
  printf '[%s/50] %s\n' "$number" "$title"

  if curl -L --fail --retry 3 --retry-delay 2 --connect-timeout 20 --max-time 300 \
      -A 'RAG-PDF-Development-Corpus/1.0' -o "$tmp" "$url"; then
    if head -c 5 "$tmp" | grep -q '%PDF-'; then
      mv "$tmp" "$out"
      echo "  OK -> $out"
    else
      echo "  ERROR: response is not a PDF"
      mv "$tmp" "$ROOT/failed/${filename}.invalid"
    fi
  else
    echo "  ERROR: download failed"
    rm -f "$tmp"
    printf '%s\t%s\t%s\n' "$number" "$title" "$url" >> "$ROOT/failed/failed_downloads.tsv"
  fi
done

echo
echo "Download pass complete."
echo "Validate count with: find \"$ROOT\" -type f -name '*.pdf' | wc -l"
echo "Inspect failures in: $ROOT/failed/"
