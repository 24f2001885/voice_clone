"""Data models for individual job chunks."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass
class JobChunk:
    job_id: str
    chunk_index: int
    kind: str
    status: str = "pending"
    id: int | None = None
    text: str | None = None
    detected_emotion: str | None = None
    expressiveness: float | None = None
    input_path: Path | None = None
    output_path: Path | None = None
    start_sec: float | None = None
    end_sec: float | None = None
    attempts: int = 0
    error_message: str | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any] | sqlite3.Row) -> JobChunk:
        """Construct a JobChunk model from a SQLite row mapping."""
        data = dict(row)
        input_path = Path(data["input_path"]) if data.get("input_path") else None
        output_path = Path(data["output_path"]) if data.get("output_path") else None
        return cls(
            id=data.get("id"),
            job_id=data["job_id"],
            chunk_index=int(data["chunk_index"]),
            kind=data["kind"],
            status=data.get("status", "pending"),
            text=data.get("text"),
            detected_emotion=data.get("detected_emotion"),
            expressiveness=data.get("expressiveness"),
            input_path=input_path,
            output_path=output_path,
            start_sec=data.get("start_sec"),
            end_sec=data.get("end_sec"),
            attempts=int(data.get("attempts", 0) or 0),
            error_message=data.get("error_message"),
        )
