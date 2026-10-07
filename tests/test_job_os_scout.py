"""Scout: Indeed-only saved searches and durable discovery runs, against a fake Firecrawl.

Indeed details observed against the live site: search engines index results
pages, not postings; postings are served to automated readers only through
click links (/rc/clk?jk=...); bursts of requests are refused."""

from __future__ import annotations

import json

import pytest

from api import profiles
from api.job_os import indeed, scout
from api.job_os.firecrawl import FirecrawlError
from api.job_os.repository import get_job, list_jobs


def _posting(title, company="Acme", remote=False):
    data = {"@type": "JobPosting", "title": title, "hiringOrganization": {"name": company},
            "description": "<p>Do things</p>", "baseSalary": {"currency": "USD", "value": {"minValue": 100000, "maxValue": 120000, "unitText": "YEAR"}}}
    if remote:
        data["jobLocationType"] = "TELECOMMUTE"
    else:
        data["jobLocation"] = {"address": {"addressLocality": "Austin"}}
    return f'<html><head><script type="application/ld+json">{json.dumps(data)}</script></head></html>'


class FakeFirecrawl:
    def __init__(self, results=None, pages=None, links=None, fail_search=False, on_scrape=None):
        self.results = results or {}
        self.pages = pages or {}
        self.links = links or {}
        self.fail_search = fail_search
        self.on_scrape = on_scrape
        self.queries, self.scraped = [], []

    def search(self, query, limit=10):
        self.queries.append(query)
        if self.fail_search:
            raise FirecrawlError("Firecrawl did not answer")
        for key, urls in self.results.items():
            if key in query:
                return [{"url": u, "title": "", "description": ""} for u in urls]
        return []

    def scrape(self, url, links=False):
        self.scraped.append(url)
        if self.on_scrape:
            self.on_scrape(url)
        if url in self.links:
            return {"html": "", "links": self.links[url], "title": "", "status": 200}
        if url not in self.pages:
            raise FirecrawlError("Firecrawl returned HTTP 404")
        return {"html": self.pages[url], "links": [], "title": "", "status": 200}


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    # Test hosts are treated as public; the URL policy has its own tests.
    monkeypatch.setattr(scout, "validate_external_job_url",
                        lambda url: (_ for _ in ()).throw(scout.UnsafeJobUrl("internal")) if "internal" in url else url)
    monkeypatch.setattr(scout, "_sleep", lambda seconds: None)
    return tmp_path


HOST = "malaysia.indeed.com"


def _clk(jk, token="t1", host=HOST):
    return f"https://{host}/rc/clk?jk={jk}&bb={token}&from=serp"


def _results(keywords="backend", location="", page=0, posted=0, code="my"):
    return indeed.search_url(code, keywords, location, posted_within_days=posted, page=page)


def _search(**extra):
    return scout.create_search({"keywords": "backend", "country": "my", **extra})


def _run(search, fake):
    return scout.start_discovery(search["id"], client_factory=lambda: fake, run_async=False)


def test_search_validation():
    with pytest.raises(scout.ScoutError):
        scout.normalize_search({"keywords": "", "country": "my"})
    with pytest.raises(scout.ScoutError, match="country"):
        scout.normalize_search({"keywords": "x"})
    with pytest.raises(scout.ScoutError, match="country"):
        scout.normalize_search({"keywords": "x", "country": "atlantis"})
    with pytest.raises(scout.ScoutError, match="Date posted"):
        scout.normalize_search({"keywords": "x", "country": "my", "posted_within_days": 5})
    data = scout.normalize_search({"keywords": "python dev", "country": "SG", "locations": "Singapore, Jurong",
                                   "posted_within_days": "7"})
    assert data == {"name": "python dev", "keywords": "python dev", "country": "sg", "locations": ["Singapore", "Jurong"],
                    "sites": ["indeed"], "title_filter": [], "posted_within_days": 7, "remote_only": False, "enabled": True}


def test_a_run_reads_the_countrys_results_page_and_saves_its_postings(store):
    search = _search(locations=["Kuala Lumpur"], posted_within_days=7)
    page = _results(location="Kuala Lumpur", posted=7)
    assert page == "https://malaysia.indeed.com/jobs?q=backend&l=Kuala+Lumpur&fromage=7"
    fake = FakeFirecrawl(
        links={page: [_clk("aaa111"), _clk("aaa111", "other"), f"https://{HOST}/cmp/Acme", _clk("bbb222"),
                      _clk("ccc333", host="sg.indeed.com"), "https://internal.test/rc/clk?jk=x"]},
        pages={_clk("aaa111"): _posting("Backend Engineer"), _clk("bbb222"): "<html>gone</html>"})
    run = _run(search, fake)
    assert run["status"] == "completed", run
    c = run["counts"]
    assert (c["queries"], c["candidates"], c["saved"], c["not_postings"]) == (1, 2, 1, 1), c
    job = get_job(run["new_job_ids"][0])
    assert job.title == "Backend Engineer" and job.company == "Acme" and job.status.value == "scraped"
    assert job.canonical_url == f"https://{HOST}/viewjob?jk=aaa111"
    assert job.source == "indeed" and job.country == "Malaysia" and job.run_id == run["id"]
    assert job.salary_text == "USD 100,000–120,000 / year"
    assert scout.get_search(search["id"])["last_run_at"]
    assert fake.queries == [], "no web search while Indeed answers"


