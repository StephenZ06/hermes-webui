"""Re-applying the locale must not rewrite an unchanged page.

applyLocaleToDOM() set every translated text, title, placeholder and
aria-label on each call, even when nothing changed, and _updateYoloPill()
called it for the whole document on every chat load. Each pass produced
hundreds of DOM mutations, which browser extensions watching the page
(autofill/password managers) re-scan -- one of them crashed on the flood.
"""
import pytest

from tests._pytest_port import BASE

COUNT = """(fn) => new Promise(resolve => {
  const seen = [];
  // Only what the locale code can touch: translated elements (and their text),
  // the app title bar and the workspace-panel buttons. Live views elsewhere
  // (Work Hub refreshes, shimmer animations) change on their own timers.
  const OWNED = '[data-i18n],[data-i18n-title],[data-i18n-placeholder],[data-i18n-aria-label],#appTitlebarTitle,#appTitlebarSub,#yoloPill,.rightpanel button,#btnWorkspacePanelEdgeToggle';
  const mo = new MutationObserver(records => records.forEach(r => {
    const el = r.target.nodeType === 1 ? r.target : r.target.parentElement;
    if (!el || !el.closest(OWNED) || r.attributeName === 'style') return;  // shimmer animations restyle themselves
    seen.push(`${r.type}:${r.attributeName || ''}:${r.target.id || r.target.className || r.target.nodeName}`);
  }));
  mo.observe(document.body, {subtree: true, childList: true, attributes: true, characterData: true});
  window[fn]();
  setTimeout(() => { mo.disconnect(); resolve(seen); }, 50);
})"""


def test_reapplying_the_locale_and_the_yolo_pill_cause_no_mutations():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => applyLocaleToDOM()")  # settle once
            relocalise = page.evaluate(COUNT, "applyLocaleToDOM")
            yolo = page.evaluate(COUNT, "_updateYoloPill")
            translated = page.evaluate("() => document.querySelectorAll('[data-i18n],[data-i18n-title],[data-i18n-placeholder],[data-i18n-aria-label]').length")
        finally:
            browser.close()
    assert translated > 50, "precondition: the page has many translated elements"
    assert relocalise == [], f"an unchanged locale re-applied with mutations: {relocalise}"
    assert yolo == [], f"updating the YOLO pill caused mutations: {yolo}"
