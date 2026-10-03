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


def test_context_groups_every_project_board_and_fails_closed_for_mismatched_items(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [
        {"project_id": "project-a", "name": "A"}, {"project_id": "project-b", "name": "B"},
    ])
    first = work_hub.create_board({"name": "Planning", "project_id": "project-a"}, None)
    second = work_hub.create_board({"name": "Delivery", "project_id": "project-a"}, first["revision"])
    empty = work_hub.create_board({"name": "Empty board", "project_id": "project-a"}, second["revision"])
    other = work_hub.create_board({"name": "Other project", "project_id": "project-b"}, empty["revision"])
    current = other["revision"]
    current = work_hub.create_item({"title": "Plan release", "project_id": "project-a", "board_id": first["board"]["id"], "status": "todo"}, current)["revision"]
    current = work_hub.create_item({"title": "Ship release", "project_id": "project-a", "board_id": second["board"]["id"], "status": "todo"}, current)["revision"]
    current = work_hub.create_item({"title": "Completed release", "project_id": "project-a", "board_id": second["board"]["id"], "status": "done"}, current)["revision"]
    current = work_hub.create_item({"title": "Cancelled release", "project_id": "project-a", "board_id": second["board"]["id"], "status": "cancelled"}, current)["revision"]
    work_hub.create_item({"title": "Other task", "project_id": "project-b", "board_id": other["board"]["id"], "status": "todo"}, current)
    with work_hub._connect() as conn:
        conn.execute(
            "UPDATE work_items SET board_id = ? WHERE title = ?",
            (other["board"]["id"], "Plan release"),
        )
        conn.execute(
            "INSERT INTO planning_entities(id, collection, name, project_id, content, layout, filters, created_at, updated_at) VALUES (?, 'views', ?, ?, ?, 'board', '{}', ?, ?)",
            ("malformed-view", "Malformed view", "project-a", work_hub._encode_json([]), 1.0, 1.0),
        )
        conn.commit()

    context = work_hub.render_task_context("project-a")

    assert "## Board: Planning" in context
    assert "## Board: Delivery" in context
    assert "## Board: Empty board" in context
    assert "Plan release" not in context
    assert "Ship release" in context
    assert "Completed release" not in context
    assert "Cancelled release" not in context
    assert "Other project" not in context
    assert "Other task" not in context


def test_empty_legacy_file_records_completed_migration(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    (tmp_path / "sticky_boards.json").write_text('{"boards": []}', encoding="utf-8")

    work_hub.migrate_sticky_boards()

    assert work_hub.load_state()["migration"]["status"] == "complete"


def test_bootstrap_migrates_legacy_notes_before_returning_items(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [{"project_id": "project-a", "name": "A"}])
    (tmp_path / "sticky_boards.json").write_text(json.dumps({"boards": [FIXTURE_BOARD]}), encoding="utf-8")

    result = work_hub.bootstrap()

    assert any(item["title"] == "matching task" for item in result["items"])


def test_repeated_migration_does_not_churn_revision_for_known_warnings(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    (tmp_path / "sticky_boards.json").write_text(json.dumps({"boards": [{
        "id": "legacy", "columns": [{"id": "custom", "notes": []}],
    }]}), encoding="utf-8")

    first = work_hub.migrate_sticky_boards()
    second = work_hub.migrate_sticky_boards()

    assert second["revision"] == first["revision"]


def test_migration_preserves_oversized_legacy_title_without_failing_bootstrap(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    title = "x" * 241
    (tmp_path / "sticky_boards.json").write_text(json.dumps({"boards": [{
        "id": "legacy", "columns": [{"id": "general", "notes": [{"id": "long", "title": title}]}],
    }]}), encoding="utf-8")

    result = work_hub.bootstrap()

    assert result["items"][0]["title"] == "x" * 240


def test_legacy_board_folder_upgrade_preserves_each_legacy_project(monkeypatch, tmp_path):
    """Legacy project boards become isolated Work Hub folders, not one import bucket."""
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    with work_hub._connect() as conn:
        now = 1.0
        for board_id, project_id in (("board-a", "project-a"), ("board-b", "project-b")):
            conn.execute(
                "INSERT INTO planning_entities(id, collection, name, project_id, content, layout, filters, created_at, updated_at) VALUES (?, 'views', 'Default', ?, ?, 'board', '{}', ?, ?)",
                (board_id, project_id, work_hub._encode_json({"kind": "work_hub_board", "default": True}), now, now),
            )
        conn.commit()

    work_hub._migrate_legacy_boards_to_folder()

    folders = {folder["name"]: folder["id"] for folder in work_hub.list_folders()}
    boards = {board["project_id"]: board for board in work_hub.bootstrap()["boards"]}
    assert set(folders) == {"Imported project project-a", "Imported project project-b"}
    assert boards["project-a"]["folder_id"] == folders["Imported project project-a"]
    assert boards["project-b"]["folder_id"] == folders["Imported project project-b"]
