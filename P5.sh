#!/usr/bin/env bash
# P5.sh - Milestone P5: Jobs, Resume & Performance (PDR M5)
# Depends on: P4 merged to main and tagged p4-done.
# Contains NO application logic: only git/dir setup and prompt-filled seed files.
set -euo pipefail

if ! git rev-parse -q --verify "refs/tags/p4-done" >/dev/null; then
  echo "ERROR: tag p4-done not found. Finish P4 (implement, test, merge to main, tag p4-done) before running P5.sh"
  exit 1
fi

echo "Checking out milestone branch..."
git checkout main
git checkout -b milestone/p5-jobs-performance

echo "Creating directories for P5..."
mkdir -p docs/seed_extensions

echo "Seeding P5 files..."

cat << 'EOF' > src/voxclone/ui/screens/job_history.py
"""
FILE PURPOSE: Job history, job detail, resume, delete and the output browser (S-40, S-41, S-42, S-43; UX 3.4).
PROMPT FOR LLM IMPLEMENTATION:
1. screen_job_history(state) [S-40]: table of recent jobs (columns: time, type, profile snapshot, status badge, duration, speed) with a dropdown below listing each job, plus "Output browser" and "← Back"; width >= 140 columns adds profile/elapsed/speed columns, narrower terminals show two-line records.
2. screen_job_detail(state, job) [S-41]: panel with all job fields (status badge, chunks i/N, timings, error code and hint, output path) and actions "Resume" (only when job.is_resumable), "Replay output" (only when the file exists), "Show log file path", "Delete job", "← Back".
3. S-42 resume: call JobService.resume_job and show the same live stage panels as a fresh run (reuse components.render_stage_panel / text progress), then the shared result panel.
4. S-43 delete: confirm; second confirm "Also delete the output file?" (default No); calls JobService.delete_job(job_id, delete_output=...).
5. Output browser: list jobs whose output file still exists (newest first) with a "Replay" action; missing files are shown dimmed with the skipped badge.
6. VoxcloneError is shown with render_error and returns to the history list.
DEBUGGING:
# print(f"[DEBUG] job history: {len(jobs)} jobs, selected={job_id}, resumable={job.is_resumable}")
OFFLINE DOCKER TEST CASES:
- (pexpect, fake) After one successful job the history table shows one row with a Done badge.
- A cancelled job offers "Resume"; a succeeded job does not.
- Deleting a job with "also delete output" removes the WAV; answering No keeps it.
- With the output file removed manually, the browser shows the row dimmed and Replay is not offered.
- Empty history prints "No jobs yet" and returns to the menu.
"""
EOF

cat << 'EOF' > tests/integration/test_resume.py
"""
FILE PURPOSE: Prove resume works after cancellation, errors and a forced process stop (PDR 5.8, KPI 100 percent resume success).
PROMPT FOR LLM IMPLEMENTATION:
1. Recording resume: run a 60 s fake job and cancel after chunk N via cancel_event; assert status "cancelled", chunks 0..N converted, then resume_job completes; the fake VC call count on resume equals total_chunks - converted_before (finished chunks are NOT recomputed); final audio equals the audio of an uninterrupted run (bit-identical with fake engines).
2. Text resume: same for a text job (including auto emotion: the emotion model is not re-run when all chunks already have detected_emotion).
3. Failure resume: a job failed by FakeVc fail twice on chunk k resumes successfully after the failure injector is removed.
4. Crash simulation: spawn a subprocess running a job and SIGKILL it mid-way; start a new JobService (startup sweep runs) and assert the stale "running" job became "failed" with VX-500 and is resumable and completes.
5. Resume with missing work files raises a clear VoxcloneError and leaves the job non-resumable; resuming a succeeded job is refused.
6. Resume uses the stored chunk start/end seconds, not a fresh split, even if the chunk_min/max settings changed in between.
DEBUGGING:
# print(f"[DEBUG] resume test converted_before={before} calls_on_resume={calls} total={total}")
OFFLINE DOCKER TEST CASES:
- Resume after SIGKILL succeeds and the output equals the uninterrupted run.
- The fake VC call counter proves zero recomputation of converted chunks.
EOF
chmod 644 tests/integration/test_resume.py

cat << 'EOF' > tests/gpu/test_benchmark.py
"""
FILE PURPOSE: OPT-IN benchmark and soak test measuring the PDR section 13 KPIs on real hardware (pytest -m gpu).
PROMPT FOR LLM IMPLEMENTATION:
1. Mark gpu; skip without CUDA or without VOXCLONE_TEST_REFERENCE / VOXCLONE_TEST_INPUT.
2. Benchmark grid through system_service.run_benchmark: workers in {1, cores/2, all} x chunk bounds in {(2,4), (3,5), (4,6)} x precision in {fp32, fp16 (if supported)}; record real-time factor, CPU stage share, peak VRAM and peak RAM for each cell; print a Markdown table.
3. Assertions on the default configuration (workers=all, 3-5 s, chosen precision): RTF <= 1.5, CPU share <= 15 percent, peak VRAM <= vram_budget_mb, peak RAM <= 6000 MB.
4. Soak test: run VOXCLONE_SOAK_JOBS (default 10; set 50 for the official KPI run) short jobs alternating text and recording; assert zero out-of-memory failures, zero failed jobs, and free VRAM after the final free() within 200 MB of baseline.
5. Print the tables so they can be pasted into docs/ as the KPI evidence.
DEBUGGING:
# print(f"[DEBUG] bench cell workers={w} chunk={cmin}-{cmax} prec={prec} rtf={rtf:.2f} vram={vram}MB")
OFFLINE DOCKER TEST CASES:
- Skipped on a CPU-only container.
- On the GPU machine the soak run reports 0 failures and the default configuration meets or clearly reports each target.
EOF

