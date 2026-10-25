"""Structured JSON Lines rotating file logger."""

from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from typing import Any

from voxclone.config import AppConfig

LOGGER_NAME = "voxclone"


class JsonLinesFormatter(logging.Formatter):
    """Formats log records as JSON lines with UTC timestamps."""

    def format(self, record: logging.LogRecord) -> str:
        # Generate UTC ISO-8601 timestamp with milliseconds and Z
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        ts_str = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        payload: dict[str, Any] = {
            "ts": ts_str,
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
        }

        # Include job_id if present
        if hasattr(record, "job_id"):
            payload["job_id"] = getattr(record, "job_id")

        # Include custom extra fields attached to the record
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            for k, v in record.extra_fields.items():
                if k not in payload:
                    payload[k] = v

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def setup_logging(config: AppConfig) -> None:
    """Initialize rotating file logger for voxclone namespace."""
    config.logs_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = config.logs_dir / "voxclone.log"

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(getattr(logging, config.log_level, logging.INFO))

    # Guard against duplicate handlers on multiple setup_logging calls
    for handler in list(logger.handlers):
        if isinstance(handler, RotatingFileHandler) and handler.baseFilename == str(log_file_path.resolve()):
            return

    # RotatingFileHandler: 5 MB per file, 5 backup generations
    handler = RotatingFileHandler(
        filename=log_file_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(JsonLinesFormatter())
    logger.addHandler(handler)
    logger.propagate = False


def log_event(
    logger: logging.Logger | str,
    level: int | str,
    event: str,
    **fields: Any,
) -> None:
    """Log structured event with key-value fields to JSONL handler."""
    log_obj = logging.getLogger(logger) if isinstance(logger, str) else logger
    lvl = getattr(logging, level.upper()) if isinstance(level, str) else level

    extra = {"event": event, "extra_fields": fields}
    if "job_id" in fields:
        extra["job_id"] = fields["job_id"]

    log_obj.log(lvl, event, extra=extra)


def redact_text(text: str, limit: int = 40) -> str:
    """Privacy helper: Return text truncated to limit (default 40 characters)."""
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit]
