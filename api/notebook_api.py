"""HTTP routes for Notes (api/notebook.py), mounted under /api/notebook/."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote

from api import notebook, notebook_vault
from api.helpers import bad, j

_PREFIX = "/api/notebook"


def _fail(handler, error: notebook.NotebookError) -> bool:
    if error.payload:
        j(handler, {"error": str(error), **error.payload}, status=error.status)
    else:
        bad(handler, str(error), error.status)
    return True


def _by_id(item_id: str):
    """Hermes' own notes and the Obsidian vault run side by side: vault note
    and folder ids start with "v" (api/notebook_vault.py)."""
    return notebook_vault if str(item_id or "").startswith("v") else notebook


def _flag(body_or_query, key: str):
    value = body_or_query.get(key) if isinstance(body_or_query, dict) else None
    if isinstance(value, list):
        value = value[0] if value else None
    return value


def _by_flag(body_or_query) -> object:
    """Connected, every note is in the vault (the main view's too)."""
    return notebook_vault if (_flag(body_or_query, "store") == "vault" or notebook_vault.enabled()) else notebook


_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
_CHUNK = 256 * 1024


def _send_file(handler, path: Path, mime: str, cache: str, name: str = "") -> None:
    """An uploaded image or audio/video is shown inline; any other file is only
    ever offered as a download, with no way to run or render in the page's
    origin. Audio and video honour single byte ranges (iOS will not play a file
    it cannot seek in)."""
    inline = mime in notebook.IMAGE_TYPES or mime in notebook.MEDIA_TYPES
    size = path.stat().st_size
    start, end, status = 0, size - 1, 200
    wanted = handler.headers.get("Range") if mime in notebook.MEDIA_TYPES else None
    if wanted:
        match = _RANGE.match(wanted.strip())
        if match and (match.group(1) or match.group(2)):
            if match.group(1):
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else size - 1
            else:  # "bytes=-N": the last N bytes
                start, end = max(0, size - int(match.group(2))), size - 1
            end = min(end, size - 1)
            if start > end or start >= size:
                handler.send_response(416)
                handler.send_header("Content-Range", f"bytes */{size}")
                handler.send_header("Content-Length", "0")
                handler.end_headers()
                return
            status = 206
    handler.send_response(status)
    handler.send_header("Content-Type", mime + ("; charset=utf-8" if mime.startswith("text/") else ""))
    handler.send_header("Content-Length", str(end - start + 1))
    handler.send_header("X-Content-Type-Options", "nosniff")
    if mime in notebook.MEDIA_TYPES:
        handler.send_header("Accept-Ranges", "bytes")
    if status == 206:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    if inline:
        handler.send_header("Content-Disposition", "inline")
    else:
        handler.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(name or 'download', safe='')}")
        handler.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
    handler.send_header("Cache-Control", cache)
    handler.end_headers()
    try:
        with path.open("rb") as source:
            source.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = source.read(min(_CHUNK, left))
                if not chunk:
                    break
                handler.wfile.write(chunk)
                left -= len(chunk)
    except (BrokenPipeError, ConnectionResetError):
        pass  # the player moved on (a seek opens a new request)


def handle_notebook_upload_stream(handler, parsed) -> bool:
    """POST /api/notebook/uploads/stream?filename=&note_id=: the raw bytes of an
    audio or video file as the body. The body is read here, in pieces, so it can
    be bigger than a JSON request is allowed to be."""
    query = parse_qs(parsed.query or "")
    one = lambda key: str((query.get(key) or [""])[0])  # noqa: E731
    try:
        length = int(handler.headers.get("Content-Length", "") or 0)
    except ValueError:
        length = 0
    try:
        store = _by_id(one("note_id"))
        j(handler, store.save_stream(handler.rfile, length, one("filename"), one("note_id") or None), status=201)
    except notebook.NotebookError as error:
        # Part of the body is unread; the connection cannot be reused.
        handler.close_connection = True
        return _fail(handler, error)
    return True


def _tail(path: str, prefix: str) -> list[str]:
    return [unquote(part) for part in path[len(prefix):].strip("/").split("/") if part]


