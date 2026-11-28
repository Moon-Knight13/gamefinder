"""Tests for bot/utils/formatting.py — pure helpers and DB-backed helpers."""

import datetime
from unittest.mock import MagicMock

from bot.db import queries
from bot.utils.formatting import (
    extract_id_from_footer,
    format_bar,
    format_heatmap,
    format_ranked_windows,
    get_guild_config,
    make_block_config,
    ordinal,
    validate_date,
)
from bot.utils.time_blocks import BlockConfig

# --- ordinal ---


def test_ordinal_1st():
    assert ordinal(1) == "1st"


def test_ordinal_2nd():
    assert ordinal(2) == "2nd"


def test_ordinal_3rd():
    assert ordinal(3) == "3rd"


def test_ordinal_4th():
    assert ordinal(4) == "4th"


def test_ordinal_11th():
    assert ordinal(11) == "11th"


def test_ordinal_12th():
    assert ordinal(12) == "12th"


def test_ordinal_13th():
    assert ordinal(13) == "13th"


def test_ordinal_21st():
    assert ordinal(21) == "21st"


def test_ordinal_22nd():
    assert ordinal(22) == "22nd"


def test_ordinal_111th():
    assert ordinal(111) == "111th"


def test_ordinal_112th():
    assert ordinal(112) == "112th"


# --- validate_date ---


def test_validate_date_valid():
    assert validate_date("2026-12-05") == datetime.date(2026, 12, 5)


def test_validate_date_invalid_string():
    assert validate_date("not-a-date") is None


def test_validate_date_bad_month():
    assert validate_date("2026-13-01") is None


def test_validate_date_empty():
    assert validate_date("") is None


def test_validate_date_none():
    assert validate_date(None) is None


# --- extract_id_from_footer ---


def test_extract_id_from_footer_found():
    embed = MagicMock()
    embed.footer.text = "Game #42 · by User"
    assert extract_id_from_footer(embed) == 42


def test_extract_id_from_footer_no_footer():
    embed = MagicMock()
    embed.footer = None
    assert extract_id_from_footer(embed) is None


def test_extract_id_from_footer_no_text():
    embed = MagicMock()
    embed.footer.text = None
    assert extract_id_from_footer(embed) is None


def test_extract_id_from_footer_no_match():
    embed = MagicMock()
    embed.footer.text = "No ID here"
    assert extract_id_from_footer(embed) is None


def test_extract_id_from_footer_campaign():
    embed = MagicMock()
    embed.footer.text = "Campaign #7"
    assert extract_id_from_footer(embed) == 7


# --- make_block_config ---


def test_make_block_config():
    config = {
        "morning_start": 8,
        "morning_end": 11,
        "afternoon_start": 11,
        "afternoon_end": 16,
        "evening_start": 16,
        "evening_end": 21,
    }
    bc = make_block_config(config)
    assert isinstance(bc, BlockConfig)
    assert bc.morning_start == 8
    assert bc.evening_end == 21


# --- format_bar ---


def test_format_bar_zero():
    assert format_bar(0, 10) == ""


def test_format_bar_negative():
    assert format_bar(-1, 10) == ""


def test_format_bar_positive():
    result = format_bar(3, 10)
    assert len(result) == 3


# --- format_heatmap ---


def test_format_heatmap_basic():
    data = [
        {"date": "2026-12-01", "block": "morning", "count": 2},
        {"date": "2026-12-01", "block": "evening", "count": 5},
    ]
    result = format_heatmap(data, threshold=4)
    assert "12-01" in result
    assert "\U0001f7e9" in result


def test_format_heatmap_empty():
    result = format_heatmap([], threshold=4)
    assert "Morn" in result


def test_format_heatmap_below_threshold():
    data = [
        {"date": "2026-12-01", "block": "morning", "count": 1},
    ]
    result = format_heatmap(data, threshold=4)
    assert "⬜" in result


def test_format_heatmap_zero_count_shows_black():
    data = [
        {"date": "2026-12-01", "block": "morning", "count": 0},
        {"date": "2026-12-01", "block": "afternoon", "count": 0},
        {"date": "2026-12-01", "block": "evening", "count": 3},
    ]
    result = format_heatmap(data, threshold=4)
    assert "⬛" in result


# --- format_ranked_windows ---


def test_format_ranked_windows_above_threshold():
    windows = [
        {"date": "2026-12-01", "block": "evening", "count": 5},
        {"date": "2026-12-02", "block": "morning", "count": 3},
    ]
    result = format_ranked_windows(windows, threshold=4)
    assert "2026-12-01" in result
    assert "Evening" in result
    assert "2026-12-02" not in result


def test_format_ranked_windows_none_meet_threshold():
    windows = [
        {"date": "2026-12-01", "block": "evening", "count": 2},
    ]
    result = format_ranked_windows(windows, threshold=4)
    assert result == "No windows meet threshold."


def test_format_ranked_windows_empty():
    result = format_ranked_windows([], threshold=4)
    assert result == "No windows meet threshold."


def test_format_ranked_windows_with_timezone():
    windows = [
        {"date": "2026-12-01", "block": "evening", "count": 5},
    ]
    bc = BlockConfig()
    result = format_ranked_windows(windows, threshold=4, server_tz="UTC", block_config=bc)
    assert "<t:" in result


# --- get_guild_config (DB-backed) ---


async def test_get_guild_config_existing(db):
    await queries.ensure_guild(db, 1)
    config = await get_guild_config(db, 1)
    assert config is not None
    assert config["threshold"] == 4


async def test_get_guild_config_auto_creates(db):
    config = await get_guild_config(db, 9999)
    assert config is not None
    assert config["guild_id"] == 9999
