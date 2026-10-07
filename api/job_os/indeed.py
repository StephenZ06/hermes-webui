"""Indeed: the one job site Scout searches.

Indeed runs a separate site per country (malaysia.indeed.com, sg.indeed.com,
...), each with its own listings, so a saved search names its country and
Scout searches that site directly: ``https://<host>/jobs?q=<keywords>&l=<city>``.
"""

from __future__ import annotations

from urllib.parse import urlencode

# code -> (name, host). Hosts are Indeed's own country sites.
COUNTRIES: dict[str, tuple[str, str]] = {
    "my": ("Malaysia", "malaysia.indeed.com"),
    "sg": ("Singapore", "sg.indeed.com"),
    "id": ("Indonesia", "id.indeed.com"),
    "ph": ("Philippines", "ph.indeed.com"),
    "th": ("Thailand", "th.indeed.com"),
    "vn": ("Vietnam", "vn.indeed.com"),
    "hk": ("Hong Kong", "hk.indeed.com"),
    "jp": ("Japan", "jp.indeed.com"),
    "in": ("India", "in.indeed.com"),
    "ae": ("United Arab Emirates", "ae.indeed.com"),
    "qa": ("Qatar", "qa.indeed.com"),
    "sa": ("Saudi Arabia", "sa.indeed.com"),
    "kw": ("Kuwait", "kw.indeed.com"),
    "bh": ("Bahrain", "bh.indeed.com"),
    "om": ("Oman", "om.indeed.com"),
    "au": ("Australia", "au.indeed.com"),
    "nz": ("New Zealand", "nz.indeed.com"),
    "uk": ("United Kingdom", "uk.indeed.com"),
    "ie": ("Ireland", "ie.indeed.com"),
    "de": ("Germany", "de.indeed.com"),
    "fr": ("France", "fr.indeed.com"),
    "nl": ("Netherlands", "nl.indeed.com"),
    "us": ("United States", "www.indeed.com"),
    "ca": ("Canada", "ca.indeed.com"),
    "za": ("South Africa", "za.indeed.com"),
}
# Each country's own clock and working week (Monday=0 ... Sunday=6), so a
# scheduled run follows that country's posting day: Qatar and most of the Gulf
# work Sunday to Thursday, the UAE and the rest Monday to Friday.
MON_FRI = (0, 1, 2, 3, 4)
SUN_THU = (6, 0, 1, 2, 3)
CLOCKS: dict[str, tuple[str, tuple[int, ...]]] = {
    "my": ("Asia/Kuala_Lumpur", MON_FRI), "sg": ("Asia/Singapore", MON_FRI), "id": ("Asia/Jakarta", MON_FRI),
    "ph": ("Asia/Manila", MON_FRI), "th": ("Asia/Bangkok", MON_FRI), "vn": ("Asia/Ho_Chi_Minh", MON_FRI),
    "hk": ("Asia/Hong_Kong", MON_FRI), "jp": ("Asia/Tokyo", MON_FRI), "in": ("Asia/Kolkata", MON_FRI),
    "ae": ("Asia/Dubai", MON_FRI), "qa": ("Asia/Qatar", SUN_THU), "sa": ("Asia/Riyadh", SUN_THU),
    "kw": ("Asia/Kuwait", SUN_THU), "bh": ("Asia/Bahrain", SUN_THU), "om": ("Asia/Muscat", SUN_THU),
    "au": ("Australia/Sydney", MON_FRI), "nz": ("Pacific/Auckland", MON_FRI), "uk": ("Europe/London", MON_FRI),
    "ie": ("Europe/Dublin", MON_FRI), "de": ("Europe/Berlin", MON_FRI), "fr": ("Europe/Paris", MON_FRI),
    "nl": ("Europe/Amsterdam", MON_FRI), "us": ("America/New_York", MON_FRI), "ca": ("America/Toronto", MON_FRI),
    "za": ("Africa/Johannesburg", MON_FRI),
}


def clock(code: str) -> tuple[str, tuple[int, ...]] | None:
    return CLOCKS.get(code)


# Indeed's "date posted" filter (fromage), in days. 0 = any time.
POSTED_WITHIN_DAYS = (0, 1, 3, 7, 14)
RESULTS_PER_PAGE = 10  # Indeed's page size; ``start`` steps by this


def country_name(code: str) -> str:
    return COUNTRIES.get(code, ("", ""))[0]


def country_host(code: str) -> str:
    return COUNTRIES[code][1]


def search_url(code: str, keywords: str, location: str = "", *, posted_within_days: int = 0, page: int = 0) -> str:
    """The results page for one query on the country's Indeed site."""
    params = {"q": keywords, "l": location}
    if posted_within_days:
        params["fromage"] = str(posted_within_days)
    if page:
        params["start"] = str(page * RESULTS_PER_PAGE)
    return f"https://{country_host(code)}/jobs?{urlencode(params)}"


def countries_payload() -> list[dict]:
    return [{"code": code, "name": name, "host": host} for code, (name, host) in COUNTRIES.items()]
