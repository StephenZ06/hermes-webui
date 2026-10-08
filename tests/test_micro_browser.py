"""Shared micro-interactions (static/micro.js): the sliding tab pill, button
busy/done states, the error shake, themed tooltips and stacked toasts."""

import pytest

from tests._pytest_port import BASE


def _page(pw):
    browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true && window.Micro", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    return browser, page


def test_pill_follows_the_active_tab_and_buttons_show_busy_then_done():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _page(pw)
        try:
            out = page.evaluate("""async () => {
              const box = document.createElement('div');
              box.innerHTML = '<div class="seg" data-mi-tabs><button class="seg-btn active">One</button><button class="seg-btn">Two two</button></div><button id="b">Save</button><input id="f">';
              document.body.appendChild(box);
              window.Micro.scan(box);
              const seg = box.querySelector('.seg'), pill = seg.querySelector('.mi-pill'), [one, two] = seg.querySelectorAll('.seg-btn');
              const at = () => [Math.round(pill.getBoundingClientRect().left) === Math.round(document.querySelector('.seg-btn.active').getBoundingClientRect().left),
                                Math.round(pill.getBoundingClientRect().width) === Math.round(document.querySelector('.seg-btn.active').getBoundingClientRect().width)];
              const first = at();
              one.classList.remove('active'); two.classList.add('active');
              await new Promise((r) => setTimeout(r, 500));
              const moved = at();
              const b = box.querySelector('#b');
              window.Micro.busy(b, 'Saving…');
              const busy = [b.textContent, b.disabled, !!b.querySelector('.mi-spin')];
              const finished = window.Micro.done(b, 'Saved', 200);
              const done = [b.textContent, !!b.querySelector('.mi-tick')];
              await finished;
              const back = [b.textContent, b.disabled];
              const f = box.querySelector('#f');
              window.Micro.invalid(f);
              const invalid = [f.getAttribute('aria-invalid'), f.classList.contains('mi-shake')];
              f.dispatchEvent(new Event('input'));
              const cleared = f.hasAttribute('aria-invalid');
              box.remove();
              return {first, moved, busy, done, back, invalid, cleared};
            }""")
        finally:
            browser.close()
    assert out["first"] == [True, True] and out["moved"] == [True, True]
    assert out["busy"] == ["Saving…", True, True] and out["done"] == ["Saved", True] and out["back"] == ["Save", False]
    assert out["invalid"] == ["true", True] and out["cleared"] is False


def test_tooltips_replace_the_native_one_and_toasts_stack():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _page(pw)
        try:
            page.evaluate("""() => { const b = document.createElement('button'); b.id = 'tipme'; b.title = 'Helpful hint'; b.textContent = 'x';
              Object.assign(b.style, {position: 'fixed', left: '300px', top: '300px', zIndex: 99999}); document.body.appendChild(b); }""")
            page.hover("#tipme")
            page.wait_for_selector(".mi-tip.is-open", timeout=3000)
            shown = page.evaluate("() => [document.querySelector('.mi-tip').textContent, document.querySelector('#tipme').hasAttribute('title')]")
            page.mouse.move(5, 600)
            page.wait_for_function("() => !document.querySelector('.mi-tip.is-open')", timeout=2000)
            restored = page.evaluate("() => document.querySelector('#tipme').getAttribute('title')")
            page.evaluate("() => { showToast('First'); }")
            page.wait_for_timeout(250)
            page.evaluate("() => { showToast('Second'); }")
            page.wait_for_timeout(200)
            ghosts = page.evaluate("() => [...document.querySelectorAll('.mi-toast-ghost')].map((g) => g.textContent.includes('First'))")
        finally:
            browser.close()
    assert shown == ["Helpful hint", False], "the native tooltip is parked while the themed one shows"
    assert restored == "Helpful hint"
    assert ghosts == [True]
