from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.db import queries
from bot.utils.formatting import (
    format_bar, get_guild_config, make_block_config, ordinal, validate_date,
)
from bot.utils.time_blocks import (
    BLOCK_LABELS, BLOCK_ORDER, BlockConfig, block_to_utc_range,
    date_range, utc_to_discord_timestamp,
)

if TYPE_CHECKING:
    from bot.bot import GameFinder

log = logging.getLogger(__name__)

SLOT_EMOJI = {"morning": "\U0001f305", "afternoon": "☀️", "evening": "\U0001f319"}
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class WindowsView(discord.ui.LayoutView):
    """Top viable windows with Post Game buttons."""

    def __init__(self, bot, guild_id: int, threshold: int, windows: list[dict],
                 respondents: int, config: dict) -> None:
        super().__init__(timeout=300)
        self.bot_ref = bot
        self.guild_id = guild_id
        self.threshold = threshold
        self.windows = windows
        self.respondents = respondents
        self.config = config

    async def build(self) -> None:
        self.clear_items()

        bc = BlockConfig(
            morning_start=self.config["morning_start"], morning_end=self.config["morning_end"],
            afternoon_start=self.config["afternoon_start"], afternoon_end=self.config["afternoon_end"],
            evening_start=self.config["evening_start"], evening_end=self.config["evening_end"],
        )
        server_tz = self.config["timezone"]

        viable = [w for w in self.windows if w["count"] >= self.threshold]
        top = viable[:5]

        if not top:
            best = self.windows[:3] if self.windows else []
            if best:
                lines = []
                for w in best:
                    d = datetime.date.fromisoformat(w["date"])
                    start_dt, _ = block_to_utc_range(d, w["block"], server_tz, bc)
                    ts = utc_to_discord_timestamp(start_dt, "D")
                    time_ts = utc_to_discord_timestamp(start_dt, "t")
                    lines.append(
                        f"{SLOT_EMOJI[w['block']]} **{w['count']}** available • "
                        f"{d.strftime('%a')} {ordinal(d.day)} {time_ts}"
                    )
                body = "\n".join(lines)
                msg = (
                    f"\U0001f4ca **Availability Windows**\n"
                    f"{self.respondents} responded • threshold: {self.threshold}+\n\n"
                    f"⚠️ No slots hit {self.threshold}+ yet. Best so far:\n{body}\n\n"
                    f"Try `/nudge` to get more responses!"
                )
            else:
                msg = (
                    f"\U0001f4ca **Availability Windows**\n"
                    f"No data yet. Players need to run `/available`!"
                )

            c = discord.ui.Container(
                discord.ui.TextDisplay(msg),
                accent_colour=discord.Colour.orange(),
            )
            self.add_item(c)
            return

        # Build sections for top viable windows
        sections = []
        for w in top:
            d = datetime.date.fromisoformat(w["date"])
            start_dt, end_dt = block_to_utc_range(d, w["block"], server_tz, bc)
            s_ts = utc_to_discord_timestamp(start_dt, "F")
            e_ts = utc_to_discord_timestamp(end_dt, "t")
            bar = format_bar(w["count"], top[0]["count"])

            post_btn = discord.ui.Button(
                label="\U0001f3b2 Post Game",
                style=discord.ButtonStyle.green,
                custom_id=f"win:post:{self.guild_id}:{w['date']}:{w['block']}",
            )

            section = discord.ui.Section(
                discord.ui.TextDisplay(
                    f"{SLOT_EMOJI[w['block']]} **{d.strftime('%A')} {ordinal(d.day)}**\n"
                    f"{s_ts} to {e_ts}\n"
                    f"**{w['count']} players** could fill your table\n"
                    f"{bar}"
                ),
                accessory=post_btn,
            )
            sections.append((section, w["date"], w["block"]))

        c = discord.ui.Container(
            discord.ui.TextDisplay(
                f"\U0001f3b2 **Oneshot Windows** ({self.threshold}+)\n"
                f"{self.respondents} responded • "
                f"*Best dates for a one-off game — match to your schedule*"
            ),
            discord.ui.Separator(),
            *[s[0] for s in sections],
            accent_colour=discord.Colour.green(),
        )
        self.add_item(c)

        # Attach callbacks
        for section, date_str, block in sections:
            section.accessory.callback = self._make_post_game(date_str, block)

    def _make_post_game(self, date_str: str, block: str):
        async def callback(interaction: discord.Interaction) -> None:
            d = datetime.date.fromisoformat(date_str)
            day_name = d.strftime("%A")
            modal = GamePostModal(
                self.bot_ref, interaction.guild_id, date_str, block,
                title=f"\U0001f3b2 Post Game — {day_name} {ordinal(d.day)} {BLOCK_LABELS[block]}",
            )
            await interaction.response.send_modal(modal)
        return callback


