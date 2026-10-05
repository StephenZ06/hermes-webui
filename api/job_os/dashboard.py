"""Server-owned, profile-scoped Job OS dashboard projections."""

from __future__ import annotations

from typing import Any

from api.job_os.models import JobStatus
from api.job_os.repository import list_jobs

_ACTIVE_WORK_STATUSES = frozenset(
    {
        JobStatus.TAILORING,
        JobStatus.RESUME_READY,
        JobStatus.APPLICATION_READY,
        JobStatus.AWAITING_APPROVAL,
        JobStatus.APPLYING,
    }
)


def build_dashboard() -> dict[str, Any]:
    """Build current metrics exclusively from canonical active-profile records."""
    jobs = list_jobs()
    by_status: dict[str, int] = {}
    for job in jobs:
        by_status[job.status.value] = by_status.get(job.status.value, 0) + 1
    from api.job_os.applications import board, funnel

    # Every card the board flags, wherever it sits (a follow-up nudge stays in Applied).
    attention = sum(1 for column in board()["columns"] for card in column["jobs"]
                    if card["attention"] or column["key"] == "attention")
    return {
        "total_jobs": len(jobs),
        "by_status": by_status,
        "active_work": sum(job.status in _ACTIVE_WORK_STATUSES for job in jobs),
        "needs_attention": attention,
        "funnel": funnel(),
    }
