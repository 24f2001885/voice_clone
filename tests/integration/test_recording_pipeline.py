"""Integration tests for chunked parallel voice conversion pipeline."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sqlite3
import threading
from typing import Any

import numpy as np
import pytest
import soundfile as sf

from voxclone.config import AppConfig
from voxclone.errors import ConsentRequiredError, NoSpeechDetectedError
from voxclone.services.job_service import JobService
from voxclone.storage import chunks_repo


@pytest.fixture
def sample_recording_wav(tmp_path: Path) -> Path:
    """Generate an 8-second speech-like synthetic audio file for testing conversion."""
    sr = 24000
    duration_sec = 8.0
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False, dtype=np.float32)

    # Harmonic acoustic carrier
    carrier = 0.3 * np.sin(2 * np.pi * 220.0 * t) + 0.15 * np.sin(2 * np.pi * 440.0 * t)
    # Amplitude envelope with natural phrase dips at 3.5s and 6.5s
    envelope = np.ones_like(t)
    envelope[int(3.2 * sr) : int(3.7 * sr)] = 0.02
    envelope[int(6.2 * sr) : int(6.7 * sr)] = 0.02

    audio = (carrier * envelope).astype(np.float32)
    wav_path = tmp_path / "test_speech_input.wav"
    sf.write(str(wav_path), audio, sr)
    return wav_path


def test_recording_pipeline_full_conversion(
    app_config: AppConfig,
    db_conn: sqlite3.Connection,
    model_manager: Any,
    make_profile: Any,
    sample_recording_wav: Path,
) -> None:
    """Full end-to-end voice conversion: chunk split, CPU prep, VC conversion, and crossfade join."""
    profile = make_profile("ConversionTargetSpeaker")
    assert profile.consent_confirmed is True

    job_svc = JobService(conn=db_conn, config=app_config, model_manager=model_manager)
    job = job_svc.create_recording_job(
        profile_id=profile.id,
        input_audio_path=sample_recording_wav,
        output_mode="save",
    )
    assert job.status == "queued"

    stages_observed = []
    final_result = None

    for event in job_svc.run_job(job.id):
        stages_observed.append(event.stage)
        if event.stage == "done":
            final_result = event.result

    assert "split" in stages_observed
    assert "preparing" in stages_observed
    assert "loading_model" in stages_observed
    assert "converting" in stages_observed
    assert "postprocessing" in stages_observed
    assert "joining" in stages_observed
    assert "done" in stages_observed

    assert final_result is not None
    assert final_result.output_path is not None
    assert final_result.output_path.is_file()
    assert final_result.duration_sec > 5.0
    assert final_result.real_time_factor > 0.0

    # Verify output audio file content
    out_audio, out_sr = sf.read(str(final_result.output_path))
    assert len(out_audio) > 0
    assert np.all(np.isfinite(out_audio))

    # Verify SQLite chunk records
    chunks = chunks_repo.list_chunks(db_conn, job.id)
    assert len(chunks) >= 2
    for chk in chunks:
        assert chk.kind == "audio"
        assert chk.status == "converted"
        assert chk.start_sec is not None
        assert chk.end_sec is not None
        assert chk.output_path is not None
        assert chk.output_path.is_file()


def test_recording_pipeline_unconsented_profile_rejected(
    app_config: AppConfig,
    db_conn: sqlite3.Connection,
    model_manager: Any,
    make_profile: Any,
    sample_recording_wav: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Converting recording with an unconsented profile raises ConsentRequiredError (VX-103)."""
    profile = make_profile("UnconsentedVcSpeaker")
    unconsented = replace(profile, consent_confirmed=False)
    monkeypatch.setattr("voxclone.storage.profiles_repo.get_by_id", lambda conn, pid: unconsented)

    job_svc = JobService(conn=db_conn, config=app_config, model_manager=model_manager)
    with pytest.raises(ConsentRequiredError) as exc_info:
        job_svc.create_recording_job(
            profile_id=profile.id,
            input_audio_path=sample_recording_wav,
        )
    assert exc_info.value.code == "VX-103"


def test_recording_pipeline_silent_audio_rejected(
    app_config: AppConfig,
    db_conn: sqlite3.Connection,
    model_manager: Any,
    make_profile: Any,
    tmp_path: Path,
) -> None:
    """Converting an audio file with pure silence raises NoSpeechDetectedError (VX-210)."""
    profile = make_profile("SilentTestSpeaker")
    silent_wav = tmp_path / "pure_silence.wav"
    sf.write(str(silent_wav), np.zeros(24000 * 5, dtype=np.float32), 24000)

    job_svc = JobService(conn=db_conn, config=app_config, model_manager=model_manager)
    job = job_svc.create_recording_job(profile.id, silent_wav)

    events = list(job_svc.run_job(job.id))
    last_event = events[-1]
    assert last_event.stage == "failed"
    assert "VX-210" in last_event.message


def test_recording_pipeline_cancellation(
    app_config: AppConfig,
    db_conn: sqlite3.Connection,
    model_manager: Any,
    make_profile: Any,
    sample_recording_wav: Path,
) -> None:
    """Setting cancel_event stops the recording conversion pipeline."""
    profile = make_profile("CancelVcSpeaker")
    job_svc = JobService(conn=db_conn, config=app_config, model_manager=model_manager)
    job = job_svc.create_recording_job(profile.id, sample_recording_wav)

    cancel_event = threading.Event()
    cancel_event.set()

    events = list(job_svc.run_job(job.id, cancel_event=cancel_event))
    last_event = events[-1]
    assert last_event.stage == "cancelled"

    refreshed_job = job_svc.get_job(job.id)
    assert refreshed_job is not None
    assert refreshed_job.status == "cancelled"
