"""
Personas (internal name: Agent Library / agent_definitions) storage.

A user-owned CRUD collection of named agent personas (emoji + color icon,
role, tags, editable system prompt). Modeled on api/routes.py's
_saved_prompts_path()/_load_saved_prompts()/_save_saved_prompts() pattern:
storage lives under the active profile's Hermes home, so definitions are
profile-scoped for free via the existing profile-switch mechanism, with no
extra ownership bookkeeping needed.

Built-ins ship as an in-memory constant merged in at read time and are never
written into the user's JSON file, so a v1 seed list can't drift out of sync
with repo updates. Mutation is rejected on builtin ids; duplicate always
produces a new custom row.

See docs/HERMES_STUDIO_PARITY_PLAN.md, "Priority 1 -- Personas", for the
full design and the (resolved) open questions this module implements.
"""
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

NAME_MAX = 128
ROLE_MAX = 256
SYSTEM_PROMPT_MAX = 8000
TAGS_MAX = 10
TAG_MAX = 32
EMOJI_MAX = 8
MAX_CUSTOM_DEFINITIONS = 100

_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")

# Read-modify-write is not otherwise atomic across two concurrent requests
# for the same profile (the JSON file has no row-level locking); this lock
# closes that window for the common case of two webui tabs open at once.
_WRITE_LOCK = threading.Lock()

BUILTIN_DEFINITIONS = [
    {
        "id": "builtin:default",
        "name": "Default Assistant",
        "emoji": "\U0001F916",
        "color": "#7cb9ff",
        "role": "General-purpose helpful assistant",
        "tags": ["general"],
        "system_prompt": "",
        "builtin": True,
        "created_at": 0.0,
        "updated_at": 0.0,
    },
    {
        "id": "builtin:code-reviewer",
        "name": "Code Reviewer",
        "emoji": "\U0001F50D",
        "color": "#7cd992",
        "role": "Reviews diffs for bugs, style issues, and simplification opportunities",
        "tags": ["review", "quality"],
        "system_prompt": (
            "You are a meticulous code reviewer. Focus on correctness bugs, "
            "security issues, and unnecessary complexity. Be specific: cite "
            "file paths and line numbers. Prefer the smallest fix that solves "
            "the class of problem, not just the instance in front of you."
        ),
        "builtin": True,
        "created_at": 0.0,
        "updated_at": 0.0,
    },
    {
        "id": "builtin:writer",
        "name": "Technical Writer",
        "emoji": "✍️",
        "color": "#e0a95c",
        "role": "Writes and edits clear, concise documentation",
        "tags": ["docs", "writing"],
        "system_prompt": (
            "You are a technical writer. Write in plain, concise language. "
            "Prefer active voice and short sentences. Cut anything that "
            "doesn't help the reader act or understand."
        ),
        "builtin": True,
        "created_at": 0.0,
        "updated_at": 0.0,
    },
]

_BUILTIN_IDS = {d["id"] for d in BUILTIN_DEFINITIONS}


