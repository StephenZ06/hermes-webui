"""HTTP translation for the native Job OS API prefix."""

from __future__ import annotations

from pathlib import Path
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


def _job_payload(job: JobRecord, *, detail: bool = False, analyses: dict | None = None) -> dict[str, Any]:
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
        "country": job.country,
        "has_description": bool(job.description),
    }
    if detail:
        from api.job_os.analysis import get_analysis

        from api.job_os.tailor import latest_documents

        payload["description"] = job.description
        payload["analysis"] = get_analysis(job.id)
        payload["documents"] = {kind: {k: d[k] for k in ("id", "status", "error", "revision", "updated_at")}
                                for kind, d in latest_documents(job.id).items()}
        from api.job_os.interview import get_prep

        payload["interview"] = get_prep(job.id)
        from api.job_os.apply_kit import get_kit

        payload["apply_kit"] = get_kit(job.id)
    elif analyses is not None:
        payload["analysis"] = analyses.get(job.id)
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

    from api.job_os import apify

    return {"firecrawl": _firecrawl_health(settings), "gmail": gmail.status(),
            "apify": {**apify.status(), "sites": apify.sites_payload()}}


def _scout_searches_payload() -> dict:
    from api.job_os import automations, scheduler, scout

    settings = load_settings()
    searches = scout.list_searches()
    for search in searches:
        search["next_run_at"] = scheduler.next_run_at(search, settings)
    from api.job_os.search_provider import search_provider_name

    from api.job_os.indeed import POSTED_WITHIN_DAYS, countries_payload

    from api.job_os import apify

    return {"searches": searches, "search_provider": search_provider_name(),
            # Apify runs need no Firecrawl, so the page lets them run without it.
            "apify": {"active": bool(settings["apify"]["enabled"] and apify.token())},
            "countries": countries_payload(), "posted_within_days": list(POSTED_WITHIN_DAYS),
            "sites": apify.sites_payload(),
            "schedule": {"enabled": bool(settings["scout"]["enabled"]), "hours": settings["scout"]["schedule_hours"],
                         "summary": automations._scout_when(settings["scout"])}}


def _document_get(handler, parsed) -> bool:
    from api.job_os import export
    from api.job_os.tailor import get_document

    rest = unquote(parsed.path[len(f"{_PREFIX}/documents/"):]).strip("/").split("/")
    doc = get_document(rest[0])
    if doc is None:
        return _error(handler, "Document not found", 404)
    if len(rest) == 1:
        j(handler, {"document": doc})
        return True
    if rest[1] != "export":
        return _error(handler, "Not found", 404)
    fmt = str(parse_qs(parsed.query or "").get("format", ["md"])[0])
    job = get_job(doc["job_id"])
    base = export.safe_filename(f"{doc['kind'].replace('_', '-')}-{job.company if job else ''}-{job.title if job else ''}")
    title = f"{'Cover letter' if doc['kind'] == 'cover_letter' else 'Resume'} - {job.title if job else ''}"
    # Both documents use the master resume's design; only a resume has its header and sections.
    from api.job_os.resume import style_profile

    style, is_resume = style_profile(), doc["kind"] == "resume"
    if fmt == "docx":
        body, ctype, name = (export.to_docx(doc["content"], style=style, resume=is_resume),
                             "application/vnd.openxmlformats-officedocument.wordprocessingml.document", f"{base}.docx")
    elif fmt in ("html", "pdf"):
        body = export.to_html(doc["content"], title=title, auto_print=fmt == "pdf", style=style, resume=is_resume).encode()
        ctype, name = "text/html; charset=utf-8", None
    elif fmt == "md":
        body, ctype, name = doc["content"].encode(), "text/markdown; charset=utf-8", f"{base}.md"
    else:
        return _error(handler, "Unknown format", 400)
    handler.send_response(200)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Cache-Control", "no-store")
    if name:
        handler.send_header("Content-Disposition", f'attachment; filename="{name}"')
    handler.end_headers()
    handler.wfile.write(body)
    return True


def _resume_file(handler, preview: bool) -> bool:
    """The master resume as uploaded (PDF shown inline, others downloaded), or
    an HTML page of its text in its own design for files a browser can't show."""
    from api.job_os import export
    from api.job_os.resume import load_resume, original_file, style_profile

    meta = load_resume()
    if not meta:
        return _error(handler, "No master resume yet", 404)
    found = original_file()
    if preview:
        body = export.text_page(meta["text"], title=meta["filename"], style=style_profile()).encode()
        ctype, name = "text/html; charset=utf-8", None
    elif found:
        body = found[0].read_bytes()
        kind = found[0].suffix.lower()
        ctype = {".pdf": "application/pdf",
                 ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}.get(kind, "text/plain; charset=utf-8")
        name = None if kind == ".pdf" else export.safe_filename(Path(found[1]).stem) + kind
    else:
        return _error(handler, "The resume was pasted as text; there is no original file.", 404)
    handler.send_response(200)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Cache-Control", "no-store")
    if preview:
        handler.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
    if name:
        handler.send_header("Content-Disposition", f'attachment; filename="{name}"')
    handler.end_headers()
    handler.wfile.write(body)
    return True


