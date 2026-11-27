# GameFinder Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core GameFinder Discord bot — availability collection, window insights, game posting with RSVP, and admin tools — as a standalone public repo deployed to Oracle Cloud.

**Architecture:** Single-process Python Discord bot using discord.py 2.x with cog-based command organization. SQLite for persistence via aiosqlite. APScheduler for timed jobs (reminders, purge). All times stored UTC, displayed via Discord timestamps.

**Tech Stack:** Python 3.12+, discord.py 2.x, aiosqlite, APScheduler, icalendar, pytest + pytest-asyncio, Docker, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-26-gamefinder-design.md`

## Global Constraints

- Repo created from `Moon-Knight13/claude_template_repo` — CI gates (semgrep, gitleaks, container scan), devcontainer, board, and pre-commit hooks come from template. Detach from template sync after creation.
- Python 3.12+ only — use modern syntax (match, `type` aliases)
- discord.py >= 2.4.0 — required for Poll and Forum support
- No privileged intents — bot uses slash commands only
- All DB queries MUST include `guild_id` in WHERE clause — no cross-guild leakage
- All user-facing times use Discord `<t:unix:F>` format — never raw datetime strings
- Three fixed blocks: `morning`, `afternoon`, `evening` — stored as enum strings
- Block boundaries configurable per guild, defaults: morning=09-12, afternoon=12-17, evening=17-22
- MIT license
- Keep `docs/explainer/index.html` in sync with `README.md` — per template contract

## Review Focus

1. **Guild isolation** — a query missing `guild_id` leaks another server's data. Every DB function that reads or writes must scope by guild. No test currently checks cross-guild isolation explicitly — add to Task 1.
2. **Timezone edge cases** — user sets timezone `Pacific/Auckland` (UTC+13), block "Evening 5pm" in server timezone `America/New_York` falls on a different UTC date. Availability storage must handle date rollover.
3. **Discord rate limits on @-mentions** — game posted to a window with 20+ available players generates a message mentioning all of them. Discord may reject or silently truncate. Batch mentions across messages if >15.
4. **RSVP button persistence** — Discord button interactions expire after 15 minutes if using ephemeral interaction responses. Game embeds with RSVP buttons must use persistent views that survive bot restarts.
5. **Concurrent availability updates** — two users run `/available` simultaneously in the same guild. SQLite WAL mode handles concurrent reads but writes serialize. Ensure upsert-or-delete pattern, not read-modify-write.

## File Structure

```
gamefinder/                        # repo root (from claude_template_repo)
│
│ ── FROM TEMPLATE (pre-existing) ──
├── .github/workflows/             # ci.yml, semgrep.yml, secret-scan.yml,
│   │                              # container-scan.yml, pages.yml, etc.
│   └── deploy.yml                 # NEW — SSH deploy to Oracle
├── .devcontainer/                 # devcontainer + firewall
├── scripts/                       # board.sh, setup-day0.sh, check-day0.sh,
│   │                              # validate-template.sh, bootstrap-*.sh
│   └── ci/
│       ├── lint-project.sh        # MODIFY — add ruff
│       └── test-project.sh        # MODIFY — add pytest
├── CLAUDE.md                      # MODIFY — project-specific
├── SECURITY.md                    # MODIFY — extend with data model
├── .gitleaks.toml                 # secret scanning config
├── .semgrep.yml                   # SAST rules
├── .pre-commit-config.yaml        # pre-commit hooks
├── .editorconfig
├── .env.example                   # MODIFY — add DISCORD_TOKEN
├── .gitignore
├── template.conf                  # MODIFY — configure subsystems
├── LICENSE                        # MODIFY — MIT (template ships Apache-2.0)
│
│ ── NEW (this project) ──
├── bot/
│   ├── __init__.py                # version string
│   ├── __main__.py                # entry: load config, start bot
│   ├── bot.py                     # GameFinder(commands.Bot) subclass
│   ├── config.py                  # env-based settings
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py            # connect, migrate, close
│   │   └── queries.py             # all SQL — availability, games, guilds, users
│   ├── cogs/
│   │   ├── __init__.py
│   │   ├── availability.py        # /available, /timezone, /available clear|import
│   │   ├── windows.py             # /windows, /whofree
│   │   ├── games.py               # /game create|cancel|edit, /games, RSVP views
│   │   └── admin.py               # /setup, /nudge, /stats, /data delete
│   └── utils/
│       ├── __init__.py
│       ├── time_blocks.py         # block boundary math, UTC conversion
│       └── formatting.py          # embed builders, heatmap, bar chart
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # fixtures: in-memory DB, mock bot
│   ├── test_database.py
│   ├── test_time_blocks.py
│   ├── test_availability.py
│   ├── test_windows.py
│   ├── test_games.py
│   └── test_admin.py
├── docs/
│   ├── PROJECT.md                 # project-specific instructions
│   ├── PRIVACY_POLICY.md
│   ├── explainer/index.html       # MODIFY — visual briefing (GitHub Pages)
│   └── superpowers/
│       ├── specs/
│       │   └── 2026-11-26-gamefinder-design.md
│       └── plans/
│           └── 2026-11-26-gamefinder-core.md
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

