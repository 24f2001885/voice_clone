# TECHNICAL DESIGN REPORT: VoxClone CLI

> **Reading notes.** The PDR describes a local, single-user CLI. Where the TDR template assumes a web app (CSRF, JWT, REST over HTTP, payments, email), this document says so plainly and substitutes what actually applies. Defaults chosen where the PDR is silent are marked **[DEFAULT]**.

---

## 1. Introduction & Conventions

| Item | Decision |
|---|---|
| Language / runtime | Python **3.11** inside Docker |
| Packaging | `pyproject.toml`; dependencies locked with `pip-tools` into `requirements.lock` **[DEFAULT]** |
| Package name | `voxclone` (import path), CLI entry point `voxclone` |
| Variables, functions, modules | `snake_case` |
| Classes | `PascalCase` |
| Constants / env vars | `UPPER_SNAKE_CASE`; env vars prefixed `VOXCLONE_` |
| CLI sub-commands | `kebab-case` words (`free-gpu`) |
| Resource names in the service layer | plural nouns (`profiles`, `jobs`, `models`) |
| Files | `snake_case.py`; tests mirror source as `test_<module>.py` |
| Type hints | Required on all public functions; `mypy --strict` on `voxclone/` |
| Lint / format | `ruff` (rules: E, F, I, N, UP, B, SIM), `black` (line length 100) |
| Docstrings | Google style on public classes and functions |
| Time | All timestamps stored as ISO-8601 UTC text |
| IDs | UUID v4 as lowercase text |
| Audio internal format | float32 mono numpy arrays; stored files are 16-bit PCM WAV unless stated |

## 2. System Architecture

### 2.1 Client-server model
There is **no server**. The process is a single Python application (the "client" and "server" are one process). The interactive menu and the Typer sub-commands are two front doors to the same **service layer**.

```
 ┌──────────────────────────── Docker container (GPU) ─────────────────────────────┐
 │                                                                                 │
 │  Interface layer     menu (questionary+rich)      sub-commands (Typer)          │
 │        │                       │                          │                     │
 │        └───────────────┬───────┴──────────────────────────┘                     │
 │                        ▼                                                        │
 │  Service layer   ProfileService · JobService · ModelService · SystemService     │
 │                        │                                                        │
 │        ┌───────────────┼──────────────────────────────┐                         │
 │        ▼               ▼                              ▼                         │
 │  Pipelines       text_pipeline            recording_pipeline                    │
 │                        │                              │                         │
 │  Engines   emotion_engine · tts_engine · vc_engine    │   audio_dsp (CPU pool)  │
 │                        ▲                              │                         │
 │  ModelManager (owns the single resident model) ◄──────┘                         │
 │                        │                                                        │
 │  Storage   SQLite (data/voxclone.db) · files (profiles/ outputs/ work/ logs/)   │
 └─────────────────────────────────────────────────────────────────────────────────┘
        volumes: hf_models · profiles · outputs · data        host: WSLg PulseAudio socket
```

### 2.2 Container orchestration
Docker Compose with one service (`voxclone`), GPU reservation, `stdin_open`/`tty` for the interactive menu, `shm_size: 2gb`, and four named or bind volumes. No other containers. A second compose file (`docker-compose.test.yml`) defines a CPU-only test service.

### 2.3 Data flow end to end

**Text to Voice**
1. Menu collects profile + text + emotion mode → `JobService.create_job(job_type="text_to_voice", ...)`.
2. `text_pipeline` splits text into passages (≤200 chars) and writes `job_chunks` rows (`kind="sentence"`).
3. If `auto_emotion`: `ModelManager.use("emotion")` loads the classifier → label each passage → exit context (unloads).
4. `ModelManager.use("tts")` loads TTS → synthesize each passage with the profile's reference and mapped expressiveness.
5. CPU pool post-processes (loudness match) → crossfade join → write output → optionally play.
6. Job marked `succeeded`; output path stored.

**Recording to Voice**
1. Input file (or mic recording written to `work/`) → `recording_pipeline`.
2. **CPU stage:** decode → mono 16 kHz → silence-aware split into 3-5 s chunks → pool cleans each chunk and writes `work/<job_id>/in_NNNN.wav`.
3. **GPU stage:** `ModelManager.use("vc")` → convert chunks in order; each finished chunk is persisted as `work/<job_id>/out_NNNN.wav` and its row set to `converted`.
4. **CPU stage:** pool loudness-matches each output chunk to its input chunk → crossfade join → final WAV.
5. Output saved/played; temp chunk files deleted on success.

