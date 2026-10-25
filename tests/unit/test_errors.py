"""Unit tests verifying the VoxClone standardized VX error hierarchy."""

import pytest

from voxclone.errors import (
    ERROR_CODES,
    ChunkOutOfMemoryError,
    ConsentRequiredError,
    GpuUnavailableError,
    InsufficientVramError,
    InternalError,
    InvalidTextError,
    JobInterruptedError,
    MicrophoneUnavailableError,
    ModelWeightsMissingError,
    NoSpeechDetectedError,
    SampleTooShortError,
    SpeakerUnavailableError,
    UnsupportedAudioError,
    VoxcloneError,
    wrap_unexpected,
)

EXPECTED_ERROR_SPECS: list[tuple[type[VoxcloneError], str]] = [
    (SampleTooShortError, "VX-101"),
    (UnsupportedAudioError, "VX-102"),
    (ConsentRequiredError, "VX-103"),
    (InvalidTextError, "VX-201"),
    (NoSpeechDetectedError, "VX-210"),
    (InsufficientVramError, "VX-300"),
    (ChunkOutOfMemoryError, "VX-301"),
    (GpuUnavailableError, "VX-302"),
    (ModelWeightsMissingError, "VX-310"),
    (MicrophoneUnavailableError, "VX-401"),
    (SpeakerUnavailableError, "VX-402"),
    (JobInterruptedError, "VX-500"),
    (InternalError, "VX-900"),
]


@pytest.mark.parametrize("cls,expected_code", EXPECTED_ERROR_SPECS)
def test_error_classes_and_codes(cls: type[VoxcloneError], expected_code: str) -> None:
    """Verify that each error subclass defines the exact expected VX code and non-empty messages."""
    instance = cls()
    assert instance.code == expected_code
    assert bool(instance.message.strip())
    assert bool(instance.hint.strip())
    assert f"({expected_code})" in str(instance)


def test_error_to_dict_schema() -> None:
    """Verify standard dictionary serialization shape."""
    err = SampleTooShortError(message="Custom short sample", hint="Custom hint")
    payload = err.to_dict()

    assert set(payload.keys()) == {"error_code", "message", "hint"}
    assert payload["error_code"] == "VX-101"
    assert payload["message"] == "Custom short sample"
    assert payload["hint"] == "Custom hint"


def test_error_codes_uniqueness() -> None:
    """Verify that ERROR_CODES registry contains exactly 13 unique codes."""
    assert len(ERROR_CODES) == 13
    assert len(set(ERROR_CODES.keys())) == 13
    for cls, expected_code in EXPECTED_ERROR_SPECS:
        assert ERROR_CODES[expected_code] is cls


def test_wrap_unexpected_preserves_cause() -> None:
    """Verify wrap_unexpected creates InternalError and preserves original exception as cause."""
    original = ValueError("Low-level tensor dimension mismatch")
    wrapped = wrap_unexpected(original)

    assert isinstance(wrapped, InternalError)
    assert wrapped.code == "VX-900"
    assert "Low-level tensor dimension mismatch" in wrapped.message
    assert wrapped.__cause__ is original