def _scout_get(handler, parsed) -> bool:
    from api.job_os import scout

    path = parsed.path
    if path == f"{_PREFIX}/resume":
        from api.job_os.resume import load_resume, original_file, style_profile

        found = original_file()
        meta = load_resume()
        if meta:  # a resume saved before designs were read gets its design now
            meta["style"] = style_profile()
        j(handler, {"resume": meta, "original": found[0].suffix.lstrip(".") if found and meta else None})
        return True
    if path in (f"{_PREFIX}/resume/original", f"{_PREFIX}/resume/preview"):
        return _resume_file(handler, path.endswith("/preview"))
    if path == f"{_PREFIX}/applications":
        from api.job_os import applications

        source = str(parse_qs(parsed.query or "").get("source", [""])[0] or "").strip() or None
        try:
            j(handler, applications.board(source))
        except applications.ApplicationError as error:
            return _error(handler, str(error), 400)
        return True
    if path == f"{_PREFIX}/apify/usage":
        from api.job_os import apify

        settings = load_settings()
        active = bool(settings["apify"]["enabled"] and apify.token())
        # Also carries the page's display choices, read on every refresh.
        j(handler, {"apify": {"active": active, "usage": apify.usage() if apify.token() else None},
                    "display": settings["display"]})
        return True
    if path == f"{_PREFIX}/matches":
        from api.job_os import notify

        j(handler, {"matches": notify.inbox()})
        return True
    if path == f"{_PREFIX}/notifications":
        from api.job_os import notify

        j(handler, {"notifications": notify.status()})
        return True
    if path == f"{_PREFIX}/funnel":
        from api.job_os import applications

        j(handler, {"funnel": applications.funnel()})
        return True
    if path == f"{_PREFIX}/automations":
        from api.job_os import automations

        j(handler, {"automations": automations.summary()})
        return True
    if path.startswith(f"{_PREFIX}/jobs/") and path.endswith("/interview-prep.md"):
        from api.job_os import export
        from api.job_os.interview import get_prep

        job_id = unquote(path[len(f"{_PREFIX}/jobs/"):-len("/interview-prep.md")]).strip("/")
        prep, job = get_prep(job_id), get_job(job_id)
        if not prep or prep["status"] != "done" or job is None:
            return _error(handler, "Not found", 404)
        body = prep["markdown"].encode()
        handler.send_response(200)
        handler.send_header("Content-Type", "text/markdown; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Disposition", f'attachment; filename="{export.safe_filename("interview-prep-" + job.company + "-" + job.title)}.md"')
        handler.end_headers()
        handler.wfile.write(body)
        return True
    if path.startswith(f"{_PREFIX}/jobs/") and path.endswith("/timeline"):
        from api.job_os import applications

        job_id = unquote(path[len(f"{_PREFIX}/jobs/"):-len("/timeline")]).strip("/")
        j(handler, {"timeline": applications.timeline(job_id)})
        return True
    if path == f"{_PREFIX}/documents":
        from api.job_os.tailor import list_tailored

        j(handler, {"documents": list_tailored()})
        return True
    if path.startswith(f"{_PREFIX}/documents/"):
        return _document_get(handler, parsed)
    if path.startswith(f"{_PREFIX}/jobs/") and path.endswith("/documents"):
        from api.job_os.tailor import latest_documents

        job_id = unquote(path[len(f"{_PREFIX}/jobs/"):-len("/documents")]).strip("/")
        j(handler, {"documents": latest_documents(job_id)})
        return True
    if path == f"{_PREFIX}/analysis/queue":
        from api.job_os.analysis import queue_counts

        j(handler, {"queue": queue_counts()})
        return True
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


