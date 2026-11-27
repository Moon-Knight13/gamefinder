from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.db import queries
from bot.utils.time_blocks import (
    BLOCK_LABELS, BLOCK_ORDER, BlockConfig, block_to_utc_range, utc_to_discord_timestamp,
)

if TYPE_CHECKING:
    from bot.bot import GameFinder

log = logging.getLogger(__name__)

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
CADENCE_LABELS = {"weekly": "Weekly", "biweekly": "Biweekly"}
MAX_SESSIONS = 52


def _ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{['th','st','nd','rd','th','th','th','th','th','th'][n % 10]}"


async def _get_config(db, guild_id: int) -> dict:
    config = await queries.get_guild_config(db, guild_id)
    if not config:
        await queries.ensure_guild(db, guild_id)
        config = await queries.get_guild_config(db, guild_id)
    return config


def _block_config(config: dict) -> BlockConfig:
    return BlockConfig(
        morning_start=config["morning_start"], morning_end=config["morning_end"],
        afternoon_start=config["afternoon_start"], afternoon_end=config["afternoon_end"],
        evening_start=config["evening_start"], evening_end=config["evening_end"],
    )


def _next_weekday(weekday: int, after: datetime.date | None = None) -> datetime.date:
    d = after or datetime.date.today()
    while d.weekday() != weekday:
        d += datetime.timedelta(days=1)
    return d


def _session_dates(start: datetime.date, weekday: int, cadence: str, count: int) -> list[datetime.date]:
    dates = []
    d = _next_weekday(weekday, start)
    step = 14 if cadence == "biweekly" else 7
    for _ in range(count):
        dates.append(d)
        d += datetime.timedelta(days=step)
    return dates


def _campaign_embed(campaign: dict, config: dict, roster_count: int) -> discord.Embed:
    bc = _block_config(config)
    server_tz = config["timezone"]
    day_name = DAY_NAMES[campaign["day_of_week"]]

    sample_date = _next_weekday(campaign["day_of_week"])
    start_dt, end_dt = block_to_utc_range(sample_date, campaign["block"], server_tz, bc)
    s_ts = utc_to_discord_timestamp(start_dt, "t")
    e_ts = utc_to_discord_timestamp(end_dt, "t")

    progress = campaign["sessions_completed"]
    total = campaign["session_count"]
    bar_len = 10
    filled = int((progress / total) * bar_len) if total > 0 else 0
    progress_bar = "\U0001f7e9" * filled + "⬜" * (bar_len - filled)

    dates = _session_dates(datetime.date.today(), campaign["day_of_week"],
                           campaign["cadence"], min(3, total - progress))
    upcoming = "\n".join(
        f"• {utc_to_discord_timestamp(block_to_utc_range(d, campaign['block'], server_tz, bc)[0], 'D')}"
        for d in dates
    )

    embed = discord.Embed(
        title=f"\U0001f3af {campaign['title']}",
        description=campaign["description"] or "",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="Schedule",
        value=f"{CADENCE_LABELS.get(campaign['cadence'], campaign['cadence'])} • "
              f"Every **{day_name}** {s_ts}–{e_ts}",
        inline=False,
    )
    embed.add_field(
        name="Progress",
        value=f"{progress_bar}  {progress}/{total} sessions",
        inline=True,
    )
    embed.add_field(
        name="Roster",
        value=f"{roster_count}/{campaign['player_max']} players",
        inline=True,
    )
    embed.add_field(name="Min Players", value=str(campaign["player_min"]), inline=True)
    if upcoming:
        embed.add_field(name="Next Sessions", value=upcoming, inline=False)
    embed.set_footer(text=f"Campaign #{campaign['id']}")
    return embed


