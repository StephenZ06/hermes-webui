"""
Knowledge Browser (read-only) — unified list/read/search across the
profile-scoped textual "knowledge" hermes-webui already persists on disk:

- MEMORY.md, split into individual ``§``-delimited facts (not one blob)
- USER.md / SOUL.md, each as a single item
- saved prompts (``webui/saved_prompts.json``)
- standalone prompt files under ``HERMES_HOME/prompts/*.md``

This is deliberately read-only: it never writes to any of these files. The
Memory tab (``/api/memory`` GET/write) already owns whole-file editing of
MEMORY.md/USER.md/SOUL.md, and a separate in-flight effort owns curating
individual MEMORY.md entries. This module only adds a searchable,
cross-type *browse* index on top of data that already exists.

See docs/HERMES_STUDIO_PARITY_PLAN.md, "Knowledge Browser", for the full
design, the data-source investigation that ruled out a fabricated graph
view, and the (resolved) open questions this module implements.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SNIPPET_MAX = 220
SEARCH_QUERY_MAX = 200
SEARCH_RESULTS_MAX = 50
PROMPT_FILE_MAX_BYTES = 20_000
PROMPT_FILE_GLOB_MAX = 200
MEMORY_ENTRY_MAX = 300

_MEMORY_ENTRY_SEP_RE = re.compile(r"\n§\n|\r\n§\r\n")


def _hermes_home() -> Path:
    try:
        from api.profiles import get_active_hermes_home
        return Path(get_active_hermes_home()).expanduser()
    except Exception:
        import os
        return Path(os.getenv("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser()


def _webui_truthy(value) -> bool:
    # Intentionally mirrors api.routes._webui_truthy byte-for-byte so this
    # module's memory_enabled/user_profile_enabled gating can never drift
    # from what /api/memory (GET) itself honors.
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _memory_flags() -> tuple[bool, bool]:
    """Return (memory_enabled, user_profile_enabled), same flags /api/memory honors."""
    try:
        from api.config import get_config_snapshot
        cfg = get_config_snapshot()
        mem = cfg.get("memory") if isinstance(cfg, dict) else None
        mem_cfg = mem if isinstance(mem, dict) else {}
        return (
            _webui_truthy(mem_cfg.get("memory_enabled", True)),
            _webui_truthy(mem_cfg.get("user_profile_enabled", True)),
        )
    except Exception:
        return True, True


def _snippet(text: str, limit: int = SNIPPET_MAX) -> str:
    flat = " ".join((text or "").split())
    if len(flat) <= limit:
        return flat
    return flat[:limit].rstrip() + "…"


def _load_saved_prompts(home: Path) -> list:
    p = home / "webui" / "saved_prompts.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _memory_entries(home: Path) -> list[str]:
    mem_path = home / "memories" / "MEMORY.md"
    if not mem_path.exists():
        return []
    try:
        raw = mem_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    parts = [p.strip() for p in _MEMORY_ENTRY_SEP_RE.split(raw) if p.strip()]
    return parts[:MEMORY_ENTRY_MAX]


def _prompt_files(home: Path) -> list[Path]:
    prompts_dir = home / "prompts"
    if not prompts_dir.is_dir():
        return []
    try:
        files = sorted(
            (f for f in prompts_dir.glob("*.md") if f.is_file()),
            key=lambda f: f.name,
        )
    except OSError:
        return []
    return files[:PROMPT_FILE_GLOB_MAX]


def _all_items(home: Path) -> list[dict]:
    """Build the full in-memory item list (with content) for this profile's home.

    Internal — callers should go through list_items()/read_item()/search_items()
    so the id scheme and caps stay in one place.
    """
    items: list[dict] = []
    memory_enabled, user_profile_enabled = _memory_flags()

    if memory_enabled:
        mem_path = home / "memories" / "MEMORY.md"
        mtime = mem_path.stat().st_mtime if mem_path.exists() else None
        for idx, entry in enumerate(_memory_entries(home)):
            items.append({
                "id": f"memory:{idx}",
                "type": "memory",
                "title": _snippet(entry, 70),
                "content": entry,
                "source_path": str(mem_path),
                "updated_at": mtime,
            })

    if user_profile_enabled:
        user_path = home / "memories" / "USER.md"
        if user_path.exists():
            try:
                content = user_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                content = ""
            if content.strip():
                items.append({
                    "id": "user:0",
                    "type": "user",
                    "title": _snippet(content, 70),
                    "content": content,
                    "source_path": str(user_path),
                    "updated_at": user_path.stat().st_mtime,
                })

    soul_path = home / "SOUL.md"
    if soul_path.exists():
        try:
            content = soul_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            content = ""
        if content.strip():
            items.append({
                "id": "soul:0",
                "type": "soul",
                "title": _snippet(content, 70),
                "content": content,
                "source_path": str(soul_path),
                "updated_at": soul_path.stat().st_mtime,
            })

    for row in _load_saved_prompts(home):
        if not isinstance(row, dict):
            continue
        pid = row.get("id")
        text = str(row.get("text") or "")
        if not pid or not text:
            continue
        label = str(row.get("label") or "").strip() or _snippet(text, 70)
        items.append({
            "id": f"saved_prompt:{pid}",
            "type": "saved_prompt",
            "title": label,
            "content": text,
            "source_path": str(home / "webui" / "saved_prompts.json"),
            "updated_at": row.get("created_at"),
        })

    for f in _prompt_files(home):
        try:
            data = f.read_bytes()[:PROMPT_FILE_MAX_BYTES]
            content = data.decode("utf-8", errors="replace")
        except OSError:
            continue
        if not content.strip():
            continue
        items.append({
            "id": f"prompt_file:{f.name}",
            "type": "prompt_file",
            "title": f.stem,
            "content": content,
            "source_path": str(f),
            "updated_at": f.stat().st_mtime,
        })

    return items


def _redact(text: str) -> str:
    try:
        from api.helpers import _redact_text
        return _redact_text(text)
    except Exception:
        return text


def list_items() -> dict:
    """Return the lightweight list shape (no full content)."""
    home = _hermes_home()
    rows = []
    for item in _all_items(home):
        rows.append({
            "id": item["id"],
            "type": item["type"],
            "title": _redact(item["title"]),
            "snippet": _redact(_snippet(item["content"])),
            "source_path": item["source_path"],
            "updated_at": item["updated_at"],
        })
    return {"items": rows}


def read_item(item_id: str) -> dict | None:
    """Return the full item (with content) for item_id, or None if not found.

    Re-derives the item from the same enumeration list_items() uses rather
    than building a filesystem path from client input, so an unrecognized or
    hostile id can never read outside the enumerated set.
    """
    item_id = str(item_id or "").strip()
    if not item_id:
        return None
    home = _hermes_home()
    for item in _all_items(home):
        if item["id"] == item_id:
            return {
                "id": item["id"],
                "type": item["type"],
                "title": _redact(item["title"]),
                "content": _redact(item["content"]),
                "source_path": item["source_path"],
                "updated_at": item["updated_at"],
            }
    return None


def search_items(query: str) -> dict:
    """Case-insensitive substring search across title + full content."""
    query = str(query or "").strip()[:SEARCH_QUERY_MAX]
    if not query:
        return {"query": query, "results": []}
    needle = query.lower()
    home = _hermes_home()
    results = []
    for item in _all_items(home):
        haystack = f"{item['title']}\n{item['content']}".lower()
        if needle not in haystack:
            continue
        results.append({
            "id": item["id"],
            "type": item["type"],
            "title": _redact(item["title"]),
            "snippet": _redact(_snippet(item["content"])),
            "source_path": item["source_path"],
            "updated_at": item["updated_at"],
        })
        if len(results) >= SEARCH_RESULTS_MAX:
            break
    return {"query": query, "results": results}
