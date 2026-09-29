"""Durable local state contract for the Work Hub (SQLite-backed)."""

import json

import pytest


def test_create_item_persists_revision_and_rejects_unknown_project(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [])

    created = work_hub.create_item({"title": "Ship panel", "status": "todo"}, None)

    assert created["item"]["title"] == "Ship panel"
    assert created["item"]["status"] == "todo"
    assert created["revision"] == 1
    assert (tmp_path / "work_hub.db").exists()

    with pytest.raises(work_hub.WorkHubError, match="Project not found"):
        work_hub.create_item({"title": "Bad", "project_id": "missing"}, 1)


def test_create_items_is_atomic(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [])
    with pytest.raises(work_hub.WorkHubError, match="Title is required"):
        work_hub.create_items([{"title": "First"}, {"title": ""}])
    assert work_hub.load_state()["work_items"] == []


def test_project_items_receive_a_default_board_and_can_use_new_boards(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [{"project_id": "alpha"}])

    first = work_hub.create_item({"title": "Existing", "project_id": "alpha"}, None)
    default_board = first["item"]["board_id"]
    created_board = work_hub.create_board({"name": "Frontend", "project_id": "alpha"}, first["revision"])
    second = work_hub.create_item({"title": "UI", "project_id": "alpha", "board_id": created_board["board"]["id"]}, created_board["revision"])

    assert default_board
    assert second["item"]["board_id"] == created_board["board"]["id"]
    assert {board["name"] for board in work_hub.bootstrap()["boards"]} >= {"Default", "Frontend"}


def test_board_cannot_cross_project_or_delete_default_and_delete_rehomes_items(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [{"project_id": "alpha"}, {"project_id": "beta"}])
    alpha = work_hub.create_item({"title": "Alpha", "project_id": "alpha"}, None)
    alpha_default = alpha["item"]["board_id"]
    beta_board = work_hub.create_board({"name": "Beta", "project_id": "beta"}, alpha["revision"])
    with pytest.raises(work_hub.WorkHubError, match="Board does not belong"):
        work_hub.create_item({"title": "Wrong", "project_id": "alpha", "board_id": beta_board["board"]["id"]}, beta_board["revision"])
    board = work_hub.create_board({"name": "Delivery", "project_id": "alpha"}, beta_board["revision"])
    item = work_hub.create_item({"title": "Ship", "project_id": "alpha", "board_id": board["board"]["id"]}, board["revision"])
    with pytest.raises(work_hub.WorkHubError, match="default board"):
        work_hub.delete_board(alpha_default, item["revision"])
    deleted = work_hub.delete_board(board["board"]["id"], item["revision"])
    assert deleted["revision"] > item["revision"]
    assert work_hub.get_item(item["item"]["id"])["board_id"] == alpha_default


def test_stale_revision_does_not_mutate_item(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [])
    item = work_hub.create_item({"title": "A"}, None)["item"]

    with pytest.raises(work_hub.WorkHubError, match="changed"):
        work_hub.update_item(item["id"], {"title": "B"}, 0)

    assert work_hub.get_item(item["id"])["title"] == "A"


def test_update_rejects_unknown_status_without_writing(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [])
    created = work_hub.create_item({"title": "Protect state"}, None)

    with pytest.raises(work_hub.WorkHubError, match="Invalid status"):
        work_hub.move_item(created["item"]["id"], "surprise", created["revision"])

    assert work_hub.get_item(created["item"]["id"])["status"] == "backlog"


def test_legacy_json_is_imported_into_sqlite(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [])
    (tmp_path / "work_hub.json").write_text(
        json.dumps({
            "schema_version": 1,
            "revision": 5,
            "work_items": [
                {"id": "x1", "title": "Legacy item", "status": "todo", "priority": "none", "created_at": 1.0, "updated_at": 1.0}
            ],
            "views": [], "cycles": [], "modules": [], "pages": [], "comments": [], "activities": [],
            "migration": {"status": "pending", "sources": [], "warnings": []},
        }),
        encoding="utf-8",
    )

    state = work_hub.load_state()

    assert (tmp_path / "work_hub.db").exists()
    assert state["revision"] == 5
    assert any(item["id"] == "x1" and item["title"] == "Legacy item" for item in state["work_items"])