## 3. Flagship Feature: Chunked Parallel Voice Conversion Engine

This is the hardest piece of logic because it must be **fast on a small GPU, seamless to the ear, resumable, and memory-safe** at once.

### 3.1 Why this shape
- The GPU model is large and VRAM is 8 GB, so **exactly one model copy** exists. Parallelizing *model inference* across processes would need several copies and would not fit. So the GPU stage is a **single sequential consumer**.
- Everything that is *not* the model (decode, resample, trim, normalize, loudness measure, file writes, join) is CPU work. It is split across **all cores** and **overlapped** with the GPU so the GPU never idles waiting for input.
- Short chunks (3-5 s) keep per-call GPU memory small, bound the cost of a failed chunk, and make resume cheap.

### 3.2 Algorithm

```
function convert_recording(job):
    # ---- Stage A: CPU (all cores) ----
    signal = load_mono(job.input_path, sample_rate=16000)            # streaming decode for very long files
    cut_points = find_cut_points(signal, min_sec=3.0, max_sec=5.0)   # see 3.3
    chunks = slice(signal, cut_points)
    for i, chunk in enumerate(chunks): insert job_chunks(job_id, i, status="pending")
    pool = ProcessPoolExecutor(max_workers=workers, mp_context=spawn)
    prep_futures = [pool.submit(prepare_chunk, i, chunk) for i, chunk in enumerate(chunks)]

    # ---- Stage B: GPU (single consumer, in order) ----
    with model_manager.use("vc") as vc_model:
        post_futures = []
        for i in range(len(chunks)):
            if chunk_status(job, i) == "converted": continue         # resume
            in_path = prep_futures[i].result()                       # blocks only if prep is behind
            out = convert_with_retry(vc_model, in_path, reference)   # see 3.5
            persist(out_i); set_status(i, "converted")
            post_futures.append(pool.submit(match_loudness, i, out, in_path))   # overlaps with next GPU call

    # ---- Stage C: CPU ----
    outs = [f.result() for f in post_futures]                        # already ordered by i
    final = crossfade_join(outs, fade_ms=30)
    write_wav(final, job.output_path)
```

Because preparation futures are all submitted up front, the pool works ahead of the GPU; because loudness-matching is submitted as soon as a chunk is converted, post-processing overlaps the next conversion.

### 3.3 Silence-aware cut-point search
1. Compute frame RMS energy with a 20 ms hop.
2. Starting at `start = 0`, while remaining audio > `max_sec`: search the energy frames between `start + min_sec` and `start + max_sec`; choose the **minimum-energy frame** as the cut; set `start = cut`.
3. The final remainder becomes the last chunk.
4. **Tail merge:** if the final chunk is shorter than 1.0 s, merge it into the previous chunk (allowing up to `max_sec + 1.0`).

Why minimum energy and not fixed 4 s cuts: a fixed cut lands mid-word, and the model then sees a half phoneme, which produces artifacts exactly at the join.

### 3.4 Joining (seam hiding)
- **Per-chunk loudness match:** scale each output chunk so its RMS equals the RMS of its input chunk (clipped to ±1.0). This removes level jumps caused by per-chunk model variation.
- **Equal-power crossfade of 30 ms** between neighbours (configurable). Because cuts are at near-silence, a short fade is enough and does not smear speech.
- Output sample rate is the model's native rate (read from the model object).

### 3.5 Failure handling and edge cases

| Case | Behaviour |
|---|---|
| Input shorter than `min_sec` | Single chunk, no split |
| No quiet region found (continuous noise/music) | Cut at the minimum-energy frame anyway; warn "chunks may sound abrupt" |
| Input is silence only | Job fails with `VX-210 no speech detected` before any model load |
| Stereo / high sample rate | Down-mixed and resampled in Stage A |
| Clipping in input | Peak-normalize to 0.95 in `prepare_chunk` |
| `torch.cuda.OutOfMemoryError` on a chunk | Free cache, retry once; second failure → job `failed` with `VX-301`, resumable |
| Any other model exception on a chunk | Retry once; then job `failed` with chunk index in the error message |
| Ctrl+C | Stop submitting, let the current GPU call finish, persist state, mark job `cancelled`, leave work files for resume |
| Worker process dies | `BrokenProcessPool` caught; pool recreated once; remaining prep re-submitted |
| Very long input (e.g. 1 hour) | Memory ≈ 16 kHz × 4 B × 3600 s ≈ 230 MB, acceptable; chunks written to disk, not held |
| Resume | Rows with `status="converted"` and an existing `out_NNNN.wav` are skipped |

