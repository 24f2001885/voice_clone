#!/usr/bin/env bash
# P4.sh - Milestone P4: Recording to Voice, Chunked Parallel (PDR M4) - the flagship feature
# Depends on: P3 merged to main and tagged p3-done.
# Contains NO application logic: only git/dir setup and prompt-filled seed files.
set -euo pipefail

if ! git rev-parse -q --verify "refs/tags/p3-done" >/dev/null; then
  echo "ERROR: tag p3-done not found. Finish P3 (implement, test, merge to main, tag p3-done) before running P4.sh"
  exit 1
fi

echo "Checking out milestone branch..."
git checkout main
git checkout -b milestone/p4-recording-to-voice

echo "Creating directories for P4..."
mkdir -p docs/seed_extensions

echo "Seeding P4 files..."

# ----------------------------------------------------------------------------
# Real engine
# ----------------------------------------------------------------------------

cat << 'EOF' > src/voxclone/engines/real_vc.py
"""
FILE PURPOSE: Chatterbox voice-conversion adapter implementing VcEngine (speech-to-speech, keeps timing and delivery).
PROMPT FOR LLM IMPLEMENTATION:
1. class RealVc with key "vc". Import torch and chatterbox LAZILY inside load()/convert(); importing this module must be cheap.
2. load(device): build the model with ChatterboxVC.from_pretrained(device=device); set sample_rate from the model's sr attribute; missing weights with HF_HUB_OFFLINE=1 raise ModelWeightsMissingError (VX-310) with the `system fetch-models` hint.
3. convert(input_path, reference_path) -> np.ndarray: call the model's generate with the input audio path and target_voice_path=str(reference_path) under torch.inference_mode(); return float32 mono numpy on CPU. If the installed version exposes a method that pre-computes the target voice embedding, call it ONCE per reference sha256 and reuse it for every chunk; otherwise pass the path every call. Verify method names against the installed chatterbox-tts version and record differences in docs/.
4. unload(): delete model and cached target-voice data; set is_loaded false.
5. estimated_vram_mb() returns 3500 [DEFAULT estimate; measure in the GPU smoke test and correct].
6. Map torch.cuda.OutOfMemoryError to RuntimeError("out of memory") so callers treat it uniformly.
DEBUGGING:
# print(f"[DEBUG] RealVc.convert {input_path.name} -> {audio.shape} @ {self.sample_rate} Hz")
OFFLINE DOCKER TEST CASES:
- `import voxclone.engines.real_vc` does not import torch (check sys.modules).
- With HF_HUB_OFFLINE=1 and an empty cache, load() raises VX-310 (mock from_pretrained).
- (GPU, opt-in) convert returns float32, finite values within [-1, 1], and a duration within 5 percent of the input duration.
"""
EOF

# ----------------------------------------------------------------------------
# Audio splitting and the CPU pool (all torch-free)
# ----------------------------------------------------------------------------

cat << 'EOF' > src/voxclone/audio/splitter.py
"""
FILE PURPOSE: Silence-aware cut-point search for 3-5 second chunks (TDR 3.3). Must not import torch.
PROMPT FOR LLM IMPLEMENTATION:
1. Dataclass ChunkSpan(index, start_sample, end_sample, start_sec, end_sec). Dataclass SplitResult(spans: list[ChunkSpan], warnings: list[str], speech_ratio: float).
2. has_speech(signal, sample_rate) -> bool and speech_ratio(...) using 20 ms frame RMS above max(noise_floor + 10 dB, -45 dBFS); pure silence returns False.
3. split_signal(signal, sample_rate, min_sec=3.0, max_sec=5.0, tail_min_sec=1.0) -> SplitResult implementing exactly: compute frame RMS (20 ms hop); start = 0; while remaining > max_sec: look at frames between start + min_sec and start + max_sec, choose the minimum-energy frame as the cut (ties -> the earliest), append the span, start = cut; the final remainder becomes the last span. TAIL MERGE: if the last span is shorter than tail_min_sec merge it into the previous span (the previous span may then reach max_sec + tail_min_sec).
4. Input shorter than min_sec -> exactly one span, no warning. If the chosen minimum frame is not quiet (energy above noise_floor + 6 dB) add the warning "chunks may sound abrupt (no quiet region found)" once per job.
5. Spans must be contiguous and cover the whole signal (span[i].end == span[i+1].start; first start 0; last end == len(signal)); deterministic for identical input; no I/O and no logging.
DEBUGGING:
# print(f"[DEBUG] split: {len(spans)} chunks, lengths={[round(s.end_sec - s.start_sec, 2) for s in spans]}, warnings={warnings}")
OFFLINE DOCKER TEST CASES:
- 60 s of synthetic speech with known 0.3 s gaps: every cut sample lies inside a gap and every non-final chunk is between 3.0 and 5.0 s.
- 2.0 s input returns one span; a 4.5 s input with no cut needed returns one span.
- Tail of 0.6 s is merged into the previous chunk; tail of 1.5 s stays separate.
- Continuous noise (no gaps) still returns valid spans and the abrupt-cut warning.
- Spans are contiguous and their total length equals the input length.
"""
EOF

