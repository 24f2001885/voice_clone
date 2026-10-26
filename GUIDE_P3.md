# Phase 3 Developer Runbook & Operational Guide: Emotion from Text

## 1. System & Toolchain Dependencies

### 1.1 Runtime & Hardware Requirements
* **Python Runtime:** Python 3.11, 3.12, or 3.13.
* **Audio & NLP Toolchain:** `transformers`, `torch` (optional for local real inference; fake engines for offline testing), `numpy`, `soundfile`, `rich`, `questionary`.
* **Hardware Profiles Supported:**
  * **Profile A (NVIDIA GPU / 8 GB vGPU):** PyTorch CUDA 12.x passthrough, `VOXCLONE_VRAM_BUDGET_MB=6000`, `VOXCLONE_DEVICE=auto` or `cuda`. Single-resident model manager guarantees emotion classifier is fully unloaded before TTS synthesis loads.
  * **Profile B (AMD Radeon APU / CPU Fallback):** Ryzen APU / Intel iGPU, `VOXCLONE_DEVICE=cpu`, `docker-compose.cpu.yml`. DistilRoBERTa is compact (~600 MB) and executes efficiently on CPU with near-instant inference.
  * **Profile C (Hybrid Google Drive Queue):** Text emotion classification runs locally on CPU while neural speech synthesis is queued via Google Drive to a free Google Colab NVIDIA T4 GPU worker (`VOXCLONE_BACKEND=remote_drive`).

### 1.2 Environment Variables Configuration
Ensure your local `.env` file defines:

```dotenv
# ==============================================================================
# VoxClone Phase 3 Operational Configuration (.env)
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

# Emotion Classifier Model Name
VOXCLONE_EMOTION_MODEL=j-hartmann/emotion-english-distilroberta-base

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

### 2.1 Neural Architecture: DistilRoBERTa Emotion Classifier
* **Model ID:** `j-hartmann/emotion-english-distilroberta-base`
* **VRAM/RAM Footprint:** ~600 MB (extremely lightweight, runs smoothly on CPU or GPU).
* **Role:** Sequence classification mapping text passages to 7 core emotions: `joy`, `sadness`, `anger`, `fear`, `surprise`, `disgust`, and `neutral`.
* **Single-Resident Handoff Invariant:** The emotion model is loaded to classify all sentence passages, then **explicitly unloaded from memory** before the TTS synthesis model is loaded. This prevents GPU VRAM exhaustion on 8 GB cards.

### 2.2 Emotion to Expressiveness Mapping (TDR Section 3.8)
| Detected Label | Expressiveness Value | Acoustic Delivery Character |
|---|---|---|
| `neutral` | 0.40 | Steady, balanced conversational cadence |
| `sadness` | 0.30 | Slower pacing, muted dynamic range |
| `joy` | 0.70 | Brighter pitch contours, elevated energy |
| `fear` | 0.70 | Heightened tension, dynamic variability |
| `disgust` | 0.70 | Emphatic inflections |
| `surprise` | 0.80 | Wide pitch excursions, heightened emphasis |
| `anger` | 0.90 | High intensity, sharp transients |

*Note: Expressiveness is strictly clamped to $[0.25, 1.0]$.*

### 2.3 Downloading Checkpoints
To download production weights for offline local execution:
```bash
# Option A: Hugging Face CLI
huggingface-cli download j-hartmann/emotion-english-distilroberta-base --local-dir /models/emotion --local-dir-use-symlinks False

# Option B: Built-in model fetcher
voxclone system fetch-models
```

---

## 3. Database & Storage Architecture

### 3.1 Active SQLite Tables in Phase 3
* `job_chunks`: Records individual sentence passages along with `detected_emotion` (e.g. `'joy'`) and mapped `expressiveness` (e.g. `0.70`).
* `model_events`: Formally logs the model transition:
  1. `model_key='emotion', action='load'`
  2. `model_key='emotion', action='unload'`
  3. `model_key='tts', action='load'`
  *Guarantees zero memory overlap between classifier and synthesizer.*

---

## 4. Execution Script Walkthrough (`P3.sh`)

Running `bash P3.sh` executes the automated Phase 3 validation:
1. Validates git milestone branch `milestone/p3-emotion`.
2. Inspects database schema and migrations.
3. Runs the test suite covering emotion mapping, model manager handoff, and full end-to-end text synthesis with auto emotion detection.

---

## 5. Validation & Test Execution

Run the complete Phase 3 test suite:

```bash
# In WSL or bash:
python -m pytest tests/unit/test_emotion_mapping.py tests/integration/test_text_pipeline.py -v

