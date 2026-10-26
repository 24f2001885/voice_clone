"""End-to-end integration test validating Voice Conversion workflow."""

from pathlib import Path
from typing import Callable

import pytest
from typer.testing import CliRunner

from tests.conftest import SpeechArray
from voxclone.cli import app


@pytest.mark.e2e
def test_e2e_voice_conversion_flow(
    tmp_path: Path,
    make_speech: Callable[..., SpeechArray],
    write_wav: Callable[..., Path],
) -> None:
    """Validate full flow: CLI enroll voice -> CLI convert input recording -> Verify output."""
    runner = CliRunner()

    # 1. Target speaker reference audio
    target_audio = make_speech(duration_sec=15.0, gap_sec=0.2, sr=24000, seed=101)
    target_wav = write_wav(tmp_path / "target_voice.wav", target_audio, sr=24000)

    # 2. Source input recording audio to be converted
    input_audio = make_speech(duration_sec=8.0, gap_sec=0.3, sr=16000, seed=202)
    input_wav = write_wav(tmp_path / "source_input.wav", input_audio, sr=16000)

    # 3. Enroll target profile
    enroll_res = runner.invoke(
        app,
        [
            "profiles",
            "enroll",
            "--file",
            str(target_wav),
            "--name",
            "TargetBob",
            "--consent",
            "--plain",
        ],
    )
    assert enroll_res.exit_code == 0

    # 4. Convert input audio to TargetBob's voice
    convert_res = runner.invoke(
        app,
        [
            "convert",
            "--profile",
            "TargetBob",
            "--input",
            str(input_wav),
            "--save",
            "--plain",
        ],
    )
    assert convert_res.exit_code == 0
    assert "Output generated:" in convert_res.stdout
    assert ".wav" in convert_res.stdout
