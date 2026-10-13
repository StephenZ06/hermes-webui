"""Notes backed by an Obsidian vault: plain Markdown files on disk.

When a vault is connected (Notes suggests one it detects: a saved workspace
whose folder holds ``.obsidian``), the Notes page reads and writes the vault's ``.md`` files
instead of its own SQLite store, so the same notes are open in Obsidian and
in Hermes at once. The vault stays the source of truth:

* a note is a ``.md`` file; its title is the file name. The vault root is
  "General"; each top-level folder is a Notes folder (notes in deeper
  sub-folders show under their top-level folder and stay where they are);
* the note body is Markdown. Its YAML frontmatter is kept exactly as written
  and never shown in the editor; tags live there (``tags:``);
* the revision is the file's modification time, so an edit made in Obsidian
  meanwhile is a conflict (409), never silently overwritten;
* opening a note never writes it; only an edit does;
* trash is Obsidian's own ``.trash`` folder; images go to the vault's
  attachment folder (``attachmentFolderPath`` in ``.obsidian/app.json``);
* hidden folders and symlinks are never followed or written through, and
  every path is checked to stay inside the vault.

Hermes-only state (stable note ids across renames, pinned, favourite, where a
trashed note came from) lives in a small index next to the WebUI state, never
in the vault's files.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator
from urllib.parse import quote, unquote

from api.config import STATE_DIR
from api.notebook import CONTENT_MAX_BYTES, IMAGE_TYPES, NotebookError, TITLE_MAX_CHARS, UPLOAD_MAX_BYTES, _SIGNATURES, _tags

_LOCK = threading.RLock()
# Vault ids carry a "v" so a request can be routed to the right store by its
# id alone (Hermes' own notes and folders use bare 32-hex ids).
_ID = re.compile(r"^v[0-9a-f]{32}$")
MAX_FILES = 5000
TRASH = ".trash"
FILE_ROUTE = "/api/notebook/vault/file?path="
_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_BAD_NAME = re.compile(r'[\\/:*?"<>|#^\[\]\x00-\x1f]')

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vault_notes (
    id TEXT PRIMARY KEY,
    vault TEXT NOT NULL,
    relpath TEXT NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 0,
    favorite INTEGER NOT NULL DEFAULT 0,
    deleted_at REAL,
    restore_to TEXT,
    UNIQUE(vault, relpath)
);
CREATE TABLE IF NOT EXISTS vault_places (
    vault TEXT NOT NULL,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    relpath TEXT NOT NULL,
    PRIMARY KEY(vault, kind, key)
);
CREATE TABLE IF NOT EXISTS vault_folders (
    id TEXT PRIMARY KEY,
    vault TEXT NOT NULL,
    relpath TEXT NOT NULL,
    UNIQUE(vault, relpath)
);
"""


# ── configuration ──────────────────────────────────────────────────────────────

def _config_path() -> Path:
    return Path(STATE_DIR) / "notebook_vault.json"


