"""The Dashboard page: opens from the nav, switches tabs (remembered), shows
Work Hub quests that open the item, and fits a phone without sideways scroll."""

import json
import time
import urllib.request
import uuid

import pytest

from tests._pytest_port import BASE


def _post(path, body):
    req = urllib.request.Request(BASE + path, method="POST", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def _rev():
    return json.loads(urllib.request.urlopen(BASE + "/api/work_hub/bootstrap", timeout=10).read())["revision"]


@pytest.fixture()
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        b = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            yield b
        finally:
            b.close()


def _open(browser, **ctx):
    page = browser.new_context(**ctx).new_page()
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    return page


def test_dashboard_tabs_switch_and_are_remembered(browser):
    page = _open(browser, viewport={"width": 1280, "height": 860})
    page.evaluate("() => { try { localStorage.removeItem('hermes-dashboard-tab'); } catch (_) {} }")
    page.evaluate("async () => { await switchPanel('dashboard'); }")
    # The Character page is the default view, first in the side panel.
    page.wait_for_selector("#dashboardRoot .rpg-stage", timeout=15000)
    assert page.evaluate("() => document.querySelector('#dashboardSidebar .side-menu-item').textContent.trim()").startswith("Character")
    page.evaluate("() => document.querySelector('.dash-tabs [data-dash-tab=personal]').click()")
    page.wait_for_selector("#dashboardRoot .dash-stats", timeout=15000)
    assert page.evaluate("() => document.querySelector('.dash-tabs .on').textContent") == "Personal"
    assert page.evaluate("() => document.querySelector('.dash-head h1').textContent") == "PERSONAL DASHBOARD"

    page.evaluate("() => document.querySelector('.dash-tabs [data-dash-tab=career]').click()")
    page.wait_for_function("() => document.querySelector('.dash-body')?.dataset.tab === 'career' && document.querySelector('.dash-stats')", polling=100, timeout=15000)
    assert "Funnel" in page.evaluate("() => document.querySelector('.dash-body').textContent")
    assert page.evaluate("() => document.querySelector('#dashboardSidebar .side-menu-item.active').textContent.trim()") == "Career"

    page.reload(wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("async () => { await switchPanel('dashboard'); }")
    page.wait_for_function("() => document.querySelector('.dash-body')?.dataset.tab === 'career'", polling=100, timeout=15000)


def test_a_quest_is_picked_from_the_work_hub_finishes_there_and_earns_xp(browser):
    title = f"Phase 10 {uuid.uuid4().hex[:5]}"
    item_id = _post("/api/work_hub/items/create", {"item": {"title": title, "status": "todo", "priority": "high"}, "expected_revision": _rev()})["item"]["id"]
    page = _open(browser, viewport={"width": 1280, "height": 860})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('personal'); }")
    page.wait_for_selector(".dash-card.is-quests", timeout=15000)

    page.evaluate("() => window.HermesDashboard.openQuestPicker()")
    box = f".dash-picker input[value='{item_id}']"
    page.wait_for_selector(box, timeout=15000)
    page.evaluate(f"() => {{ const b = document.querySelector(\"{box}\"); b.checked = true; b.dispatchEvent(new Event('change', {{bubbles: true}})); }}")
    page.evaluate("() => document.querySelector('[data-picker-add]').click()")
    row = f".dash-quest-row[data-quest='{item_id}']"
    page.wait_for_selector(row, timeout=15000)
    assert not page.evaluate(f"() => document.querySelector(\"{row}\").classList.contains('is-done')")

    # Finished in the Work Hub (or by a chat through the work_hub tool).
    _post("/api/work_hub/items/update", {"item_id": item_id, "item": {"status": "done"}, "expected_revision": _rev()})
    page.evaluate("() => window.HermesDashboard.select('career')")
    page.evaluate("() => window.HermesDashboard.select('personal')")
    page.wait_for_function(f"() => document.querySelector(\"{row}\")?.classList.contains('is-done')", polling=100, timeout=15000)
    assert page.evaluate(f"() => document.querySelector(\"{row} .dash-xp-gain\").textContent") == "+75 XP"  # high 50 x 1.5

    page.evaluate("() => window.HermesDashboard.select('character')")
    page.wait_for_selector(".rpg-stage .px-hero", timeout=15000)
    log = page.evaluate("() => document.querySelector('.dash-body').textContent")
    assert title in log and "+75 XP" in log
    assert page.evaluate("() => document.querySelectorAll('.rpg-tier').length") == 5
    assert page.evaluate("() => /Level \\d+/.test(document.querySelector('.rpg-title h2').textContent)")


def test_quest_rows_open_their_work_hub_item(browser):
    title = f"Dash quest {uuid.uuid4().hex[:5]}"
    item_id = _post("/api/work_hub/items/create", {"item": {"title": title, "status": "in_progress"}, "expected_revision": _rev()})["item"]["id"]
    _post("/api/dashboard/quests/add", {"item_ids": [item_id]})
    page = _open(browser, viewport={"width": 1280, "height": 860})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('personal'); }")
    quest = f".dash-quest-open[data-dash-item='{item_id}']"
    page.wait_for_selector(quest, timeout=15000)
    page.evaluate(f"() => document.querySelector(\"{quest}\").click()")
    page.wait_for_function(f"() => document.querySelector('main.main').classList.contains('showing-notes') && [...document.querySelectorAll('#workHubInspector input, #workHubInspector textarea')].some(e => e.value === {json.dumps(title)})", polling=100, timeout=15000)
    page.wait_for_selector("#workHubQuestToggle", timeout=10000)
    assert "On your quests" in page.evaluate("() => document.getElementById('workHubQuest').textContent")
    page.evaluate("() => document.getElementById('workHubQuestToggle').click()")
    page.wait_for_function("() => document.getElementById('workHubQuest')?.textContent.includes('Not a quest')", polling=100, timeout=10000)
    assert item_id not in json.loads(urllib.request.urlopen(BASE + "/api/dashboard/quests", timeout=10).read())["item_ids"]


