# GameFinder — Design Spec

**Date:** 2026-11-26
**Status:** Approved (2026-11-26)

## Problem Statement

As a DM, I've not had very good RSVP interest when I post a game. I believe this is because players may not be available during the slot I posted. If I knew the mean average of when my minimum player count is free on a given day and time, I can better advertise my games in a window that works for them.

## Intent

An end-to-end TTRPG scheduling bot for Discord. Players mark soft availability, the bot aggregates it into insights, DMs see when enough players are free, post games in those windows, and players RSVP — all in one system. Replaces GroupFlows and similar tools with something purpose-built for the TTRPG scheduling problem.

The differentiator is **availability intelligence**: instead of posting a game and hoping, DMs know the landscape first. The game posting and RSVP features close the loop so servers need one bot, not two.

### Who it's for

- **TTRPG Discord servers** of any size where games get posted and need players
- **DMs** who want to know when players are actually free before committing to a date
- **Players** who want games to land on times that work for them

### Why this doesn't exist

Every existing scheduling bot optimizes for "find ONE best time for ONE event." GameFinder optimizes for "show me the availability landscape so I can make better decisions over time." Standing data, not one-off polls.

## Goals

1. Players mark broad availability (blocks, not hours) with minimal effort — no commitment, just signal
2. DMs see aggregate insights: which slots have enough players, ranked by count
3. DMs post games into best windows, players RSVP — full loop in one bot
4. Players who marked a slot get notified when a game lands there
5. All times display in each viewer's local timezone
6. Public bot — anyone adds it to their server via invite link
7. Simple setup — add bot, run one command, works

## Non-goals

- Campaign management, session notes, character tracking
- Calendar write-back (read-only .ics import is in scope)
- Voice channel or VTT integration
- Mobile app — Discord IS the interface
- Payment/subscription gating

## Anti-goals

- Requiring players to leave Discord
- Making availability feel like a commitment
- Complex setup or admin overhead
- Needing a second bot for any part of the scheduling workflow

## Approach

### Why custom (not an existing tool)

| Existing tool | Gap |
|---|---|
| Supatimer | Week-only, resets weekly, no multi-week forecast |
| sesh / Apollo | Event-centric polls, no standing availability pool |
| Timescry | Per-session polls, no aggregate insights |
| When2meet / Timeful | Web-only, no Discord-native experience |
| Rallly / Doodle | One-off polls, no persistent data |

No existing bot provides standing availability data with threshold-based insights across a configurable window.

**Stack:** Python 3.12+, discord.py 2.x, SQLite (aiosqlite), APScheduler, icalendar.

**Deployment:** Hosted public bot. Users add via invite link. Bot runs as a hosted service (platform TBD — likely Fly.io, Railway, or similar). Self-hosting is secondary and optional (Docker image published for those who want it).

## Key Decisions

1. **No role gating.** Anyone can view windows and insights. Any member can mark availability. Open community model.
2. **Fixed three blocks, customizable hour boundaries.** Morning/Afternoon/Evening labels stay fixed. Server admin adjusts hour boundaries via `/setup`. Variable block count is v2 if needed.
3. **Availability is soft, RSVPs are firm.** Availability = "yeah that could work" (no commitment). RSVP on a posted game = commitment. Two distinct layers.
4. **Configurable forecast window.** Server admin sets how far ahead availability extends (1–6 weeks, default 3).

## Design

### Player Experience

**Mark availability:**
```
/available
```
Opens ephemeral button grid. Three blocks (Morning/Afternoon/Evening) across 7 days. Tap to toggle. Navigate weeks with Prev/Next buttons. Data persists until cleared or updated.

```
/available import
```
Attach .ics file. Bot reads free/busy data and auto-fills matching blocks.

```
/available clear
```
Reset all entries.

```
/timezone set Europe/London
```
Set once, remembered. All display adjusts to viewer's timezone via Discord `<t:>` timestamps.

**Block defaults (customizable per server):**
- Morning: 9am–12pm
- Afternoon: 12pm–5pm
- Evening: 5pm–10pm

### DM Experience

**See where players are free:**
```
/windows
```
Shows two things:

**Ranked list** — slots sorted by available player count, filtered by threshold:
```
📊 Best Windows (4+ players) — Next 3 weeks
28 of 36 responded

🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩  11  Sat Nov 30 · Evening  (5pm–10pm local)
🟩🟩🟩🟩🟩🟩🟩🟩🟩       9  Fri Dec 6 · Evening   (5pm–10pm local)
🟩🟩🟩🟩🟩🟩🟩🟩          8  Tue Dec 3 · Evening   (5pm–10pm local)
🟩🟩🟩🟩🟩🟩🟩            7  Sat Dec 7 · Afternoon (12pm–5pm local)
...
```

**Weekly heatmap** — grid with player counts per cell, green intensity = viability, grey = below threshold.

