from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.db import queries
from bot.utils.time_blocks import BLOCK_LABELS

if TYPE_CHECKING:
    from bot.bot import GameFinder
    from bot.db.database import Database

log = logging.getLogger(__name__)


class RSVPView(discord.ui.View):
    """Persistent three-tier RSVP buttons. Survives bot restarts."""

    def __init__(self, db: Database | None = None) -> None:
        super().__init__(timeout=None)
        self.db = db

    @discord.ui.button(
        label="Going",
        style=discord.ButtonStyle.green,
        custom_id="rsvp:going",
        emoji="✅",
    )
    async def going(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_rsvp(interaction, "going")

    @discord.ui.button(
        label="Maybe",
        style=discord.ButtonStyle.grey,
        custom_id="rsvp:maybe",
        emoji="\U0001f914",
    )
    async def maybe(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_rsvp(interaction, "maybe")

    @discord.ui.button(
        label="Can't Make It",
        style=discord.ButtonStyle.red,
        custom_id="rsvp:not_going",
        emoji="❌",
    )
    async def not_going(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_rsvp(interaction, "not_going")

    async def _handle_rsvp(self, interaction: discord.Interaction, status: str) -> None:
        if not self.db:
            self.db = interaction.client.db

        game_id = self._extract_game_id(interaction.message)
        if game_id is None:
            await interaction.response.send_message("Could not find game ID.", ephemeral=True)
            return

        await queries.upsert_rsvp(self.db, game_id, interaction.user.id, status)
        counts = await queries.get_rsvp_counts(self.db, game_id)
        game = await queries.get_game(self.db, game_id, interaction.guild_id)

        going = counts.get("going", 0)
        maybe = counts.get("maybe", 0)
        not_going = counts.get("not_going", 0)

        status_labels = {"going": "Going", "maybe": "Maybe", "not_going": "Can't Make It"}
        await interaction.response.send_message(
            f"RSVP: **{status_labels[status]}** — "
            f"Going: {going} | Maybe: {maybe} | Can't: {not_going}",
            ephemeral=True,
        )

        if interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0].copy()
            for i, field in enumerate(embed.fields):
                if field.name == "RSVPs":
                    embed.set_field_at(
                        i,
                        name="RSVPs",
                        value=(
                            f"✅ Going: {going}  |  \U0001f914 Maybe: {maybe}"
                            f"  |  ❌ Can't: {not_going}"
                        ),
                        inline=False,
                    )
                    break
            with contextlib.suppress(discord.HTTPException):
                await interaction.message.edit(embed=embed)

        if game and going >= game["player_cap"] and game["status"] == "open":
            await queries.update_game_status(self.db, game_id, interaction.guild_id, "full")

    def _extract_game_id(self, message: discord.Message | None) -> int | None:
        if not message or not message.embeds:
            return None
        embed = message.embeds[0]
        if embed.footer and embed.footer.text:
            parts = embed.footer.text.split("#")
            if len(parts) >= 2 and parts[1].strip().isdigit():
                return int(parts[1].strip())
        return None


class GamesCog(commands.Cog):
    def __init__(self, bot: GameFinder) -> None:
        self.bot = bot

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
        await interaction.response.defer()

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

        embed = discord.Embed(
            title=f"\U0001f3b2 {title}",
            description=description,
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="When",
            value=f"{date} · {BLOCK_LABELS[block.value]}",
            inline=True,
        )
        embed.add_field(name="Player Cap", value=str(player_cap), inline=True)
        embed.add_field(
            name="RSVPs",
            value="✅ Going: 0  |  \U0001f914 Maybe: 0  |  ❌ Can't: 0",
            inline=False,
        )
        embed.set_footer(text=f"Game #{game_id} · by {interaction.user.display_name}")

        available_users = await queries.get_available_users(
            self.bot.db, interaction.guild_id, date, block.value
        )

        view = RSVPView(self.bot.db)
        await interaction.followup.send(embed=embed, view=view, wait=True)

        if available_users:
            mentions = [f"<@{u['user_id']}>" for u in available_users]
            batch_size = 15
            for i in range(0, len(mentions), batch_size):
                batch = mentions[i : i + batch_size]
                await interaction.channel.send(
                    f"\U0001f3b2 **{title}** posted for **{date} {BLOCK_LABELS[block.value]}**!\n"
                    f"Based on your availability: {' '.join(batch)}\n"
                    f"RSVP above — open to everyone!"
                )

    @app_commands.command(name="games", description="List upcoming games")
    async def games_list(self, interaction: discord.Interaction) -> None:
        games = await queries.list_games(self.bot.db, interaction.guild_id)
        if not games:
            await interaction.response.send_message("No open games right now.", ephemeral=True)
            return

        lines = []
        for g in games:
            counts = await queries.get_rsvp_counts(self.bot.db, g["id"])
            going = counts.get("going", 0)
            maybe = counts.get("maybe", 0)
            lines.append(
                f"**#{g['id']}** {g['title']} — {g['slot_date']} {BLOCK_LABELS[g['slot_block']]} "
                f"(✅ {going} | \U0001f914 {maybe})"
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

        rsvps = await queries.get_rsvps(self.bot.db, game_id)
        notify_ids = [r["user_id"] for r in rsvps if r["status"] in ("going", "maybe")]
        if notify_ids:
            mentions = " ".join(f"<@{uid}>" for uid in notify_ids[:15])
            await interaction.channel.send(
                f"❌ **{game['title']}** has been cancelled.\n{mentions}"
            )

        await interaction.response.send_message(f"Game #{game_id} cancelled.", ephemeral=True)


async def setup(bot: GameFinder) -> None:
    await bot.add_cog(GamesCog(bot))