cat << 'EOF' > src/voxclone/audio/dsp_workers.py
"""
FILE PURPOSE: Picklable top-level functions executed in spawn worker processes (TDR 3.6). MUST NOT import torch, transformers, chatterbox or anything under voxclone.engines.
PROMPT FOR LLM IMPLEMENTATION:
1. prepare_chunk(args) where args = (index, samples float32 array, sample_rate, out_dir): compute ref_rms of the ORIGINAL samples, peak-normalize to 0.95 (guard against all-zero), DO NOT trim or alter duration (timing must be preserved), write out_dir/in_NNNN.wav as 16-bit PCM, return a plain dict {index, path, ref_rms, duration_sec}.
2. postprocess_chunk(args) where args = (index, converted float32 array, ref_rms, max_gain_db): apply audio.join.match_loudness to bring the converted chunk to ref_rms, return {index, audio}.
3. worker_probe() -> dict with os.getpid() and whether "torch" is in sys.modules (used by tests to prove workers stay torch-free).
4. All functions are pure apart from the WAV write; every exception is re-raised as a plain RuntimeError with the chunk index in the message so it pickles cleanly.
DEBUGGING:
# print(f"[DEBUG] worker pid={os.getpid()} prepared chunk {index} rms={ref_rms:.4f}")
OFFLINE DOCKER TEST CASES:
- prepare_chunk output WAV has the same number of samples as the input and a peak of 0.95 (+/- 0.01).
- postprocess_chunk of a half-level signal returns an RMS equal to ref_rms within 1 percent (within the gain cap).
- worker_probe run inside a spawn pool reports torch_imported False.
- An all-zero chunk does not divide by zero.
"""
EOF

cat << 'EOF' > src/voxclone/audio/parallel.py
"""
FILE PURPOSE: Worker-count policy and the spawn process pool wrapper (TDR 3.6, 11).
PROMPT FOR LLM IMPLEMENTATION:
1. read_available_ram_mb() -> int from /proc/meminfo MemAvailable (no psutil dependency).
2. compute_worker_count(settings_workers: int, cpu_count: int, available_ram_mb: int) -> int: requested = settings_workers or cpu_count; cap so requested * WORKER_RAM_MB <= available_ram_mb - RAM_RESERVE_MB; never below 1; never above cpu_count.
3. class ChunkPool(workers): context manager owning a ProcessPoolExecutor created with multiprocessing.get_context("spawn"); methods submit_prepare(index, samples, sample_rate, out_dir) -> Future, submit_post(index, audio, ref_rms, max_gain_db=12.0) -> Future, probe() -> dict. Shutdown waits for running tasks and cancels queued ones on exit.
4. Resilience: if a future raises BrokenProcessPool, recreate the pool ONCE, resubmit the failed task, and log a WARNING; a second break raises InternalError (VX-900).
5. The module must not import torch.
DEBUGGING:
# print(f"[DEBUG] pool: workers={workers} cpu={cpu_count} ram_avail={available_ram_mb}MB")
OFFLINE DOCKER TEST CASES:
- compute_worker_count(0, 12, 8000) is 12 only if 12 * 250 <= 8000 - 2048, else the capped value; never below 1.
- compute_worker_count(4, 12, 99999) == 4; compute_worker_count(0, 4, 100) == 1.
- Killing one worker process mid-run (os.kill) is survived: the task completes after one pool rebuild.
- Using ChunkPool as a context manager leaves no child processes after exit.
"""
EOF

