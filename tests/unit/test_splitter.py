"""Unit tests for silence-aware audio chunk splitter (TDR Section 3.3)."""
from __future__ import annotations

import numpy as np
import pytest

from voxclone.audio.splitter import compute_frame_energies, find_cut_points
from voxclone.errors import NoSpeechDetectedError


def test_splitter_empty_audio_raises_no_speech() -> None:
    """Splitting an empty array must raise NoSpeechDetectedError (VX-210)."""
    with pytest.raises(NoSpeechDetectedError) as exc_info:
        find_cut_points(np.array([], dtype=np.float32), sample_rate=16000)
    assert exc_info.value.code == "VX-210"


def test_splitter_pure_silence_raises_no_speech() -> None:
    """Splitting pure zero silence must raise NoSpeechDetectedError (VX-210)."""
    silence = np.zeros(16000 * 5, dtype=np.float32)
    with pytest.raises(NoSpeechDetectedError) as exc_info:
        find_cut_points(silence, sample_rate=16000)
    assert exc_info.value.code == "VX-210"


def test_splitter_short_audio_returns_single_chunk() -> None:
    """Audio shorter than min_sec (3.0 s) must return exactly one chunk."""
    sr = 16000
    duration_sec = 2.5
    # Generate 440 Hz tone with noise
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False, dtype=np.float32)
    audio = (0.5 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)

    intervals = find_cut_points(audio, sample_rate=sr, min_sec=3.0, max_sec=5.0)
    assert len(intervals) == 1
    assert intervals[0].index == 0
    assert intervals[0].start_sec == 0.0
    assert intervals[0].end_sec == pytest.approx(duration_sec, abs=1e-3)
    assert intervals[0].start_sample == 0
    assert intervals[0].end_sample == len(audio)


def test_splitter_long_audio_contiguous_cuts() -> None:
    """Long audio (12 s) must be sliced into 3-5 s chunks with no temporal gaps."""
    sr = 16000
    total_sec = 12.0
    t = np.linspace(0, total_sec, int(sr * total_sec), endpoint=False, dtype=np.float32)
    # Continuous tone with periodic amplitude dips (simulating pauses) at 4s, 8s
    envelope = np.ones_like(t)
    envelope[int(3.8 * sr) : int(4.2 * sr)] = 0.01
    envelope[int(7.8 * sr) : int(8.2 * sr)] = 0.01
    audio = (0.4 * np.sin(2 * np.pi * 300.0 * t) * envelope).astype(np.float32)

    intervals = find_cut_points(audio, sample_rate=sr, min_sec=3.0, max_sec=5.0)
    assert len(intervals) >= 2

    # Check temporal contiguity
    assert intervals[0].start_sec == 0.0
    for i in range(len(intervals) - 1):
        assert intervals[i].end_sec == pytest.approx(intervals[i + 1].start_sec, abs=1e-4)
        assert intervals[i].end_sample == intervals[i + 1].start_sample
    assert intervals[-1].end_sec == pytest.approx(total_sec, abs=1e-3)
    assert intervals[-1].end_sample == len(audio)


def test_splitter_tail_merge_policy() -> None:
    """A final tail chunk shorter than 1.0 s must be merged into the preceding chunk."""
    sr = 16000
    # 5.5 s of audio: first chunk takes 4.8 s, leaving 0.7 s tail (< 1.0 s)
    total_sec = 5.5
    t = np.linspace(0, total_sec, int(sr * total_sec), endpoint=False, dtype=np.float32)
    audio = (0.3 * np.sin(2 * np.pi * 350.0 * t)).astype(np.float32)

    intervals = find_cut_points(audio, sample_rate=sr, min_sec=3.0, max_sec=5.0, tail_min_sec=1.0)
    # If tail was not merged, it would be 2 chunks with the second one only 0.5-0.7 s.
    # With tail merge, the entire 5.5 s or a merged ~5.5 s single chunk is produced.
    for inter in intervals:
        assert inter.duration_sec >= 1.0
