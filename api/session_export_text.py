"""Markdown and plain-Text export for a hermes-webui session transcript.

Sibling to ``api/session_export_html.py`` (which handles the ``format=html``
export branch) — this module supplies the ``format=md`` and ``format=text``
branches of the same ``GET /api/session/export`` endpoint
(``api/routes.py:_handle_session_export``). It reuses that module's content
flattening / timestamp formatting / role labels rather than duplicating them,
so all three text-ish export formats (md/text/html) treat multimodal content,
timestamps, and role names identically.

Public entry points:
    render_session_markdown(session_dict) -> str
    render_session_text(session_dict) -> str

See docs/HERMES_STUDIO_PARITY_PLAN.md, "Priority 3 -- Chat export".
"""
from __future__ import annotations

from typing import Any

from api.session_export_html import _ROLE_LABELS, _content_to_text, _fmt_ts


def _visible_messages(session: dict) -> list[dict]:
    messages = session.get("messages") or []
    # Skip system messages, matching the existing format=html branch's
    # behavior (usually long boilerplate, not part of the human-readable
    # conversation).
    return [m for m in messages if isinstance(m, dict) and m.get("role") != "system"]


def _attachments_suffix(m: dict) -> str:
    attachments = m.get("attachments")
    if not attachments:
        return ""
    names = [str(a) for a in attachments if a]
    if not names:
        return ""
    return "Files: " + ", ".join(names)


def render_session_markdown(session: dict) -> str:
    """Render a session transcript as Markdown (mirrors static/messages.js's
    client-side ``transcript()`` structure so the two stay visually
    consistent, without importing JS into Python)."""
    title = (session.get("title") or "Hermes Conversation").strip()
    sid = session.get("session_id", "")
    model = session.get("model", "")
    workspace = session.get("workspace", "")

    lines: list[str] = [f"# {title or 'Hermes session'} {sid}".strip(), ""]
    if workspace:
        lines.append(f"Workspace: {workspace}")
    if model:
        lines.append(f"Model: {model}")
    lines.append("")

    for m in _visible_messages(session):
        role = m.get("role", "")
        body = _content_to_text(m.get("content")).strip()
        attach = _attachments_suffix(m)
        if not body and not attach:
            continue
        lines.append(f"## {role}")
        lines.append("")
        lines.append(body)
        if attach:
            lines.append("")
            lines.append(f"_{attach}_")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_session_text(session: dict) -> str:
    """Render a session transcript as plain text (no Markdown syntax) — for
    readers/tools that don't render Markdown."""
    title = (session.get("title") or "Hermes Conversation").strip()
    sid = session.get("session_id", "")
    model = session.get("model", "")
    workspace = session.get("workspace", "")

    lines: list[str] = [title or "Hermes session", f"Session: {sid}".rstrip()]
    if workspace:
        lines.append(f"Workspace: {workspace}")
    if model:
        lines.append(f"Model: {model}")
    lines.append("=" * 40)
    lines.append("")

    for m in _visible_messages(session):
        role = m.get("role", "")
        label, _cls = _ROLE_LABELS.get(role, (role or "?", ""))
        ts = _fmt_ts(m.get("timestamp"))
        body = _content_to_text(m.get("content")).strip()
        attach = _attachments_suffix(m)
        if not body and not attach:
            continue
        header = f"{label.upper()}"
        if ts:
            header += f" ({ts})"
        lines.append(header + ":")
        lines.append(body)
        if attach:
            lines.append(attach)
        lines.append("")
        lines.append("-" * 40)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
