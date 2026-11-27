from datetime import UTC, date, datetime

from bot.utils.time_blocks import (
    BlockConfig,
    block_to_utc_range,
    date_range,
    utc_to_discord_timestamp,
)


def test_block_to_utc_range_london():
    start, end = block_to_utc_range(date(2026, 12, 1), "evening", "Europe/London", BlockConfig())
    assert start == datetime(2026, 12, 1, 17, 0, tzinfo=UTC)
    assert end == datetime(2026, 12, 1, 22, 0, tzinfo=UTC)


def test_block_to_utc_range_new_york():
    start, end = block_to_utc_range(date(2026, 12, 1), "evening", "America/New_York", BlockConfig())
    assert start == datetime(2026, 12, 1, 22, 0, tzinfo=UTC)
    assert end == datetime(2026, 12, 2, 3, 0, tzinfo=UTC)


def test_utc_to_discord_timestamp():
    dt = datetime(2026, 12, 1, 17, 0, tzinfo=UTC)
    result = utc_to_discord_timestamp(dt, "t")
    assert result == f"<t:{int(dt.timestamp())}:t>"


def test_date_range_3_weeks():
    dates = date_range(date(2026, 12, 1), weeks=3)
    assert len(dates) == 21
    assert dates[0] == date(2026, 12, 1)
    assert dates[-1] == date(2026, 12, 21)


def test_block_to_utc_range_dst_transition():
    start_before, _ = block_to_utc_range(
        date(2026, 10, 31), "evening", "America/New_York", BlockConfig()
    )
    start_after, _ = block_to_utc_range(
        date(2026, 11, 2), "evening", "America/New_York", BlockConfig()
    )
    assert start_before != start_after


def test_morning_block():
    start, end = block_to_utc_range(date(2026, 12, 1), "morning", "UTC", BlockConfig())
    assert start == datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
    assert end == datetime(2026, 12, 1, 12, 0, tzinfo=UTC)


def test_custom_block_config():
    config = BlockConfig(evening_start=18, evening_end=23)
    start, end = block_to_utc_range(date(2026, 12, 1), "evening", "UTC", config)
    assert start == datetime(2026, 12, 1, 18, 0, tzinfo=UTC)
    assert end == datetime(2026, 12, 1, 23, 0, tzinfo=UTC)