**Options:**
- `/windows --min 6` — raise threshold
- `/windows --week 2` — specific week

**Drill into a slot:**
```
/whofree Saturday Evening
```
Ephemeral response listing player names available for that slot.

### Server Setup

```
/setup
```
Admin configures:
- Forecast window (1–6 weeks)
- Default player threshold
- Block hour boundaries
- Channel for bot responses (optional — works in any channel by default)

```
/nudge
```
Post a friendly prompt for members who haven't submitted availability.

```
/stats
```
Response rate, most popular windows, trend data.

### Oneshots (Single Events)

**Create:**
```
/game create
```
Title, description, player cap, and slot via two paths:
- **Quick path:** dropdown of computed viable windows (from `/windows` data)
- **Freeform path:** manual date + block or custom time

Bot creates a **forum post** in the scheduling forum channel (tagged: Oneshot, Open). Post contains game embed with custom three-tier RSVP buttons:
- **Going** — "Count me in, I'm coming" (DM preps for this player)
- **Maybe** — "Possible, don't count on me yet" (DM knows the upside)
- **Can't Make It** — "Not this one" (DM stops wondering)

Three tiers give DMs the signal they need to plan prep work. "4 Going, 2 Maybe" is actionable. "6 Interested" is not.

**Targeted channel notifications:**
Bot @-mentions players who marked that slot as available:

> "🎲 **Lost Mine of Phandelver** just posted for **Tuesday Evening**!
> Based on your availability: @Sam @Alex @Jamie @Morgan @Taylor @Casey @Riley @Jordan @Drew
> RSVP below — open to everyone!"

Mentions are a nudge, not a gate. Anyone can RSVP regardless of availability data.

