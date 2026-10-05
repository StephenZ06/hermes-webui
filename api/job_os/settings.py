"""Per-profile Job OS settings.

Stored as ``settings.json`` in the active profile's Job OS state directory,
validated field by field, and revisioned so two tabs cannot silently
overwrite each other. Secrets (Firecrawl key, Gmail app password) are never
accepted here: they live in the profile ``.env`` and are reported only as
present or absent.
"""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import threading
from urllib.parse import urlsplit

from api.job_os.paths import job_os_state_dir

SUPPORTED_ATS = ("greenhouse", "lever", "ashby")
REASONING_EFFORTS = ("low", "medium", "high")
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$")
_LOCK = threading.Lock()


class SettingsError(ValueError):
    """Raised for an invalid settings update (HTTP 400)."""


class SettingsConflict(ValueError):
    """Raised when the update was made against an older revision (HTTP 409)."""


def default_settings() -> dict:
    return {
        "revision": 0,
        "firecrawl": {"api_url": ""},
        "ai": {"provider": "openai-codex", "model": "gpt-5.6-luna", "reasoning_effort": "medium"},
        "scout": {"enabled": False, "schedule_hours": 6, "max_results_per_search": 20},
        "notifications": {
            "email_enabled": False,
            "to_address": "",
            "notify_new_matches": True,
            "min_fit_score": 70,
            "daily_digest": True,
            "digest_hour": 8,
            "reply_actions": True,
        },
        "auto_apply": {
            "enabled": False,
            "allowed_ats": list(SUPPORTED_ATS),
            "daily_cap": 5,
            "min_fit_score": 80,
            "dry_run_first": True,
        },
    }


def _bool(value, field):
    if not isinstance(value, bool):
        raise SettingsError(f"{field} must be true or false")
    return value


def _int(value, field, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise SettingsError(f"{field} must be a whole number from {low} to {high}")
    return value


def _text(value, field, limit=64):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise SettingsError(f"{field} must be a short, non-empty text value")
    return value.strip()


def _url(value, field):
    if not isinstance(value, str) or len(value) > 512:
        raise SettingsError(f"{field} must be a URL")
    text = value.strip()
    if not text:
        return ""
    parts = urlsplit(text)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise SettingsError(f"{field} must be an http(s) URL without credentials")
    return text.rstrip("/")


def _email(value, field):
    if not isinstance(value, str):
        raise SettingsError(f"{field} must be an email address")
    text = value.strip()
    if text and not _EMAIL.match(text):
        raise SettingsError(f"{field} must be an email address")
    return text


def _effort(value, field):
    if value not in REASONING_EFFORTS:
        raise SettingsError(f"{field} must be one of {', '.join(REASONING_EFFORTS)}")
    return value


def _ats(value, field):
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SettingsError(f"{field} must be a list")
    picked = [item.strip().lower() for item in value]
    unknown = [item for item in picked if item not in SUPPORTED_ATS]
    if unknown:
        raise SettingsError(f"{field} only supports {', '.join(SUPPORTED_ATS)}")
    return [ats for ats in SUPPORTED_ATS if ats in picked]


_VALIDATORS = {
    "firecrawl": {"api_url": _url},
    "ai": {
        "provider": _text,
        "model": _text,
        "reasoning_effort": _effort,
    },
    "scout": {
        "enabled": _bool,
        "schedule_hours": lambda v, f: _int(v, f, 1, 168),
        "max_results_per_search": lambda v, f: _int(v, f, 1, 100),
    },
    "notifications": {
        "email_enabled": _bool,
        "to_address": _email,
        "notify_new_matches": _bool,
        "min_fit_score": lambda v, f: _int(v, f, 0, 100),
        "daily_digest": _bool,
        "digest_hour": lambda v, f: _int(v, f, 0, 23),
        "reply_actions": _bool,
    },
    "auto_apply": {
        "enabled": _bool,
        "allowed_ats": _ats,
        "daily_cap": lambda v, f: _int(v, f, 1, 50),
        "min_fit_score": lambda v, f: _int(v, f, 0, 100),
        "dry_run_first": _bool,
    },
}


def _path():
    return job_os_state_dir() / "settings.json"


def load_settings() -> dict:
    """Current settings for the active profile, defaults filled in."""
    merged = default_settings()
    try:
        stored = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return merged
    if isinstance(stored, dict):
        if isinstance(stored.get("revision"), int):
            merged["revision"] = stored["revision"]
        for section, fields in _VALIDATORS.items():
            values = stored.get(section)
            if not isinstance(values, dict):
                continue
            for key, validate in fields.items():
                if key in values:
                    try:
                        merged[section][key] = validate(values[key], f"{section}.{key}")
                    except SettingsError:
                        pass  # keep the default for a value that no longer validates
    return merged


def save_settings(patch: dict, *, expected_revision: int) -> dict:
    """Validate ``patch`` (a partial settings object), merge and persist it."""
    if not isinstance(patch, dict):
        raise SettingsError("settings must be an object")
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        raise SettingsError("expected_revision must be an integer")
    with _LOCK:
        current = load_settings()
        if current["revision"] != expected_revision:
            raise SettingsConflict("Settings changed in another tab; reload and try again")
        updated = copy.deepcopy(current)
        for section, values in patch.items():
            if section not in _VALIDATORS:
                raise SettingsError(f"Unknown settings section: {section}")
            if not isinstance(values, dict):
                raise SettingsError(f"{section} must be an object")
            for key, value in values.items():
                validate = _VALIDATORS[section].get(key)
                if validate is None:
                    raise SettingsError(f"Unknown setting: {section}.{key}")
                updated[section][key] = validate(value, f"{section}.{key}")
        updated["revision"] = current["revision"] + 1
        path = _path()
        fd, tmp = tempfile.mkstemp(prefix=".settings-", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(updated, handle, indent=2)
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return updated
