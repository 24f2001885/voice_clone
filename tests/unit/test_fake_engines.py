"""Unit tests verifying FakeTts, FakeVc, FakeEmotion behavior, registry, and failure injection."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from voxclone.engines.base import EmotionEngine, ModelEngine, TtsEngine, VcEngine
from voxclone.engines.fake_engines import (
    FakeEmotion,
    FakeTts,
    FakeVc,
    get_loaded_fake_engines,
    reset_fake_registry,
)
from voxclone.errors import InternalError


def test_fake_engine_protocols() -> None:
    """Verify fake engines satisfy runtime-checkable ModelEngine protocols."""
    tts = FakeTts()
    vc = FakeVc()
    emotion = FakeEmotion()

    assert isinstance(tts, ModelEngine)
    assert isinstance(tts, TtsEngine)
    assert isinstance(vc, ModelEngine)
    assert isinstance(vc, VcEngine)
    assert isinstance(emotion, ModelEngine)
    assert isinstance(emotion, EmotionEngine)


def test_fake_engine_registry_lifecycle() -> None:
    """Verify registry tracks loaded fake instances."""
    reset_fake_registry()
    assert len(get_loaded_fake_engines()) == 0

    tts = FakeTts()
    tts.load("cpu")
    assert tts in get_loaded_fake_engines()
    assert len(get_loaded_fake_engines()) == 1

    tts.unload()
    assert tts not in get_loaded_fake_engines()
    assert len(get_loaded_fake_engines()) == 0


def test_fake_tts_synthesis() -> None:
    """Verify FakeTts synthesizes expected tone duration and amplitude."""
    tts = FakeTts()
    # Attempting to synthesize while unloaded raises InternalError
    with pytest.raises(InternalError):
        tts.synthesize("test", Path("ref.wav"), 0.5)

    tts.load("cpu")
    audio = tts.synthesize("Hello world! This is a test sentence.", Path("ref.wav"), expressiveness=0.8)
    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    assert len(audio) > 0
    assert np.max(np.abs(audio)) <= 1.0


def test_fake_vc_duration_matching(tmp_path: Path, write_wav: Any) -> None:
    """Verify FakeVc matches input WAV duration and RMS energy."""
    in_sr = 16000
    in_duration_sec = 2.5
    t = np.linspace(0, in_duration_sec, int(in_duration_sec * in_sr), endpoint=False, dtype=np.float32)
    in_audio = (0.5 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)

    in_wav_path = write_wav(tmp_path / "in.wav", in_audio, in_sr)
    ref_wav_path = write_wav(tmp_path / "ref.wav", in_audio, in_sr)

    vc = FakeVc()
    vc.load("cpu")
    out_audio = vc.convert(in_wav_path, ref_wav_path)

    out_duration_sec = len(out_audio) / vc.sample_rate
    assert pytest.approx(out_duration_sec, rel=1e-2) == in_duration_sec


def test_fake_emotion_deterministic_classification() -> None:
    """Verify keyword mapping of FakeEmotion."""
    emotion = FakeEmotion()
    emotion.load("cpu")

    texts = ["I am thrilled!", "Is this real?", "I feel so sad and cry", "I hate this angry bug", "Just checking in"]
    labels = emotion.classify(texts)
    assert labels == ["joy", "surprise", "sadness", "anger", "neutral"]


def test_fake_engine_failure_injection() -> None:
    """Verify oom_once and fail_on_call failure injection modes."""
    # OOM once
    tts_oom = FakeTts(oom_once=True)
    tts_oom.load("cpu")
    with pytest.raises(RuntimeError) as exc_info:
        tts_oom.synthesize("test", Path("ref.wav"), 0.5)
    assert "out of memory" in str(exc_info.value).lower()

    # Second call succeeds
    second_audio = tts_oom.synthesize("test", Path("ref.wav"), 0.5)
    assert len(second_audio) > 0

    # Fail on call
    tts_fail = FakeTts(fail_on_call={2})
    tts_fail.load("cpu")
    tts_fail.synthesize("1", Path("ref.wav"), 0.5)
    with pytest.raises(RuntimeError) as exc_info2:
        tts_fail.synthesize("2", Path("ref.wav"), 0.5)
    assert "simulated failure on call #2" in str(exc_info2.value)