# ----------------------------------------------------------------------------
# Recording pipeline (flagship)
# ----------------------------------------------------------------------------

cat << 'EOF' > src/voxclone/pipelines/recording_pipeline.py
"""
FILE PURPOSE: Chunked parallel Recording to Voice pipeline: all-core CPU prep/post around a single-consumer GPU stage (TDR 3, PDR 5.5).
PROMPT FOR LLM IMPLEMENTATION:
1. run_recording_pipeline(ctx: PipelineContext) -> Iterator[ProgressEvent]; final event stage "done" with payload PipelineOutput(audio, sample_rate, total_chunks).
2. Stage "split": load_audio(job.input_path, 16000); if not has_speech raise NoSpeechDetectedError (VX-210) BEFORE any model is requested; split_signal with settings chunk_min_sec/chunk_max_sec; insert job_chunks rows (kind "audio", start_sec, end_sec); set_total_chunks; log any split warnings and yield them in the event message.
3. Stage "preparing": create the ChunkPool with compute_worker_count(...); submit prepare_chunk for EVERY chunk up front so workers run ahead of the GPU; chunk status -> "prepared" as each future completes.
4. Stage "loading_model" then "converting": inside `with ctx.model_manager.use("vc", job_id=job.id) as vc:` iterate chunks IN ORDER (index 0..N-1): wait for that chunk's prepare future, call vc.convert(in_path, ctx.reference_path), persist the result as work/<job_id>/out_NNNN.wav, set chunk status "converted", increment job completed_chunks, and IMMEDIATELY submit postprocess_chunk to the pool so loudness matching overlaps the next GPU call. Yield one "converting" event per chunk with chunk_index, total_chunks, elapsed seconds and an ETA.
5. Per-chunk failures: retry ONCE (attempts += 1). A RuntimeError containing "out of memory": call ctx.model_manager.empty_cache() first; second failure raises ChunkOutOfMemoryError (VX-301). Any other second failure marks the chunk "failed" and raises InternalError (VX-900) naming the chunk index. The job stays resumable (finished chunks keep status "converted").
6. Check ctx.cancel_event before each chunk: when set, stop submitting, let the in-flight conversion finish, persist state, raise JobInterruptedError (VX-500).
7. Stage "postprocessing": gather post futures in chunk order; stage "joining": audio.join.crossfade_join(parts, vc.sample_rate, settings crossfade_ms). Return the PipelineOutput; do NOT save or play (JobService owns output).
8. The pipeline must never import torch itself; GPU work happens only through the engine object. Never log audio; log chunk timings at DEBUG.
DEBUGGING:
# print(f"[DEBUG] chunk {i+1}/{n} converted in {ms} ms; cpu_workers={workers}; prep_ready={prep_done}")
OFFLINE DOCKER TEST CASES:
- Fake engines, 60 s synthetic input: about 15-20 chunk rows, all "converted"; output duration within 50 ms of input duration (crossfades only shorten by fade_ms per seam); chunk order preserved (fake VC amplitude follows the input RMS pattern in order).
- Silence-only input raises VX-210 and records NO model event.
- FakeVc fail_on_call {3} succeeds on retry (attempts == 2); FakeVc failing twice on the same chunk fails the job with that chunk marked "failed" and earlier chunks still "converted".
- oom_once is recovered through empty_cache + retry.
- cancel_event set after chunk 4 raises VX-500; chunks 0-3 are "converted", the rest "pending" or "prepared".
- Exactly one vc load event per job; the pool leaves no child processes afterwards.
- With FakeVc per-call delay > 0, "preparing" completes for later chunks before earlier conversions finish (overlap proof via event/timestamp ordering).
"""
EOF

# ----------------------------------------------------------------------------
# Screens
# ----------------------------------------------------------------------------

