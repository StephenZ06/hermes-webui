"""Official public posting APIs of application-tracking sites.

Greenhouse, Ashby, Workable and SmartRecruiters render posting pages in the
browser, so their raw HTML carries no JSON-LD. Each publishes the same
postings as data through a public, unauthenticated API; Scout reads those
instead of the page. A posting the site no longer lists is reported as closed
(search indexes keep stale links for weeks).

``ats_posting(url, fetch, cache)`` returns ``("posting", fields)``,
``("closed", None)``, or ``("unsupported", None)`` for any other site (the
page is then read through Firecrawl). ``fetch`` is a policy-checked JSON GET
that raises an error whose text contains ``HTTP 404`` for a missing posting.
"""

from __future__ import annotations

import html
import re
from typing import Callable
from urllib.parse import quote, urlsplit

from api.job_os.extract import _html_to_text, _text

Fetch = Callable[[str], object]
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def _workplace(*, remote=False, hybrid=False, text: str = "") -> str:
    lowered = text.lower()
    if hybrid or "hybrid" in lowered:
        return "hybrid"
    if remote or "remote" in lowered:
        return "remote"
    return "onsite" if text.strip() else ""


def _fields(url, *, title, company="", location="", salary="", employment="", workplace="", posted="", description=""):
    title = _text(title)
    if not title:
        return None
    return {"title": title[:240], "company": _text(company)[:240], "location": _text(location)[:240],
            "salary_text": _text(salary)[:120], "employment_type": _text(employment)[:80], "workplace": workplace,
            "posted_at": _text(posted)[:40], "description": description, "canonical_url": url}


def _company_from_slug(slug: str) -> str:
    """Lever and Ashby only give the board slug; show ``acme-labs`` as ``Acme Labs``
    (a slug that already has capitals is kept as written)."""
    words = re.split(r"[-_]+", slug or "")
    return " ".join(w.capitalize() if w.islower() else w for w in words if w)


def _missing(error: Exception) -> bool:
    return "HTTP 404" in str(error)


# ---- Greenhouse ---------------------------------------------------------------
_GREENHOUSE_HOSTS = {"boards.greenhouse.io", "job-boards.greenhouse.io", "job-boards.eu.greenhouse.io"}


def _greenhouse(parts, url, fetch, cache):
    match = re.match(r"^/([A-Za-z0-9_-]+)/jobs/(\d+)", parts.path)
    if not match:
        return "unsupported", None
    try:
        data = fetch(f"https://boards-api.greenhouse.io/v1/boards/{match.group(1)}/jobs/{match.group(2)}?pay_transparency=true")
    except Exception as error:
        if _missing(error):
            return "closed", None
        raise
    if not isinstance(data, dict):
        return "closed", None
    location = (data.get("location") or {}).get("name") if isinstance(data.get("location"), dict) else ""
    salary = ""
    ranges = data.get("pay_input_ranges") if isinstance(data.get("pay_input_ranges"), list) else []
    if ranges and isinstance(ranges[0], dict):
        try:
            low, high = int(ranges[0]["min_cents"]) / 100, int(ranges[0]["max_cents"]) / 100
            salary = f"{_text(ranges[0].get('currency_type'))} {low:,.0f}–{high:,.0f}".strip()
        except (KeyError, TypeError, ValueError):
            salary = ""
    fields = _fields(url, title=data.get("title"), company=data.get("company_name"), location=location, salary=salary,
                     workplace=_workplace(text=f"{data.get('title', '')} {location}"),
                     posted=data.get("first_published") or data.get("updated_at"),
                     description=_html_to_text(html.unescape(str(data.get("content") or ""))))
    return ("posting", fields) if fields else ("closed", None)


