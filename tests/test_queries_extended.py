"""Extended query tests covering gaps in bot/db/queries.py and database.py."""

from bot.db import queries
from tests.factory import Factory

# --- update_guild_config edge cases ---


async def test_update_guild_config_filters_unknown_keys(db):
    await queries.ensure_guild(db, 1)
    await queries.update_guild_config(db, 1, threshold=5, bogus_key="ignored")
    config = await queries.get_guild_config(db, 1)
    assert config["threshold"] == 5


async def test_update_guild_config_no_kwargs(db):
    await queries.ensure_guild(db, 1)
    await queries.update_guild_config(db, 1)
    config = await queries.get_guild_config(db, 1)
    assert config["threshold"] == 4


async def test_update_guild_config_all_unknown_keys(db):
    await queries.ensure_guild(db, 1)
    await queries.update_guild_config(db, 1, fake1="a", fake2="b")
    config = await queries.get_guild_config(db, 1)
    assert config["threshold"] == 4


# --- set_game_event_id ---


async def test_set_game_event_id(db):
    game_id = await queries.create_game(
        db, guild_id=1, creator_id=100, title="Test", description="",
        slot_date="2026-12-01", slot_block="evening", player_cap=5,
    )
    await queries.set_game_event_id(db, game_id, 1, 123456)
    game = await queries.get_game(db, game_id, 1)
    assert game["discord_event_id"] == 123456


# --- update_game edge cases ---


async def test_update_game_no_valid_keys(db):
    game_id = await queries.create_game(
        db, guild_id=1, creator_id=100, title="Original", description="",
        slot_date="2026-12-01", slot_block="evening", player_cap=5,
    )
    await queries.update_game(db, game_id, 1, bogus="val")
    game = await queries.get_game(db, game_id, 1)
    assert game["title"] == "Original"


async def test_update_game_empty_kwargs(db):
    game_id = await queries.create_game(
        db, guild_id=1, creator_id=100, title="Original", description="",
        slot_date="2026-12-01", slot_block="evening", player_cap=5,
    )
    await queries.update_game(db, game_id, 1)
    game = await queries.get_game(db, game_id, 1)
    assert game["title"] == "Original"


# --- get_rsvps ordered ---


async def test_get_rsvps_returns_ordered(db):
    game_id = await queries.create_game(
        db, guild_id=1, creator_id=100, title="Test", description="",
        slot_date="2026-12-01", slot_block="evening", player_cap=5,
    )
    await queries.upsert_rsvp(db, game_id, 200, "going")
    await queries.upsert_rsvp(db, game_id, 201, "maybe")
    await queries.upsert_rsvp(db, game_id, 202, "spectator")
    rsvps = await queries.get_rsvps(db, game_id)
    assert len(rsvps) == 3
    assert rsvps[0]["user_id"] == 200


# --- recurring availability ---


async def test_delete_recurring(db):
    await queries.set_recurring(db, 1, 100, 4, "evening")
    recurring = await queries.get_user_recurring(db, 1, 100)
    assert len(recurring) == 1
    await queries.delete_recurring(db, 1, 100, 4, "evening")
    recurring = await queries.get_user_recurring(db, 1, 100)
    assert len(recurring) == 0


async def test_clear_user_recurring(db):
    await queries.set_recurring(db, 1, 100, 0, "morning")
    await queries.set_recurring(db, 1, 100, 4, "evening")
    recurring = await queries.get_user_recurring(db, 1, 100)
    assert len(recurring) == 2
    await queries.clear_user_recurring(db, 1, 100)
    recurring = await queries.get_user_recurring(db, 1, 100)
    assert len(recurring) == 0


async def test_set_recurring_custom_hours(db):
    await queries.set_recurring(db, 1, 100, 3, "custom", custom_start=14, custom_end=18)
    recurring = await queries.get_user_recurring(db, 1, 100)
    assert len(recurring) == 1
    assert recurring[0]["custom_start"] == 14
    assert recurring[0]["custom_end"] == 18


# --- list_campaigns ---


async def test_list_campaigns_filters_status(db):
    f = Factory(db)
    await f.setup_guild()
    dm = await f.create_player()
    await f.create_campaign(dm, title="Active Camp")
    c2 = await f.create_campaign(dm, title="Paused Camp")
    await queries.update_campaign(db, c2, f.guild_id, status="paused")

    active = await queries.list_campaigns(db, f.guild_id, status="active")
    assert len(active) == 1
    assert active[0]["title"] == "Active Camp"

    paused = await queries.list_campaigns(db, f.guild_id, status="paused")
    assert len(paused) == 1
    assert paused[0]["title"] == "Paused Camp"


# --- update_campaign edge cases ---


async def test_update_campaign_filters_unknown_keys(db):
    f = Factory(db)
    await f.setup_guild()
    dm = await f.create_player()
    cid = await f.create_campaign(dm, title="Test")
    await queries.update_campaign(db, cid, f.guild_id, bogus="val")
    campaign = await queries.get_campaign(db, cid, f.guild_id)
    assert campaign["title"] == "Test"


async def test_update_campaign_empty_kwargs(db):
    f = Factory(db)
    await f.setup_guild()
    dm = await f.create_player()
    cid = await f.create_campaign(dm, title="Test")
    await queries.update_campaign(db, cid, f.guild_id)
    campaign = await queries.get_campaign(db, cid, f.guild_id)
    assert campaign["title"] == "Test"


# --- get_campaign guild isolation ---


async def test_get_campaign_wrong_guild(db):
    f = Factory(db)
    await f.setup_guild()
    dm = await f.create_player()
    cid = await f.create_campaign(dm)
    result = await queries.get_campaign(db, cid, guild_id=9999)
    assert result is None


# --- database.execute_many ---


async def test_execute_many(db):
    await queries.ensure_guild(db, 1)
    await queries.ensure_user(db, 100)
    await queries.ensure_user(db, 101)
    params = [
        (1, 100, "2026-12-01", "morning"),
        (1, 101, "2026-12-01", "evening"),
    ]
    await db.execute_many(
        "INSERT OR IGNORE INTO availability (guild_id, user_id, date, block) VALUES (?, ?, ?, ?)",
        params,
    )
    rows = await queries.get_availability_counts(db, 1, "2026-12-01", "2026-12-01")
    assert len(rows) == 2


# --- get_guild_config returns None for missing guild ---


async def test_get_guild_config_missing(db):
    result = await queries.get_guild_config(db, 99999)
    assert result is None


# --- count_respondents empty ---


async def test_count_respondents_no_data(db):
    await queries.ensure_guild(db, 1)
    count = await queries.count_respondents(db, 1, "2026-12-01", "2026-12-31")
    assert count == 0


async def test_delete_guild_data_with_campaigns(db):
    """Covers campaign + roster + sessions cascade in delete_guild_data."""
    f = Factory(db)
    await f.setup_guild()
    dm = await f.create_player()
    cid = await f.create_campaign(dm, session_count=4)
    p1 = await f.create_player()
    await queries.add_to_roster(db, cid, p1.user_id)

    await db.execute(
        "INSERT INTO sessions (campaign_id, session_number, date) VALUES (?, ?, ?)",
        (cid, 1, "2026-12-05"),
    )

    await queries.delete_guild_data(db, f.guild_id)

    campaigns = await queries.list_campaigns(db, f.guild_id)
    assert len(campaigns) == 0
    roster = await queries.get_roster(db, cid)
    assert len(roster) == 0
    sessions = await db.fetch_all("SELECT * FROM sessions WHERE campaign_id = ?", (cid,))
    assert len(sessions) == 0
