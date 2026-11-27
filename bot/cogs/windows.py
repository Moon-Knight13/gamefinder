from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.db import queries
from bot.utils.formatting import format_heatmap, format_ranked_windows
from bot.utils.time_blocks import BLOCK_LABELS, BlockConfig, date_range, slot_to_discord_short

if TYPE_CHECKING:
    from bot.bot import GameFinder

log = logging.getLogger(__name__)


class WindowsCog(commands.Cog):
    def __init__(self, bot: GameFinder) -> None:
        self.bot = bot

    @app_commands.command(name="windows", description="See best windows for scheduling games")
    @app_commands.describe(
        min="Minimum players to show (overrides server default)",
        week="Specific week number (1-based)",
    )
    async def windows(
        self,
        interaction: discord.Interaction,
        min: int | None = None,
        week: int | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        config = await queries.get_guild_config(self.bot.db, interaction.guild_id)
        if not config:
            await queries.ensure_guild(self.bot.db, interaction.guild_id)
            config = await queries.get_guild_config(self.bot.db, interaction.guild_id)

        threshold = min if min is not None else config["threshold"]
        forecast = config["forecast_weeks"]

        if week is not None:
            start = datetime.date.today() + datetime.timedelta(weeks=week - 1)
            dates = date_range(start, weeks=1)
        else:
            start = datetime.date.today()
            dates = date_range(start, weeks=forecast)

        date_from = dates[0].isoformat()
        date_to = dates[-1].isoformat()

        counts = await queries.get_availability_counts(
            self.bot.db, interaction.guild_id, date_from, date_to
        )
        respondents = await queries.count_respondents(
            self.bot.db, interaction.guild_id, date_from, date_to
        )

        bc = BlockConfig(
            morning_start=config["morning_start"],
            morning_end=config["morning_end"],
            afternoon_start=config["afternoon_start"],
            afternoon_end=config["afternoon_end"],
            evening_start=config["evening_start"],
            evening_end=config["evening_end"],
        )
        server_tz = config["timezone"]

        ranked = format_ranked_windows(counts, threshold, server_tz, bc)
        heatmap = format_heatmap(counts, threshold)

        suggestion = ""
        viable = [w for w in counts if w["count"] >= threshold]
        if viable:
            best = viable[0]
            best_slot = slot_to_discord_short(best["date"], best["block"], server_tz, bc)
            suggestion = (
                f"\n\U0001f4a1 **Suggestion:** Best slot is {best_slot} "
                f"with {best['count']} players. Use `/game-create` to post there!"
            )
        elif counts:
            best = counts[0]
            best_slot = slot_to_discord_short(best["date"], best["block"], server_tz, bc)
            suggestion = (
                f"\n⚠️ No slots hit {threshold}+ players yet. "
                f"Best so far: {best_slot} with {best['count']}. "
                f"Try `/nudge` to boost responses!"
            )

        embed = discord.Embed(
            title=f"\U0001f4ca Best Windows ({threshold}+ players)",
            description=f"{respondents} responded{suggestion}\n\n**Ranked:**\n{ranked}",
            color=discord.Color.green(),
        )
        embed.add_field(name="Heatmap", value=f"```\n{heatmap}\n```", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="whofree", description="See who's free for a specific slot")
    @app_commands.describe(day="Date (YYYY-MM-DD)", block="morning, afternoon, or evening")
    @app_commands.choices(
        block=[
            app_commands.Choice(name="Morning", value="morning"),
            app_commands.Choice(name="Afternoon", value="afternoon"),
            app_commands.Choice(name="Evening", value="evening"),
        ]
    )
    async def whofree(
        self,
        interaction: discord.Interaction,
        day: str,
        block: app_commands.Choice[str],
    ) -> None:
        users = await queries.get_available_users(
            self.bot.db, interaction.guild_id, day, block.value
        )

        if not users:
            await interaction.response.send_message(
                f"Nobody marked available for {day} {BLOCK_LABELS[block.value]}.",
                ephemeral=True,
            )
            return

        mentions = []
        for u in users:
            member = interaction.guild.get_member(u["user_id"])
            if member:
                mentions.append(member.display_name)
            else:
                mentions.append(f"<@{u['user_id']}>")

        await interaction.response.send_message(
            f"**{day} · {BLOCK_LABELS[block.value]}** — {len(users)} available:\n"
            + ", ".join(mentions),
            ephemeral=True,
        )


async def setup(bot: GameFinder) -> None:
    await bot.add_cog(WindowsCog(bot))
