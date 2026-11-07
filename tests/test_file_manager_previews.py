"""Files page: what a file opens as, the byte stream behind previews, and live space status."""

from pathlib import Path

import pytest

from api import file_manager


@pytest.fixture()
def space(monkeypatch, tmp_path):
    root = tmp_path / "space"
    root.mkdir()
    monkeypatch.setattr(file_manager, "load_workspaces", lambda: [{"name": "Space", "path": str(root), "kind": "local"}])
    monkeypatch.setattr(file_manager, "list_registry_projects", lambda: [])
    return root, file_manager.list_file_manager_workspaces()[0]["id"]


PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000")


def test_a_binary_file_opens_without_its_bytes_as_characters(space):
    root, wid = space
    (root / "photo.png").write_bytes(PNG + b"\x00" * 64)
    payload = file_manager.read_file(wid, "photo.png")
    assert payload["preview_kind"] == "binary"
    assert "content" not in payload
    assert payload["size"] == len(PNG) + 64


def test_text_still_opens_as_editable_text(space):
    root, wid = space
    (root / "notes.md").write_text("# héllo\nworld\n", encoding="utf-8")
    payload = file_manager.read_file(wid, "notes.md")
    assert payload["content"] == "# héllo\nworld\n"
    assert "preview_kind" not in payload


def test_a_file_over_the_read_limit_says_so_instead_of_failing(space):
    root, wid = space
    (root / "big.log").write_bytes(b"a" * (file_manager.MAX_FILE_BYTES + 1))
    payload = file_manager.read_file(wid, "big.log")
    assert payload["preview_kind"] == "too_large"
    assert payload["size"] == file_manager.MAX_FILE_BYTES + 1
    assert "content" not in payload


def test_the_raw_stream_resolves_only_files_inside_the_space(space):
    root, wid = space
    (root / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    (root / "folder").mkdir()
    anchor, target, name = file_manager.raw_file_target(wid, "clip.mp4")
    assert (anchor, target, name) == (root, root / "clip.mp4", "clip.mp4")
    for bad, status in (("../outside.png", 400), ("folder", 404), (".", 404), ("missing.png", 404)):
        with pytest.raises(file_manager.FileManagerError) as exc:
            file_manager.raw_file_target(wid, bad)
        assert exc.value.status == status, bad


def test_a_remote_space_has_no_raw_stream(monkeypatch):
    project = {"key": "pi", "name": "Pi", "available": True, "access_mode": "ssh",
               "ssh": {"target": "u@h", "key": "/k", "remote_path": "/srv"}}
    monkeypatch.setattr(file_manager, "load_workspaces", lambda: [])
    monkeypatch.setattr(file_manager, "list_registry_projects", lambda: [project])
    with pytest.raises(file_manager.FileManagerError) as exc:
        file_manager.raw_file_target("project:pi", "a.png")
    assert exc.value.status == 409


def test_a_remote_space_is_online_only_while_its_host_answers(monkeypatch):
    project = {"key": "pi", "name": "Pi", "available": True, "access_mode": "ssh",
               "ssh": {"target": "u@h", "key": "/k", "remote_path": "/srv"}}
    monkeypatch.setattr(file_manager, "load_workspaces", lambda: [])
    monkeypatch.setattr(file_manager, "list_registry_projects", lambda: [project])
    monkeypatch.setattr(file_manager, "_ssh_status", {})
    answers = []
    monkeypatch.setattr(file_manager, "ssh_reachable", lambda p: answers.append(1) or False)
    assert file_manager.list_file_manager_workspaces()[0]["available"] is False
    # The answer is kept for a while, so a status poll does not dial the host every time.
    file_manager.list_file_manager_workspaces()
    assert len(answers) == 1
    monkeypatch.setattr(file_manager, "_ssh_status", {})
    monkeypatch.setattr(file_manager, "ssh_reachable", lambda p: True)
    assert file_manager.list_file_manager_workspaces()[0]["available"] is True


def test_a_local_space_whose_folder_is_gone_is_offline(monkeypatch, tmp_path):
    root = tmp_path / "drive"
    root.mkdir()
    monkeypatch.setattr(file_manager, "load_workspaces", lambda: [{"name": "Drive", "path": str(root), "kind": "local"}])
    monkeypatch.setattr(file_manager, "list_registry_projects", lambda: [])
    assert file_manager.list_file_manager_workspaces()[0]["available"] is True
    root.rmdir()
    assert file_manager.list_file_manager_workspaces()[0]["available"] is False


def test_ssh_reachable_never_raises(monkeypatch):
    from api import ssh_workspace

    def boom(project, command):
        raise ssh_workspace.SshWorkspaceError("Connection refused")
    monkeypatch.setattr(ssh_workspace, "_run_remote", boom)
    assert ssh_workspace.ssh_reachable({"key": "x"}) is False
    monkeypatch.setattr(ssh_workspace, "_run_remote", lambda project, command: "")
    assert ssh_workspace.ssh_reachable({"key": "x"}) is True
