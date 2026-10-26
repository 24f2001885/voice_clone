# Audio Recording & Acoustic Quality Best Practices

High-quality reference audio is the single most critical factor in achieving convincing voice cloning and speech conversion results. This guide provides actionable guidance on capturing optimal audio for voice enrollment and conversion.

---

## 1. Quick Acoustic Checklist

- **Environment**: Record in a carpeted room with curtains or soft furnishings to minimize acoustic room reflections and slap-back echo. Avoid tiled or bare rooms.
- **Microphone Distance**: Position the microphone 15 to 20 cm (6 to 8 inches) from your mouth.
- **Angle**: Angle the microphone slightly off-axis (around 30 degrees) to prevent vocal plosives (pops from 'p' and 'b' sounds).
- **Background Noise**: Turn off fans, air conditioners, heaters, and PC case fans. Keep mechanical keyboards silent.
- **Duration**: Speak continuously for 20 to 30 seconds. A minimum of 10.0 seconds of active vocal speech is strictly enforced by the enrollment gate.
- **Pacing**: Speak at a steady, natural conversational pace. Avoid reading in an exaggerated monotone.

---

## 2. Interpreting the Quality Analysis Report

When you enroll a voice via microphone or audio file, VoxClone executes `analyze_sample` (`audio/validate.py`) and generates a metric report:

| Metric | Acceptable Target | Description |
| :--- | :--- | :--- |
| **Duration** | 15.0 – 35.0 seconds | Total recorded audio duration. |
| **Speech Seconds** | $\ge$ 10.0 seconds | Total active vocal speech excluding pauses. |
| **RMS Level** | -26 dBFS to -14 dBFS | Average vocal signal strength. |
| **Peak Energy** | < 0.95 (linear) | Highest single sample amplitude. |
| **Clipping Ratio** | < 0.001 (< 0.1%) | Percentage of samples hitting maximum digital limit (1.0). |
| **Signal-to-Noise (SNR)**| $\ge$ 20.0 dB (ideal $\ge$ 25 dB) | Energy delta between active speech and background noise. |
| **Quality Score** | 0.80 to 1.00 | Composite heuristic acoustic score. |

---

## 3. Resolving Quality Notes & Diagnostic Warnings

The application provides contextual recommendations based on the detected signal characteristics:

### 3.1 "Recording is quiet; speak closer to the microphone or boost input volume."
- **Cause**: Overall RMS level is below -35 dBFS.
- **Fix**: Move closer to the microphone, increase OS microphone slider to 80-90%, or apply a clean digital gain preamp.

### 3.2 "Signal is unusually loud; decrease input volume to avoid distortion."
- **Cause**: Overall RMS level exceeds -14 dBFS, approaching distortion.
- **Fix**: Lower microphone gain and back up slightly.

### 3.3 "Minor audio clipping detected; avoid shouting directly into microphone."
- **Cause**: Clipping ratio is between 0.1% and 1.0%.
- **Fix**: Back away 5 cm from the microphone and avoid sudden loud emphasis.

### 3.4 "Significant audio clipping distortion present; decrease microphone gain."
- **Cause**: Clipping ratio exceeds 1.0%. Severe waveform flattening is present.
- **Fix**: Reduce audio gain in your sound settings immediately and re-record.

### 3.5 "Noticeable background noise detected; record in a quieter space."
- **Cause**: Measured SNR is between 15 dB and 25 dB.
- **Fix**: Eliminate ambient noise sources or record under a blanket/closet isolation booth.

### 3.6 "High background noise level; use an isolated room or close-talk microphone."
- **Cause**: Measured SNR is under 15 dB.
- **Fix**: Ambient noise is too high for reliable acoustic extraction. Use a directional cardioid microphone.

---

## 4. Selecting Source Files for Voice Conversion

When preparing an audio file for `voxclone convert`:
1. Use isolated single-speaker speech without background music, movie sound effects, or laughter.
2. Formats: Standard uncompressed PCM WAV (16 kHz or 24 kHz) yields best results. MP3 and FLAC are automatically transcoded.
3. Overlapping speakers: Ensure no overlapping dialogue; overlapping speakers confuse acoustic pitch extraction.
