"""Emotion to synthesis expressiveness mapping and configuration resolution."""
from __future__ import annotations

import logging
from typing import Any

from voxclone.constants import (
    EMOTION_LABELS,
    EMOTION_MODE_TO_EXPRESSIVENESS,
    EMOTION_MODES,
    EMOTION_TO_EXPRESSIVENESS,
)

logger = logging.getLogger("voxclone.pipelines.emotion_mapping")

# Range constraints defined in TDR Section 3.8
MIN_EXPRESSIVENESS: float = 0.25
MAX_EXPRESSIVENESS: float = 1.0
DEFAULT_EXPRESSIVENESS: float = 0.40  # Neutral fallback


def clamp_expressiveness(value: float) -> float:
    """Clamp expressiveness strictly to range [0.25, 1.0]."""
    return float(max(MIN_EXPRESSIVENESS, min(MAX_EXPRESSIVENESS, value)))


def map_emotion_label(
    label: str,
    overrides: dict[str, float] | None = None,
) -> float:
    """Map a detected emotion label to an expressiveness multiplier factor.

    Args:
        label: Emotion classification label (e.g. 'joy', 'sadness', 'neutral').
        overrides: Optional per-label override mapping (e.g. from app_settings).

    Returns:
        Float value clamped to [0.25, 1.0].
    """
    clean_label = label.strip().lower()

    if overrides and clean_label in overrides:
        try:
            return clamp_expressiveness(float(overrides[clean_label]))
        except (ValueError, TypeError):
            logger.warning("Invalid override value for emotion '%s': %r", clean_label, overrides[clean_label])

    if clean_label in EMOTION_TO_EXPRESSIVENESS:
        return clamp_expressiveness(EMOTION_TO_EXPRESSIVENESS[clean_label])

    logger.warning("Unknown emotion label '%s', defaulting to neutral (%0.2f)", clean_label, DEFAULT_EXPRESSIVENESS)
    return clamp_expressiveness(DEFAULT_EXPRESSIVENESS)


def get_mode_expressiveness(mode: str) -> float:
    """Retrieve fixed expressiveness factor for a manual preset mode.

    Args:
        mode: Preset emotion mode ('calm', 'normal', 'expressive').

    Returns:
        Float expressiveness factor clamped to [0.25, 1.0].
    """
    clean_mode = mode.strip().lower()
    if clean_mode in EMOTION_MODE_TO_EXPRESSIVENESS:
        return clamp_expressiveness(EMOTION_MODE_TO_EXPRESSIVENESS[clean_mode])

    if clean_mode == "auto":
        # Fallback if called directly without classification
        return clamp_expressiveness(EMOTION_MODE_TO_EXPRESSIVENESS["normal"])

    logger.warning("Unknown emotion mode '%s', defaulting to normal", clean_mode)
    return clamp_expressiveness(EMOTION_MODE_TO_EXPRESSIVENESS["normal"])


def resolve_expressiveness(
    emotion_mode: str,
    detected_label: str | None = None,
    overrides: dict[str, float] | None = None,
) -> float:
    """Resolve final expressiveness factor given job emotion mode and detected label.

    If mode is 'auto', uses detected_label if provided; otherwise falls back to mode preset.
    """
    clean_mode = (emotion_mode or "normal").strip().lower()
    if clean_mode == "auto" and detected_label:
        return map_emotion_label(detected_label, overrides=overrides)
    return get_mode_expressiveness(clean_mode)
