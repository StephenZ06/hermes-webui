"""Regression coverage for task references in WebUI chat turns."""
from types import SimpleNamespace

from api import sticky_board
from api.streaming import _webui_ephemeral_system_prompt


def _board(board_id, name, project_id, note):
    return {
        "id": board_id,
        "name": name,
        "project_id": project_id,
        "columns": [{
            "id": "general",
            "title": "General",
            "notes": [{"id": note, "title": note, "subItems": [f"{note} subtask"]}],
        }],
    }


def test_project_task_context_only_contains_boards_linked_to_that_project(monkeypatch):
    monkeypatch.setattr(sticky_board, "load_boards", lambda: [
        _board("project-x", "Project X", "x", "X task"),
        _board("project-y", "Project Y", "y", "Y task"),
        _board("general", "General", None, "General task"),
    ])

    context = sticky_board.render_task_context("x")

    assert "Project X" in context
    assert "X task" in context and "X task subtask" in context
    assert "Project Y" not in context and "Y task" not in context
    assert "General task" not in context


def test_general_task_context_contains_only_unlinked_boards(monkeypatch):
    monkeypatch.setattr(sticky_board, "load_boards", lambda: [
        _board("project-x", "Project X", "x", "X task"),
        _board("general", "General", None, "General task"),
    ])

    context = sticky_board.render_task_context(None)

    assert "Project X" not in context and "X task" not in context
    assert "General" in context and "General task" in context


def test_shared_chat_prompt_includes_current_sessions_task_context(monkeypatch):
    monkeypatch.setattr(
        sticky_board,
        "render_task_context",
        lambda project_id: f"TASK_CONTEXT_FOR={project_id}",
    )

    prompt = _webui_ephemeral_system_prompt(
        None,
        session=SimpleNamespace(project_id="project-x"),
    )

    assert "TASK_CONTEXT_FOR=project-x" in prompt
