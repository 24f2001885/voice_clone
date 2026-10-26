# MASTER PROJECT BLUEPRINT: VoxClone CLI (Docker + Git Milestone Workflow)

> Companion to `project-definition-report.md` (PDR), `technical-design-report.md` (TDR) and `ui-ux-design-plan.md`. Milestones **P0-P6** correspond 1:1 to PDR milestones **M0-M6**. Screen IDs (S-xx) refer to the UI/UX Design Plan.

---

## 1. Unified Directory Structure (final state)

```
voxclone/
├── .env.example                      # all VOXCLONE_* variables (TDR section 16)
├── .gitignore                        # data/, outputs/, profiles/, inputs/, *.wav, .env
├── .dockerignore
├── Dockerfile
├── docker-compose.yml                # runtime: GPU, volumes, WSLg audio
├── docker-compose.cpu.yml            # runtime: CPU/AMD fallback without NVIDIA GPU reservations
├── docker-compose.dev.yml            # source bind-mount for development
├── docker-compose.test.yml           # CPU-only, network_mode: none, fake engines
├── Makefile                          # lint, typecheck, test, test-gpu, build, run
├── pyproject.toml                    # package metadata, ruff/black/mypy/pytest config
├── requirements.in                   # top-level dependencies
├── requirements.lock                 # pinned (pip-compile output)
├── README.md
├── LICENSES.md                       # code + model/weight license record
├── docs/
│   ├── project-definition-report.md
│   ├── technical-design-report.md
│   ├── ui-ux-design-plan.md
│   ├── master-project-blueprint.md
│   ├── TESTING_GUIDE.md              # how to run each test level
│   ├── RECORDING_TIPS.md             # how to record a good 20-30 s sample
│   └── LIVE_MODE_SPIKE.md            # design-only note for the paused feature (P6)
├── migrations/
│   ├── 001_init.sql                  # all tables + default settings
│   └── 002_indexes.sql
├── scripts/
│   ├── doctor.sh                     # host-side GPU/Docker pre-checks
│   └── fetch_models.sh               # wrapper for the one-time weight download
├── src/
│   └── voxclone/
│       ├── __init__.py
│       ├── __main__.py               # `python -m voxclone`
│       ├── cli.py                    # Typer app; no args → run_main_menu()
│       ├── config.py                 # env + settings loading, defaults
│       ├── constants.py              # emotion map, error codes, limits
│       ├── errors.py                 # VoxcloneError + VX-xxx classes
│       ├── logging_setup.py          # JSONL rotating logger
│       ├── models/                   # dataclasses (not ORM)
│       │   ├── __init__.py
│       │   ├── profile.py
│       │   ├── job.py
│       │   ├── job_chunk.py
│       │   ├── model_event.py
│       │   └── progress.py           # ProgressEvent
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── db.py                 # connection, pragmas, transactions
│       │   ├── migrate.py            # applies migrations/
│       │   ├── profiles_repo.py
│       │   ├── jobs_repo.py
│       │   ├── chunks_repo.py
│       │   ├── model_events_repo.py
│       │   ├── settings_repo.py
│       │   └── files.py              # data-dir layout, safe paths, cleanup
│       ├── services/
│       │   ├── __init__.py
│       │   ├── profile_service.py
│       │   ├── job_service.py
│       │   ├── model_service.py
│       │   ├── settings_service.py
│       │   └── system_service.py     # doctor, storage, clean
│       ├── engines/
│       │   ├── __init__.py
│       │   ├── base.py               # TtsEngine, VcEngine, EmotionEngine protocols
│       │   ├── model_manager.py      # one-resident-model manager (TDR 3.7)
│       │   ├── real_tts.py
│       │   ├── real_vc.py
│       │   ├── real_emotion.py
│       │   ├── remote_tts.py         # Google Drive queue TTS adapter
│       │   ├── remote_vc.py          # Google Drive queue VC adapter
│       │   └── fake_engines.py       # deterministic test doubles
│       ├── transport/
│       │   ├── __init__.py
│       │   └── drive_queue.py        # Google Drive inbox/outbox file exchange protocol
│       ├── audio/
│       │   ├── __init__.py
│       │   ├── io.py                 # load/save/resample, mic record, playback
│       │   ├── validate.py           # sample validation + quality score
│       │   ├── splitter.py           # silence-aware 3-5 s cut points
│       │   ├── dsp_workers.py        # CPU pool functions (no torch import!)
│       │   ├── parallel.py           # spawn pool, worker-count policy
│       │   └── join.py               # loudness match + crossfade join
│       ├── pipelines/
│       │   ├── __init__.py
│       │   ├── text_splitter.py      # sentence/passages ≤200 chars
│       │   ├── emotion_mapping.py    # label → expressiveness
│       │   ├── text_pipeline.py
│       │   └── recording_pipeline.py # chunked parallel conversion (flagship)
│       └── ui/
│           ├── __init__.py
│           ├── theme.py              # palette, icons, --plain fallbacks
│           ├── components.py         # panels, tables, progress, badges
│           ├── session.py            # SessionState + screen stack
│           ├── menu.py               # run_main_menu(), dropdown helpers
│           └── screens/
│               ├── welcome.py              # S-02, S-03, S-04
│               ├── profiles.py             # S-10..S-17
│               ├── text_to_voice.py        # S-20..S-26
│               ├── recording_to_voice.py   # S-30..S-35
│               ├── job_history.py          # S-40..S-43
│               ├── system.py               # S-50..S-56
│               ├── error_panel.py          # S-57
│               └── remote_worker.py        # S-58 (Colab Drive queue status & setup)

├── tests/
│   ├── conftest.py                   # temp data dir, fake engines, synthetic audio
│   ├── unit/
│   │   ├── test_splitter.py
│   │   ├── test_join.py
│   │   ├── test_validate.py
│   │   ├── test_text_splitter.py
│   │   ├── test_emotion_mapping.py
│   │   ├── test_model_manager.py
│   │   ├── test_settings_repo.py
│   │   └── test_errors.py
│   ├── integration/
│   │   ├── test_migrations.py
│   │   ├── test_profile_service.py
│   │   ├── test_text_pipeline.py
│   │   ├── test_recording_pipeline.py
│   │   ├── test_resume.py
│   │   └── test_parallel_pool.py
│   ├── e2e/
│   │   ├── test_menu_enroll_speak.py
│   │   └── test_menu_convert.py
│   └── gpu/                          # opt-in: pytest -m gpu
│       ├── test_real_tts_smoke.py
│       ├── test_real_vc_smoke.py
│       ├── test_load_unload_memory.py
│       └── test_benchmark.py
├── data/                             # volume: voxclone.db, logs/, work/
├── profiles/                         # volume: cleaned reference WAVs
├── outputs/                          # volume: generated WAVs
└── inputs/                           # volume: drop recordings here
```

