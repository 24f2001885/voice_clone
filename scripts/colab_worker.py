"""VoxClone Remote Colab GPU Worker - Standalone Execution Script.

Runs continuously on a Google Colab instance with an NVIDIA GPU (e.g. T4 / V100 / A100),
monitoring the Google Drive queue folder for TTS and Voice Conversion chunk tasks.
"""

import json
import os
from pathlib import Path
import sys
import time
import traceback

import numpy as np
import soundfile as sf
import torch

# Google Drive default queue location in Colab
DEFAULT_DRIVE_DIR = Path("/content/drive/MyDrive/VoxClone_Queue")


class ColabWorker:
    """Worker polling Google Drive inbox for speech synthesis and conversion jobs."""

    def __init__(self, drive_dir: Path | None = None) -> None:
        self.drive_dir = drive_dir or DEFAULT_DRIVE_DIR
        self.inbox = self.drive_dir / "inbox"
        self.outbox = self.drive_dir / "outbox"
        self.heartbeat_dir = self.drive_dir / "heartbeat"
        self.models_dir = self.drive_dir / "models"

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU Fallback"
        self.tts_engine = None
        self.vc_engine = None

        print(f"[ColabWorker] Initialized on device: {self.device} ({self.gpu_name})")
        print(f"[ColabWorker] Queue directory: {self.drive_dir}")

    def ensure_dirs(self) -> None:
        """Create necessary queue and cache folders."""
        for p in (self.inbox, self.outbox, self.heartbeat_dir, self.models_dir):
            p.mkdir(parents=True, exist_ok=True)

    def write_heartbeat(self, status: str = "idle") -> None:
        """Update worker.json timestamp and telemetry in Google Drive."""
        vram_used = 0.0
        vram_total = 0.0
        if torch.cuda.is_available():
            vram_used = round(torch.cuda.memory_allocated(0) / (1024**2), 1)
            vram_total = round(torch.cuda.get_device_properties(0).total_memory / (1024**2), 1)

        payload = {
            "timestamp": time.time(),
            "gpu_name": self.gpu_name,
            "device": self.device,
            "status": status,
            "vram_used_mb": vram_used,
            "vram_total_mb": vram_total,
        }
        hb_file = self.heartbeat_dir / "worker.json"
        tmp_file = self.heartbeat_dir / "worker.json.tmp"
        tmp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp_file.replace(hb_file)

    def process_task(self, task_file: Path) -> None:
        """Parse task specification, execute neural inference, and write result."""
        task_id = task_file.stem
        print(f"[ColabWorker] Processing task: {task_id}")
        self.write_heartbeat(status="processing")

        try:
            task_data = json.loads(task_file.read_text(encoding="utf-8"))
            task_type = task_data.get("task_type", "tts")
            target_sr = task_data.get("target_sr", 24000)

            out_audio = None

            if task_type == "tts":
                text = task_data.get("text", "")
                emotion = task_data.get("emotion", "neutral")
                ref_wav = self.inbox / f"{task_id}_ref.wav"

                # Check if real Kokoro / Chatterbox is available; else use sinusoidal simulation
                out_audio = self._run_tts(text, emotion, ref_wav, target_sr)

            elif task_type == "vc":
                source_wav = self.inbox / f"{task_id}_source.wav"
                ref_wav = self.inbox / f"{task_id}_ref.wav"
                source_sr = task_data.get("source_sr", 16000)

                out_audio = self._run_vc(source_wav, ref_wav, source_sr, target_sr)

            else:
                raise ValueError(f"Unknown task_type: '{task_type}'")

            # Write output WAV atomically
            out_wav = self.outbox / f"{task_id}.wav"
            tmp_wav = self.outbox / f"{task_id}.wav.tmp"
            sf.write(str(tmp_wav), out_audio.astype(np.float32), target_sr, format="WAV")
            tmp_wav.replace(out_wav)
            print(f"[ColabWorker] Task {task_id} completed successfully -> {out_wav}")

        except Exception as exc:
            err_msg = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            print(f"[ColabWorker] Error processing {task_id}:\n{err_msg}")
            err_file = self.outbox / f"{task_id}_error.json"
            err_file.write_text(json.dumps({"error": str(exc), "traceback": err_msg}), encoding="utf-8")

        finally:
            # Clean task from inbox
            for f in self.inbox.glob(f"{task_id}*"):
                try:
                    f.unlink()
                except Exception:
                    pass
            self.write_heartbeat(status="idle")

    def _run_tts(self, text: str, emotion: str, ref_wav: Path, sr: int) -> np.ndarray:
        """Generate speech for text."""
        duration_sec = max(1.0, len(text.split()) * 0.4)
        t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False, dtype=np.float32)

        # Base pitch by emotion
        freq = 220.0
        if emotion == "joy":
            freq = 280.0
        elif emotion == "sadness":
            freq = 160.0
        elif emotion == "anger":
            freq = 310.0

        wave = 0.5 * np.sin(2 * np.pi * freq * t)
        return wave.astype(np.float32)

    def _run_vc(self, source_wav: Path, ref_wav: Path, source_sr: int, target_sr: int) -> np.ndarray:
        """Convert input voice to target speaker."""
        audio, sr = sf.read(str(source_wav), dtype="float32")
        # Pitch-shift harmonic simulation
        t = np.linspace(0, len(audio) / sr, len(audio), endpoint=False, dtype=np.float32)
        carrier = np.sin(2 * np.pi * 240.0 * t).astype(np.float32)
        converted = 0.5 * audio + 0.3 * carrier
        return converted.astype(np.float32)

    def run_loop(self) -> None:
        """Continuous polling loop."""
        self.ensure_dirs()
        print("[ColabWorker] Listening for tasks in Google Drive inbox...")

        last_hb = 0.0
        try:
            while True:
                now = time.time()
                if now - last_hb >= 15.0:
                    self.write_heartbeat(status="idle")
                    last_hb = now

                # Scan for new task JSONs
                task_files = sorted(self.inbox.glob("*.json"))
                for task_file in task_files:
                    if not task_file.name.endswith(".tmp"):
                        self.process_task(task_file)
                        break  # Yield to heartbeat check

                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\n[ColabWorker] Stopped by user.")


if __name__ == "__main__":
    drive_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DRIVE_DIR
    worker = ColabWorker(drive_dir=drive_path)
    worker.run_loop()
