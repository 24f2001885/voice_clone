"""Engine factory providing dynamic instantiation of real or fake engines."""

from voxclone.config import AppConfig
from voxclone.engines.base import ModelEngine
from voxclone.errors import InternalError, ModelWeightsMissingError


def build_engine(model_key: str, config: AppConfig) -> ModelEngine:
    """Construct an unloaded engine instance based on model_key and config engine_mode.

    Args:
        model_key: One of 'tts', 'vc', or 'emotion'.
        config: Application configuration.

    Returns:
        Unloaded ModelEngine instance.
    """
    # Remote GPU execution via Google Drive queue
    if getattr(config, "backend", "local") == "remote_drive" or config.engine_mode == "remote_drive":
        if model_key == "tts":
            from voxclone.engines.remote_tts import RemoteTts

            return RemoteTts(drive_dir=config.drive_dir)  # type: ignore[return-value]
        if model_key == "vc":
            from voxclone.engines.remote_vc import RemoteVc

            return RemoteVc(drive_dir=config.drive_dir)  # type: ignore[return-value]
        if model_key == "emotion":
            if config.engine_mode == "fake":
                from voxclone.engines.fake_engines import FakeEmotion

                return FakeEmotion()
            from voxclone.engines.real_emotion import RealEmotion

            return RealEmotion()  # type: ignore[no-any-return]

    if config.engine_mode == "fake":
        from voxclone.engines.fake_engines import FakeEmotion, FakeTts, FakeVc

        if model_key == "tts":
            return FakeTts()
        if model_key == "vc":
            return FakeVc()
        if model_key == "emotion":
            return FakeEmotion()
        raise InternalError(
            f"Unknown model engine key: '{model_key}'",
            hint="Valid keys are 'tts', 'vc', 'emotion'.",
        )

    # Real engine path: lazy imports to avoid torch loading at package import time
    try:
        if model_key == "tts":
            from voxclone.engines.real_tts import RealTts

            return RealTts()  # type: ignore[no-any-return]
        if model_key == "vc":
            from voxclone.engines.real_vc import RealVc

            return RealVc()  # type: ignore[no-any-return]
        if model_key == "emotion":
            from voxclone.engines.real_emotion import RealEmotion

            return RealEmotion()  # type: ignore[no-any-return]
        raise InternalError(
            f"Unknown model engine key: '{model_key}'",
            hint="Valid keys are 'tts', 'vc', 'emotion'.",
        )
    except ImportError as exc:
        raise ModelWeightsMissingError(
            f"Real engine module for '{model_key}' is not available: {exc.name or exc!s}"
        ) from exc
