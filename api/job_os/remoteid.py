"""remote.id (remotefreelance.id): remote jobs gathered from JobStreet, LinkedIn,
SEEK and Upwork, read straight from the site (no Firecrawl, no Apify).

Its pages are plain server-rendered HTML: ``/jobs?q=<title>&page=<n>`` lists
matching jobs (a schema.org ItemList in the page), and each job page carries
the title, company, place, pay, type, posted date, the full description and
the link to the posting on its source site. robots.txt allows /jobs; Scout
reads nothing else, waits between pages and stops at a few pages a title.

A job is saved under its source site's own link (a LinkedIn job as
``linkedin.com/jobs/view/<id>``), so a job Scout already has from a LinkedIn
search counts as known instead of being saved twice, and the other way round.
"""

from __future__ import annotations

import html as html_lib
import json
import re
import time
import urllib.parse
import urllib.request

SITE = "remoteid"
NAME = "remote.id"
BASE = "https://remotefreelance.id"
USER_AGENT = "Mozilla/5.0 (compatible; HermesJobs/1.0; personal job search)"
PAGES_PER_QUERY = 3
PAUSE_S = 1.0
TIMEOUT_S = 20
MAX_PAGE_BYTES = 2_000_000
ORIGINS = {"jobstreet": "JobStreet", "linkedin": "LinkedIn", "seek": "SEEK", "upwork": "Upwork"}

_sleep = time.sleep  # tests replace it
_JOB_PATH = re.compile(r"^/jobs/([a-z]+)/([A-Za-z0-9_~-]{3,40})/[a-z0-9-]*$")
_LD_JSON = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "mei", "jun", "jul", "agu", "sep", "okt", "nov", "des"], start=1)}
_MONTHS.update({"may": 5, "aug": 8, "oct": 10, "dec": 12, "agt": 8})


class RemoteIdError(RuntimeError):
    pass


def fetch(url: str) -> str:
    """One page from remotefreelance.id (only that host)."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname != "remotefreelance.id" or not parts.path.startswith("/jobs"):
        raise RemoteIdError("only remotefreelance.id/jobs pages are read")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            if response.status != 200:
                raise RemoteIdError(f"remote.id answered {response.status}")
            return response.read(MAX_PAGE_BYTES).decode("utf-8", "replace")
    except RemoteIdError:
        raise
    except Exception as error:  # timeouts, refusals, HTTP errors
        raise RemoteIdError(f"remote.id could not be read ({type(error).__name__})") from error


def search_url(query: str, page: int = 1) -> str:
    params = {"q": query.strip()}
    if page > 1:
        params["page"] = str(page)
    return f"{BASE}/jobs?{urllib.parse.urlencode(params)}"


def listing_links(page_html: str) -> tuple[list[str], bool]:
    """The job pages a results page lists, and whether a next page exists."""
    links: list[str] = []
    for block in _LD_JSON.findall(page_html):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for node in data if isinstance(data, list) else [data]:
            entity = node.get("mainEntity") if isinstance(node, dict) else None
            for item in (entity or {}).get("itemListElement") or []:
                url = str((item or {}).get("url") or "")
                if url.startswith(BASE + "/jobs/") and _JOB_PATH.match(url[len(BASE):]) and url not in links:
                    links.append(url)
    if not links:  # the list markup itself, should the schema block go away
        for path in re.findall(r'href="(/jobs/[a-z]+/[^"?#]+)"', page_html):
            url = BASE + html_lib.unescape(path)
            if _JOB_PATH.match(path) and url not in links:
                links.append(url)
    nav = re.search(r'<nav class="public-jobs-pagination"[^>]*>(.*?)</nav>', page_html, re.S)
    has_next = bool(nav and re.search(r'rel="next"|>\s*(?:Selanjutnya|Berikutnya|Next)\b', nav.group(1)))
    return links, has_next


def _text(fragment: str) -> str:
    fragment = re.sub(r"<(script|style)\b.*?</\1>", "", fragment, flags=re.S)
    fragment = re.sub(r"</(p|li|h[1-6]|div)>|<br\s*/?>", "\n", fragment)
    text = html_lib.unescape(re.sub(r"<[^>]+>", "", fragment))
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _one(pattern: str, page_html: str) -> str:
    match = re.search(pattern, page_html, re.S)
    return _text(match.group(1)) if match else ""


def posted_date(text: str) -> str:
    """'30 Sep 2026' / '7 Okt 2026' -> '2026-09-30'; '' when unreadable."""
    match = re.match(r"\s*(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?\s+(\d{4})", text or "")
    if not match:
        return ""
    month = _MONTHS.get(match.group(2).lower()[:3])
    return f"{match.group(3)}-{month:02d}-{int(match.group(1)):02d}" if month else ""


def source_link(origin: str, origin_id: str, apply_url: str) -> str:
    """The posting's own link on its source site (stable, without tracking)."""
    if origin == "linkedin" and origin_id.isdigit():
        return f"https://www.linkedin.com/jobs/view/{origin_id}"
    if origin == "jobstreet" and origin_id.isdigit():
        host = urllib.parse.urlsplit(apply_url).hostname or "id.jobstreet.com"
        return f"https://{host}/job/{origin_id}"
    if origin == "seek" and origin_id.isdigit():
        host = urllib.parse.urlsplit(apply_url).hostname or "www.seek.com.au"
        return f"https://{host}/job/{origin_id}"
    parts = urllib.parse.urlsplit(apply_url)
    if parts.scheme == "https" and parts.hostname:
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return ""


