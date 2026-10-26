"""GPU smoke test for real TTS engine (pytest -m gpu)."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from voxclone.audio.io import load_audio
from voxclone.config import load_config
from voxclone.engines.model_manager import ModelManager
from voxclone.storage.db import connect


@pytest.mark.gpu
def test_real_tts_smoke(tmp_path: Path) -> None:
    """Smoke test real F5-TTS inference on GPU hardware."""
    try:
        import torch
        if not torch.cuda.is_available():
            pytest.skip("CUDA GPU is not available on host system.")
    except ImportError:
        pytest.skip("PyTorch is not installed.")

    ref_env = os.environ.get("VOXCLONE_TEST_REFERENCE")
    if not ref_env or not Path(ref_env).is_file():
        pytest.skip("VOXCLONE_TEST_REFERENCE env variable not set to a valid WAV file.")

    config = load_config()
    db_path = tmp_path / "test_gpu.db"
    conn = connect(db_path)
    mgr = ModelManager(config=config, conn=conn)

    ref_audio, sr = load_audio(Path(ref_env))
    tts = mgr.acquire("tts")

    text = "Hello from the VoxClone GPU smoke test."
    out_audio = tts.synthesize(text=text, reference_audio=ref_audio)

    assert isinstance(out_audio, np.ndarray)
    assert out_audio.dtype == np.float32
    assert len(out_audio) > 0
    assert np.all(np.isfinite(out_audio))
    mgr.free_gpu_memory()
    conn.close()
