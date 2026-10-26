"""GPU smoke test for real emotion classification engine (pytest -m gpu)."""
from __future__ import annotations

from pathlib import Path
import pytest

from voxclone.config import load_config
from voxclone.constants import EMOTION_LABELS
from voxclone.engines.model_manager import ModelManager


@pytest.mark.gpu
def test_real_emotion_smoke(tmp_path: Path) -> None:
    """Smoke test real DistilRoBERTa emotion classifier on GPU hardware."""
    try:
        import torch
        if not torch.cuda.is_available():
            pytest.skip("CUDA GPU is not available on host system.")
    except ImportError:
        pytest.skip("PyTorch is not installed.")

    try:
        import transformers
    except ImportError:
        pytest.skip("Transformers is not installed.")

    config = load_config()
    db_path = tmp_path / "test_emotion_gpu.db"
    mgr = ModelManager(config=config, db_path=db_path)

    try:
        emotion_engine = mgr.acquire("emotion")
    except Exception as exc:
        pytest.skip(f"Emotion model weights missing or unreadable: {exc}")

    test_sentences = [
        "I am so thrilled and ecstatic about this wonderful achievement!",  # Joy
        "I feel deeply heartbroken and grief-stricken by this tragedy.",      # Sadness
        "This outrageous and infuriating injustice makes me so angry!",      # Anger
        "I am terrified of what might be lurking in the dark hallway.",     # Fear
        "The standard meeting is scheduled for tomorrow at two o'clock.",    # Neutral
    ]

    labels = emotion_engine.classify(test_sentences)

    assert len(labels) == len(test_sentences)
    for lbl in labels:
        assert lbl in EMOTION_LABELS

    # At least 3 of 5 should match intended sentiment
    matches = 0
    if labels[0] == "joy":
        matches += 1
    if labels[1] == "sadness":
        matches += 1
    if labels[2] == "anger":
        matches += 1
    if labels[3] == "fear":
        matches += 1
    if labels[4] == "neutral":
        matches += 1

    assert matches >= 3

    mgr.free_gpu_memory()
    assert mgr.resident_key is None
    mgr.close()
