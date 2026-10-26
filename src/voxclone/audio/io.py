"""Audio decoding, encoding, microphone recording, and speaker playback."""

import os
from pathlib import Path
import threading
import time
from typing import Any, Callable

import librosa  # type: ignore[import-untyped]
import numpy as np
import soundfile as sf

from voxclone.constants import REFERENCE_SAMPLE_RATE
from voxclone.errors import (
    MicrophoneUnavailableError,
    SpeakerUnavailableError,
    UnsupportedAudioError,
)


def is_fake_audio_mode() -> bool:
    """Return True if running in offline test environment."""
    return os.environ.get("VOXCLONE_ENGINE", "").lower() == "fake"


def load_audio(
    path: Path | str,
    sample_rate: int = REFERENCE_SAMPLE_RATE,
) -> tuple[np.ndarray, int]:
    """Load and resample audio file to float32 mono at target sample rate.

    Args:
        path: Path to audio file (WAV, MP3, FLAC, M4A).
        sample_rate: Target sample rate in Hz (default: 24000).

    Returns:
        Tuple of (1D float32 numpy array, sample_rate).
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise UnsupportedAudioError(
            f"Audio file does not exist: '{file_path}'",
            hint="Check the filepath and verify it exists.",
        )

    try:
        data, sr = librosa.load(str(file_path), sr=sample_rate, mono=True)
        return data.astype(np.float32), int(sr)
    except Exception as exc:
        raise UnsupportedAudioError(
            f"Failed to read or decode audio file '{file_path.name}': {exc!s}",
            hint="Ensure the file is a valid WAV, MP3, FLAC, or M4A audio file.",
        ) from exc


def probe_audio(path: Path | str) -> dict[str, Any]:
    """Probe audio file metadata without reading full waveform into memory."""
    file_path = Path(path)
    if not file_path.is_file():
        raise UnsupportedAudioError(f"Audio file not found: '{file_path}'")

    try:
        info = sf.info(str(file_path))
        return {
            "duration_sec": float(info.duration),
            "sample_rate": int(info.samplerate),
            "channels": int(info.channels),
        }
    except Exception as exc:
        # Fallback to librosa duration check
        try:
            dur = float(librosa.get_duration(path=str(file_path)))
            return {
                "duration_sec": dur,
                "sample_rate": 0,
                "channels": 1,
            }
        except Exception:
            raise UnsupportedAudioError(
                f"Cannot probe audio metadata for '{file_path.name}': {exc!s}"
            ) from exc


def save_wav(path: Path | str, data: np.ndarray, sample_rate: int) -> Path:
    """Save 1D or 2D audio array as 16-bit PCM WAV, clipping to [-1.0, 1.0]."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(data, -1.0, 1.0).astype(np.float32)
    sf.write(str(target), clipped, sample_rate, subtype="PCM_16")
    return target


def save_audio(data: np.ndarray, sample_rate: int, path: Path | str) -> Path:
    """Save 1D or 2D audio array as 16-bit PCM WAV."""
    return save_wav(path, data, sample_rate)


def record_microphone(
    duration_sec: float = 15.0,
    sample_rate: int = REFERENCE_SAMPLE_RATE,
    device_index: int | None = None,
    stop_event: threading.Event | None = None,
    level_callback: Callable[[float], None] | None = None,
) -> tuple[np.ndarray, int]:
    """Record mono float32 audio from microphone device.

    Returns:
        Tuple of (1D float32 numpy array, sample_rate).
    """
    if is_fake_audio_mode():
        # Null audio backend for automated testing: generate synthetic speech bursts
        num_samples = int(duration_sec * sample_rate)
        t = np.linspace(0, duration_sec, num_samples, endpoint=False, dtype=np.float32)
        # Natural speech cadence with brief pauses (approx 90% speech activity)
        gate = ((np.sin(2 * np.pi * 0.5 * t) > -0.85).astype(np.float32))
        simulated = (0.6 * np.sin(2 * np.pi * 220.0 * t) * gate).astype(np.float32)
        # Add quiet noise floor (-60 dBFS)
        simulated += (1e-3 * np.sin(2 * np.pi * 800.0 * t)).astype(np.float32)
        if level_callback:
            level_callback(0.5)
        return simulated, sample_rate

    try:
        import sounddevice as sd  # type: ignore[import-untyped]
    except ImportError as exc:
        raise MicrophoneUnavailableError(
            "sounddevice library is not installed or available."
        ) from exc

    chunks: list[np.ndarray] = []
    chunk_frames = int(sample_rate * 0.1)  # 100 ms chunks

    try:
        with sd.InputStream(
            device=device_index,
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            blocksize=chunk_frames,
        ) as stream:
            start_time = time.monotonic()
            while (time.monotonic() - start_time) < duration_sec:
                if stop_event is not None and stop_event.is_set():
                    break
                data, _ = stream.read(chunk_frames)
                flat = data.flatten()
                chunks.append(flat)
                if level_callback:
                    peak = float(np.max(np.abs(flat))) if len(flat) > 0 else 0.0
                    level_callback(min(peak, 1.0))

        if not chunks:
            return np.zeros(0, dtype=np.float32), sample_rate
        return np.concatenate(chunks).astype(np.float32), sample_rate
    except Exception as exc:
        raise MicrophoneUnavailableError(
            f"Microphone recording failed: {exc!s}"
        ) from exc


def play_audio(
    target: Path | str | np.ndarray,
    sample_rate: int = REFERENCE_SAMPLE_RATE,
) -> None:
    """Play audio array or audio file through default output device (blocking call)."""
    if is_fake_audio_mode():
        return

    try:
        import sounddevice as sd  # type: ignore[import-untyped]
    except ImportError as exc:
        raise SpeakerUnavailableError(
            "sounddevice library is not installed or available."
        ) from exc

    try:
        if isinstance(target, (str, Path)):
            audio_path = Path(target)
            data, sr = sf.read(str(audio_path), dtype="float32")
            sd.play(data, sr)
            sd.wait()
        else:
            sd.play(target, sample_rate)
            sd.wait()
    except Exception as exc:
        raise SpeakerUnavailableError(
            f"Audio playback failed: {exc!s}"
        ) from exc



def list_audio_devices() -> dict[str, list[str]]:
    """List host audio input and output device names."""
    if is_fake_audio_mode():
        return {
            "inputs": ["Fake Microphone (Null Backend)"],
            "outputs": ["Fake Speaker (Null Backend)"],
        }

    try:
        import sounddevice as sd  # type: ignore[import-untyped]

        devices = sd.query_devices()
        inputs: list[str] = []
        outputs: list[str] = []
        for d in devices:
            name = str(d.get("name", "Unknown"))
            if d.get("max_input_channels", 0) > 0:
                inputs.append(name)
            if d.get("max_output_channels", 0) > 0:
                outputs.append(name)
        return {"inputs": inputs, "outputs": outputs}
    except Exception:
        return {"inputs": [], "outputs": []}
