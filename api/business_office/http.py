"""HTTP surface of the Business Office, under ``/api/office/business/``.

Every response is built from public fields; tokens and client secrets have no
path to the browser. POST routes run behind the WebUI's auth and CSRF checks.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from api import notebook_vault as vault
from api.business_office import crypto, oauth, registry, runtime, service, store
from api.business_office.adapters import obsidian
from api.business_office.errors import ToolError

PREFIX = "/api/office/business/"
_FOLDER_DEPTH = 2
_FOLDER_CAP = 300


def _vault_root() -> Path | None:
    try:
        return vault._root()
    except vault.NotebookError:
        return None


def _vault_folders(root: Path) -> list[str]:
    found: list[str] = []
    pending = [(root, 0)]
    while pending and len(found) < _FOLDER_CAP:
        here, depth = pending.pop()
        try:
            with os.scandir(here) as entries:
                names = sorted(e.name for e in entries if not e.name.startswith(".") and e.is_dir(follow_symlinks=False))
        except OSError:
            continue
        for name in reversed(names):
            path = here / name
            found.append(path.relative_to(root).as_posix())
            if depth + 1 < _FOLDER_DEPTH:
                pending.append((path, depth + 1))
    return sorted(found)


def _provider_row(business_id: str, provider: registry.Provider, connections: dict[str, dict[str, Any]],
                  grants: list[dict[str, Any]], root: Path | None) -> dict[str, Any]:
    row = {"id": provider.id, "name": provider.name, "floor": provider.floor, "purpose": provider.purpose,
           "pricing": provider.pricing, "auth": provider.auth, "state": provider.state, "phase": provider.phase,
           "status": "planned", "account": "", "last_sync_at": 0, "last_error": "", "scopes": [], "capabilities": []}
    if provider.state != "adapter":
        return row
    if provider.auth == "vault":
        current = [grant for grant in grants if root is not None and grant["vault"] == str(root)]
        row["status"] = "unavailable" if root is None else ("connected" if current else "configured")
        row["account"] = root.name if root else ""
    else:
        app = oauth.app_for(provider.id)
        connection = connections.get(provider.id)
        row["oauth_app"] = app.id
        row["app_configured"] = store.oauth_app_configured(app.id)
        row["console_url"] = app.console_url
        row["status"] = connection["status"] if connection else ("configured" if row["app_configured"] else "not_configured")
        if connection:
            row.update(account=connection["account_label"], last_sync_at=connection["last_sync_at"],
                       last_error=connection["last_error"], scopes=connection["scopes"])
    row["capabilities"] = [
        {**registry.public_capability(item),
         "modes": {agent: store.capability_mode(business_id, agent, item) for agent in registry.AGENTS}}
        for item in registry.provider_capabilities(provider.id)
    ]
    return row


def overview(business_id: str, base_url: str) -> dict[str, Any]:
    businesses = store.list_businesses()
    if not business_id:
        business_id = businesses[0]["id"] if businesses else ""
    business = store.get_business(business_id)
    connections = {row["provider"]: row for row in store.list_connections(business_id)}
    grants = store.list_vault_grants(business_id)
    root = _vault_root()
    providers = [_provider_row(business_id, provider, connections, grants, root) for provider in registry.PROVIDERS]
    tasks = store.list_tasks(business_id, limit=50)
    failure = next((row for row in store.list_audit(business_id, limit=20)
                    if row["decision"] == "oauth_finished" and row["outcome"] == "failed" and row["ts"] > time.time() - 120), None)
    return {
        "businesses": businesses, "business": business, "agents": list(registry.AGENTS), "floors": list(registry.FLOORS),
        "providers": providers, "redirect_uri": oauth.redirect_uri(base_url), "key_source": crypto.key_source(),
        "oauth_apps": {app.id: {"label": app.label, "configured": store.oauth_app_configured(app.id), "console_url": app.console_url}
                       for app in oauth.APPS.values()},
        "vault": {"connected": root is not None, "name": root.name if root else "",
                  "folders": _vault_folders(root) if root else [],
                  "grants": [{**grant, "vault": Path(grant["vault"]).name, "current": root is not None and grant["vault"] == str(root)}
                             for grant in grants]},
        "pending_approvals": store.list_approvals(business_id, status="pending"),
        "tasks": [_public_task(task) for task in tasks],
        "schedules": store.list_schedules(business_id),
        "oauth_failure": failure["detail"] if failure else "",
    }


def _public_task(task: dict[str, Any]) -> dict[str, Any]:
    return {key: task[key] for key in ("id", "parent_id", "business_id", "agent_id", "goal", "capability_id", "status", "priority",
                                       "retries", "error", "needs_review", "approval_id", "result", "created_at", "started_at",
                                       "finished_at", "updated_at")}


def live() -> dict[str, Any]:
    """Every business's open and just-finished work, for the Office floor."""
    names = {business["id"]: business["name"] for business in store.list_businesses()}
    cutoff = time.time() - 300
    rows = [task for task in store.list_tasks(limit=200)
            if task["status"] in store.OPEN_TASK_STATES or task["finished_at"] > cutoff]
    tasks = []
    for task in rows:
        item = registry.capability(task["capability_id"])
        public = _public_task(task)
        public.pop("result")
        tasks.append({**public, "business_name": names.get(task["business_id"], ""), "provider": item.provider if item else ""})
    connections = [row for business in names for row in store.list_connections(business)]
    pending = sum(len(store.list_approvals(business, status="pending")) for business in names)
    return {"tasks": tasks, "health": {"connected": sum(row["status"] == "connected" for row in connections),
                                       "attention": sum(row["status"] in ("degraded", "unauthorized", "unavailable") for row in connections),
                                       "pending_approvals": pending}}


