# PROJECT DEFINITION REPORT: VoxClone CLI

> **Assumptions made while writing this PDR (please correct any that are wrong)**
> 1. Single user, single machine (your laptop). No accounts, no cloud, no multi-user.
> 2. Hardware budget: **8 GB usable system RAM** (WSL2) and **8 GB VRAM**. Everything below is sized to fit that.
> 3. "Speak real time" as an *input* is delivered as **record-then-convert** (you record from the mic, then it is cloned). Live streaming conversion is **paused** (see 3 Out-of-Scope and 12 Risks).
> 4. Voice cloning is **zero-shot** (no training): a 20-30 s reference sample is enough.
> 5. Primary language is English (the default model family is English-first). Multilingual is a later question (see TDR section 15).
> 6. You will only clone voices you own or have explicit permission to use. The tool enforces a consent confirmation at enrollment.

---

## 1. Executive Summary

VoxClone CLI is a terminal application that runs inside Docker on WSL2 and clones a human voice from a short sample. You give it a 20-30 second recording of a voice (a file, or recorded live from the microphone). The tool stores it as a reusable **voice profile**. From then on, you can produce speech in that voice in two ways:

- **Text to Voice:** type or paste text; the tool reads it, detects the emotion of each sentence, and speaks it in the cloned voice.
- **Recording to Voice:** give it any recording (a file, or one captured from the mic); the tool converts the speaker to the cloned voice while keeping the original timing and delivery.

Every result can be **saved as a .wav file**, **played immediately**, or both. The whole interface is a keyboard-driven **dropdown menu** that opens at launch. There are no commands to memorize.

The engineering core is built for a modest laptop: AI models are loaded **one at a time and unloaded automatically** by code, and long audio is cut into **3-5 second chunks** that are prepared and finished across **all CPU cores**, while a single loaded model on the GPU converts them in order. The chunks are then rejoined into one smooth file.

## 2. Project Objectives

### Primary Objectives
1. **Clone a voice from 20-30 s of audio** and reuse it forever as a named profile.
2. **Three input paths** all ending in the cloned voice:
   - (a) record from the mic, then convert;
   - (b) supply a recorded file;
   - (c) supply text, with emotion understood from the text.
3. **Two output paths:** save to disk, play now, or both.
4. **Automatic model lifecycle:** only one AI model resident in memory at any moment; loading and unloading is done by code, never by the user.
5. **Chunked parallel processing:** split audio into 3-5 s chunks, prepare/finish them on all CPU cores, convert on the GPU, and rejoin without audible seams.
6. **Run entirely inside Docker on WSL2**, with no other services, accounts or cloud calls once the model weights are downloaded.
7. **Fit in 8 GB VRAM / 8 GB RAM** without crashes.

### Secondary Objectives (not required for the initial build)
- Live (streaming) microphone conversion. **Paused**; design-only spike at the end of the plan.
- Multiple languages.
- Voice-profile quality scoring (suggest re-recording a poor sample).
- Batch processing of a folder of files.
- Exporting profiles to share between machines.

## 3. Scope of Work

### In-Scope
- Interactive dropdown menu CLI (opens at launch) plus scriptable sub-commands for the same actions.
- **Voice profile management:** enroll from file or mic, clean/normalize the sample, list, preview, rename, delete.
- **Text to Voice** with sentence splitting and per-sentence emotion detection (with manual override).
- **Recording to Voice** (file or freshly recorded) using the chunked parallel pipeline.
- **Output management:** save to `outputs/`, play through speakers, or both.
- **Model Manager:** one-model-at-a-time load/unload, VRAM budget checks, "Free GPU memory" action.
- **Job history** with progress and resume of an interrupted conversion.
- **Doctor/diagnostics** command: checks GPU in Docker, audio devices, disk, model cache.
- Docker image + compose file with GPU access and persistent volumes for weights, profiles and outputs.
- Offline-first automated test suite that runs inside Docker without a GPU.

### Out-of-Scope
- **Real-time / live streaming voice conversion**: paused. No menu entry in this build.
- Any graphical or web UI. (CLI only, per your decision.)
- Training or fine-tuning models on your voice.
- Cloud APIs, accounts, authentication, payments, email.
- Native Windows install (WSL + Docker only).
- Mobile apps.
- Cloning voices without consent, or any feature meant to impersonate third parties.
- Music generation, singing voice conversion, noise-removal studio features.

## 4. User Personas