### 3.6 Why `spawn` and worker restrictions
CUDA state does not survive `fork`. The pool uses the **`spawn`** start method, and worker functions live in `voxclone/audio/dsp_workers.py`, which imports only numpy/librosa/soundfile (never torch). This also keeps each worker's memory small (see risk R4).

### 3.7 Model Manager state machine (shared by all pipelines)

```
IDLE ──use(k)──► LOADING(k) ──ok──► READY(k) ──use(k)──► READY(k)          (reuse, no reload)
                     │ fail                  │ use(j≠k)
                     ▼                       ▼
                   IDLE               UNLOADING(k) ──► LOADING(j) ──► READY(j)
```
- API: `with model_manager.use("tts") as model: ...` (context manager).
- **Invariant:** `len(resident_models) ≤ 1`.
- Unload = drop reference → `gc.collect()` → `torch.cuda.empty_cache()` → `torch.cuda.synchronize()` → measure free VRAM.
- Before load, `estimated_vram_mb(k)` is compared with `VOXCLONE_VRAM_BUDGET_MB`; if free VRAM is insufficient after unload, raise `VX-300`.
- **Keep-warm policy [DEFAULT]:** after a job the last model stays resident until a different model is requested, the user picks "Free GPU memory", or the app exits. Setting `keep_warm=false` unloads after every job.

### 3.8 Emotion mapping
The classifier returns one of: `joy, sadness, anger, fear, surprise, disgust, neutral`. Default mapping to the TTS expressiveness value (0.25 calm to 1.0 intense) **[DEFAULT, to be tuned by ear in M3]**:

| Label | Expressiveness |
|---|---|
| neutral | 0.40 |
| sadness | 0.30 |
| joy | 0.70 |
| fear | 0.70 |
| disgust | 0.70 |
| surprise | 0.80 |
| anger | 0.90 |

User override replaces the mapped value for the whole job.

## 4. Database Design

SQLite 3, `PRAGMA foreign_keys = ON`, `PRAGMA journal_mode = WAL`. Types below are SQLite storage classes with the logical type in parentheses.

- `schema_migrations`
  - `version (INTEGER, Primary Key)`
  - `name (TEXT, NOT NULL)`
  - `applied_at (TEXT, NOT NULL)` — ISO-8601 UTC

- `voice_profiles`
  - `id (TEXT UUID, Primary Key)`
  - `name (TEXT, NOT NULL, UNIQUE)` — 1-64 chars, `[A-Za-z0-9_-]`
  - `reference_path (TEXT, NOT NULL)` — cleaned WAV under `profiles/`
  - `source_type (TEXT, NOT NULL, CHECK in ('file','mic'))`
  - `original_filename (TEXT, NULL)`
  - `duration_sec (REAL, NOT NULL, CHECK > 0)`
  - `sample_rate (INTEGER, NOT NULL)`
  - `quality_score (REAL, NULL)` — 0-1 heuristic from level/noise/clipping
  - `quality_notes (TEXT, NULL)`
  - `sha256 (TEXT, NOT NULL)` — of the cleaned reference
  - `consent_confirmed (INTEGER, NOT NULL, CHECK in (0,1))` — must be 1 to insert
  - `consent_confirmed_at (TEXT, NOT NULL)`
  - `created_at (TEXT, NOT NULL)`
  - `updated_at (TEXT, NOT NULL)`

