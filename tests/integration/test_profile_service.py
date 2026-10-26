"""Integration tests for ProfileService audio enrollment, consent enforcement, and CRUD."""

from pathlib import Path
from typing import Callable

import pytest

from voxclone.audio.validate import SampleReport
from voxclone.constants import REFERENCE_SAMPLE_RATE
from voxclone.errors import ConsentRequiredError, InternalError
from voxclone.models.profile import VoiceProfile
from voxclone.services.profile_service import PreparedSample, ProfileService
from tests.conftest import SpeechArray


def test_enroll_from_file_success(
    profile_service: ProfileService,
    reference_wav: Path,
) -> None:
    """Enrolling a valid audio file creates a disk asset and database record."""
    prepared = profile_service.prepare_from_file(reference_wav)
    assert prepared.duration_sec >= 10.0
    assert prepared.sample_rate == REFERENCE_SAMPLE_RATE
    assert len(prepared.sha256) == 64

    profile = profile_service.save_profile(
        name="Morgan Freeman",
        prepared=prepared,
        consent_confirmed=True,
    )

    assert isinstance(profile, VoiceProfile)
    assert profile.name == "Morgan Freeman"
    assert profile.consent_confirmed is True
    assert profile.source_type == "file"
    assert profile.reference_path.exists()
    assert profile.reference_path.stat().st_size > 0


def test_enroll_consent_required_gate(
    profile_service: ProfileService,
    reference_wav: Path,
) -> None:
    """Enrolling without consent confirmation must fail with ConsentRequiredError (VX-103)."""
    prepared = profile_service.prepare_from_file(reference_wav)

    with pytest.raises(ConsentRequiredError) as exc_info:
        profile_service.save_profile(
            name="Unconsented Voice",
            prepared=prepared,
            consent_confirmed=False,
        )

    assert exc_info.value.code == "VX-103"
    # Ensure profile was not persisted in database
    profiles = profile_service.list_profiles()
    assert not any(p.name == "Unconsented Voice" for p in profiles)


def test_enroll_from_mic_simulated(profile_service: ProfileService) -> None:
    """Enrolling via simulated microphone produces clean profile asset and record."""
    prepared = profile_service.prepare_from_mic(duration_sec=12.0)
    assert prepared.source_type == "mic"

    profile = profile_service.save_profile(
        name="Mic Voice",
        prepared=prepared,
        consent_confirmed=True,
    )

    assert profile.name == "Mic Voice"
    assert profile.reference_path.exists()


def test_duplicate_profile_name_rejected(
    profile_service: ProfileService,
    reference_wav: Path,
) -> None:
    """Registering two profiles with identical names raises validation error."""
    prepared = profile_service.prepare_from_file(reference_wav)
    profile_service.save_profile("Original Voice", prepared, consent_confirmed=True)

    with pytest.raises(InternalError) as exc_info:
        profile_service.save_profile("Original Voice", prepared, consent_confirmed=True)

    assert "already exists" in str(exc_info.value)


def test_profile_name_format_validation(
    profile_service: ProfileService,
    reference_wav: Path,
) -> None:
    """Names with invalid characters or whitespace only must be rejected."""
    prepared = profile_service.prepare_from_file(reference_wav)

    with pytest.raises(InternalError):
        profile_service.save_profile("   ", prepared, consent_confirmed=True)

    with pytest.raises(InternalError):
        profile_service.save_profile("Invalid/Slash*Name", prepared, consent_confirmed=True)


def test_rename_and_delete_profile(
    profile_service: ProfileService,
    reference_wav: Path,
) -> None:
    """Profile can be retrieved by ID or name, renamed, and permanently deleted."""
    prepared = profile_service.prepare_from_file(reference_wav)
    profile = profile_service.save_profile("Old Name", prepared, consent_confirmed=True)
    wav_path = profile.reference_path
    assert wav_path.exists()

    # Retrieve by ID and name
    assert profile_service.get_profile(profile.id).id == profile.id
    assert profile_service.get_profile("Old Name").id == profile.id

    # Rename
    renamed = profile_service.rename_profile(profile.id, "New Name")
    assert renamed.name == "New Name"
    assert profile_service.get_profile("New Name").id == profile.id

    # Delete
    deleted = profile_service.delete_profile(profile.id)
    assert deleted is True
    assert not wav_path.exists()

    with pytest.raises(InternalError):
        profile_service.get_profile(profile.id)
