"""BDD-style scenario tests for GameFinder user stories."""

import datetime

from bot.db import queries
from tests.factory import Factory


# --- Scenario: Player marks availability and DM sees windows ---


async def test_player_availability_shows_in_windows(db):
    """Given players mark availability, when DM checks windows, then viable slots appear."""
    f = Factory(db)
    await f.setup_guild(threshold=3)
    party = await f.create_party(size=5, archetype="weekend_evening")
    count = await f.fill_availability(party, weeks=3)
    assert count > 0

    today = datetime.date.today()
    date_to = (today + datetime.timedelta(weeks=3)).isoformat()
    counts = await queries.get_availability_counts(
        db, f.guild_id, today.isoformat(), date_to
    )
    viable = [c for c in counts if c["count"] >= 3]
    assert len(viable) > 0, "Should have viable windows with 5 players"


async def test_windows_respect_threshold(db):
    """Given threshold=4, when only 3 players mark a slot, it doesn't appear as viable."""
    f = Factory(db)
    await f.setup_guild(threshold=4)
    party = await f.create_party(size=3, archetype="weeknight")
    await f.fill_availability(party, weeks=2)

    today = datetime.date.today()
    date_to = (today + datetime.timedelta(weeks=2)).isoformat()
    counts = await queries.get_availability_counts(
        db, f.guild_id, today.isoformat(), date_to
    )
    # Max possible is 3 players, threshold is 4
    viable = [c for c in counts if c["count"] >= 4]
    assert len(viable) == 0


# --- Scenario: DM posts game, players RSVP, quorum reached ---


async def test_full_game_lifecycle(db):
    """Given a game is posted, when enough players RSVP going, then game reaches quorum."""
    f = Factory(db)
    await f.setup_guild()
    party = await f.create_party(size=6)
    dm = party[0]
    players = party[1:]

    game_id = await f.create_game(dm, title="Lost Mine of Phandelver", player_cap=4)
    game = await queries.get_game(db, game_id, f.guild_id)
    assert game["status"] == "open"

    # 3 going — not at quorum yet
    await f.rsvp_players(game_id, going=players[:3])
    counts = await queries.get_rsvp_counts(db, game_id)
    assert counts["going"] == 3

    # 4th going — hits quorum
    await queries.upsert_rsvp(db, game_id, players[3].user_id, "going")
    counts = await queries.get_rsvp_counts(db, game_id)
    assert counts["going"] == 4
    assert counts["going"] >= game["player_cap"]


async def test_rsvp_status_changes(db):
    """Given a player RSVPs going, when they change to maybe, then counts update."""
    f = Factory(db)
    await f.setup_guild()
    dm = await f.create_player(name="DM")
    player = await f.create_player(name="Flaky")

    game_id = await f.create_game(dm, player_cap=3)
    await queries.upsert_rsvp(db, game_id, player.user_id, "going")
    counts = await queries.get_rsvp_counts(db, game_id)
    assert counts["going"] == 1

    await queries.upsert_rsvp(db, game_id, player.user_id, "maybe")
    counts = await queries.get_rsvp_counts(db, game_id)
    assert counts.get("going", 0) == 0
    assert counts["maybe"] == 1


async def test_mixed_rsvp_types_all_tracked(db):
    """Given players RSVP with different statuses, all are counted correctly."""
    f = Factory(db)
    await f.setup_guild()
    dm = await f.create_player()
    game_id = await f.create_game(dm, player_cap=10)

    going = [await f.create_player() for _ in range(4)]
    maybe = [await f.create_player() for _ in range(2)]
    spectators = [await f.create_player() for _ in range(3)]
    waitlisted = [await f.create_player() for _ in range(1)]

    await f.rsvp_players(game_id, going=going, maybe=maybe,
                         spectators=spectators, waitlist=waitlisted)

    counts = await queries.get_rsvp_counts(db, game_id)
    assert counts["going"] == 4
    assert counts["maybe"] == 2
    assert counts["spectator"] == 3
    assert counts["waitlist"] == 1


# --- Scenario: Campaign consistency ---


async def test_campaign_consistency_detection(db):
    """Given players set recurring availability, consistent slots are detected."""
    f = Factory(db)
    await f.setup_guild()
    party = await f.create_party(size=5, archetype="weekend_evening")
    await f.fill_availability(party, weeks=4)

    today = datetime.date.today()
    date_to = (today + datetime.timedelta(weeks=4)).isoformat()
    consistent = await queries.get_consistent_players(
        db, f.guild_id, today.isoformat(), date_to, min_weeks=3
    )
    assert len(consistent) > 0, "Should detect consistent slots with 4 weeks of data"
    best = consistent[0]
    assert best["consistent_count"] >= 3


