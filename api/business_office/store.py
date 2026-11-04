"""SQLite state for the Business Office (``STATE_DIR/business_office.db``).

This module owns every row. Secrets are stored only as ciphertext from
:mod:`api.business_office.crypto`; the ``public_*`` readers never select them.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from api.business_office import crypto, registry

_LOCK = threading.RLock()
DB_NAME = "business_office.db"
SEED_BUSINESSES = (
    ("saas-temani", "SaaS — Temani", "saas"),
    ("saas-ai-honeypot", "SaaS — AI Honeypot", "saas"),
    ("cafe", "Café", "cafe"),
)
DEFAULT_SETTINGS = {"max_parallel": 3, "max_parallel_per_agent": 2, "max_parallel_per_provider": 2}

TASK_STATES = ("created", "queued", "assigned", "running", "waiting_dependency", "waiting_approval",
               "completed", "failed", "cancelled")
OPEN_TASK_STATES = ("created", "queued", "assigned", "running", "waiting_dependency", "waiting_approval")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1, paused INTEGER NOT NULL DEFAULT 0, settings TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS paused_agents(
  business_id TEXT NOT NULL, agent_id TEXT NOT NULL, PRIMARY KEY(business_id, agent_id));
CREATE TABLE IF NOT EXISTS oauth_apps(
  app TEXT PRIMARY KEY, client_id TEXT NOT NULL, secret_enc TEXT NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS connections(
  id TEXT PRIMARY KEY, business_id TEXT NOT NULL, provider TEXT NOT NULL, status TEXT NOT NULL,
  account_id TEXT NOT NULL DEFAULT '', account_label TEXT NOT NULL DEFAULT '', scopes TEXT NOT NULL DEFAULT '[]',
  token_enc TEXT NOT NULL DEFAULT '', expires_at REAL NOT NULL DEFAULT 0, last_sync_at REAL NOT NULL DEFAULT 0,
  last_error TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL,
  UNIQUE(business_id, provider));
CREATE TABLE IF NOT EXISTS oauth_states(
  state TEXT PRIMARY KEY, business_id TEXT NOT NULL, provider TEXT NOT NULL, redirect_uri TEXT NOT NULL,
  session_hash TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS capability_modes(
  business_id TEXT NOT NULL, agent_id TEXT NOT NULL, capability_id TEXT NOT NULL, mode TEXT NOT NULL,
  PRIMARY KEY(business_id, agent_id, capability_id));
CREATE TABLE IF NOT EXISTS vault_grants(
  id TEXT PRIMARY KEY, business_id TEXT NOT NULL, vault TEXT NOT NULL, folder TEXT NOT NULL, created_at REAL NOT NULL,
  UNIQUE(business_id, vault, folder));
CREATE TABLE IF NOT EXISTS vault_agent_grants(
  grant_id TEXT NOT NULL, agent_id TEXT NOT NULL, can_search INTEGER NOT NULL DEFAULT 0, can_read INTEGER NOT NULL DEFAULT 0,
  can_create INTEGER NOT NULL DEFAULT 0, can_edit INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(grant_id, agent_id));
CREATE TABLE IF NOT EXISTS tasks(
  id TEXT PRIMARY KEY, parent_id TEXT, business_id TEXT NOT NULL, agent_id TEXT NOT NULL, goal TEXT NOT NULL,
  capability_id TEXT NOT NULL, input TEXT NOT NULL DEFAULT '{}', priority INTEGER NOT NULL DEFAULT 5,
  status TEXT NOT NULL, depends_on TEXT NOT NULL DEFAULT '[]', retries INTEGER NOT NULL DEFAULT 0,
  max_retries INTEGER NOT NULL DEFAULT 3, not_before REAL NOT NULL DEFAULT 0, approval_id TEXT,
  result TEXT, error TEXT NOT NULL DEFAULT '', needs_review INTEGER NOT NULL DEFAULT 0,
  schedule_id TEXT, created_at REAL NOT NULL, started_at REAL NOT NULL DEFAULT 0,
  finished_at REAL NOT NULL DEFAULT 0, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS tasks_status ON tasks(status, not_before);
CREATE INDEX IF NOT EXISTS tasks_business ON tasks(business_id, updated_at);
CREATE TABLE IF NOT EXISTS approvals(
  id TEXT PRIMARY KEY, business_id TEXT NOT NULL, task_id TEXT NOT NULL, agent_id TEXT NOT NULL,
  capability_id TEXT NOT NULL, provider TEXT NOT NULL, target TEXT NOT NULL DEFAULT '', payload TEXT NOT NULL,
  payload_hash TEXT NOT NULL, risk TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL,
  expires_at REAL NOT NULL, decided_at REAL NOT NULL DEFAULT 0, finished_at REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, business_id TEXT NOT NULL, actor TEXT NOT NULL,
  agent_id TEXT NOT NULL DEFAULT '', task_id TEXT NOT NULL DEFAULT '', provider TEXT NOT NULL DEFAULT '',
  capability_id TEXT NOT NULL DEFAULT '', target TEXT NOT NULL DEFAULT '', decision TEXT NOT NULL,
  outcome TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS audit_business ON audit(business_id, ts);
CREATE TABLE IF NOT EXISTS schedules(
  id TEXT PRIMARY KEY, business_id TEXT NOT NULL, agent_id TEXT NOT NULL, name TEXT NOT NULL,
  capability_id TEXT NOT NULL, input TEXT NOT NULL DEFAULT '{}', every_minutes INTEGER NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1, next_run_at REAL NOT NULL, last_run_at REAL NOT NULL DEFAULT 0);
"""


