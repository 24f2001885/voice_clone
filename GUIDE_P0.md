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

#### 2.1 Hardware Sizing, vGPU (8 GB VRAM) & Memory Limits
VoxClone is engineered specifically for modest hardware budgets and virtualized GPUs:
- **System RAM:** 8 GB allocatable in WSL2 (`.wslconfig` setting `memory=8GB`).
- **GPU / vGPU VRAM:** 8 GB dedicated or virtualized VRAM (e.g., NVIDIA vGPU, GRID slice, Hyper-V GPU-PV, or discrete RTX mobile with 8 GB VRAM).
- **vGPU Compatibility & Architecture:** The system runs smoothly on an 8 GB vGPU because:
  1. The VRAM operating ceiling is locked at 6,000 MB (`VOXCLONE_VRAM_BUDGET_MB=6000`), guaranteeing at least 2,000 MB reserved headroom for host rendering, virtualization layer, and OS display contexts.
  2. The strict **one-resident-model rule** (`ModelManager`) enforces that TTS (~2.8 GB), VC (~3.2 GB), and emotion classifier (~400 MB) are *never* loaded simultaneously.
  3. Chunked DSP divides long audio into 3–5 second slices, bounding inference peak VRAM to under 500 MB per conversion forward pass.
  4. Automatic memory release (`gc.collect()` + `torch.cuda.empty_cache()` + `torch.cuda.synchronize()`) returns memory to baseline after every model transition.
  5. If the vGPU lacks CUDA passthrough or encounters hardware constraints, the CPU fallback mode (`VOXCLONE_DEVICE=cpu`) executes all DSP and synthesis workflows safely.

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

---

### 7. Operator Action Checklist: What to Download, Where to Login, Keys to Bring & Verification Steps

This section provides the exhaustive, step-by-step checklist of everything the human operator must download, configure, register, and verify before proceeding.

#### 7.1 What to Download (Software & Driver Binaries)
1. **NVIDIA Host Drivers:**
   - Download the latest NVIDIA driver for your GPU / vGPU from [nvidia.com/drivers](https://www.nvidia.com/Download/index.aspx).
   - Ensure the driver supports CUDA 12.0+ (driver version >= 525.60 on Linux / Windows).
2. **Docker Desktop with WSL2 Backend:**
   - Download from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/).
   - During installation, enable **"Use WSL 2 instead of Hyper-V"**.
   - In Docker Desktop settings: **General** -> check *Use the WSL 2 based engine*; **Resources** -> **WSL Integration** -> enable integration with your default WSL distro (e.g. Ubuntu).
3. **WSL2 Linux Kernel Update (if on Windows):**
   - In Windows PowerShell (Admin):
     ```powershell
     wsl --update
     ```
4. **NVIDIA Container Toolkit (Host Linux / WSL2):**
   - Configures Docker to access the vGPU:
     ```bash
     curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
     curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
       sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
       sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
     sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
     sudo nvidia-ctk runtime configure --runtime=docker
     ```
5. **Git & Git LFS:**
   - Linux / WSL: `sudo apt-get install -y git git-lfs`
   - Windows: [git-scm.com](https://git-scm.com/)

#### 7.2 Where to Login (Accounts & Registrations)
1. **Hugging Face Account:**
   - Register or sign in at [huggingface.co/join](https://huggingface.co/join).
   - Needed for downloading open model weights (Chatterbox TTS, HuBERT / Voice Conversion, Emotion RoBERTa) in subsequent phases.
2. **GitHub Account:**
   - Login at [github.com](https://github.com/).
   - Ensure you have write access to repository [24f2001885/voice_clone](https://github.com/24f2001885/voice_clone).

#### 7.3 What Keys & Tokens to Bring
1. **Hugging Face User Access Token (`HF_TOKEN`):**
   - Navigate to [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).
   - Create a **Read** token named `voxclone`.
   - Store it safely; in Phase P1+, you will add it to `.env`:
     ```bash
     HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
     ```
2. **GitHub Personal Access Token (PAT):**
   - Navigate to [github.com/settings/tokens](https://github.com/settings/tokens).
   - Generate a classic token or fine-grained token with `repo` scope to push code and sync branches.
   - Configure Git credential caching:
     ```bash
     git config --global credential.helper store
     ```

#### 7.4 What to Check (Pre-Flight Validations)
Run these verification commands in your WSL/Linux terminal:

| Item | Command | Expected Result | What to Do if Failing |
|---|---|---|---|
| **vGPU / GPU Visibility** | `nvidia-smi` | Lists GPU name, driver version, and VRAM (e.g. 8192 MiB) | Update NVIDIA host drivers; enable GPU partitioning in VM |
| **WSL2 RAM Allocation** | `free -m` | Mem Total >= 7,000 MB | Create `%USERPROFILE%\.wslconfig` with `[wsl2]` `memory=8GB`, then run `wsl --shutdown` in PowerShell |
| **WSLg Audio Server** | `ls -la /mnt/wslg/PulseServer` | Socket file exists | Upgrade to Windows 11 Build 22000+; file mode operates without it |
| **Disk Space** | `df -h .` | Avail >= 30 GB | Clean Docker prune or expand virtual hard disk |
| **Docker GPU Access** | `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi` | Outputs GPU table inside container | Restart Docker daemon after installing `nvidia-container-toolkit` |

#### 7.5 Exact Operator Setup Sequence (Copy-Paste)
Execute this sequence to verify your workspace is completely primed:

```bash
# Step 1: Clone or navigate to the repository
cd c:\Users\ACER\Desktop\v1   # (or /mnt/c/Users/ACER/Desktop/v1 in WSL)

# Step 2: Initialize and verify environment
cp -n .env.example .env

# Step 3: Run the automated pre-flight diagnostics
bash scripts/doctor.sh

# Step 4: Run the automated Phase P0 foundation test harness
bash P0.sh

# Step 5: Verify the interactive CLI menu opens cleanly
python -m voxclone
```

