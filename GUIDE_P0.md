# Milestone P0: Foundation & Environment Setup
## Developer Runbook & Operational Guide

---

### 1. System & Toolchain Dependencies

#### 1.1 Host & Container Requirements
VoxClone CLI is designed for **single-user, local execution** within Docker on WSL2 (Windows Subsystem for Linux 2) with NVIDIA GPU passthrough and WSLg audio support.

- **Operating System:** Windows 10/11 with WSL2 enabled (Ubuntu 22.04+ or Debian-based Linux distribution).
- **Runtime:** Python 3.11 (inside Docker container).
- **Containerization:** Docker Engine 24+ and Docker Compose v2 with NVIDIA Container Toolkit (`nvidia-container-toolkit`) installed on the host.
- **System Packages (Linux / Container):**
  - `ffmpeg` (audio decoding and format transcoding)
  - `libsndfile1` (PCM audio file I/O for `soundfile`)
  - `libportaudio2` (low-latency audio streaming for `sounddevice`)
  - `pulseaudio-utils` (WSLg PulseAudio socket interop)
  - `git` (version tracking and model repo checkpoints)
- **Host Audio:** WSLg PulseAudio UNIX domain socket located at `/mnt/wslg/PulseServer`.

#### 1.2 Environment Variables & `.env.example`
The system is configured via environment variables prefixed with `VOXCLONE_`. Tunable settings stored in SQLite (`app_settings` table) can be strictly overridden by environment variables; when an environment variable is present, the setting is marked as **locked** in the UI.

```bash
# ==============================================================================
# VoxClone CLI Environment Configuration (.env)
# ==============================================================================

# Directory Paths
VOXCLONE_DATA_DIR=/app/data
VOXCLONE_PROFILES_DIR=/app/profiles
VOXCLONE_OUTPUTS_DIR=/app/outputs
VOXCLONE_INPUTS_DIR=/app/inputs
VOXCLONE_WORK_DIR=/app/data/work

# Engine & Execution Mode
# Options: "real" (requires PyTorch & HuggingFace weights) | "fake" (offline deterministic test doubles)
VOXCLONE_ENGINE=real

# Logging Level: DEBUG, INFO, WARNING, ERROR, CRITICAL
VOXCLONE_LOG_LEVEL=INFO

# Speaker Consent Enforcement (Immutable safety gate: must be 1)
VOXCLONE_REQUIRE_CONSENT=1

# Display Modes (set to 1 to enable ASCII / monochrome fallbacks)
# VOXCLONE_PLAIN=0
# NO_COLOR=0

# Hugging Face Cache & Offline Execution
HF_HOME=/models
HF_HUB_OFFLINE=1

# Audio Socket (WSLg PulseAudio server)
PULSE_SERVER=unix:/mnt/wslg/PulseServer

# ------------------------------------------------------------------------------
# Tunable Engine Parameters (Overrides database settings in `app_settings` table)
# Uncommenting any variable below locks its value against UI modifications.
# ------------------------------------------------------------------------------
# VOXCLONE_DEVICE=auto
# VOXCLONE_WORKERS=0
# VOXCLONE_VRAM_BUDGET_MB=6000
# VOXCLONE_KEEP_WARM=1
# VOXCLONE_CHUNK_MIN_SEC=3.0
# VOXCLONE_CHUNK_MAX_SEC=5.0
# VOXCLONE_CROSSFADE_MS=30
# VOXCLONE_SENTENCE_MAX_CHARS=200
```

---

### 2. Model, Weights & Static Asset Provisioning

#### 2.1 Hardware Sizing & Memory Limits
VoxClone is engineered for modest hardware budgets:
- **System RAM:** 8 GB allocatable in WSL2 (`.wslconfig` setting `memory=8GB`).
- **GPU VRAM:** 8 GB dedicated NVIDIA VRAM (e.g., RTX 3070/4060 laptop).
- **VRAM Operating Ceiling:** 6,000 MB allocated budget (`VOXCLONE_VRAM_BUDGET_MB=6000`), leaving at least 2,000 MB headroom for OS/WSL display overhead.

#### 2.2 Model Architecture & Offline Test Strategy
- In **Phase P0**, no heavy AI model weights are loaded into memory. The application initializes the core infrastructure, SQLite schema, logging, configuration, and terminal UI shell.
- Full offline test execution is provided via **deterministic fake engines** (`FakeTts`, `FakeVc`, `FakeEmotion`), which generate synthetic sine waves and mock labels without requiring PyTorch, CUDA, or internet connectivity.
- When `VOXCLONE_ENGINE=real` is specified in subsequent phases (P1–P4), models are stored in the `/models` volume (HuggingFace cache). The model manager guarantees that **at most one AI model resides in VRAM at any time**.