def test_malformed_legacy_json_is_skipped_and_sqlite_is_created(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    (tmp_path / "work_hub.json").write_text("not-json", encoding="utf-8")

    work_hub.load_state()
    assert (tmp_path / "work_hub.db").exists()


def test_create_workflow_rejects_mixed_project_items_and_duplicate_active_items(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    projects = [{"project_id": "alpha"}, {"project_id": "beta"}]
    monkeypatch.setattr("api.models.load_projects", lambda: projects)
    alpha = work_hub.create_item({"title": "Alpha", "project_id": "alpha"}, None)
    beta = work_hub.create_item({"title": "Beta", "project_id": "beta"}, alpha["revision"])

    with pytest.raises(work_hub.WorkHubError, match="same project"):
        work_hub.create_workflow_run(
            "alpha", "Ship alpha", [alpha["item"]["id"], beta["item"]["id"]], beta["revision"],
        )

    run = work_hub.create_workflow_run(
        "alpha", "Ship alpha", [alpha["item"]["id"]], beta["revision"],
    )
    with pytest.raises(work_hub.WorkHubError, match="active workflow"):
        work_hub.create_workflow_run(
            "alpha", "Ship alpha again", [alpha["item"]["id"]], run["revision"],
        )


def test_claim_workflow_step_is_atomic_and_ordered(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [{"project_id": "alpha"}])
    first = work_hub.create_item({"title": "First", "project_id": "alpha"}, None)
    second = work_hub.create_item({"title": "Second", "project_id": "alpha"}, first["revision"])
    run = work_hub.create_workflow_run(
        "alpha", "Ship alpha", [first["item"]["id"], second["item"]["id"]], second["revision"],
    )

    claimed = work_hub.claim_workflow_step(run["workflow"]["id"], 0)

    assert claimed["item_id"] == first["item"]["id"]
    assert claimed["step_index"] == 0
    assert claimed["status"] == "running"
    assert work_hub.claim_workflow_step(run["workflow"]["id"], 1) is None


def test_success_sets_item_done_and_advances_only_current_step(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [{"project_id": "alpha"}])
    first = work_hub.create_item({"title": "First", "project_id": "alpha"}, None)
    second = work_hub.create_item({"title": "Second", "project_id": "alpha"}, first["revision"])
    run = work_hub.create_workflow_run(
        "alpha", "Ship alpha", [first["item"]["id"], second["item"]["id"]], second["revision"],
    )["workflow"]
    step = work_hub.claim_workflow_step(run["id"], 0)
    work_hub.record_workflow_child(run["id"], step["id"], "child-1")

    settled = work_hub.settle_workflow_step(
        run["id"], step["id"], {"child_id": "child-1", "status": "completed", "summary": "First delivered"},
    )

    assert settled["status"] == "running"
    assert settled["current_index"] == 1
    assert work_hub.get_item(first["item"]["id"])["status"] == "done"
    assert "First delivered" in work_hub.get_item(first["item"]["id"])["description"]
    assert work_hub.claim_workflow_step(run["id"], 1)["item_id"] == second["item"]["id"]


def test_unknown_or_missing_child_pauses_without_marking_item_done(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [{"project_id": "alpha"}])
    item = work_hub.create_item({"title": "First", "project_id": "alpha"}, None)
    run = work_hub.create_workflow_run("alpha", "Ship alpha", [item["item"]["id"]], item["revision"])["workflow"]
    step = work_hub.claim_workflow_step(run["id"], 0)
    work_hub.record_workflow_child(run["id"], step["id"], "child-1")

    reconciled = work_hub.reconcile_workflow_run(run["id"], lambda child_id: None)

    assert reconciled["status"] == "paused"
    assert "unverifiable" in reconciled["pause_reason"]
    assert work_hub.get_item(item["item"]["id"])["status"] == "blocked"


def test_reconcile_completed_child_settles_without_database_lock(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [{"project_id": "alpha"}])
    item = work_hub.create_item({"title": "First", "project_id": "alpha"}, None)
    run = work_hub.create_workflow_run("alpha", "Ship alpha", [item["item"]["id"]], item["revision"])["workflow"]
    step = work_hub.claim_workflow_step(run["id"], 0)
    work_hub.record_workflow_child(run["id"], step["id"], "child-1")

    reconciled = work_hub.reconcile_workflow_run(
        run["id"], lambda child_id: {"status": "completed", "summary": "Delivered"}
    )

    assert reconciled["status"] == "completed"
    assert work_hub.get_item(item["item"]["id"])["status"] == "done"


def test_reconcile_missing_active_step_pauses_fail_closed(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [{"project_id": "alpha"}])
    item = work_hub.create_item({"title": "First", "project_id": "alpha"}, None)
    run = work_hub.create_workflow_run("alpha", "Ship alpha", [item["item"]["id"]], item["revision"])["workflow"]
    step = work_hub.claim_workflow_step(run["id"], 0)
    with work_hub._connect() as conn:
        with conn:
            conn.execute("DELETE FROM workflow_steps WHERE id = ?", (step["id"],))

    reconciled = work_hub.reconcile_workflow_run(run["id"], lambda child_id: None)

    assert reconciled["status"] == "paused"
    assert "unverifiable" in reconciled["pause_reason"]
    assert work_hub.get_item(item["item"]["id"])["status"] == "in_progress"


def test_resume_only_retries_a_user_paused_current_step(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [{"project_id": "alpha"}])
    item = work_hub.create_item({"title": "First", "project_id": "alpha"}, None)
    run = work_hub.create_workflow_run("alpha", "Ship alpha", [item["item"]["id"]], item["revision"])["workflow"]
    step = work_hub.claim_workflow_step(run["id"], 0)
    work_hub.record_workflow_child(run["id"], step["id"], "child-1")
    paused = work_hub.settle_workflow_step(
        run["id"], step["id"], {"child_id": "child-1", "status": "paused", "summary": "Paused by user"}
    )

    resumed = work_hub.resume_workflow_run(run["id"], work_hub.load_state()["revision"])

    assert resumed["status"] == "pending"
    assert resumed["active_step_id"] is None
    assert work_hub.get_workflow_run(run["id"])["steps"][0]["status"] == "pending"
    assert work_hub.get_item(item["item"]["id"])["status"] == "todo"


def test_active_workflow_item_cannot_be_edited_or_deleted(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [{"project_id": "alpha"}])
    item = work_hub.create_item({"title": "First", "project_id": "alpha"}, None)
    run = work_hub.create_workflow_run("alpha", "Ship alpha", [item["item"]["id"]], item["revision"])["workflow"]
    work_hub.claim_workflow_step(run["id"], 0)
    revision = work_hub.load_state()["revision"]

    with pytest.raises(work_hub.WorkHubError, match="active workflow"):
        work_hub.update_item(item["item"]["id"], {"title": "Changed"}, revision)
    with pytest.raises(work_hub.WorkHubError, match="active workflow"):
        work_hub.delete_item(item["item"]["id"], revision)


def test_completed_workflow_item_preserves_durable_history_on_delete(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [{"project_id": "alpha"}])
    item = work_hub.create_item({"title": "First", "project_id": "alpha"}, None)
    run = work_hub.create_workflow_run("alpha", "Ship alpha", [item["item"]["id"]], item["revision"])["workflow"]
    step = work_hub.claim_workflow_step(run["id"], 0)
    work_hub.record_workflow_child(run["id"], step["id"], "child-1")
    work_hub.settle_workflow_step(
        run["id"], step["id"], {"child_id": "child-1", "status": "completed", "summary": "Done"}
    )

    with pytest.raises(work_hub.WorkHubError, match="workflow history"):
        work_hub.delete_item(item["item"]["id"], work_hub.load_state()["revision"])
