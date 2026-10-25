#!/usr/bin/env bash
# P2.sh - Milestone P2: Text to Voice (PDR M2)
# Depends on: P1 merged to main and tagged p1-done.
# Contains NO application logic: only git/dir setup and prompt-filled seed files.
set -euo pipefail

if ! git rev-parse -q --verify "refs/tags/p1-done" >/dev/null; then
  echo "ERROR: tag p1-done not found. Finish P1 (implement, test, merge to main, tag p1-done) before running P2.sh"
  exit 1
fi

echo "Checking out milestone branch..."
git checkout main
git checkout -b milestone/p2-text-to-voice

echo "Creating directories for P2..."
mkdir -p src/voxclone/pipelines tests/e2e docs/seed_extensions

echo "Seeding P2 files..."

# ----------------------------------------------------------------------------
# Data models shared by ALL later pipelines (designed complete here so P3-P5 need no edits)
# ----------------------------------------------------------------------------

cat << 'EOF' > src/voxclone/models/job.py
"""
FILE PURPOSE: Job and JobResult dataclasses mirroring the jobs table (TDR 4).
PROMPT FOR LLM IMPLEMENTATION:
1. Dataclass Job (mutable) with fields in table order: id, job_type, status, profile_id (str|None), profile_name_snapshot, input_source, input_path (Path|None), input_text (str|None), emotion_mode (str|None), output_mode, output_path (Path|None), output_sample_rate (int|None), output_duration_sec (float|None), total_chunks (int), completed_chunks (int), error_code (str|None), error_message (str|None), created_at, started_at (str|None), finished_at (str|None), elapsed_ms (int|None), real_time_factor (float|None).
2. Classmethod from_row(row). Property is_resumable -> True when status in ("failed","cancelled") and completed_chunks < total_chunks.
3. Frozen dataclass JobResult: job_id, output_path (Path|None), duration_sec, sample_rate, elapsed_ms, real_time_factor, played (bool), saved (bool).
DEBUGGING:
# print(f"[DEBUG] Job {job.id} type={job.job_type} status={job.status} chunks={job.completed_chunks}/{job.total_chunks}")
OFFLINE DOCKER TEST CASES:
- from_row converts input_path/output_path to Path and keeps None as None.
- is_resumable is False for succeeded jobs and for failed jobs with all chunks complete.
- JobResult is frozen.
"""
EOF

cat << 'EOF' > src/voxclone/models/job_chunk.py
"""
FILE PURPOSE: JobChunk dataclass mirroring the job_chunks table (TDR 4).
PROMPT FOR LLM IMPLEMENTATION:
1. Mutable dataclass JobChunk: id (int|None), job_id, chunk_index, kind ("sentence"|"audio"), status ("pending"|"prepared"|"converted"|"failed"), text (str|None), detected_emotion (str|None), expressiveness (float|None), input_path (Path|None), output_path (Path|None), start_sec (float|None), end_sec (float|None), attempts (int), error_message (str|None).
2. Classmethod from_row(row).
DEBUGGING:
# print(f"[DEBUG] chunk {job_id}#{chunk_index} kind={kind} status={status} attempts={attempts}")
OFFLINE DOCKER TEST CASES:
- from_row maps NULL paths to None and non-null paths to Path.
- attempts defaults to 0 for a new chunk.
"""
EOF

cat << 'EOF' > src/voxclone/models/progress.py
"""
FILE PURPOSE: ProgressEvent plus the small context/output dataclasses passed between JobService and the pipelines (TDR 5.2).
PROMPT FOR LLM IMPLEMENTATION:
1. STAGES tuple (complete list so later milestones add none): "split", "preparing", "loading_model", "emotion", "synthesizing", "converting", "postprocessing", "joining", "writing", "playing", "done", "failed", "cancelled".
2. Frozen dataclass ProgressEvent: stage (must be in STAGES), chunk_index (int|None), total_chunks (int|None), message (str), result (JobResult|None, only on "done"), payload (object|None, internal hand-off such as PipelineOutput).
3. Dataclass PipelineOutput: audio (np.ndarray float32 mono), sample_rate (int), total_chunks (int).
4. Dataclass PipelineContext: job (Job), profile (VoiceProfile), config, conn, model_manager, settings (dict of effective settings), cancel_event (threading.Event), reference_path (Path).
5. Validation: creating a ProgressEvent with an unknown stage raises a VoxcloneError (InternalError VX-900).
DEBUGGING:
# print(f"[DEBUG] progress {stage} {chunk_index}/{total_chunks} {message}")
OFFLINE DOCKER TEST CASES:
- ProgressEvent(stage="bogus", ...) raises VX-900.
- A "done" event may carry a JobResult; other stages carry result None.
- PipelineContext.cancel_event.is_set() is False by default.
"""
EOF

