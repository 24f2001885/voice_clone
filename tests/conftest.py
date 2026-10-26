"""Shared pytest fixtures, test environment monkeypatching, and synthetic audio generators."""

from collections.abc import Generator
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest
import soundfile as sf

from voxclone.config import AppConfig, load_config, reset_config_cache
from voxclone.engines.fake_engines import reset_fake_registry
from voxclone.storage.db import connect
from voxclone.storage.migrate import apply_migrations
from voxclone.ui import session
from voxclone.ui.session import SessionState


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers to prevent pytest warnings."""
    config.addinivalue_line("markers", "gpu: requires NVIDIA GPU hardware and PyTorch CUDA")
    config.addinivalue_line("markers", "e2e: end-to-end interactive terminal tests")


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Force fake engine mode and route all storage directories to temporary folder."""
    data_dir = tmp_path / "data"
    profiles_dir = tmp_path / "profiles"
    outputs_dir = tmp_path / "outputs"
    inputs_dir = tmp_path / "inputs"
    work_dir = data_dir / "work"

    monkeypatch.setenv("VOXCLONE_ENGINE", "fake")
    monkeypatch.setenv("VOXCLONE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("VOXCLONE_PROFILES_DIR", str(profiles_dir))
    monkeypatch.setenv("VOXCLONE_OUTPUTS_DIR", str(outputs_dir))
    monkeypatch.setenv("VOXCLONE_INPUTS_DIR", str(inputs_dir))
    monkeypatch.setenv("VOXCLONE_WORK_DIR", str(work_dir))
    monkeypatch.setenv("VOXCLONE_REQUIRE_CONSENT", "1")
    monkeypatch.setenv("VOXCLONE_PLAIN", "1")
    monkeypatch.setenv("NO_COLOR", "1")

    reset_config_cache()
    reset_fake_registry()
    yield
    reset_config_cache()
    reset_fake_registry()


@pytest.fixture
def app_config() -> AppConfig:
    """Return an AppConfig bound to the isolated temporary environment."""
    return load_config()


@pytest.fixture
def db_conn(app_config: AppConfig) -> Generator[Any, None, None]:
    """Provide an initialized SQLite connection with all migrations applied."""
    conn = connect(app_config.db_path)
    apply_migrations(conn, app_config.migrations_dir)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def session_state(app_config: AppConfig) -> Generator[SessionState, None, None]:
    """Provide a bootstrapped SessionState instance with plain output enabled."""
    state = session.bootstrap(debug=True, plain=True)
    try:
        yield state
    finally:
        session.close(state)


class SpeechArray(np.ndarray):
    """Numpy array subclass carrying known silence gap intervals."""

    gaps: list[tuple[float, float]]


@pytest.fixture
def make_speech() -> Callable[..., SpeechArray]:
    """Factory fixture generating synthetic speech bursts with known silence gaps."""

    def _factory(
        duration_sec: float = 10.0,
        gap_sec: float = 0.3,
        sr: int = 16000,
        seed: int = 0,
    ) -> SpeechArray:
        rng = np.random.default_rng(seed)
        samples: list[np.ndarray] = []
        gaps: list[tuple[float, float]] = []

        current_time_sec = 0.0
        while current_time_sec < duration_sec:
            # Word burst: 0.2 to 0.6 seconds at varying pitch (120 to 300 Hz)
            word_dur = float(rng.uniform(0.2, 0.6))
            if current_time_sec + word_dur > duration_sec:
                word_dur = duration_sec - current_time_sec

            if word_dur > 0.01:
                num_samples = int(word_dur * sr)
                freq = float(rng.uniform(120.0, 300.0))
                t = np.linspace(0, word_dur, num_samples, endpoint=False, dtype=np.float32)
                # Apply Hann window envelope to avoid boundary clicks
                envelope = np.hanning(num_samples).astype(np.float32)
                wave = (0.7 * np.sin(2 * np.pi * freq * t) * envelope).astype(np.float32)
                samples.append(wave)
                current_time_sec += word_dur

            # Silence gap: exact digital zero
            if current_time_sec + gap_sec < duration_sec:
                num_gap_samples = int(gap_sec * sr)
                gap_wave = np.zeros(num_gap_samples, dtype=np.float32)
                gap_start = current_time_sec
                gap_end = current_time_sec + gap_sec
                gaps.append((round(gap_start, 3), round(gap_end, 3)))
                samples.append(gap_wave)
                current_time_sec += gap_sec

        full_audio = np.concatenate(samples) if samples else np.zeros(int(duration_sec * sr), dtype=np.float32)
        target_len = int(duration_sec * sr)
        if len(full_audio) < target_len:
            pad = np.zeros(target_len - len(full_audio), dtype=np.float32)
            full_audio = np.concatenate([full_audio, pad])
        elif len(full_audio) > target_len:
            full_audio = full_audio[:target_len]

        res = full_audio.view(SpeechArray)
        res.gaps = gaps
        return res

    return _factory


@pytest.fixture
def write_wav() -> Callable[[Path, np.ndarray, int], Path]:
    """Helper fixture to write floating-point numpy array to a PCM WAV file."""

    def _writer(path: Path, data: np.ndarray, sr: int = 24000) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), data, sr, subtype="PCM_16")
        return path

    return _writer


@pytest.fixture
def model_manager(app_config: AppConfig, db_conn: Any) -> Generator[Any, None, None]:
    """Provide an isolated ModelManager instance."""
    from voxclone.engines.model_manager import ModelManager

    mgr = ModelManager(config=app_config, db_path=app_config.db_path)
    try:
        yield mgr
    finally:
        mgr.close()


@pytest.fixture
def profile_service(app_config: AppConfig, db_conn: Any) -> Any:
    """Provide a configured ProfileService instance."""
    from voxclone.services.profile_service import ProfileService

    return ProfileService(db_path=app_config.db_path, profiles_dir=app_config.profiles_dir)


@pytest.fixture
def reference_wav(tmp_path: Path, make_speech: Callable[..., SpeechArray], write_wav: Callable[..., Path]) -> Path:
    """Provide a valid 15-second synthetic speech reference WAV file."""
    audio = make_speech(duration_sec=15.0, gap_sec=0.2, sr=24000)
    target = tmp_path / "reference_speech.wav"
    return write_wav(target, audio, sr=24000)


@pytest.fixture
def make_profile(profile_service: Any, reference_wav: Path) -> Callable[[str], Any]:
    """Factory fixture to quickly create and enroll an active test voice profile."""

    def _factory(name: str = "TestVoice") -> Any:
        prepared = profile_service.prepare_from_file(reference_wav)
        return profile_service.save_profile(name=name, prepared=prepared, consent_confirmed=True)

    return _factory

