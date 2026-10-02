"""HTTP translation for the native Job OS API prefix."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, unquote

from api.helpers import bad, j
from api.job_os.dashboard import build_dashboard
from api.job_os.db import job_os_capability
from api.job_os.lifecycle import ConcurrentRevisionError, InvalidJobTransition, transition_job
from api.job_os.models import DuplicateJobError, JobFilters, JobRecord, JobStatus, JobValidationError
from api.job_os.repository import create_job, get_job, list_jobs, normalize_job_input

_PREFIX = "/api/job-os"


def _job_payload(job: JobRecord) -> dict[str, Any]:
    return {
        "id": job.id,
        "canonical_url": job.canonical_url,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "source": job.source,
        "source_id": job.source_id,
        "status": job.status.value,
        "revision": job.revision,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def _error(handler, message: str, status: int) -> bool:
    bad(handler, message, status)
    return True


def _job_id_from_path(path: str) -> str | None:
    if not path.startswith(f"{_PREFIX}/jobs/"):
        return None
    job_id = unquote(path[len(f"{_PREFIX}/jobs/") :]).strip("/")
    return job_id or None


def handle_job_os_get(handler, parsed) -> bool:
    """Handle Job OS read endpoints or return False for an unknown path."""
    if parsed.path == f"{_PREFIX}/capability":
        j(handler, job_os_capability())
        return True
    if parsed.path == f"{_PREFIX}/dashboard":
        j(handler, build_dashboard())
        return True
    if parsed.path == f"{_PREFIX}/jobs":
        query = parse_qs(parsed.query or "")
        raw_status = str(query.get("status", [""])[0] or "").strip()
        raw_source = str(query.get("source", [""])[0] or "").strip() or None
        try:
            status = JobStatus(raw_status) if raw_status else None
        except ValueError:
            return _error(handler, "Unknown job status", 400)
        jobs = list_jobs(JobFilters(status=status, source=raw_source))
        j(handler, {"jobs": [_job_payload(job) for job in jobs]})
        return True
    job_id = _job_id_from_path(parsed.path)
    if job_id is not None:
        job = get_job(job_id)
        if job is None:
            return _error(handler, "Job not found", 404)
        j(handler, {"job": _job_payload(job)})
        return True
    return False


def handle_job_os_post(handler, parsed, body) -> bool:
    """Handle Job OS creation endpoints or return False for an unknown path."""
    if parsed.path != f"{_PREFIX}/jobs":
        return False
    if not isinstance(body, dict):
        return _error(handler, "JSON object body is required", 400)
    try:
        job = normalize_job_input(body)
        created = create_job(job, idempotency_key=body.get("idempotency_key"))
    except JobValidationError as error:
        return _error(handler, str(error), 400)
    except DuplicateJobError as error:
        payload = {"error": str(error)}
        if error.existing_id is not None:
            payload["existing_id"] = error.existing_id
        j(handler, payload, status=409)
        return True
    j(handler, {"job": _job_payload(created)}, status=201)
    return True


def handle_job_os_patch(handler, parsed, body) -> bool:
    """Handle revisioned lifecycle updates or return False for an unknown path."""
    job_id = _job_id_from_path(parsed.path)
    if job_id is None:
        return False
    if not isinstance(body, dict):
        return _error(handler, "JSON object body is required", 400)
    raw_status = body.get("status")
    expected_revision = body.get("expected_revision")
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        return _error(handler, "expected_revision must be an integer", 400)
    try:
        target = JobStatus(str(raw_status or ""))
    except ValueError:
        return _error(handler, "Unknown job status", 400)
    try:
        updated = transition_job(job_id, target, expected_revision=expected_revision)
    except KeyError:
        return _error(handler, "Job not found", 404)
    except ConcurrentRevisionError as error:
        return _error(handler, str(error), 409)
    except InvalidJobTransition as error:
        return _error(handler, str(error), 400)
    j(handler, {"job": _job_payload(updated)})
    return True