cat << 'EOF' > src/voxclone/ui/screens/recording_to_voice.py
"""
FILE PURPOSE: Recording to my voice screens S-30 to S-35 (UX 4.2b, 2.3).
PROMPT FOR LLM IMPLEMENTATION:
1. screen_recording_to_voice(state): sequential prompts with a dim summary line; Back available at every step.
2. S-30: choose_profile (screens.profiles). S-31: dropdown "Audio file" / "Record from microphone now".
3. S-32 (file): path prompt with tab completion; reject missing files inline; show duration via probe_audio. S-33 (mic): 3-2-1 countdown, level meter and elapsed time, Enter stops; the recording is saved by JobService.save_mic_recording and the saved path shown.
4. Output dropdown (Save / Play / Both; default from settings), then create the job with JobService.create_recording_job.
5. S-34: live stage panel (components.render_stage_panel) mirroring UX 2.3: Split, Loaded model, Converting on GPU with a bar and i/N, a CPU line "Cleaning on N CPU cores (running in the background)", Joining, plus elapsed and estimated remaining; refresh at most 10 times per second; plain mode prints one line per event.
6. Ctrl+C sets the cancel_event, prints "Stopping after this chunk..." then a panel "Job paused at chunk i/N. You can resume it later from Job history."
7. S-35: reuse show_result_panel from voxclone.ui.screens.text_to_voice with the speed multiple ("1.1x real-time").
8. VoxcloneError is shown through render_error with the "Resume job / Free GPU memory then resume / Back" hints text; return to the main menu.
DEBUGGING:
# print(f"[DEBUG] recording screen input={source} profile={profile_name} output={output_mode}")
OFFLINE DOCKER TEST CASES:
- (pexpect, fake) Choosing an audio file converts it and prints a saved path that exists.
- A non-existent path is rejected inline and the prompt repeats.
- Mic option in fake mode records a synthetic 5 s clip, converts it and succeeds.
- Silence input prints the VX-210 error panel and returns to the menu.
- Pressing Ctrl+C mid-job prints the paused panel and the job row is "cancelled".
"""
EOF

# ----------------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------------

cat << 'EOF' > tests/unit/test_splitter.py
"""
FILE PURPOSE: Property and case tests for the silence-aware splitter.
PROMPT FOR LLM IMPLEMENTATION:
1. Use make_speech with known gap positions: assert every cut falls inside a gap, chunk lengths 3-5 s except the last, tail merge rule, single-span cases, abrupt-cut warning, determinism, contiguity and total coverage.
2. Hypothesis-style loop (20 seeded random signals of 5-120 s): spans always contiguous and cover the input; no span longer than max_sec + tail_min_sec.
3. has_speech tests: silence False, speech True, quiet noise below -45 dBFS False.
DEBUGGING:
# print(f"[DEBUG] seed={seed} spans={[(s.start_sec, s.end_sec) for s in result.spans]}")
OFFLINE DOCKER TEST CASES:
- All 20 randomised cases pass with the same seeds on every run.
- Changing min/max to 2/4 changes the chunk lengths accordingly.
"""
EOF

cat << 'EOF' > tests/integration/test_parallel_pool.py
"""
FILE PURPOSE: Prove the spawn pool works, stays torch-free and survives a worker death.
PROMPT FOR LLM IMPLEMENTATION:
1. Tests: prepare_chunk and postprocess_chunk through ChunkPool on 12 synthetic chunks; results keyed by index and complete; worker_probe shows torch_imported False in every worker; worker-count policy table (use compute_worker_count with injected cpu_count and RAM); kill one worker with os.kill and assert the task still completes after exactly one pool rebuild; no child processes remain after the context exits (check via os.getpid children listing in /proc).
2. Timing test (marked non-strict): with 4 workers, preparing 40 chunks is not slower than 1.5x of single-worker time on a multi-core runner; skip when cpu_count < 2.
DEBUGGING:
# print(f"[DEBUG] pool test workers={workers} elapsed={elapsed:.2f}s")
OFFLINE DOCKER TEST CASES:
- The torch-free assertion fails if dsp_workers imports torch anywhere in its import chain.
- The suite finishes in under 60 seconds in the test container.
"""
EOF

