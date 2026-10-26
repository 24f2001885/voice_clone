"""End-to-end integration test validating Profile Enrollment and Speak workflow."""

from pathlib import Path
from typing import Callable

import pytest
from typer.testing import CliRunner

from tests.conftest import SpeechArray
from voxclone.cli import app
from voxclone.storage import jobs_repo, profiles_repo


@pytest.mark.e2e
def test_e2e_enroll_and_speak_flow(
    tmp_path: Path,
    make_speech: Callable[..., SpeechArray],
    write_wav: Callable[..., Path],
) -> None:
    """Validate full flow: CLI enroll voice profile -> CLI synthesize speech -> Verify output."""
    runner = CliRunner()

    # 1. Generate clean 15s reference speech
    ref_audio = make_speech(duration_sec=15.0, gap_sec=0.2, sr=24000)
    ref_wav = write_wav(tmp_path / "speaker_enroll.wav", ref_audio, sr=24000)

    # 2. Enroll profile via CLI
    enroll_res = runner.invoke(
        app,
        [
            "profiles",
            "enroll",
            "--file",
            str(ref_wav),
            "--name",
            "AliceSpeaker",
            "--consent",
            "--plain",
        ],
    )
    assert enroll_res.exit_code == 0
    assert "Profile 'AliceSpeaker' enrolled successfully" in enroll_res.stdout

    # 3. List profiles to verify persistence
    list_res = runner.invoke(app, ["profiles", "list", "--plain"])
    assert list_res.exit_code == 0
    assert "AliceSpeaker" in list_res.stdout

    # 4. Synthesize text with newly enrolled profile
    text_input = "Hello! This is a complete end-to-end test of the speech cloning pipeline."
    speak_res = runner.invoke(
        app,
        [
            "speak",
            "--profile",
            "AliceSpeaker",
            "--text",
            text_input,
            "--save",
            "--plain",
        ],
    )
    assert speak_res.exit_code == 0
    assert "Output generated:" in speak_res.stdout
    assert ".wav" in speak_res.stdout
