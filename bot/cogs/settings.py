from __future__ import annotations

import functools
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.db import queries

if TYPE_CHECKING:
    from bot.bot import GameFinder

log = logging.getLogger(__name__)

FEATURE_DESCRIPTIONS: dict[str, str] = {
    "availability": "Availability tracking (/available, /windows, /whofree)",
    "games": "One-shot game posting and RSVP (/game-create, /games)",
    "campaigns": "Campaign/recurring game system (/campaign-create, etc.)",
    "widget": "Auto-updating dashboard widget (/widget)",
    "reminders": "DM reminders to game creators (24h before)",
    "game_day_pings": "Channel pings on game day",
    "auto_events": "Auto-create Discord Events at quorum",
    "player_pings": "Ping available players when a game is posted",
}

DM_PREF_DESCRIPTIONS: dict[str, str] = {
    "default_player_cap": "Default player cap for games (1-20)",
    "default_session_count": "Default sessions for campaigns (1-52)",
    "default_player_min": "Default min players for campaigns (1-20)",
    "default_player_max": "Default max players for campaigns (1-20)",
    "default_cadence": "Default campaign cadence (weekly or biweekly)",
}


def require_feature(feature: str):
    """Decorator that gates a slash command behind a guild feature toggle."""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            enabled = await queries.is_feature_enabled(
                self.bot.db, interaction.guild_id, feature
            )
            if not enabled:
                await interaction.response.send_message(
                    f"**{feature}** is disabled on this server. "
                    f"An admin can enable it with `/gf-config feature name:{feature} toggle:on`.",
                    ephemeral=True,
                )
                return
            return await func(self, interaction, *args, **kwargs)

        return wrapper

    return decorator


config_group = app_commands.Group(
    name="gf-config",
    description="Configure GameFinder features for this server",
    default_permissions=discord.Permissions(manage_guild=True),
)

prefs_group = app_commands.Group(
    name="gf-prefs",
    description="Set your DM preferences for this server",
)


class SettingsCog(commands.Cog):
    def __init__(self, bot: GameFinder) -> None:
        self.bot = bot
        self.bot.tree.add_command(config_group)
        self.bot.tree.add_command(prefs_group)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(config_group.name)
        self.bot.tree.remove_command(prefs_group.name)

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        log.exception("Settings command error", exc_info=error)
        msg = f"Error: {error}"[:200]
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except discord.HTTPException:
            pass


@config_group.command(name="show", description="View all feature toggles and server settings")
async def config_show(interaction: discord.Interaction) -> None:
    bot = interaction.client
    features = await queries.get_all_features(bot.db, interaction.guild_id)
    config = await queries.get_guild_config(bot.db, interaction.guild_id)
    if not config:
        await queries.ensure_guild(bot.db, interaction.guild_id)
        config = await queries.get_guild_config(bot.db, interaction.guild_id)

    lines = ["**Feature Toggles**"]
    for feat, enabled in features.items():
        icon = "\U0001f7e2" if enabled else "\U0001f534"
        desc = FEATURE_DESCRIPTIONS.get(feat, feat)
        lines.append(f"{icon} **{feat}** — {desc}")

    lines.append("")
    lines.append("**Server Settings**")
    channel_str = (
        f"<#{config['scheduling_channel_id']}>"
        if config.get("scheduling_channel_id")
        else "Not set"
    )
    lines.append(f"Scheduling channel: {channel_str}")
    lines.append(f"Threshold: {config['threshold']} players")
    lines.append(f"Forecast: {config['forecast_weeks']} weeks")
    lines.append(f"Timezone: {config['timezone']}")
    lines.append(
        f"Blocks: {config['morning_start']:02d}-{config['morning_end']:02d} / "
        f"{config['afternoon_start']:02d}-{config['afternoon_end']:02d} / "
        f"{config['evening_start']:02d}-{config['evening_end']:02d}"
    )

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@config_group.command(name="feature", description="Enable or disable a feature")
@app_commands.describe(
    name="Feature to toggle",
    toggle="Turn on or off",
)
@app_commands.choices(
    name=[
        app_commands.Choice(name=f, value=f) for f in sorted(queries.VALID_FEATURES)
    ],
    toggle=[
        app_commands.Choice(name="on", value="on"),
        app_commands.Choice(name="off", value="off"),
    ],
)
async def config_feature(
    interaction: discord.Interaction,
    name: app_commands.Choice[str],
    toggle: app_commands.Choice[str],
) -> None:
    bot = interaction.client
    enabled = toggle.value == "on"
    await queries.set_feature(bot.db, interaction.guild_id, name.value, enabled)
    icon = "\U0001f7e2" if enabled else "\U0001f534"
    desc = FEATURE_DESCRIPTIONS.get(name.value, name.value)
    await interaction.response.send_message(
        f"{icon} **{name.value}** {'enabled' if enabled else 'disabled'}.\n{desc}",
        ephemeral=True,
    )


@prefs_group.command(name="show", description="View your DM preferences for this server")
async def prefs_show(interaction: discord.Interaction) -> None:
    bot = interaction.client
    prefs = await queries.get_all_dm_prefs(
        bot.db, interaction.guild_id, interaction.user.id
    )

    lines = ["**Your DM Preferences**"]
    for key, value in prefs.items():
        desc = DM_PREF_DESCRIPTIONS.get(key, key)
        default = queries.DM_PREF_DEFAULTS.get(key, "")
        default_tag = " *(default)*" if value == default else ""
        lines.append(f"**{key}**: `{value}`{default_tag} — {desc}")

    lines.append("")
    lines.append("Change with `/gf-prefs set key:<name> value:<value>`")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@prefs_group.command(name="set", description="Set a DM preference for this server")
@app_commands.describe(key="Preference to set", value="New value")
@app_commands.choices(
    key=[
        app_commands.Choice(name=k, value=k) for k in sorted(queries.VALID_DM_PREF_KEYS)
    ]
)
async def prefs_set(
    interaction: discord.Interaction,
    key: app_commands.Choice[str],
    value: str,
) -> None:
    bot = interaction.client

    if key.value == "default_cadence":
        if value not in ("weekly", "biweekly"):
            await interaction.response.send_message(
                "Cadence must be `weekly` or `biweekly`.", ephemeral=True
            )
            return
    else:
        try:
            int_val = int(value)
        except ValueError:
            await interaction.response.send_message(
                f"`{key.value}` must be a number.", ephemeral=True
            )
            return
        limits = {
            "default_player_cap": (1, 20),
            "default_session_count": (1, 52),
            "default_player_min": (1, 20),
            "default_player_max": (1, 20),
        }
        lo, hi = limits.get(key.value, (1, 100))
        if not lo <= int_val <= hi:
            await interaction.response.send_message(
                f"`{key.value}` must be {lo}-{hi}.", ephemeral=True
            )
            return
        value = str(int_val)

    await queries.set_dm_pref(
        bot.db, interaction.guild_id, interaction.user.id, key.value, value
    )
    await interaction.response.send_message(
        f"Set **{key.value}** to `{value}`.", ephemeral=True
    )


async def setup(bot: GameFinder) -> None:
    await bot.add_cog(SettingsCog(bot))
