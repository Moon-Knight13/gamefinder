#!/usr/bin/env bash
# mcp-wrapper.sh — load .env then exec the MCP server command.
# Keeps secrets in .env only; no bashrc exports needed.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$PROJECT_DIR/.env"
    set +a
fi

# mcp-discord reads DISCORD_TOKEN; use the observer bot token for MCP.
# DISCORD_MCP_TOKEN must be set explicitly — never fall through to the
# GameFinder bot's DISCORD_TOKEN, which may carry higher privileges.
if [[ -z "${DISCORD_MCP_TOKEN:-}" ]]; then
    echo "FATAL: DISCORD_MCP_TOKEN not set. Refusing to start — will not fall through to DISCORD_TOKEN." >&2
    exit 1
fi
export DISCORD_TOKEN="$DISCORD_MCP_TOKEN"

exec "$@"
