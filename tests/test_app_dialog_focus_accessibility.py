"""Regression tests for dialog focus before its overlay is hidden."""

from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
UI_JS = REPO / "static" / "ui.js"


def _function_body(source: str, function_name: str) -> str:
    start = source.index(f"function {function_name}")
    return source[start: source.index("\nfunction ", start + 1)]


def test_finish_dialog_releases_descendant_focus_before_hiding_overlay():
    body = _function_body(UI_JS.read_text(encoding="utf-8"), "_finishAppDialog")

    assert "overlay.contains(document.activeElement)" in body
    assert "document.activeElement.blur()" in body
    assert body.index("document.activeElement.blur()") < body.index("overlay.setAttribute('aria-hidden','true')")
    assert "overlay.setAttribute('inert','')" in body


def test_opening_a_dialog_removes_inert_before_showing_the_overlay():
    source = UI_JS.read_text(encoding="utf-8")

    for function_name in ("showConfirmDialog", "showPromptDialog"):
        body = _function_body(source, function_name)
        assert "overlay.removeAttribute('inert')" in body
        assert body.index("overlay.removeAttribute('inert')") < body.index("overlay.setAttribute('aria-hidden','false')")
