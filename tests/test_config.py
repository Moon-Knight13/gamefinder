"""Tests for bot/config.py."""

import pytest

from bot.config import Config


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "test-token-123")
    monkeypatch.setenv("DB_PATH", "/tmp/test.db")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DEV_MODE", "true")
    config = Config.from_env()
    assert config.token == "test-token-123"
    assert config.db_path == "/tmp/test.db"
    assert config.log_level == "DEBUG"
    assert config.dev_mode is True


def test_config_from_env_defaults(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "tok")
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DEV_MODE", raising=False)
    config = Config.from_env()
    assert config.db_path == "data/gamefinder.db"
    assert config.log_level == "INFO"
    assert config.dev_mode is False


def test_config_missing_token_raises(monkeypatch):
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="DISCORD_TOKEN"):
        Config.from_env()


def test_config_dev_mode_variants(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "tok")
    for val in ("1", "True", "YES", "true", "yes"):
        monkeypatch.setenv("DEV_MODE", val)
        assert Config.from_env().dev_mode is True
    for val in ("0", "false", "no", ""):
        monkeypatch.setenv("DEV_MODE", val)
        assert Config.from_env().dev_mode is False


def test_config_is_frozen():
    config = Config(token="tok")
    with pytest.raises(AttributeError):
        config.token = "new"
