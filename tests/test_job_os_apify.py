"""Apify: the token flow, the actor call, the Indeed record mapping, and Scout
runs that go through Apify instead of reading Indeed itself."""

from __future__ import annotations

import io
import json
import os
import urllib.request
from urllib.parse import urlparse

import pytest

from api import profiles, routes, shared_env
from api.job_os import apify, scout
from api.job_os.repository import get_job, list_jobs
from api.job_os.settings import save_settings

TOKEN = "apify_api_" + "A1b2C3d4E5" * 3


def _item(key, title="Data Analyst", company="Acme", **extra):
    item = {
        "key": key, "url": f"https://www.indeed.com/viewjob?jk={key}", "title": title, "expired": False,
        "datePublished": "2026-10-06T05:00:00.000Z",
        "location": {"countryName": "Malaysia", "countryCode": "MY", "admin1Code": "14", "city": "Kuala Lumpur"},
        "employer": {"name": company},
        "attributes": {"CF3CP": "Full-time", "PAXZC": "Hybrid work", "FGY89": "SQL"},
        "jobTypes": {"CF3CP": "Full-time"},
        "baseSalary": {"min": 5000, "max": 7000, "unitOfWork": "MONTH", "currencyCode": "MYR"},
        "description": {"text": "SQL and dashboards.", "html": "<p>SQL and dashboards.</p>"},
    }
    item.update(extra)
    return item


class _H:
    def __init__(self, body=None):
        raw = json.dumps(body if body is not None else {}).encode()
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile, self.wfile, self.status = io.BytesIO(raw), io.BytesIO(), None

    def send_response(self, s):
        self.status = s

    def send_header(self, *_):
        pass

    def end_headers(self):
        pass

    def json(self):
        return json.loads(self.wfile.getvalue())


@pytest.fixture
def home(tmp_path, monkeypatch):
    work = tmp_path / "profiles" / "work"
    work.mkdir(parents=True)
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "secrets.env").write_text("")
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: work)
    monkeypatch.setattr(routes, "_check_csrf", lambda _h: True)
    monkeypatch.setattr(routes, "_guard_request_session_visibility", lambda *a, **k: True)
    monkeypatch.setattr(scout, "validate_external_job_url", lambda url: url)
    monkeypatch.delenv(apify.TOKEN_KEY, raising=False)
    yield tmp_path
    os.environ.pop(apify.TOKEN_KEY, None)  # the env writer mirrors values into os.environ


def _post(path, body=None):
    h = _H(body)
    assert routes.handle_post(h, urlparse(path)) is True
    return h


# ---- token -----------------------------------------------------------------------

def test_connect_checks_the_token_then_saves_it_and_reports_presence_only(home, monkeypatch):
    monkeypatch.setattr(apify, "verify_token", lambda value: {"username": "jane", "plan": "FREE"})
    bad = _post("/api/job-os/apify", {"token": "has spaces in it"})
    assert bad.status == 400 and not apify.token()
    ok = _post("/api/job-os/apify", {"token": f"  {TOKEN} "})
    assert ok.status == 200, ok.json()
    body = ok.wfile.getvalue().decode()
    assert TOKEN not in body, "the token never goes back to the browser"
    assert ok.json()["apify"] == {"token": True, "token_hint": f"…{TOKEN[-4:]}",
                                  "scope": "shared", "username": "jane", "plan": "FREE"}
    assert shared_env.parse_env_file(home / "shared" / "secrets.env")[apify.TOKEN_KEY] == TOKEN
    status = routes.handle_get(h := _H(), urlparse("/api/job-os/settings")) and h.json()["status"]["apify"]
    assert status["token"] is True and TOKEN not in json.dumps(h.json())
    assert _post("/api/job-os/apify/disconnect").json()["apify"]["token"] is False
    assert apify.TOKEN_KEY not in shared_env.parse_env_file(home / "shared" / "secrets.env")


def test_a_refused_token_is_not_saved(home, monkeypatch):
    def refuse(_value):
        raise apify.ApifyError("Apify refused the API token. Check it in Settings → Apify.")

    monkeypatch.setattr(apify, "verify_token", refuse)
    h = _post("/api/job-os/apify", {"token": TOKEN})
    assert h.status == 400 and "refused" in h.json()["error"]
    assert not apify.token()
    assert _post("/api/job-os/apify/test").status == 400  # nothing to test


