# Phase 1 Developer Runbook & Operational Guide: Model Manager & Voice Profiles

## 1. System & Toolchain Dependencies

### 1.1 Runtime Requirements
* **Python Runtime:** Python 3.11, 3.12, or 3.13.
* **Audio Processing Toolchain:** `libsndfile1`, `libportaudio2`, `ffmpeg` (for multi-format audio decoding/encoding).
* **Deep Learning Framework:** PyTorch >= 2.2.0 with CUDA 12.1 / 12.4 support (or CPU fallback / fake engine test mode).
* **Hardware Profile:** Specifically optimized for an **8 GB vGPU** (e.g., NVIDIA RTX 3070/4060/A2000 or WSL2 virtual GPU pass-through).
  * `VOXCLONE_VRAM_BUDGET_MB=6000` (leaves 2000 MB headroom for Windows/WSL hypervisor display buffering and CUDA context overhead).
  * System Host RAM: Minimum 8 GB RAM.

### 1.2 Environment Variables Configuration
Create or update your local `.env` configuration file:

```dotenv
# ==============================================================================
# VoxClone Phase 1 Operational Environment Configuration
# ==============================================================================

# Hardware Acceleration & Compute Device
# Options: 'auto' (detects CUDA, falls back to CPU), 'cuda' (enforces NVIDIA GPU), 'cpu'
VOXCLONE_DEVICE=auto

# Maximum VRAM Allocation Envelope (in Megabytes)
# CRITICAL FOR 8 GB vGPU: Keep at 6000 MB to prevent CUDA OOM crash
VOXCLONE_VRAM_BUDGET_MB=6000

# Single-Resident Model Retention Policy
# 'true'  -> Holds the last model in memory until a different engine is required (fast)
# 'false' -> Unloads and flushes VRAM immediately upon job completion (minimal memory)
VOXCLONE_KEEP_WARM=true

# Engine Execution Mode: 'real' (PyTorch neural engines) or 'fake' (offline test doubles)
VOXCLONE_ENGINE=real

# Local Model Weights Cache Directory
HF_HOME=/models

# Hugging Face Authentication Token (Mandatory for pulling gated weights)
HF_TOKEN=hf_your_actual_read_token_here

# Audio Storage Directories
VOXCLONE_DATA_DIR=data
VOXCLONE_PROFILES_DIR=data/profiles
VOXCLONE_OUTPUTS_DIR=data/outputs
VOXCLONE_INPUTS_DIR=data/inputs
VOXCLONE_WORK_DIR=data/work

# Safety & Ethical Cloning Policy Gate
# IMMUTABLE: Explicit consent is mandatory to enroll voice profiles (VX-103)
VOXCLONE_REQUIRE_CONSENT=1

# Logging & Terminal Theme
VOXCLONE_LOG_LEVEL=INFO
VOXCLONE_PLAIN=0
NO_COLOR=0
```

---

## 2. Model, Weights & Static Asset Provisioning

VoxClone enforces a **single-resident neural model architecture**. Only one heavyweight model resides in GPU VRAM at any moment:

| Engine Key | Model Architecture | Hugging Face Repository | Estimated VRAM | Role |
| :--- | :--- | :--- | :--- | :--- |
| `tts` | F5-TTS / E2-TTS Diffusion | `SWivid/F5-TTS` | ~3,500 MB | Zero-shot speech synthesis from text |
| `vc` | OpenVoice V2 Tone Converter | `myshell-ai/OpenVoiceV2` | ~2,200 MB | Zero-shot voice conversion from audio |
| `emotion` | DistilRoBERTa Classifier | `j-hartmann/emotion-english-distilroberta-base` | ~600 MB | Sentence-level emotion classification |

### 2.1 Model Download CLI Commands
You can pre-fetch and cache all weights using either the automated VoxClone CLI or standard `huggingface-cli`:

```bash
# Option A: Built-in VoxClone weights verification & fetcher
voxclone system fetch-models

# Option B: Direct Hugging Face CLI snapshot downloads
huggingface-cli download SWivid/F5-TTS --local-dir /models/tts --local-dir-use-symlinks False
huggingface-cli download myshell-ai/OpenVoiceV2 --local-dir /models/vc --local-dir-use-symlinks False
huggingface-cli download j-hartmann/emotion-english-distilroberta-base --local-dir /models/emotion --local-dir-use-symlinks False
```

---

## 3. Database & Storage Architecture

### 3.1 SQLite Tables Active in Phase 1
* `voice_profiles`: Stores registered speaker identity references, sha256 hashes, quality metrics, and mandatory speaker consent timestamps (`consent_confirmed=1`, `consent_confirmed_at`).
* `model_events`: Persistent audit log recording every `load`, `unload`, and `oom` transition with millisecond timings and VRAM deltas.
* `app_settings`: Key-value configuration parameters seeded with vGPU safe defaults (`vram_budget_mb=6000`, `keep_warm=true`).

