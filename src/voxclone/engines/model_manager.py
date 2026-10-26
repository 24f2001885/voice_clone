"""Single-resident AI neural model manager with lifecycle tracking and VRAM guarding."""

from contextlib import contextmanager
from dataclasses import dataclass
import gc
from pathlib import Path
import threading
import time
from typing import Any, Generator

from voxclone.config import AppConfig
from voxclone.constants import MODEL_KEYS
from voxclone.engines import build_engine
from voxclone.engines.base import ModelEngine
from voxclone.errors import (
    ChunkOutOfMemoryError,
    GpuUnavailableError,
    InsufficientVramError,
    InternalError,
)
from voxclone.storage.db import get_db
from voxclone.storage.model_events_repo import insert_event

# Optional torch detection for GPU memory inspection and cache clearing
try:
    import torch  # type: ignore[import-untyped]

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


@dataclass(frozen=True)
class ModelStatus:
    """Current residency and hardware acceleration state of the model manager."""

    resident_key: str | None
    device: str
    vram_total_mb: int | None
    vram_used_mb: int | None
    vram_free_mb: int | None
    keep_warm: bool
    engine_mode: str


class ModelManager:
    """Manages neural engine lifecycle ensuring strictly <= 1 model resident in memory.

    Enforces single-resident model architecture (TDR Section 4):
      - Prior model is fully unloaded, reference dropped, and VRAM flushed before loading next.
      - Enforces VRAM budget checking to prevent hypervisor or CUDA OOM.
      - Logs all state transitions (load, unload, oom) to SQLite model_events table.
      - Thread-safe via internal reentrant lock.
    """

    def __init__(self, config: AppConfig, db_path: Path | None = None) -> None:
        self._config = config
        self._db_path = db_path or config.db_path
        self._lock = threading.RLock()
        self._resident_key: str | None = None
        self._resident_engine: ModelEngine | None = None
        self._resolved_device = self._resolve_device(config.device, config.engine_mode)

    @property
    def resident_key(self) -> str | None:
        """Return key of currently resident model, or None if no model is loaded."""
        with self._lock:
            return self._resident_key

    @property
    def resident_engine(self) -> ModelEngine | None:
        """Return currently resident engine instance, or None if unloaded."""
        with self._lock:
            return self._resident_engine

    @property
    def resolved_device(self) -> str:
        """Return the target hardware acceleration device string ('cuda' or 'cpu')."""
        return self._resolved_device

    def _resolve_device(self, configured_device: str, engine_mode: str) -> str:
        """Resolve device setting taking into account hardware availability and engine mode."""
        if engine_mode == "fake":
            return "cuda" if configured_device == "cuda" else "cpu"

        if configured_device == "cuda":
            if not HAS_TORCH or not torch.cuda.is_available():
                raise GpuUnavailableError(
                    "CUDA acceleration was explicitly requested, but no compatible NVIDIA GPU was detected.",
                    hint="Ensure NVIDIA drivers and CUDA toolkit are installed, or set device to 'auto' or 'cpu'.",
                )
            return "cuda"

        if configured_device == "cpu":
            return "cpu"

        # "auto" resolution
        if HAS_TORCH and torch.cuda.is_available():
            return "cuda"
        return "cpu"

    def get_vram_info(self) -> tuple[int | None, int | None, int | None]:
        """Query total, used, and free VRAM in MB. Returns (total, used, free)."""
        if self._resolved_device == "cuda" and HAS_TORCH and torch.cuda.is_available():
            try:
                free_b, total_b = torch.cuda.mem_get_info()
                free_mb = int(free_b // (1024 * 1024))
                total_mb = int(total_b // (1024 * 1024))
                used_mb = total_mb - free_mb
                return total_mb, used_mb, free_mb
            except Exception:
                return None, None, None
        return None, None, None

    def status(self) -> ModelStatus:
        """Inspect current operational status and memory allocation."""
        with self._lock:
            total_mb, used_mb, free_mb = self.get_vram_info()
            return ModelStatus(
                resident_key=self._resident_key,
                device=self._resolved_device,
                vram_total_mb=total_mb,
                vram_used_mb=used_mb,
                vram_free_mb=free_mb,
                keep_warm=self._config.keep_warm,
                engine_mode=self._config.engine_mode,
            )

    def _log_event(
        self,
        model_key: str,
        action: str,
        device: str,
        vram_free_before_mb: int | None = None,
        vram_free_after_mb: int | None = None,
        duration_ms: int | None = None,
        job_id: str | None = None,
    ) -> None:
        """Persist a model lifecycle transition to SQLite."""
        if not self._db_path.exists():
            return
        try:
            with get_db(self._db_path) as conn:
                insert_event(
                    conn=conn,
                    model_key=model_key,
                    action=action,
                    device=device,
                    vram_free_before_mb=vram_free_before_mb,
                    vram_free_after_mb=vram_free_after_mb,
                    duration_ms=duration_ms,
                    job_id=job_id,
                )
        except Exception:
            # Lifecycle logging must never crash the primary execution pipeline
            pass

    def acquire(self, model_key: str, job_id: str | None = None) -> ModelEngine:
        """Acquire reference to the requested model, loading it if not already resident.

        If a different model is resident, it is cleanly unloaded first.
        """
        if model_key not in MODEL_KEYS:
            raise InternalError(
                f"Invalid model key requested: '{model_key}'",
                hint=f"Supported model keys are: {', '.join(MODEL_KEYS)}",
            )

        with self._lock:
            # 1. Fast path: Requested model is already resident and ready
            if self._resident_key == model_key and self._resident_engine is not None and self._resident_engine.is_loaded:
                return self._resident_engine

            # 2. Unload currently resident model if different
            if self._resident_engine is not None:
                self._unload_resident(job_id=job_id)

            # 3. Memory budget pre-flight check
            _, _, free_before_mb = self.get_vram_info()
            engine = build_engine(model_key, self._config)
            estimated_mb = engine.estimated_vram_mb()

            if self._resolved_device == "cuda" and free_before_mb is not None:
                if estimated_mb > free_before_mb or estimated_mb > self._config.vram_budget_mb:
                    raise InsufficientVramError(
                        f"Model '{model_key}' requires ~{estimated_mb} MB VRAM, but only {free_before_mb} MB is free (budget {self._config.vram_budget_mb} MB).",
                        hint="Free GPU memory in System menu or reduce chunk duration in settings.",
                    )

            # 4. Load the target engine
            start_time = time.perf_counter()
            try:
                engine.load(self._resolved_device)
            except Exception as exc:
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                _, _, free_after_fail = self.get_vram_info()
                self._log_event(
                    model_key=model_key,
                    action="oom",
                    device=self._resolved_device,
                    vram_free_before_mb=free_before_mb,
                    vram_free_after_mb=free_after_fail,
                    duration_ms=elapsed_ms,
                    job_id=job_id,
                )
                # Attempt aggressive cleanup on failure
                self._flush_memory()
                raise ChunkOutOfMemoryError(
                    f"Out of memory loading neural model '{model_key}': {exc!s}",
                    hint="Close other GPU applications or restart VoxClone with smaller chunks.",
                ) from exc

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            _, _, free_after_mb = self.get_vram_info()

            self._resident_key = model_key
            self._resident_engine = engine

            self._log_event(
                model_key=model_key,
                action="load",
                device=self._resolved_device,
                vram_free_before_mb=free_before_mb,
                vram_free_after_mb=free_after_mb,
                duration_ms=elapsed_ms,
                job_id=job_id,
            )

            return engine

    def _unload_resident(self, job_id: str | None = None) -> None:
        """Unload the currently resident engine and reclaim memory."""
        if self._resident_engine is None or self._resident_key is None:
            return

        key_to_unload = self._resident_key
        engine_to_unload = self._resident_engine
        _, _, free_before_mb = self.get_vram_info()
        start_time = time.perf_counter()

        try:
            engine_to_unload.unload()
        finally:
            self._resident_engine = None
            self._resident_key = None
            self._flush_memory()

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        _, _, free_after_mb = self.get_vram_info()

        self._log_event(
            model_key=key_to_unload,
            action="unload",
            device=self._resolved_device,
            vram_free_before_mb=free_before_mb,
            vram_free_after_mb=free_after_mb,
            duration_ms=elapsed_ms,
            job_id=job_id,
        )

    def _flush_memory(self) -> None:
        """Force garbage collection and PyTorch CUDA cache evacuation."""
        gc.collect()
        if HAS_TORCH and torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            except Exception:
                pass

    def unload(self, model_key: str | None = None, job_id: str | None = None) -> None:
        """Explicitly unload a specific model or the currently resident model."""
        with self._lock:
            if model_key is None or self._resident_key == model_key:
                self._unload_resident(job_id=job_id)

    def release(self, model_key: str, job_id: str | None = None) -> None:
        """Release the engine after a task completes, respecting the keep_warm policy."""
        with self._lock:
            if not self._config.keep_warm:
                self._unload_resident(job_id=job_id)

    @contextmanager
    def use(self, model_key: str, job_id: str | None = None) -> Generator[ModelEngine, None, None]:
        """Scoped context manager for executing tasks with a single resident engine."""
        engine = self.acquire(model_key, job_id=job_id)
        try:
            yield engine
        finally:
            self.release(model_key, job_id=job_id)

    def free_gpu_memory(self, job_id: str | None = None) -> dict[str, Any]:
        """Manually unload any resident model and purge GPU VRAM caches (TDR S-52)."""
        with self._lock:
            _, _, free_before = self.get_vram_info()
            unloaded_key = self._resident_key
            self._unload_resident(job_id=job_id)
            self._flush_memory()
            _, _, free_after = self.get_vram_info()

            freed_mb = None
            if free_before is not None and free_after is not None:
                freed_mb = max(0, free_after - free_before)

            return {
                "unloaded_key": unloaded_key,
                "device": self._resolved_device,
                "freed_mb": freed_mb,
                "free_now_mb": free_after,
            }

    def close(self) -> None:
        """Cleanly tear down the model manager and release all resident resources."""
        with self._lock:
            self._unload_resident()
