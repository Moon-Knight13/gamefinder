from bot.db import queries


async def test_upsert_availability(db):
    await queries.upsert_availability(
        db, guild_id=1, user_id=100, date="2026-12-01", block="evening"
    )
    rows = await queries.get_user_availability(
        db, guild_id=1, user_id=100, date_from="2026-12-01", date_to="2026-12-01"
    )
    assert len(rows) == 1
    assert rows[0]["block"] == "evening"


async def test_upsert_is_idempotent(db):
    await queries.upsert_availability(
        db, guild_id=1, user_id=100, date="2026-12-01", block="evening"
    )
    await queries.upsert_availability(
        db, guild_id=1, user_id=100, date="2026-12-01", block="evening"
    )
    rows = await queries.get_user_availability(
        db, guild_id=1, user_id=100, date_from="2026-12-01", date_to="2026-12-01"
    )
    assert len(rows) == 1


async def test_delete_availability(db):
    await queries.upsert_availability(
        db, guild_id=1, user_id=100, date="2026-12-01", block="evening"
    )
    await queries.delete_availability(
        db, guild_id=1, user_id=100, date="2026-12-01", block="evening"
    )
    rows = await queries.get_user_availability(
        db, guild_id=1, user_id=100, date_from="2026-12-01", date_to="2026-12-01"
    )
    assert len(rows) == 0


async def test_clear_user_availability(db):
    await queries.upsert_availability(
        db, guild_id=1, user_id=100, date="2026-12-01", block="evening"
    )
    await queries.upsert_availability(
        db, guild_id=1, user_id=100, date="2026-12-02", block="morning"
    )
    await queries.clear_user_availability(db, guild_id=1, user_id=100)
    rows = await queries.get_user_availability(
        db, guild_id=1, user_id=100, date_from="2026-12-01", date_to="2026-12-31"
    )
    assert len(rows) == 0


async def test_set_and_get_timezone(db):
    await queries.ensure_user(db, user_id=100)
    await queries.set_user_timezone(db, user_id=100, timezone="Europe/London")
    tz = await queries.get_user_timezone(db, user_id=100)
    assert tz == "Europe/London"


async def test_availability_across_multiple_blocks(db):
    await queries.upsert_availability(
        db, guild_id=1, user_id=100, date="2026-12-01", block="morning"
    )
    await queries.upsert_availability(
        db, guild_id=1, user_id=100, date="2026-12-01", block="evening"
    )
    rows = await queries.get_user_availability(
        db, guild_id=1, user_id=100, date_from="2026-12-01", date_to="2026-12-01"
    )
    assert len(rows) == 2
