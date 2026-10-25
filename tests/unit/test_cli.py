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
