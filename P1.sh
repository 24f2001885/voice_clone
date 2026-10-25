#!/usr/bin/env bash
# P1.sh - Milestone P1: Model Manager + Voice Profiles (PDR M1)
# Depends on: P0 merged to main and tagged p0-done.
# Contains NO application logic: only git/dir setup and prompt-filled seed files.
set -euo pipefail

if ! git rev-parse -q --verify "refs/tags/p0-done" >/dev/null; then
  echo "ERROR: tag p0-done not found. Finish P0 (implement, test, merge to main, tag p0-done) before running P1.sh"
  exit 1
fi

echo "Checking out milestone branch..."
git checkout main
git checkout -b milestone/p1-models-profiles

echo "Creating directories for P1..."
mkdir -p src/voxclone/models src/voxclone/audio tests/gpu docs/seed_extensions

echo "Seeding P1 files..."

# ----------------------------------------------------------------------------
# Data models (plain dataclasses, no ORM)
# ----------------------------------------------------------------------------

cat << 'EOF' > src/voxclone/models/__init__.py
"""
FILE PURPOSE: Package marker for dataclass models.
PROMPT FOR LLM IMPLEMENTATION:
1. Docstring only. Do NOT re-export submodules; import from voxclone.models.<module> directly (keeps later milestones from needing edits here).
DEBUGGING:
# print("[DEBUG] voxclone.models imported")
OFFLINE DOCKER TEST CASES:
- `import voxclone.models` succeeds and defines no classes.
"""
EOF

cat << 'EOF' > src/voxclone/models/profile.py
"""
FILE PURPOSE: VoiceProfile dataclass mirroring the voice_profiles table (TDR 4).
PROMPT FOR LLM IMPLEMENTATION:
1. Frozen dataclass VoiceProfile with fields in this order: id (str), name (str), reference_path (Path), source_type (str "file"|"mic"), original_filename (str|None), duration_sec (float), sample_rate (int), quality_score (float|None), quality_notes (str|None), sha256 (str), consent_confirmed (bool), consent_confirmed_at (str), created_at (str), updated_at (str).
2. Classmethod from_row(row: sqlite3.Row) -> VoiceProfile converting reference_path to Path and consent_confirmed to bool.
3. Method to_summary_dict() returning only id, name, duration_sec, created_at (TDR 5.1 list shape).
DEBUGGING:
# print(f"[DEBUG] VoiceProfile.from_row id={row['id']} name={row['name']}")
OFFLINE DOCKER TEST CASES:
- from_row on a migrated database row yields consent_confirmed is True and reference_path is a Path.
- to_summary_dict keys are exactly id, name, duration_sec, created_at.
- The dataclass is frozen (assignment raises).
"""
EOF

cat << 'EOF' > src/voxclone/models/model_event.py
"""
FILE PURPOSE: ModelEvent dataclass mirroring the model_events table (TDR 4).
PROMPT FOR LLM IMPLEMENTATION:
1. Frozen dataclass ModelEvent: id (int|None), model_key (str), action (str "load"|"unload"|"oom"), device (str), vram_free_before_mb (int|None), vram_free_after_mb (int|None), duration_ms (int|None), job_id (str|None), created_at (str).
2. Classmethod from_row(row) converting a sqlite3.Row.
DEBUGGING:
# print(f"[DEBUG] ModelEvent {action} {model_key} on {device}")
OFFLINE DOCKER TEST CASES:
- from_row round-trips a row inserted through model_events_repo.
- Missing optional values stay None.
"""
EOF

# ----------------------------------------------------------------------------
# Repositories
# ----------------------------------------------------------------------------

cat << 'EOF' > src/voxclone/storage/model_events_repo.py
"""
FILE PURPOSE: Persistence for the model_events table (load/unload/oom audit trail).
PROMPT FOR LLM IMPLEMENTATION:
1. insert_event(conn, model_key, action, device, vram_free_before_mb=None, vram_free_after_mb=None, duration_ms=None, job_id=None) -> ModelEvent with created_at = utc_now_iso().
2. list_events(conn, limit=100, model_key=None) newest first; delete_older_than(conn, days) -> int rows removed (used by the P5 sweep).
3. Parameterized SQL only.
DEBUGGING:
# print(f"[DEBUG] model_event {action} {model_key} before={vram_free_before_mb} after={vram_free_after_mb}")
OFFLINE DOCKER TEST CASES:
- Inserting an event with an invalid action raises sqlite3.IntegrityError (CHECK).
- list_events returns newest first.
- delete_older_than(conn, 90) removes only rows older than 90 days.
"""
EOF

