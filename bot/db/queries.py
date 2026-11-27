"""All SQL queries. Every function takes guild_id where applicable — no cross-guild leakage."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.db.database import Database


# --- Guild helpers ---


async def ensure_guild(db: Database, guild_id: int) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO guilds (guild_id) VALUES (?)",
        (guild_id,),
    )


async def get_guild_config(db: Database, guild_id: int) -> dict | None:
    row = await db.fetch_one("SELECT * FROM guilds WHERE guild_id = ?", (guild_id,))
    if row is None:
        return None
    return dict(row)


async def update_guild_config(db: Database, guild_id: int, **kwargs: object) -> None:
    if not kwargs:
        return
    allowed = {
        "threshold",
        "forecast_weeks",
        "morning_start",
        "morning_end",
        "afternoon_start",
        "afternoon_end",
        "evening_start",
        "evening_end",
        "scheduling_channel_id",
        "timezone",
    }
    filtered = {k: v for k, v in kwargs.items() if k in allowed}
    if not filtered:
        return
    sets = ", ".join(f"{k} = ?" for k in filtered)
    vals = tuple(filtered.values()) + (guild_id,)
    await db.execute(f"UPDATE guilds SET {sets} WHERE guild_id = ?", vals)


# --- User helpers ---


async def ensure_user(db: Database, user_id: int) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
        (user_id,),
    )


async def set_user_timezone(db: Database, user_id: int, timezone: str) -> None:
    await ensure_user(db, user_id)
    await db.execute(
        "UPDATE users SET timezone = ? WHERE user_id = ?",
        (timezone, user_id),
    )


async def get_user_timezone(db: Database, user_id: int) -> str | None:
    row = await db.fetch_one("SELECT timezone FROM users WHERE user_id = ?", (user_id,))
    if row is None:
        return None
    return row["timezone"]


# --- Availability ---


async def upsert_availability(
    db: Database, guild_id: int, user_id: int, date: str, block: str
) -> None:
    await ensure_guild(db, guild_id)
    await ensure_user(db, user_id)
    await db.execute(
        "INSERT OR IGNORE INTO availability (guild_id, user_id, date, block) VALUES (?, ?, ?, ?)",
        (guild_id, user_id, date, block),
    )


async def delete_availability(
    db: Database, guild_id: int, user_id: int, date: str, block: str
) -> None:
    await db.execute(
        "DELETE FROM availability WHERE guild_id = ? AND user_id = ? AND date = ? AND block = ?",
        (guild_id, user_id, date, block),
    )


async def get_user_availability(
    db: Database, guild_id: int, user_id: int, date_from: str, date_to: str
) -> list[dict]:
    rows = await db.fetch_all(
        "SELECT * FROM availability WHERE guild_id = ? AND user_id = ?"
        " AND date >= ? AND date <= ? ORDER BY date, block",
        (guild_id, user_id, date_from, date_to),
    )
    return [dict(r) for r in rows]


async def clear_user_availability(db: Database, guild_id: int, user_id: int) -> None:
    await db.execute(
        "DELETE FROM availability WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )


# --- Aggregation (windows/insights) ---


async def get_availability_counts(
    db: Database, guild_id: int, date_from: str, date_to: str
) -> list[dict]:
    rows = await db.fetch_all(
        """
        SELECT date, block, COUNT(DISTINCT user_id) as count
        FROM availability
        WHERE guild_id = ? AND date >= ? AND date <= ?
        GROUP BY date, block
        ORDER BY count DESC, date, block
        """,
        (guild_id, date_from, date_to),
    )
    return [dict(r) for r in rows]


async def get_available_users(db: Database, guild_id: int, date: str, block: str) -> list[dict]:
    rows = await db.fetch_all(
        "SELECT DISTINCT user_id FROM availability WHERE guild_id = ? AND date = ? AND block = ?",
        (guild_id, date, block),
    )
    return [dict(r) for r in rows]


async def count_respondents(db: Database, guild_id: int, date_from: str, date_to: str) -> int:
    row = await db.fetch_one(
        "SELECT COUNT(DISTINCT user_id) as count FROM availability"
        " WHERE guild_id = ? AND date >= ? AND date <= ?",
        (guild_id, date_from, date_to),
    )
    return row["count"] if row else 0


# --- Games ---


async def create_game(
    db: Database,
    guild_id: int,
    creator_id: int,
    title: str,
    description: str,
    slot_date: str,
    slot_block: str,
    player_cap: int,
) -> int:
    await ensure_guild(db, guild_id)
    await ensure_user(db, creator_id)
    cursor = await db.execute(
        """
        INSERT INTO games (guild_id, creator_id, title, description,
            slot_date, slot_block, player_cap)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (guild_id, creator_id, title, description, slot_date, slot_block, player_cap),
    )
    return cursor.lastrowid


