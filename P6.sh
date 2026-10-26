#!/usr/bin/env bash
# P6.sh - Milestone P6: Hardening & Release (PDR M6)
# Depends on: P5 merged to main and tagged p5-done.
# Contains NO application logic: only git/dir setup and prompt-filled seed files.
set -euo pipefail

if ! git rev-parse -q --verify "refs/tags/p5-done" >/dev/null; then
  echo "ERROR: tag p5-done not found. Finish P5 (implement, test, merge to main, tag p5-done) before running P6.sh"
  exit 1
fi

echo "Checking out milestone branch..."
BRANCH_NAME="milestone/p6-hardening-release"
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "")
if [ "$CURRENT_BRANCH" != "$BRANCH_NAME" ]; then
    if git rev-parse --verify "$BRANCH_NAME" >/dev/null 2>&1; then
        echo "Checking out existing branch: $BRANCH_NAME"
        git checkout "$BRANCH_NAME"
    else
        echo "Creating and checking out branch: $BRANCH_NAME from main"
        git checkout main
        git checkout -b "$BRANCH_NAME"
    fi
else
    echo "Already on milestone branch: $BRANCH_NAME"
fi

echo "Creating directories for P6..."
mkdir -p docs/seed_extensions

echo "Seeding P6 files..."

# ----------------------------------------------------------------------------
# Error panel (S-57)
# ----------------------------------------------------------------------------

cat << 'EOF' > src/voxclone/ui/screens/error_panel.py
"""
FILE PURPOSE: The reusable, polished error screen S-57 with recovery actions (UX 4.3, TDR 12.3).
PROMPT FOR LLM IMPLEMENTATION:
1. show_error_panel(state, err: VoxcloneError, job_id: str|None = None) -> str|None: render "✖ <message> (<code>)" and "→ <hint>" with the error badge (ASCII in plain mode), never a traceback unless state.debug is True.
2. Build a recovery dropdown from err.recovery_actions plus context: "Resume job" (only when job_id is given and the job is resumable), "Free GPU memory then resume" (codes VX-300, VX-301, VX-302 only), "Open Doctor" (codes VX-302, VX-310, VX-401, VX-402), "Show how to download models" (VX-310; prints `voxclone system fetch-models`), "Show log file path" (always), "← Back".
3. Execute the chosen action using the existing services (JobService.resume_job with the standard stage panel, ModelService.free_gpu_memory, screen_doctor, the configured log path) and return the action key chosen (or None for Back).
4. Plain mode prints the same information as lines and a numbered list with a text prompt instead of the dropdown.
5. All user-facing text is plain language with no jargon (say "voice model", not "checkpoint").
DEBUGGING:
# print(f"[DEBUG] error panel code={err.code} job={job_id} actions={actions}")
OFFLINE DOCKER TEST CASES:
- For VX-301 with a resumable job the dropdown contains "Resume job" and "Free GPU memory then resume".
- For VX-401 the dropdown contains "Open Doctor" and not "Resume job".
- For VX-103 only "Show log file path" and "Back" appear.
- Plain mode output contains no box-drawing characters and no raw traceback.
- With --debug the traceback text is included.
"""
EOF

# ----------------------------------------------------------------------------
# Documentation (seeded as prompts for the documents to be written)
# ----------------------------------------------------------------------------

