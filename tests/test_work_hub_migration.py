"""Sticky-board migration and prompt-scope behavior."""

import json


FIXTURE_BOARD = {
    "id": "board-1",
    "name": "Release",
    "project_id": "project-a",
    "columns": [
        {"id": "general", "title": "General", "notes": [{
            "id": "n1", "title": "matching task", "subItems": [{"id": "child-1", "title": "child task"}],
        }]},
        {"id": "completed", "title": "Completed", "notes": [{"id": "n2", "title": "done task"}]},
    ],
}


def test_migration_is_idempotent_and_preserves_board_source(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [{"project_id": "project-a", "name": "A"}])
    (tmp_path / "sticky_boards.json").write_text(json.dumps({"boards": [FIXTURE_BOARD]}), encoding="utf-8")

    first = work_hub.migrate_sticky_boards()
    second = work_hub.migrate_sticky_boards()

    assert first["created"] == 3
    assert second["created"] == 0
    assert {row["legacy_source"]["note_id"] for row in work_hub.load_state()["work_items"]} == {"n1", "child-1", "n2"}
    assert (tmp_path / "sticky_boards.json").exists()


def test_context_contains_only_active_items_for_requested_project(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [
        {"project_id": "project-a", "name": "A"}, {"project_id": "project-b", "name": "B"},
    ])
    work_hub.create_item({"title": "matching task", "project_id": "project-a", "status": "todo"}, None)
    work_hub.create_item({"title": "done task", "project_id": "project-a", "status": "done"}, 1)
    work_hub.create_item({"title": "other task", "project_id": "project-b", "status": "todo"}, 2)

    context = work_hub.render_task_context("project-a")

    assert "matching task" in context
    assert "done task" not in context
    assert "other task" not in context
    assert work_hub.render_task_context(None) == ""


def test_empty_legacy_file_records_completed_migration(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    (tmp_path / "sticky_boards.json").write_text('{"boards": []}', encoding="utf-8")

    work_hub.migrate_sticky_boards()

    assert work_hub.load_state()["migration"]["status"] == "complete"
