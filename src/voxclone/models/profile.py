"""VoiceProfile dataclass mirroring the voice_profiles SQLite schema."""

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any


@dataclass(frozen=True)
class VoiceProfile:
    """Immutable representation of an enrolled voice reference profile."""

    id: str
    name: str
    reference_path: Path
    source_type: str  # "file" or "mic"
    original_filename: str | None
    duration_sec: float
    sample_rate: int
    quality_score: float | None
    quality_notes: str | None
    sha256: str
    consent_confirmed: bool
    consent_confirmed_at: str
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "VoiceProfile":
        """Instantiate a VoiceProfile from a database query row."""
        return cls(
            id=str(row["id"]),
            name=str(row["name"]),
            reference_path=Path(str(row["reference_path"])),
            source_type=str(row["source_type"]),
            original_filename=str(row["original_filename"]) if row["original_filename"] is not None else None,
            duration_sec=float(row["duration_sec"]),
            sample_rate=int(row["sample_rate"]),
            quality_score=float(row["quality_score"]) if row["quality_score"] is not None else None,
            quality_notes=str(row["quality_notes"]) if row["quality_notes"] is not None else None,
            sha256=str(row["sha256"]),
            consent_confirmed=bool(row["consent_confirmed"]),
            consent_confirmed_at=str(row["consent_confirmed_at"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def to_summary_dict(self) -> dict[str, Any]:
        """Return condensed summary dictionary for table display (TDR 5.1)."""
        return {
            "id": self.id,
            "name": self.name,
            "duration_sec": self.duration_sec,
            "created_at": self.created_at,
        }
