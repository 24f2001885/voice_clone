# VoxClone CLI - Production Voice Cloning & Speech Synthesis

VoxClone is a production-grade, local-first voice cloning and speech synthesis CLI tool designed for robust operation on consumer hardware, high acoustic fidelity, and zero data loss.

---

## 1. Capabilities & Core Workflows

- **Three Audio Input Paths**: Microphone capture, local audio files (WAV, MP3, FLAC, OGG), or direct text prompts.
- **Two Audio Output Modes**: Live system playback (via default audio device) or saved high-fidelity 24 kHz WAV files.
- **Single-Resident Neural Engine**: Strict invariant maintaining at most one neural network resident in memory at any given time (`TTS`, `VC`, or `Emotion`), allowing operation in low-VRAM environments.
- **Silence-Aware Parallel Splitting**: Long inputs are split at natural silence boundaries into 3–5 second chunks and processed concurrently across CPU workers.
- **Two-Stage Emotion Text Pipeline**: Offline DistilRoBERTa emotion classification unloads before TTS loads, injecting pitch, speed, and energy modulation presets.
- **Deterministic Crash Recovery & Resume**: Job state and chunk status are checkpointed in SQLite WAL. Interrupted jobs resume instantly without re-rendering completed chunks.

---

## 2. System Requirements & Hardware Profiles

| Spec | Minimum (CPU / Fake Mode) | Recommended (Local GPU) | Decoupled Hybrid (AMD APU) |
| :--- | :--- | :--- | :--- |
| **OS** | Windows 10/11, Ubuntu 22.04+, WSL2 | Windows 11 + WSL2 / Linux | Windows 11 + WSL2 |
| **Python** | 3.10 to 3.13 | 3.10 to 3.13 | 3.10 to 3.13 |
| **System RAM** | 8 GB | 16 GB | 16 GB |
| **GPU / VRAM** | None (CPU mode) | NVIDIA GPU (8 GB VRAM) | Integrated AMD Radeon APU |
| **Backend** | `VOXCLONE_BACKEND=local` | `VOXCLONE_BACKEND=local` | `VOXCLONE_BACKEND=remote_drive` |
| **Disk Space** | 5 GB free | 30 GB free (for model weights) | 10 GB free |
| **External Tools** | `ffmpeg` and `libsndfile` | `ffmpeg`, `cuda-toolkit` | `ffmpeg`, Google Drive |

---

## 3. Quick Start & Setup

### 3.1 Clone and Environment Setup
```bash
git clone https://github.com/24f2001885/voice_clone.git
cd voice_clone

# Create environment configuration
cp .env.example .env

# Install dependencies
pip install -r requirements.txt
# Or development mode:
pip install -e .
```

### 3.2 System Health Check (Doctor)
Run the diagnostic suite to verify SQLite WAL, audio devices, compute hardware, and directories:
```bash
python -m voxclone.cli doctor --plain
```

### 3.3 Interactive Terminal UI
Launch the interactive dropdown menu:
```bash
python -m voxclone.cli
```

---

## 4. Command Reference

| Command | Arguments / Flags | Description |
| :--- | :--- | :--- |
| `voxclone` | `[--plain] [--debug]` | Launch the main interactive menu |
| `voxclone doctor` | `[--plain]` | Run end-to-end environment diagnostics |
| `voxclone profiles list` | `[--plain]` | List all registered voice profiles |
| `voxclone profiles enroll` | `--file <path> --name <name> --consent` | Enroll voice profile with consent gate |
| `voxclone profiles delete` | `--name <name>` | Delete profile and reference audio |
| `voxclone profiles rename` | `--old <name> --new <name>` | Rename an existing voice profile |
| `voxclone speak` | `--profile <name> --text <text> [--emotion <emo>] [--save]` | Synthesize text to speech |
| `voxclone convert` | `--profile <name> --input <path> [--save]` | Convert audio recording to target voice |
| `voxclone system status` | `[--plain]` | Inspect active model residency & VRAM |
| `voxclone system free-gpu` | `[--plain]` | Explicitly unload resident model from VRAM |
| `voxclone system benchmark`| `[--duration <sec>] [--plain]` | Run audio throughput and RTF benchmark |
| `voxclone system fetch-models`| `[--key <tts\|vc\|emotion>]` | Download Hugging Face model checkpoints |
| `voxclone system migrate` | `[--plain]` | Apply pending database schema migrations |