---

### 3. Database & Infrastructure State

#### 3.1 Database Architecture
VoxClone CLI uses **SQLite 3** (`data/voxclone.db`) with:
- `PRAGMA foreign_keys = ON;` (Strict constraint enforcement, cascading deletes on chunk records, nullifying on profile deletes).
- `PRAGMA journal_mode = WAL;` (Write-Ahead Logging for high-concurrency reading during chunk processing).
- Pure parameterized queries (Zero ORM overhead; high security and determinism).

#### 3.2 Migrations Pipeline
Migrations are applied sequentially and idempotently from the `migrations/` directory:
- `001_init.sql`: Creates core tables (`voice_profiles`, `jobs`, `job_chunks`, `model_events`, `app_settings`) and seeds default settings.
- `002_indexes.sql`: Creates performance indexes on timestamps and status fields (`idx_jobs_created_at`, `idx_jobs_status`, `idx_job_chunks_job`, `idx_model_events_created`).
- The `schema_migrations` tracking table records applied migration version numbers and ISO-8601 timestamps.

#### 3.3 Container Orchestration
The project provides three tailored Docker Compose definitions:
1. `docker-compose.yml`: Production runtime container with GPU passthrough (`all` capabilities), shared memory (`shm_size: 2gb`), and persistent volumes (`hf_models`, `./profiles`, `./outputs`, `./inputs`, `./data`).
2. `docker-compose.dev.yml`: Development overlay binding host `./src` and `./tests` for live hot-reloading without image rebuilding.
3. `docker-compose.test.yml`: Isolated offline test container with `network_mode: none`, CPU-only mode, and `VOXCLONE_ENGINE=fake`.

---

### 4. Execution Script Walkthrough (`P0.sh`)

Executing `bash P0.sh` performs the following automated steps:
1. **Repository Setup:** Verifies or initializes a Git repository on branch `main` and checks out the milestone branch `milestone/p0-foundation`.
2. **Directory Structure:** Creates the required hierarchy (`docs/`, `migrations/`, `scripts/`, `src/voxclone/`, `data/`, `profiles/`, `outputs/`, `inputs/`, `tests/unit/`, `tests/integration/`).
3. **Environment & Config:** Generates `.env` from `.env.example` if not present.
4. **Schema Verification & Migrations:** Runs `voxclone system migrate` to initialize SQLite tables and verify schema integrity.
5. **Pre-flight Checks:** Invokes `scripts/doctor.sh` to validate Docker, GPU access, RAM, disk, and audio connectivity.
6. **Automated Testing:** Executes `pytest tests/unit tests/integration -v` using the offline test harness.

---

### 5. Validation & Test Execution

#### 5.1 Test Invocation
Run tests using pytest:
```bash
# Run complete offline unit and integration suite
pytest tests/ -v

# Run unit tests only
pytest tests/unit/ -v

# Run integration tests only
pytest tests/integration/ -v
```

#### 5.2 Criteria for Phase P0 Sign-Off
- `test_errors.py`: All 13 VX error codes validate code formatting, non-empty user messages, and actionable fix hints.
- `test_settings_repo.py`: SQLite key-value settings round-trip typed values (int, float, bool, string), enforce validation bounds, and confirm environment variable lock overrides.
- `test_migrations.py`: Schema migrations apply cleanly, idempotently, enforce foreign keys and CHECK constraints, and prove zero drift against Python constants.
- `scripts/doctor.sh`: Runs without fatal errors on compliant host environments.

---

### 6. Local Verification Checklist

To verify Phase P0 locally:
1. **Inspect CLI Help:**
   ```bash
   python -m voxclone --help
   ```
2. **Execute Database Migrations:**
   ```bash
   python -m voxclone system migrate
   ```
3. **Run System Doctor Diagnostic:**
   ```bash
   python -m voxclone system doctor --plain
   ```
4. **Verify Storage Inspection:**
   ```bash
   python -m voxclone system storage --plain
   ```
5. **Launch Interactive Main Menu:**
   ```bash
   python -m voxclone
   ```
   *Expected behavior:* The terminal displays the boxed header bar with device and VRAM status, followed by the main interactive dropdown menu (S-01). Selecting "Exit" gracefully exits with code 0.
