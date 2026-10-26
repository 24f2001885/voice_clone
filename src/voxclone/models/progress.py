"""Progress tracking and inter-pipeline handoff context."""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from voxclone.config import AppConfig
from voxclone.errors import InternalError
from voxclone.models.job import Job, JobResult
from voxclone.models.profile import VoiceProfile

STAGES = (
    "split",
    "preparing",
    "loading_model",
    "emotion",
    "synthesizing",
    "converting",
    "postprocessing",
    "joining",
    "writing",
    "playing",
    "done",
    "failed",
    "cancelled",
)


@dataclass(frozen=True)
class ProgressEvent:
    """Progress update emitted during pipeline execution."""
    stage: str
    chunk_index: int | None = None
    total_chunks: int | None = None
    message: str = ""
    result: JobResult | None = None
    payload: Any = None

    def __post_init__(self) -> None:
        if self.stage not in STAGES:
            raise InternalError(
                f"Unknown progress event stage: '{self.stage}'. Must be one of {STAGES}",
            )


@dataclass
class PipelineOutput:
    """Audio data and metadata emitted by pipeline core execution."""
    audio: np.ndarray
    sample_rate: int
    total_chunks: int


@dataclass
class PipelineContext:
    """Execution context injected into pipelines by JobService."""
    job: Job
    profile: VoiceProfile
    config: AppConfig
    conn: sqlite3.Connection
    model_manager: Any
    settings: dict[str, Any]
    cancel_event: threading.Event = field(default_factory=threading.Event)
    reference_path: Path = field(default_factory=Path)
    backend: str = "local"
    drive_dir: Path | None = None
