"""Apify: hosted scrapers ("actors") that Scout can run instead of reading job
sites itself.

A job site refuses a reader that asks for many pages from one address; Apify
runs the scraper on its own pool of addresses and returns structured job
records. One actor per site is configured in Settings -> Apify; Indeed's
default is ``valig/indeed-jobs-scraper`` (about $0.10 per 1,000 jobs plus
$0.001 per run on Apify's free plan); LinkedIn's is
``curious_coder/linkedin-jobs-scraper``. Each actor Scout can read has an
``Adapter`` (its input and its records) in ``ADAPTERS``; ``SITES`` lists the
job sites and their actors, first one the default. Adding a site or another
scraper is one adapter and one ``SITES`` entry.

The API token lives in the profile's env files as ``APIFY_API_TOKEN`` (the
shared secrets file when enabled, like the Gmail credentials). Responses only
ever say whether it is set.
"""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from api.job_os.env import profile_env_value

TOKEN_KEY = "APIFY_API_TOKEN"
API = "https://api.apify.com/v2"
# site -> default actor. The actor's input and output shapes are mapped below.
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


_DEADLINE_KEYS = ("validThrough", "expirationDate", "expiryDate", "expiresAt", "closingDate", "applicationDeadline",
                  "deadline", "applyBefore")


def _deadline(item: dict) -> str:
    """The first closing-date field an actor sends (validated where the job is saved)."""
    return next((str(item[k])[:40] for k in _DEADLINE_KEYS if item.get(k)), "")


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
        "deadline": _deadline(item),
        "canonical_url": f"https://{host}/viewjob?jk={key}",
    }


# ---- LinkedIn ------------------------------------------------------------------
# valig/linkedin-jobs-scraper:
# LinkedIn has no per-country site: the country goes into the location text.
# Its date filter has only 1, 7 and 30 days; Scout drops anything older than
# the search's own window afterwards.
_LINKEDIN_AGE = {0: "", 1: "r86400", 3: "r604800", 7: "r604800", 14: "r2592000"}


MAX_SKIP_IDS = 1000


def linkedin_input(country_name: str, keywords: str, location: str, *, limit: int, posted_within_days: int,
                   known_ids: list[str] | None = None) -> dict:
    """``known_ids``: LinkedIn jobs Scout already has. The actor leaves them out,
    so a repeat run is not charged for them again."""
    payload = {"keywords": keywords, "location": f"{location}, {country_name}" if location else country_name,
               "limit": int(limit), "datePosted": _LINKEDIN_AGE.get(int(posted_within_days or 0), "")}
    if known_ids:
        payload["skipJobId"] = list(known_ids)[-MAX_SKIP_IDS:]
    return payload


def _workplace_from(*texts: str) -> str:
    text = " ".join(t for t in texts if t).lower()
    return "remote" if "remote" in text else "hybrid" if "hybrid" in text else "onsite" if "on-site" in text or "onsite" in text else ""


def linkedin_posting(item: dict) -> dict | None:
    job_id = str(item.get("id") or "").strip()
    if not re.fullmatch(r"\d{4,20}", job_id):
        return None
    location = str(item.get("location") or "").strip()
    return {
        "title": str(item.get("title") or "").strip()[:240],
        "company": str(item.get("companyName") or "").strip()[:240],
        "location": location[:240],
        "salary_text": str(item.get("salary") or "").strip()[:120],
        "employment_type": str(item.get("contractType") or "").strip()[:60],
        "workplace": _workplace_from(location, str(item.get("workplaceType") or "")),
        "posted_at": str(item.get("postedDate") or "")[:10],
        "description": str(item.get("description") or "").strip()[:20000],
        "deadline": _deadline(item),
        "canonical_url": f"https://www.linkedin.com/jobs/view/{job_id}",
    }


# curious_coder/linkedin-jobs-scraper: the most used LinkedIn actor. It has no
# title filter or skip list, so those jobs are returned (and charged) and
# Scout filters them out afterwards.
_CURIOUS_AGE = {0: "anyTime", 1: "past24Hours", 3: "pastWeek", 7: "pastWeek", 14: "pastMonth"}


def linkedin_curious_input(country_name: str, keywords: str, location: str, *, limit: int, posted_within_days: int) -> dict:
    return {"keywords": keywords, "location": f"{location}, {country_name}" if location else country_name,
            "datePosted": _CURIOUS_AGE.get(int(posted_within_days or 0), "anyTime"), "limitPerSource": int(limit),
            # Company pages cost an extra request per job and Scout doesn't use them.
            "scrapeCompany": False, "splitByLocation": False}


