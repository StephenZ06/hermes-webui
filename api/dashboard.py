"""Dashboard page: one read-only summary per tab (personal, career, business).

Each section is gathered from the store that owns it (Work Hub, cron jobs,
Notes, Job OS) and fails on its own: a store that cannot be read yields an
``{"error": ...}`` section instead of breaking the whole page.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

WEEK = 7 * 86400
TABS = ("personal", "career", "business", "settings")
_QUEST_LIMIT = 8
_FAILING_LIMIT = 6
_RECENT_NOTES = 5


def _section(build: Callable[[], Any]) -> Any:
    try:
        return build()
    except Exception as error:  # one unreadable store must not blank the page
        logger.info("dashboard section failed", exc_info=True)
        return {"error": str(error) or type(error).__name__}


def _area_quests(area: str) -> list[dict[str, Any]]:
    from api import dashboard_game

    return [quest for quest in dashboard_game.quests() if quest.get("area") == area]


# ── Personal ────────────────────────────────────────────────────────────────

def _work_hub(now: float) -> dict[str, Any]:
    from api import work_hub
    from api.models import load_projects

    items = work_hub.list_items()["items"]
    names = {p.get("project_id"): p.get("name") for p in load_projects()}
    open_items = [i for i in items if i.get("status") not in ("done", "cancelled")]
    totals = {
        "open": len(open_items),
        "in_progress": sum(i.get("status") == "in_progress" for i in items),
        "blocked": sum(i.get("status") == "blocked" for i in items),
        "done_this_week": sum(i.get("status") == "done" and (i.get("updated_at") or 0) >= now - WEEK for i in items),
        "working": sum(bool(i.get("working")) for i in items),
    }
    projects: dict[str, dict[str, Any]] = {}
    for item in items:
        key = item.get("project_id") or ""
        row = projects.setdefault(key, {"project_id": key or None, "name": names.get(key) or ("General" if not key else key),
                                        "open": 0, "in_progress": 0, "blocked": 0, "done": 0, "last_activity": 0})
        status = item.get("status")
        if status == "done":
            row["done"] += 1
        elif status != "cancelled":
            row["open"] += 1
            row["in_progress"] += status == "in_progress"
            row["blocked"] += status == "blocked"
        row["last_activity"] = max(row["last_activity"], item.get("updated_at") or 0)
    for row in projects.values():
        total = row["open"] + row["done"]
        row["progress"] = round(row["done"] / total, 3) if total else 0.0
    order = {"in_progress": 0, "blocked": 1, "todo": 2, "triage": 3, "backlog": 4}
    quests = sorted(open_items, key=lambda i: (order.get(i.get("status"), 9), -(i.get("updated_at") or 0)))[:_QUEST_LIMIT]
    return {
        "totals": totals,
        "projects": sorted(projects.values(), key=lambda r: -r["last_activity"]),
        "quests": [{"id": i["id"], "title": i.get("title"), "status": i.get("status"), "priority": i.get("priority"),
                    "working": bool(i.get("working")), "project": names.get(i.get("project_id")),
                    "project_id": i.get("project_id"), "board_id": i.get("board_id")} for i in quests],
    }


def _cron_jobs(home: Path) -> list[dict[str, Any]]:
    path = home / "cron" / "jobs.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8") or "{}")
    jobs = data.get("jobs") if isinstance(data, dict) else data
    return [job for job in jobs or [] if isinstance(job, dict)]


def _schedules() -> dict[str, Any]:
    from api.gateway_ticker import _iter_profile_homes

    enabled = 0
    failing: list[dict[str, Any]] = []
    upcoming: list[dict[str, Any]] = []
    for home in _iter_profile_homes():
        profile = "default" if home.parent.name != "profiles" else home.name
        for job in _cron_jobs(Path(home)):
            if not job.get("enabled", True):
                continue
            enabled += 1
            row = {"name": job.get("name") or job.get("id"), "profile": profile, "next_run_at": job.get("next_run_at")}
            if job.get("last_status") == "error":
                failing.append({**row, "error": str(job.get("last_error") or "")[:240], "last_run_at": job.get("last_run_at")})
            elif job.get("next_run_at"):
                upcoming.append(row)
    upcoming.sort(key=lambda r: str(r["next_run_at"]))
    return {"enabled": enabled, "failing": failing[:_FAILING_LIMIT], "failing_count": len(failing), "upcoming": upcoming[:5]}


def _recent_notes() -> list[dict[str, Any]]:
    from api import notebook, notebook_vault

    store = notebook_vault if notebook_vault.enabled() else notebook
    notes = [n for n in store.bootstrap().get("notes") or [] if not n.get("deleted_at")]
    notes.sort(key=lambda n: (not n.get("pinned"), -(n.get("updated_at") or 0)))
    return [{"id": n.get("id"), "title": n.get("title") or "Untitled", "updated_at": n.get("updated_at"),
             "pinned": bool(n.get("pinned"))} for n in notes[:_RECENT_NOTES]]


def personal(now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    from api import dashboard_game

    return {
        "quests": _section(lambda: _area_quests("personal")),
        "habits": _section(lambda: dashboard_game.habits(now)),
        "learning": _section(dashboard_game.learning),
        "work_hub": _section(lambda: _work_hub(now)),
        "schedules": _section(_schedules),
        "notes": _section(_recent_notes),
    }


# ── Career ──────────────────────────────────────────────────────────────────

def _week_activity(activity: dict[str, Any], now: float) -> dict[str, int]:
    from datetime import date, timedelta

    today = date.fromisoformat(activity.get("today") or time.strftime("%Y-%m-%d", time.localtime(now)))
    days = activity.get("days") or {}
    week = {"found": 0, "tailored": 0, "applied": 0, "interview": 0, "rejected": 0}
    for offset in range(7):
        for kind, count in (days.get((today - timedelta(days=offset)).isoformat()) or {}).items():
            if kind in week:
                week[kind] += int(count or 0)
    return week


def _jobs(now: float) -> dict[str, Any]:
    from api.job_os.dashboard import build_dashboard

    board = build_dashboard()
    return {
        "total_jobs": board["total_jobs"],
        "active_work": board["active_work"],
        "needs_attention": board["needs_attention"],
        "by_status": board["by_status"],
        "funnel": board["funnel"],
        "this_week": _week_activity(board.get("activity") or {}, now),
    }


def career(now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    return {"jobs": _section(lambda: _jobs(now)), "quests": _section(lambda: _area_quests("career"))}


# ── Business ────────────────────────────────────────────────────────────────

def business(now: float | None = None) -> dict[str, Any]:
    from api import dashboard_business

    return {"sales": _section(lambda: dashboard_business.summary(now)), "quests": _section(lambda: _area_quests("business"))}


def settings(now: float | None = None) -> dict[str, Any]:
    from api import dashboard_business

    return {"sales_status": _section(dashboard_business.status)}


def summary(tab: str) -> dict[str, Any]:
    tab = tab if tab in TABS else "personal"
    build = {"personal": personal, "career": career, "business": business, "settings": settings}[tab]
    return {"tab": tab, "generated_at": time.time(), **build()}
