"""Behavioral tests for canonical Job OS records and deduplication."""

from pathlib import Path

import pytest

from api import profiles
from api.job_os.models import DuplicateJobError, JobFilters, JobValidationError
from api.job_os.repository import create_job, list_jobs, normalize_job_input


def _use_profile_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(profiles, "get_active_profile_name", lambda: "research")
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path / "research")
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path / "research")


def test_normalize_job_input_trims_required_fields_and_accepts_http_urls():
    """A manually supplied job is normalized before the repository opens a write."""
    normalized = normalize_job_input(
        {
            "title": "  Platform Engineer  ",
            "company": "  Acme  ",
            "canonical_url": "https://Example.test/roles/7#overview",
        }
    )

    assert normalized.title == "Platform Engineer"
    assert normalized.company == "Acme"
    assert normalized.canonical_url == "https://example.test/roles/7"

    assert normalize_job_input(
        {"title": "Analyst", "canonical_url": "http://example.test/jobs/9"}
    ).canonical_url == "http://example.test/jobs/9"

    with pytest.raises(JobValidationError):
        normalize_job_input({"title": " ", "canonical_url": "https://example.test/jobs/10"})
    with pytest.raises(JobValidationError):
        normalize_job_input({"title": "Analyst", "canonical_url": "ftp://example.test/jobs/10"})


def test_create_job_deduplicates_canonical_url_and_source_identifier(tmp_path, monkeypatch):
    """Two source representations of the same job cannot create separate records."""
    _use_profile_home(monkeypatch, tmp_path)
    first = create_job(
        normalize_job_input(
            {
                "title": "Research Engineer",
                "canonical_url": "https://jobs.example.test/1",
                "source": "firecrawl",
                "source_id": "source-1",
            }
        )
    )

    with pytest.raises(DuplicateJobError):
        create_job(
            normalize_job_input(
                {
                    "title": "Research Engineer",
                    "canonical_url": "https://jobs.example.test/1?ref=duplicate",
                }
            )
        )
    with pytest.raises(DuplicateJobError):
        create_job(
            normalize_job_input(
                {
                    "title": "Another role",
                    "canonical_url": "https://jobs.example.test/2",
                    "source": "firecrawl",
                    "source_id": "source-1",
                }
            )
        )

    assert first.status.value == "discovered"


def test_create_job_reuses_a_stable_idempotency_key_and_filters_records(tmp_path, monkeypatch):
    """A retried import returns the original record and filters by canonical status."""
    _use_profile_home(monkeypatch, tmp_path)
    job = normalize_job_input(
        {"title": "Data Engineer", "canonical_url": "https://jobs.example.test/data"}
    )

    first = create_job(job, idempotency_key="import:data:1")
    retry = create_job(job, idempotency_key="import:data:1")
    other = create_job(
        normalize_job_input(
            {"title": "Designer", "canonical_url": "https://jobs.example.test/design"}
        )
    )

    assert retry.id == first.id
    assert {record.id for record in list_jobs(JobFilters(status=first.status))} == {first.id, other.id}