---

### Task 1: Project scaffolding + database layer

**Files:**
- From template: `.github/workflows/`, `.devcontainer/`, `scripts/`, `CLAUDE.md`, `SECURITY.md`, `.gitleaks.toml`, `.semgrep.yml`, `.pre-commit-config.yaml`, `.editorconfig`, `template.conf`
- Create: `pyproject.toml`, `bot/__init__.py`, `bot/__main__.py`, `bot/config.py`, `bot/bot.py`, `bot/db/__init__.py`, `bot/db/database.py`, `bot/db/queries.py`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_database.py`
- Modify: `template.conf` (configure subsystems), `CLAUDE.md` (project-specific instructions), `LICENSE` (MIT), `scripts/ci/lint-project.sh`, `scripts/ci/test-project.sh`

**Interfaces:**
- Consumes: nothing (first task)
- Produces:
  - `bot.db.database.Database` — `async connect(path: str) -> Database`, `async close()`, `async execute(sql: str, params: tuple) -> aiosqlite.Cursor`, `async fetch_one(sql: str, params: tuple) -> Row | None`, `async fetch_all(sql: str, params: tuple) -> list[Row]`
  - `bot.db.queries` — `async ensure_guild(db: Database, guild_id: int) -> None`, `async get_guild_config(db: Database, guild_id: int) -> GuildConfig | None`, `async ensure_user(db: Database, user_id: int) -> None`
  - `bot.config.Config` — `token: str`, `db_path: str`, `log_level: str`
  - `bot.bot.GameFinder(commands.Bot)` — cog loading, `db` attribute

- [ ] **Step 1: Create repo from template**

```bash
gh repo create Moon-Knight13/gamefinder --public --template Moon-Knight13/claude_template_repo --clone
cd gamefinder
```

- [ ] **Step 2: Run day-0 bootstrap**

```bash
bash scripts/setup-day0.sh
```

Sets up: GitHub Project board, branch protection, CODEOWNERS. Verify with `bash scripts/check-day0.sh`.

- [ ] **Step 3: Configure `template.conf`**

Enable: `SUBSYSTEM_BOARD=true`, `SUBSYSTEM_DAY0=true`. Disable any subsystems not needed (BMAD, local routing if present). Validate: `bash scripts/validate-template.sh`.

- [ ] **Step 4: Replace LICENSE with MIT**

Template ships Apache-2.0. Replace with MIT per spec.

- [ ] **Step 5: Update `CLAUDE.md` for GameFinder**

Replace template content with project-specific instructions: what this repo is (Discord bot for TTRPG scheduling), security rules (bot token in `.env` only, guild isolation), tech stack, link to `docs/PROJECT.md`.

- [ ] **Step 6: Add Python CI stubs to template's scripts**

`scripts/ci/lint-project.sh` — runs `ruff check .`. `scripts/ci/test-project.sh` — runs `pytest -v`. Template's `ci.yml` calls these stubs automatically.

- [ ] **Step 7: Write the failing test for database schema creation**

`tests/test_database.py`:
```python
async def test_tables_created(db):
    """All 8 tables exist after migration."""
    rows = await db.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", ()
    )
    names = [r["name"] for r in rows]
    assert "guilds" in names
    assert "users" in names
    assert "availability" in names
    assert "games" in names
    assert "rsvps" in names
    assert "campaigns" in names
    assert "campaign_roster" in names
    assert "sessions" in names

