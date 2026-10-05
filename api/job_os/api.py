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
from api.job_os.settings import SettingsConflict, SettingsError, load_settings, save_settings

_PREFIX = "/api/job-os"


def _job_payload(job: JobRecord, *, detail: bool = False) -> dict[str, Any]:
    payload = {
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
        "salary_text": job.salary_text,
        "employment_type": job.employment_type,
        "workplace": job.workplace,
        "posted_at": job.posted_at,
        "search_id": job.search_id,
        "run_id": job.run_id,
        "has_description": bool(job.description),
    }
    if detail:
        payload["description"] = job.description
    return payload


def _error(handler, message: str, status: int) -> bool:
    bad(handler, message, status)
    return True


def _job_id_from_path(path: str) -> str | None:
    if not path.startswith(f"{_PREFIX}/jobs/"):
        return None
    job_id = unquote(path[len(f"{_PREFIX}/jobs/") :]).strip("/")
    return job_id or None


def _firecrawl_health(settings: dict) -> dict:
    from api.job_os.firecrawl import FirecrawlClient, resolve_firecrawl_config

    override = (settings.get("firecrawl") or {}).get("api_url") or None
    return FirecrawlClient(resolve_firecrawl_config(override)).health()


def _settings_status(settings: dict) -> dict:
    """Live service status for the Settings page: presence booleans, never values."""
    from api.job_os import gmail

    return {"firecrawl": _firecrawl_health(settings), "gmail": gmail.status()}


def _scout_searches_payload() -> dict:
    from api.job_os import scheduler, scout

    settings = load_settings()
    searches = scout.list_searches()
    for search in searches:
        search["next_run_at"] = scheduler.next_run_at(search, settings)
    from api.job_os.search_provider import search_provider_name

    return {"searches": searches, "search_provider": search_provider_name(),
            "schedule": {"enabled": bool(settings["scout"]["enabled"]), "hours": settings["scout"]["schedule_hours"]}}


def _scout_get(handler, parsed) -> bool:
    from api.job_os import scout

    path = parsed.path
    if path == f"{_PREFIX}/searches":
        j(handler, _scout_searches_payload())
        return True
    if path == f"{_PREFIX}/runs":
        query = parse_qs(parsed.query or "")
        search_id = str(query.get("search_id", [""])[0] or "") or None
        try:
            limit = max(1, min(int(query.get("limit", ["20"])[0]), 100))
        except ValueError:
            limit = 20
        j(handler, {"runs": scout.list_runs(search_id=search_id, limit=limit)})
        return True
    if path.startswith(f"{_PREFIX}/runs/"):
        run = scout.get_run(unquote(path[len(f"{_PREFIX}/runs/"):]).strip("/"))
        if run is None:
            return _error(handler, "Run not found", 404)
        j(handler, {"run": run})
        return True
    return False


def _scout_post(handler, path: str, body: dict) -> bool | None:
    """Scout writes; None when ``path`` is not a Scout route."""
    from api.job_os import scout

    try:
        if path == f"{_PREFIX}/searches":
            j(handler, {"search": scout.create_search(body.get("search") or {})}, status=201)
            return True
        if path.startswith(f"{_PREFIX}/searches/"):
            rest = unquote(path[len(f"{_PREFIX}/searches/"):]).strip("/").split("/")
            search_id, action = rest[0], (rest[1] if len(rest) > 1 else "")
            if action == "":
                j(handler, {"search": scout.update_search(search_id, body.get("search") or {},
                                                          expected_revision=body.get("expected_revision"))})
            elif action == "delete":
                if not scout.delete_search(search_id):
                    raise KeyError(search_id)
                j(handler, {"ok": True})
            elif action == "run":
                j(handler, {"run": scout.start_discovery(search_id, idempotency_key=body.get("idempotency_key"))})
            else:
                return None
            return True
        if path.startswith(f"{_PREFIX}/runs/") and path.endswith("/cancel"):
            run_id = unquote(path[len(f"{_PREFIX}/runs/"):-len("/cancel")]).strip("/")
            j(handler, {"run": scout.cancel_run(run_id)})
            return True
    except KeyError:
        return _error(handler, "Not found", 404)
    except scout.ScoutConflict as error:
        return _error(handler, str(error), 409)
    except scout.ScoutError as error:
        return _error(handler, str(error), 400)
    return None


def handle_job_os_get(handler, parsed) -> bool:
    """Handle Job OS read endpoints or return False for an unknown path."""
    if _scout_get(handler, parsed):
        return True
    if parsed.path == f"{_PREFIX}/settings":
        settings = load_settings()
        j(handler, {"settings": settings, "status": _settings_status(settings)})
        return True
    if parsed.path == f"{_PREFIX}/firecrawl/health":
        j(handler, {"firecrawl": _firecrawl_health(load_settings())})
        return True
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
        j(handler, {"job": _job_payload(job, detail=True)})
        return True
    return False


def _handle_gmail_post(handler, path: str, body: dict) -> bool:
    from api import mailer
    from api.job_os import gmail

    try:
        if path == f"{_PREFIX}/gmail":
            result = gmail.connect(body.get("address"), body.get("app_password"), verify=gmail.verify_login)
            j(handler, {"gmail": result})
        elif path == f"{_PREFIX}/gmail/disconnect":
            j(handler, {"gmail": gmail.disconnect()})
        else:
            context = str(body.get("context") or gmail.CONTEXT)
            sent_to = gmail.send_test(body.get("to") or load_settings()["notifications"]["to_address"], context=context)
            j(handler, {"sent_to": sent_to, "sender_name": mailer.sender_name(context)})
    except gmail.GmailError as error:
        return _error(handler, str(error), 400)
    except ValueError as error:  # unknown sender context
        return _error(handler, str(error), 400)
    return True


def handle_job_os_post(handler, parsed, body) -> bool:
    """Handle Job OS creation endpoints or return False for an unknown path."""
    if parsed.path.startswith((f"{_PREFIX}/searches", f"{_PREFIX}/runs/")):
        handled = _scout_post(handler, parsed.path, body if isinstance(body, dict) else {})
        if handled is not None:
            return handled
    if parsed.path in {f"{_PREFIX}/gmail", f"{_PREFIX}/gmail/disconnect", f"{_PREFIX}/gmail/test"}:
        return _handle_gmail_post(handler, parsed.path, body if isinstance(body, dict) else {})
    if parsed.path == f"{_PREFIX}/settings":
        if not isinstance(body, dict):
            return _error(handler, "JSON object body is required", 400)
        try:
            saved = save_settings(body.get("settings"), expected_revision=body.get("expected_revision"))
        except SettingsConflict as error:
            return _error(handler, str(error), 409)
        except SettingsError as error:
            return _error(handler, str(error), 400)
        j(handler, {"settings": saved, "status": _settings_status(saved)})
        return True
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
