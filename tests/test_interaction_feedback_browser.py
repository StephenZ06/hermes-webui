"""Interaction feedback: toasts, copy confirmation, button press, page switch.

- Toasts slide in from the right, show a countdown bar that pauses on hover,
  and can be swiped right to dismiss.
- Copy buttons confirm with a check that pops in, then restore.
- Buttons dip while pressed.
- The page view being shown fades/rises in on a rail switch.
"""
import pytest

from tests._pytest_port import BASE


def _open(pw):
    browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    return browser, page


def test_toast_counts_down_pauses_on_hover_and_swipes_away():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw)
        try:
            page.evaluate("() => showToast('Saved the thing', 8000)")
            page.wait_for_selector("#toast.show", timeout=5000)
            timing = page.evaluate("""() => { const t = document.getElementById('toast');
              return {timing: t.classList.contains('toast-timing'), duration: t.style.getPropertyValue('--toast-duration'),
                      bar: getComputedStyle(t, '::after').animationName}; }""")
            box = page.locator("#toast").bounding_box()
            page.mouse.move(box["x"] + 20, box["y"] + box["height"] / 2)
            paused = page.evaluate("() => document.getElementById('toast').classList.contains('toast-paused')")
            page.mouse.down()
            page.mouse.move(box["x"] + 160, box["y"] + box["height"] / 2, steps=8)
            page.mouse.up()
            page.wait_for_function("() => !document.getElementById('toast').classList.contains('show')", timeout=5000)
        finally:
            browser.close()
    assert timing["timing"] and timing["duration"] == "8000ms" and timing["bar"] == "toast-countdown"
    assert paused, "hovering pauses the countdown"


def test_copy_feedback_pops_a_check_then_restores():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw)
        try:
            state = page.evaluate("""() => new Promise(resolve => {
              const btn = document.createElement('button'); btn.innerHTML = '<span id="orig">copy</span>';
              document.body.appendChild(btn);
              _showCopiedFeedback(btn, 13);
              const during = {pop: btn.classList.contains('copy-pop'), svg: !!btn.querySelector('svg'),
                              anim: getComputedStyle(btn.querySelector('svg')).animationName};
              _showCopiedFeedback(btn, 13);  // a second click inside the window
              setTimeout(() => resolve({during, restored: btn.innerHTML.includes('id="orig"'),
                                        pop: btn.classList.contains('copy-pop')}), 1700);
            })""")
        finally:
            browser.close()
    assert state["during"]["pop"] and state["during"]["svg"] and state["during"]["anim"] == "copy-pop"
    assert state["restored"] and not state["pop"], "the original icon comes back, even after a double click"


def test_buttons_dip_while_pressed_and_page_views_fade_in():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw)
        try:
            page.evaluate("async () => { await switchPanel('tasks'); }")
            view_anim = page.evaluate("() => getComputedStyle(document.getElementById('mainTasks')).animationName")
            btn = page.locator("#cronRefreshBtn").bounding_box()
            page.mouse.move(btn["x"] + btn["width"] / 2, btn["y"] + btn["height"] / 2)
            page.mouse.down()
            page.wait_for_timeout(150)
            pressed = page.evaluate("() => getComputedStyle(document.getElementById('cronRefreshBtn')).transform")
            page.mouse.up()
        finally:
            browser.close()
    assert view_anim == "page-view-in"
    assert pressed.startswith("matrix(0.96"), pressed
