"""Highlight motion and tint on the Notes and Office pages.

- Notes: the tag chips take the side panel's highlight glide (moving sideways
  as well as down), a note card's outline slides from the card picked before,
  and a workspace note's highlight moves at the click, not once it has loaded.
- Office: Dashboard / Integrations take the glide, carrying the card's
  outline, and the picked card is tinted, not grey.
- Zeus 2.0: every hover uses the active row's tint (--accent-bg), so History
  rows and project folders match "Inbox" on the Work Hub.
- Office: coming back to the floor plays the staged wake (stars, then the
  floor, then the cards), also when the floor had to be built again, and the
  light-up and wake never push the neon bands past their own glow.
"""
import json
import time
import uuid

import pytest

from tests._pytest_port import BASE


def _boot(pw, skin=None):
    browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(BASE + "/", wait_until="domcontentloaded")
    if skin:
        page.evaluate("(skin) => { localStorage.setItem('hermes-theme', 'dark'); localStorage.setItem('hermes-skin', skin); }", skin)
        page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    return browser, page


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _boot(pw)
        try:
            yield page
        finally:
            browser.close()


@pytest.fixture
def zeus_page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _boot(pw, "zeus-2")
        try:
            yield page
        finally:
            browser.close()


# Clicks `selector` and records where every glide copy is, frame by frame.
_TRACK = """async (selector) => {
    const seen = [];
    let running = true;
    const tick = () => {
        const g = document.querySelector('.sidebar-highlight-glide');
        if (g) { const r = g.getBoundingClientRect(); seen.push({left: r.left, top: r.top, border: getComputedStyle(g).borderTopWidth}); }
        if (running) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    document.querySelector(selector).click();
    await new Promise(r => setTimeout(r, 600));
    running = false;
    return seen;
}"""

_CREATE_NOTES = """async (specs) => { const ids = [];
    for (const spec of specs) ids.push((await api('/api/notebook/notes/create', {method: 'POST', body: JSON.stringify(spec)})).note.id);
    return ids; }"""
_PURGE_NOTES = """async (ids) => { for (const id of ids) {
    await api('/api/notebook/notes/' + id + '/trash', {method: 'POST'});
    await api('/api/notebook/notes/' + id + '/purge', {method: 'POST'}); } }"""


def test_notes_tag_highlight_glides_sideways_to_the_next_tag(page):
    tag = uuid.uuid4().hex[:5]
    first, second = f"aa{tag}", f"zz{tag}longer"
    ids = page.evaluate(_CREATE_NOTES, [{"title": "Tag one", "tags": [first]}, {"title": "Tag two", "tags": [second]}])
    try:
        page.evaluate("async () => { await switchPanel('notebook'); }")
        page.wait_for_selector(f".nb-tag[data-nb-tag='{second}']", timeout=15000)
        page.click(f".nb-tag[data-nb-tag='{first}']")
        page.wait_for_timeout(500)
        box = "(sel) => { const r = document.querySelector(sel).getBoundingClientRect(); return {left: r.left, top: r.top}; }"
        start = page.evaluate(box, f".nb-tag[data-nb-tag='{first}']")
        end = page.evaluate(box, f".nb-tag[data-nb-tag='{second}']")
        seen = page.evaluate(_TRACK, f".nb-tag[data-nb-tag='{second}']")
        assert seen, "no glide between tags"
        # It travels from one chip to the other (across, or down when the
        # chips wrapped onto different lines): somewhere strictly between.
        def between(a, b, values):
            return a != b and any(min(a, b) + 4 < v < max(a, b) - 4 for v in values)
        assert between(start["left"], end["left"], [s["left"] for s in seen]) or between(start["top"], end["top"], [s["top"] for s in seen]), (start, end, seen)
        assert page.evaluate(f"() => document.querySelector(\".nb-tag[data-nb-tag='{second}']\").classList.contains('active')")
    finally:
        page.evaluate(_PURGE_NOTES, ids)


