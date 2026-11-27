from __future__ import annotations

import contextlib
import datetime
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.db import queries
from bot.utils.formatting import (
    extract_id_from_footer,
    get_guild_config,
    make_block_config,
    validate_date,
)
from bot.utils.time_blocks import (
    BLOCK_LABELS,
    BlockConfig,
    block_to_utc_range,
    slot_to_discord_time,
)

if TYPE_CHECKING:
    from bot.bot import GameFinder
    from bot.db.database import Database

log = logging.getLogger(__name__)

RSVP_LABELS = {
    "going": "Going",
    "maybe": "Maybe",
    "not_going": "Can't Make It",
    "spectator": "Spectator",
    "waitlist": "Waitlist",
}

RSVP_EMOJI = {
    "going": "✅",
    "maybe": "\U0001f914",
    "not_going": "❌",
    "spectator": "\U0001f440",
    "waitlist": "\U0001f4cb",
}


def _format_rsvp_field(counts: dict[str, int]) -> str:
    going = counts.get("going", 0)
    maybe = counts.get("maybe", 0)
    not_going = counts.get("not_going", 0)
    spectator = counts.get("spectator", 0)
    waitlist = counts.get("waitlist", 0)
    parts = [f"✅ Going: {going}", f"\U0001f914 Maybe: {maybe}", f"❌ Can't: {not_going}"]
    if spectator:
        parts.append(f"\U0001f440 Spectator: {spectator}")
    if waitlist:
        parts.append(f"\U0001f4cb Waitlist: {waitlist}")
    return "  |  ".join(parts)


async def create_game_event(
    bot, guild: discord.Guild, game: dict, game_id: int, guild_id: int
) -> discord.ScheduledEvent | None:
    """Create Discord Scheduled Event for a game at quorum. Returns event or None."""
    db = bot.db
    config = await queries.get_guild_config(db, guild_id)
    if not config:
        return None

    server_tz = config["timezone"]
    bc = BlockConfig(
        morning_start=config["morning_start"],
        morning_end=config["morning_end"],
        afternoon_start=config["afternoon_start"],
        afternoon_end=config["afternoon_end"],
        evening_start=config["evening_start"],
        evening_end=config["evening_end"],
    )

    try:
        start_dt, end_dt = block_to_utc_range(
            datetime.date.fromisoformat(game["slot_date"]),
            game["slot_block"],
            server_tz,
            bc,
        )
        event = await guild.create_scheduled_event(
            name=game["title"],
            description=game.get("description", ""),
            start_time=start_dt,
            end_time=end_dt,
            entity_type=discord.EntityType.external,
            privacy_level=discord.PrivacyLevel.guild_only,
            location="Discord",
        )
        await queries.set_game_event_id(db, game_id, guild_id, event.id)
        log.info("Created Discord event %d for game #%d", event.id, game_id)
        return event
    except discord.Forbidden:
        log.warning("Missing permissions to create scheduled event for game #%d", game_id)
    except Exception:
        log.exception("Failed to create Discord event for game #%d", game_id)
    return None


