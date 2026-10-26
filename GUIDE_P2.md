# Phase 2 Developer Runbook & Operational Guide: Text to Voice Synthesis

## 1. System & Toolchain Dependencies

### 1.1 Runtime & Hardware Requirements
* **Python Runtime:** Python 3.11, 3.12, or 3.13.
* **Audio Toolchain:** `ffmpeg`, `libsndfile1`, `libportaudio2`, `sounddevice`, `soundfile`, `numpy`.
* **Hardware Profiles Supported:**
  * **Profile A (NVIDIA GPU / 8 GB vGPU):** PyTorch CUDA 12.x passthrough, `VOXCLONE_VRAM_BUDGET_MB=6000`, `VOXCLONE_DEVICE=auto` or `cuda`.
  * **Profile B (AMD Radeon APU / CPU Fallback):** Ryzen APU / Intel iGPU, `VOXCLONE_DEVICE=cpu`, `docker-compose.cpu.yml`. Runs audio DSP and sentence-chunk synthesis with zero GPU errors.
  * **Profile C (Hybrid Google Drive Queue):** Local machine manages UI/DSP while neural inference is queued via Google Drive to a free Google Colab NVIDIA T4 GPU worker (`VOXCLONE_BACKEND=remote_drive`).

### 1.2 Environment Variables Configuration
Ensure your local `.env` file defines:

```dotenv
# ==============================================================================
# VoxClone Phase 2 Operational Configuration (.env)
# ==============================================================================

# Hardware Acceleration & Compute Device
# Options: 'auto' (detects CUDA, falls back to CPU), 'cuda', 'cpu'
VOXCLONE_DEVICE=cpu

# Backend Execution Mode: 'local' or 'remote_drive'
VOXCLONE_BACKEND=local
# VOXCLONE_DRIVE_DIR=G:/My Drive/voxclone_queue

# VRAM Allocation Envelope (Megabytes) - For 8 GB vGPU
VOXCLONE_VRAM_BUDGET_MB=6000

# Single-Resident Model Retention Policy
VOXCLONE_KEEP_WARM=true

# Engine Execution Mode: 'fake' (offline deterministic test doubles) or 'real' (PyTorch)
VOXCLONE_ENGINE=fake

# Text Splitting & Boundary Settings
VOXCLONE_SENTENCE_MAX_CHARS=200
VOXCLONE_CROSSFADE_MS=30

# Audio Storage Directories
VOXCLONE_DATA_DIR=data
VOXCLONE_PROFILES_DIR=data/profiles
VOXCLONE_OUTPUTS_DIR=data/outputs
VOXCLONE_INPUTS_DIR=data/inputs
VOXCLONE_WORK_DIR=data/work

# Safety & Ethical Cloning Gate (Mandatory)
VOXCLONE_REQUIRE_CONSENT=1

# Hugging Face Cache & Token
HF_HOME=/models
HF_HUB_OFFLINE=1
HF_TOKEN=hf_your_read_token_here
```

---

## 2. Model, Weights & Static Asset Provisioning

### 2.1 Neural Architecture: F5-TTS
* **Model ID:** `SWivid/F5-TTS`
* **VRAM Footprint:** ~3,500 MB (fits inside 6,000 MB operating ceiling).
* **Role:** Zero-shot speech synthesis from text conditioned on speaker reference WAV.
* **Offline Development & Testing:** Tested offline using `FakeTts` test double which generates synthetic harmonic tones with exact length matching text character count.

### 2.2 Downloading Checkpoints
To pull production neural weights:
```bash
# Option A: Built-in fetcher
voxclone system fetch-models

# Option B: Hugging Face CLI
huggingface-cli download SWivid/F5-TTS --local-dir /models/tts --local-dir-use-symlinks False
```

---

## 3. Database & Storage Architecture

### 3.1 Active SQLite Tables in Phase 2
* `jobs`: Tracks overall job status (`queued`, `running`, `succeeded`, `failed`, `cancelled`), timings (`started_at`, `finished_at`, `elapsed_ms`), output path, and real-time factor (RTF).
* `job_chunks`: Records individual sentence passages, attempt counts, intermediate statuses (`pending`, `prepared`, `converted`), and error messages.
* `voice_profiles`: Provides consenting speaker reference audio.
* `model_events`: Records TTS model load/unload operations.

---

## 4. Execution Script Walkthrough (`P2.sh`)

Running `bash P2.sh` executes the Phase 2 pipeline:
1. Verifies milestone branch `milestone/p2-text-to-voice`.
2. Scaffolds pipeline and test directories (`src/voxclone/pipelines`, `tests/e2e`).
3. Confirms SQLite schema and applies pending migrations.
4. Executes the automated test suite (`tests/unit` and `tests/integration`).

---

## 5. Validation & Test Execution

Run the complete Phase 2 test suite:

