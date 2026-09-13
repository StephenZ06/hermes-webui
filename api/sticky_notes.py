"""Sticky notes for projects -- a lightweight corkboard of freeform notes
scoped to a project (api/models.py's load_projects()/PROJECTS_FILE), shown
in the WebUI's Notes panel (static/notes.js). Independent of chat sessions,
Kanban tasks, and Memory: just quick per-project scratch notes with a color,
no due dates or workflow state.

Storage mirrors PROJECTS_FILE: a flat JSON list at STATE_DIR/sticky_notes.json,
loaded/saved whole (the list is expected to stay small -- personal notes, not
a database of records).
"""
import json
import time
import uuid

from api.config import STATE_DIR

NOTES_FILE = STATE_DIR / "sticky_notes.json"

# Classic Post-it palette. static/notes.js has a matching CSS class per name
# (.sticky-note--yellow etc.) -- keep the two in sync if this list changes.
NOTE_COLORS = ("yellow", "pink", "blue", "green", "orange", "purple")
DEFAULT_COLOR = "yellow"


def load_notes() -> list:
    if not NOTES_FILE.exists():
        return []
    try:
        data = json.loads(NOTES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def save_notes(notes) -> None:
    NOTES_FILE.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")


def create_note(*, text: str, project_id: str | None = None, color: str | None = None) -> dict:
    notes = load_notes()
    now = time.time()
    note = {
        "id": uuid.uuid4().hex[:12],
        "project_id": project_id or None,
        "text": text,
        "color": color if color in NOTE_COLORS else DEFAULT_COLOR,
        "created_at": now,
        "updated_at": now,
    }
    notes.append(note)
    save_notes(notes)
    return note


def update_note(note_id: str, *, text=None, color=None, project_id=...) -> dict | None:
    """`project_id=...` (the sentinel) means "leave unchanged" -- None is a
    real, valid value (re-assign the note to Unassigned)."""
    notes = load_notes()
    note = next((n for n in notes if n.get("id") == note_id), None)
    if note is None:
        return None
    if text is not None:
        note["text"] = text
    if color is not None and color in NOTE_COLORS:
        note["color"] = color
    if project_id is not ...:
        note["project_id"] = project_id or None
    note["updated_at"] = time.time()
    save_notes(notes)
    return note


def delete_note(note_id: str) -> bool:
    notes = load_notes()
    remaining = [n for n in notes if n.get("id") != note_id]
    if len(remaining) == len(notes):
        return False
    save_notes(remaining)
    return True
