from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING
from zoneinfo import available_timezones

import discord
from discord import app_commands
from discord.ext import commands

from bot.db import queries
from bot.utils.time_blocks import date_range

if TYPE_CHECKING:
    from bot.bot import GameFinder

log = logging.getLogger(__name__)


class ConfirmDeleteView(discord.ui.View):
    def __init__(self, db, user_id: int) -> None:
        super().__init__(timeout=60)
        self.db = db
        self.user_id = user_id

    @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.red, emoji="⚠️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Not your request.", ephemeral=True)
            return
        await queries.delete_user_data(self.db, self.user_id)
        await interaction.response.edit_message(
            content="All your data has been deleted.", view=None
        )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled.", view=None)
        self.stop()


class AdminCog(commands.Cog):
    def __init__(self, bot: GameFinder) -> None:
        self.bot = bot

    @app_commands.command(name="setup", description="Configure GameFinder for this server")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        threshold="Minimum players to highlight a window (default 4)",
        forecast_weeks="How many weeks ahead to show (1-6, default 3)",
        timezone="Server timezone, e.g. America/New_York",
        morning_start="Morning block start hour (0-23, default 9)",
        morning_end="Morning block end hour (default 12)",
        afternoon_start="Afternoon start (default 12)",
        afternoon_end="Afternoon end (default 17)",
        evening_start="Evening start (default 17)",
        evening_end="Evening end (default 22)",
    )
    async def setup(
        self,
        interaction: discord.Interaction,
        threshold: int | None = None,
        forecast_weeks: int | None = None,
        timezone: str | None = None,
        morning_start: int | None = None,
        morning_end: int | None = None,
        afternoon_start: int | None = None,
        afternoon_end: int | None = None,
        evening_start: int | None = None,
        evening_end: int | None = None,
    ) -> None:
        await queries.ensure_guild(self.bot.db, interaction.guild_id)

        if timezone and timezone not in available_timezones():
            await interaction.response.send_message(
                f"Unknown timezone `{timezone}`.", ephemeral=True
            )
            return

        if forecast_weeks is not None and not 1 <= forecast_weeks <= 6:
            await interaction.response.send_message("forecast_weeks must be 1-6.", ephemeral=True)
            return

        kwargs = {}
        if threshold is not None:
            kwargs["threshold"] = threshold
        if forecast_weeks is not None:
            kwargs["forecast_weeks"] = forecast_weeks
        if timezone is not None:
            kwargs["timezone"] = timezone
        if morning_start is not None:
            kwargs["morning_start"] = morning_start
        if morning_end is not None:
            kwargs["morning_end"] = morning_end
        if afternoon_start is not None:
            kwargs["afternoon_start"] = afternoon_start
        if afternoon_end is not None:
            kwargs["afternoon_end"] = afternoon_end
        if evening_start is not None:
            kwargs["evening_start"] = evening_start
        if evening_end is not None:
            kwargs["evening_end"] = evening_end

        if kwargs:
            await queries.update_guild_config(self.bot.db, interaction.guild_id, **kwargs)

        config = await queries.get_guild_config(self.bot.db, interaction.guild_id)
        await interaction.response.send_message(
            f"Server configured:\n"
            f"- Threshold: {config['threshold']}\n"
            f"- Forecast: {config['forecast_weeks']} weeks\n"
            f"- Timezone: {config['timezone']}\n"
            f"- Morning: {config['morning_start']:02d}:00–{config['morning_end']:02d}:00\n"
            f"- Afternoon: {config['afternoon_start']:02d}:00–{config['afternoon_end']:02d}:00\n"
            f"- Evening: {config['evening_start']:02d}:00–{config['evening_end']:02d}:00",
            ephemeral=True,
        )

    @app_commands.command(name="nudge", description="Prompt members to submit availability")
    @app_commands.default_permissions(manage_guild=True)
    async def nudge(self, interaction: discord.Interaction) -> None:
        config = await queries.get_guild_config(self.bot.db, interaction.guild_id)
        if not config:
            await queries.ensure_guild(self.bot.db, interaction.guild_id)
            config = await queries.get_guild_config(self.bot.db, interaction.guild_id)

        start = datetime.date.today()
        dates = date_range(start, weeks=config["forecast_weeks"])
        date_from = dates[0].isoformat()
        date_to = dates[-1].isoformat()

        respondents = await queries.count_respondents(
            self.bot.db, interaction.guild_id, date_from, date_to
        )

        await interaction.response.send_message(
            f"\U0001f3b2 **Time to mark your availability!**\n"
            f"{respondents} members have responded so far. "
            f"Run `/available` to let DMs know when you're free!",
        )

    @app_commands.command(name="stats", description="View server scheduling stats")
    async def stats(self, interaction: discord.Interaction) -> None:
        config = await queries.get_guild_config(self.bot.db, interaction.guild_id)
        if not config:
            await queries.ensure_guild(self.bot.db, interaction.guild_id)
            config = await queries.get_guild_config(self.bot.db, interaction.guild_id)

        start = datetime.date.today()
        dates = date_range(start, weeks=config["forecast_weeks"])
        date_from = dates[0].isoformat()
        date_to = dates[-1].isoformat()

        stats = await queries.get_guild_stats(self.bot.db, interaction.guild_id, date_from, date_to)

        top_lines = []
        for w in stats["top_windows"]:
            top_lines.append(f"{w['count']} players — {w['date']} {w['block'].capitalize()}")

        embed = discord.Embed(
            title="\U0001f4ca Server Stats",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Respondents", value=str(stats["respondents"]), inline=True)
        embed.add_field(name="Games This Period", value=str(stats["games_count"]), inline=True)
        if top_lines:
            embed.add_field(name="Top Windows", value="\n".join(top_lines), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="data-delete", description="Delete all your data from this bot")
    async def data_delete(self, interaction: discord.Interaction) -> None:
        view = ConfirmDeleteView(self.bot.db, interaction.user.id)
        await interaction.response.send_message(
            "**Warning:** This will permanently delete all your data "
            "(availability, RSVPs, timezone). This cannot be undone.",
            view=view,
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        log.info("Removed from guild %s (%d) — scheduling data deletion", guild.name, guild.id)
        # In production, schedule via APScheduler for 30 days out.
        # For now, log the event. The purge job handles stale data.


async def setup(bot: GameFinder) -> None:
    await bot.add_cog(AdminCog(bot))
