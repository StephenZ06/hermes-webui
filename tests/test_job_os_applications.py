"""Applications board, manual apply recording, attention, funnel."""

from __future__ import annotations

import io
import json
import time
from dataclasses import replace
from urllib.parse import urlparse

import pytest

from api import profiles, routes
from api.job_os import applications
from api.job_os.db import connect_job_os
from api.job_os.lifecycle import transition_job
from api.job_os.models import JobStatus
from api.job_os.repository import create_job, get_job, normalize_job_input


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    monkeypatch.setattr(routes, "_check_csrf", lambda _h: True)
    monkeypatch.setattr(routes, "_guard_request_session_visibility", lambda *a, **k: True)


def _job_at(status: JobStatus, n=[0]):
    n[0] += 1
    job = create_job(replace(normalize_job_input({"title": f"Job {n[0]}", "canonical_url": f"https://jobs.example.test/{n[0]}"}),
                             description="x"), status=JobStatus.SCRAPED)
    path = [JobStatus.ANALYZED, JobStatus.SHORTLISTED, JobStatus.TAILORING, JobStatus.RESUME_READY,
            JobStatus.APPLICATION_READY, JobStatus.AWAITING_APPROVAL, JobStatus.APPLYING, JobStatus.SUBMITTED,
            JobStatus.SCREENING, JobStatus.INTERVIEWING, JobStatus.OFFER]
    for target in path:
        if job.status == status:
            break
        job = transition_job(job.id, target, expected_revision=job.revision)
    return job


def test_mark_applied_walks_the_path_and_records_how(store):
    job = _job_at(JobStatus.APPLICATION_READY)
    assert applications.mark_applied(job.id, note="via site")["status"] == "submitted"
    events = applications.timeline(job.id)
    assert [e["data"].get("to") for e in events if e["type"] == "status_changed"][-3:] == ["awaiting_approval", "applying", "submitted"]
    assert events[-1] == {"type": "application_submitted", "data": {"method": "manual", "note": "via site"}, "at": events[-1]["at"]}
    # Applied without a tailored resume: straight to submitted.
    untailored = _job_at(JobStatus.ANALYZED)
    assert applications.mark_applied(untailored.id)["status"] == "submitted"
    assert [e["data"].get("to") for e in applications.timeline(untailored.id) if e["type"] == "status_changed"][-1] == "submitted"
    with pytest.raises(applications.ApplicationError):
        applications.mark_applied(_job_at(JobStatus.TAILORING).id)  # wait for the resume first


def test_board_columns_attention_and_follow_up(store):
    ready = _job_at(JobStatus.APPLICATION_READY)
    review = _job_at(JobStatus.RESUME_READY)
    applied = _job_at(JobStatus.SUBMITTED)
    interviewing = _job_at(JobStatus.INTERVIEWING)
    now = int(time.time())
    conn = connect_job_os()
    conn.execute("INSERT INTO job_documents (id, job_id, kind, status, created_at, updated_at) VALUES ('d1', ?, 'resume', 'needs_review', ?, ?)", (review.id, now, now))
    conn.execute("UPDATE job_events SET created_at=? WHERE job_id=? AND event_type='status_changed'", (now - 9 * 86400, applied.id))
    conn.commit()
    conn.close()
    new = _job_at(JobStatus.SCRAPED)
    skipped = _job_at(JobStatus.SCRAPED)
    skipped = transition_job(skipped.id, JobStatus.SKIPPED, expected_revision=skipped.revision)
    cols = {c["key"]: [j["id"] for j in c["jobs"]] for c in applications.board()["columns"]}
    assert list(cols) == ["new", "shortlisted", "resume", "ready", "applied", "interviewing", "offers", "closed"]
    assert cols["ready"] == [ready.id] and cols["resume"] == [review.id] and cols["new"] == [new.id]
    assert cols["applied"] == [applied.id] and cols["interviewing"] == [interviewing.id] and cols["closed"] == [skipped.id]
    review_card = next(j for j in applications.board()["columns"][2]["jobs"] if j["id"] == review.id)
    assert review_card["attention"] == ["A tailored document has numbers to check"]
    card = next(j for c in applications.board()["columns"] for j in c["jobs"] if j["id"] == applied.id)
    assert card["attention"] and "follow up" in card["attention"][0]
    from api.job_os.dashboard import build_dashboard
    assert build_dashboard()["needs_attention"] == 2  # the review card and the follow-up nudge


def test_board_narrows_to_one_source_and_counts_both(store):
    manual = _job_at(JobStatus.SCRAPED)
    found = create_job(normalize_job_input({"title": "Found", "canonical_url": "https://malaysia.indeed.com/viewjob?jk=abc1",
                                            "source": "indeed", "country": "Malaysia", "salary_text": "RM 5,000 / month"}),
                       status=JobStatus.SCRAPED)
    ids = lambda board: [j["id"] for c in board["columns"] for j in c["jobs"]]
    assert sorted(ids(applications.board())) == sorted([manual.id, found.id])
    indeed_board = applications.board("indeed")
    assert ids(indeed_board) == [found.id] and ids(applications.board("manual")) == [manual.id]
    assert indeed_board["sources"] == {"all": 2, "indeed": 1, "linkedin": 0, "jobstreet": 0, "manual": 1}
    card = indeed_board["columns"][0]["jobs"][0]
    assert (card["source"], card["country"], card["salary_text"]) == ("indeed", "Malaysia", "RM 5,000 / month")


