"""The Office floor's first reveal: stars first, then the floors.

The stage is black space from the first frame. When the scene is ready the
canvas fades in with only the stars lit; the platforms and the conductor
(which outlet switches never fade) stay the backdrop colour for a beat and
then rise out of the dark, and the floating cards wait for the same beat.
"""
import pytest

from tests._pytest_port import BASE


def _open(pw):
    browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage",
                                      "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    page = browser.new_page(viewport={"width": 1200, "height": 800})
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    return browser, page


def test_the_conductor_and_floors_stay_dark_until_the_stars_have_shown():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw)
        try:
            out = page.evaluate("""async () => {
              const src = [...document.scripts].map(s => s.src).find(s => /office\\/index\\.js/.test(s)) || '';
              const m = await import('/static/office/scene.js' + (src.includes('?') ? src.slice(src.indexOf('?')) : ''));
              const canvas = document.createElement('canvas');
              canvas.style.cssText = 'position:fixed;left:0;top:0;width:400px;height:300px';
              document.body.appendChild(canvas);
              const s = m.createOfficeScene(canvas, {});
              // The brightest lit, opaque surface of the scene's contents.
              const brightest = () => { let mx = 0; s.scene.traverse(o => {
                if (!o.isMesh || !o.material || Array.isArray(o.material) || !o.material.emissive || o.material.transparent) return;
                mx = Math.max(mx, o.material.color.r, o.material.color.g, o.material.color.b); }); return mx; };
              const before = brightest();
              s.playIntro(2000, 300);
              const held = brightest();
              s.start();
              await new Promise(r => setTimeout(r, 200));
              const stillHeld = brightest();
              await new Promise(r => setTimeout(r, 3000));
              const after = brightest();
              s.stop();
              canvas.remove();
              return {before, held, stillHeld, after};
            }""")
            assert out["before"] > 0.2, out
            assert out["held"] == 0 and out["stillHeld"] == 0, out
            assert out["after"] == pytest.approx(out["before"]), out
        finally:
            browser.close()


def test_the_stage_is_black_and_the_cards_wait_for_the_floors():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw)
        try:
            page.evaluate("() => { document.documentElement.classList.add('dark'); switchPanel('office'); }")
            page.wait_for_function("() => document.querySelector('#mainOffice .office-stage')", timeout=15000)
            assert page.evaluate("() => getComputedStyle(document.querySelector('#mainOffice .office-stage')).backgroundColor") == "rgb(1, 1, 4)"
            page.wait_for_function("() => document.querySelector('.office-stage.is-intro')", polling=20, timeout=30000)
            cards = page.evaluate("""() => { const d = document.querySelector('.office-stage.is-intro .office-dept-cards');
              return [getComputedStyle(d).opacity, d.getAnimations().map(a => a.animationName)]; }""")
            assert cards == ["0", ["office-intro-in"]], cards
        finally:
            page.evaluate("async () => { await switchPanel('chat'); }")
            browser.close()