def test_dashboard_fits_a_phone(browser):
    page = _open(browser, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('personal'); }")
    page.wait_for_selector("#dashboardRoot .dash-stats", timeout=15000)
    time.sleep(0.4)
    widths = page.evaluate("() => { const r = document.getElementById('mainDashboard'); return [r.scrollWidth, r.clientWidth, document.querySelector('.dash-stats').getBoundingClientRect().right, innerWidth]; }")
    assert widths[0] <= widths[1] + 1 and widths[2] <= widths[3]
    assert page.evaluate("() => getComputedStyle(document.querySelector('.dash-stats')).gridTemplateColumns.split(' ').length") == 2


def test_personal_dashboard_balances_cards_headers_and_learning_entry(browser):
    page = _dashboard(browser, "personal")
    page.wait_for_selector(".dash-grid.is-personal-focus", timeout=15000)
    layout = page.evaluate("""() => {
        const focus = document.querySelector('.dash-grid.is-personal-focus');
        const [quests, habits] = focus.children;
        const nav = document.querySelector('.dash-side-nav');
        const character = nav.querySelector('.side-menu-item');
        const learning = document.querySelector('.dash-card.is-learning-log');
        const form = learning.querySelector('form.is-learning');
        const input = form.querySelector('input[name=title]');
        const header = quests.querySelector('.dash-card-head');
        const icon = header.querySelector('.dash-card-icon').getBoundingClientRect();
        const card = quests.getBoundingClientRect();
        const action = header.querySelector('.dash-card-actions').getBoundingClientRect();
        const divider = header.getBoundingClientRect();
        const navBox = nav.getBoundingClientRect();
        const characterBox = character.getBoundingClientRect();
        return {
          firstIsQuests: quests.classList.contains('is-quests'),
          secondIsHabits: habits.classList.contains('is-habits'),
          questIsWider: quests.getBoundingClientRect().width > habits.getBoundingClientRect().width,
          iconTopEqualsLeft: Math.abs((icon.top - card.top) - (icon.left - card.left)) <= 1,
              actionTopEqualsDividerGap: Math.abs((action.top - card.top) - (divider.bottom - action.bottom)) <= 1,
          titleIsCentered: Math.abs(header.querySelector('h3').getBoundingClientRect().top - icon.top) <= 8,
          formIsLast: learning.querySelector('.dash-card-body').lastElementChild === form,
          titleInputBorder: getComputedStyle(input).borderTopWidth,
          navTopEqualsSide: Math.abs((characterBox.top - navBox.top) - (characterBox.left - navBox.left)) <= 1,
        };
    }""")
    assert layout["firstIsQuests"] and layout["secondIsHabits"] and layout["questIsWider"]
    assert layout["iconTopEqualsLeft"] and layout["actionTopEqualsDividerGap"]
    assert layout["titleIsCentered"] and layout["formIsLast"]
    assert layout["titleInputBorder"] == "0px"
    assert layout["navTopEqualsSide"]


