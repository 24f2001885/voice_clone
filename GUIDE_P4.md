# Phase 4 Developer Runbook & Operational Guide: Recording to Voice (Chunked Parallel)

## 1. System & Toolchain Dependencies

### 1.1 Runtime & Hardware Requirements
* **Python Runtime:** Python 3.11, 3.12, or 3.13.
* **Audio & Compute Toolchain:** `librosa`, `soundfile`, `numpy`, `scipy`, `concurrent.futures`, `multiprocessing`.
* **Hardware Profiles Supported:**
  * **Profile A (NVIDIA GPU / 8 GB vGPU):** PyTorch CUDA 12.x passthrough, `VOXCLONE_VRAM_BUDGET_MB=6000`, `VOXCLONE_DEVICE=auto` or `cuda`. Sequential GPU conversion with peak VRAM bounded under 2.2 GB.
  * **Profile B (AMD Radeon APU / CPU Fallback):** Ryzen APU / Intel iGPU, `VOXCLONE_DEVICE=cpu`, `docker-compose.cpu.yml`. Slices audio into chunks and executes CPU workers across all cores with zero CUDA crash.
  * **Profile C (Hybrid Google Drive Queue):** Local machine runs silence-aware splitting, CPU normalization, and crossfade joining, while neural acoustic conversion is queued via Google Drive to a free Google Colab NVIDIA T4 GPU worker (`VOXCLONE_BACKEND=remote_drive`).

### 1.2 Environment Variables Configuration
Ensure your local `.env` file defines:

```dotenv
# ==============================================================================
# VoxClone Phase 4 Operational Configuration (.env)
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

# Chunking & Parallel Execution Tunables (TDR Sections 3.1-3.6)
VOXCLONE_CHUNK_MIN_SEC=3.0
VOXCLONE_CHUNK_MAX_SEC=5.0
VOXCLONE_CHUNK_TAIL_MIN_SEC=1.0
VOXCLONE_CROSSFADE_MS=30
VOXCLONE_WORKERS=0  # 0 = auto-detect based on CPU cores and RAM budget

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

### 2.1 Neural Architecture: Zero-Shot Voice Conversion (OpenVoice V2 / Chatterbox)
* **Model Key:** `vc`
* **VRAM Footprint:** ~1,800 MB (fits comfortably within 6,000 MB operating envelope).
* **Sequential GPU Consumer Model:** The neural model is instantiated once on GPU/CPU. Chunks are converted sequentially to keep memory usage deterministic.
* **All-Core CPU Parallelism:** Audio decoding, stereo-to-mono downmix, peak normalization, DC bias removal, and post-conversion RMS loudness matching run in parallel across CPU cores using Python's `spawn` multiprocessing context.
* **Deterministic Offline Testing:** Fully verified offline using `FakeVc` test double which preserves exact input chunk durations and produces clean harmonic tones without model weights.

### 2.2 Slicing & Seam-Hiding Algorithm (TDR Section 3.3 & 3.4)
1. **Silence-Aware Cut-Point Search:** Audio is scanned with 20 ms RMS energy frames. Chunks are cut at the minimum-energy point between 3.0 s and 5.0 s to prevent mid-phoneme clipping artifacts.
2. **Tail Merge Policy:** If the final remaining chunk is $< 1.0\text{ s}$ (`CHUNK_TAIL_MIN_SEC`), it is merged into the previous chunk instead of emitting an undersized chunk.
3. **Equal-Power Crossfade:** Converted chunks are assembled using an equal-power crossfade of 30 ms at boundaries, guaranteeing zero audible clicks or seams.

### 2.3 Downloading Production Weights
To pull real neural weights for local GPU/CPU execution:
```bash
# Option A: Built-in fetcher
voxclone system fetch-models

# Option B: Hugging Face CLI
huggingface-cli download myshell-ai/OpenVoiceV2 --local-dir /models/vc --local-dir-use-symlinks False
```

---

## 3. Database & Storage Architecture

### 3.1 Active SQLite Tables in Phase 4
* `job_chunks`: Records temporal chunk boundaries (`start_sec`, `end_sec`), processing statuses (`pending`, `prepared`, `converted`), retry attempts, and chunk file paths (`input_path`, `output_path`).
* `jobs`: Records job metadata, input source file, output mode, execution elapsed time, and real-time factor (RTF).
* `voice_profiles`: Provides consenting speaker reference audio.
* `model_events`: Records VC model load/unload operations.

---

## 4. Execution Script Walkthrough (`P4.sh`)

Running `bash P4.sh` automates the Phase 4 pipeline:
1. Verifies git milestone branch `milestone/p4-recording-to-voice`.
2. Scaffolds pipeline, worker, and test directories.
3. Confirms SQLite schema and applies pending migrations.
4. Executes the automated test suite (`tests/unit` and `tests/integration`).

---

## 5. Validation & Test Execution

Run the complete Phase 4 test suite:

```bash
# In WSL or bash:
python -m pytest tests/unit/test_splitter.py tests/unit/test_dsp_workers.py tests/integration/test_parallel_pool.py tests/integration/test_recording_pipeline.py -v

