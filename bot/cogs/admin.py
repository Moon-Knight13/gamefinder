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

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError,
    ) -> None:
        log.exception("Admin command error", exc_info=error)
        msg = f"Error: {error}"[:200]
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except discord.HTTPException:
            pass

    @app_commands.command(name="setup", description="Configure GameFinder for this server")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        threshold="Minimum players to highlight a window (default 4)",
        forecast_weeks="How many weeks ahead to show (1-12, default 3)",
        timezone="Server timezone, e.g. America/New_York",
        scheduling_channel="Channel for game posts and notifications",
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
        scheduling_channel: discord.TextChannel | None = None,
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

        if forecast_weeks is not None and not 1 <= forecast_weeks <= 12:
            await interaction.response.send_message("forecast_weeks must be 1-12.", ephemeral=True)
            return

        kwargs = {}
        if threshold is not None:
            kwargs["threshold"] = threshold
        if forecast_weeks is not None:
            kwargs["forecast_weeks"] = forecast_weeks
        if timezone is not None:
            kwargs["timezone"] = timezone
        if scheduling_channel is not None:
            kwargs["scheduling_channel_id"] = scheduling_channel.id
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
        channel_str = f"<#{config['scheduling_channel_id']}>" if config["scheduling_channel_id"] else "Any channel"
        await interaction.response.send_message(
            f"Server configured:\n"
            f"- Scheduling channel: {channel_str}\n"
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

    @app_commands.command(name="simulate-rsvp", description="[Dev] Simulate mock player RSVPs on a game")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        game_id="Game ID to RSVP on",
        going="Number of Going RSVPs",
        maybe="Number of Maybe RSVPs",
        spectators="Number of Spectators",
    )
    async def simulate_rsvp(
        self,
        interaction: discord.Interaction,
        game_id: int,
        going: int = 4,
        maybe: int = 1,
        spectators: int = 1,
    ) -> None:
        if not self.bot.config.dev_mode:
            await interaction.response.send_message("Dev commands disabled. Set DEV_MODE=1.", ephemeral=True)
            return
        game = await queries.get_game(self.bot.db, game_id, interaction.guild_id)
        if not game:
            await interaction.response.send_message("Game not found.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        mock_uid = 900001
        results = {"going": 0, "maybe": 0, "spectator": 0}
        for _ in range(going):
            await queries.upsert_rsvp(self.bot.db, game_id, mock_uid, "going")
            results["going"] += 1
            mock_uid += 1
        for _ in range(maybe):
            await queries.upsert_rsvp(self.bot.db, game_id, mock_uid, "maybe")
            results["maybe"] += 1
            mock_uid += 1
        for _ in range(spectators):
            await queries.upsert_rsvp(self.bot.db, game_id, mock_uid, "spectator")
            results["spectator"] += 1
            mock_uid += 1

        counts = await queries.get_rsvp_counts(self.bot.db, game_id)
        total_going = counts.get("going", 0)

        # Update embed if we have message location
        if game.get("message_id") and game.get("channel_id"):
            try:
                channel = interaction.guild.get_channel(game["channel_id"])
                if channel:
                    msg = await channel.fetch_message(game["message_id"])
                    if msg.embeds:
                        from bot.cogs.games import _format_rsvp_field
                        embed = msg.embeds[0].copy()
                        for i, field in enumerate(embed.fields):
                            if field.name == "RSVPs":
                                embed.set_field_at(i, name="RSVPs",
                                                   value=_format_rsvp_field(counts), inline=False)
                                break
                        await msg.edit(embed=embed)
            except Exception as e:
                log.warning("Failed to update embed: %s", e)

        # Check quorum + create Discord event
        quorum_msg = ""
        if total_going >= game["player_cap"] and game["status"] == "open":
            await queries.update_game_status(self.bot.db, game_id, interaction.guild_id, "full")
            from bot.cogs.games import create_game_event
            event = await create_game_event(
                self.bot, interaction.guild, game, game_id, interaction.guild_id
            )
            quorum_msg = f"\n\U0001f389 **Quorum reached!** ({total_going}/{game['player_cap']})"
            if event:
                quorum_msg += " — Discord Event created!"

                config = await queries.get_guild_config(self.bot.db, interaction.guild_id)
                post_channel = interaction.channel
                if config and config["scheduling_channel_id"]:
                    ch = interaction.guild.get_channel(config["scheduling_channel_id"])
                    if ch:
                        post_channel = ch

                await post_channel.send(
                    f"\U0001f389 **{game['title']}** reached quorum! "
                    f"({total_going}/{game['player_cap']} Going) — Event created!"
                )
                # DM real Going players with event link
                rsvps = await queries.get_rsvps(self.bot.db, game_id)
                for r in rsvps:
                    if r["status"] == "going" and r["user_id"] < 900000:
                        try:
                            member = interaction.guild.get_member(r["user_id"])
                            if not member:
                                member = await interaction.guild.fetch_member(r["user_id"])
                            await member.send(
                                f"\U0001f3b2 **{game['title']}** is confirmed!\n\n"
                                f"Click to join the Discord Event and get reminders:\n"
                                f"{event.url}"
                            )
                        except (Exception,):
                            log.debug("Could not DM user %d", r["user_id"])
            else:
                quorum_msg += " — Event creation failed (check bot permissions)"

        await interaction.followup.send(
            f"Simulated RSVPs on game #{game_id}:\n"
            f"✅ {results['going']} Going | \U0001f914 {results['maybe']} Maybe | "
            f"\U0001f440 {results['spectator']} Spectator\n"
            f"Total Going: {total_going}/{game['player_cap']}{quorum_msg}",
            ephemeral=True,
        )

    @app_commands.command(name="simulate-roster", description="[Dev] Simulate mock players joining a campaign roster")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        campaign_id="Campaign ID",
        count="Number of players to add",
    )
    async def simulate_roster(
        self,
        interaction: discord.Interaction,
        campaign_id: int,
        count: int = 4,
    ) -> None:
        if not self.bot.config.dev_mode:
            await interaction.response.send_message("Dev commands disabled. Set DEV_MODE=1.", ephemeral=True)
            return
        campaign = await queries.get_campaign(self.bot.db, campaign_id, interaction.guild_id)
        if not campaign:
            await interaction.response.send_message("Campaign not found.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        mock_uid = 900101
        added = 0
        for _ in range(count):
            await queries.add_to_roster(self.bot.db, campaign_id, mock_uid)
            added += 1
            mock_uid += 1

        roster = await queries.get_roster(self.bot.db, campaign_id)

        # Update embed
        if campaign.get("message_id") and campaign.get("channel_id"):
            try:
                channel = interaction.guild.get_channel(campaign["channel_id"])
                if channel:
                    msg = await channel.fetch_message(campaign["message_id"])
                    if msg.embeds:
                        config = await queries.get_guild_config(self.bot.db, interaction.guild_id)
                        from bot.cogs.campaigns import _campaign_embed
                        embed = _campaign_embed(campaign, config, len(roster))
                        await msg.edit(embed=embed)
            except Exception as e:
                log.warning("Failed to update campaign embed: %s", e)

        await interaction.followup.send(
            f"Added {added} mock players to campaign #{campaign_id}.\n"
            f"Roster: {len(roster)}/{campaign['player_max']}",
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        log.info("Removed from guild %s (%d) — scheduling data deletion in 30 days", guild.name, guild.id)
        if hasattr(self.bot, "_scheduler"):
            from apscheduler.triggers.date import DateTrigger
            run_date = datetime.datetime.now() + datetime.timedelta(days=30)
            self.bot._scheduler.add_job(
                self._delete_guild_data, DateTrigger(run_date=run_date),
                args=[guild.id], id=f"guild_delete_{guild.id}",
                replace_existing=True,
            )

    async def _delete_guild_data(self, guild_id: int) -> None:
        log.info("Executing scheduled data deletion for guild %d", guild_id)
        await queries.delete_guild_data(self.bot.db, guild_id)


async def setup(bot: GameFinder) -> None:
    await bot.add_cog(AdminCog(bot))