- `jobs`
  - `id (TEXT UUID, Primary Key)`
  - `job_type (TEXT, NOT NULL, CHECK in ('text_to_voice','recording_to_voice'))`
  - `status (TEXT, NOT NULL, CHECK in ('queued','running','succeeded','failed','cancelled'))`
  - `profile_id (TEXT UUID, Foreign Key → voice_profiles.id, ON DELETE SET NULL)`
  - `profile_name_snapshot (TEXT, NOT NULL)` — survives profile deletion
  - `input_source (TEXT, NOT NULL, CHECK in ('text','file','mic'))`
  - `input_path (TEXT, NULL)`
  - `input_text (TEXT, NULL)`
  - `emotion_mode (TEXT, NULL, CHECK in ('auto','calm','normal','expressive'))`
  - `output_mode (TEXT, NOT NULL, CHECK in ('save','play','both'))`
  - `output_path (TEXT, NULL)`
  - `output_sample_rate (INTEGER, NULL)`
  - `output_duration_sec (REAL, NULL)`
  - `total_chunks (INTEGER, NOT NULL, DEFAULT 0)`
  - `completed_chunks (INTEGER, NOT NULL, DEFAULT 0)`
  - `error_code (TEXT, NULL)`
  - `error_message (TEXT, NULL)`
  - `created_at (TEXT, NOT NULL)`
  - `started_at (TEXT, NULL)`
  - `finished_at (TEXT, NULL)`
  - `elapsed_ms (INTEGER, NULL)`
  - `real_time_factor (REAL, NULL)` — elapsed / output duration

- `job_chunks`
  - `id (INTEGER, Primary Key, AUTOINCREMENT)`
  - `job_id (TEXT UUID, Foreign Key → jobs.id, ON DELETE CASCADE, NOT NULL)`
  - `chunk_index (INTEGER, NOT NULL, CHECK >= 0)`
  - `kind (TEXT, NOT NULL, CHECK in ('sentence','audio'))`
  - `status (TEXT, NOT NULL, CHECK in ('pending','prepared','converted','failed'))`
  - `text (TEXT, NULL)` — for `sentence`
  - `detected_emotion (TEXT, NULL)`
  - `expressiveness (REAL, NULL)`
  - `input_path (TEXT, NULL)`
  - `output_path (TEXT, NULL)`
  - `start_sec (REAL, NULL)` and `end_sec (REAL, NULL)` — position in the source
  - `attempts (INTEGER, NOT NULL, DEFAULT 0)`
  - `error_message (TEXT, NULL)`
  - `UNIQUE (job_id, chunk_index)`

- `model_events`
  - `id (INTEGER, Primary Key, AUTOINCREMENT)`
  - `model_key (TEXT, NOT NULL, CHECK in ('tts','vc','emotion'))`
  - `action (TEXT, NOT NULL, CHECK in ('load','unload','oom'))`
  - `device (TEXT, NOT NULL)`
  - `vram_free_before_mb (INTEGER, NULL)`
  - `vram_free_after_mb (INTEGER, NULL)`
  - `duration_ms (INTEGER, NULL)`
  - `job_id (TEXT UUID, Foreign Key → jobs.id, ON DELETE SET NULL, NULL)`
  - `created_at (TEXT, NOT NULL)`

- `app_settings`
  - `key (TEXT, Primary Key)`
  - `value (TEXT, NOT NULL)` — JSON-encoded
  - `updated_at (TEXT, NOT NULL)`

**Indexes:** `idx_jobs_created_at (jobs.created_at DESC)`, `idx_jobs_status (jobs.status)`, `idx_job_chunks_job (job_chunks.job_id, chunk_index)`, `idx_model_events_created (model_events.created_at)`.

**Default settings rows** (inserted by migration 001): `device=auto`, `workers=0` (0 = all cores), `chunk_min_sec=3.0`, `chunk_max_sec=5.0`, `crossfade_ms=30`, `default_output_mode=both`, `keep_warm=true`, `vram_budget_mb=7000`, `sentence_max_chars=200`.

**Data-access approach [DEFAULT]:** plain SQL in `voxclone/storage/` with parameterized queries and migration files `migrations/001_init.sql` … (no ORM; the schema is small and an ORM adds weight).

## 5. REST API Design

**No HTTP API exists in this build** (PDR: CLI only). To keep a future FastAPI/HTTP wrapper trivial, the **service layer is specified as RESTful resources** and the CLI maps onto it 1:1. Calls below are Python functions returning dataclasses (shown as JSON shapes).

