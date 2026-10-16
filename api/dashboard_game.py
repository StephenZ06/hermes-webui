"""Dashboard game layer: quests picked from the Work Hub, and an XP ledger that
levels up the character.

Quests are Work Hub items the user chose to focus on (no dates). Their status
is always read live from the Work Hub, so finishing one there, or a chat
finishing it through the work_hub tool, shows here on the next read.

XP is a ledger of events, each awarded once under a stable key (the Work Hub
item, the Job OS event). The ledger is filled by ``sync()`` from the stores
that own the work, on every read, so it needs no hooks in those stores and
past completions are counted too. An award survives the item being deleted or
reopened later.
"""

from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

from api.config import STATE_DIR

CATEGORIES = ("personal", "career", "business")
QUEST_LIMIT = 30
LOG_PAGE = 50
DAY = 86400

# XP per finished Work Hub item, by priority; a chosen quest earns half again.
WORK_XP = {"none": 20, "low": 20, "medium": 30, "high": 50}
QUEST_BONUS = 1.5
# Career milestones from the Jobs pipeline.
JOB_XP = {"tailored": 15, "applied": 30, "interview": 80, "offer": 250}

TIERS = (  # (first level, name)
    (1, "Apprentice"),
    (5, "Adept"),
    (10, "Sorcerer"),
    (20, "Archmage"),
    (35, "Legendary"),
)

_LOCK = threading.RLock()
_SCHEMA = """
CREATE TABLE IF NOT EXISTS quests (
    item_id TEXT PRIMARY KEY,
    added_at REAL NOT NULL,
    cleared_at REAL
);
CREATE TABLE IF NOT EXISTS xp_events (
    key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    category TEXT,
    project_id TEXT,
    title TEXT NOT NULL,
    xp INTEGER NOT NULL,
    at REAL NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS xp_events_at ON xp_events(at);
CREATE TABLE IF NOT EXISTS project_categories (
    project_id TEXT PRIMARY KEY,
    category TEXT NOT NULL
);
"""


class GameError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _db_path():
    return STATE_DIR / "dashboard.db"


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_db_path()), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


# ── levels ──────────────────────────────────────────────────────────────────

def xp_for_level(level: int) -> int:
    """XP needed to go from ``level`` to the next: 100, 125, 150, ..."""
    return 100 + 25 * (max(1, level) - 1)


def level_for(total: int) -> dict[str, Any]:
    level, floor = 1, 0
    while total >= floor + xp_for_level(level):
        floor += xp_for_level(level)
        level += 1
    need = xp_for_level(level)
    tier_index = max(i for i, (first, _) in enumerate(TIERS) if level >= first)
    next_tier = TIERS[tier_index + 1] if tier_index + 1 < len(TIERS) else None
    return {
        "level": level,
        "into_level": total - floor,
        "level_size": need,
        "progress": round((total - floor) / need, 4),
        "tier": tier_index + 1,
        "tier_name": TIERS[tier_index][1],
        "next_tier": {"level": next_tier[0], "name": next_tier[1]} if next_tier else None,
    }


# ── categories ──────────────────────────────────────────────────────────────

def _categories(conn: sqlite3.Connection) -> dict[str, str]:
    return {row["project_id"]: row["category"] for row in conn.execute("SELECT * FROM project_categories")}


def set_category(project_id: str, category: str) -> dict[str, Any]:
    project_id = str(project_id or "").strip()
    if not project_id:
        raise GameError("Choose a project")
    if category not in CATEGORIES:
        raise GameError("Category must be personal, career or business")
    with _LOCK, _connect() as conn:
        conn.execute("INSERT INTO project_categories(project_id, category) VALUES(?, ?) "
                     "ON CONFLICT(project_id) DO UPDATE SET category = excluded.category", (project_id, category))
    return {"project_id": project_id, "category": category}


# ── quests ──────────────────────────────────────────────────────────────────

def add_quests(item_ids: list[str]) -> dict[str, Any]:
    from api import work_hub

    if not isinstance(item_ids, list) or not item_ids:
        raise GameError("Choose at least one Work Hub item")
    added = []
    now = time.time()
    with _LOCK, _connect() as conn:
        active = conn.execute("SELECT COUNT(*) FROM quests WHERE cleared_at IS NULL").fetchone()[0]
        for item_id in item_ids:
            item = work_hub.get_item(str(item_id))
            if not item:
                raise GameError("Work item not found", 404)
            existing = conn.execute("SELECT cleared_at FROM quests WHERE item_id = ?", (item["id"],)).fetchone()
            if existing and existing["cleared_at"] is None:
                continue
            if active >= QUEST_LIMIT:
                raise GameError(f"You can have at most {QUEST_LIMIT} quests at once")
            conn.execute("INSERT INTO quests(item_id, added_at, cleared_at) VALUES(?, ?, NULL) "
                         "ON CONFLICT(item_id) DO UPDATE SET added_at = excluded.added_at, cleared_at = NULL", (item["id"], now))
            active += 1
            added.append(item["id"])
    return {"added": added}