def test_personal_pixel_icons_are_unboxed_and_optically_aligned(browser):
    page = _dashboard(browser, "personal")
    page.evaluate("""() => {
        document.documentElement.classList.add('dark');
        document.documentElement.dataset.skin = 'geist-contrast';
    }""")
    page.wait_for_selector(".dash-card-icon.is-pixel img[data-dash-pix]", timeout=15000)
    icons = page.evaluate("""() => [...document.querySelectorAll('.dash-card-icon.is-pixel')].map((box) => {
        const image = box.querySelector('img');
        return {
          name: image.dataset.dashPix,
          background: getComputedStyle(box).backgroundColor,
          x: getComputedStyle(image).getPropertyValue('--dash-pix-x').trim(),
          y: getComputedStyle(image).getPropertyValue('--dash-pix-y').trim(),
        };
    })""")
    names = {icon["name"] for icon in icons}
    assert {"personal-quest", "habits", "learning-log", "project-health"} <= names
    assert all(icon["background"] in {"transparent", "rgba(0, 0, 0, 0)"} for icon in icons)
    offsets = {icon["name"]: (icon["x"], icon["y"]) for icon in icons}
    assert offsets["personal-quest"] == ("0px", "0px")
    assert offsets["habits"] == ("0px", "-1px")
    assert offsets["learning-log"] == ("-3px", "0px")
    assert offsets["project-health"] == ("0px", "-2px")


def test_character_page_fits_a_phone(browser):
    page = _open(browser, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('character'); }")
    page.wait_for_selector(".rpg-stage .px-hero", timeout=15000)
    time.sleep(0.4)
    assert page.evaluate("() => { const m = document.getElementById('mainDashboard'); return m.scrollWidth <= m.clientWidth + 1; }")
    assert page.evaluate("() => document.querySelector('.rpg-sheet').getBoundingClientRect().right <= innerWidth")


def test_character_page_uses_geist_contrast_dashboard_surfaces(browser):
    page = _open(browser, viewport={"width": 1280, "height": 860})
    page.evaluate("""async () => {
        document.documentElement.classList.add('dark');
        document.documentElement.dataset.skin = 'geist-contrast';
        await switchPanel('dashboard');
        window.HermesDashboard.select('character');
    }""")
    page.wait_for_selector(".rpg-stage .px-hero", timeout=15000)
    visuals = page.evaluate("""() => {
        const canvas = document.getElementById('mainDashboard');
        const panel = document.querySelector('.rpg-panel');
        const stage = document.querySelector('.rpg-stage');
        return {
          canvasImage: getComputedStyle(canvas).backgroundImage,
          panelBackground: getComputedStyle(panel).backgroundColor,
          panelBorder: getComputedStyle(panel).borderColor,
          stageBackground: getComputedStyle(stage).backgroundColor,
        };
    }""")
    assert "background.png" not in visuals["canvasImage"]
    assert visuals["panelBackground"] == "rgb(10, 10, 10)"
    assert visuals["panelBorder"] == "rgb(63, 63, 63)"
    assert visuals["stageBackground"] == "rgb(10, 10, 10)"


def _dashboard(browser, tab, **ctx):
    page = _open(browser, **(ctx or {"viewport": {"width": 1280, "height": 860}}))
    page.evaluate(f"async () => {{ await switchPanel('dashboard'); window.HermesDashboard.select('{tab}'); }}")
    return page


def test_a_habit_is_added_and_ticked_for_vitality_xp(browser):
    page = _dashboard(browser, "personal")
    page.wait_for_selector("[data-form-open=habit]", timeout=15000)
    name = f"Gym {uuid.uuid4().hex[:4]}"
    page.evaluate("() => document.querySelector('[data-form-open=habit]').click()")
    page.wait_for_selector("form[data-form=habit] input[name=name]", timeout=5000)
    page.fill("form[data-form=habit] input[name=name]", name)
    page.evaluate("() => document.querySelector('form[data-form=habit] [type=submit]').click()")
    toggle = page.wait_for_selector(f".dash-habit:has-text('{name}') [data-habit-toggle]", timeout=10000)
    toggle.evaluate("el => el.click()")
    page.wait_for_function(f"() => [...document.querySelectorAll('.dash-habit')].find(h => h.textContent.includes('{name}'))?.querySelector('.dash-habit-check.is-on')", polling=100, timeout=10000)
    page.evaluate("() => window.HermesDashboard.select('character')")
    page.wait_for_selector(".rpg-stage .px-hero", timeout=15000)
    assert name in page.evaluate("() => document.querySelector('.dash-body').textContent")


