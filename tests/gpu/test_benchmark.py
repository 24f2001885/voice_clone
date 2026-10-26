"""GPU benchmark test measuring real-time factor and throughput (pytest -m gpu)."""
from __future__ import annotations

import os
from pathlib import Path
import time
import numpy as np
import pytest
import soundfile as sf

from voxclone.config import load_config
from voxclone.engines.model_manager import ModelManager


@pytest.mark.gpu
def test_gpu_benchmark_vc(tmp_path: Path) -> None:
    """Benchmark neural VC throughput on actual GPU hardware."""
    try:
        import torch
        if not torch.cuda.is_available():
            pytest.skip("CUDA GPU is not available on host system.")
    except ImportError:
        pytest.skip("PyTorch is not installed.")

    ref_env = os.environ.get("VOXCLONE_TEST_REFERENCE")
    if not ref_env or not Path(ref_env).is_file():
        pytest.skip("VOXCLONE_TEST_REFERENCE not set to a valid WAV file.")

    sr = 16000
    duration_sec = 4.0
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False, dtype=np.float32)
    in_audio = (0.3 * np.sin(2 * np.pi * 300.0 * t)).astype(np.float32)
    in_wav = tmp_path / "bench_input.wav"
    sf.write(str(in_wav), in_audio, sr)

    config = load_config()
    db_path = tmp_path / "bench.db"
    mgr = ModelManager(config=config, db_path=db_path)

    try:
        vc = mgr.acquire("vc")
    except Exception as exc:
        pytest.skip(f"VC model not loaded: {exc}")

    # Warm-up run
    _ = vc.convert(in_wav, Path(ref_env))

    # Timed run
    t0 = time.perf_counter()
    out = vc.convert(in_wav, Path(ref_env))
    elapsed = time.perf_counter() - t0

    rtf = elapsed / duration_sec
    print(f"\n[BENCHMARK] 4.0s audio processed in {elapsed:.3f}s (RTF = {rtf:.2f}x)")

    assert len(out) > 0
    assert rtf < 5.0  # Safe sanity bound
    mgr.free_gpu_memory()
    mgr.close()