async def test_guild_isolation(db):
    """Queries for guild 1 never return guild 2 data."""
    await queries.upsert_availability(db, guild_id=1, user_id=100, date="2026-12-01", block="evening")
    await queries.upsert_availability(db, guild_id=2, user_id=200, date="2026-12-01", block="evening")
    rows = await queries.get_user_availability(db, guild_id=1, user_id=100, date_from="2026-12-01", date_to="2026-12-01")
    assert len(rows) == 1
    assert rows[0]["user_id"] == 100
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_database.py -v`
Expected: FAIL — imports not found

- [ ] **Step 4: Implement `pyproject.toml` with all dependencies**

Dependencies: discord.py>=2.4.0, aiosqlite>=0.20.0, apscheduler>=3.10.0, icalendar>=6.0.0, python-dotenv>=1.0.0. Dev: pytest>=8.0.0, pytest-asyncio>=0.24.0, ruff>=0.8.0.

- [ ] **Step 5: Implement `bot/config.py` — `Config` dataclass from env vars**

Reads `DISCORD_TOKEN`, `DB_PATH` (default `data/gamefinder.db`), `LOG_LEVEL` (default `INFO`).

- [ ] **Step 6: Implement `bot/db/database.py` — `Database` class**

Wraps aiosqlite connection. `connect()` enables WAL mode and foreign keys. `migrate()` creates all 8 tables with IF NOT EXISTS. Schema matches spec exactly: guilds, users, availability, games, rsvps, campaigns, campaign_roster, sessions.

- [ ] **Step 7: Implement `bot/db/queries.py` — guild and user helpers**

`ensure_guild`, `get_guild_config`, `ensure_user`, `upsert_availability`, `get_availability`. Every function takes `guild_id` parameter.

- [ ] **Step 8: Implement `tests/conftest.py` — in-memory DB fixture**

`db` fixture: creates `Database` with `:memory:`, runs `migrate()`, yields, closes.

- [ ] **Step 9: Implement `bot/bot.py` — `GameFinder` subclass**

Subclass `commands.Bot`. Accepts `Config` and `Database`. Loads cogs from `bot/cogs/`. Sets `intents = discord.Intents.default()` (no privileged intents).

- [ ] **Step 10: Implement `bot/__main__.py` — entry point**

Loads config from env, connects DB, runs bot. `python -m bot`.

- [ ] **Step 11: Create `Dockerfile`, `docker-compose.yml`, update `.env.example`**

Multi-stage Dockerfile: build deps, copy source, run `python -m bot`. Compose: single service, volume for `data/`, env_file `.env`. Add `DISCORD_TOKEN=` to template's existing `.env.example`.

- [ ] **Step 12: Run tests to verify they pass**

Run: `pytest tests/test_database.py -v`
Expected: PASS — both tests green

- [ ] **Step 13: Commit**

```bash
git add -A
git commit -m "feat: project scaffolding with database layer and Docker setup"
```

---

### Task 2: Time block utilities

**Files:**
- Create: `bot/utils/time_blocks.py`, `tests/test_time_blocks.py`

**Interfaces:**
- Consumes: nothing (pure functions)
- Produces:
  - `block_to_utc_range(date: datetime.date, block: str, server_tz: str, block_config: BlockConfig) -> tuple[datetime, datetime]` — returns UTC start/end for a block on a date
  - `utc_to_discord_timestamp(dt: datetime, style: str = "F") -> str` — returns `<t:unix:style>`
  - `date_range(start: datetime.date, weeks: int) -> list[datetime.date]` — list of dates in forecast window
  - `BlockConfig` — dataclass with `morning_start`, `morning_end`, `afternoon_start`, `afternoon_end`, `evening_start`, `evening_end` (all `int` hours, defaults 9/12/12/17/17/22)

- [ ] **Step 1: Write failing tests**

`tests/test_time_blocks.py`:
```python
def test_block_to_utc_range_london():
    start, end = block_to_utc_range(date(2026, 12, 1), "evening", "Europe/London", BlockConfig())
    assert start == datetime(2026, 12, 1, 17, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 12, 1, 22, 0, tzinfo=timezone.utc)

def test_block_to_utc_range_new_york():
    start, end = block_to_utc_range(date(2026, 12, 1), "evening", "America/New_York", BlockConfig())
    assert start == datetime(2026, 12, 1, 22, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 12, 2, 3, 0, tzinfo=timezone.utc)

def test_utc_to_discord_timestamp():
    dt = datetime(2026, 12, 1, 17, 0, tzinfo=timezone.utc)
    assert utc_to_discord_timestamp(dt, "t") == "<t:1796148000:t>"

def test_date_range_3_weeks():
    dates = date_range(date(2026, 12, 1), weeks=3)
    assert len(dates) == 21
    assert dates[0] == date(2026, 12, 1)
    assert dates[-1] == date(2026, 12, 21)

