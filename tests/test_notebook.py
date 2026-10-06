"""Notes (api/notebook.py): storage, revisions, places, trash, folders, search, uploads."""

from __future__ import annotations

import base64

import pytest

from api import notebook

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
DOC = [
    {"type": "heading", "props": {"level": 1}, "content": [{"type": "text", "text": "Bridge redesign", "styles": {}}], "children": []},
    {"type": "paragraph", "content": [{"type": "text", "text": "White artifacts around ", "styles": {}},
                                      {"type": "link", "href": "https://x.test", "content": [{"type": "text", "text": "platforms", "styles": {}}]}],
     "children": [{"type": "checkListItem", "props": {"checked": True}, "content": "Measure", "children": []}]},
]


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(notebook, "STATE_DIR", tmp_path)
    projects = [{"project_id": "p1", "name": "Hermes WebUI", "color": "#7c8cff"}]
    monkeypatch.setattr("api.models.load_projects", lambda *a, **k: projects)
    return projects


def test_create_update_with_revisions(store):
    note = notebook.create_note({"title": "Draft"})
    assert note["revision"] == 1 and note["project_id"] is None and note["content"] == []
    updated = notebook.update_note(note["id"], {"expected_revision": 1, "title": "Bridge", "content": DOC, "tags": ["#Office", "office", "UI Work"]})
    assert updated["revision"] == 2 and updated["title"] == "Bridge"
    assert updated["tags"] == ["office", "ui-work"]
    assert "White artifacts around platforms" in updated["preview"]
    with pytest.raises(notebook.NotebookError) as stale:
        notebook.update_note(note["id"], {"expected_revision": 1, "title": "older autosave"})
    assert stale.value.status == 409 and stale.value.payload["note"]["title"] == "Bridge"
    with pytest.raises(notebook.NotebookError):
        notebook.update_note(note["id"], {"title": "no revision"})


def test_plain_text_keeps_structure_for_search_and_agents():
    text = notebook.extract_plain_text(DOC)
    assert text.splitlines() == ["Bridge redesign", "White artifacts around platforms", "  [x] Measure"]


def test_a_note_lives_in_one_place(store):
    folder = notebook.create_folder({"name": "Ideas"})
    in_project = notebook.create_note({"project_id": "p1"})
    in_folder = notebook.create_note({"folder_id": folder["id"]})
    assert in_project["project_id"] == "p1" and in_folder["folder_id"] == folder["id"]
    with pytest.raises(notebook.NotebookError):
        notebook.create_note({"project_id": "p1", "folder_id": folder["id"]})
    with pytest.raises(notebook.NotebookError) as missing:
        notebook.create_note({"project_id": "nope"})
    assert missing.value.status == 404
    moved = notebook.update_note(in_folder["id"], {"expected_revision": 1, "project_id": None, "folder_id": None})
    assert moved["folder_id"] is None and moved["project_id"] is None


def test_deleted_workspace_notes_show_under_general(store):
    note = notebook.create_note({"project_id": "p1"})
    store.clear()  # the project was deleted on the Chat page
    assert notebook.get_note(note["id"])["project_id"] is None
    assert [n["project_id"] for n in notebook.bootstrap()["notes"]] == [None]


def test_trash_restore_and_purge(store):
    note = notebook.create_note({"title": "Old"})
    with pytest.raises(notebook.NotebookError):
        notebook.purge_note(note["id"])  # only from the trash
    trashed = notebook.trash_note(note["id"])
    assert trashed["deleted_at"] and not notebook.search_notes("old")
    assert notebook.search_notes("old", include_deleted=True)[0]["id"] == note["id"]
    assert notebook.restore_note(note["id"])["deleted_at"] is None
    notebook.trash_note(note["id"])
    notebook.purge_note(note["id"])
    with pytest.raises(notebook.NotebookError):
        notebook.get_note(note["id"])


def test_duplicate_copies_content_and_place(store):
    note = notebook.create_note({"title": "Spec", "content": DOC, "project_id": "p1", "tags": ["a"]})
    copy = notebook.duplicate_note(note["id"])
    assert copy["id"] != note["id"] and copy["title"] == "Spec (copy)"
    assert copy["content"] == DOC and copy["project_id"] == "p1" and copy["tags"] == ["a"]


def test_deleting_a_folder_keeps_its_notes_in_general(store):
    folder = notebook.create_folder({"name": "Scratch"})
    note = notebook.create_note({"folder_id": folder["id"]})
    assert notebook.rename_folder(folder["id"], {"name": "Renamed"})["name"] == "Renamed"
    assert notebook.delete_folder(folder["id"])["moved_to_general"] == 1
    assert notebook.get_note(note["id"])["folder_id"] is None
    assert notebook.bootstrap()["folders"] == []


def test_search_covers_title_content_tags_and_places(store):
    folder = notebook.create_folder({"name": "Research"})
    a = notebook.create_note({"title": "Orchestration", "tags": ["backend"]})
    b = notebook.create_note({"content": DOC, "folder_id": folder["id"]})
    c = notebook.create_note({"title": "Other", "project_id": "p1"})
    ids = lambda q: {n["id"] for n in notebook.search_notes(q)}
    assert ids("orchestration") == {a["id"]}
    assert ids("artifacts platforms") == {b["id"]}
    assert ids("#backend") == {a["id"]}
    assert ids("research") == {b["id"]}
    assert ids("hermes webui") == {c["id"]}
    assert ids("") == {a["id"], b["id"], c["id"]}


def test_image_uploads_are_checked_by_content(store):
    saved = notebook.save_upload({"filename": "../../shot.png", "content_base64": base64.b64encode(PNG).decode()})
    data, mime = notebook.read_upload(saved["id"])
    assert data == PNG and mime == "image/png" and saved["url"].endswith(saved["id"])
    for bad in (b"<svg onload=alert(1)>", b"<html><script>", b"GIF89"[:3]):
        with pytest.raises(notebook.NotebookError) as refused:
            notebook.save_upload({"filename": "x.png", "content_base64": base64.b64encode(bad).decode()})
        assert refused.value.status in (400, 415)
    with pytest.raises(notebook.NotebookError) as too_big:
        notebook.save_upload({"content_base64": base64.b64encode(PNG + b"0" * (notebook.UPLOAD_MAX_BYTES + 1)).decode()})
    assert too_big.value.status == 413
    with pytest.raises(notebook.NotebookError):
        notebook.read_upload("../etc/passwd")


def test_purging_a_note_removes_its_images(store):
    note = notebook.create_note({})
    saved = notebook.save_upload({"content_base64": base64.b64encode(PNG).decode(), "note_id": note["id"]})
    notebook.trash_note(note["id"])
    notebook.purge_note(note["id"])
    with pytest.raises(notebook.NotebookError):
        notebook.read_upload(saved["id"])
    assert not list(notebook.files_dir().iterdir())


def test_content_must_be_a_block_list(store):
    note = notebook.create_note({})
    with pytest.raises(notebook.NotebookError):
        notebook.update_note(note["id"], {"expected_revision": 1, "content": "<p>html</p>"})


def test_note_context_is_plain_text_with_its_place(store):
    note = notebook.create_note({"title": "Bridge", "content": DOC, "project_id": "p1", "tags": ["office"]})
    context = notebook.note_context(note["id"])
    assert context["text"].startswith("Bridge redesign\nWhite artifacts around platforms")
    assert context["project"] == {"project_id": "p1", "name": "Hermes WebUI"} and context["tags"] == ["office"]
