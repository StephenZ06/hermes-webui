"""Resume tailoring with a fake model: truthfulness flags, coverage, lifecycle, exports."""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import replace
from urllib.parse import urlparse

import pytest

from api import profiles, routes
from api.job_os import analysis, export, llm, resume, tailor
from api.job_os.lifecycle import transition_job
from api.job_os.models import JobStatus
from api.job_os.db import connect_job_os
from api.job_os.repository import create_job, get_job, normalize_job_input

MASTER = ("# Jane Doe\njane@example.com\n## Experience\n- Built Python services on AWS for 8 years.\n"
          "- Cut latency 40% with Kafka.\n" + "Shipped Postgres-backed APIs. " * 10)
TAILORED = "# Jane Doe\njane@example.com\n## Summary\nBackend engineer.\n## Experience\n- **Python** services on AWS for 8 years.\n- Cut latency 40% with Kafka and Postgres.\n" + "More detail. " * 20


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    monkeypatch.setattr(routes, "_check_csrf", lambda _h: True)
    monkeypatch.setattr(routes, "_guard_request_session_visibility", lambda *a, **k: True)
    monkeypatch.setattr(tailor, "_recovered", False)
    answer = {"resume_markdown": TAILORED, "cover_letter": "Dear Acme team, I have 8 years of Python.",
              "changes": [{"what": "Led with Python", "why": "Must-have"}]}
    monkeypatch.setattr(llm, "_transport", lambda **kw: json.dumps(answer))
    resume.save_resume(filename="cv.md", text=MASTER)
    return answer


def _shortlisted():
    job = create_job(replace(normalize_job_input({"title": "Backend", "company": "Acme", "canonical_url": "https://jobs.example.test/b"}),
                             description="Python, AWS, Kafka"), status=JobStatus.SCRAPED)
    job = transition_job(job.id, JobStatus.ANALYZED, expected_revision=job.revision)
    return transition_job(job.id, JobStatus.SHORTLISTED, expected_revision=job.revision)


def test_number_guard_and_coverage():
    assert tailor.unverified_numbers("Grew revenue 300% over 12 years", "Grew revenue in 8 years") == ["300%", "12"]
    assert tailor.unverified_numbers("Cut latency 40% in 2021", "cut latency 40 % in 2021") == []
    cov = tailor.keyword_coverage("Python and AWS services", ["Strong Python experience", "Kubernetes in production"])
    assert cov == {"found": ["Strong Python experience"], "missing": ["Kubernetes in production"], "score": 50}


def test_tailoring_moves_the_job_and_stores_both_documents(store):
    job = _shortlisted()
    tailor.request_tailoring(job.id, start_worker=False)
    assert get_job(job.id).status == JobStatus.TAILORING
    docs = tailor.tailor_one(job.id)
    assert docs["resume"]["status"] == "ready" and docs["cover_letter"]["status"] == "ready"
    assert docs["resume"]["notes"]["changes"][0]["what"] == "Led with Python"
    assert get_job(job.id).status == JobStatus.RESUME_READY


def test_the_tailored_resume_is_scored_like_the_master(store, monkeypatch):
    def transport(**kw):
        if "career analyst" in kw["system"]:  # the scoring prompt
            return json.dumps({"fit_score": 84 if "Kafka and Postgres" in kw["user"] else 61, "verdict": "good", "summary": "Closer."})
        return json.dumps(store)
    monkeypatch.setattr(llm, "_transport", transport)
    job = _shortlisted()
    conn = connect_job_os()
    conn.execute("INSERT INTO job_analyses (job_id, status, fit_score, verdict, data_json, requested_at, finished_at)"
                 " VALUES (?, 'done', 68, 'stretch', '{}', 1, 1)", (job.id,))
    conn.commit()
    conn.close()
    tailor.request_tailoring(job.id, start_worker=False)
    notes = tailor.tailor_one(job.id)["resume"]["notes"]
    assert notes["master_fit"] == 68
    assert notes["tailored_fit"]["status"] == "done" and notes["tailored_fit"]["fit_score"] == 84
    doc = tailor.latest_documents(job.id)["resume"]
    edited = tailor.update_document(doc["id"], "# Jane\n\nRewritten without the services line.", expected_revision=doc["revision"])
    assert edited["notes"]["tailored_fit"]["stale"] is True
    again = tailor.rescore_document(doc["id"], run_async=False)
    assert again["notes"]["tailored_fit"]["fit_score"] == 61 and "stale" not in again["notes"]["tailored_fit"]