def test_run_actor_sends_the_token_in_a_header_and_returns_the_items(home, monkeypatch):
    seen = {}

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(request, timeout):
        seen["url"], seen["auth"], seen["body"], seen["timeout"] = request.full_url, request.get_header("Authorization"), json.loads(request.data), timeout
        return _Resp(json.dumps([_item("abc123"), "junk"]).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    items = apify.run_actor("valig/indeed-jobs-scraper", {"country": "my"}, value=TOKEN)
    assert [i["key"] for i in items] == ["abc123"]
    assert seen["url"].startswith("https://api.apify.com/v2/acts/valig~indeed-jobs-scraper/run-sync-get-dataset-items?")
    assert TOKEN not in seen["url"] and seen["auth"] == f"Bearer {TOKEN}"
    assert seen["body"] == {"country": "my"} and seen["timeout"] > apify.RUN_TIMEOUT_S
    with pytest.raises(apify.ApifyError, match="owner/name"):
        apify.run_actor("not an actor", {}, value=TOKEN)


# ---- mapping -----------------------------------------------------------------------

def test_an_indeed_record_maps_to_a_scout_posting():
    posting = apify.indeed_posting(_item("abc123"), "malaysia.indeed.com")
    assert posting == {
        "title": "Data Analyst", "company": "Acme", "location": "Kuala Lumpur", "country": "Malaysia",
        "salary_text": "MYR 5,000–7,000 / month", "employment_type": "Full-time", "workplace": "hybrid",
        "posted_at": "2026-10-06", "description": "SQL and dashboards.",
        "canonical_url": "https://malaysia.indeed.com/viewjob?jk=abc123",
    }
    assert apify.indeed_posting(_item("abc123", expired=True), "x") is None
    assert apify.indeed_posting(_item("../evil"), "x") is None
    assert apify.indeed_posting(_item("k1", baseSalary={"min": 30, "max": 30, "unitOfWork": "HOUR", "currencyCode": "SGD"}), "x")["salary_text"] == "SGD 30 / hour"
    assert apify.indeed_posting(_item("k2", baseSalary=None, attributes={"A": "Remote"}), "x")["workplace"] == "remote"
    assert apify.indeed_input("my", "data analyst", "Penang", limit=50, posted_within_days=0) == {
        "country": "my", "title": "data analyst", "location": "Penang", "limit": 50, "datePosted": ""}
    assert apify.indeed_input("sg", "x", "", limit=5, posted_within_days=7)["datePosted"] == "7"


# ---- Scout through Apify -------------------------------------------------------------

def _apify_on(monkeypatch, runs, **settings):
    save_settings({"apify": {"enabled": True, **settings}}, expected_revision=0)
    monkeypatch.setenv(apify.TOKEN_KEY, TOKEN)

    def fake_run(actor, actor_input):
        runs.append((actor, actor_input))
        result = runs_result.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    runs_result = []
    monkeypatch.setattr(scout, "_apify_run", fake_run)
    return runs_result


class _NoFirecrawl:
    def search(self, *a, **k):
        raise AssertionError("Apify runs never search through Firecrawl")

    def scrape(self, *a, **k):
        raise AssertionError("Apify runs never read pages through Firecrawl")


def _run(search):
    return scout.start_discovery(search["id"], client_factory=_NoFirecrawl, run_async=False)


def test_a_run_through_apify_saves_each_citys_postings(home, monkeypatch):
    runs = []
    results = _apify_on(monkeypatch, runs, results_per_city=30)
    results += [[_item("kl1"), _item("kl2", title="BI Analyst", company="Globex"), _item("old", expired=True)],
                [_item("kl1"), _item("pg1", title="Data Engineer", company="Initech")]]
    search = scout.create_search({"keywords": "data analyst", "country": "my", "locations": ["Kuala Lumpur", "Penang"],
                                  "posted_within_days": 1})
    run = _run(search)
    assert run["status"] == "completed", run
    assert [(a, i["location"], i["limit"], i["datePosted"], i["country"]) for a, i in runs] == [
        ("valig/indeed-jobs-scraper", "Kuala Lumpur", 30, "1", "my"), ("valig/indeed-jobs-scraper", "Penang", 30, "1", "my")]
    c = run["counts"]
    assert (c["queries"], c["found"], c["saved"], c["closed"]) == (2, 5, 3, 1), c
    jobs = {j.title: j for j in list_jobs()}
    assert jobs["Data Analyst"].canonical_url == "https://malaysia.indeed.com/viewjob?jk=kl1"
    assert jobs["Data Analyst"].source == "indeed" and jobs["Data Analyst"].country == "Malaysia"
    assert jobs["Data Analyst"].description == "SQL and dashboards." and jobs["Data Analyst"].status.value == "scraped"
    assert get_job(run["new_job_ids"][0]).search_id == search["id"]

    results += [[_item("kl1"), _item("kl3", title="Analyst II", company="Umbrella")], []]
    again = _run(search)
    assert again["counts"]["saved"] == 1 and again["counts"]["duplicates"] == 1


def test_one_failed_city_keeps_the_others_and_all_failing_fails_the_run(home, monkeypatch):
    runs = []
    results = _apify_on(monkeypatch, runs)
    results += [apify.ApifyError("Apify did not answer"), [_item("ok1")]]
    search = scout.create_search({"keywords": "x", "country": "my", "locations": ["A", "B"]})
    run = _run(search)
    assert run["status"] == "completed" and run["counts"]["saved"] == 1 and run["errors"][0]["where"] == "Apify Indeed “x” in A"
    results += [apify.ApifyError("Your Apify account is out of credit for this month.")]
    failed = _run(scout.create_search({"keywords": "y", "country": "my"}))
    assert failed["status"] == "failed" and "out of credit" in failed["stage_detail"]


def test_apify_on_without_a_token_fails_clearly(home, monkeypatch):
    save_settings({"apify": {"enabled": True}}, expected_revision=0)
    run = _run(scout.create_search({"keywords": "x", "country": "my"}))
    assert run["status"] == "failed" and "not connected" in run["stage_detail"]


def test_apify_settings_are_validated(home):
    from api.job_os.settings import SettingsError

    for bad in ({"indeed_actor": "valig/linkedin-jobs-scraper"}, {"results_per_city": 0}, {"results_per_city": 5000}, {"enabled": "yes"}):
        with pytest.raises(SettingsError):
            save_settings({"apify": bad}, expected_revision=0)
    with pytest.raises(SettingsError, match="must be one of"):
        save_settings({"apify": {"linkedin_actor": "someone/unknown"}}, expected_revision=0)
    saved = save_settings({"apify": {"linkedin_actor": "valig/linkedin-jobs-scraper", "results_per_city": 120}}, expected_revision=0)["apify"]
    assert saved == {"enabled": False, "indeed_actor": "valig/indeed-jobs-scraper",
                     "linkedin_actor": "valig/linkedin-jobs-scraper", "results_per_city": 120}


def test_indeed_region_codes_are_dropped_from_the_location():
    item = _item("k9", location={"countryName": "Malaysia", "admin1Code": "M14", "city": "Kuala Lumpur"})
    assert apify.indeed_posting(item, "x")["location"] == "Kuala Lumpur"
    us = _item("k8", location={"countryName": "United States", "admin1Code": "NY", "city": "New York"})
    assert apify.indeed_posting(us, "x")["location"] == "New York, NY", "a readable state stays"


def test_a_run_says_when_new_finds_were_not_scored_for_want_of_a_resume(home, monkeypatch):
    runs = []
    results = _apify_on(monkeypatch, runs)
    results += [[_item("n1")]]
    run = _run(scout.create_search({"keywords": "x", "country": "my"}))
    assert run["status"] == "completed"
    assert run["stage_detail"] == "1 new job · not scored: upload your master resume in Resume Studio"


# ---- LinkedIn, the scraper registry, title filter ----------------------------------

def _linkedin(job_id, title="Data Analyst", company="Acme", posted="2026-10-07", **extra):
    """A curious_coder/linkedin-jobs-scraper record."""
    return {"id": job_id, "link": f"https://www.linkedin.com/jobs/view/data-analyst-at-acme-{job_id}?trk=x", "title": title,
            "location": "Kuala Lumpur, Federal Territory of Kuala Lumpur, Malaysia", "companyName": company,
            "salaryInfo": ["RM5,000", "RM7,000"], "postedAt": posted, "descriptionText": "SQL.", **extra}


def test_curious_coder_linkedin_records_map_to_postings():
    li = apify.linkedin_curious_posting(_linkedin("4219847745"))
    assert li["canonical_url"] == "https://www.linkedin.com/jobs/view/4219847745"
    assert (li["company"], li["salary_text"], li["posted_at"], li["description"]) == ("Acme", "RM5,000 – RM7,000", "2026-10-07", "SQL.")
    assert apify.linkedin_curious_posting(_linkedin("../x")) is None
    assert apify.linkedin_curious_input("Qatar", "SOC Analyst", "Doha", limit=40, posted_within_days=1) == {
        "keywords": "SOC Analyst", "location": "Doha, Qatar", "datePosted": "past24Hours", "limitPerSource": 40,
        "scrapeCompany": False, "splitByLocation": False}
    assert apify.linkedin_curious_input("Malaysia", "x", "", limit=5, posted_within_days=3)["datePosted"] == "pastWeek"


def test_the_registry_offers_each_sites_scrapers_and_refuses_unknown_ones():
    assert apify.SITE_NAMES == {"indeed": "Indeed", "linkedin": "LinkedIn"}
    assert apify.default_actor("linkedin") == "curious_coder/linkedin-jobs-scraper"
    payload = {s["key"]: s for s in apify.sites_payload()}
    assert [a["actor"] for a in payload["linkedin"]["actors"]] == ["curious_coder/linkedin-jobs-scraper", "valig/linkedin-jobs-scraper"]
    assert payload["linkedin"]["needs_apify"] and not payload["indeed"]["needs_apify"]
    with pytest.raises(apify.ApifyError, match="pick a scraper"):
        apify.adapter("linkedin", "valig/indeed-jobs-scraper")


def test_a_search_on_both_sites_runs_each_and_saves_a_role_once(home, monkeypatch):
    runs = []
    results = _apify_on(monkeypatch, runs)
    today = __import__("time").strftime("%Y-%m-%d")
    results += [[_item("in1", datePublished=today + "T00:00:00Z")],
                [_linkedin("1111111", title="BI Analyst", company="Globex", posted=today),
                 _linkedin("2222222", title="Data Analyst", company="Acme", posted=today),  # the same role as Indeed's
                 _linkedin("3333333", title="Old Role", company="Initech", posted="2020-01-01")]]
    search = scout.create_search({"keywords": "data", "country": "my", "sites": ["linkedin", "indeed"], "posted_within_days": 7})
    assert search["sites"] == ["indeed", "linkedin"]
    run = _run(search)
    assert run["status"] == "completed", run
    assert [a for a, _ in runs] == ["valig/indeed-jobs-scraper", "curious_coder/linkedin-jobs-scraper"]
    assert runs[1][1]["location"] == "Malaysia" and "skipJobId" not in runs[1][1] and "titleInclude" not in runs[1][1]
    c = run["counts"]
    assert (c["saved"], c["duplicates"], c["filtered"]) == (2, 1, 1), c
    by_source = {j.source: j for j in list_jobs()}
    assert set(by_source) == {"indeed", "linkedin"} and by_source["linkedin"].country == "Malaysia"


def test_sites_are_validated_and_need_apify(home, monkeypatch):
    with pytest.raises(scout.ScoutError, match="Unknown job site"):
        scout.create_search({"keywords": "x", "country": "my", "sites": ["jobstreet"]})
    run = _run(scout.create_search({"keywords": "x", "country": "my", "sites": ["linkedin"]}))
    assert run["status"] == "failed" and "LinkedIn need" in run["stage_detail"]


def test_scrapers_that_can_skip_known_jobs_and_off_title_ones_are_told_to(home, monkeypatch):
    runs = []
    results = _apify_on(monkeypatch, runs, linkedin_actor="valig/linkedin-jobs-scraper")
    today = __import__("time").strftime("%Y-%m-%d")
    valig = lambda job_id, title, company: {"id": job_id, "title": title, "companyName": company, "location": "Kuala Lumpur",
                                            "postedDate": today, "description": "x"}
    results += [[valig("1111111", "SOC Analyst", "A")]]
    search = scout.create_search({"keywords": "SOC Analyst", "country": "my", "sites": ["linkedin"], "title_filter": "soc"})
    assert _run(search)["counts"]["saved"] == 1
    assert runs[0][1]["titleInclude"] == ["soc"] and "skipJobId" not in runs[0][1]
    results += [[]]
    _run(search)
    assert runs[1][1]["skipJobId"] == ["1111111"], "jobs Scout already has are left out on the actor's side"


def test_title_filter_keeps_only_matching_titles(home, monkeypatch):
    runs = []
    results = _apify_on(monkeypatch, runs)
    today = __import__("time").strftime("%Y-%m-%d")
    results += [
        [_item("a1", title="SOC Analyst L1", company="A", datePublished=today), _item("a2", title="Network Engineer", company="B", datePublished=today)],
        [_item("a3", title="Senior Security Analyst", company="C", datePublished=today), _item("a4", title="Analyst Relations Lead", company="D", datePublished=today)],
        [_linkedin("5555555", title="Cyber Security Analyst", company="E", posted=today)],
        [_linkedin("6666666", title="Security Operations Analyst", company="F", posted=today)],
    ]
    search = scout.create_search({"keywords": "SOC Analyst, Security Analyst", "country": "my", "sites": ["indeed", "linkedin"],
                                  "title_filter": "soc, Security Analyst"})
    assert search["title_filter"] == ["soc", "security analyst"] and search["queries"] == ["SOC Analyst", "Security Analyst"]
    run = _run(search)
    assert [(a.split("/")[1], i.get("title") or i.get("keywords")) for a, i in runs] == [
        ("indeed-jobs-scraper", "SOC Analyst"), ("indeed-jobs-scraper", "Security Analyst"),
        ("linkedin-jobs-scraper", "SOC Analyst"), ("linkedin-jobs-scraper", "Security Analyst")]
    saved = sorted(j.title for j in list_jobs())
    assert saved == ["Cyber Security Analyst", "SOC Analyst L1", "Security Operations Analyst", "Senior Security Analyst"]
    assert run["counts"]["filtered"] == 2  # Network Engineer, Analyst Relations Lead
    assert scout.title_matches("Senior SOC Analyst (L2)", ["soc"]) and not scout.title_matches("Associate", ["soc"])
    assert scout.title_matches("Analyst, Security Operations", ["security analyst"]), "all words, any order"
    assert scout.title_matches("Anything", []), "no filter keeps everything"


def test_usage_reports_spend_against_the_limit_and_is_cached(home, monkeypatch):
    calls = []

    def fetch(value):
        calls.append(value)
        return {"data": {"current": {"monthlyUsageUsd": 4.25}, "limits": {"maxMonthlyUsageUsd": 5},
                         "monthlyUsageCycle": {"endAt": "2026-11-06T23:59:59.999Z"}}}

    assert apify.usage(fetch=fetch) is None and calls == [], "no token, no call"
    monkeypatch.setenv(apify.TOKEN_KEY, TOKEN)
    apify._usage_cache.clear()
    first = apify.usage(now=1000, fetch=fetch)
    assert first == {"used_usd": 4.25, "limit_usd": 5.0, "ratio": 0.85, "warn": True, "cycle_end": "2026-11-06"}
    assert apify.usage(now=1000 + apify.USAGE_TTL_S - 1, fetch=fetch) == first and len(calls) == 1
    apify.usage(now=1000 + apify.USAGE_TTL_S + 1, fetch=fetch)
    assert len(calls) == 2

    def down(value):
        raise apify.ApifyError("Apify did not answer")

    assert apify.usage(now=10 ** 9, fetch=down) == first, "a failed check keeps the last figure"
    h = _H()
    monkeypatch.setattr(apify, "usage", lambda: first)
    assert routes.handle_get(h, urlparse("/api/job-os/apify/usage")) is True
    assert h.json()["apify"] == {"active": False, "usage": first} and TOKEN not in h.wfile.getvalue().decode()
    assert h.json()["display"] == {"show_logistics": True}
