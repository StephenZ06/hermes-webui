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
    assert run["status"] == "completed" and run["counts"]["saved"] == 1 and run["errors"][0]["where"] == "Apify A"
    results += [apify.ApifyError("Your Apify account is out of credit for this month.")]
    failed = _run(scout.create_search({"keywords": "y", "country": "my"}))
    assert failed["status"] == "failed" and "out of credit" in failed["stage_detail"]


def test_apify_on_without_a_token_fails_clearly(home, monkeypatch):
    save_settings({"apify": {"enabled": True}}, expected_revision=0)
    run = _run(scout.create_search({"keywords": "x", "country": "my"}))
    assert run["status"] == "failed" and "not connected" in run["stage_detail"]


def test_apify_settings_are_validated(home):
    from api.job_os.settings import SettingsError

    for bad in ({"indeed_actor": "no-slash"}, {"results_per_city": 0}, {"results_per_city": 5000}, {"enabled": "yes"}):
        with pytest.raises(SettingsError):
            save_settings({"apify": bad}, expected_revision=0)
    assert save_settings({"apify": {"indeed_actor": "someone/indeed-v2", "results_per_city": 120}}, expected_revision=0)["apify"] == {
        "enabled": False, "indeed_actor": "someone/indeed-v2", "results_per_city": 120}
