"""Remove retired OpenCode Go credentials without touching OpenCode Zen."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from api.config import _save_yaml_config_file
from api.paths import _atomic_write_text

_RETIRED_PROVIDER_ID = "opencode-go"
_OPENCODE_GO_ENV = "OPENCODE_GO_API_KEY"
_ENV_LINE = re.compile(r"^\s*(?:export\s+)?OPENCODE_GO_API_KEY\s*=", re.IGNORECASE)


def _canonical_provider_id(value: object) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _is_retired_provider(value: object) -> bool:
    return _canonical_provider_id(value) == _RETIRED_PROVIDER_ID


def _profile_homes(home: Path) -> list[Path]:
    homes = [home]
    for root in (home / "profiles", home / "profiles" / ".deleted"):
        if not root.is_dir():
            continue
        homes.extend(path for path in root.iterdir() if path.is_dir())
    return homes


def _remove_env_entries(path: Path) -> int:
    if not path.is_file():
        return 0
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    kept = [line for line in lines if not _ENV_LINE.match(line)]
    removed = len(lines) - len(kept)
    if removed:
        _atomic_write_text(path, "".join(kept), encoding="utf-8")
    return removed


def _remove_retired_keys(value: Any) -> int:
    """Remove only dictionary entries whose key is the retired provider id."""
    removed = 0
    if isinstance(value, dict):
        for key in list(value):
            if _is_retired_provider(key):
                value.pop(key)
                removed += 1
            else:
                removed += _remove_retired_keys(value[key])
    elif isinstance(value, list):
        for item in value:
            removed += _remove_retired_keys(item)
    return removed


def _clean_auth(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    removed = _remove_retired_keys(payload)
    if removed:
        _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return removed


def _clean_config(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        import yaml
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (ImportError, OSError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0
    removed = _remove_retired_keys(payload.get("providers"))
    model = payload.get("model")
    if isinstance(model, dict) and _is_retired_provider(model.get("provider")):
        model.pop("provider", None)
        removed += 1
    if removed:
        _save_yaml_config_file(path, payload)
    return removed


def remove_opencodego_state(home: Path | str) -> dict[str, int]:
    """Permanently remove OpenCode Go state from a Hermes home and profiles.

    The similarly named ``OPENCODE_API_KEY`` and OpenCode Zen entries are
    deliberately retained because they are a different provider.
    """
    root = Path(home).expanduser()
    summary = {"env_entries_removed": 0, "auth_entries_removed": 0, "config_entries_removed": 0}
    for profile_home in _profile_homes(root):
        summary["env_entries_removed"] += _remove_env_entries(profile_home / ".env")
        summary["auth_entries_removed"] += _clean_auth(profile_home / "auth.json")
        summary["config_entries_removed"] += _clean_config(profile_home / "config.yaml")
    return summary