def _one(query: dict[str, list[str]], key: str) -> str:
    return str(query.get(key, [""])[0] or "").strip()


def handle_get(path: str, query_string: str, base_url: str) -> dict[str, Any]:
    query = parse_qs(query_string or "")
    business_id = _one(query, "business_id")
    if path == "overview":
        return overview(business_id, base_url)
    if path == "live":
        return live()
    store.get_business(business_id)
    if path == "approvals":
        return {"approvals": store.list_approvals(business_id, status=_one(query, "status") or None)}
    if path == "tasks":
        return {"tasks": [_public_task(task) for task in store.list_tasks(business_id, status=_one(query, "status") or None)]}
    if path == "audit":
        try:
            since = float(_one(query, "since") or 0)
        except ValueError:
            since = 0
        return {"audit": store.list_audit(business_id, agent_id=_one(query, "agent"), provider=_one(query, "provider"),
                                          outcome=_one(query, "outcome"), task_id=_one(query, "task"), since=since)}
    raise store.StoreError("Not found", 404)


def _text(body: dict[str, Any], key: str) -> str:
    return str(body.get(key) or "").strip()


def _create_task(business_id: str, body: dict[str, Any]) -> dict[str, Any]:
    payload = body.get("input") if isinstance(body.get("input"), dict) else {}
    item = registry.capability(_text(body, "capability_id"))
    if item is None:
        raise store.StoreError("Unknown capability", 404)
    depends = body.get("depends_on") if isinstance(body.get("depends_on"), list) else []
    task = store.create_task(business_id, _text(body, "agent_id"), item.id, payload, goal=_text(body, "goal"),
                             depends_on=[str(dep) for dep in depends])
    store.audit(business_id, actor="user", agent_id=task["agent_id"], task_id=task["id"], provider=item.provider,
                capability_id=item.id, decision="task_created")
    return {"task": _public_task(task)}