cat << 'EOF' > src/voxclone/storage/profiles_repo.py
"""
FILE PURPOSE: CRUD persistence for voice_profiles.
PROMPT FOR LLM IMPLEMENTATION:
1. insert_profile(conn, **fields) -> VoiceProfile (generates id with new_uuid(), created_at/updated_at with utc_now_iso()); get_by_id; get_by_name; list_profiles() ordered by created_at DESC; update_name(conn, profile_id, new_name) (updates updated_at); delete_profile(conn, profile_id) -> bool.
2. Translate sqlite3.IntegrityError on the UNIQUE name column into InternalError (VX-900) with the message "A profile with this name already exists" (the UI validates earlier; this is the safety net).
3. Parameterized SQL only.
DEBUGGING:
# print(f"[DEBUG] profiles_repo {operation} id={profile_id}")
OFFLINE DOCKER TEST CASES:
- Inserting the same name twice raises the VX-900 error.
- Inserting with consent_confirmed False is rejected by the database CHECK.
- delete_profile leaves existing jobs rows with profile_id NULL and their profile_name_snapshot intact.
- list_profiles returns newest first.
"""
EOF

# ----------------------------------------------------------------------------
# Model Manager (the one-resident-model rule)
# ----------------------------------------------------------------------------

cat << 'EOF' > src/voxclone/engines/model_manager.py
"""
FILE PURPOSE: Owns the ONE resident model; loads and unloads automatically (TDR 3.7, PDR 5.6).
PROMPT FOR LLM IMPLEMENTATION:
1. class ModelManager(config, conn, settings_service, engine_factory=build_engine, vram_probe=None). vram_probe is a callable returning (free_mb, total_mb) or None when unmeasurable; the default probe uses torch.cuda.mem_get_info lazily and returns None when torch or CUDA is absent. Injectable so tests need no GPU.
2. Dataclass ModelStatus(resident_key: str|None, device: str, vram_total_mb: int|None, vram_used_mb: int|None, vram_free_mb: int|None). Method status() -> ModelStatus.
3. Context manager use(key, job_id=None) yielding the loaded engine. Behaviour: if key is already resident, reuse it with NO reload. Otherwise: unload the resident model first, then load the new one. INVARIANT: never more than one resident engine; enforce with a threading.Lock.
4. Device resolution from the "device" setting: auto -> cuda if available else cpu (log a WARNING on CPU fallback); cuda requested but unavailable -> GpuUnavailableError (VX-302); cpu -> cpu.
5. Pre-flight before loading: if engine.estimated_vram_mb() > vram_budget_mb setting, or the probe reports free VRAM below the estimate AFTER unloading the old model, raise InsufficientVramError (VX-300).
6. Load: call engine.load(device). If it raises an out-of-memory error (RuntimeError whose message contains "out of memory", or torch.cuda.OutOfMemoryError), run gc.collect() and torch.cuda.empty_cache() (lazily, if torch is loaded), record an "oom" event, retry ONCE; a second failure raises InsufficientVramError (VX-300).
7. Unload: engine.unload(), drop the reference, gc.collect(), then if torch is loaded and CUDA is available call torch.cuda.synchronize() and torch.cuda.empty_cache().
8. Every load and unload inserts a model_events row (model_key, action, device, free VRAM before/after, duration_ms, job_id) and writes a JSONL log line at INFO.
9. After the with-block, if the keep_warm setting is false, unload immediately; otherwise keep the model resident (default true) until a different key is requested, free() is called, or the app exits.
10. free() -> str|None unloads the resident model and returns its key. close() = free().
DEBUGGING:
# print(f"[DEBUG] ModelManager: {old_key} -> {new_key}, free VRAM {before_mb}->{after_mb} MB")
OFFLINE DOCKER TEST CASES:
- With fake engines: use("emotion") then use("tts") leaves exactly one engine loaded; the event order is load emotion, unload emotion, load tts.
- use("tts") twice in a row records one load event only.
- Fake probe reporting 100 MB free with estimate 500 MB raises VX-300.
- A fake engine configured with oom_once loads successfully on the retry and an "oom" event is recorded.
- keep_warm=False unloads after the with-block; keep_warm=True does not.
- Two threads requesting different models never leave two engines loaded (registry length never exceeds 1).
- free() returns the key, then status().resident_key is None.
"""
EOF

