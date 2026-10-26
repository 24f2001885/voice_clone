"""Loudness matching and joining of audio pieces. Pure numpy, torch-free."""
from __future__ import annotations

import numpy as np

from voxclone.errors import InternalError


def rms(x: np.ndarray) -> float:
    """Calculate root-mean-square with epsilon safety."""
    if len(x) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64)) + 1e-12))


def match_loudness(
    out: np.ndarray,
    reference_rms: float,
    max_gain_db: float = 12.0,
) -> np.ndarray:
    """Scale audio array so its RMS matches reference_rms, clamped to +/- max_gain_db."""
    if len(out) == 0 or reference_rms <= 1e-9:
        return out.astype(np.float32, copy=True)

    current_rms = rms(out)
    if current_rms <= 1e-9:
        return out.astype(np.float32, copy=True)

    target_gain = reference_rms / current_rms
    max_gain = float(10.0 ** (max_gain_db / 20.0))
    min_gain = float(10.0 ** (-max_gain_db / 20.0))
    clamped_gain = float(np.clip(target_gain, min_gain, max_gain))

    scaled = out.astype(np.float32, copy=True) * clamped_gain
    return np.clip(scaled, -1.0, 1.0).astype(np.float32)


def crossfade_join(
    parts: list[np.ndarray],
    sample_rate: int,
    fade_ms: int = 30,
) -> np.ndarray:
    """Join multiple audio parts with an equal-power crossfade at boundaries."""
    if not parts:
        raise InternalError("Cannot join empty audio list")
    if len(parts) == 1:
        return parts[0].astype(np.float32, copy=True)

    fade_samples_target = int(sample_rate * (fade_ms / 1000.0))
    result = parts[0].astype(np.float32, copy=True)

    for next_part in parts[1:]:
        b = next_part.astype(np.float32, copy=True)
        # Bounded fade length: at most half of either piece
        max_possible_fade = min(len(result) // 2, len(b) // 2, fade_samples_target)
        if max_possible_fade <= 0:
            result = np.concatenate([result, b])
            continue

        fade_len = max_possible_fade
        t = np.linspace(0.0, 1.0, fade_len, endpoint=False, dtype=np.float32)
        # Equal power crossfade curves: cos and sin of (t * pi / 2)
        fade_out = np.cos(t * (np.pi / 2.0))
        fade_in = np.sin(t * (np.pi / 2.0))

        # Split left into head and overlap
        left_head = result[:-fade_len]
        left_tail = result[-fade_len:]

        # Split right into overlap and tail
        right_head = b[:fade_len]
        right_tail = b[fade_len:]

        # Blend
        blended = (left_tail * fade_out) + (right_head * fade_in)
        result = np.concatenate([left_head, blended, right_tail])

    return np.clip(result, -1.0, 1.0).astype(np.float32)


def join_with_pauses(
    parts: list[np.ndarray],
    sample_rate: int,
    pause_ms: int = 250,
    fade_ms: int = 10,
) -> np.ndarray:
    """Join audio chunks with short fade in/out click prevention and digital silence pauses."""
    if not parts:
        raise InternalError("Cannot join empty audio list")
    if len(parts) == 1:
        return parts[0].astype(np.float32, copy=True)

    fade_samples = max(1, int(sample_rate * (fade_ms / 1000.0)))
    silence_samples = int(sample_rate * (pause_ms / 1000.0))
    silence = np.zeros(silence_samples, dtype=np.float32)

    conditioned_parts = []
    for p in parts:
        arr = p.astype(np.float32, copy=True)
        cur_fade = min(fade_samples, len(arr) // 2)
        if cur_fade > 0:
            fade_in = np.linspace(0.0, 1.0, cur_fade, dtype=np.float32)
            fade_out = np.linspace(1.0, 0.0, cur_fade, dtype=np.float32)
            arr[:cur_fade] *= fade_in
            arr[-cur_fade:] *= fade_out
        conditioned_parts.append(arr)

    output_pieces = []
    for i, part in enumerate(conditioned_parts):
        output_pieces.append(part)
        if i < len(conditioned_parts) - 1:
            output_pieces.append(silence)

    return np.concatenate(output_pieces).astype(np.float32)
