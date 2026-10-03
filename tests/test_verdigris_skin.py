"""Workspace skin registration and dark, graphite workbench affordances."""

from pathlib import Path

REPO = Path(__file__).parent.parent
CSS = (REPO / "static" / "style.css").read_text(encoding="utf-8")
BOOT_JS = (REPO / "static" / "boot.js").read_text(encoding="utf-8")
CONFIG_PY = (REPO / "api" / "config.py").read_text(encoding="utf-8")
INDEX_HTML = (REPO / "static" / "index.html").read_text(encoding="utf-8")
I18N_JS = (REPO / "static" / "i18n.js").read_text(encoding="utf-8")


def test_workspace_skin_preserves_the_verdigris_preference_key():
    assert "{name:'Workspace', value:'verdigris'" in BOOT_JS
    assert "'verdigris':1" in INDEX_HTML
    assert '"verdigris"' in CONFIG_PY


def test_workspace_dark_palette_is_graphite():
    assert ':root.dark[data-skin="verdigris"]' in CSS
    assert "--bg:#101412" in CSS
    assert "--sidebar:#161B18" in CSS
    assert "--border:#2C3530" in CSS


def test_workspace_accent_is_muted_mint():
    assert "--accent:#78C7A3" in CSS
    assert "--accent-hover:#92D5B6" in CSS
    assert "--focus-ring:rgba(120,199,163,.28)" in CSS


def test_verdigris_has_no_light_variant():
    # The skin is dark-only; no light root block should be registered.
    assert ':root[data-skin="verdigris"]{' not in CSS
    assert ':root[data-skin=\"verdigris\"]{\n' not in CSS


def test_verdigris_i18n_lists_skin_in_all_locales():
    # There are 12 locales; each should now include verdigris as the trailing skin.
    # 10 locales use ASCII closing paren, 2 Chinese locales use full-width paren.
    assert I18N_JS.count("verdigris)") + I18N_JS.count("verdigris）") == 15