### 5.1 Profiles
| Verb | Resource path | Request | Response |
|---|---|---|---|
| POST | `/profiles` | `{name, source: "file"\|"mic", file_path?, record_seconds?, consent_confirmed}` | `201 {id, name, duration_sec, quality_score, quality_notes}` |
| GET | `/profiles` | — | `200 [{id, name, duration_sec, created_at}]` |
| GET | `/profiles/{id}` | — | `200 {full profile}` |
| PATCH | `/profiles/{id}` | `{name}` | `200 {profile}` |
| DELETE | `/profiles/{id}` | — | `204` |
| POST | `/profiles/{id}/preview` | — | `202 {playing: true}` |

CLI map: `profiles enroll | list | preview | rename | delete`.

### 5.2 Jobs
| Verb | Resource path | Request | Response |
|---|---|---|---|
| POST | `/jobs` (type text) | `{job_type:"text_to_voice", profile_id, text, emotion_mode, output_mode}` | `202 {job_id}` (progress via callback/iterator) |
| POST | `/jobs` (type recording) | `{job_type:"recording_to_voice", profile_id, input_source:"file"\|"mic", input_path?, record_seconds?, output_mode}` | `202 {job_id}` |
| GET | `/jobs` | `?status=&limit=` | `200 [{id, job_type, status, created_at, output_path}]` |
| GET | `/jobs/{id}` | — | `200 {job + chunk counts}` |
| POST | `/jobs/{id}/resume` | — | `202 {job_id}` |
| POST | `/jobs/{id}/cancel` | — | `200 {status:"cancelled"}` |
| DELETE | `/jobs/{id}` | `?delete_output=bool` | `204` |

Progress is delivered as a Python iterator of `ProgressEvent{stage, chunk_index, total_chunks, message}`.

### 5.3 Models
| Verb | Resource path | Request | Response |
|---|---|---|---|
| GET | `/models` | — | `200 {resident: "tts"\|null, vram_used_mb, vram_free_mb, available:[...]}` |
| DELETE | `/models/resident` | — | `200 {unloaded: "tts"}` (Free GPU memory) |

(Models are loaded only as a side effect of jobs; there is intentionally **no** public "load model" call.)

### 5.4 System and settings
| Verb | Resource path | Request | Response |
|---|---|---|---|
| GET | `/system/doctor` | — | `200 {checks:[{name, ok, detail, fix_hint}]}` |
| GET | `/system/storage` | — | `200 {profiles_mb, outputs_mb, models_mb, work_mb}` |
| POST | `/system/clean` | — | `200 {freed_mb}` |
| GET | `/settings` | — | `200 {key: value}` |
| PUT | `/settings/{key}` | `{value}` | `200 {key, value}` |

### 5.5 Standard error shape
`{error_code: "VX-xxx", message: "plain language", hint: "what to do"}`. Error codes in section 12.

## 6. Security Design

CSRF, password hashing, JWT/session handling and network RBAC **do not apply** (no network surface, no accounts). The applicable controls are:

| Control | Implementation |
|---|---|
| Consent gate | `voice_profiles.consent_confirmed` must be 1 (DB CHECK + service check); enrollment prompt text is fixed and logged |
| Access control | Single operator; permissions are filesystem-level: `data/`, `profiles/`, `outputs/` created with mode `0700`; container runs as non-root user `voxclone` (UID 1000) |
| Role matrix (PDR section 11) | Implemented as code-level separation: runtime settings editable via UI; engine/schema changes require code changes |
| Path safety | All user-supplied paths resolved with `Path.resolve()`; output names generated by the app, never taken from user text; profile names validated by `^[A-Za-z0-9_-]{1,64}$` |
| SQL injection | Parameterized queries only; lint rule forbids string-formatted SQL |
| Network | After first weight download, `HF_HUB_OFFLINE=1`; compose test service uses `network_mode: none` |
| Supply chain | Versions pinned in `requirements.lock`; installs at image build only |
| Privacy | No telemetry; logs never contain full input text (first 40 chars only) and never contain audio |
| Output provenance | Default TTS engine is expected to embed an inaudible watermark in generated audio **(verify in M2 and document)** |
| Temp data | Work directories deleted after success; startup sweep removes orphans older than 24 h |

## 7. Frontend Technical Design

The "frontend" is a **terminal UI**.