def test_notes_card_outline_slides_down_to_the_next_card(page):
    ids = page.evaluate(_CREATE_NOTES, [{"title": f"Slide {i} {uuid.uuid4().hex[:4]}"} for i in (1, 2, 3)])
    try:
        page.evaluate("async () => { await switchPanel('notebook'); }")
        page.click("[data-nb-scope=general]")
        page.wait_for_selector(f".nb-item[data-nb-open='{ids[2]}']", timeout=15000)
        cards = page.evaluate("(ids) => ids.map(id => document.querySelector(`.nb-item[data-nb-open='${id}']`).getBoundingClientRect().top)", ids)
        # The list is newest first; pick the top card, then the one below it.
        order = sorted(range(3), key=lambda i: cards[i])
        first, below = ids[order[0]], ids[order[1]]
        page.click(f".nb-item[data-nb-open='{first}']")
        page.wait_for_function(f"() => document.querySelector(\".nb-item.active[data-nb-open='{first}']\")", timeout=10000)
        page.wait_for_timeout(600)
        page.mouse.move(5, 5)
        box = "(sel) => document.querySelector(sel).getBoundingClientRect().top"
        start = page.evaluate(box, f".nb-item[data-nb-open='{first}']")
        end = page.evaluate(box, f".nb-item[data-nb-open='{below}']")
        seen = page.evaluate(_TRACK, f".nb-item[data-nb-open='{below}']")
        assert seen and float(seen[0]["border"].rstrip("px")) > 0, seen
        # The outline travels down through the gap between the two cards.
        assert any(start + 4 < s["top"] < end - 4 for s in seen), (start, end, seen)
        page.wait_for_timeout(400)
        fills = page.evaluate(f"""() => {{
            const probe = document.createElement('div'); probe.style.background = 'var(--accent-bg)'; document.body.appendChild(probe);
            const tint = getComputedStyle(probe).backgroundColor; probe.remove();
            return [getComputedStyle(document.querySelector(".nb-item.active[data-nb-open='{below}']")).backgroundColor, tint];
        }}""")
        assert fills[0] == fills[1] and fills[0] != "rgba(0, 0, 0, 0)", fills
    finally:
        page.evaluate(_PURGE_NOTES, ids)


def test_notes_workspace_note_highlight_moves_at_the_click_not_after_loading(page):
    pid = page.evaluate("""async () => (await api('/api/projects/create', {method: 'POST',
        body: JSON.stringify({name: 'Tree glide', work_hub_managed: true})})).project.project_id""")
    ids = page.evaluate(_CREATE_NOTES, [{"title": f"Tree {i} {uuid.uuid4().hex[:4]}", "project_id": pid} for i in (1, 2, 3)])
    try:
        page.reload(wait_until="domcontentloaded")
        page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
        page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
        page.evaluate("async () => { await switchPanel('notebook'); }")
        tile = f".nb-place-btn[data-nb-id='{pid}']"
        page.wait_for_selector(tile, timeout=15000)
        if page.get_attribute(tile, "aria-expanded") != "true":
            page.click(tile)
        page.wait_for_timeout(500)
        rows = page.evaluate(f"() => [...document.querySelector(\"{tile}\").nextElementSibling.querySelectorAll('.nb-tree-note > button')].map(b => b.dataset.nbOpen)")
        assert len(rows) >= 3, rows
        row = lambda note: f".nb-tree-note > button[data-nb-open='{note}']"
        page.click(row(rows[0]))
        page.wait_for_function(f"() => document.querySelector(\".nb-tree-note.active > button[data-nb-open='{rows[0]}']\")", timeout=10000)
        page.wait_for_timeout(600)
        page.mouse.move(5, 5)
        # The next note takes a while to load; the highlight must not wait for it.
        slow = f"**/api/notebook/notes/{rows[2]}*"
        page.route(slow, lambda route: (time.sleep(0.9), route.continue_()))
        start = page.evaluate(f"() => document.querySelector(\"{row(rows[0])}\").getBoundingClientRect().top")
        end = page.evaluate(f"() => document.querySelector(\"{row(rows[2])}\").getBoundingClientRect().top")
        seen = page.evaluate(_TRACK, row(rows[2]))
        assert any(start + 4 < s["top"] < end - 4 for s in seen), (start, end, seen)
    finally:
        page.evaluate("() => new Promise(r => setTimeout(r, 1200))")
        page.evaluate(_PURGE_NOTES, ids)
        page.evaluate("(id) => api('/api/projects/delete', {method: 'POST', body: JSON.stringify({project_id: id})})", pid)