async def test_campaign_roster_cap(db):
    """Given a campaign with max 4 players, 5th player is rejected."""
    f = Factory(db)
    await f.setup_guild()
    dm = await f.create_player()
    campaign_id = await f.create_campaign(dm, player_max=4, session_count=8)

    players = [await f.create_player() for _ in range(5)]
    added = await f.fill_roster(campaign_id, players)
    assert added == 4

    roster = await queries.get_roster(db, campaign_id)
    assert len(roster) == 4


async def test_campaign_lifecycle(db):
    """Given a campaign, it progresses through active → paused → completed."""
    f = Factory(db)
    await f.setup_guild()
    dm = await f.create_player()
    campaign_id = await f.create_campaign(dm, session_count=10)

    campaign = await queries.get_campaign(db, campaign_id, f.guild_id)
    assert campaign["status"] == "active"

    await queries.update_campaign(db, campaign_id, f.guild_id, status="paused")
    campaign = await queries.get_campaign(db, campaign_id, f.guild_id)
    assert campaign["status"] == "paused"

    await queries.update_campaign(db, campaign_id, f.guild_id, status="active")
    await queries.update_campaign(db, campaign_id, f.guild_id, sessions_completed=10)
    await queries.update_campaign(db, campaign_id, f.guild_id, status="completed")
    campaign = await queries.get_campaign(db, campaign_id, f.guild_id)
    assert campaign["status"] == "completed"
    assert campaign["sessions_completed"] == 10


# --- Scenario: Guild isolation ---


async def test_guild_isolation_games(db):
    """Given games in two guilds, each guild only sees its own."""
    f1 = Factory(db, guild_id=1001)
    f2 = Factory(db, guild_id=1002)
    await f1.setup_guild()
    await f2.setup_guild()

    dm1 = await f1.create_player()
    dm2 = await f2.create_player()

    await f1.create_game(dm1, title="Guild1 Game")
    await f2.create_game(dm2, title="Guild2 Game")

    games1 = await queries.list_games(db, 1001)
    games2 = await queries.list_games(db, 1002)
    assert len(games1) == 1
    assert games1[0]["title"] == "Guild1 Game"
    assert len(games2) == 1
    assert games2[0]["title"] == "Guild2 Game"


async def test_guild_isolation_availability(db):
    """Given availability in two guilds, windows don't cross-contaminate."""
    f1 = Factory(db, guild_id=2001)
    f2 = Factory(db, guild_id=2002)
    await f1.setup_guild()
    await f2.setup_guild()

    p1 = await f1.create_player()
    await queries.upsert_availability(db, 2001, p1.user_id, "2026-12-01", "evening")

    today = datetime.date.today()
    counts1 = await queries.get_availability_counts(db, 2001, "2026-12-01", "2026-12-01")
    counts2 = await queries.get_availability_counts(db, 2002, "2026-12-01", "2026-12-01")
    assert len(counts1) == 1
    assert len(counts2) == 0


# --- Scenario: Data deletion ---


async def test_user_data_deletion_cascades(db):
    """Given a user with availability + RSVPs, deletion removes everything."""
    f = Factory(db)
    await f.setup_guild()
    player = await f.create_player()
    dm = await f.create_player()

    await f.fill_availability([player], weeks=2)
    game_id = await f.create_game(dm, player_cap=5)
    await queries.upsert_rsvp(db, game_id, player.user_id, "going")

    await queries.delete_user_data(db, player.user_id)

    avail = await queries.get_user_availability(
        db, f.guild_id, player.user_id, "2026-01-01", "2027-12-31"
    )
    assert len(avail) == 0
    tz = await queries.get_user_timezone(db, player.user_id)
    assert tz is None


# --- Stress tests ---


async def test_stress_many_players(db):
    """50 players, 4 weeks availability, verify aggregation handles volume."""
    f = Factory(db)
    await f.setup_guild(threshold=10)
    party = await f.create_party(size=50, archetype="scattered")
    count = await f.fill_availability(party, weeks=4)
    assert count > 500

    today = datetime.date.today()
    date_to = (today + datetime.timedelta(weeks=4)).isoformat()
    counts = await queries.get_availability_counts(
        db, f.guild_id, today.isoformat(), date_to
    )
    assert len(counts) > 0
    top = counts[0]
    assert top["count"] >= 10


