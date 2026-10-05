"""Filesystem locations for Job OS state.

Job OS is global: one jobs store, settings and resume for the person using
Hermes, whichever profile is active (decision update 2026-10-05 in the Job OS
spec). Isolated-profile deployments -- one contained profile per user -- keep
it per profile, so contained users never share a store.
"""

from __future__ import annotations

import os
from pathlib import Path


def job_os_root() -> Path:
    """The Hermes home that owns Job OS state: the base ``~/.hermes`` normally,
    the active profile's home in isolated-profile mode."""
    from api import profiles

    if profiles._is_isolated_profile_mode():
        return Path(profiles.get_active_hermes_home())
    return Path(profiles._resolve_base_hermes_home())


def job_os_state_dir() -> Path:
    """Return the private Job OS state directory."""
    state_dir = job_os_root() / "webui_state" / "job_os"
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