async def get_game(db: Database, game_id: int, guild_id: int) -> dict | None:
    row = await db.fetch_one(
        "SELECT * FROM games WHERE id = ? AND guild_id = ?",
        (game_id, guild_id),
    )
    return dict(row) if row else None


async def list_games(
    db: Database, guild_id: int, status: str | None = "open",
) -> list[dict]:
    if status:
        rows = await db.fetch_all(
            "SELECT * FROM games WHERE guild_id = ? AND status = ? ORDER BY slot_date, slot_block",
            (guild_id, status),
        )
    else:
        rows = await db.fetch_all(
            "SELECT * FROM games WHERE guild_id = ? ORDER BY slot_date, slot_block",
            (guild_id,),
        )
    return [dict(r) for r in rows]


async def update_game_status(db: Database, game_id: int, guild_id: int, status: str) -> None:
    await db.execute(
        "UPDATE games SET status = ? WHERE id = ? AND guild_id = ?",
        (status, game_id, guild_id),
    )


async def set_game_event_id(db: Database, game_id: int, guild_id: int, event_id: int) -> None:
    await db.execute(
        "UPDATE games SET discord_event_id = ? WHERE id = ? AND guild_id = ?",
        (event_id, game_id, guild_id),
    )


async def set_game_message(
    db: Database, game_id: int, guild_id: int, message_id: int, channel_id: int
) -> None:
    await db.execute(
        "UPDATE games SET message_id = ?, channel_id = ? WHERE id = ? AND guild_id = ?",
        (message_id, channel_id, game_id, guild_id),
    )


async def update_game(db: Database, game_id: int, guild_id: int, **kwargs: object) -> None:
    allowed = {"title", "description", "slot_date", "slot_block", "player_cap", "status"}
    filtered = {k: v for k, v in kwargs.items() if k in allowed}
    if not filtered:
        return
    sets = ", ".join(f"{k} = ?" for k in filtered)
    vals = tuple(filtered.values()) + (game_id, guild_id)
    await db.execute(f"UPDATE games SET {sets} WHERE id = ? AND guild_id = ?", vals)


# --- RSVPs ---


async def upsert_rsvp(db: Database, game_id: int, user_id: int, status: str) -> None:
    await ensure_user(db, user_id)
    await db.execute(
        """
        INSERT INTO rsvps (game_id, user_id, status)
        VALUES (?, ?, ?)
        ON CONFLICT (game_id, user_id) DO UPDATE SET status = excluded.status,
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        """,
        (game_id, user_id, status),
    )


async def get_rsvps(db: Database, game_id: int) -> list[dict]:
    rows = await db.fetch_all(
        "SELECT * FROM rsvps WHERE game_id = ? ORDER BY updated_at",
        (game_id,),
    )
    return [dict(r) for r in rows]


async def get_rsvp_counts(db: Database, game_id: int) -> dict[str, int]:
    rows = await db.fetch_all(
        "SELECT status, COUNT(*) as count FROM rsvps WHERE game_id = ? GROUP BY status",
        (game_id,),
    )
    return {row["status"]: row["count"] for row in rows}


# --- Consistency analysis (campaign viability) ---


