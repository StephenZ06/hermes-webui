"""Closing dates, the daily expiry sweep, the daily posting re-check and the
closing-soon and age labels."""

from __future__ import annotations

import json

import pytest
from dataclasses import replace
from datetime import date

from api.job_os import apify, applications, checks, expiry, extract, notify
from api.job_os.db import connect_job_os
from api.job_os.models import JobStatus
from api.job_os.repository import create_job, get_job, normalize_job_input, parse_deadline
from tests.test_job_os_tailor import store  # noqa: F401 - shared fixture

TODAY = date(2026, 10, 27)


def _job(slug, *, deadline="", posted_at="", status="analyzed"):
    job = create_job(replace(normalize_job_input({"title": f"Analyst {slug}", "canonical_url": f"https://jobs.example.test/{slug}",
                                                  "deadline": deadline, "posted_at": posted_at}), description="SQL"),
                     status=JobStatus.SCRAPED)
    conn = connect_job_os()
    conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, job.id))
    conn.commit()
    conn.close()
    return get_job(job.id)


def test_deadlines_are_validated_and_bad_ones_dropped():
    assert parse_deadline("2026-11-03T23:59:00Z") == "2026-11-03"
    assert parse_deadline("2026-02-30") == "" and parse_deadline("next Friday") == "" and parse_deadline(None) == ""
    ld = {"@type": "JobPosting", "title": "Analyst", "description": "x", "validThrough": "2026-11-15T00:00"}
    posting = extract.extract_job_posting(f'<script type="application/ld+json">{json.dumps(ld)}</script>', "https://jobs.example.test/x")
    assert normalize_job_input({**posting, "canonical_url": "https://jobs.example.test/x"}).deadline == "2026-11-15"
    item = {"id": "123456", "title": "Analyst", "expirationDate": "2026-12-01"}
    assert apify.linkedin_posting(item)["deadline"] == "2026-12-01"


def test_the_sweep_expires_past_deadlines_only(store):  # noqa: F811
    past, near, none, applied = _job("past", deadline="2026-10-26"), _job("near", deadline="2026-10-30"), _job("none"), \
        _job("applied", deadline="2026-10-01", status="submitted")
    out = expiry.sweep(on=TODAY)
    assert out == {"expired": 1, "closing": 1}
    assert get_job(past.id).status == JobStatus.EXPIRED
    assert get_job(near.id).status == get_job(none.id).status == JobStatus.ANALYZED
    assert get_job(applied.id).status == JobStatus.SUBMITTED  # applied: not ours to expire
    moved = [e for e in applications.timeline(past.id) if e["type"] == "status_changed"][-1]["data"]
    assert moved == {"from": "analyzed", "to": "expired", "by": "deadline", "deadline": "2026-10-26"}
    board = {c["key"]: [j["id"] for j in c["jobs"]] for c in applications.board()["columns"]}
    assert past.id in board["closed"]  # Closed, with the reason in its activity


def test_closing_soon_and_age_labels(store):  # noqa: F811
    soon = _job("soon", deadline="2026-10-28", posted_at="2026-08-01")
    shown = {c["key"]: c for c in checks.job_checks(soon, None, on=TODAY)}
    assert shown["deadline"]["short"] == "Closes tomorrow" and shown["deadline"]["tone"] == "danger"
    assert shown["stale"]["short"] == "87 days old" and shown["stale"]["tone"] == "warn"
    later = _job("later", deadline="2026-11-02", posted_at="2026-10-20")
    shown = {c["key"]: c for c in checks.job_checks(later, None, on=TODAY)}
    assert shown["deadline"]["short"] == "Closes in 6 days" and shown["deadline"]["tone"] == "warn" and "stale" not in shown
    assert checks.job_checks(_job("far", deadline="2026-12-31"), None, on=TODAY) == []


def test_closing_soon_reaches_the_digest(store, monkeypatch):  # noqa: F811
    monkeypatch.setattr(expiry, "today", lambda now=None: TODAY)
    _job("digest", deadline="2026-10-29")
    subject, body = notify.build_digest()
    assert "Closing soon:\n  • Analyst digest at ? — closes in 2 days" in body


