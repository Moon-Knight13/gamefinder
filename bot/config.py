import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    token: str
    db_path: str = "data/gamefinder.db"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        token = os.environ.get("DISCORD_TOKEN", "")
        if not token:
            raise RuntimeError("DISCORD_TOKEN environment variable is required")
        return cls(
            token=token,
            db_path=os.environ.get("DB_PATH", "data/gamefinder.db"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
