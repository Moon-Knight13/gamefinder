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
