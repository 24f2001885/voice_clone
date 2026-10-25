"""Filesystem layout, safe path resolution, and storage utilities."""

from datetime import datetime, timezone
import os
from pathlib import Path
import shutil

from voxclone.config import AppConfig
from voxclone.errors import InternalError


def ensure_data_layout(config: AppConfig) -> None:
    """Ensure all required runtime data directories exist with appropriate permissions."""
    directories = [
        config.data_dir,
        config.profiles_dir,
        config.outputs_dir,
        config.inputs_dir,
        config.work_dir,
        config.logs_dir,
    ]

    for d in directories:
        d.mkdir(parents=True, exist_ok=True)

    # Restrict permissions on sensitive directories (0700: user rwx only)
    sensitive_dirs = [config.data_dir, config.profiles_dir, config.outputs_dir]
    for s_dir in sensitive_dirs:
        try:
            s_dir.chmod(0o700)
        except OSError:
            # Tolerated on platforms (e.g., Windows NTFS) that do not support POSIX mode bits
            pass


def safe_join(base: Path, *parts: str | Path) -> Path:
    """Safely join subpaths to base and ensure the resolved path does not escape base."""
    resolved_base = base.resolve()
    candidate = resolved_base
    for part in parts:
        candidate = candidate / part
    resolved_target = candidate.resolve()

    try:
        # Raises ValueError if resolved_target is not relative to resolved_base
        resolved_target.relative_to(resolved_base)
    except ValueError as exc:
        raise InternalError(
            f"Path traversal detected: '{candidate}' escapes base '{base}'.",
            hint="Do not use '../' or absolute paths that escape storage roots.",
        ) from exc

    return resolved_target


def job_work_dir(config: AppConfig, job_id: str) -> Path:
    """Return the work directory path for a specific job."""
    return safe_join(config.work_dir, job_id)


def build_output_path(
    config: AppConfig,
    job_type: str,
    profile_name: str,
    now: datetime | None = None,
) -> Path:
    """Generate a sanitized, unique output filename for a completed voice conversion job."""
    prefix = "text" if job_type == "text_to_voice" else "recording"
    ts = datetime.now(timezone.utc) if now is None else now
    ts_str = ts.strftime("%Y%m%d_%H%M%S")

    # Sanitize profile_name: alphanumeric and underscore only
    safe_profile = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in profile_name)
    base_name = f"{prefix}_{safe_profile}_{ts_str}"

    target_path = safe_join(config.outputs_dir, f"{base_name}.wav")
    if not target_path.exists():
        return target_path

    # Handle collision with incremental numeric suffix
    counter = 1
    while True:
        candidate = safe_join(config.outputs_dir, f"{base_name}_{counter}.wav")
        if not candidate.exists():
            return candidate
        counter += 1


def dir_size_mb(path: Path) -> float:
    """Calculate the total size of a directory in megabytes (MB). Returns 0.0 if missing."""
    if not path.exists():
        return 0.0

    total_bytes = 0
    if path.is_file():
        total_bytes = path.stat().st_size
    else:
        for root, _, files in os.walk(path):
            for f in files:
                fp = Path(root) / f
                try:
                    total_bytes += fp.stat().st_size
                except OSError:
                    pass

    return round(total_bytes / (1024 * 1024), 2)


def remove_tree_safe(path: Path, base: Path) -> float:
    """Safely delete a directory tree within base, returning freed megabytes."""
    resolved_path = safe_join(base, path.relative_to(base) if path.is_absolute() else path)
    if not resolved_path.exists():
        return 0.0

    freed_mb = dir_size_mb(resolved_path)
    if resolved_path.is_dir():
        shutil.rmtree(resolved_path)
    else:
        resolved_path.unlink()

    return freed_mb