**Discord Scheduled Event (auto-created at quorum):**
When Going count reaches minimum player cap, bot auto-creates a native Discord Scheduled Event for the date/time. This provides:
- Calendar visibility (shows in Discord's event bar and user calendar)
- Discord's built-in reminders
- Server-wide event awareness

Bot's custom RSVP data remains the source of truth for headcount — the Discord event is for visibility and reminders, not for tracking commitment. If Going drops below minimum (cancellations), event is removed and creator notified.

**Management:**
- `/games` — list upcoming games with RSVP counts (Going/Maybe/Can't)
- `/game cancel <id>` — cancel, notify Going + Maybe players
- `/game edit <id>` — modify, notify of changes

**Reminders:**
- Discord Scheduled Event handles basic reminders natively
- Bot supplements: creator gets prep summary 24h before — "4 Going, 2 Maybe, 1 Can't — you're set"
- Bot posts session-day ping in game's forum thread: "@Going — tonight! @Maybe — still in?"

### Campaigns (Recurring Games)

**Scope a campaign — find consistent slots:**
```
/campaign scope --players 4 --sessions 8
```
Queries availability data for CONSISTENCY, not just count. Shows slots where the same people overlap across multiple weeks:

```
📊 Campaign-Viable Slots (4+ consistent players, 8 sessions)

6 consistent  Tue Evening   — Alex, Sam, Jamie, Morgan, Casey, Riley
5 consistent  Sat Evening   — Taylor, Jordan, Drew, Pat, Quinn
4 consistent  Fri Evening   — Sam, Morgan, Casey, Drew
```

"Consistent" = marked available across all forecast weeks. Stronger signal than oneshot count.

**Create a campaign:**
```
/campaign create "Curse of Strahd"
```
- Title, description, player min/max
- Recurring slot: day + block
- Cadence: weekly, biweekly, or every N weeks
- Expected duration (number of sessions or open-ended)

Bot posts campaign embed in scheduling channel. Players join the **roster** (not per-session RSVP). @-mentions consistent players from `/campaign scope`.

**Session lifecycle:**
Each recurring session is auto-generated from the campaign schedule.
- Bot posts weekly confirmation: "Session 4 this Tuesday. @roster — react if you CAN'T make it"
- Default = attending (reduces friction vs. confirming every week)
- Absence threshold: "3/5 confirmed. Below minimum — cancel or run short?" (creator decides)
- Discord Scheduled Event auto-created per session
- If cadence is biweekly: bot skips alternate weeks, players see "Next session: Dec 17" not "Dec 10"

**Campaign management:**
- `/campaign roster` — view members, attendance history
- `/campaign status` — next session, overall attendance rate, roster health
- `/campaign invite @player` — add to roster
- `/campaign leave` — player removes self
- `/session cancel` — skip one session, notify roster
- `/session reschedule` — move one session, check roster availability for alternate slot
- `/campaign pause` — pause sessions (holiday break), resume later
- `/campaign end` — wrap up, final stats

### Timezone Handling

- All storage in UTC
- Per-user timezone stored via `/timezone set`, remembered
- Display uses Discord's native `<t:unix:F>` — renders in viewer's local timezone automatically
- .ics import interprets events in their declared timezone
- Block boundaries defined in server timezone, displayed in viewer's timezone

## Native Discord Features Used

Build on Discord's platform, don't rebuild it:

| Feature | Used for | Replaces |
|---|---|---|
| **Native Polls** (multi-select, up to 10 answers) | Availability collection — poll per day with Morning/Afternoon/Evening answers | Custom button grid |
| **Forum Channels** (with tags) | Game listings — one post per game, tagged Oneshot/Campaign, Open/Full/Complete | Flat channel with embeds |
| **Threads** | Session discussion under campaign forum posts | Nothing (new capability) |
| **Scheduled Events** | Calendar visibility, built-in reminders, event bar | Custom reminder system (partially) |
| **Discord Timestamps** (`<t:unix:F>`) | Timezone-aware time display | Custom timezone conversion |

**What stays custom** (no native equivalent):
- Availability aggregation, threshold filtering, heatmap
- `/windows` insights — ranked viable slots
- `/campaign scope` — consistency analysis
- Three-tier RSVP (Going/Maybe/Can't) — Scheduled Events only have "Interested"
- Targeted @-mentions based on availability data
- Campaign roster + session lifecycle management
- Auto-event creation at quorum

## Technical Architecture

```
┌─────────────────────────┐
│   Discord API (Gateway)  │
└──────────┬──────────────┘
           │
┌──────────▼──────────────┐
│    GameFinder Bot        │
│    (Python / discord.py) │
│                          │
│  ┌────────────────────┐  │
│  │  Slash Commands    │  │
│  │  Button Handlers   │  │
│  │  Scheduler (APSch) │  │
│  └────────┬───────────┘  │
│           │              │
│  ┌────────▼───────────┐  │
│  │  SQLite Database   │  │
│  │  (per-guild data)  │  │
│  └────────────────────┘  │
└──────────────────────────┘
```

Single process. No external services. SQLite handles the scale (hundreds of guilds, thousands of users trivially).

**Database tables:**
- `guilds` — server config (threshold, forecast window, block times, scheduling channel)
- `users` — discord ID, timezone, notification preference
- `availability` — user_id, guild_id, date, block, created_at (UTC)
- `games` — id, guild_id, creator_id, title, description, slot_date, slot_block, player_cap, status, campaign_id (nullable)
- `rsvps` — game_id, user_id, status (going/not_going/maybe), timestamp
- `campaigns` — id, guild_id, creator_id, title, description, day_of_week, block, cadence (weekly/biweekly/every_n), cadence_interval, player_min, player_max, status, started_at
- `campaign_roster` — campaign_id, user_id, joined_at, status (active/left)
- `sessions` — id, campaign_id, session_number, date, status (scheduled/cancelled/completed), discord_event_id

**Deployment:**

Target: Oracle Cloud Always Free ARM VM (2 OCPU, 12GB RAM, 200GB disk — permanently free).

```
Oracle Cloud free tier ARM VM
├── Docker + Docker Compose
├── gamefinder container (Python + SQLite)
├── Volume for SQLite persistence
└── Firewall: SSH only, all other ports closed
```

Bot connects outbound to Discord gateway. No exposed ports, no web server, no reverse proxy, no domain needed.

**CI/CD: GitHub Actions → SSH deploy**
Push to `main` triggers automated deployment:
1. GitHub Actions runs tests + linting
2. On pass, SSHs into Oracle VM
3. Pulls latest code, rebuilds container, restarts
4. SSH key stored in GitHub repository secrets

**Setup:** `git clone` on VM, add `.env` with bot token, `docker compose up -d`. GitHub Actions handles all subsequent deploys.

**Self-hosters:** Docker image published to GHCR. Anyone can `docker pull` and run with their own bot token.

**Security:**
- Bot token in `.env` on VM only, never in repo
- SSH key in GitHub secrets, Oracle VM firewall SSH-only
- SQLite file permissions `600`, volume-mounted
- All queries scoped by `guild_id` — no cross-guild data leakage
- Auto-purge availability data older than forecast window
- `/data delete` — user requests full data deletion, bot wipes immediately
- Auto-delete guild data 30 days after bot removed from server
- Privacy policy + security policy published in repo

**Discord requirements:**
- No privileged intents needed (slash commands only, generic `/nudge`)
- Standard permissions: Send Messages, Embed Links, Create Events, Manage Threads
- Privacy policy linked in bot profile
- Bot verification at 100+ servers

## What's Left to the Builder

- Exact Discord embed layouts and button grid mechanics
- Error handling UX (rate limits, unreachable DB, permission errors)
- Database migration strategy between versions
- Notification bridge: message parsing heuristics vs explicit `/notify` trigger
- README, contributing guide, license (leaning MIT)
- Bot branding and icon
- Hosting platform selection and cost model
- Privacy policy (bot stores Discord user IDs and timezone)
