"""SQLite connection and capability boundary for Job OS."""

from __future__ import annotations

import sqlite3
from typing import Any

from api.job_os.paths import job_os_db_path
from api.job_os.schema import migrate_job_os

_BUSY_TIMEOUT_MS = 5_000


def connect_job_os() -> sqlite3.Connection:
    """Open and migrate the active profile's Job OS database."""
    connection = sqlite3.connect(str(job_os_db_path()), timeout=_BUSY_TIMEOUT_MS / 1_000)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
        migrate_job_os(connection)
        return connection
    except Exception:
        connection.close()
        raise


def job_os_capability() -> dict[str, Any]:
    """Return whether the active profile can safely use Job OS storage."""
    try:
        connection = connect_job_os()
    except Exception:
        return {"available": False, "reason": "Job OS storage is unavailable"}
    try:
        version = connection.execute("SELECT MAX(version) FROM schema_meta").fetchone()[0]
        return {"available": True, "schema_version": version}
    finally:
        connection.close()
