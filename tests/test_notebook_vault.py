"""Notes on an Obsidian vault (api/notebook_vault.py): the vault's Markdown
files are the notes, and Hermes never rewrites what it did not change."""

from __future__ import annotations

import base64
import io
import json
import os
import time
from urllib.parse import urlparse

import pytest

from api import notebook, notebook_api, notebook_vault

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


@pytest.fixture
def vault(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(notebook, "STATE_DIR", state)
    monkeypatch.setattr(notebook_vault, "STATE_DIR", state)
    root = tmp_path / "Vault"
    (root / ".obsidian").mkdir(parents=True)
    (root / ".obsidian" / "app.json").write_text(json.dumps({"attachmentFolderPath": "Attachments"}))
    (root / "01 Projects").mkdir()
    (root / "01 Projects" / "Honeypot.md").write_text(
        "---\nstatus: active\ntags:\n  - security\n---\n# Honeypot\n\nSee [[Network]] and ![[diagram.png]].\n")
    (root / "Attachments").mkdir()
    (root / "Attachments" / "diagram.png").write_bytes(PNG)
    (root / "Inbox note.md").write_text("Quick #idea\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("never listed")
    os.symlink(outside, root / "Linked")
    monkeypatch.setattr(notebook_vault, "detect_vault", lambda: str(root))
    return root


def _connect(root):
    return notebook_vault.set_config({"path": str(root), "enabled": True})


def test_a_detected_vault_is_only_suggested_until_connected(vault):
    cfg = notebook_vault.config()
    assert cfg["detected"] == str(vault) and cfg["enabled"] is False and not notebook_vault.enabled()
    assert _connect(vault)["enabled"] is True and notebook_vault.enabled()
    with pytest.raises(notebook.NotebookError):
        notebook_vault.set_config({"path": str(vault / "01 Projects")})  # not a vault


def test_bootstrap_lists_the_vaults_notes_and_folders_not_symlinks(vault):
    _connect(vault)
    data = notebook_vault.bootstrap()
    titles = sorted(n["title"] for n in data["notes"])
    assert titles == ["Honeypot", "Inbox note"]
    folders = {f["name"]: f["id"] for f in data["folders"]}
    assert set(folders) == {"01 Projects"}, "hidden, symlinked and attachment-only folders are not Notes folders"
    honeypot = next(n for n in data["notes"] if n["title"] == "Honeypot")
    assert honeypot["folder_id"] == folders["01 Projects"] and honeypot["tags"] == ["security"]
    assert next(n for n in data["notes"] if n["title"] == "Inbox note")["folder_id"] is None
    assert data["vault"]["name"] == "Vault"


def test_opening_never_writes_and_images_round_trip(vault):
    _connect(vault)
    note_id = next(n["id"] for n in notebook_vault.bootstrap()["notes"] if n["title"] == "Honeypot")
    before = (vault / "01 Projects" / "Honeypot.md").read_text()
    mtime = os.stat(vault / "01 Projects" / "Honeypot.md").st_mtime_ns
    note = notebook_vault.get_note(note_id)
    assert (vault / "01 Projects" / "Honeypot.md").read_text() == before
    assert os.stat(vault / "01 Projects" / "Honeypot.md").st_mtime_ns == mtime
    assert note["format"] == "markdown" and "status: active" not in note["markdown"], "frontmatter is not shown"
    assert notebook_vault.FILE_ROUTE + "Attachments/diagram.png" in note["markdown"]
    # The editor's markdown (wikilink escaped by the serializer) is written back
    # in Obsidian's own syntax, with the frontmatter kept as it was.
    edited = note["markdown"].replace("[[Network]]", "\\[\\[Network\\]\\]") + "\nMore.\n"
    saved = notebook_vault.update_note(note_id, {"expected_revision": note["revision"], "markdown": edited})
    text = (vault / "01 Projects" / "Honeypot.md").read_text()
    assert text.startswith("---\nstatus: active\ntags:\n  - security\n---\n")
    assert "See [[Network]] and ![[diagram.png]]." in text and text.rstrip().endswith("More.")
    bullets = notebook_vault._from_editor("* one\n  * two\n**bold** stays\n")
    assert bullets == "- one\n  - two\n**bold** stays\n"
    assert notebook_vault.FILE_ROUTE not in text
    assert saved["revision"] != note["revision"]


def test_an_edit_made_in_obsidian_is_a_conflict(vault):
    _connect(vault)
    note_id = next(n["id"] for n in notebook_vault.bootstrap()["notes"] if n["title"] == "Inbox note")
    note = notebook_vault.get_note(note_id)
    time.sleep(0.01)
    path = vault / "Inbox note.md"
    path.write_text("Changed in Obsidian\n")
    os.utime(path, ns=(time.time_ns() + 5_000_000, time.time_ns() + 5_000_000))
    with pytest.raises(notebook.NotebookError) as stale:
        notebook_vault.update_note(note_id, {"expected_revision": note["revision"], "markdown": "Mine"})
    assert stale.value.status == 409 and "Changed in Obsidian" in stale.value.payload["note"]["markdown"]
    assert path.read_text() == "Changed in Obsidian\n"


def test_create_rename_move_trash_restore_purge(vault):
    _connect(vault)
    folders = {f["name"]: f["id"] for f in notebook_vault.bootstrap()["folders"]}
    note = notebook_vault.create_note({"title": "Plan: Q4/next", "folder_id": folders["01 Projects"], "markdown": "Hello"})
    assert (vault / "01 Projects" / "Plan Q4 next.md").read_text() == "Hello\n", "unsafe characters are dropped"
    renamed = notebook_vault.update_note(note["id"], {"expected_revision": note["revision"], "title": "Roadmap"})
    assert renamed["id"] == note["id"] and (vault / "01 Projects" / "Roadmap.md").is_file()
    moved = notebook_vault.update_note(note["id"], {"expected_revision": renamed["revision"], "folder_id": None, "tags": ["Plan"]})
    assert moved["path"] == "Roadmap.md" and moved["tags"] == ["plan"]
    assert (vault / "Roadmap.md").read_text().startswith("---\ntags:\n  - plan\n---\n")
    trashed = notebook_vault.trash_note(note["id"])
    assert trashed["deleted_at"] and (vault / ".trash" / "Roadmap.md").is_file() and not (vault / "Roadmap.md").exists()
    assert [n["title"] for n in notebook_vault.search_notes("", include_deleted=True)] == ["Roadmap"]
    restored = notebook_vault.restore_note(note["id"])
    assert restored["path"] == "Roadmap.md" and not restored["deleted_at"]
    with pytest.raises(notebook.NotebookError):
        notebook_vault.purge_note(note["id"])  # not in the trash
    notebook_vault.trash_note(note["id"])
    notebook_vault.purge_note(note["id"])
    assert not (vault / ".trash" / "Roadmap.md").exists()


def test_folders_and_paths_never_leave_the_vault(vault):
    _connect(vault)
    folder = notebook_vault.create_folder({"name": "02 Areas"})
    assert (vault / "02 Areas").is_dir()
    notebook_vault.create_note({"title": "Keep", "folder_id": folder["id"]})
    with pytest.raises(notebook.NotebookError) as busy:
        notebook_vault.delete_folder(folder["id"])
    assert busy.value.status == 409 and (vault / "02 Areas" / "Keep.md").is_file(), "a folder with files is never emptied"
    empty = notebook_vault.create_folder({"name": "Scratch"})
    notebook_vault.delete_folder(empty["id"])
    assert not (vault / "Scratch").exists()
    for bad in ("../outside/secret.md", "Linked/secret.md", ".obsidian/app.json", "/etc/passwd"):
        with pytest.raises(notebook.NotebookError):
            notebook_vault.read_file(bad)


def test_uploads_go_to_the_attachment_folder(vault):
    _connect(vault)
    up = notebook_vault.save_upload({"filename": "shot.png", "content_base64": base64.b64encode(PNG).decode()})
    assert up["path"] == "Attachments/shot.png" and (vault / "Attachments" / "shot.png").read_bytes() == PNG
    assert notebook_vault.read_file("Attachments/shot.png") == (PNG, "image/png")
    note = notebook_vault.create_note({"title": "Pic", "markdown": f"![shot]({up['url']})"})
    assert (vault / "Pic.md").read_text() == "![shot](Attachments/shot.png)\n"
    assert notebook_vault.get_note(note["id"])["markdown"].startswith("![shot](" + notebook_vault.FILE_ROUTE)


class _H:
    def __init__(self):
        self.wfile, self.status, self.headers_out = io.BytesIO(), None, {}

    def send_response(self, s):
        self.status = s

    def send_header(self, k, v):
        self.headers_out[k] = v

    def end_headers(self):
        pass


def test_routes_use_the_vault_only_when_connected(vault):
    assert notebook_api._store() is notebook, "not connected: Hermes' own notes"
    _connect(vault)
    assert notebook_api._store() is notebook_vault
    h = _H()
    assert notebook_api.handle_notebook_get(h, urlparse("/api/notebook/vault/file?path=Attachments/diagram.png")) is True
    assert h.status == 200 and h.headers_out["Content-Type"] == "image/png" and h.wfile.getvalue() == PNG
    notebook_vault.set_config({"enabled": False})
    assert notebook_api._store() is notebook and notebook_vault.config()["path"] == str(vault)
