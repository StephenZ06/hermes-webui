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
    with pytest.raises(applications.ApplicationError):
        applications.mark_applied(_job_at(JobStatus.ANALYZED).id)


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
    cols = {c["key"]: [j["id"] for j in c["jobs"]] for c in applications.board()["columns"]}
    assert cols["ready"] == [ready.id] and cols["attention"] == [review.id]
    assert cols["applied"] == [applied.id] and cols["interviewing"] == [interviewing.id]
    card = next(j for c in applications.board()["columns"] for j in c["jobs"] if j["id"] == applied.id)
    assert card["attention"] and "follow up" in card["attention"][0]


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
    assert [c["key"] for c in json.loads(b.wfile.getvalue())["columns"]][:2] == ["preparing", "ready"]
    t = _H()
    routes.handle_get(t, urlparse(f"/api/job-os/jobs/{job.id}/timeline"))
    assert json.loads(t.wfile.getvalue())["timeline"][-1]["data"]["text"] == "Called recruiter"
