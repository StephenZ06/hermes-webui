"""Notes (the BlockNote notebook): SQLite-backed note documents and folders.

A note lives in exactly one place:

* ``General``                     -- no project and no folder,
* a Hermes workspace (project)    -- ``project_id`` from the shared project
  registry (the same workspaces Chat and Work Hub list), or
* a Notes folder                  -- ``folder_id``; folders are owned here and
  shown only on the Notes page.

A note whose project was deleted elsewhere is shown under General rather than
disappearing. ``content`` is BlockNote's own block JSON (stored as-is);
``plain_text`` is extracted from it on the server for search and, later,
agent context / retrieval (``extract_plain_text``).

Every note carries its own ``revision``. An update must name the revision it
was based on; a stale one is refused (409) with the current note, so an older
autosave can never overwrite a newer edit. Deleting moves a note to the trash
(``deleted_at``); purging removes it for good.
"""

from __future__ import annotations

import base64
import json
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Iterable

from api.config import STATE_DIR

TITLE_MAX_CHARS = 240
FOLDER_MAX_CHARS = 120
CONTENT_MAX_BYTES = 4 * 1024 * 1024
TAG_MAX_CHARS = 40
TAGS_MAX = 20
UPLOAD_MAX_BYTES = 8 * 1024 * 1024
SEARCH_LIMIT = 200
IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
_LOCK = threading.RLock()
_ID = re.compile(r"^[0-9a-f]{32}$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notebook_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notebook_folders (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS notebook_notes (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '[]',
    plain_text TEXT NOT NULL DEFAULT '',
    project_id TEXT,
    folder_id TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    pinned INTEGER NOT NULL DEFAULT 0,
    favorite INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0,
    deleted_at REAL,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notebook_notes_updated ON notebook_notes(updated_at);
CREATE INDEX IF NOT EXISTS idx_notebook_notes_project ON notebook_notes(project_id);
CREATE INDEX IF NOT EXISTS idx_notebook_notes_folder ON notebook_notes(folder_id);
CREATE TABLE IF NOT EXISTS notebook_files (
    id TEXT PRIMARY KEY,
    note_id TEXT,
    filename TEXT NOT NULL,
    mime TEXT NOT NULL,
    size INTEGER NOT NULL,
    created_at REAL NOT NULL
);
"""


class NotebookError(ValueError):
    """A request-safe validation or state failure."""

    def __init__(self, message: str, status: int = 400, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.status = status
        self.payload = payload or {}


# ── storage ────────────────────────────────────────────────────────────────────

def _db_path() -> Path:
    """Resolved at call time so isolated tests can point STATE_DIR elsewhere."""
    return Path(STATE_DIR) / "notebook.db"


def files_dir() -> Path:
    path = Path(STATE_DIR) / "notebook_files"
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def _connect() -> Generator[sqlite3.Connection, None, None]:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0)
    try:
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.commit()
        yield conn
    finally:
        conn.close()


def _now() -> float:
    return time.time()


def _clean_text(value: object, *, field: str, maximum: int, required: bool = False) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\x00", "").strip()
    if required and not text:
        raise NotebookError(f"{field} is required")
    if len(text) > maximum:
        raise NotebookError(f"{field} must be at most {maximum} characters")
    return text


def _check_id(value: object, what: str = "Note") -> str:
    text = str(value or "")
    if not _ID.match(text):
        raise NotebookError(f"{what} not found", 404)
    return text


# ── plain text (search, agent context, retrieval) ─────────────────────────────

def _inline_text(content: object) -> Iterable[str]:
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for part in content:
            yield from _inline_text(part)
    elif isinstance(content, dict):
        if isinstance(content.get("text"), str):
            yield content["text"]
        if "content" in content:  # links wrap their own inline content
            yield from _inline_text(content["content"])
        if isinstance(content.get("rows"), list):  # tables
            for row in content["rows"]:
                for cell in (row or {}).get("cells", []) if isinstance(row, dict) else []:
                    yield from _inline_text(cell.get("content") if isinstance(cell, dict) else cell)
                    yield " "


def extract_plain_text(blocks: object) -> str:
    """Readable text of a BlockNote document: one line per block, nested
    children indented. Used for search now and agent context / embeddings later."""
    lines: list[str] = []

    def walk(items: object, depth: int) -> None:
        if not isinstance(items, list):
            return
        for block in items:
            if not isinstance(block, dict):
                continue
            text = "".join(_inline_text(block.get("content"))).strip()
            props = block.get("props") if isinstance(block.get("props"), dict) else {}
            if not text and block.get("type") in ("image", "file", "video", "audio"):
                text = str(props.get("caption") or props.get("name") or "").strip()
            if text:
                prefix = "[x] " if props.get("checked") is True else "[ ] " if block.get("type") == "checkListItem" else ""
                lines.append("  " * depth + prefix + text)
            walk(block.get("children"), depth + 1)

    walk(blocks, 0)
    return "\n".join(lines)


# ── projects (shared registry) ────────────────────────────────────────────────

def _projects() -> list[dict[str, Any]]:
    from api.models import load_projects

    return [
        {"project_id": str(p.get("project_id")), "name": p.get("name") or "Untitled project", "color": p.get("color") or ""}
        for p in load_projects() if p.get("project_id")
    ]


def _validate_place(conn: sqlite3.Connection, payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """(project_id, folder_id) for a note: at most one of them."""
    project_id = _clean_text(payload.get("project_id"), field="Project", maximum=128) or None
    folder_id = _clean_text(payload.get("folder_id"), field="Folder", maximum=64) or None
    if project_id and folder_id:
        raise NotebookError("A note belongs to a workspace or a folder, not both")
    if project_id and project_id not in {p["project_id"] for p in _projects()}:
        raise NotebookError("Workspace not found", 404)
    if folder_id:
        _check_id(folder_id, "Folder")
        if conn.execute("SELECT 1 FROM notebook_folders WHERE id=?", (folder_id,)).fetchone() is None:
            raise NotebookError("Folder not found", 404)
    return project_id, folder_id


# ── notes ─────────────────────────────────────────────────────────────────────

def _tags(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise NotebookError("Tags must be a list")
    out: list[str] = []
    for raw in value:
        tag = _clean_text(raw, field="Tag", maximum=TAG_MAX_CHARS).lstrip("#").lower()
        tag = re.sub(r"\s+", "-", tag)
        if tag and tag not in out:
            out.append(tag)
    if len(out) > TAGS_MAX:
        raise NotebookError(f"A note can have at most {TAGS_MAX} tags")
    return out


def _content(value: object) -> tuple[str, str]:
    """(stored JSON, plain text) for a BlockNote document."""
    if not isinstance(value, list):
        raise NotebookError("Note content must be a BlockNote document (a list of blocks)")
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > CONTENT_MAX_BYTES:
        raise NotebookError("This note is too large to save (4 MB limit)", 413)
    return encoded, extract_plain_text(value)


def _summary(row: sqlite3.Row, known_projects: set[str]) -> dict[str, Any]:
    project_id = row["project_id"] if row["project_id"] in known_projects else None
    preview = re.sub(r"\s+", " ", row["plain_text"] or "").strip()[:160]
    return {
        "id": row["id"], "title": row["title"], "preview": preview,
        "project_id": project_id, "folder_id": row["folder_id"],
        "tags": json.loads(row["tags"] or "[]"),
        "pinned": bool(row["pinned"]), "favorite": bool(row["favorite"]), "archived": bool(row["archived"]),
        "deleted_at": row["deleted_at"], "revision": row["revision"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def _full(row: sqlite3.Row, known_projects: set[str]) -> dict[str, Any]:
    note = _summary(row, known_projects)
    note["content"] = json.loads(row["content"] or "[]")
    return note


def _row(conn: sqlite3.Connection, note_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM notebook_notes WHERE id=?", (_check_id(note_id),)).fetchone()
    if row is None:
        raise NotebookError("Note not found", 404)
    return row


def _known() -> set[str]:
    return {p["project_id"] for p in _projects()}


def bootstrap() -> dict[str, Any]:
    """Everything the Notes page needs to draw: workspaces, folders and every
    note's summary (content is fetched per note)."""
    with _LOCK, _connect() as conn:
        known = _known()
        folders = [dict(r) for r in conn.execute("SELECT * FROM notebook_folders ORDER BY sort_order, created_at")]
        notes = [_summary(r, known) for r in conn.execute("SELECT * FROM notebook_notes ORDER BY pinned DESC, updated_at DESC")]
    return {"projects": _projects(), "folders": folders, "notes": notes}


def get_note(note_id: str) -> dict[str, Any]:
    with _LOCK, _connect() as conn:
        return _full(_row(conn, note_id), _known())


def note_context(note_id: str) -> dict[str, Any]:
    """A note as agent context: plain text plus where it lives. The stable
    shape future agent actions, search indexing and retrieval build on."""
    with _LOCK, _connect() as conn:
        row = _row(conn, note_id)
        folders = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM notebook_folders")}
    projects = {p["project_id"]: p for p in _projects()}
    project = projects.get(row["project_id"])
    return {
        "id": row["id"], "title": row["title"] or "Untitled", "text": row["plain_text"],
        "tags": json.loads(row["tags"] or "[]"),
        "project": {"project_id": project["project_id"], "name": project["name"]} if project else None,
        "folder": folders.get(row["folder_id"]), "updated_at": row["updated_at"], "revision": row["revision"],
    }


def create_note(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NotebookError("Note must be an object")
    with _LOCK, _connect() as conn:
        project_id, folder_id = _validate_place(conn, payload)
        title = _clean_text(payload.get("title"), field="Title", maximum=TITLE_MAX_CHARS)
        content, plain = _content(payload.get("content", []))
        tags = _tags(payload.get("tags"))
        now = _now()
        note_id = uuid.uuid4().hex
        with conn:
            conn.execute(
                "INSERT INTO notebook_notes(id, title, content, plain_text, project_id, folder_id, tags, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (note_id, title, content, plain, project_id, folder_id, json.dumps(tags), now, now))
        return _full(_row(conn, note_id), _known())


_FLAGS = ("pinned", "favorite", "archived")


def update_note(note_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Apply a partial update. ``expected_revision`` must match the stored one."""
    if not isinstance(payload, dict):
        raise NotebookError("Update must be an object")
    expected = payload.get("expected_revision")
    if isinstance(expected, bool) or not isinstance(expected, int):
        raise NotebookError("expected_revision is required", 409)
    with _LOCK, _connect() as conn:
        row = _row(conn, note_id)
        known = _known()
        if row["revision"] != expected:
            raise NotebookError("This note changed somewhere else", 409, {"note": _full(row, known)})
        sets: dict[str, Any] = {}
        if "title" in payload:
            sets["title"] = _clean_text(payload.get("title"), field="Title", maximum=TITLE_MAX_CHARS)
        if "content" in payload:
            sets["content"], sets["plain_text"] = _content(payload.get("content"))
        if "tags" in payload:
            sets["tags"] = json.dumps(_tags(payload.get("tags")))
        if "project_id" in payload or "folder_id" in payload:
            sets["project_id"], sets["folder_id"] = _validate_place(conn, payload)
        for flag in _FLAGS:
            if flag in payload:
                if not isinstance(payload[flag], bool):
                    raise NotebookError(f"{flag} must be true or false")
                sets[flag] = int(payload[flag])
        if not sets:
            return _full(row, known)
        sets["updated_at"] = _now()
        assignments = ", ".join(f"{column}=?" for column in sets)
        with conn:
            cur = conn.execute(
                f"UPDATE notebook_notes SET {assignments}, revision=revision+1 WHERE id=? AND revision=?",
                (*sets.values(), row["id"], expected))
            if cur.rowcount != 1:  # another writer won between the read and the write
                raise NotebookError("This note changed somewhere else", 409, {"note": _full(_row(conn, note_id), known)})
        return _full(_row(conn, note_id), known)


def trash_note(note_id: str) -> dict[str, Any]:
    with _LOCK, _connect() as conn:
        row = _row(conn, note_id)
        with conn:
            conn.execute("UPDATE notebook_notes SET deleted_at=?, pinned=0, revision=revision+1 WHERE id=?", (_now(), row["id"]))
        return _full(_row(conn, note_id), _known())


def restore_note(note_id: str) -> dict[str, Any]:
    with _LOCK, _connect() as conn:
        row = _row(conn, note_id)
        with conn:
            conn.execute("UPDATE notebook_notes SET deleted_at=NULL, revision=revision+1, updated_at=? WHERE id=?", (_now(), row["id"]))
        return _full(_row(conn, note_id), _known())


def purge_note(note_id: str) -> dict[str, Any]:
    """Delete for good -- only from the trash. Its uploaded images go too."""
    with _LOCK, _connect() as conn:
        row = _row(conn, note_id)
        if row["deleted_at"] is None:
            raise NotebookError("Move the note to the trash first")
        files = [r["id"] + IMAGE_TYPES.get(r["mime"], "") for r in conn.execute("SELECT id, mime FROM notebook_files WHERE note_id=?", (row["id"],))]
        with conn:
            conn.execute("DELETE FROM notebook_files WHERE note_id=?", (row["id"],))
            conn.execute("DELETE FROM notebook_notes WHERE id=?", (row["id"],))
    for name in files:
        try:
            (files_dir() / name).unlink()
        except OSError:
            pass
    return {"ok": True, "id": row["id"]}


def empty_trash() -> dict[str, Any]:
    with _LOCK, _connect() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM notebook_notes WHERE deleted_at IS NOT NULL")]
    for note_id in ids:
        purge_note(note_id)
    return {"ok": True, "purged": len(ids)}


def duplicate_note(note_id: str) -> dict[str, Any]:
    with _LOCK, _connect() as conn:
        row = _row(conn, note_id)
        now = _now()
        new_id = uuid.uuid4().hex
        title = (row["title"] or "Untitled")[: TITLE_MAX_CHARS - 7] + " (copy)"
        with conn:
            conn.execute(
                "INSERT INTO notebook_notes(id, title, content, plain_text, project_id, folder_id, tags, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id, title, row["content"], row["plain_text"], row["project_id"], row["folder_id"], row["tags"], now, now))
        return _full(_row(conn, new_id), _known())


def search_notes(query: str, *, include_deleted: bool = False) -> list[dict[str, Any]]:
    """Notes whose title, text, tags or workspace/folder name contain every
    word of ``query`` (case-insensitive). Semantic search can replace this later."""
    words = [w for w in re.split(r"\s+", str(query or "").strip().lower()) if w][:8]
    with _LOCK, _connect() as conn:
        known = _known()
        names = {p["project_id"]: p["name"].lower() for p in _projects()}
        folders = {r["id"]: r["name"].lower() for r in conn.execute("SELECT id, name FROM notebook_folders")}
        rows = conn.execute("SELECT * FROM notebook_notes ORDER BY pinned DESC, updated_at DESC").fetchall()
    out = []
    for row in rows:
        if row["deleted_at"] is not None and not include_deleted:
            continue
        hay = " ".join([row["title"] or "", row["plain_text"] or "", " ".join("#" + t for t in json.loads(row["tags"] or "[]")),
                        names.get(row["project_id"], ""), folders.get(row["folder_id"], "")]).lower()
        if all(word.lstrip("#") in hay for word in words):
            out.append(_summary(row, known))
        if len(out) >= SEARCH_LIMIT:
            break
    return out


# ── folders (Notes-only) ──────────────────────────────────────────────────────

def create_folder(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NotebookError("Folder must be an object")
    name = _clean_text(payload.get("name"), field="Folder name", maximum=FOLDER_MAX_CHARS, required=True)
    color = _clean_text(payload.get("color"), field="Folder colour", maximum=32)
    with _LOCK, _connect() as conn:
        now = _now()
        order = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM notebook_folders").fetchone()[0]
        folder = {"id": uuid.uuid4().hex, "name": name, "color": color, "sort_order": order, "created_at": now, "updated_at": now}
        with conn:
            conn.execute("INSERT INTO notebook_folders(id, name, color, sort_order, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                         tuple(folder.values()))
        return folder


def rename_folder(folder_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    folder_id = _check_id(folder_id, "Folder")
    name = _clean_text((payload or {}).get("name"), field="Folder name", maximum=FOLDER_MAX_CHARS, required=True)
    with _LOCK, _connect() as conn:
        with conn:
            cur = conn.execute("UPDATE notebook_folders SET name=?, updated_at=? WHERE id=?", (name, _now(), folder_id))
        if cur.rowcount != 1:
            raise NotebookError("Folder not found", 404)
        return dict(conn.execute("SELECT * FROM notebook_folders WHERE id=?", (folder_id,)).fetchone())


def delete_folder(folder_id: str) -> dict[str, Any]:
    """Remove a folder. Its notes are kept: they move to General."""
    folder_id = _check_id(folder_id, "Folder")
    with _LOCK, _connect() as conn:
        with conn:
            moved = conn.execute("UPDATE notebook_notes SET folder_id=NULL, revision=revision+1 WHERE folder_id=?", (folder_id,)).rowcount
            cur = conn.execute("DELETE FROM notebook_folders WHERE id=?", (folder_id,))
        if cur.rowcount != 1:
            raise NotebookError("Folder not found", 404)
    return {"ok": True, "moved_to_general": moved}


# ── images ────────────────────────────────────────────────────────────────────

_SIGNATURES = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/webp": (b"RIFF",),
}


def save_upload(payload: dict[str, Any]) -> dict[str, Any]:
    """Store an image pasted or dropped into a note. The type is checked from
    the file's own bytes; the client's name is kept only as a label."""
    if not isinstance(payload, dict):
        raise NotebookError("Upload must be an object")
    try:
        data = base64.b64decode(str(payload.get("content_base64") or ""), validate=True)
    except (ValueError, TypeError) as error:
        raise NotebookError("The file could not be read") from error
    if not data:
        raise NotebookError("The file is empty")
    if len(data) > UPLOAD_MAX_BYTES:
        raise NotebookError("Images can be at most 8 MB", 413)
    mime = next((m for m, sigs in _SIGNATURES.items() if any(data.startswith(s) for s in sigs)), None)
    if mime == "image/webp" and data[8:12] != b"WEBP":
        mime = None
    if mime is None:
        raise NotebookError("Only PNG, JPEG, GIF and WebP images can be added to notes", 415)
    filename = re.sub(r"[^A-Za-z0-9._ -]+", "_", str(payload.get("filename") or "image"))[:120] or "image"
    note_id = payload.get("note_id")
    note_id = note_id if isinstance(note_id, str) and _ID.match(note_id) else None
    file_id = uuid.uuid4().hex
    (files_dir() / (file_id + IMAGE_TYPES[mime])).write_bytes(data)
    with _LOCK, _connect() as conn:
        with conn:
            conn.execute("INSERT INTO notebook_files(id, note_id, filename, mime, size, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                         (file_id, note_id, filename, mime, len(data), _now()))
    return {"id": file_id, "url": f"/api/notebook/files/{file_id}", "mime": mime, "size": len(data)}


def read_upload(file_id: str) -> tuple[bytes, str]:
    file_id = _check_id(file_id, "File")
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT mime FROM notebook_files WHERE id=?", (file_id,)).fetchone()
    if row is None or row["mime"] not in IMAGE_TYPES:
        raise NotebookError("File not found", 404)
    try:
        return (files_dir() / (file_id + IMAGE_TYPES[row["mime"]])).read_bytes(), row["mime"]
    except OSError as error:
        raise NotebookError("File not found", 404) from error
