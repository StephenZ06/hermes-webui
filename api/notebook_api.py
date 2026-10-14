"""HTTP routes for Notes (api/notebook.py), mounted under /api/notebook/."""

from __future__ import annotations

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


def _send_image(handler, data: bytes, mime: str, cache: str, name: str = "") -> None:
    """An uploaded image is shown inline; any other file is only ever offered as
    a download, with no way to run or render in the page's origin."""
    inline = mime in notebook.IMAGE_TYPES
    handler.send_response(200)
    handler.send_header("Content-Type", mime if inline else mime + ("; charset=utf-8" if mime.startswith("text/") else ""))
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("X-Content-Type-Options", "nosniff")
    if inline:
        handler.send_header("Content-Disposition", "inline")
    else:
        safe = quote(name or "download", safe="")
        handler.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{safe}")
        handler.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
    handler.send_header("Cache-Control", cache)
    handler.end_headers()
    handler.wfile.write(data)


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
            data, mime, name = notebook_vault.read_file(rel)
            _send_image(handler, data, mime, "private, no-cache", name)
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
            data, mime, name = notebook.read_upload(parts[0])
            _send_image(handler, data, mime, "private, max-age=31536000, immutable", name)
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