| # | Persona | Description | Primary needs |
|---|---------|-------------|---------------|
| P1 | **Owner-Operator** (you) | A developer who lives in the WSL terminal and wants to clone their own voice for narration, content, or experiments. | Quick enrollment; menu-driven workflow; predictable speed on 8 GB VRAM; the tool never crashes the machine; output as file or instant playback. |
| P2 | **Maintainer** (also you, wearing the developer hat) | Extends the tool: swaps in a different TTS or voice-conversion model, fixes bugs, runs tests. | Clean engine interface so models are swappable; tests that run without a GPU; clear logs; one-command build/run. |

Only two personas are needed because this is a local single-user tool.

## 5. Functional Requirements

### 5.1 Admin Control Panel: "System" Menu (Foundational, Priority #1)
For a single-user CLI this is the **System menu** inside the same dropdown. It exists so you never have to touch the file system or Docker commands for housekeeping.
- **Model status:** shows which model (if any) is loaded and the VRAM used.
- **Free GPU memory:** unloads any resident model on demand.
- **Doctor:** checks GPU visibility inside Docker, CUDA availability, audio input/output devices, free disk, free RAM, and model cache presence; shows each check as pass/fail with a fix hint.
- **Settings:** viewable and editable (device auto/cuda/cpu, worker count, chunk bounds, crossfade length, default output mode, consent prompts).
- **Storage:** shows size of profiles, outputs, model cache and temp; clean temp files.
- Business rule: every System action is available without loading any AI model.

### 5.2 Authentication & Role Access
**Not applicable.** There are no accounts. Access control is the operating system and Docker volume permissions on your machine. The one control that *does* exist is a **consent gate**: enrolling a voice requires confirming "I own this voice or have the speaker's permission." The confirmation is stored with the profile.

### 5.3 Voice Profile Management
- **Enroll from file:** accepts wav/mp3/flac/m4a; converts to mono, trims leading/trailing silence, peak-normalizes, stores the cleaned reference.
- **Enroll from microphone:** records 20-30 s (with an on-screen countdown and a level meter), then saves like a file.
- **Validation:** sample must be **≥10 s of speech** (target 20-30 s) and not mostly silence; warns on clipping or very low level; refuses empty/corrupt files.
- **List / preview / rename / delete** profiles. Preview plays the stored reference.
- Business rules: profile names are unique; deleting a profile does not delete previously generated outputs; a profile can be used by any number of jobs.

### 5.4 Text to Voice with Emotion
- Input: typed text, pasted text, or a `.txt` file path.
- The text is **split into sentences/short passages (≤200 characters)**.
- An **emotion classifier** labels each passage (joy, sadness, anger, fear, surprise, disgust, neutral). Each label maps to a speech-expressiveness setting for the TTS model.
- The user can accept **Auto emotion**, or choose a fixed expressiveness (calm / normal / expressive).
- Passages are synthesized in the cloned voice and joined with short natural pauses.
- Business rule: the emotion model is unloaded before the TTS model is loaded (never both resident).

### 5.5 Recording to Voice (Chunked Parallel Conversion)
- Input: an audio file **or** a fresh mic recording (record, then convert).
- **Pipeline:** (1) split at the quietest point into **3-5 s chunks**; (2) clean each chunk on **all CPU cores**; (3) convert chunks one by one on the GPU with the loaded voice-conversion model; (4) match loudness per chunk on all CPU cores; (5) rejoin with a short crossfade.
- Progress is shown per chunk with an elapsed/remaining estimate.
- Business rules: output chunk order always equals input order; a failed chunk is retried once, then the job fails with a clear message and can be **resumed** from the last finished chunk.

### 5.6 Model Lifecycle Manager
- Models: **text-to-speech**, **voice conversion**, **emotion classifier**. (Speech-to-text is not needed in this build.)
- Rule: **at most one model resident** at any time. Requesting a different model first unloads the current one, frees GPU memory, then loads the new one.
- Pre-flight VRAM check against a configurable budget (default 7 GB).
- On an out-of-memory error: free memory, retry once, otherwise stop with a plain-language message.
- Every load/unload is recorded (with time and VRAM before/after) for diagnostics.

### 5.7 Output Management
- **Save:** writes a `.wav` into `outputs/` with an automatic descriptive name (`<type>_<profile>_<timestamp>.wav`).
- **Play now:** plays through the speakers via WSLg audio; if playback is unavailable it says so and falls back to Save.
- **Both** is a first-class option.
- A simple browser lists past outputs with a replay action.

