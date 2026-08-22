#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

echo
echo "Development environment ready."
echo "Activate with: source .venv/bin/activate"
echo "Try: ragctl --help"
