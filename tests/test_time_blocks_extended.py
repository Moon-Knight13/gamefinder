"""Extended tests for bot/utils/time_blocks.py — slot_to_discord_time, slot_to_discord_short."""

from bot.utils.time_blocks import (
    BLOCK_LABELS,
    BlockConfig,
    slot_to_discord_short,
    slot_to_discord_time,
)


def test_slot_to_discord_time_utc():
    result = slot_to_discord_time("2026-12-01", "evening", "UTC", BlockConfig())
    assert "<t:" in result
    assert "to" in result


def test_slot_to_discord_time_new_york():
    result = slot_to_discord_time("2026-12-01", "evening", "America/New_York", BlockConfig())
    assert "<t:" in result


def test_slot_to_discord_time_morning():
    result = slot_to_discord_time("2026-12-01", "morning", "UTC", BlockConfig())
    assert "<t:" in result


def test_slot_to_discord_short_utc():
    result = slot_to_discord_short("2026-12-01", "evening", "UTC", BlockConfig())
    assert "<t:" in result
    assert BLOCK_LABELS["evening"] in result


def test_slot_to_discord_short_all_blocks():
    bc = BlockConfig()
    for block in ("morning", "afternoon", "evening"):
        result = slot_to_discord_short("2026-12-01", block, "UTC", bc)
        assert BLOCK_LABELS[block] in result
        assert "<t:" in result


def test_slot_to_discord_short_tokyo():
    result = slot_to_discord_short("2026-12-01", "morning", "Asia/Tokyo", BlockConfig())
    assert "<t:" in result
    assert "Morning" in result