Every top-level item above exists from the milestone that first needs it (see section 3); nothing built later needs a new top-level folder.

## 2. Git + Docker Workflow

### 2.1 Branching
- `main`: always passes `make lint typecheck test`; each merge corresponds to a finished milestone.
- One branch per milestone, created from an up-to-date `main`:
  `git checkout main && git pull && git checkout -b milestone/p<N>-<slug>`
  | Milestone | Branch |
  |---|---|
  | P0 | `milestone/p0-foundation` |
  | P1 | `milestone/p1-models-profiles` |
  | P2 | `milestone/p2-text-to-voice` |
  | P3 | `milestone/p3-emotion` |
  | P4 | `milestone/p4-recording-to-voice` |
  | P5 | `milestone/p5-jobs-performance` |
  | P6 | `milestone/p6-hardening-release` |
  | P7 | `milestone/p7-remote-gpu` |
- Small fixes inside a milestone use `fix/<short-desc>` branches off the milestone branch.

### 2.2 What "offline Docker testing" means here
- Tests run in `docker-compose.test.yml`: **no GPU, `network_mode: none`**, `VOXCLONE_ENGINE=fake`, a throwaway data directory.
- Fake engines return deterministic audio (e.g. a tone whose length matches the input), so the full pipelines, SQLite, the `spawn` worker pool and the menu are exercised without any model weights.
- Real-model checks are separate and opt-in (`make test-gpu`) and are run **manually on your machine** before merging P2, P3, P4 and P5.
- Command: `docker compose -f docker-compose.test.yml run --rm tests make test`.

### 2.3 Commit and merge rules
1. **Commit small, commit working.** Conventional commits: `type(scope): message` where type ∈ `feat, fix, test, docs, build, refactor, chore` and scope = `p0`…`p6` or a module name. Example: `feat(p4): add silence-aware chunk splitter`.
2. **Test first or together.** A feature commit includes its tests; a commit may not leave `make test` red.
3. **Before each commit:** `make lint` (ruff + black --check). **Before each push/merge:** full offline suite green.
4. **Milestone gate (all required to merge to `main`):**
   - offline test suite green in the Docker test container;
   - milestone's acceptance checks (section 3) done;
   - for P2-P5: `make test-gpu` pass on the real machine;
   - `docs/` updated; `git tag p<N>-done` after merge (`git merge --no-ff milestone/p<N>-<slug>`).
