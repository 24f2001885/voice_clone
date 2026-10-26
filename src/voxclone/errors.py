"""Exception hierarchy and standardized error codes (VX-xxx) for VoxClone CLI."""

from typing import Any


class VoxcloneError(Exception):
    """Base exception for all domain and operational errors in VoxClone."""

    code: str = "VX-900"
    default_message: str = "Unexpected internal error"
    default_hint: str = "See log file path shown"

    def __init__(
        self,
        message: str | None = None,
        hint: str | None = None,
        code: str | None = None,
    ) -> None:
        self.message: str = message if message is not None else self.default_message
        self.hint: str = hint if hint is not None else self.default_hint
        if code is not None:
            self.code = code
        super().__init__(self.__str__())

    @property
    def error_code(self) -> str:
        """Alias for code to support both instance.code and instance.error_code."""
        return self.code

    def to_dict(self) -> dict[str, Any]:
        """Return standardized error dictionary representation."""
        return {
            "error_code": self.code,
            "message": self.message,
            "hint": self.hint,
        }

    def __str__(self) -> str:
        return f"{self.message} ({self.code})"


class SampleTooShortError(VoxcloneError):
    """Raised when an enrolled voice sample is too short or mostly silence."""

    code = "VX-101"
    default_message = "Sample too short or mostly silent"
    default_hint = "Record 20-30 s of clear speech"


class UnsupportedAudioError(VoxcloneError):
    """Raised when an audio file cannot be decoded or has an invalid format."""

    code = "VX-102"
    default_message = "Unsupported or corrupt audio file"
    default_hint = "Convert to wav and retry"


class ConsentRequiredError(VoxcloneError):
    """Raised when speaker consent is missing or rejected."""

    code = "VX-103"
    default_message = "Consent not confirmed"
    default_hint = "Confirm you own or have permission for this voice"


class InvalidTextError(VoxcloneError):
    """Raised when input text for TTS is empty or exceeds character limits."""

    code = "VX-201"
    default_message = "Text empty or too long"
    default_hint = "Shorten or split input"


class NoSpeechDetectedError(VoxcloneError):
    """Raised when silence-aware analysis detects zero speech."""

    code = "VX-210"
    default_message = "No speech detected in input"
    default_hint = "Check the file or microphone"


class InsufficientVramError(VoxcloneError):
    """Raised when remaining GPU VRAM is below model requirement."""

    code = "VX-300"
    default_message = "Not enough GPU memory for model"
    default_hint = "Close GPU apps; run Free GPU memory"


class ChunkOutOfMemoryError(VoxcloneError):
    """Raised when GPU OOM occurs during single chunk conversion."""

    code = "VX-301"
    default_message = "Out of memory during a chunk"
    default_hint = "Resume the job; lower chunk length"


class GpuUnavailableError(VoxcloneError):
    """Raised when GPU execution is requested but CUDA is not functional."""

    code = "VX-302"
    default_message = "GPU not available"
    default_hint = "Run Doctor; CPU mode is much slower"


class ModelWeightsMissingError(VoxcloneError):
    """Raised when required weights are not found in the local cache."""

    code = "VX-310"
    default_message = "Model weights missing"
    default_hint = "Run `system fetch-models` while online"


class MicrophoneUnavailableError(VoxcloneError):
    """Raised when audio capture device cannot be opened."""

    code = "VX-401"
    default_message = "Microphone unavailable"
    default_hint = "Run Doctor; use a file instead"


class SpeakerUnavailableError(VoxcloneError):
    """Raised when audio playback device cannot be opened."""

    code = "VX-402"
    default_message = "Speaker unavailable"
    default_hint = "Output was saved; play it from Windows"


class JobInterruptedError(VoxcloneError):
    """Raised when a job is canceled or aborted unexpectedly."""

    code = "VX-500"
    default_message = "Job interrupted"
    default_hint = "Choose Resume"


class InternalError(VoxcloneError):
    """Raised for unexpected internal errors, bugs, or unhandled exceptions."""

    code = "VX-900"
    default_message = "Unexpected internal error"
    default_hint = "See log file path shown"


ERROR_CODES: dict[str, type[VoxcloneError]] = {
    "VX-101": SampleTooShortError,
    "VX-102": UnsupportedAudioError,
    "VX-103": ConsentRequiredError,
    "VX-201": InvalidTextError,
    "VX-210": NoSpeechDetectedError,
    "VX-300": InsufficientVramError,
    "VX-301": ChunkOutOfMemoryError,
    "VX-302": GpuUnavailableError,
    "VX-310": ModelWeightsMissingError,
    "VX-401": MicrophoneUnavailableError,
    "VX-402": SpeakerUnavailableError,
    "VX-500": JobInterruptedError,
    "VX-900": InternalError,
}


def wrap_unexpected(exc: BaseException) -> InternalError:
    """Wrap any unexpected exception into an InternalError preserving cause."""
    err = InternalError(message=f"Unexpected internal error: {exc!s}")
    err.__cause__ = exc
    return err
