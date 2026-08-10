"""Crews (multi-agent dispatch templates) API tests.

CRUD (create/update/delete/duplicate/list) is pure profile-scoped JSON
storage with no hermes_cli dependency, so it's tested via HTTP round-trip
against the live test server, mirroring tests/test_agent_definitions_api.py.

Dispatch calls through to api.kanban_bridge._create_task_payload, which in
turn needs hermes_cli.kanban_db. Mirroring tests/test_kanban_bridge.py, CI
for hermes-webui does not install hermes-agent, so the dispatch tests inject
a tiny fake ``hermes_cli.kanban_db`` module and call api.crews.dispatch_crew()
directly rather than depending on a real agent checkout being mounted.

See docs/HERMES_STUDIO_PARITY_PLAN.md, "Multi-agent orchestration (Crews +
Conductor)" -> "Phase 1 (v1) -- Crew templates + bulk dispatch".
"""
import importlib
import json
import sys
import time
import types
import urllib.error
import urllib.request
from dataclasses import dataclass
from types import SimpleNamespace

from tests._pytest_port import BASE


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return json.loads(r.read()), r.status


def post(path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(BASE + path, data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code


def make_crew(created_list, **overrides):
    body = {
        "name": "Test Crew",
        "description": "A crew for testing",
        "tasks": [{"title": "Do the thing", "assignee": "webui-test"}],
    }
    body.update(overrides)
    d, status = post("/api/crews/create", body)
    assert status == 200, f"create failed: {d}"
    cid = d["crew"]["id"]
    created_list.append(cid)
    return cid, d["crew"]


def cleanup_crews(ids):
    for cid in ids:
        try:
            post("/api/crews/delete", {"id": cid})
        except Exception:
            pass


# ── CRUD round-trip ─────────────────────────────────────────────────────

def test_list_starts_as_dict_with_crews_key():
    d, status = get("/api/crews")
    assert status == 200
    assert "crews" in d
    assert isinstance(d["crews"], list)


def test_create_crew_appears_in_list():
    cids = []
    try:
        cid, crew = make_crew(cids, name="Research crew", icon="\U0001F52C")
        assert len(cid) == 12
        assert crew["name"] == "Research crew"
        assert crew["icon"] == "\U0001F52C"
        assert len(crew["tasks"]) == 1
        assert "created_at" in crew and "updated_at" in crew

        d, status = get("/api/crews")
        assert status == 200
        ids = [c["id"] for c in d["crews"]]
        assert cid in ids
    finally:
        cleanup_crews(cids)


def test_create_requires_name():
    d, status = post("/api/crews/create", {"tasks": [{"title": "x"}]})
    assert status == 400
    assert "error" in d


def test_create_requires_at_least_one_task():
    d, status = post("/api/crews/create", {"name": "Empty crew", "tasks": []})
    assert status == 400


def test_create_requires_task_title():
    d, status = post("/api/crews/create", {"name": "No title", "tasks": [{"body": "no title here"}]})
    assert status == 400


def test_create_allows_task_with_no_assignee():
    """Phase 1 open question #1 -- resolved as 'allow it': assignee
    validation happens at kb.create_task time, not duplicated here."""
    cids = []
    try:
        cid, crew = make_crew(cids, tasks=[{"title": "Unassigned task"}])
        assert crew["tasks"][0]["assignee"] is None
    finally:
        cleanup_crews(cids)


def test_update_crew():
    cids = []
    try:
        cid, _ = make_crew(cids, name="Original")
        d, status = post("/api/crews/update", {"id": cid, "name": "Renamed", "description": "New desc"})
        assert status == 200
        assert d["crew"]["name"] == "Renamed"
        assert d["crew"]["description"] == "New desc"

        d2, _ = get("/api/crews")
        match = next(c for c in d2["crews"] if c["id"] == cid)
        assert match["name"] == "Renamed"
    finally:
        cleanup_crews(cids)


def test_update_nonexistent_returns_404():
    d, status = post("/api/crews/update", {"id": "does-not-exist", "name": "x"})
    assert status == 404


def test_delete_removes_crew():
    cid, _ = make_crew([], name="Deleteme")
    d, status = post("/api/crews/delete", {"id": cid})
    assert status == 200
    assert d["ok"] is True

    d2, _ = get("/api/crews")
    ids = [c["id"] for c in d2["crews"]]
    assert cid not in ids


def test_delete_requires_id():
    d, status = post("/api/crews/delete", {})
    assert status == 400


def test_delete_nonexistent_returns_404():
    d, status = post("/api/crews/delete", {"id": "does-not-exist"})
    assert status == 404


def test_duplicate_produces_new_row_with_independent_tasks():
    cids = []
    try:
        cid, original = make_crew(cids, name="Original", tasks=[{"title": "T1", "skills": ["python"]}])
        dup, status = post("/api/crews/duplicate", {"id": cid})
        assert status == 200
        new_crew = dup["crew"]
        cids.append(new_crew["id"])
        assert new_crew["id"] != cid
        assert new_crew["name"] == original["name"] + " (copy)"
        assert new_crew["tasks"] == original["tasks"]
        assert new_crew["tasks"] is not original["tasks"]

        # Mutating the copy's tasks via update must not affect the original.
        post("/api/crews/update", {"id": new_crew["id"], "tasks": [{"title": "Changed"}]})
        d, _ = get("/api/crews")
        orig_row = next(c for c in d["crews"] if c["id"] == cid)
        assert orig_row["tasks"][0]["title"] == "T1"
    finally:
        cleanup_crews(cids)


def test_duplicate_nonexistent_returns_404():
    d, status = post("/api/crews/duplicate", {"id": "does-not-exist"})
    assert status == 404


# ── Caps ─────────────────────────────────────────────────────────────────

def test_name_capped_at_128_chars():
    cids = []
    try:
        cid, crew = make_crew(cids, name="x" * 500)
        assert len(crew["name"]) == 128
    finally:
        cleanup_crews(cids)


def test_description_over_cap_rejected_via_truncation():
    cids = []
    try:
        cid, crew = make_crew(cids, description="y" * 1000)
        assert len(crew["description"]) == 512
    finally:
        cleanup_crews(cids)


def test_invalid_color_rejected():
    d, status = post("/api/crews/create", {
        "name": "Bad color", "color": "not-a-color", "tasks": [{"title": "x"}],
    })
    assert status == 400


def test_too_many_task_specs_rejected():
    d, status = post("/api/crews/create", {
        "name": "Too many tasks",
        "tasks": [{"title": f"t{i}"} for i in range(25)],
    })
    assert status == 400


def test_task_skills_capped_at_10_items():
    cids = []
    try:
        cid, crew = make_crew(cids, tasks=[{"title": "x", "skills": [f"s{i}" for i in range(20)]}])
        assert len(crew["tasks"][0]["skills"]) == 10
    finally:
        cleanup_crews(cids)


# ── Profile isolation ────────────────────────────────────────────────────

def test_profile_isolation(tmp_path, monkeypatch):
    """Two profiles must never see each other's crews.

    Unit-level (not HTTP) since it targets the storage layer directly, same
    approach as test_agent_definitions_api.py's test_profile_isolation.
    """
    from api import crews

    home_a = tmp_path / "profile-a"
    home_b = tmp_path / "profile-b"
    home_a.mkdir()
    home_b.mkdir()

    import api.profiles as profiles_mod

    monkeypatch.setattr(profiles_mod, "get_active_hermes_home", lambda: str(home_a))
    crews.create_crew({"name": "Crew A", "tasks": [{"title": "t"}]})
    a_names = [c["name"] for c in crews.list_crews()["crews"]]
    assert a_names == ["Crew A"]

    monkeypatch.setattr(profiles_mod, "get_active_hermes_home", lambda: str(home_b))
    b_names = [c["name"] for c in crews.list_crews()["crews"]]
    assert b_names == []

    crews.create_crew({"name": "Crew B", "tasks": [{"title": "t"}]})
    b_names2 = [c["name"] for c in crews.list_crews()["crews"]]
    assert b_names2 == ["Crew B"]

    monkeypatch.setattr(profiles_mod, "get_active_hermes_home", lambda: str(home_a))
    a_names2 = [c["name"] for c in crews.list_crews()["crews"]]
    assert a_names2 == ["Crew A"]


# ── Dispatch (needs a fake hermes_cli.kanban_db -- see module docstring) ──

@dataclass
class FakeTask:
    id: str
    title: str
    status: str = "ready"
    assignee: str | None = None
    priority: int = 0
    body: str | None = None
    workflow_template_id: str | None = None
    current_step_key: str | None = None


class FakeConn:
    def __init__(self, tasks):
        self.tasks = tasks

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=()):
        if sql.startswith("UPDATE tasks SET workflow_template_id"):
            workflow_template_id, current_step_key, task_id = params
            task = next((t for t in self.tasks if t.id == task_id), None)
            if task:
                task.workflow_template_id = workflow_template_id
                task.current_step_key = current_step_key
            return SimpleNamespace(fetchall=lambda: [], fetchone=lambda: None)
        raise AssertionError(f"unexpected SQL: {sql}")


class FakeKanbanDBNoWorkflowKwargs:
    """create_task's signature intentionally does NOT accept
    workflow_template_id/current_step_key -- simulates the currently-installed
    hermes_cli (verified against the real kanban_db.py mounted in this repo's
    dev/test environment, which also lacks these kwargs today), forcing
    _create_task_payload's inspect.signature feature-detect down the raw-UPDATE
    fallback path rather than the kwarg path."""

    def __init__(self):
        self.tasks: list[FakeTask] = []
        self.next_id = 1
        self.dispatch_once_calls = 0

    def init_db(self, *, board=None):
        return None

    def connect_closing(self, *, board=None):
        self.last_board = board
        return FakeConn(self.tasks)

    def create_task(self, conn, *, title, body=None, assignee=None, created_by=None,
                     tenant=None, priority=0, parents=(), triage=False,
                     workspace_kind="scratch", workspace_path=None,
                     idempotency_key=None, max_runtime_seconds=None, skills=None):
        if not title or not title.strip():
            raise ValueError("title is required")
        if assignee == "totally-bad-assignee":
            raise ValueError(f"unknown assignee: {assignee}")
        task_id = f"t_{self.next_id}"
        self.next_id += 1
        task = FakeTask(task_id, title, "ready", assignee, int(priority or 0), body)
        self.tasks.append(task)
        return task_id

    def get_task(self, conn, task_id):
        return next((t for t in conn.tasks if t.id == task_id), None)

    def task_age(self, task):
        return 0

    def dispatch_once(self, conn, dry_run=False, max_spawn=8):
        # Must never be called by the Crews dispatch path -- see
        # test_dispatch_never_calls_dispatch_once below.
        self.dispatch_once_calls += 1
        return {"spawned": []}


def _load_crews_with_fake_kanban(monkeypatch):
    fake_kanban = FakeKanbanDBNoWorkflowKwargs()
    fake_hermes_cli = types.ModuleType("hermes_cli")
    fake_hermes_cli.kanban_db = fake_kanban
    monkeypatch.setitem(sys.modules, "hermes_cli", fake_hermes_cli)
    monkeypatch.setitem(sys.modules, "hermes_cli.kanban_db", fake_kanban)
    import api.kanban_bridge as bridge
    importlib.reload(bridge)
    import api.crews as crews_mod
    return crews_mod, fake_kanban


def _crew_dict(**overrides):
    crew = {
        "id": "crew123456ab",
        "name": "Research crew",
        "icon": "",
        "color": None,
        "description": "",
        "tasks": [
            {"title": "Angle A: {topic}", "body": "Research {topic}", "assignee": "a", "skills": [], "priority": 0},
            {"title": "Angle B: {topic}", "body": "", "assignee": "b", "skills": [], "priority": 0},
        ],
        "created_at": 0.0,
        "updated_at": 0.0,
    }
    crew.update(overrides)
    return crew


def test_dispatch_creates_tasks_sharing_workflow_template_id_and_step_key(monkeypatch):
    crews_mod, fake_kanban = _load_crews_with_fake_kanban(monkeypatch)
    monkeypatch.setattr(crews_mod, "get_crew", lambda cid: _crew_dict(id=cid) if cid == "crewXYZ" else None)

    result = crews_mod.dispatch_crew("crewXYZ", {"variables": {"topic": "AI safety"}})

    assert result["ok"] is True
    assert result["run_id"]
    assert len(result["results"]) == 2
    assert all(r["ok"] for r in result["results"])
    task_ids = [r["task_id"] for r in result["results"]]
    created_tasks = [t for t in fake_kanban.tasks if t.id in task_ids]
    assert len(created_tasks) == 2
    # Fallback path (stub lacks the create_task kwargs) must still stamp both
    # fields via the raw-UPDATE fallback, and every task in the run shares
    # the SAME workflow_template_id + current_step_key.
    assert {t.workflow_template_id for t in created_tasks} == {"crewXYZ"}
    step_keys = {t.current_step_key for t in created_tasks}
    assert len(step_keys) == 1
    assert list(step_keys)[0] == result["run_id"]


def test_dispatch_variable_substitution(monkeypatch):
    crews_mod, fake_kanban = _load_crews_with_fake_kanban(monkeypatch)
    monkeypatch.setattr(crews_mod, "get_crew", lambda cid: _crew_dict())

    crews_mod.dispatch_crew("crewXYZ", {"variables": {"topic": "AI safety"}})

    titles = sorted(t.title for t in fake_kanban.tasks)
    assert titles == ["Angle A: AI safety", "Angle B: AI safety"]
    bodies = sorted(t.body for t in fake_kanban.tasks if t.body)
    assert bodies == ["Research AI safety"]


def test_dispatch_missing_variable_produces_per_item_error_not_abort(monkeypatch):
    """A template referencing {topic} with no `topic` in `variables` must
    fail ONLY that task spec's result entry, not abort the whole dispatch."""
    crews_mod, fake_kanban = _load_crews_with_fake_kanban(monkeypatch)
    monkeypatch.setattr(crews_mod, "get_crew", lambda cid: _crew_dict())

    result = crews_mod.dispatch_crew("crewXYZ", {"variables": {}})

    assert result["ok"] is True
    assert len(result["results"]) == 2
    assert all(r["ok"] is False for r in result["results"])
    assert all(r.get("error") for r in result["results"])
    assert fake_kanban.tasks == []


def test_dispatch_partial_failure_one_bad_assignee_does_not_abort_rest(monkeypatch):
    crews_mod, fake_kanban = _load_crews_with_fake_kanban(monkeypatch)
    crew = _crew_dict(tasks=[
        {"title": "Good task", "body": "", "assignee": "webui-test", "skills": [], "priority": 0},
        {"title": "Bad task", "body": "", "assignee": "totally-bad-assignee", "skills": [], "priority": 0},
    ])
    monkeypatch.setattr(crews_mod, "get_crew", lambda cid: crew)

    result = crews_mod.dispatch_crew("crewXYZ", {})

    assert len(result["results"]) == 2
    assert result["results"][0]["ok"] is True
    assert result["results"][1]["ok"] is False
    assert "totally-bad-assignee" in result["results"][1]["error"] or "unknown assignee" in result["results"][1]["error"]
    # The good task must still have been created.
    assert len(fake_kanban.tasks) == 1
    assert fake_kanban.tasks[0].title == "Good task"


def test_dispatch_board_param_forwarded(monkeypatch):
    crews_mod, fake_kanban = _load_crews_with_fake_kanban(monkeypatch)
    monkeypatch.setattr(crews_mod, "get_crew", lambda cid: _crew_dict(tasks=[
        {"title": "Only task", "body": "", "assignee": "a", "skills": [], "priority": 0},
    ]))

    crews_mod.dispatch_crew("crewXYZ", {"board": "experiments"})

    assert fake_kanban.last_board == "experiments"


def test_dispatch_nonexistent_crew_raises_keyerror(monkeypatch):
    crews_mod, fake_kanban = _load_crews_with_fake_kanban(monkeypatch)
    monkeypatch.setattr(crews_mod, "get_crew", lambda cid: None)
    try:
        crews_mod.dispatch_crew("does-not-exist", {})
        raise AssertionError("dispatching an unknown crew must raise KeyError")
    except KeyError:
        pass


def test_dispatch_requires_id():
    from api import crews as crews_mod
    try:
        crews_mod.dispatch_crew("", {})
        raise AssertionError("empty id must raise ValueError")
    except ValueError:
        pass


# ── Phase 1.2: last-dispatched recency signal ──────────────────────────────
# See docs/HERMES_STUDIO_PARITY_PLAN.md, "Multi-agent orchestration (Crews +
# Conductor)" -> "Phase 1.2 (v1.2) -- Crew templates gallery: search +
# last-dispatched recency".

def test_create_crew_has_last_dispatched_at_none():
    cids = []
    try:
        cid, crew = make_crew(cids, name="Fresh crew")
        assert "last_dispatched_at" in crew
        assert crew["last_dispatched_at"] is None
    finally:
        cleanup_crews(cids)


def test_duplicate_crew_does_not_carry_over_last_dispatched_at(monkeypatch, tmp_path):
    """A duplicate is a new template with no dispatch history of its own,
    even if the source crew has already been dispatched."""
    from api import crews as crews_mod
    import api.profiles as profiles_mod

    monkeypatch.setattr(profiles_mod, "get_active_hermes_home", lambda: str(tmp_path))
    crew = crews_mod.create_crew({"name": "Original", "tasks": [{"title": "t"}]})
    # Directly touch the source's last_dispatched_at (unit-level -- avoids
    # needing a real hermes_cli.kanban_db for this particular assertion).
    crews_mod._touch_crew_dispatched(crew["id"], 1700000000.0)
    source = crews_mod.get_crew(crew["id"])
    assert source["last_dispatched_at"] == 1700000000.0

    dup = crews_mod.duplicate_crew(crew["id"])
    assert dup["last_dispatched_at"] is None


def test_dispatch_stamps_last_dispatched_at_on_real_storage(monkeypatch, tmp_path):
    """End-to-end: dispatching a template that's actually on disk (not just a
    monkeypatched get_crew stub) must persist last_dispatched_at."""
    crews_mod, fake_kanban = _load_crews_with_fake_kanban(monkeypatch)
    import api.profiles as profiles_mod
    monkeypatch.setattr(profiles_mod, "get_active_hermes_home", lambda: str(tmp_path))

    crew = crews_mod.create_crew({
        "name": "Real crew",
        "tasks": [{"title": "Do the thing", "assignee": "webui-test"}],
    })
    assert crews_mod.get_crew(crew["id"])["last_dispatched_at"] is None

    before = time.time()
    crews_mod.dispatch_crew(crew["id"], {})
    after = time.time()

    updated = crews_mod.get_crew(crew["id"])
    assert updated["last_dispatched_at"] is not None
    assert before <= updated["last_dispatched_at"] <= after


def test_dispatch_stamps_last_dispatched_at_even_on_total_failure(monkeypatch, tmp_path):
    """A dispatch attempt still counts as 'last dispatched' even when every
    task spec fails (e.g. every assignee is bad) -- it's a
    last-attempted signal, not a last-succeeded one."""
    crews_mod, fake_kanban = _load_crews_with_fake_kanban(monkeypatch)
    import api.profiles as profiles_mod
    monkeypatch.setattr(profiles_mod, "get_active_hermes_home", lambda: str(tmp_path))

    crew = crews_mod.create_crew({
        "name": "Doomed crew",
        "tasks": [{"title": "Bad task", "assignee": "totally-bad-assignee"}],
    })

    result = crews_mod.dispatch_crew(crew["id"], {})
    assert all(r["ok"] is False for r in result["results"])

    updated = crews_mod.get_crew(crew["id"])
    assert updated["last_dispatched_at"] is not None


def test_dispatch_of_crew_absent_from_storage_does_not_raise(monkeypatch):
    """A crew that get_crew() resolves (e.g. via monkeypatch in other tests,
    or a race with a concurrent delete) but that isn't actually in the
    on-disk list must not blow up the touch step -- it's best-effort
    metadata, not load-bearing for dispatch to succeed."""
    crews_mod, fake_kanban = _load_crews_with_fake_kanban(monkeypatch)
    monkeypatch.setattr(crews_mod, "get_crew", lambda cid: _crew_dict())

    result = crews_mod.dispatch_crew("crewXYZ", {"variables": {"topic": "x"}})
    assert result["ok"] is True


def test_dispatch_never_calls_dispatch_once(monkeypatch):
    """Regression pinned by docs/HERMES_STUDIO_PARITY_PLAN.md: crew dispatch
    bulk-CREATEs tasks (staged Ready) and must NEVER trigger the
    dispatcher/dispatch_once -- a human still clicks Run Dispatcher
    separately to actually spawn worker subprocesses."""
    crews_mod, fake_kanban = _load_crews_with_fake_kanban(monkeypatch)
    monkeypatch.setattr(crews_mod, "get_crew", lambda cid: _crew_dict())

    crews_mod.dispatch_crew("crewXYZ", {"variables": {"topic": "x"}})

    assert fake_kanban.dispatch_once_calls == 0
