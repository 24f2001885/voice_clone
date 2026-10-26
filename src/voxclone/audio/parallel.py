"""Multiprocessing worker pool management using 'spawn' start method (TDR Section 3.6)."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import logging
import multiprocessing
import os
from typing import Any

from voxclone.constants import RAM_RESERVE_MB, WORKER_RAM_MB

logger = logging.getLogger("voxclone.audio.parallel")


def resolve_worker_count(configured_workers: int = 0) -> int:
    """Calculate the optimal parallel worker count based on CPU cores and system RAM.

    Args:
        configured_workers: Explicit worker count from settings (0 = auto-detect).

    Returns:
        Safe integer worker count in range [1, 16].
    """
    if configured_workers > 0:
        return min(max(1, configured_workers), 32)

    cpu_cores = os.cpu_count() or 2

    # Estimate available system RAM
    total_ram_mb = 8192  # Default conservative estimate (8 GB)
    try:
        import psutil  # type: ignore[import-untyped]
        total_ram_mb = int(psutil.virtual_memory().total / (1024 * 1024))
    except Exception:
        pass

    usable_ram_mb = max(WORKER_RAM_MB, total_ram_mb - RAM_RESERVE_MB)
    ram_limited_workers = max(1, usable_ram_mb // WORKER_RAM_MB)

    chosen_workers = min(cpu_cores, ram_limited_workers)
    # Bound within [1, 16] to prevent OS scheduling thrash
    final_count = max(1, min(16, chosen_workers))
    logger.debug(
        "Resolved parallel workers: %d (CPU cores=%d, RAM=%d MB)",
        final_count,
        cpu_cores,
        total_ram_mb,
    )
    return final_count


def get_spawn_context() -> multiprocessing.context.BaseContext:
    """Return the explicit 'spawn' multiprocessing context."""
    return multiprocessing.get_context("spawn")


def create_dsp_pool(workers: int = 0) -> ProcessPoolExecutor:
    """Instantiate a ProcessPoolExecutor adhering to the 'spawn' context and worker budget.

    Args:
        workers: Optional explicit worker count (0 = auto).

    Returns:
        Configured ProcessPoolExecutor.
    """
    count = resolve_worker_count(workers)
    ctx = get_spawn_context()
    return ProcessPoolExecutor(max_workers=count, mp_context=ctx)
