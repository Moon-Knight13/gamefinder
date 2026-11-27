import aiosqlite


class Database:
    def __init__(self) -> None:
        self._conn: aiosqlite.Connection | None = None

    @classmethod
    async def connect(cls, path: str) -> "Database":
        db = cls()
        db._conn = await aiosqlite.connect(path)
        db._conn.row_factory = aiosqlite.Row
        await db._conn.execute("PRAGMA journal_mode=WAL")
        await db._conn.execute("PRAGMA foreign_keys=ON")
        return db

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        assert self._conn is not None
        cursor = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cursor

    async def execute_many(self, sql: str, params_seq: list[tuple]) -> None:
        assert self._conn is not None
        await self._conn.executemany(sql, params_seq)
        await self._conn.commit()

    async def fetch_one(self, sql: str, params: tuple = ()) -> aiosqlite.Row | None:
        assert self._conn is not None
        cursor = await self._conn.execute(sql, params)
        return await cursor.fetchone()

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[aiosqlite.Row]:
        assert self._conn is not None
        cursor = await self._conn.execute(sql, params)
        return await cursor.fetchall()

    async def migrate(self) -> None:
        assert self._conn is not None
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS guilds (
    guild_id INTEGER PRIMARY KEY,
    threshold INTEGER NOT NULL DEFAULT 4,
    forecast_weeks INTEGER NOT NULL DEFAULT 3,
    morning_start INTEGER NOT NULL DEFAULT 9,
    morning_end INTEGER NOT NULL DEFAULT 12,
    afternoon_start INTEGER NOT NULL DEFAULT 12,
    afternoon_end INTEGER NOT NULL DEFAULT 17,
    evening_start INTEGER NOT NULL DEFAULT 17,
    evening_end INTEGER NOT NULL DEFAULT 22,
    scheduling_channel_id INTEGER,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    timezone TEXT,
    notify_pref TEXT NOT NULL DEFAULT 'all',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS availability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    block TEXT NOT NULL CHECK (block IN ('morning', 'afternoon', 'evening')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (guild_id, user_id, date, block),
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    creator_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    day_of_week INTEGER NOT NULL,
    block TEXT NOT NULL CHECK (block IN ('morning', 'afternoon', 'evening')),
    cadence TEXT NOT NULL DEFAULT 'weekly' CHECK (cadence IN ('weekly', 'biweekly', 'every_n')),
    cadence_interval INTEGER NOT NULL DEFAULT 1,
    player_min INTEGER NOT NULL DEFAULT 3,
    player_max INTEGER NOT NULL DEFAULT 6,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed')),
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id),
    FOREIGN KEY (creator_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    creator_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    slot_date TEXT NOT NULL,
    slot_block TEXT NOT NULL CHECK (slot_block IN ('morning', 'afternoon', 'evening')),
    player_cap INTEGER NOT NULL DEFAULT 5,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'full', 'cancelled', 'completed')),
    campaign_id INTEGER,
    discord_event_id INTEGER,
    message_id INTEGER,
    channel_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id),
    FOREIGN KEY (creator_id) REFERENCES users(user_id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);

CREATE TABLE IF NOT EXISTS rsvps (
    game_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('going', 'maybe', 'not_going')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (game_id, user_id),
    FOREIGN KEY (game_id) REFERENCES games(id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS campaign_roster (
    campaign_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    joined_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'left')),
    PRIMARY KEY (campaign_id, user_id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    session_number INTEGER NOT NULL,
    date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'cancelled', 'completed')),
    discord_event_id INTEGER,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);
"""