# ----------------------------------------------------------------------------
# Repositories (complete CRUD now; reused by P4 and P5)
# ----------------------------------------------------------------------------

cat << 'EOF' > src/voxclone/storage/jobs_repo.py
"""
FILE PURPOSE: Persistence for the jobs table, including history queries used later by P5.
PROMPT FOR LLM IMPLEMENTATION:
1. create_job(conn, job_type, profile_id, profile_name_snapshot, input_source, output_mode, input_path=None, input_text=None, emotion_mode=None) -> Job (status "queued", id new_uuid(), created_at utc_now_iso()).
2. get_job(conn, job_id) -> Job|None; list_jobs(conn, status=None, job_type=None, limit=50) ordered by created_at DESC; delete_job(conn, job_id) -> bool.
3. mark_started(conn, job_id) (status running, started_at); set_total_chunks(conn, job_id, n); increment_completed(conn, job_id) -> int; mark_finished(conn, job_id, status, output_path=None, output_sample_rate=None, output_duration_sec=None, elapsed_ms=None, real_time_factor=None, error_code=None, error_message=None) setting finished_at.
4. find_stale_running(conn) -> list[Job] (status running) for the P5 startup sweep.
5. Parameterized SQL only.
DEBUGGING:
# print(f"[DEBUG] jobs_repo {operation} id={job_id} status={status}")
OFFLINE DOCKER TEST CASES:
- create_job rejects an invalid output_mode via the CHECK constraint.
- list_jobs(limit=2) returns the two newest jobs.
- mark_finished(status="failed", error_code="VX-301") stores both error fields and finished_at.
- delete_job also removes that job's job_chunks (cascade).
"""
EOF

cat << 'EOF' > src/voxclone/storage/chunks_repo.py
"""
FILE PURPOSE: Persistence for job_chunks; supports sentence chunks (P2/P3) and audio chunks (P4) and resume (P5).
PROMPT FOR LLM IMPLEMENTATION:
1. insert_chunks(conn, job_id, chunks: list[dict]) inserts many rows in one transaction (chunk_index, kind, text, input_path, start_sec, end_sec, expressiveness, detected_emotion all optional except index/kind); status starts "pending".
2. list_chunks(conn, job_id) ordered by chunk_index -> list[JobChunk]; get_chunk(conn, job_id, chunk_index).
3. update_chunk(conn, job_id, chunk_index, **fields) for status, output_path, detected_emotion, expressiveness, error_message; increment_attempts(conn, job_id, chunk_index) -> int.
4. count_by_status(conn, job_id) -> dict; delete_for_job(conn, job_id); delete_finished_older_than(conn, days) -> int (chunks of jobs finished more than N days ago; used by the P5 sweep).
5. Parameterized SQL only; UNIQUE (job_id, chunk_index) violations surface as InternalError (VX-900).
DEBUGGING:
# print(f"[DEBUG] chunks_repo {job_id}#{chunk_index} -> {fields}")
OFFLINE DOCKER TEST CASES:
- Inserting 5 chunks returns them in index order.
- update_chunk(status="converted") is reflected by count_by_status.
- Inserting a duplicate (job_id, chunk_index) raises VX-900.
- delete_finished_older_than leaves chunks of recent jobs untouched.
"""
EOF

# ----------------------------------------------------------------------------
# Audio join (CPU, torch-free)
# ----------------------------------------------------------------------------