### 5.8 Job History & Resume
- Each generation is a **job** with status, timings, chunk counts and output path.
- Interrupted conversions (Ctrl+C, crash, power loss) can be **resumed**; finished chunks are not recomputed.
- *Assumption:* resume is included because long conversions on a laptop are likely to be interrupted at least once.

### Ticketing / Support
**Not applicable** (no support desk). Replaced by **Diagnostics & Error Reporting:** every failure shows an error code and a fix hint, and `System > Doctor` can bundle the log file for troubleshooting.

### Password Reset & Notifications
**Password reset: not applicable.** **Notifications** are in-terminal only: stage banners, progress bars, completion summary, warning panels (e.g. low-quality sample). No email, no push.

## 6. Non-Functional Requirements

| Area | Requirement |
|---|---|
| **Memory** | Peak VRAM ≤ **7 GB** with any single model; peak system RAM ≤ **6 GB** inside the container (leaves headroom within 8 GB). |
| **Performance (targets, to be verified in M5)** | Text to Voice: start of audio saved within **30 s** of confirming for a one-paragraph input (model load included on first use). Recording to Voice: processing time **≤ 1.5x** the audio length on GPU after the model is loaded. CPU-side prep and post stages **≤ 15 %** of total job time. Menu response to key press **< 100 ms**. |
| **Reliability** | A failed or cancelled job never corrupts profiles or outputs. Temp files are cleaned at next start. Resume works after a forced stop. |
| **Offline** | After first download of weights, no network access is needed (`HF_HUB_OFFLINE=1`). |
| **Security / Privacy** | All audio stays on the machine. Container runs as a non-root user. No telemetry. Profile and output folders are mode 0700. Consent confirmation stored per profile. |
| **Portability** | One `docker compose` command to build and run on any WSL2 + NVIDIA GPU machine. |
| **Usability / Accessibility** | Fully keyboard-driven. Color is never the only signal (icons + words). `NO_COLOR` and `--plain` mode supported. Contrast target equivalent to WCAG 2.1 AA (4.5:1) on dark and light terminals. |
| **Uptime** | Not applicable (local tool); success is measured by job success rate (see 13). |

## 7. System Architecture (Overview)

**Style: modular monolith, single container.** One Python application with clear layers: *interface* (menu + sub-commands) → *services* (profiles, jobs, models) → *engines* (TTS, voice conversion, emotion, audio DSP) → *storage* (SQLite + files). Microservices would add networking and memory overhead for no benefit on one laptop.

**Deployment:** Docker on WSL2, GPU passed through with the NVIDIA Container Toolkit. Persistent **volumes**: model cache, profiles, outputs, data (SQLite + logs). Audio devices are reached through WSLg's PulseAudio socket mounted into the container.

**Concurrency model (the key design decision):**
- **GPU = one consumer.** A single loaded model processes chunks sequentially (eight GB of VRAM cannot hold several copies).
- **CPU = many workers.** A process pool (one worker per core, `spawn` start method so CUDA is never touched in workers) does the splitting, trimming, normalizing, loudness matching and the file writes, overlapping with the GPU so the GPU is never waiting.

## 8. Database Schema (Summary)

A small embedded **SQLite** database (file on a volume), because the app needs durable history and resume but not a database server.

- **VoiceProfile** (one per cloned voice) has many **Job**.
- **Job** (one generation) has many **JobChunk** (one sentence or one 3-5 s audio slice).
- **ModelEvent** records every model load/unload, optionally linked to a Job.
- **AppSetting** is a key-value table for user settings.
- **SchemaMigration** tracks database version.

Audio files themselves (reference samples, chunks, outputs) live on disk; the database stores their paths and metadata.

## 9. Technology Stack

| Layer | Choice |
|---|---|
| **Language / runtime** | Python 3.11 |
| **Voice synthesis & conversion** | Chatterbox (text-to-speech with voice prompt and emotion-exaggeration control; voice-conversion model from the same package) |
| **Emotion detection** | Hugging Face `transformers` with a DistilRoBERTa emotion classifier (`j-hartmann/emotion-english-distilroberta-base`) |
| **Deep learning runtime** | PyTorch (CUDA build, pinned via lockfile) |
| **Audio DSP / IO** | librosa, soundfile, numpy; sounddevice (mic and speakers via PortAudio) |
| **Interactive CLI** | questionary (arrow-key dropdown menus), rich (panels, tables, progress bars) |
| **Scriptable CLI** | Typer |
| **Database** | SQLite (stdlib `sqlite3`), SQL migration files |
| **Parallelism** | `concurrent.futures.ProcessPoolExecutor` (`spawn`) |
| **DevOps** | Docker, Docker Compose, NVIDIA Container Toolkit, WSL2, Git |
| **Quality** | pytest, ruff, black, mypy |
| **Third-party services** | None at runtime. Hugging Face Hub used **only** for the one-time weight download. |