class RSVPView(discord.ui.View):
    """Persistent five-tier RSVP buttons. Survives bot restarts."""

    def __init__(self, db: Database | None = None) -> None:
        super().__init__(timeout=None)
        self.db = db

    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        log.exception("RSVP error", exc_info=error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"RSVP error: {error}", ephemeral=True)
            else:
                await interaction.response.send_message(f"RSVP error: {error}", ephemeral=True)
        except discord.HTTPException:
            pass

    @discord.ui.button(
        label="Going", style=discord.ButtonStyle.green, custom_id="rsvp:going", emoji="✅", row=0
    )
    async def going(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_rsvp(interaction, "going")

    @discord.ui.button(
        label="Maybe",
        style=discord.ButtonStyle.grey,
        custom_id="rsvp:maybe",
        emoji="\U0001f914",
        row=0,
    )
    async def maybe(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_rsvp(interaction, "maybe")

    @discord.ui.button(
        label="Can't Make It",
        style=discord.ButtonStyle.red,
        custom_id="rsvp:not_going",
        emoji="❌",
        row=0,
    )
    async def not_going(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_rsvp(interaction, "not_going")

    @discord.ui.button(
        label="Spectator",
        style=discord.ButtonStyle.blurple,
        custom_id="rsvp:spectator",
        emoji="\U0001f440",
        row=1,
    )
    async def spectator(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_rsvp(interaction, "spectator")

    @discord.ui.button(
        label="Waitlist",
        style=discord.ButtonStyle.grey,
        custom_id="rsvp:waitlist",
        emoji="\U0001f4cb",
        row=1,
    )
    async def waitlist(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_rsvp(interaction, "waitlist")

    async def _handle_rsvp(self, interaction: discord.Interaction, status: str) -> None:
        if not self.db:
            self.db = interaction.client.db

        game_id = self._extract_game_id(interaction.message)
        if game_id is None:
            await interaction.response.send_message("Could not find game ID.", ephemeral=True)
            return

        game = await queries.get_game(self.db, game_id, interaction.guild_id)
        if not game:
            await interaction.response.send_message("Game not found.", ephemeral=True)
            return

        # Block Going RSVP on full games (allow other statuses)
        if game["status"] == "full" and status == "going":
            await interaction.response.send_message(
                "This game is full! You can join the **Waitlist** or watch as **Spectator**.",
                ephemeral=True,
            )
            return

        await queries.upsert_rsvp(self.db, game_id, interaction.user.id, status)
        counts = await queries.get_rsvp_counts(self.db, game_id)

        going = counts.get("going", 0)

        await interaction.response.send_message(
            f"RSVP: **{RSVP_LABELS[status]}** {RSVP_EMOJI[status]}\n{_format_rsvp_field(counts)}",
            ephemeral=True,
        )

        # Update embed with new counts
        if interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0].copy()
            for i, field in enumerate(embed.fields):
                if field.name == "RSVPs":
                    embed.set_field_at(
                        i, name="RSVPs", value=_format_rsvp_field(counts), inline=False
                    )
                    break
            with contextlib.suppress(discord.HTTPException):
                await interaction.message.edit(embed=embed)

        # Auto-close at quorum + create Discord event
        if going >= game["player_cap"] and game["status"] == "open":
            await queries.update_game_status(self.db, game_id, interaction.guild_id, "full")
            if interaction.guild:
                event = await create_game_event(
                    interaction.client, interaction.guild, game, game_id, interaction.guild_id
                )
                if event:
                    if interaction.channel:
                        await interaction.channel.send(
                            f"\U0001f389 **{game['title']}** reached quorum! "
                            f"({going}/{game['player_cap']} Going) — Event created!"
                        )
                    # DM each Going player with event link
                    rsvps = await queries.get_rsvps(self.db, game_id)
                    for r in rsvps:
                        if r["status"] == "going":
                            try:
                                member = interaction.guild.get_member(r["user_id"])
                                if not member:
                                    member = await interaction.guild.fetch_member(r["user_id"])
                                await member.send(
                                    f"\U0001f3b2 **{game['title']}** is confirmed!\n\n"
                                    f"Click to join the Discord Event and get reminders:\n"
                                    f"{event.url}"
                                )
                            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                                log.debug("Could not DM user %d", r["user_id"])

    def _extract_game_id(self, message: discord.Message | None) -> int | None:
        if not message or not message.embeds:
            return None
        return extract_id_from_footer(message.embeds[0])


class GamesCog(commands.Cog):
    def __init__(self, bot: GameFinder) -> None:
        self.bot = bot

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        log.exception("Games command error", exc_info=error)
        msg = f"Error: {error}"[:200]
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except discord.HTTPException:
            pass

    async def _get_post_channel(
        self, interaction: discord.Interaction
    ) -> discord.TextChannel | discord.abc.Messageable:
        config = await queries.get_guild_config(self.bot.db, interaction.guild_id)
        if config and config["scheduling_channel_id"]:
            channel = interaction.guild.get_channel(config["scheduling_channel_id"])
            if channel:
                return channel
        return interaction.channel

    @app_commands.command(name="game-create", description="Post a new game")
    @app_commands.describe(
        title="Game title",
        description="Game description",
        date="Date for the game (YYYY-MM-DD)",
        block="Time block: morning, afternoon, or evening",
        player_cap="Maximum player count",
    )
    @app_commands.choices(
        block=[
            app_commands.Choice(name="Morning", value="morning"),
            app_commands.Choice(name="Afternoon", value="afternoon"),
            app_commands.Choice(name="Evening", value="evening"),
        ]
    )
    async def game_create(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        date: str,
        block: app_commands.Choice[str],
        player_cap: int = 5,
    ) -> None:
        if not validate_date(date):
            await interaction.response.send_message(
                "Invalid date. Use YYYY-MM-DD format (e.g. 2026-12-05).", ephemeral=True
            )
            return

        await interaction.response.defer()

        config = await get_guild_config(self.bot.db, interaction.guild_id)
        bc = make_block_config(config)

        game_id = await queries.create_game(
            self.bot.db,
            guild_id=interaction.guild_id,
            creator_id=interaction.user.id,
            title=title,
            description=description,
            slot_date=date,
            slot_block=block.value,
            player_cap=player_cap,
        )

        when_str = slot_to_discord_time(date, block.value, config["timezone"], bc)

        embed = discord.Embed(
            title=f"\U0001f3b2 {title}",
            description=description,
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="When",
            value=when_str,
            inline=False,
        )
        embed.add_field(name="Player Cap", value=str(player_cap), inline=True)
        embed.add_field(name="Status", value="\U0001f7e2 Open", inline=True)
        embed.add_field(
            name="RSVPs",
            value=_format_rsvp_field({}),
            inline=False,
        )
        embed.set_footer(text=f"Game #{game_id} · by {interaction.user.display_name}")

        post_channel = await self._get_post_channel(interaction)
        view = RSVPView(self.bot.db)

        if post_channel == interaction.channel:
            msg = await interaction.followup.send(embed=embed, view=view, wait=True)
        else:
            msg = await post_channel.send(embed=embed, view=view)
            await interaction.followup.send(
                f"Game **{title}** posted in {post_channel.mention}!", ephemeral=True
            )

        # Store message location for future edits
        await queries.set_game_message(
            self.bot.db, game_id, interaction.guild_id, msg.id, msg.channel.id
        )

        # Ping available users
        available_users = await queries.get_available_users(
            self.bot.db, interaction.guild_id, date, block.value
        )
        if available_users:
            mentions = [f"<@{u['user_id']}>" for u in available_users]
            batch_size = 15
            for i in range(0, len(mentions), batch_size):
                batch = mentions[i : i + batch_size]
                await post_channel.send(
                    f"\U0001f3b2 **{title}** posted for **{date} {BLOCK_LABELS[block.value]}**!\n"
                    f"Based on your availability: {' '.join(batch)}\n"
                    f"RSVP above — open to everyone!"
                )

    @app_commands.command(name="games", description="List games")
    @app_commands.describe(status="Filter by status (default: open)")
    @app_commands.choices(
        status=[
            app_commands.Choice(name="Open", value="open"),
            app_commands.Choice(name="Full", value="full"),
            app_commands.Choice(name="Cancelled", value="cancelled"),
            app_commands.Choice(name="All", value="all"),
        ]
    )
    async def games_list(
        self,
        interaction: discord.Interaction,
        status: app_commands.Choice[str] | None = None,
    ) -> None:
        filter_val = status.value if status else "open"
        games = await queries.list_games(
            self.bot.db,
            interaction.guild_id,
            status=None if filter_val == "all" else filter_val,
        )
        if not games:
            await interaction.response.send_message(f"No {filter_val} games.", ephemeral=True)
            return

        config = await get_guild_config(self.bot.db, interaction.guild_id)
        bc = make_block_config(config)

        lines = []
        for g in games:
            counts = await queries.get_rsvp_counts(self.bot.db, g["id"])
            going = counts.get("going", 0)
            maybe = counts.get("maybe", 0)
            from bot.utils.time_blocks import slot_to_discord_short

            slot_str = slot_to_discord_short(
                g["slot_date"], g["slot_block"], config["timezone"], bc
            )
            status_icon = "\U0001f7e2" if g["status"] == "open" else "\U0001f534"
            lines.append(
                f"{status_icon} **#{g['id']}** {g['title']} — {slot_str} "
                f"(✅ {going} | \U0001f914 {maybe} | Cap: {g['player_cap']})"
            )

        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="game-cancel", description="Cancel a game you created")
    @app_commands.describe(game_id="Game ID number")
    async def game_cancel(self, interaction: discord.Interaction, game_id: int) -> None:
        game = await queries.get_game(self.bot.db, game_id, interaction.guild_id)
        if not game:
            await interaction.response.send_message("Game not found.", ephemeral=True)
            return
        if game["creator_id"] != interaction.user.id:
            await interaction.response.send_message(
                "Only the creator can cancel this game.", ephemeral=True
            )
            return

        await queries.update_game_status(self.bot.db, game_id, interaction.guild_id, "cancelled")

        # Remove Discord event if exists
        if game.get("discord_event_id") and interaction.guild:
            try:
                event = await interaction.guild.fetch_scheduled_event(game["discord_event_id"])
                await event.cancel()
            except discord.NotFound:
                pass
            except discord.HTTPException:
                log.warning("Failed to cancel Discord event for game #%d", game_id)

        rsvps = await queries.get_rsvps(self.bot.db, game_id)
        notify_ids = [r["user_id"] for r in rsvps if r["status"] in ("going", "maybe")]

        post_channel = await self._get_post_channel(interaction)
        if notify_ids:
            mentions = " ".join(f"<@{uid}>" for uid in notify_ids[:15])
            await post_channel.send(f"❌ **{game['title']}** has been cancelled.\n{mentions}")

        await interaction.response.send_message(f"Game #{game_id} cancelled.", ephemeral=True)

    @app_commands.command(name="game-edit", description="Edit a game you created")
    @app_commands.describe(
        game_id="Game ID number",
        title="New title",
        description="New description",
        date="New date (YYYY-MM-DD)",
        block="New time block",
        player_cap="New player cap",
    )
    @app_commands.choices(
        block=[
            app_commands.Choice(name="Morning", value="morning"),
            app_commands.Choice(name="Afternoon", value="afternoon"),
            app_commands.Choice(name="Evening", value="evening"),
        ]
    )
    async def game_edit(
        self,
        interaction: discord.Interaction,
        game_id: int,
        title: str | None = None,
        description: str | None = None,
        date: str | None = None,
        block: app_commands.Choice[str] | None = None,
        player_cap: int | None = None,
    ) -> None:
        game = await queries.get_game(self.bot.db, game_id, interaction.guild_id)
        if not game:
            await interaction.response.send_message("Game not found.", ephemeral=True)
            return
        if game["creator_id"] != interaction.user.id:
            await interaction.response.send_message(
                "Only the creator can edit this game.", ephemeral=True
            )
            return

        if date is not None and not validate_date(date):
            await interaction.response.send_message(
                "Invalid date. Use YYYY-MM-DD format.", ephemeral=True
            )
            return

        updates = {}
        if title is not None:
            updates["title"] = title
        if description is not None:
            updates["description"] = description
        if date is not None:
            updates["slot_date"] = date
        if block is not None:
            updates["slot_block"] = block.value
        if player_cap is not None:
            updates["player_cap"] = player_cap

        if not updates:
            await interaction.response.send_message("Nothing to update.", ephemeral=True)
            return

        await queries.update_game(self.bot.db, game_id, interaction.guild_id, **updates)

        # Refresh game data
        game = await queries.get_game(self.bot.db, game_id, interaction.guild_id)
        counts = await queries.get_rsvp_counts(self.bot.db, game_id)

        # Update original message if we have its location
        if game.get("message_id") and game.get("channel_id"):
            try:
                config = await get_guild_config(self.bot.db, interaction.guild_id)
                bc = make_block_config(config)
                when_str = slot_to_discord_time(
                    game["slot_date"], game["slot_block"], config["timezone"], bc
                )

                channel = interaction.guild.get_channel(game["channel_id"])
                if channel:
                    msg = await channel.fetch_message(game["message_id"])
                    embed = discord.Embed(
                        title=f"\U0001f3b2 {game['title']}",
                        description=game["description"],
                        color=discord.Color.blue(),
                    )
                    embed.add_field(name="When", value=when_str, inline=False)
                    embed.add_field(name="Player Cap", value=str(game["player_cap"]), inline=True)
                    status_text = (
                        "\U0001f7e2 Open" if game["status"] == "open" else "\U0001f534 Full"
                    )
                    embed.add_field(name="Status", value=status_text, inline=True)
                    embed.add_field(name="RSVPs", value=_format_rsvp_field(counts), inline=False)
                    embed.set_footer(
                        text=f"Game #{game_id} · by {interaction.user.display_name} · edited"
                    )
                    await msg.edit(embed=embed)
            except (discord.NotFound, discord.HTTPException):
                log.warning("Could not update original message for game #%d", game_id)

        # Notify RSVP'd users of changes
        rsvps = await queries.get_rsvps(self.bot.db, game_id)
        notify_ids = [r["user_id"] for r in rsvps if r["status"] in ("going", "maybe")]
        if notify_ids:
            changes = ", ".join(f"**{k}**" for k in updates)
            post_channel = await self._get_post_channel(interaction)
            mentions = " ".join(f"<@{uid}>" for uid in notify_ids[:15])
            await post_channel.send(f"✏️ **{game['title']}** updated ({changes}).\n{mentions}")

        await interaction.response.send_message(f"Game #{game_id} updated.", ephemeral=True)


async def setup(bot: GameFinder) -> None:
    await bot.add_cog(GamesCog(bot))
