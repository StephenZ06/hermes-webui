"""One shared env file for every Hermes profile, layered under each profile's .env.

``<base>/shared/secrets.env`` holds the API keys and settings common to all
profiles; a profile's own ``.env`` still wins for any key it sets, so a single
profile can override one value. This mirrors the agent side, where every
profile's ``config.yaml`` reads the same file through the ``command`` secret
source with ``override_existing: false`` (see docs/shared-secrets.md).

All WebUI code that reads a profile's env should use :func:`load_layered_env`,
and all code that writes one should use :func:`write_env_values`, so a key set
once appears in every profile and a removal really removes it.

The layer is opt-in: it exists only once ``shared/secrets.env`` exists
(created by the migration in docs/shared-secrets.md). Without that file every
read and write behaves exactly as before -- the profile ``.env`` only.

In isolated-profile deployments (one contained profile per user) the shared
file is ignored entirely: a contained profile must not see operator secrets.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

SHARED_DIRNAME = "shared"
SHARED_FILENAME = "secrets.env"


def _isolated() -> bool:
    try:
        from api.profiles import _is_isolated_profile_mode

        return bool(_is_isolated_profile_mode())
    except Exception:
        return False


def shared_env_path() -> Path:
    from api.profiles import _resolve_base_hermes_home

    return Path(_resolve_base_hermes_home()) / SHARED_DIRNAME / SHARED_FILENAME


def parse_env_file(path: Path) -> dict[str, str]:
    """``KEY=value`` pairs from ``path`` (quotes stripped; ``export`` allowed)."""
    values: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return values
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip().strip('"').strip("'")
    return values


def load_shared_env() -> dict[str, str]:
    if not shared_env_enabled():
        return {}
    return parse_env_file(shared_env_path())


def load_layered_env(home: Path | str) -> dict[str, str]:
    """The env a profile actually sees: shared values, then the profile's own
    non-empty ``.env`` values on top."""
    merged = load_shared_env()
    for key, value in parse_env_file(Path(home) / ".env").items():
        if value != "" or key not in merged:
            merged[key] = value
    return merged


def shared_env_enabled() -> bool:
    """True once the shared secrets file exists (and the deployment is not isolated)."""
    return not _isolated() and shared_env_path().is_file()


def env_write_path(home: Path | str, key: str) -> Path:
    """Where a new value for ``key`` belongs: the shared file when the layer is
    enabled and this profile does not override the key, else the profile ``.env``."""
    profile_env = Path(home) / ".env"
    if not shared_env_enabled() or parse_env_file(profile_env).get(key):
        return profile_env
    return shared_env_path()


def write_env_values(home: Path | str, updates: Mapping[str, str | None]) -> None:
    """Set (or, for ``None``, remove) keys for this profile.

    A set goes to :func:`env_write_path`; a removal clears the key from both
    the profile ``.env`` and the shared file, so it is really gone.
    """
    from api.providers import _write_env_file

    profile_env = Path(home) / ".env"
    shared = shared_env_path()
    by_path: dict[Path, dict[str, str | None]] = {}
    for key, value in updates.items():
        if value is None:
            # Only touch files that hold the key: removing must not create files.
            if key in parse_env_file(profile_env):
                by_path.setdefault(profile_env, {})[key] = None
            if shared_env_enabled() and key in parse_env_file(shared):
                by_path.setdefault(shared, {})[key] = None
        else:
            by_path.setdefault(env_write_path(home, key), {})[key] = value
    for path, values in by_path.items():
        _write_env_file(path, values)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
