"""Work Hub references remain safe as surrounding Hermes state changes."""

import pytest


def test_linked_session_must_exist_and_unavailable_profile_is_safe(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [])
    monkeypatch.setattr("api.models.get_session", lambda session_id: None)
    monkeypatch.setattr("api.profiles.list_profiles_api", lambda: [])
    item = work_hub.create_item({"title": "Delegate"}, None)

    with pytest.raises(work_hub.WorkHubError, match="Session not found"):
        work_hub.update_item(item["item"]["id"], {"linked_session_ids": ["missing"]}, item["revision"])

    shown = work_hub.present_item({**item["item"], "agent_profile": "removed-profile"})
    assert shown["agent"]["availability"] == "unavailable"


def test_office_event_adds_activity_without_changing_planned_status(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [])
    item = work_hub.create_item({"title": "Observe", "status": "todo"}, None)

    result = work_hub.record_office_activity(item["item"]["id"], {"state": "running"})

    assert work_hub.get_item(item["item"]["id"])["status"] == "todo"
    assert result["activity"]["kind"] == "office_execution"


def test_planning_entities_are_project_scoped_and_revisioned(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [{"project_id": "project-a", "name": "A"}])

    cycle = work_hub.create_planning_entity("cycles", {"name": "September", "project_id": "project-a"}, None)

    assert cycle["entity"]["name"] == "September"
    assert cycle["entity"]["project_id"] == "project-a"
    assert cycle["revision"] == 1
    with pytest.raises(work_hub.WorkHubError, match="Planning entity type"):
        work_hub.create_planning_entity("unknown", {"name": "Nope"}, 1)
