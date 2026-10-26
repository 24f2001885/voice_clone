"""Exception hierarchy and standardized error codes (VX-xxx) for VoxClone CLI."""

from typing import Any


class VoxcloneError(Exception):
    """Base exception for all domain and operational errors in VoxClone."""

    code: str = "VX-900"
    default_message: str = "Unexpected internal error"
    default_hint: str = "See log file path shown"
    recovery_actions: tuple[str, ...] = ("log_path",)

    def __init__(
        self,
        message: str | None = None,
        hint: str | None = None,
        code: str | None = None,
        recovery_actions: tuple[str, ...] | None = None,
    ) -> None:
        self.message: str = message if message is not None else self.default_message
        self.hint: str = hint if hint is not None else self.default_hint
        if code is not None:
            self.code = code
        if recovery_actions is not None:
            self.recovery_actions = recovery_actions
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
            "recovery_actions": list(self.recovery_actions),
        }

    def __str__(self) -> str:
        return f"{self.message} ({self.code})"


class SampleTooShortError(VoxcloneError):
    """Raised when an enrolled voice sample is too short or mostly silence."""

    code = "VX-101"
    default_message = "Sample too short or mostly silent"
    default_hint = "Record 20-30 s of clear speech"
    recovery_actions: tuple[str, ...] = ("log_path",)


class UnsupportedAudioError(VoxcloneError):
    """Raised when an audio file cannot be decoded or has an invalid format."""

    code = "VX-102"
    default_message = "Unsupported or corrupt audio file"
    default_hint = "Convert to wav and retry"
    recovery_actions: tuple[str, ...] = ("log_path",)


class ConsentRequiredError(VoxcloneError):
    """Raised when speaker consent is missing or rejected."""

    code = "VX-103"
    default_message = "Consent not confirmed"
    default_hint = "Confirm you own or have permission for this voice"
    recovery_actions: tuple[str, ...] = ("log_path",)


class InvalidTextError(VoxcloneError):
    """Raised when input text for TTS is empty or exceeds character limits."""

    code = "VX-201"
    default_message = "Text empty or too long"
    default_hint = "Shorten or split input"
    recovery_actions: tuple[str, ...] = ("log_path",)


class NoSpeechDetectedError(VoxcloneError):
    """Raised when silence-aware analysis detects zero speech."""

    code = "VX-210"
    default_message = "No speech detected in input"
    default_hint = "Check the file or microphone"
    recovery_actions: tuple[str, ...] = ("doctor", "log_path")


class InsufficientVramError(VoxcloneError):
    """Raised when remaining GPU VRAM is below model requirement."""

    code = "VX-300"
    default_message = "Not enough GPU memory for model"
    default_hint = "Close GPU apps; run Free GPU memory"
    recovery_actions: tuple[str, ...] = ("free_gpu", "doctor", "log_path")


class ChunkOutOfMemoryError(VoxcloneError):
    """Raised when GPU OOM occurs during single chunk conversion."""

    code = "VX-301"
    default_message = "Out of memory during a chunk"
    default_hint = "Resume the job; lower chunk length"
    recovery_actions: tuple[str, ...] = ("resume", "free_gpu", "log_path")


class GpuUnavailableError(VoxcloneError):
    """Raised when GPU execution is requested but CUDA is not functional."""

    code = "VX-302"
    default_message = "GPU not available"
    default_hint = "Run Doctor; CPU mode is much slower"
    recovery_actions: tuple[str, ...] = ("doctor", "free_gpu", "log_path")


class ModelWeightsMissingError(VoxcloneError):
    """Raised when required weights are not found in the local cache."""

    code = "VX-310"
    default_message = "Model weights missing"
    default_hint = "Run `system fetch-models` while online"
    recovery_actions: tuple[str, ...] = ("fetch_models", "doctor", "log_path")


class RemoteWorkerOfflineError(VoxcloneError):
    """Raised when remote Colab GPU worker is not responding or heartbeat is stale."""

    code = "VX-320"
    default_message = "Remote Colab GPU worker offline or heartbeat missing"
    default_hint = "Start the Colab worker notebook on Google Colab"
    recovery_actions: tuple[str, ...] = ("doctor", "log_path")


class RemoteQueueTimeoutError(VoxcloneError):
    """Raised when a task times out waiting for remote Colab worker response."""

    code = "VX-321"
    default_message = "Timeout waiting for remote GPU response"
    default_hint = "Check Colab notebook execution status and retry"
    recovery_actions: tuple[str, ...] = ("resume", "doctor", "log_path")


class RemoteDriveNotMountedError(VoxcloneError):
    """Raised when the specified Google Drive queue folder does not exist or is not mounted."""

    code = "VX-322"
    default_message = "Google Drive queue directory not accessible"
    default_hint = "Verify Google Drive sync is running and configure drive_dir"
    recovery_actions: tuple[str, ...] = ("doctor", "log_path")


class RemoteWorkerInternalError(VoxcloneError):
    """Raised when remote Colab GPU worker reports an internal execution error."""

    code = "VX-323"
    default_message = "Remote Colab GPU worker reported an error"
    default_hint = "Check output logs in Colab worker notebook cell"
    recovery_actions: tuple[str, ...] = ("resume", "log_path")


class MicrophoneUnavailableError(VoxcloneError):
    """Raised when audio capture device cannot be opened."""

    code = "VX-401"
    default_message = "Microphone unavailable"
    default_hint = "Run Doctor; use a file instead"
    recovery_actions: tuple[str, ...] = ("doctor", "log_path")


class SpeakerUnavailableError(VoxcloneError):
    """Raised when audio playback device cannot be opened."""

    code = "VX-402"
    default_message = "Speaker unavailable"
    default_hint = "Output was saved; play it from Windows"
    recovery_actions: tuple[str, ...] = ("doctor", "log_path")


class JobInterruptedError(VoxcloneError):
    """Raised when a job is canceled or aborted unexpectedly."""

    code = "VX-500"
    default_message = "Job interrupted"
    default_hint = "Choose Resume"
    recovery_actions: tuple[str, ...] = ("resume", "log_path")


class InternalError(VoxcloneError):
    """Raised for unexpected internal errors, bugs, or unhandled exceptions."""

    code = "VX-900"
    default_message = "Unexpected internal error"
    default_hint = "See log file path shown"
    recovery_actions: tuple[str, ...] = ("log_path",)


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
    "VX-320": RemoteWorkerOfflineError,
    "VX-321": RemoteQueueTimeoutError,
    "VX-322": RemoteDriveNotMountedError,
    "VX-323": RemoteWorkerInternalError,
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
