from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
STYLE = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


def test_initial_theme_color_is_resynced_after_skin_css_is_available():
    css_pos = INDEX.index('rel="stylesheet" href="static/style.css')
    sync_pos = INDEX.index("data-initial-theme-color-sync")
    assert sync_pos > css_pos
    block = INDEX[sync_pos:sync_pos + 900]
    assert "getComputedStyle(document.documentElement)" in block
    assert "--sidebar" in block
    assert "meta[name=\"theme-color\"]" in block


def test_mobile_sidebar_panel_titles_are_visually_centered():
    assert ".sidebar .panel-head>span:first-child" in STYLE
    rule = STYLE[STYLE.index(".sidebar .panel-head>span:first-child"):]
    rule = rule[:rule.index("}") + 1]
    assert "left:50%" in rule and "translateX(-50%)" in rule
