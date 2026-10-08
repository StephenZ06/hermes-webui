"""Luna reads employer replies and moves applied jobs to Rejected or Interview."""

from __future__ import annotations

import uuid
from dataclasses import replace
from email.message import EmailMessage

import pytest

from api import mailer, profiles
from api.job_os import applications, outcomes
from api.job_os.lifecycle import transition_job
from api.job_os.models import JobStatus
from api.job_os.repository import create_job, get_job, normalize_job_input
from api.job_os.settings import save_settings


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    monkeypatch.setattr(mailer, "credentials", lambda: ("hermes.bot@gmail.com", "app-password"))


def _applied(title, company):
    job = create_job(replace(normalize_job_input({"title": title, "company": company, "canonical_url": f"https://jobs.example.test/{uuid.uuid4().hex}"}),
                             description="x"), status=JobStatus.SCRAPED)
    return transition_job(job.id, JobStatus.SUBMITTED, expected_revision=job.revision)


def _mail(subject, body, sender="Talent Team <careers@acme.example>"):
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = sender, "hermes.bot@gmail.com", subject
    message.set_content(body)
    return message.as_bytes()


def _check(raws, verdicts):
    asked = []

    def ask(_system, user, max_tokens):
        asked.append(user)
        return verdicts.pop(0), "test/model"

    first = outcomes.check(fetch=lambda *_a: ([], {"outcome_uidvalidity": 1, "outcome_last_uid": 10}), ask=ask)
    moved = outcomes.check(fetch=lambda *_a: (raws, {"outcome_uidvalidity": 1, "outcome_last_uid": 12}), ask=ask)
    return first, moved, asked


def test_a_rejection_and_an_interview_invite_move_their_jobs(store):
    soc = _applied("SOC Analyst", "Acme")
    sec = _applied("Security Analyst", "Globex")
    other = _applied("IT Analyst", "Initech")
    raws = [_mail("Your application for SOC Analyst", "Unfortunately we will not be moving forward with your application."),
            _mail("Globex — next steps", "We'd like to invite you to an interview for the Security Analyst role.", "hr@globex.example"),
            _mail("Weekend sale!", "50% off everything this weekend.")]
    verdicts = [{"about_application": True, "job_id": soc.id, "decision": "rejected", "confidence": 0.95, "summary": "Not selected."},
                {"about_application": True, "job_id": sec.id, "decision": "interview", "confidence": 0.9, "summary": "Interview invite."}]
    first, moved, asked = _check(raws, verdicts)
    assert first == 0, "the first check only notes where the inbox is"
    assert moved == 2 and len(asked) == 2, "mail that isn't about an application never reaches Luna"
    assert soc.id in asked[0] and "Unfortunately" in asked[0]
    assert get_job(soc.id).status == JobStatus.REJECTED and get_job(sec.id).status == JobStatus.INTERVIEWING
    assert get_job(other.id).status == JobStatus.SUBMITTED
    event = [e for e in applications.timeline(soc.id) if e["type"] == "status_changed"][-1]["data"]
    assert event["by"] == "email" and event["subject"] == "Your application for SOC Analyst" and event["sender"] == "careers@acme.example"


def test_unsure_unmatched_or_acknowledgement_mail_moves_nothing(store):
    job = _applied("SOC Analyst", "Acme")
    raws = [_mail("Application received", "Thank you for your application. We will review it."),
            _mail("About your application", "Unfortunately the role has been filled."),
            _mail("Interview", "Please pick an interview slot.")]
    verdicts = [{"about_application": True, "job_id": job.id, "decision": "other", "confidence": 0.9},
                {"about_application": True, "job_id": job.id, "decision": "rejected", "confidence": 0.4},
                {"about_application": True, "job_id": "not-a-listed-job", "decision": "interview", "confidence": 0.95}]
    _first, moved, asked = _check(raws, verdicts)
    assert moved == 0 and len(asked) == 3
    assert get_job(job.id).status == JobStatus.SUBMITTED


def test_nothing_is_read_when_turned_off_or_without_applied_jobs(store):
    save_settings({"notifications": {"track_outcomes": False}}, expected_revision=0)
    assert outcomes.check(fetch=lambda *_a: (_ for _ in ()).throw(AssertionError("no inbox read"))) == 0
    save_settings({"notifications": {"track_outcomes": True}}, expected_revision=1)
    _first, moved, asked = _check([_mail("Your application", "Unfortunately not.")], [])
    assert moved == 0 and asked == [], "no applied jobs, so Luna is never asked"


def test_an_unreadable_inbox_is_reported(store):
    def broken(*_a):
        raise OSError("down")

    assert outcomes.check(fetch=broken) == 0
    assert "Couldn't read the inbox" in outcomes.status()["error"]