cat << 'EOF' > src/voxclone/audio/join.py
"""
FILE PURPOSE: Loudness matching and joining of audio pieces (TDR 3.4). Used by text (pauses) and recording (crossfade) pipelines. Must not import torch.
PROMPT FOR LLM IMPLEMENTATION:
1. rms(x) -> float (epsilon-safe); match_loudness(out, reference_rms, max_gain_db=12.0) -> np.ndarray scaling out so its RMS equals reference_rms, gain limited to +/- max_gain_db, result clipped to [-1, 1].
2. crossfade_join(parts, sample_rate, fade_ms=30) -> np.ndarray: equal-power crossfade between neighbours (fade length = min(fade_ms, half of either neighbour)); single part returned unchanged; empty list raises InternalError (VX-900).
3. join_with_pauses(parts, sample_rate, pause_ms=250, fade_ms=10) -> np.ndarray: apply a short fade-in/out to each part (click prevention) and insert digital silence of pause_ms between parts.
4. Output dtype float32; input arrays are never mutated.
5. All functions are pure numpy so they can run in spawn workers.
DEBUGGING:
# print(f"[DEBUG] join: {len(parts)} parts, total {total_len/sample_rate:.2f}s, fade={fade_ms}ms")
OFFLINE DOCKER TEST CASES:
- Joining two 1 s tones with a 30 ms crossfade gives length 2*sr - fade_samples (no gap, no overlap beyond the fade).
- crossfade_join output has no sample-to-sample jump larger than 0.2 at the seam for two same-frequency tones.
- join_with_pauses of 3 parts at 250 ms adds exactly 2 * 250 ms of silence.
- match_loudness brings a 0.1-RMS signal to a 0.2 target within 1 percent and never exceeds the gain cap.
- crossfade_join([]) raises VX-900.
"""
EOF

# ----------------------------------------------------------------------------
# Text pipeline
# ----------------------------------------------------------------------------

cat << 'EOF' > src/voxclone/pipelines/__init__.py
"""
FILE PURPOSE: Package marker for pipelines.
PROMPT FOR LLM IMPLEMENTATION:
1. Docstring only.
DEBUGGING:
# print("[DEBUG] voxclone.pipelines imported")
OFFLINE DOCKER TEST CASES:
- `import voxclone.pipelines` succeeds without importing torch.
"""
EOF

cat << 'EOF' > src/voxclone/pipelines/text_splitter.py
"""
FILE PURPOSE: Split text into speakable passages of at most N characters (PDR 5.4, TDR 2.3).
PROMPT FOR LLM IMPLEMENTATION:
1. split_text(text: str, max_chars: int = 200) -> list[str].
2. Normalise whitespace and newlines; paragraphs and sentence terminators (. ! ? … and the Devanagari danda "।") end a sentence; keep the terminator with its sentence; do not split after common abbreviations (Mr., Mrs., Dr., e.g., i.e., vs.) or inside decimals like 3.14.
3. Greedily merge consecutive short sentences while the merged length stays <= max_chars.
4. A single sentence longer than max_chars is split at commas/semicolons/colons first, then at whitespace; never cut inside a word; every returned passage <= max_chars unless one unbroken word exceeds it (then that word is its own passage).
5. Order is preserved; empty or whitespace-only passages are dropped; empty input returns [].
6. Pure function, no I/O, no logging of the text.
DEBUGGING:
# print(f"[DEBUG] split_text -> {len(passages)} passages, lengths={[len(p) for p in passages]}")
OFFLINE DOCKER TEST CASES:
- "Hello world. How are you? I am fine!" with max_chars 200 returns one merged passage; with max_chars 15 returns three.
- A 450-character sentence with commas returns passages each <= 200 characters whose joined text equals the original words in order.
- "Dr. Rao paid 3.14 dollars." stays one passage.
- "" and "   \n  " return [].
- Text containing "।" splits at the danda.
"""
EOF

