"""Repository for key-value application settings stored in SQLite."""

import json
import sqlite3
from typing import Any

from voxclone.storage.db import utc_now_iso


def get_setting(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    """Fetch setting value by key, decoding from JSON."""
    cursor = conn.execute(
        "SELECT value FROM app_settings WHERE key = ?;",
        (key,),
    )
    row = cursor.fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return row["value"]


def get_all_settings(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return all stored settings as a Python dictionary with decoded JSON values."""
    cursor = conn.execute("SELECT key, value FROM app_settings ORDER BY key ASC;")
    result: dict[str, Any] = {}
    for row in cursor.fetchall():
        key = str(row["key"])
        raw_val = row["value"]
        try:
            result[key] = json.loads(raw_val)
        except Exception:
            result[key] = raw_val
    return result


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    """Upsert setting value as JSON-encoded string with current ISO timestamp."""
    json_val = json.dumps(value)
    now_iso = utc_now_iso()
    conn.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at;
        """,
        (key, json_val, now_iso),
    )


def delete_setting(conn: sqlite3.Connection, key: str) -> bool:
    """Delete setting row by key; return True if a row was deleted."""
    cursor = conn.execute("DELETE FROM app_settings WHERE key = ?;", (key,))
    return cursor.rowcount > 0