def test_second_run_counts_known_jobs_as_duplicates_despite_fresh_click_tokens(store):
    search = _search()
    fake = FakeFirecrawl(links={_results(): [_clk("aaa111")]}, pages={_clk("aaa111"): _posting("Backend Engineer"),
                                                                     _clk("aaa111", "t9"): _posting("Backend Engineer")})
    _run(search, fake)
    fake.links[_results()] = [_clk("aaa111", "t9")]
    again = _run(search, fake)
    assert again["counts"]["saved"] == 0 and again["counts"]["duplicates"] == 1
    assert len(list_jobs()) == 1


def test_more_results_pages_are_read_until_they_run_out(store):
    search = _search()
    first, second = [f"a{i}" for i in range(10)], [f"b{i}" for i in range(3)]
    fake = FakeFirecrawl(links={_results(page=0): [_clk(k) for k in first], _results(page=1): [_clk(k) for k in second]},
                         pages={_clk(k): _posting(k, company=k) for k in first + second})
    run = _run(search, fake)
    assert run["counts"]["saved"] == 13 and run["counts"]["errors"] == 0
    assert [u for u in fake.scraped if "/jobs?" in u] == [_results(page=0), _results(page=1)], "a short page is the last"


def test_remote_only_adds_remote_and_filters_onsite_postings(store):
    search = _search(remote_only=True)
    page = _results(keywords="backend remote")
    fake = FakeFirecrawl(links={page: [_clk("a1"), _clk("a2"), _clk("a3")]},
                         pages={_clk("a1"): _posting("Onsite"), _clk("a2"): _posting("Remote", remote=True),
                                _clk("a3"): _posting("Backend (Remote)", company="Initech")})
    run = _run(search, fake)
    assert run["counts"]["filtered"] == 1 and run["counts"]["saved"] == 2


def test_blocked_companies_and_repeated_roles_are_skipped(store):
    from api.job_os.settings import save_settings

    save_settings({"scout": {"blocked_companies": ["Globex Corporation"]}}, expected_revision=0)
    search = _search()
    fake = FakeFirecrawl(links={_results(): [_clk("a1"), _clk("a2"), _clk("a3")]}, pages={
        _clk("a1"): _posting("Backend Engineer", company="Acme"),
        _clk("a2"): _posting("Backend Engineer", company="ACME, Inc."),  # the same role, posted twice
        _clk("a3"): _posting("Backend Engineer", company="globex"),
    })
    run = _run(search, fake)
    c = run["counts"]
    assert (c["saved"], c["duplicates"], c["blocked"]) == (1, 1, 1)
    assert [j.company for j in list_jobs()] == ["Acme"]


def test_company_key_normalises_names():
    assert scout.company_key("Acme, Inc.") == scout.company_key("ACME") == "acme"
    assert scout.company_key("Globex Corporation") == "globex"
    assert scout.company_key("Initech Ltd") != scout.company_key("Initrode")


def test_a_refused_results_page_falls_back_to_a_web_search_of_that_indeed_site(store):
    search = _search(locations=["Penang"])
    listing = f"https://{HOST}/q-backend-l-penang-jobs.html"
    fake = FakeFirecrawl(results={f"site:{HOST} backend Penang": [listing, "https://www.linkedin.com/jobs/view/1"]},
                         links={listing: [_clk("a1")]}, pages={_clk("a1"): _posting("Backend")})
    run = _run(search, fake)
    assert run["status"] == "completed" and run["counts"]["saved"] == 1, run
    assert run["counts"]["filtered"] == 1, "LinkedIn is not searched"
    assert run["errors"][0]["where"] == f"{HOST} Penang"


def test_a_failed_posting_does_not_lose_the_others(store):
    search = _search()
    fake = FakeFirecrawl(links={_results(): [_clk("gone"), _clk("a1")]}, pages={_clk("a1"): _posting("Backend")})
    run = _run(search, fake)
    assert run["status"] == "completed" and run["counts"]["saved"] == 1 and run["counts"]["errors"] == 1
    assert run["errors"][0]["where"] == HOST


def test_an_unreachable_indeed_fails_the_run_clearly(store):
    run = _run(_search(), FakeFirecrawl(fail_search=True))
    assert run["status"] == "failed" and HOST in run["stage_detail"]


def test_a_search_without_a_country_fails_clearly(store):
    search = _search()
    from api.job_os.db import connect_job_os
    conn = connect_job_os()
    conn.execute("UPDATE searches SET country='' WHERE id=?", (search["id"],))
    conn.commit()
    conn.close()
    run = _run(search, FakeFirecrawl())
    assert run["status"] == "failed" and "country" in run["stage_detail"]