# ---- Ashby (whole board, cached per run) ------------------------------------------
def _ashby(parts, url, fetch, cache):
    match = re.match(rf"^/([^/]+)/({_UUID})", parts.path, re.I)
    if not match:
        return "unsupported", None
    board, job_id = match.group(1), match.group(2).lower()
    key = ("ashby", board.lower())
    if key not in cache:
        try:
            cache[key] = fetch(f"https://api.ashbyhq.com/posting-api/job-board/{quote(board)}?includeCompensation=true")
        except Exception as error:
            if _missing(error):
                cache[key] = {"jobs": []}
            else:
                raise
    jobs = (cache[key] or {}).get("jobs") if isinstance(cache[key], dict) else []
    job = next((j for j in jobs or [] if isinstance(j, dict) and str(j.get("id", "")).lower() == job_id), None)
    if job is None:
        return "closed", None
    workplace_type = str(job.get("workplaceType") or "").lower()
    comp = job.get("compensation") if isinstance(job.get("compensation"), dict) else {}
    employment = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(job.get("employmentType") or "")).capitalize()
    fields = _fields(url, title=job.get("title"), company=_company_from_slug(board), location=job.get("location"),
                     salary=comp.get("compensationTierSummary") or "", employment=employment,
                     workplace=_workplace(remote=bool(job.get("isRemote")) or workplace_type == "remote",
                                          hybrid=workplace_type == "hybrid", text=str(job.get("location") or "")),
                     posted=job.get("publishedAt"),
                     description=_html_to_text(job.get("descriptionHtml") or "") or str(job.get("descriptionPlain") or "")[:20000])
    return ("posting", fields) if fields else ("closed", None)


# ---- Workable (whole account, cached per run) --------------------------------------
def _workable(parts, url, fetch, cache):
    match = re.match(r"^/([^/]+)/j/([0-9A-Za-z]+)", parts.path)
    if not match:
        return "unsupported", None
    account, shortcode = match.group(1), match.group(2).upper()
    key = ("workable", account.lower())
    if key not in cache:
        try:
            cache[key] = fetch(f"https://apply.workable.com/api/v1/widget/accounts/{quote(account)}?details=true")
        except Exception as error:
            if _missing(error):
                cache[key] = {"jobs": []}
            else:
                raise
    data = cache[key] if isinstance(cache[key], dict) else {}
    job = next((j for j in data.get("jobs") or [] if isinstance(j, dict) and str(j.get("shortcode", "")).upper() == shortcode), None)
    if job is None:
        return "closed", None
    place = ", ".join(p for p in (_text(job.get("city")), _text(job.get("state")), _text(job.get("country"))) if p)
    remote = str(job.get("telecommuting")).lower() == "true"
    fields = _fields(url, title=job.get("title"), company=data.get("name"),
                     location=(f"Remote ({place})" if place else "Remote") if remote else place,
                     employment=job.get("employment_type"), workplace=_workplace(remote=remote, text=place),
                     posted=job.get("published_on") or job.get("created_at"),
                     description=_html_to_text(job.get("description") or ""))
    return ("posting", fields) if fields else ("closed", None)


# ---- SmartRecruiters --------------------------------------------------------------
def _smartrecruiters(parts, url, fetch, cache):
    match = re.match(r"^/([^/]+)/(\d{6,})", parts.path)
    if not match:
        return "unsupported", None
    try:
        data = fetch(f"https://api.smartrecruiters.com/v1/companies/{quote(match.group(1))}/postings/{match.group(2)}")
    except Exception as error:
        if _missing(error) or "HTTP 400" in str(error):  # SmartRecruiters answers 400 for a removed posting
            return "closed", None
        raise
    if not isinstance(data, dict) or data.get("active") is False:
        return "closed", None
    loc = data.get("location") if isinstance(data.get("location"), dict) else {}
    place = loc.get("fullLocation") or ", ".join(p for p in (_text(loc.get("city")), _text(loc.get("region")), _text(loc.get("country")).upper()) if p)
    sections = ((data.get("jobAd") or {}).get("sections") or {}) if isinstance(data.get("jobAd"), dict) else {}
    description = "\n\n".join(_html_to_text((sections.get(k) or {}).get("text") or "")
                              for k in ("jobDescription", "qualifications", "additionalInformation")
                              if isinstance(sections.get(k), dict))
    fields = _fields(url, title=data.get("name"), company=(data.get("company") or {}).get("name"), location=place,
                     employment=(data.get("typeOfEmployment") or {}).get("label"),
                     workplace=_workplace(remote=bool(loc.get("remote")), hybrid=bool(loc.get("hybrid")), text=str(place)),
                     posted=data.get("releasedDate"), description=description[:20000])
    return ("posting", fields) if fields else ("closed", None)


