"""Picking a language the page did not load fetches it, then shows it.

The page's i18n.js carries English, its own language and stubs for the rest
(api/i18n_bundle.py). setLocale() of a stubbed language loads that language
and resolves once its strings are in place.
"""

import re
from pathlib import Path

import pytest

from tests._pytest_port import BASE

SOURCE = (Path(__file__).resolve().parent.parent / "static" / "i18n.js").read_text(encoding="utf-8")


def _source_value(code, key):
    start = SOURCE.index(f"\n  {code}: {{\n") if not "-" in code else SOURCE.index(f"\n  '{code}': {{\n")
    match = re.search(rf"^    {key}: '((?:[^'\\]|\\.)*)',", SOURCE[start:], re.M)
    return match.group(1)


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            tab = browser.new_page(viewport={"width": 1280, "height": 800})
            tab.i18n_requests = []
            tab.on("request", lambda r: tab.i18n_requests.append(r.url) if "/static/i18n.js" in r.url else None)
            tab.goto(BASE + "/", wait_until="load")
            tab.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            yield tab
            tab.evaluate("() => setLocale('en')")
        finally:
            browser.close()


def test_the_page_starts_with_only_its_language_loaded(page):
    assert len(page.i18n_requests) == 1 and "lang=" in page.i18n_requests[0], page.i18n_requests
    state = page.evaluate("() => Object.entries(LOCALES).map(([code, b]) => [code, !!b._lazy, typeof b._label])")
    lazy = [code for code, is_lazy, _ in state if is_lazy]
    assert "en" not in lazy and len(lazy) >= len(state) - 2
    assert all(label == "string" for _, _, label in state), state


def test_switching_to_a_stubbed_language_loads_and_shows_it(page):
    expected = _source_value("ja", "outline_empty")
    result = page.evaluate("""async () => {
        const before = LOCALES.ja._lazy === true;
        const done = await setLocale('ja');
        return {before, done, lazy: !!LOCALES.ja._lazy, text: t('outline_empty'), lang: document.documentElement.lang};
    }""")
    assert result["before"] and result["done"] == "ja" and not result["lazy"], result
    assert result["text"] == expected
    assert result["lang"].startswith("ja")
    assert any("locale=ja" in url for url in page.i18n_requests), page.i18n_requests
    # Switching back and forth does not fetch it again.
    page.evaluate("async () => { await setLocale('en'); await setLocale('ja'); }")
    assert sum("locale=ja" in url for url in page.i18n_requests) == 1


def test_static_text_is_restamped_when_the_language_arrives(page):
    key = page.evaluate("""() => {
        const el = [...document.querySelectorAll('[data-i18n]')].find(e => {
            const k = e.getAttribute('data-i18n'); return LOCALES.en[k] && typeof LOCALES.en[k] === 'string';
        });
        return el && el.getAttribute('data-i18n');
    }""")
    assert key
    page.evaluate("async () => { await setLocale('fr'); }")
    text = page.evaluate("(key) => document.querySelector(`[data-i18n=\"${key}\"]`).textContent", key)
    assert text == page.evaluate("(key) => t(key)", key)
    assert page.evaluate("(key) => LOCALES.fr[key] === undefined || t(key) === LOCALES.fr[key]", key)
