"""Chunked parallel voice conversion pipeline generator (TDR Sections 3.1-3.6)."""
from __future__ import annotations

import logging
from pathlib import Path
import time
from typing import Generator

import numpy as np
import soundfile as sf

from voxclone.audio.dsp_workers import postprocess_chunk_worker, prepare_chunk_worker
from voxclone.audio.io import load_audio
from voxclone.audio.join import crossfade_join, rms
from voxclone.audio.parallel import create_dsp_pool
from voxclone.audio.splitter import find_cut_points
from voxclone.errors import (
    ChunkOutOfMemoryError,
    InternalError,
    JobInterruptedError,
    NoSpeechDetectedError,
    VoxcloneError,
)
from voxclone.models.progress import PipelineContext, PipelineOutput, ProgressEvent
from voxclone.storage import chunks_repo, jobs_repo

logger = logging.getLogger("voxclone.pipelines.recording")


def run_recording_pipeline(
    ctx: PipelineContext,
) -> Generator[ProgressEvent, None, None]:
    """Execute chunked parallel recording-to-voice conversion pipeline."""
    job = ctx.job
    conn = ctx.conn
    input_path = job.input_audio_path
    dsp_pool = None

    try:
        if not input_path or not input_path.is_file():
            raise InternalError(
                f"Input audio file not found: {input_path}",
                hint="Provide a valid audio file path for voice conversion.",
            )

        # 1. Load source audio signal
        raw_audio, in_sr = load_audio(input_path)
        if len(raw_audio) == 0:
            raise NoSpeechDetectedError(
                "Input recording is empty.",
                hint="Record or select a non-empty audio recording.",
            )

        # 2. Slice audio into silence-aware chunks (3-5 s)
        min_sec = float(ctx.settings.get("chunk_min_sec", 3.0))
        max_sec = float(ctx.settings.get("chunk_max_sec", 5.0))
        crossfade_ms = int(ctx.settings.get("crossfade_ms", 30))
        workers = int(ctx.settings.get("workers", 0))

        intervals = find_cut_points(
            audio=raw_audio,
            sample_rate=in_sr,
            min_sec=min_sec,
            max_sec=max_sec,
        )
        total_chunks = len(intervals)
        jobs_repo.set_total_chunks(conn, job.id, total_chunks)

        # Insert chunk records if not already existing
        existing_chunks = chunks_repo.list_chunks(conn, job.id)
        if not existing_chunks:
            chunk_records = [
                {
                    "chunk_index": i,
                    "kind": "audio",
                    "status": "pending",
                    "start_sec": inter.start_sec,
                    "end_sec": inter.end_sec,
                }
                for i, inter in enumerate(intervals)
            ]
            chunks_repo.insert_chunks(conn, job.id, chunk_records)

        yield ProgressEvent(
            stage="split",
            total_chunks=total_chunks,
            message=f"Divided recording into {total_chunks} silence-aware chunks (3.0-5.0 s)",
        )

        if ctx.cancel_event.is_set():
            yield ProgressEvent(stage="cancelled", message="Job cancelled by user")
            return

        # Work directory setup
        work_base = Path(ctx.config.work_dir) / job.id
        prep_dir = work_base / "prep"
        conv_dir = work_base / "conv"
        post_dir = work_base / "post"
        prep_dir.mkdir(parents=True, exist_ok=True)
        conv_dir.mkdir(parents=True, exist_ok=True)
        post_dir.mkdir(parents=True, exist_ok=True)

        # Compute reference speaker RMS energy
        ref_audio, ref_sr = load_audio(ctx.reference_path)
        ref_rms = rms(ref_audio)

        # Stage A: Parallel CPU chunk preparation
        yield ProgressEvent(
            stage="preparing",
            total_chunks=total_chunks,
            message=f"Starting parallel CPU prep across cores ({total_chunks} chunks)...",
        )

        dsp_pool = create_dsp_pool(workers=workers)
        prep_futures = []
        prep_paths = []

        for i, inter in enumerate(intervals):
            out_prep_wav = prep_dir / f"prep_{i:04d}.wav"
            prep_paths.append(out_prep_wav)
            fut = dsp_pool.submit(
                prepare_chunk_worker,
                str(input_path),
                str(out_prep_wav),
                inter.start_sample,
                inter.end_sample,
                target_sr=16000,
            )
            prep_futures.append(fut)

        # Stage B: Load Voice Conversion engine
        yield ProgressEvent(
            stage="loading_model",
            message="Loading neural Voice Conversion engine...",
        )
        vc_engine = ctx.model_manager.acquire("vc")
        target_sr = getattr(vc_engine, "sample_rate", 24000)

        # Stage C: Sequential conversion overlapped with parallel postprocessing
        post_futures = []
        post_paths = []

        for i, inter in enumerate(intervals):
            if ctx.cancel_event.is_set():
                if dsp_pool:
                    dsp_pool.shutdown(wait=False, cancel_futures=True)
                yield ProgressEvent(
                    stage="cancelled",
                    chunk_index=i,
                    total_chunks=total_chunks,
                    message="Job cancelled by user during conversion",
                )
                return

            # Resume check: If chunk was already converted and output file exists, reuse it
            existing = chunks_repo.get_chunk(conn, job.id, i)
            if existing and existing.status == "converted" and existing.output_path and Path(existing.output_path).is_file():
                logger.info("Chunk %d already converted, reusing for resume: %s", i, existing.output_path)
                post_paths.append(Path(existing.output_path))
                continue

            yield ProgressEvent(
                stage="converting",
                chunk_index=i,
                total_chunks=total_chunks,
                message=f"Converting voice identity for chunk {i + 1}/{total_chunks}...",
            )

            # Wait for CPU preparation of this chunk if not already done
            prep_res = prep_futures[i].result()
            prepared_chunk_path = Path(prep_res["out_path"])
            chunks_repo.update_chunk(
                conn,
                job.id,
                i,
                status="prepared",
                input_path=prepared_chunk_path,
            )

            # Convert chunk with retry logic (TDR Section 3.5)
            raw_conv_wav = conv_dir / f"conv_{i:04d}.wav"
            chunks_repo.increment_attempts(conn, job.id, i)

            converted_arr = None
            for attempt in range(2):
                try:
                    converted_arr = vc_engine.convert(
                        input_path=prepared_chunk_path,
                        reference_path=ctx.reference_path,
                    )
                    break
                except Exception as exc:
                    if "out of memory" in str(exc).lower():
                        logger.warning("CUDA OOM converting chunk %d (attempt %d/2)", i, attempt + 1)
                        ctx.model_manager.free_gpu_memory()
                        if attempt == 1:
                            raise ChunkOutOfMemoryError(
                                f"Out of memory converting chunk {i + 1}/{total_chunks}",
                                hint="Close other GPU processes or reduce chunk size in settings.",
                            ) from exc
                        vc_engine = ctx.model_manager.acquire("vc")
                    else:
                        if attempt == 1:
                            raise InternalError(
                                f"Neural voice conversion failed on chunk {i + 1}: {exc}"
                            ) from exc
                        time.sleep(0.1)

            if converted_arr is None:
                raise InternalError(f"Conversion returned no audio for chunk {i + 1}")

            # Save raw converted audio to disk
            sf.write(str(raw_conv_wav), converted_arr, target_sr, subtype="PCM_16")

            # Submit postprocessing (loudness match to reference RMS) to CPU pool
            final_post_wav = post_dir / f"post_{i:04d}.wav"
            post_paths.append(final_post_wav)
            post_fut = dsp_pool.submit(
                postprocess_chunk_worker,
                str(raw_conv_wav),
                ref_rms,
                str(final_post_wav),
            )
            post_futures.append(post_fut)

            chunks_repo.update_chunk(
                conn,
                job.id,
                i,
                status="converted",
                output_path=final_post_wav,
            )
            jobs_repo.increment_completed(conn, job.id)

        # Wait for all postprocessing jobs to finish
        yield ProgressEvent(
            stage="postprocessing",
            message="Finalizing loudness matching across all converted chunks...",
        )
        for fut in post_futures:
            fut.result()

        dsp_pool.shutdown(wait=True)
        dsp_pool = None

        # Stage D: Joining chunks with equal-power crossfade
        yield ProgressEvent(
            stage="joining",
            message=f"Assembling {total_chunks} converted chunks with equal-power crossfade ({crossfade_ms} ms)...",
        )

        converted_parts: list[np.ndarray] = []
        for p in post_paths:
            data, sr = sf.read(str(p), dtype="float32")
            if data.ndim > 1:
                data = np.mean(data, axis=1)
            converted_parts.append(data)

        combined_audio = crossfade_join(
            parts=converted_parts,
            sample_rate=target_sr,
            fade_ms=crossfade_ms,
        )

        output_payload = PipelineOutput(
            audio=combined_audio,
            sample_rate=target_sr,
            total_chunks=total_chunks,
        )

        yield ProgressEvent(
            stage="done",
            total_chunks=total_chunks,
            message="Voice conversion successfully completed",
            payload=output_payload,
        )

    except JobInterruptedError as err:
        if dsp_pool:
            try:
                dsp_pool.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
        logger.warning("Job %s interrupted: %s", job.id, err)
        yield ProgressEvent(stage="cancelled", message=str(err))
    except Exception as err:
        if dsp_pool:
            try:
                dsp_pool.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
        logger.error("Job %s failed in recording pipeline: %s", job.id, err, exc_info=True)
        code = getattr(err, "error_code", getattr(err, "code", "VX-900"))
        yield ProgressEvent(stage="failed", message=f"{err} ({code})")
