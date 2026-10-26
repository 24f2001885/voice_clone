# Technical Spike: Real-Time Live Streaming Voice Conversion (Paused Feature)

## 1. Feature Objective & Scope

The live voice conversion spike investigated the feasibility of a bidirectional microphone-to-speaker streaming pipeline: speaking into a microphone and outputting the converted target voice in real time with conversational latency (< 500 ms round-trip).

As specified in the Project Definition Report (PDR Section 3.2, Out of Scope) and Technical Design Report (TDR 15.8), **this feature is paused in VoxClone v1.0**.

---

## 2. Why Live Mode Is Paused

1. **Hardware & VRAM Constraints**: VoxClone targets consumer hardware with 8 GB VRAM. Full real-time neural voice conversion while simultaneously servicing OS display rendering exceeds the allowable memory headroom.
2. **Autoregressive & Non-Causal Model Structures**: Contemporary high-fidelity zero-shot VC models (FreeVC, OpenVoice) rely on full-sequence bi-directional attention mechanisms, requiring complete utterance context to establish pitch envelopes. Truncating context to sub-second frames degrades acoustic speaker similarity.
3. **Audio Subsystem Latency in WSL2 / Docker**: Routing audio across the Windows host $\leftrightarrow$ WSL2 VM $\leftrightarrow$ Docker container boundary introduces 80–150 ms of driver and buffer overhead alone.

---

## 3. Projected Latency Budget (Target: < 500 ms)

| Stage | Candidate Window | Latency Contribution | Feasibility Status |
| :--- | :--- | :--- | :--- |
| **Audio Capture Buffer** | 100 ms ring buffer | ~100 ms | Proven |
| **Voice Activity Detection (VAD)** | Energy / Silero VAD | ~50 ms | Proven |
| **Acoustic Pre-processing** | Mel-spectrogram extraction | ~20 ms | Proven |
| **Neural Conversion Inference** | Causal streaming checkpoint | ~150–250 ms (at RTF $\le$ 0.5) | Unproven on 8 GB GPU |
| **Neural Vocoder Synthesis** | Streaming HiFi-GAN / BigVGAN | ~60 ms | Proven on CUDA |
| **Audio Playback Buffer** | PulseAudio / ALSA ring | ~50 ms | Proven |
| **WSL2 / Container Interop** | PulseAudio over TCP / socket | ~50–100 ms | Variable |
| **Total Round-Trip Latency** | | **480 – 630 ms** | **Borderline** |

---

## 4. Architectural Alternatives Evaluated

1. **Short-Chunk Overlap-Add (OLA)**:
   - Slice continuous microphone input into 1.0s chunks with 200 ms crossfade overlap.
   - *Result*: Noticeable boundary phase discontinuities and excessive latency (~1.2s round-trip).
2. **Causal Streaming VC (e.g., StreamVC, FastVC)**:
   - Evaluated lightweight causal models with unidirectional convolution kernels.
   - *Result*: Low latency (~300 ms), but acoustic similarity and prosody score drop significantly below the quality bar for zero-shot cloning.

---

## 5. Go / No-Go Criteria for Future Unfreezing

Before live streaming voice conversion is considered for implementation in a future milestone, all of the following measurable criteria must be met:

- [ ] High-fidelity causal zero-shot VC checkpoint available under an OSI-compliant commercial license.
- [ ] End-to-end model inference latency $\le 120$ ms on NVIDIA RTX 3060 (8 GB VRAM).
- [ ] Peak VRAM consumption of the streaming pipeline $\le 3500$ MB.
- [ ] Native host audio execution without VM crossing (or native Windows DirectSound/WASAPI audio routing).
- [ ] Round-trip audio delay $\le 400$ ms with zero audible buffer underruns in a 10-minute continuous test.
