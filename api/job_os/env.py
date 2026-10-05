"""Read configuration values from the active profile's ``.env``.

Job OS reads its service URLs and credentials per request from the active
profile, so a profile switch can never reuse another profile's Firecrawl or
Gmail settings. Values are returned to server code only; API responses carry
presence booleans, never the values.
"""

from __future__ import annotations

import os
from pathlib import Path


def _parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def profile_env_value(key: str) -> tuple[str | None, str | None]:
    """Return ``(value, source)`` for ``key``: the profile ``.env`` first, then
    the process environment. ``source`` is ``"profile"``, ``"process"`` or None."""
    from api import profiles

    value = _parse_dotenv(Path(profiles.get_active_hermes_home()) / ".env").get(key, "")
    if value:
        return value, "profile"
    value = os.environ.get(key, "")
    if value:
        return value, "process"
    return None, None
