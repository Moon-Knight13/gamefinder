from bot.db import queries


async def test_create_and_get_game(db):
    game_id = await queries.create_game(
        db,
        guild_id=1,
        creator_id=100,
        title="Test Game",
        description="A test",
        slot_date="2026-12-01",
        slot_block="evening",
        player_cap=5,
    )
    game = await queries.get_game(db, game_id=game_id, guild_id=1)
    assert game["title"] == "Test Game"
    assert game["player_cap"] == 5
    assert game["status"] == "open"


async def test_rsvp_counts(db):
    game_id = await queries.create_game(
        db,
        guild_id=1,
        creator_id=100,
        title="Test",
        description="",
        slot_date="2026-12-01",
        slot_block="evening",
        player_cap=5,
    )
    await queries.upsert_rsvp(db, game_id=game_id, user_id=200, status="going")
    await queries.upsert_rsvp(db, game_id=game_id, user_id=201, status="going")
    await queries.upsert_rsvp(db, game_id=game_id, user_id=202, status="maybe")
    counts = await queries.get_rsvp_counts(db, game_id=game_id)
    assert counts["going"] == 2
    assert counts["maybe"] == 1
    assert counts.get("not_going", 0) == 0


async def test_rsvp_upsert_changes_status(db):
    game_id = await queries.create_game(
        db,
        guild_id=1,
        creator_id=100,
        title="Test",
        description="",
        slot_date="2026-12-01",
        slot_block="evening",
        player_cap=5,
    )
    await queries.upsert_rsvp(db, game_id=game_id, user_id=200, status="going")
    await queries.upsert_rsvp(db, game_id=game_id, user_id=200, status="not_going")
    counts = await queries.get_rsvp_counts(db, game_id=game_id)
    assert counts.get("going", 0) == 0
    assert counts["not_going"] == 1


async def test_list_games_filters_by_guild(db):
    await queries.create_game(
        db,
        guild_id=1,
        creator_id=100,
        title="Guild 1 Game",
        description="",
        slot_date="2026-12-01",
        slot_block="evening",
        player_cap=5,
    )
    await queries.create_game(
        db,
        guild_id=2,
        creator_id=200,
        title="Guild 2 Game",
        description="",
        slot_date="2026-12-01",
        slot_block="evening",
        player_cap=5,
    )
    games = await queries.list_games(db, guild_id=1)
    assert len(games) == 1
    assert games[0]["title"] == "Guild 1 Game"


async def test_get_game_respects_guild(db):
    game_id = await queries.create_game(
        db,
        guild_id=1,
        creator_id=100,
        title="Test",
        description="",
        slot_date="2026-12-01",
        slot_block="evening",
        player_cap=5,
    )
    result = await queries.get_game(db, game_id=game_id, guild_id=2)
    assert result is None


async def test_update_game_status(db):
    game_id = await queries.create_game(
        db,
        guild_id=1,
        creator_id=100,
        title="Test",
        description="",
        slot_date="2026-12-01",
        slot_block="evening",
        player_cap=5,
    )
    await queries.update_game_status(db, game_id=game_id, guild_id=1, status="cancelled")
    game = await queries.get_game(db, game_id=game_id, guild_id=1)
    assert game["status"] == "cancelled"


async def test_rsvp_spectator_and_waitlist(db):
    game_id = await queries.create_game(
        db,
        guild_id=1,
        creator_id=100,
        title="Test",
        description="",
        slot_date="2026-12-01",
        slot_block="evening",
        player_cap=5,
    )
    await queries.upsert_rsvp(db, game_id=game_id, user_id=200, status="spectator")
    await queries.upsert_rsvp(db, game_id=game_id, user_id=201, status="waitlist")
    await queries.upsert_rsvp(db, game_id=game_id, user_id=202, status="going")
    counts = await queries.get_rsvp_counts(db, game_id=game_id)
    assert counts["spectator"] == 1
    assert counts["waitlist"] == 1
    assert counts["going"] == 1


async def test_update_game_fields(db):
    game_id = await queries.create_game(
        db,
        guild_id=1,
        creator_id=100,
        title="Original",
        description="Old desc",
        slot_date="2026-12-01",
        slot_block="evening",
        player_cap=5,
    )
    await queries.update_game(db, game_id=game_id, guild_id=1, title="Updated", player_cap=8)
    game = await queries.get_game(db, game_id=game_id, guild_id=1)
    assert game["title"] == "Updated"
    assert game["player_cap"] == 8
    assert game["description"] == "Old desc"


