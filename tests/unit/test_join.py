"""Unit tests for audio joining, loudness matching, and crossfading."""
from __future__ import annotations

import numpy as np
import pytest

from voxclone.audio.join import crossfade_join, join_with_pauses, match_loudness, rms
from voxclone.errors import InternalError


def test_rms_basic_and_empty() -> None:
    """RMS of empty array returns 0, and non-zero tone calculates positive RMS."""
    assert rms(np.array([], dtype=np.float32)) == 0.0

    # Sine wave with amplitude A has RMS A / sqrt(2)
    t = np.linspace(0, 1, 16000, endpoint=False)
    sine = 0.5 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    expected_rms = 0.5 / np.sqrt(2)
    assert abs(rms(sine) - expected_rms) < 0.01


def test_match_loudness_scales_to_reference() -> None:
    """match_loudness scales output audio to target RMS within gain clamp."""
    t = np.linspace(0, 1, 16000, endpoint=False)
    source = 0.1 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    target_rms = 0.25

    scaled = match_loudness(source, target_rms, max_gain_db=12.0)
    measured_rms = rms(scaled)
    assert abs(measured_rms - target_rms) < 0.02
    assert np.max(scaled) <= 1.0
    assert np.min(scaled) >= -1.0


def test_crossfade_join_empty_raises() -> None:
    """Empty list passed to crossfade_join raises InternalError (VX-900)."""
    with pytest.raises(InternalError) as exc_info:
        crossfade_join([], sample_rate=16000)
    assert exc_info.value.code == "VX-900"


def test_crossfade_join_two_parts() -> None:
    """Joining two 1.0s audio segments with 30ms fade produces expected sample count and smooth seam."""
    sr = 16000
    fade_ms = 30
    fade_samples = int(sr * (fade_ms / 1000.0))

    t = np.linspace(0, 1.0, sr, endpoint=False)
    tone1 = 0.5 * np.sin(2 * np.pi * 200 * t).astype(np.float32)
    tone2 = 0.5 * np.sin(2 * np.pi * 200 * t).astype(np.float32)

    joined = crossfade_join([tone1, tone2], sample_rate=sr, fade_ms=fade_ms)
    expected_length = (2 * sr) - fade_samples
    assert len(joined) == expected_length

    # Ensure no massive sample discontinuity at the boundary
    diffs = np.abs(np.diff(joined))
    assert np.max(diffs) < 0.25


def test_join_with_pauses_length_and_structure() -> None:
    """join_with_pauses inserts exact digital silence duration between parts."""
    sr = 16000
    pause_ms = 250
    pause_samples = int(sr * (pause_ms / 1000.0))

    part1 = np.ones(sr, dtype=np.float32) * 0.5
    part2 = np.ones(sr, dtype=np.float32) * 0.5
    part3 = np.ones(sr, dtype=np.float32) * 0.5

    result = join_with_pauses([part1, part2, part3], sample_rate=sr, pause_ms=pause_ms, fade_ms=10)
    expected_samples = (3 * sr) + (2 * pause_samples)
    assert len(result) == expected_samples

    # Check that silence section in the middle is actually zeros
    middle_pause_start = sr + 10  # after part1 fade out
    middle_pause_end = sr + pause_samples - 10
    assert np.allclose(result[middle_pause_start:middle_pause_end], 0.0, atol=1e-5)
