"""Skill-gap report: gaps added up across analysed jobs, near-identical
wording merged, the last five kept, and what changed since the last one."""

from __future__ import annotations

import json

import pytest

from api.job_os import llm, skill_gaps
from api.job_os.db import connect_job_os
from tests.test_job_os_gates import _job
from tests.test_job_os_tailor import store  # noqa: F401 - shared fixture


def _analysed(slug, gaps, must=(), fit=70):
    job = _job(slug)
    conn = connect_job_os()
    conn.execute("INSERT INTO job_analyses (job_id, status, fit_score, verdict, data_json, requested_at, finished_at)"
                 " VALUES (?, 'done', ?, 'good', ?, 1, strftime('%s','now'))",
                 (job.id, fit, json.dumps({"gaps": list(gaps), "must_haves": list(must)})))
    conn.commit()
    conn.close()


def test_near_identical_gaps_merge_and_count_once_per_job(store):  # noqa: F811
    _analysed("a", ["Kubernetes", "No Power BI experience"], ["Kubernetes in production"])
    _analysed("b", ["Kubernetes in production", "Power BI dashboards", "Power BI"], ["SQL"])
    _analysed("c", ["Tableau"], fit=30)
    out = skill_gaps.aggregate()
    assert out["jobs"] == 3
    counts = {g["label"]: (g["gap"], g["asked"]) for g in out["gaps"]}
    assert counts["Kubernetes"] == (2, 1)
    assert counts["No Power BI experience"] == (2, 0)  # counted once in job b despite two wordings
    assert skill_gaps.aggregate(good_only=True)["jobs"] == 2


def test_the_empty_state_says_what_to_do(store):  # noqa: F811
    assert skill_gaps.aggregate() == {"jobs": 0, "gaps": []}
    with pytest.raises(skill_gaps.SkillGapError):
        skill_gaps.build()


def test_reports_are_kept_and_compared(store, monkeypatch):  # noqa: F811
    monkeypatch.setattr(llm, "_transport", lambda **kw: json.dumps({
        "themes": [{"name": "Cloud", "gaps": ["Kubernetes", "made up"], "why": "Asked often"}],
        "plan": [{"step": "Run a cluster", "detail": "Use kind locally, see https://example.test"}]}))
    _analysed("a", ["Kubernetes", "Go"])
    first = skill_gaps.build()
    assert first["themes"][0]["gaps"] == ["Kubernetes"]  # only labels that exist
    assert "https://" not in first["plan"][0]["detail"] and first["since_last"] is None
    conn = connect_job_os()
    conn.execute("DELETE FROM job_analyses")
    conn.commit()
    conn.close()
    _analysed("b", ["Kubernetes", "Terraform"])
    second = skill_gaps.build()
    assert second["since_last"] == {"new": ["Terraform"], "closed": ["Go"]}
    for _ in range(5):
        skill_gaps.build()
    assert len(skill_gaps.load()["reports"]) == skill_gaps.KEEP