cat << 'EOF' > docs/seed_extensions/P5_extensions.md
<!--
FILE PURPOSE: Additive changes P5 needs in files that ALREADY exist. Give this document to code-implementer with the current contents of each listed file. Keep ALL existing code, apply only the additions, re-emit the complete file.
-->

# P5 Extensions

## EXTEND: src/voxclone/pipelines/recording_pipeline.py
PROMPT FOR LLM IMPLEMENTATION:
1. Support resume: if job_chunks rows already exist for the job, do NOT re-split; rebuild the spans from the stored start_sec/end_sec of each chunk and the original input file.
2. For each chunk whose status is "converted" AND whose work/<job_id>/out_NNNN.wav exists, load that file instead of converting; submit its post-processing as usual; do not call the engine. Chunks "pending"/"prepared"/"failed" are prepared and converted normally. Prepare only the chunks that still need conversion.
3. If a converted chunk's output file is missing, reset it to "pending" and convert it again.
4. completed_chunks must equal the number of converted chunks at the end; emit events with the true chunk indices.
5. Ctrl+C: honour ctx.cancel_event exactly as before; the job ends as "cancelled" and stays resumable.
DEBUGGING:
# print(f"[DEBUG] resume: {reused} chunks reused, {todo} to convert")
OFFLINE DOCKER TEST CASES:
- Resuming after chunk 4 of 15 makes exactly 10 FakeVc calls.
- Deleting one converted chunk's out file causes exactly one extra conversion.
- Final audio equals the uninterrupted run (fake engines).

## EXTEND: src/voxclone/pipelines/text_pipeline.py
PROMPT FOR LLM IMPLEMENTATION:
1. Support resume: reuse existing chunk rows (text and expressiveness are authoritative); skip passages already "converted" whose out file exists; skip the emotion stage when every chunk already has detected_emotion (auto jobs).
2. Only request the TTS model when at least one passage still needs synthesis; if none do, go straight to postprocessing.
DEBUGGING:
# print(f"[DEBUG] text resume: {reused} reused, {todo} to synthesize")
OFFLINE DOCKER TEST CASES:
- Resuming an auto-emotion job with all emotions stored records no emotion model event.
- A fully converted job resumed loads no TTS model and still produces the output.

