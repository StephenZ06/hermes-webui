"""Master resume and Luna job analysis (with a fake model)."""

from __future__ import annotations

import base64
import io
import json
import zipfile
from urllib.parse import urlparse

import pytest

from api import profiles, routes
from api.job_os import analysis, llm, resume
from api.job_os.models import JobStatus
from api.job_os.repository import create_job, get_job, normalize_job_input

RESUME = ("Jane Doe\nSenior Backend Engineer\n" + "Built Python services on AWS with Postgres and Kafka for 8 years. " * 6)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    monkeypatch.setattr(routes, "_check_csrf", lambda _h: True)
    monkeypatch.setattr(routes, "_guard_request_session_visibility", lambda *a, **k: True)
    monkeypatch.setattr(analysis, "_recovered", False)
    calls = []

    def fake(**kw):
        calls.append(kw)
        return json.dumps({"fit_score": 91.6, "verdict": "STRONG", "summary": "Close match.",
                           "strengths": ["8 years Python", "AWS"], "gaps": ["No Go"], "must_haves": ["Python"] * 9})
    monkeypatch.setattr(llm, "_transport", fake)
    return calls


def _job(description="Python, AWS, Postgres"):
    job = normalize_job_input({"title": "Backend", "canonical_url": f"https://jobs.example.test/{len(description)}-{id(description)}"})
    from dataclasses import replace
    return create_job(replace(job, description=description), status=JobStatus.SCRAPED)


def _docx(paragraphs):
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = "".join(f"<w:p>{'<w:pPr><w:numPr/></w:pPr>' if b else ''}<w:r><w:t>{t}</w:t></w:r></w:p>" for t, b in paragraphs)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f"<w:document {ns}><w:body>{body}</w:body></w:document>")
    return buf.getvalue()


def test_resume_text_from_txt_and_docx_and_rejections(store):
    assert "Jane Doe" in resume.extract_text("cv.md", RESUME.encode())
    text = resume.extract_text("cv.docx", _docx([("Jane Doe", False), ("Python services " * 30, True)]))
    assert text.startswith("Jane Doe") and "\n• Python services" in text
    with pytest.raises(resume.ResumeError):
        resume.extract_text("cv.exe", b"x" * 500)
    with pytest.raises(resume.ResumeError):
        resume.extract_text("cv.txt", b"too short")
    meta = resume.save_resume(filename="cv.md", text=RESUME, original=RESUME.encode())
    assert meta["revision"] == 1 and resume.load_resume()["text"].startswith("Jane Doe")
    assert resume.save_resume(filename="cv.md", text=RESUME)["revision"] == 2


def test_analysis_needs_a_resume(store):
    with pytest.raises(analysis.AnalysisError):
        analysis.request_analysis([_job().id])


def test_analysis_scores_cleans_and_moves_the_job_to_analyzed(store):
    resume.save_resume(filename="cv.md", text=RESUME)
    job = _job()
    assert analysis.request_analysis([job.id], start_worker=False) == 1
    assert analysis.request_analysis([job.id], start_worker=False) == 0, "already queued"
    result = analysis.analyze_one(job.id)
    assert result["status"] == "done" and result["fit_score"] == 92 and result["verdict"] == "strong"
    assert len(result["must_haves"]) == 5
    assert get_job(job.id).status == JobStatus.ANALYZED
    prompt = store[0]["user"]
    assert "<<<POSTING" in prompt and "Jane Doe" in prompt and "untrusted" in store[0]["system"]
    assert analysis.request_analysis([job.id], start_worker=False) == 0, "done jobs are not re-queued"
    assert analysis.request_analysis([job.id], force=True, start_worker=False) == 1


def test_a_bad_model_answer_fails_cleanly(store, monkeypatch):
    resume.save_resume(filename="cv.md", text=RESUME)
    job = _job()
    analysis.request_analysis([job.id], start_worker=False)
    monkeypatch.setattr(llm, "_transport", lambda **kw: "I think it's a good fit!")
    result = analysis.analyze_one(job.id)
    assert result["status"] == "failed" and "JSON" in result["error"]
    assert get_job(job.id).status == JobStatus.SCRAPED


def test_jobs_without_a_description_are_skipped_and_orphans_requeue(store):
    resume.save_resume(filename="cv.md", text=RESUME)
    bare = create_job(normalize_job_input({"title": "Bare", "canonical_url": "https://jobs.example.test/bare"}))
    assert analysis.request_analysis([bare.id], start_worker=False) == 0
    job = _job()
    analysis.request_analysis([job.id], start_worker=False)
    from api.job_os.db import connect_job_os
    conn = connect_job_os()
    conn.execute("UPDATE job_analyses SET status='running'")
    conn.commit()
    conn.close()
    analysis._requeue_orphans()
    assert analysis.get_analysis(job.id)["status"] == "pending"


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


def test_routes_upload_resume_and_queue_analysis(store, monkeypatch):
    monkeypatch.setattr(analysis, "ensure_worker", lambda: None)
    h = _H({"filename": "cv.md", "content_base64": base64.b64encode(RESUME.encode()).decode()})
    routes.handle_post(h, urlparse("/api/job-os/resume"))
    assert h.status == 200 and json.loads(h.wfile.getvalue())["resume"]["words"] > 50
    bad = _H({"filename": "cv.md", "content_base64": "%%%"})
    routes.handle_post(bad, urlparse("/api/job-os/resume"))
    assert bad.status == 400
    job = _job()
    q = _H({"scope": "new"})
    routes.handle_post(q, urlparse("/api/job-os/analyze"))
    assert json.loads(q.wfile.getvalue())["queued"] == 1
    g = _H()
    routes.handle_get(g, urlparse(f"/api/job-os/jobs/{job.id}"))
    assert json.loads(g.wfile.getvalue())["job"]["analysis"]["status"] == "pending"
    lst = _H()
    routes.handle_get(lst, urlparse("/api/job-os/jobs"))
    assert json.loads(lst.wfile.getvalue())["jobs"][0]["analysis"] == {"status": "pending", "fit_score": None, "verdict": ""}
