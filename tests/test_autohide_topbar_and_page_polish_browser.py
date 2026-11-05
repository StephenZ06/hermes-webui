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


def test_a_closing_bar_lets_the_pointer_through_to_buttons_beneath_it(page):
    page.mouse.move(600, 0)
    page.wait_for_function(f"() => ({BAR_TOP})() === 0", timeout=3000)
    page.mouse.move(600, 500)
    hit = page.evaluate("""() => { const e = document.elementFromPoint(600, 20);
      return !!e.closest('.app-titlebar'); }""")
    assert hit is False


def test_touch_screens_keep_the_bar_because_they_cannot_reveal_it(browser):
    page = _open(browser, viewport={"width": 1024, "height": 768}, has_touch=True, is_mobile=True)
    assert page.evaluate(BAR_TOP) == 0
    assert page.evaluate("() => getComputedStyle(document.querySelector('.app-titlebar')).position") != "fixed"


def test_rail_icons_arrive_with_the_stylesheet_not_one_request_each(browser):
    """Each icon used to be its own request, so a hard refresh drew them one by one."""
    page = browser.new_context(viewport={"width": 1400, "height": 800}).new_page()
    requests = []
    page.on("request", lambda r: requests.append(r.url) if re.search(r"(nav-[a-z]+-mark|nav-mark|nav-dashboard-icon)\.png", r.url) else None)
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => !document.documentElement.classList.contains('nav-marks-pending')", timeout=8000)
    page.wait_for_timeout(300)
    assert requests == []
    masks = page.evaluate("""() => [...document.querySelectorAll('.rail :is(.page-nav-mark,.chat-nav-mark,.office-nav-mark)')]
      .map(e => { const c = getComputedStyle(e); return c.maskImage + c.backgroundImage; })""")
    assert masks and all("data:image/png" in m for m in masks)


def test_rail_shows_without_waiting_for_settings_and_kanban_stays_put(browser):
    """A slow page load used to outlast the rail's timer, so it showed half loaded."""
    context = browser.new_context(viewport={"width": 1400, "height": 800})
    page = context.new_page()
    held = []
    page.route("**/api/settings*", lambda route: held.append(route))
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => !document.documentElement.classList.contains('nav-marks-pending')", timeout=8000)
    assert page.evaluate("() => document.querySelector('.rail [data-panel=kanban]').hidden") is False
    for route in held:
        route.continue_()
    page.unroute("**/api/settings*")

    page.evaluate("() => localStorage.setItem('hermes-hide-kanban', '1')")
    page.goto(BASE + "/", wait_until="commit")
    page.wait_for_selector(".rail [data-panel='kanban']", state="attached", timeout=10000)
    page.wait_for_function("() => !document.documentElement.classList.contains('nav-marks-pending')", timeout=8000)
    assert page.evaluate("() => document.querySelector('.rail [data-panel=kanban]').hidden") is True


def test_usage_card_swaps_windows_with_dots_and_names_them_in_the_label(page):
    page.evaluate("async () => { await switchPanel('chat'); }")
    page.evaluate("""() => { const d = {available: true, provider: 'openai-codex', windows: [
      {label: 'Session', used_percent: 30}, {label: 'Weekly', used_percent: 60}]};
      _accountUsageData = d; _accountUsageWindow = 'session'; _renderAccountUsageImpl(d); }""")
    label = "() => document.getElementById('chatUsageWidgetLabel').textContent"
    assert page.evaluate(label) == "Session usage (5H)"
    weekly = page.locator("[data-usage-window='weekly']")
    assert weekly.text_content() == "" and weekly.get_attribute("aria-label") == "Weekly window"
    weekly.click()
    page.wait_for_timeout(450)
    assert page.evaluate(label) == "Session usage (W)"
    state = page.evaluate("""() => { const t = document.getElementById('chatUsageWidgetWindowToggle'), a = getComputedStyle(t, '::before');
      const root = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
      const probe = document.createElement('i'); probe.style.color = root; document.body.append(probe);
      const accent = getComputedStyle(probe).color; probe.remove();
      return {color: a.backgroundColor, accent, x: new DOMMatrix(a.transform).m41, w: a.width}; }""")
    assert state["color"] == state["accent"] and state["x"] == 14 and state["w"] == "6px"


FOLDER_ROW_HOSTS = [['', 'sessionList'], ['nb-folders', ''], ['office-project-folders', ''], ['', 'workHubProjects']]


