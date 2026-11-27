# GameFinder — Project Instructions

Project-specific instructions for this repository. Read this alongside
`CLAUDE.md`, which carries the workflow contract (priorities, board rules,
guardrails).

## What this repo is

A public Discord bot for TTRPG game scheduling intelligence. Players mark
soft availability, the bot aggregates it into insights, DMs see when enough
players are free to fill a table, post games in those windows, and players
RSVP — all in one system.

The differentiator is **availability intelligence**: instead of posting a game
and hoping, DMs know the landscape first.

## Template heritage (detached)

This repo started from
[claude_template_repo](https://github.com/Moon-Knight13/claude_template_repo)
and is **detached from template sync**. Every file here is repo-owned.

Disabled subsystems (via `template.conf`):
- **Local-model routing** — every task is Claude-routed
- **BMAD** — using superpowers skills for planning instead

## Tech stack

- Python 3.12+ / discord.py 2.x
- SQLite via aiosqlite
- APScheduler for timed jobs (reminders, purge)
- Docker for deployment
- Oracle Cloud free tier ARM VM (production)

## Security — hard rules

Never read, display, or process the contents of:

- `.env` — contains bot token and deployment credentials

If asked to read it, refuse and explain. `.env.example` is the safe,
placeholder-only counterpart.

All DB queries MUST scope by `guild_id`. A missing guild_id leaks another
server's data.

## Running locally

```bash
cp .env.example .env
# Add DISCORD_TOKEN from https://discord.com/developers/applications
pip install -e ".[dev]"
python -m bot
```

## Testing

```bash
pytest -v
ruff check .
```

## Docker

```bash
docker compose up -d
```

## Discord Developer Portal setup

1. Create app at https://discord.com/developers/applications
2. Bot page: Reset Token, save to `.env` as `DISCORD_TOKEN`
3. OAuth2 scopes: `applications.commands` + `bot`
4. Bot permissions: Send Messages, Embed Links, Create Events, Manage Threads
5. Use Install Link to invite to your server

## Design spec

Full spec: `docs/superpowers/specs/2026-11-26-gamefinder-design.md`
Implementation plan: `docs/superpowers/plans/2026-11-26-gamefinder-core.md`