def handle_notebook_get(handler, parsed) -> bool:
    path = parsed.path
    try:
        if path == f"{_PREFIX}/vault":
            j(handler, {"vault": notebook_vault.config()})
            return True
        if path == f"{_PREFIX}/vault/file":
            rel = str(parse_qs(parsed.query or "").get("path", [""])[0])
            path, mime, name = notebook_vault.file_path(rel)
            _send_file(handler, path, mime, "private, no-cache", name)
            return True
        if path == f"{_PREFIX}/bootstrap":
            # Connected: the main view laid out from the vault (00 Inbox,
            # 01 Projects/<workspace>, 03 Resources/<folder>), plus the whole
            # vault for the Obsidian view. Otherwise Hermes' own store.
            if notebook_vault.enabled():
                data = notebook_vault.main_bootstrap()
                data["vault"] = notebook_vault.bootstrap()
            else:
                data = notebook.bootstrap()
                data["vault"] = None
            data["vault_config"] = notebook_vault.config()
            j(handler, data)
            return True
        if path == f"{_PREFIX}/notes":
            query = parse_qs(parsed.query or "")
            q = str(query.get("q", [""])[0])
            trash = str(query.get("trash", [""])[0]) == "1"
            store = _by_flag(query)
            if store is notebook_vault:
                notes = store.search_notes(q, include_deleted=trash, main_only=_flag(query, "view") == "notes")
            else:
                notes = store.search_notes(q, include_deleted=trash)
            j(handler, {"notes": notes})
            return True
        if path.startswith(f"{_PREFIX}/notes/"):
            parts = _tail(path, f"{_PREFIX}/notes/")
            if len(parts) == 2 and parts[1] == "context":
                j(handler, {"context": _by_id(parts[0]).note_context(parts[0])})
                return True
            if len(parts) != 1:
                return bool(bad(handler, "Not found", 404)) or True
            j(handler, {"note": _by_id(parts[0]).get_note(parts[0])})
            return True
        if path.startswith(f"{_PREFIX}/files/"):
            parts = _tail(path, f"{_PREFIX}/files/")
            if len(parts) != 1:
                return bool(bad(handler, "Not found", 404)) or True
            path, mime, name = notebook.upload_path(parts[0])
            _send_file(handler, path, mime, "private, max-age=31536000, immutable", name)
            return True
    except notebook.NotebookError as error:
        return _fail(handler, error)
    return False


def handle_notebook_post(handler, parsed, body) -> bool:
    path = parsed.path
    body = body if isinstance(body, dict) else {}
    try:
        if path == f"{_PREFIX}/vault":
            j(handler, {"vault": notebook_vault.set_config(body)})
            return True
        if path == f"{_PREFIX}/vault/import":
            j(handler, notebook_vault.import_from_store())
            return True
        if path == f"{_PREFIX}/notes/create":
            j(handler, {"note": _by_flag(body).create_note(body)}, status=201)
            return True
        if path == f"{_PREFIX}/trash/empty":
            store = _by_flag(body)
            j(handler, store.empty_trash(main_only=body.get("view") == "notes") if store is notebook_vault else store.empty_trash())
            return True
        if path == f"{_PREFIX}/uploads":
            j(handler, _by_id(body.get("note_id")).save_upload(body), status=201)
            return True
        if path == f"{_PREFIX}/folders/create":
            j(handler, {"folder": _by_flag(body).create_folder(body)}, status=201)
            return True
        if path.startswith(f"{_PREFIX}/folders/"):
            parts = _tail(path, f"{_PREFIX}/folders/")
            store = _by_id(parts[0] if parts else "")
            if len(parts) == 2 and parts[1] == "rename":
                j(handler, {"folder": store.rename_folder(parts[0], body)})
                return True
            if len(parts) == 2 and parts[1] == "delete":
                j(handler, store.delete_folder(parts[0]))
                return True
            return bool(bad(handler, "Not found", 404)) or True
        if path.startswith(f"{_PREFIX}/notes/"):
            parts = _tail(path, f"{_PREFIX}/notes/")
            store = _by_id(parts[0] if parts else "")
            actions = {
                "update": lambda note_id: {"note": store.update_note(note_id, body)},
                "trash": lambda note_id: {"note": store.trash_note(note_id)},
                "restore": lambda note_id: {"note": store.restore_note(note_id)},
                "purge": store.purge_note,
                "duplicate": lambda note_id: {"note": store.duplicate_note(note_id)},
            }
            if len(parts) == 2 and parts[1] in actions:
                j(handler, actions[parts[1]](parts[0]))
                return True
            return bool(bad(handler, "Not found", 404)) or True
    except notebook.NotebookError as error:
        return _fail(handler, error)
    return False