# Or run full offline test suite:
python -m pytest tests/unit tests/integration -v -m "not gpu"
```

* **Acceptance Sign-off Criteria:**
  * All unit and integration tests pass (`119+ passed`).
  * Audio splitter slices long recordings into 3.0–5.0 s chunks at low-energy frames with zero temporal gaps.
  * Tail merge prevents chunks shorter than 1.0 s.
  * CPU DSP pool runs on spawned worker processes without importing PyTorch or blocking CUDA state.
  * Voice conversion converts chunks in strict chronological order and joins them seamlessly with 30 ms equal-power crossfades.
  * Unconsented voice profiles are rejected with `ConsentRequiredError (VX-103)`.
  * Pure silent audio is rejected with `NoSpeechDetectedError (VX-210)`.

---

## 6. Local Interactive Verification

Test voice conversion locally:

```bash
# 1. Convert an audio file using CLI convert command
voxclone convert --profile "TargetSpeaker" --input "sample_speech.wav" --save --plain

# 2. Launch interactive menu
python -m voxclone

# Navigation:
# 1. Select Option 2: "Recording  →  my voice"
# 2. Select enrolled voice profile
# 3. Select input: "Select existing audio file" or "Record speech from microphone now"
# 4. Choose output: "Save to audio file (.wav)"
# 5. Observe S-34 stage panel: Slicing -> Parallel CPU prep -> GPU Neural Conversion -> DSP Loudness Match -> Crossfade Join
# 6. Review S-35 Result Panel (duration, elapsed time, RTF multiple)
```

---

## 7. Operator Action Checklist: Setup, Downloads, Logins & Keys

Follow this comprehensive operator checklist to prepare and verify your workstation for Phase 4:

### Step 1: Hardware & Compute Environment Check
* [ ] Verify hardware acceleration profile:
  * Windows PowerShell:
    ```powershell
    Get-PnpDevice -Class Display | Select-Object FriendlyName, Status, InstanceId
    python -c "import torch; print('CUDA Available:', torch.cuda.is_available())"
    ```
  * **If AMD Radeon(TM) Graphics (VEN_1002):** Set `VOXCLONE_DEVICE=cpu` in `.env`.
  * **If NVIDIA GPU (8 GB vGPU):** Set `VOXCLONE_DEVICE=auto` and `VOXCLONE_VRAM_BUDGET_MB=6000`.

### Step 2: What to Download (Software & Binaries)
* [ ] **Python 3.11–3.13:** Verify with `python --version`.
* [ ] **FFmpeg & libsndfile:**
  * PowerShell: `winget install Gyan.FFmpeg`
  * Linux/WSL: `sudo apt install -y ffmpeg libsndfile1 libportaudio2`
* [ ] **OpenVoice / Chatterbox Weights (Optional for Real Mode):**
  * Target directory: `models/vc` or Hugging Face cache.

### Step 3: Where to Login (Accounts & Portals)
* [ ] **GitHub:** Sign in at [github.com](https://github.com) to synchronize with repository `https://github.com/24f2001885/voice_clone.git`.
* [ ] **Hugging Face:** Sign in at [huggingface.co](https://huggingface.co) if downloading gated models.
* [ ] **Google Colab (for Hybrid Mode):** Sign in to Google Drive and [colab.research.google.com](https://colab.research.google.com).

### Step 4: What Keys & Tokens to Bring
* [ ] **Hugging Face Read Token (`HF_TOKEN`):**
  * Add to `.env`:
    ```dotenv
    HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    ```
* [ ] **GitHub Personal Access Token:**
  * Ensure Git credential helper is active:
    ```bash
    git config --global credential.helper store
    ```
* [ ] **Google Drive Queue Path (for Hybrid Mode):**
  * Add to `.env`:
    ```dotenv
    VOXCLONE_BACKEND=remote_drive
    VOXCLONE_DRIVE_DIR=G:/My Drive/voxclone_queue
    ```

### Step 5: What to Check (Pre-Flight Validations)
| Check Item | Command | Expected Output | Remediation if Failing |
|---|---|---|---|
| **Audio Chunk Splitter** | `python -m pytest tests/unit/test_splitter.py -v` | All tests `PASSED` | Inspect `voxclone/audio/splitter.py` |
| **CPU DSP Workers** | `python -m pytest tests/unit/test_dsp_workers.py -v` | All tests `PASSED` | Verify `numpy` and `soundfile` installation |
| **Spawn Parallel Pool** | `python -m pytest tests/integration/test_parallel_pool.py -v` | All tests `PASSED` | Inspect `voxclone/audio/parallel.py` |
| **Voice Conversion Pipeline** | `python -m pytest tests/integration/test_recording_pipeline.py -v` | All tests `PASSED` | Check SQLite job/chunks tables |
| **CLI Convert Command** | `voxclone convert --help` | Shows `--profile`, `--input`, etc. | Verify `voxclone/cli.py` |
| **Full Offline Suite** | `python -m pytest -q` | `119 passed` | Run `pytest -v` to inspect failing assertions |

### Step 6: Execute Phase P4 Automation & Milestone Sign-off
```bash
# Run the automated Phase P4 test runner
bash P4.sh
```
* **Sign-off Criteria:** All unit and integration tests report green (119+ passed).
