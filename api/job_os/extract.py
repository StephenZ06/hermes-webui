"""Read a job posting from a page's schema.org ``JobPosting`` data.

Almost every real posting page (Greenhouse, Lever, Ashby, Workable,
SmartRecruiters, most company career sites) embeds a JSON-LD ``JobPosting``
block for search engines. Reading it gives exact fields without an AI call;
a page without one is treated as "not a single posting" (a search-results or
listing page) and skipped. Page content is untrusted: it is only parsed into
plain strings, never executed or interpreted as instructions.
"""

from __future__ import annotations

import html
import json
import re
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

from api.job_os import posting_guard

MAX_DESCRIPTION = 20000
_LD_JSON = re.compile(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.I | re.S)
_EMPLOYMENT = {
    "FULL_TIME": "Full time", "PART_TIME": "Part time", "CONTRACTOR": "Contract", "CONTRACT": "Contract",
    "TEMPORARY": "Temporary", "INTERN": "Internship", "INTERNSHIP": "Internship", "PER_DIEM": "Per diem",
    "VOLUNTEER": "Volunteer", "OTHER": "Other",
}
_UNITS = {"YEAR": "year", "MONTH": "month", "WEEK": "week", "DAY": "day", "HOUR": "hour"}


def _types(node) -> set[str]:
    raw = node.get("@type") if isinstance(node, dict) else None
    values = raw if isinstance(raw, list) else [raw]
    return {str(v) for v in values if v}


def _walk(node):
    if isinstance(node, list):
        for item in node:
            yield from _walk(item)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node:
                yield from _walk(node[key])


def _text(value) -> str:
    if isinstance(value, list):
        return ", ".join(dict.fromkeys(t for t in (_text(v) for v in value) if t))
    if isinstance(value, dict):
        value = value.get("name") or value.get("@value") or ""
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def _html_to_text(markup: str) -> str:
    text = str(markup or "")
    text = re.sub(r"(?i)<li[^>]*>", "\n• ", text)
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|h[1-6]|li|ul|ol|tr)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    return text[:MAX_DESCRIPTION]


def _location(posting: dict) -> str:
    places = posting.get("jobLocation")
    parts: list[str] = []
    for place in places if isinstance(places, list) else [places]:
        if not isinstance(place, dict):
            continue
        address = place.get("address") if isinstance(place.get("address"), dict) else {}
        label = ", ".join(_text(address.get(k)) for k in ("addressLocality", "addressRegion", "addressCountry")
                          if _text(address.get(k)))
        label = label or _text(place.get("name"))
        if label and label not in parts:
            parts.append(label)
    return "; ".join(parts[:3])


def _salary(posting: dict) -> str:
    salary = posting.get("baseSalary") or posting.get("estimatedSalary")
    if isinstance(salary, list):
        salary = salary[0] if salary else None
    if not isinstance(salary, dict):
        return ""
    currency = _text(salary.get("currency"))
    value = salary.get("value")
    unit = ""
    if isinstance(value, dict):
        unit = _UNITS.get(str(value.get("unitText") or "").upper(), "")
        low, high, single = value.get("minValue"), value.get("maxValue"), value.get("value")
    else:
        low = high = None
        single = value
    def fmt(n):
        try:
            number = float(n)
        except (TypeError, ValueError):
            return ""
        return f"{number:,.0f}" if number >= 100 else f"{number:g}"
    if fmt(low) and fmt(high) and fmt(low) != fmt(high):
        amount = f"{fmt(low)}–{fmt(high)}"
    else:
        amount = fmt(low) or fmt(high) or fmt(single)
    if not amount:
        return ""
    return " ".join(part for part in (currency, amount) if part) + (f" / {unit}" if unit else "")


def _employment(posting: dict) -> str:
    raw = posting.get("employmentType")
    values = raw if isinstance(raw, list) else [raw]
    labels = [_EMPLOYMENT.get(str(v).upper().replace("-", "_").replace(" ", "_"), _text(v)) for v in values if v]
    return ", ".join(dict.fromkeys(label for label in labels if label))


def extract_job_posting(page_html: str, url: str) -> dict | None:
    """The posting's fields from ``page_html``, or None when it holds no JobPosting."""
    for block in _LD_JSON.findall(page_html or ""):
        try:
            data = json.loads(html.unescape(block).strip())
        except ValueError:
            continue
        for node in _walk(data):
            if "JobPosting" not in _types(node):
                continue
            title = _text(node.get("title"))
            if not title:
                continue
            org = node.get("hiringOrganization")
            remote = str(node.get("jobLocationType") or "").upper() == "TELECOMMUTE"
            location = _location(node)
            if remote:
                region = _text(node.get("applicantLocationRequirements"))
                location = f"Remote ({region})" if region else (location or "Remote")
            haystack = f"{title} {location}".lower()
            workplace = "remote" if remote else "hybrid" if "hybrid" in haystack else (
                "remote" if "remote" in haystack else "onsite" if location else "")
            description, hidden = posting_guard.strip_hidden_html(node.get("description") or "")
            return {
                "title": title[:240],
                "company": _text(org)[:240],
                "location": location[:240],
                "salary_text": _salary(node)[:120],
                "employment_type": _employment(node)[:80],
                "workplace": workplace,
                "posted_at": _text(node.get("datePosted"))[:40],
                "description": _html_to_text(description),
                "guard_hidden": hidden,
                "canonical_url": url,
            }
    return None


def _strip_fragment(link: str) -> str:
    parts = urlsplit(link)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


# ---- Indeed -------------------------------------------------------------------
# Search engines index Indeed's results pages rather than single postings. A
# posting is reached through a click link (/rc/clk?jk=<key>&bb=<token>): Indeed
# serves those to automated readers but refuses /viewjob?jk=<key>, and the click
# token changes on every results page, so the job key identifies the posting.
_INDEED_POSTING_PATHS = {"/rc/clk", "/pagead/clk", "/viewjob"}
_INDEED_KEY = re.compile(r"^[0-9A-Za-z]{1,40}$")


def is_indeed(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host == "indeed.com" or host.endswith(".indeed.com")


def indeed_job_key(url: str) -> str | None:
    """The posting key of an Indeed posting link, or None for any other link."""
    if not is_indeed(url):
        return None
    parts = urlsplit(url)
    if parts.path.rstrip("/") not in _INDEED_POSTING_PATHS:
        return None
    key = (parse_qs(parts.query).get("jk") or [""])[0]
    return key if _INDEED_KEY.match(key) else None


def indeed_posting_url(url: str) -> str:
    """The stable address of an Indeed posting (what is stored and shown)."""
    return f"https://{urlsplit(url).hostname.lower()}/viewjob?jk={indeed_job_key(url)}"


def indeed_posting_links(links: list[str], page_url: str, *, limit: int = 50) -> list[str]:
    """Click links to single postings on an Indeed results page, one per posting."""
    picked: dict[str, str] = {}
    for raw in links or []:
        link = _strip_fragment(urljoin(page_url, str(raw)))
        key = indeed_job_key(link)
        if key and key not in picked and urlsplit(link).path.rstrip("/") != "/viewjob":
            picked[key] = link
        if len(picked) >= limit:
            break
    return list(picked.values())


def looks_like_single_posting(url: str) -> bool:
    """False for an Indeed results page; True for a posting link (and for any
    other site, which is judged by the structured data on its page)."""
    if is_indeed(url):
        return indeed_job_key(url) is not None
    return True
