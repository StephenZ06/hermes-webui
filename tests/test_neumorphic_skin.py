"""Neumorphic skin registration and dark dashboard palette affordances."""

from pathlib import Path


REPO = Path(__file__).parent.parent
CSS = (REPO / "static" / "style.css").read_text(encoding="utf-8")
BOOT_JS = (REPO / "static" / "boot.js").read_text(encoding="utf-8")
CONFIG_PY = (REPO / "api" / "config.py").read_text(encoding="utf-8")
INDEX_HTML = (REPO / "static" / "index.html").read_text(encoding="utf-8")


def test_neumorphic_skin_is_selectable_and_persistable():
    assert "{name:'Neumorphic', value:'neumorphic'" in BOOT_JS
    assert "'neumorphic':1" in INDEX_HTML
    assert '"neumorphic"' in CONFIG_PY


def test_neumorphic_skin_is_dark_and_uses_the_reference_palette():
    assert ':root.dark[data-skin="neumorphic"]' in CSS
    assert "--bg:#0E0E10" in CSS
    assert "--accent:#9B6CFF" in CSS
    assert "--accent-secondary:#F06AB4" in CSS
    assert "--accent-tertiary:#45C6F5" in CSS


def test_neumorphic_skin_has_raised_surface_and_focused_primary_action():
    assert ".neumorphic-surface" in CSS
    assert ".new-chat-btn" in CSS
    assert "linear-gradient(135deg,var(--accent),var(--accent-secondary))" in CSS


def test_teal_neumorphic_variant_preserves_the_dark_canvas():
    assert "{name:'Teal Neumorphic', value:'teal-neumorphic'" in BOOT_JS
    assert "'teal-neumorphic':1" in INDEX_HTML
    assert '"teal-neumorphic"' in CONFIG_PY
    assert ':root.dark[data-skin="teal-neumorphic"]' in CSS
    assert "--accent:#29C7B8" in CSS