async def test_rsvp_quorum_triggers_full(db):
    game_id = await queries.create_game(
        db,
        guild_id=1,
        creator_id=100,
        title="Quorum Test",
        description="",
        slot_date="2026-12-01",
        slot_block="evening",
        player_cap=3,
    )
    for uid in [200, 201, 202]:
        await queries.upsert_rsvp(db, game_id=game_id, user_id=uid, status="going")
    counts = await queries.get_rsvp_counts(db, game_id=game_id)
    assert counts["going"] == 3
    game = await queries.get_game(db, game_id=game_id, guild_id=1)
    # Status change happens in the RSVP handler, not the query layer
    # But verify the data supports detecting quorum
    assert counts["going"] >= game["player_cap"]


async def test_mixed_rsvp_roles(db):
    game_id = await queries.create_game(
        db,
        guild_id=1,
        creator_id=100,
        title="Mixed",
        description="",
        slot_date="2026-12-01",
        slot_block="evening",
        player_cap=5,
    )
    await queries.upsert_rsvp(db, game_id=game_id, user_id=200, status="going")
    await queries.upsert_rsvp(db, game_id=game_id, user_id=201, status="going")
    await queries.upsert_rsvp(db, game_id=game_id, user_id=202, status="maybe")
    await queries.upsert_rsvp(db, game_id=game_id, user_id=203, status="spectator")
    await queries.upsert_rsvp(db, game_id=game_id, user_id=204, status="waitlist")
    await queries.upsert_rsvp(db, game_id=game_id, user_id=205, status="not_going")
    counts = await queries.get_rsvp_counts(db, game_id=game_id)
    assert counts["going"] == 2
    assert counts["maybe"] == 1
    assert counts["spectator"] == 1
    assert counts["waitlist"] == 1
    assert counts["not_going"] == 1


async def test_rsvp_change_going_to_waitlist(db):
    game_id = await queries.create_game(
        db,
        guild_id=1,
        creator_id=100,
        title="Switch",
        description="",
        slot_date="2026-12-01",
        slot_block="evening",
        player_cap=5,
    )
    await queries.upsert_rsvp(db, game_id=game_id, user_id=200, status="going")
    counts = await queries.get_rsvp_counts(db, game_id=game_id)
    assert counts["going"] == 1
    await queries.upsert_rsvp(db, game_id=game_id, user_id=200, status="waitlist")
    counts = await queries.get_rsvp_counts(db, game_id=game_id)
    assert counts.get("going", 0) == 0
    assert counts["waitlist"] == 1


async def test_campaign_roster(db):
    campaign_id = await queries.create_campaign(
        db,
        guild_id=1,
        creator_id=100,
        title="Test Campaign",
        description="",
        day_of_week=4,
        block="evening",
        session_count=8,
    )
    for uid in [200, 201, 202, 203]:
        await queries.add_to_roster(db, campaign_id, uid)
    roster = await queries.get_roster(db, campaign_id)
    assert len(roster) == 4
    await queries.remove_from_roster(db, campaign_id, 201)
    roster = await queries.get_roster(db, campaign_id)
    assert len(roster) == 3
    assert all(r["user_id"] != 201 for r in roster)


async def test_campaign_lifecycle(db):
    campaign_id = await queries.create_campaign(
        db,
        guild_id=1,
        creator_id=100,
        title="Lifecycle",
        description="",
        day_of_week=5,
        block="evening",
        session_count=10,
    )
    campaign = await queries.get_campaign(db, campaign_id, guild_id=1)
    assert campaign["status"] == "active"
    assert campaign["session_count"] == 10
    assert campaign["sessions_completed"] == 0
    await queries.update_campaign(db, campaign_id, 1, sessions_completed=5)
    campaign = await queries.get_campaign(db, campaign_id, guild_id=1)
    assert campaign["sessions_completed"] == 5
    await queries.update_campaign(db, campaign_id, 1, status="completed")
    campaign = await queries.get_campaign(db, campaign_id, guild_id=1)
    assert campaign["status"] == "completed"


async def test_set_game_message(db):
    game_id = await queries.create_game(
        db,
        guild_id=1,
        creator_id=100,
        title="Test",
        description="",
        slot_date="2026-12-01",
        slot_block="evening",
        player_cap=5,
    )
    await queries.set_game_message(db, game_id=game_id, guild_id=1, message_id=999, channel_id=888)
    game = await queries.get_game(db, game_id=game_id, guild_id=1)
    assert game["message_id"] == 999
    assert game["channel_id"] == 888
