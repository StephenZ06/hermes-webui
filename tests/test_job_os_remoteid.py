"""remote.id (remotefreelance.id) in Scout: pages read straight from the site,
saved under each job's source-site link and labelled remote.id, Upwork gigs
kept, LinkedIn jobs already found through a LinkedIn search skipped.

The fixtures are real pages saved from the site on 2026-10-09 (the app bundle
scripts removed)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api import profiles
from api.job_os import apify, remoteid, scout
from api.job_os.repository import create_job, list_jobs, normalize_job_input

FIX = Path(__file__).parent / "fixtures" / "remoteid"
BASE = "https://remotefreelance.id"
JOBSTREET = BASE + "/jobs/jobstreet/94318388/seo-specialist"
LINKEDIN = BASE + "/jobs/linkedin/4474484467/remote-customer-service-agent-11-30-hire"
UPWORK = BASE + "/jobs/upwork/2107984703966389368/4k-vsl-long-form-video-editor-needed-immediately"
PAGES = {JOBSTREET: "job-jobstreet.html", LINKEDIN: "job-linkedin.html", UPWORK: "job-upwork.html"}


def _page(name):
    return (FIX / name).read_text(encoding="utf-8")


def _listing(urls, next_page=False):
    items = [{"@type": "ListItem", "position": i + 1, "url": u} for i, u in enumerate(urls)]
    schema = [{"@type": "CollectionPage", "mainEntity": {"@type": "ItemList", "itemListElement": items}}]
    nav = '<nav class="public-jobs-pagination" aria-label="Pagination"><a href="/jobs?page=2">Selanjutnya</a></nav>' if next_page else ""
    return f'<html><head><script type="application/ld+json">{json.dumps(schema)}</script></head><body>{nav}</body></html>'


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    monkeypatch.setattr(remoteid, "_sleep", lambda seconds: None)
    return tmp_path


def test_job_pages_are_read_into_postings_with_their_source_links():
    jobstreet = remoteid.parse_job(_page("job-jobstreet.html"), JOBSTREET)
    assert jobstreet["title"] == "SEO Specialist" and jobstreet["company"] == "Ryvo"
    assert jobstreet["location"] == "Indonesia · Jakarta" and jobstreet["country"] == "Indonesia"
    assert jobstreet["salary_text"] == "Rp 60,000 per hour" and jobstreet["employment_type"] == "Full time"
    assert jobstreet["posted_at"] == "2026-09-30" and jobstreet["workplace"] == "Remote"
    assert jobstreet["canonical_url"] == "https://id.jobstreet.com/job/94318388"
    assert jobstreet["description"].startswith("About the Role\nWe are looking for")
    linkedin = remoteid.parse_job(_page("job-linkedin.html"), LINKEDIN)
    # Tracking parameters dropped: the same link a LinkedIn search stores.
    assert linkedin["canonical_url"] == "https://www.linkedin.com/jobs/view/4474484467"
    assert linkedin["salary_text"] == "" and linkedin["posted_at"] == "2026-10-07"  # "7 Okt 2026"
    upwork = remoteid.parse_job(_page("job-upwork.html"), UPWORK)
    assert upwork["origin"] == "upwork" and upwork["company"] == "Upwork client"
    assert upwork["canonical_url"] == "https://www.upwork.com/jobs/~022107984703966389368"
    assert remoteid.parse_job("<html>not a job</html>", JOBSTREET) is None


def test_a_results_page_lists_its_jobs_and_says_whether_more_follow():
    links, more = remoteid.listing_links(_page("list-p2.html"))
    assert len(links) == 12 and all(u.startswith(BASE + "/jobs/") for u in links) and more
    links, more = remoteid.listing_links(_listing([JOBSTREET]))
    assert links == [JOBSTREET] and not more


def test_only_remotefreelance_job_pages_are_fetched():
    for url in ("https://example.com/jobs", "http://remotefreelance.id/jobs", "https://remotefreelance.id/api/jobs"):
        with pytest.raises(remoteid.RemoteIdError):
            remoteid.fetch(url)


def test_the_site_is_offered_everywhere_and_needs_no_apify(store):
    keys = {s["key"]: s for s in apify.sites_payload()}
    assert keys["remoteid"]["name"] == "remote.id" and keys["remoteid"]["needs_apify"] is False
    search = scout.create_search({"keywords": "SEO Specialist", "country": "my", "sites": ["remoteid"], "strict_titles": False})
    assert search["sites"] == ["remoteid"]


def test_a_run_saves_remote_id_finds_keeps_upwork_and_skips_known_linkedin_jobs(store, monkeypatch):
    # A LinkedIn search already found the LinkedIn job.
    create_job(normalize_job_input({"title": "Remote Customer Service Agent", "company": "TalentHop", "source": "linkedin",
                                    "canonical_url": "https://www.linkedin.com/jobs/view/4474484467"}))
    fetched = []

    def fake_fetch(url):
        fetched.append(url)
        if url.startswith(BASE + "/jobs?"):
            return _listing([JOBSTREET, LINKEDIN, UPWORK])
        return _page(PAGES[url])

    monkeypatch.setattr(scout, "_remoteid_fetch", fake_fetch)
    search = scout.create_search({"keywords": "SEO Specialist", "country": "my", "sites": ["remoteid"],
                                  "strict_titles": False, "posted_within_days": 0})

    def no_firecrawl():
        raise AssertionError("remote.id runs without Firecrawl")

    run = scout.start_discovery(search["id"], client_factory=no_firecrawl, run_async=False)
    assert run["status"] == "completed", run
    assert run["counts"]["saved"] == 2 and run["counts"]["duplicates"] == 1
    saved = {j.canonical_url: j for j in list_jobs() if j.source == "remoteid"}
    assert set(saved) == {"https://id.jobstreet.com/job/94318388", "https://www.upwork.com/jobs/~022107984703966389368"}
    seo = saved["https://id.jobstreet.com/job/94318388"]
    assert seo.company == "Ryvo" and seo.workplace == "remote" and seo.country == "Indonesia" and seo.description
    assert all(u.startswith(BASE + "/jobs") for u in fetched)
    # A second run finds nothing new.
    again = scout.start_discovery(search["id"], client_factory=no_firecrawl, run_async=False)
    assert again["status"] == "completed" and again["counts"]["saved"] == 0


def test_with_indeed_too_remote_id_runs_before_the_indeed_search(store, monkeypatch):
    monkeypatch.setattr(scout, "_remoteid_fetch", lambda url: _listing([]) if "?" in url else "")
    search = scout.create_search({"keywords": "SEO Specialist", "country": "my", "sites": ["indeed", "remoteid"],
                                  "strict_titles": False})
    calls = []

    class Client:
        def scrape(self, url, links=False):
            calls.append(url)
            return {"html": "", "links": [], "title": "", "status": 200}

        def search(self, query, limit=10):
            return []

    run = scout.start_discovery(search["id"], client_factory=Client, run_async=False)
    assert run["counts"]["queries"] >= 2 and calls, "both sites were searched"
