from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from bot.config import Config
    from bot.db.database import Database

log = logging.getLogger(__name__)


class GameFinder(commands.Bot):
    def __init__(self, config: Config, db: Database) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.config = config
        self.db = db

    async def setup_hook(self) -> None:
        cog_modules = [
            "bot.cogs.availability",
            "bot.cogs.windows",
            "bot.cogs.games",
            "bot.cogs.campaigns",
            "bot.cogs.admin",
        ]
        for module in cog_modules:
            try:
                await self.load_extension(module)
                log.info("Loaded cog: %s", module)
            except Exception:
                log.exception("Failed to load cog: %s", module)

        from bot.cogs.campaigns import RosterView
        from bot.cogs.games import RSVPView

        self.add_view(RSVPView(self.db))
        self.add_view(RosterView(self.db))

        await self.tree.sync()
        log.info("Command tree synced (global)")

    async def setup_hook_error_handlers(self) -> None:
        @self.tree.error
        async def on_app_command_error(
            interaction: discord.Interaction,
            error: discord.app_commands.AppCommandError,
        ) -> None:
            log.exception(
                "Command error in /%s",
                interaction.command.name if interaction.command else "unknown",
                exc_info=error,
            )
            msg = f"Something went wrong: {error}"
            if len(msg) > 200:
                msg = msg[:200] + "..."
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
            except discord.HTTPException:
                pass

    async def on_ready(self) -> None:
        log.info("GameFinder ready as %s (ID: %s)", self.user, self.user.id if self.user else "?")
        log.info("Guilds: %d", len(self.guilds))
        await self.setup_hook_error_handlers()

        from bot.scheduler import setup_scheduler

        self._scheduler = setup_scheduler(self)
        self._scheduler.start()
        log.info("Scheduler started (%d jobs)", len(self._scheduler.get_jobs()))

        for guild in self.guilds:
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Guild sync %s: %d commands", guild.name, len(synced))
