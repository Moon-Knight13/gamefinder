"""Tests for guild features and DM preferences."""

import pytest

from bot.db import queries

GUILD_ID = 1
USER_ID = 100


@pytest.fixture
async def guild_db(db):
    await queries.ensure_guild(db, GUILD_ID)
    await queries.ensure_user(db, USER_ID)
    return db


# --- Tables exist ---


async def test_feature_tables_created(db):
    rows = await db.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", ()
    )
    names = [r["name"] for r in rows]
    assert "guild_features" in names
    assert "dm_preferences" in names


# --- Feature toggles ---


async def test_feature_enabled_by_default(guild_db):
    for feature in queries.VALID_FEATURES:
        assert await queries.is_feature_enabled(guild_db, GUILD_ID, feature) is True


async def test_disable_feature(guild_db):
    await queries.set_feature(guild_db, GUILD_ID, "games", False)
    assert await queries.is_feature_enabled(guild_db, GUILD_ID, "games") is False


async def test_reenable_feature(guild_db):
    await queries.set_feature(guild_db, GUILD_ID, "games", False)
    await queries.set_feature(guild_db, GUILD_ID, "games", True)
    assert await queries.is_feature_enabled(guild_db, GUILD_ID, "games") is True


async def test_unknown_feature_returns_true(guild_db):
    assert await queries.is_feature_enabled(guild_db, GUILD_ID, "nonexistent") is True


async def test_get_all_features_defaults(guild_db):
    features = await queries.get_all_features(guild_db, GUILD_ID)
    assert len(features) == len(queries.VALID_FEATURES)
    assert all(v is True for v in features.values())


async def test_get_all_features_mixed(guild_db):
    await queries.set_feature(guild_db, GUILD_ID, "widget", False)
    await queries.set_feature(guild_db, GUILD_ID, "reminders", False)
    features = await queries.get_all_features(guild_db, GUILD_ID)
    assert features["widget"] is False
    assert features["reminders"] is False
    assert features["games"] is True


async def test_feature_isolation_between_guilds(guild_db):
    await queries.ensure_guild(guild_db, 2)
    await queries.set_feature(guild_db, GUILD_ID, "games", False)
    assert await queries.is_feature_enabled(guild_db, GUILD_ID, "games") is False
    assert await queries.is_feature_enabled(guild_db, 2, "games") is True


# --- DM preferences ---


async def test_dm_pref_defaults(guild_db):
    prefs = await queries.get_all_dm_prefs(guild_db, GUILD_ID, USER_ID)
    assert prefs["default_player_cap"] == "5"
    assert prefs["default_session_count"] == "8"
    assert prefs["default_player_min"] == "3"
    assert prefs["default_player_max"] == "6"
    assert prefs["default_cadence"] == "weekly"


async def test_set_dm_pref(guild_db):
    await queries.set_dm_pref(guild_db, GUILD_ID, USER_ID, "default_player_cap", "8")
    val = await queries.get_dm_pref(guild_db, GUILD_ID, USER_ID, "default_player_cap")
    assert val == "8"


async def test_dm_pref_overwrite(guild_db):
    await queries.set_dm_pref(guild_db, GUILD_ID, USER_ID, "default_cadence", "biweekly")
    await queries.set_dm_pref(guild_db, GUILD_ID, USER_ID, "default_cadence", "weekly")
    val = await queries.get_dm_pref(guild_db, GUILD_ID, USER_ID, "default_cadence")
    assert val == "weekly"


async def test_dm_pref_isolation_between_users(guild_db):
    await queries.ensure_user(guild_db, 200)
    await queries.set_dm_pref(guild_db, GUILD_ID, USER_ID, "default_player_cap", "10")
    val_other = await queries.get_dm_pref(guild_db, GUILD_ID, 200, "default_player_cap")
    assert val_other == "5"


async def test_dm_pref_isolation_between_guilds(guild_db):
    await queries.ensure_guild(guild_db, 2)
    await queries.set_dm_pref(guild_db, GUILD_ID, USER_ID, "default_player_cap", "10")
    val_other = await queries.get_dm_pref(guild_db, 2, USER_ID, "default_player_cap")
    assert val_other == "5"


async def test_get_all_dm_prefs_mixed(guild_db):
    await queries.set_dm_pref(guild_db, GUILD_ID, USER_ID, "default_player_cap", "7")
    await queries.set_dm_pref(guild_db, GUILD_ID, USER_ID, "default_cadence", "biweekly")
    prefs = await queries.get_all_dm_prefs(guild_db, GUILD_ID, USER_ID)
    assert prefs["default_player_cap"] == "7"
    assert prefs["default_cadence"] == "biweekly"
    assert prefs["default_session_count"] == "8"


async def test_unknown_dm_pref_returns_none(guild_db):
    val = await queries.get_dm_pref(guild_db, GUILD_ID, USER_ID, "nonexistent")
    assert val is None


# --- Data cleanup ---


async def test_delete_user_cleans_dm_prefs(guild_db):
    await queries.set_dm_pref(guild_db, GUILD_ID, USER_ID, "default_player_cap", "10")
    await queries.delete_user_data(guild_db, USER_ID)
    val = await queries.get_dm_pref(guild_db, GUILD_ID, USER_ID, "default_player_cap")
    assert val == "5"


async def test_delete_guild_cleans_features_and_prefs(guild_db):
    await queries.set_feature(guild_db, GUILD_ID, "games", False)
    await queries.set_dm_pref(guild_db, GUILD_ID, USER_ID, "default_player_cap", "10")
    await queries.delete_guild_data(guild_db, GUILD_ID)
    features = await queries.get_all_features(guild_db, GUILD_ID)
    assert all(v is True for v in features.values())
    val = await queries.get_dm_pref(guild_db, GUILD_ID, USER_ID, "default_player_cap")
    assert val == "5"