def test_the_recheck_reads_410_as_expired_and_404_as_unknown(store, monkeypatch):  # noqa: F811
    monkeypatch.setattr("api.job_os.network_policy.validate_external_job_url", lambda url, **kw: url)
    gone, missing, filled, open_ = (_job(s, status="shortlisted") for s in ("gone", "missing", "filled", "open"))
    pages = {gone.canonical_url: {"status": 410, "html": ""},
             missing.canonical_url: {"status": 404, "html": ""},
             filled.canonical_url: {"status": 200, "html": "<p>Sorry, this position has been filled.</p>"},
             open_.canonical_url: {"status": 200, "html": "<p>Apply below</p>"}}

    class Client:
        def scrape(self, url):
            return pages[url]
    out = expiry.recheck(client=Client(), now=1_000_000)
    assert out == {"checked": 4, "expired": 2, "unknown": 2}
    assert get_job(gone.id).status == get_job(filled.id).status == JobStatus.EXPIRED
    assert get_job(missing.id).status == get_job(open_.id).status == JobStatus.SHORTLISTED
    # Each posting is read at most once a day.
    assert expiry.recheck(client=Client(), now=1_000_000 + 3600)["checked"] == 0
    assert expiry.recheck(client=Client(), now=1_000_000 + 86400)["checked"] == 2


def test_the_tick_runs_once_a_day(store, monkeypatch):  # noqa: F811
    monkeypatch.setattr(expiry, "today", lambda now=None: TODAY)
    calls = []
    assert expiry.tick(recheck_with=lambda **kw: calls.append(1)) is True
    assert expiry.tick(recheck_with=lambda **kw: calls.append(1)) is False
    assert calls == [1]


def test_every_job_not_yet_applied_for_is_rechecked_and_closed_with_a_reason(store, monkeypatch):  # noqa: F811
    from api.job_os.api import _job_payload

    monkeypatch.setattr("api.job_os.network_policy.validate_external_job_url", lambda url, **kw: url)
    new, applied = _job("fresh", status="scraped"), _job("sent", status="submitted")
    seen = []

    class Client:
        def scrape(self, url):
            seen.append(url)
            return {"status": 200, "html": "<h1>Analyst</h1><p>This job is no longer accepting applications.</p>"}
    assert expiry.recheck(client=Client(), now=2_000_000)["expired"] == 1
    assert seen == [new.canonical_url]  # an application's outcome comes from the employer
    assert get_job(new.id).status == JobStatus.EXPIRED and get_job(applied.id).status == JobStatus.SUBMITTED
    reason = expiry.closed_reasons([new.id])[new.id]
    assert reason == "The posting says “no longer accepting applications”"
    assert _job_payload(get_job(new.id))["closed_reason"] == reason
    closed = [c for c in applications.board()["columns"] if c["key"] == "closed"][0]["jobs"]
    assert [c["closed_reason"] for c in closed if c["id"] == new.id] == [reason]


def test_a_sign_in_or_bot_check_is_not_a_closed_posting():
    url = "https://www.linkedin.com/jobs/view/123"
    wall = {"status": 200, "html": "<p>Sign in to see this job</p>", "final_url": "https://www.linkedin.com/authwall?trk=x"}
    bot = {"status": 200, "html": "<title>Just a moment...</title>", "final_url": url}
    moved = {"status": 200, "html": "<p>Search all jobs</p>", "final_url": "https://www.linkedin.com/jobs/search"}
    assert expiry.classify_with_reason(wall, url) == ("unknown", "")
    assert expiry.classify_with_reason(bot, url) == ("unknown", "")
    assert expiry.classify_with_reason(moved, url) == ("expired", "The posting link now leads to another page")