# Or run full offline test suite:
python -m pytest tests/unit tests/integration -v -m "not gpu"
```

* **Acceptance Sign-off Criteria:**
  * All unit and integration tests pass (`100+ passed`).
  * Emotion mapping correctly maps all 7 labels and clamps values to $[0.25, 1.0]$.
  * In Auto mode, passages are labeled and stored with their respective expressiveness values in `job_chunks`.
  * Single-resident model invariant is maintained: emotion model is unloaded before TTS model is loaded.
  * Preview table (S-23) displays passages, emotions, and expressiveness before generation.

---

## 6. Local Interactive Verification

Test interactive speech synthesis with emotion detection:

```bash
# Launch VoxClone interactive menu
python -m voxclone

# Navigation:
# 1. Select "Text  →  my voice"
# 2. Pick enrolled profile
# 3. Enter emotional text: "I am thrilled to see you! But why did this happen? It makes me so sad."
# 4. Choose Emotion: "Auto (Detect emotion from text passages)"
# 5. Review S-23 Emotion Preview Table (Joy, Surprise, Sadness)
# 6. Select "Continue with synthesis"
# 7. Observe stage panel: Emotion Analysis -> Model Manager unload/load -> Passage synthesis
```

---

## 7. Operator Action Checklist: Setup, Downloads, Logins & Keys

Follow this comprehensive operator checklist to prepare and verify your workstation for Phase 3:

### Step 1: Hardware & Compute Environment Check
* [ ] Open terminal and verify compute environment:
  * Windows PowerShell:
    ```powershell
    Get-PnpDevice -Class Display | Select-Object FriendlyName, Status, InstanceId
    python -c "import torch; print('CUDA Available:', torch.cuda.is_available())"
    ```
  * **If AMD Radeon(TM) Graphics (VEN_1002):** Set `VOXCLONE_DEVICE=cpu` in `.env`.
  * **If NVIDIA GPU (8 GB vGPU):** Set `VOXCLONE_DEVICE=auto` and `VOXCLONE_VRAM_BUDGET_MB=6000`.

### Step 2: What to Download (Software & Binaries)
* [ ] **Python 3.11–3.13:** Verify with `python --version`.
* [ ] **Hugging Face Transformers (for Real Inference):**
  * `pip install transformers` (included in `requirements.lock`).
* [ ] **DistilRoBERTa Weights (for Real Mode):**
  * Target directory: `models/emotion` or default Hugging Face cache `~/.cache/huggingface/hub`.

### Step 3: Where to Login (Accounts & Portals)
* [ ] **GitHub:** Sign in at [github.com](https://github.com) to synchronize with repository `https://github.com/24f2001885/voice_clone.git`.
* [ ] **Hugging Face:** Sign in at [huggingface.co](https://huggingface.co) to verify access token if using private models.

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

### Step 5: What to Check (Pre-Flight Validations)
| Check Item | Command | Expected Output | Remediation if Failing |
|---|---|---|---|
| **Emotion Mapping** | `python -c "from voxclone.pipelines.emotion_mapping import map_emotion_label; print(map_emotion_label('joy'))"` | `0.7` | Check `voxclone/pipelines/emotion_mapping.py` |
| **Model Invariant** | `python -m pytest tests/unit/test_model_manager.py -k "test_model_manager_single_resident_invariant"` | `1 passed` | Check `voxclone/engines/model_manager.py` |
| **Auto Emotion Pipeline** | `python -m pytest tests/integration/test_text_pipeline.py -k "test_text_pipeline_auto_emotion_classification_and_handoff"` | `1 passed` | Check `voxclone/pipelines/text_pipeline.py` |
| **Full Offline Test Suite** | `python -m pytest -q` | `100 passed` | Run `pytest -v` to inspect any failing assertions |

### Step 6: Execute Phase P3 Automation & Milestone Sign-off
```bash
# Run the automated Phase P3 test runner
bash P3.sh
```
* **Sign-off Criteria:** All unit and integration tests report green (100+ passed).