class StoreError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def db_path() -> Path:
    from api import config

    return Path(config.STATE_DIR) / DB_NAME


_READY: set[str] = set()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            if str(path) not in _READY or not _has_schema(conn):
                conn.execute("PRAGMA journal_mode=WAL")
                conn.executescript(_SCHEMA)
                _seed(conn)
                conn.commit()
                path.chmod(0o600)
                _READY.add(str(path))
            with conn:
                yield conn
        finally:
            conn.close()


def _has_schema(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name='businesses'").fetchone() is not None


def _seed(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT 1 FROM businesses LIMIT 1").fetchone():
        return
    now = time.time()
    for order, (business_id, name, kind) in enumerate(SEED_BUSINESSES):
        conn.execute("INSERT INTO businesses(id,name,kind,settings,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                     (business_id, name, kind, json.dumps(DEFAULT_SETTINGS), now + order, now + order))


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _loads(raw: Any, fallback: Any) -> Any:
    try:
        return json.loads(raw) if raw else fallback
    except (TypeError, ValueError):
        return fallback


# ── businesses ──────────────────────────────────────────────────────────────────

def _business(row: sqlite3.Row, paused_agents: list[str]) -> dict[str, Any]:
    return {"id": row["id"], "name": row["name"], "kind": row["kind"], "description": row["description"],
            "active": bool(row["active"]), "paused": bool(row["paused"]), "paused_agents": paused_agents,
            "settings": {**DEFAULT_SETTINGS, **_loads(row["settings"], {})}}


def list_businesses() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM businesses ORDER BY created_at, name").fetchall()
        paused = conn.execute("SELECT business_id, agent_id FROM paused_agents").fetchall()
    return [_business(row, sorted(p["agent_id"] for p in paused if p["business_id"] == row["id"])) for row in rows]


def get_business(business_id: str) -> dict[str, Any]:
    for business in list_businesses():
        if business["id"] == business_id:
            return business
    raise StoreError("Business not found", 404)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]


def create_business(name: object, kind: object = "saas", description: object = "") -> dict[str, Any]:
    clean = str(name or "").strip()
    if not clean or len(clean) > 80:
        raise StoreError("Give the business a name of up to 80 characters")
    business_id = _slug(clean) or new_id("biz")
    now = time.time()
    with connect() as conn:
        if conn.execute("SELECT 1 FROM businesses WHERE id=?", (business_id,)).fetchone():
            raise StoreError("A business with this name already exists", 409)
        conn.execute("INSERT INTO businesses(id,name,kind,description,settings,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                     (business_id, clean, str(kind or "saas")[:20], str(description or "")[:500],
                      json.dumps(DEFAULT_SETTINGS), now, now))
    return get_business(business_id)


def update_settings(business_id: str, raw: object) -> dict[str, Any]:
    business = get_business(business_id)
    if not isinstance(raw, dict):
        raise StoreError("Settings must be an object")
    settings = dict(business["settings"])
    for key in DEFAULT_SETTINGS:
        if key in raw:
            value = raw[key]
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
                raise StoreError(f"{key} must be between 1 and 10")
            settings[key] = value
    with connect() as conn:
        conn.execute("UPDATE businesses SET settings=?, updated_at=? WHERE id=?", (json.dumps(settings), time.time(), business_id))
    return get_business(business_id)


def set_paused(business_id: str, paused: bool, agent_id: str | None = None) -> dict[str, Any]:
    get_business(business_id)
    with connect() as conn:
        if agent_id is None:
            conn.execute("UPDATE businesses SET paused=?, updated_at=? WHERE id=?", (int(paused), time.time(), business_id))
        elif agent_id not in registry.AGENTS:
            raise StoreError("Unknown agent", 404)
        elif paused:
            conn.execute("INSERT OR IGNORE INTO paused_agents VALUES(?,?)", (business_id, agent_id))
        else:
            conn.execute("DELETE FROM paused_agents WHERE business_id=? AND agent_id=?", (business_id, agent_id))
    return get_business(business_id)


# ── OAuth apps and connections ──────────────────────────────────────────────────

def save_oauth_app(app: str, client_id: object, client_secret: object) -> None:
    cid, secret = str(client_id or "").strip(), str(client_secret or "").strip()
    if not cid or not secret or len(cid) > 400 or len(secret) > 400:
        raise StoreError("Enter both the client ID and the client secret")
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO oauth_apps VALUES(?,?,?,?)",
                     (app, cid, crypto.encrypt(secret, context=f"app:{app}"), time.time()))