def test_block_to_utc_range_dst_transition():
    """US clocks fall back Nov 1 2026. Evening block spans different UTC offsets before/after."""
    start_before, _ = block_to_utc_range(date(2026, 10, 31), "evening", "America/New_York", BlockConfig())
    start_after, _ = block_to_utc_range(date(2026, 11, 2), "evening", "America/New_York", BlockConfig())
    assert start_before != start_after  # UTC offset changed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_time_blocks.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `bot/utils/time_blocks.py`**

Use `zoneinfo.ZoneInfo` for timezone conversion. `block_to_utc_range` constructs a naive datetime in the server's timezone, then converts to UTC. Handles DST by converting through aware datetimes.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_time_blocks.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/utils/time_blocks.py tests/test_time_blocks.py
git commit -m "feat: time block utilities with timezone conversion"
```

---

### Task 3: Availability cog

**Files:**
- Create: `bot/cogs/availability.py`, `tests/test_availability.py`
- Modify: `bot/db/queries.py` (add availability queries)

**Interfaces:**
- Consumes: `Database` from Task 1, `block_to_utc_range` and `date_range` from Task 2
- Produces:
  - `bot/db/queries.py`: `async upsert_availability(db, guild_id, user_id, date, block) -> None`, `async delete_availability(db, guild_id, user_id, date, block) -> None`, `async get_user_availability(db, guild_id, user_id, date_from, date_to) -> list[Row]`, `async clear_user_availability(db, guild_id, user_id) -> None`, `async set_user_timezone(db, user_id, timezone: str) -> None`, `async get_user_timezone(db, user_id) -> str | None`
  - `AvailabilityCog` — slash commands `/available`, `/available clear`, `/available import`, `/timezone set`

- [ ] **Step 1: Write failing tests for availability queries**

`tests/test_availability.py`:
```python
async def test_upsert_availability(db):
    await queries.upsert_availability(db, guild_id=1, user_id=100, date="2026-12-01", block="evening")
    rows = await queries.get_user_availability(db, guild_id=1, user_id=100, date_from="2026-12-01", date_to="2026-12-01")
    assert len(rows) == 1
    assert rows[0]["block"] == "evening"

async def test_upsert_is_idempotent(db):
    await queries.upsert_availability(db, guild_id=1, user_id=100, date="2026-12-01", block="evening")
    await queries.upsert_availability(db, guild_id=1, user_id=100, date="2026-12-01", block="evening")
    rows = await queries.get_user_availability(db, guild_id=1, user_id=100, date_from="2026-12-01", date_to="2026-12-01")
    assert len(rows) == 1

async def test_delete_availability(db):
    await queries.upsert_availability(db, guild_id=1, user_id=100, date="2026-12-01", block="evening")
    await queries.delete_availability(db, guild_id=1, user_id=100, date="2026-12-01", block="evening")
    rows = await queries.get_user_availability(db, guild_id=1, user_id=100, date_from="2026-12-01", date_to="2026-12-01")
    assert len(rows) == 0

async def test_clear_user_availability(db):
    await queries.upsert_availability(db, guild_id=1, user_id=100, date="2026-12-01", block="evening")
    await queries.upsert_availability(db, guild_id=1, user_id=100, date="2026-12-02", block="morning")
    await queries.clear_user_availability(db, guild_id=1, user_id=100)
    rows = await queries.get_user_availability(db, guild_id=1, user_id=100, date_from="2026-12-01", date_to="2026-12-31")
    assert len(rows) == 0

async def test_set_and_get_timezone(db):
    await queries.ensure_user(db, user_id=100)
    await queries.set_user_timezone(db, user_id=100, timezone="Europe/London")
    tz = await queries.get_user_timezone(db, user_id=100)
    assert tz == "Europe/London"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_availability.py -v`
Expected: FAIL

- [ ] **Step 3: Implement availability queries in `bot/db/queries.py`**

`upsert_availability` uses INSERT OR IGNORE with unique constraint on (guild_id, user_id, date, block). `delete_availability` removes one row. `clear_user_availability` deletes all for user+guild. `set_user_timezone` updates `users` table.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_availability.py -v`
Expected: PASS

- [ ] **Step 5: Implement `bot/cogs/availability.py` — slash commands**

`/available` — creates ephemeral view with button grid: 7 days x 3 blocks. Buttons toggle availability in DB. Prev/Next buttons navigate weeks. `/available clear` — calls `clear_user_availability`. `/timezone set timezone:str` — validates against `zoneinfo.available_timezones()`, calls `set_user_timezone`. `/available import` — accepts attachment, parses .ics with icalendar library, maps free periods to blocks.