```bash
# In WSL or bash:
python -m pytest tests/unit tests/integration -v -m "not gpu"

# Or in Windows PowerShell:
python -m pytest tests/unit/test_text_splitter.py tests/unit/test_join.py tests/unit/test_jobs_repo.py tests/integration/test_text_pipeline.py -v
```

* **Acceptance Sign-off Criteria:**
  * All unit and integration tests report green (`87+ passed`).
  * Text splitting strictly respects punctuation and character limits.
  * Audio crossfade joining and digital pause insertion produce clean waveforms without audible clicks or sample jumps.
  * Full synthesis flow creates valid WAV audio files in `data/outputs/`.
  * Attempting to synthesize with an unconsented profile raises `ConsentRequiredError (VX-103)`.

---

## 6. Local Interactive Verification

Test the CLI and interactive menu locally:

```bash
# 1. Synthesize text using CLI speak command
voxclone speak --profile "TestSpeaker" --text "Welcome to VoxClone voice synthesis." --save --plain

# 2. Launch the interactive menu
python -m voxclone

# Select option 1: "Text  →  my voice"
# Pick enrolled profile -> Type text -> Select Normal emotion -> Select Save -> View result panel (S-26)
```

---

## 7. Operator Action Checklist: Setup, Downloads, Logins & Keys

Follow this comprehensive operator checklist to prepare and verify your workstation for Phase 2:

### Step 1: Hardware & Compute Environment Check
* [ ] Open terminal and check display hardware:
  * Windows PowerShell:
    ```powershell
    Get-PnpDevice -Class Display | Select-Object FriendlyName, Status, InstanceId
    python -c "import torch; print('CUDA Available:', torch.cuda.is_available())"
    ```
  * **If AMD Radeon(TM) Graphics (VEN_1002):** Set `VOXCLONE_DEVICE=cpu` in `.env`.
  * **If NVIDIA GPU (8 GB vGPU):** Set `VOXCLONE_DEVICE=auto` and `VOXCLONE_VRAM_BUDGET_MB=6000`.

### Step 2: What to Download (Software & Binaries)
* [ ] **Python 3.11–3.13:** Verify installation with `python --version`.
* [ ] **FFmpeg:** Verify FFmpeg is available on PATH:
  * PowerShell: `winget install Gyan.FFmpeg`
  * Linux/WSL: `sudo apt install -y ffmpeg libsndfile1 libportaudio2`
* [ ] **Google Drive for Desktop (Optional, for Hybrid Mode):**
  * Download from [google.com/drive/download](https://www.google.com/drive/download/).
  * Creates synchronized drive letter (e.g. `G:\My Drive\voxclone_queue`).

### Step 3: Where to Login (Accounts & Portals)
* [ ] **GitHub:** Sign in at [github.com](https://github.com) to synchronize with repository `https://github.com/24f2001885/voice_clone.git`.
* [ ] **Hugging Face:** Sign in at [huggingface.co](https://huggingface.co) to generate or copy access token.
* [ ] **Google Account (for Hybrid Mode):** Sign in to Google Drive and Google Colab ([colab.research.google.com](https://colab.research.google.com)).

### Step 4: What Keys & Tokens to Bring
* [ ] **Hugging Face Read Token (`HF_TOKEN`):**
  * Generate a Read token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).
  * Add to `.env`:
    ```dotenv
    HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    ```
* [ ] **GitHub Personal Access Token:**
  * Ensure Git credential helper is active:
    ```bash
    git config --global credential.helper store
    ```
* [ ] **Google Drive Queue Path:**
  * For remote hybrid mode, add to `.env`:
    ```dotenv
    VOXCLONE_BACKEND=remote_drive
    VOXCLONE_DRIVE_DIR=G:/My Drive/voxclone_queue
    ```

### Step 5: What to Check (Pre-Flight Validations)
| Check Item | Command | Expected Output | Remediation if Failing |
|---|---|---|---|
| **Audio I/O & DSP** | `python -c "import numpy, soundfile, librosa; print('DSP ready')"` | `DSP ready` | Run `pip install numpy soundfile librosa` |
| **Speaker Consent Enforcement** | `voxclone speak --profile "Unconsented" --text "Test" --plain` | Exits with error `VX-103` | Verifies safety gate prevents unconsented synthesis |
| **Text Splitting** | `python -c "from voxclone.pipelines.text_splitter import split_text_into_chunks; print(len(split_text_into_chunks('One. Two.')))"` | `2` | Verifies sentence boundaries |
| **Output File Writing** | `python -m pytest tests/integration/test_text_pipeline.py -v` | All tests `PASSED` | Inspect `data/outputs/` directory permissions |

### Step 6: Execute Phase P2 Automation & Milestone Sign-off
```bash
# Run the automated Phase P2 test runner
bash P2.sh
```
* **Sign-off Criteria:** All unit and integration tests report green (87+ passed).
