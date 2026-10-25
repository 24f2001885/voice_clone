"""Fixed values, enums, limits, and configuration defaults for VoxClone CLI."""

from typing import Any

APP_NAME: str = "VoxClone CLI"

# Model keys and actions
MODEL_KEYS: tuple[str, ...] = ("tts", "vc", "emotion")
MODEL_ACTIONS: tuple[str, ...] = ("load", "unload", "oom")

# Job enumeration constants
JOB_TYPES: tuple[str, ...] = ("text_to_voice", "recording_to_voice")
JOB_STATUSES: tuple[str, ...] = ("queued", "running", "succeeded", "failed", "cancelled")
INPUT_SOURCES: tuple[str, ...] = ("text", "file", "mic")
OUTPUT_MODES: tuple[str, ...] = ("save", "play", "both")

# Chunk processing enums
CHUNK_KINDS: tuple[str, ...] = ("sentence", "audio")
CHUNK_STATUSES: tuple[str, ...] = ("pending", "prepared", "converted", "failed")

# Profile sources
PROFILE_SOURCES: tuple[str, ...] = ("file", "mic")

# Emotion definitions
EMOTION_MODES: tuple[str, ...] = ("auto", "calm", "normal", "expressive")
EMOTION_LABELS: tuple[str, ...] = (
    "neutral",
    "joy",
    "sadness",
    "anger",
    "fear",
    "surprise",
    "disgust",
)

# Emotion label to synthesis expressiveness mapping (TDR 3.8)
EMOTION_TO_EXPRESSIVENESS: dict[str, float] = {
    "neutral": 0.40,
    "sadness": 0.30,
    "joy": 0.70,
    "fear": 0.70,
    "disgust": 0.70,
    "surprise": 0.80,
    "anger": 0.90,
}

# Emotion preset mode to expressiveness mapping
EMOTION_MODE_TO_EXPRESSIVENESS: dict[str, float] = {
    "calm": 0.30,
    "normal": 0.50,
    "expressive": 0.80,
}

# Default settings stored in SQLite app_settings table
DEFAULT_SETTINGS: dict[str, Any] = {
    "device": "auto",
    "workers": 0,
    "chunk_min_sec": 3.0,
    "chunk_max_sec": 5.0,
    "crossfade_ms": 30,
    "default_output_mode": "both",
    "keep_warm": True,
    "vram_budget_mb": 6000,
    "sentence_max_chars": 200,
}

# System limits and operational bounds
PROFILE_NAME_PATTERN: str = r"^[A-Za-z0-9_-]{1,64}$"
MIN_SAMPLE_SPEECH_SEC: float = 10.0
TARGET_SAMPLE_SEC: tuple[float, float] = (20.0, 30.0)
REFERENCE_SAMPLE_RATE: int = 24000
CHUNK_ANALYSIS_SAMPLE_RATE: int = 16000
CHUNK_TAIL_MIN_SEC: float = 1.0
MAX_TEXT_CHARS: int = 20000
WORK_DIR_MAX_AGE_HOURS: int = 24
CHUNK_ROW_RETENTION_DAYS: int = 30
MODEL_EVENT_RETENTION_DAYS: int = 90
WORKER_RAM_MB: int = 250
RAM_RESERVE_MB: int = 2048
