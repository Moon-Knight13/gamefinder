#!/usr/bin/env bash
# mcp-wrapper.sh — load .env then exec the MCP server command.
# Keeps secrets in .env only; no bashrc exports needed.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

exec "$@"