cat << 'EOF' > tests/integration/test_recording_pipeline.py
"""
FILE PURPOSE: End-to-end recording job tests with fake engines through JobService.
PROMPT FOR LLM IMPLEMENTATION:
1. Tests via JobService.create_recording_job + run_job on a 60 s synthetic WAV: success (all three output modes), chunk rows and order preservation, output duration check, model events (single vc load), work dir cleaned after success.
2. Failure tests: VX-210 on silence with zero model events; retry and double-failure behaviour; oom_once recovery; cancel producing a "cancelled" job with partially converted chunks; BrokenProcessPool recovery inside a job.
3. Parameterize workers in {1, 2, 4} and assert identical audio output for all (determinism independent of core count).
DEBUGGING:
# print(f"[DEBUG] recording job {job.id} chunks={counts} stages={[e.stage for e in events]}")
OFFLINE DOCKER TEST CASES:
- Output audio for workers=1 and workers=4 is bit-identical with fake engines.
- The ordered stages include split, preparing, loading_model, converting, postprocessing, joining, writing, done.
"""
EOF

cat << 'EOF' > tests/e2e/test_menu_convert.py
"""
FILE PURPOSE: Drive the menu with pexpect through Recording to my voice (marker: e2e).
PROMPT FOR LLM IMPLEMENTATION:
1. Mark e2e. Using spawn_menu and an enrolled fake profile, select Recording -> my voice, choose Audio file, give a 30 s synthetic WAV path, choose Save; expect the stage panel lines (Split, Converting, Joining) in plain mode and a result panel with an existing output file.
2. Scenario: Record from microphone now (fake backend), stop with Enter, convert, Save.
3. Scenario: silence file shows VX-210 and returns to the menu.
4. Always terminate the child in a finally block; generous timeouts.
DEBUGGING:
# print(f"[DEBUG] convert e2e buffer={child.before!r}")
OFFLINE DOCKER TEST CASES:
- All three scenarios pass in docker-compose.test.yml.
- The saved WAV duration is within 100 ms of the input duration.
"""
EOF

cat << 'EOF' > tests/gpu/test_real_vc_smoke.py
"""
FILE PURPOSE: OPT-IN real-model check for voice conversion and performance targets (pytest -m gpu).
PROMPT FOR LLM IMPLEMENTATION:
1. Mark gpu; skip without CUDA or when VOXCLONE_TEST_REFERENCE and VOXCLONE_TEST_INPUT env paths (real recordings you own) are unset.
2. Run the full recording pipeline through JobService on a 60 s input with the real engines; assert output float32, finite, duration within 5 percent of input; peak VRAM <= vram_budget_mb; real_time_factor <= 1.5; CPU stage share (preparing + postprocessing wall time) <= 15 percent of total.
3. Seam check: for every join point compute the largest first-difference and assert it is below 3x the median first-difference of the whole output.
4. Print a results table (VRAM, RTF, CPU share, chunks, workers) to paste into docs/.
DEBUGGING:
# print(f"[DEBUG] vc smoke: rtf={rtf:.2f} vram={peak_mb}MB cpu_share={cpu_share:.1%} workers={workers}")
OFFLINE DOCKER TEST CASES:
- Skipped on a CPU-only container.
- On the GPU machine every assertion above passes or the printed table shows which target was missed.
"""
EOF

# ----------------------------------------------------------------------------
# Extensions to files created in earlier milestones (additive only)
# ----------------------------------------------------------------------------

cat << 'EOF' > docs/seed_extensions/P4_extensions.md
<!--
FILE PURPOSE: Additive changes P4 needs in files that ALREADY exist. Give this document to code-implementer with the current contents of each listed file. Keep ALL existing code, apply only the additions, re-emit the complete file.
-->

# P4 Extensions

## EXTEND: src/voxclone/engines/model_manager.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add public method empty_cache() -> None: gc.collect(), then, only if torch is already imported and CUDA is available, torch.cuda.empty_cache(). Safe to call at any time and when nothing is loaded.
2. Add public method peak_vram_mb() -> int|None returning the highest used VRAM seen since the last reset_peak(); add reset_peak(). Update the peak after every load and via a lightweight sample each time empty_cache() or status() runs. None when VRAM cannot be measured.
DEBUGGING:
# print(f"[DEBUG] empty_cache called; free VRAM now {free_mb} MB")
OFFLINE DOCKER TEST CASES:
- empty_cache() with nothing loaded and no torch does not raise.
- With the fake probe, peak_vram_mb returns the largest used value seen and reset_peak() clears it.

