"""Validated, serializable Job OS domain records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class JobValidationError(ValueError):
    """Raised when an untrusted job payload cannot become a canonical record."""


class DuplicateJobError(ValueError):
    """Raised when a canonical URL or source identifier already exists."""

    def __init__(self, message: str, existing_id: str | None = None) -> None:
        super().__init__(message)
        self.existing_id = existing_id


class JobStatus(str, Enum):
    DISCOVERED = "discovered"
    SCRAPED = "scraped"
    ANALYZED = "analyzed"
    SHORTLISTED = "shortlisted"
    SKIPPED = "skipped"
    EXPIRED = "expired"
    TAILORING = "tailoring"
    RESUME_READY = "resume_ready"
    APPLICATION_READY = "application_ready"
    AWAITING_APPROVAL = "awaiting_approval"
    APPLYING = "applying"
    SUBMITTED = "submitted"
    SCREENING = "screening"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    CLOSED = "closed"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    NO_RESPONSE = "no_response"
    OFFER_ACCEPTED = "offer_accepted"
    OFFER_DECLINED = "offer_declined"


@dataclass(frozen=True)
class JobInput:
    title: str
    canonical_url: str
    company: str = ""
    location: str = ""
    source: str = "manual"
    source_id: str | None = None
    # Posting details (filled by Scout from the page's structured data).
    description: str = ""
    salary_text: str = ""
    employment_type: str = ""
    workplace: str = ""  # "remote", "hybrid", "onsite" or ""
    posted_at: str = ""
    search_id: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class JobFilters:
    status: JobStatus | None = None
    source: str | None = None


@dataclass(frozen=True)
class JobRecord:
    id: str
    canonical_url: str
    title: str
    company: str
    location: str
    source: str
    source_id: str | None
    status: JobStatus
    revision: int
    created_at: int
    updated_at: int
    description: str = ""
    salary_text: str = ""
    employment_type: str = ""
    workplace: str = ""
    posted_at: str = ""
    search_id: str | None = None
    run_id: str | None = None
