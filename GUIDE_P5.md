# GUIDE_P5.md - Milestone P5: Jobs, Resume & Performance

## Executive Overview

Milestone **P5 (Jobs, Resume & Performance)** implements robust multi-stage job persistence, crash recovery, pause/resume capability, interactive job history navigation, and performance benchmarking. It ensures zero data loss during process interruption and guarantees that already completed chunks are never re-rendered upon resumption.

---

## 1. System & Toolchain Dependencies

### 1.1 Runtime Requirements
- **Python**: 3.10+ (tested on Python 3.11, 3.12, 3.13 on Linux/WSL2 and Windows)
- **C Compiler / Build Tools**: GCC or MSVC build tools for C-extensions (`soundfile`, `numpy`)
- **System Audio Tools**: `ffmpeg` (for multi-format audio decode/encode) and `libsndfile`
- **Terminal Capabilities**: 256-color UTF-8 terminal (with automatic ASCII fallback when `--plain` or `NO_COLOR=1` is active)

### 1.2 Environment Configuration (`.env`)

Add or verify the following configuration keys in `.env`:

```ini
# ==============================================================================
# VoxClone Phase P5 Environment Configuration
# ==============================================================================

# Core Application Engine Mode (fake, real, remote_drive)
VOXCLONE_ENGINE=fake

# Execution Backend: local or remote_drive (Colab T4 offloading)
VOXCLONE_BACKEND=local

# Compute Device (cpu, cuda, or auto)
VOXCLONE_DEVICE=cpu

# Base Directories
VOXCLONE_DATA_DIR=data
VOXCLONE_WORK_DIR=data/work
VOXCLONE_PROFILES_DIR=data/profiles
VOXCLONE_OUTPUTS_DIR=data/outputs
VOXCLONE_INPUTS_DIR=data/inputs
VOXCLONE_LOGS_DIR=data/logs

# Multiprocessing Worker Pool Size (0 = all available physical cores)
VOXCLONE_CPU_WORKERS=0

# Chunk Duration Bounds (seconds)
VOXCLONE_CHUNK_MIN_SEC=3.0
VOXCLONE_CHUNK_MAX_SEC=5.0

# Startup Sweep Retention Policies
VOXCLONE_CHUNK_RETENTION_DAYS=30
VOXCLONE_LOG_RETENTION_DAYS=90

# Benchmark Configuration
VOXCLONE_BENCHMARK_DURATION=5.0
```

---

## 2. Model, Weights & Static Asset Provisioning

### 2.1 Model Checkpoints
In `VOXCLONE_ENGINE=fake` mode (used for test suites, CI, and CPU dry runs), all model inference is simulated deterministically with zero weights downloads.

In `VOXCLONE_ENGINE=real` mode:
| Model Key | Architecture | Hugging Face Repository | Disk Footprint | Target VRAM / RAM |
| :--- | :--- | :--- | :--- | :--- |
| `tts` | Chatterbox Multilingual | `hexgrad/Kokoro-82M` | ~350 MB | < 2.0 GB |
| `vc` | FreeVC Voice Conversion | `OlaWod/FreeVC` | ~600 MB | < 2.5 GB |
| `emotion` | DistilRoBERTa Emotion | `j-hartmann/emotion-english-distilroberta-base` | ~330 MB | < 1.0 GB |

### 2.2 CLI Verification Command
```bash
# Verify model weight accessibility or download to local Hugging Face cache:
python -m voxclone.cli system fetch-models --plain
```

---

## 3. Database & Infrastructure State

### 3.1 SQLite WAL Schema & Job Tables
P5 leverages the SQLite schema defined in migrations:
- `jobs`: Stores root job metadata, input source path, output destination, status (`pending`, `running`, `done`, `failed`, `cancelled`), `elapsed_sec`, `rtf`, and error codes.
- `job_chunks`: Stores atomic chunk records (`chunk_index`, `start_sec`, `end_sec`, `status`, `stage`, `error_code`).
- `settings`: Key-value configuration overrides with environment variable lock indicators.

### 3.2 Startup Sweep Execution
Upon application startup, `system_service.startup_sweep(conn, config)` executes automatically:
1. Identifies any dangling jobs stuck in `running` status (e.g. from a prior `SIGKILL` or power failure) and marks them `failed` with code `VX-500` and message `Process was interrupted unexpectedly; ready to resume.`
2. Purges stale temporary working directories (`data/work/<job_id>`) older than 24 hours.
3. Prunes audio chunks exceeding `VOXCLONE_CHUNK_RETENTION_DAYS` (default 30 days) and log records exceeding `VOXCLONE_LOG_RETENTION_DAYS` (default 90 days).

---

## 4. Execution Script Walkthrough (`P5.sh`)

`bash P5.sh` automates the milestone verification pipeline:

