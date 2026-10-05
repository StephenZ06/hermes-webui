"""Scout: saved searches and durable discovery runs, against a fake Firecrawl."""

from __future__ import annotations

import json

import pytest

from api import profiles
from api.job_os import scout
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
    return tmp_path


def _run(search, fake):
    return scout.start_discovery(search["id"], client_factory=lambda: fake, run_async=False)


def test_search_validation():
    with pytest.raises(scout.ScoutError):
        scout.normalize_search({"keywords": ""})
    with pytest.raises(scout.ScoutError):
        scout.normalize_search({"keywords": "x", "sites": ["not a site!"]})
    data = scout.normalize_search({"keywords": "python dev", "locations": "Berlin, Remote", "sites": "WWW.Acme.com\nhttps://acme.com/careers/"})
    assert data["name"] == "python dev" and data["locations"] == ["Berlin", "Remote"]
    assert data["sites"] == ["acme.com", "https://acme.com/careers"]


def test_a_run_searches_reads_postings_and_saves_only_real_ones(store):
    search = scout.create_search({"keywords": "backend", "sites": ["jobs.lever.co"]})
    fake = FakeFirecrawl(
        results={"site:jobs.lever.co backend": ["https://jobs.lever.co/a/1", "https://jobs.lever.co/a/2",
                                                  "https://internal.test/x", "https://jobs.lever.co/a/1"]},
        pages={"https://jobs.lever.co/a/1": _posting("Backend Engineer"), "https://jobs.lever.co/a/2": "<html>listing page</html>"})
    run = _run(search, fake)
    assert run["status"] == "completed", run
    c = run["counts"]
    assert (c["queries"], c["found"], c["candidates"], c["saved"], c["not_postings"], c["unsafe"]) == (1, 4, 2, 1, 1, 1)
    job = get_job(run["new_job_ids"][0])
    assert job.title == "Backend Engineer" and job.company == "Acme" and job.status.value == "scraped"
    assert job.salary_text == "USD 100,000–120,000 / year" and job.source == "lever" and job.run_id == run["id"]
    assert scout.get_search(search["id"])["last_run_at"]


def test_second_run_counts_known_jobs_as_duplicates(store):
    search = scout.create_search({"keywords": "backend", "sites": ["jobs.lever.co"]})
    fake = FakeFirecrawl(results={"backend": ["https://jobs.lever.co/a/1"]}, pages={"https://jobs.lever.co/a/1": _posting("Backend Engineer")})
    _run(search, fake)
    again = _run(search, fake)
    assert again["counts"]["saved"] == 0 and again["counts"]["duplicates"] == 1
    assert len(list_jobs()) == 1


def test_remote_only_filters_onsite_postings(store):
    search = scout.create_search({"keywords": "backend", "remote_only": True, "sites": ["jobs.lever.co"]})
    fake = FakeFirecrawl(results={"backend": ["https://jobs.lever.co/a/1", "https://jobs.lever.co/a/2"]},
                         pages={"https://jobs.lever.co/a/1": _posting("Onsite"), "https://jobs.lever.co/a/2": _posting("Remote", remote=True)})
    run = _run(search, fake)
    assert run["counts"]["filtered"] == 1 and run["counts"]["saved"] == 1
    assert "remote" in fake.queries[0]


def test_careers_page_links_are_followed(store):
    search = scout.create_search({"keywords": "backend", "sites": ["https://acme.com/careers"]})
    fake = FakeFirecrawl(links={"https://acme.com/careers": ["https://acme.com/careers/jobs/42-backend", "https://acme.com/about"]},
                         pages={"https://acme.com/careers/jobs/42-backend": _posting("Backend")})
    run = _run(search, fake)
    assert run["counts"]["saved"] == 1
    assert fake.queries and all(q.startswith("site:") for q in fake.queries), "default ATS sites are still searched"


def test_a_failed_page_does_not_lose_the_others(store):
    search = scout.create_search({"keywords": "backend", "sites": ["jobs.lever.co"]})
    fake = FakeFirecrawl(results={"backend": ["https://jobs.lever.co/a/404", "https://jobs.lever.co/a/1"]},
                         pages={"https://jobs.lever.co/a/1": _posting("Backend")})
    run = _run(search, fake)
    assert run["status"] == "completed" and run["counts"]["saved"] == 1 and run["counts"]["errors"] == 1
    assert run["errors"][0]["where"] == "jobs.lever.co"


def test_search_outage_fails_the_run_clearly(store):
    search = scout.create_search({"keywords": "backend", "sites": ["jobs.lever.co"]})
    run = _run(search, FakeFirecrawl(fail_search=True))
    assert run["status"] == "failed" and "Firecrawl" in run["stage_detail"]


def test_cancel_mid_scrape_stops_before_the_next_page(store):
    search = scout.create_search({"keywords": "backend", "sites": ["jobs.lever.co"]})
    urls = [f"https://jobs.lever.co/a/{i}" for i in range(5)]
    holder = {}

    def cancel_after_first(url):
        if url == urls[0]:
            scout.cancel_run(holder["run_id"])

    fake = FakeFirecrawl(results={"backend": urls}, pages={u: _posting(f"Job {u[-1]}") for u in urls}, on_scrape=cancel_after_first)
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
    assert len(fake.scraped) == 1 and run["counts"]["saved"] == 1


def test_one_active_run_per_search_and_idempotent_start(store):
    search = scout.create_search({"keywords": "backend"})
    first = scout.start_discovery(search["id"], idempotency_key="k1", client_factory=lambda: FakeFirecrawl(), run_async=False)
    again = scout.start_discovery(search["id"], idempotency_key="k1", client_factory=lambda: FakeFirecrawl(), run_async=False)
    assert again["id"] == first["id"]


def test_restart_marks_orphaned_runs_interrupted(store):
    search = scout.create_search({"keywords": "backend"})
    from api.job_os.db import connect_job_os
    conn = connect_job_os()
    conn.execute("INSERT INTO discovery_runs (id, search_id, status, owner_pid, created_at) VALUES ('r1', ?, 'scraping', 999999, 1)", (search["id"],))
    conn.commit()
    conn.close()
    run = scout.get_run("r1")
    assert run["status"] == "interrupted" and run["finished_at"]


def test_update_is_revisioned_and_delete_keeps_found_jobs(store):
    search = scout.create_search({"keywords": "backend", "sites": ["jobs.lever.co"]})
    fake = FakeFirecrawl(results={"backend": ["https://jobs.lever.co/a/1"]}, pages={"https://jobs.lever.co/a/1": _posting("Backend")})
    _run(search, fake)
    updated = scout.update_search(search["id"], {"enabled": False}, expected_revision=0)
    assert updated["enabled"] is False and updated["revision"] == 1
    with pytest.raises(scout.ScoutConflict):
        scout.update_search(search["id"], {"enabled": True}, expected_revision=0)
    assert scout.delete_search(search["id"]) and len(list_jobs()) == 1
