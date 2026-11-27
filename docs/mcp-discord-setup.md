# mcp-discord Setup

## What it is

[mcp-discord](https://github.com/hanweg/mcp-discord) is an MCP server that gives Claude Code direct read/write access to Discord: list servers, read messages, send messages, manage channels and roles. Claude sees bot output in real time without screenshot relay.

## Why

During GameFinder development, Claude can read bot responses, check formatting, verify command output, and test interactions directly through the MCP bridge instead of relying on pasted screenshots or logs.

## Discord bot setup

mcp-discord needs its **own bot**, separate from GameFinder. Minimal permissions, single-purpose.

1. Go to [Discord Developer Portal](https://discord.com/developers/applications) and create a new application (e.g. `gamefinder-mcp-observer`).
2. Go to **Bot** tab. Click **Reset Token**, copy it, save it somewhere safe.
3. Enable all three **Privileged Gateway Intents**:
   - Presence Intent
   - Server Members Intent
   - Message Content Intent
4. Go to **OAuth2 > URL Generator**:
   - Scopes: `bot`
   - Bot Permissions: `Read Messages/View Channels`, `Send Messages`, `Read Message History`, `Add Reactions`
   - Copy the generated URL, open it, invite to your dev server.

## Environment variable

Add to `.env` in project root (already gitignored):

```bash
DISCORD_MCP_TOKEN=your-bot-token-here
```

`scripts/mcp-wrapper.sh` sources `.env` before launching the MCP server, same pattern as my_claude_dev. No bashrc exports needed.

## Configuration

`.mcp.json` (already in repo root, gitignored):

```json
{
  "mcpServers": {
    "mcp-discord": {
      "command": "./scripts/mcp-wrapper.sh",
      "args": ["uvx", "mcp-discord"],
      "env": {
        "DISCORD_TOKEN": "${DISCORD_MCP_TOKEN}"
      }
    }
  }
}
```

Wrapper loads `.env` → `DISCORD_MCP_TOKEN` becomes available → `.mcp.json` maps it to `DISCORD_TOKEN` for the server. Requires `uv` installed.

## Verify

1. Source your shell profile or export the token in current shell.
2. Start a Claude Code session in the gamefinder directory.
3. MCP server list should show `mcp-discord` connected.
4. Ask Claude to `list_servers` — should return your dev server.

## Available tools

**Server info:** `list_servers`, `get_server_info`, `get_channels`, `list_members`, `get_user_info`

**Messages:** `send_message`, `read_messages`, `add_reaction`, `add_multiple_reactions`, `remove_reaction`, `moderate_message`

**Channels:** `create_text_channel`, `delete_channel`

**Roles:** `add_role`, `remove_role`

## Security notes

- This bot is **not** GameFinder. It's a separate observer bot with its own token.
- Grant minimal permissions — read + send + react is enough for dev work.
- Never commit the token. `.mcp.json` is gitignored; token comes from env var only.
- Keep this bot out of production servers. Dev server only.
- If the bot token leaks, regenerate immediately in the Developer Portal.
