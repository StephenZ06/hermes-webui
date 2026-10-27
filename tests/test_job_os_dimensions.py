"""Dimension scores: the fit score is their weighted average, a location
fail holds the job like a failed gate, and old analyses still render."""

from __future__ import annotations

import json

from api.job_os import analysis, autopilot, calibration, checks, notify
from api.job_os.db import connect_job_os
from api.job_os.repository import get_job
from api.job_os.settings import load_settings
from tests.test_job_os_gates import PROFILE, _job
from tests.test_job_os_tailor import store  # noqa: F401 - shared fixture


def test_the_weighted_score_shares_out_a_missing_culture_weight():
    w = calibration.DEFAULT_WEIGHTS
    assert calibration.weighted_score({"skills": 80, "experience": 60, "culture": 100, "career": 40}, w) == 66
    # Without culture its 15 is shared over the other 85 points: (80*30 + 60*25 + 40*30) / 85.
    assert calibration.weighted_score({"skills": 80, "experience": 60, "culture": None, "career": 40}, w) == 60
    assert calibration.weighted_score({"skills": 80, "experience": None, "culture": 50, "career": 40}, w) is None


def test_dimensions_set_the_score_and_band():
    out = analysis._clean({"fit_score": 95, "verdict": "strong", "dimensions": {
        "skills": 50, "experience": 50, "career": 50, "culture": None, "location": "pass"}}, PROFILE)
    assert out["fit_score"] == 50 and out["verdict"] == "stretch"
    assert out["dimensions"]["culture"] is None and out["dimensions"]["location"] == "pass"


def test_unusable_dimensions_keep_the_models_score():
    out = analysis._clean({"fit_score": 77, "dimensions": {"skills": "lots"}}, PROFILE)
    assert out["fit_score"] == 77 and out["dimensions"] is None
    out = analysis._clean({"fit_score": 77, "dimensions": {"skills": 70, "experience": 70, "career": 70, "location": "?"}}, PROFILE)
    assert out["dimensions"]["location"] == "flag"  # unknown is never a pass


def test_a_location_fail_holds_the_job(store):  # noqa: F811
    job = _job("far", {"eligibility": "pass", "language": "pass"})
    conn = connect_job_os()
    conn.execute("UPDATE job_analyses SET data_json=? WHERE job_id=?", (json.dumps({"gates": {"eligibility": "pass", "language": "pass"},
                 "dimensions": {"skills": 90, "experience": 90, "career": 90, "culture": 90, "location": "fail",
                                "location_quote": "On site in Doha"}}), job.id))
    conn.commit()
    conn.close()
    a = analysis.get_analysis(job.id)
    assert checks.held_by(get_job(job.id), a) == ["location"]
    shown = {c["key"]: c for c in checks.job_checks(get_job(job.id), a)}
    assert shown["location"]["tone"] == "danger" and shown["location"]["quotes"] == ["On site in Doha"]
    assert job.id not in [m["id"] for m in notify.pending_matches(load_settings())]
    assert autopilot.automate([job.id], start_workers=False)["skipped"] == 1
    checks.set_override(job.id, "location", True)
    assert checks.held_by(get_job(job.id), a) == []


def test_calibrated_weights_and_guidance_are_used(store, monkeypatch):  # noqa: F811
    calibration._path().write_text(json.dumps({"current": {"weights": {"skills": 70, "experience": 10, "culture": 10, "career": 10},
                                                           "guidance": "Bank analyst roles went quiet."}}))
    assert calibration.weights()["skills"] == 70
    out = analysis._clean({"fit_score": 10, "dimensions": {"skills": 100, "experience": 0, "career": 0, "culture": 0}}, PROFILE)
    assert out["fit_score"] == 70
    assert analysis._prompt(_job("p"), "resume", PROFILE).startswith("Calibration note from this candidate's past outcomes")
