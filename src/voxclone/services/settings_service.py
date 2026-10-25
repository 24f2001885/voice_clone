"""Settings service managing application configuration persistence and validation."""

from dataclasses import dataclass
import sqlite3
from typing import Any

from voxclone.config import AppConfig
from voxclone.constants import DEFAULT_SETTINGS, OUTPUT_MODES
from voxclone.errors import InternalError, VoxcloneError
from voxclone.storage import settings_repo

VALID_DEVICES: set[str] = {"auto", "cuda", "cpu"}


@dataclass(frozen=True)
class SettingValue:
    """Represents a resolved configuration setting with provenance and lock status."""

    key: str
    value: Any
    source: str  # "env" or "db"
    locked: bool


class SettingsService:
    """Provides validated read, write, and lifecycle operations for user settings."""

    def __init__(self, conn: sqlite3.Connection, config: AppConfig) -> None:
        self._conn = conn
        self._config = config

    def get_all(self) -> dict[str, SettingValue]:
        """Return all application settings with override indicators."""
        db_settings = settings_repo.get_all_settings(self._conn)
        result: dict[str, SettingValue] = {}

        # Merge defaults, db settings, and env overrides
        all_keys = set(DEFAULT_SETTINGS.keys()).union(db_settings.keys())

        for key in sorted(all_keys):
            if key in self._config.env_overrides:
                val = self._config.env_overrides[key]
                result[key] = SettingValue(key=key, value=val, source="env", locked=True)
            elif key in db_settings:
                val = db_settings[key]
                result[key] = SettingValue(key=key, value=val, source="db", locked=False)
            else:
                val = DEFAULT_SETTINGS[key]
                result[key] = SettingValue(key=key, value=val, source="db", locked=False)

        return result

    def get(self, key: str) -> Any:
        """Fetch validated single setting by key, prioritizing environment override."""
        if key not in DEFAULT_SETTINGS:
            raise VoxcloneError(
                f"Unknown setting key: '{key}'",
                code="VX-900",
                hint="Check valid setting keys in documentation.",
            )

        if key in self._config.env_overrides:
            return self._config.env_overrides[key]

        return settings_repo.get_setting(self._conn, key, default=DEFAULT_SETTINGS[key])

    def set(self, key: str, value: Any) -> Any:
        """Validate and persist setting to database; raises if locked by environment."""
        if key not in DEFAULT_SETTINGS:
            raise VoxcloneError(
                f"Cannot set unknown setting key: '{key}'",
                code="VX-900",
                hint="Use only recognized setting keys.",
            )

        if key in self._config.env_overrides:
            raise InternalError(
                f"Setting '{key}' is locked by environment variable override and cannot be modified via UI/API.",
                hint="Remove or comment out the variable in your .env file to unlock it.",
            )

        validated_value = self._validate_setting(key, value)
        settings_repo.set_setting(self._conn, key, validated_value)
        return validated_value

    def _validate_setting(self, key: str, value: Any) -> Any:
        """Enforce type and boundary constraints on settings."""
        if key == "device":
            s_val = str(value).lower()
            if s_val not in VALID_DEVICES:
                raise VoxcloneError(
                    f"Invalid device '{value}'. Must be one of: {sorted(VALID_DEVICES)}",
                    code="VX-900",
                    hint="Choose 'auto', 'cuda', or 'cpu'.",
                )
            return s_val

        if key == "workers":
            try:
                i_val = int(value)
            except (ValueError, TypeError) as exc:
                raise VoxcloneError("Workers must be an integer.", code="VX-900") from exc
            if i_val < 0:
                raise VoxcloneError("Workers count must be >= 0 (0 = all cores).", code="VX-900")
            return i_val

        if key == "chunk_min_sec":
            try:
                f_val = float(value)
            except (ValueError, TypeError) as exc:
                raise VoxcloneError("chunk_min_sec must be a numeric value.", code="VX-900") from exc
            if not (1.0 <= f_val <= 10.0):
                raise VoxcloneError("chunk_min_sec must be between 1.0 and 10.0 seconds.", code="VX-900")
            current_max = self.get("chunk_max_sec")
            if f_val >= current_max:
                raise VoxcloneError(
                    f"chunk_min_sec ({f_val}) must be strictly less than chunk_max_sec ({current_max}).",
                    code="VX-900",
                )
            return f_val

        if key == "chunk_max_sec":
            try:
                f_val = float(value)
            except (ValueError, TypeError) as exc:
                raise VoxcloneError("chunk_max_sec must be a numeric value.", code="VX-900") from exc
            if not (2.0 <= f_val <= 15.0):
                raise VoxcloneError("chunk_max_sec must be between 2.0 and 15.0 seconds.", code="VX-900")
            current_min = self.get("chunk_min_sec")
            if f_val <= current_min:
                raise VoxcloneError(
                    f"chunk_max_sec ({f_val}) must be strictly greater than chunk_min_sec ({current_min}).",
                    code="VX-900",
                )
            return f_val

        if key == "crossfade_ms":
            try:
                i_val = int(value)
            except (ValueError, TypeError) as exc:
                raise VoxcloneError("crossfade_ms must be an integer.", code="VX-900") from exc
            if not (0 <= i_val <= 200):
                raise VoxcloneError("crossfade_ms must be between 0 and 200 milliseconds.", code="VX-900")
            return i_val

        if key == "default_output_mode":
            s_val = str(value).lower()
            if s_val not in OUTPUT_MODES:
                raise VoxcloneError(
                    f"Invalid output mode '{value}'. Must be one of: {OUTPUT_MODES}",
                    code="VX-900",
                )
            return s_val

        if key == "keep_warm":
            if isinstance(value, bool):
                return value
            s = str(value).strip().lower()
            if s in {"1", "true", "yes", "on"}:
                return True
            if s in {"0", "false", "no", "off"}:
                return False
            raise VoxcloneError("keep_warm must be a boolean value.", code="VX-900")

        if key == "vram_budget_mb":
            try:
                i_val = int(value)
            except (ValueError, TypeError) as exc:
                raise VoxcloneError("vram_budget_mb must be an integer.", code="VX-900") from exc
            if not (1000 <= i_val <= 24000):
                raise VoxcloneError("vram_budget_mb must be between 1,000 and 24,000 MB.", code="VX-900")
            return i_val

        if key == "sentence_max_chars":
            try:
                i_val = int(value)
            except (ValueError, TypeError) as exc:
                raise VoxcloneError("sentence_max_chars must be an integer.", code="VX-900") from exc
            if not (50 <= i_val <= 400):
                raise VoxcloneError("sentence_max_chars must be between 50 and 400 characters.", code="VX-900")
            return i_val

        return value

    def reset_defaults(self) -> None:
        """Reset all non-locked database settings to system default values."""
        for key, val in DEFAULT_SETTINGS.items():
            if key not in self._config.env_overrides:
                settings_repo.set_setting(self._conn, key, val)

    def ensure_defaults(self) -> None:
        """Populate any missing default settings in database."""
        current = settings_repo.get_all_settings(self._conn)
        for key, val in DEFAULT_SETTINGS.items():
            if key not in current:
                settings_repo.set_setting(self._conn, key, val)