def test_folder_row_parts_share_one_centre_with_no_offsets(page):
    """Every part is centred by the row, in every page's host and with no nudges."""
    state = page.evaluate("""(hosts) => { document.documentElement.dataset.skin = 'zeus-2';
      const made = hosts.map(([cls, id]) => {
        const host = document.createElement('div'); if (cls) host.className = cls;
        const target = id && document.getElementById(id);
        const list = document.createElement('div'); list.className = 'project-folder-list';
        const row = document.createElement('button'); row.className = 'project-chip project-folder-row';
        row.innerHTML = '<span class="project-folder-chevron"></span><span class="project-folder-dot-slot"><span class="color-dot"></span></span><span class="project-folder-name">Folder</span><span class="project-folder-count">1</span>';
        list.append(row); (target || host).append(list); if (!target) document.body.append(host);
        return [list, host, !target, row]; });
      const out = made.map(([, , , row]) => { const r = row.getBoundingClientRect();
        return [...row.children].map(part => { const b = part.getBoundingClientRect(), c = getComputedStyle(part);
          return {offset: (b.top + b.bottom - r.top - r.bottom) / 2, top: c.top, translate: c.translate, transform: c.transform}; }); });
      const slots = made.map(([, , , row]) => ['.project-folder-chevron', '.project-folder-dot-slot'].map(sel => {
        const c = getComputedStyle(row.querySelector(sel)); return [c.display, c.alignItems, c.justifyContent, c.height]; }));
      made.forEach(([list, host, own]) => { list.remove(); if (own) host.remove(); });
      return {out, slots}; }""", FOLDER_ROW_HOSTS)
    for row in state["out"]:
        assert len(row) == 4
        for part in row:
            assert abs(part["offset"]) <= 0.75, part
            assert part["top"] == "auto" and part["translate"] == "none" and part["transform"] == "none", part
    assert state["slots"] == [[["flex", "center", "center", "16px"]] * 2] * 4


def test_side_menu_labels_centre_on_the_row_without_offsets(page):
    state = page.evaluate("""() => { document.documentElement.dataset.skin = 'zeus-2';
      const nav = document.createElement('div'); nav.id = 'panelMemory';
      const row = document.createElement('button'); row.className = 'side-menu-item';
      row.innerHTML = '<svg width="16" height="16"></svg><span>Label</span>';
      nav.append(row); document.body.append(nav);
      const label = row.querySelector('span'), r = row.getBoundingClientRect(), b = label.getBoundingClientRect(), c = getComputedStyle(label);
      const out = {offset: (b.top + b.bottom - r.top - r.bottom) / 2, translate: c.translate, transform: c.transform, trim: c.textBoxTrim};
      nav.remove(); return out; }""")
    assert abs(state["offset"]) <= 0.75, state
    assert state["translate"] == "none" and state["transform"] == "none", state
    assert state["trim"] == "trim-both", state


def test_view_live_is_bold_and_status_pill_text_is_centred(page):
    state = page.evaluate("""() => { const h = document.createElement('div'); h.className = 'office-header';
      h.innerHTML = '<span class="office-pill">IDLE</span><button id="officePauseBtn" class="office-header-btn">View live</button>';
      document.body.append(h); const b = getComputedStyle(h.querySelector('button')), p = getComputedStyle(h.querySelector('span'));
      const out = {weight: b.fontWeight, btn: [b.paddingTop, b.paddingBottom], pill: [p.paddingTop, p.paddingBottom], case: b.textTransform};
      h.remove(); return out; }""")
    assert state == {"weight": "700", "btn": ["2px", "2px"], "pill": ["3px", "3px"], "case": "uppercase"}


def test_every_suggestion_icon_sits_one_pixel_low(page):
    shifts = page.evaluate("() => [...document.querySelectorAll('.suggestion-grid > .suggestion > svg')].map(i => getComputedStyle(i).translate)")
    assert shifts == ["0px 1px"] * 3


def test_chat_session_titles_have_no_zeus_offset(page):
    shift = page.evaluate("""() => { document.documentElement.dataset.skin = 'zeus-2';
      const row = document.createElement('div'); row.className = 'session-item';
      row.innerHTML = '<span class="session-text">Title</span>'; document.body.append(row);
      const value = getComputedStyle(row.firstChild).translate; row.remove(); return value; }""")
    assert shift == "none"


def test_new_chat_logo_rides_above_its_layout_slot(page):
    assert page.evaluate("() => getComputedStyle(document.querySelector('.empty-logo')).translate") == "0px -8px"


