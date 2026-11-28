"""Tests for pure helper functions in cog modules (no Discord mocking needed)."""

import datetime

from bot.cogs.campaigns import _campaign_embed, _next_weekday, _session_dates
from bot.cogs.games import _format_rsvp_field

# --- _format_rsvp_field ---


def test_format_rsvp_field_empty():
    result = _format_rsvp_field({})
    assert "Going: 0" in result
    assert "Maybe: 0" in result


def test_format_rsvp_field_going_only():
    result = _format_rsvp_field({"going": 5})
    assert "Going: 5" in result
    assert "Maybe: 0" in result


def test_format_rsvp_field_all_statuses():
    counts = {"going": 3, "maybe": 2, "not_going": 1, "spectator": 2, "waitlist": 1}
    result = _format_rsvp_field(counts)
    assert "Going: 3" in result
    assert "Maybe: 2" in result
    assert "Can't: 1" in result
    assert "Spectator: 2" in result
    assert "Waitlist: 1" in result


def test_format_rsvp_field_hides_zero_spectator():
    result = _format_rsvp_field({"going": 1, "maybe": 0, "not_going": 0})
    assert "Spectator" not in result
    assert "Waitlist" not in result


# --- _next_weekday ---


def test_next_weekday_same_day():
    monday = datetime.date(2026, 12, 7)
    assert monday.weekday() == 0
    result = _next_weekday(0, after=monday)
    assert result == monday


def test_next_weekday_next_occurrence():
    monday = datetime.date(2026, 12, 7)
    result = _next_weekday(4, after=monday)
    assert result == datetime.date(2026, 12, 11)
    assert result.weekday() == 4


def test_next_weekday_wraps_around():
    friday = datetime.date(2026, 12, 11)
    result = _next_weekday(0, after=friday)
    assert result == datetime.date(2026, 12, 14)
    assert result.weekday() == 0


# --- _session_dates ---


def test_session_dates_weekly():
    start = datetime.date(2026, 12, 7)
    dates = _session_dates(start, weekday=0, cadence="weekly", count=4)
    assert len(dates) == 4
    assert dates[0] == datetime.date(2026, 12, 7)
    assert dates[1] == datetime.date(2026, 12, 14)
    assert dates[3] == datetime.date(2026, 12, 28)


def test_session_dates_biweekly():
    start = datetime.date(2026, 12, 7)
    dates = _session_dates(start, weekday=0, cadence="biweekly", count=3)
    assert len(dates) == 3
    assert dates[0] == datetime.date(2026, 12, 7)
    assert dates[1] == datetime.date(2026, 12, 21)
    assert dates[2] == datetime.date(2027, 1, 4)


def test_session_dates_zero_count():
    dates = _session_dates(datetime.date(2026, 12, 7), weekday=0, cadence="weekly", count=0)
    assert dates == []


# --- _campaign_embed ---


def test_campaign_embed_structure():
    campaign = {
        "id": 1,
        "title": "Curse of Strahd",
        "description": "Gothic horror",
        "day_of_week": 4,
        "block": "evening",
        "cadence": "weekly",
        "session_count": 10,
        "sessions_completed": 3,
        "player_max": 6,
        "player_min": 3,
    }
    config = {
        "timezone": "UTC",
        "morning_start": 9,
        "morning_end": 12,
        "afternoon_start": 12,
        "afternoon_end": 17,
        "evening_start": 17,
        "evening_end": 22,
        "forecast_weeks": 3,
    }
    embed = _campaign_embed(campaign, config, roster_count=4)
    assert "Curse of Strahd" in embed.title
    assert embed.footer.text == "Campaign #1"
    field_names = [f.name for f in embed.fields]
    assert "Schedule" in field_names
    assert "Progress" in field_names
    assert "Roster" in field_names


def test_campaign_embed_completed():
    campaign = {
        "id": 2,
        "title": "Done Campaign",
        "description": "",
        "day_of_week": 0,
        "block": "morning",
        "cadence": "biweekly",
        "session_count": 8,
        "sessions_completed": 8,
        "player_max": 5,
        "player_min": 3,
    }
    config = {
        "timezone": "America/New_York",
        "morning_start": 9,
        "morning_end": 12,
        "afternoon_start": 12,
        "afternoon_end": 17,
        "evening_start": 17,
        "evening_end": 22,
        "forecast_weeks": 3,
    }
    embed = _campaign_embed(campaign, config, roster_count=5)
    progress_field = next(f for f in embed.fields if f.name == "Progress")
    assert "8/8" in progress_field.value