def test_funnel_counts_progress(store):
    _job_at(JobStatus.ANALYZED)
    _job_at(JobStatus.SUBMITTED)
    _job_at(JobStatus.OFFER)
    counts = {s["key"]: s["count"] for s in applications.funnel()}
    assert counts == {"found": 3, "analysed": 0, "shortlisted": 2, "applied": 2, "interviewing": 1, "offers": 1}


class _H:
    def __init__(self, body=None):
        raw = json.dumps(body or {}).encode()
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile, self.wfile, self.status = io.BytesIO(raw), io.BytesIO(), None

    def send_response(self, s):
        self.status = s

    def send_header(self, *_):
        pass

    def end_headers(self):
        pass


def test_routes(store):
    job = _job_at(JobStatus.APPLICATION_READY)
    h = _H({"note": "x"})
    routes.handle_post(h, urlparse(f"/api/job-os/jobs/{job.id}/applied"))
    assert h.status == 200 and get_job(job.id).status == JobStatus.SUBMITTED
    n = _H({"text": "Called recruiter"})
    routes.handle_post(n, urlparse(f"/api/job-os/jobs/{job.id}/note"))
    assert n.status == 200
    empty = _H({"text": "  "})
    routes.handle_post(empty, urlparse(f"/api/job-os/jobs/{job.id}/note"))
    assert empty.status == 400
    b = _H()
    routes.handle_get(b, urlparse("/api/job-os/applications"))
    assert [c["key"] for c in json.loads(b.wfile.getvalue())["columns"]][:2] == ["new", "shortlisted"]
    bad = _H()
    routes.handle_get(bad, urlparse("/api/job-os/applications?source=monster"))
    assert bad.status == 400
    t = _H()
    routes.handle_get(t, urlparse(f"/api/job-os/jobs/{job.id}/timeline"))
    assert json.loads(t.wfile.getvalue())["timeline"][-1]["data"]["text"] == "Called recruiter"


def _post(path, body):
    h = _H(body)
    routes.handle_post(h, urlparse(path))
    return h, json.loads(h.wfile.getvalue() or b"{}")


def test_the_manual_tracker_saves_details_and_a_described_job_is_ready_to_work_on(store):
    h, data = _post("/api/job-os/jobs", {"title": "Data Analyst", "canonical_url": "https://careers.acme.test/jobs/7",
                                          "company": "Acme", "country": "Singapore", "location": "Jurong",
                                          "salary_text": "SGD 6,000 / month", "employment_type": "Full time",
                                          "workplace": "hybrid", "description": "SQL, Python, dashboards",
                                          "source": "indeed"})
    assert h.status == 201, data
    job = get_job(data["job"]["id"])
    assert job.source == "manual", "the tracker can't pose as a Scout find"
    assert job.status == JobStatus.SCRAPED and job.country == "Singapore" and job.workplace == "hybrid"
    bare, data = _post("/api/job-os/jobs", {"title": "Later", "canonical_url": "https://careers.acme.test/jobs/8"})
    assert get_job(data["job"]["id"]).status == JobStatus.DISCOVERED
    bad, _ = _post("/api/job-os/jobs", {"title": "X", "canonical_url": "https://careers.acme.test/jobs/9", "workplace": "moon"})
    assert bad.status == 400


def test_edit_updates_details_with_a_revision_check(store):
    job = _job_at(JobStatus.SCRAPED)
    h, data = _post(f"/api/job-os/jobs/{job.id}/edit", {"job": {"salary_text": "RM 7,000", "country": "Malaysia"},
                                                       "expected_revision": job.revision})
    assert h.status == 200, data
    edited = get_job(job.id)
    assert (edited.salary_text, edited.country, edited.revision) == ("RM 7,000", "Malaysia", job.revision + 1)
    assert edited.status == JobStatus.SCRAPED and edited.canonical_url == job.canonical_url
    stale, _ = _post(f"/api/job-os/jobs/{job.id}/edit", {"job": {"salary_text": "x"}, "expected_revision": job.revision})
    assert stale.status == 409
    for change in ({"status": "offer"}, {"canonical_url": "https://evil.test"}, {"title": ""}):
        refused, _ = _post(f"/api/job-os/jobs/{job.id}/edit", {"job": change, "expected_revision": edited.revision})
        assert refused.status == 400, change
    assert applications.timeline(job.id)[-1]["type"] == "details_edited"


def test_cards_offer_only_the_moves_their_stage_allows(store):
    moves = lambda status: [value for value, _label in applications.moves_for(status)]
    assert moves(JobStatus.SCRAPED) == ["shortlisted", "submitted", "skipped"]
    assert moves(JobStatus.RESUME_READY) == ["shortlisted", "submitted"]
    assert moves(JobStatus.SUBMITTED) == ["screening", "rejected", "no_response", "withdrawn"]
    assert moves(JobStatus.OFFER) == ["offer_accepted", "offer_declined", "withdrawn"]
    assert moves(JobStatus.REJECTED) == []