cat << 'EOF' > src/voxclone/services/model_service.py
"""
FILE PURPOSE: Thin service over ModelManager for the UI and CLI (TDR 5.3).
PROMPT FOR LLM IMPLEMENTATION:
1. class ModelService(manager). get_status() -> dict {resident, vram_used_mb, vram_free_mb, available: ["tts","vc","emotion"]} (values None when unmeasurable).
2. free_gpu_memory() -> dict {unloaded: key|None}; calling it when nothing is loaded is not an error.
3. No public "load model" method: models are loaded only as a side effect of jobs (TDR 5.3).
DEBUGGING:
# print(f"[DEBUG] model_service status={status}")
OFFLINE DOCKER TEST CASES:
- get_status on a fresh manager shows resident None.
- free_gpu_memory with nothing loaded returns {"unloaded": None}.
- After a fake load, free_gpu_memory returns the loaded key.
"""
EOF

# ----------------------------------------------------------------------------
# Audio helpers (CPU-side, torch-free)
# ----------------------------------------------------------------------------

cat << 'EOF' > src/voxclone/audio/__init__.py
"""
FILE PURPOSE: Package marker for audio helpers. This package must never import torch.
PROMPT FOR LLM IMPLEMENTATION:
1. Docstring only, stating the "no torch import" rule (CPU pool workers import from here).
DEBUGGING:
# print("[DEBUG] voxclone.audio imported")
OFFLINE DOCKER TEST CASES:
- After `import voxclone.audio`, "torch" is not in sys.modules.
"""
EOF

cat << 'EOF' > src/voxclone/audio/io.py
"""
FILE PURPOSE: Decode, encode, record and play audio (PDR 5.3, 5.7).
PROMPT FOR LLM IMPLEMENTATION:
1. load_audio(path, sample_rate) -> np.ndarray float32 mono resampled with librosa; accepts wav/mp3/flac/m4a (ffmpeg fallback for m4a/mp3); corrupt or unsupported files raise UnsupportedAudioError (VX-102).
2. probe_audio(path) -> dict {duration_sec, sample_rate, channels} without decoding the whole file.
3. save_wav(path, data, sample_rate): 16-bit PCM WAV; clip to [-1, 1]; create parent dirs.
4. record_microphone(seconds, sample_rate, stop_event=None, level_callback=None) -> np.ndarray: records mono float32 via sounddevice, calls level_callback(peak 0..1) about 10 times per second, ends early when stop_event is set; any device failure raises MicrophoneUnavailableError (VX-401).
5. play_audio(data, sample_rate): blocking playback via sounddevice; failure raises SpeakerUnavailableError (VX-402).
6. list_audio_devices() -> dict with input and output lists (names only) for the Doctor screen.
7. NULL BACKEND: when config.engine_mode == "fake" (or VOXCLONE_ENGINE=fake), record_microphone returns a deterministic synthetic tone of the requested length and play_audio is a recorded no-op, so e2e tests need no audio hardware. sounddevice must be imported lazily inside the functions that need it.
DEBUGGING:
# print(f"[DEBUG] load_audio {path} -> {data.shape} @ {sample_rate} Hz")
OFFLINE DOCKER TEST CASES:
- save_wav then load_audio at the same rate round-trips within 1e-3 amplitude error.
- A text file renamed to .wav raises VX-102.
- Stereo input is returned mono; a 44.1 kHz file is returned at the requested rate with the right length.
- In fake mode record_microphone(2.0, 24000) returns 48000 samples and play_audio returns without error.
- With sounddevice missing and engine_mode real, record_microphone raises VX-401.
"""
EOF

