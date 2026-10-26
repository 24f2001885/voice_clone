"""Unit tests for CPU DSP worker functions (pure NumPy/SciPy/librosa, torch-free)."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import soundfile as sf

from voxclone.audio.dsp_workers import postprocess_chunk_worker, prepare_chunk_worker
from voxclone.audio.join import rms


def test_prepare_chunk_worker(tmp_path: Path) -> None:
    """Prepare worker correctly down-mixes, normalizes, resamples, and writes WAV."""
    sr = 24000
    dur_sec = 2.0
    t = np.linspace(0, dur_sec, int(sr * dur_sec), endpoint=False, dtype=np.float32)
    # Stereo signal with DC bias offset
    ch1 = 0.8 * np.sin(2 * np.pi * 440.0 * t) + 0.1
    ch2 = 0.6 * np.sin(2 * np.pi * 220.0 * t) + 0.1
    stereo_audio = np.column_stack([ch1, ch2]).astype(np.float32)

    src_wav = tmp_path / "raw_stereo.wav"
    sf.write(str(src_wav), stereo_audio, sr)

    out_prep_wav = tmp_path / "prepared.wav"
    start_samp = 0
    end_samp = len(stereo_audio)

    meta = prepare_chunk_worker(
        input_path=str(src_wav),
        out_path=str(out_prep_wav),
        start_sample=start_samp,
        end_sample=end_samp,
        target_sr=16000,
    )

    assert Path(meta["out_path"]).is_file()
    assert meta["sample_rate"] == 16000
    assert meta["duration_sec"] > 1.9

    # Verify prepared audio properties
    prep_data, prep_sr = sf.read(str(out_prep_wav), dtype="float32")
    assert prep_sr == 16000
    assert prep_data.ndim == 1  # Mono
    # DC offset removed
    assert abs(float(np.mean(prep_data))) < 0.05
    # Max peak capped <= 0.95
    assert float(np.max(np.abs(prep_data))) <= 0.96


def test_postprocess_chunk_worker(tmp_path: Path) -> None:
    """Postprocess worker matches loudness to reference RMS and writes WAV."""
    sr = 24000
    t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
    # Low-amplitude converted tone (RMS ~0.07)
    conv_audio = (0.1 * np.sin(2 * np.pi * 330.0 * t)).astype(np.float32)
    conv_wav = tmp_path / "conv_raw.wav"
    sf.write(str(conv_wav), conv_audio, sr)

    out_post_wav = tmp_path / "postprocessed.wav"
    target_rms = 0.25

    meta = postprocess_chunk_worker(
        converted_path=str(conv_wav),
        reference_rms=target_rms,
        out_path=str(out_post_wav),
        max_gain_db=12.0,
    )

    assert Path(meta["out_path"]).is_file()
    assert meta["sample_rate"] == sr

    post_data, _ = sf.read(str(out_post_wav), dtype="float32")
    post_rms = rms(post_data)
    # RMS scaled closer to target_rms (within gain clamping bounds)
    assert post_rms > 0.15
    assert float(np.max(np.abs(post_data))) <= 1.0
