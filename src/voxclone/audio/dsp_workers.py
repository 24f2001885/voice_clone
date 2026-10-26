"""CPU DSP worker functions executed in parallel subprocesses (TDR Section 3.6).

CRITICAL RULE:
Strictly no PyTorch or CUDA imports in this module to keep worker footprints small
and avoid deadlocks across spawned process pools.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from voxclone.audio.join import match_loudness, rms


def prepare_chunk_worker(
    input_path: str,
    out_path: str,
    start_sample: int,
    end_sample: int,
    target_sr: int = 16000,
) -> dict[str, Any]:
    """Prepare a normalized, resampled audio chunk for neural model consumption.

    Args:
        input_path: Path to source recording WAV file.
        out_path: Destination path for prepared chunk WAV file.
        start_sample: Starting sample index in input audio.
        end_sample: Ending sample index in input audio.
        target_sr: Target sample rate for model input (default: 16000 Hz).

    Returns:
        Dictionary with chunk metadata and output path.
    """
    p_in = Path(input_path)
    p_out = Path(out_path)
    p_out.parent.mkdir(parents=True, exist_ok=True)

    with sf.SoundFile(str(p_in), "r") as f:
        in_sr = f.samplerate
        channels = f.channels
        f.seek(start_sample)
        frames_to_read = max(0, end_sample - start_sample)
        data = f.read(frames=frames_to_read, dtype="float32")

    # Down-mix stereo to mono
    if data.ndim > 1:
        data = np.mean(data, axis=1)

    # Remove DC bias offset
    if len(data) > 0:
        data = data - np.mean(data)

    # Peak normalization to 0.95 if clipping or excessively loud
    peak = float(np.max(np.abs(data))) if len(data) > 0 else 0.0
    if peak > 0.95:
        data = (data / peak) * 0.95

    # Resample to target_sr if required
    if in_sr != target_sr and len(data) > 0:
        import librosa  # type: ignore[import-untyped]
        data = librosa.resample(data, orig_sr=in_sr, target_sr=target_sr)

    # Write prepared WAV
    sf.write(str(p_out), data, target_sr, subtype="PCM_16")

    chunk_rms = rms(data)
    duration_sec = float(len(data)) / float(target_sr) if target_sr > 0 else 0.0

    return {
        "out_path": str(p_out),
        "duration_sec": duration_sec,
        "sample_rate": target_sr,
        "rms": chunk_rms,
    }


def postprocess_chunk_worker(
    converted_path: str,
    reference_rms: float,
    out_path: str,
    max_gain_db: float = 12.0,
) -> dict[str, Any]:
    """Postprocess a converted audio chunk: match loudness and prevent clipping.

    Args:
        converted_path: Path to raw model-converted WAV chunk.
        reference_rms: Target RMS energy to match.
        out_path: Destination path for final postprocessed chunk WAV.
        max_gain_db: Maximum amplification allowed in dB (default: 12.0 dB).

    Returns:
        Dictionary with postprocessed metadata.
    """
    p_in = Path(converted_path)
    p_out = Path(out_path)
    p_out.parent.mkdir(parents=True, exist_ok=True)

    data, sr = sf.read(str(p_in), dtype="float32")
    if data.ndim > 1:
        data = np.mean(data, axis=1)

    # Match loudness to reference RMS
    matched = match_loudness(data, reference_rms=reference_rms, max_gain_db=max_gain_db)

    # Prevent digital overs
    peak = float(np.max(np.abs(matched))) if len(matched) > 0 else 0.0
    if peak > 0.99:
        matched = (matched / peak) * 0.99

    sf.write(str(p_out), matched, sr, subtype="PCM_16")

    return {
        "out_path": str(p_out),
        "sample_rate": sr,
        "duration_sec": float(len(matched)) / float(sr) if sr > 0 else 0.0,
        "rms": rms(matched),
    }