- [ ] **Step 6: Commit**

```bash
git add bot/cogs/availability.py bot/db/queries.py tests/test_availability.py
git commit -m "feat: availability collection with button grid and timezone support"
```

---

### Task 4: Windows and insights cog

**Files:**
- Create: `bot/cogs/windows.py`, `bot/utils/formatting.py`, `tests/test_windows.py`
- Modify: `bot/db/queries.py` (add aggregation queries)

**Interfaces:**
- Consumes: `Database` from Task 1, `BlockConfig` and `utc_to_discord_timestamp` from Task 2, availability data from Task 3
- Produces:
  - `bot/db/queries.py`: `async get_availability_counts(db, guild_id, date_from, date_to) -> list[Row]` (returns date, block, count), `async get_available_users(db, guild_id, date, block) -> list[Row]` (returns user_ids for a slot), `async count_respondents(db, guild_id, date_from, date_to) -> int`
  - `bot/utils/formatting.py`: `format_bar(count: int, max_count: int) -> str` (green square bar), `format_heatmap(week_data: list[Row], threshold: int) -> str` (grid string), `format_ranked_windows(windows: list[Window], threshold: int) -> str`
  - `WindowsCog` — `/windows`, `/whofree`

- [ ] **Step 1: Write failing tests for aggregation queries**

`tests/test_windows.py`:
```python
async def test_availability_counts(db):
    for uid in [100, 101, 102]:
        await queries.upsert_availability(db, guild_id=1, user_id=uid, date="2026-12-01", block="evening")
    await queries.upsert_availability(db, guild_id=1, user_id=100, date="2026-12-01", block="morning")
    counts = await queries.get_availability_counts(db, guild_id=1, date_from="2026-12-01", date_to="2026-12-01")
    evening = next(r for r in counts if r["block"] == "evening")
    morning = next(r for r in counts if r["block"] == "morning")
    assert evening["count"] == 3
    assert morning["count"] == 1

async def test_available_users(db):
    for uid in [100, 101, 102]:
        await queries.upsert_availability(db, guild_id=1, user_id=uid, date="2026-12-01", block="evening")
    users = await queries.get_available_users(db, guild_id=1, date="2026-12-01", block="evening")
    assert {r["user_id"] for r in users} == {100, 101, 102}

async def test_counts_respect_threshold(db):
    for uid in [100, 101]:
        await queries.upsert_availability(db, guild_id=1, user_id=uid, date="2026-12-01", block="evening")
    counts = await queries.get_availability_counts(db, guild_id=1, date_from="2026-12-01", date_to="2026-12-01")
    evening = next(r for r in counts if r["block"] == "evening")
    assert evening["count"] == 2  # filtering by threshold is display-side, not query-side

async def test_respondent_count(db):
    await queries.upsert_availability(db, guild_id=1, user_id=100, date="2026-12-01", block="evening")
    await queries.upsert_availability(db, guild_id=1, user_id=100, date="2026-12-02", block="morning")
    await queries.upsert_availability(db, guild_id=1, user_id=101, date="2026-12-01", block="evening")
    count = await queries.count_respondents(db, guild_id=1, date_from="2026-12-01", date_to="2026-12-31")
    assert count == 2  # 2 unique users, not 3 rows
```

- [ ] **Step 2: Write failing tests for formatting**

```python
def test_format_bar():
    assert format_bar(5, 10) == "🟩🟩🟩🟩🟩"
    assert format_bar(0, 10) == ""

def test_format_bar_max():
    result = format_bar(15, 15)
    assert len(result) == 15  # one emoji per player, capped at count
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_windows.py -v`
Expected: FAIL

- [ ] **Step 4: Implement aggregation queries in `bot/db/queries.py`**

`get_availability_counts` — GROUP BY date, block with COUNT(DISTINCT user_id). `get_available_users` — SELECT DISTINCT user_id WHERE date and block match. `count_respondents` — COUNT(DISTINCT user_id) in date range.

- [ ] **Step 5: Implement `bot/utils/formatting.py`**

`format_bar` — repeat `🟩` count times. `format_heatmap` — 7x3 grid with counts, green intensity via different thresholds. `format_ranked_windows` — sorted by count descending, each line: bar + count + day + block + time range.

- [ ] **Step 6: Implement `bot/cogs/windows.py` — `/windows` and `/whofree`**