def test_a_manual_sale_meets_a_goal_and_unlocks_the_first_sale_milestone(browser):
    page = _dashboard(browser, "business")
    page.wait_for_selector("[data-form-open=goal]", timeout=15000)
    page.evaluate("() => document.querySelector('[data-form-open=goal]').click()")
    page.fill("form[data-form=goal] input[name=target]", "1")
    page.evaluate("() => document.querySelector('form[data-form=goal] [type=submit]').click()")
    page.wait_for_selector(".dash-goal", timeout=10000)
    page.evaluate("() => document.querySelector('[data-form-open=sale]').click()")
    page.fill("form[data-form=sale] input[name=amount]", "29")
    page.fill("form[data-form=sale] input[name=product]", "Pro plan")
    page.evaluate("() => document.querySelector('form[data-form=sale] [type=submit]').click()")
    page.wait_for_function("() => document.querySelector('.dash-goal')?.classList.contains('is-met')", polling=100, timeout=10000)
    unlocked = page.evaluate("() => [...document.querySelectorAll('.dash-badge:not(.is-locked) strong')].map(e => e.textContent)")
    assert "First Sale" in unlocked
    assert "Pro plan" in page.evaluate("() => document.querySelector('.dash-body').textContent")


def test_a_reward_is_bought_with_gold_on_the_character_page(browser):
    item = _post("/api/work_hub/items/create", {"item": {"title": f"Gold {uuid.uuid4().hex[:4]}", "priority": "high"}, "expected_revision": _rev()})["item"]["id"]
    _post("/api/work_hub/items/update", {"item_id": item, "item": {"status": "done"}, "expected_revision": _rev()})
    page = _dashboard(browser, "character")
    page.wait_for_selector("[data-form-open=reward]", timeout=15000)
    page.evaluate("() => document.querySelector('[data-form-open=reward]').click()")
    page.fill("form[data-form=reward] input[name=name]", "Coffee break")
    page.fill("form[data-form=reward] input[name=cost]", "5")
    page.evaluate("() => document.querySelector('form[data-form=reward] [type=submit]').click()")
    buy = page.wait_for_selector(".rpg-reward:has-text('Coffee break') [data-reward-redeem]:not([disabled])", timeout=10000)
    before = page.evaluate("() => parseInt(document.querySelector('.rpg-purse b').textContent.replace(/\\D/g, ''), 10)")
    buy.evaluate("el => el.click()")
    page.wait_for_function(f"() => parseInt(document.querySelector('.rpg-purse b')?.textContent.replace(/\\D/g, ''), 10) === {before} - 5", polling=100, timeout=10000)
    assert "Coffee break" in page.evaluate("() => document.querySelector('.rpg-history').textContent")


def test_libraries_dev_effects_mount_on_the_character_page(browser):
    page = _dashboard(browser, "character")
    page.wait_for_selector(".rpg-stage .px-hero", timeout=15000)
    page.wait_for_function("() => document.querySelector('.rpg-member-avatar canvas')", polling=100, timeout=15000)
    assert page.evaluate("() => document.querySelectorAll('.rpg-member-avatar canvas').length") >= 1


def test_work_hub_cards_mark_quests(browser):
    item = _post("/api/work_hub/items/create", {"item": {"title": f"Marked {uuid.uuid4().hex[:4]}"}, "expected_revision": _rev()})["item"]["id"]
    _post("/api/dashboard/quests/add", {"item_ids": [item]})
    page = _open(browser, viewport={"width": 1280, "height": 860})
    page.evaluate("async () => { await switchPanel('notes'); }")
    page.wait_for_selector(f".work-hub-card[data-item-id='{item}'] .work-hub-quest-mark", timeout=15000)


