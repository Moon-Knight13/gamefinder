import pytest

from bot.db.database import Database


@pytest.fixture
async def db():
    database = await Database.connect(":memory:")
    await database.migrate()
    yield database
    await database.close()
