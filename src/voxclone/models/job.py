"""Data models for jobs and job results."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass
class Job:
    id: str
    job_type: str
    status: str
    profile_id: str | None
    profile_name_snapshot: str
    input_source: str
    output_mode: str
    created_at: str
    input_path: Path | None = None
    input_text: str | None = None
    emotion_mode: str | None = None
    output_path: Path | None = None
    output_sample_rate: int | None = None
    output_duration_sec: float | None = None
    total_chunks: int = 0
    completed_chunks: int = 0
    error_code: str | None = None
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    elapsed_ms: int | None = None
    real_time_factor: float | None = None

    @property
    def input_audio_path(self) -> Path | None:
        """Alias property for input_path when job is recording-to-voice."""
        return self.input_path

    @classmethod
    def from_row(cls, row: Mapping[str, Any] | sqlite3.Row) -> Job:
        """Construct a Job model from a SQLite row mapping."""
        data = dict(row)
        input_path = Path(data["input_path"]) if data.get("input_path") else None
        output_path = Path(data["output_path"]) if data.get("output_path") else None
        return cls(
            id=data["id"],
            job_type=data["job_type"],
            status=data["status"],
            profile_id=data.get("profile_id"),
            profile_name_snapshot=data["profile_name_snapshot"],
            input_source=data["input_source"],
            input_path=input_path,
            input_text=data.get("input_text"),
            emotion_mode=data.get("emotion_mode"),
            output_mode=data["output_mode"],
            output_path=output_path,
            output_sample_rate=data.get("output_sample_rate"),
            output_duration_sec=data.get("output_duration_sec"),
            total_chunks=int(data.get("total_chunks") or 0),
            completed_chunks=int(data.get("completed_chunks") or 0),
            error_code=data.get("error_code"),
            error_message=data.get("error_message"),
            created_at=data["created_at"],
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            elapsed_ms=data.get("elapsed_ms"),
            real_time_factor=data.get("real_time_factor"),
        )

    @property
    def is_resumable(self) -> bool:
        """True when a job failed or was cancelled before completing all chunks."""
        return (
            self.status in ("failed", "cancelled")
            and self.completed_chunks < self.total_chunks
        )


@dataclass(frozen=True)
class JobResult:
    """Immutable final result returned upon job completion."""
    job_id: str
    output_path: Path | None
    duration_sec: float
    sample_rate: int
    elapsed_ms: int
    real_time_factor: float
    played: bool = False
    saved: bool = False
