"""Analytics/cost dashboard UI wiring guards.

Structural checks (not a browser test) pinning that the nav tab, panel
container, main content pane, and JS functions introduced for the
Analytics dashboard stay wired together. See
docs/HERMES_STUDIO_PARITY_PLAN.md, "Analytics/cost dashboard".
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def test_nav_tab_and_panel_containers_present():
    html = read("static/index.html")
    assert 'data-panel="analytics"' in html
    assert "onclick=\"switchPanel('analytics'" in html
    assert 'id="panelAnalytics"' in html
    assert 'id="mainAnalytics"' in html
    assert 'id="analyticsContent"' in html
    assert 'id="analyticsPeriod"' in html
    assert 'id="analyticsGranularity"' in html


def test_main_view_css_wiring_present():
    css = read("static/style.css")
    assert "main.main > #mainAnalytics" in css
    assert "main.main.showing-analytics > #mainAnalytics{display:flex;}" in css
    assert ":not(.showing-analytics)" in css


def test_panels_js_core_wiring_present():
    js = read("static/panels.js")
    for fn in ("loadAnalytics", "_renderAnalytics"):
        assert f"function {fn}(" in js, f"{fn} not defined in panels.js"
    assert "'analytics'" in js.split("MAIN_VIEW_PANELS")[1][:200]
    assert re.search(r"api\(`/api/analytics\?days=\$\{period\}&granularity=\$\{granularity\}`\)", js)


def test_backend_route_and_handler_present():
    routes = read("api/routes.py")
    assert '"/api/analytics"' in routes
    assert "def _handle_analytics(" in routes
    assert "billing_provider" in routes
    assert "model_provider" in routes


def test_reuses_existing_insights_card_classes_not_a_full_duplicate():
    """Per the Open questions decision, Analytics reuses the existing
    theme-var-only insights-card/table/stat classes rather than re-styling
    a parallel card system from scratch."""
    js = read("static/panels.js")
    analytics_fn_src = js[js.index("function _renderAnalytics("):js.index("async function clearConversation(")]
    assert "insights-card" in analytics_fn_src
    assert "insights-stat" in analytics_fn_src
    assert "insights-table" in analytics_fn_src


def test_i18n_keys_present_in_all_15_locales():
    src = read("static/i18n.js")
    required_keys = [
        "tab_analytics", "analytics_title", "analytics_total_sessions", "analytics_total_tokens",
        "analytics_total_cost", "analytics_providers", "analytics_provider_col_provider",
        "analytics_provider_col_sessions", "analytics_provider_col_tokens", "analytics_provider_col_cost",
        "analytics_provider_col_share", "analytics_trend_title", "analytics_top_sessions_title",
        "analytics_top_sessions_empty", "analytics_no_data", "analytics_granularity_day",
        "analytics_granularity_week", "analytics_granularity_month", "analytics_unknown_provider",
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