| Aspect | Decision |
|---|---|
| Menu library | `questionary` (built on `prompt_toolkit`): `select` for dropdown menus (arrow keys, Enter, type-to-filter on long lists), `text`, `path`, `confirm` |
| Rendering | `rich`: `Panel`, `Table`, `Progress` (multi-stage bars), `Status` spinner, `Live` for model-load banners |
| Menu opens at launch | `voxclone` with no arguments calls `run_main_menu()` immediately after the banner |
| State management | A `SessionState` dataclass (selected profile, last job id, settings snapshot) held in `ui/session.py`; screens are functions `screen_x(state) -> next_screen_key`; a small **screen stack** gives "Back" on every screen |
| Templating | `rich` renderables built in `ui/components.py`; no template files |
| Theming | Central palette in `ui/theme.py` (see UX Design Plan section 7); `NO_COLOR` and `--plain` disable styling |
| Non-interactive use | Typer commands call the same services and print plain results |
| Long operations | Run in the main thread; progress callbacks update `rich.Progress`; Ctrl+C handled once, centrally |

## 8. Third-Party Integration Design

### 8.1 Email / OTP
**Not applicable.** No accounts or email in this product. No SMTP configured.

### 8.2 Payment Gateway (Sandbox)
**Not applicable.** The PDR contains no payment feature.

### 8.3 Hugging Face Hub (model weights, one-time)
- Used only for the first-time download of TTS, VC and emotion-classifier weights into `HF_HOME=/models` (named volume).
- `voxclone system doctor` reports whether each model is cached; `voxclone system fetch-models` performs an explicit download with `HF_HUB_OFFLINE=0`; all normal runs set `HF_HUB_OFFLINE=1`.
- Failure: retry with backoff (3 attempts), then show the manual download hint.

### 8.4 WSLg audio (PulseAudio) for mic and speakers
- Compose mounts `/mnt/wslg` and sets `PULSE_SERVER=unix:/mnt/wslg/PulseServer`.
- `sounddevice` (PortAudio) opens the default devices through Pulse.
- `doctor` opens a 0.2 s test stream in each direction; failures are reported with `VX-401`/`VX-402` and the feature falls back to file-only operation.

## 9. Infrastructure & DevOps

### 9.1 Docker setup
- **Base image:** `python:3.11-slim`; system packages `ffmpeg libsndfile1 libportaudio2 pulseaudio-utils git`.
- **Torch:** installed via the voice-engine package's resolved CUDA wheels; the exact version is pinned in `requirements.lock` after the M0 build.
- **User:** non-root `voxclone`.
- **Env defaults in image:** `HF_HOME=/models`, `PYTHONUNBUFFERED=1`, `VOXCLONE_DATA_DIR=/app/data`.
- **Compose (runtime):** GPU reservation (`driver: nvidia, count: all, capabilities: [gpu]`), `stdin_open: true`, `tty: true`, `shm_size: "2gb"`, volumes `hf_models:/models`, `./profiles`, `./outputs`, `./inputs`, `./data`, `/mnt/wslg:/mnt/wslg`. **No CPU limit** is set, so all cores are available to the worker pool.
- **Compose (test):** `docker-compose.test.yml` with no GPU, `network_mode: none`, fake engines.

### 9.2 Local development environment
Windows (current NVIDIA driver with WSL2 CUDA support) → WSL2 Ubuntu → Docker Engine + NVIDIA Container Toolkit. Memory for WSL set in `%UserProfile%\.wslconfig` (`memory=8GB` minimum **[DEFAULT]**, higher if available). Source mounted into the container for live editing in dev (`docker-compose.dev.yml`).

### 9.3 CI/CD [DEFAULT]
No hosted service required. A `Makefile` is the pipeline: `make lint` → `make typecheck` → `make test` → `make build`. Optionally a GitHub Actions workflow runs the same targets on CPU with fake engines. GPU tests are opt-in (`make test-gpu`).

## 10. Testing Strategy

**Philosophy:** offline-first. All automated tests run inside an isolated Docker container **with no network and no GPU**, using fake engines. Real-model tests are opt-in.

