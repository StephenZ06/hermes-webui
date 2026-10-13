"""HTTP routes for Notes (api/notebook.py), mounted under /api/notebook/."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote

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


def _by_flag(body_or_query) -> object:
    value = body_or_query.get("store") if isinstance(body_or_query, dict) else None
    if isinstance(value, list):
        value = value[0] if value else None
    return notebook_vault if value == "vault" else notebook


def _send_image(handler, data: bytes, mime: str, cache: str) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", mime)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Content-Disposition", "inline")
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
            data, mime = notebook_vault.read_file(rel)
            _send_image(handler, data, mime, "private, no-cache")
            return True
        if path == f"{_PREFIX}/bootstrap":
            # Hermes' own notes, plus the connected vault's alongside them.
            data = notebook.bootstrap()
            data["vault"] = notebook_vault.bootstrap() if notebook_vault.enabled() else None
            data["vault_config"] = notebook_vault.config()
            j(handler, data)
            return True
        if path == f"{_PREFIX}/notes":
            query = parse_qs(parsed.query or "")
            q = str(query.get("q", [""])[0])
            trash = str(query.get("trash", [""])[0]) == "1"
            j(handler, {"notes": _by_flag(query).search_notes(q, include_deleted=trash)})
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
            data, mime = notebook.read_upload(parts[0])
            _send_image(handler, data, mime, "private, max-age=31536000, immutable")
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
        if path == f"{_PREFIX}/notes/create":
            store = notebook_vault if (body.get("store") == "vault" or str(body.get("folder_id") or "").startswith("v")) else notebook
            j(handler, {"note": store.create_note(body)}, status=201)
            return True
        if path == f"{_PREFIX}/trash/empty":
            j(handler, _by_flag(body).empty_trash())
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
