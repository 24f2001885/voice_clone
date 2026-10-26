"""Real emotion classification engine adapter using DistilRoBERTa."""
from __future__ import annotations

import gc
import logging
from typing import Any

from voxclone.constants import EMOTION_LABELS
from voxclone.engines.base import EmotionEngine
from voxclone.errors import InternalError, ModelWeightsMissingError

logger = logging.getLogger("voxclone.engines.real_emotion")

DEFAULT_MODEL_NAME = "j-hartmann/emotion-english-distilroberta-base"


class RealEmotion(EmotionEngine):
    """Emotion classifier adapter powered by Hugging Face DistilRoBERTa.

    Classifies input sentence passages into one of the 7 core emotions:
    anger, disgust, fear, joy, neutral, sadness, surprise.
    """

    key: str = "emotion"

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
        self.model_name = model_name
        self._is_loaded: bool = False
        self._pipeline: Any = None
        self._device: str = "cpu"

    @property
    def is_loaded(self) -> bool:
        """Return True if model and tokenizer are resident in memory."""
        return self._is_loaded

    def load(self, device: str) -> None:
        """Load DistilRoBERTa tokenizer and classifier weights onto target device."""
        if self._is_loaded:
            logger.debug("RealEmotion is already loaded on device %s", self._device)
            return

        try:
            import torch  # type: ignore[import-untyped]
            from transformers import pipeline  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ModelWeightsMissingError(
                f"Missing required ML libraries for emotion classifier: {exc.name or exc!s}. "
                "Ensure torch and transformers are installed."
            ) from exc

        self._device = device
        logger.info("Loading RealEmotion model '%s' onto device '%s'", self.model_name, device)

        try:
            device_id = 0 if device == "cuda" and torch.cuda.is_available() else -1
            self._pipeline = pipeline(
                "text-classification",
                model=self.model_name,
                device=device_id,
                truncation=True,
                max_length=512,
            )
            self._is_loaded = True
        except Exception as exc:
            self._is_loaded = False
            self._pipeline = None
            raise ModelWeightsMissingError(
                f"Failed loading emotion model '{self.model_name}': {exc}"
            ) from exc

    def unload(self) -> None:
        """Release pipeline references and flush PyTorch / system caches."""
        if not self._is_loaded:
            return

        logger.info("Unloading RealEmotion classifier from memory")
        self._pipeline = None
        self._is_loaded = False

        gc.collect()
        try:
            import torch  # type: ignore[import-untyped]
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def estimated_vram_mb(self) -> int:
        """Return estimated VRAM footprint in megabytes (~600 MB)."""
        return 600

    def classify(self, texts: list[str]) -> list[str]:
        """Classify emotional delivery for a list of text passages.

        Args:
            texts: List of string chunks to classify.

        Returns:
            List of normalized emotion labels in identical order.
        """
        if not self._is_loaded or self._pipeline is None:
            raise InternalError(
                "RealEmotion classifier called while not loaded.",
                hint="Engine must be loaded via ModelManager before classification.",
            )

        if not texts:
            return []

        clean_texts = [t.strip() if t.strip() else "." for t in texts]
        results: list[str] = []

        try:
            outputs = self._pipeline(clean_texts)
            for item in outputs:
                # pipeline returns dict {'label': 'joy', 'score': 0.98}
                raw_label = item.get("label", "neutral").strip().lower()
                if raw_label in EMOTION_LABELS:
                    results.append(raw_label)
                else:
                    results.append("neutral")
        except Exception as exc:
            logger.error("Emotion classification inference failed: %s", exc, exc_info=True)
            raise InternalError(f"Emotion classification failed: {exc}") from exc

        return results