async def test_stress_many_games(db):
    """20 concurrent games with RSVPs on each."""
    f = Factory(db)
    await f.setup_guild()
    dm = await f.create_player()
    players = [await f.create_player() for _ in range(10)]

    game_ids = []
    for i in range(20):
        date = (datetime.date.today() + datetime.timedelta(days=i % 14)).isoformat()
        gid = await f.create_game(dm, title=f"Game {i+1}", date=date, player_cap=5)
        game_ids.append(gid)

    # RSVP random players to random games
    for game_id in game_ids:
        sample = random.sample(players, min(5, len(players)))
        for p in sample[:3]:
            await queries.upsert_rsvp(db, game_id, p.user_id, "going")
        for p in sample[3:]:
            await queries.upsert_rsvp(db, game_id, p.user_id, "maybe")

    games = await queries.list_games(db, f.guild_id)
    assert len(games) == 20

    for game_id in game_ids:
        counts = await queries.get_rsvp_counts(db, game_id)
        assert counts.get("going", 0) + counts.get("maybe", 0) > 0


async def test_stress_concurrent_availability_updates(db):
    """Many players updating availability for the same slots."""
    f = Factory(db)
    await f.setup_guild()
    players = [await f.create_player() for _ in range(30)]
    target_date = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()

    # All 30 players mark the same slot
    for p in players:
        await queries.upsert_availability(db, f.guild_id, p.user_id, target_date, "evening")

    counts = await queries.get_availability_counts(db, f.guild_id, target_date, target_date)
    evening = next(c for c in counts if c["block"] == "evening")
    assert evening["count"] == 30

    # Half remove it
    for p in players[:15]:
        await queries.delete_availability(db, f.guild_id, p.user_id, target_date, "evening")

    counts = await queries.get_availability_counts(db, f.guild_id, target_date, target_date)
    evening = next(c for c in counts if c["block"] == "evening")
    assert evening["count"] == 15


import random


# --- Testing gaps from review ---


async def test_invalid_date_rejected(db):
    """validate_date returns None for bad input."""
    from bot.utils.formatting import validate_date
    assert validate_date("2026-12-05") == datetime.date(2026, 12, 5)
    assert validate_date("banana") is None
    assert validate_date("2026-13-01") is None
    assert validate_date("") is None


async def test_delete_user_data_includes_recurring(db):
    """delete_user_data removes recurring_availability too."""
    f = Factory(db)
    await f.setup_guild()
    player = await f.create_player()
    await queries.set_recurring(db, f.guild_id, player.user_id, 4, "evening")
    recurring = await queries.get_user_recurring(db, f.guild_id, player.user_id)
    assert len(recurring) == 1

    await queries.delete_user_data(db, player.user_id)
    recurring = await queries.get_user_recurring(db, f.guild_id, player.user_id)
    assert len(recurring) == 0


async def test_weekday_convention_monday_zero(db):
    """get_consistent_players uses Monday=0 convention matching Python."""
    f = Factory(db)
    await f.setup_guild()
    player = await f.create_player()

    # Mark availability on 3 Fridays (Python weekday 4)
    for week in range(3):
        d = datetime.date(2026, 12, 4) + datetime.timedelta(weeks=week)
        assert d.weekday() == 4
        await queries.upsert_availability(db, f.guild_id, player.user_id, d.isoformat(), "evening")

    consistent = await queries.get_consistent_players(
        db, f.guild_id, "2026-12-04", "2026-12-25", min_weeks=3
    )
    friday_slots = [s for s in consistent if s["weekday"] == 4]
    assert len(friday_slots) == 1
    assert friday_slots[0]["consistent_count"] == 1


async def test_list_games_all_statuses(db):
    """list_games with status=None returns all games."""
    f = Factory(db, guild_id=5001)
    await f.setup_guild()
    dm = await f.create_player()
    g1 = await f.create_game(dm, title="Open Game")
    g2 = await f.create_game(dm, title="Full Game")
    await queries.update_game_status(db, g2, 5001, "full")
    g3 = await f.create_game(dm, title="Cancelled Game")
    await queries.update_game_status(db, g3, 5001, "cancelled")

    open_only = await queries.list_games(db, 5001, status="open")
    assert len(open_only) == 1
    all_games = await queries.list_games(db, 5001, status=None)
    assert len(all_games) == 3


async def test_roster_cap_enforced(db):
    """add_to_roster returns False when roster is full."""
    f = Factory(db)
    await f.setup_guild()
    dm = await f.create_player()
    cid = await f.create_campaign(dm, player_max=2, session_count=4)
    p1 = await f.create_player()
    p2 = await f.create_player()
    p3 = await f.create_player()
    assert await queries.add_to_roster(db, cid, p1.user_id) is True
    assert await queries.add_to_roster(db, cid, p2.user_id) is True
    assert await queries.add_to_roster(db, cid, p3.user_id) is False