## 10. Development Phases & Timeline

Solo, part-time estimate; each milestone is roughly one focused week. **M0-M6 map 1:1 to P0-P6 in the Master Project Blueprint.**

| Milestone | Goal | Features delivered |
|---|---|---|
| **M0: Foundation** (wk 1) | A running, GPU-aware container with an empty menu | WSL2 + Docker GPU verified; repo scaffold; config + logging; SQLite + migrations; menu opens at launch; `doctor` checks; fake-engine test harness |
| **M1: Model Manager + Voice Profiles** (wk 2) | Models load/unload safely; voices can be enrolled | One-model-at-a-time manager with VRAM budget; enroll from file and mic; sample validation and cleaning; list/preview/rename/delete; consent gate |
| **M2: Text to Voice** (wk 3) | Type text, hear it in your voice | Sentence splitter; Chatterbox TTS; crossfade join; Save / Play / Both output |
| **M3: Emotion from Text** (wk 4) | Delivery follows the emotion of the text | Emotion classifier stage; emotion-to-expressiveness mapping; manual override; classifier-then-TTS handoff with unload in between |
| **M4: Recording to Voice (Chunked Parallel)** (wk 5-6) | Convert recordings to your voice quickly | Silence-aware 3-5 s splitter; all-core prep/post pool; GPU conversion queue; loudness match; crossfade rejoin; record-then-convert from the mic |
| **M5: Jobs, Resume & Performance** (wk 7) | Reliable and measurably fast | Job history; resume; output browser; settings; benchmark command; tuning against targets |
| **M6: Hardening & Release** (wk 8) | Ready for daily use | Full E2E tests; error-message polish; docs; `--plain` mode; documented design spike for the paused live mode |

## 11. Admin & Permission Model

Only one runtime role exists. The matrix below documents which capabilities belong to which persona.

| Capability | Owner-Operator (P1) | Maintainer (P2) |
|---|:--:|:--:|
| Enroll / delete voice profiles | Yes | Yes |
| Generate Text to Voice / Recording to Voice | Yes | Yes |
| Change settings, free GPU memory, run Doctor | Yes | Yes |
| Read job history and logs | Yes | Yes |
| Add or swap a model engine (code change) | No | Yes |
| Change DB schema (migrations) | No | Yes |
| Run the test suite | No | Yes |
| Bypass consent gate | **No** (one) | **No** (one) |

Both personas are the same person on the same machine; the table exists so permissions in code (settings that are editable vs code-level changes) are explicit.

## 12. Risk Analysis & Mitigation

| # | Risk | Likelihood / Impact | Mitigation |
|---|------|---|---|
| R1 | **VRAM out-of-memory** (8 GB card) | High / High | Single resident model; VRAM budget pre-check; `empty_cache` on unload; one retry after OOM; chunked processing keeps activations small. |
| R2 | **Models not freed** (memory leak across switches) | Medium / High | Manager owns the only reference; explicit `gc.collect()` + `torch.cuda.empty_cache()`; automated test that loads/unloads repeatedly and asserts memory returns near baseline. |
| R3 | **Audible seams** between 3-5 s chunks (clicks, loudness jumps, voice drift) | High / Medium | Cut only at the quietest frame; per-chunk loudness matching; 30 ms equal-power crossfade; same reference used for every chunk; tunable chunk bounds. |
| R4 | **CPU worker pool exhausts RAM** (every worker imports heavy libraries) | Medium / High | Workers import only light DSP libraries; chunk arrays are small; worker count configurable (default all cores, capped by free RAM check). |
| R5 | **GPU not visible inside Docker/WSL** | Medium / High | `doctor` check with exact fix steps (Windows driver, container toolkit, `--gpus`); CPU fallback with a loud slowness warning. |
| R6 | **WSL audio (mic/speaker) unavailable** | High / Medium | File-based paths work without audio; `doctor` tests PulseAudio socket; clear fallback message; mic features degrade gracefully. |
| R7 | **Poor reference sample** produces bad clones | High / Medium | Validation (duration, level, clipping, noise estimate); guidance text on recording conditions; preview before saving. |
| R8 | **Misuse / impersonation** | Medium / High | Consent gate at enrollment, stored with profile; no features for covert use; docs state permitted use. Generated audio from the default engine carries an embedded watermark (verify in M2). |
| R9 | **Model license limits** (some models non-commercial) | Medium / Medium | Record each model's license in the TDR; verify before any commercial use. |
| R10 | **Long jobs interrupted** | Medium / Medium | Per-chunk persistence and resume. |
| R11 | **Weights download fails or is slow** | Medium / Low | Persistent cache volume; retry; offline mode after first success. |
| R12 | **Live mode scope creep** | Medium / Medium | Explicitly paused; zero menu entry; design-only spike in M6. |