`/windows` — optional `min` parameter (default from guild config). Fetches counts for forecast window, formats as ranked list + heatmap embed. `/whofree day:str block:str` — ephemeral response listing usernames for that slot.

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_windows.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add bot/cogs/windows.py bot/utils/formatting.py bot/db/queries.py tests/test_windows.py
git commit -m "feat: windows insights with ranked list and heatmap display"
```

---

### Task 5: Game posting and RSVP

**Files:**
- Create: `bot/cogs/games.py`, `tests/test_games.py`
- Modify: `bot/db/queries.py` (add game + RSVP queries)

**Interfaces:**
- Consumes: `Database` from Task 1, `formatting` from Task 4, `get_available_users` from Task 4, `utc_to_discord_timestamp` from Task 2
- Produces:
  - `bot/db/queries.py`: `async create_game(db, guild_id, creator_id, title, description, slot_date, slot_block, player_cap) -> int` (returns game ID), `async get_game(db, game_id, guild_id) -> Row | None`, `async upsert_rsvp(db, game_id, user_id, status: str) -> None`, `async get_rsvps(db, game_id) -> list[Row]`, `async get_rsvp_counts(db, game_id) -> dict[str, int]`, `async list_games(db, guild_id, status="open") -> list[Row]`, `async update_game_status(db, game_id, guild_id, status: str) -> None`, `async set_game_event_id(db, game_id, guild_id, event_id: int) -> None`
  - `GamesCog` — `/game create`, `/games`, `/game cancel`, `/game edit`
  - `RSVPView(discord.ui.View)` — persistent view with Going/Maybe/Can't buttons

- [ ] **Step 1: Write failing tests for game queries**

`tests/test_games.py`:
```python
async def test_create_and_get_game(db):
    game_id = await queries.create_game(db, guild_id=1, creator_id=100, title="Test Game",
        description="A test", slot_date="2026-12-01", slot_block="evening", player_cap=5)
    game = await queries.get_game(db, game_id=game_id, guild_id=1)
    assert game["title"] == "Test Game"
    assert game["player_cap"] == 5
    assert game["status"] == "open"

async def test_rsvp_counts(db):
    game_id = await queries.create_game(db, guild_id=1, creator_id=100, title="Test",
        description="", slot_date="2026-12-01", slot_block="evening", player_cap=5)
    await queries.upsert_rsvp(db, game_id=game_id, user_id=200, status="going")
    await queries.upsert_rsvp(db, game_id=game_id, user_id=201, status="going")
    await queries.upsert_rsvp(db, game_id=game_id, user_id=202, status="maybe")
    counts = await queries.get_rsvp_counts(db, game_id=game_id)
    assert counts["going"] == 2
    assert counts["maybe"] == 1
    assert counts.get("not_going", 0) == 0

async def test_rsvp_upsert_changes_status(db):
    game_id = await queries.create_game(db, guild_id=1, creator_id=100, title="Test",
        description="", slot_date="2026-12-01", slot_block="evening", player_cap=5)
    await queries.upsert_rsvp(db, game_id=game_id, user_id=200, status="going")
    await queries.upsert_rsvp(db, game_id=game_id, user_id=200, status="not_going")
    counts = await queries.get_rsvp_counts(db, game_id=game_id)
    assert counts.get("going", 0) == 0
    assert counts["not_going"] == 1

async def test_list_games_filters_by_guild(db):
    await queries.create_game(db, guild_id=1, creator_id=100, title="Guild 1 Game",
        description="", slot_date="2026-12-01", slot_block="evening", player_cap=5)
    await queries.create_game(db, guild_id=2, creator_id=200, title="Guild 2 Game",
        description="", slot_date="2026-12-01", slot_block="evening", player_cap=5)
    games = await queries.list_games(db, guild_id=1)
    assert len(games) == 1
    assert games[0]["title"] == "Guild 1 Game"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_games.py -v`
Expected: FAIL

- [ ] **Step 3: Implement game + RSVP queries in `bot/db/queries.py`**

`create_game` — INSERT returning lastrowid. `upsert_rsvp` — INSERT OR REPLACE on (game_id, user_id). `get_rsvp_counts` — GROUP BY status with COUNT. All queries include guild_id where the table has it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_games.py -v`
Expected: PASS

- [ ] **Step 5: Implement `RSVPView` — persistent button view in `bot/cogs/games.py`**

Subclass `discord.ui.View` with `timeout=None`. Three buttons: Going (green), Maybe (grey), Can't Make It (red). Each button callback calls `upsert_rsvp` and updates the embed with new counts. Register as persistent view in `bot.py` on startup so buttons survive restarts. Custom ID format: `rsvp:{game_id}:{status}`.

