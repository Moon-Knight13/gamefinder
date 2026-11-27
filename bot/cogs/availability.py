from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, available_timezones

import discord
from discord import app_commands
from discord.ext import commands

from bot.db import queries
from bot.utils.time_blocks import BLOCK_LABELS, BLOCK_ORDER, date_range

if TYPE_CHECKING:
    from bot.bot import GameFinder

log = logging.getLogger(__name__)


class AvailabilityGrid(discord.ui.View):
    def __init__(
        self,
        db,
        guild_id: int,
        user_id: int,
        week_offset: int = 0,
    ) -> None:
        super().__init__(timeout=300)
        self.db = db
        self.guild_id = guild_id
        self.user_id = user_id
        self.week_offset = week_offset
        self.selected: set[tuple[str, str]] = set()

    async def build(self) -> None:
        self.clear_items()
        start = datetime.date.today() + datetime.timedelta(weeks=self.week_offset)
        dates = date_range(start, weeks=1)

        existing = await queries.get_user_availability(
            self.db,
            guild_id=self.guild_id,
            user_id=self.user_id,
            date_from=dates[0].isoformat(),
            date_to=dates[-1].isoformat(),
        )
        self.selected = {(r["date"], r["block"]) for r in existing}

        for day in dates:
            for block in BLOCK_ORDER:
                key = (day.isoformat(), block)
                is_on = key in self.selected
                label = f"{day.strftime('%a')} {BLOCK_LABELS[block]}"
                style = discord.ButtonStyle.green if is_on else discord.ButtonStyle.grey
                button = discord.ui.Button(
                    label=label[:20],
                    style=style,
                    custom_id=f"avail:{self.guild_id}:{self.user_id}:{day.isoformat()}:{block}",
                    row=BLOCK_ORDER.index(block),
                )
                button.callback = self._make_callback(day.isoformat(), block)
                self.add_item(button)

        prev_btn = discord.ui.Button(label="◀ Prev", style=discord.ButtonStyle.blurple, row=3)
        prev_btn.callback = self._prev_week
        self.add_item(prev_btn)

        next_btn = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.blurple, row=3)
        next_btn.callback = self._next_week
        self.add_item(next_btn)

    def _make_callback(self, date_str: str, block: str):
        async def callback(interaction: discord.Interaction):
            key = (date_str, block)
            if key in self.selected:
                await queries.delete_availability(
                    self.db, self.guild_id, self.user_id, date_str, block
                )
                self.selected.discard(key)
            else:
                await queries.upsert_availability(
                    self.db, self.guild_id, self.user_id, date_str, block
                )
                self.selected.add(key)
            await self.build()
            await interaction.response.edit_message(view=self)

        return callback

    async def _prev_week(self, interaction: discord.Interaction):
        self.week_offset = max(0, self.week_offset - 1)
        await self.build()
        await interaction.response.edit_message(content=self._header(), view=self)

    async def _next_week(self, interaction: discord.Interaction):
        config = await queries.get_guild_config(self.db, self.guild_id)
        max_weeks = (config["forecast_weeks"] if config else 3) - 1
        self.week_offset = min(max_weeks, self.week_offset + 1)
        await self.build()
        await interaction.response.edit_message(content=self._header(), view=self)

    def _header(self) -> str:
        start = datetime.date.today() + datetime.timedelta(weeks=self.week_offset)
        end = start + datetime.timedelta(days=6)
        return (
            f"**Availability** — {start.strftime('%b %d')} to "
            f"{end.strftime('%b %d')}\nTap to toggle slots."
        )


class AvailabilityCog(commands.Cog):
    def __init__(self, bot: GameFinder) -> None:
        self.bot = bot

    @app_commands.command(name="available", description="Mark your availability for upcoming weeks")
    async def available(self, interaction: discord.Interaction) -> None:
        view = AvailabilityGrid(
            db=self.bot.db,
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
        )
        await view.build()
        await interaction.response.send_message(
            view._header(),
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="available-clear", description="Clear all your availability data")
    async def available_clear(self, interaction: discord.Interaction) -> None:
        await queries.clear_user_availability(
            self.bot.db, interaction.guild_id, interaction.user.id
        )
        await interaction.response.send_message(
            "All your availability data cleared.", ephemeral=True
        )

    @app_commands.command(name="timezone", description="Set your timezone")
    @app_commands.describe(tz="Timezone name, e.g. America/New_York, Europe/London")
    async def timezone_set(self, interaction: discord.Interaction, tz: str) -> None:
        if tz not in available_timezones():
            await interaction.response.send_message(
                f"Unknown timezone `{tz}`. Use IANA names like `America/New_York`.",
                ephemeral=True,
            )
            return
        await queries.set_user_timezone(self.bot.db, interaction.user.id, tz)
        await interaction.response.send_message(f"Timezone set to `{tz}`.", ephemeral=True)

    @app_commands.command(name="available-import", description="Import availability from .ics file")
    async def available_import(
        self, interaction: discord.Interaction, file: discord.Attachment
    ) -> None:
        if not file.filename.endswith(".ics"):
            await interaction.response.send_message("Please attach an .ics file.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        data = await file.read()
        try:
            from icalendar import Calendar
        except ImportError:
            await interaction.followup.send("icalendar library not available.")
            return

        cal = Calendar.from_ical(data)
        config = await queries.get_guild_config(self.bot.db, interaction.guild_id)
        if not config:
            await queries.ensure_guild(self.bot.db, interaction.guild_id)
            config = await queries.get_guild_config(self.bot.db, interaction.guild_id)

        from bot.utils.time_blocks import BlockConfig

        bc = BlockConfig(
            morning_start=config["morning_start"],
            morning_end=config["morning_end"],
            afternoon_start=config["afternoon_start"],
            afternoon_end=config["afternoon_end"],
            evening_start=config["evening_start"],
            evening_end=config["evening_end"],
        )

        server_tz = ZoneInfo(config["timezone"])
        count = 0

        for component in cal.walk():
            if component.name != "VFREEBUSY" and component.name != "VEVENT":
                continue

            dtstart = component.get("dtstart")
            dtend = component.get("dtend")
            if not dtstart or not dtend:
                continue

            start_dt = dtstart.dt
            end_dt = dtend.dt

            if isinstance(start_dt, datetime.date) and not isinstance(start_dt, datetime.datetime):
                start_dt = datetime.datetime.combine(start_dt, datetime.time.min, tzinfo=server_tz)
                end_dt = datetime.datetime.combine(end_dt, datetime.time.max, tzinfo=server_tz)

            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=server_tz)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=server_tz)

            local_start = start_dt.astimezone(server_tz)
            local_end = end_dt.astimezone(server_tz)

            current = local_start.date()
            while current <= local_end.date():
                for block_name in BLOCK_ORDER:
                    block_start_h = getattr(bc, f"{block_name}_start")
                    block_end_h = getattr(bc, f"{block_name}_end")
                    block_start = datetime.datetime.combine(
                        current, datetime.time(block_start_h), tzinfo=server_tz
                    )
                    block_end = datetime.datetime.combine(
                        current, datetime.time(block_end_h), tzinfo=server_tz
                    )
                    if local_start <= block_start and local_end >= block_end:
                        await queries.upsert_availability(
                            self.bot.db,
                            interaction.guild_id,
                            interaction.user.id,
                            current.isoformat(),
                            block_name,
                        )
                        count += 1
                current += datetime.timedelta(days=1)

        await interaction.followup.send(f"Imported {count} availability blocks from calendar.")


async def setup(bot: GameFinder) -> None:
    await bot.add_cog(AvailabilityCog(bot))