def parse_job(page_html: str, url: str) -> dict | None:
    """A posting from one job page, in Scout's posting shape; None if it isn't one."""
    match = _JOB_PATH.match(urllib.parse.urlsplit(url).path)
    title = _one(r'<header class="job-detail-header">.*?<h1>(.*?)</h1>', page_html)
    if not match or not title:
        return None
    origin, origin_id = match.group(1), match.group(2)
    facts = {_text(k).lower(): _text(v) for k, v in re.findall(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", page_html, re.S)}
    def fact(*names: str) -> str:
        return next((facts[n] for n in names if facts.get(n)), "")
    company = _one(r'<p class="job-detail-company">(.*?)</p>', page_html) or fact("perusahaan", "company")
    place = fact("lokasi pada lowongan", "lokasi klien", "location")
    if not place:
        place = re.sub(r"^Lokasi klien:\s*", "", _one(r'<p class="job-detail-location">(.*?)</p>', page_html))
    place = re.sub(r"^[\U0001F1E6-\U0001F1FF]{2}\s*", "", place).strip()
    pay = fact("gaji", "tarif per jam", "anggaran", "salary", "budget")
    if re.search(r"belum dicantumkan|not (listed|specified)", pay, re.I):
        pay = ""
    apply_url = html_lib.unescape(next(iter(re.findall(r'class="fw-button" href="([^"]+)"', page_html)), ""))
    link = source_link(origin, origin_id, apply_url)
    if not link:
        return None
    description = _one(r'<section class="job-detail-description">(.*?)</section>', page_html)
    description = re.sub(r"^Tentang pekerjaan\n", "", description)
    company = company or ("Upwork client" if origin == "upwork" else "")
    country = place.split("·")[0].strip()
    return {
        "title": title[:240],
        "company": company[:240],
        "location": place[:240],
        "country": country[:120],
        "salary_text": pay[:120],
        "employment_type": fact("jenis pekerjaan", "job type")[:60],
        "workplace": "Remote",
        "posted_at": posted_date(fact("diposting", "posted")),
        "description": description[:20000],
        "canonical_url": link,
        "origin": origin,
        "origin_name": ORIGINS.get(origin, origin.title()),
    }


def page_key(url: str) -> str | None:
    """'jobstreet/94318388' for a job page: its source site and that site's id."""
    match = _JOB_PATH.match(urllib.parse.urlsplit(url).path)
    return f"{match.group(1)}/{match.group(2)}" if match else None


def queries_for(titles: list[str], title_filter: list[str]) -> list[str]:
    """What to type into the site's search. It matches the words as one phrase
    ("IT Analyst" misses "IT Help Desk Analyst"; "security" found nothing while
    "analyst" found five), so Scout searches the broadest word, the search's
    title filter or else the last word of each title, and its own title
    matching keeps only the right jobs."""
    from api.job_os.relevance import distinctive

    words = [w for w in (title_filter or []) if str(w).strip()]
    if not words:
        words = [distinctive(t)[-1] for t in titles if distinctive(t)]
    out: list[str] = []
    for word in words:
        word = str(word).strip().lower()
        if word and word not in out:
            out.append(word)
    return out[:6]


def check_layout(fetch_page=None) -> str:
    """'' when the site's unfiltered job list still parses; otherwise why not.
    Run when every search came back empty, to tell "nothing matched" from
    "the site changed and Scout no longer understands its pages"."""
    try:
        links, _more = listing_links((fetch_page or fetch)(BASE + "/jobs"))
    except RemoteIdError as error:
        return str(error)
    if not links:
        return "remote.id's job list could not be read (the site's pages may have changed); Scout needs an update"
    return ""


def search(query: str, *, limit: int, seen_pages: set[str] | None = None,
           fetch_page=None, cancelled=lambda: False) -> tuple[list[str], list[str]]:
    """Job page links for one title, up to `limit`; also the errors met."""
    fetch_page = fetch_page or fetch
    seen_pages = seen_pages if seen_pages is not None else set()
    links: list[str] = []
    errors: list[str] = []
    for page in range(1, PAGES_PER_QUERY + 1):
        if cancelled() or len(links) >= limit:
            break
        if page > 1:
            _sleep(PAUSE_S)
        try:
            page_links, has_next = listing_links(fetch_page(search_url(query, page)))
        except RemoteIdError as error:
            errors.append(str(error))
            break
        fresh = [u for u in page_links if u not in seen_pages]
        seen_pages.update(fresh)
        links.extend(fresh[: max(0, limit - len(links))])
        if not has_next or not page_links:
            break
    return links, errors


def read(url: str, fetch_page=None) -> dict | None:
    """One job page, read after a pause (one page a second at most)."""
    _sleep(PAUSE_S)
    return parse_job((fetch_page or fetch)(url), url)
