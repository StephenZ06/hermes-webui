"""Server-owned validation and atomic transitions for Job OS records."""

from __future__ import annotations

import json
import time
import uuid

from api.job_os.db import connect_job_os
from api.job_os.models import JobRecord, JobStatus
from api.job_os.repository import _record_from_row


class InvalidJobTransition(ValueError):
    """Raised when a requested lifecycle jump is not canonical."""


class ConcurrentRevisionError(ValueError):
    """Raised when a browser acts on an older view of a job."""


_ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    # Any stage before applying can go straight to submitted: a tracked job
    # is often applied for without a tailored resume.
    JobStatus.DISCOVERED: frozenset({JobStatus.SCRAPED, JobStatus.SKIPPED, JobStatus.EXPIRED, JobStatus.SUBMITTED}),
    JobStatus.SCRAPED: frozenset({JobStatus.ANALYZED, JobStatus.SHORTLISTED, JobStatus.SKIPPED, JobStatus.EXPIRED,
                                  JobStatus.SUBMITTED}),
    JobStatus.ANALYZED: frozenset({JobStatus.SHORTLISTED, JobStatus.SKIPPED, JobStatus.EXPIRED, JobStatus.SUBMITTED}),
    JobStatus.SHORTLISTED: frozenset({JobStatus.TAILORING, JobStatus.SKIPPED, JobStatus.EXPIRED, JobStatus.SUBMITTED}),
    JobStatus.TAILORING: frozenset({JobStatus.RESUME_READY, JobStatus.SHORTLISTED}),
    JobStatus.RESUME_READY: frozenset({JobStatus.APPLICATION_READY, JobStatus.SHORTLISTED}),
    JobStatus.APPLICATION_READY: frozenset({JobStatus.AWAITING_APPROVAL}),
    JobStatus.AWAITING_APPROVAL: frozenset({JobStatus.APPLYING}),
    JobStatus.APPLYING: frozenset({JobStatus.SUBMITTED, JobStatus.APPLICATION_READY}),
    JobStatus.SUBMITTED: frozenset(
        {JobStatus.SCREENING, JobStatus.REJECTED, JobStatus.WITHDRAWN, JobStatus.NO_RESPONSE}
    ),
    JobStatus.SCREENING: frozenset(
        {JobStatus.INTERVIEWING, JobStatus.REJECTED, JobStatus.WITHDRAWN, JobStatus.NO_RESPONSE}
    ),
    JobStatus.INTERVIEWING: frozenset(
        {JobStatus.OFFER, JobStatus.REJECTED, JobStatus.WITHDRAWN, JobStatus.NO_RESPONSE}
    ),
    JobStatus.OFFER: frozenset(
        {JobStatus.OFFER_ACCEPTED, JobStatus.OFFER_DECLINED, JobStatus.WITHDRAWN}
    ),
}


def transition_job(job_id: str, target: JobStatus, *, expected_revision: int) -> JobRecord:
    """Validate, revision-check, and atomically record one lifecycle transition."""
    connection = connect_job_os()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            connection.rollback()
            raise KeyError("Job not found")
        current = JobStatus(row["status"])
        if row["revision"] != expected_revision:
            connection.rollback()
            raise ConcurrentRevisionError("Job has changed; refresh before updating it")
        if target not in _ALLOWED_TRANSITIONS.get(current, frozenset()):
            connection.rollback()
            raise InvalidJobTransition(f"Cannot transition {current.value} to {target.value}")
        now = int(time.time())
        updated = connection.execute(
            """
            UPDATE jobs
            SET status = ?, revision = revision + 1, updated_at = ?
            WHERE id = ? AND revision = ?
            """,
            (target.value, now, job_id, expected_revision),
        )
        if updated.rowcount != 1:
            connection.rollback()
            raise ConcurrentRevisionError("Job has changed; refresh before updating it")
        connection.execute(
            """
            INSERT INTO job_events (id, job_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                job_id,
                "status_changed",
                json.dumps({"from": current.value, "to": target.value}, separators=(",", ":")),
                now,
            ),
        )
        result = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        connection.commit()
        return _record_from_row(result)
    finally:
        connection.close()


def move_job(job_id: str, target: JobStatus, *, expected_revision: int, payload: dict | None = None) -> JobRecord:
    """Put a job at ``target`` because a person (or an email they received) said so.

    The board lets you drag a card to any stage, back as well as forward, so this
    skips the transition graph that automation follows. It keeps the revision
    check and records the move in the event log like any other transition.
    """
    connection = connect_job_os()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            connection.rollback()
            raise KeyError("Job not found")
        if row["revision"] != expected_revision:
            connection.rollback()
            raise ConcurrentRevisionError("Job has changed; refresh before updating it")
        current = JobStatus(row["status"])
        if current == target:
            connection.rollback()
            return _record_from_row(row)
        now = int(time.time())
        connection.execute("UPDATE jobs SET status = ?, revision = revision + 1, updated_at = ? WHERE id = ? AND revision = ?",
                           (target.value, now, job_id, expected_revision))
        connection.execute(
            "INSERT INTO job_events (id, job_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), job_id, "status_changed",
             json.dumps({"from": current.value, "to": target.value, **(payload or {"by": "you"})}, separators=(",", ":")), now),
        )
        result = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        connection.commit()
        return _record_from_row(result)
    finally:
        connection.close()
