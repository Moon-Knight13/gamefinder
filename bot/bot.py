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
            "bot.cogs.admin",
        ]
        for module in cog_modules:
            try:
                await self.load_extension(module)
                log.info("Loaded cog: %s", module)
            except Exception:
                log.exception("Failed to load cog: %s", module)

        from bot.cogs.games import RSVPView

        self.add_view(RSVPView(self.db))

        await self.tree.sync()
        log.info("Command tree synced (global)")

    async def on_ready(self) -> None:
        log.info("GameFinder ready as %s (ID: %s)", self.user, self.user.id if self.user else "?")
        log.info("Guilds: %d", len(self.guilds))
        for guild in self.guilds:
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Guild sync %s: %d commands", guild.name, len(synced))
