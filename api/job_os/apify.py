"""Apify: hosted scrapers ("actors") that Scout can run instead of reading job
sites itself.

A job site refuses a reader that asks for many pages from one address; Apify
runs the scraper on its own pool of addresses and returns structured job
records. One actor per site is configured in Settings -> Apify; Indeed's
default is ``valig/indeed-jobs-scraper`` (about $0.10 per 1,000 jobs plus
$0.001 per run on Apify's free plan). LinkedIn and JobStreet actors can be
added to ``SITES`` the same way.

The API token lives in the profile's env files as ``APIFY_API_TOKEN`` (the
shared secrets file when enabled, like the Gmail credentials). Responses only
ever say whether it is set.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Callable

from api.job_os.env import profile_env_value

TOKEN_KEY = "APIFY_API_TOKEN"
API = "https://api.apify.com/v2"
# site -> default actor. The actor's input and output shapes are mapped below.
SITES = {"indeed": "valig/indeed-jobs-scraper"}
RUN_TIMEOUT_S = 300  # Apify's limit for a synchronous run
_MAX_BODY = 32 * 1024 * 1024
_ACTOR = re.compile(r"^[A-Za-z0-9_.-]{1,80}/[A-Za-z0-9_.-]{1,80}$")
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{10,200}$")


class ApifyError(RuntimeError):
    """Apify refused or could not run the request; the text is safe to show."""


def valid_actor(actor: str) -> bool:
    return bool(_ACTOR.match(str(actor or "")))


def token() -> str | None:
    return profile_env_value(TOKEN_KEY)[0]


def status() -> dict:
    """Presence only: never the token itself."""
    from api.shared_env import shared_env_enabled

    value = token()
    return {"token": bool(value), "token_hint": f"…{value[-4:]}" if value else "",
            "scope": "shared" if shared_env_enabled() else "profile"}


def _request(method: str, path: str, value: str, *, body: dict | None = None, timeout: float = 20.0):
    request = urllib.request.Request(
        API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
        # The token goes in a header, not the URL, so it never lands in a log line.
        headers={"Authorization": f"Bearer {value}", "Content-Type": "application/json", "User-Agent": "HermesJobs/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed Apify host
            raw = response.read(_MAX_BODY + 1)
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            detail = (json.loads(error.read(65536) or b"{}").get("error") or {}).get("message", "")
        except (ValueError, AttributeError):
            pass
        if error.code in (401, 403):
            raise ApifyError("Apify refused the API token. Check it in Settings → Apify.") from error
        if error.code == 402:
            raise ApifyError("Your Apify account is out of credit for this month.") from error
        raise ApifyError(f"Apify returned HTTP {error.code}{': ' + detail[:200] if detail else ''}") from error
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        raise ApifyError("Apify did not answer") from error
    if len(raw) > _MAX_BODY:
        raise ApifyError("Apify's answer was too large")
    try:
        return json.loads(raw.decode("utf-8", "replace") or "null")
    except ValueError as error:
        raise ApifyError("Apify returned something that is not JSON") from error


def verify_token(value: str) -> dict:
    """Who the token belongs to: {"username", "plan"}."""
    data = (_request("GET", "/users/me", value) or {}).get("data") or {}
    plan = data.get("plan") or {}
    return {"username": str(data.get("username") or ""), "plan": str(plan.get("id") or "")}


def connect(value: str, *, verify: Callable[[str], dict] | None = None) -> dict:
    """Check the token with Apify, then save it. Nothing is written if Apify refuses it."""
    from api import profiles
    from api.shared_env import write_env_values

    value = str(value or "").strip()
    if not _TOKEN.match(value):
        raise ApifyError("That doesn't look like an Apify API token (Apify console → Settings → API & Integrations).")
    account = (verify or verify_token)(value)
    write_env_values(profiles.get_active_hermes_home(), {TOKEN_KEY: value})
    return {**status(), **account}


def disconnect() -> dict:
    from api import profiles
    from api.shared_env import write_env_values

    write_env_values(profiles.get_active_hermes_home(), {TOKEN_KEY: None})
    return status()


def run_actor(actor: str, actor_input: dict, *, timeout_s: int = RUN_TIMEOUT_S, value: str | None = None) -> list[dict]:
    """Run an actor and wait for its dataset (one synchronous call)."""
    if not valid_actor(actor):
        raise ApifyError("The Apify actor must look like owner/name")
    value = value or token()
    if not value:
        raise ApifyError("Connect Apify in Settings first.")
    items = _request("POST", f"/acts/{actor.replace('/', '~')}/run-sync-get-dataset-items?timeout={int(timeout_s)}&format=json",
                     value, body=actor_input, timeout=timeout_s + 30)
    if not isinstance(items, list):
        raise ApifyError("Apify returned no job list")
    return [item for item in items if isinstance(item, dict)]


# ---- Indeed (valig/indeed-jobs-scraper) ----------------------------------------
_UNITS = {"YEAR": "year", "MONTH": "month", "WEEK": "week", "DAY": "day", "HOUR": "hour"}


def _money(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{number:,.0f}" if number == int(number) else f"{number:,.2f}"


def _salary(base) -> str:
    if not isinstance(base, dict):
        return ""
    low, high = _money(base.get("min")), _money(base.get("max"))
    if not low and not high:
        return ""
    amount = low if low == high or not high else high if not low else f"{low}–{high}"
    unit = _UNITS.get(str(base.get("unitOfWork") or "").upper())
    return " ".join(p for p in (str(base.get("currencyCode") or ""), amount) if p) + (f" / {unit}" if unit else "")


def _values(mapping) -> list[str]:
    return [str(v) for v in (mapping or {}).values() if v] if isinstance(mapping, dict) else []


def indeed_input(country: str, keywords: str, location: str, *, limit: int, posted_within_days: int) -> dict:
    return {"country": country, "title": keywords, "location": location, "limit": int(limit),
            "datePosted": str(posted_within_days) if posted_within_days else ""}


def indeed_posting(item: dict, host: str) -> dict | None:
    """One actor record as a Scout posting, or None for an expired or keyless one."""
    key = str(item.get("key") or "").strip()
    if not re.fullmatch(r"[0-9A-Za-z]{1,40}", key) or item.get("expired"):
        return None
    where = item.get("location") if isinstance(item.get("location"), dict) else {}
    tags = " ".join(_values(item.get("attributes")) + _values(item.get("jobTypes"))).lower()
    workplace = "remote" if "remote" in tags else "hybrid" if "hybrid" in tags else ""
    description = item.get("description")
    text = description.get("text") if isinstance(description, dict) else description
    return {
        "title": str(item.get("title") or "").strip()[:240],
        "company": str((item.get("employer") or {}).get("name") or "").strip()[:240] if isinstance(item.get("employer"), dict) else "",
        # Indeed's region codes ("M14", "061") mean nothing to a reader; a state like "NY" does.
        "location": ", ".join(p for p in (str(where.get("city") or ""), str(where.get("admin1Code") or ""))
                              if p and not re.fullmatch(r"[A-Za-z]?\d+", p))[:240],
        "country": str(where.get("countryName") or "")[:80],
        "salary_text": _salary(item.get("baseSalary"))[:120],
        "employment_type": ", ".join(_values(item.get("jobTypes")))[:60],
        "workplace": workplace,
        "posted_at": str(item.get("datePublished") or item.get("dateOnIndeed") or "")[:10],
        "description": str(text or "").strip()[:20000],
        "canonical_url": f"https://{host}/viewjob?jk={key}",
    }
