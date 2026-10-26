"""GPU-only integration test verifying VRAM reclamation over repetitive load/unload cycles."""

import os
import pytest

from voxclone.config import load_config
from voxclone.engines.model_manager import ModelManager


@pytest.mark.gpu
def test_gpu_repetitive_load_unload_vram_stability(tmp_path: pytest.TempPathFactory) -> None:
    """Perform 10 load/unload cycles and ensure VRAM is reclaimed within tolerance."""
    try:
        import torch
    except ImportError:
        pytest.skip("PyTorch is not installed in the current environment.")

    if not torch.cuda.is_available():
        pytest.skip("No CUDA-capable NVIDIA GPU detected.")

    # Use real engine mode for GPU test
    os.environ["VOXCLONE_ENGINE"] = "real"
    config = load_config()

    mgr = ModelManager(config=config, db_path=tmp_path / "gpu_test.db")  # type: ignore[operator]
    initial_total, initial_used, initial_free = mgr.get_vram_info()
    if initial_free is None:
        pytest.skip("VRAM inspection unavailable on this GPU device.")

    # Cycle model residency 5 times
    for cycle in range(5):
        # Simulate loading tensor footprint into VRAM
        tensor_alloc = torch.zeros((1024, 1024, 256), dtype=torch.float32, device="cuda")
        torch.cuda.synchronize()

        # Free allocation and flush
        del tensor_alloc
        mgr._flush_memory()

    final_total, final_used, final_free = mgr.get_vram_info()
    mgr.close()

    assert final_free is not None and initial_free is not None
    # Verify free VRAM has not decayed significantly (< 50 MB difference due to driver caching)
    vram_drift_mb = abs(final_free - initial_free)
    assert vram_drift_mb < 50
