# GameFinder

[![ci](https://github.com/Moon-Knight13/gamefinder/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Moon-Knight13/gamefinder/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

**A Discord bot that turns "when is everyone free?" into actual games.**

DMs post games and hope players show up. GameFinder flips this: players mark
broad availability, the bot shows DMs when enough players are free, and games
land in windows that actually work. Availability intelligence, not guesswork.

## How It Works

```
1. Players mark availability     /available
2. Bot aggregates insights       /windows
3. DMs post games in best slots  /game create
4. Players RSVP                  Going / Maybe / Can't
5. Bot handles the rest          Notifications, reminders, events
```

## Features

### Availability Collection
- **Button grid** — tap to toggle Morning/Afternoon/Evening across 7 days
- **Week navigation** — Prev/Next buttons, configurable forecast window (1–6 weeks)
- **Calendar import** — attach .ics file, bot maps free periods to blocks
- **Timezone support** — set once with `/timezone`, all times display locally

### Scheduling Intelligence
- **Ranked windows** — slots sorted by available player count with green bar chart
- **Weekly heatmap** — visual grid showing player density per slot
- **Threshold filtering** — only show slots with enough players (configurable)
- **Drill-down** — `/whofree Saturday Evening` lists who's available

### Game Posting & RSVP
- **Three-tier RSVP** — Going / Maybe / Can't Make It (DMs need all three signals)
- **Targeted notifications** — bot @-mentions players who marked that slot available
- **Auto Discord Events** — created when Going reaches player cap
- **Game management** — list, cancel, edit posted games

### Server Admin
- **One-command setup** — `/setup` configures threshold, forecast, block hours, timezone
- **Nudge** — prompt members to submit availability
- **Stats** — response rate, top windows, games posted
- **Data deletion** — `/data delete` for users, auto-cleanup on server removal

## Commands

| Command | Description |
|---------|-------------|
| `/available` | Open availability grid |
| `/available-clear` | Clear all your availability |
| `/available-import` | Import from .ics calendar file |
| `/timezone <tz>` | Set your timezone |
| `/windows` | See best scheduling windows |
| `/whofree <day> <block>` | List who's free for a slot |
| `/game-create` | Post a new game |
| `/games` | List upcoming games |
| `/game-cancel <id>` | Cancel a game |
| `/setup` | Configure server settings |
| `/nudge` | Prompt for availability |
| `/stats` | View server stats |
| `/data-delete` | Delete all your data |

## Quick Start

1. **Invite the bot** to your Discord server (invite link TBD)
2. Run `/setup` to configure your server
3. Members run `/available` to mark when they're free
4. DMs check `/windows` and post games with `/game-create`

## Self-Hosting

### Prerequisites
- Python 3.12+
- A Discord bot token ([create one here](https://discord.com/developers/applications))

### Docker (recommended)

```bash
git clone https://github.com/Moon-Knight13/gamefinder.git
cd gamefinder
cp .env.example .env
# Edit .env — add your DISCORD_TOKEN
docker compose up -d
```

### Local

```bash
git clone https://github.com/Moon-Knight13/gamefinder.git
cd gamefinder
pip install -e ".[dev]"
cp .env.example .env
# Edit .env — add your DISCORD_TOKEN
python -m bot
```

### Discord Bot Setup

1. Create app at https://discord.com/developers/applications
2. Bot page: Reset Token, save to `.env` as `DISCORD_TOKEN`
3. OAuth2 scopes: `applications.commands` + `bot`
4. Bot permissions: Send Messages, Embed Links, Create Events, Manage Threads
5. Use Install Link to invite to your server

## Development

```bash
pip install -e ".[dev]"
pytest -v          # run tests
ruff check .       # lint
```

## Architecture

Single-process Python bot. No external services.

- **discord.py 2.x** — slash commands, buttons, embeds, scheduled events
- **SQLite (aiosqlite)** — persistence with WAL mode, guild-scoped queries
- **APScheduler** — reminder and cleanup jobs
- **icalendar** — .ics calendar import

All times stored UTC, displayed via Discord `<t:unix:F>` timestamps.

## Privacy

See [docs/PRIVACY_POLICY.md](docs/PRIVACY_POLICY.md). In short: we store
Discord user IDs, timezone preferences, and availability blocks. No message
content, no emails, no tracking. Data is auto-purged and deletable on request.

## Security

See [SECURITY.md](SECURITY.md). Guild isolation is enforced at the query
layer — every database query scopes by `guild_id`.

## License

MIT — see [LICENSE](LICENSE).