| Level | What | How |
|---|---|---|
| **Unit** | Silence-aware splitter (synthetic tone + silence signals: cuts land in gaps; chunk lengths in 3-5 s; tail merge), crossfade (length and continuity), loudness match, sentence splitter, emotion mapping table, sample validator, name validation, settings store | `pytest`; synthetic numpy audio; no models |
| **Unit** | `ModelManager` invariants: never >1 resident; unload before load; reuse when same key; OOM path | `FakeEngine` that allocates a tracked object and records order |
| **Integration** | `recording_pipeline` and `text_pipeline` with `FakeVC`/`FakeTTS`/`FakeEmotion` (deterministic outputs); SQLite migrations; resume after simulated crash; worker pool with `spawn` | `pytest`, temp data dir |
| **E2E** | Drive the interactive menu end to end (enroll → speak → convert → output) | `pexpect` against `voxclone` with fake engines enabled by `VOXCLONE_ENGINE=fake` |
| **GPU smoke (opt-in)** | One real TTS call, one real VC call, load/unload ×10 memory-return check, benchmark vs. targets | `pytest -m gpu`, run via `make test-gpu` |
| **Static** | `ruff`, `black --check`, `mypy --strict` | in `make lint` / `make typecheck` |

**Coverage target:** ≥ 85 % lines on `voxclone/` excluding `engines/real_*.py`.

## 11. Business Logic Algorithms

| Job | Trigger | Logic |
|---|---|---|
| **Startup sweep** | Every app start | Delete `work/<job_id>/` directories older than 24 h whose job is `succeeded`/`failed`/`cancelled` ≥ 24 h ago; mark stale `running` jobs (no process alive) as `failed` with `VX-500 interrupted`, resumable |
| **Work cleanup on success** | End of a successful job | Delete chunk files; delete `job_chunks` rows older than 30 days **[DEFAULT]** at the next sweep |
| **Model-event retention** | Startup sweep | Delete `model_events` older than 90 days **[DEFAULT]** |
| **Output retention** | None by default | Outputs are kept until the user deletes them; `System > Storage` shows size |
| **Profile quality scoring** | On enroll | Heuristic 0-1 from RMS level, clipping ratio, estimated noise floor (energy of the quietest 10 % of frames vs. speech), duration vs. 20-30 s target |
| **Worker count** | Each job | `workers = settings.workers or os.cpu_count()`, then capped so `workers × 250 MB ≤ available RAM − 2 GB` **[DEFAULT estimate, tune in M5]** |

## 12. Error Handling & Logging

### 12.1 Log format
JSON Lines to `data/logs/voxclone.log`, rotating 5 MB × 5 files.
```json
{"ts":"2026-10-25T10:15:30.123Z","level":"INFO","logger":"voxclone.pipelines.recording","job_id":"…","event":"chunk_converted","chunk":7,"of":42,"ms":812}
```

### 12.2 Levels
| Level | Use |
|---|---|
| DEBUG | Chunk boundaries, worker timings (off by default) |
| INFO | Job lifecycle, model load/unload with VRAM, settings changes |
| WARNING | Low-quality sample, audio device missing, fallback taken |
| ERROR | Job failure, retry exhausted |
| CRITICAL | Database unusable, cannot create data dir |

### 12.3 User-facing messages and codes
Format: `✖ <what happened> (VX-xxx)` then `→ <what to do>`. Never show a traceback unless `--debug`.

| Code | Meaning | Hint |
|---|---|---|
| VX-101 | Sample too short or mostly silent | Record 20-30 s of clear speech |
| VX-102 | Unsupported or corrupt audio file | Convert to wav and retry |
| VX-103 | Consent not confirmed | Confirm you own or have permission for this voice |
| VX-201 | Text empty or too long | Shorten or split input |
| VX-210 | No speech detected in input | Check the file or microphone |
| VX-300 | Not enough GPU memory for model | Close GPU apps; run Free GPU memory |
| VX-301 | Out of memory during a chunk | Resume the job; lower chunk length |
| VX-302 | GPU not available | Run Doctor; CPU mode is much slower |
| VX-310 | Model weights missing | Run `system fetch-models` while online |
| VX-401 | Microphone unavailable | Run Doctor; use a file instead |
| VX-402 | Speaker unavailable | Output was saved; play it from Windows |
| VX-500 | Job interrupted | Choose Resume |
| VX-900 | Unexpected internal error | See log file path shown |

## 13. Operational Runbook

