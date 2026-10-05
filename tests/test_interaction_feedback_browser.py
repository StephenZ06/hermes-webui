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


def test_removed_rows_collapse_and_new_rows_glow_in():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw)
        try:
            state = page.evaluate("""async () => {
              const box = document.createElement('div');
              box.innerHTML = '<div id="gone" style="height:40px;margin:6px 0;padding:4px">row</div><div id="new">new</div>';
              document.body.appendChild(box);
              const gone = document.getElementById('gone');
              await animateRemoval(gone);
              const after = getComputedStyle(gone);
              const fresh = markArrival(document.getElementById('new'));
              return {height: gone.getBoundingClientRect().height, opacity: after.opacity,
                      arrive: getComputedStyle(fresh).animationName};
            }""")
        finally:
            browser.close()
    assert state["height"] == 0 and state["opacity"] == "0", state
    assert state["arrive"] == "item-arrive"


def test_deleting_a_job_animates_its_own_row_away():
    import json
    import urllib.request
    import uuid

    sync_api = pytest.importorskip("playwright.sync_api")
    name = f"Fade me {uuid.uuid4().hex[:6]}"
    req = urllib.request.Request(BASE + "/api/crons/create",
                                 data=json.dumps({"name": name, "schedule": "0 9 * * *", "prompt": "hi"}).encode(),
                                 headers={"Content-Type": "application/json", "Origin": BASE})
    job = json.loads(urllib.request.urlopen(req, timeout=20).read())
    job_id = (job.get("job") or job)["id"]
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw)
        try:
            page.evaluate("async () => { await switchPanel('tasks'); }")
            page.wait_for_function("(n) => document.querySelector('#cronList').innerText.includes(n)", arg=name, timeout=20000)
            page.evaluate("""() => { const real = window.animateRemoval; window.__removed = [];
              window.animateRemoval = (el, o) => { window.__removed.push(el && el.querySelector('.cron-name') && el.querySelector('.cron-name').textContent); return real(el, o); };
              animateRemoval = window.animateRemoval; }""")
            page.click("#cronDeleteModeBtn")
            page.click(f"#cronList .dm-item:has-text('{name}') .dm-x", force=True)
            page.wait_for_selector("#appDialogConfirm", state="visible", timeout=10000)
            page.click("#appDialogConfirm")
            page.wait_for_function("(n) => !document.querySelector('#cronList').innerText.includes(n)", arg=name, timeout=20000)
            removed = page.evaluate("() => window.__removed")
        finally:
            browser.close()
            try:  # already gone when the test passed
                urllib.request.urlopen(urllib.request.Request(BASE + "/api/crons/delete", data=json.dumps({"job_id": job_id}).encode(),
                                                              headers={"Content-Type": "application/json", "Origin": BASE}), timeout=20)
            except Exception:
                pass
    assert removed == [name], removed


def test_dashboard_numbers_roll_only_when_they_change():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw)
        try:
            seen = page.evaluate("""() => new Promise(resolve => {
              const host = document.createElement('div');
              host.innerHTML = '<strong data-count-key="t-roll">12</strong>';
              document.body.appendChild(host);
              const el = host.firstChild;
              const values = new Set();
              animateCounts(host);
              const sample = () => { values.add(el.textContent); };
              const timer = setInterval(sample, 16);
              setTimeout(() => {
                clearInterval(timer);
                const firstPass = [...values];
                // Same value again (a live re-render): no animation.
                host.innerHTML = '<strong data-count-key="t-roll">12</strong>';
                animateCounts(host);
                resolve({firstPass, final: el.textContent, rerender: host.firstChild.textContent});
              }, 1200);
            })""")
        finally:
            browser.close()
    assert seen["final"] == "12"
    assert len(seen["firstPass"]) > 3 and "0" in seen["firstPass"], "it counts up from 0 on first view"
    assert seen["rerender"] == "12", "an unchanged number does not restart"


def test_work_hub_drag_opens_a_slot_and_the_card_settles():
    import json
    import urllib.request
    import uuid

    sync_api = pytest.importorskip("playwright.sync_api")

    def call(path, body=None):
        req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "Origin": BASE})
        return json.loads(urllib.request.urlopen(req, timeout=20).read() or b"{}")

    title = f"Drag me {uuid.uuid4().hex[:6]}"
    rev = call("/api/work_hub/bootstrap")["revision"]
    item = call("/api/work_hub/items/create", {"item": {"title": title, "status": "todo"}, "expected_revision": rev})["item"]
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw)
        try:
            page.evaluate("async () => { await switchPanel('notes'); }")
            page.wait_for_selector(f".work-hub-card[data-item-id='{item['id']}']", timeout=20000)
            state = page.evaluate("""async (id) => {
              const card = document.querySelector(`.work-hub-card[data-item-id="${id}"]`);
              const from = card.closest('.work-hub-column');
              const to = [...document.querySelectorAll('.work-hub-column')].find(c => c !== from);
              const dt = new DataTransfer();
              card.dispatchEvent(new DragEvent('dragstart', {bubbles: true, dataTransfer: dt}));
              from.dispatchEvent(new DragEvent('dragover', {bubbles: true, cancelable: true, dataTransfer: dt}));
              const slotInOwn = !!from.querySelector('.drag-slot');
              to.dispatchEvent(new DragEvent('dragover', {bubbles: true, cancelable: true, dataTransfer: dt}));
              const slotInTarget = !!to.querySelector('.drag-slot');
              to.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt}));
              card.dispatchEvent(new DragEvent('dragend', {bubbles: true, dataTransfer: dt}));
              const target = to.dataset.status;
              await new Promise(r => setTimeout(r, 1500));
              const moved = document.querySelector(`.work-hub-card[data-item-id="${id}"]`);
              return {slotInOwn, slotInTarget, slotAfter: !!document.querySelector('.drag-slot'),
                      target, landed: moved && (moved.classList.contains('card-landed') || getComputedStyle(moved).animationName === 'card-landed'),
                      column: moved && moved.closest('.work-hub-column').dataset.status};
            }""", item["id"])
        finally:
            browser.close()
            call("/api/work_hub/items/delete", {"item_id": item["id"], "expected_revision": call("/api/work_hub/bootstrap")["revision"]})
    assert not state["slotInOwn"], "no slot in the card's own column"
    assert state["slotInTarget"], "a slot opens in the column under the pointer"
    assert not state["slotAfter"], "the slot goes away on drop"
    assert state["column"] == state["target"]


def test_insights_bars_grow_on_open_but_not_on_auto_refresh():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw)
        try:
            page.evaluate("async () => { await switchPanel('insights'); }")
            page.wait_for_selector("#insightsContent .insights-card", timeout=20000)
            opened = page.evaluate("() => document.getElementById('insightsContent').classList.contains('insights-grow')")
            page.wait_for_function("() => !document.getElementById('insightsContent').classList.contains('insights-grow')", timeout=5000)
            page.evaluate("async () => { await loadInsights(false); }")
            refreshed = page.evaluate("() => document.getElementById('insightsContent').classList.contains('insights-grow')")
        finally:
            browser.close()
    assert opened, "opening Insights grows the charts in"
    assert not refreshed, "the 15s auto-refresh does not replay it"
