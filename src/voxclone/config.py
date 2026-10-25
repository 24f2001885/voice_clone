"""Application configuration loader and validator."""

from collections.abc import Mapping
from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any

from voxclone.errors import InternalError, VoxcloneError

VALID_ENGINE_MODES: set[str] = {"real", "fake"}
VALID_LOG_LEVELS: set[str] = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

TUNABLE_ENV_VARS: dict[str, type] = {
    "VOXCLONE_DEVICE": str,
    "VOXCLONE_WORKERS": int,
    "VOXCLONE_VRAM_BUDGET_MB": int,
    "VOXCLONE_KEEP_WARM": bool,
    "VOXCLONE_CHUNK_MIN_SEC": float,
    "VOXCLONE_CHUNK_MAX_SEC": float,
    "VOXCLONE_CROSSFADE_MS": int,
    "VOXCLONE_SENTENCE_MAX_CHARS": int,
}


def _parse_bool(val: Any) -> bool:
    """Parse string representation of boolean."""
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off", ""}:
        return False
    raise InternalError(f"Invalid boolean value: {val!r}")


@dataclass(frozen=True)
class AppConfig:
    """Immutable application runtime configuration."""

    data_dir: Path
    profiles_dir: Path
    outputs_dir: Path
    inputs_dir: Path
    work_dir: Path
    logs_dir: Path
    db_path: Path
    migrations_dir: Path
    engine_mode: str
    log_level: str
    require_consent: bool
    plain_mode: bool
    no_color: bool
    env_overrides: dict[str, object] = field(default_factory=dict)


_CACHED_CONFIG: AppConfig | None = None


def _find_migrations_dir() -> Path:
    """Resolve migrations directory from container standard or repository root."""
    app_migrations = Path("/app/migrations")
    if app_migrations.is_dir():
        return app_migrations
    # fallback to source tree: src/voxclone/config.py -> ../../../migrations
    repo_migrations = Path(__file__).resolve().parent.parent.parent / "migrations"
    return repo_migrations


def load_config(env: Mapping[str, str] | None = None) -> AppConfig:
    """Load configuration from environment mapping with validation."""
    source_env = os.environ if env is None else env

    data_dir_str = source_env.get("VOXCLONE_DATA_DIR", "/app/data")
    data_dir = Path(data_dir_str)

    profiles_dir = Path(source_env.get("VOXCLONE_PROFILES_DIR", "/app/profiles"))
    outputs_dir = Path(source_env.get("VOXCLONE_OUTPUTS_DIR", "/app/outputs"))
    inputs_dir = Path(source_env.get("VOXCLONE_INPUTS_DIR", "/app/inputs"))
    work_dir = Path(source_env.get("VOXCLONE_WORK_DIR", str(data_dir / "work")))
    logs_dir = Path(data_dir / "logs")
    db_path = data_dir / "voxclone.db"
    migrations_dir = _find_migrations_dir()

    engine_mode = source_env.get("VOXCLONE_ENGINE", "real").strip().lower()
    if engine_mode not in VALID_ENGINE_MODES:
        raise VoxcloneError(
            f"Invalid engine mode '{engine_mode}'. Expected one of: {sorted(VALID_ENGINE_MODES)}",
            code="VX-900",
            hint="Set VOXCLONE_ENGINE to 'real' or 'fake'.",
        )

    log_level = source_env.get("VOXCLONE_LOG_LEVEL", "INFO").strip().upper()
    if log_level not in VALID_LOG_LEVELS:
        raise VoxcloneError(
            f"Invalid log level '{log_level}'. Expected one of: {sorted(VALID_LOG_LEVELS)}",
            code="VX-900",
            hint="Set VOXCLONE_LOG_LEVEL to DEBUG, INFO, WARNING, ERROR, or CRITICAL.",
        )

    consent_raw = source_env.get("VOXCLONE_REQUIRE_CONSENT", "1")
    try:
        require_consent = _parse_bool(consent_raw)
    except Exception as exc:
        raise InternalError("Invalid VOXCLONE_REQUIRE_CONSENT value.") from exc

    if not require_consent:
        raise InternalError("Consent requirement cannot be disabled (safety invariant).")

    plain_mode = _parse_bool(source_env.get("VOXCLONE_PLAIN", "0"))
    no_color = _parse_bool(source_env.get("NO_COLOR", "0")) or ("NO_COLOR" in source_env and source_env["NO_COLOR"] != "0")

    # Extract explicitly set tunables
    env_overrides: dict[str, object] = {}
    for env_key, val_type in TUNABLE_ENV_VARS.items():
        if env_key in source_env:
            raw_val = source_env[env_key]
            override_key = env_key.removeprefix("VOXCLONE_").lower()
            try:
                if val_type is bool:
                    parsed_val: object = _parse_bool(raw_val)
                elif val_type is int:
                    parsed_val = int(raw_val)
                elif val_type is float:
                    parsed_val = float(raw_val)
                else:
                    parsed_val = str(raw_val)
                env_overrides[override_key] = parsed_val
            except Exception as exc:
                raise InternalError(
                    f"Failed to parse environment variable {env_key}={raw_val!r} as {val_type.__name__}"
                ) from exc

    # Cross-validation
    if "chunk_min_sec" in env_overrides and "chunk_max_sec" in env_overrides:
        c_min = float(env_overrides["chunk_min_sec"])  # type: ignore[arg-type]
        c_max = float(env_overrides["chunk_max_sec"])  # type: ignore[arg-type]
        if c_min >= c_max:
            raise VoxcloneError(
                f"VOXCLONE_CHUNK_MIN_SEC ({c_min}) must be strictly less than VOXCLONE_CHUNK_MAX_SEC ({c_max}).",
                code="VX-900",
                hint="Adjust chunk duration bounds so min < max.",
            )

    return AppConfig(
        data_dir=data_dir,
        profiles_dir=profiles_dir,
        outputs_dir=outputs_dir,
        inputs_dir=inputs_dir,
        work_dir=work_dir,
        logs_dir=logs_dir,
        db_path=db_path,
        migrations_dir=migrations_dir,
        engine_mode=engine_mode,
        log_level=log_level,
        require_consent=require_consent,
        plain_mode=plain_mode,
        no_color=no_color,
        env_overrides=env_overrides,
    )


def get_config() -> AppConfig:
    """Return cached AppConfig singleton."""
    global _CACHED_CONFIG
    if _CACHED_CONFIG is None:
        _CACHED_CONFIG = load_config()
    return _CACHED_CONFIG


def reset_config_cache() -> None:
    """Clear cached AppConfig singleton (for testing fixtures)."""
    global _CACHED_CONFIG
    _CACHED_CONFIG = None
