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
        "ai": {"provider": "openai-codex", "model": "gpt-5.6-luna", "reasoning_effort": "medium", "auto_analyze": True},
        # Contact details for tailored resumes and cover letters.
        "applicant": {"full_name": "", "email": "", "phone": "", "location": "", "linkedin_url": "", "portfolio_url": ""},
        # blocked_companies: Scout never saves postings from these employers.
        # schedule_mode "times": runs at run_times in timezone (job ads go up in
        # morning and afternoon waves, so one run follows each); "interval": every
        # schedule_hours. weekend: "saturday" (one run, Saturday only), "same", "none".
        # quiet_skip: after a run with 0-1 new jobs, skip the next run that day.
        # Run times follow each search country's clock (indeed.CLOCKS); timezone
        # is the person's own, used for the evening release of good matches.
        "scout": {"enabled": False, "schedule_mode": "times", "run_times": ["12:30", "18:30"], "weekend": "saturday",
                  "quiet_skip": True, "timezone": "Asia/Kuala_Lumpur", "schedule_hours": 6,
                  "max_results_per_search": 20, "blocked_companies": []},
        # Apify runs the job-site scraper on its own addresses (api/job_os/apify.py).
        # The token is a secret in the env files; these are the non-secret choices.
        # One "<site>_actor" per job site in apify.SITES (its first actor by default).
        "apify": {"enabled": False, **{f"{site}_actor": _default_actor(site) for site in _sites()}, "results_per_city": 50},
        # Sections of the Jobs page that can be hidden.
        "display": {"show_logistics": True},
        "notifications": {
            "email_enabled": False,
            "to_address": "",
            "notify_new_matches": True,
            # A good match: Luna's fit score of the master resume against the job.
            # Good matches wait in the Scout inbox and go out together once
            # release_count are waiting, or at release_cutoff_hour (scout timezone).
            "min_fit_score": 65,
            "release_count": 5,
            "release_cutoff_hour": 20,
            "daily_digest": True,
            "digest_hour": 8,
            "reply_actions": True,
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


def _free_text(value, field, limit):
    if not isinstance(value, str) or len(value) > limit or "\n" in value:
        raise SettingsError(f"{field} must be a single line of up to {limit} characters")
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


def _sites():
    from api.job_os.apify import SITES

    return tuple(SITES)


def _default_actor(site):
    from api.job_os.apify import default_actor

    return default_actor(site)


def _actor_for(site):
    """Only actors Scout has an adapter for (apify.ADAPTERS) can read this site."""
    def check(value, field):
        from api.job_os.apify import SITES

        if value not in SITES[site][1]:
            raise SettingsError(f"{field} must be one of: {', '.join(SITES[site][1])}")
        return value
    return check


def _run_times(value, field):
    if not isinstance(value, list) or not 1 <= len(value) <= 6:
        raise SettingsError(f"{field} must list 1 to 6 times")
    times = []
    for item in value:
        match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", str(item).strip())
        if not match:
            raise SettingsError(f"{field}: {str(item)[:10]!r} is not a time like 12:30")
        times.append(f"{int(match.group(1)):02d}:{match.group(2)}")
    return sorted(set(times))


def _timezone(value, field):
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        ZoneInfo(str(value))
    except (ZoneInfoNotFoundError, ValueError):
        raise SettingsError(f"{field} must be a time zone like Asia/Kuala_Lumpur") from None
    return str(value)


def _choice(*options):
    def check(value, field):
        if value not in options:
            raise SettingsError(f"{field} must be one of: {', '.join(options)}")
        return value
    return check


def _companies(value, field):
    if isinstance(value, str):
        value = value.splitlines()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SettingsError(f"{field} must be a list of company names")
    names = list(dict.fromkeys(item.strip() for item in value if item.strip()))
    if len(names) > 200 or any(len(name) > 120 for name in names):
        raise SettingsError(f"{field} allows up to 200 names of 120 characters")
    return names


_VALIDATORS = {
    "firecrawl": {"api_url": _url},
    "ai": {
        "provider": _text,
        "model": _text,
        "reasoning_effort": _effort,
        "auto_analyze": _bool,
    },
    "applicant": {
        "full_name": lambda v, f: _free_text(v, f, 120),
        "email": _email,
        "phone": lambda v, f: _free_text(v, f, 40),
        "location": lambda v, f: _free_text(v, f, 120),
        "linkedin_url": _url,
        "portfolio_url": _url,
    },
    "apify": {
        "enabled": _bool,
        **{f"{site}_actor": _actor_for(site) for site in _sites()},
        "results_per_city": lambda v, f: _int(v, f, 1, 1000),
    },
    "scout": {
        "enabled": _bool,
        "schedule_mode": _choice("times", "interval"),
        "run_times": _run_times,
        "weekend": _choice("saturday", "same", "none"),
        "quiet_skip": _bool,
        "timezone": _timezone,
        "schedule_hours": lambda v, f: _int(v, f, 1, 168),
        "max_results_per_search": lambda v, f: _int(v, f, 1, 100),
        "blocked_companies": _companies,
    },
    "display": {"show_logistics": _bool},
    "notifications": {
        "email_enabled": _bool,
        "to_address": _email,
        "notify_new_matches": _bool,
        "min_fit_score": lambda v, f: _int(v, f, 0, 100),
        "release_count": lambda v, f: _int(v, f, 1, 50),
        "release_cutoff_hour": lambda v, f: _int(v, f, 0, 23),
        "daily_digest": _bool,
        "digest_hour": lambda v, f: _int(v, f, 0, 23),
        "reply_actions": _bool,
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