def linkedin_curious_posting(item: dict) -> dict | None:
    job_id = str(item.get("id") or "").strip()
    if not re.fullmatch(r"\d{4,20}", job_id):
        return None
    location = str(item.get("location") or "").strip()
    salary = item.get("salaryInfo")
    salary_text = " – ".join(str(v) for v in salary if v) if isinstance(salary, list) else str(salary or "")
    return {
        "title": str(item.get("title") or "").strip()[:240],
        "company": str(item.get("companyName") or "").strip()[:240],
        "location": location[:240],
        "salary_text": salary_text.strip()[:120],
        "employment_type": str(item.get("employmentType") or "").strip()[:60],
        "workplace": _workplace_from(location, str(item.get("workplaceType") or "")),
        "posted_at": str(item.get("postedAt") or "")[:10],
        "description": str(item.get("descriptionText") or "").strip()[:20000],
        "deadline": _deadline(item),
        "canonical_url": f"https://www.linkedin.com/jobs/view/{job_id}",
    }


# ---- Bayt (blackfalcondata/bayt-scraper) ---------------------------------------------
# The Gulf's main job board. Scout's country codes are Bayt's in lower case.
BAYT_COUNTRIES = ("ae", "sa", "qa", "kw", "bh", "om", "eg", "jo", "lb", "pk", "in", "iq", "ma")
_BAYT_AGE = {0: "", 1: "past-24h", 3: "past-week", 7: "past-week", 14: "past-month"}


def bayt_input(country: str, keywords: str, location: str, *, limit: int, posted_within_days: int) -> dict:
    # Not descriptionFormat="text": with it the actor returned only a ~120-character
    # teaser in "description" (checked 2026-10-08); the default carries the full text.
    payload = {"query": keywords, "country": country.upper(), "location": location, "maxResults": int(limit),
               "sortBy": "date", "includeDetails": True}
    if _BAYT_AGE.get(int(posted_within_days or 0)):
        payload["datePosted"] = _BAYT_AGE[int(posted_within_days)]
    return payload


_BAYT_URL = re.compile(r"^https://www\.bayt\.com/en/[a-z-]+/jobs/[a-z0-9-]*-(\d{4,12})/?$")


def bayt_posting(item: dict) -> dict | None:
    match = _BAYT_URL.match(str(item.get("url") or "").split("?")[0])
    if not match:
        return None
    location = html.unescape(str(item.get("location") or "")).strip()
    text = lambda key: html.unescape(str(item.get(key) or "")).strip()  # noqa: E731 - Bayt sends "&amp;" in titles
    return {
        "title": text("title")[:240],
        "company": text("company")[:240],
        "location": location[:240],
        "salary_text": text("salaryText")[:120],
        "employment_type": text("employmentType")[:60],
        "workplace": "remote" if item.get("isRemote") else _workplace_from(location),
        "posted_at": str(item.get("postedDate") or item.get("postedAt") or "")[:10],
        "description": str(item.get("description") or "").strip()[:20000],
        "deadline": _deadline(item),
        "canonical_url": match.group(0).rstrip("/") + "/",
    }


def state_key(*parts: str) -> str:
    """A stable, safe name for an incremental actor's memory."""
    text = "-".join(re.sub(r"[^a-z0-9]+", "-", str(p).lower()).strip("-") for p in parts if p)
    return ("hermes-" + text)[:80]


# ---- registry ------------------------------------------------------------------
@dataclass(frozen=True)
class Adapter:
    """How Scout talks to one actor: its input, its records, and what it can
    do on its own side (dropping titles, skipping known jobs)."""
    actor: str
    site: str
    price: str  # for Settings, free plan
    build: Callable[[dict], dict]
    parse: Callable[[dict, dict], dict | None]
    title_filter: str = ""  # the input field taking title phrases, if any
    skip_known: str = ""  # the input field taking known job ids, if any
    incremental: bool = False  # remembers earlier runs itself (incrementalMode + stateKey)