```bash
# One-time (Windows host): install NVIDIA driver with WSL2 support; in WSL:
#   install Docker Engine + NVIDIA Container Toolkit, then verify GPU in a container:
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi

# Build and start the app (menu opens at launch)
git clone <repo> voxclone && cd voxclone
cp .env.example .env
docker compose build
docker compose run --rm voxclone

# One-time model download (needs network)
docker compose run --rm -e HF_HUB_OFFLINE=0 voxclone voxclone system fetch-models

# Migrations (also run automatically at startup)
docker compose run --rm voxclone voxclone system migrate

# Tests (offline, no GPU)
docker compose -f docker-compose.test.yml run --rm tests make test

# Lint and type check
make lint && make typecheck

# Opt-in GPU tests and benchmark
docker compose run --rm voxclone pytest -m gpu
docker compose run --rm voxclone voxclone bench
```

## 14. Technical Dependencies & Licenses

> Licenses are from general knowledge; **verify each at pin time** and record the result in `LICENSES.md`.

| Package / asset | Purpose | License (verify) |
|---|---|---|
| Python 3.11 | Runtime | PSF |
| chatterbox-tts | TTS and voice-conversion engines | MIT (verify weights license) |
| PyTorch | Deep learning runtime | BSD-3-Clause |
| transformers | Emotion classifier loading | Apache-2.0 |
| `j-hartmann/emotion-english-distilroberta-base` (weights) | Emotion labels | verify before use |
| numpy | Arrays | BSD-3-Clause |
| librosa | DSP | ISC |
| soundfile | WAV IO | BSD-3-Clause |
| sounddevice | Mic/speaker | MIT |
| questionary | Dropdown menus | MIT |
| rich | Terminal rendering | MIT |
| typer | Sub-commands | MIT |
| pytest, pexpect | Testing | MIT, ISC |
| ruff, black, mypy | Quality tools | MIT, MIT, MIT |
| pip-tools | Lockfile | BSD-3-Clause |
| Docker, NVIDIA Container Toolkit | Containers | Apache-2.0 |

No JavaScript libraries are used.

## 15. Open Issues & Decisions Pending

1. **Emotion mapping calibration:** the table in 3.8 is an initial guess; tune by listening in M3.
2. **Chunk length vs. quality:** 3-5 s is the requirement; verify in M4 whether voice consistency is better at the upper end, and whether a short context overlap improves joins.
3. **Precision / VRAM:** test half-precision loading to cut VRAM and time; decide in M5.
4. **WSL RAM:** the PDR says 8 GB usable; confirm `.wslconfig`. If only 8 GB total is available to WSL, the worker-count RAM cap in section 11 becomes the limiting factor.
5. **Output watermark:** confirm whether the engine embeds one and document it (PDR R8).
6. **Multi-language:** engine support is unconfirmed; out of scope until verified.
7. **Weight and model licenses:** verify for any non-personal use.
8. **Paused live mode:** a design spike in M6 should decide whether a streaming-capable conversion model fits the 8 GB budget while the other models are unloaded.

## 16. Appendix: Environment Variable Reference

```dotenv
# ---- Core paths ----
VOXCLONE_DATA_DIR=/app/data
VOXCLONE_PROFILES_DIR=/app/profiles
VOXCLONE_OUTPUTS_DIR=/app/outputs
VOXCLONE_WORK_DIR=/app/data/work

# ---- Runtime ----
VOXCLONE_DEVICE=auto            # auto | cuda | cpu
VOXCLONE_ENGINE=real            # real | fake (tests)
VOXCLONE_LOG_LEVEL=INFO         # DEBUG | INFO | WARNING | ERROR
VOXCLONE_WORKERS=0              # 0 = all CPU cores
VOXCLONE_VRAM_BUDGET_MB=7000
VOXCLONE_KEEP_WARM=true

# ---- Audio pipeline ----
VOXCLONE_CHUNK_MIN_SEC=3.0
VOXCLONE_CHUNK_MAX_SEC=5.0
VOXCLONE_CROSSFADE_MS=30
VOXCLONE_SENTENCE_MAX_CHARS=200

# ---- Safety ----
VOXCLONE_REQUIRE_CONSENT=1      # must stay 1

# ---- Model cache / network ----
HF_HOME=/models
HF_HUB_OFFLINE=1                # set to 0 only for system fetch-models

# ---- Audio devices (WSLg) ----
PULSE_SERVER=unix:/mnt/wslg/PulseServer

# ---- UI ----
NO_COLOR=                       # set to any value to disable color
```
