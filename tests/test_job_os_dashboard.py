"""Tests for profile-owned Job OS dashboard projections."""

from pathlib import Path

from api import profiles
from api.job_os.dashboard import build_dashboard
from api.job_os.lifecycle import transition_job
from api.job_os.models import JobStatus
from api.job_os.repository import create_job, normalize_job_input


def test_dashboard_counts_only_canonical_records_from_the_active_profile(tmp_path, monkeypatch):
    """Dashboard totals do not inherit jobs from a profile that is no longer active."""
    homes = {"research": tmp_path / "research", "applications": tmp_path / "applications"}
    active = {"name": "research"}
    monkeypatch.setattr(profiles, "get_active_profile_name", lambda: active["name"])
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: homes[active["name"]])
    # Per-profile stores are the isolated-deployment contract; Job OS is
    # otherwise global (see test_job_os_storage.py).
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: True)

    first = create_job(
        normalize_job_input({"title": "Backend", "canonical_url": "https://jobs.example.test/backend"})
    )
    active_job = create_job(
        normalize_job_input({"title": "Security", "canonical_url": "https://jobs.example.test/security"})
    )
    scraped = transition_job(active_job.id, JobStatus.SCRAPED, expected_revision=0)
    analyzed = transition_job(active_job.id, JobStatus.ANALYZED, expected_revision=scraped.revision)
    shortlisted = transition_job(
        active_job.id, JobStatus.SHORTLISTED, expected_revision=analyzed.revision
    )
    transition_job(active_job.id, JobStatus.TAILORING, expected_revision=shortlisted.revision)

    research_dashboard = build_dashboard()
    assert research_dashboard["total_jobs"] == 2
    assert research_dashboard["by_status"]["discovered"] == 1
    assert research_dashboard["active_work"] == 1

    active["name"] = "applications"
    other_dashboard = build_dashboard()
    assert other_dashboard["total_jobs"] == 0
    assert other_dashboard["by_status"] == {}
    assert first.id != active_job.id
