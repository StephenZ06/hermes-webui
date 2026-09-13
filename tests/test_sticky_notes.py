"""Sticky notes for projects (api/sticky_notes.py, static/notes.js).

A lightweight corkboard of freeform per-project notes -- independent of chat
sessions, Kanban tasks, and Memory. Storage mirrors api/models.py's
load_projects()/PROJECTS_FILE: a flat JSON list, loaded/saved whole.
"""
from api import sticky_notes


def test_load_notes_missing_file_answers_empty_list(tmp_path, monkeypatch):
    monkeypatch.setattr(sticky_notes, "NOTES_FILE", tmp_path / "sticky_notes.json")
    assert sticky_notes.load_notes() == []


def test_load_notes_corrupt_file_answers_empty_list(tmp_path, monkeypatch):
    f = tmp_path / "sticky_notes.json"
    f.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(sticky_notes, "NOTES_FILE", f)
    assert sticky_notes.load_notes() == []


def test_load_notes_non_list_json_answers_empty_list(tmp_path, monkeypatch):
    f = tmp_path / "sticky_notes.json"
    f.write_text('{"not": "a list"}', encoding="utf-8")
    monkeypatch.setattr(sticky_notes, "NOTES_FILE", f)
    assert sticky_notes.load_notes() == []


def test_create_note_persists_and_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(sticky_notes, "NOTES_FILE", tmp_path / "sticky_notes.json")
    note = sticky_notes.create_note(text="Ship the release", project_id="proj-1", color="pink")
    assert note["text"] == "Ship the release"
    assert note["project_id"] == "proj-1"
    assert note["color"] == "pink"
    assert note["id"]
    assert note["created_at"] == note["updated_at"]
    reloaded = sticky_notes.load_notes()
    assert reloaded == [note]


def test_create_note_with_unknown_color_falls_back_to_default(tmp_path, monkeypatch):
    monkeypatch.setattr(sticky_notes, "NOTES_FILE", tmp_path / "sticky_notes.json")
    note = sticky_notes.create_note(text="x", color="not-a-real-color")
    assert note["color"] == sticky_notes.DEFAULT_COLOR


def test_create_note_without_project_id_is_unassigned(tmp_path, monkeypatch):
    monkeypatch.setattr(sticky_notes, "NOTES_FILE", tmp_path / "sticky_notes.json")
    note = sticky_notes.create_note(text="x")
    assert note["project_id"] is None


def test_update_note_changes_only_given_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(sticky_notes, "NOTES_FILE", tmp_path / "sticky_notes.json")
    note = sticky_notes.create_note(text="original", project_id="proj-1", color="yellow")
    updated = sticky_notes.update_note(note["id"], text="edited")
    assert updated["text"] == "edited"
    assert updated["project_id"] == "proj-1"
    assert updated["color"] == "yellow"
    assert updated["updated_at"] >= note["updated_at"]


def test_update_note_can_reassign_project_to_unassigned(tmp_path, monkeypatch):
    monkeypatch.setattr(sticky_notes, "NOTES_FILE", tmp_path / "sticky_notes.json")
    note = sticky_notes.create_note(text="x", project_id="proj-1")
    updated = sticky_notes.update_note(note["id"], project_id=None)
    assert updated["project_id"] is None


def test_update_note_omitting_project_id_leaves_it_untouched(tmp_path, monkeypatch):
    # project_id defaults to the `...` sentinel, distinct from an explicit
    # None -- otherwise a text-only edit would silently unassign the note.
    monkeypatch.setattr(sticky_notes, "NOTES_FILE", tmp_path / "sticky_notes.json")
    note = sticky_notes.create_note(text="x", project_id="proj-1")
    updated = sticky_notes.update_note(note["id"], text="y")
    assert updated["project_id"] == "proj-1"


def test_update_note_rejects_unknown_color_silently(tmp_path, monkeypatch):
    monkeypatch.setattr(sticky_notes, "NOTES_FILE", tmp_path / "sticky_notes.json")
    note = sticky_notes.create_note(text="x", color="blue")
    updated = sticky_notes.update_note(note["id"], color="not-a-real-color")
    assert updated["color"] == "blue"


def test_update_note_missing_id_answers_none(tmp_path, monkeypatch):
    monkeypatch.setattr(sticky_notes, "NOTES_FILE", tmp_path / "sticky_notes.json")
    assert sticky_notes.update_note("does-not-exist", text="x") is None


def test_delete_note_removes_it(tmp_path, monkeypatch):
    monkeypatch.setattr(sticky_notes, "NOTES_FILE", tmp_path / "sticky_notes.json")
    note = sticky_notes.create_note(text="x")
    assert sticky_notes.delete_note(note["id"]) is True
    assert sticky_notes.load_notes() == []


def test_delete_note_missing_id_answers_false(tmp_path, monkeypatch):
    monkeypatch.setattr(sticky_notes, "NOTES_FILE", tmp_path / "sticky_notes.json")
    assert sticky_notes.delete_note("does-not-exist") is False


def test_multiple_notes_coexist_independently(tmp_path, monkeypatch):
    monkeypatch.setattr(sticky_notes, "NOTES_FILE", tmp_path / "sticky_notes.json")
    a = sticky_notes.create_note(text="a", project_id="p1")
    b = sticky_notes.create_note(text="b", project_id="p2")
    sticky_notes.delete_note(a["id"])
    remaining = sticky_notes.load_notes()
    assert len(remaining) == 1
    assert remaining[0]["id"] == b["id"]


class TestRoutesWiring:
    """Source-pin that api/routes.py exposes the four sticky-notes endpoints
    wired to api/sticky_notes.py -- mirrors tests/test_opencode_go_usage_widget.py's
    approach for routes that need a live server/profile context to exercise
    end-to-end and have no existing HTTP-level test harness to extend."""

    def test_get_endpoint_is_wired(self):
        import pathlib
        src = pathlib.Path("api/routes.py").read_text(encoding="utf-8")
        assert '"/api/sticky_notes"' in src
        assert "from api.sticky_notes import load_notes" in src

    def test_create_endpoint_is_wired(self):
        import pathlib
        src = pathlib.Path("api/routes.py").read_text(encoding="utf-8")
        assert '"/api/sticky_notes/create"' in src
        assert "from api.sticky_notes import create_note" in src

    def test_update_endpoint_is_wired(self):
        import pathlib
        src = pathlib.Path("api/routes.py").read_text(encoding="utf-8")
        assert '"/api/sticky_notes/update"' in src
        assert "from api.sticky_notes import update_note" in src

    def test_delete_endpoint_is_wired(self):
        import pathlib
        src = pathlib.Path("api/routes.py").read_text(encoding="utf-8")
        assert '"/api/sticky_notes/delete"' in src
        assert "from api.sticky_notes import delete_note" in src
