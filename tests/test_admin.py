from bot.db import queries


async def test_update_guild_config(db):
    await queries.ensure_guild(db, guild_id=1)
    await queries.update_guild_config(db, guild_id=1, threshold=6, forecast_weeks=4)
    config = await queries.get_guild_config(db, guild_id=1)
    assert config["threshold"] == 6
    assert config["forecast_weeks"] == 4


async def test_delete_user_data(db):
    await queries.ensure_user(db, user_id=100)
    await queries.upsert_availability(
        db, guild_id=1, user_id=100, date="2026-12-01", block="evening"
    )
    await queries.delete_user_data(db, user_id=100)
    rows = await queries.get_user_availability(
        db, guild_id=1, user_id=100, date_from="2026-12-01", date_to="2026-12-31"
    )
    assert len(rows) == 0
    user_tz = await queries.get_user_timezone(db, user_id=100)
    assert user_tz is None


async def test_purge_stale_availability(db):
    await queries.upsert_availability(
        db, guild_id=1, user_id=100, date="2026-11-01", block="evening"
    )
    await queries.upsert_availability(
        db, guild_id=1, user_id=100, date="2026-12-01", block="evening"
    )
    deleted = await queries.purge_stale_availability(db, guild_id=1, before_date="2026-11-30")
    assert deleted == 1
    rows = await queries.get_user_availability(
        db, guild_id=1, user_id=100, date_from="2026-11-01", date_to="2026-12-31"
    )
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-12-01"


async def test_delete_guild_data(db):
    await queries.ensure_guild(db, guild_id=1)
    await queries.upsert_availability(
        db, guild_id=1, user_id=100, date="2026-12-01", block="evening"
    )
    await queries.create_game(
        db,
        guild_id=1,
        creator_id=100,
        title="Test",
        description="",
        slot_date="2026-12-01",
        slot_block="evening",
        player_cap=5,
    )
    await queries.delete_guild_data(db, guild_id=1)
    config = await queries.get_guild_config(db, guild_id=1)
    assert config is None
    games = await queries.list_games(db, guild_id=1)
    assert len(games) == 0


async def test_guild_stats(db):
    await queries.ensure_guild(db, guild_id=1)
    await queries.upsert_availability(
        db, guild_id=1, user_id=100, date="2026-12-01", block="evening"
    )
    await queries.upsert_availability(
        db, guild_id=1, user_id=101, date="2026-12-01", block="evening"
    )
    stats = await queries.get_guild_stats(
        db, guild_id=1, date_from="2026-12-01", date_to="2026-12-31"
    )
    assert stats["respondents"] == 2
    assert len(stats["top_windows"]) == 1
