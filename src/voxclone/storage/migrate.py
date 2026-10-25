"""Database schema migration runner."""

from pathlib import Path
import re
import sqlite3

from voxclone.errors import InternalError
from voxclone.storage.db import transaction, utc_now_iso

MIGRATION_PATTERN = re.compile(r"^(\d{3})_(.+)\.sql$")


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    """Create schema_migrations table if it does not already exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );
        """
    )


def current_version(conn: sqlite3.Connection) -> int:
    """Return the latest applied migration version number, or 0 if none."""
    _ensure_migrations_table(conn)
    cursor = conn.execute("SELECT COALESCE(MAX(version), 0) AS max_v FROM schema_migrations;")
    row = cursor.fetchone()
    return int(row["max_v"]) if row else 0


def _split_sql_statements(sql: str) -> list[str]:
    """Split a SQL script into individual statements for execution within a transaction."""
    statements: list[str] = []
    current: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            continue
        current.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
    if current:
        stmt = "\n".join(current).strip()
        if stmt:
            statements.append(stmt)
    return statements


def apply_migrations(conn: sqlite3.Connection, migrations_dir: Path) -> list[int]:
    """Discover, validate, and execute pending SQL migration scripts sequentially."""
    _ensure_migrations_table(conn)

    if not migrations_dir.is_dir():
        raise InternalError(
            f"Migrations directory not found: {migrations_dir}",
            hint="Ensure the migrations/ directory exists and contains SQL files.",
        )

    # Parse and sort migration files
    migration_files: list[tuple[int, str, Path]] = []
    seen_versions: dict[int, Path] = {}

    for file_path in sorted(migrations_dir.glob("*.sql")):
        match = MIGRATION_PATTERN.match(file_path.name)
        if not match:
            continue
        v_num = int(match.group(1))
        name = match.group(2)
        if v_num in seen_versions:
            raise InternalError(
                f"Duplicate migration version {v_num:03d}: found in '{seen_versions[v_num].name}' and '{file_path.name}'.",
                hint="Resolve migration version collisions.",
            )
        seen_versions[v_num] = file_path
        migration_files.append((v_num, name, file_path))

    migration_files.sort(key=lambda item: item[0])

    # Validate that there are no gaps in the migration sequence
    for idx, (v_num, _, path) in enumerate(migration_files, start=1):
        if v_num != idx:
            raise InternalError(
                f"Gap detected in migrations sequence: expected version {idx:03d}, but found {v_num:03d} in '{path.name}'.",
                hint="Renumber migration files sequentially without gaps.",
            )

    # Fetch already applied versions
    cursor = conn.execute("SELECT version FROM schema_migrations ORDER BY version ASC;")
    applied_versions = {int(row["version"]) for row in cursor.fetchall()}

    newly_applied: list[int] = []

    for v_num, name, file_path in migration_files:
        if v_num in applied_versions:
            continue

        sql_content = file_path.read_text(encoding="utf-8")
        stmts = _split_sql_statements(sql_content)
        try:
            with transaction(conn):
                # Execute individual migration statements within the transaction
                for stmt in stmts:
                    conn.execute(stmt)
                # Record migration in schema_migrations
                conn.execute(
                    """
                    INSERT INTO schema_migrations (version, name, applied_at)
                    VALUES (?, ?, ?);
                    """,
                    (v_num, name, utc_now_iso()),
                )
            newly_applied.append(v_num)
        except Exception as exc:
            raise InternalError(
                f"Failed to execute migration {file_path.name}: {exc!s}",
                hint="Review SQL syntax and ensure schema changes are safe.",
            ) from exc

    return newly_applied
