"""Unit tests verifying CLI sub-commands and execution paths."""

from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from voxclone.cli import app

runner = CliRunner()


def test_cli_help() -> None:
    """Verify top-level CLI help command lists system command group."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "system" in result.stdout


def test_cli_system_help() -> None:
    """Verify system sub-commands (doctor, storage, migrate) are present in help."""
    result = runner.invoke(app, ["system", "--help"])
    assert result.exit_code == 0
    assert "doctor" in result.stdout
    assert "storage" in result.stdout
    assert "migrate" in result.stdout


def test_cli_system_migrate(tmp_path: Path, monkeypatch: Any) -> None:
    """Verify voxclone system migrate command runs and applies migrations."""
    result = runner.invoke(app, ["system", "migrate", "--plain"])
    assert result.exit_code == 0
    assert "Applied migrations: 001, 002" in result.stdout or "Database schema is up to date" in result.stdout


def test_cli_system_doctor_plain() -> None:
    """Verify voxclone system doctor --plain executes and prints table."""
    result = runner.invoke(app, ["system", "doctor", "--plain"])
    assert result.exit_code == 0
    assert "System Doctor Diagnostics" in result.stdout
    assert "gpu_visible" in result.stdout
    assert "cuda_available" in result.stdout


def test_cli_system_storage_plain() -> None:
    """Verify voxclone system storage --plain executes and outputs report."""
    result = runner.invoke(app, ["system", "storage", "--plain"])
    assert result.exit_code == 0
    assert "Storage Utilization Report" in result.stdout
    assert "Voice Profiles" in result.stdout


def test_cli_profiles_help() -> None:
    """Verify profiles command group lists all sub-commands."""
    result = runner.invoke(app, ["profiles", "--help"])
    assert result.exit_code == 0
    assert "enroll" in result.stdout
    assert "list" in result.stdout
    assert "preview" in result.stdout
    assert "rename" in result.stdout
    assert "delete" in result.stdout


def test_cli_profiles_enroll_and_list(reference_wav: Path) -> None:
    """Test full CLI enrollment from file and subsequent listing."""
    # Enroll with consent
    res_enroll = runner.invoke(
        app,
        ["profiles", "enroll", "--file", str(reference_wav), "--name", "CliSpeaker", "--consent", "--plain"],
    )
    assert res_enroll.exit_code == 0
    assert "enrolled successfully" in res_enroll.stdout

    # List profiles
    res_list = runner.invoke(app, ["profiles", "list", "--plain"])
    assert res_list.exit_code == 0
    assert "CliSpeaker" in res_list.stdout


def test_cli_profiles_enroll_consent_gate(reference_wav: Path) -> None:
    """Enrolling via CLI without --consent must fail with non-zero exit code."""
    result = runner.invoke(
        app,
        ["profiles", "enroll", "--file", str(reference_wav), "--name", "BadSpeaker", "--no-consent", "--plain"],
    )
    assert result.exit_code != 0
    assert "VX-103" in result.stdout or "Consent confirmation is mandatory" in result.stdout


def test_cli_profiles_rename_and_delete(reference_wav: Path) -> None:
    """Test CLI renaming and deleting a registered voice profile."""
    # Enroll first
    runner.invoke(
        app,
        ["profiles", "enroll", "--file", str(reference_wav), "--name", "OrigName", "--consent", "--plain"],
    )

    # Rename
    res_rename = runner.invoke(app, ["profiles", "rename", "OrigName", "RenamedSpeaker", "--plain"])
    assert res_rename.exit_code == 0
    assert "RenamedSpeaker" in res_rename.stdout

    # Delete with --yes
    res_del = runner.invoke(app, ["profiles", "delete", "RenamedSpeaker", "--yes", "--plain"])
    assert res_del.exit_code == 0
    assert "deleted" in res_del.stdout


def test_cli_system_free_gpu() -> None:
    """Verify voxclone system free-gpu command."""
    result = runner.invoke(app, ["system", "free-gpu", "--plain"])
    assert result.exit_code == 0
    assert "Unloaded resident model" in result.stdout


def test_cli_system_status() -> None:
    """Verify voxclone system status command."""
    result = runner.invoke(app, ["system", "status", "--plain"])
    assert result.exit_code == 0
    assert "Resident Model" in result.stdout


def test_cli_speak_help() -> None:
    """Verify speak command help lists expected options."""
    result = runner.invoke(app, ["speak", "--help"])
    assert result.exit_code == 0
    assert "--profile" in result.stdout
    assert "--text" in result.stdout
    assert "--emotion" in result.stdout


def test_cli_speak_requires_text_or_file() -> None:
    """Invoking speak without text or with both text and text-file must fail."""
    result = runner.invoke(app, ["speak", "--profile", "Any", "--plain"])
    assert result.exit_code != 0
    assert "Exactly one of --text or --text-file" in result.stdout


def test_cli_speak_success(reference_wav: Path) -> None:
    """Enrolling a profile and speaking via CLI produces an output WAV path."""
    runner.invoke(
        app,
        ["profiles", "enroll", "--file", str(reference_wav), "--name", "SpeakTester", "--consent", "--plain"],
    )
    result = runner.invoke(
        app,
        ["speak", "--profile", "SpeakTester", "--text", "Hello from speak CLI test.", "--save", "--plain"],
    )
    assert result.exit_code == 0
    assert "Output generated:" in result.stdout


