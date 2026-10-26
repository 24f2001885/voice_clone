"""CRUD persistence repository for voice_profiles."""

from pathlib import Path
import sqlite3
from typing import Any

from voxclone.errors import InternalError
from voxclone.models.profile import VoiceProfile
from voxclone.storage.db import new_uuid, utc_now_iso


def insert_profile(
    conn: sqlite3.Connection,
    name: str,
    reference_path: Path,
    source_type: str,
    duration_sec: float,
    sample_rate: int,
    sha256: str,
    consent_confirmed: bool,
    consent_confirmed_at: str,
    original_filename: str | None = None,
    quality_score: float | None = None,
    quality_notes: str | None = None,
    profile_id: str | None = None,
) -> VoiceProfile:
    """Insert a new voice profile row into SQLite, generating UUID and timestamps."""
    pid = profile_id or new_uuid()
    now_iso = utc_now_iso()
    ref_str = str(reference_path)
    consent_int = 1 if consent_confirmed else 0

    try:
        conn.execute(
            """
            INSERT INTO voice_profiles (
                id, name, reference_path, source_type, original_filename,
                duration_sec, sample_rate, quality_score, quality_notes,
                sha256, consent_confirmed, consent_confirmed_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                pid,
                name,
                ref_str,
                source_type,
                original_filename,
                duration_sec,
                sample_rate,
                quality_score,
                quality_notes,
                sha256,
                consent_int,
                consent_confirmed_at,
                now_iso,
                now_iso,
            ),
        )
    except sqlite3.IntegrityError as exc:
        if "UNIQUE constraint failed: voice_profiles.name" in str(exc) or "voice_profiles.name" in str(exc):
            raise InternalError(
                f"A profile with this name already exists: '{name}'",
                hint="Choose a distinct profile name.",
            ) from exc
        raise

    return VoiceProfile(
        id=pid,
        name=name,
        reference_path=reference_path,
        source_type=source_type,
        original_filename=original_filename,
        duration_sec=duration_sec,
        sample_rate=sample_rate,
        quality_score=quality_score,
        quality_notes=quality_notes,
        sha256=sha256,
        consent_confirmed=consent_confirmed,
        consent_confirmed_at=consent_confirmed_at,
        created_at=now_iso,
        updated_at=now_iso,
    )


def get_by_id(conn: sqlite3.Connection, profile_id: str) -> VoiceProfile | None:
    """Find voice profile by UUID identifier."""
    cursor = conn.execute(
        "SELECT * FROM voice_profiles WHERE id = ?;",
        (profile_id,),
    )
    row = cursor.fetchone()
    return VoiceProfile.from_row(row) if row else None


def get_by_name(conn: sqlite3.Connection, name: str) -> VoiceProfile | None:
    """Find voice profile by unique name."""
    cursor = conn.execute(
        "SELECT * FROM voice_profiles WHERE name = ?;",
        (name,),
    )
    row = cursor.fetchone()
    return VoiceProfile.from_row(row) if row else None


def list_profiles(conn: sqlite3.Connection) -> list[VoiceProfile]:
    """List all voice profiles sorted by creation timestamp descending."""
    cursor = conn.execute(
        "SELECT * FROM voice_profiles ORDER BY created_at DESC, name ASC;"
    )
    return [VoiceProfile.from_row(row) for row in cursor.fetchall()]


def update_name(conn: sqlite3.Connection, profile_id: str, new_name: str) -> VoiceProfile:
    """Rename a voice profile, updating the updated_at timestamp."""
    now_iso = utc_now_iso()
    try:
        conn.execute(
            """
            UPDATE voice_profiles
            SET name = ?, updated_at = ?
            WHERE id = ?;
            """,
            (new_name, now_iso, profile_id),
        )
    except sqlite3.IntegrityError as exc:
        if "UNIQUE constraint failed: voice_profiles.name" in str(exc) or "voice_profiles.name" in str(exc):
            raise InternalError(
                f"A profile with this name already exists: '{new_name}'",
                hint="Choose a distinct profile name.",
            ) from exc
        raise

    updated = get_by_id(conn, profile_id)
    if updated is None:
        raise InternalError(f"Profile with id '{profile_id}' not found for rename.")
    return updated


def delete_profile(conn: sqlite3.Connection, profile_id: str) -> bool:
    """Delete profile by ID; returns True if deleted."""
    cursor = conn.execute("DELETE FROM voice_profiles WHERE id = ?;", (profile_id,))
    return cursor.rowcount > 0
