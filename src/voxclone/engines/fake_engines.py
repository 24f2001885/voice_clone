"""Deterministic test doubles for TTS, VC, and emotion engines without PyTorch."""

from pathlib import Path
import time
from typing import Any

import numpy as np
import soundfile as sf

from voxclone.errors import InternalError

# Global registry tracking resident fake engines
_LOADED_FAKE_ENGINES: set[Any] = set()


def get_loaded_fake_engines() -> set[Any]:
    """Return set of currently resident fake engine instances."""
    return set(_LOADED_FAKE_ENGINES)


def reset_fake_registry() -> None:
    """Clear fake engine tracking registry (for test setup/teardown)."""
    _LOADED_FAKE_ENGINES.clear()


class _BaseFakeEngine:
    """Base implementation providing state management and failure injection."""

    def __init__(
        self,
        fail_on_call: set[int] | None = None,
        oom_once: bool = False,
        delay_sec: float = 0.0,
    ) -> None:
        self._is_loaded: bool = False
        self.load_count: int = 0
        self.unload_count: int = 0
        self.call_count: int = 0
        self.fail_on_call: set[int] = fail_on_call or set()
        self.oom_once: bool = oom_once
        self.delay_sec: float = delay_sec

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    def load(self, device: str) -> None:
        self._is_loaded = True
        self.load_count += 1
        _LOADED_FAKE_ENGINES.add(self)

    def unload(self) -> None:
        self._is_loaded = False
        self.unload_count += 1
        _LOADED_FAKE_ENGINES.discard(self)

    def estimated_vram_mb(self) -> int:
        return 100

    def _before_call(self) -> None:
        if not self._is_loaded:
            raise InternalError(
                f"{self.__class__.__name__} called while not loaded.",
                hint="Engine must be loaded via ModelManager before inference.",
            )
        self.call_count += 1
        if self.oom_once and self.call_count == 1:
            raise RuntimeError("CUDA out of memory: tried to allocate 512 MiB")
        if self.call_count in self.fail_on_call:
            raise RuntimeError(f"{self.__class__.__name__} simulated failure on call #{self.call_count}")
        if self.delay_sec > 0:
            time.sleep(self.delay_sec)


class FakeTts(_BaseFakeEngine):
    """Deterministic TTS double generating pure sine tones with duration proportional to text length."""

    key = "tts"
    sample_rate: int = 24000

    def synthesize(
        self,
        text: str,
        reference_path: Path,
        expressiveness: float,
    ) -> np.ndarray:
        self._before_call()

        # Duration: 0.05 s per character, minimum 0.2 s
        char_count = max(len(text), 1)
        duration_sec = max(0.2, char_count * 0.05)
        num_samples = int(duration_sec * self.sample_rate)

        # Amplitude scaled by expressiveness: 0.2 + 0.6 * expressiveness
        amplitude = float(np.clip(0.2 + 0.6 * expressiveness, 0.05, 0.95))

        # Generate a smooth 440 Hz sine tone
        t = np.linspace(0, duration_sec, num_samples, endpoint=False, dtype=np.float32)
        sine_wave = (amplitude * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
        return sine_wave


class FakeVc(_BaseFakeEngine):
    """Deterministic Voice Conversion double preserving input chunk duration."""

    key = "vc"
    sample_rate: int = 24000

    def convert(
        self,
        input_path: Path,
        reference_path: Path,
    ) -> np.ndarray:
        self._before_call()

        # Read input audio to match its exact duration and RMS energy
        data, in_sr = sf.read(str(input_path), dtype="float32")
        if data.ndim > 1:
            data = np.mean(data, axis=1)

        duration_sec = float(len(data)) / float(in_sr)
        num_samples = int(duration_sec * self.sample_rate)

        # Calculate input RMS
        rms = float(np.sqrt(np.mean(data**2))) if len(data) > 0 else 0.1
        amplitude = float(np.clip(rms, 0.05, 0.9))

        t = np.linspace(0, duration_sec, num_samples, endpoint=False, dtype=np.float32)
        # 330 Hz tone matching input duration
        output_wave = (amplitude * np.sin(2 * np.pi * 330.0 * t)).astype(np.float32)
        return output_wave


class FakeEmotion(_BaseFakeEngine):
    """Deterministic Emotion double using rule-based keyword mapping."""

    key = "emotion"

    def classify(self, texts: list[str]) -> list[str]:
        self._before_call()
        results: list[str] = []

        for text in texts:
            lower = text.lower()
            if "!" in text:
                results.append("joy")
            elif "?" in text:
                results.append("surprise")
            elif "sad" in lower or "cry" in lower:
                results.append("sadness")
            elif "angry" in lower or "hate" in lower:
                results.append("anger")
            else:
                results.append("neutral")

        return results
