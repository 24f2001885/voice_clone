"""Repository for persisting and querying jobs in SQLite."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from voxclone.models.job import Job


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(
    conn: sqlite3.Connection,
    job_type: str,
    profile_id: str | None,
    profile_name_snapshot: str,
    input_source: str,
    output_mode: str,
    input_path: Path | None = None,
    input_text: str | None = None,
    emotion_mode: str | None = None,
) -> Job:
    """Create a new job record with 'queued' status."""
    job_id = str(uuid.uuid4())
    now = _utc_now_iso()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO jobs (
            id, job_type, status, profile_id, profile_name_snapshot,
            input_source, input_path, input_text, emotion_mode,
            output_mode, total_chunks, completed_chunks, created_at
        ) VALUES (?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
        """,
        (
            job_id,
            job_type,
            profile_id,
            profile_name_snapshot,
            input_source,
            str(input_path) if input_path else None,
            input_text,
            emotion_mode,
            output_mode,
            now,
        ),
    )
    conn.commit()
    return get_job(conn, job_id)  # type: ignore[return-value]


def get_job(conn: sqlite3.Connection, job_id: str) -> Job | None:
    """Retrieve a single job by UUID."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    if not row:
        return None
    return Job.from_row(row)


def list_jobs(
    conn: sqlite3.Connection,
    status: str | None = None,
    job_type: str | None = None,
    limit: int = 50,
) -> list[Job]:
    """List jobs ordered by creation date descending, optionally filtered."""
    cursor = conn.cursor()
    query = "SELECT * FROM jobs"
    clauses: list[str] = []
    params: list[Any] = []

    if status:
        clauses.append("status = ?")
        params.append(status)
    if job_type:
        clauses.append("job_type = ?")
        params.append(job_type)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    return [Job.from_row(row) for row in rows]


def delete_job(conn: sqlite3.Connection, job_id: str) -> bool:
    """Delete a job and its associated chunks via foreign key cascade."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    return cursor.rowcount > 0


def mark_started(conn: sqlite3.Connection, job_id: str) -> None:
    """Mark a job as running and stamp started_at."""
    now = _utc_now_iso()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE jobs SET status = 'running', started_at = ? WHERE id = ?",
        (now, job_id),
    )
    conn.commit()


def set_total_chunks(conn: sqlite3.Connection, job_id: str, n: int) -> None:
    """Set the total number of chunks for a job."""
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE jobs SET total_chunks = ? WHERE id = ?",
        (n, job_id),
    )
    conn.commit()


def increment_completed(conn: sqlite3.Connection, job_id: str) -> int:
    """Increment completed_chunks count by 1 and return the new total."""
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE jobs SET completed_chunks = completed_chunks + 1 WHERE id = ?",
        (job_id,),
    )
    cursor.execute("SELECT completed_chunks FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.commit()
    return int(row["completed_chunks"]) if row else 0


def mark_finished(
    conn: sqlite3.Connection,
    job_id: str,
    status: str,
    output_path: Path | None = None,
    output_sample_rate: int | None = None,
    output_duration_sec: float | None = None,
    elapsed_ms: int | None = None,
    real_time_factor: float | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    """Mark a job as finished (succeeded, failed, or cancelled) and record stats."""
    now = _utc_now_iso()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE jobs
        SET status = ?,
            finished_at = ?,
            output_path = ?,
            output_sample_rate = ?,
            output_duration_sec = ?,
            elapsed_ms = ?,
            real_time_factor = ?,
            error_code = ?,
            error_message = ?
        WHERE id = ?
        """,
        (
            status,
            now,
            str(output_path) if output_path else None,
            output_sample_rate,
            output_duration_sec,
            elapsed_ms,
            real_time_factor,
            error_code,
            error_message,
            job_id,
        ),
    )
    conn.commit()


def find_stale_running(conn: sqlite3.Connection) -> list[Job]:
    """Find jobs that were left in 'running' state upon crash/unexpected exit."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE status = 'running' ORDER BY created_at ASC")
    rows = cursor.fetchall()
    return [Job.from_row(row) for row in rows]
