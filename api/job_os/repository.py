"""Canonical Job OS record creation, lookup, filtering, and normalization."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from api.job_os import posting_guard
from api.job_os.db import connect_job_os
from api.job_os.extract import indeed_job_key
from api.job_os.models import (
    DuplicateJobError,
    JobFilters,
    JobInput,
    JobRecord,
    JobStatus,
    JobValidationError,
)


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise JobValidationError(f"{key} is required")
    return value


def _optional_text(payload: Mapping[str, object], key: str) -> str:
    return str(payload.get(key) or "").strip()


def _canonicalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise JobValidationError("canonical_url must use http or https")
    if parsed.username or parsed.password:
        raise JobValidationError("canonical_url must not contain credentials")
    host = parsed.hostname.lower()
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    path = parsed.path.rstrip("/") or "/"
    # Queries are dropped (tracking noise), except Indeed's job key: every Indeed
    # posting lives at /viewjob and only ?jk= tells them apart.
    query = ""
    key = indeed_job_key(value.strip())
    if key:
        query = f"jk={key}"
    return urlunsplit((parsed.scheme.lower(), netloc, path, query, ""))


WORKPLACES = ("", "remote", "hybrid", "onsite")
# Longest accepted value per field; anything longer is a pasted mistake.
_LIMITS = {"title": 240, "company": 240, "location": 240, "country": 80, "salary_text": 120,
           "employment_type": 60, "posted_at": 40, "description": 20000}


def _bounded(payload: Mapping[str, object], key: str) -> str:
    value = _optional_text(payload, key)
    if len(value) > _LIMITS[key]:
        raise JobValidationError(f"{key.replace('_', ' ')} is too long (at most {_LIMITS[key]} characters)")
    return value


def normalize_job_input(payload: Mapping[str, object]) -> JobInput:
    """Validate and normalize one untrusted job payload before persistence.

    Besides the identity fields it takes the posting details a person types into
    the manual tracker (or Scout reads from a posting)."""
    title = _required_text(payload, "title")
    if len(title) > _LIMITS["title"]:
        raise JobValidationError("title is too long")
    canonical_url = _canonicalize_url(_required_text(payload, "canonical_url"))
    source = _optional_text(payload, "source") or "manual"
    source_id = _optional_text(payload, "source_id") or None
    workplace = _optional_text(payload, "workplace").lower()
    if workplace not in WORKPLACES:
        raise JobValidationError("workplace must be remote, hybrid or onsite")
    # Every posting enters here: hidden text is removed before it is stored or
    # read by Luna, and what was found is kept with the job (advisory only).
    hidden = payload.get("guard_hidden")
    description, guard = posting_guard.guard_text(_bounded(payload, "description"),
                                                  hidden if isinstance(hidden, Mapping) else None)
    return JobInput(
        title=title,
        canonical_url=canonical_url,
        company=_bounded(payload, "company"),
        location=_bounded(payload, "location"),
        source=source,
        source_id=source_id,
        description=description.strip(),
        salary_text=_bounded(payload, "salary_text"),
        employment_type=_bounded(payload, "employment_type"),
        workplace=workplace,
        posted_at=_bounded(payload, "posted_at"),
        country=_bounded(payload, "country"),
        guard=guard,
    )


def _record_from_row(row: sqlite3.Row) -> JobRecord:
    return JobRecord(
        id=row["id"],
        canonical_url=row["canonical_url"],
        title=row["title"],
        company=row["company"],
        location=row["location"],
        source=row["source"],
        source_id=row["source_id"],
        status=JobStatus(row["status"]),
        revision=row["revision"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        description=row["description"],
        salary_text=row["salary_text"],
        employment_type=row["employment_type"],
        workplace=row["workplace"],
        posted_at=row["posted_at"],
        search_id=row["search_id"],
        run_id=row["run_id"],
        country=row["country"],
        guard=_guard(row),
    )


def _guard(row: sqlite3.Row) -> dict:
    try:
        value = json.loads(row["guard_json"] or "{}")
    except (IndexError, KeyError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _find_duplicate(connection: sqlite3.Connection, job: JobInput) -> sqlite3.Row | None:
    row = connection.execute(
        "SELECT * FROM jobs WHERE canonical_url = ?", (job.canonical_url,)
    ).fetchone()
    if row is not None:
        return row
    if job.source_id is None:
        return None
    return connection.execute(
        "SELECT * FROM jobs WHERE source = ? AND source_id = ?", (job.source, job.source_id)
    ).fetchone()


def create_job(job: JobInput, *, idempotency_key: str | None = None,
               status: JobStatus = JobStatus.DISCOVERED) -> JobRecord:
    """Persist one normalized job or return the original idempotent creation.

    ``status`` is the starting point: ``discovered`` for a bare link,
    ``scraped`` when Scout already read the full posting.
    """
    if status not in (JobStatus.DISCOVERED, JobStatus.SCRAPED):
        raise JobValidationError("A new job starts as discovered or scraped")
    key = str(idempotency_key or "").strip() or None
    connection = connect_job_os()
    try:
        connection.execute("BEGIN IMMEDIATE")
        if key is not None:
            existing = connection.execute(
                "SELECT * FROM jobs WHERE idempotency_key = ?", (key,)
            ).fetchone()
            if existing is not None:
                connection.rollback()
                return _record_from_row(existing)
        duplicate = _find_duplicate(connection, job)
        if duplicate is not None:
            connection.rollback()
            raise DuplicateJobError("A matching job already exists", duplicate["id"])
        now = int(time.time())
        record_id = str(uuid.uuid4())
        connection.execute(
            """
            INSERT INTO jobs (
                id, canonical_url, source, source_id, title, company, location,
                status, revision, idempotency_key, created_at, updated_at,
                description, salary_text, employment_type, workplace, posted_at,
                search_id, run_id, country, guard_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                job.canonical_url,
                job.source,
                job.source_id,
                job.title,
                job.company,
                job.location,
                status.value,
                0,
                key,
                now,
                now,
                job.description,
                job.salary_text,
                job.employment_type,
                job.workplace,
                job.posted_at,
                job.search_id,
                job.run_id,
                job.country,
                json.dumps(job.guard or {}),
            ),
        )
        connection.execute(
            "INSERT INTO job_events (id, job_id, event_type, created_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), record_id, "job_created", now),
        )
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (record_id,)).fetchone()
        connection.commit()
        return _record_from_row(row)
    except sqlite3.IntegrityError as error:
        connection.rollback()
        raise DuplicateJobError("A matching job already exists") from error
    finally:
        connection.close()


