"""Behavioral tests for the server-owned Job OS lifecycle."""

from pathlib import Path

import pytest

from api import profiles
from api.job_os.db import connect_job_os
from api.job_os.lifecycle import ConcurrentRevisionError, InvalidJobTransition, transition_job
from api.job_os.models import JobStatus
from api.job_os.repository import create_job, get_job, normalize_job_input


def _use_profile_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(profiles, "get_active_profile_name", lambda: "research")
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path / "research")


def _new_job(tmp_path, monkeypatch):
    _use_profile_home(monkeypatch, tmp_path)
    return create_job(
        normalize_job_input(
            {"title": "Security Engineer", "canonical_url": "https://jobs.example.test/security"}
        )
    )


def test_transition_job_allows_the_initial_canonical_path(tmp_path, monkeypatch):
    """The first discovery path is server-controlled and revisioned."""
    job = _new_job(tmp_path, monkeypatch)

    scraped = transition_job(job.id, JobStatus.SCRAPED, expected_revision=job.revision)
    analyzed = transition_job(
        scraped.id, JobStatus.ANALYZED, expected_revision=scraped.revision
    )

    assert scraped.status is JobStatus.SCRAPED
    assert analyzed.status is JobStatus.ANALYZED
    assert analyzed.revision == 2


def test_transition_job_rejects_invalid_target_without_mutating_state_or_events(tmp_path, monkeypatch):
    """An invalid jump cannot change the job or append misleading activity."""
    job = _new_job(tmp_path, monkeypatch)
    connection = connect_job_os()
    try:
        before_events = connection.execute("SELECT COUNT(*) FROM job_events").fetchone()[0]
    finally:
        connection.close()

    with pytest.raises(InvalidJobTransition):
        transition_job(job.id, JobStatus.SUBMITTED, expected_revision=job.revision)

    unchanged = get_job(job.id)
    connection = connect_job_os()
    try:
        after_events = connection.execute("SELECT COUNT(*) FROM job_events").fetchone()[0]
    finally:
        connection.close()

    assert unchanged.status is JobStatus.DISCOVERED
    assert unchanged.revision == job.revision
    assert after_events == before_events


def test_transition_job_rejects_a_stale_revision_without_mutating_state(tmp_path, monkeypatch):
    """A stale browser action cannot overwrite a newer lifecycle decision."""
    job = _new_job(tmp_path, monkeypatch)
    current = transition_job(job.id, JobStatus.SCRAPED, expected_revision=job.revision)

    with pytest.raises(ConcurrentRevisionError):
        transition_job(job.id, JobStatus.ANALYZED, expected_revision=job.revision)

    assert get_job(job.id).revision == current.revision
