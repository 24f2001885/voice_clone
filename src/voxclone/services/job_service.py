"""Job orchestration service executing synthesis and conversion pipelines."""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Generator

from voxclone.audio.io import play_audio, save_audio
from voxclone.config import AppConfig
from voxclone.errors import ConsentRequiredError, InternalError, SpeakerUnavailableError
from voxclone.models.job import Job, JobResult
from voxclone.models.progress import PipelineContext, PipelineOutput, ProgressEvent
from voxclone.pipelines.recording_pipeline import run_recording_pipeline
from voxclone.pipelines.text_pipeline import run_text_pipeline
from voxclone.storage import files, jobs_repo, profiles_repo, settings_repo

logger = logging.getLogger("voxclone.services.jobs")


class JobService:
    """Coordinates job lifecycle, pipeline dispatch, and output persistence."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        config: AppConfig,
        model_manager: Any,
    ) -> None:
        self.conn = conn
        self.config = config
        self.model_manager = model_manager

    def create_text_job(
        self,
        profile_id: str,
        input_text: str,
        emotion_mode: str = "normal",
        output_mode: str = "save",
    ) -> Job:
        """Create and queue a text-to-voice job for a consenting profile."""
        profile = profiles_repo.get_by_id(self.conn, profile_id)
        if not profile:
            raise InternalError(
                f"Voice profile ID '{profile_id}' not found.",
                hint="Run 'voxclone profiles list' to inspect registered voices.",
                code="VX-104",
            )

        if not profile.consent_confirmed:
            raise ConsentRequiredError(
                f"Voice profile '{profile.name}' cannot be used without ethical consent.",
            )

        job = jobs_repo.create_job(
            conn=self.conn,
            job_type="text_to_voice",
            profile_id=profile.id,
            profile_name_snapshot=profile.name,
            input_source="text",
            output_mode=output_mode,
            input_text=input_text,
            emotion_mode=emotion_mode,
        )
        return job

    def create_recording_job(
        self,
        profile_id: str,
        input_audio_path: Path | str,
        output_mode: str = "save",
    ) -> Job:
        """Create and queue a recording-to-voice conversion job for a consenting profile."""
        profile = profiles_repo.get_by_id(self.conn, profile_id)
        if not profile:
            raise InternalError(
                f"Voice profile ID '{profile_id}' not found.",
                hint="Run 'voxclone profiles list' to inspect registered voices.",
                code="VX-104",
            )

        if not profile.consent_confirmed:
            raise ConsentRequiredError(
                f"Voice profile '{profile.name}' cannot be used without ethical consent.",
            )

        p_audio = Path(input_audio_path)
        if not p_audio.is_file():
            raise InternalError(
                f"Source recording file does not exist: {p_audio}",
                hint="Verify input file path before submitting conversion job.",
            )

        job = jobs_repo.create_job(
            conn=self.conn,
            job_type="recording_to_voice",
            profile_id=profile.id,
            profile_name_snapshot=profile.name,
            input_source="file",
            output_mode=output_mode,
            input_path=p_audio,
        )
        return job

    def run_job(
        self,
        job_id: str,
        cancel_event: threading.Event | None = None,
    ) -> Generator[ProgressEvent, None, None]:
        """Execute a job through its designated pipeline and stream ProgressEvents."""
        job = jobs_repo.get_job(self.conn, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found.")

        profile = None
        if job.profile_id:
            profile = profiles_repo.get_by_id(self.conn, job.profile_id)
        if not profile:
            profile_name = job.profile_name_snapshot
            profile = profiles_repo.get_by_name(self.conn, profile_name)

        if not profile:
            jobs_repo.mark_finished(
                self.conn,
                job_id,
                status="failed",
                error_code="VX-104",
                error_message="Voice profile referenced by job is missing.",
            )
            yield ProgressEvent(stage="failed", message="Profile missing (VX-104)")
            return

        cancel_ev = cancel_event or threading.Event()
        effective_settings = settings_repo.get_all_settings(self.conn)
        reference_path = Path(profile.reference_path)

        ctx = PipelineContext(
            job=job,
            profile=profile,
            config=self.config,
            conn=self.conn,
            model_manager=self.model_manager,
            settings=effective_settings,
            cancel_event=cancel_ev,
            reference_path=reference_path,
            backend=self.config.backend,
            drive_dir=self.config.drive_dir,
        )

        jobs_repo.mark_started(self.conn, job.id)
        start_time = time.time()

        if job.job_type == "text_to_voice":
            pipeline_gen = run_text_pipeline(ctx)
        elif job.job_type == "recording_to_voice":
            pipeline_gen = run_recording_pipeline(ctx)
        else:
            raise NotImplementedError(f"Job type '{job.job_type}' pipeline not implemented.")

        for event in pipeline_gen:
            if event.stage == "done":
                # Handle pipeline completion, audio persistence, and playback
                payload: PipelineOutput = event.payload
                audio_data = payload.audio
                sample_rate = payload.sample_rate

                duration_sec = float(len(audio_data) / max(1, sample_rate))
                elapsed_ms = int((time.time() - start_time) * 1000)
                rtf = (elapsed_ms / 1000.0) / max(0.001, duration_sec)

                out_path = None
                saved = False
                played = False

                if job.output_mode in ("save", "both"):
                    out_path = files.build_output_path(
                        config=self.config,
                        job_type=job.job_type,
                        profile_name=profile.name,
                    )
                    save_audio(audio_data, sample_rate, out_path)
                    saved = True

                if job.output_mode in ("play", "both"):
                    try:
                        play_audio(audio_data, sample_rate)
                        played = True
                    except SpeakerUnavailableError as e:
                        logger.warning(f"Audio playback skipped: {e}")

                jobs_repo.mark_finished(
                    conn=self.conn,
                    job_id=job.id,
                    status="succeeded",
                    output_path=out_path,
                    output_sample_rate=sample_rate,
                    output_duration_sec=duration_sec,
                    elapsed_ms=elapsed_ms,
                    real_time_factor=rtf,
                )

                job_result = JobResult(
                    job_id=job.id,
                    output_path=out_path,
                    duration_sec=duration_sec,
                    sample_rate=sample_rate,
                    elapsed_ms=elapsed_ms,
                    real_time_factor=rtf,
                    played=played,
                    saved=saved,
                )

                yield ProgressEvent(
                    stage="done",
                    total_chunks=payload.total_chunks,
                    message="Job completed successfully",
                    result=job_result,
                )
                return

            elif event.stage in ("failed", "cancelled"):
                elapsed_ms = int((time.time() - start_time) * 1000)
                jobs_repo.mark_finished(
                    conn=self.conn,
                    job_id=job.id,
                    status=event.stage,
                    error_message=event.message,
                    elapsed_ms=elapsed_ms,
                )
                yield event
                return
            else:
                yield event

    def list_recent_jobs(self, limit: int = 50) -> list[Job]:
        """List recently queued, running, or finished jobs."""
        return jobs_repo.list_jobs(self.conn, limit=limit)

    def get_job(self, job_id: str) -> Job | None:
        """Fetch job by ID."""
        return jobs_repo.get_job(self.conn, job_id)

    def delete_job(self, job_id: str, delete_output: bool = False) -> bool:
        """Delete job record and optionally remove output file from disk."""
        job = jobs_repo.get_job(self.conn, job_id)
        if not job:
            return False
        if delete_output and job.output_path and job.output_path.is_file():
            try:
                job.output_path.unlink()
            except OSError as err:
                logger.warning(f"Failed deleting output file {job.output_path}: {err}")
        return jobs_repo.delete_job(self.conn, job_id)

    def resume_job(
        self,
        job_id: str,
        cancel_event: threading.Event | None = None,
    ) -> Generator[ProgressEvent, None, None]:
        """Resume an incomplete, cancelled, or failed job from its last completed state."""
        job = jobs_repo.get_job(self.conn, job_id)
        if not job:
            raise InternalError(f"Cannot resume nonexistent job: '{job_id}'")

        if job.status == "succeeded":
            yield ProgressEvent(
                stage="done",
                total_chunks=job.total_chunks,
                message="Job has already succeeded and is fully complete.",
            )
            return

        # Reset status to queued and execute remaining chunks
        jobs_repo.update_job_status(self.conn, job_id, "queued")
        yield from self.run_job(job_id, cancel_event=cancel_event)

