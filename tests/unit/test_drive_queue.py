"""Unit tests for the Google Drive queue transport layer (P7)."""

import json
from pathlib import Path
import threading
import time

import numpy as np
import pytest

from voxclone.errors import (
    RemoteDriveNotMountedError,
    RemoteQueueTimeoutError,
    RemoteWorkerInternalError,
    RemoteWorkerOfflineError,
)
from voxclone.transport.drive_queue import (
    check_worker_heartbeat,
    cleanup_task,
    ensure_queue_dirs,
    get_queue_stats,
    poll_result,
    submit_task,
    write_heartbeat,
)


def test_ensure_queue_dirs(tmp_path: Path) -> None:
    """Verify queue directories are created cleanly."""
    drive_dir = tmp_path / "DriveQueue"
    inbox, outbox, heartbeat = ensure_queue_dirs(drive_dir)

    assert inbox.is_dir()
    assert outbox.is_dir()
    assert heartbeat.is_dir()


def test_heartbeat_not_mounted(tmp_path: Path) -> None:
    """Missing Google Drive path raises RemoteDriveNotMountedError (VX-322)."""
    non_existent = tmp_path / "non_existent_folder"
    with pytest.raises(RemoteDriveNotMountedError) as exc_info:
        check_worker_heartbeat(non_existent)
    assert exc_info.value.code == "VX-322"


def test_heartbeat_missing_worker_file(tmp_path: Path) -> None:
    """Missing worker.json raises RemoteWorkerOfflineError (VX-320)."""
    drive_dir = tmp_path / "DriveQueue"
    ensure_queue_dirs(drive_dir)

    with pytest.raises(RemoteWorkerOfflineError) as exc_info:
        check_worker_heartbeat(drive_dir)
    assert exc_info.value.code == "VX-320"


def test_heartbeat_stale_detection(tmp_path: Path) -> None:
    """Heartbeat older than max_age_sec raises RemoteWorkerOfflineError."""
    drive_dir = tmp_path / "DriveQueue"
    _, _, hb_dir = ensure_queue_dirs(drive_dir)

    old_hb = {
        "timestamp": time.time() - 300.0,
        "gpu_name": "Tesla T4",
        "status": "idle",
    }
    (hb_dir / "worker.json").write_text(json.dumps(old_hb), encoding="utf-8")

    with pytest.raises(RemoteWorkerOfflineError) as exc_info:
        check_worker_heartbeat(drive_dir, max_age_sec=60.0)
    assert exc_info.value.code == "VX-320"
    assert "stale" in str(exc_info.value)


def test_heartbeat_fresh_success(tmp_path: Path) -> None:
    """Fresh heartbeat returns metadata dictionary."""
    drive_dir = tmp_path / "DriveQueue"
    write_heartbeat(drive_dir, gpu_name="Tesla T4", status="idle", vram_used_mb=2048.0)

    data = check_worker_heartbeat(drive_dir, max_age_sec=60.0)
    assert data["gpu_name"] == "Tesla T4"
    assert data["status"] == "idle"
    assert data["vram_used_mb"] == 2048.0
    assert data["heartbeat_age_sec"] < 5.0


def test_submit_and_poll_task_success(tmp_path: Path) -> None:
    """Task submission writes inbox files and poll_result retrieves outbox audio."""
    drive_dir = tmp_path / "DriveQueue"
    task_id = "test_task_001"
    ref_audio = np.ones(16000, dtype=np.float32) * 0.1

    submit_task(
        drive_dir=drive_dir,
        task_id=task_id,
        task_type="tts",
        payload={"text": "Hello world"},
        audio_files={"ref": (ref_audio, 16000)},
    )

    stats = get_queue_stats(drive_dir)
    assert stats["inbox_count"] == 1

    # Simulate worker producing output
    outbox = drive_dir / "outbox"
    out_audio = np.sin(np.linspace(0, 1.0, 24000, dtype=np.float32)).astype(np.float32)
    import soundfile as sf

    sf.write(str(outbox / f"{task_id}.wav"), out_audio, 24000)

    received_audio, sr = poll_result(drive_dir, task_id, timeout_sec=5.0)
    assert sr == 24000
    assert len(received_audio) == 24000

    # Ensure cleanup
    stats_after = get_queue_stats(drive_dir)
    assert stats_after["inbox_count"] == 0
    assert stats_after["outbox_count"] == 0


def test_poll_task_timeout(tmp_path: Path) -> None:
    """Unfulfilled task raises RemoteQueueTimeoutError (VX-321)."""
    drive_dir = tmp_path / "DriveQueue"
    ensure_queue_dirs(drive_dir)

    with pytest.raises(RemoteQueueTimeoutError) as exc_info:
        poll_result(drive_dir, "non_existent_task", timeout_sec=0.5, poll_interval_sec=0.1)
    assert exc_info.value.code == "VX-321"


def test_poll_task_worker_error(tmp_path: Path) -> None:
    """Worker error report in outbox raises RemoteWorkerInternalError (VX-323)."""
    drive_dir = tmp_path / "DriveQueue"
    _, outbox, _ = ensure_queue_dirs(drive_dir)

    task_id = "failing_task"
    err_report = {"error": "CUDA out of memory during neural synthesis"}
    (outbox / f"{task_id}_error.json").write_text(json.dumps(err_report), encoding="utf-8")

    with pytest.raises(RemoteWorkerInternalError) as exc_info:
        poll_result(drive_dir, task_id, timeout_sec=2.0)
    assert exc_info.value.code == "VX-323"
    assert "CUDA out of memory" in str(exc_info.value)
