"""Unit tests verifying filesystem layout, safe path traversal checks, and output path generator."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from voxclone.config import AppConfig
from voxclone.errors import InternalError
from voxclone.storage.files import (
    build_output_path,
    dir_size_mb,
    ensure_data_layout,
    remove_tree_safe,
    safe_join,
)


def test_safe_join_traversal_protection(tmp_path: Path) -> None:
    """Verify safe_join rejects directory traversal attempts."""
    base = tmp_path / "storage"
    base.mkdir()

    # Valid subpaths
    valid = safe_join(base, "profiles", "me.wav")
    assert str(valid).startswith(str(base.resolve()))

    # Traversal escape attempts
    with pytest.raises(InternalError) as exc_info:
        safe_join(base, "..", "etc", "passwd")
    assert "Path traversal detected" in str(exc_info.value)


def test_build_output_path_uniqueness(tmp_path: Path, app_config: AppConfig) -> None:
    """Verify build_output_path generates clean names and handles collision with numeric suffixes."""
    fixed_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    # First call creates base path
    p1 = build_output_path(app_config, "text_to_voice", "alice", now=fixed_time)
    assert p1.name == "text_alice_20261026_120000.wav"

    # Create the file on disk to simulate existing collision
    p1.parent.mkdir(parents=True, exist_ok=True)
    p1.write_bytes(b"wavdata")

    # Second call at same second should append _1
    p2 = build_output_path(app_config, "text_to_voice", "alice", now=fixed_time)
    assert p2.name == "text_alice_20261026_120000_1.wav"


def test_dir_size_and_safe_removal(tmp_path: Path) -> None:
    """Verify directory size computation and safe subtree deletion."""
    base = tmp_path / "base"
    sub = base / "subdir"
    sub.mkdir(parents=True)

    test_file = sub / "audio.bin"
    test_file.write_bytes(b"0" * (1024 * 1024 * 2))  # 2 MB

    assert dir_size_mb(base) >= 2.0
    assert dir_size_mb(tmp_path / "non_existent") == 0.0

    freed = remove_tree_safe(sub, base)
    assert freed >= 2.0
    assert not sub.exists()
