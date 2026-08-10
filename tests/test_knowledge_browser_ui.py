"""Knowledge Browser UI wiring guards.

Structural checks (not a browser test) pinning that the nav tab, panel
container, main detail pane, and JS functions introduced for the Knowledge
Browser feature stay wired together. See
docs/HERMES_STUDIO_PARITY_PLAN.md, "Knowledge Browser".
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def test_nav_tab_and_panel_containers_present():
    html = read("static/index.html")
    assert 'data-panel="knowledge"' in html
    assert "onclick=\"switchPanel('knowledge'" in html
    assert 'id="panelKnowledge"' in html
    assert 'id="mainKnowledge"' in html
    assert 'id="knowledgeList"' in html
    assert 'id="knowledgeSearch"' in html
    assert 'id="knowledgeDetailTitle"' in html
    assert 'id="knowledgeDetailBody"' in html
    assert 'id="knowledgeDetailEmpty"' in html


def test_main_view_css_wiring_present():
    css = read("static/style.css")
    assert "main.main > #mainKnowledge" in css
    assert "main.main.showing-knowledge > #mainKnowledge{display:flex;}" in css
    assert ":not(.showing-knowledge)" in css


def test_panels_js_core_wiring_present():
    js = read("static/panels.js")
    for fn in (
        "loadKnowledgeItems", "renderKnowledgeItems", "searchKnowledgeItems",
        "openKnowledgeItem", "_renderKnowledgeDetail",
    ):
        assert f"function {fn}(" in js, f"{fn} not defined in panels.js"
    assert "'knowledge'" in js.split("MAIN_VIEW_PANELS")[1][:200]
    assert re.search(r"api\('/api/knowledge/list'\)", js)
    assert re.search(r"api\(`/api/knowledge/read\?id=", js)
    assert re.search(r"api\(`/api/knowledge/search\?q=", js)


def test_read_only_no_create_edit_delete_buttons():
    """Knowledge Browser is read-only in v1 — no create/edit/delete affordances."""
    html = read("static/index.html")
    panel_match = re.search(r'<div class="panel-view" id="panelKnowledge">.*?</div>\s*<!-- Todo panel -->', html, re.DOTALL)
    assert panel_match, "panelKnowledge block not found"
    panel_html = panel_match.group(0)
    assert "openKnowledgeCreate" not in panel_html
    assert "onclick=\"deleteKnowledge" not in panel_html


def test_i18n_keys_present_in_all_15_locales():
    src = read("static/i18n.js")
    required_keys = [
        "tab_knowledge", "search_knowledge", "knowledge_empty_title", "knowledge_empty_sub",
        "knowledge_no_match", "knowledge_type_memory", "knowledge_type_user", "knowledge_type_soul",
        "knowledge_type_saved_prompt", "knowledge_type_prompt_file",
    ]
    locale_keys = re.findall(r"^  (?:'([a-zA-Z-]+)'|([a-zA-Z-]+)): \{$", src, re.MULTILINE)
    locales = [a or b for a, b in locale_keys]
    assert locales == [
        "en", "it", "ja", "ru", "es", "de", "zh", "zh-Hant", "pt", "ko",
        "fr", "cs", "tr", "pl", "vi",
    ], locales

    starts = [m.start() for m in re.finditer(r"^  (?:'[a-zA-Z-]+'|[a-zA-Z-]+): \{$", src, re.MULTILINE)]
    starts.append(len(src))
    for i, locale in enumerate(locales):
        block = src[starts[i]:starts[i + 1]]
        for key in required_keys:
            count = len(re.findall(rf"^    {re.escape(key)}: ", block, re.MULTILINE))
            assert count == 1, f"{locale} locale: expected exactly one '{key}', found {count}"


def test_backend_module_is_read_only():
    """The knowledge_browser module must expose no write/delete functions."""
    module = read("api/knowledge_browser.py")
    assert "def list_items(" in module
    assert "def read_item(" in module
    assert "def search_items(" in module
    assert "def create_item(" not in module
    assert "def delete_item(" not in module
    assert "def write_item(" not in module
