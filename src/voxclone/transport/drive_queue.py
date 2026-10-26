"""Google Drive file queue transport layer for decoupled remote GPU inference."""

import json
from pathlib import Path
import threading
import time
from typing import Any

import numpy as np
import soundfile as sf

from voxclone.errors import (
    RemoteDriveNotMountedError,
    RemoteQueueTimeoutError,
    RemoteWorkerInternalError,
    RemoteWorkerOfflineError,
)


def ensure_queue_dirs(drive_dir: Path) -> tuple[Path, Path, Path]:
    """Ensure inbox, outbox, and heartbeat directories exist in the Drive folder."""
    if not drive_dir.exists():
        try:
            drive_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            raise RemoteDriveNotMountedError(
                f"Cannot create or access Google Drive folder: {drive_dir}. ({exc!s})",
                hint="Ensure your local Google Drive folder is synced or select a valid local path.",
            ) from exc

    inbox = drive_dir / "inbox"
    outbox = drive_dir / "outbox"
    heartbeat = drive_dir / "heartbeat"
    inbox.mkdir(parents=True, exist_ok=True)
    outbox.mkdir(parents=True, exist_ok=True)
    heartbeat.mkdir(parents=True, exist_ok=True)
    return inbox, outbox, heartbeat


def check_worker_heartbeat(drive_dir: Path, max_age_sec: float = 180.0) -> dict[str, Any]:
    """Inspect the Colab worker heartbeat file and verify it is recent and alive."""
    if not drive_dir.is_dir():
        raise RemoteDriveNotMountedError(
            f"Google Drive directory not found: {drive_dir}",
            hint="Mount Google Drive or set VOXCLONE_DRIVE_DIR to your local Drive mirror.",
        )

    hb_file = drive_dir / "heartbeat" / "worker.json"
    if not hb_file.exists():
        raise RemoteWorkerOfflineError(
            "Remote Colab GPU worker is offline; no heartbeat detected in Google Drive.",
            hint="Open scripts/colab_worker.ipynb in Google Colab and run all cells.",
        )

    try:
        data = json.loads(hb_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RemoteWorkerOfflineError(
            f"Failed to read Colab worker heartbeat file: {exc!s}",
            hint="Restart the Colab worker notebook.",
        ) from exc

    timestamp = data.get("timestamp", 0)
    now = time.time()
    age = now - timestamp
    if age > max_age_sec:
        raise RemoteWorkerOfflineError(
            f"Colab GPU worker heartbeat is stale ({age:.0f}s old, limit {max_age_sec:.0f}s).",
            hint="Verify Google Colab session is active and has not disconnected.",
        )

    data["heartbeat_age_sec"] = age
    return data


def write_heartbeat(
    drive_dir: Path,
    gpu_name: str = "NVIDIA T4",
    status: str = "idle",
    vram_used_mb: float = 0.0,
    vram_total_mb: float = 15360.0,
) -> None:
    """Write heartbeat file from worker side (used by Colab worker or test doubles)."""
    _, _, hb_dir = ensure_queue_dirs(drive_dir)
    hb_file = hb_dir / "worker.json"
    payload = {
        "timestamp": time.time(),
        "gpu_name": gpu_name,
        "status": status,
        "vram_used_mb": vram_used_mb,
        "vram_total_mb": vram_total_mb,
    }
    tmp_file = hb_dir / "worker.json.tmp"
    tmp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_file.replace(hb_file)


def submit_task(
    drive_dir: Path,
    task_id: str,
    task_type: str,
    payload: dict[str, Any],
    audio_files: dict[str, tuple[np.ndarray, int]] | None = None,
) -> None:
    """Submit an inference task to the Google Drive inbox using atomic file writes.

    Args:
        drive_dir: Root Google Drive queue path.
        task_id: Unique task identifier (e.g. "{job_id}_{chunk_index}").
        task_type: "tts" or "vc".
        payload: Parameters such as text, emotion, pitch, speed, sample rate.
        audio_files: Mapping of filename prefix -> (1D numpy array, sample_rate).
    """
    inbox, _, _ = ensure_queue_dirs(drive_dir)

    # 1. Write audio payload files atomically
    if audio_files:
        for prefix, (arr, sr) in audio_files.items():
            wav_path = inbox / f"{task_id}_{prefix}.wav"
            tmp_wav = inbox / f"{task_id}_{prefix}.wav.tmp"
            sf.write(str(tmp_wav), arr.astype(np.float32), sr, format="WAV")
            tmp_wav.replace(wav_path)

    # 2. Write metadata JSON task file atomically
    meta = {
        "task_id": task_id,
        "task_type": task_type,
        "submitted_at": time.time(),
        **payload,
    }
    json_path = inbox / f"{task_id}.json"
    tmp_json = inbox / f"{task_id}.json.tmp"
    tmp_json.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    tmp_json.replace(json_path)


def poll_result(
    drive_dir: Path,
    task_id: str,
    timeout_sec: float = 120.0,
    poll_interval_sec: float = 0.5,
    cancel_event: threading.Event | None = None,
) -> tuple[np.ndarray, int]:
    """Poll the Google Drive outbox folder for task completion.

    Args:
        drive_dir: Root Google Drive queue path.
        task_id: Task identifier matching submitted task.
        timeout_sec: Maximum wait time in seconds.
        poll_interval_sec: Polling check period.
        cancel_event: Optional threading cancel signal.

    Returns:
        tuple of (float32 numpy array audio, sample_rate).

    Raises:
        RemoteQueueTimeoutError: If result is not produced within timeout.
        RemoteWorkerInternalError: If remote worker wrote an error report.
    """
    _, outbox, _ = ensure_queue_dirs(drive_dir)
    out_wav = outbox / f"{task_id}.wav"
    err_json = outbox / f"{task_id}_error.json"

    deadline = time.time() + timeout_sec

    while time.time() < deadline:
        if cancel_event and cancel_event.is_set():
            cleanup_task(drive_dir, task_id)
            raise RemoteQueueTimeoutError(f"Task {task_id} canceled while waiting for remote GPU.")

        # Check for remote worker error
        if err_json.exists():
            try:
                err_data = json.loads(err_json.read_text(encoding="utf-8"))
                msg = err_data.get("error", "Unknown worker error")
            except Exception:
                msg = "Remote worker failure report"
            cleanup_task(drive_dir, task_id)
            raise RemoteWorkerInternalError(
                f"Colab worker failed on task {task_id}: {msg}",
                hint="Check GPU logs in Google Colab worker notebook.",
            )

        # Check for output WAV
        if out_wav.exists() and out_wav.stat().st_size > 44:  # At least valid WAV header
            # Wait brief moment to guarantee write flush
            time.sleep(0.1)
            try:
                audio, sr = sf.read(str(out_wav), dtype="float32")
                cleanup_task(drive_dir, task_id)
                return audio, int(sr)
            except Exception:
                # File may still be flushing from Drive sync
                time.sleep(poll_interval_sec)
                continue

        time.sleep(poll_interval_sec)

    cleanup_task(drive_dir, task_id)
    raise RemoteQueueTimeoutError(
        f"Timed out after {timeout_sec:.0f}s waiting for Colab GPU worker response ({task_id}).",
        hint="Check if the Google Colab session is still running or experiencing high load.",
    )


def cleanup_task(drive_dir: Path, task_id: str) -> None:
    """Remove all temporary inbox and outbox files associated with a task."""
    inbox = drive_dir / "inbox"
    outbox = drive_dir / "outbox"

    for folder in (inbox, outbox):
        if folder.exists():
            for f in folder.glob(f"{task_id}*"):
                try:
                    f.unlink()
                except Exception:
                    pass


def get_queue_stats(drive_dir: Path) -> dict[str, int]:
    """Retrieve queue length counts for inbox and outbox."""
    if not drive_dir.exists():
        return {"inbox_count": 0, "outbox_count": 0}

    inbox = drive_dir / "inbox"
    outbox = drive_dir / "outbox"

    inbox_count = len(list(inbox.glob("*.json"))) if inbox.exists() else 0
    outbox_count = len(list(outbox.glob("*.wav"))) if outbox.exists() else 0
    return {
        "inbox_count": inbox_count,
        "outbox_count": outbox_count,
    }
