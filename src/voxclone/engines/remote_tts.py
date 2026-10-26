"""Remote TTS Engine adapter delegating synthesis to Google Colab T4 GPU via Google Drive."""

from pathlib import Path
import uuid

import numpy as np

from voxclone.constants import REFERENCE_SAMPLE_RATE
from voxclone.transport.drive_queue import (
    check_worker_heartbeat,
    poll_result,
    submit_task,
)


class RemoteTts:
    """TTS Engine adapter submitting chunk synthesis tasks to Google Colab via Google Drive queue."""

    key: str = "remote_tts"

    def __init__(self, drive_dir: Path, timeout_sec: float = 120.0) -> None:
        self.drive_dir = drive_dir
        self.timeout_sec = timeout_sec
        self.is_loaded = False
        self.device = "remote_drive"

    def load(self, device: str = "remote_drive") -> None:
        """Verify Google Drive queue connectivity and worker heartbeat."""
        check_worker_heartbeat(self.drive_dir)
        self.is_loaded = True
        self.device = device

    def synthesize(
        self,
        text: str,
        reference_audio: np.ndarray,
        reference_text: str | None = None,
        emotion: str | None = None,
    ) -> np.ndarray:
        """Offload text synthesis task to remote Colab GPU worker."""
        if not self.is_loaded:
            self.load()

        task_id = f"tts_{uuid.uuid4().hex[:12]}"
        payload = {
            "text": text,
            "reference_text": reference_text or "",
            "emotion": emotion or "neutral",
            "target_sr": REFERENCE_SAMPLE_RATE,
        }
        audio_files = {
            "ref": (reference_audio, REFERENCE_SAMPLE_RATE),
        }

        submit_task(
            drive_dir=self.drive_dir,
            task_id=task_id,
            task_type="tts",
            payload=payload,
            audio_files=audio_files,
        )

        audio, _ = poll_result(
            drive_dir=self.drive_dir,
            task_id=task_id,
            timeout_sec=self.timeout_sec,
        )
        return audio.astype(np.float32)

    def unload(self) -> None:
        """No-op for remote execution."""
        self.is_loaded = False
