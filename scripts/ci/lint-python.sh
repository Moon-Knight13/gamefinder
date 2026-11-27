#!/usr/bin/env bash
set -euo pipefail

echo "=== Ruff lint ==="
pip install --quiet ruff
ruff check .
echo "Lint passed."
