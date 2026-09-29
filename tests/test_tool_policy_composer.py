"""Composer contract for the session tool-policy control."""

from pathlib import Path


def test_composer_exposes_policy_actions_and_unavailable_state():
    root = Path(__file__).resolve().parents[1]
    source = (root / "static" / "ui.js").read_text(encoding="utf-8")

    assert "toolPolicy" in source
    assert "minimal_toolset_not_supported" in source
    assert "Minimal" in source