- [ ] **Step 6: Implement `/game create` command**

Modal or slash options for title, description, player_cap. Slot selection: autocomplete from `/windows` data + freeform date/block option. Creates DB game, posts forum thread (tagged Oneshot, Open), embeds game details + RSVPView. @-mentions users from `get_available_users` for the slot. When Going >= player_cap: auto-create Discord Scheduled Event via `guild.create_scheduled_event()`, store event ID.

- [ ] **Step 7: Implement `/games`, `/game cancel`, `/game edit`**

`/games` — list open games with RSVP counts, ephemeral. `/game cancel game_id:int` — creator only, sets status=cancelled, notifies Going+Maybe users in thread, removes Discord event if exists. `/game edit game_id:int` — creator only, modal for editable fields, updates embed.

- [ ] **Step 8: Implement reminder jobs**

APScheduler job checks games 24h before slot. Sends creator a prep summary in game thread: "4 Going, 2 Maybe, 1 Can't — you're set." Posts session-day ping: "@Going — tonight! @Maybe — still in?" Registered in `bot.py` on startup alongside purge job.

- [ ] **Step 9: Commit**

```bash
git add bot/cogs/games.py bot/db/queries.py tests/test_games.py
git commit -m "feat: game posting with three-tier RSVP and auto Discord events"
```

---

### Task 6: Admin cog and data management

**Files:**
- Create: `bot/cogs/admin.py`, `tests/test_admin.py`
- Modify: `bot/db/queries.py` (add admin queries)

**Interfaces:**
- Consumes: `Database` from Task 1, `count_respondents` from Task 4
- Produces:
  - `bot/db/queries.py`: `async update_guild_config(db, guild_id, **kwargs) -> None`, `async delete_user_data(db, user_id) -> None`, `async delete_guild_data(db, guild_id) -> None`, `async purge_stale_availability(db, guild_id, before_date: str) -> int` (returns deleted count), `async get_guild_stats(db, guild_id, date_from, date_to) -> dict`
  - `AdminCog` — `/setup`, `/nudge`, `/stats`, `/data delete`

- [ ] **Step 1: Write failing tests**

`tests/test_admin.py`:
```python
async def test_update_guild_config(db):
    await queries.ensure_guild(db, guild_id=1)
    await queries.update_guild_config(db, guild_id=1, threshold=6, forecast_weeks=4)
    config = await queries.get_guild_config(db, guild_id=1)
    assert config["threshold"] == 6
    assert config["forecast_weeks"] == 4

async def test_delete_user_data(db):
    await queries.ensure_user(db, user_id=100)
    await queries.upsert_availability(db, guild_id=1, user_id=100, date="2026-12-01", block="evening")
    await queries.delete_user_data(db, user_id=100)
    rows = await queries.get_user_availability(db, guild_id=1, user_id=100, date_from="2026-12-01", date_to="2026-12-31")
    assert len(rows) == 0
    user_tz = await queries.get_user_timezone(db, user_id=100)
    assert user_tz is None

async def test_purge_stale_availability(db):
    await queries.upsert_availability(db, guild_id=1, user_id=100, date="2026-11-01", block="evening")
    await queries.upsert_availability(db, guild_id=1, user_id=100, date="2026-12-01", block="evening")
    deleted = await queries.purge_stale_availability(db, guild_id=1, before_date="2026-11-30")
    assert deleted == 1
    rows = await queries.get_user_availability(db, guild_id=1, user_id=100, date_from="2026-11-01", date_to="2026-12-31")
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-12-01"

async def test_delete_guild_data(db):
    await queries.ensure_guild(db, guild_id=1)
    await queries.upsert_availability(db, guild_id=1, user_id=100, date="2026-12-01", block="evening")
    await queries.create_game(db, guild_id=1, creator_id=100, title="Test",
        description="", slot_date="2026-12-01", slot_block="evening", player_cap=5)
    await queries.delete_guild_data(db, guild_id=1)
    config = await queries.get_guild_config(db, guild_id=1)
    assert config is None
    games = await queries.list_games(db, guild_id=1)
    assert len(games) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_admin.py -v`
Expected: FAIL

- [ ] **Step 3: Implement admin queries in `bot/db/queries.py`**

