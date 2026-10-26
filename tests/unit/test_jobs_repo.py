"""Unit tests for jobs and job_chunks database persistence."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from voxclone.errors import InternalError
from voxclone.storage import chunks_repo, jobs_repo


def test_job_create_and_get(db_conn: sqlite3.Connection) -> None:
    """A created job is persisted in SQLite with status 'queued'."""
    job = jobs_repo.create_job(
        conn=db_conn,
        job_type="text_to_voice",
        profile_id=None,
        profile_name_snapshot="TestVoice",
        input_source="text",
        output_mode="save",
        input_text="Hello world.",
        emotion_mode="normal",
    )
    assert job.id is not None
    assert job.status == "queued"
    assert job.profile_name_snapshot == "TestVoice"
    assert job.input_text == "Hello world."

    fetched = jobs_repo.get_job(db_conn, job.id)
    assert fetched is not None
    assert fetched.id == job.id
    assert fetched.is_resumable is False


def test_job_status_transitions_and_mark_finished(db_conn: sqlite3.Connection) -> None:
    """Verify job status transition to running, then finished with stats."""
    job = jobs_repo.create_job(
        conn=db_conn,
        job_type="text_to_voice",
        profile_id=None,
        profile_name_snapshot="Voice1",
        input_source="text",
        output_mode="save",
        input_text="Sample",
    )

    jobs_repo.mark_started(db_conn, job.id)
    running_job = jobs_repo.get_job(db_conn, job.id)
    assert running_job is not None
    assert running_job.status == "running"
    assert running_job.started_at is not None

    jobs_repo.mark_finished(
        conn=db_conn,
        job_id=job.id,
        status="succeeded",
        output_path=Path("/app/outputs/out.wav"),
        output_sample_rate=24000,
        output_duration_sec=3.5,
        elapsed_ms=1200,
        real_time_factor=0.34,
    )

    finished_job = jobs_repo.get_job(db_conn, job.id)
    assert finished_job is not None
    assert finished_job.status == "succeeded"
    assert finished_job.finished_at is not None
    assert finished_job.output_duration_sec == 3.5
    assert finished_job.real_time_factor == 0.34


def test_chunk_lifecycle_and_foreign_key_cascade(db_conn: sqlite3.Connection) -> None:
    """Inserting chunks, updating statuses, and cascading deletion on job removal."""
    job = jobs_repo.create_job(
        conn=db_conn,
        job_type="text_to_voice",
        profile_id=None,
        profile_name_snapshot="VoiceCascade",
        input_source="text",
        output_mode="save",
        input_text="Sentence one. Sentence two.",
    )

    chunks = [
        {"chunk_index": 0, "kind": "sentence", "text": "Sentence one."},
        {"chunk_index": 1, "kind": "sentence", "text": "Sentence two."},
    ]
    chunks_repo.insert_chunks(db_conn, job.id, chunks)

    fetched_chunks = chunks_repo.list_chunks(db_conn, job.id)
    assert len(fetched_chunks) == 2
    assert fetched_chunks[0].chunk_index == 0
    assert fetched_chunks[0].status == "pending"

    # Update chunk status
    chunks_repo.update_chunk(db_conn, job.id, 0, status="converted")
    counts = chunks_repo.count_by_status(db_conn, job.id)
    assert counts.get("converted") == 1
    assert counts.get("pending") == 1

    # Cascade deletion
    deleted = jobs_repo.delete_job(db_conn, job.id)
    assert deleted is True
    assert jobs_repo.get_job(db_conn, job.id) is None
    # Chunks must be deleted by cascade
    assert len(chunks_repo.list_chunks(db_conn, job.id)) == 0


def test_duplicate_chunk_index_raises_internal_error(db_conn: sqlite3.Connection) -> None:
    """Inserting duplicate (job_id, chunk_index) violates unique constraint and raises InternalError."""
    job = jobs_repo.create_job(
        conn=db_conn,
        job_type="text_to_voice",
        profile_id=None,
        profile_name_snapshot="VoiceDup",
        input_source="text",
        output_mode="save",
        input_text="Text",
    )

    chunks = [
        {"chunk_index": 0, "kind": "sentence", "text": "One"},
        {"chunk_index": 0, "kind": "sentence", "text": "Duplicate"},
    ]
    with pytest.raises(InternalError) as exc_info:
        chunks_repo.insert_chunks(db_conn, job.id, chunks)
    assert exc_info.value.code == "VX-900"
