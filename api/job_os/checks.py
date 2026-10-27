"""The checks shown on a job: one list, built here for the board card and the
job drawer alike, so both always say the same thing.

Each check is ``{"key", "tone", "short", "label", "detail", "quotes"}``: ``tone`` is
``danger`` (the job is held back from automation) or ``warn`` (worth a look).
"""

from __future__ import annotations

from api.job_os import posting_guard


def job_checks(job, analysis: dict | None = None) -> list[dict]:
    """Every check on one job, most serious first."""
    checks: list[dict] = []
    guard = posting_guard.public(job.guard)
    if guard:
        checks.append({"key": "guard", "tone": "warn", "short": "Hidden text",
                       "label": "Hidden instructions found",
                       "detail": guard["summary"] + ". Luna was told to ignore it; check the posting yourself.",
                       "quotes": guard["excerpts"]})
    return sorted(checks, key=lambda c: c["tone"] != "danger")
