"""Durable local state contract for the Work Hub."""

import pytest


def test_create_item_persists_revision_and_rejects_unknown_project(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [])

    created = work_hub.create_item({"title": "Ship panel", "status": "todo"}, None)

    assert created["item"]["title"] == "Ship panel"
    assert created["item"]["status"] == "todo"
    assert created["revision"] == 1
    assert (tmp_path / "work_hub.json").exists()

    with pytest.raises(work_hub.WorkHubError, match="Project not found"):
        work_hub.create_item({"title": "Bad", "project_id": "missing"}, 1)


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


def test_malformed_state_is_rejected_before_any_mutation(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    (tmp_path / "work_hub.json").write_text(
        '{"schema_version": 1, "revision": true, "work_items": [null], "migration": null}',
        encoding="utf-8",
    )

    with pytest.raises(work_hub.WorkHubError, match="invalid revision"):
        work_hub.load_state()
