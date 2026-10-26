"""Audio sample quality validation, speech presence analysis, and reference cleaning."""

from dataclasses import dataclass

import librosa  # type: ignore[import-untyped]
import numpy as np

from voxclone.constants import MIN_SAMPLE_SPEECH_SEC, REFERENCE_SAMPLE_RATE
from voxclone.errors import NoSpeechDetectedError, SampleTooShortError


@dataclass(frozen=True)
class SampleReport:
    """Detailed quality and speech metric analysis of an audio sample."""

    duration_sec: float
    speech_sec: float
    rms_dbfs: float
    peak: float
    clipping_ratio: float
    noise_floor_dbfs: float
    snr_db: float
    quality_score: float  # 0.0 to 1.0
    notes: list[str]
    acceptable: bool


def analyze_sample(data: np.ndarray, sample_rate: int) -> SampleReport:
    """Evaluate speech sample against quality, duration, and SNR criteria (TDR 11).

    Args:
        data: 1D float32 audio numpy array.
        sample_rate: Sampling rate in Hz.

    Returns:
        SampleReport with detailed metrics and actionable notes.

    Raises:
        NoSpeechDetectedError (VX-210): If audio is complete silence.
        SampleTooShortError (VX-101): If detected speech is under 10.0 seconds.
    """
    total_samples = len(data)
    if total_samples == 0:
        raise NoSpeechDetectedError("Input audio array is empty.")

    duration_sec = float(total_samples) / float(sample_rate)
    peak = float(np.max(np.abs(data)))

    # Zero speech check (pure silence)
    if peak < 1e-4:
        raise NoSpeechDetectedError(
            "Audio sample is completely silent; no audible signal detected.",
            hint="Check microphone gain or ensure the selected audio file contains speech.",
        )

    # Compute frame energy with 20 ms hop and 40 ms window
    frame_length = int(sample_rate * 0.040)
    hop_length = int(sample_rate * 0.020)
    if frame_length > total_samples:
        frame_length = total_samples
    if hop_length <= 0:
        hop_length = 1

    rms_frames = librosa.feature.rms(y=data, frame_length=frame_length, hop_length=hop_length)[0]
    rms_frames_db = 20.0 * np.log10(np.maximum(rms_frames, 1e-7))

    # Noise floor: 10th percentile of frame energy
    noise_floor_dbfs = float(np.percentile(rms_frames_db, 10))

    # Speech frames: energy > noise_floor + 10 dB AND energy > -45 dBFS
    speech_mask = (rms_frames_db > (noise_floor_dbfs + 10.0)) & (rms_frames_db > -45.0)
    speech_frame_count = int(np.sum(speech_mask))
    speech_sec = float(speech_frame_count * hop_length) / float(sample_rate)

    # Enforce minimum speech duration gate
    if speech_sec < MIN_SAMPLE_SPEECH_SEC:
        raise SampleTooShortError(
            f"Detected only {speech_sec:.1f} s of speech (minimum {MIN_SAMPLE_SPEECH_SEC:.1f} s required).",
            hint=f"Record or provide an audio file with at least {MIN_SAMPLE_SPEECH_SEC:.0f} seconds of continuous clear speech.",
        )

    # Clipping analysis
    clipping_ratio = float(np.mean(np.abs(data) >= 0.99))

    # Overall RMS and SNR
    overall_rms = float(np.sqrt(np.mean(data**2)))
    rms_dbfs = float(20.0 * np.log10(max(overall_rms, 1e-7)))

    if speech_frame_count > 0:
        speech_rms_dbfs = float(np.mean(rms_frames_db[speech_mask]))
        snr_db = float(max(0.0, speech_rms_dbfs - noise_floor_dbfs))
    else:
        snr_db = 0.0

    # Quality scoring heuristic (TDR 11)
    notes: list[str] = []

    # 1. Level Score (ideal: -26 to -14 dBFS)
    if -26.0 <= rms_dbfs <= -14.0:
        level_score = 1.0
    elif -35.0 <= rms_dbfs < -26.0:
        level_score = 0.8
    elif rms_dbfs < -35.0:
        level_score = max(0.2, 1.0 - (-14.0 - rms_dbfs) / 40.0)
        notes.append("Recording is quiet; speak closer to the microphone or boost input volume.")
    else:
        level_score = 0.6
        notes.append("Signal is unusually loud; decrease input volume to avoid distortion.")

    # 2. Clipping Score
    if clipping_ratio < 0.001:
        clip_score = 1.0
    elif clipping_ratio < 0.01:
        clip_score = 0.7
        notes.append("Minor audio clipping detected; avoid shouting directly into microphone.")
    else:
        clip_score = max(0.0, 1.0 - (clipping_ratio * 30.0))
        notes.append("Significant audio clipping distortion present; decrease microphone gain.")

    # 3. SNR Score (ideal >= 25 dB)
    if snr_db >= 25.0:
        snr_score = 1.0
    elif snr_db >= 18.0:
        snr_score = 0.8
    elif snr_db >= 12.0:
        snr_score = 0.6
        notes.append("Background room noise is audible; record in a quieter room.")
    else:
        snr_score = max(0.1, snr_db / 20.0)
        notes.append("Heavy background noise detected; SNR is low.")

    # 4. Duration Score (ideal: 20 to 30 s)
    if 20.0 <= duration_sec <= 35.0:
        dur_score = 1.0
    elif duration_sec > 35.0:
        dur_score = 0.95
    else:
        # 10s to 20s
        dur_score = 0.6 + 0.4 * ((duration_sec - 10.0) / 10.0)
        notes.append("Recording length is short (20-30s recommended for maximum clone fidelity).")

    quality_score = round(
        0.30 * level_score + 0.30 * clip_score + 0.25 * snr_score + 0.15 * dur_score,
        2,
    )

    if not notes:
        notes.append("Excellent reference sample: clear speech, good level, and low background noise.")

    acceptable = bool(quality_score >= 0.50 and clipping_ratio < 0.02 and snr_db >= 12.0)

    return SampleReport(
        duration_sec=round(duration_sec, 2),
        speech_sec=round(speech_sec, 2),
        rms_dbfs=round(rms_dbfs, 1),
        peak=round(peak, 2),
        clipping_ratio=round(clipping_ratio, 4),
        noise_floor_dbfs=round(noise_floor_dbfs, 1),
        snr_db=round(snr_db, 1),
        quality_score=quality_score,
        notes=notes,
        acceptable=acceptable,
    )


def clean_reference(data: np.ndarray, sample_rate: int) -> tuple[np.ndarray, int]:
    """Trim leading/trailing silence, peak normalize to 0.95, and resample to 24 kHz."""
    # 1. Trim leading and trailing silence (top_db=35)
    trimmed, _ = librosa.effects.trim(data, top_db=35)

    # 2. Peak normalization to 0.95
    current_peak = float(np.max(np.abs(trimmed))) if len(trimmed) > 0 else 0.0
    if current_peak > 0.0:
        normalized = (trimmed / current_peak) * 0.95
    else:
        normalized = trimmed

    # 3. Resample to standard reference rate (24000 Hz)
    if sample_rate != REFERENCE_SAMPLE_RATE:
        resampled = librosa.resample(
            normalized,
            orig_sr=sample_rate,
            target_sr=REFERENCE_SAMPLE_RATE,
        )
    else:
        resampled = normalized

    return resampled.astype(np.float32), REFERENCE_SAMPLE_RATE