def _resume_and_analysis_post(handler, path: str, body: dict) -> bool | None:
    import base64
    import binascii

    from api.job_os import analysis, resume, scout

    try:
        if path == f"{_PREFIX}/resume":
            if body.get("content_base64"):
                try:
                    data = base64.b64decode(str(body["content_base64"]), validate=True)
                except (binascii.Error, ValueError):
                    return _error(handler, "The file could not be decoded", 400)
                filename = str(body.get("filename") or "resume")
                text = resume.extract_text(filename, data)
                meta = resume.save_resume(filename=filename, text=text, original=data)
            else:
                meta = resume.save_resume(filename=str(body.get("filename") or "pasted.txt"), text=str(body.get("text") or ""))
            j(handler, {"resume": meta})
            return True
        if path == f"{_PREFIX}/analyze":
            if body.get("scope") == "new":
                ids = [job.id for job in list_jobs(JobFilters(status=JobStatus.SCRAPED))]
            else:
                ids = [str(i) for i in (body.get("job_ids") or []) if isinstance(i, str)]
            j(handler, {"queued": analysis.request_analysis(ids, force=bool(body.get("force")))})
            return True
        if path.startswith(f"{_PREFIX}/jobs/") and path.endswith("/interview-prep"):
            from api.job_os import interview

            job_id = unquote(path[len(f"{_PREFIX}/jobs/"):]).rsplit("/", 1)[0].strip("/")
            j(handler, {"interview": interview.request_prep(job_id)})
            return True
        if path.startswith(f"{_PREFIX}/jobs/") and path.endswith(("/applied", "/note")):
            from api.job_os import applications

            job_id = unquote(path[len(f"{_PREFIX}/jobs/"):]).rsplit("/", 1)[0].strip("/")
            if path.endswith("/applied"):
                j(handler, applications.mark_applied(job_id, method="manual", note=str(body.get("note") or "")))
            else:
                j(handler, applications.add_note(job_id, body.get("text")))
            return True
        if path.startswith(f"{_PREFIX}/jobs/") and path.endswith(("/tailor", "/ready")):
            from api.job_os import tailor
            from api.job_os.lifecycle import transition_job

            job_id = unquote(path[len(f"{_PREFIX}/jobs/"):]).rsplit("/", 1)[0].strip("/")
            job = get_job(job_id)
            if job is None:
                return _error(handler, "Job not found", 404)
            if path.endswith("/tailor"):
                j(handler, tailor.request_tailoring(job_id))
            else:
                if job.status != JobStatus.RESUME_READY:
                    return _error(handler, "Only a job with a ready resume can be marked ready to apply", 400)
                j(handler, {"job": _job_payload(transition_job(job_id, JobStatus.APPLICATION_READY, expected_revision=job.revision))})
            return True
        if path.startswith(f"{_PREFIX}/documents/"):
            from api.job_os import tailor

            doc_id = unquote(path[len(f"{_PREFIX}/documents/"):]).strip("/")
            if doc_id.endswith("/score"):
                j(handler, {"document": tailor.rescore_document(doc_id[:-len("/score")])})
                return True
            j(handler, {"document": tailor.update_document(doc_id, body.get("content"), expected_revision=body.get("expected_revision"))})
            return True
        if path.startswith(f"{_PREFIX}/jobs/") and path.endswith(("/analyze", "/details")):
            job_id = unquote(path[len(f"{_PREFIX}/jobs/"):]).rsplit("/", 1)[0].strip("/")
            if get_job(job_id) is None:
                return _error(handler, "Job not found", 404)
            if path.endswith("/analyze"):
                queued = analysis.request_analysis([job_id], force=bool(body.get("force")))
                j(handler, {"queued": queued, "analysis": analysis.get_analysis(job_id)})
            else:
                j(handler, scout.fill_job_details(job_id))
            return True
    except KeyError:
        return _error(handler, "Not found", 404)
    except (resume.ResumeError, analysis.AnalysisError, scout.ScoutError) as error:
        return _error(handler, str(error), 400)
    except ValueError as error:  # TailorError, invalid transitions, stale revisions
        from api.job_os.lifecycle import ConcurrentRevisionError

        return _error(handler, str(error), 409 if isinstance(error, ConcurrentRevisionError) else 400)
    except Exception as error:  # unsafe link, Firecrawl or site API down: say so, never a 500
        from api.job_os.firecrawl import FirecrawlError
        from api.job_os.network_policy import UnsafeJobUrl

        if isinstance(error, (UnsafeJobUrl, FirecrawlError)):
            return _error(handler, f"Could not read that posting: {error}", 400)
        raise
    return None


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
        from api.job_os.analysis import analyses_by_job

        analyses = analyses_by_job()
        j(handler, {"jobs": [_job_payload(job, analyses=analyses) for job in jobs]})
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


def _apify_post(handler, path: str, body: dict) -> bool:
    """Connect (verify then save the token), disconnect, or test the saved token."""
    from api.job_os import apify

    try:
        if path == f"{_PREFIX}/apify":
            j(handler, {"apify": apify.connect(body.get("token"))})
        elif path == f"{_PREFIX}/apify/disconnect":
            j(handler, {"apify": apify.disconnect()})
        else:
            value = apify.token()
            if not value:
                return _error(handler, "Connect Apify first.", 400)
            j(handler, {"apify": {**apify.status(), **apify.verify_token(value)}})
    except apify.ApifyError as error:
        return _error(handler, str(error), 400)
    return True


