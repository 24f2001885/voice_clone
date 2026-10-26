"""Unit tests for ModelManager lifecycle, single-resident invariant, and memory guarding."""

import threading
from typing import Any

import pytest

from voxclone.config import AppConfig
from voxclone.engines.base import ModelEngine
from voxclone.engines.fake_engines import get_loaded_fake_engines
from voxclone.engines.model_manager import ModelManager
from voxclone.errors import ChunkOutOfMemoryError, InsufficientVramError, InternalError
from voxclone.storage.db import get_db
from voxclone.storage.model_events_repo import list_events


def test_model_manager_single_resident_invariant(model_manager: ModelManager) -> None:
    """Verify that switching between all 6 model pairs strictly enforces <= 1 resident model."""
    pairs = [
        ("tts", "vc"),
        ("vc", "emotion"),
        ("emotion", "tts"),
        ("tts", "emotion"),
        ("emotion", "vc"),
        ("vc", "tts"),
    ]

    for first, second in pairs:
        e1 = model_manager.acquire(first)
        assert e1.is_loaded
        assert model_manager.resident_key == first
        # Verify fake registry has exactly 1 loaded engine
        loaded = get_loaded_fake_engines()
        assert len(loaded) == 1
        assert e1 in loaded

        # Switch to second model
        e2 = model_manager.acquire(second)
        assert not e1.is_loaded
        assert e2.is_loaded
        assert model_manager.resident_key == second

        loaded = get_loaded_fake_engines()
        assert len(loaded) == 1
        assert e2 in loaded
        assert e1 not in loaded


def test_model_manager_acquire_same_model_idempotent(model_manager: ModelManager) -> None:
    """Acquiring the currently resident model must return existing instance without reloading."""
    e1 = model_manager.acquire("tts")
    assert getattr(e1, "load_count", 1) == 1

    e2 = model_manager.acquire("tts")
    assert e1 is e2
    assert getattr(e1, "load_count", 1) == 1


def test_model_manager_invalid_key_rejected(model_manager: ModelManager) -> None:
    """Attempting to acquire an unrecognized model key raises InternalError."""
    with pytest.raises(InternalError) as exc_info:
        model_manager.acquire("non_existent_engine")
    assert "Invalid model key" in str(exc_info.value)


def test_model_manager_free_gpu_memory(model_manager: ModelManager) -> None:
    """Manual free_gpu_memory must unload resident model and evacuate registry."""
    model_manager.acquire("vc")
    assert model_manager.resident_key == "vc"
    assert len(get_loaded_fake_engines()) == 1

    res = model_manager.free_gpu_memory()
    assert res["unloaded_key"] == "vc"
    assert model_manager.resident_key is None
    assert model_manager.resident_engine is None
    assert len(get_loaded_fake_engines()) == 0


def test_model_manager_keep_warm_policy_respect(app_config: AppConfig) -> None:
    """When keep_warm is False, release() must immediately unload the model."""
    # Test with keep_warm=False
    cfg_cold = AppConfig(
        **{**app_config.__dict__, "env_overrides": {**app_config.env_overrides, "keep_warm": False}}
    )
    mgr_cold = ModelManager(config=cfg_cold, db_path=app_config.db_path)

    with mgr_cold.use("tts") as eng:
        assert eng.is_loaded
        assert mgr_cold.resident_key == "tts"

    # Exiting context manager triggers release -> unloads because keep_warm=False
    assert mgr_cold.resident_key is None
    assert len(get_loaded_fake_engines()) == 0
    mgr_cold.close()


def test_model_manager_keep_warm_true_retains_model(app_config: AppConfig) -> None:
    """When keep_warm is True, release() retains model in memory for subsequent tasks."""
    cfg_warm = AppConfig(
        **{**app_config.__dict__, "env_overrides": {**app_config.env_overrides, "keep_warm": True}}
    )
    mgr_warm = ModelManager(config=cfg_warm, db_path=app_config.db_path)

    with mgr_warm.use("emotion") as eng:
        assert eng.is_loaded
        assert mgr_warm.resident_key == "emotion"

    # Model stays resident after exiting context
    assert mgr_warm.resident_key == "emotion"
    assert len(get_loaded_fake_engines()) == 1
    mgr_warm.close()


def test_model_manager_events_logged_to_sqlite(model_manager: ModelManager, app_config: AppConfig) -> None:
    """Model load and unload operations must append records to SQLite model_events table."""
    model_manager.acquire("tts")
    model_manager.acquire("vc")
    model_manager.free_gpu_memory()

    with get_db(app_config.db_path) as conn:
        events = list_events(conn, limit=10)

    actions = [ev.action for ev in reversed(events)]
    # Expected sequence: load(tts) -> unload(tts) -> load(vc) -> unload(vc)
    assert actions == ["load", "unload", "load", "unload"]


def test_model_manager_budget_guard_rejection(app_config: AppConfig, monkeypatch: pytest.MonkeyPatch) -> None:
    """If model estimated VRAM exceeds configured budget, raise InsufficientVramError (VX-300)."""
    # Set low budget (50 MB) where FakeEngine estimated VRAM (100 MB) exceeds it
    cfg_tiny = AppConfig(
        **{**app_config.__dict__, "env_overrides": {**app_config.env_overrides, "vram_budget_mb": 50}}
    )
    mgr = ModelManager(config=cfg_tiny, db_path=app_config.db_path)
    # Monkeypatch device and free memory probe
    monkeypatch.setattr(mgr, "_resolved_device", "cuda")
    monkeypatch.setattr(mgr, "get_vram_info", lambda: (8000, 4000, 4000))

    # Fake TTS estimated MB is 100 > 50 MB budget
    with pytest.raises(InsufficientVramError) as exc_info:
        mgr.acquire("tts")
    assert exc_info.value.code == "VX-300"
    mgr.close()




def test_model_manager_thread_safety_stress(model_manager: ModelManager) -> None:
    """Multiple threads concurrently acquiring models must not corrupt residency invariant."""
    errors: list[Exception] = []

    def worker(key: str) -> None:
        try:
            for _ in range(5):
                eng = model_manager.acquire(key)
                assert eng.is_loaded
                assert len(get_loaded_fake_engines()) <= 1
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("tts",)),
        threading.Thread(target=worker, args=("vc",)),
        threading.Thread(target=worker, args=("emotion",)),
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert not errors
    assert len(get_loaded_fake_engines()) <= 1
