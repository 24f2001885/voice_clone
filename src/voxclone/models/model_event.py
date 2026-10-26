"""ModelEvent dataclass mirroring the model_events SQLite schema."""

from dataclasses import dataclass
import sqlite3


@dataclass(frozen=True)
class ModelEvent:
    """Immutable record of an AI model lifecycle transition or memory event."""

    id: int | None
    model_key: str  # "tts", "vc", or "emotion"
    action: str  # "load", "unload", or "oom"
    device: str
    vram_free_before_mb: int | None
    vram_free_after_mb: int | None
    duration_ms: int | None
    job_id: str | None
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ModelEvent":
        """Instantiate a ModelEvent from a database query row."""
        return cls(
            id=int(row["id"]) if row["id"] is not None else None,
            model_key=str(row["model_key"]),
            action=str(row["action"]),
            device=str(row["device"]),
            vram_free_before_mb=int(row["vram_free_before_mb"]) if row["vram_free_before_mb"] is not None else None,
            vram_free_after_mb=int(row["vram_free_after_mb"]) if row["vram_free_after_mb"] is not None else None,
            duration_ms=int(row["duration_ms"]) if row["duration_ms"] is not None else None,
            job_id=str(row["job_id"]) if row["job_id"] is not None else None,
            created_at=str(row["created_at"]),
        )
