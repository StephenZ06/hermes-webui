"""Profile-aware filesystem locations for Job OS state."""

from __future__ import annotations

import os
from pathlib import Path


def job_os_state_dir() -> Path:
    """Return the active profile's private Job OS state directory."""
    from api import profiles

    state_dir = profiles.get_active_hermes_home() / "webui_state" / "job_os"
    state_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(state_dir, 0o700)
    except OSError:
        # Permission tightening is best-effort on platforms that do not expose
        # POSIX modes; the directory remains profile-owned either way.
        pass
    return state_dir


def job_os_db_path() -> Path:
    """Return the active profile's canonical Job OS SQLite database path."""
    return job_os_state_dir() / "job_os.db"

