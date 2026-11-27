from bot.db import queries
from bot.utils.formatting import format_bar


async def test_availability_counts(db):
    for uid in [100, 101, 102]:
        await queries.upsert_availability(
            db, guild_id=1, user_id=uid, date="2026-12-01", block="evening"
        )
    await queries.upsert_availability(
        db, guild_id=1, user_id=100, date="2026-12-01", block="morning"
    )
    counts = await queries.get_availability_counts(
        db, guild_id=1, date_from="2026-12-01", date_to="2026-12-01"
    )
    evening = next(r for r in counts if r["block"] == "evening")
    morning = next(r for r in counts if r["block"] == "morning")
    assert evening["count"] == 3
    assert morning["count"] == 1


async def test_available_users(db):
    for uid in [100, 101, 102]:
        await queries.upsert_availability(
            db, guild_id=1, user_id=uid, date="2026-12-01", block="evening"
        )
    users = await queries.get_available_users(db, guild_id=1, date="2026-12-01", block="evening")
    assert {r["user_id"] for r in users} == {100, 101, 102}


async def test_counts_respect_guild_isolation(db):
    await queries.upsert_availability(
        db, guild_id=1, user_id=100, date="2026-12-01", block="evening"
    )
    await queries.upsert_availability(
        db, guild_id=2, user_id=200, date="2026-12-01", block="evening"
    )
    counts = await queries.get_availability_counts(
        db, guild_id=1, date_from="2026-12-01", date_to="2026-12-01"
    )
    assert len(counts) == 1
    assert counts[0]["count"] == 1


async def test_respondent_count(db):
    await queries.upsert_availability(
        db, guild_id=1, user_id=100, date="2026-12-01", block="evening"
    )
    await queries.upsert_availability(
        db, guild_id=1, user_id=100, date="2026-12-02", block="morning"
    )
    await queries.upsert_availability(
        db, guild_id=1, user_id=101, date="2026-12-01", block="evening"
    )
    count = await queries.count_respondents(
        db, guild_id=1, date_from="2026-12-01", date_to="2026-12-31"
    )
    assert count == 2


def test_format_bar():
    assert format_bar(5, 10) == "\U0001f7e9" * 5
    assert format_bar(0, 10) == ""


def test_format_bar_max():
    result = format_bar(15, 15)
    assert len(result) == 15
