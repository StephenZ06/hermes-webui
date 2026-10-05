"""Gated auto-apply: the gate, the preview -> approve -> submit flow, and the browser runner.

The runner is exercised against local fixture forms only; no real site is contacted.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from api import mailer, profiles
from api.job_os import apply_runner, autoapply, notify
from api.job_os.applications import board, timeline
from api.job_os.db import connect_job_os
from api.job_os.lifecycle import transition_job
from api.job_os.models import JobStatus
from api.job_os.repository import create_job, get_job, normalize_job_input
from api.job_os.settings import load_settings, save_settings

FORMS = Path(__file__).parent / "fixtures" / "job_os_forms"
REPO = Path(__file__).resolve().parents[1]
APPLICANT = {"full_name": "Jane Doe", "email": "jane@example.com", "phone": "+1 555 0100",
             "linkedin_url": "https://linkedin.com/in/jane", "portfolio_url": "https://jane.dev", "location": "Remote"}


# ---- classification (pure) -----------------------------------------------

@pytest.mark.parametrize("control, field", [
    ({"label": "First Name *", "name": "first_name", "type": "text", "tag": "input"}, "first_name"),
    ({"label": "Full name ✱", "name": "name", "type": "text", "tag": "input"}, "full_name"),
    ({"label": "Name", "name": "_systemfield_name", "type": "text", "tag": "input"}, "full_name"),
    ({"label": "Legal name", "name": "q", "type": "text", "tag": "input"}, "full_name"),
    ({"label": "Current company", "name": "org", "type": "text", "tag": "input"}, "unknown"),
    ({"label": "Company name", "name": "q", "type": "text", "tag": "input"}, "unknown"),
    ({"label": "Email", "name": "x", "type": "email", "tag": "input"}, "email"),
    ({"label": "Resume/CV", "name": "resume", "type": "file", "tag": "input"}, "resume"),
    ({"label": "Cover Letter", "name": "cover_letter", "type": "file", "tag": "input"}, "cover_letter"),
    ({"label": "Attach", "name": "cover_letter", "type": "file", "tag": "input", "accept": ".pdf"}, "cover_letter"),
    ({"label": "Attach", "name": "resume", "type": "file", "tag": "input", "accept": ".pdf"}, "resume"),
    ({"label": "", "name": "", "type": "file", "tag": "input", "accept": ".pdf"}, "unknown"),
    ({"label": "What's the name you'd prefer us to use?", "name": "q", "type": "text", "tag": "input"}, "unknown"),
    ({"label": "Will you now or in the future require sponsorship?", "name": "q", "type": "select-one", "tag": "select"}, "sensitive"),
    ({"label": "Desired salary", "name": "q", "type": "text", "tag": "input"}, "sensitive"),
    ({"label": "I agree to the privacy policy", "name": "consent", "type": "checkbox", "tag": "input"}, "sensitive"),
    ({"label": "Veteran status", "name": "q", "type": "select-one", "tag": "select"}, "eeo"),
    ({"label": "How did you hear about us?", "name": "q", "type": "text", "tag": "input"}, "unknown"),
])
def test_classify(control, field):
    assert apply_runner.classify(control) == field


def test_plan_fills_known_fields_and_stops_on_required_unknowns():
    controls = [
        {"index": 0, "label": "Full name", "name": "name", "type": "text", "tag": "input", "required": True},
        {"index": 1, "label": "Email", "name": "email", "type": "email", "tag": "input", "required": True},
        {"index": 2, "label": "How did you hear about us?", "name": "q", "type": "text", "tag": "input", "required": False},
        {"index": 3, "label": "Gender", "name": "g", "type": "select-one", "tag": "select", "required": False},
    ]
    fills, stops = apply_runner.plan(controls, APPLICANT, {}, "")
    assert [(f["field"], f["value"]) for f in fills] == [("full_name", "Jane Doe"), ("email", "jane@example.com")] and stops == []
    controls[2]["required"] = True
    assert apply_runner.plan(controls, APPLICANT, {}, "")[1] == ["Required question Hermes can't answer: “How did you hear about us?”"]


# ---- the browser runner, on local fixture forms ----------------------------

def _run(tmp_path, form, mode, **extra):
    pytest.importorskip("playwright.sync_api")
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n%fake\n")
    job = {"url": (FORMS / form).as_uri(), "mode": mode, "applicant": APPLICANT, "files": {"resume": str(resume)},
           "pdf_html": {}, "cover_text": "", "out_dir": str(tmp_path / "proof"), **extra}
    return apply_runner.run(job)


def test_runner_preview_fills_and_never_submits(tmp_path):
    result = _run(tmp_path, "greenhouse.html", "preview")
    assert result["status"] == "filled" and result["stops"] == []
    assert {f["field"] for f in result["filled"]} == {"first_name", "last_name", "email", "phone", "resume", "linkedin_url", "portfolio_url"}
    assert (tmp_path / "proof" / result["screenshots"][0]).stat().st_size > 1000


def test_runner_submit_waits_for_the_confirmation(tmp_path):
    result = _run(tmp_path, "greenhouse.html", "submit")
    assert result["status"] == "submitted" and len(result["screenshots"]) == 2


@pytest.mark.parametrize("form, reason", [
    ("lever_salary.html", "Salary, legal or consent question"),
    ("ashby_unknown.html", "Required question Hermes can't answer"),
    ("captcha.html", "A captcha must be solved by a person"),  # stops before pressing submit
])
def test_runner_stops_instead_of_guessing(tmp_path, form, reason):
    result = _run(tmp_path, form, "submit")
    assert result["status"] == "stopped" and reason in result["reason"]
    assert result["screenshots"]  # proof of where it stopped


def test_runner_reports_a_missing_confirmation(tmp_path):
    result = _run(tmp_path, "no_confirmation.html", "submit")
    assert result["status"] == "stopped" and "No confirmation" in result["reason"]


def test_runner_renders_tailored_documents_to_pdf(tmp_path):
    result = _run(tmp_path, "greenhouse.html", "preview", files={},
                  pdf_html={"resume": "<html><body><h1>Jane Doe</h1></body></html>"})
    assert (tmp_path / "proof" / "resume.pdf").read_bytes()[:4] == b"%PDF"
    assert "resume" in {f["field"] for f in result["filled"]}


def test_runner_subprocess_protocol(tmp_path):
    pytest.importorskip("playwright.sync_api")
    payload = {"url": (FORMS / "ashby_unknown.html").as_uri(), "mode": "preview", "applicant": APPLICANT, "files": {},
               "pdf_html": {}, "cover_text": "", "out_dir": str(tmp_path / "proof")}
    proc = subprocess.run([sys.executable, "-m", "api.job_os.apply_runner"], input=json.dumps(payload), capture_output=True,
                          text=True, timeout=120, cwd=str(REPO))
    assert json.loads(proc.stdout.strip().splitlines()[-1])["status"] == "stopped"


# ---- the gate and the flow ------------------------------------------------

@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    monkeypatch.setattr(mailer, "credentials", lambda: ("hermes.sender@gmail.com", "app-password"))
    monkeypatch.setattr("api.job_os.network_policy.socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    save_settings({"auto_apply": {"enabled": True, "min_fit_score": 70, "daily_cap": 2, "dry_run_first": True},
                   "applicant": {"full_name": "Jane Doe", "email": "jane@example.com"},
                   "notifications": {"email_enabled": True, "to_address": "me@gmail.com"}}, expected_revision=0)
    calls, sent = [], []
    outcome = {"preview": {"status": "filled", "filled": [{"field": "email", "label": "Email"}], "screenshots": ["20261006-010101-preview-filled.png"]},
               "submit": {"status": "submitted", "filled": [], "screenshots": []}}

    def runner(payload):
        calls.append(payload)
        return dict(outcome[payload["mode"]])

    monkeypatch.setattr(autoapply, "_runner", runner)
    monkeypatch.setattr(notify.mailer, "send", lambda *args: sent.append(args) or args[1])
    yield {"calls": calls, "outcome": outcome, "sent": sent}


def _ready_job(url="https://job-boards.greenhouse.io/acme/jobs/123", score=85):
    job = create_job(replace(normalize_job_input({"title": "Backend Engineer", "company": "Acme", "canonical_url": url}),
                             description="x"), status=JobStatus.SCRAPED)
    for status in (JobStatus.ANALYZED, JobStatus.SHORTLISTED, JobStatus.TAILORING, JobStatus.RESUME_READY, JobStatus.APPLICATION_READY):
        job = transition_job(job.id, status, expected_revision=job.revision)
    now = int(time.time())
    conn = connect_job_os()
    conn.execute("INSERT INTO job_analyses (job_id, status, fit_score, verdict, requested_at, finished_at) VALUES (?, 'done', ?, 'good', ?, ?)",
                 (job.id, score, now, now))
    conn.execute("INSERT INTO job_documents (id, job_id, kind, status, content, created_at, updated_at) VALUES (?, ?, 'resume', 'ready', '# Jane Doe', ?, ?)",
                 (job.id + "-r", job.id, now, now))
    conn.commit()
    conn.close()
    return job


def test_ats_detection_and_form_urls():
    assert autoapply.ats_of("https://jobs.lever.co/acme/abc") == "lever"
    assert autoapply.ats_of("https://careers.acme.com/jobs?gh_jid=1") is None
    assert autoapply.form_url("https://jobs.lever.co/acme/abc", "lever") == "https://jobs.lever.co/acme/abc/apply"
    assert autoapply.form_url("https://jobs.ashbyhq.com/acme/abc?src=x", "ashby") == "https://jobs.ashbyhq.com/acme/abc/application"
    assert autoapply.form_url("https://job-boards.greenhouse.io/acme/jobs/1", "greenhouse") == "https://job-boards.greenhouse.io/acme/jobs/1"


def test_gate_refuses_with_a_reason(store):
    job = _ready_job()
    save_settings({"auto_apply": {"enabled": False}}, expected_revision=load_settings()["revision"])
    with pytest.raises(autoapply.AutoApplyError, match="off"):
        autoapply.request_preview(job.id, start_worker=False)
    save_settings({"auto_apply": {"enabled": True}}, expected_revision=load_settings()["revision"])
    with pytest.raises(autoapply.AutoApplyError, match="Greenhouse, Lever and Ashby"):
        autoapply.request_preview(_ready_job(url="https://careers.example.com/jobs/1").id, start_worker=False)
    with pytest.raises(autoapply.AutoApplyError, match="Fit score"):
        autoapply.request_preview(_ready_job(url="https://jobs.lever.co/acme/low", score=60).id, start_worker=False)
    save_settings({"auto_apply": {"allowed_ats": ["lever"]}}, expected_revision=load_settings()["revision"])
    with pytest.raises(autoapply.AutoApplyError, match="allowed"):
        autoapply.request_preview(job.id, start_worker=False)


def test_preview_then_approve_submits_and_records_auto(store):
    job = _ready_job()
    autoapply._execute(job.id, "preview", "manual")
    assert get_job(job.id).status == JobStatus.AWAITING_APPROVAL
    assert store["calls"][0]["url"] == "https://job-boards.greenhouse.io/acme/jobs/123" and "resume" in store["calls"][0]["pdf_html"]
    card = next(c for col in board()["columns"] for c in col["jobs"] if c["id"] == job.id)
    assert card["auto"]["status"] == "filled" and card["auto"]["screenshots"]
    email = store["sent"][-1]
    assert email[2].startswith("Ready to send") and "APPLY " in email[3]
    autoapply._execute(job.id, "submit", "manual")
    assert get_job(job.id).status == JobStatus.SUBMITTED
    assert [e["data"]["method"] for e in timeline(job.id) if e["type"] == "application_submitted"] == ["auto"]
    assert autoapply.submitted_today() == 1


def test_failed_submission_goes_back_and_needs_attention(store):
    job = _ready_job()
    autoapply._execute(job.id, "preview", "manual")
    store["outcome"]["submit"] = {"status": "stopped", "reason": "A captcha appeared after pressing submit.", "screenshots": []}
    autoapply._execute(job.id, "submit", "manual")
    assert get_job(job.id).status == JobStatus.APPLICATION_READY
    card = next(c for col in board()["columns"] for c in col["jobs"] if c["id"] == job.id)
    assert any("captcha" in reason for reason in card["attention"])


def test_cancel_returns_the_job(store):
    job = _ready_job()
    autoapply._execute(job.id, "preview", "manual")
    autoapply.cancel(job.id)
    assert get_job(job.id).status == JobStatus.APPLICATION_READY


def test_daily_cap_blocks_submissions(store):
    jobs = [_ready_job(url=f"https://jobs.lever.co/acme/{n}") for n in range(3)]
    for job in jobs:
        autoapply._execute(job.id, "preview", "manual")
    for job in jobs:
        autoapply._execute(job.id, "submit", "manual")
    assert [get_job(j.id).status for j in jobs] == [JobStatus.SUBMITTED, JobStatus.SUBMITTED, JobStatus.APPLICATION_READY]
    assert sum(1 for c in store["calls"] if c["mode"] == "submit") == 2  # the third never reached the browser


def test_schedule_previews_first_then_submits_directly_and_never_retries(store):
    first = _ready_job(url="https://jobs.lever.co/acme/1")
    assert autoapply.tick(start_worker=False) == first.id
    autoapply._work()
    assert get_job(first.id).status == JobStatus.AWAITING_APPROVAL  # dry run first: waits for you
    assert autoapply.tick(start_worker=False) is None  # already tried: never picked again
    autoapply.approve(first.id, start_worker=False)
    autoapply._work()
    assert get_job(first.id).status == JobStatus.SUBMITTED
    second = _ready_job(url="https://jobs.lever.co/acme/2")
    assert autoapply.tick(start_worker=False) == second.id
    autoapply._work()
    assert get_job(second.id).status == JobStatus.SUBMITTED  # Lever is trusted now
    assert [c["mode"] for c in store["calls"]] == ["preview", "submit", "submit"]


def test_schedule_never_retries_a_stopped_job(store):
    job = _ready_job(url="https://jobs.lever.co/acme/stuck")
    store["outcome"]["preview"] = {"status": "stopped", "reason": "Salary, legal or consent question", "screenshots": []}
    assert autoapply.tick(start_worker=False) == job.id
    autoapply._work()
    assert get_job(job.id).status == JobStatus.APPLICATION_READY
    assert autoapply.tick(start_worker=False) is None
    assert len(store["calls"]) == 1


def test_email_apply_code_approves(store, monkeypatch):
    job = _ready_job()
    autoapply._execute(job.id, "preview", "manual")
    code = notify._COMMAND.findall(store["sent"][-1][3])[0][1]
    monkeypatch.setattr(autoapply, "approve", lambda job_id, **k: store.setdefault("approved", []).append(job_id))
    from email.message import EmailMessage

    message = EmailMessage()
    message["Authentication-Results"] = "mx.google.com; dkim=pass; spf=pass; dmarc=pass header.from=gmail.com"
    message["From"] = "me@gmail.com"
    message.set_content(f"APPLY {code}")
    outcome = notify.handle_message(bytes(message), load_settings())
    assert store["approved"] == [job.id] and outcome[0].startswith("Sending")