def get_job(job_id: str) -> JobRecord | None:
    """Return one profile-owned canonical job record, if it exists."""
    connection = connect_job_os()
    try:
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _record_from_row(row) if row is not None else None
    finally:
        connection.close()


def list_jobs(filters: JobFilters | None = None) -> list[JobRecord]:
    """List the active profile's jobs using only explicit canonical filters."""
    filters = filters or JobFilters()
    clauses: list[str] = []
    params: list[Any] = []
    if filters.status is not None:
        clauses.append("status = ?")
        params.append(filters.status.value)
    if filters.source is not None:
        clauses.append("source = ?")
        params.append(filters.source)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    connection = connect_job_os()
    try:
        rows = connection.execute(
            f"SELECT * FROM jobs{where} ORDER BY created_at ASC, id ASC", params
        ).fetchall()
        return [_record_from_row(row) for row in rows]
    finally:
        connection.close()


EDITABLE_FIELDS = ("title", "company", "location", "country", "salary_text", "employment_type", "workplace",
                   "posted_at", "description")


def update_job_details(job_id: str, changes: Mapping[str, object], *, expected_revision: int) -> JobRecord:
    """Edit a job's posting details (the tracker's Edit form). The link, source
    and stage are not editable here; every edit bumps the revision."""
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        raise JobValidationError("expected_revision must be an integer")
    if not isinstance(changes, Mapping) or not changes:
        raise JobValidationError("Nothing to change")
    unknown = sorted(set(changes) - set(EDITABLE_FIELDS))
    if unknown:
        raise JobValidationError(f"Not editable: {', '.join(unknown)}")
    current = get_job(job_id)
    if current is None:
        raise KeyError(job_id)
    merged = {field: getattr(current, field) for field in EDITABLE_FIELDS}
    merged.update(changes)
    clean = normalize_job_input({**merged, "canonical_url": current.canonical_url})
    values = {field: getattr(clean, field) for field in EDITABLE_FIELDS}
    connection = connect_job_os()
    try:
        connection.execute("BEGIN IMMEDIATE")
        now = int(time.time())
        cursor = connection.execute(
            f"UPDATE jobs SET {', '.join(f'{f} = ?' for f in EDITABLE_FIELDS)}, guard_json = ?, revision = revision + 1,"
            " updated_at = ? WHERE id = ? AND revision = ?",
            (*values.values(), json.dumps(clean.guard if "description" in changes else current.guard), now, job_id, expected_revision),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            raise StaleJobRevision("This job changed in another tab; reload and try again")
        connection.execute(
            "INSERT INTO job_events (id, job_id, event_type, payload_json, created_at) VALUES (?, ?, 'details_edited', ?, ?)",
            (str(uuid.uuid4()), job_id, json.dumps({"fields": sorted(changes)}), now),
        )
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        connection.commit()
        return _record_from_row(row)
    finally:
        connection.close()


class StaleJobRevision(ValueError):
    """The job changed since the browser loaded it (HTTP 409)."""
