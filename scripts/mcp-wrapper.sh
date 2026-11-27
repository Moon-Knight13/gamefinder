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

# mcp-discord reads DISCORD_TOKEN; use the observer bot token for MCP
if [[ -n "${DISCORD_MCP_TOKEN:-}" ]]; then
    export DISCORD_TOKEN="$DISCORD_MCP_TOKEN"
fi

exec "$@"
