"""Unit tests covering settings repository and SettingsService validation rules."""

from pathlib import Path
import sqlite3

import pytest

from voxclone.config import AppConfig, load_config
from voxclone.constants import DEFAULT_SETTINGS
from voxclone.errors import InternalError, VoxcloneError
from voxclone.services.settings_service import SettingsService
from voxclone.storage import settings_repo


def test_settings_repo_roundtrip(db_conn: sqlite3.Connection) -> None:
    """Verify repository accurately persists and deserializes typed values."""
    settings_repo.set_setting(db_conn, "test_int", 42)
    assert settings_repo.get_setting(db_conn, "test_int") == 42

    settings_repo.set_setting(db_conn, "test_float", 3.1415)
    assert settings_repo.get_setting(db_conn, "test_float") == 3.1415

    settings_repo.set_setting(db_conn, "test_bool_true", True)
    assert settings_repo.get_setting(db_conn, "test_bool_true") is True

    settings_repo.set_setting(db_conn, "test_bool_false", False)
    assert settings_repo.get_setting(db_conn, "test_bool_false") is False

    settings_repo.set_setting(db_conn, "test_str", "voxclone")
    assert settings_repo.get_setting(db_conn, "test_str") == "voxclone"

    # Default fallback for missing key
    assert settings_repo.get_setting(db_conn, "missing_key", default="fallback") == "fallback"

    # Deletion
    assert settings_repo.delete_setting(db_conn, "test_str") is True
    assert settings_repo.get_setting(db_conn, "test_str") is None
    assert settings_repo.delete_setting(db_conn, "test_str") is False


def test_settings_repo_upsert_uniqueness(db_conn: sqlite3.Connection) -> None:
    """Verify set_setting performs upsert without creating duplicate rows."""
    settings_repo.set_setting(db_conn, "workers", 2)
    settings_repo.set_setting(db_conn, "workers", 8)

    cursor = db_conn.execute("SELECT COUNT(*) AS c FROM app_settings WHERE key = 'workers';")
    assert cursor.fetchone()["c"] == 1
    assert settings_repo.get_setting(db_conn, "workers") == 8


def test_settings_service_validation(db_conn: sqlite3.Connection, app_config: AppConfig) -> None:
    """Verify SettingsService enforces constraints and boundary rules."""
    service = SettingsService(db_conn, app_config)

    # Valid updates
    assert service.set("device", "cuda") == "cuda"
    assert service.set("workers", 4) == 4
    assert service.set("crossfade_ms", 50) == 50
    assert service.set("default_output_mode", "save") == "save"
    assert service.set("keep_warm", False) is False
    assert service.set("vram_budget_mb", 7000) == 7000
    assert service.set("sentence_max_chars", 150) == 150

    # Invalid updates: device
    with pytest.raises(VoxcloneError):
        service.set("device", "invalid_dev")

    # Invalid updates: workers < 0
    with pytest.raises(VoxcloneError):
        service.set("workers", -1)

    # Invalid updates: chunk bounds
    with pytest.raises(VoxcloneError):
        service.set("chunk_min_sec", 0.5)  # Under 1.0

    with pytest.raises(VoxcloneError):
        service.set("chunk_max_sec", 20.0)  # Over 15.0

    # chunk_min_sec must stay strictly below chunk_max_sec
    service.set("chunk_max_sec", 4.0)
    with pytest.raises(VoxcloneError):
        service.set("chunk_min_sec", 4.5)

    # Unknown key
    with pytest.raises(VoxcloneError):
        service.set("unknown_key", "value")


def test_settings_service_env_override_lock(db_conn: sqlite3.Connection, tmp_path: Path) -> None:
    """Verify that environment variable overrides take precedence and lock settings."""
    env = {
        "VOXCLONE_DATA_DIR": str(tmp_path / "data"),
        "VOXCLONE_PROFILES_DIR": str(tmp_path / "profiles"),
        "VOXCLONE_OUTPUTS_DIR": str(tmp_path / "outputs"),
        "VOXCLONE_INPUTS_DIR": str(tmp_path / "inputs"),
        "VOXCLONE_WORK_DIR": str(tmp_path / "work"),
        "VOXCLONE_ENGINE": "fake",
        "VOXCLONE_WORKERS": "12",  # Override
    }
    cfg = load_config(env)
    service = SettingsService(db_conn, cfg)

    all_settings = service.get_all()
    assert all_settings["workers"].value == 12
    assert all_settings["workers"].source == "env"
    assert all_settings["workers"].locked is True

    # Attempting to mutate locked setting must raise InternalError (VX-900)
    with pytest.raises(InternalError) as exc_info:
        service.set("workers", 4)
    assert "locked by environment" in str(exc_info.value)


def test_settings_service_reset_and_ensure_defaults(
    db_conn: sqlite3.Connection,
    app_config: AppConfig,
) -> None:
    """Verify reset_defaults and ensure_defaults behavior."""
    service = SettingsService(db_conn, app_config)

    # Change settings
    service.set("workers", 6)
    assert service.get("workers") == 6

    # Reset
    service.reset_defaults()
    assert service.get("workers") == DEFAULT_SETTINGS["workers"]

    # Delete one key and call ensure_defaults
    settings_repo.delete_setting(db_conn, "crossfade_ms")
    assert settings_repo.get_setting(db_conn, "crossfade_ms") is None

    service.ensure_defaults()
    assert settings_repo.get_setting(db_conn, "crossfade_ms") == DEFAULT_SETTINGS["crossfade_ms"]
