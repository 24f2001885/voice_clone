"""Silence-aware audio chunk splitter with minimum-energy cut point search (TDR Section 3.3)."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Sequence

import numpy as np

from voxclone.constants import CHUNK_TAIL_MIN_SEC
from voxclone.errors import NoSpeechDetectedError

logger = logging.getLogger("voxclone.audio.splitter")


@dataclass(frozen=True)
class AudioChunkInterval:
    """Temporal and sample bounds for an individual audio chunk."""

    index: int
    start_sec: float
    end_sec: float
    start_sample: int
    end_sample: int

    @property
    def duration_sec(self) -> float:
        """Duration of this chunk in seconds."""
        return self.end_sec - self.start_sec


def compute_frame_energies(
    audio: np.ndarray,
    sample_rate: int,
    frame_ms: float = 20.0,
    hop_ms: float = 20.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute short-time root-mean-square (RMS) frame energies.

    Args:
        audio: 1D float32 audio waveform.
        sample_rate: Sampling frequency in Hertz.
        frame_ms: Frame length in milliseconds (default: 20 ms).
        hop_ms: Step interval in milliseconds (default: 20 ms).

    Returns:
        Tuple of (frame_centers_sec, frame_rms_energies).
    """
    frame_len = max(1, int(sample_rate * (frame_ms / 1000.0)))
    hop_len = max(1, int(sample_rate * (hop_ms / 1000.0)))
    num_samples = len(audio)

    if num_samples < frame_len:
        rms_val = float(np.sqrt(np.mean(audio**2))) if num_samples > 0 else 0.0
        return np.array([0.0], dtype=np.float32), np.array([rms_val], dtype=np.float32)

    num_frames = max(1, 1 + (num_samples - frame_len) // hop_len)
    energies = np.empty(num_frames, dtype=np.float32)
    times = np.empty(num_frames, dtype=np.float32)

    for i in range(num_frames):
        start = i * hop_len
        end = start + frame_len
        frame = audio[start:end]
        energies[i] = float(np.sqrt(np.mean(frame**2)))
        times[i] = (start + end) / (2.0 * sample_rate)

    return times, energies


def find_cut_points(
    audio: np.ndarray,
    sample_rate: int,
    min_sec: float = 3.0,
    max_sec: float = 5.0,
    tail_min_sec: float = CHUNK_TAIL_MIN_SEC,
) -> list[AudioChunkInterval]:
    """Slice an audio signal into silence-aware chunks between min_sec and max_sec.

    Args:
        audio: 1D float32 audio signal.
        sample_rate: Audio sampling frequency in Hertz.
        min_sec: Minimum duration for each chunk (default: 3.0 s).
        max_sec: Maximum duration for each chunk (default: 5.0 s).
        tail_min_sec: Threshold below which a final tail chunk is merged into its predecessor (default: 1.0 s).

    Returns:
        List of AudioChunkInterval covering the complete audio with zero temporal gaps.
    """
    if len(audio) == 0:
        raise NoSpeechDetectedError(
            "Cannot split empty audio signal.",
            hint="Ensure input audio contains valid speech.",
        )

    # Validate overall energy
    overall_rms = float(np.sqrt(np.mean(audio**2)))
    if overall_rms < 1e-4:
        raise NoSpeechDetectedError(
            "Input recording contains only silence or near-zero energy.",
            hint="Record or provide an audio file with audible speech.",
        )

    total_samples = len(audio)
    total_sec = float(total_samples) / float(sample_rate)

    # Edge case 1: Input shorter than or equal to min_sec -> single chunk
    if total_sec <= min_sec:
        return [
            AudioChunkInterval(
                index=0,
                start_sec=0.0,
                end_sec=total_sec,
                start_sample=0,
                end_sample=total_samples,
            )
        ]

    # Compute short-time energy curve
    times, energies = compute_frame_energies(audio, sample_rate, frame_ms=20.0, hop_ms=20.0)

    cut_sec_points: list[float] = [0.0]
    curr_start_sec = 0.0

    while (total_sec - curr_start_sec) > max_sec:
        search_start_sec = curr_start_sec + min_sec
        search_end_sec = curr_start_sec + max_sec

        # Find frames within search window
        window_mask = (times >= search_start_sec) & (times <= search_end_sec)
        window_indices = np.where(window_mask)[0]

        if len(window_indices) > 0:
            # Find minimum energy frame in the window
            window_energies = energies[window_indices]
            min_sub_idx = int(np.argmin(window_energies))
            best_frame_idx = window_indices[min_sub_idx]
            cut_time = float(times[best_frame_idx])
        else:
            # Fallback to mid-point if no frame matches
            cut_time = (search_start_sec + search_end_sec) / 2.0

        cut_sec_points.append(cut_time)
        curr_start_sec = cut_time

    # Append end of file
    cut_sec_points.append(total_sec)

    # Tail merge: If the last interval is shorter than tail_min_sec, merge it into the previous chunk
    if len(cut_sec_points) >= 3:
        last_interval = cut_sec_points[-1] - cut_sec_points[-2]
        if last_interval < tail_min_sec:
            logger.debug(
                "Tail chunk (%.2f s) is below tail_min_sec (%.2f s); merging into predecessor",
                last_interval,
                tail_min_sec,
            )
            cut_sec_points.pop(-2)

    # Construct intervals
    intervals: list[AudioChunkInterval] = []
    for i in range(len(cut_sec_points) - 1):
        s_sec = cut_sec_points[i]
        e_sec = cut_sec_points[i + 1]
        s_samp = int(round(s_sec * sample_rate))
        e_samp = total_samples if (i == len(cut_sec_points) - 2) else int(round(e_sec * sample_rate))
        intervals.append(
            AudioChunkInterval(
                index=i,
                start_sec=s_sec,
                end_sec=e_sec,
                start_sample=s_samp,
                end_sample=e_samp,
            )
        )

    return intervals