class GamePostModal(discord.ui.Modal):
    """Quick game creation modal triggered from /windows."""

    game_title = discord.ui.TextInput(
        label="Game Title",
        placeholder="e.g. Lost Mine of Phandelver",
        max_length=100,
    )
    description = discord.ui.TextInput(
        label="Description",
        placeholder="System, tone, what players should expect...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False,
    )
    player_cap = discord.ui.TextInput(
        label="Player Cap",
        placeholder="5",
        default="5",
        max_length=2,
    )

    def __init__(self, bot, guild_id: int, date_str: str, block: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.bot_ref = bot
        self.guild_id = guild_id
        self.date_str = date_str
        self.block = block

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            cap = int(self.player_cap.value)
        except ValueError:
            cap = 5

        await interaction.response.defer(ephemeral=True)

        try:
            game_id = await queries.create_game(
                self.bot_ref.db,
                guild_id=interaction.guild_id,
                creator_id=interaction.user.id,
                title=self.game_title.value,
                description=self.description.value or "",
                slot_date=self.date_str,
                slot_block=self.block,
                player_cap=cap,
            )

            config = await queries.get_guild_config(self.bot_ref.db, interaction.guild_id)
            if not config:
                await queries.ensure_guild(self.bot_ref.db, interaction.guild_id)
                config = await queries.get_guild_config(self.bot_ref.db, interaction.guild_id)

            bc = BlockConfig(
                morning_start=config["morning_start"], morning_end=config["morning_end"],
                afternoon_start=config["afternoon_start"], afternoon_end=config["afternoon_end"],
                evening_start=config["evening_start"], evening_end=config["evening_end"],
            )
            from bot.utils.time_blocks import slot_to_discord_time
            when_str = slot_to_discord_time(self.date_str, self.block, config["timezone"], bc)

            embed = discord.Embed(
                title=f"\U0001f3b2 {self.game_title.value}",
                description=self.description.value or "",
                color=discord.Color.blue(),
            )
            embed.add_field(name="When", value=when_str, inline=False)
            embed.add_field(name="Player Cap", value=str(cap), inline=True)
            embed.add_field(name="Status", value="\U0001f7e2 Open", inline=True)

            from bot.cogs.games import RSVPView, _format_rsvp_field
            embed.add_field(name="RSVPs", value=_format_rsvp_field({}), inline=False)
            embed.set_footer(text=f"Game #{game_id} · by {interaction.user.display_name}")

            post_channel = None
            if config and config["scheduling_channel_id"] and interaction.guild:
                post_channel = interaction.guild.get_channel(config["scheduling_channel_id"])
            if not post_channel:
                post_channel = interaction.channel

            view = RSVPView(self.bot_ref.db)
            msg = await post_channel.send(embed=embed, view=view)

            await queries.set_game_message(
                self.bot_ref.db, game_id, interaction.guild_id, msg.id, msg.channel.id
            )

            await interaction.followup.send(
                f"✅ **{self.game_title.value}** posted in {post_channel.mention}!"
            )

            available_users = await queries.get_available_users(
                self.bot_ref.db, interaction.guild_id, self.date_str, self.block
            )
            if available_users:
                mentions = [f"<@{u['user_id']}>" for u in available_users]
                for i in range(0, len(mentions), 15):
                    batch = mentions[i:i + 15]
                    await post_channel.send(
                        f"\U0001f3b2 **{self.game_title.value}** posted for this window!\n"
                        f"You marked this slot as available: {' '.join(batch)}\n"
                        f"RSVP above — open to everyone!"
                    )
        except Exception as e:
            log.exception("Failed to create game from modal")
            try:
                await interaction.followup.send(f"Error creating game: {e}", ephemeral=True)
            except Exception:
                pass




class CombinedWindowsView(discord.ui.LayoutView):
    """Oneshot windows + campaign-viable slots in one view."""

    def __init__(self, bot, guild_id: int, threshold: int, windows: list[dict],
                 consistent: list[dict], respondents: int, config: dict) -> None:
        super().__init__(timeout=300)
        self.bot_ref = bot
        self.guild_id = guild_id
        self.threshold = threshold
        self.windows = windows
        self.consistent = consistent
        self.respondents = respondents
        self.config = config

    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        log.exception("Windows error", exc_info=error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"Error: {error}", ephemeral=True)
            else:
                await interaction.response.send_message(f"Error: {error}", ephemeral=True)
        except discord.HTTPException:
            pass

    async def build(self) -> None:
        self.clear_items()

        bc = BlockConfig(
            morning_start=self.config["morning_start"], morning_end=self.config["morning_end"],
            afternoon_start=self.config["afternoon_start"], afternoon_end=self.config["afternoon_end"],
            evening_start=self.config["evening_start"], evening_end=self.config["evening_end"],
        )
        server_tz = self.config["timezone"]
        today = datetime.date.today()

        # --- Oneshot section ---
        viable = [w for w in self.windows if w["count"] >= self.threshold]
        top_oneshot = viable[:3]

        if top_oneshot:
            sections = []
            for w in top_oneshot:
                d = datetime.date.fromisoformat(w["date"])
                start_dt, end_dt = block_to_utc_range(d, w["block"], server_tz, bc)
                s_ts = utc_to_discord_timestamp(start_dt, "F")
                e_ts = utc_to_discord_timestamp(end_dt, "t")
                bar = format_bar(w["count"], top_oneshot[0]["count"])

                post_btn = discord.ui.Button(
                    label="\U0001f3b2 Post Game",
                    style=discord.ButtonStyle.green,
                    custom_id=f"win:post:{self.guild_id}:{w['date']}:{w['block']}",
                )

                section = discord.ui.Section(
                    discord.ui.TextDisplay(
                        f"{SLOT_EMOJI[w['block']]} **{d.strftime('%A')} {ordinal(d.day)}**\n"
                        f"{s_ts} to {e_ts}\n"
                        f"**{w['count']} players** could fill your table\n"
                        f"{bar}"
                    ),
                    accessory=post_btn,
                )
                sections.append((section, w["date"], w["block"]))

            oneshot_container = discord.ui.Container(
                discord.ui.TextDisplay(
                    f"\U0001f3b2 **Oneshot Windows** ({self.threshold}+)\n"
                    f"{self.respondents} responded • "
                    f"*Best dates for a one-off game — match to your schedule*"
                ),
                discord.ui.Separator(),
                *[s[0] for s in sections],
                accent_colour=discord.Colour.green(),
            )
            self.add_item(oneshot_container)

            for section, date_str, block in sections:
                section.accessory.callback = self._make_post_game(date_str, block)
        else:
            # No viable oneshot windows
            best = self.windows[:2] if self.windows else []
            lines = ""
            if best:
                parts = []
                for w in best:
                    d = datetime.date.fromisoformat(w["date"])
                    parts.append(
                        f"{SLOT_EMOJI[w['block']]} {d.strftime('%a')} {ordinal(d.day)} — {w['count']} available"
                    )
                lines = "\nBest so far: " + " • ".join(parts)

            oneshot_container = discord.ui.Container(
                discord.ui.TextDisplay(
                    f"\U0001f3b2 **Oneshot Windows** ({self.threshold}+)\n"
                    f"{self.respondents} responded\n\n"
                    f"⚠️ No slots hit {self.threshold}+ yet.{lines}\n"
                    f"Try `/nudge` to get more responses!"
                ),
                accent_colour=discord.Colour.orange(),
            )
            self.add_item(oneshot_container)

        # --- Campaign section ---
        viable_campaign = [s for s in self.consistent if s["consistent_count"] >= self.threshold]
        top_campaign = viable_campaign[:3]

        if top_campaign:
            cam_sections = []
            for s in top_campaign:
                day_name = DAY_NAMES[s["weekday"]]
                bar = format_bar(s["consistent_count"], top_campaign[0]["consistent_count"])

                sample_date = today
                target_wd = s["weekday"]
                while sample_date.isoweekday() % 7 != target_wd:
                    sample_date += datetime.timedelta(days=1)

                start_dt, end_dt = block_to_utc_range(sample_date, s["block"], server_tz, bc)
                time_s = utc_to_discord_timestamp(start_dt, "t")
                time_e = utc_to_discord_timestamp(end_dt, "t")

                cam_btn = discord.ui.Button(
                    label="\U0001f3af Details",
                    style=discord.ButtonStyle.blurple,
                    custom_id=f"cwin:{self.guild_id}:{s['weekday']}:{s['block']}",
                )

                cam_section = discord.ui.Section(
                    discord.ui.TextDisplay(
                        f"{SLOT_EMOJI[s['block']]} **Every {day_name}** {time_s}–{time_e}\n"
                        f"**{s['consistent_count']}** consistent across {s['total_weeks']} weeks\n"
                        f"{bar}"
                    ),
                    accessory=cam_btn,
                )
                cam_sections.append((cam_section, s))

            campaign_container = discord.ui.Container(
                discord.ui.TextDisplay(
                    f"\U0001f3af **Campaign-Viable Slots**\n"
                    f"*Same players free every week — reliable for recurring games*"
                ),
                discord.ui.Separator(),
                *[s[0] for s in cam_sections],
                accent_colour=discord.Colour.blue(),
            )
            self.add_item(campaign_container)

            for cam_section, slot_data in cam_sections:
                cam_section.accessory.callback = self._make_campaign_info(slot_data)
        else:
            campaign_container = discord.ui.Container(
                discord.ui.TextDisplay(
                    f"\U0001f3af **Campaign-Viable Slots**\n"
                    f"No weekly slots with {self.threshold}+ consistent players yet.\n"
                    f"Need more recurring availability data."
                ),
                accent_colour=discord.Colour.greyple(),
            )
            self.add_item(campaign_container)

    def _make_post_game(self, date_str: str, block: str):
        async def callback(interaction: discord.Interaction) -> None:
            d = datetime.date.fromisoformat(date_str)
            day_name = d.strftime("%A")
            modal = GamePostModal(
                self.bot_ref, interaction.guild_id, date_str, block,
                title=f"\U0001f3b2 Post Game — {day_name} {ordinal(d.day)} {BLOCK_LABELS[block]}",
            )
            await interaction.response.send_modal(modal)
        return callback

    def _make_campaign_info(self, slot: dict):
        async def callback(interaction: discord.Interaction) -> None:
            day_name = DAY_NAMES[slot["weekday"]]

            modal = CampaignPostModal(
                self.bot_ref, interaction.guild_id, slot["weekday"], slot["block"],
                slot["consistent_count"],
                title=f"\U0001f3af Campaign — Every {day_name} {BLOCK_LABELS[slot['block']]}",
            )
            await interaction.response.send_modal(modal)
        return callback


class CampaignPostModal(discord.ui.Modal):
    """Quick campaign creation from /windows."""

    campaign_title = discord.ui.TextInput(
        label="Campaign Title",
        placeholder="e.g. Curse of Strahd",
        max_length=100,
    )
    description = discord.ui.TextInput(
        label="Description",
        placeholder="System, setting, what to expect...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False,
    )
    sessions = discord.ui.TextInput(
        label="Number of Sessions (1-52)",
        placeholder="8",
        default="8",
        max_length=2,
    )
    player_max = discord.ui.TextInput(
        label="Max Players",
        placeholder="6",
        default="6",
        max_length=2,
    )

    def __init__(self, bot, guild_id: int, weekday: int, block: str,
                 consistent_count: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self.bot_ref = bot
        self.guild_id = guild_id
        self.weekday = weekday
        self.block = block
        self.consistent_count = consistent_count

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            session_count = max(1, min(52, int(self.sessions.value)))
        except ValueError:
            session_count = 8
        try:
            max_players = max(2, int(self.player_max.value))
        except ValueError:
            max_players = 6

        campaign_id = await queries.create_campaign(
            self.bot_ref.db,
            guild_id=interaction.guild_id,
            creator_id=interaction.user.id,
            title=self.campaign_title.value,
            description=self.description.value or "",
            day_of_week=self.weekday,
            block=self.block,
            session_count=session_count,
            player_min=3,
            player_max=max_players,
        )

        await queries.add_to_roster(self.bot_ref.db, campaign_id, interaction.user.id)

        config = await queries.get_guild_config(self.bot_ref.db, interaction.guild_id)
        if not config:
            await queries.ensure_guild(self.bot_ref.db, interaction.guild_id)
            config = await queries.get_guild_config(self.bot_ref.db, interaction.guild_id)

        campaign = await queries.get_campaign(self.bot_ref.db, campaign_id, interaction.guild_id)

        from bot.cogs.campaigns import _campaign_embed, RosterView, _block_config
        embed = _campaign_embed(campaign, config, 1)
        embed.set_footer(text=f"Campaign #{campaign_id} · by {interaction.user.display_name}")

        await interaction.response.defer()

        post_channel = interaction.channel
        if config and config["scheduling_channel_id"]:
            ch = interaction.guild.get_channel(config["scheduling_channel_id"])
            if ch:
                post_channel = ch

        view = RosterView(self.bot_ref.db)
        if post_channel == interaction.channel:
            msg = await interaction.followup.send(embed=embed, view=view, wait=True)
        else:
            msg = await post_channel.send(embed=embed, view=view)
            await interaction.followup.send(
                f"Campaign **{self.campaign_title.value}** posted in {post_channel.mention}!",
                ephemeral=True,
            )

        await queries.update_campaign(
            self.bot_ref.db, campaign_id, interaction.guild_id,
            message_id=msg.id, channel_id=msg.channel.id,
        )

        # Ping consistent players
        consistent = await queries.get_consistent_players(
            self.bot_ref.db, interaction.guild_id,
            datetime.date.today().isoformat(),
            (datetime.date.today() + datetime.timedelta(weeks=6)).isoformat(),
            min_weeks=3,
        )
        # Map Python weekday to SQL weekday for matching
        matching = [s for s in consistent
                    if s["weekday"] == self.weekday and s["block"] == self.block]
        if matching and matching[0]["players"]:
            mentions = [f"<@{uid}>" for uid in matching[0]["players"]
                        if uid != interaction.user.id]
            if mentions:
                await post_channel.send(
                    f"\U0001f3af **{self.campaign_title.value}** — {session_count} session campaign!\n"
                    f"You're consistently free for this slot: {' '.join(mentions[:15])}\n"
                    f"Join the roster above if you're in!"
                )


class CampaignWindowsView(discord.ui.LayoutView):
    """Campaign-viable slots: same players across 3+ weeks."""

    def __init__(self, bot, guild_id: int, threshold: int, consistent: list[dict],
                 respondents: int, config: dict) -> None:
        super().__init__(timeout=300)
        self.bot_ref = bot
        self.guild_id = guild_id
        self.threshold = threshold
        self.consistent = consistent
        self.respondents = respondents
        self.config = config

    async def build(self) -> None:
        self.clear_items()

        bc = BlockConfig(
            morning_start=self.config["morning_start"], morning_end=self.config["morning_end"],
            afternoon_start=self.config["afternoon_start"], afternoon_end=self.config["afternoon_end"],
            evening_start=self.config["evening_start"], evening_end=self.config["evening_end"],
        )
        server_tz = self.config["timezone"]

        viable = [s for s in self.consistent if s["consistent_count"] >= self.threshold]
        top = viable[:5]

        if not top:
            best = self.consistent[:3] if self.consistent else []
            if best:
                lines = []
                for s in best:
                    day_name = DAY_NAMES[s["weekday"]]
                    lines.append(
                        f"{SLOT_EMOJI[s['block']]} **{day_name} {BLOCK_LABELS[s['block']]}** — "
                        f"{s['consistent_count']} consistent across {s['total_weeks']} weeks"
                    )
                body = "\n".join(lines)
                msg = (
                    f"\U0001f3af **Campaign Windows** (consistent players)\n"
                    f"{self.respondents} responded • need {self.threshold}+ consistent\n\n"
                    f"⚠️ No slots hit {self.threshold}+ consistent players. Best so far:\n{body}"
                )
            else:
                msg = (
                    f"\U0001f3af **Campaign Windows**\n"
                    f"Not enough data yet. Need 3+ weeks of availability."
                )

            c = discord.ui.Container(
                discord.ui.TextDisplay(msg),
                accent_colour=discord.Colour.orange(),
            )
            self.add_item(c)
            return

        # Find a sample date for timestamp display
        today = datetime.date.today()

        sections = []
        for s in top:
            day_name = DAY_NAMES[s["weekday"]]
            bar = format_bar(s["consistent_count"], top[0]["consistent_count"])

            # Find next occurrence of this weekday for time display
            sample_date = today
            target_wd = s["weekday"]
            while sample_date.isoweekday() % 7 != target_wd:
                sample_date += datetime.timedelta(days=1)

            start_dt, end_dt = block_to_utc_range(sample_date, s["block"], server_tz, bc)
            time_start = utc_to_discord_timestamp(start_dt, "t")
            time_end = utc_to_discord_timestamp(end_dt, "t")

            section = discord.ui.Section(
                discord.ui.TextDisplay(
                    f"{SLOT_EMOJI[s['block']]} **Every {day_name}** {time_start}–{time_end}\n"
                    f"**{s['consistent_count']} players** consistent across {s['total_weeks']} weeks\n"
                    f"{bar}"
                ),
                accessory=discord.ui.Button(
                    label="\U0001f3af Campaign",
                    style=discord.ButtonStyle.green,
                    custom_id=f"cwin:{self.guild_id}:{s['weekday']}:{s['block']}",
                ),
            )
            sections.append((section, s))

        c = discord.ui.Container(
            discord.ui.TextDisplay(
                f"\U0001f3af **Campaign-Viable Slots** ({self.threshold}+ consistent)\n"
                f"{self.respondents} responded • "
                f"*Same players free every week — reliable for recurring games*"
            ),
            discord.ui.Separator(),
            *[s[0] for s in sections],
            accent_colour=discord.Colour.blue(),
        )
        self.add_item(c)

        for section, slot_data in sections:
            section.accessory.callback = self._make_campaign_info(slot_data)

    def _make_campaign_info(self, slot: dict):
        async def callback(interaction: discord.Interaction) -> None:
            day_name = DAY_NAMES[slot["weekday"]]
            player_list = []
            for uid in slot["players"][:15]:
                member = interaction.guild.get_member(uid)
                if member:
                    player_list.append(member.display_name)
                else:
                    player_list.append(f"User {uid}")

            await interaction.response.send_message(
                f"\U0001f3af **Every {day_name} {BLOCK_LABELS[slot['block']]}**\n\n"
                f"**{slot['consistent_count']} consistent players:**\n"
                f"{', '.join(player_list)}\n\n"
                f"These players marked this slot across {slot['total_weeks']} weeks.\n"
                f"Use `/campaign create` when ready (coming soon).",
                ephemeral=True,
            )
        return callback


class WindowsCog(commands.Cog):
    def __init__(self, bot: GameFinder) -> None:
        self.bot = bot

    @app_commands.command(name="windows", description="See best windows for scheduling games")
    @app_commands.describe(
        min="Minimum available players to show (overrides server default)",
    )
    async def windows(
        self,
        interaction: discord.Interaction,
        min: int | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        config = await queries.get_guild_config(self.bot.db, interaction.guild_id)
        if not config:
            await queries.ensure_guild(self.bot.db, interaction.guild_id)
            config = await queries.get_guild_config(self.bot.db, interaction.guild_id)

        threshold = min if min is not None else config["threshold"]
        forecast = config["forecast_weeks"]

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
        consistent = await queries.get_consistent_players(
            self.bot.db, interaction.guild_id, date_from, date_to, min_weeks=3,
        )

        view = CombinedWindowsView(
            self.bot, interaction.guild_id, threshold,
            counts, consistent, respondents, config,
        )
        await view.build()
        await interaction.followup.send(view=view, ephemeral=True)

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
                mentions.append(f"User {u['user_id']}")

        await interaction.response.send_message(
            f"**{day} · {BLOCK_LABELS[block.value]}** — {len(users)} available:\n"
            + ", ".join(mentions),
            ephemeral=True,
        )


async def setup(bot: GameFinder) -> None:
    await bot.add_cog(WindowsCog(bot))