def _read_config() -> dict[str, Any]:
    try:
        data = json.loads(_config_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _is_vault(path: Path) -> bool:
    try:
        return path.is_dir() and (path / ".obsidian").is_dir()
    except OSError:
        return False


def detect_vault() -> str:
    """The first saved workspace whose folder is an Obsidian vault."""
    try:
        from api.workspace import load_workspaces

        for ws in load_workspaces():
            path = Path(str(ws.get("path") or "")).expanduser()
            if str(path) and _is_vault(path):
                return str(path)
    except Exception:
        pass
    return ""


def config() -> dict[str, Any]:
    """{enabled, path, detected, available}: what Notes reads from."""
    # Only an explicitly connected vault is used: detection merely suggests
    # one, so no install (or test run) is switched onto real files unasked.
    stored = _read_config()
    detected = detect_vault()
    path = str(stored.get("path") or "")
    enabled = stored.get("enabled", True) is not False and bool(path)
    return {"enabled": enabled, "path": path, "detected": detected,
            "available": bool(path) and _is_vault(Path(path)), "name": Path(path).name if path else ""}


def set_config(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NotebookError("Vault settings must be an object")
    current = _read_config()
    if "enabled" in payload:
        if not isinstance(payload["enabled"], bool):
            raise NotebookError("enabled must be true or false")
        current["enabled"] = payload["enabled"]
    if "path" in payload:
        raw = str(payload.get("path") or "").strip()
        if raw:
            path = Path(raw).expanduser()
            if not _is_vault(path):
                raise NotebookError("That folder is not an Obsidian vault (it has no .obsidian folder)")
            current["path"] = str(path)
        else:
            current.pop("path", None)
    target = _config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return config()


def enabled() -> bool:
    cfg = config()
    return cfg["enabled"] and cfg["available"]


def _root() -> Path:
    cfg = config()
    if not (cfg["enabled"] and cfg["available"]):
        raise NotebookError("No Obsidian vault is connected", 409)
    return Path(cfg["path"]).resolve()


# ── index ──────────────────────────────────────────────────────────────────────

@contextmanager
def _connect() -> Generator[sqlite3.Connection, None, None]:
    path = Path(STATE_DIR) / "notebook_vault.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        # Ids from before the "v" prefix keep working, prefixed.
        with conn:
            conn.execute("UPDATE vault_notes SET id='v'||id WHERE id NOT LIKE 'v%'")
            conn.execute("UPDATE vault_folders SET id='v'||id WHERE id NOT LIKE 'v%'")
        yield conn
    finally:
        conn.close()


def _note_id(conn: sqlite3.Connection, vault: str, rel: str) -> str:
    row = conn.execute("SELECT id FROM vault_notes WHERE vault=? AND relpath=?", (vault, rel)).fetchone()
    if row:
        return row["id"]
    note_id = "v" + uuid.uuid4().hex
    with conn:
        conn.execute("INSERT INTO vault_notes(id, vault, relpath) VALUES (?, ?, ?)", (note_id, vault, rel))
    return note_id


def _folder_id(conn: sqlite3.Connection, vault: str, rel: str) -> str:
    row = conn.execute("SELECT id FROM vault_folders WHERE vault=? AND relpath=?", (vault, rel)).fetchone()
    if row:
        return row["id"]
    folder_id = "v" + uuid.uuid4().hex
    with conn:
        conn.execute("INSERT INTO vault_folders(id, vault, relpath) VALUES (?, ?, ?)", (folder_id, vault, rel))
    return folder_id


def _check_id(value: object, what: str = "Note") -> str:
    if not isinstance(value, str) or not _ID.match(value):
        raise NotebookError(f"{what} not found", 404)
    return value


# ── paths ──────────────────────────────────────────────────────────────────────

def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _inside(root: Path, rel: str) -> Path:
    """``root/rel``, refusing anything that leaves the vault or passes through
    a symlink or a hidden folder (other than the trash)."""
    if not rel or rel.startswith("/") or "\\" in rel:
        raise NotebookError("Not found", 404)
    parts = Path(rel).parts
    if any(p in ("", ".", "..") for p in parts):
        raise NotebookError("Not found", 404)
    if any(p.startswith(".") and not (i == 0 and p == TRASH) for i, p in enumerate(parts)):
        raise NotebookError("Not found", 404)
    path = root.joinpath(*parts)
    probe = root
    for part in parts:
        probe = probe / part
        if probe.is_symlink():
            raise NotebookError("Not found", 404)
    if os.path.commonpath([str(root), str(path)]) != str(root):
        raise NotebookError("Not found", 404)
    return path


def _clean_title(value: object) -> str:
    title = str(value or "").strip()
    if len(title) > TITLE_MAX_CHARS:
        raise NotebookError(f"Title can be at most {TITLE_MAX_CHARS} characters")
    return title


def _file_name(title: str) -> str:
    name = _BAD_NAME.sub(" ", title).strip().strip(".")
    name = re.sub(r"\s+", " ", name)[:120].strip()
    return name or "Untitled"


def _unique(folder: Path, stem: str, suffix: str = ".md", skip: Path | None = None) -> Path:
    candidate = folder / f"{stem}{suffix}"
    n = 1
    while candidate.exists() and candidate != skip:
        candidate = folder / f"{stem} {n}{suffix}"
        n += 1
    return candidate


def _walk_notes(root: Path, *, trash: bool) -> list[Path]:
    base = root / TRASH if trash else root
    out: list[Path] = []
    if not base.is_dir() or base.is_symlink():
        return out
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        here = Path(dirpath)
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and not (here / d).is_symlink()]
        for name in filenames:
            path = here / name
            if name.endswith(".md") and not name.startswith(".") and not path.is_symlink():
                out.append(path)
                if len(out) >= MAX_FILES:
                    return out
    return out


def _top_folders(root: Path) -> list[Path]:
    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return []
    return [p for p in entries if p.is_dir() and not p.is_symlink() and not p.name.startswith(".")]


# ── markdown ───────────────────────────────────────────────────────────────────

def _split(text: str) -> tuple[str, str]:
    """(frontmatter block including its fences, body)."""
    match = _FRONTMATTER.match(text)
    if not match:
        return "", text
    return text[:match.end()], text[match.end():]


def _frontmatter_tags(front: str) -> list[str]:
    if not front:
        return []
    try:
        import yaml

        data = yaml.safe_load(_FRONTMATTER.match(front).group(1)) or {}
    except Exception:
        return []
    raw = data.get("tags") if isinstance(data, dict) else None
    if isinstance(raw, str):
        raw = [t for t in re.split(r"[,\s]+", raw) if t]
    if not isinstance(raw, list):
        return []
    return [str(t).lstrip("#").strip().lower() for t in raw if str(t).strip()][:20]


def _with_tags(front: str, tags: list[str]) -> str:
    """Frontmatter with its ``tags`` replaced; every other key kept as written."""
    tag_block = ("tags:\n" + "".join(f"  - {t}\n" for t in tags)) if tags else ""
    if not front:
        return f"---\n{tag_block}---\n" if tags else ""
    inner = _FRONTMATTER.match(front).group(1)
    lines = inner.splitlines()
    kept: list[str] = []
    skipping = False
    for line in lines:
        if re.match(r"^tags\s*:", line):
            skipping = True
            continue
        if skipping and (line.startswith((" ", "\t", "-")) or not line.strip()):
            continue
        skipping = False
        kept.append(line)
    body = "\n".join(kept).strip("\n")
    parts = [p for p in (body, tag_block.rstrip("\n")) if p]
    if not parts:
        return ""
    return "---\n" + "\n".join(parts) + "\n---\n"


_SRC = "#hermes-src="


def _to_editor(root: Path, body: str, note_rel: str) -> str:
    """Images made displayable in the editor: ``![[x.png]]`` embeds and
    relative ``![](path)`` links point at the vault file route, and remember
    their original syntax (``#hermes-src=``) so a save writes them back as
    they were."""
    def embed(match: re.Match) -> str:
        target = match.group(1).split("|", 1)[0].strip()
        rel = resolve_image(target, note_rel) if Path(target).suffix.lower() in _IMAGE_EXT else ""
        if not rel:
            return match.group(0)
        return f"![{Path(target).name}]({FILE_ROUTE}{quote(rel)}{_SRC}{quote(match.group(0), safe='')})"

    def link(match: re.Match) -> str:
        alt, target = match.group(1), match.group(2).strip()
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith(FILE_ROUTE):
            return match.group(0)
        rel = resolve_image(target, note_rel)
        if not rel:
            return match.group(0)
        return f"![{alt}]({FILE_ROUTE}{quote(rel)}{_SRC}{quote(match.group(0), safe='')})"

    text = re.sub(r"!\[\[([^\]]+)\]\]", embed, body)
    return re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", link, text)


def _from_editor(markdown: str) -> str:
    """Markdown from the editor, made Obsidian's again: wikilinks and tags the
    serializer escaped, and image links back in their original syntax (or, for
    a new upload, as a vault-relative link)."""
    text = str(markdown or "")
    text = re.sub(r"\\\[\\\[(.+?)\\\]\\\]", r"[[\1]]", text)
    text = re.sub(r"(^|\s)\\#(?=[\w/-])", r"\1#", text)

    def image(match: re.Match) -> str:
        alt, route = match.group(1), match.group(2)
        path, _, src = route.partition(_SRC)
        if src:
            return unquote(src)
        return f"![{alt}]({unquote(path).replace(' ', '%20')})"

    text = re.sub(r"!\[([^\]]*)\]\(" + re.escape(FILE_ROUTE) + r"([^)\s]+)\)", image, text)
    # The editor writes "*" bullets; Obsidian's (and most vaults') style is "-".
    text = re.sub(r"(?m)^(\s*)\* (?=\S)", r"\1- ", text)
    return text if text.endswith("\n") or not text else text + "\n"


def _plain(body: str) -> str:
    text = re.sub(r"!\[\[[^\]]*\]\]|!\[[^\]]*\]\([^)]*\)", " ", body)
    text = re.sub(r"\[\[([^\]|]*\|)?([^\]]*)\]\]", r"\2", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"(?m)^\s*[-*+]\s+\[[ xX]\]\s*", " ", text)
    text = re.sub(r"[#>*_`~|-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise NotebookError("Note not found", 404) from error


def _write(path: Path, text: str) -> None:
    data = text.encode("utf-8")
    if len(data) > CONTENT_MAX_BYTES:
        raise NotebookError("This note is too large to save (4 MB limit)", 413)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".hermes-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _revision(path: Path) -> int:
    try:
        return int(path.stat().st_mtime_ns // 1_000_000)
    except OSError:
        return 0


# ── where the main Notes view lives in the vault ────────────────────────────────
#
# With a vault connected every note is a vault file. The main Notes view keeps
# its own structure, laid out PARA-style in the vault (the vault's own
# .hermes-brain-rules.md): General is 00 Inbox/, each Hermes workspace is
# 01 Projects/<workspace>/, and a folder made on the Notes page is
# 03 Resources/<folder>/. The Obsidian view shows the whole vault, two folder
# levels deep, so "01 Projects / Triple S" is a section there too: one note,
# one file, seen from both sides.

INBOX = "00 Inbox"
PROJECTS = "01 Projects"
RESOURCES = "03 Resources"


def _workspaces() -> list[dict[str, Any]]:
    from api.notebook import _projects

    try:
        return _projects()
    except Exception:
        return []


def _place_row(conn: sqlite3.Connection, vault: str, kind: str, key: str):
    return conn.execute("SELECT relpath FROM vault_places WHERE vault=? AND kind=? AND key=?", (vault, kind, key)).fetchone()


def _project_dirs(conn: sqlite3.Connection, root: Path) -> dict[str, str]:
    """workspace id -> its folder (as first laid out; a later rename of the
    workspace keeps the folder it already has)."""
    out = {}
    for ws in _workspaces():
        row = _place_row(conn, str(root), "project", ws["project_id"])
        out[ws["project_id"]] = row["relpath"] if row else f"{PROJECTS}/{_file_name(ws['name'])}"
    return out


def _main_folders(conn: sqlite3.Connection, root: Path) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT relpath FROM vault_places WHERE vault=? AND kind='folder' ORDER BY relpath", (str(root),)).fetchall()
    out = []
    for row in rows:
        try:
            if not _inside(root, row["relpath"]).is_dir():
                continue
        except NotebookError:
            continue
        out.append({"id": _folder_id(conn, str(root), row["relpath"]), "name": row["relpath"].rsplit("/", 1)[-1],
                    "color": "", "path": row["relpath"], "store": "vault"})
    return out


def _context(conn: sqlite3.Connection, root: Path) -> dict[str, Any]:
    return {"projects": _project_dirs(conn, root), "folders": _main_folders(conn, root)}


def _main_place(rel: str, ctx: dict[str, Any]) -> tuple[bool, str | None, str | None]:
    """(in the main view, workspace id, main folder id) for a vault path."""
    for project_id, folder in ctx["projects"].items():
        if rel.startswith(folder + "/"):
            return True, project_id, None
    for folder in ctx["folders"]:
        if rel.startswith(folder["path"] + "/"):
            return True, None, folder["id"]
    if rel.startswith(INBOX + "/"):
        return True, None, None
    return False, None, None


def _vault_folder_rel(rel: str) -> str | None:
    """The Obsidian view's folder for a note: its first two folder levels."""
    parts = rel.split("/")[:-1]
    if not parts or parts[0] == TRASH:
        return None
    return "/".join(parts[:2])


# ── notes ──────────────────────────────────────────────────────────────────────

def _summary(conn: sqlite3.Connection, root: Path, path: Path, ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    vault = str(root)
    ctx = ctx or _context(conn, root)
    rel = _rel(root, path)
    note_id = _note_id(conn, vault, rel)
    row = conn.execute("SELECT * FROM vault_notes WHERE id=?", (note_id,)).fetchone()
    in_trash = rel.split("/", 1)[0] == TRASH
    # A trashed note belongs where it is restored to.
    placed = (row["restore_to"] or rel) if in_trash else rel
    in_main, project_id, folder_id = _main_place(placed, ctx)
    vault_rel = _vault_folder_rel(rel)
    text = _read(path)
    front, body = _split(text)
    stat = path.stat()
    deleted_at = row["deleted_at"] if in_trash else None
    if in_trash and not deleted_at:
        deleted_at = stat.st_mtime
    return {
        "id": note_id, "title": path.stem, "preview": _plain(body)[:160],
        # The main Notes view's place for it, and the Obsidian view's folder.
        "in_main": in_main, "project_id": project_id, "folder_id": folder_id,
        "vault_folder_id": _folder_id(conn, vault, vault_rel) if vault_rel else None,
        "tags": _frontmatter_tags(front),
        "pinned": bool(row["pinned"]), "favorite": bool(row["favorite"]), "archived": False,
        "deleted_at": deleted_at, "revision": _revision(path),
        "created_at": getattr(stat, "st_birthtime", stat.st_ctime), "updated_at": stat.st_mtime,
        "path": rel, "format": "markdown", "store": "vault",
    }


def _full(conn: sqlite3.Connection, root: Path, path: Path) -> dict[str, Any]:
    note = _summary(conn, root, path)
    _front, body = _split(_read(path))
    note["markdown"] = _to_editor(root, body, note["path"])
    note["content"] = None
    return note


def _path_of(conn: sqlite3.Connection, root: Path, note_id: str) -> Path:
    row = conn.execute("SELECT relpath FROM vault_notes WHERE id=? AND vault=?", (_check_id(note_id), str(root))).fetchone()
    if row is None:
        raise NotebookError("Note not found", 404)
    path = _inside(root, row["relpath"])
    if not path.is_file():
        raise NotebookError("This note was moved or deleted in your vault", 404)
    return path


def _set_rel(conn: sqlite3.Connection, root: Path, note_id: str, path: Path) -> None:
    with conn:
        conn.execute("DELETE FROM vault_notes WHERE vault=? AND relpath=? AND id<>?", (str(root), _rel(root, path), note_id))
        conn.execute("UPDATE vault_notes SET relpath=? WHERE id=?", (_rel(root, path), note_id))


def _folder_dir(conn: sqlite3.Connection, root: Path, folder_id: object) -> Path:
    if not folder_id:
        return root
    row = conn.execute("SELECT relpath FROM vault_folders WHERE id=? AND vault=?", (_check_id(folder_id, "Folder"), str(root))).fetchone()
    if row is None:
        raise NotebookError("Folder not found", 404)
    path = _inside(root, row["relpath"])
    if not path.is_dir():
        raise NotebookError("Folder not found", 404)
    return path


def _place_dir(conn: sqlite3.Connection, root: Path, payload: dict[str, Any]) -> Path:
    """The folder a note goes to: its workspace's, a folder, or (from the main
    view) 00 Inbox / (from the Obsidian view) the vault root."""
    project_id = payload.get("project_id")
    if project_id:
        dirs = _project_dirs(conn, root)
        if project_id not in dirs:
            raise NotebookError("Workspace not found", 404)
        rel = dirs[project_id]
        path = _inside(root, rel)
        path.mkdir(parents=True, exist_ok=True)
        if _place_row(conn, str(root), "project", project_id) is None:
            with conn:
                conn.execute("INSERT INTO vault_places(vault, kind, key, relpath) VALUES (?, 'project', ?, ?)", (str(root), project_id, rel))
        return path
    if payload.get("folder_id"):
        return _folder_dir(conn, root, payload.get("folder_id"))
    if payload.get("view") == "notes":
        path = root / INBOX
        path.mkdir(exist_ok=True)
        return path
    return root


def _visible_folders(conn: sqlite3.Connection, root: Path) -> list[dict[str, Any]]:
    """The Obsidian view's folders: each top-level folder, then the folders
    inside it ("01 Projects / Triple S")."""
    attachments = _attachments_dir(root)
    out = []
    for top in _top_folders(root):
        if top == attachments and not any(top.rglob("*.md")):
            continue
        out.append({"id": _folder_id(conn, str(root), top.name), "name": top.name, "color": "", "path": top.name, "store": "vault"})
        for sub in _top_folders(top):
            rel = f"{top.name}/{sub.name}"
            out.append({"id": _folder_id(conn, str(root), rel), "name": f"{top.name} / {sub.name}", "color": "",
                        "path": rel, "parent": top.name, "store": "vault"})
    return out


def bootstrap() -> dict[str, Any]:
    """The Obsidian view: every folder (two levels) and every note."""
    root = _root()
    with _LOCK, _connect() as conn:
        ctx = _context(conn, root)
        folders = _visible_folders(conn, root)
        notes = [_summary(conn, root, p, ctx) for p in _walk_notes(root, trash=False) + _walk_notes(root, trash=True)]
    notes.sort(key=lambda n: (not n["pinned"], -n["updated_at"]))
    cfg = config()
    return {"projects": [], "folders": folders, "notes": notes,
            "vault": {"name": cfg["name"], "path": cfg["path"]}}


def main_bootstrap() -> dict[str, Any]:
    """The main Notes view, from the vault: workspaces, Notes folders and the
    notes that live in them (or in 00 Inbox, its General)."""
    root = _root()
    with _LOCK, _connect() as conn:
        ctx = _context(conn, root)
        notes = [_summary(conn, root, p, ctx) for p in _walk_notes(root, trash=False) + _walk_notes(root, trash=True)]
    notes = [n for n in notes if n["in_main"]]
    notes.sort(key=lambda n: (not n["pinned"], -n["updated_at"]))
    return {"projects": _workspaces(), "folders": ctx["folders"], "notes": notes}


def get_note(note_id: str) -> dict[str, Any]:
    root = _root()
    with _LOCK, _connect() as conn:
        return _full(conn, root, _path_of(conn, root, note_id))


def note_context(note_id: str) -> dict[str, Any]:
    note = get_note(note_id)
    folder = note["path"].rsplit("/", 1)[0] if "/" in note["path"] else None
    project = next(({"project_id": w["project_id"], "name": w["name"]} for w in _workspaces() if w["project_id"] == note["project_id"]), None)
    return {"id": note["id"], "title": note["title"] or "Untitled", "text": _plain(note["markdown"]),
            "tags": note["tags"], "project": project, "folder": folder,
            "updated_at": note["updated_at"], "revision": note["revision"], "path": note["path"]}


def create_note(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NotebookError("Note must be an object")
    root = _root()
    with _LOCK, _connect() as conn:
        folder = _place_dir(conn, root, payload)
        title = _clean_title(payload.get("title"))
        path = _unique(folder, _file_name(title))
        tags = _tags(payload.get("tags"))
        body = _from_editor(payload.get("markdown") or "")
        _write(path, _with_tags("", tags) + body)
        _note_id(conn, str(root), _rel(root, path))
        return _full(conn, root, path)


def update_note(note_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NotebookError("Update must be an object")
    expected = payload.get("expected_revision")
    if isinstance(expected, bool) or not isinstance(expected, int):
        raise NotebookError("expected_revision is required", 409)
    root = _root()
    with _LOCK, _connect() as conn:
        path = _path_of(conn, root, note_id)
        if _revision(path) != expected:
            raise NotebookError("This note changed somewhere else (in Obsidian?)", 409, {"note": _full(conn, root, path)})
        text = _read(path)
        front, body = _split(text)
        changed = False
        if "markdown" in payload:
            body = _from_editor(payload.get("markdown"))
            changed = True
        if "tags" in payload:
            front = _with_tags(front, _tags(payload.get("tags")))
            changed = True
        if changed:
            _write(path, front + body)
        for flag in ("pinned", "favorite"):
            if flag in payload:
                if not isinstance(payload[flag], bool):
                    raise NotebookError(f"{flag} must be true or false")
                with conn:
                    conn.execute(f"UPDATE vault_notes SET {flag}=? WHERE id=?", (int(payload[flag]), note_id))
        target_dir = path.parent
        if "folder_id" in payload or "project_id" in payload:
            target_dir = _place_dir(conn, root, payload)
        stem = path.stem
        if "title" in payload:
            stem = _file_name(_clean_title(payload.get("title")))
        target = target_dir / f"{stem}.md"
        if target != path:
            target = _unique(target_dir, stem, skip=path)
            if target != path:
                path.rename(target)
                _set_rel(conn, root, note_id, target)
                path = target
        return _full(conn, root, path)


def trash_note(note_id: str) -> dict[str, Any]:
    root = _root()
    with _LOCK, _connect() as conn:
        path = _path_of(conn, root, note_id)
        rel = _rel(root, path)
        if rel.split("/", 1)[0] == TRASH:
            return _full(conn, root, path)
        trash = root / TRASH
        trash.mkdir(exist_ok=True)
        target = _unique(trash, path.stem)
        path.rename(target)
        _set_rel(conn, root, note_id, target)
        with conn:
            conn.execute("UPDATE vault_notes SET deleted_at=?, restore_to=? WHERE id=?", (time.time(), rel, note_id))
        return _full(conn, root, target)


def restore_note(note_id: str) -> dict[str, Any]:
    root = _root()
    with _LOCK, _connect() as conn:
        path = _path_of(conn, root, note_id)
        row = conn.execute("SELECT restore_to FROM vault_notes WHERE id=?", (note_id,)).fetchone()
        dest_rel = (row["restore_to"] if row else None) or path.name
        try:
            dest = _inside(root, dest_rel)
        except NotebookError:
            dest = root / path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest = _unique(dest.parent, dest.stem)
        path.rename(dest)
        _set_rel(conn, root, note_id, dest)
        with conn:
            conn.execute("UPDATE vault_notes SET deleted_at=NULL, restore_to=NULL WHERE id=?", (note_id,))
        return _full(conn, root, dest)


def purge_note(note_id: str) -> dict[str, Any]:
    root = _root()
    with _LOCK, _connect() as conn:
        path = _path_of(conn, root, note_id)
        if _rel(root, path).split("/", 1)[0] != TRASH:
            raise NotebookError("Move the note to the trash first", 409)
        path.unlink()
        with conn:
            conn.execute("DELETE FROM vault_notes WHERE id=?", (note_id,))
    return {"ok": True, "id": note_id}


def empty_trash(*, main_only: bool = False) -> dict[str, Any]:
    """Empty the vault's trash; from the main view, only the notes that came
    from its places (the rest is the Obsidian side's)."""
    root = _root()
    removed = 0
    with _LOCK, _connect() as conn:
        ctx = _context(conn, root)
        for path in _walk_notes(root, trash=True):
            if main_only and not _summary(conn, root, path, ctx)["in_main"]:
                continue
            rel = _rel(root, path)
            path.unlink()
            removed += 1
            with conn:
                conn.execute("DELETE FROM vault_notes WHERE vault=? AND relpath=?", (str(root), rel))
    return {"ok": True, "removed": removed}


def duplicate_note(note_id: str) -> dict[str, Any]:
    root = _root()
    with _LOCK, _connect() as conn:
        path = _path_of(conn, root, note_id)
        target = _unique(path.parent, f"{path.stem} copy")
        shutil.copyfile(path, target)
        _note_id(conn, str(root), _rel(root, target))
        return _full(conn, root, target)


def search_notes(query: str, *, include_deleted: bool = False, main_only: bool = False) -> list[dict[str, Any]]:
    root = _root()
    words = [w for w in str(query or "").lower().split() if w]
    out: list[dict[str, Any]] = []
    with _LOCK, _connect() as conn:
        ctx = _context(conn, root)
        for path in _walk_notes(root, trash=include_deleted):
            hay = (path.stem + "\n" + _read(path)).lower()
            if all(w in hay for w in words):
                note = _summary(conn, root, path, ctx)
                if not main_only or note["in_main"]:
                    out.append(note)
            if len(out) >= 200:
                break
    out.sort(key=lambda n: -n["updated_at"])
    return out


# ── folders ────────────────────────────────────────────────────────────────────

def _folder_name(value: object) -> str:
    name = _BAD_NAME.sub(" ", str(value or "")).strip().strip(".")
    name = re.sub(r"\s+", " ", name)[:120].strip()
    if not name:
        raise NotebookError("Folder name is required")
    return name


def create_folder(payload: dict[str, Any]) -> dict[str, Any]:
    """A folder made on the main Notes page goes under 03 Resources/; one made
    on the Obsidian side at the top of the vault."""
    root = _root()
    payload = payload or {}
    name = _folder_name(payload.get("name"))
    main = payload.get("view") == "notes"
    rel = f"{RESOURCES}/{name}" if main else name
    path = _inside(root, rel)
    if path.exists():
        raise NotebookError("A folder with that name is already in your vault", 409)
    path.mkdir(parents=True)
    with _LOCK, _connect() as conn:
        if main:
            with conn:
                conn.execute("INSERT OR REPLACE INTO vault_places(vault, kind, key, relpath) VALUES (?, 'folder', ?, ?)", (str(root), rel, rel))
        return {"id": _folder_id(conn, str(root), rel), "name": name, "color": "", "path": rel, "store": "vault"}


def rename_folder(folder_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    root = _root()
    name = _folder_name((payload or {}).get("name"))
    with _LOCK, _connect() as conn:
        path = _folder_dir(conn, root, folder_id)
        target = path.parent / name
        if target.exists() and target != path:
            raise NotebookError("A folder with that name is already in your vault", 409)
        old, new = _rel(root, path), _rel(root, target)
        path.rename(target)
        vault = str(root)
        with conn:
            for table in ("vault_folders", "vault_notes"):
                for row in conn.execute(f"SELECT id, relpath FROM {table} WHERE vault=? AND (relpath=? OR relpath LIKE ?)", (vault, old, old + "/%")).fetchall():
                    conn.execute(f"UPDATE {table} SET relpath=? WHERE id=?", (new + row["relpath"][len(old):], row["id"]))
            for row in conn.execute("SELECT kind, key, relpath FROM vault_places WHERE vault=? AND (relpath=? OR relpath LIKE ?)", (vault, old, old + "/%")).fetchall():
                conn.execute("UPDATE vault_places SET relpath=? WHERE vault=? AND kind=? AND key=?", (new + row["relpath"][len(old):], vault, row["kind"], row["key"]))
        return {"id": folder_id, "name": name, "color": "", "path": new, "store": "vault"}


def delete_folder(folder_id: str) -> dict[str, Any]:
    """Only an empty folder is removed: Hermes never moves or deletes your
    vault's files to make room."""
    root = _root()
    with _LOCK, _connect() as conn:
        path = _folder_dir(conn, root, folder_id)
        if any(p.is_file() or p.is_symlink() for p in path.rglob("*")):
            raise NotebookError("This folder still has files in your vault. Move or delete them in Obsidian first.", 409)
        rel = _rel(root, path)
        shutil.rmtree(path)
        with conn:
            conn.execute("DELETE FROM vault_folders WHERE id=?", (folder_id,))
            conn.execute("DELETE FROM vault_places WHERE vault=? AND relpath=?", (str(root), rel))
    return {"ok": True, "id": folder_id}


# ── moving Hermes' own notes in ────────────────────────────────────────────────

def _blocks_markdown(blocks: object, depth: int = 0) -> str:
    """Plain Markdown from BlockNote blocks (headings, paragraphs, lists,
    checklists, quotes, code): enough to carry a note over into the vault."""
    lines: list[str] = []
    numbered = 0

    def inline(content: object) -> str:
        if isinstance(content, str):
            return content
        out = []
        for item in content if isinstance(content, list) else []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "link":
                out.append(f"[{inline(item.get('content'))}]({item.get('href', '')})")
                continue
            text = str(item.get("text") or "")
            styles = item.get("styles") or {}
            if styles.get("code"):
                text = f"`{text}`"
            if styles.get("bold"):
                text = f"**{text}**"
            if styles.get("italic"):
                text = f"*{text}*"
            out.append(text)
        return "".join(out)

    pad = "  " * depth
    for block in blocks if isinstance(blocks, list) else []:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        props = block.get("props") or {}
        text = inline(block.get("content"))
        numbered = numbered + 1 if kind == "numberedListItem" else 0
        if kind == "heading":
            lines.append("#" * int(props.get("level") or 1) + " " + text)
        elif kind == "bulletListItem":
            lines.append(f"{pad}- {text}")
        elif kind == "numberedListItem":
            lines.append(f"{pad}{numbered}. {text}")
        elif kind == "checkListItem":
            lines.append(f"{pad}- [{'x' if props.get('checked') else ' '}] {text}")
        elif kind == "quote":
            lines.append("> " + text)
        elif kind == "codeBlock":
            lines.append(f"```{props.get('language') or ''}\n{text}\n```")
        elif kind == "image" and props.get("url"):
            lines.append(f"![{props.get('caption') or ''}]({props.get('url')})")
        else:
            lines.append(pad + text if text else "")
        children = block.get("children") or []
        if children:
            lines.append(_blocks_markdown(children, depth + 1).rstrip("\n"))
        if kind in ("heading", "paragraph", "quote", "codeBlock", "image", None):
            lines.append("")
    return "\n".join(lines).strip("\n") + "\n"


def import_from_store(*, skip_empty: bool = True) -> dict[str, Any]:
    """Write Hermes' own notes into the vault, each in its place (workspace,
    Notes folder or General). Hermes' store is left as it is, as a backup;
    a note already brought over is not written twice."""
    from api import notebook

    root = _root()
    moved, skipped = [], 0
    with notebook._LOCK, notebook._connect() as source:
        rows = source.execute("SELECT * FROM notebook_notes WHERE deleted_at IS NULL").fetchall()
        folders = {r["id"]: r["name"] for r in source.execute("SELECT id, name FROM notebook_folders")}
    with _LOCK, _connect() as conn:
        for row in rows:
            content = json.loads(row["content"] or "[]")
            if skip_empty and not (row["title"] or "").strip() and not (row["plain_text"] or "").strip():
                skipped += 1
                continue
            if conn.execute("SELECT 1 FROM vault_places WHERE vault=? AND kind='imported' AND key=?", (str(root), row["id"])).fetchone():
                continue
            place: dict[str, Any] = {"view": "notes"}
            if row["project_id"] and row["project_id"] in _project_dirs(conn, root):
                place["project_id"] = row["project_id"]
            elif row["folder_id"] and row["folder_id"] in folders:
                rel = f"{RESOURCES}/{_folder_name(folders[row['folder_id']])}"
                _inside(root, rel).mkdir(parents=True, exist_ok=True)
                with conn:
                    conn.execute("INSERT OR REPLACE INTO vault_places(vault, kind, key, relpath) VALUES (?, 'folder', ?, ?)", (str(root), rel, rel))
                place["folder_id"] = _folder_id(conn, str(root), rel)
            folder = _place_dir(conn, root, place)
            path = _unique(folder, _file_name(row["title"] or "Untitled"))
            tags = json.loads(row["tags"] or "[]")
            _write(path, _with_tags("", tags) + _blocks_markdown(content))
            note_id = _note_id(conn, str(root), _rel(root, path))
            with conn:
                conn.execute("UPDATE vault_notes SET pinned=?, favorite=? WHERE id=?", (row["pinned"], row["favorite"], note_id))
                conn.execute("INSERT INTO vault_places(vault, kind, key, relpath) VALUES (?, 'imported', ?, ?)", (str(root), row["id"], _rel(root, path)))
            moved.append(_rel(root, path))
    return {"moved": moved, "skipped_empty": skipped}


# ── attachments ────────────────────────────────────────────────────────────────

def _attachments_dir(root: Path) -> Path:
    try:
        app = json.loads((root / ".obsidian" / "app.json").read_text(encoding="utf-8"))
        folder = str(app.get("attachmentFolderPath") or "").strip()
    except (OSError, ValueError):
        folder = ""
    if not folder or folder in ("/", ".") or folder.startswith("./"):
        folder = "Attachments"
    return _inside(root, folder.strip("/"))


def save_upload(payload: dict[str, Any]) -> dict[str, Any]:
    import base64

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
    root = _root()
    folder = _attachments_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    stem = _file_name(Path(str(payload.get("filename") or "image")).stem)
    target = _unique(folder, stem, IMAGE_TYPES[mime])
    target.write_bytes(data)
    rel = _rel(root, target)
    return {"id": rel, "url": FILE_ROUTE + quote(rel), "path": rel, "mime": mime, "size": len(data)}


def read_file(rel: str) -> tuple[bytes, str]:
    root = _root()
    path = _inside(root, unquote(str(rel or "")))
    mime = next((m for m, ext in IMAGE_TYPES.items() if path.suffix.lower() in (ext, ".jpeg" if ext == ".jpg" else ext)), None)
    if mime is None or not path.is_file():
        raise NotebookError("File not found", 404)
    return path.read_bytes(), mime


def resolve_image(rel_from_note: str, note_path: str) -> str:
    """A vault-relative path for an image a note links to (relative to the
    note, or by bare name for ``![[name.png]]`` embeds)."""
    root = _root()
    target = unquote(rel_from_note).strip()
    note_dir = Path(note_path).parent
    for candidate in (note_dir / target, Path(target)):
        try:
            path = _inside(root, candidate.as_posix())
            if path.is_file():
                return _rel(root, path)
        except NotebookError:
            continue
    name = Path(target).name
    for path in [*_attachments_dir(root).glob(name), *root.rglob(name)][:1]:
        if path.is_file() and not path.is_symlink():
            try:
                return _rel(root, path)
            except ValueError:
                continue
    return ""
