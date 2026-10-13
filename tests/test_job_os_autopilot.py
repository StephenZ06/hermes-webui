"""Automate all tailors every job in the Match check: scored jobs now,
unscored ones as soon as their score comes back (whatever it is, even when
scoring fails). Jobs without a description or already past tailoring are
left alone."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from api.job_os import analysis, applications, autopilot, llm, tailor
from api.job_os.db import connect_job_os
from api.job_os.models import JobStatus
from api.job_os.repository import create_job, get_job, normalize_job_input
from tests.test_job_os_tailor import store  # noqa: F401 - shared fixture


def _job(slug, *, description="SOC monitoring with a SIEM", status=JobStatus.SCRAPED, score=None):
    job = create_job(replace(normalize_job_input({"title": f"Analyst {slug}", "canonical_url": f"https://jobs.example.test/{slug}"}),
                             description=description), status=status)
    if score is not None:
        conn = connect_job_os()
        conn.execute("INSERT INTO job_analyses (job_id, status, fit_score, verdict, data_json, requested_at, finished_at)"
                     " VALUES (?, 'done', ?, 'good', '{}', 1, 1)", (job.id, score))
        conn.commit()
        conn.close()
    return job


def test_automate_all_tailors_every_job_whatever_its_score(store, monkeypatch):  # noqa: F811
    good, low, fresh, bare = _job("good", score=72), _job("low", score=31), _job("fresh"), _job("bare", description="")
    applied = _job("applied", score=90)
    applications.mark_applied(applied.id)
    out = autopilot.automate([good.id, low.id, fresh.id, bare.id, applied.id, "missing"], start_workers=False)
    assert out == {"tailoring": 2, "scoring": 1, "skipped": 3}
    assert get_job(good.id).status == JobStatus.TAILORING
    assert get_job(low.id).status == JobStatus.TAILORING, "a low score is no longer a reason to skip"
    assert analysis.get_analysis(fresh.id)["status"] == "pending" and autopilot.waiting() == {fresh.id}

    # The score comes back (low, even): the job is tailored, and no longer waiting.
    monkeypatch.setattr(llm, "_transport", lambda **kw: json.dumps({"fit_score": 22, "verdict": "poor", "summary": "ok"}))
    monkeypatch.setattr(tailor, "ensure_worker", lambda: None)
    analysis.analyze_one(fresh.id)
    assert get_job(fresh.id).status == JobStatus.TAILORING and autopilot.waiting() == set()


def test_a_failed_score_is_still_tailored(store, monkeypatch):  # noqa: F811
    broken = _job("broken")
    autopilot.automate([broken.id], start_workers=False)
    monkeypatch.setattr(tailor, "ensure_worker", lambda: None)
    monkeypatch.setattr(llm, "_transport", lambda **kw: "not json")
    analysis.analyze_one(broken.id)
    assert get_job(broken.id).status == JobStatus.TAILORING and autopilot.waiting() == set()
    # An analysis nobody was waiting on tailors nothing.
    other = _job("other", score=80)
    assert autopilot.after_analysis(other.id, 99, start_worker=False) is False


def test_automate_all_needs_a_resume(tmp_path, monkeypatch):
    from api import profiles

    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    with pytest.raises(autopilot.AutopilotError):
        autopilot.automate(["x"])
