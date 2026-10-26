"""Integration test for text-to-voice end-to-end pipeline execution."""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf

from voxclone.config import AppConfig
from voxclone.errors import ConsentRequiredError
from voxclone.services.job_service import JobService


def test_text_pipeline_full_synthesis(
    app_config: AppConfig,
    db_conn: sqlite3.Connection,
    model_manager: Any,
    make_profile: Any,
) -> None:
    """A consenting voice profile can synthesize multi-sentence text to WAV."""
    profile = make_profile("Alice")
    assert profile.consent_confirmed is True

    job_svc = JobService(conn=db_conn, config=app_config, model_manager=model_manager)
    input_text = "Good morning everyone. Welcome to the conference. Let us begin our session."

    job = job_svc.create_text_job(
        profile_id=profile.id,
        input_text=input_text,
        emotion_mode="normal",
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
    assert "synthesizing" in stages_observed
    assert "postprocessing" in stages_observed
    assert "joining" in stages_observed
    assert "done" in stages_observed

    assert final_result is not None
    assert final_result.output_path is not None
    assert final_result.output_path.is_file()
    assert final_result.duration_sec > 0.0
    assert final_result.real_time_factor > 0.0

    # Verify generated WAV is readable and non-empty
    gen_audio, gen_sr = sf.read(str(final_result.output_path))
    assert len(gen_audio) > 0
    assert np.all(np.isfinite(gen_audio))


def test_text_pipeline_unconsented_profile_rejected(
    app_config: AppConfig,
    db_conn: sqlite3.Connection,
    model_manager: Any,
    make_profile: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Synthesizing text with an unconsented profile raises ConsentRequiredError (VX-103)."""
    profile = make_profile("ConsentTestSpeaker")
    unconsented = replace(profile, consent_confirmed=False)
    monkeypatch.setattr("voxclone.storage.profiles_repo.get_by_id", lambda conn, pid: unconsented)

    job_svc = JobService(conn=db_conn, config=app_config, model_manager=model_manager)
    with pytest.raises(ConsentRequiredError) as exc_info:
        job_svc.create_text_job(
            profile_id=profile.id,
            input_text="Unauthorized text.",
        )
    assert exc_info.value.code == "VX-103"


def test_text_pipeline_cancellation(
    app_config: AppConfig,
    db_conn: sqlite3.Connection,
    model_manager: Any,
    make_profile: Any,
) -> None:
    """Setting cancel_event stops the text pipeline and stamps job cancelled."""
    profile = make_profile("CancelSpeaker")
    job_svc = JobService(conn=db_conn, config=app_config, model_manager=model_manager)
    job = job_svc.create_text_job(profile.id, "Sentence one. Sentence two.")

    cancel_event = threading.Event()
    cancel_event.set()

    events = list(job_svc.run_job(job.id, cancel_event=cancel_event))
    last_event = events[-1]
    assert last_event.stage == "cancelled"

    refreshed_job = job_svc.get_job(job.id)
    assert refreshed_job is not None
    assert refreshed_job.status == "cancelled"


def test_text_pipeline_auto_emotion_classification_and_handoff(
    app_config: AppConfig,
    db_conn: sqlite3.Connection,
    model_manager: Any,
    make_profile: Any,
) -> None:
    """Auto emotion mode runs emotion classification, unloads emotion, loads TTS, and stores chunk emotions."""
    profile = make_profile("EmotionSpeaker")
    job_svc = JobService(conn=db_conn, config=app_config, model_manager=model_manager)

    # Passage 1 has '!', triggering FakeEmotion 'joy' -> 0.70
    # Passage 2 has '?', triggering FakeEmotion 'surprise' -> 0.80
    # Passage 3 has 'sad', triggering FakeEmotion 'sadness' -> 0.30
    input_text = "I am so happy today! Why did this happen? It makes me very sad."

    job = job_svc.create_text_job(
        profile_id=profile.id,
        input_text=input_text,
        emotion_mode="auto",
        output_mode="save",
    )

    stages_observed = []
    for event in job_svc.run_job(job.id):
        stages_observed.append(event.stage)

    assert "emotion" in stages_observed
    assert "loading_model" in stages_observed
    assert "synthesizing" in stages_observed
    assert "done" in stages_observed

    # Check chunks table in SQLite
    from voxclone.storage import chunks_repo
    chunks = chunks_repo.list_chunks(db_conn, job.id)
    assert len(chunks) == 3

    assert chunks[0].detected_emotion == "joy"
    assert chunks[0].expressiveness == pytest.approx(0.70)

    assert chunks[1].detected_emotion == "surprise"
    assert chunks[1].expressiveness == pytest.approx(0.80)

    assert chunks[2].detected_emotion == "sadness"
    assert chunks[2].expressiveness == pytest.approx(0.30)

