from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, available_timezones

import discord
from discord import app_commands
from discord.ext import commands

from bot.db import queries
from bot.utils.formatting import get_guild_config, make_block_config, ordinal
from bot.utils.time_blocks import (
    BLOCK_LABELS, BLOCK_ORDER, BlockConfig, block_to_utc_range,
    date_range, utc_to_discord_timestamp,
)

if TYPE_CHECKING:
    from bot.bot import GameFinder

log = logging.getLogger(__name__)

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

SLOT_LABEL = {"morning": "AM", "afternoon": "MID", "evening": "PM"}
SLOT_EMOJI = {"morning": "\U0001f305", "afternoon": "☀️", "evening": "\U0001f319"}


def _time_slots_header(day: datetime.date, server_tz: str, bc: BlockConfig) -> str:
    parts = []
    for block in BLOCK_ORDER:
        start_dt, end_dt = block_to_utc_range(day, block, server_tz, bc)
        s = utc_to_discord_timestamp(start_dt, "t")
        e = utc_to_discord_timestamp(end_dt, "t")
        parts.append(f"{SLOT_EMOJI[block]} **{SLOT_LABEL[block]}** {s}–{e}")
    return " │ ".join(parts)


class CalendarGrid(discord.ui.LayoutView):
    """Weekly grid: 7 days × 3 slot toggles + select menus for custom/recurring."""

    def __init__(self, db, guild_id: int, user_id: int, week_offset: int = 0) -> None:
        super().__init__(timeout=600)
        self.db = db
        self.guild_id = guild_id
        self.user_id = user_id
        self.week_offset = week_offset
        self.available: set[tuple[str, str]] = set()
        self.recurring: set[tuple[int, str]] = set()

    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        log.exception("Calendar error", exc_info=error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"Error: {error}", ephemeral=True)
            else:
                await interaction.response.send_message(f"Error: {error}", ephemeral=True)
        except discord.HTTPException:
            pass

    async def build(self) -> None:
        self.clear_items()
        today = datetime.date.today()
        week_start = today + datetime.timedelta(weeks=self.week_offset)
        week_start -= datetime.timedelta(days=week_start.weekday())
        if week_start < today:
            week_start = today

        days = []
        d = week_start
        while len(days) < 7:
            days.append(d)
            d += datetime.timedelta(days=1)

        await self._load_data()

        config = await get_guild_config(self.db, self.guild_id)
        bc = make_block_config(config)
        server_tz = config["timezone"]

        import calendar
        month_name = calendar.month_name[days[0].month]
        year = days[0].year
        slots_header = _time_slots_header(days[0], server_tz, bc)

        week_dates = {d.isoformat() for d in days}
        week_count = sum(1 for dt, _ in self.available if dt in week_dates)
        total = len(self.available)
        rec_count = len(self.recurring)

        day_rows = [self._make_day_row(d) for d in days]

        # Nav
        prev_btn = discord.ui.Button(
            label="◀ Prev", style=discord.ButtonStyle.blurple,
            custom_id=f"g:prev:{self.guild_id}:{self.user_id}",
            disabled=self.week_offset <= 0,
        )
        prev_btn.callback = self._prev_week

        next_btn = discord.ui.Button(
            label="Next ▶", style=discord.ButtonStyle.blurple,
            custom_id=f"g:next:{self.guild_id}:{self.user_id}",
        )
        next_btn.callback = self._next_week

        sync_btn = discord.ui.Button(
            label="\U0001f4c5 Sync", style=discord.ButtonStyle.grey,
            custom_id=f"g:sync:{self.guild_id}:{self.user_id}",
        )
        sync_btn.callback = self._sync_placeholder

        clear_btn = discord.ui.Button(
            label="\U0001f5d1 Clear", style=discord.ButtonStyle.red,
            custom_id=f"g:clear:{self.guild_id}:{self.user_id}",
        )
        clear_btn.callback = self._clear_all

        # Select menu: custom hours or recurring for a day
        action_options = []
        for d in days:
            lbl = f"{DAY_ABBR[d.weekday()]} {ordinal(d.day)}"
            has_rec = any((d.weekday(), b) in self.recurring for b in BLOCK_ORDER)
            rec_tag = " \U0001f501" if has_rec else ""
            action_options.append(discord.SelectOption(
                label=f"⏰ {lbl} — custom hours",
                value=f"custom:{d.isoformat()}",
            ))
            action_options.append(discord.SelectOption(
                label=f"\U0001f501 {lbl} — recurring{rec_tag}",
                value=f"recurring:{d.isoformat()}",
            ))

        action_select = discord.ui.Select(
            custom_id=f"g:action:{self.guild_id}:{self.user_id}",
            placeholder="⏰ Custom hours or \U0001f501 Recurring for a day...",
            min_values=1, max_values=1,
            options=action_options[:25],
        )
        action_select.callback = self._on_action

        rec_line = f" • \U0001f501 {rec_count} recurring" if rec_count else ""
        date_range_str = f"{days[0].strftime('%b %d')} – {days[-1].strftime('%b %d')}"

        # Container 1: header + 4 days
        c1 = discord.ui.Container(
            discord.ui.TextDisplay(
                f"\U0001f4c5 **{month_name} {year}** • {date_range_str}\n"
                f"{slots_header}\n"
                f"\U0001f7e2 on │ \U0001f501 recurring │ {week_count} this week • {total} total{rec_line}"
            ),
            day_rows[0], day_rows[1], day_rows[2], day_rows[3],
            accent_colour=discord.Colour.green(),
        )

        # Container 2: 3 days + action select + nav
        c2 = discord.ui.Container(
            day_rows[4], day_rows[5], day_rows[6],
            discord.ui.ActionRow(action_select),
            discord.ui.ActionRow(prev_btn, next_btn, sync_btn, clear_btn),
        )

        self.add_item(c1)
        self.add_item(c2)

    def _make_day_row(self, d: datetime.date) -> discord.ui.ActionRow:
        date_str = d.isoformat()
        day_lbl = f"{DAY_ABBR[d.weekday()]} {ordinal(d.day)}"
        buttons = []

        for block in BLOCK_ORDER:
            is_on = (date_str, block) in self.available
            is_rec = (d.weekday(), block) in self.recurring

            if is_on and is_rec:
                label = f"\U0001f501 {day_lbl}"
                style = discord.ButtonStyle.green
            elif is_on:
                label = f"{SLOT_EMOJI[block]} {day_lbl}"
                style = discord.ButtonStyle.green
            else:
                label = f"{SLOT_EMOJI[block]} {day_lbl}"
                style = discord.ButtonStyle.grey

            btn = discord.ui.Button(
                label=label, style=style,
                custom_id=f"g:t:{self.guild_id}:{self.user_id}:{date_str}:{block}",
            )
            btn.callback = self._make_toggle(date_str, block, is_on)
            buttons.append(btn)

        return discord.ui.ActionRow(*buttons)

    def _make_toggle(self, date_str: str, block: str, is_on: bool):
        async def callback(interaction: discord.Interaction) -> None:
            if is_on:
                await queries.delete_availability(
                    self.db, self.guild_id, self.user_id, date_str, block
                )
            else:
                await queries.upsert_availability(
                    self.db, self.guild_id, self.user_id, date_str, block
                )
            await self.build()
            await interaction.response.edit_message(view=self)
        return callback

    async def _on_action(self, interaction: discord.Interaction) -> None:
        value = interaction.data.get("values", [""])[0]
        action, date_str = value.split(":", 1)
        d = datetime.date.fromisoformat(date_str)
        if action == "custom":
            view = CustomHoursView(self.db, self.guild_id, self.user_id, d, self.week_offset)
        else:
            view = RecurringEditView(self.db, self.guild_id, self.user_id, d, self.week_offset)
        await view.build()
        await interaction.response.edit_message(view=view)

    async def _load_data(self) -> None:
        today = datetime.date.today()
        all_rows = await queries.get_user_availability(
            self.db, self.guild_id, self.user_id,
            today.isoformat(),
            (today + datetime.timedelta(days=180)).isoformat(),
        )
        self.available = {(r["date"], r["block"]) for r in all_rows}
        recurring_rows = await queries.get_user_recurring(self.db, self.guild_id, self.user_id)
        self.recurring = {(r["weekday"], r["block"]) for r in recurring_rows}

    async def _prev_week(self, interaction: discord.Interaction) -> None:
        self.week_offset = max(0, self.week_offset - 1)
        await self.build()
        await interaction.response.edit_message(view=self)

    async def _next_week(self, interaction: discord.Interaction) -> None:
        self.week_offset = min(25, self.week_offset + 1)
        await self.build()
        await interaction.response.edit_message(view=self)

    async def _clear_all(self, interaction: discord.Interaction) -> None:
        await queries.clear_user_availability(self.db, self.guild_id, self.user_id)
        await queries.clear_user_recurring(self.db, self.guild_id, self.user_id)
        await self.build()
        await interaction.response.edit_message(view=self)

    async def _sync_placeholder(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "\U0001f4c5 Calendar sync coming soon! Use `/available-import` with .ics for now.",
            ephemeral=True,
        )


