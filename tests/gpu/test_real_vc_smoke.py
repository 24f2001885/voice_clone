"""GPU smoke test for real Voice Conversion engine (pytest -m gpu)."""
from __future__ import annotations

import os
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf

from voxclone.config import load_config
from voxclone.engines.model_manager import ModelManager


@pytest.mark.gpu
def test_real_vc_smoke(tmp_path: Path) -> None:
    """Smoke test real neural voice conversion on GPU hardware."""
    try:
        import torch
        if not torch.cuda.is_available():
            pytest.skip("CUDA GPU is not available on host system.")
    except ImportError:
        pytest.skip("PyTorch is not installed.")

    ref_env = os.environ.get("VOXCLONE_TEST_REFERENCE")
    if not ref_env or not Path(ref_env).is_file():
        pytest.skip("VOXCLONE_TEST_REFERENCE env variable not set to a valid WAV file.")

    # Create synthetic input chunk
    in_sr = 16000
    t = np.linspace(0, 3.0, int(in_sr * 3.0), endpoint=False, dtype=np.float32)
    in_audio = (0.3 * np.sin(2 * np.pi * 300.0 * t)).astype(np.float32)
    in_wav = tmp_path / "vc_input.wav"
    sf.write(str(in_wav), in_audio, in_sr)

    config = load_config()
    db_path = tmp_path / "test_vc_gpu.db"
    mgr = ModelManager(config=config, db_path=db_path)

    try:
        vc_engine = mgr.acquire("vc")
    except Exception as exc:
        pytest.skip(f"Voice conversion model weights missing: {exc}")

    out_audio = vc_engine.convert(input_path=in_wav, reference_path=Path(ref_env))

    assert isinstance(out_audio, np.ndarray)
    assert out_audio.dtype == np.float32
    assert len(out_audio) > 0
    assert np.all(np.isfinite(out_audio))

    mgr.free_gpu_memory()
    assert mgr.resident_key is None
    mgr.close()
