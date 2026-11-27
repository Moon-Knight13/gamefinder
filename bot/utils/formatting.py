from __future__ import annotations

import datetime
import re

from bot.db import queries
from bot.utils.time_blocks import BlockConfig


async def get_guild_config(db, guild_id: int) -> dict:
    config = await queries.get_guild_config(db, guild_id)
    if not config:
        await queries.ensure_guild(db, guild_id)
        config = await queries.get_guild_config(db, guild_id)
    return config


def make_block_config(config: dict) -> BlockConfig:
    return BlockConfig(
        morning_start=config["morning_start"],
        morning_end=config["morning_end"],
        afternoon_start=config["afternoon_start"],
        afternoon_end=config["afternoon_end"],
        evening_start=config["evening_start"],
        evening_end=config["evening_end"],
    )


def ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{['th', 'st', 'nd', 'rd', 'th', 'th', 'th', 'th', 'th', 'th'][n % 10]}"


def extract_id_from_footer(embed) -> int | None:
    if embed.footer and embed.footer.text:
        match = re.search(r"#(\d+)", embed.footer.text)
        if match:
            return int(match.group(1))
    return None


def validate_date(date_str: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


def format_bar(count: int, max_count: int) -> str:
    if count <= 0:
        return ""
    return "\U0001f7e9" * count


def format_heatmap(week_data: list[dict], threshold: int) -> str:
    from bot.utils.time_blocks import BLOCK_ORDER

    days: dict[str, dict[str, int]] = {}
    for row in week_data:
        d = row["date"]
        if d not in days:
            days[d] = {}
        days[d][row["block"]] = row["count"]

    lines = []
    header = "         " + "  ".join(["Morn", " Aft", " Eve"])
    lines.append(header)

    for date_str in sorted(days.keys()):
        counts = days[date_str]
        cells = []
        for block in BLOCK_ORDER:
            c = counts.get(block, 0)
            if c >= threshold:
                cells.append(f" {c:>2}\U0001f7e9")
            elif c > 0:
                cells.append(f" {c:>2}⬜")
            else:
                cells.append("  0⬛")
        day_label = date_str[-5:]
        lines.append(f"{day_label}  {'  '.join(cells)}")

    return "\n".join(lines)


def format_ranked_windows(
    windows: list[dict],
    threshold: int,
    server_tz: str | None = None,
    block_config=None,
) -> str:
    lines = []
    for w in windows:
        count = w["count"]
        if count < threshold:
            continue
        bar = format_bar(count, count)
        if server_tz and block_config:
            from bot.utils.time_blocks import slot_to_discord_short

            slot_str = slot_to_discord_short(w["date"], w["block"], server_tz, block_config)
        else:
            slot_str = f"{w['date']} · {w['block'].capitalize()}"
        lines.append(f"{bar}  {count}  {slot_str}")
    return "\n".join(lines) if lines else "No windows meet threshold."