cat << 'EOF' > README.md
<!--
FILE PURPOSE: Top-level user and developer guide; a fresh clone must be usable from this file alone (Blueprint P6 acceptance).
PROMPT FOR LLM IMPLEMENTATION:
1. Sections in order: What it does (3 input paths, 2 output paths, dropdown menu); Requirements (Windows 11 recommended for audio, WSL2, NVIDIA driver with WSL support, Docker + NVIDIA Container Toolkit, 8 GB VRAM, 8 GB RAM for WSL, 30 GB free disk); One-time setup (.wslconfig example with memory=8GB and processors, `docker run --gpus all ... nvidia-smi` check, `bash scripts/doctor.sh`); Build and run (`cp .env.example .env`, `docker compose build`, `docker compose run --rm voxclone`); First model download (`system fetch-models`); Quick tour with the three flows (enroll a voice, Text to voice, Recording to voice) and the menu keys; Command reference table (copy the PDR 14.1 command map as implemented); Settings reference (the nine settings plus emotion_map and precision); Troubleshooting table keyed by VX codes; Testing (`make docker-test`, opt-in GPU tests); Responsible use (consent rule, only clone voices you own or have permission to use, note on any output watermark found in P2); Paused features (live real-time conversion, with a link to docs/LIVE_MODE_SPIKE.md).
2. Every command must be copy-pasteable and match the final Makefile and compose files; no placeholder text.
3. Keep it under about 250 lines.
DEBUGGING:
<!-- DEBUG: run every shell snippet in a clean WSL shell and note any that fail. -->
OFFLINE DOCKER TEST CASES:
- A reader following only this file reaches the open menu on a clean machine.
- Every VX code in errors.py appears in the troubleshooting table.
- All relative links resolve (docs/*.md exist).
-->
EOF

cat << 'EOF' > LICENSES.md
<!--
FILE PURPOSE: Record of code and model/weight licenses (TDR 14 requires verification at pin time).
PROMPT FOR LLM IMPLEMENTATION:
1. A table with columns: Component, Version (from requirements.lock), Licence (verified), Source URL, Commercial use allowed (yes/no/unknown), Notes. Rows: every runtime dependency in requirements.lock that is direct (chatterbox-tts, torch, transformers, numpy, librosa, soundfile, sounddevice, questionary, rich, typer) plus dev tools, plus the model weights: Chatterbox TTS/VC weights and j-hartmann/emotion-english-distilroberta-base.
2. For weights, record exactly what the model card says and the date it was checked; where uncertain write "unknown - verify before any non-personal use" rather than guessing.
3. Add a short "Responsible use" paragraph repeating the consent rule.
DEBUGGING:
<!-- DEBUG: compare the table against `pip list --format=freeze` to find missing direct dependencies. -->
OFFLINE DOCKER TEST CASES:
- Every direct dependency in requirements.in has a row.
- No row has an empty Licence cell.
-->
EOF

cat << 'EOF' > docs/TESTING_GUIDE.md
<!--
FILE PURPOSE: How to run and extend each test level (TDR 10, Blueprint 2.2).
PROMPT FOR LLM IMPLEMENTATION:
1. Explain the four levels (unit, integration, e2e with pexpect, opt-in GPU) and which command runs each: `make docker-test`, `docker compose -f docker-compose.test.yml run --rm tests pytest tests/unit`, `... pytest -m e2e`, and `docker compose run --rm voxclone pytest -m gpu`.
2. Document the fake engines (VOXCLONE_ENGINE=fake), their failure-injection options, the fixtures in tests/conftest.py (make_speech, spawn_menu, make_profile, make_recording_file) and how to write a new pipeline test.
3. Document the environment variables needed for GPU tests (VOXCLONE_TEST_REFERENCE, VOXCLONE_TEST_INPUT, VOXCLONE_SOAK_JOBS) and where to paste the benchmark tables.
4. Explain the coverage gate: `make coverage` requires >= 85 percent and excludes engines/real_*.py.
5. A "Debugging a failing test" section: using the commented [DEBUG] print hooks, DEBUG log level and the JSONL log file.
DEBUGGING:
<!-- DEBUG: run each documented command once and confirm the stated outcome. -->
OFFLINE DOCKER TEST CASES:
- Every command in the guide exits 0 on a healthy checkout.
- The guide names every marker registered in pyproject.toml.
-->
EOF

cat << 'EOF' > docs/RECORDING_TIPS.md
<!--
FILE PURPOSE: Help users record a good 20-30 second reference sample (PDR risk R7; quality matters more than model choice).
PROMPT FOR LLM IMPLEMENTATION:
1. Practical checklist: quiet room, soft furnishings to reduce echo, microphone 15-20 cm away, steady volume, no music or fans, speak naturally with normal expression, 20-30 seconds of continuous speech, avoid long pauses and reading in a monotone, record in one take, avoid clipping (peaks below full scale).
2. Explain the quality report in the app (duration, speech seconds, level, noise, clipping, score) and what each note means and how to fix it, matching the notes produced by audio/validate.py.
3. A short section on choosing a good source file for Recording -> Voice (clear speech, minimal background noise) and what happens with music or overlapping speakers.
4. A reminder to record only voices you own or have permission to use.
DEBUGGING:
<!-- DEBUG: enrol one deliberately bad sample and verify each tip addresses a note the app shows. -->
OFFLINE DOCKER TEST CASES:
- Every possible note string in validate.py has a matching tip in this file.
-->
EOF

cat << 'EOF' > docs/LIVE_MODE_SPIKE.md
<!--
FILE PURPOSE: DESIGN-ONLY note for the PAUSED real-time voice conversion feature (PDR out-of-scope, TDR 15 item 8). No code, no menu entry.
PROMPT FOR LLM IMPLEMENTATION:
1. Describe the goal (speak into the mic and hear the cloned voice with low latency) and why it is paused (8 GB VRAM, TTS models are not real-time, WSLg audio latency).
2. Latency budget table: capture buffer, voice-activity chunking (candidate 0.2-0.5 s), model inference, output buffer, WSLg/PulseAudio overhead; target total (state the assumed target such as under 500 ms and mark it as an assumption).
3. VRAM budget: which model would be resident (voice-conversion only, with TTS and emotion unloaded by the ModelManager) and how the one-resident-model rule would apply; state what measurements from P4 (VRAM, RTF per chunk length) the decision depends on.
4. Options considered: streaming-capable conversion models versus short-chunk reuse of the current conversion model; list what to verify for each (license, English quality, latency, VRAM) without claiming results not measured.
5. Audio plumbing risks inside Docker (PulseAudio over WSLg, buffer underruns) and how a prototype could be isolated.
6. A go/no-go checklist with measurable criteria and an explicit statement that no menu entry or code is added until the checklist passes.
DEBUGGING:
<!-- DEBUG: cross-check each number in the document against the P4/P5 benchmark tables; mark anything unmeasured as "unmeasured". -->
OFFLINE DOCKER TEST CASES:
- The document states clearly that live mode is NOT implemented.
- Every quantitative claim cites a measurement from docs/ or is labelled an assumption.
-->
EOF

# ----------------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------------

cat << 'EOF' > tests/unit/test_plain_mode.py
"""
FILE PURPOSE: Prove --plain, NO_COLOR and narrow-terminal behaviour (UX section 8).
PROMPT FOR LLM IMPLEMENTATION:
1. Render header, panel, table, stage panel and error panel with a recording rich Console in plain mode; assert pure ASCII output (str.isascii()) and no box-drawing characters.
2. NO_COLOR mode: unicode icons present, zero ANSI colour escape codes.
3. Width tests at 50, 80, 120 and 150 columns: no line exceeds the width; at 50 the header shows only the app name and tables become two-line records; at 150 the job table shows the extra columns.
4. Every badge state always shows both icon and word.
DEBUGGING:
# print(f"[DEBUG] width={width} lines={len(lines)} max_len={max(map(len, lines))}")
OFFLINE DOCKER TEST CASES:
- No rendered line is longer than the configured console width.
- Plain-mode output of every component is ASCII only.
EOF
sed -i '$d' tests/unit/test_plain_mode.py

cat << 'EOF' > tests/e2e/test_menu_system.py
"""
FILE PURPOSE: Full menu E2E pass for the System menu, history, resume and error recovery (marker: e2e).
PROMPT FOR LLM IMPLEMENTATION:
1. Mark e2e. Using spawn_menu in plain mode: open System -> Doctor and Storage and Settings (change workers and observe it persisted), Model status and Free GPU memory, Help and About; Job history after a successful job; cancel a job with Ctrl+C and resume it from Job history; trigger a VX error (silence input) and use the error panel's "Show log file path" action.
2. Assert the first-run welcome appears once and not on the second launch (same data dir).
3. Terminate the child in a finally block; generous timeouts.
DEBUGGING:
# print(f"[DEBUG] system e2e buffer={child.before!r}")
OFFLINE DOCKER TEST CASES:
- All scenarios pass in docker-compose.test.yml with the network disabled.
- The overall suite (unit + integration + e2e) reaches >= 85 percent coverage via `make coverage`.
EOF
sed -i '$d' tests/e2e/test_menu_system.py

# ----------------------------------------------------------------------------
# Extensions to files created in earlier milestones (additive only)
# ----------------------------------------------------------------------------

cat << 'EOF' > docs/seed_extensions/P6_extensions.md
<!--
FILE PURPOSE: Additive changes P6 needs in files that ALREADY exist. Give this document to code-implementer with the current contents of each listed file. Keep ALL existing code, apply only the additions, re-emit the complete file.
-->

# P6 Extensions

## EXTEND: src/voxclone/errors.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add a class attribute recovery_actions (tuple of action keys from: "resume", "free_gpu", "doctor", "fetch_models", "log_path") to every error class: VX-300/301 -> ("free_gpu","resume","log_path"); VX-302 -> ("doctor","free_gpu","log_path"); VX-310 -> ("fetch_models","doctor","log_path"); VX-401/402 -> ("doctor","log_path"); VX-500 -> ("resume","log_path"); VX-900 -> ("log_path",); all others -> ("log_path",).
2. Re-read every message and hint for plain language (no jargon, no stack terms) and confirm they match TDR 12.3 word for word where the TDR gives text.
DEBUGGING:
# print(f"[DEBUG] {code} recovery_actions={cls.recovery_actions}")
OFFLINE DOCKER TEST CASES:
- Every error class defines recovery_actions and every action key is one of the five allowed.
- VX-500 offers "resume"; VX-103 does not.

## EXTEND: src/voxclone/ui/menu.py and every screen module (profiles.py, text_to_voice.py, recording_to_voice.py, job_history.py, system.py)
PROMPT FOR LLM IMPLEMENTATION:
1. Replace direct render_error calls with screens.error_panel.show_error_panel(state, err, job_id=...), passing the job id whenever a job exists so "Resume job" can be offered.
2. In plain mode the main menu labels use ASCII arrows ("Text  ->  my voice", "<- Back") consistently across all menus.
3. Behaviour otherwise unchanged.
DEBUGGING:
# print(f"[DEBUG] screen error routed to panel: {err.code}")
OFFLINE DOCKER TEST CASES:
- A failing job in each screen group opens the error panel with the expected actions.
- grep finds no remaining direct render_error call in screens (except inside error_panel itself).

## EXTEND: src/voxclone/ui/theme.py and src/voxclone/ui/components.py
PROMPT FOR LLM IMPLEMENTATION:
1. Implement the width breakpoints from UX section 8: under 60 columns single column (header shows only the app name, progress bars 20 characters, tables as two-line records); 60-99 standard; 100-139 panels capped at 100 columns; 140 or more adds extra columns to the job table.
2. Re-render on terminal resize (SIGWINCH) for live panels; honour NO_COLOR and VOXCLONE_PLAIN everywhere including questionary prompts (ASCII pointer, no colours).
3. Verify contrast: every palette colour pair must meet 4.5:1 against #1E1E1E (dark) or #FFFFFF (light); document the computed ratios in a comment-free table in docs/TESTING_GUIDE.md.
DEBUGGING:
# print(f"[DEBUG] layout width={width} mode={mode}")
OFFLINE DOCKER TEST CASES:
- Rendering at width 50 produces no line longer than 50 characters.
- A resize from 120 to 50 columns re-renders the live stage panel without exceptions.
- Computed contrast ratios for all eight palette entries are >= 4.5.

## EXTEND: src/voxclone/cli.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add `--version` printing the version and engine mode; make --plain, --debug and NO_COLOR behave identically for every command.
2. Ensure every command prints its error through the same code path as the error panel's text (message, code, hint) when not interactive.
DEBUGGING:
# print(f"[DEBUG] cli version={version} plain={plain}")
OFFLINE DOCKER TEST CASES:
- `python -m voxclone --version` prints the version and exits 0.
- A forced error in `speak` prints message, code and hint in plain mode.

## EXTEND: tests/unit/test_errors.py
PROMPT FOR LLM IMPLEMENTATION:
1. Add a registry test: for each of the 13 codes assert there is (a) a Troubleshooting row in README.md, (b) a recovery_actions tuple, and (c) at least one test elsewhere in the suite that raises or expects that code (search the tests tree for the code string).
DEBUGGING:
# print(f"[DEBUG] code {code}: readme={in_readme} actions={actions} tests={n_tests}")
OFFLINE DOCKER TEST CASES:
- Removing a code from the README troubleshooting table makes this test fail.

## EXTEND: Makefile and pyproject.toml (confirm only)
PROMPT FOR LLM IMPLEMENTATION:
1. Confirm `make coverage` enforces fail_under = 85 with src/voxclone/engines/real_*.py omitted; adjust only if the P0 definition differs.
2. Add a `release` target that runs lint, typecheck, coverage and prints the git tag command `git tag v1.0` (does not tag automatically).
DEBUGGING:
# print("[DEBUG] make release steps echoed")
OFFLINE DOCKER TEST CASES:
- `make release` fails if coverage is below 85 percent and succeeds otherwise.
EOF

echo "====================================================="
echo "Milestone P6 Seeded Successfully!"
echo "NEXT STEPS:"
echo "1. Provide the seeded files AND docs/seed_extensions/P6_extensions.md to generate code and docs."
echo "2. Run offline tests & coverage: 'pytest tests/ --cov=src/voxclone --cov-fail-under=85 -m \"not gpu\"'."
echo "3. For local GPU KPI run: 'docker compose run --rm -e VOXCLONE_SOAK_JOBS=50 voxclone pytest -m gpu'."
echo "   For CPU / AMD Radeon APU execution: test using docker-compose.cpu.yml."
echo "4. Run 'git add . && git commit -m \"feat: complete P6\"'"
echo "5. Merge and tag: 'git checkout main && git merge --no-ff milestone/p6-hardening-release && git tag p6-done && git tag v1.0'"
echo "6. Proceed to P7.sh (Remote GPU Backend with Google Colab & Google Drive queue)."
echo "====================================================="
