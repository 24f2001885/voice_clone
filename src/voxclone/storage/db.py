"""SQLite connection factory, transaction management, and database utilities.

Architectural Rule:
All database interactions must use parameterized SQL queries exclusively.
Zero string interpolation, zero ORM.
"""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import uuid


def connect(db_path: Path) -> sqlite3.Connection:
    """Open or create a SQLite database with WAL and foreign key pragmas enabled."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        database=str(db_path),
        check_same_thread=False,
        isolation_level=None,  # Manual transaction management via BEGIN/COMMIT
    )
    conn.row_factory = sqlite3.Row

    # Execute critical operational pragmas
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


@contextmanager
def get_db(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Context manager providing an active SQLite connection, closing it upon exit."""
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()



@contextmanager
def transaction(conn: sqlite3.Connection) -> Generator[sqlite3.Connection, None, None]:
    """Provide a transactional scope around a series of operations."""
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")
    try:
        yield conn
        if conn.in_transaction:
            conn.execute("COMMIT;")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK;")
        raise


def utc_now_iso() -> str:
    """Return the current UTC timestamp formatted as ISO-8601 with milliseconds and 'Z' suffix."""
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def new_uuid() -> str:
    """Generate a lowercase UUID v4 string identifier."""
    return str(uuid.uuid4()).lower()
