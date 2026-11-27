"""Scheduled jobs: auto-purge stale availability, game reminders."""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler

if TYPE_CHECKING:
    from bot.bot import GameFinder

log = logging.getLogger(__name__)


def setup_scheduler(bot: GameFinder) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        _purge_stale_availability, "cron", hour=3, minute=0,
        args=[bot], id="purge_stale", replace_existing=True,
    )
    scheduler.add_job(
        _game_reminders, "cron", hour=9, minute=0,
        args=[bot], id="game_reminders", replace_existing=True,
    )
    scheduler.add_job(
        _game_day_pings, "cron", hour=10, minute=0,
        args=[bot], id="game_day_pings", replace_existing=True,
    )
    scheduler.add_job(
        _update_widgets, "interval", hours=1,
        args=[bot], id="update_widgets", replace_existing=True,
    )

    return scheduler


async def _purge_stale_availability(bot: GameFinder) -> None:
    """Remove availability entries older than each guild's forecast window."""
    from bot.db import queries

    for guild in bot.guilds:
        try:
            config = await queries.get_guild_config(bot.db, guild.id)
            if not config:
                continue
            cutoff = datetime.date.today() - datetime.timedelta(days=1)
            deleted = await queries.purge_stale_availability(
                bot.db, guild.id, cutoff.isoformat()
            )
            if deleted > 0:
                log.info("Purged %d stale availability entries for guild %s", deleted, guild.name)
        except Exception:
            log.exception("Failed to purge stale availability for guild %d", guild.id)


async def _game_reminders(bot: GameFinder) -> None:
    """Send 24h prep reminder to game creators."""
    from bot.db import queries

    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

    for guild in bot.guilds:
        try:
            games = await queries.list_games(bot.db, guild.id, status="open")
            full_games = await queries.list_games(bot.db, guild.id, status="full")
            all_games = games + full_games

            for game in all_games:
                if game["slot_date"] != tomorrow:
                    continue

                counts = await queries.get_rsvp_counts(bot.db, game["id"])
                going = counts.get("going", 0)
                maybe = counts.get("maybe", 0)
                cant = counts.get("not_going", 0)

                try:
                    creator = guild.get_member(game["creator_id"])
                    if not creator:
                        creator = await guild.fetch_member(game["creator_id"])
                    await creator.send(
                        f"\U0001f4cb **Prep reminder: {game['title']}** is tomorrow!\n\n"
                        f"✅ Going: {going}  |  \U0001f914 Maybe: {maybe}  |  ❌ Can't: {cant}\n"
                        f"{'You have enough players!' if going >= game['player_cap'] else 'Below player cap — check Maybe responses.'}"
                    )
                    log.info("Sent prep reminder for game #%d to %s", game["id"], creator)
                except Exception:
                    log.debug("Could not DM creator of game #%d", game["id"])
        except Exception:
            log.exception("Failed to send reminders for guild %d", guild.id)


async def _game_day_pings(bot: GameFinder) -> None:
    """Post session-day ping in scheduling channel for today's games."""
    from bot.db import queries

    today = datetime.date.today().isoformat()

    for guild in bot.guilds:
        try:
            config = await queries.get_guild_config(bot.db, guild.id)
            if not config:
                continue

            channel = None
            if config["scheduling_channel_id"]:
                channel = guild.get_channel(config["scheduling_channel_id"])
            if not channel:
                continue

            games = await queries.list_games(bot.db, guild.id, status="open")
            full_games = await queries.list_games(bot.db, guild.id, status="full")
            all_games = games + full_games

            for game in all_games:
                if game["slot_date"] != today:
                    continue

                rsvps = await queries.get_rsvps(bot.db, game["id"])
                going = [f"<@{r['user_id']}>" for r in rsvps if r["status"] == "going"]
                maybe = [f"<@{r['user_id']}>" for r in rsvps if r["status"] == "maybe"]

                parts = [f"\U0001f3b2 **{game['title']}** is today!"]
                if going:
                    parts.append(f"✅ Going: {' '.join(going[:15])}")
                if maybe:
                    parts.append(f"\U0001f914 Maybe — still in? {' '.join(maybe[:10])}")

                await channel.send("\n".join(parts))
                log.info("Posted day-of ping for game #%d", game["id"])
        except Exception:
            log.exception("Failed to send day pings for guild %d", guild.id)


async def _update_widgets(bot: GameFinder) -> None:
    """Update pinned stat widgets in all guilds."""
    from bot.db import queries
    import discord

    for guild in bot.guilds:
        try:
            config = await queries.get_guild_config(bot.db, guild.id)
            if not config or not config.get("widget_message_id"):
                continue

            channel = guild.get_channel(config["widget_channel_id"])
            if not channel:
                continue

            try:
                msg = await channel.fetch_message(config["widget_message_id"])
            except discord.NotFound:
                await queries.update_guild_config(
                    bot.db, guild.id, widget_message_id=None, widget_channel_id=None
                )
                continue

            admin_cog = bot.get_cog("AdminCog")
            if admin_cog:
                embed = await admin_cog._build_widget_embed(guild.id)
                await msg.edit(embed=embed)
                log.debug("Updated widget for guild %s", guild.name)
        except Exception:
            log.exception("Failed to update widget for guild %d", guild.id)