cat << 'EOF' > src/voxclone/audio/validate.py
"""
FILE PURPOSE: Check and clean a reference sample; compute the quality score (PDR 5.3, TDR 11).
PROMPT FOR LLM IMPLEMENTATION:
1. Dataclass SampleReport: duration_sec, speech_sec, rms_dbfs, peak, clipping_ratio, noise_floor_dbfs, snr_db, quality_score (0..1), notes (list[str] plain-language), acceptable (bool).
2. analyze_sample(data, sample_rate) -> SampleReport. Frame RMS with a 20 ms hop; a frame counts as speech when it is above (noise_floor + 10 dB) and above -45 dBFS; noise_floor = RMS of the quietest 10 percent of frames. clipping_ratio = share of samples with |x| >= 0.99.
3. Quality score heuristic (TDR 11): weighted blend of level (ideal speech RMS -30 to -12 dBFS), clipping (full marks below 0.1 percent), SNR (full marks at >= 25 dB), and duration (full marks within 20-30 s; linearly reduced down to 10 s). Notes must say what to fix (for example "Recording is too quiet; move closer to the microphone").
4. clean_reference(data, sample_rate) -> (np.ndarray, int): mono, trim leading/trailing silence (top_db 35), peak-normalize to 0.95, resample to REFERENCE_SAMPLE_RATE (24000); returns the cleaned array and the sample rate.
5. Validation: if speech_sec < MIN_SAMPLE_SPEECH_SEC raise SampleTooShortError (VX-101); audio that is entirely silent raises NoSpeechDetectedError (VX-210). Low quality (score < 0.5) does NOT raise: acceptable=False and notes explain.
6. Pure numpy/librosa; no torch; no file I/O.
DEBUGGING:
# print(f"[DEBUG] sample report: dur={duration_sec:.1f}s speech={speech_sec:.1f}s snr={snr_db:.1f}dB score={quality_score:.2f}")
OFFLINE DOCKER TEST CASES:
- 25 s of synthetic speech bursts with clean silence scores >= 0.7 and acceptable True.
- 6 s of speech raises VX-101; 30 s of pure zeros raises VX-210.
- A clipped signal (values forced to +/-1.0) reports clipping_ratio > 0.01 and a note about clipping.
- clean_reference output peak is 0.95 (+/- 0.01), the sample rate is 24000, and leading silence is gone.
"""
EOF

# ----------------------------------------------------------------------------
# Profile service
# ----------------------------------------------------------------------------

cat << 'EOF' > src/voxclone/services/profile_service.py
"""
FILE PURPOSE: Business logic for voice profiles with the consent gate (PDR 5.3, TDR 5.1, 6).
PROMPT FOR LLM IMPLEMENTATION:
1. class ProfileService(conn, config). Two-step enrollment so the UI can show the quality report between steps:
   a. prepare_sample(source: "file"|"mic", file_path=None, record_seconds=None, stop_event=None, level_callback=None) -> PreparedSample (cleaned array, sample_rate, SampleReport, original_filename). File: load_audio then analyze_sample then clean_reference. Mic: record_microphone then the same steps. Nothing is written to disk or the database in this step.
   b. save_profile(prepared, name, consent_confirmed: bool) -> VoiceProfile. FIRST check consent: if not True raise ConsentRequiredError (VX-103) and write nothing. Validate name with PROFILE_NAME_PATTERN and uniqueness. Write profiles_dir/<name>.wav via save_wav (file mode 0o600), compute sha256 of the cleaned reference file, insert the row with consent_confirmed=1 and consent_confirmed_at=utc_now_iso(), quality_score and quality_notes from the report.
2. list_profiles(), get_profile(profile_id_or_name), rename_profile(profile_id, new_name) (renames the WAV file too, same validation), delete_profile(profile_id) (removes the WAV; generated outputs are NOT deleted), preview_profile(profile_id) (play_audio of the stored reference; propagates VX-402).
3. If require_consent were ever false in config the service still enforces consent (config.py forbids disabling it).
4. Never log the audio; log profile name and duration only.
DEBUGGING:
# print(f"[DEBUG] profile saved: name={name} dur={duration_sec:.1f}s score={quality_score:.2f} consent={consent_confirmed}")
OFFLINE DOCKER TEST CASES:
- save_profile with consent_confirmed=False raises VX-103 and creates no file and no row.
- Enrolling a 25 s synthetic file creates profiles/<name>.wav and one DB row with a 64-character sha256.
- Enrolling a 5 s file raises VX-101 in prepare_sample.
- Names "bad name!" and a 65-character name are rejected; a duplicate name is rejected.
- rename_profile moves the WAV and updates updated_at; delete_profile removes both the file and the row.
- Mic enrollment in fake mode works with a 12 s synthetic recording.
"""
EOF