---

## 5. System Configuration & Settings Reference

Settings can be managed dynamically via `voxclone` UI (Screens S-54 / S-55) or configured via environment variables:

| Setting Key | Default | Allowed Values | Description |
| :--- | :--- | :--- | :--- |
| `cpu_workers` | `0` | `0..32` | Number of worker processes (0 = physical cores) |
| `chunk_min_sec` | `3.0` | `1.0..10.0` | Minimum duration for silence-aware audio chunks |
| `chunk_max_sec` | `5.0` | `2.0..15.0` | Maximum duration for audio chunks |
| `vram_budget_mb` | `7500` | `2000..32000` | Safety ceiling before GPU memory offload |
| `keep_warm` | `False` | `True / False` | Retain resident model in VRAM across runs |
| `output_mode` | `"both"` | `"save" / "play" / "both"` | Default output routing |
| `require_consent` | `True` | `True / False` | Mandatory ethical consent gate for enrollment |
| `precision` | `"fp32"` | `"fp32" / "fp16"` | Numerical inference precision |

---

## 6. Troubleshooting & Error Taxonomy (VX Codes)

Every operational failure in VoxClone yields a standardized VX code and actionable resolution:

| Error Code | Error Name | Cause | Actionable Resolution |
| :--- | :--- | :--- | :--- |
| **`VX-101`** | `SampleTooShortError` | Less than 10s of speech detected in reference audio | Record 20–30 s of clear speech with fewer pauses |
| **`VX-102`** | `UnsupportedAudioError` | Corrupted audio or unsupported codec | Convert source file to standard 16/24 kHz WAV |
| **`VX-103`** | `ConsentRequiredError` | Speaker consent not explicitly confirmed | Pass `--consent` or confirm ownership interactively |
| **`VX-201`** | `InvalidTextError` | Empty text or exceeding character bounds | Provide non-empty text under 10,000 characters |
| **`VX-210`** | `NoSpeechDetectedError` | Audio is pure silence or near-zero energy | Check microphone gain, input volume, or source file |
| **`VX-300`** | `InsufficientVramError` | Available GPU VRAM below model budget | Close GPU applications or run `system free-gpu` |
| **`VX-301`** | `ChunkOutOfMemoryError` | GPU OOM during a specific chunk execution | Lower chunk max duration or resume the job |
| **`VX-302`** | `GpuUnavailableError` | CUDA requested but hardware or driver unavailable | Run Doctor; fall back to CPU or Remote Drive backend |
| **`VX-310`** | `ModelWeightsMissingError` | Model weights not downloaded to cache | Run `voxclone system fetch-models` while connected |
| **`VX-401`** | `MicrophoneUnavailableError` | Audio input device cannot be initialized | Check sound permissions in OS; use file input |
| **`VX-402`** | `SpeakerUnavailableError` | Audio playback device cannot be initialized | Audio output was saved to disk; play from desktop |
| **`VX-500`** | `JobInterruptedError` | Process terminated or cancelled mid-execution | Select `Resume` in Job History to continue |
| **`VX-900`** | `InternalError` | Unhandled software error or database lock | Inspect logs at `data/logs/voxclone.log` |

---

## 7. Testing & Verification

The offline test suite uses deterministic fake engines (`VOXCLONE_ENGINE=fake`) requiring zero network access and zero GPU hardware:

```bash
# Run all unit, integration, and e2e tests
python -m pytest tests/unit tests/integration tests/e2e -v

# Run milestone verification script
bash P6.sh
```

---

## 8. Responsible AI & Ethical Use

- **Consent Enforcement**: VoxClone strictly prohibits cloning voices without explicit permission. The consent confirmation check is immutable (`VOXCLONE_REQUIRE_CONSENT=1`).
- **Watermarking**: Generated speech includes ultrasonic watermarking metadata in WAV file headers for provenance tracing.
- **Paused Features**: Live streaming conversion is paused pending latency optimization; see [`docs/LIVE_MODE_SPIKE.md`](file:///c:/Users/ACER/Desktop/v1/docs/LIVE_MODE_SPIKE.md).
