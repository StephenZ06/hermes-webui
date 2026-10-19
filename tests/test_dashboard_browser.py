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
    page.wait_for_selector(".rpg-stage :is(.px-hero,.rpg-hero-video)", timeout=15000)
    log = page.evaluate("() => document.querySelector('.dash-body').textContent")
    assert title in log and "+75 XP" in log
    assert page.evaluate("() => document.querySelectorAll('.rpg-evo .rpg-evo-dots i').length") == 5  # five forms in the evolution carousel
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
    # The learning entry opens from the card's header button, as Habits' does.
    assert page.locator(".dash-card.is-learning-log form.is-learning").count() == 0
    page.click(".dash-card.is-learning-log [data-form-open='learning']")
    page.wait_for_selector(".dash-card.is-learning-log form.is-learning input[name=title]:focus", timeout=3000)
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
          // Measured from the frame art's bars (12px in at the top, 14.4px at the sides).
          iconTopEqualsLeft: Math.abs((icon.top - card.top - 12) - (icon.left - card.left - 14.4)) <= 1,
              actionTopEqualsDividerGap: Math.abs((action.top - card.top - 12) - (divider.bottom - 2 - action.bottom)) <= 1,
          titleIsCentered: Math.abs(header.querySelector('h3').getBoundingClientRect().top - icon.top) <= 8,
          formIsFirst: learning.querySelector('.dash-card-body').firstElementChild === form,
          inputSpansForm: Math.abs(input.getBoundingClientRect().width - form.clientWidth) <= 1,
          navTopEqualsSide: Math.abs((characterBox.top - navBox.top) - (characterBox.left - navBox.left)) <= 1,
        };
    }""")
    assert layout["firstIsQuests"] and layout["secondIsHabits"] and layout["questIsWider"]
    assert layout["iconTopEqualsLeft"] and layout["actionTopEqualsDividerGap"]
    assert layout["titleIsCentered"] and layout["formIsFirst"]
    assert layout["inputSpansForm"]  # the text has its own row; the choices and the button share the next
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
    page.wait_for_selector(".rpg-stage :is(.px-hero,.rpg-hero-video)", timeout=15000)
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
    page.wait_for_selector(".rpg-stage :is(.px-hero,.rpg-hero-video)", timeout=15000)
    # While the video loads the scene is black behind the ring; measure after.
    page.wait_for_function("() => !document.querySelector('.rpg-stage.is-media-loading')", polling=100, timeout=12000)
    visuals = page.evaluate("""() => {
        const canvas = document.getElementById('mainDashboard');
        const panel = document.querySelector('.rpg-panel');
        const stage = document.querySelector('.rpg-stage');
        return {
          canvasImage: getComputedStyle(canvas).backgroundImage,
          panelBackground: getComputedStyle(panel).backgroundColor,
          panelBorder: getComputedStyle(panel).borderColor,
          stageBackground: getComputedStyle(stage).backgroundColor,
          sceneBackground: getComputedStyle(stage.querySelector('.rpg-stage-scene')).backgroundImage,
        };
    }""")
    assert "background.png" not in visuals["canvasImage"]
    assert visuals["panelBackground"] == "rgb(10, 10, 10)"
    # Cards draw their outline with the antique-gold pixel frame in every skin.
    assert visuals["panelBorder"] == "rgba(0, 0, 0, 0)"
    # The stage is the gold frame only; the night scene inside it is painted.
    assert visuals["stageBackground"] == "rgba(0, 0, 0, 0)" and "gradient" in visuals["sceneBackground"]


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
    page.wait_for_selector(".rpg-stage :is(.px-hero,.rpg-hero-video)", timeout=15000)
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


def test_a_reward_is_bought_with_gold_in_the_shop(browser):
    item = _post("/api/work_hub/items/create", {"item": {"title": f"Gold {uuid.uuid4().hex[:4]}", "priority": "high"}, "expected_revision": _rev()})["item"]["id"]
    _post("/api/work_hub/items/update", {"item_id": item, "item": {"status": "done"}, "expected_revision": _rev()})
    page = _dashboard(browser, "shop")
    page.wait_for_selector("[data-form-open=reward]", timeout=15000)
    page.evaluate("() => document.querySelector('[data-form-open=reward]').click()")
    page.fill("form[data-form=reward] input[name=name]", "Coffee break")
    page.fill("form[data-form=reward] input[name=cost]", "5")
    page.evaluate("() => document.querySelector('form[data-form=reward] [type=submit]').click()")
    buy = page.wait_for_selector(".shop-item:has-text('Coffee break') [data-reward-redeem]:not([disabled])", timeout=10000)
    before = page.evaluate("() => parseInt(document.querySelector('.shop-purse b').textContent.replace(/\\D/g, ''), 10)")
    buy.evaluate("el => el.click()")
    page.wait_for_function(f"() => parseInt(document.querySelector('.shop-purse b')?.textContent.replace(/\\D/g, ''), 10) === {before} - 5", polling=100, timeout=10000)
    assert page.locator(".shop-ledger-row:has-text('Coffee break') .shop-ledger-gold.is-spend").count() == 1
    nav = page.evaluate("() => [...document.querySelectorAll('#dashboardSidebar [data-dash-tab]')].map(b => b.dataset.dashTab)")
    assert nav[:2] == ["character", "shop"]  # the Shop sits under Character
    assert page.locator("[data-dash-card=flow] .sf-col").count() == 14
    page.evaluate("() => window.HermesDashboard.select('character')")
    page.wait_for_selector(".rpg-stage", timeout=10000)
    assert page.locator(".rpg-purse").count() == 0  # the treasury moved to the Shop



def test_libraries_dev_effects_mount_on_the_character_page(browser):
    page = _dashboard(browser, "character")
    page.wait_for_selector(".rpg-stage :is(.px-hero,.rpg-hero-video)", timeout=15000)
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
    assert pads and all(p == [26, 28, 28] for p in pads)  # ~16px clear of the frame bars on every side


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
    # Achievements shows every badge at full height and runs down to
    # Chronicle's bottom edge; Chronicle fills what is left and scrolls inside.
    # (Measured once the page's rise-in has finished.)
    page.wait_for_function("() => !document.getAnimations().some(a => a.animationName === 'dash-rise' && a.playState === 'running')", polling=50, timeout=5000)
    ends = page.evaluate("""() => {
        const ach = document.querySelector('.rpg-panel:has(.rpg-achs)').getBoundingClientRect();
        const chron = document.querySelector('.rpg-panel.is-chronicle');
        const body = chron.querySelector(':scope > .dash-card-body');
        return {gap: Math.abs(ach.bottom - chron.getBoundingClientRect().bottom), scroll: getComputedStyle(body).overflowY};
    }""")
    assert ends["gap"] <= 1 and ends["scroll"] == "auto", ends
    assert page.evaluate("() => { const b = document.querySelector('.rpg-achs').closest('.dash-card-body'); return b.scrollHeight <= b.clientHeight + 1; }")


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
        # The icon sits as far from the card's left edge as from the text, and
        # the tallest icon is as tall as the label plus the value.
        stats = page.evaluate("""() => [...document.querySelectorAll('.dash-stat')].map(s => {
            const box = s.querySelector('.dash-stat-icon'), img = box && box.querySelector('img'), copy = s.querySelector('.dash-stat-copy');
            if (!box || !copy) return null;
            const card = s.getBoundingClientRect(), a = box.getBoundingClientRect(), b = copy.getBoundingClientRect();
            const border = parseFloat(getComputedStyle(s).borderLeftWidth);
            const text = copy.querySelector('b').getBoundingClientRect().bottom - copy.querySelector('small').getBoundingClientRect().top;
            const label = copy.querySelector('small'), oneLine = label.getBoundingClientRect().height < parseFloat(getComputedStyle(label).fontSize) * 1.6;
            return {left: a.left - card.left - border, gap: b.left - a.right, icon: img.getBoundingClientRect().height, text, oneLine};
        })""")
        assert len(stats) == 4 and all(st is not None and abs(st["left"] - st["gap"]) <= 1 for st in stats)
        assert all(st["icon"] <= st["text"] + 1 for st in stats)
        one_line = [st for st in stats if st["oneLine"]]
        assert one_line and abs(max(st["icon"] for st in one_line) - one_line[0]["text"]) <= 2, stats
    page.evaluate("() => window.HermesDashboard.select('personal')")
    page.wait_for_function("() => !window.HermesDashboard._state.loading.personal", polling=100, timeout=10000)
    assert page.evaluate("() => [...document.querySelectorAll('.dash-stat small')].some(e => e.textContent.trim() === 'Personal quests')")
    # The entry opens from the header button at the top of the card; measure
    # once its slide-in has settled.
    page.click(".dash-card.is-learning-log [data-form-open='learning']")
    page.wait_for_function("() => { const f = document.querySelector('.dash-card.is-learning-log form.is-learning'); return f && f.getAnimations().length === 0; }", polling=50, timeout=5000)
    entry = page.evaluate("""() => { const card = document.querySelector('.dash-card.is-learning-log'), form = card.querySelector('form.is-learning'),
        button = form.querySelector('button[type=submit]'), selects = [...form.querySelectorAll('.themed-select-trigger')];
        return {first: card.querySelector('.dash-card-body').firstElementChild === form, heights: [button, ...selects].map(e => Math.round(e.getBoundingClientRect().height))}; }""")
    assert entry["first"] and len(set(entry["heights"])) == 1, entry
    icons = page.evaluate("""() => [...document.querySelectorAll('.dash-card')].filter(c => c.querySelector(':scope > .dash-card-head .dash-card-icon')).map(c => {
        const r = c.getBoundingClientRect(), b = parseFloat(getComputedStyle(c).borderTopWidth), i = c.querySelector('.dash-card-icon').getBoundingClientRect();
        return [Math.round(i.top - r.top - b), Math.round(i.left - r.left - b)]; })""")
    assert icons and all(left - top == 2 for top, left in icons)  # equal room from the frame bars (side bars are 2.4px deeper)


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


def test_a_summary_tile_scrolls_to_its_card_and_makes_it_pulse(browser):
    page = _open(browser, viewport={"width": 1280, "height": 700})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('personal'); }")
    page.wait_for_selector(".dash-stat.is-link", timeout=15000)
    page.wait_for_function("() => !window.HermesDashboard._state.loading.personal", polling=100, timeout=10000)
    targets = page.evaluate("() => [...document.querySelectorAll('.dash-stat.is-link')].map(s => [s.dataset.dashFocus, !!document.querySelector(`[data-dash-card=\"${s.dataset.dashFocus}\"]`)])")
    assert len(targets) == 4 and all(found for _, found in targets)  # every tile points at a card on the page
    page.click(".dash-stat[data-dash-focus='habits']")
    assert page.evaluate("() => document.querySelector('[data-dash-card=habits]').classList.contains('is-pulsing')")
    assert not page.evaluate("() => document.querySelector('[data-dash-card=quests]').classList.contains('is-pulsing')")
    # It bobs (no glow).
    pulse = page.evaluate("() => { const s = getComputedStyle(document.querySelector('[data-dash-card=habits]')); return [s.animationName, s.boxShadow]; }")
    assert pulse == ["dash-card-bob", "none"]
    page.wait_for_function("() => !document.querySelector('[data-dash-card=habits]').classList.contains('is-pulsing')", polling=100, timeout=4000)
    for tab in ("career", "business"):
        page.evaluate(f"() => window.HermesDashboard.select('{tab}')")
        page.wait_for_function(f"() => !window.HermesDashboard._state.loading.{tab}", polling=100, timeout=10000)
        missing = page.evaluate("() => [...document.querySelectorAll('.dash-stat.is-link')].filter(s => !document.querySelector(`[data-dash-card=\"${s.dataset.dashFocus}\"]`)).length")
        assert missing == 0


def test_career_pairs_quests_with_skills_and_funnel_with_this_week(browser):
    name = f"Skill {uuid.uuid4().hex[:6]}"
    added = _post("/api/dashboard/skills/add", {"name": name, "kind": "bootcamp"})["skill"]
    page = _open(browser, viewport={"width": 1440, "height": 900})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('career'); }")
    page.wait_for_selector("[data-dash-card=skills]", timeout=15000)
    page.wait_for_function("() => !window.HermesDashboard._state.loading.career", polling=100, timeout=10000)
    # The entry opens from the header's Skill button.
    assert page.locator("[data-dash-card=skills] form[data-form=skill]").count() == 0
    page.click("[data-dash-card=skills] [data-form-open='skill']")
    page.wait_for_selector("[data-dash-card=skills] form[data-form=skill]", timeout=3000)
    layout = page.evaluate("""() => { const r = (k) => document.querySelector(`[data-dash-card="${k}"]`).getBoundingClientRect();
        const q = document.querySelector('.dash-card.is-quests').getBoundingClientRect(), s = r('skills'), f = r('funnel'), w = r('this-week');
        const form = document.querySelector('[data-dash-card=skills] form[data-form=skill]');
        return {skillsRightOfQuests: Math.abs(q.top - s.top) <= 1 && s.left > q.right, weekRightOfFunnel: Math.abs(f.top - w.top) <= 1 && w.left > f.right,
                funnelWider: f.width > w.width, selects: form.querySelectorAll('select').length, button: form.querySelector('button[type=submit]').textContent.trim(),
                placeholder: form.querySelector('input').placeholder, icon: document.querySelector('[data-dash-card=skills] .dash-pix-icon').dataset.dashPix}; }""")
    assert layout["skillsRightOfQuests"] and layout["weekRightOfFunnel"] and layout["funnelWider"]
    assert (layout["selects"], layout["button"], layout["placeholder"], layout["icon"]) == (1, "Add Skill", "What skills did you learn?", "gambling")
    assert page.locator(f"[data-dash-card=skills] .dash-row:has-text('{name}')").count() == 1
    _post("/api/dashboard/skills/remove", {"skill_id": added["id"]})


def test_resume_studio_lists_skills_gained_and_tailoring_shows_what_it_added(browser):
    page = _open(browser, viewport={"width": 1280, "height": 900})
    html = page.evaluate("""() => window.JobOSRender.skillsGainedView({resume: {text: 'x'}, skillsGained: [
        {name: 'Docker', kind: 'course'}, {name: 'AWS Cloud Practitioner', kind: 'certification'}]})""")
    assert "Skills gained" in html and "Docker" in html and "Certification" in html and 'data-job-os-action="skills-manage"' in html
    assert page.evaluate("() => window.JobOSRender.skillsGainedView({resume: null, skillsGained: []})") == ""
    assert "No skills yet" in page.evaluate("() => window.JobOSRender.skillsGainedView({resume: {text: 'x'}, skillsGained: []})")


def test_road_title_settings_realms_and_a_solid_picker(browser):
    page = _open(browser, viewport={"width": 1280, "height": 900})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('business'); }")
    page.wait_for_selector("[data-dash-card=road]", timeout=15000)
    road = page.evaluate("() => document.querySelector('[data-dash-card=road]').textContent")
    assert "Road to $10k" in road and "MRR" not in road
    page.evaluate("() => window.HermesDashboard.select('settings')")
    page.wait_for_selector("[data-dash-card=realms]", timeout=15000)
    page.evaluate("() => window.HermesDashboard.select('character')")
    page.wait_for_selector(".rpg-stage", timeout=15000)
    assert page.evaluate("() => !document.querySelector('#dashboardRoot').textContent.includes('Project realms')")
    tab = page.evaluate("() => { const on = getComputedStyle(document.querySelector('.dash-char-btn.on')).backgroundImage; return on; }")
    assert "linear-gradient" in tab  # the gold toggle, like Personal / Career / Business
    page.evaluate("() => window.HermesDashboard.openQuestPicker()")
    page.wait_for_selector(".dash-picker-overlay.is-open .dash-picker", timeout=10000)
    bg = page.evaluate("() => getComputedStyle(document.querySelector('.dash-picker')).backgroundColor")
    assert bg not in ("rgba(0, 0, 0, 0)", "transparent") and not bg.endswith(", 0)")


def test_the_quest_picker_filters_by_folder_and_adds_to_the_tab_it_was_opened_on(browser):
    title = f"Picker item {uuid.uuid4().hex[:6]}"
    item = _post("/api/work_hub/items/create", {"item": {"title": title, "status": "todo"}, "expected_revision": _rev()})["item"]
    page = _open(browser, viewport={"width": 1280, "height": 900})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('career'); }")
    page.wait_for_function("() => !window.HermesDashboard._state.loading.career", polling=100, timeout=10000)
    page.click(".dash-card.is-quests [data-dash-add-quest]")
    page.wait_for_selector(f".dash-picker-row:has-text('{title}')", timeout=10000)
    assert "Career" in page.inner_text(".dash-picker header h3")
    options = page.evaluate("() => [...document.querySelectorAll('[data-picker-filter] option')].map(o => o.value)")
    assert options[:2] == ["", "__general"]
    tools = page.evaluate("""() => { const s = document.querySelector('.dash-picker-search').getBoundingClientRect(), t = document.querySelector('.dash-picker-tools .themed-select-trigger').getBoundingClientRect();
        const f = [...document.querySelectorAll('.dash-picker footer .dash-btn')].map(b => Math.round(b.getBoundingClientRect().height));
        return {search: Math.round(s.height), filter: Math.round(t.height), footer: f}; }""")
    assert tools["search"] == tools["filter"] >= 30 and len(set(tools["footer"])) == 1
    page.evaluate("() => { const f = document.querySelector('[data-picker-filter]'); f.value = '__general'; f.dispatchEvent(new Event('change')); }")
    assert page.locator(f".dash-picker-row:has-text('{title}')").count() == 1  # a General item
    page.click(f".dash-picker-row:has-text('{title}') input")
    page.click("[data-picker-add]")
    page.wait_for_selector(f".dash-card.is-quests .dash-quest-row:has-text('{title}')", timeout=10000)
    _post("/api/dashboard/quests/remove", {"item_id": item["id"]})


def test_sale_dates_use_the_themed_calendar_and_forms_line_up(browser):
    page = _open(browser, viewport={"width": 1280, "height": 900})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('business'); }")
    page.wait_for_selector("[data-form-open=sale]", timeout=15000)
    page.click("[data-form-open=sale]")
    assert page.locator("[data-form=sale] input[type=date]").count() == 0
    page.click("[data-date-pick]")
    page.wait_for_selector(".dash-cal.is-open")
    assert page.evaluate("() => document.querySelectorAll('.dash-cal-days button:not([disabled])').length") >= 1
    page.click(".dash-cal-days button:not([disabled]) >> nth=0")
    value = page.evaluate("() => document.querySelector('[data-form=sale] input[name=date]').value")
    assert len(value) == 10 and value.endswith("-01")
    assert page.locator(".dash-cal").count() == 0
    heights = page.evaluate("() => [...document.querySelectorAll('[data-form=sale] :is(input[type=number],input[type=text],.dash-date-btn,.dash-btn)')].map(e => Math.round(e.getBoundingClientRect().height))")
    assert len(set(heights)) == 1
    page.click("[data-form-open=goal]")
    goal = page.evaluate("() => [...document.querySelectorAll('[data-form=goal] :is(input,.themed-select-trigger,.dash-btn)')].filter(e => e.offsetParent).map(e => Math.round(e.getBoundingClientRect().height))")
    assert len(set(goal)) == 1
    assert page.locator("[data-form=goal] select[name=project_id]").count() == 1


def test_habit_form_hides_weekly_count_for_daily_and_lists_scroll_with_an_arrow(browser):
    for i in range(10):
        _post("/api/dashboard/learning/add", {"title": f"Arrow fixture {uuid.uuid4().hex[:4]} {i}", "kind": "book", "area": "career"})
    page = _open(browser, viewport={"width": 1280, "height": 900})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('personal'); }")
    page.wait_for_selector(".dash-card.is-learning-log", timeout=15000)
    page.wait_for_function("() => !window.HermesDashboard._state.loading.personal", polling=100, timeout=10000)
    assert page.locator(".dash-card.is-learning-log .dash-row small:has-text('Book ·')").count() >= 1  # capitalised kind
    page.wait_for_function("() => document.querySelector('.dash-card.is-learning-log .dash-more.is-on')", polling=100, timeout=5000)
    page.evaluate("() => { const l = document.querySelector('.dash-card.is-learning-log .dash-learning-entries'); l.scrollTop = l.scrollHeight; }")
    page.wait_for_function("() => !document.querySelector('.dash-card.is-learning-log .dash-more.is-on')", polling=100, timeout=5000)
    page.click("[data-form-open=habit]")
    page.wait_for_selector("[data-form=habit]")
    visible = lambda: page.evaluate("() => { const w = document.querySelector('[data-weekly-target]').closest('.themed-select-wrap') || document.querySelector('[data-weekly-target]'); return getComputedStyle(w).display !== 'none'; }")
    assert visible() is False
    page.evaluate("() => { const s = document.querySelector('[data-form=habit] select[name=cadence]'); s.value = 'weekly'; s.dispatchEvent(new Event('change')); }")
    assert visible() is True
    assert page.evaluate("() => getComputedStyle(document.querySelector('.dash')).userSelect") == "none"


def test_card_dividers_are_square_dashes_and_dropdowns_match_their_button(browser):
    page = _open(browser, viewport={"width": 1280, "height": 900})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('personal'); }")
    page.wait_for_selector(".dash-card.is-learning-log [data-form-open='learning']", timeout=15000)
    page.click(".dash-card.is-learning-log [data-form-open='learning']")
    page.wait_for_selector(".dash-card.is-learning-log .themed-select-trigger", timeout=5000)
    rules = page.evaluate("() => [...document.querySelectorAll('.dash :is(.dash-card-head,.rpg-panel-head)')].map(h => [getComputedStyle(h).borderBottomStyle, getComputedStyle(h).backgroundImage.startsWith('repeating-linear-gradient')])")
    assert rules and all(style == "none" and gradient for style, gradient in rules)
    radii = page.evaluate("() => [...document.querySelectorAll('.dash :is(.dash-row,.dash-quest-row,.dash-habit)')].map(r => getComputedStyle(r).borderTopLeftRadius)")
    assert radii and set(radii) == {"0px"}  # rounded rows bent the lines between them
    # Open and measure in one step, so a background repaint can't swap the button out.
    widths = page.evaluate("""() => { const t = document.querySelectorAll('.dash-card.is-learning-log .themed-select-trigger')[1];  // Career / Personal / Business
        t.click(); const p = document.querySelector('.themed-select-popup'); return p ? [p.getBoundingClientRect().width, t.getBoundingClientRect().width] : null; }""")
    assert widths and abs(widths[0] - widths[1]) <= 1  # the options fit: as wide as the button
    page.mouse.click(5, 5)
    grown = page.evaluate("""() => { const s = document.createElement('select'); s.innerHTML = '<option>A</option><option>' + 'A much longer option label '.repeat(3) + '</option>';
        const host = document.createElement('div'); host.style.cssText = 'position:fixed;left:20px;top:20px;width:80px'; host.appendChild(s); document.body.appendChild(host);
        window.enhanceThemedSelect(s); const t = host.querySelector('.themed-select-trigger'); t.click();
        const p = document.querySelector('.themed-select-popup'), opt = p.querySelectorAll('.themed-select-option')[1];
        return {popup: p.getBoundingClientRect().width, trigger: t.getBoundingClientRect().width, cut: opt.scrollWidth > opt.clientWidth + 1}; }""")
    assert grown["popup"] > grown["trigger"] and not grown["cut"]  # long text widens the list instead of being cut


def test_quest_picker_search_and_filter_wait_until_the_panel_settles(browser):
    page = _open(browser, viewport={"width": 1280, "height": 900})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('personal'); }")
    page.wait_for_function("() => !window.HermesDashboard._state.loading.personal", polling=100, timeout=10000)
    early = page.evaluate("""() => { document.querySelector('.dash-card.is-quests [data-dash-add-quest]').click();
        const t = document.querySelector('.dash-picker-tools .themed-select-trigger'), s = document.querySelector('[data-picker-search]');
        return {trigger: t.disabled, search: s.disabled}; }""")
    assert early == {"trigger": True, "search": True}  # nothing to open while the panel still moves
    page.wait_for_function("() => !document.querySelector('[data-picker-search]').disabled", polling=50, timeout=10000)
    assert not page.evaluate("() => document.querySelector('.dash-picker').classList.contains('is-resizing')")
    page.click(".dash-picker-tools .themed-select-trigger")
    page.wait_for_selector(".themed-select-popup")
    gap = page.evaluate("() => document.querySelector('.themed-select-popup').getBoundingClientRect().top - document.querySelector('.dash-picker-tools .themed-select-trigger').getBoundingClientRect().bottom")
    assert 0 <= gap <= 8  # the list sits under its button


def test_character_page_frame_evolution_party_achievements_and_level_up(browser):
    page = _open(browser, viewport={"width": 1440, "height": 1000})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('character'); }")
    page.wait_for_selector(".rpg-evo", timeout=15000)
    page.wait_for_function("() => !window.HermesDashboard._state.loading.character", polling=100, timeout=10000)
    page.wait_for_timeout(300)
    hero = page.evaluate("""() => { const a = document.querySelector('.rpg-stage').getBoundingClientRect(), b = document.querySelector('.rpg-sheet').getBoundingClientRect();
        return {top: Math.round(a.top - b.top), bottom: Math.round(a.bottom - b.bottom)}; }""")
    assert hero == {"top": 0, "bottom": 0}  # the frame is exactly as tall as the level card
    titles = page.evaluate("() => [...document.querySelectorAll('.rpg-panel-head h3')].map(h => h.textContent)")
    assert not any(t.startswith("Quest log") or t == "Evolution" for t in titles)  # quest log gone, evolution moved into the level card
    # Evolution: one form at a time, later forms chained.
    data = page.evaluate("() => window.HermesDashboard._state.data.character")
    for _ in range(len(data["tiers"])):
        page.evaluate("() => { const b = document.querySelector('[data-evo-step=\"1\"]'); if (!b.disabled) b.click(); }")
    last = page.evaluate("() => ({locked: document.querySelector('.rpg-evo-art').classList.contains('is-locked'), name: document.querySelector('.rpg-evo-name').textContent, next: document.querySelector('[data-evo-step=\"1\"]').disabled})")
    assert last["name"] == data["tiers"][-1]["name"] and last["next"] is True
    assert last["locked"] == (data["level"] < data["tiers"][-1]["level"])
    assert page.evaluate("() => document.querySelectorAll('.rpg-evo-art').length") == 1
    # Party two to a row; achievements one height.
    assert page.evaluate("() => getComputedStyle(document.querySelector('.rpg-party')).gridTemplateColumns.split(' ').length") == 2
    heights = page.evaluate("() => [...new Set([...document.querySelectorAll('.rpg-ach')].map(a => Math.round(a.getBoundingClientRect().height)))]")
    assert len(heights) == 1
    assert page.evaluate("() => [...document.querySelectorAll('.rpg-ach')].every(a => a.scrollHeight <= a.clientHeight + 1)")  # text fits
    assert page.evaluate("() => getComputedStyle(document.querySelector('.rpg-panel-icon.is-pixel')).backgroundColor") in ("rgba(0, 0, 0, 0)", "transparent")
    # Level up: a themed card that closes on Continue.
    page.evaluate("() => window.HermesDashboard._celebrate(window.HermesDashboard._state.data.character, {force: true})")
    page.wait_for_selector(".rpg-levelup.is-open .rpg-levelup-card")
    assert str(data["level"]) in page.inner_text(".rpg-levelup-levels")
    page.click("[data-levelup-close]")
    page.wait_for_function("() => !document.querySelector('.rpg-levelup')", polling=50, timeout=3000)


def test_character_frame_art_level_card_columns_and_achievement_badges(browser):
    page = _open(browser, viewport={"width": 1440, "height": 1000})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('character'); }")
    page.wait_for_selector(".rpg-ach", timeout=15000)
    frame = page.evaluate("() => { const s = document.querySelector('.rpg-stage'), r = s.getBoundingClientRect(); return [getComputedStyle(s, '::after').borderImageSource, r.width / r.height]; }")
    # The blade frame as a nine-slice: 3:4 where the page is wide; narrower
    # here, where the level card needs the width.
    assert "frame-gold.png" in frame[0] and 0.55 <= frame[1] <= 0.8
    cols = page.evaluate("""() => { const e = document.querySelector('.rpg-evo').getBoundingClientRect(), b = [...document.querySelectorAll('.rpg-badges > div')].pop().getBoundingClientRect();
        return [Math.round(e.left - b.left), Math.round(e.width - b.width)]; }""")
    assert cols == [0, 0]  # evolution lines up with the badge below it
    art = page.evaluate("() => [...document.querySelectorAll('.rpg-ach.has-art img')].map(i => [i.naturalWidth > 0, i.getAttribute('src')])")
    data = page.evaluate("() => window.HermesDashboard._state.data.character.achievements")
    assert len(art) == sum(1 for a in data if a["art"]) >= 21 and all(ok for ok, _ in art)
    # Titles are one size and one height across a row; only descriptions shrink.
    assert page.evaluate("() => new Set([...document.querySelectorAll('.rpg-ach strong')].map(s => getComputedStyle(s).fontSize)).size") == 1
    offsets = page.evaluate("() => new Set([...document.querySelectorAll('.rpg-ach')].map(a => Math.round(a.querySelector('strong').getBoundingClientRect().top - a.getBoundingClientRect().top))).size")
    assert offsets == 1
    earned = page.evaluate("() => [...document.querySelectorAll('.rpg-ach:not(.is-locked)')].every(a => a.querySelector('.rpg-ach-shine'))")
    assert earned and page.evaluate("() => document.querySelectorAll('.rpg-ach.is-locked .rpg-ach-shine').length") == 0
    # The glint is masked to the badge art: the mask must point at the real file
    # (a relative url() in a custom property resolves against the stylesheet).
    masks = page.evaluate("() => [...document.querySelectorAll('.rpg-ach.has-art:not(.is-locked) .rpg-ach-shine')].map(s => getComputedStyle(s).webkitMaskImage)")
    assert masks and all("/static/dashboard/achievements/" in m and "/static/static/" not in m for m in masks)
    ok = page.evaluate("async () => { const m = getComputedStyle(document.querySelector('.rpg-ach.has-art:not(.is-locked) .rpg-ach-shine')).webkitMaskImage.match(/url\\(\"([^\"]+)\"\\)/)[1]; return (await fetch(m)).ok; }")
    assert ok
    page.hover(".rpg-ach.has-art:not(.is-locked)")
    assert page.evaluate("() => getComputedStyle(document.querySelector('.rpg-ach.has-art:not(.is-locked) img')).transform") == "none"  # no zoom, so no blur


def test_character_frame_only_chronicle_filters_stick_and_lists_keep_their_scroll(browser):
    for i in range(20):
        _post("/api/dashboard/learning/add", {"title": f"Scroll fixture {uuid.uuid4().hex[:4]} {i}", "kind": "book", "area": "career"})
    page = _open(browser, viewport={"width": 1440, "height": 900})
    page.evaluate("async () => { document.documentElement.dataset.skin = 'geist-contrast'; await switchPanel('dashboard'); window.HermesDashboard.select('character'); }")
    page.wait_for_selector(".rpg-panel.is-chronicle .rpg-log-row", timeout=15000)
    page.wait_for_function("() => !window.HermesDashboard._state.loading.character", polling=100, timeout=10000)
    stage = page.evaluate("() => { const c = getComputedStyle(document.querySelector('.rpg-stage')); return [c.borderTopWidth, c.borderImageSource]; }")
    assert stage == ["0px", "none"]  # only the gold frame art, in this skin too
    cols = page.evaluate("() => [...document.querySelectorAll('.rpg-col')].map(c => [...c.querySelectorAll(':scope > .rpg-panel h3')].map(h => h.textContent.split(' ')[0]))")
    assert cols[1][-1] == "Chronicle" and cols[1].index("Realms") == len(cols[1]) - 2
    assert page.evaluate("() => document.querySelectorAll('.rpg-ach .dash-new').length") == 0
    body = ".rpg-panel.is-chronicle > .dash-card-body"
    page.wait_for_function("() => !document.getAnimations().some(a => a.animationName === 'dash-rise' && a.playState === 'running')", polling=50, timeout=5000)
    page.evaluate(f"() => {{ document.querySelector('{body}').scrollTop = 240; }}")
    top = page.evaluate(f"() => document.querySelector('{body}').getBoundingClientRect().top")
    chips = page.evaluate("() => document.querySelector('.rpg-log-filters').getBoundingClientRect().top")
    assert abs(chips - top) <= 1  # the filters stay at the top of the list while it scrolls
    page.evaluate("() => window.HermesDashboard._state.data.character = {...window.HermesDashboard._state.data.character, streak: 999}")
    page.evaluate("() => window.HermesDashboard.refresh()")
    page.wait_for_function("() => !window.HermesDashboard._state.loading.character", polling=100, timeout=10000)
    page.wait_for_timeout(200)
    assert page.evaluate(f"() => document.querySelector('{body}').scrollTop") == 240  # a refresh keeps the list where it was
    page.evaluate("() => { document.getElementById('mainDashboard').scrollTop = 400; }")
    page.evaluate("() => document.querySelector('[data-log-filter=career]').click()")
    page.wait_for_function("() => document.querySelector('[data-log-filter=career]').classList.contains('on')", polling=100, timeout=10000)
    page.wait_for_timeout(200)
    assert page.evaluate("() => document.getElementById('mainDashboard').scrollTop") == 400  # the page stays put


def test_earned_achievements_keep_their_description(browser):
    page = _open(browser, viewport={"width": 1440, "height": 900})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('character'); }")
    page.wait_for_selector(".rpg-ach", timeout=15000)
    data = page.evaluate("() => window.HermesDashboard._state.data.character.achievements")
    shown = page.evaluate("() => [...document.querySelectorAll('.rpg-ach small')].map(s => s.textContent)")
    assert shown == [a["description"] for a in data]  # earned or not, the line under the title is what it is for
    assert {a["key"]: a["description"] for a in data}["habit_week"] == "7-day habits streak"


def test_dashboard_cards_use_the_chamfered_pixel_frame(browser):
    page = _open(browser, viewport={"width": 1440, "height": 900})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('personal'); }")
    page.wait_for_selector(".dash-card", timeout=15000)
    for tab in ("personal", "character"):
        page.evaluate(f"() => window.HermesDashboard.select('{tab}')")
        page.wait_for_function(f"() => !window.HermesDashboard._state.loading.{tab}", polling=100, timeout=10000)
        # Large panels draw the frame art and carry the centre gems; small boxes a plain gold chamfer.
        panels = page.evaluate("""() => [...document.querySelectorAll('.dash :is(.dash-card,.rpg-panel)')].map(c => { const s = getComputedStyle(c);
            return [s.borderImageSource.includes('card-frame.png'), s.borderTopLeftRadius, getComputedStyle(c, '::after').backgroundImage.includes('card-gem-top.png')]; })""")
        assert panels and all(art and radius == "0px" and gem for art, radius, gem in panels)
        # Summary tiles wear the frame art too, smaller; the level card's own
        # boxes a thin dark-gold pixel frame with stepped corners.
        tiles = page.evaluate("() => [...document.querySelectorAll('.dash .dash-stat')].map(e => getComputedStyle(e).borderImageSource.includes('card-frame.png'))")
        assert all(tiles)
        small = page.evaluate("() => [...document.querySelectorAll('.dash :is(.rpg-stat,.rpg-badges > div,.rpg-evo)')].map(e => { const s = getComputedStyle(e); return s.borderImageSource.includes('svg') && s.clipPath.startsWith('polygon') && s.borderImageWidth === '4px'; })")
        assert all(small)
    # The character frame keeps its own art, without the card frame.
    assert page.evaluate("() => getComputedStyle(document.querySelector('.rpg-stage')).borderImageSource") == "none"


def test_level_card_has_as_much_space_below_the_bars_as_above(browser):
    page = _open(browser, viewport={"width": 1440, "height": 900})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('character'); }")
    page.wait_for_selector(".rpg-stats", timeout=15000)
    gaps = page.evaluate("() => { const R = s => document.querySelector(s).getBoundingClientRect(); return [R('.rpg-stats').top - R('.rpg-xpbar').bottom, R('.rpg-badges').top - R('.rpg-stats').bottom]; }")
    assert abs(gaps[0] - gaps[1]) <= 0.5


def test_character_videos_are_served_with_byte_ranges():
    req = urllib.request.Request(BASE + "/static/dashboard/characters/ascended.mp4", headers={"Range": "bytes=0-99"})
    with urllib.request.urlopen(req, timeout=10) as res:
        assert res.status == 206 and res.headers["Content-Type"] == "video/mp4"
        assert res.headers["Content-Range"].startswith("bytes 0-99/") and len(res.read()) == 100
    from api import dashboard_game
    assert {"ascended", "celestial"} <= dashboard_game._character_video() and {"ascended", "celestial"} <= dashboard_game._character_sprite()


def test_character_video_plays_only_while_it_can_be_seen(browser):
    page = _open(browser, viewport={"width": 1440, "height": 700})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('character'); }")
    page.wait_for_selector(".rpg-stage video.rpg-hero-video", timeout=15000)
    video = ".rpg-stage video.rpg-hero-video"
    assert page.evaluate(f"() => !document.querySelector('{video}').autoplay")  # nothing starts on its own
    page.wait_for_function(f"() => !document.querySelector('{video}').paused", polling=100, timeout=10000)
    page.evaluate("() => { document.getElementById('mainDashboard').scrollTop = 100000; }")
    page.wait_for_function(f"() => document.querySelector('{video}').paused", polling=100, timeout=5000)  # scrolled away
    page.evaluate("() => { document.getElementById('mainDashboard').scrollTop = 0; }")
    page.wait_for_function(f"() => !document.querySelector('{video}').paused", polling=100, timeout=5000)  # back in view
    page.evaluate("async () => { window.__v = document.querySelector('.rpg-stage video.rpg-hero-video'); await switchPanel('chat'); }")
    page.wait_for_function("() => window.__v.paused", polling=100, timeout=5000)  # left the Dashboard


def test_evolution_opens_on_the_next_form_and_a_locked_form_is_a_still(browser):
    page = _open(browser, viewport={"width": 1440, "height": 1000})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('character'); }")
    page.wait_for_selector(".rpg-evo-art", timeout=15000)
    page.wait_for_function("() => !window.HermesDashboard._state.loading.character", polling=100, timeout=10000)
    data = page.evaluate("() => window.HermesDashboard._state.data.character")
    start = min(len(data["tiers"]) - 1, data["tier"])  # the form after the current one
    shown = page.evaluate("() => ({name: document.querySelector('.rpg-evo-name').textContent, src: (document.querySelector('.rpg-hero-sprite') || {}).src || ''})")
    tier = data["tiers"][start]
    assert shown["name"] == tier["name"]
    if tier["sprite"]:
        locked = data["level"] < tier["level"]
        assert shown["src"].endswith(f"/{tier['name'].lower()}{'-still' if locked else ''}.webp")  # nothing animates for a form not reached
        glow = page.evaluate("() => getComputedStyle(document.querySelector('.rpg-hero-sprite')).filter")
        assert "drop-shadow" not in glow


def test_chronicle_filter_answers_at_once_without_rebuilding_the_page(browser):
    _post("/api/dashboard/learning/add", {"title": f"Personal fixture {uuid.uuid4().hex[:4]}", "kind": "book", "area": "personal"})
    _post("/api/dashboard/learning/add", {"title": f"Career fixture {uuid.uuid4().hex[:4]}", "kind": "book", "area": "career"})
    page = _open(browser, viewport={"width": 1440, "height": 900})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('character'); }")
    page.wait_for_selector(".rpg-panel.is-chronicle .rpg-log-row", timeout=15000)
    page.wait_for_function("() => !window.HermesDashboard._state.loading.character", polling=100, timeout=10000)
    page.evaluate("() => { window.__sheet = document.querySelector('.rpg-sheet'); }")
    # In the same task as the click: the chip is on and other realms' rows are gone.
    now = page.evaluate("""() => { document.querySelector('[data-log-filter=personal]').click();
        const rows = [...document.querySelectorAll('.rpg-log-row')].filter(r => !r.hidden);
        return {on: document.querySelector('.dash-chip.on').dataset.logFilter, cats: [...new Set(rows.map(r => r.dataset.logCat))]}; }""")
    assert now["on"] == "personal" and now["cats"] in (["personal"], [])
    page.wait_for_function("() => !window.HermesDashboard._state.loading.character", polling=50, timeout=10000)
    page.wait_for_timeout(150)
    after = page.evaluate("() => ({same: window.__sheet === document.querySelector('.rpg-sheet'), cats: [...new Set([...document.querySelectorAll('.rpg-log-row')].map(r => r.dataset.logCat))]})")
    assert after["same"] and after["cats"] == ["personal"]  # only Chronicle was redrawn


def test_revenue_filter_redraws_its_card_and_is_remembered(browser):
    _post("/api/dashboard/sales/add", {"amount": "12", "product": f"Filter {uuid.uuid4().hex[:4]}"})
    page = _open(browser, viewport={"width": 1440, "height": 900})
    page.evaluate("async () => { try { localStorage.removeItem('hermes-dashboard-revenue'); } catch (_) {} await switchPanel('dashboard'); window.HermesDashboard.select('business'); }")
    page.wait_for_selector("[data-dash-card=revenue] .px-chart", timeout=15000)
    page.wait_for_function("() => !window.HermesDashboard._state.loading.business", polling=100, timeout=10000)
    counts = {}
    for key in ("today", "week", "month"):
        page.click(f"[data-rev-range={key}]")
        counts[key] = page.evaluate("() => document.querySelectorAll('[data-dash-card=revenue] .px-chart-col').length")
        assert page.evaluate(f"() => document.querySelector('[data-rev-range={key}]').classList.contains('on')")
    assert counts["today"] == 24 and counts["week"] == 7 and 28 <= counts["month"] <= 31
    page.click("[data-rev-range=week]")
    assert page.evaluate("() => localStorage.getItem('hermes-dashboard-revenue')") == "week"
    # Milestones wear pixel icons and never a "New" label.
    assert page.evaluate("() => document.querySelectorAll('.dash-badge .dash-new, .dash-badge [data-ld=metal-badge]').length") == 0
    assert page.evaluate("() => [...document.querySelectorAll('.dash-badge-icon')].every(i => i.querySelector('img[data-dash-pix]'))")


def test_buying_a_reward_bursts_coins_and_the_level_up_card_is_framed(browser):
    reward = _post("/api/dashboard/rewards/add", {"name": f"Treat {uuid.uuid4().hex[:4]}", "cost": 1})["reward"]
    page = _open(browser, viewport={"width": 1440, "height": 900})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('shop'); }")
    page.wait_for_selector(f"[data-reward-redeem='{reward['id']}']", timeout=15000)
    page.route("**/api/dashboard/rewards/redeem", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"redeemed": reward["name"]})))
    page.evaluate(f"() => document.querySelector(\"[data-reward-redeem='{reward['id']}']\").removeAttribute('disabled')")
    page.click(f"[data-reward-redeem='{reward['id']}']")
    page.wait_for_selector(".shop-burst .shop-burst-coin", timeout=3000)
    page.wait_for_function("() => !document.querySelector('.shop-burst')", polling=100, timeout=4000)  # it cleans up after itself
    _post("/api/dashboard/rewards/remove", {"reward_id": reward["id"]})
    page.evaluate("() => window.HermesDashboard.select('character')")
    page.wait_for_function("() => window.HermesDashboard._state.data.character", polling=100, timeout=15000)
    page.evaluate("() => window.HermesDashboard._celebrate(window.HermesDashboard._state.data.character, {force: true})")
    page.wait_for_selector(".rpg-levelup.is-open .rpg-levelup-card", timeout=3000)
    page.wait_for_timeout(500)
    card = page.evaluate("""() => { const c = document.querySelector('.rpg-levelup-card'), b = document.querySelector('[data-levelup-close]'), t = b.querySelector('span');
        const br = b.getBoundingClientRect(), tr = t.getBoundingClientRect(), stage = document.querySelector('.rpg-levelup-stage');
        return {frame: getComputedStyle(c).borderImageSource.includes('card-frame.png'), heroFrame: getComputedStyle(stage, '::after').borderImageSource.includes('frame-gold.png'),
                textTop: tr.top - br.top, textBottom: br.bottom - tr.bottom, rays: document.querySelector('.rpg-levelup-rays').getBoundingClientRect().width / c.getBoundingClientRect().width}; }""")
    assert card["frame"] and card["heroFrame"] and card["rays"] > 0.9
    assert abs(card["textTop"] - card["textBottom"]) <= 1  # Continue sits in the middle of its button


def test_a_repaint_keeps_the_hero_video_and_only_a_page_change_animates(browser):
    page = _open(browser, viewport={"width": 1440, "height": 900})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('character'); }")
    page.wait_for_selector(".rpg-sheet", timeout=15000)
    page.wait_for_function("() => !window.HermesDashboard._state.loading.character", polling=100, timeout=10000)
    if not page.evaluate("() => !!document.querySelector('.rpg-stage video.rpg-hero-video')"):
        pytest.skip("this form has no video")
    kept = page.evaluate("""() => { const v = document.querySelector('.rpg-hero-video'), sheet = document.querySelector('.rpg-sheet');
        window.HermesDashboard.select('character');  // same page: a forced repaint
        return {video: v === document.querySelector('.rpg-hero-video'), rebuilt: sheet !== document.querySelector('.rpg-sheet'),
                entering: document.querySelector('.dash-body').classList.contains('is-entering')}; }""")
    assert kept == {"video": True, "rebuilt": True, "entering": False}  # no reload, no fade on a repaint


def test_character_layout_fits_from_laptop_to_wide_screens(browser):
    # Wide: the frame is 3:4. At every width nothing in the level card is cut.
    for width, three_four in ((1700, True), (1440, False), (1366, False), (1280, False)):
        page = _open(browser, viewport={"width": width, "height": 900})
        page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('character'); }")
        page.wait_for_selector(".rpg-badges", timeout=15000)
        page.wait_for_function("() => !window.HermesDashboard._state.loading.character", polling=100, timeout=10000)
        page.wait_for_function("() => !document.getAnimations().some(a => a.animationName === 'dash-rise' && a.playState === 'running')", polling=50, timeout=5000)
        fit = page.evaluate("""() => { const s = document.querySelector('.rpg-stage').getBoundingClientRect();
            const cut = [...document.querySelectorAll('.rpg-badge-copy :is(b,small), .rpg-evo-head :is(span,small), .rpg-evo-status, .rpg-evo-name, .rpg-stat :is(strong,small,b), .rpg-plate-class')]
              .filter(e => { const r = e.getBoundingClientRect(), p = e.closest('.rpg-badges > div,.rpg-evo,.rpg-stat,.rpg-plate').getBoundingClientRect(); return r.right > p.right - 2 || e.scrollWidth > e.clientWidth + 1; })
              .map(e => e.textContent);
            return {ratio: s.width / s.height, cut}; }""")
        assert fit["cut"] == [], (width, fit)
        if three_four:
            assert abs(fit["ratio"] - 0.75) <= 0.04, (width, fit)
        page.context.close()


def test_new_unlocks_slide_in_once_and_old_ones_stay_quiet(browser):
    page = _open(browser, viewport={"width": 1440, "height": 900})
    page.evaluate("() => { try { localStorage.removeItem('hermes-dashboard-seen-unlocks'); } catch (_) {} }")
    items = [{"key": "a", "title": "Alpha", "description": "First", "unlocked_at": 1, "art": False, "icon": "★"},
             {"key": "b", "title": "Beta", "description": "Second", "unlocked_at": None, "art": False, "icon": "★"}]
    page.evaluate("(items) => window.HermesDashboard._announce('achievement', items)", items)
    assert page.evaluate("() => document.querySelectorAll('.dash-unlock').length") == 0  # first read: recorded, not announced
    items[1]["unlocked_at"] = 2
    page.evaluate("(items) => window.HermesDashboard._announce('achievement', items)", items)
    page.wait_for_selector(".dash-unlock.is-open", timeout=3000)
    assert "Beta" in page.inner_text(".dash-unlock") and "Achievement unlocked" in page.text_content(".dash-unlock")
    page.click(".dash-unlock")
    page.wait_for_function("() => !document.querySelector('.dash-unlock')", polling=50, timeout=3000)
    page.evaluate("(items) => window.HermesDashboard._announce('achievement', items)", items)
    page.wait_for_timeout(300)
    assert page.evaluate("() => document.querySelectorAll('.dash-unlock').length") == 0  # announced once


def test_revenue_shows_the_change_against_the_previous_period(browser):
    _post("/api/dashboard/sales/add", {"amount": "9", "product": f"Delta {uuid.uuid4().hex[:4]}"})
    page = _open(browser, viewport={"width": 1440, "height": 900})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('business'); }")
    page.wait_for_selector("[data-dash-card=revenue] .px-chart", timeout=15000)
    page.click("[data-rev-range=today]")
    delta = page.evaluate("() => { const d = document.querySelector('[data-dash-card=revenue] .px-chart-delta'); return d && [d.textContent, d.className, d.title]; }")
    assert delta and "vs yesterday" in delta[0] and "is-up" in delta[1] and "at this point" in delta[2]


def test_loading_ring_on_start_up_on_navigation_and_in_cards_still_fetching_art(browser):
    html = urllib.request.urlopen(BASE + "/", timeout=10).read().decode()
    root = html[html.index('id="dashboardRoot"'):][:600]
    assert 'dash-loader is-page' in root and "Loading" in root  # shows before any script runs
    page = _open(browser, viewport={"width": 1440, "height": 900})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('character'); }")
    page.wait_for_selector(".rpg-sheet", timeout=15000)
    # Start-up with no data yet: the whole page is the loader, with its text...
    page.evaluate("() => { const st = window.HermesDashboard._state; window.__data = st.data.character; st.started = false; st.data = {}; st.loading.character = true; window.HermesDashboard.select('character'); }")
    assert page.evaluate("() => { const l = document.querySelector('#dashboardRoot > .dash-loader.is-page'); return !!l && !!l.querySelector('.dash-loader-text') && l.querySelectorAll('.px-spin i').length === 8; }")
    # ...which fades out over the page once the data is in.
    page.evaluate("() => { const st = window.HermesDashboard._state; st.loading.character = false; st.data.character = window.__data; window.HermesDashboard.select('character'); }")
    assert page.evaluate("() => !!document.querySelector('.dash-loader.is-page.is-leaving') && !!document.querySelector('.rpg-sheet')")
    page.wait_for_function("() => !document.querySelector('.dash-loader')", polling=50, timeout=3000)
    # A page change to a page not loaded yet: only the ring, in the page body.
    page.route("**/api/dashboard/summary*", lambda r: (time.sleep(1.0), r.continue_()))
    page.evaluate("() => { delete window.HermesDashboard._state.data.shop; window.HermesDashboard.select('shop'); }")
    assert page.evaluate("() => { const l = document.querySelector('.dash-body > .dash-loader'); return !!l && !l.classList.contains('is-page') && !l.querySelector('.dash-loader-text'); }")
    page.wait_for_selector("[data-dash-card=rewards]", timeout=10000)
    page.unroute("**/api/dashboard/summary*")
    page.context.close()
    # A card whose art is still coming shows the ring in its middle until it
    # lands (a fresh page, so the badges are not cached; one of them is slow).
    page = _open(browser, viewport={"width": 1440, "height": 900})
    slow = {"done": False}

    def badge(route):
        if not slow["done"]:
            slow["done"] = True
            time.sleep(1.5)
        route.continue_()
    page.route("**/static/dashboard/achievements/*", badge)
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('character'); }")
    page.wait_for_selector(".rpg-panel:has(.rpg-achs) > .dash-card-body.is-media-loading .dash-media-wait .px-spin", timeout=5000)
    page.wait_for_function("() => !document.querySelector('.rpg-panel:has(.rpg-achs) > .dash-card-body.is-media-loading')", polling=100, timeout=10000)



def test_round_12_names_bars_milestones_and_revenue(browser):
    _post("/api/dashboard/sales/add", {"amount": "5", "product": f"R12 {uuid.uuid4().hex[:4]}"})
    page = _open(browser, viewport={"width": 1560, "height": 1000})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('character'); }")
    page.wait_for_selector(".rpg-stat", timeout=15000)
    names = page.evaluate("() => [...document.querySelectorAll('.rpg-stat strong')].map(s => s.textContent)")
    assert names == ["PER", "CAR", "BUS", "VIT", "CON"]
    colours = page.evaluate("() => new Set([...document.querySelectorAll('.rpg-stat-bar')].map(b => getComputedStyle(b).getPropertyValue('--c2').trim())).size")
    assert colours == 5  # each attribute its own colour
    realms = page.evaluate("() => new Set([...document.querySelectorAll('.dash-meters.is-realms .dash-bar')].map(b => getComputedStyle(b).getPropertyValue('--c2').trim())).size")
    assert realms == 3
    page.evaluate("() => window.HermesDashboard.select('business')")
    page.wait_for_selector(".dash-badge-art img", timeout=15000)
    ms = page.evaluate("() => [...document.querySelectorAll('.dash-badge')].map(b => [getComputedStyle(b).borderImageWidth, b.querySelector('img').getAttribute('src')])")
    assert ms and all(w == "4px" and "/milestones/" in src for w, src in ms)
    # The filter is rounded like the other buttons (its buttons sit inside, clipped).
    assert page.evaluate("() => getComputedStyle(document.querySelector('.dash-seg')).borderTopLeftRadius") == "4px"
    assert "First Sub" in page.evaluate("() => [...document.querySelectorAll('.dash-badge strong')].map(s => s.textContent).join('|')").split("|")
    # Template 04-2 bars, and no workspace panel toggle on the Dashboard.
    assert page.evaluate("() => [...document.querySelectorAll('.dash-bar')].every(b => b.getBoundingClientRect().height === 10)")
    assert page.evaluate("() => getComputedStyle(document.getElementById('btnWorkspacePanelEdgeToggle')).display") == "none"
    page.click("[data-rev-range=month]")
    labels = page.evaluate("() => [...document.querySelectorAll('[data-dash-card=revenue] .px-chart-col > small')].map(s => s.textContent).filter(Boolean)")
    assert labels[:3] == ["1", "8", "15"]  # every 7th day, no extra label squeezed in for today
