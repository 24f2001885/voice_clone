"""Voice profile service handling audio enrollment, validation, consent, and lifecycle."""

from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import re
import sqlite3

import numpy as np
import soundfile as sf

from voxclone.audio.io import load_audio, record_microphone, save_wav
from voxclone.audio.validate import SampleReport, analyze_sample, clean_reference
from voxclone.errors import ConsentRequiredError, InternalError
from voxclone.models.profile import VoiceProfile
from voxclone.storage.db import get_db, new_uuid, utc_now_iso
from voxclone.storage.profiles_repo import (
    delete_profile as repo_delete_profile,
    get_by_id,
    get_by_name,
    insert_profile,
    list_profiles as repo_list_profiles,
    update_name,
)

_VALID_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\s]{1,50}$")


@dataclass(frozen=True)
class PreparedSample:
    """Pre-processed and analyzed audio sample ready for consent confirmation and enrollment."""

    clean_audio: np.ndarray
    sample_rate: int
    duration_sec: float
    sha256: str
    report: SampleReport
    source_type: str  # "file" or "mic"
    original_filename: str | None


class ProfileService:
    """Business service governing voice profile registration, validation, and storage."""

    def __init__(self, db_path: Path, profiles_dir: Path) -> None:
        self._db_path = db_path
        self._profiles_dir = profiles_dir
        self._profiles_dir.mkdir(parents=True, exist_ok=True)

    def prepare_from_file(self, file_path: Path) -> PreparedSample:
        """Load, validate, and clean an audio file for enrollment.

        Args:
            file_path: Path to input audio file (WAV, MP3, FLAC, OGG, M4A).

        Returns:
            PreparedSample containing cleaned audio, metrics, and report.
        """
        resolved_path = Path(file_path).resolve()
        if not resolved_path.exists() or not resolved_path.is_file():
            raise InternalError(
                f"Reference audio file not found: '{resolved_path}'",
                hint="Check the filepath and verify read permissions.",
            )

        data, sr = load_audio(resolved_path)
        report = analyze_sample(data, sr)
        clean_data, clean_sr = clean_reference(data, sr)

        buf = io.BytesIO()
        sf.write(buf, clean_data, clean_sr, format="WAV", subtype="PCM_16")
        wav_bytes = buf.getvalue()
        sha256_hash = hashlib.sha256(wav_bytes).hexdigest()
        duration_sec = round(float(len(clean_data)) / float(clean_sr), 2)

        return PreparedSample(
            clean_audio=clean_data,
            sample_rate=clean_sr,
            duration_sec=duration_sec,
            sha256=sha256_hash,
            report=report,
            source_type="file",
            original_filename=resolved_path.name,
        )

    def prepare_from_mic(
        self,
        duration_sec: float = 15.0,
        device_index: int | None = None,
    ) -> PreparedSample:
        """Record from microphone, validate, and clean audio for enrollment.

        Args:
            duration_sec: Target recording duration in seconds (default: 15.0).
            device_index: Optional hardware input device index.

        Returns:
            PreparedSample containing cleaned audio, metrics, and report.
        """
        data, sr = record_microphone(duration_sec=duration_sec, device_index=device_index)
        report = analyze_sample(data, sr)
        clean_data, clean_sr = clean_reference(data, sr)

        buf = io.BytesIO()
        sf.write(buf, clean_data, clean_sr, format="WAV", subtype="PCM_16")
        wav_bytes = buf.getvalue()
        sha256_hash = hashlib.sha256(wav_bytes).hexdigest()
        actual_duration = round(float(len(clean_data)) / float(clean_sr), 2)

        return PreparedSample(
            clean_audio=clean_data,
            sample_rate=clean_sr,
            duration_sec=actual_duration,
            sha256=sha256_hash,
            report=report,
            source_type="mic",
            original_filename=None,
        )

    def validate_name(self, name: str) -> str:
        """Validate profile name format and check for uniqueness."""
        stripped = name.strip()
        if not stripped:
            raise InternalError("Voice profile name cannot be empty.", hint="Provide a name with 1 to 50 characters.")
        if not _VALID_NAME_PATTERN.match(stripped):
            raise InternalError(
                f"Invalid profile name: '{stripped}'",
                hint="Use only letters, numbers, hyphens, underscores, and spaces (max 50 chars).",
            )
        with get_db(self._db_path) as conn:
            existing = get_by_name(conn, stripped)
            if existing is not None:
                raise InternalError(
                    f"A voice profile named '{stripped}' already exists.",
                    hint="Choose a distinct profile name or delete/rename the existing profile.",
                )
        return stripped

    def save_profile(
        self,
        name: str,
        prepared: PreparedSample,
        consent_confirmed: bool,
    ) -> VoiceProfile:
        """Commit an analyzed voice sample to disk and SQLite.

        CRITICAL GATE: If consent_confirmed is False, raises ConsentRequiredError (VX-103).
        """
        if not consent_confirmed:
            raise ConsentRequiredError(
                "Consent confirmation is mandatory to enroll a voice profile (VX-103).",
                hint="You must confirm you have the right and authorization to clone this voice.",
            )

        validated_name = self.validate_name(name)
        profile_id = new_uuid()
        target_path = (self._profiles_dir / f"{profile_id}.wav").resolve()

        # Write clean WAV to storage
        save_wav(target_path, prepared.clean_audio, prepared.sample_rate)

        now_iso = utc_now_iso()
        quality_notes = "; ".join(prepared.report.notes) if prepared.report.notes else None

        with get_db(self._db_path) as conn:
            return insert_profile(
                conn=conn,
                name=validated_name,
                reference_path=target_path,
                source_type=prepared.source_type,
                duration_sec=prepared.duration_sec,
                sample_rate=prepared.sample_rate,
                sha256=prepared.sha256,
                consent_confirmed=True,
                consent_confirmed_at=now_iso,
                original_filename=prepared.original_filename,
                quality_score=prepared.report.quality_score,
                quality_notes=quality_notes,
                profile_id=profile_id,
            )

    def list_profiles(self) -> list[VoiceProfile]:
        """Fetch all registered voice profiles ordered by creation time descending."""
        with get_db(self._db_path) as conn:
            return repo_list_profiles(conn)

    def get_profile(self, identifier: str) -> VoiceProfile:
        """Fetch profile by ID or by exact name."""
        with get_db(self._db_path) as conn:
            profile = get_by_id(conn, identifier)
            if profile is None:
                profile = get_by_name(conn, identifier)
            if profile is None:
                raise InternalError(
                    f"Voice profile '{identifier}' not found.",
                    hint="Run 'voxclone profiles list' to see available registered profiles.",
                )
            return profile

    def rename_profile(self, profile_id: str, new_name: str) -> VoiceProfile:
        """Rename an existing voice profile after format and collision validation."""
        validated_name = self.validate_name(new_name)
        with get_db(self._db_path) as conn:
            profile = get_by_id(conn, profile_id)
            if profile is None:
                raise InternalError(
                    f"Cannot rename: voice profile '{profile_id}' not found.",
                    hint="Check profile ID with 'voxclone profiles list'.",
                )
            return update_name(conn, profile_id, validated_name)

    def delete_profile(self, profile_id: str) -> bool:
        """Permanently delete a voice profile record and its reference audio file."""
        with get_db(self._db_path) as conn:
            profile = get_by_id(conn, profile_id)
            if profile is None:
                raise InternalError(
                    f"Cannot delete: voice profile '{profile_id}' not found.",
                    hint="Check profile ID with 'voxclone profiles list'.",
                )
            # Remove audio file from disk
            if profile.reference_path.exists():
                try:
                    profile.reference_path.unlink()
                except OSError:
                    pass
            return repo_delete_profile(conn, profile_id)

    def preview_profile(self, identifier: str) -> Path:
        """Return the path to the reference voice audio file for playback."""
        profile = self.get_profile(identifier)
        if not profile.reference_path.exists():
            raise InternalError(
                f"Reference audio file missing on disk: {profile.reference_path}",
                hint="Re-enroll the voice profile to restore the missing audio asset.",
            )
        return profile.reference_path