def remove_quest(item_id: str) -> dict[str, Any]:
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM quests WHERE item_id = ?", (str(item_id),))
    return {"removed": str(item_id)}


def clear_completed() -> dict[str, Any]:
    from api import work_hub

    now = time.time()
    cleared = []
    with _LOCK, _connect() as conn:
        for row in conn.execute("SELECT item_id FROM quests WHERE cleared_at IS NULL").fetchall():
            item = work_hub.get_item(row["item_id"])
            if not item or item.get("status") in ("done", "cancelled"):
                conn.execute("UPDATE quests SET cleared_at = ? WHERE item_id = ?", (now, row["item_id"]))
                cleared.append(row["item_id"])
    return {"cleared": cleared}


def quest_ids() -> list[str]:
    with _LOCK, _connect() as conn:
        return [row["item_id"] for row in conn.execute("SELECT item_id FROM quests WHERE cleared_at IS NULL ORDER BY added_at")]


def quests() -> list[dict[str, Any]]:
    """The chosen quests with their live Work Hub state: open ones first (in
    progress, then blocked, then the rest), finished ones after."""
    from api import work_hub
    from api.models import load_projects

    sync()
    with _LOCK, _connect() as conn:
        rows = conn.execute("SELECT * FROM quests WHERE cleared_at IS NULL ORDER BY added_at").fetchall()
        earned = {row["key"]: row["xp"] for row in conn.execute("SELECT key, xp FROM xp_events WHERE source = 'work_hub'")}
    items = {item["id"]: item for item in work_hub.list_items()["items"]}
    names = {p.get("project_id"): p.get("name") for p in load_projects()}
    out = []
    for row in rows:
        item = items.get(row["item_id"])
        if item is None:
            remove_quest(row["item_id"])  # deleted from the Work Hub
            continue
        status = item.get("status")
        out.append({
            "id": item["id"], "title": item.get("title"), "status": status, "priority": item.get("priority"),
            "working": bool(item.get("working")), "project": names.get(item.get("project_id")),
            "project_id": item.get("project_id"), "board_id": item.get("board_id"),
            "done": status in ("done", "cancelled"), "xp": earned.get(f"work_hub:{item['id']}"),
            "added_at": row["added_at"],
        })
    order = {"in_progress": 0, "blocked": 1, "todo": 2, "triage": 3, "backlog": 4}
    out.sort(key=lambda q: (q["done"], order.get(q["status"], 5), q["added_at"]))
    return out


# ── XP ledger ───────────────────────────────────────────────────────────────

def _insert(conn: sqlite3.Connection, key: str, source: str, title: str, xp: int, at: float,
            *, category: str | None = None, project_id: str | None = None, detail: dict | None = None) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO xp_events(key, source, category, project_id, title, xp, at, detail) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
        (key, source, category, project_id, title[:240], int(xp), float(at), json.dumps(detail or {})),
    )


def _sync_work_hub(conn: sqlite3.Connection) -> None:
    from api import work_hub

    quest_rows = {row["item_id"] for row in conn.execute("SELECT item_id FROM quests")}
    for item in work_hub.completed_items():
        quest = item["id"] in quest_rows
        xp = WORK_XP.get(str(item.get("priority") or "none"), WORK_XP["none"])
        if quest:
            xp = int(round(xp * QUEST_BONUS))
        _insert(conn, f"work_hub:{item['id']}", "work_hub", str(item.get("title") or "Work item"), xp,
                item.get("done_at") or time.time(), project_id=item.get("project_id"),
                detail={"priority": item.get("priority"), "quest": quest})


