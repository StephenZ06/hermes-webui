"""Second-pass review of tailored documents: on for good matches by default,
a failed review keeps the first draft, and reviewer-found claims hold the
resume for review."""

from __future__ import annotations

import json

from api.job_os import llm, tailor
from api.job_os.db import connect_job_os
from api.job_os.settings import load_settings, save_settings
from tests.test_job_os_tailor import TAILORED, _shortlisted, store  # noqa: F401 - shared fixture

REVISED = TAILORED.replace("Backend engineer.", "Backend engineer building Python services on AWS.")


def _score(job_id, fit):
    conn = connect_job_os()
    conn.execute("INSERT INTO job_analyses (job_id, status, fit_score, verdict, data_json, requested_at) VALUES (?, 'done', ?, 'good', '{}', 1)"
                 " ON CONFLICT(job_id) DO UPDATE SET fit_score=excluded.fit_score", (job_id, fit))
    conn.commit()
    conn.close()


def _transport(calls, review=None, fail_review=False):
    def fake(**kw):
        calls.append(kw["system"][:30])
        if kw["system"] == tailor.REVIEW_SYSTEM:
            if fail_review:
                raise llm.LLMError("down")
            return json.dumps(review or {"edits": ["Name AWS in the summary"], "generic_phrases": ["team player"]})
        if "FIRST DRAFT" in kw["user"]:
            return json.dumps({"resume_markdown": REVISED, "cover_letter": "Dear Acme, revised. " * 10})
        if "career analyst" in kw["system"]:
            return json.dumps({"fit_score": 80})
        return json.dumps({"resume_markdown": TAILORED, "cover_letter": "Dear Acme team, I have 8 years of Python."})
    return fake


def _tailoring_calls(calls):
    return [c for c in calls if not c.startswith("You are a careful career")]


def test_off_keeps_one_tailoring_call(store, monkeypatch):  # noqa: F811
    save_settings({"ai": {"review_tailoring": "off"}}, expected_revision=load_settings()["revision"])
    calls = []
    monkeypatch.setattr(llm, "_transport", _transport(calls))
    job = _shortlisted()
    _score(job.id, 90)
    tailor.request_tailoring(job.id, start_worker=False)
    docs = tailor.tailor_one(job.id)
    assert len(_tailoring_calls(calls)) == 1 and docs["resume"]["notes"]["review"] is None


def test_good_matches_are_reviewed_and_revised_and_poor_ones_are_not(store, monkeypatch):  # noqa: F811
    assert load_settings()["ai"]["review_tailoring"] == "good"
    calls = []
    monkeypatch.setattr(llm, "_transport", _transport(calls))
    job = _shortlisted()
    _score(job.id, 82)
    tailor.request_tailoring(job.id, start_worker=False)
    docs = tailor.tailor_one(job.id)
    assert len(_tailoring_calls(calls)) == 3
    assert docs["resume"]["content"] == REVISED.strip() and docs["resume"]["notes"]["review"]["revised"] is True

    calls.clear()
    _score(job.id, 40)
    tailor.request_tailoring(job.id, start_worker=False)
    tailor.tailor_one(job.id)
    assert len(_tailoring_calls(calls)) == 1


def test_a_failed_review_keeps_the_first_draft(store, monkeypatch):  # noqa: F811
    calls = []
    monkeypatch.setattr(llm, "_transport", _transport(calls, fail_review=True))
    job = _shortlisted()
    _score(job.id, 90)
    tailor.request_tailoring(job.id, start_worker=False)
    docs = tailor.tailor_one(job.id)
    assert docs["resume"]["status"] == "ready" and docs["resume"]["content"] == TAILORED.strip()
    assert "first draft" in docs["resume"]["notes"]["review"]["error"]


def test_reviewer_found_claims_hold_the_resume_for_review(store, monkeypatch):  # noqa: F811
    calls = []
    monkeypatch.setattr(llm, "_transport", _transport(calls, review={"unsupported_claims": ["Led a team of engineers"],
                                                                     "edits": ["Drop the team lead claim"]}))
    job = _shortlisted()
    _score(job.id, 90)
    tailor.request_tailoring(job.id, start_worker=False)
    docs = tailor.tailor_one(job.id)
    assert docs["resume"]["status"] == "needs_review"
    assert docs["resume"]["notes"]["review"]["unsupported_claims"] == ["Led a team of engineers"]