async def get_consistent_players(
    db: Database, guild_id: int, date_from: str, date_to: str, min_weeks: int = 3,
) -> list[dict]:
    """Find slots where the same players appear across multiple weeks.

    Returns list of {weekday, block, consistent_count, total_weeks, players}
    sorted by consistent_count descending.
    """
    # Use (strftime('%w') + 6) % 7 to convert Sun=0 to Mon=0 convention
    rows = await db.fetch_all(
        """
        SELECT user_id, block,
               (CAST(strftime('%w', date) AS INTEGER) + 6) % 7 as weekday,
               COUNT(DISTINCT date) as week_count
        FROM availability
        WHERE guild_id = ? AND date >= ? AND date <= ?
        GROUP BY user_id, block, weekday
        HAVING week_count >= ?
        ORDER BY weekday, block
        """,
        (guild_id, date_from, date_to, min_weeks),
    )

    # Group by (weekday, block)
    slots: dict[tuple[int, str], list[int]] = {}
    for r in rows:
        key = (r["weekday"], r["block"])
        if key not in slots:
            slots[key] = []
        slots[key].append(r["user_id"])

    # Calculate total weeks in range
    from datetime import date as dt_date
    d_from = dt_date.fromisoformat(date_from)
    d_to = dt_date.fromisoformat(date_to)
    total_weeks = max(1, (d_to - d_from).days // 7)

    result = []
    for (weekday, block), player_ids in slots.items():
        result.append({
            "weekday": weekday,
            "block": block,
            "consistent_count": len(player_ids),
            "total_weeks": total_weeks,
            "players": player_ids,
        })

    result.sort(key=lambda x: x["consistent_count"], reverse=True)
    return result


# --- Recurring availability ---


async def set_recurring(
    db: Database, guild_id: int, user_id: int, weekday: int, block: str,
    custom_start: int | None = None, custom_end: int | None = None,
) -> None:
    await ensure_guild(db, guild_id)
    await ensure_user(db, user_id)
    await db.execute(
        """INSERT OR REPLACE INTO recurring_availability
           (guild_id, user_id, weekday, block, custom_start, custom_end)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (guild_id, user_id, weekday, block, custom_start, custom_end),
    )


async def delete_recurring(
    db: Database, guild_id: int, user_id: int, weekday: int, block: str,
) -> None:
    await db.execute(
        "DELETE FROM recurring_availability WHERE guild_id = ? AND user_id = ? AND weekday = ? AND block = ?",
        (guild_id, user_id, weekday, block),
    )


async def get_user_recurring(
    db: Database, guild_id: int, user_id: int,
) -> list[dict]:
    rows = await db.fetch_all(
        "SELECT * FROM recurring_availability WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    return [dict(r) for r in rows]


async def clear_user_recurring(db: Database, guild_id: int, user_id: int) -> None:
    await db.execute(
        "DELETE FROM recurring_availability WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )


# --- Campaigns ---


async def create_campaign(
    db: Database, guild_id: int, creator_id: int, title: str, description: str,
    day_of_week: int, block: str, session_count: int,
    cadence: str = "weekly", player_min: int = 3, player_max: int = 6,
) -> int:
    await ensure_guild(db, guild_id)
    await ensure_user(db, creator_id)
    cursor = await db.execute(
        """INSERT INTO campaigns (guild_id, creator_id, title, description,
            day_of_week, block, cadence, session_count, player_min, player_max)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (guild_id, creator_id, title, description, day_of_week, block,
         cadence, session_count, player_min, player_max),
    )
    return cursor.lastrowid


async def get_campaign(db: Database, campaign_id: int, guild_id: int) -> dict | None:
    row = await db.fetch_one(
        "SELECT * FROM campaigns WHERE id = ? AND guild_id = ?",
        (campaign_id, guild_id),
    )
    return dict(row) if row else None


async def list_campaigns(db: Database, guild_id: int, status: str = "active") -> list[dict]:
    rows = await db.fetch_all(
        "SELECT * FROM campaigns WHERE guild_id = ? AND status = ? ORDER BY started_at DESC",
        (guild_id, status),
    )
    return [dict(r) for r in rows]


async def update_campaign(db: Database, campaign_id: int, guild_id: int, **kwargs: object) -> None:
    allowed = {"title", "description", "status", "sessions_completed", "player_min",
               "player_max", "session_count", "message_id", "channel_id"}
    filtered = {k: v for k, v in kwargs.items() if k in allowed}
    if not filtered:
        return
    sets = ", ".join(f"{k} = ?" for k in filtered)
    vals = tuple(filtered.values()) + (campaign_id, guild_id)
    await db.execute(f"UPDATE campaigns SET {sets} WHERE id = ? AND guild_id = ?", vals)


async def add_to_roster(db: Database, campaign_id: int, user_id: int) -> bool:
    """Add user to roster. Returns False if roster full."""
    await ensure_user(db, user_id)
    # Check cap
    row = await db.fetch_one(
        "SELECT player_max FROM campaigns WHERE id = ?", (campaign_id,)
    )
    if row:
        roster = await db.fetch_one(
            "SELECT COUNT(*) as count FROM campaign_roster WHERE campaign_id = ? AND status = 'active'",
            (campaign_id,),
        )
        if roster and roster["count"] >= row["player_max"]:
            return False
    await db.execute(
        "INSERT OR IGNORE INTO campaign_roster (campaign_id, user_id) VALUES (?, ?)",
        (campaign_id, user_id),
    )
    return True


async def remove_from_roster(db: Database, campaign_id: int, user_id: int) -> None:
    await db.execute(
        "UPDATE campaign_roster SET status = 'left' WHERE campaign_id = ? AND user_id = ?",
        (campaign_id, user_id),
    )


async def get_roster(db: Database, campaign_id: int) -> list[dict]:
    rows = await db.fetch_all(
        "SELECT * FROM campaign_roster WHERE campaign_id = ? AND status = 'active' ORDER BY joined_at",
        (campaign_id,),
    )
    return [dict(r) for r in rows]


# --- Admin / data management ---


async def delete_user_data(db: Database, user_id: int) -> None:
    await db.execute("DELETE FROM rsvps WHERE user_id = ?", (user_id,))
    await db.execute("DELETE FROM availability WHERE user_id = ?", (user_id,))
    await db.execute("DELETE FROM recurring_availability WHERE user_id = ?", (user_id,))
    await db.execute("DELETE FROM campaign_roster WHERE user_id = ?", (user_id,))
    await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))


