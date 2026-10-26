# Software and Model Licenses

This document records the licenses, origins, and commercial terms for all third-party software libraries and pre-trained neural network weights utilized by VoxClone CLI.

---

## 1. Runtime Software Dependencies

| Component | License | Source / Repository | Commercial Use Allowed | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **PyTorch (`torch`, `torchaudio`)** | BSD-3-Clause | https://github.com/pytorch/pytorch | Yes | Core tensor compute & DSP operations |
| **Hugging Face Transformers** | Apache-2.0 | https://github.com/huggingface/transformers | Yes | Neural model definitions & tokenizers |
| **Hugging Face Hub** | Apache-2.0 | https://github.com/huggingface/huggingface_hub | Yes | Model weight downloading & caching |
| **NumPy** | BSD-3-Clause | https://github.com/numpy/numpy | Yes | Numerical array manipulation |
| **SciPy** | BSD-3-Clause | https://github.com/scipy/scipy | Yes | Scientific computing & signal processing |
| **librosa** | ISC | https://github.com/librosa/librosa | Yes | Speech analysis & silence detection |
| **SoundFile** | BSD-3-Clause | https://github.com/bastibe/python-soundfile | Yes | C-bindings to libsndfile audio I/O |
| **sounddevice** | MIT | https://github.com/spatialaudio/python-sounddevice | Yes | Cross-platform PortAudio bindings |
| **Rich** | MIT | https://github.com/Textualize/rich | Yes | Terminal styling, tables, & status badges |
| **Typer** | MIT | https://github.com/tiangolo/typer | Yes | CLI option parsing & command routing |
| **Questionary** | MIT | https://github.com/tmbo/questionary | Yes | Interactive dropdown prompts |
| **prompt_toolkit** | BSD-3-Clause | https://github.com/prompt-toolkit/python-prompt-toolkit | Yes | Terminal interactive engine |
| **Platformdirs** | MIT | https://github.com/platformdirs/platformdirs | Yes | OS-specific cache and configuration paths |

---

## 2. Neural Model Checkpoints & Weights

| Model Key | Repository | Author / Org | License | Commercial Terms |
| :--- | :--- | :--- | :--- | :--- |
| **`tts`** | `hexgrad/Kokoro-82M` | Hexgrad | Apache-2.0 | Permitted under Apache 2.0 conditions |
| **`vc`** | `OlaWod/FreeVC` | OlaWod / FreeVC Contributors | MIT | Permitted under MIT terms |
| **`emotion`** | `j-hartmann/emotion-english-distilroberta-base` | Jochen Hartmann | Apache-2.0 | Permitted with attribution |

*All licenses verified against official Hugging Face model cards as of October 2026.*

---

## 3. Development & Testing Tools

| Tool | License | Purpose |
| :--- | :--- | :--- |
| **pytest** | MIT | Unit, integration, and e2e test execution |
| **pytest-cov** | MIT | Code coverage auditing |
| **flake8** | MIT | PEP-8 linting |
| **black** | MIT | Deterministic code formatting |
| **mypy** | MIT | Static typing validation |

---

## 4. Responsible AI & Attribution Notice

VoxClone is distributed under the MIT License. Users are strictly required to observe ethical synthetic speech practices:
1. Do not clone any individual's voice without verifiable, explicit consent.
2. Comply with local regulations governing synthetic audio disclosure and provenance.
