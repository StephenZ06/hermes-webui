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
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from api.config import STATE_DIR

CATEGORIES = ("personal", "career", "business")
QUEST_LIMIT = 30
LOG_PAGE = 15
DAY = 86400

# XP per finished Work Hub item, by priority; a chosen quest earns half again.
WORK_XP = {"none": 20, "low": 20, "medium": 30, "high": 50}
QUEST_BONUS = 1.5
# Career milestones from the Jobs pipeline.
JOB_XP = {"tailored": 15, "applied": 30, "interview": 80, "offer": 250}
# A habit ticked off (once per day it is done).
HABIT_XP = 10
# Something learnt: a course, a book, a certification, a new skill.
LEARNING_XP = {"course": 40, "book": 30, "certification": 100, "skill": 20, "other": 15}
CADENCES = ("daily", "weekly")
# A skill gained, by how it was learnt.
SKILL_XP = {"course": 40, "bootcamp": 80, "certification": 100, "project": 30, "work": 30, "self": 20}
SKILL_NAME_MAX = 80
GOLD_PER_XP = 0.5
ACHIEVEMENT_GOLD = 50

# (key, title, description, icon, test(profile) -> bool). Display order.
ACHIEVEMENTS: list[tuple[str, str, str, str, Any]] = [
    ("first_task", "First Steps", "Finish your first task", "👣", lambda p: p["tasks_done"] >= 1),
    ("first_quest", "Questor", "Complete a quest", "⚔️", lambda p: p["quests_done"] >= 1),
    ("quests_10", "Quest Master", "Complete 10 quests", "🗡️", lambda p: p["quests_done"] >= 10),
    ("tasks_50", "Workhorse", "Earn XP 50 times", "🐎", lambda p: p["tasks_done"] >= 50),
    ("streak_7", "On Fire", "A 7-day streak", "🔥", lambda p: p["best_streak"] >= 7),
    ("streak_30", "Unstoppable", "A 30-day streak", "☄️", lambda p: p["best_streak"] >= 30),
    ("level_5", "Adept", "Reach level 5", "✨", lambda p: p["level"] >= 5),
    ("level_10", "Sorcerer", "Reach level 10", "🔮", lambda p: p["level"] >= 10),
    ("level_20", "Archmage", "Reach level 20", "🌌", lambda p: p["level"] >= 20),
    ("level_35", "Legend", "Reach level 35", "👑", lambda p: p["level"] >= 35),
    ("first_application", "Into the Arena", "Send a job application", "📨", lambda p: p["kinds"].get("applied", 0) >= 1),
    ("first_interview", "Audience", "Land an interview", "🎤", lambda p: p["kinds"].get("interview", 0) >= 1),
    ("first_offer", "Recruited", "Receive a job offer", "🏆", lambda p: p["kinds"].get("offer", 0) >= 1),
    ("first_sale", "Merchant", "Make your first sale", "💰", lambda p: p["kinds"].get("sale", 0) >= 1),
    ("habit_week", "Creature of Habit", "7-day habits streak", "🌱", lambda p: p["habit_days"] >= 7),
    ("scholar", "Scholar", "Log 5 things you learnt", "📚", lambda p: p["kinds"].get("learning", 0) >= 5),
    ("balanced", "Well-Rounded", "Earn XP in all three areas", "⚖️", lambda p: all(a["xp"] > 0 for a in p["areas"])),
    ("first_skill", "Skilled", "Add your first skill", "🎲", lambda p: p["kinds"].get("skill", 0) >= 1),
    ("certified", "Certified", "Add a certification skill", "📜", lambda p: p["kinds"].get("skill:certification", 0) >= 1),
    ("polymath", "Polymath", "Gain 10 skills", "🧠", lambda p: p["kinds"].get("skill", 0) >= 10),
    ("applications_10", "Persistent", "Send 10 job applications", "📮", lambda p: p["kinds"].get("applied", 0) >= 10),
    ("sales_10", "Trader", "Make 10 sales", "🪙", lambda p: p["kinds"].get("sale", 0) >= 10),
    ("habit_month", "Iron Will", "30-day habits streak", "🛡️", lambda p: p["habit_days"] >= 30),
    ("tasks_200", "Tireless", "Earn XP 200 times", "⚙️", lambda p: p["tasks_done"] >= 200),
]
NAME_MAX = 120

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
CREATE TABLE IF NOT EXISTS habits (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    icon TEXT NOT NULL DEFAULT '',
    cadence TEXT NOT NULL DEFAULT 'daily',
    target INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    archived_at REAL
);
CREATE TABLE IF NOT EXISTS habit_checks (
    habit_id TEXT NOT NULL,
    day TEXT NOT NULL,
    at REAL NOT NULL,
    PRIMARY KEY (habit_id, day)
);
CREATE TABLE IF NOT EXISTS achievements (
    key TEXT PRIMARY KEY,
    unlocked_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rewards (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    icon TEXT NOT NULL DEFAULT '',
    cost INTEGER NOT NULL,
    created_at REAL NOT NULL,
    archived_at REAL
);
CREATE TABLE IF NOT EXISTS redemptions (
    id TEXT PRIMARY KEY,
    reward_id TEXT NOT NULL,
    name TEXT NOT NULL,
    cost INTEGER NOT NULL,
    at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS learning (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    area TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    done_at REAL NOT NULL,
    created_at REAL NOT NULL
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
        _migrate(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    # quests.area: the area a quest was chosen for (Personal, Career or
    # Business tab); NULL means it follows its project's realm.
    if "area" not in {row[1] for row in conn.execute("PRAGMA table_info(quests)")}:
        conn.execute("ALTER TABLE quests ADD COLUMN area TEXT")


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

def add_quests(item_ids: list[str], area: str | None = None) -> dict[str, Any]:
    """Make Work Hub items quests. ``area`` is the tab they were chosen on; a
    quest chosen on Career shows (and earns XP) there whatever its project's realm."""
    from api import work_hub

    if not isinstance(item_ids, list) or not item_ids:
        raise GameError("Choose at least one Work Hub item")
    if area not in (None, "", *CATEGORIES):
        raise GameError("Unknown area")
    area = area or None
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
            conn.execute("INSERT INTO quests(item_id, added_at, cleared_at, area) VALUES(?, ?, NULL, ?) "
                         "ON CONFLICT(item_id) DO UPDATE SET added_at = excluded.added_at, cleared_at = NULL, area = excluded.area",
                         (item["id"], now, area))
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
    with _LOCK, _connect() as conn:
        categories = _categories(conn)
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
            "added_at": row["added_at"], "area": row["area"] or categories.get(item.get("project_id") or "", "personal"),
        })
    order = {"in_progress": 0, "blocked": 1, "todo": 2, "triage": 3, "backlog": 4}
    out.sort(key=lambda q: (q["done"], order.get(q["status"], 5), q["added_at"]))
    return out


# ── habits ──────────────────────────────────────────────────────────────────

def _clean_name(value: object, field: str = "Name") -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        raise GameError(f"{field} is required")
    if len(text) > NAME_MAX:
        raise GameError(f"{field} is too long")
    return text


def _day(value: object = None, now: float | None = None) -> str:
    if value:
        text = str(value)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            raise GameError("Day must be YYYY-MM-DD")
        return text
    return time.strftime("%Y-%m-%d", time.localtime(time.time() if now is None else now))


def create_habit(payload: dict[str, Any]) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    cadence = str(payload.get("cadence") or "daily")
    if cadence not in CADENCES:
        raise GameError("Cadence must be daily or weekly")
    try:
        target = int(payload.get("target") or 1)
    except (TypeError, ValueError):
        raise GameError("Target must be a number")
    if not 1 <= target <= (1 if cadence == "daily" else 7):
        raise GameError("A daily habit is done once a day; a weekly one 1 to 7 times a week")
    habit = {"id": uuid.uuid4().hex, "name": _clean_name(payload.get("name")),
             "icon": str(payload.get("icon") or "")[:8], "cadence": cadence, "target": target, "created_at": time.time()}
    with _LOCK, _connect() as conn:
        if conn.execute("SELECT COUNT(*) FROM habits WHERE archived_at IS NULL").fetchone()[0] >= 30:
            raise GameError("You can track at most 30 habits")
        conn.execute("INSERT INTO habits(id, name, icon, cadence, target, created_at) VALUES(?, ?, ?, ?, ?, ?)",
                     (habit["id"], habit["name"], habit["icon"], habit["cadence"], habit["target"], habit["created_at"]))
    return {"habit": habit}


def archive_habit(habit_id: str) -> dict[str, Any]:
    with _LOCK, _connect() as conn:
        if not conn.execute("UPDATE habits SET archived_at = ? WHERE id = ? AND archived_at IS NULL", (time.time(), str(habit_id))).rowcount:
            raise GameError("Habit not found", 404)
    return {"archived": str(habit_id)}


def check_habit(habit_id: str, day: object = None, done: bool = True) -> dict[str, Any]:
    """Tick a habit for a day (today by default), or untick it. Ticking earns
    HABIT_XP once for that day; unticking takes it back."""
    day = _day(day)
    with _LOCK, _connect() as conn:
        habit = conn.execute("SELECT * FROM habits WHERE id = ? AND archived_at IS NULL", (str(habit_id),)).fetchone()
        if habit is None:
            raise GameError("Habit not found", 404)
        key = f"habit:{habit['id']}:{day}"
        if done:
            at = time.time()
            conn.execute("INSERT OR IGNORE INTO habit_checks(habit_id, day, at) VALUES(?, ?, ?)", (habit["id"], day, at))
            _insert(conn, key, "habit", habit["name"], HABIT_XP, at, category="personal", detail={"kind": "habit", "day": day})
        else:
            conn.execute("DELETE FROM habit_checks WHERE habit_id = ? AND day = ?", (habit["id"], day))
            conn.execute("DELETE FROM xp_events WHERE key = ?", (key,))
    return {"habit_id": habit["id"], "day": day, "done": bool(done)}


def habits(now: float | None = None) -> list[dict[str, Any]]:
    from datetime import date, timedelta

    now = time.time() if now is None else now
    today = date.fromisoformat(_day(now=now))
    week_start = today - timedelta(days=today.weekday())
    with _LOCK, _connect() as conn:
        rows = conn.execute("SELECT * FROM habits WHERE archived_at IS NULL ORDER BY created_at").fetchall()
        checks: dict[str, set[str]] = {}
        for row in conn.execute("SELECT habit_id, day FROM habit_checks WHERE day >= ?", ((today - timedelta(days=400)).isoformat(),)):
            checks.setdefault(row["habit_id"], set()).add(row["day"])
    out = []
    for row in rows:
        days = checks.get(row["id"], set())
        week_count = sum((week_start + timedelta(days=i)).isoformat() in days for i in range(7))
        if row["cadence"] == "daily":
            streak = _streak(days, today.isoformat())
            done = today.isoformat() in days
        else:  # weeks in a row that met the target (this week counts once met)
            streak, start = 0, week_start
            if week_count < row["target"]:
                start -= timedelta(days=7)
            while sum((start + timedelta(days=i)).isoformat() in days for i in range(7)) >= row["target"]:
                streak += 1
                start -= timedelta(days=7)
            done = week_count >= row["target"]
        out.append({
            "id": row["id"], "name": row["name"], "icon": row["icon"], "cadence": row["cadence"], "target": row["target"],
            "done": done, "today": today.isoformat() in days, "week_count": week_count, "streak": streak,
            "recent": [(today - timedelta(days=i)).isoformat() in days for i in range(20, -1, -1)],
        })
    return out


# ── learning log ────────────────────────────────────────────────────────────

def add_learning(payload: dict[str, Any]) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    kind = str(payload.get("kind") or "other")
    if kind not in LEARNING_XP:
        raise GameError("Kind must be course, book, certification, skill or other")
    area = str(payload.get("area") or "career")
    if area not in CATEGORIES:
        raise GameError("Area must be personal, career or business")
    entry = {"id": uuid.uuid4().hex, "title": _clean_name(payload.get("title"), "Title"), "kind": kind, "area": area,
             "notes": str(payload.get("notes") or "")[:2000], "done_at": time.time()}
    with _LOCK, _connect() as conn:
        conn.execute("INSERT INTO learning(id, title, kind, area, notes, done_at, created_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
                     (entry["id"], entry["title"], kind, area, entry["notes"], entry["done_at"], entry["done_at"]))
        label = {"course": "Finished course", "book": "Finished book", "certification": "Earned", "skill": "Learnt", "other": "Learnt"}[kind]
        _insert(conn, f"learning:{entry['id']}", "learning", f"{label}: {entry['title']}", LEARNING_XP[kind], entry["done_at"],
                category=area, detail={"kind": kind})
    return {"entry": {**entry, "xp": LEARNING_XP[kind]}}


def remove_learning(entry_id: str) -> dict[str, Any]:
    with _LOCK, _connect() as conn:
        if not conn.execute("DELETE FROM learning WHERE id = ?", (str(entry_id),)).rowcount:
            raise GameError("Entry not found", 404)
        conn.execute("DELETE FROM xp_events WHERE key = ?", (f"learning:{entry_id}",))
    return {"removed": str(entry_id)}


def learning(limit: int = 8) -> dict[str, Any]:
    with _LOCK, _connect() as conn:
        rows = conn.execute("SELECT * FROM learning ORDER BY done_at DESC").fetchall()
    return {"total": len(rows), "entries": [{**dict(r), "xp": LEARNING_XP.get(r["kind"], 0)} for r in rows[:limit]],
            "by_kind": {k: sum(r["kind"] == k for r in rows) for k in LEARNING_XP}}


# ── skills gained ───────────────────────────────────────────────────────────

def add_skill(payload: dict[str, Any]) -> dict[str, Any]:
    """A skill the user gained (course, bootcamp, certification...). Earns Career
    XP once; the same name (any case) is not added twice."""
    payload = payload if isinstance(payload, dict) else {}
    kind = str(payload.get("kind") or "course")
    if kind not in SKILL_XP:
        raise GameError("Type must be course, bootcamp, certification, project, work or self")
    name = _clean_name(payload.get("name"), "Skill")
    if len(name) > SKILL_NAME_MAX:
        raise GameError("Skill name is too long")
    skill = {"id": uuid.uuid4().hex, "name": name, "kind": kind, "created_at": time.time()}
    with _LOCK, _connect() as conn:
        if conn.execute("SELECT 1 FROM skills WHERE lower(name) = lower(?)", (name,)).fetchone():
            raise GameError("That skill is already on your list", 409)
        if conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0] >= 200:
            raise GameError("You can list at most 200 skills")
        conn.execute("INSERT INTO skills(id, name, kind, created_at) VALUES(:id, :name, :kind, :created_at)", skill)
        _insert(conn, f"skill:{skill['id']}", "skill", f"Skill gained: {name}", SKILL_XP[kind], skill["created_at"],
                category="career", detail={"kind": "skill", "via": kind})
    return {"skill": {**skill, "xp": SKILL_XP[kind]}}


def remove_skill(skill_id: str) -> dict[str, Any]:
    with _LOCK, _connect() as conn:
        if not conn.execute("DELETE FROM skills WHERE id = ?", (str(skill_id),)).rowcount:
            raise GameError("Skill not found", 404)
        conn.execute("DELETE FROM xp_events WHERE key = ?", (f"skill:{skill_id}",))
    return {"removed": str(skill_id)}


def skills(limit: int | None = None) -> dict[str, Any]:
    with _LOCK, _connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM skills ORDER BY created_at DESC")]
    entries = [{**r, "xp": SKILL_XP.get(r["kind"], 0)} for r in rows]
    return {"total": len(entries), "entries": entries[:limit] if limit else entries}


def skill_names() -> list[str]:
    """The user's skills, oldest first (for the resume)."""
    with _LOCK, _connect() as conn:
        return [r["name"] for r in conn.execute("SELECT name FROM skills ORDER BY created_at")]


def project_realms() -> list[dict[str, Any]]:
    from api.models import load_projects

    with _LOCK, _connect() as conn:
        categories = _categories(conn)
    return [{"project_id": p.get("project_id"), "name": p.get("name"),
             "category": categories.get(p.get("project_id") or "", "personal")} for p in load_projects()]


# ── party: the Hermes agent profiles ────────────────────────────────────────

def party() -> list[dict[str, Any]]:
    """Each agent profile as a party member, busy while one of its chats runs."""
    from api.profiles import list_profiles_api

    busy: dict[str, int] = {}
    try:
        from api.config import STREAM_SESSION_OWNERS, STREAM_SESSION_OWNERS_LOCK
        from api.models import get_session

        with STREAM_SESSION_OWNERS_LOCK:
            running = [str(s) for s in STREAM_SESSION_OWNERS.values() if s]
        for session_id in running:
            try:
                profile = getattr(get_session(session_id), "profile", None) or "default"
            except Exception:
                continue
            busy[profile] = busy.get(profile, 0) + 1
    except Exception:
        pass
    members = []
    for row in list_profiles_api():
        name = str(row.get("name") or "")
        if not name:
            continue
        members.append({"name": name, "model": row.get("model") or "", "provider": row.get("provider") or "",
                        "active": bool(row.get("is_active") or row.get("active")), "busy": busy.get(name, 0)})
    return members


# ── gold and the rewards shop ───────────────────────────────────────────────

def add_reward(payload: dict[str, Any]) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    try:
        cost = int(payload.get("cost"))
    except (TypeError, ValueError):
        raise GameError("Cost must be a whole number of gold")
    if not 1 <= cost <= 1_000_000:
        raise GameError("Cost must be between 1 and 1,000,000 gold")
    reward = {"id": uuid.uuid4().hex, "name": _clean_name(payload.get("name")), "icon": str(payload.get("icon") or "🎁")[:8],
              "cost": cost, "created_at": time.time()}
    with _LOCK, _connect() as conn:
        if conn.execute("SELECT COUNT(*) FROM rewards WHERE archived_at IS NULL").fetchone()[0] >= 40:
            raise GameError("You can have at most 40 rewards")
        conn.execute("INSERT INTO rewards(id, name, icon, cost, created_at) VALUES(:id, :name, :icon, :cost, :created_at)", reward)
    return {"reward": reward}


def remove_reward(reward_id: str) -> dict[str, Any]:
    with _LOCK, _connect() as conn:
        if not conn.execute("UPDATE rewards SET archived_at = ? WHERE id = ? AND archived_at IS NULL", (time.time(), str(reward_id))).rowcount:
            raise GameError("Reward not found", 404)
    return {"removed": str(reward_id)}


def _gold(conn: sqlite3.Connection) -> dict[str, int]:
    xp = conn.execute("SELECT COALESCE(SUM(xp), 0) FROM xp_events").fetchone()[0]
    achieved = conn.execute("SELECT COUNT(*) FROM achievements").fetchone()[0]
    spent = conn.execute("SELECT COALESCE(SUM(cost), 0) FROM redemptions").fetchone()[0]
    earned = int(xp * GOLD_PER_XP) + achieved * ACHIEVEMENT_GOLD
    return {"earned": earned, "spent": int(spent), "balance": earned - int(spent)}


def redeem(reward_id: str) -> dict[str, Any]:
    """Spend gold on a reward. Refused when the balance is short."""
    with _LOCK, _connect() as conn:
        reward = conn.execute("SELECT * FROM rewards WHERE id = ? AND archived_at IS NULL", (str(reward_id),)).fetchone()
        if reward is None:
            raise GameError("Reward not found", 404)
        gold = _gold(conn)
        if gold["balance"] < reward["cost"]:
            raise GameError(f"You need {reward['cost'] - gold['balance']} more gold", 409)
        conn.execute("INSERT INTO redemptions(id, reward_id, name, cost, at) VALUES(?, ?, ?, ?, ?)",
                     (uuid.uuid4().hex, reward["id"], reward["name"], reward["cost"], time.time()))
        return {"redeemed": reward["name"], "gold": _gold(conn)}


def treasury(now: float | None = None) -> dict[str, Any]:
    """The Shop page: balance, rewards, gold earned and spent over time, the
    next reward to save for, and one ledger of gold in (XP, achievements) and
    out (rewards)."""
    from datetime import date, datetime, timedelta

    now = time.time() if now is None else now
    sync()
    today = datetime.fromtimestamp(now).date()

    def start(day: date) -> float:
        return datetime(day.year, day.month, day.day).timestamp()

    with _LOCK, _connect() as conn:
        gold = _gold(conn)
        rewards = [dict(r) for r in conn.execute("SELECT * FROM rewards WHERE archived_at IS NULL ORDER BY cost")]
        spends = [dict(r) for r in conn.execute("SELECT * FROM redemptions ORDER BY at DESC")]
        events = [dict(r) for r in conn.execute("SELECT key, source, category, title, xp, at FROM xp_events ORDER BY at DESC")]
        unlocks = {r["key"]: r["unlocked_at"] for r in conn.execute("SELECT * FROM achievements")}
    titles = {a[0]: a[1] for a in ACHIEVEMENTS}
    flows = [{"kind": "earn", "title": e["title"], "gold": e["xp"] * GOLD_PER_XP, "at": e["at"], "category": e["category"], "source": e["source"]} for e in events]
    flows += [{"kind": "achievement", "title": f"Achievement: {titles.get(k, k)}", "gold": ACHIEVEMENT_GOLD, "at": at} for k, at in unlocks.items()]
    flows += [{"kind": "spend", "title": r["name"], "gold": -r["cost"], "at": r["at"]} for r in spends]
    flows.sort(key=lambda f: -f["at"])

    def earned_since(t: float) -> int:
        return int(sum(f["gold"] for f in flows if f["gold"] > 0 and f["at"] >= t))

    days = []
    for back in range(13, -1, -1):
        day = today - timedelta(days=back)
        lo, hi = start(day), start(day + timedelta(days=1))
        inside = [f for f in flows if lo <= f["at"] < hi]
        days.append({"day": day.isoformat(), "label": day.strftime("%a")[:2], "earned": int(sum(f["gold"] for f in inside if f["gold"] > 0)),
                     "spent": int(-sum(f["gold"] for f in inside if f["gold"] < 0))})
    week_start = start(today - timedelta(days=today.weekday()))
    month_start = start(today.replace(day=1))
    first = min((f["at"] for f in flows), default=now)
    active_days = max(1, int((now - first) // 86400) + 1)
    best = max(days, key=lambda d: d["earned"]) if days else None
    goal = next((r for r in rewards if r["cost"] > gold["balance"]), None)
    return {
        "gold": gold,
        "rewards": [{**r, "affordable": r["cost"] <= gold["balance"], "progress": round(min(1.0, gold["balance"] / r["cost"]), 4)} for r in rewards],
        "stats": {
            "earned_today": earned_since(start(today)), "earned_week": earned_since(week_start), "earned_month": earned_since(month_start),
            "spent_month": int(-sum(f["gold"] for f in flows if f["gold"] < 0 and f["at"] >= month_start)),
            "redeemed": len(spends), "per_day": round(gold["earned"] / active_days, 1),
            "best_day": best if best and best["earned"] else None,
            "biggest": max(spends, key=lambda r: r["cost"])["name"] if spends else None,
        },
        "saving_for": {**goal, "short": goal["cost"] - gold["balance"], "progress": round(gold["balance"] / goal["cost"], 4)} if goal else None,
        "days": days,
        "ledger": [{**f, "gold": int(round(f["gold"]))} for f in flows[:40]],
        "ledger_total": len(flows),
    }


def shop() -> dict[str, Any]:
    with _LOCK, _connect() as conn:
        rewards = [dict(r) for r in conn.execute("SELECT * FROM rewards WHERE archived_at IS NULL ORDER BY cost")]
        history = [dict(r) for r in conn.execute("SELECT * FROM redemptions ORDER BY at DESC LIMIT 10")]
        return {"gold": _gold(conn), "rewards": rewards, "history": history}


# ── XP ledger ───────────────────────────────────────────────────────────────

def _insert(conn: sqlite3.Connection, key: str, source: str, title: str, xp: int, at: float,
            *, category: str | None = None, project_id: str | None = None, detail: dict | None = None) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO xp_events(key, source, category, project_id, title, xp, at, detail) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
        (key, source, category, project_id, title[:240], int(xp), float(at), json.dumps(detail or {})),
    )


def _sync_work_hub(conn: sqlite3.Connection) -> None:
    from api import work_hub

    quest_rows = {row["item_id"]: row["area"] for row in conn.execute("SELECT item_id, area FROM quests")}
    for item in work_hub.completed_items():
        quest = item["id"] in quest_rows
        xp = WORK_XP.get(str(item.get("priority") or "none"), WORK_XP["none"])
        if quest:
            xp = int(round(xp * QUEST_BONUS))
        _insert(conn, f"work_hub:{item['id']}", "work_hub", str(item.get("title") or "Work item"), xp,
                item.get("done_at") or time.time(), project_id=item.get("project_id"), category=quest_rows.get(item["id"]),
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


def _sync_sales(conn: sqlite3.Connection) -> None:
    from api.dashboard_business import sync_xp

    sync_xp(conn)


def sync() -> None:
    """Fold every finished piece of work into the ledger (idempotent). A
    source that cannot be read is skipped this time and caught up later."""
    with _LOCK, _connect() as conn:
        for step in (_sync_work_hub, _sync_jobs, _sync_sales):
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
    habit_xp = 0
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
        if row["source"] == "habit":
            habit_xp += row["xp"]
        if category in (None, "", "all") or cat == category:
            log.append({"title": row["title"], "xp": row["xp"], "at": row["at"], "category": cat, "source": row["source"],
                        "quest": bool(detail.get("quest"))})
    total = sum(by_category.values())
    week = sum(row["xp"] for row in rows if row["at"] >= now - 7 * DAY)
    kinds: dict[str, int] = {}
    habit_days: set[str] = set()
    for row in rows:
        detail = json.loads(row["detail"] or "{}")
        kind = detail.get("kind") or row["source"]
        if row["source"] == "learning":
            kind = "learning"
        kinds[kind] = kinds.get(kind, 0) + 1
        if row["source"] == "skill" and detail.get("via"):
            kinds[f"skill:{detail['via']}"] = kinds.get(f"skill:{detail['via']}", 0) + 1
        if row["source"] == "habit":
            habit_days.add(detail.get("day") or "")
    today = time.strftime("%Y-%m-%d", time.localtime(now))

    def score(xp: int) -> int:  # attributes grow quickly early, then slow down
        return 1 + int(math.sqrt(max(0, xp) / 10))

    stats = {
        "STR": {"value": score(by_category["personal"] - habit_xp), "label": "Personal", "hint": "Personal projects and learning"},
        "INT": {"value": score(by_category["career"]), "label": "Career", "hint": "Jobs pipeline, career tasks and learning"},
        "CHA": {"value": score(by_category["business"]), "label": "Business", "hint": "Business tasks and sales"},
        "VIT": {"value": score(habit_xp), "label": "Vitality", "hint": "Habits kept"},
        "DEX": {"value": 1 + len(recent_days), "label": "Consistency", "hint": "Active days in the last 30"},
    }
    level_info = level_for(total)
    progress = {"tasks_done": len(rows), "quests_done": quests_done, "best_streak": _best_streak(days), "level": level_info["level"],
                "kinds": kinds, "habit_days": len(habit_days),
                "areas": [{"key": c, "xp": by_category[c]} for c in CATEGORIES]}
    achievements = _achievements(progress, now)
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
        "tiers": [{"level": first, "name": name, "video": name.lower() in _character_video()} for first, name in TIERS],
        "quests": _safe(quests, []),
        "party": _safe(party, []),
        "achievements": achievements,
        "best_streak": progress["best_streak"],
        "shop": _safe(shop, {"gold": {"earned": 0, "spent": 0, "balance": 0}, "rewards": [], "history": []}),
    }


def _best_streak(days: set[str]) -> int:
    from datetime import date, timedelta

    best = run = 0
    previous = None
    for day in sorted(d for d in days if d):
        current = date.fromisoformat(day)
        run = run + 1 if previous is not None and current - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = current
    return best


def _achievements(progress: dict[str, Any], now: float) -> list[dict[str, Any]]:
    """Unlock what the progress now earns (once, kept forever) and list all."""
    with _LOCK, _connect() as conn:
        unlocked = {r["key"]: r["unlocked_at"] for r in conn.execute("SELECT * FROM achievements")}
        for key, _title, _desc, _icon, test in ACHIEVEMENTS:
            if key not in unlocked:
                try:
                    earned = bool(test(progress))
                except Exception:
                    earned = False
                if earned:
                    unlocked[key] = now
                    conn.execute("INSERT OR IGNORE INTO achievements(key, unlocked_at) VALUES(?, ?)", (key, now))
    return [{"key": k, "title": t, "description": d, "icon": i, "unlocked_at": unlocked.get(k), "art": k in _achievement_art(),
             "new": bool(unlocked.get(k)) and unlocked[k] >= now - 3 * DAY} for k, t, d, i, _ in ACHIEVEMENTS]


_VIDEO_DIR = Path(__file__).resolve().parent.parent / "static" / "dashboard" / "characters"


def _character_video() -> set[str]:
    """Evolution forms with an animation (static/dashboard/characters/<form>.mp4,
    e.g. apprentice.mp4); the rest are drawn as pixel sprites."""
    try:
        return {f.stem.lower() for f in _VIDEO_DIR.glob("*.mp4")}
    except OSError:
        return set()


_ART_DIR = Path(__file__).resolve().parent.parent / "static" / "dashboard" / "achievements"


def _achievement_art() -> set[str]:
    """Achievements with badge art (static/dashboard/achievements/<key>.png);
    the rest show their icon in a medallion. Read each time, so new art shows
    without a restart."""
    try:
        return {f.stem for f in _ART_DIR.glob("*.png")}
    except OSError:
        return set()


def _safe(build, default):
    try:
        return build()
    except Exception:
        import logging
        logging.getLogger(__name__).info("character section failed", exc_info=True)
        return default