1. **Branch Verification**: Confirms git branch `milestone/p5-jobs-performance`.
2. **Directory Scaffolding**: Ensures `data/work`, `data/outputs`, `data/profiles`, and `data/logs` exist.
3. **Environment Setup**: Bootstraps `.env` from `.env.example` if absent.
4. **Python Resolution**: Automatically detects `python3`, `python`, or `python.exe` with `pytest` installed.
5. **Schema Verification & Startup Sweep**: Executes `voxclone system migrate` and runs startup sweep checks.
6. **Test Suite Runner**: Executes all 122 unit and integration tests offline:
   ```bash
   pytest tests/unit tests/integration -v -m "not gpu"
   ```

---

## 5. Validation & Test Execution

### 5.1 Invoking Test Suites
```bash
# Run all unit and integration tests (100% offline, deterministic fake engines)
python -m pytest tests/unit tests/integration -v

# Run the specific resume and crash recovery test suite
python -m pytest tests/integration/test_resume.py -vv

# Run the system benchmark CLI command
python -m voxclone.cli system benchmark --duration 2.0 --plain
```

### 5.2 Interactive Screens Verified in P5
- **S-40 (`Job History`)**: Browse past text-to-voice and recording-to-voice conversions with status badges, timestamps, and real-time factors.
- **S-41 (`Job Detail`)**: Deep dive into job chunk status, output file paths, and actionable buttons (`Resume`, `Replay Audio`, `Delete`).
- **S-42 (`Resume Job`)**: Resumes interrupted or failed jobs without recomputing finished chunks.
- **S-43 (`Delete Job`)**: Safely removes job records with optional output WAV file deletion.
- **S-54 (`Settings Overview`)** & **S-55 (`Edit Setting`)**: Live system configuration management with range validation.

---

## 6. Hardware Profile & Hybrid Remote Execution

For systems with integrated GPUs (such as AMD Ryzen APU with integrated `AMD Radeon(TM) Graphics` / `VEN_1002&DEV_164C`):
- **Local Testing & DSP**: Fast CPU execution using `VOXCLONE_DEVICE=cpu` and `VOXCLONE_ENGINE=fake`.
- **Hybrid Remote GPU**: Offload heavy neural synthesis to Google Colab T4 GPU via Google Drive queue (`VOXCLONE_BACKEND=remote_drive`). The Colab worker picks up chunk manifests from Google Drive and uploads synthesized WAVs back.

---

## 7. Operator Action Checklist

> [!IMPORTANT]
> Follow this exact step-by-step checklist to prepare, verify, and operate Phase P5 on your system.

### 7.1 What to Download
- [x] **Repository Code**: Cloned from `https://github.com/24f2001885/voice_clone.git`.
- [x] **Python 3.10+**: Ensure Python is installed and accessible from terminal or WSL.
- [x] **FFmpeg Executable**:
  - Windows: Download `ffmpeg-release-essentials.zip` from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) or install via `winget install Gyan.FFmpeg`.
  - Linux/WSL: `sudo apt update && sudo apt install -y ffmpeg libsndfile1`.

### 7.2 Where to Login
- [x] **GitHub**: Ensure your Git credential helper or SSH key is configured for pushing to `https://github.com/24f2001885/voice_clone.git`.
- [x] **Google Account (Hybrid Remote Mode Only)**: If running neural inference via Colab, log into Google Drive on your local machine and mount Google Drive in your Colab runtime.

### 7.3 What Keys to Bring
- [x] **GitHub Personal Access Token (PAT)**: Required for git push over HTTPS if SSH keys are not enabled.
- [x] **Hugging Face Token (Optional)**: Only needed if downloading gated model checkpoints in `VOXCLONE_ENGINE=real` mode. Not required for offline fake testing.

### 7.4 What to Check
- [x] Verify SQLite database connectivity: `python -m voxclone.cli doctor --plain`.
- [x] Verify active branch: `git status` should show `milestone/p5-jobs-performance`.
- [x] Verify offline tests: `pytest tests/unit tests/integration -v -m "not gpu"`.

### 7.5 Pre-flight Verification Table
| Step | Action Command | Expected Output | Status |
| :--- | :--- | :--- | :--- |
| **1** | `python -m voxclone.cli --version` | `voxclone version 0.1.0` | READY |
| **2** | `python -m voxclone.cli doctor --plain` | All checks pass (`[OK]`) | READY |
| **3** | `python -m pytest tests/integration/test_resume.py -v` | `2 passed` | READY |
| **4** | `python -m voxclone.cli system benchmark --duration 2.0 --plain` | RTF metrics table displayed | READY |
| **5** | `bash P5.sh` | `Milestone P5 Jobs, Resume & Performance: Completed Successfully!` | READY |