def test_office_page_cards_glide_with_their_outline_and_take_the_tint(page):
    try:
        page.evaluate("async () => { await switchPanel('office'); }")
        page.wait_for_selector("[data-office-subview=integrations]", timeout=20000)
        page.click("[data-office-subview=dashboard]")
        page.wait_for_timeout(500)
        page.mouse.move(900, 880)
        seen = page.evaluate(_TRACK, "[data-office-subview=integrations]")
        assert seen and float(seen[0]["border"].rstrip("px")) > 0, seen
        lefts = [round(s["left"]) for s in seen]
        assert max(lefts) - min(lefts) > 40, lefts
        page.wait_for_timeout(300)
        fills = page.evaluate("""() => {
            const probe = document.createElement('div'); probe.style.background = 'var(--accent-bg)'; document.body.appendChild(probe);
            const tint = getComputedStyle(probe).backgroundColor; probe.remove();
            return [getComputedStyle(document.querySelector('.office-page-nav-btn.is-active')).backgroundColor, tint,
                document.querySelector('.office-page-nav-btn.is-active').dataset.officeSubview];
        }""")
        assert fills[0] == fills[1] and fills[2] == "integrations", fills
    finally:
        page.evaluate("async () => { await switchPanel('chat'); }")


def test_zeus2_hovers_use_the_active_tint_including_office_history(zeus_page):
    page = zeus_page
    parents = [{"parent_session_id": "hist1", "title": "History run", "children": []}]
    page.route("**/api/agent-canvas/sessions*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps({"parents": parents})))
    try:
        page.evaluate("async () => { await switchPanel('office'); }")
        page.wait_for_selector(".office-session-row[data-parent-id='hist1']", timeout=20000)
        page.mouse.move(5, 5)
        cdp = page.context.new_cdp_session(page)
        cdp.send("DOM.enable")
        cdp.send("CSS.enable")
        root = cdp.send("DOM.getDocument", {"depth": 0})["root"]["nodeId"]
        node = cdp.send("DOM.querySelector", {"nodeId": root, "selector": ".office-session-row[data-parent-id='hist1']"})["nodeId"]
        cdp.send("CSS.forcePseudoState", {"nodeId": node, "forcedPseudoClasses": ["hover"]})
        page.wait_for_timeout(800)
        out = page.evaluate("""() => {
            const probe = document.createElement('div'); document.body.appendChild(probe);
            probe.style.background = 'var(--accent-bg)'; const tint = getComputedStyle(probe).backgroundColor;
            probe.style.background = 'var(--hover-bg)'; const hover = getComputedStyle(probe).backgroundColor; probe.remove();
            return {tint, hover, row: getComputedStyle(document.querySelector(".office-session-row[data-parent-id='hist1']")).backgroundColor};
        }""")
        assert out["hover"] == out["tint"] == out["row"], out
    finally:
        page.evaluate("async () => { await switchPanel('chat'); }")


def test_office_comes_back_in_stages(page):
    page.evaluate("async () => { await switchPanel('office'); }")
    try:
        page.wait_for_function("() => document.querySelector('.office-canvas') && !document.querySelector('.office-canvas.is-mounting')", timeout=30000)
    except Exception:
        pytest.skip("the Office scene did not mount in this browser")
    page.wait_for_timeout(3000)
    page.evaluate("async () => { await switchPanel('chat'); }")
    page.wait_for_timeout(500)
    page.evaluate("async () => { await switchPanel('office'); }")
    page.wait_for_function("() => !document.querySelector('.office-canvas.is-waking')", timeout=10000)
    out = page.evaluate("""() => {
        const stage = document.querySelector('.office-stage'), canvas = document.querySelector('.office-canvas');
        return {intro: stage.classList.contains('is-intro'), delay: parseFloat(stage.style.getPropertyValue('--office-intro-delay')),
            stars: parseFloat(getComputedStyle(canvas).transitionDuration) * 1000};
    }""")
    # The stars come in quickly, and the cards wait for the floor.
    assert out["intro"] and out["stars"] < 300 and 300 <= out["delay"] <= 700, out
    page.evaluate("async () => { await switchPanel('chat'); }")


def test_office_rebuilt_floor_comes_back_the_quick_way(page):
    page.evaluate("async () => { await switchPanel('office'); }")
    ready = "() => document.querySelector('.office-canvas') && !document.querySelector('.office-canvas.is-mounting')"
    try:
        page.wait_for_function(ready, timeout=30000)
    except Exception:
        pytest.skip("the Office scene did not mount in this browser")
    page.wait_for_timeout(2500)
    # Away long enough that the scene was released: the floor is built again.
    page.evaluate("async () => { await switchPanel('chat'); window.HermesOffice.dispose(); }")
    page.evaluate("async () => { await switchPanel('office'); }")
    page.wait_for_function(ready, timeout=30000)
    delay = page.evaluate("() => parseFloat(document.querySelector('.office-stage').style.getPropertyValue('--office-intro-delay'))")
    # The wake's cards follow within a beat; the first power-up waits ~1.3s.
    assert 300 <= delay <= 700, delay
    page.evaluate("async () => { await switchPanel('chat'); }")


_GLOW = """async () => {
  const v = document.querySelector('script[src*="office/index.js"]').getAttribute('src').split('?')[1];
  const {createOfficeScene} = await import('/static/office/scene.js?' + v);
  const c = document.createElement('canvas');
  c.style.cssText = 'position:fixed;left:0;top:0;width:600px;height:400px';
  document.body.appendChild(c);
  const sc = createOfficeScene(c, {}); sc.resize(); sc.start();
  await new Promise(r => setTimeout(r, 800));
  let band = null;
  sc.scene.traverse(o => { if (o.userData && o.userData.hubBand) band = o.userData.hubBand; });
  const natural = band.userData.idleEmissiveIntensity;
  const glow = () => { const m = band.material; return Math.max(m.emissive.r, m.emissive.g, m.emissive.b) * m.emissiveIntensity; };
  const peak = async (ms) => { let p = 0; const t0 = performance.now();
    while (performance.now() - t0 < ms) { await new Promise(r => requestAnimationFrame(r)); p = Math.max(p, glow()); } return p; };
  sc.playIntro(0); const intro = await peak(1800);
  await new Promise(r => setTimeout(r, 300));
  sc.playWake(100, 320); const wake = await peak(900);
  try { sc.stop(); } catch (_) {}
  c.remove();
  return {natural, intro, wake};
}"""


def test_office_light_up_and_wake_keep_the_bands_at_their_own_glow(page):
    try:
        out = page.evaluate(_GLOW)
    except Exception as exc:  # no WebGL in this browser
        pytest.skip(f"the Office scene could not start: {exc}")
    # The hub band's colour is at most 1 per channel, so its glow never
    # passes its idle intensity; the wake used to double it.
    limit = out["natural"] * 1.02
    assert out["intro"] <= limit and out["wake"] <= limit, out