def test_a_refresh_with_nothing_new_does_not_repaint(browser):
    page = _open(browser, viewport={"width": 1280, "height": 860})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('personal'); }")
    page.wait_for_selector(".dash-stats", timeout=15000)
    page.wait_for_function("() => !window.HermesDashboard._state.loading.personal", polling=100, timeout=10000)
    page.evaluate("() => { window.__body = document.querySelector('.dash-body'); }")
    page.evaluate("() => window.HermesDashboard.refresh()")
    page.wait_for_function("() => !window.HermesDashboard._state.loading.personal", polling=100, timeout=10000)
    assert page.evaluate("() => window.__body === document.querySelector('.dash-body')")


def test_the_sales_connection_lives_in_settings(browser):
    page = _open(browser, viewport={"width": 1280, "height": 860})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('business'); }")
    page.wait_for_selector(".dash-stats", timeout=15000)
    assert not page.evaluate("() => !!document.querySelector('form[data-form=connect]')")
    page.evaluate("() => document.querySelector('.dash-connect-hint').click()")
    page.wait_for_selector("form[data-form=connect]", timeout=15000)
    assert page.evaluate("() => document.querySelector('.dash-head h1').textContent") == "SETTINGS"


def test_header_controls_share_a_height_and_cards_have_equal_padding(browser):
    page = _open(browser, viewport={"width": 1440, "height": 900})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('personal'); }")
    page.wait_for_selector(".dash-stats", timeout=15000)
    page.wait_for_function("() => !window.HermesDashboard._state.loading.personal", polling=100, timeout=10000)
    heights = page.evaluate("() => [document.querySelector('.dash-tabs'), document.querySelector('.dash-char-btn')].map(e => Math.round(e.getBoundingClientRect().height))")
    assert heights[0] == heights[1]
    pads = page.evaluate("""() => [...document.querySelectorAll('.dash-card')].filter(c => c.querySelector(':scope > .dash-card-head')).map(c => {
        const r = c.getBoundingClientRect(), b = parseFloat(getComputedStyle(c).borderTopWidth), h = c.querySelector('.dash-card-head').getBoundingClientRect();
        return [Math.round(h.top - r.top - b), Math.round(h.left - r.left - b), Math.round(r.right - b - h.right)]; })""")
    assert pads and all(p == [16, 16, 16] for p in pads)


def test_paired_cards_share_a_height_and_long_panels_scroll_inside(browser):
    for i in range(6):
        _post("/api/dashboard/learning/add", {"title": f"Course {uuid.uuid4().hex[:4]} {i}", "kind": "course", "area": "career"})
    page = _open(browser, viewport={"width": 1440, "height": 900})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('personal'); }")
    page.wait_for_selector(".dash-grid", timeout=15000)
    page.wait_for_function("() => !window.HermesDashboard._state.loading.personal", polling=100, timeout=10000)
    pairs = page.evaluate("() => [...document.querySelectorAll('.dash-grid')].map(g => [...g.children].map(c => Math.round(c.getBoundingClientRect().height)))")
    assert pairs and all(len(set(p)) == 1 for p in pairs)
    page.evaluate("() => window.HermesDashboard.select('character')")
    page.wait_for_selector(".rpg-stage", timeout=15000)
    page.wait_for_function("() => !window.HermesDashboard._state.loading.character", polling=100, timeout=10000)
    capped = page.evaluate("() => [...document.querySelectorAll('.rpg-col > .rpg-panel')].map(p => Math.round(p.getBoundingClientRect().height))")
    assert capped and max(capped) <= 560


def test_a_fresh_launch_opens_the_dashboard_but_a_reload_in_chat_stays_in_chat(browser):
    # The test server pins Chat as the start page; switch this page to the
    # product default (Dashboard) and replay the boot-time route restore.
    page = _open(browser, viewport={"width": 1280, "height": 860})
    opened = page.evaluate("""async () => {
        document.body.dataset.startPage = 'dashboard';
        try { sessionStorage.removeItem('hermes-webui-panel-route'); } catch (_) {}
        await switchPanel('chat'); try { sessionStorage.removeItem('hermes-webui-panel-route'); } catch (_) {}
        await restorePanelFromRoute(); return _currentPanel; }""")
    assert opened == "dashboard"
    stays = page.evaluate("""async () => { await switchPanel('chat'); await restorePanelFromRoute(); return _currentPanel; }""")
    assert stays == "chat"  # Chat is remembered for the tab
    assert page.evaluate("() => [...document.querySelector('.rail').children].filter(e => e.dataset.panel)[0].dataset.panel") == "dashboard"


