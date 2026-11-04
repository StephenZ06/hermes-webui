"""Obsidian adapter: the connected vault, seen only through explicit grants.

A grant names the vault as well as the folder, so reconnecting a different
vault grants nothing. Each operation needs the folder grant *and* that agent's
own flag. Wikilinks are plain text here: a link never widens access.

The revision is a hash of the file's bytes, not its modification time, so the
check does not depend on how a mount reports timestamps. The check runs
immediately before an atomic replace. That closes the window against this
process and against an edit already saved, but not against a writer that lands
in the instant between check and replace; the file is re-read afterwards and a
mismatch is reported as an uncertain outcome instead of a success.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from api import notebook_vault as vault
from api.business_office import store
from api.business_office.errors import ToolError, denied

_FLAG = {"obsidian.search_notes": "can_search", "obsidian.read_note": "can_read",
         "obsidian.create_note": "can_create", "obsidian.edit_note": "can_edit"}
_SNIPPET = 240


def _root() -> Path:
    try:
        return vault._root()
    except vault.NotebookError:
        raise ToolError("unavailable", "No Obsidian vault is connected") from None


def _folders(business_id: str, agent_id: str, flag: str, root: Path) -> list[str]:
    folders = []
    for grant in store.list_vault_grants(business_id):
        if grant["vault"] == str(root) and (grant["agents"].get(agent_id) or {}).get(flag):
            folders.append(grant["folder"])
    return folders


def _covered(rel: str, folders: list[str]) -> bool:
    return any(rel == folder or rel.startswith(folder + "/") for folder in folders)


def normal_folder(root: Path, raw: object) -> str:
    """Validate a folder for a new grant; it must exist inside the vault."""
    rel = str(raw or "").strip().strip("/")
    try:
        path = vault._inside(root, rel)
    except vault.NotebookError:
        raise store.StoreError("That folder is not inside the vault") from None
    if not path.is_dir():
        raise store.StoreError("That folder does not exist in the vault")
    return rel


def _path(root: Path, rel: str) -> Path:
    try:
        return vault._inside(root, rel)
    except vault.NotebookError:
        raise denied("That path is not allowed") from None


def _bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        raise ToolError("not_found", "That note does not exist") from None


def _revision(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:32]


def _source(rel: str, revision: str) -> dict[str, str]:
    return {"path": rel, "revision": revision}


def preview(capability_id: str, values: dict[str, Any], business_id: str) -> dict[str, Any]:
    return dict(values)


def _search(values: dict[str, Any], root: Path, folders: list[str]) -> dict[str, Any]:
    words = [word for word in values["query"].lower().split() if word]
    limit = max(1, min(int(values.get("limit") or 20), 50))
    rows = []
    for path in vault._walk_notes(root, trash=False):
        rel = vault._rel(root, path)
        if not _covered(rel, folders):
            continue
        data = _bytes(path)
        text = data.decode("utf-8", "replace")
        if all(word in (path.stem + "\n" + text).lower() for word in words):
            _front, body = vault._split(text)
            rows.append({"title": path.stem, "snippet": body.strip()[:_SNIPPET], "source": _source(rel, _revision(data))})
            if len(rows) >= limit:
                break
    return {"notes": rows}


def _read(values: dict[str, Any], root: Path, folders: list[str]) -> dict[str, Any]:
    rel = values["path"]
    if not rel.endswith(".md") or not _covered(rel, folders):
        raise denied("That note is outside the granted folders")
    data = _bytes(_path(root, rel))
    front, body = vault._split(data.decode("utf-8", "replace"))
    return {"title": Path(rel).stem, "frontmatter": front, "body": body, "source": _source(rel, _revision(data))}


def _create(values: dict[str, Any], root: Path, folders: list[str]) -> dict[str, Any]:
    folder = values["folder"].strip("/")
    if not _covered(folder, folders):
        raise denied("That folder is not granted")
    try:
        name = vault._file_name(vault._clean_title(values["title"]))
    except vault.NotebookError as error:
        raise ToolError("rejected", str(error)) from None
    rel = f"{folder}/{name}.md"
    path = _path(root, rel)
    if not path.parent.is_dir():
        raise ToolError("not_found", "That folder does not exist")
    data = values["body"].encode("utf-8")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        raise ToolError("conflict", "A note with this title already exists") from None
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    return {"created": True, "source": _source(rel, _revision(data))}


def _edit(values: dict[str, Any], root: Path, folders: list[str]) -> dict[str, Any]:
    rel = values["path"]
    if not rel.endswith(".md") or not _covered(rel, folders):
        raise denied("That note is outside the granted folders")
    path = _path(root, rel)
    with vault._LOCK:
        before = _bytes(path)
        if _revision(before) != values["expected_revision"]:
            raise ToolError("conflict", "This note changed since it was read")
        text = before.decode("utf-8")
        count = text.count(values["find"])
        if count != 1:
            raise ToolError("rejected", "The text to replace must appear exactly once")
        updated = text.replace(values["find"], values["replace"]).encode("utf-8")
        if _bytes(path) != before:
            raise ToolError("conflict", "This note changed since it was read")
        try:
            vault._write(path, updated.decode("utf-8"))
        except (OSError, vault.NotebookError):
            raise ToolError("uncertain", "The write may not have finished. Check the note.") from None
        if _bytes(path) != updated:
            raise ToolError("uncertain", "The note differs from what was written. Another edit may have landed.")
    return {"edited": True, "source": _source(rel, _revision(updated))}


_OPERATIONS = {"obsidian.search_notes": _search, "obsidian.read_note": _read,
               "obsidian.create_note": _create, "obsidian.edit_note": _edit}


def invoke(capability_id: str, values: dict[str, Any], business_id: str, agent_id: str) -> dict[str, Any]:
    root = _root()
    folders = _folders(business_id, agent_id, _FLAG[capability_id], root)
    if not folders:
        raise denied("This agent has no folder grant for that operation")
    return _OPERATIONS[capability_id](values, root, folders)