## EXTEND: src/voxclone/services/job_service.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add resume_job(job_id, cancel_event=None) -> Iterator[ProgressEvent]: allowed only when job.is_resumable (failed/cancelled with unfinished chunks) and the work directory exists; otherwise raise a clear VoxcloneError (InternalError VX-900) with the reason. Set status running, clear error fields, then run the same dispatch as run_job in resume mode.
2. Add cancel_job(job_id) setting the status "cancelled" for a stale running job; delete_job(job_id, delete_output=False) deleting the row (cascade chunks), the work dir, and optionally the output file; list_outputs() -> jobs whose output file exists; get_job_detail(job_id) -> job plus chunk counts by status.
3. Keep the success/failure bookkeeping identical to run_job; real_time_factor is computed from the cumulative elapsed time of all attempts (store the sum in elapsed_ms).
DEBUGGING:
# print(f"[DEBUG] resume_job {job_id}: converted={converted}/{total}")
OFFLINE DOCKER TEST CASES:
- resume_job on a succeeded job raises a VoxcloneError.
- resume_job after the work dir was deleted raises a VoxcloneError and the job stays failed.
- delete_job(delete_output=True) removes the WAV; with False it keeps it.
- list_outputs omits jobs whose WAV is gone.

## EXTEND: src/voxclone/storage/files.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add list_work_dirs(config) -> list[(job_id, path, age_hours, size_mb)] and remove_work_dir(config, job_id) -> freed_mb using the existing safe path helpers.
DEBUGGING:
# print(f"[DEBUG] work dirs: {len(dirs)} total {total_mb:.1f} MB")
OFFLINE DOCKER TEST CASES:
- list_work_dirs reports age in hours within 0.1 of the mtime difference.
- remove_work_dir refuses a job_id containing path separators.

## EXTEND: src/voxclone/services/system_service.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add run_startup_sweep(config, conn) -> SweepReport: (a) mark every job with status "running" whose process is not alive as "failed" with error_code VX-500 "interrupted"; (b) delete work dirs older than WORK_DIR_MAX_AGE_HOURS whose job is succeeded/failed-nonresumable/cancelled-nonresumable (never delete a resumable job's work dir); (c) delete job_chunks rows of jobs finished more than CHUNK_ROW_RETENTION_DAYS ago; (d) delete model_events older than MODEL_EVENT_RETENTION_DAYS; (e) remove orphan work dirs with no matching job row. Each part is independent and failure-tolerant; return counts.
2. Add clean_temp(config, conn) -> freed_mb implementing the "Clean temp files" action: same safety rules as (b) and (e) but without the age limit.
3. Add run_benchmark(config, conn, model_manager, reference_path, input_path, workers_list, chunk_bounds_list, precisions, repeat=1) -> list of result dicts {workers, chunk_min, chunk_max, precision, rtf, cpu_share, peak_vram_mb, peak_ram_mb, failures}; uses the real recording pipeline through JobService and ModelManager.reset_peak()/peak_vram_mb().
DEBUGGING:
# print(f"[DEBUG] sweep: stale={stale} work_dirs_removed={removed} chunk_rows={rows} events={events}")
OFFLINE DOCKER TEST CASES:
- A job left "running" with no live process becomes "failed" with VX-500 after the sweep.
- A resumable cancelled job's work dir survives the sweep even when older than 24 h.
- Orphan work dirs are removed.
- run_benchmark with fake engines returns one result dict per grid cell.

## EXTEND: src/voxclone/services/settings_service.py
PROMPT FOR LLM IMPLEMENTATION:
1. Accept one more OPTIONAL key "precision" with values "fp32" (default when unset), "fp16", "bf16"; not part of DEFAULT_SETTINGS (the table keeps nine default rows); reset_defaults() deletes it.
DEBUGGING:
# print(f"[DEBUG] precision setting={value}")
OFFLINE DOCKER TEST CASES:
- set("precision", "int4") raises a VoxcloneError; set("precision", "fp16") succeeds; reset removes it.

## EXTEND: src/voxclone/engines/model_manager.py
PROMPT FOR LLM IMPLEMENTATION:
1. Before engine.load(device), if the "precision" setting is set and the engine has a set_precision(value) method, call it (duck-typed; engines without it ignore the setting). Log the precision used in the load event log line.
2. Honour the keep_warm setting change at runtime (read each time, not cached).
DEBUGGING:
# print(f"[DEBUG] loading {key} precision={precision}")
OFFLINE DOCKER TEST CASES:
- With a fake engine exposing set_precision, the call happens exactly once before load.
- With a fake engine lacking set_precision nothing breaks.