class RecurringEditView(discord.ui.LayoutView):
    """Per-day recurring editor. Multi-select which slots recur for this weekday."""

    def __init__(self, db, guild_id: int, user_id: int, day: datetime.date, week_offset: int) -> None:
        super().__init__(timeout=300)
        self.db = db
        self.guild_id = guild_id
        self.user_id = user_id
        self.day = day
        self.week_offset = week_offset

    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        log.exception("Recurring edit error", exc_info=error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"Error: {error}", ephemeral=True)
            else:
                await interaction.response.send_message(f"Error: {error}", ephemeral=True)
        except discord.HTTPException:
            pass

    async def build(self) -> None:
        self.clear_items()
        weekday = self.day.weekday()
        day_name = DAY_NAMES[weekday]

        recurring_rows = await queries.get_user_recurring(self.db, self.guild_id, self.user_id)
        active = {r["block"] for r in recurring_rows if r["weekday"] == weekday}

        config = await get_guild_config(self.db, self.guild_id)
        bc = make_block_config(config)
        server_tz = config["timezone"]

        # Slot descriptions with times
        slot_options = []
        for block in BLOCK_ORDER:
            start_dt, end_dt = block_to_utc_range(self.day, block, server_tz, bc)
            s = utc_to_discord_timestamp(start_dt, "t")
            e = utc_to_discord_timestamp(end_dt, "t")
            is_active = block in active
            slot_options.append(discord.SelectOption(
                label=f"{SLOT_EMOJI[block]} {SLOT_LABEL[block]} ({BLOCK_LABELS[block]})",
                value=block,
                description=f"Currently {'ON' if is_active else 'OFF'}",
                default=is_active,
            ))

        slot_select = discord.ui.Select(
            custom_id=f"reced:slots:{self.guild_id}:{self.user_id}:{weekday}",
            placeholder="Select which slots recur...",
            min_values=0, max_values=3,
            options=slot_options,
        )
        slot_select.callback = self._on_slots_selected

        active_str = ", ".join(f"{SLOT_EMOJI[b]} {SLOT_LABEL[b]}" for b in BLOCK_ORDER if b in active)
        if not active_str:
            active_str = "None"

        back_btn = discord.ui.Button(
            label="◀ Back", style=discord.ButtonStyle.grey,
            custom_id=f"reced:back:{self.guild_id}:{self.user_id}",
        )
        back_btn.callback = self._back

        clear_btn = discord.ui.Button(
            label=f"❌ Remove all {day_name} recurring", style=discord.ButtonStyle.red,
            custom_id=f"reced:clear:{self.guild_id}:{self.user_id}:{weekday}",
        )
        clear_btn.callback = self._clear_day_recurring

        c = discord.ui.Container(
            discord.ui.TextDisplay(
                f"\U0001f501 **Recurring: Every {day_name}**\n\n"
                f"Currently recurring: {active_str}\n\n"
                f"Select which slots should repeat every {day_name} for 6 months:"
            ),
            discord.ui.ActionRow(slot_select),
            discord.ui.Separator(),
            discord.ui.ActionRow(back_btn, clear_btn),
            accent_colour=discord.Colour.blue(),
        )
        self.add_item(c)

    async def _on_slots_selected(self, interaction: discord.Interaction) -> None:
        selected = interaction.data.get("values", [])
        weekday = self.day.weekday()
        today = datetime.date.today()

        # Clear existing recurring for this weekday
        for block in BLOCK_ORDER:
            await queries.delete_recurring(self.db, self.guild_id, self.user_id, weekday, block)

        # Set new recurring + fill dates
        for block in selected:
            await queries.set_recurring(self.db, self.guild_id, self.user_id, weekday, block)
            for i in range(180):
                d = today + datetime.timedelta(days=i)
                if d.weekday() == weekday:
                    await queries.upsert_availability(
                        self.db, self.guild_id, self.user_id, d.isoformat(), block
                    )

        # Return to grid
        grid = CalendarGrid(self.db, self.guild_id, self.user_id, self.week_offset)
        await grid.build()
        await interaction.response.edit_message(view=grid)

    async def _clear_day_recurring(self, interaction: discord.Interaction) -> None:
        weekday = self.day.weekday()
        for block in BLOCK_ORDER:
            await queries.delete_recurring(self.db, self.guild_id, self.user_id, weekday, block)
        grid = CalendarGrid(self.db, self.guild_id, self.user_id, self.week_offset)
        await grid.build()
        await interaction.response.edit_message(view=grid)

    async def _back(self, interaction: discord.Interaction) -> None:
        grid = CalendarGrid(self.db, self.guild_id, self.user_id, self.week_offset)
        await grid.build()
        await interaction.response.edit_message(view=grid)