def test_without_firecrawl_the_page_is_read_directly_and_every_redirect_is_checked(monkeypatch):
    import io
    import urllib.error
    from email.message import Message

    checked = []

    def validate(url, **kw):
        checked.append(url)
        if "169.254" in url:
            raise ValueError("not a public address")
        return url

    def headers(**values):
        h = Message()
        for k, v in values.items():
            h[k] = v
        return h

    html_headers = headers(**{"Content-Type": "text/html; charset=utf-8"})

    class Response(io.BytesIO):
        status = 200
        headers = html_headers

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class Opener:
        def __init__(self, hops):
            self.hops = hops

        def open(self, request, timeout):
            target = self.hops[request.full_url]
            if isinstance(target, str):
                raise urllib.error.HTTPError(request.full_url, 302, "Found", headers(Location=target), None)
            return Response(target)

    client = expiry.DirectPageClient(opener=Opener({"https://jobs.example.test/a": "/b", "https://jobs.example.test/b": b"<p>ok</p>"}),
                                     validate=validate, sleep=lambda s: None)
    page = client.scrape("https://jobs.example.test/a")
    assert page == {"status": 200, "html": "<p>ok</p>", "final_url": "https://jobs.example.test/b"}
    assert checked == ["https://jobs.example.test/a", "https://jobs.example.test/b"]
    sneaky = expiry.DirectPageClient(opener=Opener({"https://jobs.example.test/c": "http://169.254.169.254/"}), validate=validate,
                                     sleep=lambda s: None)
    with pytest.raises(ValueError):
        sneaky.scrape("https://jobs.example.test/c")


def test_the_daily_tick_rechecks_in_the_background_without_firecrawl(store, monkeypatch):  # noqa: F811
    import threading

    monkeypatch.setattr(expiry, "today", lambda now=None: TODAY)
    monkeypatch.setattr(expiry, "_firecrawl_ready", lambda: False)
    ran = threading.Event()
    monkeypatch.setattr(expiry, "recheck", lambda **kw: ran.set())
    assert expiry.tick() is True
    assert ran.wait(5)


GUEST_OPEN = ('<h2 class="top-card-layout__title">SOC Analyst</h2><a class="topcard__org-name-link">Acme</a>'
              '<button class="apply-button">Apply</button><div class="show-more-less-html">We are no longer accepting '
              'paper forms, apply online.</div>')
GUEST_CLOSED = ('<h2 class="top-card-layout__title">SOC Analyst</h2><figure class="closed-job">'
                '<figcaption>No longer accepting applications</figcaption></figure><div class="show-more-less-html">x</div>')


def test_linkedin_postings_are_read_from_the_guest_page_spaced_apart(store, monkeypatch):  # noqa: F811
    monkeypatch.setattr("api.job_os.network_policy.validate_external_job_url", lambda url, **kw: url)
    shut, live = (create_job(replace(normalize_job_input({"title": f"Analyst {n}", "canonical_url": url}), description="SQL"),
                             status=JobStatus.SCRAPED)
                  for n, url in (("a", "https://www.linkedin.com/jobs/view/soc-analyst-at-acme-4312345678"),
                                 ("b", "https://www.linkedin.com/jobs/view/4300000001/?trk=x")))
    pages = {"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/4312345678": GUEST_CLOSED,
             "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/4300000001": GUEST_OPEN}
    seen = []

    class Client:
        def scrape(self, url):
            seen.append(url)
            return {"status": 200, "html": pages[url], "final_url": url}
    out = expiry.recheck(client=Client(), now=2_000_000)
    assert sorted(seen) == sorted(pages)
    assert out == {"checked": 2, "expired": 1, "unknown": 0}
    assert get_job(shut.id).status == JobStatus.EXPIRED and get_job(live.id).status == JobStatus.SCRAPED
    assert expiry.closed_reasons([shut.id])[shut.id] == "The posting says “No longer accepting applications”"


def test_a_guest_page_without_its_top_card_is_not_read_as_open_or_closed():
    url = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/1234567"
    assert expiry.classify_with_reason({"status": 200, "html": GUEST_OPEN, "final_url": url}, url) == ("open", "")
    assert expiry.classify_with_reason({"status": 200, "html": "<div>Something went wrong</div>", "final_url": url}, url) == ("unknown", "")
    assert expiry.classify_with_reason({"status": 404, "html": "", "final_url": url}, url) == ("unknown", "")