def test_cancel_mid_scrape_stops_before_the_next_page(store):
    search = _search()
    keys = [f"k{i}" for i in range(5)]
    holder = {}

    def cancel_after_first(url):
        if url == _clk(keys[0]):
            scout.cancel_run(holder["run_id"])

    fake = FakeFirecrawl(links={_results(): [_clk(k) for k in keys]}, pages={_clk(k): _posting(f"Job {k}", company=k) for k in keys},
                         on_scrape=cancel_after_first)
    original = scout._update_run

    def capture(run_id, **fields):
        holder["run_id"] = run_id
        return original(run_id, **fields)

    scout._update_run = capture
    try:
        run = _run(search, fake)
    finally:
        scout._update_run = original
    assert run["status"] == "cancelled"
    assert fake.scraped == [_results(), _clk(keys[0])] and run["counts"]["saved"] == 1


def test_one_active_run_per_search_and_idempotent_start(store):
    search = _search()
    first = scout.start_discovery(search["id"], idempotency_key="k1", client_factory=lambda: FakeFirecrawl(), run_async=False)
    again = scout.start_discovery(search["id"], idempotency_key="k1", client_factory=lambda: FakeFirecrawl(), run_async=False)
    assert again["id"] == first["id"]


def test_restart_marks_orphaned_runs_interrupted(store):
    search = _search()
    from api.job_os.db import connect_job_os
    conn = connect_job_os()
    conn.execute("INSERT INTO discovery_runs (id, search_id, status, owner_pid, created_at) VALUES ('r1', ?, 'scraping', 999999, 1)", (search["id"],))
    conn.commit()
    conn.close()
    run = scout.get_run("r1")
    assert run["status"] == "interrupted" and run["finished_at"]


def test_update_is_revisioned_and_delete_keeps_found_jobs(store):
    search = _search()
    fake = FakeFirecrawl(links={_results(): [_clk("a1")]}, pages={_clk("a1"): _posting("Backend")})
    _run(search, fake)
    updated = scout.update_search(search["id"], {"enabled": False, "locations": ["Ipoh"]}, expected_revision=0)
    assert updated["enabled"] is False and updated["revision"] == 1 and updated["locations"] == ["Ipoh"]
    assert updated["country"] == "my" and updated["country_name"] == "Malaysia"
    with pytest.raises(scout.ScoutConflict):
        scout.update_search(search["id"], {"enabled": True}, expected_revision=0)
    assert scout.delete_search(search["id"]) and len(list_jobs()) == 1


def test_the_quota_is_shared_across_locations(store):
    from api.job_os.settings import save_settings
    save_settings({"scout": {"max_results_per_search": 4}}, expected_revision=0)
    search = _search(locations=["Kuala Lumpur", "Penang"])
    kl = [f"kl{i}" for i in range(6)]
    pg = [f"pg{i}" for i in range(6)]
    fake = FakeFirecrawl(links={_results(location="Kuala Lumpur"): [_clk(k) for k in kl],
                                _results(location="Penang"): [_clk(k) for k in pg]},
                         pages={_clk(k): _posting(k, company=k) for k in kl + pg})
    run = _run(search, fake)
    saved = sorted(get_job(i).title[:2] for i in run["new_job_ids"])
    assert run["counts"]["saved"] == 4 and saved == ["kl", "kl", "pg", "pg"]


def test_indeed_requests_are_spaced_out(store, monkeypatch):
    waits = []
    monkeypatch.setattr(scout, "_sleep", waits.append)
    clock = iter(range(0, 10_000, 1))
    monkeypatch.setattr(scout, "_monotonic", lambda: next(clock))
    fake = FakeFirecrawl(links={_results(): [_clk("a1"), _clk("b2")]},
                         pages={_clk("a1"): _posting("A"), _clk("b2"): _posting("B", company="Globex")})
    _run(_search(), fake)
    assert len(waits) == 2 and all(w > 0 for w in waits), waits  # before the 2nd and 3rd Indeed page


def test_a_run_stops_early_once_indeed_keeps_refusing(store):
    # Indeed blocks a reader for minutes after a burst; every further request
    # in that window fails, so the run stops instead of waiting on each one.
    keys = [f"k{i}" for i in range(12)]
    fake = FakeFirecrawl(links={_results(): [_clk(k) for k in keys]}, pages={_clk("k0"): _posting("First")})
    run = _run(_search(), fake)
    assert run["status"] == "completed" and run["counts"]["saved"] == 1
    assert "refusing" in run["stage_detail"] and "1 new job" in run["stage_detail"]
    assert len([u for u in fake.scraped if "/rc/clk" in u]) == 1 + scout.REFUSALS_BEFORE_STOP

    empty = _run(scout.create_search({"keywords": "ops", "country": "my"}),
                 FakeFirecrawl(links={_results(keywords="ops"): [_clk(k) for k in keys]}))
    assert empty["status"] == "failed" and "refusing" in empty["stage_detail"]
    assert scout.get_search(empty["search_id"])["last_run_at"], "the schedule waits before trying again"