# ---- Lever -----------------------------------------------------------------------
def _lever(parts, url, fetch, cache):
    match = re.match(rf"^/([^/]+)/({_UUID})", parts.path, re.I)
    if not match:
        return "unsupported", None
    api_host = "api.eu.lever.co" if (parts.hostname or "").lower() == "jobs.eu.lever.co" else "api.lever.co"
    try:
        data = fetch(f"https://{api_host}/v0/postings/{quote(match.group(1))}/{match.group(2)}?mode=json")
    except Exception as error:
        if _missing(error):
            return "closed", None
        raise
    if not isinstance(data, dict) or not data.get("text"):
        return "closed", None
    categories = data.get("categories") if isinstance(data.get("categories"), dict) else {}
    location = categories.get("location") or ", ".join(categories.get("allLocations") or [])
    workplace_type = str(data.get("workplaceType") or "").lower()
    salary = ""
    rng = data.get("salaryRange") if isinstance(data.get("salaryRange"), dict) else None
    if rng and rng.get("min") and rng.get("max"):
        unit = {"per-year-salary": " / year", "per-month-salary": " / month", "per-hour-wage": " / hour"}.get(str(rng.get("interval")), "")
        salary = f"{_text(rng.get('currency'))} {float(rng['min']):,.0f}–{float(rng['max']):,.0f}{unit}".strip()
    body = [_html_to_text(data.get("description") or "")]
    for block in data.get("lists") or []:
        if isinstance(block, dict):
            body.append(_text(block.get("text")) + "\n" + _html_to_text("<ul>" + str(block.get("content") or "") + "</ul>"))
    body.append(_html_to_text(data.get("additional") or ""))
    posted = ""
    try:
        import datetime as _dt
        posted = _dt.datetime.fromtimestamp(int(data.get("createdAt")) / 1000, _dt.timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        posted = ""
    fields = _fields(url, title=data.get("text"), company=_company_from_slug(match.group(1)), location=location, salary=salary,
                     employment=categories.get("commitment"),
                     workplace=workplace_type if workplace_type in ("remote", "hybrid", "onsite") else _workplace(text=str(location)),
                     posted=posted, description="\n\n".join(part for part in body if part)[:20000])
    return ("posting", fields) if fields else ("closed", None)


_ADAPTERS = {
    "jobs.lever.co": _lever,
    "jobs.eu.lever.co": _lever,
    **{host: _greenhouse for host in _GREENHOUSE_HOSTS},
    "jobs.ashbyhq.com": _ashby,
    "apply.workable.com": _workable,
    "jobs.smartrecruiters.com": _smartrecruiters,
}


def ats_posting(url: str, fetch: Fetch, cache: dict) -> tuple[str, dict | None]:
    parts = urlsplit(url)
    adapter = _ADAPTERS.get((parts.hostname or "").lower())
    if adapter is None:
        return "unsupported", None
    return adapter(parts, url, fetch, cache)


def canonical_posting_url(url: str) -> str:
    """Trim trailing ``/apply`` (Lever, Ashby) so a posting and its apply page are one job."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host in {"jobs.lever.co", "jobs.eu.lever.co", "jobs.ashbyhq.com"} and parts.path.rstrip("/").endswith("/application"):
        return url.rstrip("/")[: -len("/application")]
    if host in {"jobs.lever.co", "jobs.eu.lever.co", "jobs.ashbyhq.com"} and parts.path.rstrip("/").endswith("/apply"):
        return url.rstrip("/")[: -len("/apply")]
    return url