5. **Never commit:** `.env`, weights, `data/`, `outputs/`, `profiles/`, audio files (except tiny synthetic fixtures generated at test time).

## 3. Milestone → Feature → Commit Map

Order guarantees each milestone depends only on earlier ones. Time is the PDR estimate (solo, part-time).

### P0: Foundation (PDR M0, ~1 week)
**Goal:** a GPU-aware container that starts, shows the open menu, logs, and has a test harness. No AI model yet.

| Feature | Files | Commit |
|---|---|---|
| Repo skeleton, tooling config, Makefile | `pyproject.toml`, `Makefile`, `.gitignore`, `.dockerignore`, `requirements.in/.lock` | `build(p0): scaffold repo and tooling` |
| Dockerfile + compose (GPU, volumes, WSLg) | `Dockerfile`, `docker-compose*.yml`, `.env.example`, `scripts/doctor.sh` | `build(p0): add Docker images and compose files` |
| Config + error classes + constants | `config.py`, `constants.py`, `errors.py` | `feat(p0): add config, constants and VX error codes` |
| JSONL logging | `logging_setup.py` | `feat(p0): add rotating JSON logger` |
| SQLite + migrations | `storage/db.py`, `storage/migrate.py`, `migrations/001_init.sql`, `002_indexes.sql`, `settings_repo.py`, `files.py` | `feat(p0): add SQLite schema and migration runner` |
| Settings service | `settings_service.py` | `feat(p0): add settings service` |
| Theme + components + session + open main menu (S-01) | `ui/theme.py`, `components.py`, `session.py`, `menu.py`, `cli.py`, `__main__.py` | `feat(p0): add dropdown main menu shell` |
| Doctor + Model status stub + Storage report (S-50, S-51, S-53, S-56) | `system_service.py`, `screens/system.py` | `feat(p0): add System menu with doctor and storage` |
| Fake engines + test harness | `engines/base.py`, `engines/fake_engines.py`, `tests/conftest.py` | `test(p0): add fake engines and fixtures` |

**Acceptance:** `nvidia-smi` works inside the container; `docker compose run --rm voxclone` opens the menu; Doctor shows GPU/RAM/disk checks; `make test` passes offline.

### P1: Model Manager + Voice Profiles (PDR M1, ~1 week)
**Goal:** models can be loaded/unloaded safely and voices can be enrolled. Depends on P0.

| Feature | Files | Commit |
|---|---|---|
| Engine protocols finalized + ModelManager with one-resident invariant, VRAM budget check, event log | `engines/model_manager.py`, `model_events_repo.py`, `model_service.py` | `feat(p1): add one-model-at-a-time manager` |
| Free GPU memory + Model status screens (S-51, S-52) | `screens/system.py` | `feat(p1): add model status and free GPU memory` |
| Audio IO (load, resample, mic record, playback) | `audio/io.py` | `feat(p1): add audio input/output helpers` |
| Sample validation + quality score | `audio/validate.py` | `feat(p1): add sample validation and quality scoring` |
| Profile repo + service (create, list, rename, delete, preview, consent) | `profiles_repo.py`, `profile_service.py`, `models/profile.py` | `feat(p1): add voice profile service with consent gate` |
| Profile screens S-10..S-17 and first-run welcome S-02..S-04 | `screens/profiles.py`, `screens/welcome.py` | `feat(p1): add profile menus and enrollment flows` |
| Manager + profile tests | `test_model_manager.py`, `test_validate.py`, `test_profile_service.py`, `tests/gpu/test_load_unload_memory.py` | `test(p1): cover model manager and profiles` |

**Acceptance:** loading model A then B never leaves both resident; 10× load/unload returns VRAM to within 200 MB of baseline (GPU test); a profile can be enrolled from file and mic, listed, previewed, renamed, deleted; enrollment without consent is refused.

### P2: Text → Voice (PDR M2, ~1 week)
**Goal:** type text, hear it in your voice, save/play/both. Depends on P1 (profiles, manager).