# ----------------------------------------------------------------------------
# Screens
# ----------------------------------------------------------------------------

cat << 'EOF' > src/voxclone/ui/screens/profiles.py
"""
FILE PURPOSE: Voice profile screens S-10 to S-17 plus the shared profile chooser (UX 3.4, 4.1).
PROMPT FOR LLM IMPLEMENTATION:
1. screen_profiles(state) [S-10]: dropdown with "Enroll a new voice from a file", "Enroll a new voice from the microphone", "Preview a profile", "Rename a profile", "Delete a profile", "← Back"; loops until Back.
2. screen_enroll_file(state) [S-11]: ask profile name (validate pattern and uniqueness inline), then path (tab completion), then call prepare_sample.
3. screen_enroll_mic(state) [S-12]: 3-2-1 countdown, then a recording progress bar (up to 30 s) with a live level meter; Enter stops early but not before 10 s (show "keep going" otherwise).
4. show_quality_report(state, report) [S-13]: panel with duration, speech seconds, level, noise, clipping, score and plain-language notes; if not acceptable offer the dropdown "Use anyway", "Re-record", "Cancel".
5. confirm_consent(state) [S-14]: fixed text "I own this voice or have the speaker's permission to clone it." with Yes/No; No saves nothing. Only after Yes call save_profile; then offer "Preview it" / "Back".
6. screen_preview, screen_rename, screen_delete [S-15..S-17]: each starts with the profile chooser; delete asks for confirmation and states that outputs are kept.
7. choose_profile(state, message="Voice profile:") -> VoiceProfile|None: dropdown of profiles with the last used preselected; when there are none, offer "Enroll one now". Sets state.selected_profile_id/name. This helper is reused by P2 and P4 screens.
8. Catch VoxcloneError at screen level via components.render_error and return to the profile menu.
DEBUGGING:
# print(f"[DEBUG] profiles screen action={choice} profile={profile_name}")
OFFLINE DOCKER TEST CASES:
- (pexpect, fake engine) Enroll from a synthetic 25 s file: answer name, path, Yes at consent; the profile appears in the list.
- Answering No at consent leaves the profiles table empty.
- A name with a space is rejected inline and the prompt repeats.
- Deleting a profile prints that outputs are kept and requires confirmation.
- choose_profile with zero profiles offers "Enroll one now".
"""
EOF

cat << 'EOF' > src/voxclone/ui/screens/welcome.py
"""
FILE PURPOSE: First-run welcome S-02, Help S-03 and About S-04 (UX 3.1).
PROMPT FOR LLM IMPLEMENTATION:
1. screen_welcome(state) [S-02]: panel explaining what the tool does, that audio never leaves the machine, and the consent rule; wait for Enter; then store setting first_run_done = true through settings_repo.
2. screen_help(state) [S-03]: table of keys (↑↓ move, Enter select, Esc/Back, type to filter, Ctrl+C cancel job and offer Resume) and of the --plain flag.
3. screen_about(state) [S-04]: version from voxclone.__version__, active engine mode, device, a pointer to LICENSES.md, and the permitted-use statement (only clone voices you own or have permission to use).
4. All three work in plain mode.
DEBUGGING:
# print(f"[DEBUG] welcome: first_run_done={flag}")
OFFLINE DOCKER TEST CASES:
- Second launch does not show the welcome screen again.
- Help and About render without raising in plain mode.
- About shows the engine mode "fake" under the test environment.
"""
EOF

# ----------------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------------

cat << 'EOF' > tests/unit/test_model_manager.py
"""
FILE PURPOSE: Prove the one-resident-model invariant and OOM/budget handling with fake engines.
PROMPT FOR LLM IMPLEMENTATION:
1. Build ModelManager with the fake engine factory and an injectable fake VRAM probe (list of (free, total) values).
2. Tests: reuse without reload; switch order (unload before load) via model_events rows; invariant never more than one loaded engine, including a two-thread race; budget rejection (VX-300); free-VRAM rejection (VX-300); OOM retry once then success; second OOM raises VX-300; keep_warm false/true; free() behaviour; device auto falls back to cpu when the probe is None; device "cuda" with no CUDA raises VX-302.
3. Parametrize across all six ordered pairs of the three model keys.
DEBUGGING:
# print(f"[DEBUG] events: {[(e.action, e.model_key) for e in events]}")
OFFLINE DOCKER TEST CASES:
- All six model switch orders end with exactly one resident engine.
- The fake registry length is never above 1 at any recorded checkpoint.
"""
EOF

