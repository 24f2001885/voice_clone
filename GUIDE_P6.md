# GUIDE_P6.md - Milestone P6: Hardening & Release

## Executive Overview

Milestone **P6 (Hardening & Release)** marks the production hardening, full test suite unification (unit, integration, and end-to-end), error recovery screen (S-57), accessibility contrast validation, and documentation release for VoxClone CLI `v1.0`.

---

## 1. System & Toolchain Dependencies

### 1.1 Runtime Environment
- **Operating System**: Windows 10/11, Ubuntu 22.04+, Debian 12+, or WSL2.
- **Python**: 3.10+ (tested through 3.13).
- **Audio Subsystem**: `ffmpeg` (installed and available on system PATH) and `libsndfile1`.
- **Packaging Tools**: `pip`, `wheel`, and `setuptools`.

### 1.2 Environment Variables (`.env`)

```ini
# ==============================================================================
# VoxClone Phase P6 Production Environment Configuration
# ==============================================================================

# Core Application Engine Mode (fake, real, remote_drive)
VOXCLONE_ENGINE=fake

# Execution Backend: local or remote_drive (Colab T4 offloading)
VOXCLONE_BACKEND=local

# Compute Device (cpu, cuda, or auto)
VOXCLONE_DEVICE=cpu

# Base Directory Paths
VOXCLONE_DATA_DIR=data
VOXCLONE_WORK_DIR=data/work
VOXCLONE_PROFILES_DIR=data/profiles
VOXCLONE_OUTPUTS_DIR=data/outputs
VOXCLONE_INPUTS_DIR=data/inputs
VOXCLONE_LOGS_DIR=data/logs

# Multiprocessing Worker Pool Size (0 = all physical CPU cores)
VOXCLONE_CPU_WORKERS=0

# Silence-Aware Audio Splitting Bounds (seconds)
VOXCLONE_CHUNK_MIN_SEC=3.0
VOXCLONE_CHUNK_MAX_SEC=5.0

# Ethical Safeguards (strictly immutable)
VOXCLONE_REQUIRE_CONSENT=1

# Terminal Rendering Preferences
VOXCLONE_PLAIN=0
NO_COLOR=0
```

---

## 2. Model, Weights & Static Asset Provisioning

### 2.1 Supported Weights
| Model | Identifier | Purpose | Default Footprint |
| :--- | :--- | :--- | :--- |
| **TTS** | `hexgrad/Kokoro-82M` | Text-to-speech synthesis | ~350 MB |
| **VC** | `OlaWod/FreeVC` | Voice conversion | ~600 MB |
| **Emotion** | `j-hartmann/emotion-english-distilroberta-base` | Text emotion classification | ~330 MB |

### 2.2 Model Verification Command
```bash
python -m voxclone.cli system fetch-models --plain
```

---

## 3. Database & Infrastructure State

### 3.1 SQLite WAL Production Mode
- WAL (Write-Ahead Logging) mode is activated on every database connection with a 5000 ms busy timeout.
- Foreign key constraints are enforced on all tables (`profiles`, `jobs`, `job_chunks`, `model_events`, `settings`).
- Cascade deletion guarantees that removing a job removes all associated chunk metadata.

### 3.2 Automated Startup Sweep
On application start, any dangling jobs from previous process terminations are updated to `failed` with code `VX-500`, temporary folders older than 24 hours are cleared, and retention policies are applied.

---

## 4. Execution Script Walkthrough (`P6.sh`)

`bash P6.sh` performs end-to-end milestone verification:

1. **Branch Verification**: Confirms git branch `milestone/p6-hardening-release`.
2. **Directory Scaffolding**: Verifies presence of `data/`, `docs/`, `tests/`.
3. **Environment Configuration**: Copies `.env.example` to `.env` if missing.
4. **Python Resolution**: Automatically detects `python3`, `python`, or `python.exe`.
5. **Database Migration & Doctor Diagnostics**: Verifies SQLite schema and performs complete system health check.
6. **Full Test Suite Execution**: Executes all unit, integration, and e2e tests offline:
   ```bash
   pytest tests/unit tests/integration tests/e2e -v -m "not gpu"
   ```

