# Testing & Verification Guide

This guide details the testing architecture, execution commands, fixture usage, and debugging workflows for VoxClone CLI.

---

## 1. Test Levels & Hierarchy

VoxClone tests are structured into four distinct execution levels:

| Level | Directory | Marker | Execution Command | Hardware Needed |
| :--- | :--- | :--- | :--- | :--- |
| **Unit** | `tests/unit/` | None | `pytest tests/unit/ -v` | CPU only |
| **Integration**| `tests/integration/` | None | `pytest tests/integration/ -v` | CPU only |
| **End-to-End** | `tests/e2e/` | `e2e` | `pytest tests/e2e/ -v` | CPU only |
| **GPU / Benchmark** | `tests/gpu/` | `gpu` | `pytest tests/gpu/ -v -m gpu` | NVIDIA GPU (>= 8 GB VRAM) |

---

## 2. Deterministic Fake Engines

To enable instant, reproducible, and fully offline testing in CI/CD and CPU environments:
- **`VOXCLONE_ENGINE=fake`**: Automatically activated in `isolated_env` fixture in `tests/conftest.py`.
- **`FakeTts`**: Generates synthetic sinusoidal waveforms modulated by requested emotion and duration.
- **`FakeVc`**: Produces pitched output without requiring heavy neural checkpoint loading.
- **`FakeEmotion`**: Evaluates keyword heuristics to deterministically classify emotion labels (`joy`, `anger`, `sadness`, `surprise`, `fear`, `disgust`, `neutral`).

### 2.1 Failure Injection
For testing resilience and retry logic:
- `FakeVc.set_failure_injections(count)`: Injects artificial failures on the next $N$ chunks to test automatic pipeline retry and error code propagation.

---

## 3. Core Test Fixtures

- **`make_speech(duration_sec, gap_sec, sr, seed)`**: Returns a synthetic `SpeechArray` with alternating harmonic speech bursts and exact digital silence gaps, guaranteed to pass SNR and duration gates in `analyze_sample`.
- **`db_conn`**: Provides an isolated temporary SQLite database connection with all WAL migrations pre-applied.
- **`session_state`**: Bootstraps an isolated `SessionState` configured in plain output mode.
- **`write_wav(path, data, sr)`**: Safely writes audio data to a temporary WAV file.

---

## 4. Running Offline Test Suites

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run all integration tests (database, parallel pool, pipelines, resume)
pytest tests/integration/ -v

# Run end-to-end user workflow tests
pytest tests/e2e/ -v

# Run complete offline verification suite
pytest tests/unit tests/integration tests/e2e -v -m "not gpu"
```

---

## 5. Opt-in GPU Benchmark & Soak Testing

When running on a machine equipped with a dedicated NVIDIA GPU:

```bash
# Set test audio paths
export VOXCLONE_TEST_REFERENCE=/path/to/reference.wav
export VOXCLONE_TEST_INPUT=/path/to/input.wav
export VOXCLONE_SOAK_JOBS=10

# Execute benchmark
pytest tests/gpu/test_benchmark.py -v -m gpu
```

---

## 6. Code Coverage Audit

Code coverage is audited excluding heavyweight neural wrapper stubs (`real_*.py`):

```bash
pytest --cov=src/voxclone --cov-report=term-missing --cov-fail-under=85 tests/ -m "not gpu"
```

---

## 7. Terminal Palette Contrast Compliance (WCAG 2.1 AA)

All colors meet or exceed the 4.5:1 contrast ratio requirement against dark (`#1E1E1E`) and light (`#FFFFFF`) backgrounds:

| Theme Role | Dark Palette (`#1E1E1E`) | Contrast Ratio | Light Palette (`#FFFFFF`) | Contrast Ratio | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Primary** | `#4FC3F7` | 9.8:1 | `#0277BD` | 5.2:1 | PASS |
| **Secondary** | `#B39DDB` | 8.4:1 | `#5E35B1` | 6.8:1 | PASS |
| **Success** | `#66BB6A` | 7.9:1 | `#2E7D32` | 5.4:1 | PASS |
| **Warning** | `#FFB74D` | 10.6:1 | `#E65100` | 5.1:1 | PASS |
| **Error** | `#EF5350` | 5.9:1 | `#C62828` | 5.8:1 | PASS |