def _notifications_post(handler, path: str) -> bool:
    """Send the digest now, or check for reply commands now."""
    from api import mailer
    from api.job_os import notify

    if not notify.status()["ready"]:
        return _error(handler, "Connect Gmail and turn on email notifications (with a Send-to address) first.", 400)
    try:
        if path.endswith("/digest"):
            sent = notify.maybe_send_digest(force=True)
            j(handler, {"sent": sent, "notifications": notify.status()})
        else:
            handled = notify.poll_replies()
            j(handler, {"handled": handled, "notifications": notify.status()})
    except mailer.GmailError as error:
        return _error(handler, str(error), 400)
    return True


def handle_job_os_post(handler, parsed, body) -> bool:
    """Handle Job OS creation endpoints or return False for an unknown path."""
    if parsed.path == f"{_PREFIX}/automate":
        from api.job_os import autopilot

        ids = body.get("job_ids") if isinstance(body, dict) else None
        if not isinstance(ids, list) or not ids or len(ids) > 200:
            return _error(handler, "job_ids must list 1-200 jobs", 400)
        try:
            j(handler, {"automate": autopilot.automate([str(i) for i in ids]), "min_fit": autopilot.MIN_FIT})
        except autopilot.AutopilotError as error:
            return _error(handler, str(error), 400)
        return True
    if parsed.path in {f"{_PREFIX}/resume", f"{_PREFIX}/analyze"} or parsed.path.startswith(f"{_PREFIX}/documents/") or (
            parsed.path.startswith(f"{_PREFIX}/jobs/") and parsed.path.endswith(("/analyze", "/details", "/tailor", "/ready", "/applied", "/note",
                                                                                "/interview-prep"))):
        handled = _resume_and_analysis_post(handler, parsed.path, body if isinstance(body, dict) else {})
        if handled is not None:
            return handled
    if parsed.path.startswith((f"{_PREFIX}/searches", f"{_PREFIX}/runs/")):
        handled = _scout_post(handler, parsed.path, body if isinstance(body, dict) else {})
        if handled is not None:
            return handled
    if parsed.path in {f"{_PREFIX}/notifications/digest", f"{_PREFIX}/notifications/check"}:
        return _notifications_post(handler, parsed.path)
    if parsed.path == f"{_PREFIX}/matches/seen":
        from api.job_os import notify

        j(handler, {"matches": notify.mark_matches_seen()})
        return True
    if parsed.path in {f"{_PREFIX}/apify", f"{_PREFIX}/apify/disconnect", f"{_PREFIX}/apify/test"}:
        return _apify_post(handler, parsed.path, body if isinstance(body, dict) else {})
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
    if parsed.path.startswith(f"{_PREFIX}/jobs/") and parsed.path.endswith("/edit"):
        return _edit_job(handler, parsed.path, body)
    if parsed.path.startswith(f"{_PREFIX}/jobs/") and parsed.path.endswith("/apply-kit"):
        from api.job_os import apply_kit

        try:
            j(handler, {"apply_kit": apply_kit.request(unquote(parsed.path[len(f"{_PREFIX}/jobs/"):-len("/apply-kit")]).strip("/"))})
        except KeyError:
            return _error(handler, "Job not found", 404)
        except apply_kit.ApplyKitError as error:
            return _error(handler, str(error), 400)
        return True
    if parsed.path != f"{_PREFIX}/jobs":
        return False
    if not isinstance(body, dict):
        return _error(handler, "JSON object body is required", 400)
    try:
        # The manual tracker: a job saved with its description is ready to
        # analyse and tailor, like a Scout find.
        job = normalize_job_input({**body, "source": "manual"})
        created = create_job(job, idempotency_key=body.get("idempotency_key"),
                             status=JobStatus.SCRAPED if job.description else JobStatus.DISCOVERED)
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


def _edit_job(handler, path: str, body) -> bool:
    from api.job_os.repository import StaleJobRevision, update_job_details

    if not isinstance(body, dict):
        return _error(handler, "JSON object body is required", 400)
    job_id = unquote(path[len(f"{_PREFIX}/jobs/"):-len("/edit")]).strip("/")
    try:
        updated = update_job_details(job_id, body.get("job") or {}, expected_revision=body.get("expected_revision"))
    except KeyError:
        return _error(handler, "Job not found", 404)
    except StaleJobRevision as error:
        return _error(handler, str(error), 409)
    except JobValidationError as error:
        return _error(handler, str(error), 400)
    j(handler, {"job": _job_payload(updated, detail=True)})
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