## EXTEND: src/voxclone/services/job_service.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add create_recording_job(profile_id, input_source ("file"|"mic"), input_path, output_mode) -> Job: validate the profile; for "file" the path must exist and decode (UnsupportedAudioError VX-102 otherwise); store input_path; job_type "recording_to_voice"; emotion_mode NULL.
2. Add save_mic_recording(data, sample_rate) -> Path: write inputs_dir/mic_<YYYYMMDD_HHMMSS>.wav (so the recording survives crashes and can be resumed), file mode 0o600.
3. Make run_job's dispatch table import recording_pipeline lazily (already specified in P2) and verify the "recording_to_voice" entry now works.
4. For recording jobs use settings chunk_min_sec, chunk_max_sec, crossfade_ms and workers from the effective settings when building the PipelineContext.
DEBUGGING:
# print(f"[DEBUG] recording job created id={job.id} source={input_source} path={input_path}")
OFFLINE DOCKER TEST CASES:
- create_recording_job with a missing file raises VX-102 (or a clear VoxcloneError) and creates no row.
- save_mic_recording writes a readable WAV in inputs/ with mode 0o600.
- run_job on a recording job succeeds with fake engines and sets total_chunks > 1 for a 30 s input.

## EXTEND: src/voxclone/ui/components.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add dataclass StageRow(name, state, detail, current=None, total=None) and render_stage_panel(console, rows, elapsed_sec, remaining_sec) drawing the UX 2.3 panel: one row per stage with theme.badge icon+word, a progress bar for rows with current/total, and an elapsed/remaining footer.
2. Add a StagePanelLive context manager wrapping rich.Live that refreshes at most 10 times per second; in plain mode it prints one line per state change instead and never uses Live.
DEBUGGING:
# print(f"[DEBUG] stage panel rows={[(r.name, r.state) for r in rows]}")
OFFLINE DOCKER TEST CASES:
- Plain-mode output for 3 rows is 3 ASCII lines with no box characters.
- A row with current=27 total=42 renders "27/42".
- Elapsed 48 s renders as 00:48.

## EXTEND: src/voxclone/cli.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add command `convert` with options --profile NAME, exactly one of --in PATH or --record SECONDS, and --save / --play / --both (default from settings). --record records from the microphone, saves via save_mic_recording, then converts.
2. Print stage lines (or the stage panel when not --plain) and the output path at the end; Ctrl+C prints the paused message and exits 130.
DEBUGGING:
# print(f"[DEBUG] cli convert source={source} profile={profile}")
OFFLINE DOCKER TEST CASES:
- `convert --profile me --in sample.wav --save` exits 0 under the fake engine and prints an existing path.
- Passing both --in and --record exits 1 with a usage error.
- A silent input file exits 1 and prints VX-210.

## EXTEND: tests/conftest.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add fixture make_recording_file(duration_sec, name) writing a speech-like synthetic WAV (using make_speech) into inputs_dir and returning its path; add silent_file(duration_sec).
DEBUGGING:
# print(f"[DEBUG] fixture recording {path} dur={duration_sec}")
OFFLINE DOCKER TEST CASES:
- make_recording_file(30) yields a 30.0 s (+/- 10 ms) WAV that has_speech() accepts; silent_file is rejected by has_speech().
EOF

echo "====================================================="
echo "Milestone P4 Seeded Successfully!"
echo "NEXT STEPS:"
echo "1. Provide the seeded files AND docs/seed_extensions/P4_extensions.md (with the current contents of the files it lists) to your LLM (code-implementer) to generate the code."
echo "2. Run 'docker compose -f docker-compose.test.yml run --rm tests make test' to test offline; then on your GPU machine: 'docker compose run --rm -e VOXCLONE_TEST_REFERENCE=/app/inputs/ref.wav -e VOXCLONE_TEST_INPUT=/app/inputs/talk.wav voxclone pytest -m gpu'."
echo "3. Run 'git add . && git commit -m \"feat: complete P4\"'"
echo "4. Merge and tag: 'git checkout main && git merge --no-ff milestone/p4-recording-to-voice && git tag p4-done'"
echo "5. Execute P5.sh"
echo "====================================================="
