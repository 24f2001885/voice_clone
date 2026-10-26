"""Service layer for inspecting model residency, memory, and lifecycle logs."""

from pathlib import Path
from typing import Any

from voxclone.engines.model_manager import ModelManager, ModelStatus
from voxclone.models.model_event import ModelEvent
from voxclone.storage.db import get_db
from voxclone.storage.model_events_repo import delete_older_than, list_events


class ModelService:
    """Provides high-level business operations for neural model state and audit trails."""

    def __init__(self, model_manager: ModelManager, db_path: Path) -> None:
        self._manager = model_manager
        self._db_path = db_path

    def get_status(self) -> ModelStatus:
        """Inspect current resident model, device, and VRAM utilization."""
        return self._manager.status()

    def free_gpu_memory(self) -> dict[str, Any]:
        """Trigger explicit eviction of resident models and CUDA cache evacuation."""
        return self._manager.free_gpu_memory()

    def get_recent_events(self, limit: int = 50, model_key: str | None = None) -> list[ModelEvent]:
        """Fetch audit trail of recent model transitions (load, unload, oom)."""
        with get_db(self._db_path) as conn:
            return list_events(conn, limit=limit, model_key=model_key)

    def prune_audit_logs(self, days: int = 90) -> int:
        """Prune model transition events older than the specified retention horizon."""
        with get_db(self._db_path) as conn:
            return delete_older_than(conn, days=days)
