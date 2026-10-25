"""Integration tests verifying database schema creation, constraints, and migrations."""

from pathlib import Path
import re
import sqlite3

import pytest

from voxclone import constants
from voxclone.config import AppConfig
from voxclone.errors import InternalError
from voxclone.storage.db import connect
from voxclone.storage.migrate import apply_migrations, current_version


def test_migrations_fresh_db_and_idempotency(tmp_path: Path, app_config: AppConfig) -> None:
    """Verify applying migrations from scratch creates expected tables, and a second run is a no-op."""
    db_file = tmp_path / "fresh_voxclone.db"
    conn = connect(db_file)

    # 1. Fresh application
    applied = apply_migrations(conn, app_config.migrations_dir)
    assert applied == [1, 2]
    assert current_version(conn) == 2

    # Verify tables
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table';")
    table_names = {row["name"] for row in cursor.fetchall()}
    expected_tables = {
        "schema_migrations",
        "voice_profiles",
        "jobs",
        "job_chunks",
        "model_events",
        "app_settings",
    }
    assert expected_tables.issubset(table_names)

    # Verify indexes
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type = 'index';")
    index_names = {row["name"] for row in cursor.fetchall()}
    expected_indexes = {
        "idx_jobs_created_at",
        "idx_jobs_status",
        "idx_job_chunks_job",
        "idx_model_events_created",
    }
    assert expected_indexes.issubset(index_names)

    # 2. Idempotency
    reapplied = apply_migrations(conn, app_config.migrations_dir)
    assert reapplied == []
    assert current_version(conn) == 2

    conn.close()


def test_migration_seed_settings_count(db_conn: sqlite3.Connection) -> None:
    """Verify that exactly nine default settings are present after migration 001."""
    cursor = db_conn.execute("SELECT COUNT(*) AS total FROM app_settings;")
    assert cursor.fetchone()["total"] == len(constants.DEFAULT_SETTINGS)


def test_schema_constraints_and_foreign_keys(db_conn: sqlite3.Connection) -> None:
    """Test SQL CHECK and FOREIGN KEY constraints."""
    # 1. voice_profiles: consent_confirmed must equal 1
    with pytest.raises(sqlite3.IntegrityError):
        db_conn.execute(
            """
            INSERT INTO voice_profiles (
                id, name, reference_path, source_type, duration_sec, sample_rate,
                sha256, consent_confirmed, consent_confirmed_at, created_at, updated_at
            ) VALUES (
                'p1', 'test_voice', '/path/ref.wav', 'file', 15.0, 24000,
                'hash123', 0, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'
            );
            """
        )

    # Insert valid profile
    db_conn.execute(
        """
        INSERT INTO voice_profiles (
            id, name, reference_path, source_type, duration_sec, sample_rate,
            sha256, consent_confirmed, consent_confirmed_at, created_at, updated_at
        ) VALUES (
            'p1', 'valid_voice', '/path/ref.wav', 'file', 15.0, 24000,
            'hash123', 1, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'
        );
        """
    )

    # 2. jobs: invalid job_type rejected
    with pytest.raises(sqlite3.IntegrityError):
        db_conn.execute(
            """
            INSERT INTO jobs (
                id, job_type, status, profile_id, profile_name_snapshot,
                input_source, output_mode, created_at
            ) VALUES (
                'j1', 'invalid_type', 'queued', 'p1', 'valid_voice',
                'text', 'both', '2026-01-01T00:00:00Z'
            );
            """
        )

    # Insert valid job
    db_conn.execute(
        """
        INSERT INTO jobs (
            id, job_type, status, profile_id, profile_name_snapshot,
            input_source, output_mode, created_at
        ) VALUES (
            'j1', 'text_to_voice', 'queued', 'p1', 'valid_voice',
            'text', 'both', '2026-01-01T00:00:00Z'
        );
        """
    )

    # 3. job_chunks: duplicate (job_id, chunk_index) rejected
    db_conn.execute(
        """
        INSERT INTO job_chunks (
            job_id, chunk_index, kind, status
        ) VALUES (
            'j1', 0, 'sentence', 'pending'
        );
        """
    )
    with pytest.raises(sqlite3.IntegrityError):
        db_conn.execute(
            """
            INSERT INTO job_chunks (
                job_id, chunk_index, kind, status
            ) VALUES (
                'j1', 0, 'sentence', 'pending'
            );
            """
        )

    # 4. Profile delete sets jobs.profile_id = NULL
    db_conn.execute("DELETE FROM voice_profiles WHERE id = 'p1';")
    job_row = db_conn.execute("SELECT profile_id, profile_name_snapshot FROM jobs WHERE id = 'j1';").fetchone()
    assert job_row["profile_id"] is None
    assert job_row["profile_name_snapshot"] == "valid_voice"

    # 5. Job delete cascades to job_chunks
    db_conn.execute("DELETE FROM jobs WHERE id = 'j1';")
    chunks_count = db_conn.execute("SELECT COUNT(*) AS c FROM job_chunks WHERE job_id = 'j1';").fetchone()["c"]
    assert chunks_count == 0


def test_schema_sql_drift_against_constants(app_config: AppConfig) -> None:
    """Ensure SQL CHECK constraint value lists match constants in constants.py."""
    sql_path = app_config.migrations_dir / "001_init.sql"
    sql = sql_path.read_text(encoding="utf-8")

    # Helper to parse: CHECK (column IN ('a', 'b', ...))
    def _extract_check_set(col_name: str) -> set[str]:
        pattern = re.compile(rf"{col_name}\s+TEXT[^\n]*?CHECK\s*\([^\)]*?{col_name}\s+IN\s*\(([^)]+)\)", re.IGNORECASE)
        match = pattern.search(sql)
        assert match is not None, f"Could not find CHECK IN pattern for column {col_name}"
        raw = match.group(1)
        return {item.strip().strip("'\"") for item in raw.split(",")}

    assert _extract_check_set("source_type") == set(constants.PROFILE_SOURCES)
    assert _extract_check_set("job_type") == set(constants.JOB_TYPES)
    assert _extract_check_set("status") == set(constants.JOB_STATUSES)
    assert _extract_check_set("input_source") == set(constants.INPUT_SOURCES)
    assert _extract_check_set("output_mode") == set(constants.OUTPUT_MODES)
    assert _extract_check_set("kind") == set(constants.CHUNK_KINDS)
    assert _extract_check_set("model_key") == set(constants.MODEL_KEYS)
    assert _extract_check_set("action") == set(constants.MODEL_ACTIONS)


def test_broken_migration_rollback(tmp_path: Path) -> None:
    """Verify that a failing migration rolls back and leaves previous version intact."""
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()

    # Valid migration 001
    (mig_dir / "001_first.sql").write_text(
        "CREATE TABLE table_one (id INTEGER PRIMARY KEY);",
        encoding="utf-8",
    )

    # Broken migration 002
    (mig_dir / "002_broken.sql").write_text(
        "SYNTAX ERROR INVALID SQL;",
        encoding="utf-8",
    )

    conn = connect(tmp_path / "rollback_test.db")
    with pytest.raises(InternalError):
        apply_migrations(conn, mig_dir)

    # 001 succeeded and committed, but 002 rolled back
    assert current_version(conn) == 1
    cursor = conn.execute("SELECT COUNT(*) AS c FROM schema_migrations;")
    assert cursor.fetchone()["c"] == 1
    assert conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='table_one';").fetchone() is not None
    conn.close()