class CustomHoursView(discord.ui.LayoutView):
    """Set exact hours for a specific day."""

    def __init__(self, db, guild_id: int, user_id: int, day: datetime.date, week_offset: int) -> None:
        super().__init__(timeout=300)
        self.db = db
        self.guild_id = guild_id
        self.user_id = user_id
        self.day = day
        self.week_offset = week_offset
        self.start_hour: int | None = None
        self.end_hour: int | None = None

    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        log.exception("Custom hours error", exc_info=error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"Error: {error}", ephemeral=True)
            else:
                await interaction.response.send_message(f"Error: {error}", ephemeral=True)
        except discord.HTTPException:
            pass

    async def build(self) -> None:
        self.clear_items()

        config = await get_guild_config(self.db, self.guild_id)
        server_tz = config["timezone"]
        bc = make_block_config(config)
        day_name = DAY_NAMES[self.day.weekday()]
        tz = ZoneInfo(server_tz)

        # Time reference with Discord timestamps
        time_lines = []
        for h in range(8, 24, 2):
            local_dt = datetime.datetime(self.day.year, self.day.month, self.day.day, h, tzinfo=tz)
            ts = utc_to_discord_timestamp(local_dt.astimezone(datetime.UTC), "t")
            time_lines.append(f"`{h:02d}:00` = {ts}")
        time_ref = " │ ".join(time_lines)

        # Quick block buttons
        block_btns = []
        for block in BLOCK_ORDER:
            start_dt, end_dt = block_to_utc_range(self.day, block, server_tz, bc)
            btn = discord.ui.Button(
                label=f"{SLOT_EMOJI[block]} {SLOT_LABEL[block]}",
                style=discord.ButtonStyle.green,
                custom_id=f"ch:b:{self.guild_id}:{self.user_id}:{self.day.isoformat()}:{block}",
            )
            btn.callback = self._make_quick_block(block)
            block_btns.append(btn)

        # Hour selects
        start_opts = [discord.SelectOption(label=f"{h:02d}:00", value=str(h)) for h in range(8, 23)]
        end_opts = [discord.SelectOption(label=f"{h:02d}:00", value=str(h)) for h in range(9, 24)]

        start_sel = discord.ui.Select(
            custom_id=f"ch:s:{self.guild_id}:{self.user_id}",
            placeholder="From...", min_values=1, max_values=1, options=start_opts,
        )
        start_sel.callback = self._on_start

        end_sel = discord.ui.Select(
            custom_id=f"ch:e:{self.guild_id}:{self.user_id}",
            placeholder="To...", min_values=1, max_values=1, options=end_opts,
        )
        end_sel.callback = self._on_end

        apply_btn = discord.ui.Button(
            label="✅ Apply", style=discord.ButtonStyle.green,
            custom_id=f"ch:apply:{self.guild_id}:{self.user_id}",
        )
        apply_btn.callback = self._apply

        back_btn = discord.ui.Button(
            label="◀ Back", style=discord.ButtonStyle.grey,
            custom_id=f"ch:back:{self.guild_id}:{self.user_id}",
        )
        back_btn.callback = self._back

        status = ""
        if self.start_hour is not None and self.end_hour is not None:
            s_dt = datetime.datetime(self.day.year, self.day.month, self.day.day, self.start_hour, tzinfo=tz)
            e_dt = datetime.datetime(self.day.year, self.day.month, self.day.day, self.end_hour, tzinfo=tz)
            s_ts = utc_to_discord_timestamp(s_dt.astimezone(datetime.UTC), "t")
            e_ts = utc_to_discord_timestamp(e_dt.astimezone(datetime.UTC), "t")
            status = f"\n\n✅ **{s_ts} – {e_ts}** — hit Apply"
        elif self.start_hour is not None:
            status = f"\n\n\U0001f4cc From `{self.start_hour:02d}:00` — now pick end"

        c = discord.ui.Container(
            discord.ui.TextDisplay(
                f"⏰ **{day_name} {ordinal(self.day.day)}**{status}\n\n"
                f"**Quick:** tap a slot │ **Custom:** pick range below\n"
                f"{time_ref}"
            ),
            discord.ui.ActionRow(*block_btns),
            discord.ui.Separator(),
            discord.ui.ActionRow(start_sel),
            discord.ui.ActionRow(end_sel),
            discord.ui.ActionRow(apply_btn, back_btn),
            accent_colour=discord.Colour.blue(),
        )
        self.add_item(c)

    def _make_quick_block(self, block: str):
        async def callback(interaction: discord.Interaction) -> None:
            await queries.upsert_availability(
                self.db, self.guild_id, self.user_id, self.day.isoformat(), block
            )
            grid = CalendarGrid(self.db, self.guild_id, self.user_id, self.week_offset)
            await grid.build()
            await interaction.response.edit_message(view=grid)
        return callback

    async def _on_start(self, interaction: discord.Interaction) -> None:
        self.start_hour = int(interaction.data.get("values", ["9"])[0])
        await self.build()
        await interaction.response.edit_message(view=self)

    async def _on_end(self, interaction: discord.Interaction) -> None:
        self.end_hour = int(interaction.data.get("values", ["22"])[0])
        await self.build()
        await interaction.response.edit_message(view=self)

    async def _apply(self, interaction: discord.Interaction) -> None:
        if self.start_hour is None or self.end_hour is None:
            await interaction.response.send_message("Pick both start and end.", ephemeral=True)
            return
        if self.start_hour >= self.end_hour:
            await interaction.response.send_message("End must be after start.", ephemeral=True)
            return
        config = await get_guild_config(self.db, self.guild_id)
        bc = make_block_config(config)
        for block in BLOCK_ORDER:
            bs = getattr(bc, f"{block}_start")
            be = getattr(bc, f"{block}_end")
            if self.start_hour < be and self.end_hour > bs:
                await queries.upsert_availability(
                    self.db, self.guild_id, self.user_id, self.day.isoformat(), block
                )
        grid = CalendarGrid(self.db, self.guild_id, self.user_id, self.week_offset)
        await grid.build()
        await interaction.response.edit_message(view=grid)

    async def _back(self, interaction: discord.Interaction) -> None:
        grid = CalendarGrid(self.db, self.guild_id, self.user_id, self.week_offset)
        await grid.build()
        await interaction.response.edit_message(view=grid)


