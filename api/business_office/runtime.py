"""Durable task runner, inside the WebUI process.

Tasks live in SQLite, so a restart loses nothing. On start, a task that was
running is retried only when its capability is idempotent; anything else may
already have happened and goes to review instead of running twice.

One thread picks work; each task runs on its own short-lived thread within the
business's parallel limits.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any

from api.business_office import registry, service, store
from api.business_office.errors import ToolError

logger = logging.getLogger(__name__)
TICK_SECONDS = 2.0
GLOBAL_LIMIT = 6
_BACKOFF_BASE = 5.0
_BACKOFF_MAX = 300.0

_lock = threading.Lock()
_running: dict[str, dict[str, Any]] = {}
_thread: threading.Thread | None = None
_stop = threading.Event()


def backoff(retries: int) -> float:
    delay = min(_BACKOFF_MAX, _BACKOFF_BASE * (2 ** retries))
    return delay * (0.75 + random.random() * 0.5)


def recover() -> None:
    """Settle tasks a previous process left mid-flight."""
    for status in ("assigned", "running"):
        for task in store.list_tasks(status=status, limit=500):
            item = registry.capability(task["capability_id"])
            if item is not None and item.idempotent:
                store.update_task(task["id"], status="queued")
            else:
                store.update_task(task["id"], status="failed", needs_review=1, finished_at=time.time(),
                                  error="The server restarted during this action. Check whether it happened.")
                if task["approval_id"]:
                    store.move_approval(task["approval_id"], "executing", "uncertain")
                store.audit(task["business_id"], actor="system", agent_id=task["agent_id"], task_id=task["id"],
                            capability_id=task["capability_id"], decision="recovered", outcome="needs_review")


def _release_dependents() -> None:
    for task in store.list_tasks(status="waiting_dependency", limit=500):
        states = [store.get_task(dep)["status"] for dep in task["depends_on"]]
        if any(state in ("failed", "cancelled") for state in states):
            if store.claim_task(task["id"], "waiting_dependency", "cancelled"):
                store.update_task(task["id"], error="A task this depends on did not finish", finished_at=time.time())
        elif all(state == "completed" for state in states):
            store.claim_task(task["id"], "waiting_dependency", "queued")


def _enqueue_schedules(now: float) -> None:
    for schedule in store.list_schedules():
        if not schedule["enabled"] or schedule["next_run_at"] > now:
            continue
        if store.advance_schedule(schedule["id"], schedule["every_minutes"], schedule["next_run_at"], now):
            store.create_task(schedule["business_id"], schedule["agent_id"], schedule["capability_id"], schedule["input"],
                              goal=schedule["name"], schedule_id=schedule["id"])


def _fits(task: dict[str, Any], settings: dict[str, Any]) -> bool:
    rows = list(_running.values())
    if len(rows) >= GLOBAL_LIMIT:
        return False
    same_business = [row for row in rows if row["business_id"] == task["business_id"]]
    item = registry.capability(task["capability_id"])
    provider = item.provider if item else ""
    return (len(same_business) < settings["max_parallel"]
            and sum(row["agent_id"] == task["agent_id"] for row in same_business) < settings["max_parallel_per_agent"]
            and sum(row["provider"] == provider for row in same_business) < settings["max_parallel_per_provider"])


def _finish_error(task: dict[str, Any], error: ToolError) -> None:
    item = registry.capability(task["capability_id"])
    fresh = store.get_task(task["id"])
    if error.kind == "paused":
        store.update_task(task["id"], status="queued", not_before=time.time() + 30)
        return
    if (error.kind in ToolError.RETRYABLE and item is not None and item.idempotent
            and fresh["retries"] < fresh["max_retries"]):
        wait = max(error.retry_after, backoff(fresh["retries"]))
        store.update_task(task["id"], status="queued", retries=fresh["retries"] + 1, not_before=time.time() + wait, error=str(error))
        return
    store.update_task(task["id"], status="failed", error=str(error), finished_at=time.time(),
                      needs_review=int(error.kind == "uncertain"))


def _execute(task: dict[str, Any]) -> None:
    try:
        if not store.claim_task(task["id"], "assigned", "running"):
            return
        store.update_task(task["id"], started_at=time.time())
        outcome = service.run_task(task["id"])
        if outcome["status"] == "completed":
            if store.claim_task(task["id"], "running", "completed"):
                store.update_task(task["id"], result=outcome.get("result"), error="", finished_at=time.time())
    except ToolError as error:
        _finish_error(task, error)
    except Exception:
        logger.exception("Business Office task failed")
        store.update_task(task["id"], status="failed", needs_review=1, finished_at=time.time(),
                          error="Something went wrong. Check the result before trying again.")
    finally:
        with _lock:
            _running.pop(task["id"], None)


def tick(now: float | None = None) -> list[threading.Thread]:
    """One pass: release, schedule, start what fits. Returns the started threads."""
    now = time.time() if now is None else now
    _release_dependents()
    _enqueue_schedules(now)
    businesses = {business["id"]: business for business in store.list_businesses()}
    ready = [task for task in store.list_tasks(status="queued", limit=500) if task["not_before"] <= now]
    ready.sort(key=lambda task: (task["priority"], task["created_at"]))
    started = []
    for task in ready:
        business = businesses.get(task["business_id"])
        if business is None or business["paused"] or task["agent_id"] in business["paused_agents"]:
            continue
        with _lock:
            if not _fits(task, business["settings"]) or not store.claim_task(task["id"], "queued", "assigned"):
                continue
            item = registry.capability(task["capability_id"])
            _running[task["id"]] = {"business_id": task["business_id"], "agent_id": task["agent_id"],
                                    "provider": item.provider if item else ""}
        thread = threading.Thread(target=_execute, args=(task,), name=f"business-task-{task['id']}", daemon=True)
        thread.start()
        started.append(thread)
    return started


def cancel(business_id: str, task_id: str) -> dict[str, Any]:
    task = store.get_task(task_id)
    if task["business_id"] != business_id:
        raise store.StoreError("Task not found", 404)
    for status in ("queued", "waiting_dependency", "waiting_approval", "created"):
        if store.claim_task(task_id, status, "cancelled"):
            store.update_task(task_id, finished_at=time.time(), error="Cancelled")
            store.audit(business_id, actor="user", agent_id=task["agent_id"], task_id=task_id, decision="cancelled")
            return store.get_task(task_id)
    raise store.StoreError("This task can no longer be cancelled", 409)


def _loop() -> None:
    try:
        recover()
    except Exception:
        logger.exception("Business Office recovery failed")
    while not _stop.wait(TICK_SECONDS):
        try:
            tick()
        except Exception:
            logger.exception("Business Office tick failed")


def start() -> bool:
    global _thread
    if _thread is not None and _thread.is_alive():
        return False
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="business-office-runtime", daemon=True)
    _thread.start()
    return True
