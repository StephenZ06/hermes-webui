"""The one door to every provider call.

Business and agent come from the server-owned task row, never from model or
browser arguments, and every rule is rechecked here at the moment of the call.
No route or agent tool reaches an adapter except through :func:`run_task`.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from api.business_office import crypto, registry, store
from api.business_office.adapters import gmail, meta, obsidian
from api.business_office.errors import ToolError, denied

_ADAPTERS = {"gmail": gmail, "threads": meta, "instagram": meta, "obsidian": obsidian}


def _hash(capability_id: str, content: dict[str, Any]) -> str:
    canonical = json.dumps({"capability": capability_id, "content": content}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _target(content: dict[str, Any]) -> str:
    for key in ("to", "path", "folder", "draft_id"):
        if content.get(key):
            return str(content[key])
    return ""


def _check_scope(item: registry.Capability, connection: dict[str, Any]) -> None:
    missing = [scope for scope in item.scopes if scope not in connection["scopes"]]
    if missing:
        raise ToolError("permission", "The connected account did not grant this permission")


def _authorize(task: dict[str, Any], item: registry.Capability) -> tuple[str, dict[str, Any]]:
    business = store.get_business(task["business_id"])
    if not business["active"]:
        raise denied("This business is not active")
    if business["paused"] or task["agent_id"] in business["paused_agents"]:
        raise ToolError("paused", "Paused")
    mode = store.capability_mode(task["business_id"], task["agent_id"], item)
    if mode == registry.DISABLED:
        raise denied("This capability is off for this agent")
    values = registry.validate_input(item, task["input"])
    provider = registry.provider(item.provider)
    if provider is not None and provider.auth == "oauth":
        connection = store.get_connection(task["business_id"], item.provider)
        if connection is None or connection["status"] not in ("connected", "degraded", "unavailable"):
            raise ToolError("not_connected", "This account is not connected")
        _check_scope(item, connection)
    return mode, values


def _call(item: registry.Capability, task: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    adapter = _ADAPTERS[item.provider]
    if item.provider == "obsidian":
        return adapter.invoke(item.id, values, task["business_id"], task["agent_id"])
    return adapter.invoke(item.id, values, task["business_id"])


def _request_approval(task: dict[str, Any], item: registry.Capability, values: dict[str, Any]) -> dict[str, Any]:
    content = _ADAPTERS[item.provider].preview(item.id, values, task["business_id"])
    approval = store.create_approval(task, item, content, _hash(item.id, content), _target(content))
    store.update_task(task["id"], status="waiting_approval", approval_id=approval["id"])
    store.audit(task["business_id"], actor=f"agent:{task['agent_id']}", agent_id=task["agent_id"], task_id=task["id"],
                provider=item.provider, capability_id=item.id, target=approval["target"], decision="approval_requested",
                outcome="waiting")
    return {"status": "waiting_approval", "approval_id": approval["id"]}


def _claim_approval(task: dict[str, Any], item: registry.Capability, values: dict[str, Any]) -> dict[str, Any]:
    """Prove this exact action was approved, then take the approval for one use."""
    approval = store.get_approval(task["approval_id"])
    if (approval["business_id"], approval["task_id"], approval["capability_id"]) != (task["business_id"], task["id"], item.id):
        raise denied("That approval belongs to a different action")
    if approval["status"] != "approved":
        raise denied("This action has not been approved")
    if approval["expires_at"] < time.time():
        store.move_approval(approval["id"], "approved", "expired")
        raise denied("This approval expired")
    content = _ADAPTERS[item.provider].preview(item.id, values, task["business_id"])
    if _hash(item.id, content) != approval["payload_hash"]:
        store.move_approval(approval["id"], "approved", "stale")
        raise denied("The content changed after it was approved")
    if not store.move_approval(approval["id"], "approved", "executing"):
        raise denied("This approval was already used")
    return approval


def _note_connection(business_id: str, provider_id: str, kind: str, message: str) -> None:
    """Keep the visible connection state true to the last real call."""
    connection = store.get_connection(business_id, provider_id)
    if connection is None:
        return
    if kind == "ok":
        if connection["status"] != "degraded":
            store.mark_connection(business_id, provider_id, "connected")
    elif kind == "auth_expired":
        store.mark_connection(business_id, provider_id, "unauthorized", message)
    elif kind in ("timeout", "unavailable", "rate_limited"):
        store.mark_connection(business_id, provider_id, "unavailable", message)


def run_task(task_id: str) -> dict[str, Any]:
    """Run one task's capability under every check. Returns ``{status, ...}``."""
    task = store.get_task(task_id)
    item = registry.capability(task["capability_id"])
    if item is None:
        raise denied("Unknown capability")
    actor = f"agent:{task['agent_id']}"
    common = {"actor": actor, "agent_id": task["agent_id"], "task_id": task_id, "provider": item.provider, "capability_id": item.id}
    approval = None
    try:
        mode, values = _authorize(task, item)
        needs_approval = item.requires_approval or mode == registry.APPROVAL
        if needs_approval and not task["approval_id"]:
            return _request_approval(task, item, values)
        if needs_approval:
            approval = _claim_approval(task, item, values)
        result = _call(item, task, values)
    except (ToolError, ValueError, store.StoreError, crypto.SecretError) as error:
        kind = error.kind if isinstance(error, ToolError) else "rejected"
        if approval is not None:
            # An external write that failed part-way may still have happened.
            definite = isinstance(error, ToolError) and error.kind in ("denied", "not_connected", "permission", "not_found", "rejected")
            store.move_approval(approval["id"], "executing", "failed" if definite else "uncertain")
            if not definite:
                error = ToolError("uncertain", "The provider did not confirm this. Check it before trying again.")
                kind = "uncertain"
        _note_connection(task["business_id"], item.provider, kind, str(error))
        store.audit(task["business_id"], decision="blocked" if kind in ("denied", "paused") else "called",
                    outcome=kind, detail=str(error), **common)
        raise error if isinstance(error, ToolError) else ToolError("rejected", str(error)) from None
    if approval is not None:
        store.move_approval(approval["id"], "executing", "executed")
    _note_connection(task["business_id"], item.provider, "ok", "")
    store.audit(task["business_id"], decision="approved_call" if approval else "called", outcome="ok",
                target=_target({**values, **(result if isinstance(result, dict) else {})}), **common)
    return {"status": "completed", "result": result}


def decide_approval(business_id: str, approval_id: str, approve: bool) -> dict[str, Any]:
    approval = store.get_approval(approval_id)
    if approval["business_id"] != business_id:
        raise store.StoreError("Approval not found", 404)
    if approval["expires_at"] < time.time():
        store.move_approval(approval_id, "pending", "expired")
        raise store.StoreError("This approval expired", 409)
    if not store.move_approval(approval_id, "pending", "approved" if approve else "rejected"):
        raise store.StoreError("This approval was already decided", 409)
    if approve:
        store.claim_task(approval["task_id"], "waiting_approval", "queued")
    elif store.claim_task(approval["task_id"], "waiting_approval", "cancelled"):
        store.update_task(approval["task_id"], error="Rejected", finished_at=time.time())
    store.audit(business_id, actor="user", agent_id=approval["agent_id"], task_id=approval["task_id"], provider=approval["provider"],
                capability_id=approval["capability_id"], target=approval["target"], decision="approved" if approve else "rejected")
    return store.get_approval(approval_id)
