#!/usr/bin/env bash
set -euo pipefail

echo "=== pytest ==="
pip install --quiet -e ".[dev]"
pytest -v
echo "Tests passed."
