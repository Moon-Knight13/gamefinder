# GameFinder

[![ci](https://github.com/Moon-Knight13/gamefinder/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Moon-Knight13/gamefinder/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![discord.py 2.4+](https://img.shields.io/badge/discord.py-2.4+-5865F2.svg)](https://github.com/Rapptz/discord.py)

**A Discord bot that turns "when is everyone free?" into actual games.**

DMs post games and hope players show up. GameFinder flips this: players mark
broad availability, the bot shows DMs when enough players are free, and games
land in windows that actually work. Availability intelligence, not guesswork.

Built with Discord's Components V2 for a native, interactive calendar
experience — no web links, no external tools, everything inside Discord.

## How It Works

```
1. Players mark availability     /available        (interactive calendar grid)
2. Bot aggregates insights       /windows          (ranked windows + campaign viability)
3. DMs post games in best slots  Post Game button  (modal — zero friction)
4. Players RSVP                  Going / Maybe / Can't / Spectator / Waitlist
5. Quorum reached                Discord Event created, Going players DM'd
```

## Features

### Interactive Availability Calendar
- **Components V2 weekly grid** — one-tap AM/MID/PM toggles per day, 7 days visible
- **Localized times** — Discord `<t:>` timestamps so every player sees their own timezone
- **Recurring patterns** — "every Friday evening" fills 6 months in one click
- **Custom hours** — drill into a day to set exact start/end times
- **Calendar import** — attach .ics file, bot maps free periods to blocks
- **Week navigation** — browse up to 26 weeks ahead

### Scheduling Intelligence
- **Oneshot windows** — best single dates ranked by player count, with Post Game buttons
- **Campaign-viable slots** — same players consistently free across 3+ weeks
- **Combined view** — both in one `/windows` response so DMs see the full landscape
- **Matchmaking language** — "9 players could fill your table" with one-click game posting

### Game Posting & RSVP
- **Five-tier RSVP** — Going, Maybe, Can't Make It, Spectator, Waitlist
- **Targeted notifications** — bot @-mentions players who marked that slot available
- **Auto Discord Events** — created when Going reaches player cap
- **Private DMs** — Going players receive the event link to get reminders
- **Full CRUD** — create, edit, cancel, list games (filter by status)

### Campaigns
- **Campaign creation** — recurring games with defined session count (1–52), weekly or biweekly cadence
- **Roster management** — Join, Leave, Spectate buttons (persistent across restarts)
- **Progress tracking** — visual progress bar, next session dates, roster count, `/session-complete` advances it
- **Consistency detection** — identifies players reliably free for the same weekly slot
- **Lifecycle** — active, paused, completed states with auto-complete at session count

### Server Admin
- **One-command setup** — `/setup` configures scheduling channel, timezone, block hours, threshold, forecast window (1–12 weeks)
- **Live dashboard** — `/widget` posts a pinned stats embed that auto-updates hourly (games, campaigns, top windows)
- **Nudge** — prompt members who haven't submitted availability
- **Stats** — response rate, top windows, games posted
- **Data deletion** — `/data-delete` with confirmation for GDPR compliance
- **Dev tools** — `/simulate-rsvp` and `/simulate-roster` for testing (gated behind `DEV_MODE`)

## Commands

### Players
| Command | Description |
|---------|-------------|
| `/available` | Open interactive calendar grid |
| `/available-clear` | Clear all your availability |
| `/available-quick` | Quick-set a recurring day + block |
| `/available-import` | Import from .ics calendar file |
| `/timezone` | Set your timezone (IANA name) |
| `/data-delete` | Delete all your data (with confirmation) |

### Dungeon Masters
| Command | Description |
|---------|-------------|
| `/windows` | See oneshot + campaign windows with Post Game buttons |
| `/whofree` | List who's free for a specific date + block |
| `/game-create` | Post a new game (or use Post Game button from `/windows`) |
| `/game-edit` | Edit a game you created |
| `/game-cancel` | Cancel a game and notify RSVP'd players |
| `/games` | List games (filter: open, full, cancelled, all) |
| `/campaign-create` | Start a recurring campaign (weekly/biweekly, 1–52 sessions) |
| `/campaigns` | List active campaigns |
| `/campaign-status` | View campaign details and roster |
| `/campaign-pause` | Pause or resume a campaign |
| `/campaign-end` | End a campaign with final stats |
| `/session-complete` | Mark a campaign session done (auto-completes at count) |

### Admin
| Command | Description |
|---------|-------------|
| `/setup` | Configure server settings |
| `/widget` | Post a live stats dashboard that auto-updates hourly |
| `/nudge` | Prompt members to submit availability |
| `/stats` | View server scheduling stats |

## Quick Start

1. **Invite the bot** to your Discord server (invite link TBD)
2. Run `/setup` to configure timezone and scheduling channel
3. Members run `/available` to mark when they're free
4. DMs check `/windows` — post games directly from the best windows

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

The image is also available on GHCR:

```bash
docker pull ghcr.io/moon-knight13/gamefinder:latest
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

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DISCORD_TOKEN` | Yes | — | Bot token from Discord Developer Portal |
| `DISCORD_MCP_TOKEN` | No | — | Token for MCP Discord integration (dev only) |
| `DB_PATH` | No | `data/gamefinder.db` | SQLite database path |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `DEV_MODE` | No | `false` | Enable dev commands (`/simulate-*`) |

## Development

```bash
pip install -e ".[dev]"
pytest -v          # 61 tests
ruff check .       # lint
```

### Testing

The test suite includes:
- **Unit tests** — database queries, RSVP logic, availability CRUD
- **BDD scenarios** — full user story flows (player → DM → game → quorum)
- **Stress tests** — 50 players, 20 concurrent games, 30 simultaneous updates
- **Test factory** — `tests/factory.py` generates realistic TTRPG scenarios with configurable party archetypes

## Architecture

Single-process Python bot. No external services.

- **discord.py 2.4+** — Components V2 (LayoutView, Container, Section), slash commands, persistent views, scheduled events
- **SQLite (aiosqlite)** — WAL mode, guild-scoped queries, auto-migration
- **APScheduler** — auto-purge stale availability, 24h game reminders, session-day pings, hourly widget updates
- **icalendar** — .ics calendar import

All times stored UTC. Displayed via Discord `<t:>` timestamps — each viewer
sees their own timezone automatically.

### Database Schema

9 tables: `guilds`, `users`, `availability`, `recurring_availability`, `games`,
`rsvps`, `campaigns`, `campaign_roster`, `sessions`. Every query scopes by
`guild_id` — no cross-server data leakage.

### Deployment

Target: Oracle Cloud Always Free ARM VM. Docker Compose with volume-mounted
SQLite. Bot connects outbound to Discord gateway — no exposed ports, no web
server, no domain needed. GitHub Actions CI runs tests and linting on every push.

## Privacy

See [docs/PRIVACY_POLICY.md](docs/PRIVACY_POLICY.md). In short: we store
Discord user IDs, timezone preferences, and availability blocks. No message
content, no emails, no tracking. Data is auto-purged and deletable on request.

## Security

See [SECURITY.md](SECURITY.md). Guild isolation is enforced at the query
layer — every database query scopes by `guild_id`.

## License

MIT — see [LICENSE](LICENSE).
