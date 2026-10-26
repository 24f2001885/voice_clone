"""Persistence repository for model load/unload and OOM events."""

from datetime import datetime, timedelta, timezone
import sqlite3

from voxclone.models.model_event import ModelEvent
from voxclone.storage.db import utc_now_iso


def insert_event(
    conn: sqlite3.Connection,
    model_key: str,
    action: str,
    device: str,
    vram_free_before_mb: int | None = None,
    vram_free_after_mb: int | None = None,
    duration_ms: int | None = None,
    job_id: str | None = None,
) -> ModelEvent:
    """Insert a new model lifecycle event record and return the resulting ModelEvent object."""
    created_at = utc_now_iso()
    cursor = conn.execute(
        """
        INSERT INTO model_events (
            model_key, action, device, vram_free_before_mb,
            vram_free_after_mb, duration_ms, job_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            model_key,
            action,
            device,
            vram_free_before_mb,
            vram_free_after_mb,
            duration_ms,
            job_id,
            created_at,
        ),
    )
    event_id = cursor.lastrowid
    return ModelEvent(
        id=event_id,
        model_key=model_key,
        action=action,
        device=device,
        vram_free_before_mb=vram_free_before_mb,
        vram_free_after_mb=vram_free_after_mb,
        duration_ms=duration_ms,
        job_id=job_id,
        created_at=created_at,
    )


def list_events(
    conn: sqlite3.Connection,
    limit: int = 100,
    model_key: str | None = None,
) -> list[ModelEvent]:
    """Retrieve recent model events ordered by creation timestamp descending."""
    if model_key:
        cursor = conn.execute(
            """
            SELECT id, model_key, action, device, vram_free_before_mb,
                   vram_free_after_mb, duration_ms, job_id, created_at
            FROM model_events
            WHERE model_key = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?;
            """,
            (model_key, limit),
        )
    else:
        cursor = conn.execute(
            """
            SELECT id, model_key, action, device, vram_free_before_mb,
                   vram_free_after_mb, duration_ms, job_id, created_at
            FROM model_events
            ORDER BY created_at DESC, id DESC
            LIMIT ?;
            """,
            (limit,),
        )
    return [ModelEvent.from_row(row) for row in cursor.fetchall()]


def delete_older_than(conn: sqlite3.Connection, days: int) -> int:
    """Purge event records older than specified number of days; returns count of removed rows."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    cursor = conn.execute(
        "DELETE FROM model_events WHERE created_at < ?;",
        (cutoff_iso,),
    )
    return cursor.rowcount
