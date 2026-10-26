"""Text-to-voice synthesis pipeline generator with emotion classification handoff."""
from __future__ import annotations

import logging
from typing import Generator

from voxclone.audio.io import load_audio
from voxclone.audio.join import join_with_pauses, match_loudness, rms
from voxclone.errors import JobInterruptedError, VoxcloneError
from voxclone.models.progress import PipelineContext, PipelineOutput, ProgressEvent
from voxclone.pipelines.emotion_mapping import map_emotion_label, resolve_expressiveness
from voxclone.pipelines.text_splitter import split_text_into_chunks
from voxclone.storage import chunks_repo, jobs_repo

logger = logging.getLogger("voxclone.pipelines.text")


def run_text_pipeline(
    ctx: PipelineContext,
) -> Generator[ProgressEvent, None, None]:
    """Execute text-to-voice pipeline, yielding ProgressEvents for every stage."""
    job = ctx.job
    input_text = job.input_text or ""
    conn = ctx.conn
    max_chars = int(ctx.settings.get("sentence_max_chars", 200))

    try:
        # Stage 1: Text splitting into sentence passages
        raw_chunks = split_text_into_chunks(input_text, max_chars=max_chars)
        total_chunks = len(raw_chunks)
        jobs_repo.set_total_chunks(conn, job.id, total_chunks)

        chunk_records = [
            {
                "chunk_index": i,
                "kind": "sentence",
                "text": text,
                "status": "pending",
            }
            for i, text in enumerate(raw_chunks)
        ]
        chunks_repo.insert_chunks(conn, job.id, chunk_records)

        yield ProgressEvent(
            stage="split",
            total_chunks=total_chunks,
            message=f"Divided text into {total_chunks} sentence passages",
        )

        if ctx.cancel_event.is_set():
            yield ProgressEvent(stage="cancelled", message="Job cancelled by user")
            return

        # Stage 2: Emotion Classification (if emotion_mode is 'auto')
        chunk_expressiveness: list[float] = []
        chunk_emotions: list[str] = []

        if (job.emotion_mode or "normal").lower() == "auto":
            yield ProgressEvent(
                stage="emotion",
                total_chunks=total_chunks,
                message="Loading emotion classifier to analyze text passages...",
            )

            # Acquire emotion engine under single-resident manager
            emotion_engine = ctx.model_manager.acquire("emotion")
            detected_labels = emotion_engine.classify(raw_chunks)

            for i, label in enumerate(detected_labels):
                expr_val = map_emotion_label(label)
                chunk_emotions.append(label)
                chunk_expressiveness.append(expr_val)
                chunks_repo.update_chunk(
                    conn,
                    job.id,
                    i,
                    detected_emotion=label,
                    expressiveness=expr_val,
                )

            yield ProgressEvent(
                stage="emotion",
                total_chunks=total_chunks,
                message=f"Analyzed emotion across {total_chunks} passages",
            )

            if ctx.cancel_event.is_set():
                yield ProgressEvent(stage="cancelled", message="Job cancelled by user")
                return

            # Explicitly unload emotion model before acquiring TTS model to guarantee single-resident invariant
            yield ProgressEvent(
                stage="loading_model",
                message="Unloading emotion classifier before loading speech synthesis engine...",
            )
            ctx.model_manager.unload("emotion")

        else:
            # Fixed manual emotion preset
            fixed_mode = (job.emotion_mode or "normal").lower()
            fixed_expr = resolve_expressiveness(fixed_mode)
            for i in range(total_chunks):
                chunk_emotions.append(fixed_mode)
                chunk_expressiveness.append(fixed_expr)
                chunks_repo.update_chunk(
                    conn,
                    job.id,
                    i,
                    detected_emotion=fixed_mode,
                    expressiveness=fixed_expr,
                )

        if ctx.cancel_event.is_set():
            yield ProgressEvent(stage="cancelled", message="Job cancelled by user")
            return

        # Stage 3: Reference audio preparation
        yield ProgressEvent(
            stage="preparing",
            message="Loading speaker reference audio...",
        )
        ref_audio, ref_sr = load_audio(ctx.reference_path)
        ref_rms = rms(ref_audio)

        if ctx.cancel_event.is_set():
            yield ProgressEvent(stage="cancelled", message="Job cancelled by user")
            return

        # Stage 4: Acquire TTS engine via single-resident ModelManager
        yield ProgressEvent(
            stage="loading_model",
            message="Loading neural TTS engine...",
        )
        tts_engine = ctx.model_manager.acquire("tts")

        # Stage 5: Synthesize each sentence chunk
        synthesized_parts = []
        sample_rate = getattr(tts_engine, "sample_rate", 24000)

        for i, text in enumerate(raw_chunks):
            if ctx.cancel_event.is_set():
                yield ProgressEvent(
                    stage="cancelled",
                    chunk_index=i,
                    total_chunks=total_chunks,
                    message="Job cancelled by user during synthesis",
                )
                return

            expr = chunk_expressiveness[i]
            emotion_tag = chunk_emotions[i]

            yield ProgressEvent(
                stage="synthesizing",
                chunk_index=i,
                total_chunks=total_chunks,
                message=f"Synthesizing passage {i + 1}/{total_chunks} ({emotion_tag}, expressiveness={expr:.2f})...",
            )

            chunks_repo.increment_attempts(conn, job.id, i)
            part_audio = tts_engine.synthesize(
                text=text,
                reference_path=ctx.reference_path,
                expressiveness=expr,
            )

            # Loudness match chunk against speaker reference
            matched_audio = match_loudness(part_audio, ref_rms, max_gain_db=12.0)
            synthesized_parts.append(matched_audio)

            chunks_repo.update_chunk(conn, job.id, i, status="converted", expressiveness=expr)
            jobs_repo.increment_completed(conn, job.id)

        # Stage 6: Audio postprocessing & joining
        yield ProgressEvent(
            stage="postprocessing",
            message="Smoothing boundaries and matching loudness...",
        )

        yield ProgressEvent(
            stage="joining",
            message=f"Joining {len(synthesized_parts)} audio passages...",
        )
        combined_audio = join_with_pauses(
            synthesized_parts,
            sample_rate=sample_rate,
            pause_ms=250,
            fade_ms=10,
        )

        output_payload = PipelineOutput(
            audio=combined_audio,
            sample_rate=sample_rate,
            total_chunks=total_chunks,
        )

        yield ProgressEvent(
            stage="done",
            total_chunks=total_chunks,
            message="Speech synthesis successfully generated",
            payload=output_payload,
        )

    except JobInterruptedError as err:
        logger.warning("Job %s interrupted: %s", job.id, err)
        yield ProgressEvent(stage="cancelled", message=str(err))
    except Exception as err:
        logger.error("Job %s failed in text pipeline: %s", job.id, err, exc_info=True)
        code = getattr(err, "error_code", "VX-900")
        yield ProgressEvent(stage="failed", message=f"{err} ({code})")