def test_linkedin_reads_wait_longer_between_requests():
    slept, clock = [], [100.0]
    client = expiry.DirectPageClient(opener=object(), validate=lambda u: u, sleep=slept.append, clock=lambda: clock[0])
    client._pause("https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/1")
    client._pause("https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/2")
    client._pause("https://jobs.example.test/a")
    client._pause("https://jobs.example.test/b")
    assert slept == [expiry.host_gap("www.linkedin.com"), expiry.SAME_HOST_GAP_S]
    assert expiry.host_gap("www.linkedin.com") >= 8


def _scraped(url, n):
    return create_job(replace(normalize_job_input({"title": f"Analyst {n}", "canonical_url": url}), description="SQL"),
                      status=JobStatus.SCRAPED)


class FakeApify:
    """Stands in for ``apify``: answers each actor run from ``answers`` and
    reports ``headroom`` dollars left this month."""

    def __init__(self, answers, headroom=8.0):
        self.answers, self.headroom, self.runs = answers, headroom, []

    def token(self):
        return "t"

    def monthly_headroom_usd(self):
        return self.headroom

    def run_actor(self, actor, actor_input, **kw):
        self.runs.append((actor, actor_input))
        answer = self.answers[actor]
        if isinstance(answer, Exception):
            raise answer
        return answer


INDEED = "https://malaysia.indeed.com/viewjob?jk={}"


def test_indeed_and_seek_postings_are_reread_through_apify_in_one_run_each(store, monkeypatch):  # noqa: F811
    monkeypatch.setattr("api.job_os.network_policy.validate_external_job_url", lambda url, **kw: url)
    shut, live = _scraped(INDEED.format("aaaa1111bbbb2222"), "a"), _scraped(INDEED.format("cccc3333dddd4444"), "b")
    seek = _scraped("https://au.seek.com/job/94878460", "c")
    fake = FakeApify({"misceres/indeed-scraper": [{"id": "aaaa1111bbbb2222", "isExpired": True},
                                                  {"id": "cccc3333dddd4444", "isExpired": False}],
                      "blackfalcondata/seek-scraper": [{"seekJobId": "94878460", "title": "Help Desk"}]})
    monkeypatch.setattr(expiry, "_apify", lambda: fake)

    class Direct:
        def scrape(self, url):
            raise AssertionError(f"read directly: {url}")
    out = expiry.recheck(client=Direct(), now=2_000_000)
    assert out == {"checked": 3, "expired": 1, "unknown": 0}
    assert [actor for actor, _ in fake.runs] == ["misceres/indeed-scraper", "blackfalcondata/seek-scraper"]
    assert sorted(u["url"] for u in fake.runs[0][1]["startUrls"]) == sorted([INDEED.format("aaaa1111bbbb2222"),
                                                                             INDEED.format("cccc3333dddd4444")])
    assert fake.runs[1][1]["startUrls"] == ["https://www.seek.com.au/job/94878460"]
    assert get_job(shut.id).status == JobStatus.EXPIRED
    assert get_job(live.id).status == JobStatus.SCRAPED and get_job(seek.id).status == JobStatus.SCRAPED
    assert expiry.closed_reasons([shut.id])[shut.id] == "Indeed marks the posting as expired"


def test_a_posting_apify_stops_returning_closes_only_after_three_days_running(store, monkeypatch):  # noqa: F811
    monkeypatch.setattr("api.job_os.network_policy.validate_external_job_url", lambda url, **kw: url)
    gone, here = _scraped(INDEED.format("aaaa1111bbbb2222"), "a"), _scraped(INDEED.format("cccc3333dddd4444"), "b")
    fake = FakeApify({"misceres/indeed-scraper": [{"id": "cccc3333dddd4444", "isExpired": False}]})
    monkeypatch.setattr(expiry, "_apify", lambda: fake)
    for day in range(2):
        assert expiry.recheck(now=2_000_000 + day * 86400)["expired"] == 0
        assert get_job(gone.id).status == JobStatus.SCRAPED
    fake.answers["misceres/indeed-scraper"] = []  # a run that returns nothing proves nothing
    assert expiry.recheck(now=2_000_000 + 2 * 86400) == {"checked": 2, "expired": 0, "unknown": 2}
    fake.answers["misceres/indeed-scraper"] = [{"id": "cccc3333dddd4444", "isExpired": False}]
    assert expiry.recheck(now=2_000_000 + 3 * 86400)["expired"] == 0  # the empty run broke the streak
    assert expiry.recheck(now=2_000_000 + 4 * 86400)["expired"] == 0
    assert expiry.recheck(now=2_000_000 + 5 * 86400)["expired"] == 1
    assert get_job(gone.id).status == JobStatus.EXPIRED and get_job(here.id).status == JobStatus.SCRAPED
    assert expiry.closed_reasons([gone.id])[gone.id] == "Indeed no longer shows the posting (checked 3 days running)"