`update_guild_config` — UPDATE with kwargs. `delete_user_data` — DELETE from users, availability, rsvps for user_id. `delete_guild_data` — DELETE from all tables for guild_id (CASCADE or explicit). `purge_stale_availability` — DELETE WHERE date < before_date AND guild_id, return rowcount. `get_guild_stats` — response rate, top windows, game count.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_admin.py -v`
Expected: PASS

- [ ] **Step 5: Implement `bot/cogs/admin.py` — slash commands**

`/setup` — `manage_guild` permission required. Options for threshold, forecast_weeks, block hours, scheduling channel. `/nudge` — posts generic message prompting non-responders (no GUILD_MEMBERS intent — just "X of Y responded, run /available!"). `/stats` — ephemeral embed with response rate, top 3 windows, games posted this month. `/data delete` — confirmation button, then `delete_user_data`. Register `on_guild_remove` event — schedule guild data deletion after 30 days via APScheduler.

- [ ] **Step 6: Implement auto-purge scheduled job**

APScheduler job runs daily. For each guild, calls `purge_stale_availability` for dates before forecast window start. Registered in `bot.py` on startup.

- [ ] **Step 7: Run full test suite**

Run: `pytest -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add bot/cogs/admin.py bot/db/queries.py tests/test_admin.py
git commit -m "feat: admin setup, stats, data deletion, and auto-purge"
```

---

### Task 7: Deploy workflow, docs, and explainer

**Files:**
- Create: `.github/workflows/deploy.yml`, `docs/PRIVACY_POLICY.md`, `docs/PROJECT.md`
- Modify: `README.md` (replace template README), `SECURITY.md` (extend template's with bot-specific data model), `docs/explainer/index.html` (project explainer page)
- Move: spec and plan files into `docs/superpowers/`

**Interfaces:**
- Consumes: all prior tasks (this tests and ships them)
- Produces: deployment workflow, public-facing docs, portfolio-quality README and explainer

**Note:** Template provides CI workflows (ci.yml, semgrep.yml, secret-scan.yml, container-scan.yml), pre-commit hooks, and SECURITY.md. This task adds only what's new: deploy workflow and project docs.

- [ ] **Step 1: Create `.github/workflows/deploy.yml`**

Triggers on push to main (after template CI passes via `needs: [ci]` or `workflow_run`). Steps: SSH into Oracle VM via secrets (`ORACLE_HOST`, `ORACLE_SSH_KEY`, `ORACLE_USER`), runs `cd gamefinder && git pull && docker compose up -d --build`.

- [ ] **Step 2: Write `README.md`**

Replace template README. Sections: problem statement (from spec), how it works (availability → insights → game → RSVP), features list with command reference, quick setup (invite link + `/setup`), self-hosting (Docker), screenshots/mockups of Discord output, contributing, license (MIT). Portfolio quality — clear value proposition at the top, clean formatting, badges (CI status, license, Python version).

- [ ] **Step 3: Write `docs/PRIVACY_POLICY.md`**

What data is collected (Discord user IDs, timezone, availability blocks, RSVP status). Why (scheduling functionality). Retention (auto-purge, delete on request, delete on server removal after 30 days). No third-party sharing. Contact for requests. GDPR rights.

- [ ] **Step 4: Update `SECURITY.md`**

Extend template's security doc with bot-specific details: data model (what's in SQLite), guild isolation guarantee, bot token handling, vulnerability reporting process.

- [ ] **Step 5: Write `docs/PROJECT.md`**

Project-specific instructions per CLAUDE.md convention. What this repo is, how to run it locally, testing, architecture overview, link to spec.

- [ ] **Step 6: Update `docs/explainer/index.html`**

Replace template explainer with GameFinder visual briefing. Self-contained HTML page (works offline, served via GitHub Pages). Shows: problem statement, architecture diagram, feature overview, command examples. Synced with README per CLAUDE.md contract.

- [ ] **Step 7: Move spec and plan into repo docs**

```bash
mkdir -p docs/superpowers/specs docs/superpowers/plans
cp <spec> docs/superpowers/specs/2026-11-26-gamefinder-design.md
cp <plan> docs/superpowers/plans/2026-11-26-gamefinder-core.md
```

- [ ] **Step 8: Run full CI locally**

Run: `ruff check . && pytest -v`
Expected: PASS with zero warnings. Also verify template gates: `bash scripts/validate-template.sh`.

- [ ] **Step 9: Commit and push**

```bash
git add -A
git commit -m "feat: deploy workflow, README, privacy policy, and explainer page"
git push origin main
```

- [ ] **Step 10: Verify all CI passes on GitHub**

Check: GitHub Actions shows green — template CI (semgrep, gitleaks, secret scan, container scan) + Python CI (ruff, pytest) + pages deploy.
