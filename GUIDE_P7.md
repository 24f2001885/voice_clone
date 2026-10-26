# GUIDE_P7.md - Milestone P7: Remote GPU Backend (Google Drive Queue & Colab Worker)

## Executive Overview

Milestone **P7 (Remote GPU Backend)** implements a decoupled, zero-port-forwarding hybrid architecture tailored specifically for users running on hardware without dedicated local NVIDIA CUDA cards (such as **AMD Ryzen APUs with integrated Radeon Graphics** or laptops with Intel Iris iGPUs).

By coupling the local VoxClone CLI with a free **Google Colab NVIDIA T4 GPU runtime** via a personal **Google Drive folder queue**, users get the best of both worlds:
- **Local Machine**: Instant terminal UI, low-latency microphone recording, local SQLite WAL state, silence-aware CPU splitting, audio normalization, and playback.
- **Remote Colab Worker**: Accelerated neural inference (Kokoro TTS and FreeVC voice conversion) running on an NVIDIA T4 GPU with 16 GB VRAM.
- **Transport**: Standard file exchange via Google Drive desktop mirror (`inbox/`, `outbox/`, `heartbeat/`). Zero webhooks, zero ngrok tunnels, zero firewall or router configuration required.

---

## 1. System & Toolchain Dependencies

### 1.1 Local Machine Requirements
- **OS**: Windows 10/11 (with or without WSL2), Linux, or macOS.
- **Python**: 3.10+ (tested through 3.13).
- **Google Drive for Desktop**: Installed and syncing a personal Google Drive folder (e.g. `G:\My Drive\VoxClone_Queue` on Windows or `~/GoogleDrive/VoxClone_Queue` on Linux/WSL).
- **System Audio**: `ffmpeg` for audio transcoding.

### 1.2 Remote Environment (Google Colab)
- **Runtime**: Free Google Colab instance with **T4 GPU** accelerator.
- **Google Account**: Signed in with access to Google Drive.

### 1.3 Environment Configuration (`.env`)

Add or update the following settings in your `.env` file:

```ini
# ==============================================================================
# VoxClone Phase P7 Hybrid Remote GPU Configuration
# ==============================================================================

# Execution Backend: Set to 'remote_drive' to offload neural models to Colab GPU
VOXCLONE_BACKEND=remote_drive

# Engine mode: 'real' when offloading to Colab, or 'fake' for offline testing
VOXCLONE_ENGINE=real

# Local compute device for audio DSP and text splitting
VOXCLONE_DEVICE=cpu

# Absolute or relative path to your synced Google Drive queue directory
# On Windows: G:\My Drive\VoxClone_Queue or C:\Users\<Username>\Google Drive\VoxClone_Queue
# In repository test folder: drive_queue
VOXCLONE_DRIVE_DIR=drive_queue

# Remote request timeout (seconds)
VOXCLONE_REMOTE_TIMEOUT=120.0
```

---

## 2. Model, Weights & Static Asset Provisioning

### 2.1 Persistent Colab Cache
To prevent redownloading 1+ GB of neural checkpoints on every Colab runtime restart, model weights are cached directly inside Google Drive:
- **Location**: `/content/drive/MyDrive/VoxClone_Queue/models`
- **Models Cached**:
  - `hexgrad/Kokoro-82M` (~350 MB)
  - `OlaWod/FreeVC` (~600 MB)
- **Subsequent Boots**: Weights load from Google Drive in under 15 seconds.

---

## 3. Database & Infrastructure State

### 3.1 Local SQLite Database Integrity
- All job definitions, audio segment cut points, speaker profile reference files, and progress states remain **100% local on your PC** inside `data/voxclone.db` (SQLite WAL mode).
- No sensitive profile voice recordings or SQLite databases are sent to Google Colab. Only individual anonymous 3–5 second chunk audio clips are transmitted through the queue and deleted immediately after processing.

---

## 4. Execution Script Walkthrough (`P7.sh`)

`bash P7.sh` executes the complete verification sequence:

1. **Branch Verification**: Confirms git branch `milestone/p7-remote-gpu`.
2. **Directory Scaffolding**: Creates `drive_queue/inbox`, `drive_queue/outbox`, `drive_queue/heartbeat`, and `drive_queue/models`.
3. **Python Environment Resolution**: Detects `python3`, `python`, or `python.exe`.
4. **Diagnostic Probe**: Runs `voxclone doctor` verifying both local health and Google Drive queue availability.
5. **Full Automated Test Suite**: Executes 136 tests offline covering queue file transport, atomic writes, timeout handling, and remote engine adapters:
   ```bash
   pytest tests/unit tests/integration tests/e2e -v -m "not gpu"
   ```

---

## 5. Validation & Test Execution

### 5.1 Invoking Test Suites
```bash
# Run Google Drive queue transport unit tests
python -m pytest tests/unit/test_drive_queue.py -vv

# Run RemoteTts and RemoteVc integration tests (with mock background worker)
python -m pytest tests/integration/test_remote_engines.py -vv

# Run full test suite
python -m pytest tests/ -v -m "not gpu"
```

### 5.2 Interactive Screens Verified in P7
- **S-58 (`screen_remote_worker`)**: Shows Google Drive folder path, Colab worker heartbeat status (`ONLINE` vs `OFFLINE`), queue depth counters (inbox/outbox), queue ping test, and Colab launch guide.

---

## 6. Colab Worker Operation

### 6.1 Starting the Worker on Google Colab
1. Navigate to [Google Colab](https://colab.research.google.com).
2. Click **Upload** and upload [`scripts/colab_worker.ipynb`](file:///c:/Users/ACER/Desktop/v1/scripts/colab_worker.ipynb).
3. In the top navigation: **Runtime** > **Change runtime type** > Select **T4 GPU** > Click **Save**.
4. Run all cells:
   - **Cell 1**: Mounts Google Drive (`/content/drive/MyDrive/VoxClone_Queue`).
   - **Cell 2**: Installs runtime audio dependencies (`soundfile`, `torch`, `transformers`).
   - **Cell 3**: Enters the continuous worker polling loop.
5. While Cell 3 displays `Polling for tasks from local machine...`, run `voxclone speak` or `voxclone convert` on your computer!

---

## 7. Operator Action Checklist

> [!IMPORTANT]
> Follow this exact step-by-step checklist to configure, launch, and operate the Hybrid Remote GPU backend on your AMD Radeon APU / CPU system.

### 7.1 What to Download
- [x] **Repository Code**: Verified on branch `milestone/p7-remote-gpu`.
- [x] **Google Drive for Desktop**: Download from [google.com/drive/download](https://www.google.com/drive/download/) if not already installed.
- [x] **Colab Worker Notebook**: Located at [`scripts/colab_worker.ipynb`](file:///c:/Users/ACER/Desktop/v1/scripts/colab_worker.ipynb).

### 7.2 Where to Login
- [x] **Google Account**: Sign in on your desktop Google Drive client and in your browser for [Google Colab](https://colab.research.google.com).
- [x] **GitHub**: Ensure credentials are configured for git push.

### 7.3 What Keys to Bring
- [x] **None Required**: Google Drive authentication is handled via your standard browser Google account sign-in. Zero API keys or cloud tokens are required.

### 7.4 What to Check
- [x] Check that Google Drive is syncing the folder `VoxClone_Queue` locally on your PC.
- [x] Check that `scripts/colab_worker.ipynb` runs with runtime type set to **T4 GPU**.
- [x] Check remote worker status in VoxClone CLI: select **System** > **Remote Colab GPU worker (S-58)**.

### 7.5 Pre-flight Verification Table
| Step | Action Command | Expected Output | Status |
| :--- | :--- | :--- | :--- |
| **1** | `python -m pytest tests/unit/test_drive_queue.py -v` | All 8 queue transport tests pass | READY |
| **2** | `python -m pytest tests/integration/test_remote_engines.py -v` | All 3 remote engine tests pass | READY |
| **3** | `python -m voxclone.cli doctor --plain` | All system checks passing (`[OK]`) | READY |
| **4** | Launch Colab notebook Cell 3 | `Worker active on: cuda (Tesla T4)` | READY |
| **5** | `bash P7.sh` | `Milestone P7 Remote GPU Backend: Completed Successfully!` | READY |
