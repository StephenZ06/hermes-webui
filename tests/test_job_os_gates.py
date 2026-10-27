"""Eligibility and language gates: judged against Settings -> Application
answers, failing closed, and holding a failed job out of the inbox, the match
email and Automate all until you choose to ignore the check."""

from __future__ import annotations

import json
from dataclasses import replace

from api.job_os import analysis, autopilot, checks, llm, notify
from api.job_os.db import connect_job_os
from api.job_os.models import JobStatus
from api.job_os.repository import create_job, get_job, normalize_job_input
from api.job_os.settings import load_settings, save_settings
from tests.test_job_os_tailor import store  # noqa: F401 - shared fixture

PROFILE = "Right to work: Malaysian citizen\nLanguages: English, Malay\nRelocation: no\nBased in: Kuala Lumpur"


def _job(slug, gates=None, score=82):
    job = create_job(replace(normalize_job_input({"title": f"Analyst {slug}", "canonical_url": f"https://jobs.example.test/{slug}"}),
                             description="SQL and Python"), status=JobStatus.SCRAPED)
    conn = connect_job_os()
    conn.execute("UPDATE jobs SET status='analyzed' WHERE id=?", (job.id,))
    conn.commit()
    conn.close()
    if gates is not None:
        conn = connect_job_os()
        conn.execute("INSERT INTO job_analyses (job_id, status, fit_score, verdict, data_json, requested_at, finished_at)"
                     " VALUES (?, 'done', ?, 'good', ?, 1, strftime('%s','now'))",
                     (job.id, score, json.dumps({"summary": "ok", "gates": gates})))
        conn.commit()
        conn.close()
    return job


def test_invalid_or_missing_gates_fail_closed():
    out = analysis._clean({"fit_score": 80, "gates": {"eligibility": "yes", "language": "maybe"}}, PROFILE)
    assert out["gates"]["eligibility"] == "unverified" and out["gates"]["language"] == "flag"
    out = analysis._clean({"fit_score": 80}, PROFILE)
    assert out["gates"]["eligibility"] == "unverified"
    assert out["prompt_version"] == analysis.ANALYSIS_PROMPT_VERSION


def test_a_failed_gate_caps_the_verdict_and_keeps_the_quote():
    out = analysis._clean({"fit_score": 91, "verdict": "strong", "gates": {
        "eligibility": "fail", "eligibility_quote": "Singapore citizens only", "language": "pass"}}, PROFILE)
    assert out["verdict"] == "poor" and out["fit_score"] == 91
    assert out["gates"]["eligibility_quote"] == "Singapore citizens only"


def test_without_application_answers_the_gates_are_unverified():
    empty = "Right to work: not stated\nLanguages: not stated\nRelocation: not stated\nBased in: not stated"
    out = analysis._clean({"fit_score": 70, "gates": {"eligibility": "fail", "language": "fail"}}, empty)
    assert out["gates"]["eligibility"] == "unverified" and out["gates"]["language"] == "unverified"
    assert out["gates"]["profile_missing"] == ["Right to work", "Languages"]
    assert out["verdict"] != "poor"


def test_the_prompt_carries_the_application_answers(store, monkeypatch):  # noqa: F811
    save_settings({"apply": {"work_authorization": "Malaysian citizen", "languages": "English, Malay"}},
                  expected_revision=load_settings()["revision"])
    assert "Right to work: Malaysian citizen" in analysis.profile_block()
    seen = []

    def fake(**kw):
        seen.append(kw["user"])
        return json.dumps({"fit_score": 80, "gates": {"eligibility": "fail", "eligibility_quote": "PR only", "language": "pass"}})
    monkeypatch.setattr(llm, "_transport", fake)
    monkeypatch.setattr(analysis, "_after", lambda *a: None)
    job = _job("prompt")
    analysis.request_analysis([job.id], start_worker=False)
    stored = analysis.analyze_one(job.id)
    assert "<<<PROFILE\nRight to work: Malaysian citizen" in seen[0]
    assert stored["gates"]["eligibility"] == "fail" and stored["verdict"] == "poor"


def test_a_failed_gate_holds_the_job_until_the_check_is_ignored(store):  # noqa: F811
    held = _job("held", {"eligibility": "fail", "eligibility_quote": "Citizens only", "language": "pass"})
    fine = _job("fine", {"eligibility": "pass", "language": "pass"})
    shown = {c["key"]: c for c in checks.job_checks(get_job(held.id), analysis.get_analysis(held.id))}
    assert shown["eligibility"]["tone"] == "danger" and shown["eligibility"]["quotes"] == ["Citizens only"]
    assert checks.job_checks(get_job(fine.id), analysis.get_analysis(fine.id)) == []

    # Automate all and the good-match inbox leave it out...
    out = autopilot.automate([held.id], start_workers=False)
    assert out["skipped"] == 1 and get_job(held.id).status == JobStatus.ANALYZED
    ids = [m["id"] for m in notify.pending_matches(load_settings())]
    assert fine.id in ids and held.id not in ids

    # ...until you ignore the check on that job.
    checks.set_override(held.id, "eligibility", True)
    assert checks.held_by(get_job(held.id), analysis.get_analysis(held.id)) == []
    assert held.id in [m["id"] for m in notify.pending_matches(load_settings())]
    shown = {c["key"]: c for c in checks.job_checks(get_job(held.id), analysis.get_analysis(held.id))}
    assert shown["eligibility"]["tone"] == "muted"
    checks.set_override(held.id, "eligibility", False)
    assert checks.held_by(get_job(held.id), analysis.get_analysis(held.id)) == ["eligibility"]


def test_an_analysis_arriving_for_a_held_job_does_not_tailor_it(store):  # noqa: F811
    job = _job("later", {"eligibility": "pass", "language": "fail"})
    autopilot._remember(job.id, 1)
    assert autopilot.after_analysis(job.id, 82, start_worker=False) is False
    assert get_job(job.id).status == JobStatus.ANALYZED


def test_old_analyses_without_gates_show_no_gate_checks(store):  # noqa: F811
    job = _job("old")
    conn = connect_job_os()
    conn.execute("INSERT INTO job_analyses (job_id, status, fit_score, verdict, data_json, requested_at) VALUES (?, 'done', 70, 'good', '{}', 1)", (job.id,))
    conn.commit()
    conn.close()
    assert checks.job_checks(get_job(job.id), analysis.get_analysis(job.id)) == []
    assert checks.held_by(get_job(job.id), analysis.get_analysis(job.id)) == []