## EXTEND: src/voxclone/engines/real_tts.py and src/voxclone/engines/real_vc.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add set_precision(value): store "fp32"/"fp16"/"bf16"; after loading, cast the model submodules to that dtype when the installed engine supports it; if casting fails, log a WARNING and continue in fp32 (never crash). Keep output arrays float32 for the pipeline.
2. Update estimated_vram_mb to scale down for fp16/bf16 only after the benchmark has measured it; until then keep the fp32 estimate.
DEBUGGING:
# print(f"[DEBUG] {self.key} precision={self._precision} dtype_applied={applied}")
OFFLINE DOCKER TEST CASES:
- With a mocked model, set_precision("fp16") followed by load() calls the cast routine once.
- A failing cast logs a warning and leaves the engine usable.
- Output arrays remain float32.

## EXTEND: src/voxclone/ui/session.py
PROMPT FOR LLM IMPLEMENTATION:
1. In bootstrap(), call system_service.run_startup_sweep after migrations; show a one-line notice only when something was cleaned or a stale job was found ("1 interrupted job found; resume it from Job history").
2. Add class CancelController: install_sigint(event) used while a job runs; first Ctrl+C sets the cancel event and prints "Stopping after this chunk..."; a second Ctrl+C within 3 seconds raises KeyboardInterrupt (hard stop); restores the previous handler afterwards. All screens use this one controller (TDR 7: handled once, centrally).
DEBUGGING:
# print(f"[DEBUG] sigint #{count} cancel_set={event.is_set()}")
OFFLINE DOCKER TEST CASES:
- Sending SIGINT once during a fake job leaves the job "cancelled" and resumable.
- Sending it twice quickly aborts with exit code 130.
- The original SIGINT handler is restored after the job.

## EXTEND: src/voxclone/ui/screens/system.py
PROMPT FOR LLM IMPLEMENTATION:
1. Replace the Settings stub with screen_settings (S-54): a table of all settings (value, source env/db, locked marker) plus "Reset to defaults"; choosing a setting opens screen_setting_editor (S-55): a dropdown for enumerated values (device, default_output_mode, keep_warm, precision) or a validated numeric prompt (workers, chunk_min_sec, chunk_max_sec, crossfade_ms, vram_budget_mb, sentence_max_chars) that shows the allowed range; locked settings show the environment variable name and cannot be edited.
2. In screen_storage (S-56) add the action "Clean temp files" calling system_service.clean_temp and printing the freed MB.
DEBUGGING:
# print(f"[DEBUG] setting edit {key}: {old} -> {new}")
OFFLINE DOCKER TEST CASES:
- Setting workers to -1 shows the validation message and does not save.
- A key overridden by environment is shown as locked.
- Clean temp prints the freed space and never removes a resumable job's work.

## EXTEND: src/voxclone/cli.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add group `jobs` with `list` (--status, --limit), `show --id`, `resume --id`, `delete --id [--delete-output]`.
2. Add `system settings` (list/get/set/reset, e.g. `system settings set workers 4`) and `system clean`.
3. Add command `bench` with options --profile, --in, --workers (comma list), --chunks (e.g. 2-4,3-5), --precision (comma list), --repeat; prints the results as a Markdown table.
DEBUGGING:
# print(f"[DEBUG] cli jobs command={name} id={job_id}")
OFFLINE DOCKER TEST CASES:
- `jobs list` on an empty database prints "No jobs yet" and exits 0.
- `jobs resume --id <cancelled job>` exits 0 under the fake engine.
- `system settings set workers 4` persists; `system settings set workers x` exits 1 with a clear message.
- `bench --repeat 1` with fake engines prints one row per grid cell.
EOF

echo "====================================================="
echo "Milestone P5 Seeded Successfully!"
echo "NEXT STEPS:"
echo "1. Provide the seeded files AND docs/seed_extensions/P5_extensions.md (with the current contents of the files it lists) to your LLM (code-implementer) to generate the code."
echo "2. Run 'docker compose -f docker-compose.test.yml run --rm tests make test' to test offline; then on your GPU machine run the benchmark and soak test: 'docker compose run --rm -e VOXCLONE_SOAK_JOBS=50 voxclone pytest -m gpu' and paste the printed tables into docs/."
echo "3. Run 'git add . && git commit -m \"feat: complete P5\"'"
echo "4. Merge and tag: 'git checkout main && git merge --no-ff milestone/p5-jobs-performance && git tag p5-done'"
echo "5. Execute P6.sh"
echo "====================================================="
