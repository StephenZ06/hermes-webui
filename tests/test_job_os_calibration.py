"""Calibration from outcomes: offered from 3 outcomes, bounded, approved
before anything changes, undoable, and used by new analyses."""

from __future__ import annotations

import json

import pytest

from api.job_os import analysis, calibration, llm
from api.job_os.db import connect_job_os
from tests.test_job_os_gates import PROFILE, _job
from tests.test_job_os_tailor import store  # noqa: F401 - shared fixture


def _resolved(slug, status, dims):
    job = _job(slug, {"eligibility": "pass", "language": "pass"})
    conn = connect_job_os()
    conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, job.id))
    conn.execute("UPDATE job_analyses SET data_json=? WHERE job_id=?", (json.dumps({"dimensions": dims}), job.id))
    conn.commit()
    conn.close()
    return job


DIMS = {"skills": 80, "experience": 60, "culture": 50, "career": 70, "location": "pass"}


def test_no_offer_below_three_outcomes(store):  # noqa: F811
    _resolved("a", "rejected", DIMS)
    _resolved("b", "interviewing", DIMS)
    assert calibration.status()["offer"] is False
    with pytest.raises(calibration.CalibrationError):
        calibration.request_proposal(run_async=False)
    _resolved("c", "no_response", DIMS)
    assert calibration.status()["offer"] is True


def test_weight_changes_are_bounded():
    current = calibration.DEFAULT_WEIGHTS
    out = calibration.bounded({"skills": 90, "experience": 0, "culture": "x", "career": 31}, current)
    assert out == {"skills": 40, "experience": 15, "culture": 15, "career": 31}


def test_approve_and_undo_round_trip_and_new_analyses_use_it(store, monkeypatch):  # noqa: F811
    for slug, status in (("r1", "rejected"), ("i1", "interviewing"), ("n1", "no_response")):
        _resolved(slug, status, DIMS)
    seen = []

    def fake(**kw):
        seen.append(kw["user"])
        return json.dumps({"weights": {"skills": 45, "experience": 20, "culture": 10, "career": 30},
                           "guidance": "Weigh skills more.", "patterns": ["Bank roles went quiet"]})
    monkeypatch.setattr(llm, "_transport", fake)
    state = calibration.request_proposal(run_async=False)
    assert "-> rejected" in seen[0] and "-> interview" in seen[0]
    assert state["proposal"]["weights"] == {"skills": 40, "experience": 20, "culture": 10, "career": 30}
    assert calibration.weights() == calibration.DEFAULT_WEIGHTS  # nothing changes before you accept

    state = calibration.accept()
    assert state["current"]["version"] == 1 and calibration.weights()["skills"] == 40
    assert analysis._clean({"fit_score": 1, "dimensions": {"skills": 100, "experience": 0, "career": 0, "culture": 0}}, PROFILE)["fit_score"] == 40
    assert "Weigh skills more." in analysis._prompt(_job("p2"), "resume", PROFILE)

    state = calibration.undo()
    assert state["current"] is None and calibration.weights() == calibration.DEFAULT_WEIGHTS
    assert state["can_undo"] is False


def test_a_failed_proposal_is_reported_and_clears_running(store, monkeypatch):  # noqa: F811
    for slug in ("f1", "f2", "f3"):
        _resolved(slug, "rejected", DIMS)
    monkeypatch.setattr(llm, "_transport", lambda **kw: "nope")
    state = calibration.request_proposal(run_async=False)
    assert calibration.status()["running"] is False and calibration.status()["error"]
    assert state is not None