## 13. Success Metrics

### Technical KPIs
- **Zero out-of-memory crashes** across the M5 benchmark set (≥50 jobs).
- Peak VRAM ≤ 7 GB; peak RAM ≤ 6 GB.
- Recording to Voice ≤ **1.5x** real-time on GPU (post model-load).
- CPU prep+post ≤ 15 % of job time.
- 100 % of resume tests succeed after forced interruption.
- Test suite passes in Docker without a GPU.

### Business KPIs
*(Personal tool, so "business" means project value.)*
- All **three inputs** and **both outputs** work end to end by M4.
- One-command setup works on a clean WSL install.

### User Adoption KPIs
- Enroll a voice and hear first output in **under 5 minutes** from a fresh install (excluding weight download).
- ≥ **90 %** of jobs finish on first attempt without opening the log.
- Blind self-listening test: cloned output rated "recognizably me" on ≥ 8 of 10 samples.

## 14. Appendices

### 14.1 API Endpoint Summary (CLI Command Map)
There is no network API. The scriptable command map is below; each interactive menu item maps to one of these.

| Command | Purpose |
|---|---|
| `voxclone` | Open the interactive dropdown menu |
| `voxclone profiles enroll --name N --file F` / `--record 30` | Create a voice profile |
| `voxclone profiles list` | List profiles |
| `voxclone profiles preview --name N` | Play the stored reference |
| `voxclone profiles rename --name N --to M` | Rename |
| `voxclone profiles delete --name N` | Delete |
| `voxclone speak --profile N --text T [--emotion auto\|calm\|normal\|expressive] [--save\|--play\|--both]` | Text to Voice |
| `voxclone convert --profile N --in F [--save\|--play\|--both]` | Recording to Voice (file) |
| `voxclone convert --profile N --record SECS` | Record then convert |
| `voxclone jobs list` / `jobs resume --id ID` | History and resume |
| `voxclone system doctor` / `system free-gpu` / `system settings` / `system clean` | System menu actions |
| `voxclone bench` | Performance benchmark |

### 14.2 Notification Templates (in-terminal messages)

| Name | Trigger | Content |
|---|---|---|
| Profile saved | Enrollment succeeds | Name, duration, quality notes |
| Sample warning | Validation finds low level, clipping, or short duration | What is wrong and how to re-record |
| Model loading | Manager loads a model | Model name, "freeing previous model" if any, VRAM before/after |
| Chunk progress | During conversion | Chunk i/N, stage (prep/GPU/post), ETA |
| Job complete | Job succeeds | Output path, duration, elapsed, real-time factor |
| Job failed | Unrecoverable error | Error code, plain reason, fix hint, "Resume" option |
| Audio unavailable | Playback/mic cannot open | What failed and the file-based alternative |
| GPU memory freed | User selects Free GPU memory | Model unloaded, VRAM now free |

### 14.3 Glossary

| Term | Meaning |
|---|---|
| **Zero-shot cloning** | Imitating a voice from a short sample with no training |
| **Voice profile** | A named, cleaned reference sample stored for reuse |
| **TTS** | Text-to-speech: turns text into audio |
| **Voice conversion (VC)** | Changes who is speaking in existing audio, keeping the words and timing |
| **Chunk** | A 3-5 s slice of audio (or a sentence of text) processed as one unit |
| **Crossfade** | Short overlap blend between two chunks to hide the join |
| **Exaggeration** | The TTS control that makes delivery calmer or more expressive |
| **VRAM** | Video memory on the GPU (8 GB here) |
| **Model Manager** | The component that loads/unloads models so only one is resident |
| **WSLg** | Windows' Linux GUI/audio bridge that lets WSL use mic and speakers |
| **RTF** | Real-time factor: processing time divided by audio length |