async def delete_guild_data(db: Database, guild_id: int) -> None:
    game_ids = await db.fetch_all("SELECT id FROM games WHERE guild_id = ?", (guild_id,))
    for row in game_ids:
        await db.execute("DELETE FROM rsvps WHERE game_id = ?", (row["id"],))

    campaign_ids = await db.fetch_all("SELECT id FROM campaigns WHERE guild_id = ?", (guild_id,))
    for row in campaign_ids:
        await db.execute("DELETE FROM sessions WHERE campaign_id = ?", (row["id"],))
        await db.execute("DELETE FROM campaign_roster WHERE campaign_id = ?", (row["id"],))

    await db.execute("DELETE FROM games WHERE guild_id = ?", (guild_id,))
    await db.execute("DELETE FROM campaigns WHERE guild_id = ?", (guild_id,))
    await db.execute("DELETE FROM availability WHERE guild_id = ?", (guild_id,))
    await db.execute("DELETE FROM guilds WHERE guild_id = ?", (guild_id,))


async def purge_stale_availability(db: Database, guild_id: int, before_date: str) -> int:
    cursor = await db.execute(
        "DELETE FROM availability WHERE guild_id = ? AND date < ?",
        (guild_id, before_date),
    )
    return cursor.rowcount


async def get_guild_stats(db: Database, guild_id: int, date_from: str, date_to: str) -> dict:
    respondents = await count_respondents(db, guild_id, date_from, date_to)
    top_windows = await get_availability_counts(db, guild_id, date_from, date_to)
    games = await db.fetch_one(
        "SELECT COUNT(*) as count FROM games WHERE guild_id = ? AND created_at >= ?",
        (guild_id, date_from),
    )
    return {
        "respondents": respondents,
        "top_windows": top_windows[:3],
        "games_count": games["count"] if games else 0,
    }