cat << 'EOF' > src/voxclone/pipelines/text_pipeline.py
"""
FILE PURPOSE: Text to Voice pipeline with fixed expressiveness (PDR 5.4, TDR 2.3). Emotion detection is added by P3 through a documented extension.
PROMPT FOR LLM IMPLEMENTATION:
1. run_text_pipeline(ctx: PipelineContext) -> Iterator[ProgressEvent]; the LAST event is stage "done" whose payload is a PipelineOutput(audio, sample_rate, total_chunks).
2. Step "split": split_text(job.input_text, settings["sentence_max_chars"]); insert one job_chunks row per passage (kind "sentence", expressiveness from EMOTION_MODE_TO_EXPRESSIVENESS[job.emotion_mode]); set_total_chunks. In P2 an emotion_mode of "auto" is treated as "normal" and a WARNING is logged (P3 replaces this).
3. Step "loading_model": inside `with ctx.model_manager.use("tts", job_id=job.id) as tts:` yield a loading event before the first synthesis and again when load finishes.
4. Step "synthesizing": for each passage in order call tts.synthesize(text, ctx.reference_path, expressiveness); persist each result as work/<job_id>/out_NNNN.wav (float32 -> 16-bit WAV) and set the chunk status "converted"; yield one event per passage with chunk_index/total_chunks. Retry a failing passage ONCE (increment attempts); a second failure marks the chunk "failed" and raises the underlying VoxcloneError (an out-of-memory RuntimeError becomes ChunkOutOfMemoryError VX-301, anything else InternalError VX-900 with the passage index).
5. Check ctx.cancel_event between passages; when set, raise JobInterruptedError (VX-500) after finishing the current passage.
6. Step "postprocessing": match_loudness of every passage to the median passage RMS; Step "joining": join_with_pauses(parts, tts.sample_rate, pause_ms=250); return as PipelineOutput. Do NOT save or play here (JobService owns output handling).
7. Never log full passage text (use redact_text).
DEBUGGING:
# print(f"[DEBUG] text passage {i+1}/{n} expressiveness={expr:.2f} chars={len(text)}")
OFFLINE DOCKER TEST CASES:
- Fake engines: a 3-sentence input yields 3 chunk rows, all "converted", and an output whose length is sum(parts) + 2 pauses.
- A failing passage is retried once (attempts == 2) then the job fails with the engine error mapped to VX-900.
- fake oom_once on passage 2 succeeds on retry; the final audio has all passages.
- Setting cancel_event after passage 1 raises VX-500 and leaves passage 1 "converted" and the rest "pending".
- Model events show exactly one tts load for the whole job.
"""
EOF

# ----------------------------------------------------------------------------
# Job service (output handling lives here)
# ----------------------------------------------------------------------------

cat << 'EOF' > src/voxclone/services/job_service.py
"""
FILE PURPOSE: Creates, runs and finishes jobs; owns save/play/both output handling and file naming (PDR 5.7, TDR 5.2).
PROMPT FOR LLM IMPLEMENTATION:
1. class JobService(conn, config, model_manager, settings_service).
2. create_text_job(profile_id, text, emotion_mode, output_mode) -> Job: validate profile exists, emotion_mode in EMOTION_MODES, output_mode in OUTPUT_MODES; text must be non-empty after strip and <= MAX_TEXT_CHARS else InvalidTextError (VX-201); snapshot profile name. Helper read_text_file(path) -> str (utf-8, errors raise VX-201).
3. run_job(job_id, cancel_event=None) -> Iterator[ProgressEvent]: load job and profile; mark_started; build PipelineContext with effective settings; dispatch on job_type through a table {"text_to_voice": text_pipeline.run_text_pipeline, "recording_to_voice": recording_pipeline.run_recording_pipeline} where the recording entry is imported lazily and a missing module raises InternalError (VX-900) "pipeline not available yet".
4. Forward every pipeline event unchanged. When the pipeline's "done" payload arrives, handle output: mode "save"/"both" -> build_output_path + save_wav; mode "play"/"both" -> play_audio. If playback fails (VX-402) and mode was "play", fall back to saving and yield a warning event; if mode was "both" keep the saved file. Yield "writing" and "playing" events, then a final "done" event carrying a JobResult (duration, elapsed_ms, real_time_factor = elapsed / duration).
5. Finish bookkeeping: on success mark_finished("succeeded", output fields); on VoxcloneError mark_finished("failed", error_code, error_message) and re-raise; on JobInterruptedError mark "cancelled"; on other exceptions wrap_unexpected -> "failed". Delete the job's work directory after success.
6. replay_output(job_id) plays the saved file (VX-402 propagates); list_jobs / get_job passthroughs to jobs_repo.
7. Log job lifecycle with log_event (job_id, job_type, status, elapsed_ms); never log text beyond 40 chars.
DEBUGGING:
# print(f"[DEBUG] job {job.id} {old_status} -> {new_status} elapsed={elapsed_ms}ms")
OFFLINE DOCKER TEST CASES:
- create_text_job with empty text raises VX-201; with 20001 characters raises VX-201.
- Fake-engine run with output_mode "save" creates outputs/text_<profile>_<timestamp>.wav and the job row is "succeeded" with output_path set.
- output_mode "play" with a failing player saves the file anyway and emits a warning event.
- A pipeline raising a VoxcloneError leaves the job "failed" with error_code stored.
- real_time_factor equals elapsed seconds divided by audio seconds (within 1 percent).
"""
EOF

