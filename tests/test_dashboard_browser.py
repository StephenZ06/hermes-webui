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
          inputSpansForm: Math.abs(input.getBoundingClientRect().width - form.clientWidth) <= 1,
          navTopEqualsSide: Math.abs((characterBox.top - navBox.top) - (characterBox.left - navBox.left)) <= 1,
        };
    }""")
    assert layout["firstIsQuests"] and layout["secondIsHabits"] and layout["questIsWider"]
    assert layout["iconTopEqualsLeft"] and layout["actionTopEqualsDividerGap"]
    assert layout["titleIsCentered"] and layout["formIsLast"]
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
          sceneBackground: getComputedStyle(stage.querySelector('.rpg-stage-scene')).backgroundImage,
        };
    }""")
    assert "background.png" not in visuals["canvasImage"]
    assert visuals["panelBackground"] == "rgb(10, 10, 10)"
    assert visuals["panelBorder"] == "rgb(63, 63, 63)"
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
    assert page.locator("[data-dash-card=flow] .shop-flow-day").count() == 14
    page.evaluate("() => window.HermesDashboard.select('character')")
    page.wait_for_selector(".rpg-stage", timeout=10000)
    assert page.locator(".rpg-purse").count() == 0  # the treasury moved to the Shop



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
    # Lists cap and scroll; Achievements shows every badge at full height.
    capped = page.evaluate("() => [...document.querySelectorAll('.rpg-col > .rpg-panel:not(:has(.rpg-achs))')].map(p => Math.round(p.getBoundingClientRect().height))")
    assert capped and max(capped) <= 560
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
    # The form slides in (dash-in); measure once it has settled.
    page.wait_for_function("() => document.querySelector('.dash-card.is-learning-log form.is-learning').getAnimations().length === 0", polling=50, timeout=5000)
    footer = page.evaluate("""() => { const card = document.querySelector('.dash-card.is-learning-log'), form = card.querySelector('form.is-learning'),
        button = form.querySelector('button'), selects = [...form.querySelectorAll('.themed-select-trigger')], r = card.getBoundingClientRect(), f = form.getBoundingClientRect();
        return {bottom: Math.round(r.bottom - f.bottom - parseFloat(getComputedStyle(card).borderBottomWidth)), heights: [button, ...selects].map(e => Math.round(e.getBoundingClientRect().height))}; }""")
    assert abs(footer["bottom"] - 16) <= 1, footer
    assert len(set(footer["heights"])) == 1
    icons = page.evaluate("""() => [...document.querySelectorAll('.dash-card')].filter(c => c.querySelector(':scope > .dash-card-head .dash-card-icon')).map(c => {
        const r = c.getBoundingClientRect(), b = parseFloat(getComputedStyle(c).borderTopWidth), i = c.querySelector('.dash-card-icon').getBoundingClientRect();
        return [Math.round(i.top - r.top - b), Math.round(i.left - r.left - b)]; })""")
    assert icons and all(left == top for top, left in icons)  # icons are cropped to their visible pixels


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
    assert page.evaluate("() => getComputedStyle(document.querySelector('[data-dash-card=habits]')).animationName") == "dash-card-pulse"
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
    page.wait_for_selector(".dash-card.is-learning-log .themed-select-trigger", timeout=15000)
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
    assert "frame-gold.png" in page.evaluate("() => getComputedStyle(document.querySelector('.rpg-stage'), '::after').backgroundImage")
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
