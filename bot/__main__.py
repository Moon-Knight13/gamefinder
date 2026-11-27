import asyncio
import logging
from pathlib import Path

from bot.bot import GameFinder
from bot.config import Config
from bot.db.database import Database


async def main() -> None:
    config = Config.from_env()
    logging.basicConfig(level=getattr(logging, config.log_level))

    db_dir = Path(config.db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)

    db = await Database.connect(config.db_path)
    await db.migrate()

    bot = GameFinder(config, db)
    try:
        await bot.start(config.token)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