# ----------------------------------------------------------------------------
# Real engine
# ----------------------------------------------------------------------------

cat << 'EOF' > src/voxclone/engines/real_tts.py
"""
FILE PURPOSE: Chatterbox TTS adapter implementing TtsEngine (zero-shot voice cloning with emotion control).
PROMPT FOR LLM IMPLEMENTATION:
1. class RealTts with key "tts". Import torch and chatterbox LAZILY inside load()/synthesize(); importing this module must be cheap.
2. load(device): build the model with ChatterboxTTS.from_pretrained(device=device); set sample_rate from the model's sr attribute; if weights are not cached and HF_HUB_OFFLINE=1, raise ModelWeightsMissingError (VX-310) with the hint to run `system fetch-models`. is_loaded true after success.
3. synthesize(text, reference_path, expressiveness): call the model's generate with audio_prompt_path=str(reference_path) and exaggeration=expressiveness (clamped 0.25..1.0) under torch.inference_mode(); convert the returned tensor to a float32 mono numpy array on CPU. If the installed version exposes a conditionals-preparation method, cache the conditionals per reference sha256 so the 20-30 s reference is not re-encoded for every passage; otherwise pass the path each call. Verify method names against the installed chatterbox-tts version and note any difference in docs/.
4. unload(): delete the model and cached conditionals; set is_loaded false (the ModelManager performs gc and torch.cuda.empty_cache).
5. estimated_vram_mb() returns 5500 [DEFAULT estimate; measure in the GPU smoke test and update].
6. Map torch.cuda.OutOfMemoryError to RuntimeError("out of memory") so ModelManager handles it uniformly.
DEBUGGING:
# print(f"[DEBUG] RealTts.synthesize chars={len(text)} expr={expressiveness:.2f} -> {audio.shape} @ {self.sample_rate}")
OFFLINE DOCKER TEST CASES:
- `import voxclone.engines.real_tts` does not import torch (check sys.modules in the offline container).
- With HF_HUB_OFFLINE=1 and an empty cache, load() raises VX-310 (mock from_pretrained).
- (GPU, opt-in) synthesize returns float32, mono, finite values within [-1, 1].
"""
EOF

# ----------------------------------------------------------------------------
# Screens
# ----------------------------------------------------------------------------

cat << 'EOF' > src/voxclone/ui/screens/text_to_voice.py
"""
FILE PURPOSE: Text to my voice screens S-20 to S-22 and S-24 to S-26 (UX 4.2a). Auto emotion and the preview table (S-23) are added by P3.
PROMPT FOR LLM IMPLEMENTATION:
1. screen_text_to_voice(state): sequential prompts with a dim summary line of earlier answers; every step can go back.
2. S-20: choose_profile(state) from screens.profiles. S-21: text entry: dropdown "Type or paste text" (multi-line; an empty line finishes) or "Load from a .txt file" (path prompt with tab completion); show character count; empty input shows a gentle message and repeats.
3. S-22: emotion dropdown with "Calm", "Normal" (default), "Expressive" (Auto is added by P3).
4. S-24: output dropdown "Save to file", "Play now", "Both", preselecting the setting default_output_mode.
5. Run: JobService.create_text_job then iterate run_job events, showing a rich progress bar and the stage badges (loading banner for model loads, "Speaking passage i/N"). Ctrl+C sets the cancel_event and shows "Stopping after this passage...".
6. show_result_panel(state, job_result) [S-26, reused by S-35 in P4]: boxed panel with saved path, length, time taken and speed multiple; then dropdown "Play again", "Another text", "Back to main menu". Play again uses JobService.replay_output.
7. VoxcloneError at any step is shown via render_error and returns to the main menu loop with the job marked failed.
DEBUGGING:
# print(f"[DEBUG] text screen profile={profile_name} chars={len(text)} emotion={emotion_mode} output={output_mode}")
OFFLINE DOCKER TEST CASES:
- (pexpect, fake engines) Enroll, then choose Text -> my voice, type "Hello world.", Normal, Save: the result panel shows a saved path that exists.
- Empty text input re-prompts instead of creating a job.
- An error during synthesis prints its VX code and returns to the menu.
- Play again after a Save-only job calls the (fake) player without error.
"""
EOF