class AvailabilityCog(commands.Cog):
    def __init__(self, bot: GameFinder) -> None:
        self.bot = bot

    @app_commands.command(name="available", description="Mark your availability — tap slots to toggle")
    async def available(self, interaction: discord.Interaction) -> None:
        view = CalendarGrid(
            db=self.bot.db, guild_id=interaction.guild_id, user_id=interaction.user.id,
        )
        await view.build()
        await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(name="available-clear", description="Clear all your availability data")
    async def available_clear(self, interaction: discord.Interaction) -> None:
        await queries.clear_user_availability(self.bot.db, interaction.guild_id, interaction.user.id)
        await queries.clear_user_recurring(self.bot.db, interaction.guild_id, interaction.user.id)
        await interaction.response.send_message("All availability cleared.", ephemeral=True)

    @app_commands.command(name="available-quick", description="Quick-set recurring availability")
    @app_commands.describe(day="Day of week", block="Time block", weeks="Weeks (default 4)")
    @app_commands.choices(
        day=[app_commands.Choice(name=d, value=str(i)) for i, d in enumerate(DAY_NAMES)],
        block=[
            app_commands.Choice(name="AM (Morning)", value="morning"),
            app_commands.Choice(name="MID (Afternoon)", value="afternoon"),
            app_commands.Choice(name="PM (Evening)", value="evening"),
        ],
    )
    async def available_quick(
        self, interaction: discord.Interaction,
        day: app_commands.Choice[str], block: app_commands.Choice[str], weeks: int = 4,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        target = int(day.value)
        today = datetime.date.today()
        count = 0
        for i in range(weeks * 7):
            d = today + datetime.timedelta(days=i)
            if d.weekday() == target:
                await queries.upsert_availability(
                    self.bot.db, interaction.guild_id, interaction.user.id,
                    d.isoformat(), block.value,
                )
                count += 1
        await interaction.followup.send(
            f"Marked **{day.name} {SLOT_LABEL[block.value]}** for {count} weeks.", ephemeral=True
        )

    @app_commands.command(name="timezone", description="Set your timezone")
    @app_commands.describe(tz="Timezone name, e.g. America/New_York, Europe/London")
    async def timezone_set(self, interaction: discord.Interaction, tz: str) -> None:
        if tz not in available_timezones():
            await interaction.response.send_message(
                f"Unknown timezone `{tz}`. Use IANA names like `America/New_York`.", ephemeral=True
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
        config = await get_guild_config(self.bot.db, interaction.guild_id)
        bc = make_block_config(config)
        server_tz = ZoneInfo(config["timezone"])
        count = 0
        for component in cal.walk():
            if component.name not in ("VFREEBUSY", "VEVENT"):
                continue
            dtstart = component.get("dtstart")
            dtend = component.get("dtend")
            if not dtstart or not dtend:
                continue
            start_dt, end_dt = dtstart.dt, dtend.dt
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
                for bn in BLOCK_ORDER:
                    bsh = getattr(bc, f"{bn}_start")
                    beh = getattr(bc, f"{bn}_end")
                    bs = datetime.datetime.combine(current, datetime.time(bsh), tzinfo=server_tz)
                    be = datetime.datetime.combine(current, datetime.time(beh), tzinfo=server_tz)
                    if local_start <= bs and local_end >= be:
                        await queries.upsert_availability(
                            self.bot.db, interaction.guild_id, interaction.user.id,
                            current.isoformat(), bn,
                        )
                        count += 1
                current += datetime.timedelta(days=1)
        await interaction.followup.send(f"Imported {count} blocks from calendar.")


async def setup(bot: GameFinder) -> None:
    await bot.add_cog(AvailabilityCog(bot))
