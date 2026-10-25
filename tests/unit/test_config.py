"""Unit tests verifying AppConfig validation, defaults, and environment overrides."""

import pytest

from voxclone.config import load_config
from voxclone.errors import InternalError, VoxcloneError


def test_config_defaults() -> None:
    """Verify load_config returns expected defaults with empty environment."""
    cfg = load_config({})
    assert cfg.data_dir.as_posix() == "/app/data"
    assert cfg.profiles_dir.as_posix() == "/app/profiles"
    assert cfg.outputs_dir.as_posix() == "/app/outputs"
    assert cfg.inputs_dir.as_posix() == "/app/inputs"
    assert cfg.engine_mode == "real"
    assert cfg.log_level == "INFO"
    assert cfg.require_consent is True
    assert cfg.plain_mode is False
    assert cfg.no_color is False
    assert cfg.env_overrides == {}


def test_config_invalid_engine_mode() -> None:
    """Verify invalid engine_mode is rejected with VoxcloneError."""
    with pytest.raises(VoxcloneError):
        load_config({"VOXCLONE_ENGINE": "banana"})


def test_config_invalid_log_level() -> None:
    """Verify invalid log_level is rejected with VoxcloneError."""
    with pytest.raises(VoxcloneError):
        load_config({"VOXCLONE_LOG_LEVEL": "ULTRA_VERBOSE"})


def test_config_consent_requirement_immutable() -> None:
    """Verify VOXCLONE_REQUIRE_CONSENT cannot be disabled."""
    with pytest.raises(InternalError) as exc_info:
        load_config({"VOXCLONE_REQUIRE_CONSENT": "0"})
    assert "Consent requirement cannot be disabled" in str(exc_info.value)

    with pytest.raises(InternalError):
        load_config({"VOXCLONE_REQUIRE_CONSENT": "false"})


def test_config_chunk_bounds_validation() -> None:
    """Verify chunk_min_sec >= chunk_max_sec raises VoxcloneError."""
    with pytest.raises(VoxcloneError):
        load_config({
            "VOXCLONE_CHUNK_MIN_SEC": "6.0",
            "VOXCLONE_CHUNK_MAX_SEC": "4.0",
        })


def test_config_tunable_env_overrides() -> None:
    """Verify only explicitly provided tunables are extracted into env_overrides."""
    cfg = load_config({
        "VOXCLONE_WORKERS": "4",
        "VOXCLONE_DEVICE": "cuda",
        "VOXCLONE_VRAM_BUDGET_MB": "5500",
        "VOXCLONE_KEEP_WARM": "true",
    })
    assert cfg.env_overrides == {
        "workers": 4,
        "device": "cuda",
        "vram_budget_mb": 5500,
        "keep_warm": True,
    }
