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


def _store():
    """The connected Obsidian vault when there is one, else Hermes' own store."""
    return notebook_vault if notebook_vault.enabled() else notebook


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
        store = _store()
        if path == f"{_PREFIX}/bootstrap":
            data = store.bootstrap()
            data.setdefault("vault", None)
            data["vault_config"] = notebook_vault.config()
            j(handler, data)
            return True
        if path == f"{_PREFIX}/notes":
            query = parse_qs(parsed.query or "")
            q = str(query.get("q", [""])[0])
            trash = str(query.get("trash", [""])[0]) == "1"
            j(handler, {"notes": store.search_notes(q, include_deleted=trash)})
            return True
        if path.startswith(f"{_PREFIX}/notes/"):
            parts = _tail(path, f"{_PREFIX}/notes/")
            if len(parts) == 2 and parts[1] == "context":
                j(handler, {"context": store.note_context(parts[0])})
                return True
            if len(parts) != 1:
                return bool(bad(handler, "Not found", 404)) or True
            j(handler, {"note": store.get_note(parts[0])})
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
        store = _store()
        if path == f"{_PREFIX}/notes/create":
            j(handler, {"note": store.create_note(body)}, status=201)
            return True
        if path == f"{_PREFIX}/trash/empty":
            j(handler, store.empty_trash())
            return True
        if path == f"{_PREFIX}/uploads":
            j(handler, store.save_upload(body), status=201)
            return True
        if path == f"{_PREFIX}/folders/create":
            j(handler, {"folder": store.create_folder(body)}, status=201)
            return True
        if path.startswith(f"{_PREFIX}/folders/"):
            parts = _tail(path, f"{_PREFIX}/folders/")
            if len(parts) == 2 and parts[1] == "rename":
                j(handler, {"folder": store.rename_folder(parts[0], body)})
                return True
            if len(parts) == 2 and parts[1] == "delete":
                j(handler, store.delete_folder(parts[0]))
                return True
            return bool(bad(handler, "Not found", 404)) or True
        if path.startswith(f"{_PREFIX}/notes/"):
            parts = _tail(path, f"{_PREFIX}/notes/")
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