# ----------------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------------

cat << 'EOF' > tests/unit/test_text_splitter.py
"""
FILE PURPOSE: Cover split_text rules.
PROMPT FOR LLM IMPLEMENTATION:
1. Parametrized cases: merge vs split by max_chars, long sentence with commas, abbreviations, decimals, danda, ellipsis, empty input, one 300-character word, multi-paragraph input.
2. Property test: for 20 random texts, "".join(passages) with whitespace normalised equals the normalised input, and every passage <= max_chars (except the unbroken-word case).
DEBUGGING:
# print(f"[DEBUG] case={name} -> {passages}")
OFFLINE DOCKER TEST CASES:
- All parametrized cases pass; the property test is deterministic (seeded).
"""
EOF

cat << 'EOF' > tests/unit/test_join.py
"""
FILE PURPOSE: Cover loudness matching, crossfade and pause joins.
PROMPT FOR LLM IMPLEMENTATION:
1. Tests for each function in audio/join.py using generated sine tones: exact output lengths, seam continuity, no input mutation, dtype float32, gain cap, clipping safety, single-part and empty-list behaviour.
2. A seam-click test: max absolute first difference at the join point is below 0.2 for a 30 ms crossfade of equal-frequency tones.
DEBUGGING:
# print(f"[DEBUG] seam max diff={max_diff:.4f} len={len(joined)}")
OFFLINE DOCKER TEST CASES:
- Output lengths match the formulas in the audio/join.py seed.
- Calling any function does not modify its input arrays (compare copies).
"""
EOF

cat << 'EOF' > tests/integration/test_text_pipeline.py
"""
FILE PURPOSE: End-to-end text job tests with fake engines, SQLite and real files.
PROMPT FOR LLM IMPLEMENTATION:
1. Tests through JobService.create_text_job + run_job: success with output_mode save, play, both; chunk rows; model events (single tts load); work directory cleaned after success; job row fields (total_chunks, completed_chunks, real_time_factor).
2. Failure tests: engine error mapping (VX-900), oom_once recovery, cancel_event raising VX-500 with job status "cancelled", invalid text VX-201, playback failure fallback.
3. Reproducibility: same input twice yields identical audio with fake engines.
DEBUGGING:
# print(f"[DEBUG] events={[e.stage for e in events]} job={job.status}")
OFFLINE DOCKER TEST CASES:
- The ordered event stages contain split, loading_model, synthesizing, postprocessing, joining, writing, done.
- After success the work/<job_id> directory does not exist.
"""
EOF

cat << 'EOF' > tests/e2e/test_menu_enroll_speak.py
"""
FILE PURPOSE: Drive the real dropdown menu with pexpect: enroll a voice, then speak text (marker: e2e).
PROMPT FOR LLM IMPLEMENTATION:
1. Mark with pytest.mark.e2e. Spawn `python -m voxclone --plain` through the spawn_menu fixture with VOXCLONE_ENGINE=fake and temp data dirs.
2. Send arrow-down (ESC [ B) and Enter to select menu items; expect the prompt texts from the UX plan ("Voice profiles", "Enroll a new voice from a file", "Profile name", "Path to file", consent text, "Text  ->  my voice" in plain mode).
3. Scenario 1: enroll from a synthetic 25 s WAV with consent Yes, then run Text -> my voice with "Hello world." Normal, Save; expect a result panel with a path and assert the WAV exists and is non-empty.
4. Scenario 2: answer No at consent; assert no profile is listed afterwards.
5. Use generous timeouts (30 s) and always terminate the child process in a finally block.
DEBUGGING:
# print(f"[DEBUG] pexpect buffer: {child.before!r}")
OFFLINE DOCKER TEST CASES:
- Scenario 1 passes in docker-compose.test.yml (no network, no GPU).
- Scenario 2 leaves the profiles directory empty.
"""
EOF

