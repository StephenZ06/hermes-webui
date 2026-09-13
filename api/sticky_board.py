"""Server-side storage for the Sticky Board (static/vendor/sticky-board/,
a vendored third-party Kanban-style note board, see PROVENANCE.md there).

Upstream persists to the browser's own localStorage -- per-browser, not
synced across devices. This module backs it with a flat JSON document at
STATE_DIR/sticky_board.json instead (same load/save-whole convention as
api/models.py's load_projects()/PROJECTS_FILE), so the board is shared
across every browser/device that opens this hermes-webui instance.

The stored shape is exactly what the board's own client-side `state` object
already is -- ``{"columns": [{"id", "title", "color", "notes": [...]}]}`` --
no transformation needed between the two.
"""
import json

from api.config import STATE_DIR

BOARD_FILE = STATE_DIR / "sticky_board.json"


def load_board():
    """Return the saved board dict, or None if nothing has been saved yet
    (the client falls back to its own built-in starter columns in that case)."""
    if not BOARD_FILE.exists():
        return None
    try:
        data = json.loads(BOARD_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def save_board(data) -> None:
    BOARD_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
