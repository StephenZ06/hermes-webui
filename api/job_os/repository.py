"""Canonical Job OS record creation, lookup, filtering, and normalization."""

from __future__ import annotations

import sqlite3
import time
import uuid
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from api.job_os.db import connect_job_os
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
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def normalize_job_input(payload: Mapping[str, object]) -> JobInput:
    """Validate and normalize one untrusted job payload before persistence."""
    title = _required_text(payload, "title")
    canonical_url = _canonicalize_url(_required_text(payload, "canonical_url"))
    source = _optional_text(payload, "source") or "manual"
    source_id = _optional_text(payload, "source_id") or None
    return JobInput(
        title=title,
        canonical_url=canonical_url,
        company=_optional_text(payload, "company"),
        location=_optional_text(payload, "location"),
        source=source,
        source_id=source_id,
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
    )


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


def create_job(job: JobInput, *, idempotency_key: str | None = None) -> JobRecord:
    """Persist one normalized job or return the original idempotent creation."""
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
            raise DuplicateJobError("A matching job already exists")
        now = int(time.time())
        record_id = str(uuid.uuid4())
        connection.execute(
            """
            INSERT INTO jobs (
                id, canonical_url, source, source_id, title, company, location,
                status, revision, idempotency_key, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                job.canonical_url,
                job.source,
                job.source_id,
                job.title,
                job.company,
                job.location,
                JobStatus.DISCOVERED.value,
                0,
                key,
                now,
                now,
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
