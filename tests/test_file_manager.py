"""Workspace-scoped file manager facade tests."""

from pathlib import Path

import pytest

from api import file_manager


def _local_entry(root: Path):
    return {"name": "Project", "path": str(root), "kind": "local"}


def test_local_workspace_is_listed_and_reads_only_under_registered_root(monkeypatch, tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "readme.md").write_text("hello", encoding="utf-8")
    monkeypatch.setattr(file_manager, "load_workspaces", lambda: [_local_entry(root)])
    monkeypatch.setattr(file_manager, "list_registry_projects", lambda: [])

    workspace = file_manager.list_file_manager_workspaces()[0]
    assert workspace["id"].startswith("local:")
    assert file_manager.list_directory(workspace["id"], ".")["entries"][0]["name"] == "readme.md"
    assert file_manager.read_file(workspace["id"], "readme.md")["content"] == "hello"

    with pytest.raises(file_manager.FileManagerError, match="traversal"):
        file_manager.list_directory(workspace["id"], "../outside")


def test_unknown_workspace_is_non_disclosing(monkeypatch):
    monkeypatch.setattr(file_manager, "load_workspaces", lambda: [])
    monkeypatch.setattr(file_manager, "list_registry_projects", lambda: [])

    with pytest.raises(file_manager.FileManagerError) as exc:
        file_manager.resolve_file_manager_workspace("not-a-workspace")
    assert exc.value.status == 404
    assert "not found" in str(exc.value).lower()


def test_remote_workspace_uses_ssh_reader_without_local_fallback(monkeypatch):
    project = {
        "key": "remote-project",
        "name": "Remote project",
        "available": True,
        "access_mode": "ssh",
        "ssh": {"target": "user@host", "key": "/key", "remote_path": "/srv/project"},
    }
    monkeypatch.setattr(file_manager, "load_workspaces", lambda: [])
    monkeypatch.setattr(file_manager, "list_registry_projects", lambda: [project])
    monkeypatch.setattr(file_manager, "ssh_read_file", lambda p, rel: {"path": rel, "content": "remote", "size": 6, "lines": 1})

    payload = file_manager.read_file("project:remote-project", "notes.txt")
    assert payload["content"] == "remote"
    assert payload["read_only"] is True
    with pytest.raises(file_manager.FileManagerError, match="read-only"):
        file_manager.create_file("project:remote-project", "new.txt", "nope")


def test_local_mutations_return_workspace_relative_refresh_targets(monkeypatch, tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "old.txt").write_text("old", encoding="utf-8")
    monkeypatch.setattr(file_manager, "load_workspaces", lambda: [_local_entry(root)])
    monkeypatch.setattr(file_manager, "list_registry_projects", lambda: [])

    workspace_id = file_manager.list_file_manager_workspaces()[0]["id"]
    renamed = file_manager.rename_file(workspace_id, "old.txt", "new.txt")
    assert renamed["path"] == "new.txt"
    assert renamed["parent_path"] == "."
    created = file_manager.create_file(workspace_id, "docs/plan.md", "plan")
    assert created["path"] == "docs/plan.md"
    assert (root / "docs" / "plan.md").read_text(encoding="utf-8") == "plan"
    moved = file_manager.move_path(workspace_id, "new.txt", "docs")
    assert moved["path"] == "docs/new.txt"
    assert (root / "docs" / "new.txt").exists()


def test_download_returns_binary_bytes_from_a_registered_workspace(monkeypatch, tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "asset.bin").write_bytes(b"\x00\xffasset")
    monkeypatch.setattr(file_manager, "load_workspaces", lambda: [_local_entry(root)])
    monkeypatch.setattr(file_manager, "list_registry_projects", lambda: [])

    workspace_id = file_manager.list_file_manager_workspaces()[0]["id"]
    raw, filename, mime = file_manager.download_file(workspace_id, "asset.bin")
    assert raw == b"\x00\xffasset"
    assert filename == "asset.bin"
    assert mime == "application/octet-stream"
