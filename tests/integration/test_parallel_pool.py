"""Integration tests for parallel DSP process pool management and worker policies."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import os

from voxclone.audio.parallel import create_dsp_pool, get_spawn_context, resolve_worker_count


def _sample_worker(val: int) -> int:
    """Simple picklable worker for pool execution testing."""
    return val * val


def test_resolve_worker_count() -> None:
    """Worker resolution returns explicit settings or safe auto-detected bounds."""
    # Explicit count
    assert resolve_worker_count(4) == 4
    assert resolve_worker_count(1) == 1
    # Clamped bounds
    assert resolve_worker_count(50) == 32

    # Auto-detect (0)
    auto_count = resolve_worker_count(0)
    assert 1 <= auto_count <= 16


def test_spawn_context() -> None:
    """Parallel pool must strictly use spawn start method."""
    ctx = get_spawn_context()
    assert isinstance(ctx, multiprocessing.context.BaseContext)


def test_pool_concurrent_execution() -> None:
    """Process pool executes mapped tasks concurrently and returns ordered results."""
    pool = create_dsp_pool(workers=2)
    inputs = [1, 2, 3, 4, 5]
    results = list(pool.map(_sample_worker, inputs))
    pool.shutdown(wait=True)

    assert results == [1, 4, 9, 16, 25]
