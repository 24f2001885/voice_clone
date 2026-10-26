"""Integration tests for RemoteTts and RemoteVc engine adapters with simulated Colab worker."""

import json
from pathlib import Path
import threading
import time

import numpy as np
import pytest
import soundfile as sf

from voxclone.engines.remote_tts import RemoteTts
from voxclone.engines.remote_vc import RemoteVc
from voxclone.errors import RemoteWorkerOfflineError
from voxclone.transport.drive_queue import ensure_queue_dirs, write_heartbeat


def _run_mock_colab_worker(drive_dir: Path, stop_event: threading.Event) -> None:
    """Mock worker thread simulating Google Colab T4 worker."""
    inbox, outbox, _ = ensure_queue_dirs(drive_dir)

    while not stop_event.is_set():
        # Keep heartbeat fresh
        write_heartbeat(drive_dir, gpu_name="Tesla T4 (Mock)", status="idle")

        tasks = list(inbox.glob("*.json"))
        for t in tasks:
            if t.name.endswith(".tmp"):
                continue
            task_id = t.stem
            try:
                task_data = json.loads(t.read_text(encoding="utf-8"))
                sr = task_data.get("target_sr", 24000)
                # Generate simple sine wave output
                dur = 1.0
                out_audio = (0.4 * np.sin(2 * np.pi * 330.0 * np.linspace(0, dur, int(sr * dur), dtype=np.float32))).astype(np.float32)

                out_wav = outbox / f"{task_id}.wav"
                sf.write(str(out_wav), out_audio, sr)
            finally:
                for f in inbox.glob(f"{task_id}*"):
                    try:
                        f.unlink()
                    except Exception:
                        pass
        time.sleep(0.05)


def test_remote_tts_synthesis(tmp_path: Path) -> None:
    """Verify RemoteTts adapter interacts with Drive queue and returns valid audio."""
    drive_dir = tmp_path / "ColabDrive"
    stop_event = threading.Event()
    worker_thread = threading.Thread(target=_run_mock_colab_worker, args=(drive_dir, stop_event), daemon=True)
    worker_thread.start()

    try:
        # Allow worker to write initial heartbeat
        time.sleep(0.1)

        engine = RemoteTts(drive_dir=drive_dir, timeout_sec=5.0)
        ref_audio = np.zeros(24000, dtype=np.float32)
        result_audio = engine.synthesize(text="Hello from AMD APU", reference_audio=ref_audio, emotion="joy")

        assert isinstance(result_audio, np.ndarray)
        assert len(result_audio) > 0
        assert np.max(np.abs(result_audio)) > 0.01

    finally:
        stop_event.set()
        worker_thread.join(timeout=1.0)


def test_remote_vc_conversion(tmp_path: Path) -> None:
    """Verify RemoteVc adapter interacts with Drive queue and returns valid audio."""
    drive_dir = tmp_path / "ColabDrive"
    stop_event = threading.Event()
    worker_thread = threading.Thread(target=_run_mock_colab_worker, args=(drive_dir, stop_event), daemon=True)
    worker_thread.start()

    try:
        time.sleep(0.1)

        engine = RemoteVc(drive_dir=drive_dir, timeout_sec=5.0)
        source_audio = np.ones(16000, dtype=np.float32) * 0.2
        ref_audio = np.ones(24000, dtype=np.float32) * 0.3
        result_audio = engine.convert(source_audio=source_audio, reference_audio=ref_audio, source_sr=16000)

        assert isinstance(result_audio, np.ndarray)
        assert len(result_audio) > 0

    finally:
        stop_event.set()
        worker_thread.join(timeout=1.0)


def test_remote_tts_offline_worker_rejected(tmp_path: Path) -> None:
    """Attempting remote synthesis without active worker heartbeat raises RemoteWorkerOfflineError."""
    drive_dir = tmp_path / "EmptyDrive"
    ensure_queue_dirs(drive_dir)

    engine = RemoteTts(drive_dir=drive_dir, timeout_sec=2.0)
    ref_audio = np.zeros(16000, dtype=np.float32)

    with pytest.raises(RemoteWorkerOfflineError) as exc_info:
        engine.synthesize(text="Test offline", reference_audio=ref_audio)
    assert exc_info.value.code == "VX-320"
