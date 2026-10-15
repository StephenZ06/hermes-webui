"""The work_hub chat tool: a chat can list, add and move Work Hub items, and an
item it starts shows as being worked on only while that chat runs a turn."""

import json
import types

import pytest


@pytest.fixture()
def hub(monkeypatch, tmp_path):
    from api import config, work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [{"project_id": "p1", "name": "One"}])
    sessions = {"chat-1": types.SimpleNamespace(session_id="chat-1", project_id=None),
                "chat-p1": types.SimpleNamespace(session_id="chat-p1", project_id="p1")}

    def get_session(sid):
        if sid not in sessions:
            raise KeyError(sid)
        return sessions[sid]

    monkeypatch.setattr("api.models.get_session", get_session)
    monkeypatch.setattr(config, "STREAM_SESSION_OWNERS", {})
    return work_hub, config


def _call(args, session="chat-1"):
    from api.work_hub_agent_tool import handle

    return json.loads(handle(args, session))


def test_a_chat_lists_open_items_across_boards_with_ids(hub):
    work_hub, _ = hub
    work_hub.create_item({"title": "General task"}, None)
    work_hub.create_item({"title": "Project task", "project_id": "p1"}, None)
    done = work_hub.create_item({"title": "Finished", "status": "done"}, None)

    listed = _call({"action": "list"})

    titles = {row["title"] for row in listed["items"]}
    assert titles == {"General task", "Project task"}
    assert all(row["id"] for row in listed["items"])
    assert done["item"]["id"] not in {row["id"] for row in listed["items"]}


def test_a_project_chat_lists_its_project_unless_asked_for_all(hub):
    work_hub, _ = hub
    work_hub.create_item({"title": "General task"}, None)
    work_hub.create_item({"title": "Project task", "project_id": "p1"}, None)

    assert [row["title"] for row in _call({"action": "list"}, "chat-p1")["items"]] == ["Project task"]
    assert len(_call({"action": "list", "scope": "all"}, "chat-p1")["items"]) == 2


def test_starting_an_item_links_the_chat_and_it_shows_working_only_while_the_chat_runs(hub):
    work_hub, config = hub
    item_id = work_hub.create_item({"title": "Do it"}, None)["item"]["id"]

    updated = _call({"action": "update", "item_id": item_id, "status": "in_progress"})
    assert updated["updated"]["status"] == "in_progress"
    assert work_hub.get_item(item_id)["linked_session_ids"] == ["chat-1"]

    config.STREAM_SESSION_OWNERS["stream-a"] = "chat-1"
    assert [row["working"] for row in work_hub.list_items()["items"]] == [True]

    config.STREAM_SESSION_OWNERS.clear()
    assert [row["working"] for row in work_hub.list_items()["items"]] == [False]


def test_a_finished_item_is_no_longer_working_even_while_the_chat_runs(hub):
    work_hub, config = hub
    item_id = work_hub.create_item({"title": "Do it"}, None)["item"]["id"]
    _call({"action": "update", "item_id": item_id, "status": "in_progress"})
    config.STREAM_SESSION_OWNERS["stream-a"] = "chat-1"

    _call({"action": "update", "item_id": item_id, "status": "done"})

    assert [row["working"] for row in work_hub.list_items()["items"]] == [False]


def test_a_write_survives_the_board_changing_underneath(hub, monkeypatch):
    work_hub, _ = hub
    item_id = work_hub.create_item({"title": "Do it"}, None)["item"]["id"]
    real = work_hub.update_item
    calls = []

    def racing(item, payload, revision):
        if not calls:
            calls.append(1)
            work_hub.create_item({"title": "Someone else"}, None)  # bumps the revision
        return real(item, payload, revision)

    monkeypatch.setattr(work_hub, "update_item", racing)

    assert _call({"action": "update", "item_id": item_id, "status": "done"})["updated"]["status"] == "done"


def test_create_adds_to_the_chats_project_and_bad_input_is_an_error_not_a_crash(hub):
    work_hub, _ = hub

    created = _call({"action": "create", "title": "New one", "priority": "high"}, "chat-p1")["created"]
    assert work_hub.get_item(created["id"])["project_id"] == "p1"

    assert "error" in _call({"action": "update", "item_id": "nope", "status": "done"})
    assert "error" in _call({"action": "update", "item_id": created["id"], "status": "bogus"})
    assert "error" in _call({"action": "explode"})


def test_the_tool_registers_into_the_todo_toolset(monkeypatch):
    from api import work_hub_agent_tool

    registered = {}
    fake = types.SimpleNamespace(get_entry=lambda name: None, register=lambda **kw: registered.update(kw))
    monkeypatch.setitem(__import__("sys").modules, "tools.registry", types.SimpleNamespace(registry=fake))
    monkeypatch.setattr(work_hub_agent_tool, "_INSTALLED", False)

    work_hub_agent_tool.install()

    assert registered["name"] == "work_hub" and registered["toolset"] == "todo"
    assert registered["schema"]["parameters"]["properties"]["action"]["enum"] == ["list", "create", "update"]