---

## 5. Validation & Test Execution

### 5.1 Invoking Test Suites
```bash
# Run unit tests
python -m pytest tests/unit -v

# Run integration tests
python -m pytest tests/integration -v

# Run end-to-end interactive CLI tests
python -m pytest tests/e2e -v

# Run complete test suite with coverage audit
python -m pytest tests/ --cov=src/voxclone --cov-report=term-missing --cov-fail-under=85 -m "not gpu"
```

### 5.2 Release Artifacts Verified
- **Screen S-57 (`Error Panel`)**: Full VX error recovery panel with dynamic actions ("Resume job", "Free GPU memory then resume", "Open Doctor", "Show how to download models", "Show log file path").
- **Documentation**:
  - `README.md`: Complete user and developer documentation.
  - `LICENSES.md`: Comprehensive dependency and model weight license verification.
  - `docs/TESTING_GUIDE.md`: Guide for unit, integration, e2e, and opt-in GPU testing.
  - `docs/RECORDING_TIPS.md`: Acoustic room setup and quality metrics guide.
  - `docs/LIVE_MODE_SPIKE.md`: Architectural spike document for paused low-latency live conversion.

---

## 6. Hardware Adaptation: AMD Radeon APU / CPU Execution

For users with integrated graphics (e.g. AMD Ryzen APU with integrated `AMD Radeon(TM) Graphics` / `VEN_1002&DEV_164C`):
- All local processing, DSP, audio validation, chunking, and deterministic fake testing execute on the CPU.
- Real model synthesis can be offloaded seamlessly via the decoupled Google Colab T4 GPU backend (`VOXCLONE_BACKEND=remote_drive`).

---

## 7. Operator Action Checklist

> [!IMPORTANT]
> Follow this exact step-by-step checklist to finalize and operate Phase P6 on your system.

### 7.1 What to Download
- [x] **Repository Code**: Verified on branch `milestone/p6-hardening-release`.
- [x] **Python 3.10+**: Verified installed and functional.
- [x] **FFmpeg Executable**:
  - Windows: Verify `ffmpeg.exe` is in PATH (`ffmpeg -version`).
  - Linux/WSL: `sudo apt install -y ffmpeg libsndfile1`.

### 7.2 Where to Login
- [x] **GitHub**: Ensure Git credentials are authenticated for pushing tags to `https://github.com/24f2001885/voice_clone.git`.
- [x] **Hugging Face (Optional)**: Only needed if authenticating private models; public models require no login.

### 7.3 What Keys to Bring
- [x] **GitHub Personal Access Token (PAT)**: For pushing commits and tags.

### 7.4 What to Check
- [x] Run `python -m voxclone.cli doctor --plain` to verify zero environment warnings.
- [x] Verify all 13 error codes (`VX-101`..`VX-900`) in `tests/unit/test_errors.py`.
- [x] Verify end-to-end tests: `python -m pytest tests/e2e/ -v`.

### 7.5 Pre-flight Verification Table
| Step | Action Command | Expected Output | Status |
| :--- | :--- | :--- | :--- |
| **1** | `python -m voxclone.cli --version` | `voxclone version 0.1.0` | READY |
| **2** | `python -m voxclone.cli doctor --plain` | All system checks passing (`[OK]`) | READY |
| **3** | `python -m pytest tests/unit/test_errors.py -v` | `17 passed` | READY |
| **4** | `python -m pytest tests/e2e/ -v` | `2 passed` | READY |
| **5** | `bash P6.sh` | `Milestone P6 Hardening & Release: Completed Successfully!` | READY |
| **6** | `git tag v1.0` | Production release tag created | READY |
