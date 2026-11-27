from __future__ import annotations

import datetime
from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class BlockConfig:
    morning_start: int = 9
    morning_end: int = 12
    afternoon_start: int = 12
    afternoon_end: int = 17
    evening_start: int = 17
    evening_end: int = 22


BLOCK_RANGES: dict[str, tuple[str, str]] = {
    "morning": ("morning_start", "morning_end"),
    "afternoon": ("afternoon_start", "afternoon_end"),
    "evening": ("evening_start", "evening_end"),
}


def block_to_utc_range(
    date: datetime.date,
    block: str,
    server_tz: str,
    block_config: BlockConfig,
) -> tuple[datetime.datetime, datetime.datetime]:
    start_attr, end_attr = BLOCK_RANGES[block]
    start_hour = getattr(block_config, start_attr)
    end_hour = getattr(block_config, end_attr)

    tz = ZoneInfo(server_tz)
    local_start = datetime.datetime(date.year, date.month, date.day, start_hour, tzinfo=tz)
    local_end = datetime.datetime(date.year, date.month, date.day, end_hour, tzinfo=tz)

    utc_start = local_start.astimezone(datetime.UTC).replace(tzinfo=datetime.UTC)
    utc_end = local_end.astimezone(datetime.UTC).replace(tzinfo=datetime.UTC)
    return utc_start, utc_end


def utc_to_discord_timestamp(dt: datetime.datetime, style: str = "F") -> str:
    unix = int(dt.timestamp())
    return f"<t:{unix}:{style}>"


def date_range(start: datetime.date, weeks: int) -> list[datetime.date]:
    return [start + datetime.timedelta(days=i) for i in range(weeks * 7)]


BLOCK_LABELS = {
    "morning": "Morning",
    "afternoon": "Afternoon",
    "evening": "Evening",
}

BLOCK_ORDER = ["morning", "afternoon", "evening"]