ADAPTERS: dict[str, Adapter] = {a.actor: a for a in (
    Adapter("valig/indeed-jobs-scraper", "indeed", "$0.001 a run + $0.10 per 1,000 jobs",
            lambda c: indeed_input(c["country"], c["keywords"], c["location"], limit=c["limit"],
                                   posted_within_days=c["posted_within_days"]),
            lambda item, c: indeed_posting(item, c["indeed_host"])),
    Adapter("curious_coder/linkedin-jobs-scraper", "linkedin", "$0.00005 a run + $2.00 per 1,000 jobs",
            lambda c: linkedin_curious_input(c["country_name"], c["keywords"], c["location"], limit=c["limit"],
                                             posted_within_days=c["posted_within_days"]),
            lambda item, c: linkedin_curious_posting(item)),
    Adapter("valig/linkedin-jobs-scraper", "linkedin", "$0.001 a run + $0.40 per 1,000 jobs",
            lambda c: linkedin_input(c["country_name"], c["keywords"], c["location"], limit=c["limit"],
                                     posted_within_days=c["posted_within_days"]),
            lambda item, c: linkedin_posting(item), title_filter="titleInclude", skip_known="skipJobId"),
    Adapter("blackfalcondata/bayt-scraper", "bayt", "$0.0005 a run + $0.99 per 1,000 jobs",
            lambda c: bayt_input(c["country"], c["keywords"], c["location"], limit=c["limit"],
                                 posted_within_days=c["posted_within_days"]),
            lambda item, c: bayt_posting(item), incremental=True),
)}
# site -> (name, actors it can use with the first the default, countries it
# covers or None for any)
SITES: dict[str, tuple[str, tuple[str, ...], tuple[str, ...] | None]] = {
    "indeed": ("Indeed", ("valig/indeed-jobs-scraper",), None),
    "linkedin": ("LinkedIn", ("curious_coder/linkedin-jobs-scraper", "valig/linkedin-jobs-scraper"), None),
    "bayt": ("Bayt", ("blackfalcondata/bayt-scraper",), BAYT_COUNTRIES),
}
SITE_NAMES = {site: entry[0] for site, entry in SITES.items()}


def covers(site: str, country: str) -> bool:
    countries = SITES[site][2]
    return countries is None or country in countries


def default_actor(site: str) -> str:
    return SITES[site][1][0]


def adapter(site: str, actor: str) -> Adapter:
    found = ADAPTERS.get(actor)
    if found is None or found.site != site:
        raise ApifyError(f"Scout can't read {actor!r} for {SITE_NAMES.get(site, site)}; pick a scraper in Settings → Apify")
    return found


def sites_payload() -> list[dict]:
    """Sites and their scrapers, for the Scout form and Settings."""
    from api.job_os import remoteid

    return [{"key": site, "name": name, "needs_apify": site != "indeed", "countries": list(countries) if countries else None,
             "actors": [{"actor": a, "price": ADAPTERS[a].price} for a in actors]}
            for site, (name, actors, countries) in SITES.items()] + [
        # Read straight from the site (remoteid.py): no scraper to choose, no Apify needed.
        {"key": remoteid.SITE, "name": remoteid.NAME, "needs_apify": False, "countries": None, "actors": []}]


# ---- usage ----------------------------------------------------------------------
USAGE_TTL_S = 600  # Apify's figure moves slowly; don't ask on every page refresh
WARN_RATIO = 0.8
_usage_cache: dict = {}


def usage(*, now: float | None = None, fetch: Callable[[str], dict] | None = None) -> dict | None:
    """This month's Apify spend against the account's monthly limit:
    {used_usd, limit_usd, ratio, warn, cycle_end}, or None without a token or
    when Apify doesn't answer. Cached for USAGE_TTL_S per token."""
    import time

    value = token()
    if not value:
        return None
    now = time.time() if now is None else now
    key = value[-8:]
    cached = _usage_cache.get(key)
    if cached and now - cached[0] < USAGE_TTL_S:
        return cached[1]
    try:
        data = ((fetch or (lambda v: _request("GET", "/users/me/limits", v)))(value) or {}).get("data") or {}
    except ApifyError:
        return cached[1] if cached else None
    used = float((data.get("current") or {}).get("monthlyUsageUsd") or 0)
    limit = float((data.get("limits") or {}).get("maxMonthlyUsageUsd") or 0)
    ratio = used / limit if limit else 0.0
    result = {"used_usd": round(used, 2), "limit_usd": round(limit, 2), "ratio": round(ratio, 3),
              "warn": ratio >= WARN_RATIO, "cycle_end": str((data.get("monthlyUsageCycle") or {}).get("endAt") or "")[:10]}
    _usage_cache.clear()
    _usage_cache[key] = (now, result)
    return result