def _agent_definitions_path() -> Path:
    try:
        from api.profiles import get_active_hermes_home
        return Path(get_active_hermes_home()).expanduser() / "webui" / "agent_definitions.json"
    except Exception:
        return Path(os.getenv("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser() / "webui" / "agent_definitions.json"


def _atomic_write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(f".tmp.{os.getpid()}.{threading.get_ident()}")
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _load_custom_definitions() -> list:
    p = _agent_definitions_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_custom_definitions(definitions: list) -> None:
    _atomic_write(_agent_definitions_path(), definitions)


def _validate_color(color) -> None:
    if color and not _COLOR_RE.match(color):
        raise ValueError("Invalid color format")


def _clean_tags(tags) -> list:
    if tags is None:
        return []
    if not isinstance(tags, list):
        raise ValueError("tags must be a list")
    cleaned = []
    for tag in tags[:TAGS_MAX]:
        tag = str(tag).strip()[:TAG_MAX]
        if tag:
            cleaned.append(tag)
    return cleaned


def list_definitions() -> dict:
    custom = _load_custom_definitions()
    return {
        "definitions": [*BUILTIN_DEFINITIONS, *custom],
        "builtin_count": len(BUILTIN_DEFINITIONS),
    }


def create_definition(body: dict) -> dict:
    name = str(body.get("name") or "").strip()[:NAME_MAX]
    if not name:
        raise ValueError("name is required")
    system_prompt = str(body.get("system_prompt") or "")
    if len(system_prompt) > SYSTEM_PROMPT_MAX:
        raise ValueError(f"system_prompt too long (max {SYSTEM_PROMPT_MAX} chars)")
    color = body.get("color")
    _validate_color(color)
    role = str(body.get("role") or "").strip()[:ROLE_MAX]
    emoji = str(body.get("emoji") or "").strip()[:EMOJI_MAX]
    tags = _clean_tags(body.get("tags"))

    with _WRITE_LOCK:
        custom = _load_custom_definitions()
        if len(custom) >= MAX_CUSTOM_DEFINITIONS:
            raise ValueError(f"persona limit reached (max {MAX_CUSTOM_DEFINITIONS})")
        now = time.time()
        definition = {
            "id": uuid.uuid4().hex[:12],
            "name": name,
            "emoji": emoji,
            "color": color,
            "role": role,
            "tags": tags,
            "system_prompt": system_prompt,
            "builtin": False,
            "created_at": now,
            "updated_at": now,
        }
        custom.append(definition)
        _save_custom_definitions(custom)
    return definition


def update_definition(body: dict) -> dict:
    def_id = str(body.get("id") or "").strip()
    if not def_id:
        raise ValueError("id is required")
    if def_id in _BUILTIN_IDS:
        raise PermissionError("Built-in agent definitions cannot be edited")

    # Validate/normalize before taking the lock so a bad request never
    # partially mutates the in-memory row.
    updates = {}
    if "name" in body:
        name = str(body.get("name") or "").strip()[:NAME_MAX]
        if not name:
            raise ValueError("name is required")
        updates["name"] = name
    if "system_prompt" in body:
        system_prompt = str(body.get("system_prompt") or "")
        if len(system_prompt) > SYSTEM_PROMPT_MAX:
            raise ValueError(f"system_prompt too long (max {SYSTEM_PROMPT_MAX} chars)")
        updates["system_prompt"] = system_prompt
    if "color" in body:
        _validate_color(body.get("color"))
        updates["color"] = body.get("color")
    if "role" in body:
        updates["role"] = str(body.get("role") or "").strip()[:ROLE_MAX]
    if "emoji" in body:
        updates["emoji"] = str(body.get("emoji") or "").strip()[:EMOJI_MAX]
    if "tags" in body:
        updates["tags"] = _clean_tags(body.get("tags"))

    with _WRITE_LOCK:
        custom = _load_custom_definitions()
        definition = next((d for d in custom if d.get("id") == def_id), None)
        if definition is None:
            raise KeyError("Persona not found")
        definition.update(updates)
        definition["updated_at"] = time.time()
        _save_custom_definitions(custom)
        return definition


def delete_definition(def_id: str) -> None:
    def_id = str(def_id or "").strip()
    if not def_id:
        raise ValueError("id is required")
    if def_id in _BUILTIN_IDS:
        raise PermissionError("Built-in agent definitions cannot be deleted")
    with _WRITE_LOCK:
        custom = _load_custom_definitions()
        remaining = [d for d in custom if d.get("id") != def_id]
        if len(remaining) == len(custom):
            raise KeyError("Persona not found")
        _save_custom_definitions(remaining)


def duplicate_definition(def_id: str) -> dict:
    def_id = str(def_id or "").strip()
    if not def_id:
        raise ValueError("id is required")
    with _WRITE_LOCK:
        custom = _load_custom_definitions()
        source = next(
            (d for d in [*BUILTIN_DEFINITIONS, *custom] if d.get("id") == def_id),
            None,
        )
        if source is None:
            raise KeyError("Persona not found")
        if len(custom) >= MAX_CUSTOM_DEFINITIONS:
            raise ValueError(f"persona limit reached (max {MAX_CUSTOM_DEFINITIONS})")

        now = time.time()
        new_def = {
            "id": uuid.uuid4().hex[:12],
            "name": (source.get("name") or "Persona") + " (copy)",
            "emoji": source.get("emoji") or "",
            "color": source.get("color"),
            "role": source.get("role") or "",
            "tags": list(source.get("tags") or []),
            "system_prompt": source.get("system_prompt") or "",
            "builtin": False,
            "created_at": now,
            "updated_at": now,
        }
        custom.append(new_def)
        _save_custom_definitions(custom)
        return new_def
