"""Repository for persisting and querying job chunks in SQLite."""
from __future__ import annotations

import sqlite3
from typing import Any

from voxclone.errors import InternalError
from voxclone.models.job_chunk import JobChunk


def insert_chunks(
    conn: sqlite3.Connection,
    job_id: str,
    chunks: list[dict[str, Any]],
) -> None:
    """Insert multiple chunk records for a job in a single atomic transaction."""
    cursor = conn.cursor()
    records = []
    for c in chunks:
        records.append(
            (
                job_id,
                int(c["chunk_index"]),
                c["kind"],
                c.get("status", "pending"),
                c.get("text"),
                c.get("detected_emotion"),
                c.get("expressiveness"),
                str(c["input_path"]) if c.get("input_path") else None,
                str(c["output_path"]) if c.get("output_path") else None,
                c.get("start_sec"),
                c.get("end_sec"),
                int(c.get("attempts", 0) or 0),
                c.get("error_message"),
            )
        )
    try:
        cursor.executemany(
            """
            INSERT INTO job_chunks (
                job_id, chunk_index, kind, status, text,
                detected_emotion, expressiveness, input_path,
                output_path, start_sec, end_sec, attempts, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            records,
        )
        conn.commit()
    except sqlite3.IntegrityError as err:
        conn.rollback()
        raise InternalError(
            f"Failed inserting chunks for job {job_id}: {err}",
        ) from err


def list_chunks(conn: sqlite3.Connection, job_id: str) -> list[JobChunk]:
    """Retrieve all chunks belonging to a job, ordered by chunk_index."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM job_chunks WHERE job_id = ? ORDER BY chunk_index ASC",
        (job_id,),
    )
    rows = cursor.fetchall()
    return [JobChunk.from_row(row) for row in rows]


def get_chunk(
    conn: sqlite3.Connection,
    job_id: str,
    chunk_index: int,
) -> JobChunk | None:
    """Retrieve a specific chunk by job ID and index."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM job_chunks WHERE job_id = ? AND chunk_index = ?",
        (job_id, chunk_index),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return JobChunk.from_row(row)


def update_chunk(
    conn: sqlite3.Connection,
    job_id: str,
    chunk_index: int,
    **fields: Any,
) -> None:
    """Update fields of a specific chunk."""
    if not fields:
        return
    clauses = []
    params = []
    for k, v in fields.items():
        clauses.append(f"{k} = ?")
        params.append(str(v) if hasattr(v, "__fspath__") else v)
    params.extend([job_id, chunk_index])

    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE job_chunks SET {', '.join(clauses)} WHERE job_id = ? AND chunk_index = ?",
        tuple(params),
    )
    conn.commit()


def increment_attempts(
    conn: sqlite3.Connection,
    job_id: str,
    chunk_index: int,
) -> int:
    """Increment chunk attempt counter and return new count."""
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE job_chunks SET attempts = attempts + 1 WHERE job_id = ? AND chunk_index = ?",
        (job_id, chunk_index),
    )
    cursor.execute(
        "SELECT attempts FROM job_chunks WHERE job_id = ? AND chunk_index = ?",
        (job_id, chunk_index),
    )
    row = cursor.fetchone()
    conn.commit()
    return int(row["attempts"]) if row else 0


def count_by_status(conn: sqlite3.Connection, job_id: str) -> dict[str, int]:
    """Return dictionary of status counts for a job's chunks."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status, COUNT(*) as count FROM job_chunks WHERE job_id = ? GROUP BY status",
        (job_id,),
    )
    rows = cursor.fetchall()
    return {row["status"]: row["count"] for row in rows}


def delete_for_job(conn: sqlite3.Connection, job_id: str) -> int:
    """Delete all chunks for a job."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM job_chunks WHERE job_id = ?", (job_id,))
    conn.commit()
    return cursor.rowcount


def delete_finished_older_than(conn: sqlite3.Connection, days: int) -> int:
    """Delete chunk records of completed jobs older than N days."""
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM job_chunks
        WHERE job_id IN (
            SELECT id FROM jobs
            WHERE status IN ('succeeded', 'failed', 'cancelled')
            AND datetime(finished_at) <= datetime('now', '-' || ? || ' days')
        )
        """,
        (days,),
    )
    conn.commit()
    return cursor.rowcount