| Feature | Files | Commit |
|---|---|---|
| Real TTS engine adapter | `engines/real_tts.py` | `feat(p2): add real TTS engine adapter` |
| Sentence/passage splitter (≤200 chars) | `pipelines/text_splitter.py`, `test_text_splitter.py` | `feat(p2): add text passage splitter` |
| Crossfade join + loudness match | `audio/join.py`, `test_join.py` | `feat(p2): add crossfade join and loudness match` |
| Text pipeline (fixed expressiveness) + job records | `pipelines/text_pipeline.py`, `jobs_repo.py`, `chunks_repo.py`, `job_service.py`, `models/job.py`, `models/job_chunk.py`, `models/progress.py` | `feat(p2): add text-to-voice pipeline` |
| Output handling (save/play/both, naming) | `job_service.py`, `audio/io.py` | `feat(p2): add save and play output modes` |
| Screens S-20..S-22, S-24..S-26 + `speak` sub-command | `screens/text_to_voice.py`, `cli.py` | `feat(p2): add text-to-voice menus and speak command` |
| Tests | `test_text_pipeline.py`, `tests/e2e/test_menu_enroll_speak.py`, `tests/gpu/test_real_tts_smoke.py` | `test(p2): cover text pipeline end to end` |

**Acceptance:** a paragraph spoken in the enrolled voice; Save, Play and Both all work (Play falls back gracefully if audio is unavailable); watermark behaviour documented.

### P3: Emotion from Text (PDR M3, ~1 week)
**Goal:** delivery follows the emotion of the text. Depends on P2.

| Feature | Files | Commit |
|---|---|---|
| Real emotion classifier adapter | `engines/real_emotion.py` | `feat(p3): add emotion classifier adapter` |
| Label → expressiveness mapping (settings-overridable) | `pipelines/emotion_mapping.py`, `constants.py`, `test_emotion_mapping.py` | `feat(p3): add emotion mapping` |
| Two-stage text pipeline (classify → unload → TTS) | `pipelines/text_pipeline.py` | `feat(p3): chain emotion and TTS with unload between` |
| Emotion choice + preview table screens (S-22, S-23) | `screens/text_to_voice.py` | `feat(p3): add emotion choice and preview table` |
| Tests | `test_text_pipeline.py` (extended), `test_model_manager.py` (handoff order) | `test(p3): verify emotion handoff and mapping` |

**Acceptance:** Auto mode labels passages and varies delivery audibly; Manual override works; model events show *emotion unload before TTS load*.

### P4: Recording → Voice, Chunked Parallel (PDR M4, ~2 weeks)
**Goal:** the flagship conversion pipeline. Depends on P1, P2 (join, output, jobs).

| Feature | Files | Commit |
|---|---|---|
| Real voice-conversion engine adapter | `engines/real_vc.py` | `feat(p4): add real voice-conversion adapter` |
| Silence-aware 3-5 s splitter + tail merge | `audio/splitter.py`, `test_splitter.py` | `feat(p4): add silence-aware chunk splitter` |
| CPU workers (prep, loudness match) with `spawn` pool and worker-count policy | `audio/dsp_workers.py`, `audio/parallel.py`, `test_parallel_pool.py` | `feat(p4): add all-core chunk prep and post workers` |
| Recording pipeline: prep → GPU queue → post → join; retry; chunk persistence | `pipelines/recording_pipeline.py`, `chunks_repo.py` | `feat(p4): add chunked parallel conversion pipeline` |
| Mic "record then convert" input | `audio/io.py`, `screens/recording_to_voice.py` | `feat(p4): add record-then-convert input` |
| Screens S-30..S-35 + `convert` sub-command + stage panel | `screens/recording_to_voice.py`, `ui/components.py`, `cli.py` | `feat(p4): add recording-to-voice menus and progress panel` |
| Tests (incl. cut-point properties, order preservation, failure retry) | `test_recording_pipeline.py`, `tests/e2e/test_menu_convert.py`, `tests/gpu/test_real_vc_smoke.py` | `test(p4): cover chunked conversion` |

**Acceptance:** a 2-3 minute file converts with no audible clicks; output order always matches input; CPU stage runs on all cores while GPU is busy (verified by timing log); peak VRAM ≤ 7 GB.

### P5: Jobs, Resume & Performance (PDR M5, ~1 week)
**Goal:** reliable and measurably fast. Depends on P2-P4.

| Feature | Files | Commit |
|---|---|---|
| Job history table, detail, delete (S-40, S-41, S-43) | `screens/job_history.py`, `job_service.py` | `feat(p5): add job history screens` |
| Resume interrupted jobs; Ctrl+C handling | `recording_pipeline.py`, `text_pipeline.py`, `test_resume.py` | `feat(p5): add job resume and clean cancel` |
| Startup sweep (stale jobs, work dirs, retention) | `storage/files.py`, `system_service.py` | `feat(p5): add startup sweep and retention` |
| Settings screens (S-54, S-55) + keep-warm policy | `screens/system.py`, `settings_service.py` | `feat(p5): add settings editor` |
| Benchmark command + tuning (chunk length, workers, precision) | `cli.py`, `tests/gpu/test_benchmark.py` | `feat(p5): add benchmark and tune performance` |
| Output browser and replay | `screens/job_history.py` | `feat(p5): add output browser with replay` |