def oauth_app(app: str) -> tuple[str, str] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM oauth_apps WHERE app=?", (app,)).fetchone()
    return (row["client_id"], crypto.decrypt(row["secret_enc"], context=f"app:{app}")) if row else None


def oauth_app_configured(app: str) -> bool:
    with connect() as conn:
        return conn.execute("SELECT 1 FROM oauth_apps WHERE app=?", (app,)).fetchone() is not None


def _token_context(business_id: str, provider: str) -> str:
    return f"token:{business_id}:{provider}"


def _connection(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": row["id"], "business_id": row["business_id"], "provider": row["provider"], "status": row["status"],
            "account_id": row["account_id"], "account_label": row["account_label"], "scopes": _loads(row["scopes"], []),
            "expires_at": row["expires_at"], "last_sync_at": row["last_sync_at"], "last_error": row["last_error"]}


def get_connection(business_id: str, provider: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM connections WHERE business_id=? AND provider=?", (business_id, provider)).fetchone()
    return _connection(row) if row else None


def list_connections(business_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM connections WHERE business_id=?", (business_id,)).fetchall()
    return [_connection(row) for row in rows]


def save_connection(business_id: str, provider: str, *, tokens: dict[str, Any], account_id: str, account_label: str,
                    scopes: list[str], expires_at: float, status: str = "connected") -> dict[str, Any]:
    now = time.time()
    sealed = crypto.encrypt(json.dumps(tokens), context=_token_context(business_id, provider))
    with connect() as conn:
        conn.execute(
            """INSERT INTO connections(id,business_id,provider,status,account_id,account_label,scopes,token_enc,expires_at,
                 last_sync_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(business_id,provider) DO UPDATE SET status=excluded.status, account_id=excluded.account_id,
                 account_label=excluded.account_label, scopes=excluded.scopes, token_enc=excluded.token_enc,
                 expires_at=excluded.expires_at, last_sync_at=excluded.last_sync_at, last_error='', updated_at=excluded.updated_at""",
            (new_id("conn"), business_id, provider, status, account_id, account_label, json.dumps(scopes), sealed,
             expires_at, now, now, now))
    return get_connection(business_id, provider) or {}


def connection_tokens(business_id: str, provider: str) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT token_enc FROM connections WHERE business_id=? AND provider=?", (business_id, provider)).fetchone()
    if not row or not row["token_enc"]:
        raise crypto.SecretError("No stored credentials")
    return json.loads(crypto.decrypt(row["token_enc"], context=_token_context(business_id, provider)))


def update_tokens(business_id: str, provider: str, tokens: dict[str, Any], expires_at: float) -> None:
    sealed = crypto.encrypt(json.dumps(tokens), context=_token_context(business_id, provider))
    with connect() as conn:
        conn.execute("UPDATE connections SET token_enc=?, expires_at=?, updated_at=? WHERE business_id=? AND provider=?",
                     (sealed, expires_at, time.time(), business_id, provider))


def mark_connection(business_id: str, provider: str, status: str, error: str = "") -> None:
    now = time.time()
    with connect() as conn:
        if status == "connected":
            conn.execute("UPDATE connections SET status=?, last_error='', last_sync_at=?, updated_at=? WHERE business_id=? AND provider=?",
                         (status, now, now, business_id, provider))
        else:
            conn.execute("UPDATE connections SET status=?, last_error=?, updated_at=? WHERE business_id=? AND provider=?",
                         (status, error[:300], now, business_id, provider))


def delete_connection(business_id: str, provider: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM connections WHERE business_id=? AND provider=?", (business_id, provider))


def save_oauth_state(state: str, business_id: str, provider: str, redirect_uri: str, session_hash: str, ttl: int = 600) -> None:
    now = time.time()
    with connect() as conn:
        conn.execute("DELETE FROM oauth_states WHERE expires_at<?", (now,))
        conn.execute("INSERT INTO oauth_states VALUES(?,?,?,?,?,?)", (state, business_id, provider, redirect_uri, session_hash, now + ttl))


def take_oauth_state(state: str) -> dict[str, Any] | None:
    """Single use: the row is gone whether or not it turns out to be valid."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM oauth_states WHERE state=?", (state,)).fetchone()
        conn.execute("DELETE FROM oauth_states WHERE state=?", (state,))
    if not row or row["expires_at"] < time.time():
        return None
    return dict(row)


# ── capability modes ────────────────────────────────────────────────────────────

def capability_mode(business_id: str, agent_id: str, item: registry.Capability) -> str:
    with connect() as conn:
        row = conn.execute("SELECT mode FROM capability_modes WHERE business_id=? AND agent_id=? AND capability_id=?",
                           (business_id, agent_id, item.id)).fetchone()
    mode = row["mode"] if row else registry.default_mode(agent_id, item)
    return mode if mode in registry.allowed_modes(item) else registry.DISABLED


def set_capability_mode(business_id: str, agent_id: str, capability_id: str, mode: object) -> None:
    get_business(business_id)
    item = registry.capability(capability_id)
    if item is None or agent_id not in registry.AGENTS:
        raise StoreError("Unknown capability or agent", 404)
    if mode not in registry.allowed_modes(item):
        raise StoreError("This capability cannot use that mode")
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO capability_modes VALUES(?,?,?,?)", (business_id, agent_id, capability_id, mode))


# ── vault grants ────────────────────────────────────────────────────────────────

_VAULT_FLAGS = ("can_search", "can_read", "can_create", "can_edit")


def list_vault_grants(business_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM vault_grants WHERE business_id=? ORDER BY folder", (business_id,)).fetchall()
        agents = conn.execute(
            "SELECT a.* FROM vault_agent_grants a JOIN vault_grants g ON g.id=a.grant_id WHERE g.business_id=?", (business_id,)).fetchall()
    out = []
    for row in rows:
        grants = {a["agent_id"]: {flag: bool(a[flag]) for flag in _VAULT_FLAGS} for a in agents if a["grant_id"] == row["id"]}
        out.append({"id": row["id"], "business_id": business_id, "vault": row["vault"], "folder": row["folder"], "agents": grants})
    return out


def add_vault_grant(business_id: str, vault: str, folder: str) -> dict[str, Any]:
    get_business(business_id)
    grant_id = new_id("grant")
    with connect() as conn:
        try:
            conn.execute("INSERT INTO vault_grants VALUES(?,?,?,?,?)", (grant_id, business_id, vault, folder, time.time()))
        except sqlite3.IntegrityError as error:
            raise StoreError("This folder is already granted", 409) from error
    return next(item for item in list_vault_grants(business_id) if item["id"] == grant_id)


def remove_vault_grant(business_id: str, grant_id: str) -> None:
    with connect() as conn:
        row = conn.execute("SELECT 1 FROM vault_grants WHERE id=? AND business_id=?", (grant_id, business_id)).fetchone()
        if not row:
            raise StoreError("Grant not found", 404)
        conn.execute("DELETE FROM vault_agent_grants WHERE grant_id=?", (grant_id,))
        conn.execute("DELETE FROM vault_grants WHERE id=?", (grant_id,))


def set_vault_agent_grant(business_id: str, grant_id: str, agent_id: str, flags: object) -> None:
    if agent_id not in registry.AGENTS or not isinstance(flags, dict):
        raise StoreError("Unknown agent", 404)
    values = [int(flags.get(flag) is True) for flag in _VAULT_FLAGS]
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM vault_grants WHERE id=? AND business_id=?", (grant_id, business_id)).fetchone():
            raise StoreError("Grant not found", 404)
        conn.execute("INSERT OR REPLACE INTO vault_agent_grants VALUES(?,?,?,?,?,?)", (grant_id, agent_id, *values))


# ── tasks ───────────────────────────────────────────────────────────────────────

def _task(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["input"] = _loads(row["input"], {})
    data["depends_on"] = _loads(row["depends_on"], [])
    data["result"] = _loads(row["result"], None)
    data["needs_review"] = bool(row["needs_review"])
    return data


def create_task(business_id: str, agent_id: str, capability_id: str, payload: dict[str, Any], *, goal: str = "",
                parent_id: str | None = None, depends_on: list[str] | None = None, priority: int = 5,
                schedule_id: str | None = None) -> dict[str, Any]:
    get_business(business_id)
    item = registry.capability(capability_id)
    if item is None or agent_id not in registry.AGENTS:
        raise StoreError("Unknown capability or agent", 404)
    deps = list(depends_on or [])
    task_id, now = new_id("task"), time.time()
    with connect() as conn:
        for dep in [*deps, *([parent_id] if parent_id else [])]:
            if not conn.execute("SELECT 1 FROM tasks WHERE id=? AND business_id=?", (dep, business_id)).fetchone():
                raise StoreError("A linked task is not part of this business", 404)
        conn.execute(
            """INSERT INTO tasks(id,parent_id,business_id,agent_id,goal,capability_id,input,priority,status,depends_on,
                 max_retries,schedule_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (task_id, parent_id, business_id, agent_id, str(goal or item.label)[:500], capability_id, json.dumps(payload),
             int(priority), "waiting_dependency" if deps else "queued", json.dumps(deps), 3 if item.idempotent else 0,
             schedule_id, now, now))
    return get_task(task_id)


def get_task(task_id: str) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise StoreError("Task not found", 404)
    return _task(row)


def list_tasks(business_id: str | None = None, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    sql, args = "SELECT * FROM tasks WHERE 1=1", []
    if business_id:
        sql += " AND business_id=?"
        args.append(business_id)
    if status:
        sql += " AND status=?"
        args.append(status)
    with connect() as conn:
        rows = conn.execute(sql + " ORDER BY updated_at DESC LIMIT ?", (*args, max(1, min(limit, 500)))).fetchall()
    return [_task(row) for row in rows]


def update_task(task_id: str, **values: Any) -> None:
    allowed = {"status", "retries", "not_before", "approval_id", "error", "needs_review", "started_at", "finished_at"}
    fields = {key: value for key, value in values.items() if key in allowed}
    if "result" in values:
        fields["result"] = json.dumps(values["result"])
    fields["updated_at"] = time.time()
    assignments = ", ".join(f"{key}=?" for key in fields)
    with connect() as conn:
        conn.execute(f"UPDATE tasks SET {assignments} WHERE id=?", (*fields.values(), task_id))


def claim_task(task_id: str, from_status: str, to_status: str) -> bool:
    """Atomic state change; False means another worker or a cancel got there first."""
    with connect() as conn:
        cursor = conn.execute("UPDATE tasks SET status=?, updated_at=? WHERE id=? AND status=?",
                              (to_status, time.time(), task_id, from_status))
        return cursor.rowcount == 1


# ── approvals ───────────────────────────────────────────────────────────────────

def _approval(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["payload"] = _loads(row["payload"], {})
    return data


def create_approval(task: dict[str, Any], item: registry.Capability, payload: dict[str, Any], payload_hash: str,
                    target: str, ttl: int = 86_400) -> dict[str, Any]:
    approval_id, now = new_id("appr"), time.time()
    with connect() as conn:
        conn.execute(
            """INSERT INTO approvals(id,business_id,task_id,agent_id,capability_id,provider,target,payload,payload_hash,risk,
                 status,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (approval_id, task["business_id"], task["id"], task["agent_id"], item.id, item.provider, target,
             json.dumps(payload), payload_hash, item.risk, "pending", now, now + ttl))
    return get_approval(approval_id)


def get_approval(approval_id: str) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
    if not row:
        raise StoreError("Approval not found", 404)
    return _approval(row)


def list_approvals(business_id: str, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    sql, args = "SELECT * FROM approvals WHERE business_id=?", [business_id]
    if status:
        sql += " AND status=?"
        args.append(status)
    with connect() as conn:
        rows = conn.execute(sql + " ORDER BY created_at DESC LIMIT ?", (*args, limit)).fetchall()
    return [_approval(row) for row in rows]


def move_approval(approval_id: str, from_status: str, to_status: str) -> bool:
    now = time.time()
    column = "decided_at" if from_status == "pending" else "finished_at"
    with connect() as conn:
        cursor = conn.execute(f"UPDATE approvals SET status=?, {column}=? WHERE id=? AND status=?",
                              (to_status, now, approval_id, from_status))
        return cursor.rowcount == 1


# ── audit ───────────────────────────────────────────────────────────────────────

def audit(business_id: str, *, actor: str, decision: str, agent_id: str = "", task_id: str = "", provider: str = "",
          capability_id: str = "", target: str = "", outcome: str = "", detail: str = "") -> None:
    from api.helpers import _redact_text

    with connect() as conn:
        conn.execute(
            """INSERT INTO audit(ts,business_id,actor,agent_id,task_id,provider,capability_id,target,decision,outcome,detail)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (time.time(), business_id, actor, agent_id, task_id, provider, capability_id, target[:300], decision, outcome,
             _redact_text(detail, _enabled=True)[:500]))


def list_audit(business_id: str, *, agent_id: str = "", provider: str = "", outcome: str = "", task_id: str = "",
               since: float = 0, limit: int = 200) -> list[dict[str, Any]]:
    sql, args = "SELECT * FROM audit WHERE business_id=? AND ts>=?", [business_id, since]
    for column, value in (("agent_id", agent_id), ("provider", provider), ("outcome", outcome), ("task_id", task_id)):
        if value:
            sql += f" AND {column}=?"
            args.append(value)
    with connect() as conn:
        rows = conn.execute(sql + " ORDER BY id DESC LIMIT ?", (*args, max(1, min(limit, 500)))).fetchall()
    return [dict(row) for row in rows]


# ── schedules ───────────────────────────────────────────────────────────────────

def list_schedules(business_id: str | None = None) -> list[dict[str, Any]]:
    sql, args = "SELECT * FROM schedules", []
    if business_id:
        sql += " WHERE business_id=?"
        args.append(business_id)
    with connect() as conn:
        rows = conn.execute(sql + " ORDER BY name", args).fetchall()
    return [{**dict(row), "input": _loads(row["input"], {}), "enabled": bool(row["enabled"])} for row in rows]


def create_schedule(business_id: str, agent_id: str, name: object, capability_id: str, payload: dict[str, Any],
                    every_minutes: object) -> dict[str, Any]:
    get_business(business_id)
    item = registry.capability(capability_id)
    if item is None or agent_id not in registry.AGENTS:
        raise StoreError("Unknown capability or agent", 404)
    if item.risk != registry.READ:
        raise StoreError("Only read capabilities can run on a schedule")
    if isinstance(every_minutes, bool) or not isinstance(every_minutes, int) or not 5 <= every_minutes <= 10_080:
        raise StoreError("Run every 5 minutes to 7 days")
    schedule_id, now = new_id("sched"), time.time()
    with connect() as conn:
        conn.execute("INSERT INTO schedules(id,business_id,agent_id,name,capability_id,input,every_minutes,next_run_at) VALUES(?,?,?,?,?,?,?,?)",
                     (schedule_id, business_id, agent_id, str(name or item.label)[:100], capability_id, json.dumps(payload),
                      every_minutes, now + every_minutes * 60))
    return next(row for row in list_schedules(business_id) if row["id"] == schedule_id)


def delete_schedule(business_id: str, schedule_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM schedules WHERE id=? AND business_id=?", (schedule_id, business_id))


def advance_schedule(schedule_id: str, every_minutes: int, due_at: float, now: float) -> bool:
    """Claim one run; a second scheduler pass over the same slot gets False."""
    with connect() as conn:
        cursor = conn.execute("UPDATE schedules SET next_run_at=?, last_run_at=? WHERE id=? AND next_run_at=?",
                              (now + every_minutes * 60, now, schedule_id, due_at))
        return cursor.rowcount == 1
