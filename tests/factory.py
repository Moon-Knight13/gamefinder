"""Test data factory for GameFinder. Generates realistic TTRPG scenarios."""

from __future__ import annotations

import datetime
import random
from dataclasses import dataclass, field

from bot.db import queries
from bot.db.database import Database

GUILD_ID = 1


@dataclass
class MockPlayer:
    user_id: int
    name: str
    timezone: str = "America/New_York"
    preferred_days: list[int] = field(default_factory=lambda: [4, 5])
    preferred_blocks: list[str] = field(default_factory=lambda: ["evening"])
    reliability: float = 0.85


class Factory:
    """Create test scenarios with realistic data."""

    def __init__(self, db: Database, guild_id: int = GUILD_ID) -> None:
        self.db = db
        self.guild_id = guild_id
        self._uid_counter = 200000
        self._players: list[MockPlayer] = []

    def _next_uid(self) -> int:
        self._uid_counter += 1
        return self._uid_counter

    async def setup_guild(self, timezone: str = "UTC", threshold: int = 4) -> None:
        await queries.ensure_guild(self.db, self.guild_id)
        await queries.update_guild_config(
            self.db, self.guild_id, timezone=timezone, threshold=threshold
        )

    async def create_player(
        self,
        name: str | None = None,
        timezone: str = "America/New_York",
        preferred_days: list[int] | None = None,
        preferred_blocks: list[str] | None = None,
        reliability: float = 0.85,
    ) -> MockPlayer:
        uid = self._next_uid()
        player = MockPlayer(
            user_id=uid,
            name=name or f"Player_{uid}",
            timezone=timezone,
            preferred_days=preferred_days or [4, 5],
            preferred_blocks=preferred_blocks or ["evening"],
            reliability=reliability,
        )
        await queries.ensure_user(self.db, uid)
        await queries.set_user_timezone(self.db, uid, timezone)
        self._players.append(player)
        return player

    async def create_party(
        self, size: int = 5, archetype: str = "weekend_evening"
    ) -> list[MockPlayer]:
        """Create a party with common availability patterns."""
        archetypes = {
            "weekend_evening": {"days": [4, 5], "blocks": ["evening"]},
            "weeknight": {"days": [1, 2, 3], "blocks": ["evening"]},
            "weekend_all_day": {"days": [5, 6], "blocks": ["morning", "afternoon", "evening"]},
            "scattered": {
                "days": [0, 1, 2, 3, 4, 5, 6],
                "blocks": ["morning", "afternoon", "evening"],
            },
        }
        config = archetypes.get(archetype, archetypes["weekend_evening"])
        players = []
        for _i in range(size):
            # Each player varies slightly from archetype
            days = list(config["days"])
            if random.random() < 0.3 and len(days) > 1:
                days.pop(random.randint(0, len(days) - 1))
            player = await self.create_player(
                preferred_days=days,
                preferred_blocks=list(config["blocks"]),
                reliability=random.uniform(0.7, 0.95),
            )
            players.append(player)
        return players

    async def fill_availability(
        self,
        players: list[MockPlayer] | None = None,
        weeks: int = 3,
        start: datetime.date | None = None,
    ) -> int:
        """Generate availability entries based on player preferences."""
        players = players or self._players
        start = start or datetime.date.today()
        count = 0
        for i in range(weeks * 7):
            d = start + datetime.timedelta(days=i)
            for player in players:
                if d.weekday() in player.preferred_days and random.random() < player.reliability:
                    for block in player.preferred_blocks:
                        await queries.upsert_availability(
                            self.db,
                            self.guild_id,
                            player.user_id,
                            d.isoformat(),
                            block,
                        )
                        count += 1
        return count

    async def fill_recurring(
        self,
        players: list[MockPlayer] | None = None,
    ) -> int:
        """Set recurring patterns matching player preferences."""
        players = players or self._players
        count = 0
        for player in players:
            for day in player.preferred_days:
                for block in player.preferred_blocks:
                    await queries.set_recurring(self.db, self.guild_id, player.user_id, day, block)
                    count += 1
        return count

    async def create_game(
        self,
        creator: MockPlayer,
        title: str = "Test Oneshot",
        date: str | None = None,
        block: str = "evening",
        player_cap: int = 5,
    ) -> int:
        date = date or (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
        return await queries.create_game(
            self.db,
            guild_id=self.guild_id,
            creator_id=creator.user_id,
            title=title,
            description=f"A game by {creator.name}",
            slot_date=date,
            slot_block=block,
            player_cap=player_cap,
        )

    async def rsvp_players(
        self,
        game_id: int,
        going: list[MockPlayer] | None = None,
        maybe: list[MockPlayer] | None = None,
        spectators: list[MockPlayer] | None = None,
        waitlist: list[MockPlayer] | None = None,
    ) -> dict[str, int]:
        """RSVP multiple players to a game."""
        counts = {"going": 0, "maybe": 0, "spectator": 0, "waitlist": 0}
        for player in going or []:
            await queries.upsert_rsvp(self.db, game_id, player.user_id, "going")
            counts["going"] += 1
        for player in maybe or []:
            await queries.upsert_rsvp(self.db, game_id, player.user_id, "maybe")
            counts["maybe"] += 1
        for player in spectators or []:
            await queries.upsert_rsvp(self.db, game_id, player.user_id, "spectator")
            counts["spectator"] += 1
        for player in waitlist or []:
            await queries.upsert_rsvp(self.db, game_id, player.user_id, "waitlist")
            counts["waitlist"] += 1
        return counts

    async def create_campaign(
        self,
        creator: MockPlayer,
        title: str = "Test Campaign",
        day_of_week: int = 5,
        block: str = "evening",
        session_count: int = 8,
        player_max: int = 6,
    ) -> int:
        return await queries.create_campaign(
            self.db,
            self.guild_id,
            creator.user_id,
            title=title,
            description=f"Campaign by {creator.name}",
            day_of_week=day_of_week,
            block=block,
            session_count=session_count,
            player_max=player_max,
        )

    async def fill_roster(
        self,
        campaign_id: int,
        players: list[MockPlayer],
    ) -> int:
        count = 0
        for player in players:
            added = await queries.add_to_roster(self.db, campaign_id, player.user_id)
            if added:
                count += 1
        return count