### 3.2 Executing Migrations
```bash
# Verify and apply pending migrations (001_init.sql, 002_indexes.sql)
voxclone system migrate
```

---

## 4. Execution Script Walkthrough (`P1.sh`)

`bash P1.sh` executes the end-to-end scaffolding and verification pipeline:
1. **Toolchain Inspection:** Verifies Python >= 3.11, SQLite 3, PortAudio, and NVIDIA driver presence.
2. **Directory Scaffolding:** Guarantees `data/profiles`, `data/outputs`, `data/work`, and `data/logs` exist with proper permissions.
3. **Database Migration Sync:** Validates that SQLite schemas (including `voice_profiles` and `model_events`) are cleanly migrated.
4. **Automated Test Suite Execution:** Runs the complete unit and integration test suite (73 tests) in isolated fake engine mode.
5. **Interactive Sanity Test:** Runs CLI health check to verify clean exit codes.

To execute:
```bash
chmod +x P1.sh
./P1.sh
```

---

## 5. Validation & Test Execution

### 5.1 Running the Automated Test Suite
```bash
# Run all unit and integration tests (excluding live GPU hardware tests)
python -m pytest tests/ -v -m "not gpu"

# Run GPU hardware stability test (requires physical NVIDIA vGPU with CUDA)
python -m pytest tests/gpu/ -v -m "gpu"
```

### 5.2 Expected Output & Sign-off Criteria
* All 73 tests in `tests/unit/` and `tests/integration/` must report `PASSED`.
* Zero regressions on database constraints, foreign keys, or traversal protections.
* ModelManager enforces single-resident invariant across all 6 model switching permutations:
  * `tts -> vc`, `vc -> emotion`, `emotion -> tts`, `tts -> emotion`, `emotion -> vc`, `vc -> tts`.
* Voice profile enrollment strictly enforces `ConsentRequiredError` (VX-103) if `--consent` is omitted.

---

## 6. Local Verification Checklist

Execute these verification steps in your terminal to confirm Phase 1 functionality:

```bash
# 1. Inspect System Doctor diagnostics
voxclone system doctor --plain

# 2. Inspect active neural model residency and VRAM budget
voxclone system status --plain

# 3. Enroll a voice profile from reference audio with explicit consent
voxclone profiles enroll --file tests/fixtures/sample_speech.wav --name "TestSpeaker" --consent --plain

# 4. List registered voice profiles
voxclone profiles list --plain

# 5. Verify ethical consent gate rejects unconsented enrollment (expect error VX-103)
voxclone profiles enroll --file tests/fixtures/sample_speech.wav --name "BadSpeaker" --no-consent --plain

# 6. Test manual GPU memory evacuation (S-52)
voxclone system free-gpu --plain
```

---

## 7. Operator Action Checklist: Setup, Downloads, Logins & Keys

Follow this checklist to prepare your environment:

### Step 1: Verify Hardware & vGPU Settings
* [ ] Open terminal and run `nvidia-smi` to confirm NVIDIA GPU driver is functional.
* [ ] Ensure total VRAM is recognized (8192 MB).
* [ ] Confirm `VOXCLONE_VRAM_BUDGET_MB=6000` is configured in your `.env`.

### Step 2: System Audio Libraries Installation
* On Ubuntu / Debian / WSL2:
  ```bash
  sudo apt update
  sudo apt install -y libsndfile1 libportaudio2 libasound2-dev ffmpeg
  ```
* On Windows (native PowerShell):
  * Audio is handled via WASAPI / DirectSound through pre-compiled `sounddevice` and `soundfile` wheels.

### Step 3: Hugging Face Account & Access Token Setup
* [ ] **Where to login:** Navigate to [https://huggingface.co](https://huggingface.co) and sign in (or register).
* [ ] **What key to bring:** Go to **Settings -> Access Tokens** ([https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)).
* [ ] Generate a new **Read** token (named e.g. `voxclone-cli`).
* [ ] Copy the token (`hf_...`).
* [ ] Authenticate your local CLI:
  ```bash
  huggingface-cli login --token hf_your_token_here
  ```
  Or export in your environment:
  ```bash
  export HF_TOKEN=hf_your_token_here
  ```

### Step 4: Model Checkpoints Provisioning
* [ ] Pull model checkpoints to local storage (`/models` or `./models`):
  ```bash
  voxclone system fetch-models
  ```
  Or pull manually via `huggingface-cli download`:
  * F5-TTS: `SWivid/F5-TTS`
  * OpenVoice V2: `myshell-ai/OpenVoiceV2`
  * DistilRoBERTa Emotion: `j-hartmann/emotion-english-distilroberta-base`

### Step 5: Run Phase 1 Automation & Sign-off
* [ ] Execute `./P1.sh`.
* [ ] Verify all 73 automated tests report green.
