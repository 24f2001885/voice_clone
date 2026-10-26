"""Unit tests for emotion to expressiveness mapping and resolution."""
from __future__ import annotations

import pytest

from voxclone.constants import EMOTION_LABELS
from voxclone.pipelines.emotion_mapping import (
    clamp_expressiveness,
    get_mode_expressiveness,
    map_emotion_label,
    resolve_expressiveness,
)


def test_standard_emotion_labels_mapping() -> None:
    """Verify that all standard emotion labels map to their expected values."""
    expected = {
        "neutral": 0.40,
        "sadness": 0.30,
        "joy": 0.70,
        "fear": 0.70,
        "disgust": 0.70,
        "surprise": 0.80,
        "anger": 0.90,
    }
    for label, val in expected.items():
        assert map_emotion_label(label) == pytest.approx(val, abs=1e-3)
        assert label in EMOTION_LABELS


def test_unknown_emotion_defaults_to_neutral() -> None:
    """Verify unknown labels fall back safely to neutral (0.40)."""
    assert map_emotion_label("ecstatic") == pytest.approx(0.40)
    assert map_emotion_label("bored") == pytest.approx(0.40)
    assert map_emotion_label("") == pytest.approx(0.40)


def test_emotion_case_and_whitespace_insensitivity() -> None:
    """Verify mapping trims whitespace and ignores case."""
    assert map_emotion_label("  JOY  ") == pytest.approx(0.70)
    assert map_emotion_label("Anger") == pytest.approx(0.90)


def test_overrides_dictionary() -> None:
    """Verify custom user overrides take precedence."""
    overrides = {"joy": 0.95, "neutral": 0.35}
    assert map_emotion_label("joy", overrides=overrides) == pytest.approx(0.95)
    assert map_emotion_label("neutral", overrides=overrides) == pytest.approx(0.35)
    # Non-overridden label falls back to default
    assert map_emotion_label("anger", overrides=overrides) == pytest.approx(0.90)


def test_clamping_constraints() -> None:
    """Verify values are strictly clamped to range [0.25, 1.0]."""
    assert clamp_expressiveness(0.0) == 0.25
    assert clamp_expressiveness(0.1) == 0.25
    assert clamp_expressiveness(1.5) == 1.0
    assert clamp_expressiveness(0.65) == 0.65

    # With overrides out of bounds
    overrides = {"joy": 1.5, "sadness": 0.05}
    assert map_emotion_label("joy", overrides=overrides) == 1.0
    assert map_emotion_label("sadness", overrides=overrides) == 0.25


def test_mode_expressiveness_presets() -> None:
    """Verify mode presets (calm, normal, expressive)."""
    assert get_mode_expressiveness("calm") == pytest.approx(0.30)
    assert get_mode_expressiveness("normal") == pytest.approx(0.50)
    assert get_mode_expressiveness("expressive") == pytest.approx(0.80)
    assert get_mode_expressiveness("auto") == pytest.approx(0.50)
    assert get_mode_expressiveness("unknown") == pytest.approx(0.50)


def test_resolve_expressiveness() -> None:
    """Verify resolution of expressiveness based on mode and detected emotion."""
    # When mode is auto and detected label is present
    assert resolve_expressiveness("auto", detected_label="joy") == pytest.approx(0.70)
    assert resolve_expressiveness("auto", detected_label="anger") == pytest.approx(0.90)

    # When mode is manual preset, it overrides detected emotion
    assert resolve_expressiveness("calm", detected_label="anger") == pytest.approx(0.30)
    assert resolve_expressiveness("expressive", detected_label="sadness") == pytest.approx(0.80)