def test_usage_card_rows_keep_a_tight_even_layout(page):
    state = page.evaluate("""() => { switchPanel('chat');
      _renderAccountUsage({available: true, provider: 'openai-codex', plan: 'Pro',
        windows: [{label: '5h session', used_percent: 10}, {label: 'Weekly', used_percent: 42}]});
      selectAccountUsageWindow('session');
      const card = document.getElementById('chatUsageWidget'), c = getComputedStyle(card);
      const row = card.querySelector('.chat-usage-widget-title-row').getBoundingClientRect();
      const stage = document.getElementById('chatUsageWidgetLabelStage').getBoundingClientRect();
      const reset = card.querySelector('.chat-usage-widget-reset');
      return {sides: [c.paddingLeft, c.paddingRight], rowHeight: row.height,
              labelOffset: stage.top + stage.height / 2 - (row.top + row.height / 2),
              size: getComputedStyle(document.getElementById('chatUsageWidgetLabel')).fontSize,
              emptyReset: getComputedStyle(reset).display, height: card.getBoundingClientRect().height}; }""")
    assert state["sides"] == ["12px", "12px"]
    assert state["rowHeight"] == 14
    assert abs(state["labelOffset"]) <= 1  # the taller dot buttons must not push the label down
    assert state["size"] == "13px"
    assert state["emptyReset"] == "none"
    assert state["height"] == round(state["height"])


CRONS = {"jobs": [{"id": "a1", "name": "Daily digest", "enabled": True, "state": "scheduled", "schedule": {"kind": "cron", "expr": "0 9 * * *"},
                   "schedule_display": "0 9 * * *", "prompt": "Summarise", "profile": "default"},
                  {"id": "a2", "name": "Weekly report", "enabled": True, "state": "scheduled", "schedule": {"kind": "cron", "expr": "0 9 * * 1"},
                   "schedule_display": "0 9 * * 1", "prompt": "Report", "profile": "default"}],
         "other_profile_count": 2}


def _open_scheduled_jobs(page):
    page.route("**/api/crons", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(CRONS)))
    page.evaluate("async () => { await switchPanel('tasks'); }")
    page.wait_for_selector("#cronList .cron-item")


def test_scheduled_jobs_cards_share_the_page_background(page):
    _open_scheduled_jobs(page)
    page.locator("#cronList .cron-item").nth(1).click()
    page.wait_for_selector("#taskDetailBody .detail-card")
    page.mouse.move(900, 500)
    page.wait_for_timeout(300)
    state = page.evaluate("""() => { const bg = s => getComputedStyle(document.querySelector(s)).backgroundColor;
      return {page: bg('#mainTasks'), idle: bg('#cronList .cron-item:not(.active)'), active: bg('#cronList .cron-item.active'),
              toggle: bg('#cronList .cron-profile-toggle'), card: bg('#taskDetailBody .detail-card')}; }""")
    assert state["idle"] == state["toggle"] == state["card"] == state["page"]
    assert state["active"] != state["page"]  # the selected job stays marked


def test_scheduled_jobs_header_and_toggle_nudges(page):
    _open_scheduled_jobs(page)
    state = page.evaluate("""() => { const c = s => getComputedStyle(document.querySelector(s));
      return {title: c('#panelTasks > .panel-head > span').translate,
              icons: [...document.querySelectorAll('#panelTasks > .panel-head .panel-head-btn svg')].map(i => getComputedStyle(i).translate),
              toggle: [c('#cronList .cron-profile-toggle').paddingTop, c('#cronList .cron-profile-toggle').paddingBottom]}; }""")
    assert state["title"] == "0px 1px"
    assert state["icons"] == ["0px 1px"] * 3
    assert state["toggle"] == ["7px", "9px"]


def test_scheduled_job_badge_text_sits_one_pixel_low(page):
    _open_scheduled_jobs(page)
    state = page.evaluate("""() => ['.cron-profile-badge', '.cron-status'].map(s => { const c = getComputedStyle(document.querySelector('#cronList ' + s));
      return [c.paddingTop, c.paddingBottom]; })""")
    assert state == [["1px", "1px"], ["2px", "2px"]]


def test_scheduled_job_script_card_text_sits_one_pixel_low(page):
    state = page.evaluate("""() => { const host = document.getElementById('taskDetailBody');
      const card = document.createElement('div'); card.className = 'detail-card cron-script-card';
      card.innerHTML = '<div class="detail-script">job.py</div><div class="detail-hint cron-script-card-hint">Resolved</div>';
      host.append(card); const s = getComputedStyle(card.firstChild), h = getComputedStyle(card.lastChild);
      const out = {script: [s.paddingTop, s.paddingBottom], hint: h.translate}; card.remove(); return out; }""")
    assert state == {"script": ["11px", "9px"], "hint": "0px 1px"}


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


def test_usage_card_title_is_regular_and_window_buttons_are_wordless(page):
    page.evaluate("async () => { await switchPanel('chat'); }")
    page.wait_for_selector("#chatUsageWidgetWindowToggle button", state="visible", timeout=8000)
    assert page.evaluate("() => getComputedStyle(document.querySelector('.chat-usage-widget-label')).fontWeight") == "400"
    assert page.evaluate("() => [...document.querySelectorAll('#chatUsageWidgetWindowToggle button')].map(b => b.innerText)") == ["", ""]
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
