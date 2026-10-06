"""Luna interview prep: only for interview stages, grounded output, failure is reported."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from api import profiles
from api.job_os import interview, llm, resume
from api.job_os.lifecycle import transition_job
from api.job_os.models import JobStatus
from api.job_os.repository import create_job, normalize_job_input

RESUME = "Jane Doe\nBackend engineer. Built Python payment services at Acme for 5 years.\n" * 3
PREP = {"questions": [{"question": "Tell us about a payments system you built", "why": "Domain depth",
                       "outline": "Acme payment services in Python", "supported": True},
                      {"question": "How have you used Kubernetes?", "why": "Infra", "outline": "Review K8s basics", "supported": False}],
        "stories": [{"title": "Payments migration", "situation": "Legacy", "action": "Rewrote", "result": "Faster", "use_for": "Q1"}],
        "ask_them": ["What does on-call look like?"], "research": ["Their API docs"], "watch_outs": ["No Kubernetes"]}


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    resume.save_resume(filename="cv.md", text=RESUME)
    seen = []
    monkeypatch.setattr(llm, "_transport", lambda **kw: seen.append(kw) or json.dumps(PREP))
    return seen


def _job_at(status):
    job = create_job(replace(normalize_job_input({"title": "Backend Engineer", "company": "Acme", "canonical_url": f"https://jobs.example.test/{status}"}),
                             description="Python, payments, Kubernetes."), status=JobStatus.SCRAPED)
    for target in (JobStatus.ANALYZED, JobStatus.SHORTLISTED, JobStatus.TAILORING, JobStatus.RESUME_READY, JobStatus.APPLICATION_READY,
                   JobStatus.AWAITING_APPROVAL, JobStatus.APPLYING, JobStatus.SUBMITTED, JobStatus.SCREENING, JobStatus.INTERVIEWING):
        if job.status.value == status:
            break
        job = transition_job(job.id, target, expected_revision=job.revision)
    return job


def test_prep_only_for_interview_stages(store):
    with pytest.raises(interview.InterviewError):
        interview.request_prep(_job_at("submitted").id, start_worker=False)
    assert interview.request_prep(_job_at("interviewing").id, start_worker=False)["status"] == "pending"


def test_prepare_one_stores_grounded_prep_and_markdown(store):
    job = _job_at("screening")
    interview.request_prep(job.id, start_worker=False)
    prep = interview.prepare_one(job.id)
    assert prep["status"] == "done" and len(prep["questions"]) == 2
    assert prep["questions"][1]["supported"] is False
    assert "**Prepare:** Review K8s basics" in prep["markdown"] and "## Questions to ask them" in prep["markdown"]
    assert "untrusted data" in store[0]["system"] and "<<<POSTING" in store[0]["user"]


def test_unusable_model_output_is_a_failure_not_a_blank_prep(store, monkeypatch):
    monkeypatch.setattr(llm, "_transport", lambda **kw: '{"questions": []}')
    job = _job_at("interviewing")
    interview.request_prep(job.id, start_worker=False)
    prep = interview.prepare_one(job.id)
    assert prep["status"] == "failed" and "no questions" in prep["error"]