def _sync_jobs(conn: sqlite3.Connection) -> None:
    from api.job_os.db import connect_job_os

    jobs_conn = connect_job_os()
    try:
        titles = {row["id"]: f"{row['title'] or 'a role'} at {row['company'] or 'a company'}"
                  for row in jobs_conn.execute("SELECT id, title, company FROM jobs")}
        for row in jobs_conn.execute("SELECT id, job_id, created_at FROM job_documents WHERE kind='resume' AND status IN ('ready', 'needs_review')"):
            _insert(conn, f"job_doc:{row['id']}", "jobs", f"Tailored resume for {titles.get(row['job_id'], 'a role')}",
                    JOB_XP["tailored"], row["created_at"], category="career")
        for row in jobs_conn.execute("SELECT id, job_id, event_type, payload_json, created_at FROM job_events "
                                     "WHERE event_type IN ('application_submitted', 'status_changed')"):
            kind = "applied" if row["event_type"] == "application_submitted" else None
            if kind is None:
                to = (json.loads(row["payload_json"] or "{}") or {}).get("to")
                kind = "interview" if to in ("screening", "interviewing") else "offer" if to in ("offer", "offer_accepted") else None
            if kind is None:
                continue
            label = {"applied": "Applied to", "interview": "Interview for", "offer": "Offer for"}[kind]
            _insert(conn, f"job_event:{row['id']}", "jobs", f"{label} {titles.get(row['job_id'], 'a role')}",
                    JOB_XP[kind], row["created_at"], category="career", detail={"kind": kind})
    finally:
        jobs_conn.close()


def sync() -> None:
    """Fold every finished piece of work into the ledger (idempotent). A
    source that cannot be read is skipped this time and caught up later."""
    with _LOCK, _connect() as conn:
        for step in (_sync_work_hub, _sync_jobs):
            try:
                step(conn)
            except Exception:
                import logging
                logging.getLogger(__name__).info("XP sync step %s failed", step.__name__, exc_info=True)


def _event_category(row: sqlite3.Row, categories: dict[str, str]) -> str:
    if row["category"]:
        return row["category"]
    return categories.get(row["project_id"] or "", "personal")


def _streak(days: set[str], today: str) -> int:
    from datetime import date, timedelta

    day = date.fromisoformat(today)
    if today not in days:  # a streak survives until today is over
        day -= timedelta(days=1)
    count = 0
    while day.isoformat() in days:
        count += 1
        day -= timedelta(days=1)
    return count


def character(*, category: str | None = None, offset: int = 0, now: float | None = None) -> dict[str, Any]:
    """Everything the Character page shows: level, tier, stats, XP per area,
    streak, and a page of the XP log."""
    from api.models import load_projects

    sync()
    now = time.time() if now is None else now
    with _LOCK, _connect() as conn:
        categories = _categories(conn)
        rows = conn.execute("SELECT * FROM xp_events ORDER BY at DESC").fetchall()
    by_category = {c: 0 for c in CATEGORIES}
    counts = {c: 0 for c in CATEGORIES}
    days: set[str] = set()
    recent_days: set[str] = set()
    quests_done = 0
    log = []
    for row in rows:
        cat = _event_category(row, categories)
        by_category[cat] = by_category.get(cat, 0) + row["xp"]
        counts[cat] = counts.get(cat, 0) + 1
        day = time.strftime("%Y-%m-%d", time.localtime(row["at"]))
        days.add(day)
        if row["at"] >= now - 30 * DAY:
            recent_days.add(day)
        detail = json.loads(row["detail"] or "{}")
        quests_done += bool(detail.get("quest"))
        if category in (None, "", "all") or cat == category:
            log.append({"title": row["title"], "xp": row["xp"], "at": row["at"], "category": cat, "source": row["source"],
                        "quest": bool(detail.get("quest"))})
    total = sum(by_category.values())
    week = sum(row["xp"] for row in rows if row["at"] >= now - 7 * DAY)
    today = time.strftime("%Y-%m-%d", time.localtime(now))

    def score(xp: int) -> int:  # attributes grow quickly early, then slow down
        return 1 + int(math.sqrt(max(0, xp) / 10))

    stats = {
        "STR": {"value": score(by_category["personal"]), "label": "Personal", "hint": "Personal projects finished"},
        "INT": {"value": score(by_category["career"]), "label": "Career", "hint": "Jobs pipeline and career tasks"},
        "CHA": {"value": score(by_category["business"]), "label": "Business", "hint": "Business tasks and sales"},
        "DEX": {"value": 1 + len(recent_days), "label": "Consistency", "hint": "Active days in the last 30"},
    }
    projects = [{"project_id": p.get("project_id"), "name": p.get("name"),
                 "category": categories.get(p.get("project_id") or "", "personal")} for p in load_projects()]
    return {
        "total_xp": total,
        "xp_this_week": week,
        **level_for(total),
        "areas": [{"key": c, "xp": by_category[c], "tasks": counts[c], **{k: v for k, v in level_for(by_category[c]).items() if k in ("level", "progress")}} for c in CATEGORIES],
        "stats": stats,
        "streak": _streak(days, today),
        "tasks_done": len(rows),
        "quests_done": quests_done,
        "log": log[offset:offset + LOG_PAGE],
        "log_total": len(log),
        "projects": projects,
        "tiers": [{"level": first, "name": name} for first, name in TIERS],
    }
