"""Engine interface definitions and protocols for TTS, VC, and emotion analysis."""

from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class ModelEngine(Protocol):
    """Base protocol for managed AI neural engines."""

    key: str  # One of MODEL_KEYS: 'tts', 'vc', 'emotion'

    @property
    def is_loaded(self) -> bool:
        """Return True if model weights are loaded and resident in memory."""
        ...

    def load(self, device: str) -> None:
        """Load model weights onto the target execution device ('cuda', 'cpu')."""
        ...

    def unload(self) -> None:
        """Release all model references and tensors from memory."""
        ...

    def estimated_vram_mb(self) -> int:
        """Return the estimated VRAM footprint of the model in megabytes (MB)."""
        ...


@runtime_checkable
class TtsEngine(ModelEngine, Protocol):
    """Protocol for zero-shot text-to-speech synthesis models."""

    sample_rate: int  # Output audio sampling rate in Hertz (e.g., 24000)

    def synthesize(
        self,
        text: str,
        reference_path: Path,
        expressiveness: float,
    ) -> np.ndarray:
        """Synthesize text using the reference voice profile.

        Args:
            text: Input sentence or passage.
            reference_path: Path to reference voice WAV file.
            expressiveness: Expressiveness control factor in range [0.25, 1.0].

        Returns:
            1D float32 numpy array normalized to range [-1.0, 1.0].
        """
        ...


@runtime_checkable
class VcEngine(ModelEngine, Protocol):
    """Protocol for zero-shot voice conversion models."""

    sample_rate: int  # Converted audio sampling rate in Hertz (e.g., 24000)

    def convert(
        self,
        input_path: Path,
        reference_path: Path,
    ) -> np.ndarray:
        """Convert speaker identity of input audio to match the reference voice.

        Args:
            input_path: Path to source audio chunk WAV file.
            reference_path: Path to reference voice WAV file.

        Returns:
            1D float32 numpy array normalized to range [-1.0, 1.0].
        """
        ...


@runtime_checkable
class EmotionEngine(ModelEngine, Protocol):
    """Protocol for sentence-level emotion classification models."""

    def classify(self, texts: list[str]) -> list[str]:
        """Classify emotional state of text passages.

        Args:
            texts: List of text passages to evaluate.

        Returns:
            List of detected emotion labels matching EMOTION_LABELS in identical order.
        """
        ...
