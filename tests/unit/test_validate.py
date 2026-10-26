"""Unit tests for audio validation, SNR computation, and reference cleaning."""

from typing import Callable

import numpy as np
import pytest

from voxclone.audio.validate import (
    SampleReport,
    analyze_sample,
    clean_reference,
)
from voxclone.constants import MIN_SAMPLE_SPEECH_SEC, REFERENCE_SAMPLE_RATE
from voxclone.errors import NoSpeechDetectedError, SampleTooShortError
from tests.conftest import SpeechArray


def test_analyze_pure_silence_raises_no_speech() -> None:
    """Pure silence array must raise NoSpeechDetectedError (VX-210)."""
    silent_audio = np.zeros(24000 * 12, dtype=np.float32)
    with pytest.raises(NoSpeechDetectedError) as exc_info:
        analyze_sample(silent_audio, sample_rate=24000)
    assert exc_info.value.code == "VX-210"


def test_analyze_empty_array_raises_no_speech() -> None:
    """Empty audio array must raise NoSpeechDetectedError."""
    with pytest.raises(NoSpeechDetectedError):
        analyze_sample(np.zeros(0, dtype=np.float32), sample_rate=24000)


def test_analyze_sample_under_10s_speech_raises_too_short(make_speech: Callable[..., SpeechArray]) -> None:
    """Audio containing less than 10.0 seconds of speech must raise SampleTooShortError (VX-101)."""
    # 5.0 seconds of speech burst
    short_speech = make_speech(duration_sec=5.0, gap_sec=0.1, sr=24000)
    with pytest.raises(SampleTooShortError) as exc_info:
        analyze_sample(short_speech, sample_rate=24000)
    assert exc_info.value.code == "VX-101"
    assert "10.0 s" in str(exc_info.value)


def test_analyze_sample_valid_speech_passes(make_speech: Callable[..., SpeechArray]) -> None:
    """Clean 15-second synthetic speech must produce an acceptable SampleReport."""
    clean_audio = make_speech(duration_sec=15.0, gap_sec=0.15, sr=24000)
    report = analyze_sample(clean_audio, sample_rate=24000)

    assert isinstance(report, SampleReport)
    assert report.duration_sec >= 14.5
    assert report.speech_sec >= MIN_SAMPLE_SPEECH_SEC
    assert report.peak > 0.1
    assert report.clipping_ratio < 0.01
    assert report.quality_score >= 0.50
    assert report.acceptable is True


def test_analyze_sample_clipping_detection(make_speech: Callable[..., SpeechArray]) -> None:
    """Intentionally clipped audio must reflect elevated clipping ratio and warning note."""
    audio = make_speech(duration_sec=12.0, gap_sec=0.1, sr=24000)
    # Intentionally hard-clip 50% of the signal
    clipped = np.clip(audio * 3.0, -1.0, 1.0)

    report = analyze_sample(clipped, sample_rate=24000)
    assert report.clipping_ratio > 0.01
    assert any("clipping" in note.lower() for note in report.notes)


def test_clean_reference_normalization_and_trimming(make_speech: Callable[..., SpeechArray]) -> None:
    """clean_reference must trim silences, normalize peak to 0.95, and resample to 24 kHz."""
    # Create 12s speech at 16 kHz with 2s leading zero silence and 2s trailing zero silence
    speech = make_speech(duration_sec=12.0, gap_sec=0.1, sr=16000)
    leading_silence = np.zeros(16000 * 2, dtype=np.float32)
    trailing_silence = np.zeros(16000 * 2, dtype=np.float32)
    padded = np.concatenate([leading_silence, speech * 0.4, trailing_silence])

    cleaned, target_sr = clean_reference(padded, sample_rate=16000)

    assert target_sr == REFERENCE_SAMPLE_RATE
    # Peak amplitude must be normalized to approximately 0.95
    peak = float(np.max(np.abs(cleaned)))
    assert 0.94 <= peak <= 0.96
    # Total duration should be shorter than original padded (16s) due to silence trimming
    cleaned_dur = float(len(cleaned)) / float(target_sr)
    assert cleaned_dur < 14.0