def test_the_apify_reread_is_skipped_when_it_would_eat_the_scout_budget_or_fails(store, monkeypatch):  # noqa: F811
    monkeypatch.setattr("api.job_os.network_policy.validate_external_job_url", lambda url, **kw: url)
    job = _scraped(INDEED.format("aaaa1111bbbb2222"), "a")
    fake = FakeApify({"misceres/indeed-scraper": [{"id": "aaaa1111bbbb2222", "isExpired": True}]},
                     headroom=expiry.APIFY_RESERVE_USD + 0.001)
    monkeypatch.setattr(expiry, "_apify", lambda: fake)
    assert expiry.recheck(now=2_000_000) == {"checked": 1, "expired": 0, "unknown": 1}
    assert fake.runs == []
    fake.headroom = None  # usage unknown: don't spend
    assert expiry.recheck(now=2_000_000 + 86400)["unknown"] == 1 and fake.runs == []
    from api.job_os.apify import ApifyError

    fake.headroom, fake.answers["misceres/indeed-scraper"] = 8.0, ApifyError("Apify did not answer")
    assert expiry.recheck(now=2_000_000 + 2 * 86400)["unknown"] == 1
    assert get_job(job.id).status == JobStatus.SCRAPED


def test_without_an_apify_token_indeed_falls_back_to_a_direct_read(store, monkeypatch):  # noqa: F811
    monkeypatch.setattr("api.job_os.network_policy.validate_external_job_url", lambda url, **kw: url)
    _scraped(INDEED.format("aaaa1111bbbb2222"), "a")
    fake = FakeApify({})
    fake.token = lambda: None
    monkeypatch.setattr(expiry, "_apify", lambda: fake)
    seen = []

    class Direct:
        def scrape(self, url):
            seen.append(url)
            return {"status": 403, "html": ""}
    assert expiry.recheck(client=Direct(), now=2_000_000)["unknown"] == 1
    assert seen == [INDEED.format("aaaa1111bbbb2222")]


def test_a_bare_site_address_is_not_a_posting_that_moved():
    url = "https://google.co.uk/"
    page = {"status": 200, "html": "<p>Search</p>", "final_url": "https://www.google.com/"}
    assert expiry.classify_with_reason(page, url) == ("unknown", "")
    same = {"status": 200, "html": "<p>x</p>", "final_url": "https://www.jobs.example.test/a/"}
    assert expiry.classify_with_reason(same, "https://jobs.example.test/a") == ("unknown", "")


def test_many_postings_are_reread_in_runs_of_a_bounded_size(store, monkeypatch):  # noqa: F811
    monkeypatch.setattr("api.job_os.network_policy.validate_external_job_url", lambda url, **kw: url)
    monkeypatch.setattr(expiry, "APIFY_CHUNK", 2)
    keys = [f"aaaa1111bbbb000{n}" for n in range(5)]
    for n, key in enumerate(keys):
        _scraped(INDEED.format(key), n)
    fake = FakeApify({"misceres/indeed-scraper": [{"id": key, "isExpired": False} for key in keys]})
    monkeypatch.setattr(expiry, "_apify", lambda: fake)
    assert expiry.recheck(now=2_000_000) == {"checked": 5, "expired": 0, "unknown": 0}
    assert [len(run[1]["startUrls"]) for run in fake.runs] == [2, 2, 1]