cat << 'EOF' > tests/gpu/test_real_tts_smoke.py
"""
FILE PURPOSE: OPT-IN real-model check for TTS (pytest -m gpu).
PROMPT FOR LLM IMPLEMENTATION:
1. Mark gpu; skip without CUDA or when env VOXCLONE_TEST_REFERENCE (path to a real 20-30 s recording of a voice you own) is unset.
2. Through the real ModelManager synthesize one 2-sentence text; assert float32, mono, finite, duration between 2 and 20 s, and peak VRAM used <= vram_budget_mb.
3. Print measured peak VRAM and seconds-per-second-of-audio so estimated_vram_mb in real_tts.py can be corrected; print a reminder to check the engine's documentation about an output watermark and record the finding in docs/.
DEBUGGING:
# print(f"[DEBUG] tts smoke: peak_vram={peak_mb} MB, rtf={rtf:.2f}")
OFFLINE DOCKER TEST CASES:
- Skipped (not failed) on a CPU-only container.
- On the GPU machine the output has no NaN/Inf values.
"""
EOF

# ----------------------------------------------------------------------------
# Extensions to files created in earlier milestones (additive only)
# ----------------------------------------------------------------------------

cat << 'EOF' > docs/seed_extensions/P2_extensions.md
<!--
FILE PURPOSE: Additive changes P2 needs in files that ALREADY exist. Give this document to code-implementer with the current contents of each listed file. Keep ALL existing code, apply only the additions, re-emit the complete file.
-->

# P2 Extensions

## EXTEND: src/voxclone/cli.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add command `speak` with options --profile NAME, --text TEXT or --text-file PATH (exactly one required), --emotion [calm|normal|expressive] (default normal; auto is added in P3), and --save / --play / --both (default from settings).
2. Build JobService from bootstrap state, iterate run_job, and print compact progress lines (or a rich bar when not --plain); print the output path at the end.
3. Same VoxcloneError handler and exit codes as before.
DEBUGGING:
# print(f"[DEBUG] cli speak profile={profile} chars={len(text)} output={mode}")
OFFLINE DOCKER TEST CASES:
- `speak --profile me --text "Hello." --save` (fake engine, profile enrolled) exits 0 and prints an existing path.
- Providing both --text and --text-file exits 1 with a clear message.
- An unknown profile exits 1 and prints the enrollment hint.

## EXTEND: tests/conftest.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add fixture spawn_menu(args=("--plain",), extra_env=None) returning a started pexpect child for `python -m voxclone` with the fake engine env and temp dirs, terminated automatically at teardown.
2. Add helper functions send_down(child, n) and send_enter(child) wrapping the escape sequences used by questionary.
DEBUGGING:
# print(f"[DEBUG] spawn_menu pid={child.pid} env_keys={sorted(env)}")
OFFLINE DOCKER TEST CASES:
- spawn_menu starts, the main menu text appears within 30 s, and teardown leaves no child process.
EOF

echo "====================================================="
echo "Milestone P2 Seeded Successfully!"
echo "NEXT STEPS:"
echo "1. Provide the seeded files AND docs/seed_extensions/P2_extensions.md (with the current contents of the files it lists) to your LLM (code-implementer) to generate the code."
echo "2. Run 'docker compose -f docker-compose.test.yml run --rm tests make test' to test offline; then on your GPU machine: 'docker compose run --rm voxclone voxclone system fetch-models' and 'docker compose run --rm -e VOXCLONE_TEST_REFERENCE=/app/inputs/ref.wav voxclone pytest -m gpu'."
echo "3. Run 'git add . && git commit -m \"feat: complete P2\"'"
echo "4. Merge and tag: 'git checkout main && git merge --no-ff milestone/p2-text-to-voice && git tag p2-done'"
echo "5. Execute P3.sh"
echo "====================================================="
