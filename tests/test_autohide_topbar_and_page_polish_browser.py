"""The auto-hiding top bar, the rail's single fade-in, and the page polish that
shipped with them: centred folder dots, popups on the page background, the
work item's icon footer, Office's toggle buttons and live folder badge, and a
floor that recovers its colours when a fade is interrupted."""
import json
import re

import pytest

from tests._pytest_port import BASE

USAGE = {"available": True, "provider": "openai-codex", "plan": "ChatGPT Pro",
         "windows": [{"key": "session", "label": "5-hour", "used_percent": 20, "reset_at": None},
                     {"key": "weekly", "label": "Weekly", "used_percent": 40, "reset_at": None}]}
READY = "() => typeof S !== 'undefined' && S._bootReady === true"
BAR_TOP = "() => document.querySelector('.app-titlebar').getBoundingClientRect().top"


def _open(browser, **context):
    page = browser.new_context(**{"viewport": {"width": 1899, "height": 990}, **context}).new_page()
    page.route("**/api/account_usage*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(USAGE)))
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function(READY, polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    return page


@pytest.fixture
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        instance = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        yield instance
        instance.close()


@pytest.fixture
def page(browser):
    page = _open(browser)
    page.mouse.move(900, 500)
    page.wait_for_timeout(900)
    return page


def test_top_bar_rests_above_the_window_and_gives_the_page_its_height(page):
    assert page.evaluate(BAR_TOP) < -30
    assert page.evaluate("() => document.querySelector('.layout').getBoundingClientRect().top") == 0


def test_top_bar_slides_down_at_the_top_edge_and_leaves_again(page):
    page.mouse.move(900, 2)
    page.wait_for_timeout(700)
    assert page.evaluate(BAR_TOP) == 0
    page.mouse.move(900, 20)
    page.wait_for_timeout(700)
    assert page.evaluate(BAR_TOP) == 0, "the bar must stay while the pointer is on it"
    page.mouse.move(900, 500)
    page.wait_for_timeout(1000)
    assert page.evaluate(BAR_TOP) < -30


def test_top_bar_opens_for_keyboard_focus(page):
    page.evaluate("() => document.getElementById('btnCommandPalette').focus()")
    page.wait_for_timeout(700)
    assert page.evaluate(BAR_TOP) == 0


def test_the_strip_that_catches_the_pointer_clears_the_page_once_the_bar_is_down(page):
    page.mouse.move(900, 2)
    page.wait_for_timeout(900)
    height = page.evaluate("() => getComputedStyle(document.querySelector('.app-titlebar'), '::after').height")
    assert height == "0px"


def test_touch_screens_keep_the_bar_because_they_cannot_reveal_it(browser):
    page = _open(browser, viewport={"width": 1024, "height": 768}, has_touch=True, is_mobile=True)
    assert page.evaluate(BAR_TOP) == 0
    assert page.evaluate("() => getComputedStyle(document.querySelector('.app-titlebar')).position") != "fixed"


def test_rail_icons_wait_for_the_slowest_mark_then_appear_together(browser):
    page = browser.new_context(viewport={"width": 1400, "height": 800}).new_page()

    held = []
    page.route("**/static/nav-audit-mark.png*", lambda route: held.append(route))
    page.goto(BASE + "/", wait_until="commit")
    page.wait_for_selector(".rail .page-nav-mark", state="attached", timeout=10000)
    pending = page.evaluate("""() => ({
      pending: document.documentElement.classList.contains('nav-marks-pending'),
      opacities: [...document.querySelectorAll('.rail .page-nav-mark')].map(e => getComputedStyle(e).opacity)})""")
    assert pending["pending"] is True
    assert set(pending["opacities"]) == {"0"}
    assert held
    held[0].continue_()
    page.wait_for_function("() => !document.documentElement.classList.contains('nav-marks-pending')", timeout=5000)
    page.wait_for_timeout(600)
    shown = page.evaluate("() => [...document.querySelectorAll('.rail .page-nav-mark')].map(e => getComputedStyle(e).opacity)")
    assert "0" not in shown


def test_marks_are_preloaded_the_way_css_masks_request_them(browser):
    """A mask is a CORS fetch, so a plain Image() warms a different cache entry
    and each mask still loads on its own after the rail has been shown."""
    page = browser.new_context(viewport={"width": 1400, "height": 800}).new_page()
    requests = []
    page.on("request", lambda r: requests.append(r.url) if "nav-audit-mark" in r.url else None)
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => !document.documentElement.classList.contains('nav-marks-pending')", timeout=8000)
    page.wait_for_timeout(300)
    assert len(requests) == 1, "the mask must reuse the preloaded image"


def test_folder_dots_have_equal_space_above_and_below(page):
    """Chat's list has its own offsets, so it is checked alongside the shared row."""
    page.evaluate("async () => { await switchPanel('chat'); }")
    page.wait_for_timeout(300)
    gaps = page.evaluate("""() => { const list = document.getElementById('sessionList');
      const row = document.createElement('button'); row.className = 'project-chip project-folder-row';
      row.innerHTML = '<span class="color-dot"></span><span class="project-folder-name">Folder</span>';
      list.prepend(row);
      const r = row.querySelector('.color-dot').getBoundingClientRect(), w = row.getBoundingClientRect();
      row.remove(); return [r.top - w.top, w.bottom - r.bottom]; }""")
    assert abs(gaps[0] - gaps[1]) < 0.1, gaps


def test_new_chat_menu_and_workspace_arrow_sit_on_the_page_background(page):
    page.evaluate("async () => { await switchPanel('chat'); }")
    page.wait_for_timeout(400)
    page.click("#btnNewChat")
    page.wait_for_selector(".new-chat-menu")
    colours = page.evaluate("""() => {
      const probe = document.createElement('div'); probe.style.background = 'var(--bg)'; document.body.append(probe);
      const bg = getComputedStyle(probe).backgroundColor; probe.remove();
      return [bg, getComputedStyle(document.querySelector('.new-chat-menu')).backgroundColor,
              getComputedStyle(document.getElementById('btnWorkspacePanelEdgeToggle')).backgroundColor]; }""")
    assert colours[1] == colours[0]
    assert colours[2] == colours[0]


def test_usage_card_title_is_regular_and_window_labels_are_capitals(page):
    page.evaluate("async () => { await switchPanel('chat'); }")
    page.wait_for_selector("#chatUsageWidgetWindowToggle button", state="visible", timeout=8000)
    assert page.evaluate("() => getComputedStyle(document.querySelector('.chat-usage-widget-label')).fontWeight") == "400"
    assert page.evaluate("() => [...document.querySelectorAll('#chatUsageWidgetWindowToggle button')].map(b => b.innerText)") == ["5 HOURS", "WEEKLY"]
    overflow = page.evaluate("() => [...document.querySelectorAll('#chatUsageWidgetWindowToggle button')].map(b => b.scrollWidth - b.clientWidth)")
    assert max(overflow) <= 0


def test_new_chat_logo_has_no_glow(page):
    assert page.evaluate("() => getComputedStyle(document.querySelector('.empty-logo'), '::before').content") == "none"


def _open_work_item(page):
    page.evaluate("async () => { await switchPanel('notes'); }")
    page.wait_for_selector("#workHubCreate", timeout=8000)
    page.click("#workHubCreate")
    page.wait_for_timeout(300)
    if page.locator(".work-hub-create-menu button").count():
        page.locator(".work-hub-create-menu button").first.click()
    page.wait_for_selector("#workHubSave", timeout=8000)


def test_work_item_footer_buttons_are_named_icons_without_text_or_native_tooltips(page):
    _open_work_item(page)
    footer = page.evaluate("""() => ['workHubDelete', 'workHubSave'].map(id => {
      const b = document.getElementById(id), m = b.querySelector('.wh-foot-mark'), r = b.getBoundingClientRect(), q = m.getBoundingClientRect();
      return {text: b.textContent.trim(), label: b.getAttribute('aria-label'), title: b.getAttribute('title'),
              mask: getComputedStyle(m).maskImage, above: q.top - r.top, below: r.bottom - q.bottom}; })""")
    assert [f["label"] for f in footer] == ["Delete work item", "Save changes"]
    for item, asset in zip(footer, ("work-hub-delete-mark", "work-hub-save-mark")):
        assert item["text"] == "" and item["title"] is None
        assert asset in item["mask"]
        assert item["above"] == item["below"]


def test_office_tool_buttons_toggle_back_to_the_live_floor(page):
    page.evaluate("async () => { await switchPanel('office'); }")
    button = '.office-page-nav-btn[data-office-subview="%s"]'
    for name in ("dashboard", "integrations"):
        page.wait_for_selector(button % name, state="visible", timeout=8000)
        page.click(button % name)
        page.wait_for_selector(f".office-subview.office-{name}", timeout=8000)
        page.click(button % name)
        page.wait_for_selector(".office-subview", state="detached", timeout=8000)
    # Moving from one to the other is a switch, not a toggle.
    page.click(button % "dashboard")
    page.wait_for_selector(".office-subview.office-dashboard", timeout=8000)
    page.click(button % "integrations")
    page.wait_for_selector(".office-subview.office-integrations", timeout=8000)


def test_office_folder_shows_live_while_its_subagents_run(browser):
    page = browser.new_context(viewport={"width": 1400, "height": 800}).new_page()
    projects = [{"project_id": "p1", "name": "One", "color": "#4682B4"}, {"project_id": "p2", "name": "Two", "color": "#4682B4"}]
    now = __import__("time").time()
    parents = [{"parent_session_id": "s1", "project_id": "p1", "title": "Run", "latest_at": now,
                "children": [{"session_id": "c1", "status": "running", "ended_at": None, "last_activity": now}]}]
    page.route("**/api/projects*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"projects": projects})))
    page.route(re.compile(r".*/api/agent-canvas/sessions.*"), lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"parents": parents})))
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function(READY, polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate("async () => { await switchPanel('office'); }")
    page.wait_for_selector('.office-project-folder[data-project-id="p1"] .project-folder-schedule-live', timeout=10000)
    assert page.locator('.office-project-folder[data-project-id="p2"] .project-folder-schedule-live').count() == 0
    gaps = page.evaluate("""() => { const b = document.querySelector('.office-project-folder[data-project-id="p1"] .project-folder-schedule-live');
      const r = b.getBoundingClientRect(), w = b.parentElement.getBoundingClientRect(); return [r.top - w.top, w.bottom - r.bottom]; }""")
    assert abs(gaps[0] - gaps[1]) <= 1
    dot = page.evaluate("""() => { const d = document.querySelector('.office-project-folder .color-dot');
      const r = d.getBoundingClientRect(), w = d.parentElement.getBoundingClientRect(); return [r.top - w.top, w.bottom - r.bottom]; }""")
    assert abs(dot[0] - dot[1]) < 0.1, dot


def test_floor_recovers_its_colours_when_a_fade_is_interrupted():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        try:
            page = _open(browser, viewport={"width": 1200, "height": 800})
            out = page.evaluate("""async () => {
              const src = [...document.scripts].map(s => s.src).find(s => /office\\/index\\.js/.test(s)) || '';
              const m = await import('/static/office/scene.js' + (src.includes('?') ? src.slice(src.indexOf('?')) : ''));
              const canvas = document.createElement('canvas');
              canvas.style.cssText = 'position:fixed;left:0;top:0;width:400px;height:300px';
              document.body.appendChild(canvas);
              const s = m.createOfficeScene(canvas, {});
              const brightest = () => { let mx = 0; s.scene.traverse(o => {
                if (!o.isMesh || !o.material || Array.isArray(o.material) || !o.material.emissive || o.material.transparent) return;
                mx = Math.max(mx, o.material.color.r, o.material.color.g, o.material.color.b); }); return mx; };
              const before = brightest();
              s.playIntro(5000);      // everything is dark, waiting to light up
              s.playWake(0, 200);     // the page is left and reopened meanwhile
              s.start();
              await new Promise(r => setTimeout(r, 2500));
              const after = brightest();
              s.stop(); canvas.remove();
              return {before, after}; }""")
            assert out["before"] > 0.1
            assert out["after"] == pytest.approx(out["before"], abs=0.01)
        finally:
            browser.close()


def test_part_added_during_a_fade_keeps_its_colour_when_another_fade_takes_over():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        try:
            page = _open(browser, viewport={"width": 1200, "height": 800})
            red = page.evaluate("""async () => {
              const src = [...document.scripts].map(s => s.src).find(s => /office\\/index\\.js/.test(s)) || '';
              const m = await import('/static/office/scene.js' + (src.includes('?') ? src.slice(src.indexOf('?')) : ''));
              const canvas = document.createElement('canvas');
              canvas.style.cssText = 'position:fixed;left:0;top:0;width:400px;height:300px';
              document.body.appendChild(canvas);
              const s = m.createOfficeScene(canvas, {});
              let sample = null;
              s.scene.traverse(o => { if (!sample && o.isMesh && o.material && o.material.emissive && o.parent) sample = o; });
              s.playWake(5000, 200);
              const part = sample.clone();
              part.material = new sample.material.constructor({ color: 0xffffff });
              sample.parent.add(part);
              s.playWake(5000, 200);   // dims the new part, still uncloned
              s.playWake(0, 200);      // and this one takes over from it
              s.start();
              await new Promise(r => setTimeout(r, 2500));
              const value = part.material.color.r;
              s.stop(); canvas.remove();
              return value; }""")
            assert red == pytest.approx(1, abs=0.01)
        finally:
            browser.close()