def test_a_failed_tailored_score_keeps_the_tailored_resume(store):
    job = _shortlisted()
    tailor.request_tailoring(job.id, start_worker=False)
    docs = tailor.tailor_one(job.id)  # the stub answers the scoring prompt with the tailoring JSON (no fit_score)
    assert docs["resume"]["status"] == "ready" and docs["resume"]["notes"]["tailored_fit"]["status"] == "failed"


def test_invented_numbers_mark_the_resume_for_review(store):
    store["resume_markdown"] = TAILORED + "\n- Managed a team of 15 engineers.\n"
    job = _shortlisted()
    tailor.request_tailoring(job.id, start_worker=False)
    docs = tailor.tailor_one(job.id)
    assert docs["resume"]["status"] == "needs_review" and docs["resume"]["notes"]["unverified"] == ["15"]
    edited = tailor.update_document(docs["resume"]["id"], TAILORED, expected_revision=docs["resume"]["revision"])
    assert edited["status"] == "ready" and edited["notes"]["unverified"] == [] and edited["notes"]["edited"]
    with pytest.raises(tailor.TailorError):
        tailor.update_document(docs["resume"]["id"], TAILORED, expected_revision=0)


def test_a_failed_tailoring_returns_the_job_to_shortlisted(store, monkeypatch):
    job = _shortlisted()
    tailor.request_tailoring(job.id, start_worker=False)
    monkeypatch.setattr(llm, "_transport", lambda **kw: "nope")
    docs = tailor.tailor_one(job.id)
    assert docs["resume"]["status"] == "failed" and get_job(job.id).status == JobStatus.SHORTLISTED


def test_tailoring_needs_a_shortlisted_job_with_a_description(store):
    bare = create_job(normalize_job_input({"title": "Bare", "canonical_url": "https://jobs.example.test/bare"}))
    with pytest.raises(tailor.TailorError):
        tailor.request_tailoring(bare.id, start_worker=False)


def test_a_tracked_job_with_a_description_can_be_tailored_without_analysis(store):
    job = create_job(normalize_job_input({"title": "Analyst", "canonical_url": "https://jobs.example.test/manual",
                                          "description": "SQL and Python"}), status=JobStatus.SCRAPED)
    assert tailor.request_tailoring(job.id, start_worker=False)["status"] == "tailoring"
    assert get_job(job.id).status == JobStatus.TAILORING


def test_exports_are_valid():
    docx = export.to_docx(TAILORED)
    with zipfile.ZipFile(io.BytesIO(docx)) as z:
        assert {"[Content_Types].xml", "word/document.xml", "word/styles.xml"} <= set(z.namelist())
    text = resume._docx_text(docx)
    assert text.startswith("Jane Doe") and "• Python services on AWS for 8 years." in text
    page = export.to_html(TAILORED + "\n[site](javascript:alert(1))", title="Resume", auto_print=True)
    assert '<h1 class="name">Jane Doe</h1>' in page and "<strong>Python</strong>" in page and "window.print" in page
    assert "javascript:" not in page


class _H:
    def __init__(self, body=None):
        raw = json.dumps(body or {}).encode()
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile, self.wfile, self.status, self.sent = io.BytesIO(raw), io.BytesIO(), None, {}

    def send_response(self, s):
        self.status = s

    def send_header(self, k, v):
        self.sent[k] = v

    def end_headers(self):
        pass


def test_routes_tailor_export_and_ready(store, monkeypatch):
    monkeypatch.setattr(tailor, "ensure_worker", lambda: None)
    job = _shortlisted()
    h = _H()
    routes.handle_post(h, urlparse(f"/api/job-os/jobs/{job.id}/tailor"))
    assert h.status == 200
    tailor.tailor_one(job.id)
    g = _H()
    routes.handle_get(g, urlparse(f"/api/job-os/jobs/{job.id}"))
    doc_id = json.loads(g.wfile.getvalue())["job"]["documents"]["resume"]["id"]
    x = _H()
    routes.handle_get(x, urlparse(f"/api/job-os/documents/{doc_id}/export?format=docx"))
    assert x.status == 200 and x.sent["Content-Disposition"].endswith('.docx"') and x.wfile.getvalue()[:2] == b"PK"
    listing = _H()
    routes.handle_get(listing, urlparse("/api/job-os/documents"))
    assert json.loads(listing.wfile.getvalue())["documents"][0]["job_title"] == "Backend"
    ready = _H()
    routes.handle_post(ready, urlparse(f"/api/job-os/jobs/{job.id}/ready"))
    assert ready.status == 200 and get_job(job.id).status == JobStatus.APPLICATION_READY
    again = _H()
    routes.handle_post(again, urlparse(f"/api/job-os/jobs/{job.id}/ready"))
    assert again.status == 400
