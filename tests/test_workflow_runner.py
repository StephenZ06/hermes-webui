from __future__ import annotations


class FakeRuntime:
    def __init__(self):
        self.calls: list[tuple] = []
        self.children: dict[str, dict] = {}

    def create_parent(self, workflow):
        self.calls.append(("create_parent", workflow["id"]))
        return "parent-1"

    def create_child(self, parent_session_id, step):
        child_id = f"child-{len(self.children) + 1}"
        self.calls.append(("create_child", parent_session_id, step["id"], child_id))
        self.children[child_id] = {"status": "pending"}
        return child_id

    def start_child(self, child_id, step):
        self.calls.append(("start_child", child_id, step["id"]))
        self.children[child_id] = {"status": "running"}

    def lookup_child(self, child_id):
        return self.children.get(child_id)

    def interrupt_child(self, child_id):
        self.calls.append(("interrupt_child", child_id))


def _workflow(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [{"project_id": "alpha"}])
    first = work_hub.create_item({"title": "First", "project_id": "alpha"}, None)
    second = work_hub.create_item({"title": "Second", "project_id": "alpha"}, first["revision"])
    return work_hub.create_workflow_run(
        "alpha", "Ship alpha", [first["item"]["id"], second["item"]["id"]], second["revision"]
    )["workflow"]


def test_runner_starts_one_child_then_waits_before_claiming_next_step(monkeypatch, tmp_path):
    from api import work_hub
    from api.workflow_runner import WorkflowRunner

    run = _workflow(monkeypatch, tmp_path)
    runtime = FakeRuntime()
    runner = WorkflowRunner(runtime)

    started = runner.reconcile_and_advance(run["id"])

    assert started["active_step_id"]
    assert [call[0] for call in runtime.calls] == ["create_parent", "create_child", "start_child"]
    assert len([step for step in work_hub.get_workflow_run(run["id"])["steps"] if step["status"] == "running"]) == 1

    waiting = runner.reconcile_and_advance(run["id"])

    assert waiting["active_step_id"] == started["active_step_id"]
    assert len([call for call in runtime.calls if call[0] == "start_child"]) == 1


def test_runner_persists_child_identity_before_completion_reconciliation(monkeypatch, tmp_path):
    from api import work_hub
    from api.workflow_runner import WorkflowRunner

    run = _workflow(monkeypatch, tmp_path)
    runtime = FakeRuntime()
    runner = WorkflowRunner(runtime)

    runner.reconcile_and_advance(run["id"])
    current = work_hub.get_workflow_run(run["id"])
    step = next(step for step in current["steps"] if step["id"] == current["active_step_id"])

    assert step["child_id"] == "child-1"
    runtime.children["child-1"] = {"status": "completed", "summary": "Done"}
    settled = runner.reconcile_and_advance(run["id"])
    assert settled["status"] == "running"
    assert settled["active_step_id"] is None


def test_pause_during_startup_gap_fails_closed(monkeypatch, tmp_path):
    from api import work_hub
    from api.workflow_runner import WorkflowRunner

    run = _workflow(monkeypatch, tmp_path)
    step = work_hub.claim_workflow_step(run["id"], 0)

    paused = WorkflowRunner(FakeRuntime()).request_pause(run["id"])

    assert step["child_id"] is None
    assert paused["status"] == "paused"