**Acceptance:** PDR section 13 technical KPIs measured and recorded in `docs/` (VRAM, RAM, RTF ≤ 1.5, CPU share ≤ 15 %, 0 OOM across 50 jobs); resume succeeds after a forced `docker kill`.

### P6: Hardening & Release (PDR M6, ~1 week)
**Goal:** ready for daily use. Depends on all prior.

| Feature | Files | Commit |
|---|---|---|
| Error panel polish; full VX code coverage | `screens/error_panel.py`, `errors.py` | `feat(p6): finalize error panel and codes` |
| `--plain` / `NO_COLOR` mode; small-terminal layouts | `ui/theme.py`, `ui/components.py` | `feat(p6): add plain mode and responsive layouts` |
| Full E2E pass; coverage ≥ 85 % | `tests/` | `test(p6): complete E2E and coverage` |
| Docs: README, TESTING_GUIDE, RECORDING_TIPS, LICENSES | `README.md`, `docs/*.md`, `LICENSES.md` | `docs(p6): write user and developer docs` |
| Live mode design spike (**paused feature, design only, no menu entry**) | `docs/LIVE_MODE_SPIKE.md` | `docs(p6): document paused live-mode design` |
| Release tag | git tag | `chore(p6): release v1.0` |

**Acceptance:** fresh-clone setup works from the README alone; all PDR section 13 KPIs met; no real-time menu entry exists.

### P7: Remote GPU Backend (Google Drive Queue & Colab Worker) (PDR M7, ~1 week)
**Goal:** Enables full-speed GPU neural generation on AMD APUs, Intel iGPUs, or machines without local NVIDIA CUDA cards using a decoupled Google Drive queue connected to a free Google Colab NVIDIA T4 GPU worker.

| Feature | Files | Commit |
|---|---|---|
| Google Drive queue transport layer (inbox/outbox file exchange, JSON manifest, heartbeat) | `transport/drive_queue.py`, `constants.py` | `feat(p7): add Google Drive file queue transport` |
| Remote engine adapters implementing TtsEngine and VcEngine protocols | `engines/remote_tts.py`, `engines/remote_vc.py`, `engines/__init__.py` | `feat(p7): add RemoteTTS and RemoteVC engine adapters` |
| Google Colab GPU worker notebook with persistent Drive model cache | `scripts/colab_worker.ipynb` | `feat(p7): add standalone Colab T4 GPU worker notebook` |
| Remote worker error codes (VX-320..VX-323) & Doctor connectivity probe | `errors.py`, `services/system_service.py` | `feat(p7): add remote worker error codes and doctor probe` |
| UI Remote worker status & Colab setup guide (S-58) + Settings toggle | `screens/system.py`, `screens/remote_worker.py` | `feat(p7): add remote worker status and configuration screens` |
| Comprehensive test suite simulating Google Drive folder queue | `tests/unit/test_drive_queue.py`, `tests/integration/test_remote_engines.py` | `test(p7): cover Google Drive queue and remote engine adapters` |

**Acceptance:** With `VOXCLONE_BACKEND=remote_drive`, chunk requests write cleanly to `inbox/`; Colab worker (or test double) produces `outbox/` audio; VoxClone CLI seamlessly stitches and delivers output identical to local execution; zero port forwarding or public network tunnels required.

### Traceability

| PDR milestone | Blueprint | TDR sections | Main screens |
|---|---|---|---|
| M0 | P0 | 1, 2, 9, 12, 13 | S-01, S-50, S-51, S-53, S-56 |
| M1 | P1 | 3.7, 4 (profiles, model_events), 6 | S-02..S-04, S-10..S-17, S-51, S-52 |
| M2 | P2 | 3.4, 4 (jobs, job_chunks), 5.2 | S-20..S-26 |
| M3 | P3 | 3.8 | S-22, S-23 |
| M4 | P4 | 3.1-3.6 | S-30..S-35 |
| M5 | P5 | 11 | S-40..S-43, S-54, S-55 |
| M6 | P6 | 10, 12, 15 | S-57, S-03, S-04 |
| M7 | P7 | 2.4, 4.5, 12.3 | S-58, S-50, S-54 |