def test_dashboard_summary_tiles_center_icon_copy_and_footer_controls(browser):
    for i in range(8):
        _post("/api/dashboard/learning/add", {"title": f"Footer fixture {uuid.uuid4().hex[:4]} {i}", "kind": "course", "area": "career"})
    page = _open(browser, viewport={"width": 1440, "height": 900})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('personal'); }")
    page.wait_for_selector(".dash-stats", timeout=15000)
    page.wait_for_function("() => !window.HermesDashboard._state.loading.personal", polling=100, timeout=10000)
    for tab in ("personal", "career", "business"):
        page.evaluate(f"async () => {{ window.HermesDashboard.select('{tab}'); }}")
        page.wait_for_function(f"() => !window.HermesDashboard._state.loading.{tab}", polling=100, timeout=10000)
        stats = page.evaluate("""() => [...document.querySelectorAll('.dash-stat')].map(s => {
            const icon = s.querySelector('.dash-stat-icon'); const copy = s.querySelector('.dash-stat-copy');
            if (!icon || !copy) return null;
            const card = s.getBoundingClientRect(), a = icon.getBoundingClientRect(), b = copy.getBoundingClientRect();
            const left = Math.min(a.left, b.left), right = Math.max(a.right, b.right);
            return Math.round(((left + right) / 2) - ((card.left + card.right) / 2));
        })""")
        assert len(stats) == 4 and all(offset is not None and abs(offset) <= 1 for offset in stats)
    page.evaluate("() => window.HermesDashboard.select('personal')")
    page.wait_for_function("() => !window.HermesDashboard._state.loading.personal", polling=100, timeout=10000)
    assert page.evaluate("() => [...document.querySelectorAll('.dash-stat small')].some(e => e.textContent.trim() === 'Personal quests')")
    footer = page.evaluate("""() => { const card = document.querySelector('.dash-card.is-learning-log'), form = card.querySelector('form.is-learning'),
        button = form.querySelector('button'), selects = [...form.querySelectorAll('.themed-select-trigger')], r = card.getBoundingClientRect(), f = form.getBoundingClientRect();
        return {bottom: Math.round(r.bottom - f.bottom - parseFloat(getComputedStyle(card).borderBottomWidth)), heights: [button, ...selects].map(e => Math.round(e.getBoundingClientRect().height))}; }""")
    assert abs(footer["bottom"] - 16) <= 1
    assert len(set(footer["heights"])) == 1
    icons = page.evaluate("""() => [...document.querySelectorAll('.dash-card')].filter(c => c.querySelector(':scope > .dash-card-head .dash-card-icon')).map(c => {
        const r = c.getBoundingClientRect(), b = parseFloat(getComputedStyle(c).borderTopWidth), i = c.querySelector('.dash-card-icon').getBoundingClientRect();
        return [Math.round(i.top - r.top - b), Math.round(i.left - r.left - b)]; })""")
    assert icons and all(left - top == 1 for top, left in icons)


def test_the_wheel_moves_on_to_the_page_once_a_card_has_scrolled_to_its_end(browser):
    for i in range(12):
        _post("/api/dashboard/rewards/add", {"name": f"Reward {uuid.uuid4().hex[:4]} {i}", "cost": 10 + i})
    page = _open(browser, viewport={"width": 1440, "height": 800})
    page.evaluate("() => document.querySelectorAll('.app-tour-overlay').forEach(e => e.remove())")
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('character'); }")
    page.wait_for_selector(".rpg-stage", timeout=15000)
    page.wait_for_function("() => !window.HermesDashboard._state.loading.character", polling=100, timeout=10000)
    target = page.evaluate("""() => { const m = document.getElementById('mainDashboard');
        const panel = [...document.querySelectorAll('.rpg-col > .rpg-panel')].find(p => { const b = p.querySelector('.dash-card-body'); return b && b.scrollHeight > b.clientHeight + 4; });
        if (!panel) return null; panel.scrollIntoView({block: 'center'}); const b = panel.querySelector('.dash-card-body'); b.scrollTop = 0;
        const r = b.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2, m.scrollTop]; }""")
    if target is None or target[2] < 50:
        pytest.skip("no scrolling card or page in this state")
    page.mouse.move(target[0], target[1])
    for _ in range(4):
        page.mouse.wheel(0, -200)
        time.sleep(0.15)
    page.wait_for_function(f"() => document.getElementById('mainDashboard').scrollTop < {target[2]}", polling=100, timeout=5000)