cat << 'EOF' > tests/unit/test_validate.py
"""
FILE PURPOSE: Cover sample analysis, quality scoring and cleaning.
PROMPT FOR LLM IMPLEMENTATION:
1. Use make_speech to build: a good 25 s sample, a 6 s sample, silence, a clipped signal, a very quiet signal, a noisy signal.
2. Assert score ordering (good > noisy > clipped/quiet), notes content, VX-101 and VX-210 raises, and clean_reference postconditions (peak 0.95, 24000 Hz, trimmed).
3. Boundary tests at exactly 10.0 s of speech and 9.9 s.
DEBUGGING:
# print(f"[DEBUG] report {name}: score={report.quality_score:.2f} notes={report.notes}")
OFFLINE DOCKER TEST CASES:
- The ordering good > noisy holds across 5 random seeds.
- The 9.9 s case raises VX-101 and the 10.0 s case does not.
"""
EOF

cat << 'EOF' > tests/integration/test_profile_service.py
"""
FILE PURPOSE: End-to-end service tests for enrollment, consent and CRUD against a real SQLite file.
PROMPT FOR LLM IMPLEMENTATION:
1. Fixtures: migrated db_conn, tmp profiles dir, 25 s reference WAV.
2. Tests: enroll from file; enroll from fake mic; consent refusal writes nothing; duplicate and invalid names; rename moves the file; delete removes file and row and keeps jobs rows with NULL profile_id and their snapshot (insert a job row manually); preview calls the fake playback; low-quality sample still saves when accepted.
3. Assert file mode 0o600 for the stored WAV and 0o700 for the profiles directory.
DEBUGGING:
# print(f"[DEBUG] profile files: {sorted(p.name for p in profiles_dir.iterdir())}")
OFFLINE DOCKER TEST CASES:
- After a refused consent, profiles_dir has no new WAV and the table is empty.
- sha256 stored equals the sha256 recomputed from the saved file.
"""
EOF

cat << 'EOF' > tests/gpu/test_load_unload_memory.py
"""
FILE PURPOSE: OPT-IN GPU test (pytest -m gpu): repeated load/unload returns VRAM to baseline (PDR risk R2).
PROMPT FOR LLM IMPLEMENTATION:
1. Mark the module with pytest.mark.gpu and skip with a clear message when CUDA is not available.
2. Using the real ModelManager and whichever real engines are installed at this milestone (emotion is available now; tts/vc once their milestones land; skip missing ones), record free VRAM, then load and unload each engine 10 times alternating keys.
3. Assert free VRAM after the final unload is within 200 MB of the starting free VRAM, and that peak used VRAM never exceeds the vram_budget_mb setting.
4. Print a small table of free MB after each cycle so the result can be pasted into docs/.
DEBUGGING:
# print(f"[DEBUG] cycle {i}: key={key} free_mb={free_mb}")
OFFLINE DOCKER TEST CASES:
- On a CPU-only container the test is skipped, not failed.
- On the GPU machine, 10 cycles end within 200 MB of baseline.
"""
EOF

# ----------------------------------------------------------------------------
# Extensions to files created in earlier milestones (additive only)
# ----------------------------------------------------------------------------

cat << 'EOF' > docs/seed_extensions/P1_extensions.md
<!--
FILE PURPOSE: Additive changes P1 needs in files that ALREADY exist from P0. Give this document to code-implementer together with the current contents of each listed file. For each section: keep ALL existing code, apply only the listed additions, and re-emit the complete file.
-->

# P1 Extensions

## EXTEND: src/voxclone/ui/session.py
PROMPT FOR LLM IMPLEMENTATION:
1. In bootstrap(), after settings are ready, build SettingsService and ModelManager (engine factory from voxclone.engines) and store it on state.model_manager.
2. Add a close() step that calls model_manager.close() before closing the connection.
3. Do not load any model at startup.
DEBUGGING:
# print(f"[DEBUG] model_manager attached: resident={state.model_manager.status().resident_key}")
OFFLINE DOCKER TEST CASES:
- After bootstrap in fake mode, state.model_manager is not None and no engine is loaded.
- close() leaves no resident model.

