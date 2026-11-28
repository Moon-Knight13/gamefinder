from bot.db import queries


async def test_tables_created(db):
    rows = await db.fetch_all("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", ())
    names = [r["name"] for r in rows]
    assert "guilds" in names
    assert "users" in names
    assert "availability" in names
    assert "games" in names
    assert "rsvps" in names
    assert "campaigns" in names
    assert "campaign_roster" in names
    assert "sessions" in names
    assert "guild_features" in names
    assert "dm_preferences" in names


async def test_guild_isolation(db):
    await queries.upsert_availability(
        db, guild_id=1, user_id=100, date="2026-12-01", block="evening"
    )
    await queries.upsert_availability(
        db, guild_id=2, user_id=200, date="2026-12-01", block="evening"
    )
    rows = await queries.get_user_availability(
        db, guild_id=1, user_id=100, date_from="2026-12-01", date_to="2026-12-01"
    )
    assert len(rows) == 1
    assert rows[0]["user_id"] == 100


async def test_ensure_guild_idempotent(db):
    await queries.ensure_guild(db, guild_id=1)
    await queries.ensure_guild(db, guild_id=1)
    config = await queries.get_guild_config(db, guild_id=1)
    assert config is not None
    assert config["threshold"] == 4


async def test_ensure_user_idempotent(db):
    await queries.ensure_user(db, user_id=100)
    await queries.ensure_user(db, user_id=100)
    tz = await queries.get_user_timezone(db, user_id=100)
    assert tz is None
