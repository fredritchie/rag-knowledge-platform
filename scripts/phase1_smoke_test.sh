#!/usr/bin/env bash
set -euo pipefail

PDF="${1:?usage: ./scripts/phase1_smoke_test.sh path/to/document.pdf}"
DATA_DIR="${RAG_DATA_DIR:-.rag_data-smoke}"

rm -rf "$DATA_DIR"
ragctl validate "$PDF" --data-dir "$DATA_DIR"
ragctl ingest "$PDF" --data-dir "$DATA_DIR"
ragctl list --data-dir "$DATA_DIR"

echo "Smoke test complete. Inspect a document with ragctl inspect <document-id>."