class RosterView(discord.ui.View):
    """Join/leave campaign roster. Persistent."""

    def __init__(self, db=None) -> None:
        super().__init__(timeout=None)
        self.db = db

    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        log.exception("Roster error", exc_info=error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"Roster error: {error}", ephemeral=True)
            else:
                await interaction.response.send_message(f"Roster error: {error}", ephemeral=True)
        except discord.HTTPException:
            pass

    @discord.ui.button(label="Join Roster", style=discord.ButtonStyle.green,
                       custom_id="campaign:join", emoji="✅")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle(interaction, "join")

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.red,
                       custom_id="campaign:leave", emoji="\U0001f44b")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle(interaction, "leave")

    @discord.ui.button(label="Spectate", style=discord.ButtonStyle.grey,
                       custom_id="campaign:spectate", emoji="\U0001f440")
    async def spectate(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle(interaction, "spectate")

    async def _handle(self, interaction: discord.Interaction, action: str) -> None:
        if not self.db:
            self.db = interaction.client.db

        campaign_id = self._extract_id(interaction.message)
        if not campaign_id:
            await interaction.response.send_message("Could not find campaign.", ephemeral=True)
            return

        campaign = await queries.get_campaign(self.db, campaign_id, interaction.guild_id)
        if not campaign:
            await interaction.response.send_message("Campaign not found.", ephemeral=True)
            return

        if action == "join":
            roster = await queries.get_roster(self.db, campaign_id)
            if len(roster) >= campaign["player_max"]:
                await interaction.response.send_message(
                    f"Roster full ({campaign['player_max']}/{campaign['player_max']}). "
                    f"You can Spectate instead.", ephemeral=True
                )
                return
            await queries.add_to_roster(self.db, campaign_id, interaction.user.id)
            await interaction.response.send_message(
                f"✅ Joined **{campaign['title']}** roster!", ephemeral=True
            )
        elif action == "leave":
            await queries.remove_from_roster(self.db, campaign_id, interaction.user.id)
            await interaction.response.send_message(
                f"\U0001f44b Left **{campaign['title']}** roster.", ephemeral=True
            )
        elif action == "spectate":
            await interaction.response.send_message(
                f"\U0001f440 Watching **{campaign['title']}**. You'll see updates.", ephemeral=True
            )

        # Update embed with new roster count
        roster = await queries.get_roster(self.db, campaign_id)
        config = await _get_config(self.db, interaction.guild_id)
        embed = _campaign_embed(campaign, config, len(roster))
        try:
            await interaction.message.edit(embed=embed)
        except discord.HTTPException:
            pass

    def _extract_id(self, message: discord.Message | None) -> int | None:
        if not message or not message.embeds:
            return None
        embed = message.embeds[0]
        if embed.footer and embed.footer.text:
            import re
            match = re.search(r"#(\d+)", embed.footer.text)
            if match:
                return int(match.group(1))
        return None


class CampaignsCog(commands.Cog):
    def __init__(self, bot: GameFinder) -> None:
        self.bot = bot

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError,
    ) -> None:
        log.exception("Campaign command error", exc_info=error)
        msg = f"Error: {error}"[:200]
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except discord.HTTPException:
            pass

    @app_commands.command(name="campaign-create", description="Start a recurring campaign")
    @app_commands.describe(
        title="Campaign title (e.g. Curse of Strahd)",
        description="What players should know",
        day="Day of week for sessions",
        block="Time block",
        sessions="Number of sessions (1-52)",
        cadence="Weekly or biweekly",
        player_min="Minimum players needed (default 3)",
        player_max="Maximum roster size (default 6)",
    )
    @app_commands.choices(
        day=[app_commands.Choice(name=d, value=i) for i, d in enumerate(DAY_NAMES)],
        block=[
            app_commands.Choice(name="Morning (AM)", value="morning"),
            app_commands.Choice(name="Afternoon (MID)", value="afternoon"),
            app_commands.Choice(name="Evening (PM)", value="evening"),
        ],
        cadence=[
            app_commands.Choice(name="Weekly", value="weekly"),
            app_commands.Choice(name="Biweekly", value="biweekly"),
        ],
    )
    async def campaign_create(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        day: app_commands.Choice[int],
        block: app_commands.Choice[str],
        sessions: int,
        cadence: app_commands.Choice[str] = None,
        player_min: int = 3,
        player_max: int = 6,
    ) -> None:
        if not 1 <= sessions <= MAX_SESSIONS:
            await interaction.response.send_message(
                f"Sessions must be 1-{MAX_SESSIONS}.", ephemeral=True
            )
            return
        if player_min < 1 or player_max < player_min:
            await interaction.response.send_message("Invalid player range.", ephemeral=True)
            return

        await interaction.response.defer()

        cadence_val = cadence.value if cadence else "weekly"

        campaign_id = await queries.create_campaign(
            self.bot.db,
            guild_id=interaction.guild_id,
            creator_id=interaction.user.id,
            title=title,
            description=description,
            day_of_week=day.value,
            block=block.value,
            session_count=sessions,
            cadence=cadence_val,
            player_min=player_min,
            player_max=player_max,
        )

        # Add creator to roster
        await queries.add_to_roster(self.bot.db, campaign_id, interaction.user.id)

        config = await _get_config(self.bot.db, interaction.guild_id)
        campaign = await queries.get_campaign(self.bot.db, campaign_id, interaction.guild_id)
        embed = _campaign_embed(campaign, config, 1)
        embed.set_footer(text=f"Campaign #{campaign_id} · by {interaction.user.display_name}")

        # Post to scheduling channel
        post_channel = interaction.channel
        if config and config["scheduling_channel_id"]:
            ch = interaction.guild.get_channel(config["scheduling_channel_id"])
            if ch:
                post_channel = ch

        view = RosterView(self.bot.db)

        if post_channel == interaction.channel:
            msg = await interaction.followup.send(embed=embed, view=view, wait=True)
        else:
            msg = await post_channel.send(embed=embed, view=view)
            await interaction.followup.send(
                f"Campaign **{title}** posted in {post_channel.mention}!", ephemeral=True
            )

        await queries.update_campaign(
            self.bot.db, campaign_id, interaction.guild_id,
            message_id=msg.id, channel_id=msg.channel.id,
        )

        # Ping consistent players for this slot
        bc = _block_config(config)
        server_tz = config["timezone"]
        today = datetime.date.today()
        forecast_end = (today + datetime.timedelta(weeks=config["forecast_weeks"])).isoformat()

        consistent = await queries.get_consistent_players(
            self.bot.db, interaction.guild_id, today.isoformat(), forecast_end, min_weeks=3,
        )
        matching = [s for s in consistent
                    if s["weekday"] == day.value and s["block"] == block.value]

        if matching and matching[0]["players"]:
            player_ids = matching[0]["players"]
            mentions = [f"<@{uid}>" for uid in player_ids if uid != interaction.user.id]
            if mentions:
                await post_channel.send(
                    f"\U0001f3af **{title}** — {cadence_val} campaign!\n"
                    f"You're consistently free for this slot: {' '.join(mentions[:15])}\n"
                    f"Join the roster above if you're in!"
                )

    @app_commands.command(name="campaigns", description="List active campaigns")
    async def campaigns_list(self, interaction: discord.Interaction) -> None:
        campaigns = await queries.list_campaigns(self.bot.db, interaction.guild_id)
        if not campaigns:
            await interaction.response.send_message("No active campaigns.", ephemeral=True)
            return

        lines = []
        for c in campaigns:
            day_name = DAY_NAMES[c["day_of_week"]]
            roster = await queries.get_roster(self.bot.db, c["id"])
            progress = c["sessions_completed"]
            total = c["session_count"]
            lines.append(
                f"\U0001f3af **#{c['id']}** {c['title']} — "
                f"Every {day_name} {BLOCK_LABELS[c['block']]} • "
                f"{progress}/{total} sessions • {len(roster)} players"
            )

        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="campaign-status", description="View campaign details and roster")
    @app_commands.describe(campaign_id="Campaign ID number")
    async def campaign_status(self, interaction: discord.Interaction, campaign_id: int) -> None:
        campaign = await queries.get_campaign(self.bot.db, campaign_id, interaction.guild_id)
        if not campaign:
            await interaction.response.send_message("Campaign not found.", ephemeral=True)
            return

        roster = await queries.get_roster(self.bot.db, campaign_id)
        config = await _get_config(self.bot.db, interaction.guild_id)

        player_names = []
        for r in roster:
            member = interaction.guild.get_member(r["user_id"])
            player_names.append(member.display_name if member else f"Player #{r['user_id']}")

        embed = _campaign_embed(campaign, config, len(roster))
        if player_names:
            embed.add_field(
                name="Current Roster",
                value=", ".join(player_names),
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="campaign-end", description="End a campaign you created")
    @app_commands.describe(campaign_id="Campaign ID number")
    async def campaign_end(self, interaction: discord.Interaction, campaign_id: int) -> None:
        campaign = await queries.get_campaign(self.bot.db, campaign_id, interaction.guild_id)
        if not campaign:
            await interaction.response.send_message("Campaign not found.", ephemeral=True)
            return
        if campaign["creator_id"] != interaction.user.id:
            await interaction.response.send_message(
                "Only the creator can end this campaign.", ephemeral=True
            )
            return

        await queries.update_campaign(
            self.bot.db, campaign_id, interaction.guild_id, status="completed"
        )

        roster = await queries.get_roster(self.bot.db, campaign_id)
        if roster:
            config = await _get_config(self.bot.db, interaction.guild_id)
            post_channel = interaction.channel
            if config and config["scheduling_channel_id"]:
                ch = interaction.guild.get_channel(config["scheduling_channel_id"])
                if ch:
                    post_channel = ch

            mentions = " ".join(f"<@{r['user_id']}>" for r in roster[:15])
            completed = campaign["sessions_completed"]
            await post_channel.send(
                f"\U0001f3c1 **{campaign['title']}** has wrapped up! "
                f"{completed} sessions completed.\n{mentions}"
            )

        await interaction.response.send_message(
            f"Campaign #{campaign_id} ended.", ephemeral=True
        )

    @app_commands.command(name="campaign-pause", description="Pause/resume a campaign")
    @app_commands.describe(campaign_id="Campaign ID number")
    async def campaign_pause(self, interaction: discord.Interaction, campaign_id: int) -> None:
        campaign = await queries.get_campaign(self.bot.db, campaign_id, interaction.guild_id)
        if not campaign:
            await interaction.response.send_message("Campaign not found.", ephemeral=True)
            return
        if campaign["creator_id"] != interaction.user.id:
            await interaction.response.send_message(
                "Only the creator can pause/resume.", ephemeral=True
            )
            return

        new_status = "active" if campaign["status"] == "paused" else "paused"
        await queries.update_campaign(
            self.bot.db, campaign_id, interaction.guild_id, status=new_status
        )
        label = "resumed" if new_status == "active" else "paused"
        await interaction.response.send_message(
            f"Campaign #{campaign_id} {label}.", ephemeral=True
        )


async def setup(bot: GameFinder) -> None:
    await bot.add_cog(CampaignsCog(bot))