def _add_grant(business_id: str, body: dict[str, Any]) -> dict[str, Any]:
    root = _vault_root()
    if root is None:
        raise store.StoreError("No Obsidian vault is connected", 409)
    folder = obsidian.normal_folder(root, body.get("folder"))
    grant = store.add_vault_grant(business_id, str(root), folder)
    store.audit(business_id, actor="user", provider="obsidian", target=folder, decision="folder_granted")
    return {"grant": {**grant, "vault": root.name}}


def handle_post(path: str, body: dict[str, Any], base_url: str, cookie_value: str) -> dict[str, Any]:
    if path == "businesses/create":
        return {"business": store.create_business(body.get("name"), body.get("kind"), body.get("description"))}
    if path == "oauth/app":
        app = _text(body, "app")
        if app not in oauth.APPS:
            raise store.StoreError("Unknown app", 404)
        store.save_oauth_app(app, body.get("client_id"), body.get("client_secret"))
        return {"ok": True}
    business_id = _text(body, "business_id")
    store.get_business(business_id)
    if path == "settings":
        return {"business": store.update_settings(business_id, body.get("settings"))}
    if path == "pause":
        agent = _text(body, "agent_id") or None
        paused = body.get("paused") is True
        business = store.set_paused(business_id, paused, agent)
        store.audit(business_id, actor="user", agent_id=agent or "", decision="paused" if paused else "resumed")
        return {"business": business}
    if path == "oauth/start":
        return {"url": oauth.start(business_id, _text(body, "provider"), base_url, cookie_value)}
    if path == "connections/disconnect":
        oauth.disconnect(business_id, _text(body, "provider"))
        return {"ok": True}
    if path == "capabilities/mode":
        store.set_capability_mode(business_id, _text(body, "agent_id"), _text(body, "capability_id"), body.get("mode"))
        store.audit(business_id, actor="user", agent_id=_text(body, "agent_id"), capability_id=_text(body, "capability_id"),
                    decision="mode_changed", outcome=str(body.get("mode")))
        return {"ok": True}
    if path == "vault/grants/add":
        return _add_grant(business_id, body)
    if path == "vault/grants/remove":
        store.remove_vault_grant(business_id, _text(body, "grant_id"))
        store.audit(business_id, actor="user", provider="obsidian", decision="folder_removed")
        return {"ok": True}
    if path == "vault/grants/agent":
        store.set_vault_agent_grant(business_id, _text(body, "grant_id"), _text(body, "agent_id"), body.get("flags"))
        store.audit(business_id, actor="user", agent_id=_text(body, "agent_id"), provider="obsidian", decision="folder_permissions_changed")
        return {"ok": True}
    if path == "tasks/create":
        return _create_task(business_id, body)
    if path == "tasks/cancel":
        return {"task": _public_task(runtime.cancel(business_id, _text(body, "task_id")))}
    if path == "approvals/decide":
        return {"approval": service.decide_approval(business_id, _text(body, "approval_id"), body.get("approve") is True)}
    if path == "schedules/create":
        payload = body.get("input") if isinstance(body.get("input"), dict) else {}
        return {"schedule": store.create_schedule(business_id, _text(body, "agent_id"), body.get("name"), _text(body, "capability_id"),
                                                  payload, body.get("every_minutes"))}
    if path == "schedules/delete":
        store.delete_schedule(business_id, _text(body, "schedule_id"))
        return {"ok": True}
    raise store.StoreError("Not found", 404)


def finish_oauth(query_string: str, cookie_value: str) -> str:
    """Handle the provider's redirect and return where to send the browser."""
    query = parse_qs(query_string or "")
    state, code = _one(query, "state"), _one(query, "code")
    target = "/#office/integrations"
    if _one(query, "error") or not code:
        row = store.take_oauth_state(state)
        if row is not None:
            store.audit(row["business_id"], actor="user", decision="oauth_finished", provider=row["provider"],
                        outcome="failed", detail="The sign-in was cancelled.")
        return target
    try:
        oauth.finish(state, code, cookie_value)
    except (ToolError, store.StoreError, crypto.SecretError):
        pass  # recorded by oauth.finish where a business is known; the page shows the state
    return target