## EXTEND: src/voxclone/ui/components.py
PROMPT FOR LLM IMPLEMENTATION:
1. render_header must read state.model_manager.status() and show "model: none" (muted), "model: <key> loaded" (success badge) and free VRAM in GB, or "unknown" when None.
2. Add render_model_loading_banner(console, state, old_key, new_key) showing the loading badge (magenta, "⇅ Loading") and the text "Freeing <old> / loading <new>".
DEBUGGING:
# print(f"[DEBUG] header model={status.resident_key} free={status.vram_free_mb}")
OFFLINE DOCKER TEST CASES:
- With no resident model the recorded header output contains "model: none".
- The loading banner output contains both the icon (or "~" in plain mode) and the word "Loading".

## EXTEND: src/voxclone/ui/screens/system.py
PROMPT FOR LLM IMPLEMENTATION:
1. screen_model_status (S-51): replace the stub with real data from ModelService.get_status(): resident model, VRAM used/free/total, and the last 5 model_events as a table.
2. Add screen_free_gpu (S-52): call ModelService.free_gpu_memory() and print "Model unloaded: <key>, GPU memory now free" or "No model was loaded"; add the menu item "Free GPU memory" to the System menu.
3. Add menu items "Help / shortcuts" (welcome.screen_help) and "About" (welcome.screen_about).
DEBUGGING:
# print(f"[DEBUG] free_gpu result={result}")
OFFLINE DOCKER TEST CASES:
- Free GPU memory with nothing loaded prints the "No model was loaded" message.
- After a fake load, S-51 shows the resident key and S-52 unloads it.
- Help and About are reachable from System.

## EXTEND: src/voxclone/services/system_service.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add fetch_models(config, keys=None, progress_cb=None): for each requested key download the repo listed in MODEL_REPOS via huggingface_hub.snapshot_download with HF_HUB_OFFLINE temporarily set to 0 for this call only (restored afterwards); retry 3 times with exponential backoff; on failure raise ModelWeightsMissingError (VX-310) with the repo id and a manual-download hint.
2. Skip repos already cached; report bytes downloaded per key.
DEBUGGING:
# print(f"[DEBUG] fetching {repo_id} attempt {attempt}")
OFFLINE DOCKER TEST CASES:
- With the network disabled and an empty cache, fetch_models raises VX-310 after 3 attempts (mock snapshot_download).
- With a populated fake cache directory it downloads nothing and reports 0 bytes.

## EXTEND: src/voxclone/cli.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add group `profiles` with commands: enroll (--name, --file or --record SECONDS, --consent flag required; without it the command refuses with VX-103), list, preview --name, rename --name --to, delete --name.
2. Add `system free-gpu` and `system fetch-models` commands.
3. Reuse ProfileService/ModelService; same error-to-exit-code handler as P0.
DEBUGGING:
# print(f"[DEBUG] cli profiles command={name}")
OFFLINE DOCKER TEST CASES:
- `profiles enroll --name me --file sample.wav` without --consent exits 1 and prints VX-103.
- `profiles list` prints a table including the enrolled profile.
- `system free-gpu` exits 0 even when nothing is loaded.

## EXTEND: tests/conftest.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add fixtures: model_manager (fake factory, fake VRAM probe), make_profile (enrolls a synthetic 25 s sample through ProfileService with consent True and returns the VoiceProfile), reference_wav (path to a 25 s cleaned reference).
DEBUGGING:
# print(f"[DEBUG] fixture make_profile created {profile.name}")
OFFLINE DOCKER TEST CASES:
- make_profile can be called twice with different names in one test.
- model_manager fixture shuts down cleanly (no resident model after teardown).
EOF

echo "====================================================="
echo "Milestone P1 Seeded Successfully!"
echo "NEXT STEPS:"
echo "1. Provide the seeded files AND docs/seed_extensions/P1_extensions.md (with the current contents of the files it lists) to your LLM (code-implementer) to generate the code."
echo "2. Run 'docker compose -f docker-compose.test.yml run --rm tests make test' to test offline; then run the GPU check: 'docker compose run --rm voxclone pytest -m gpu'."
echo "3. Run 'git add . && git commit -m \"feat: complete P1\"'"
echo "4. Merge and tag: 'git checkout main && git merge --no-ff milestone/p1-models-profiles && git tag p1-done'"
echo "5. Execute P2.sh"
echo "====================================================="
