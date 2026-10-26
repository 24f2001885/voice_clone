"""Integration tests for job resumption and startup sweep housekeeping (TDR Section 3.5 & P5)."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import threading
from typing import Any

import numpy as np
import pytest
import soundfile as sf

from voxclone.config import AppConfig
from voxclone.services.job_service import JobService
from voxclone.services.system_service import startup_sweep
from voxclone.storage import chunks_repo, jobs_repo


@pytest.fixture
def multi_chunk_wav(tmp_path: Path) -> Path:
    """Generate a 10-second audio recording guaranteed to split into multiple chunks."""
    sr = 24000
    duration_sec = 10.0
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False, dtype=np.float32)

    carrier = 0.3 * np.sin(2 * np.pi * 260.0 * t)
    # Pause dips at 3.5s and 7.0s
    envelope = np.ones_like(t)
    envelope[int(3.3 * sr) : int(3.7 * sr)] = 0.01
    envelope[int(6.8 * sr) : int(7.2 * sr)] = 0.01

    audio = (carrier * envelope).astype(np.float32)
    wav_path = tmp_path / "resume_test_input.wav"
    sf.write(str(wav_path), audio, sr)
    return wav_path


def test_resume_interrupted_recording_job(
    app_config: AppConfig,
    db_conn: sqlite3.Connection,
    model_manager: Any,
    make_profile: Any,
    multi_chunk_wav: Path,
) -> None:
    """An interrupted conversion job resumes from its checkpoint, reusing existing converted chunks."""
    profile = make_profile("ResumeWorkerSpeaker")
    job_svc = JobService(conn=db_conn, config=app_config, model_manager=model_manager)

    job = job_svc.create_recording_job(profile_id=profile.id, input_audio_path=multi_chunk_wav)

    # 1. Run job until first converted chunk, then cancel
    cancel_ev = threading.Event()
    events_run1 = []
    for ev in job_svc.run_job(job.id, cancel_event=cancel_ev):
        events_run1.append(ev)
        if ev.stage == "converting" and ev.chunk_index == 1:
            # Trigger cancel when chunk 1 starts, so chunk 0 was already converted and saved
            cancel_ev.set()

    refreshed_job = job_svc.get_job(job.id)
    assert refreshed_job is not None
    assert refreshed_job.status in ("cancelled", "running", "failed")

    # Inspect chunks: chunk 0 was converted and has valid output WAV
    chunks = chunks_repo.list_chunks(db_conn, job.id)
    assert len(chunks) >= 2
    converted_chunks = [c for c in chunks if c.status == "converted" and c.output_path and Path(c.output_path).is_file()]
    assert len(converted_chunks) >= 1
    reused_chunk_path = Path(converted_chunks[0].output_path)
    reused_chunk_mtime = reused_chunk_path.stat().st_mtime

    # 2. Resume the job to completion
    events_resume = []
    final_res = None
    for ev in job_svc.resume_job(job.id):
        events_resume.append(ev.stage)
        if ev.stage == "done":
            final_res = ev.result

    assert "done" in events_resume
    assert final_res is not None
    assert final_res.output_path is not None
    assert final_res.output_path.is_file()

    # Verify that previously converted chunk 0 was reused
    assert reused_chunk_path.stat().st_mtime == reused_chunk_mtime

    # All chunks should now be converted
    all_chunks = chunks_repo.list_chunks(db_conn, job.id)
    assert all(c.status == "converted" for c in all_chunks)

    resumed_job = job_svc.get_job(job.id)
    assert resumed_job is not None
    assert resumed_job.status == "succeeded"


def test_startup_sweep_cleans_stale_running_jobs(
    app_config: AppConfig,
    db_conn: sqlite3.Connection,
    model_manager: Any,
    make_profile: Any,
    multi_chunk_wav: Path,
) -> None:
    """Startup sweep marks crashed/stale 'running' jobs as failed with VX-500 ready for resume."""
    profile = make_profile("CrashSpeaker")
    job_svc = JobService(conn=db_conn, config=app_config, model_manager=model_manager)
    job = job_svc.create_recording_job(profile.id, multi_chunk_wav)

    # Simulate crashed job stuck in 'running'
    jobs_repo.mark_started(db_conn, job.id)
    stuck_job = job_svc.get_job(job.id)
    assert stuck_job.status == "running"

    # Run startup sweep
    stats = startup_sweep(db_conn, app_config)
    assert stats["interrupted_jobs_cleaned"] >= 1

    swept_job = job_svc.get_job(job.id)
    assert swept_job is not None
    assert swept_job.status == "failed"
    assert swept_job.error_code == "VX-500"
    assert "Ready to resume" in swept_job.error_message
