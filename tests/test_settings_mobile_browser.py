"""Settings on a phone: aux model rows stay inside their card, the vault buttons and
Save Settings wear the same outline style as the other settings buttons."""

import json

import pytest

from tests._pytest_port import BASE

PHONE = {"viewport": {"width": 430, "height": 932}, "is_mobile": True, "has_touch": True}


def _open_preferences(pw, vault=None):
    browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    page = browser.new_page(**PHONE)
    if vault is not None:
        page.route("**/api/notebook/vault", lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps({"vault": vault})) if route.request.method == "GET" else route.continue_())
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("async () => { document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove()); await switchPanel('settings'); switchSettingsSection('preferences'); }")
    page.wait_for_selector("#settingsNotesVault .settings-btn", timeout=15000)
    return browser, page


def test_aux_model_rows_stay_inside_their_card():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open_preferences(pw)
        try:
            page.wait_for_selector("#auxModelsContainer select", state="attached", timeout=15000)
            page.wait_for_timeout(500)
            m = page.evaluate("""() => { const c = document.getElementById('auxModelsContainer'); const card = c.closest('.settings-field').getBoundingClientRect();
              const over = [...c.querySelectorAll('.themed-select-trigger, button.aux-advanced-btn')].filter((e) => e.getBoundingClientRect().right > card.right + 0.5).length;
              return {over, scroll: c.scrollWidth - c.clientWidth, rows: c.children.length}; }""")
            assert m["rows"] >= 5 and m["over"] == 0 and m["scroll"] <= 1, m
        finally:
            browser.close()


def test_vault_buttons_are_outline_buttons_side_by_side_and_save_matches():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open_preferences(pw, vault={"enabled": True, "available": True, "path": "/tmp/vault", "name": "vault"})
        try:
            page.wait_for_selector("#settingsNotesVaultOff", timeout=10000)
            m = page.evaluate("""() => { const q = (s) => document.querySelector(s); const box = (e) => { const r = e.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height, b: r.bottom}; };
              const st = (e) => { const c = getComputedStyle(e); return {bg: c.backgroundColor, color: c.color, border: c.borderTopColor, radius: c.borderTopLeftRadius, weight: c.fontWeight, size: c.fontSize}; };
              const change = q('#settingsNotesVaultApply'), off = q('#settingsNotesVaultOff'), input = q('#settingsNotesVaultPath');
              const save = q('#settingsPanePreferences .sm-btn[onclick*=saveSettings]'), reset = q('#btnResetAuxModels');
              return {change: box(change), off: box(off), input: box(input), changeStyle: st(change), offStyle: st(off), saveStyle: st(save), resetStyle: st(reset)}; }""")
            assert abs(m["change"]["y"] - m["off"]["y"]) < 1 and m["change"]["x"] < m["off"]["x"], "Change sits beside Disconnect"
            assert m["change"]["y"] >= m["input"]["b"], "both sit below the path box"
            assert abs(m["change"]["w"] - m["off"]["w"]) < 1.5
            solid = "rgb(255, 255, 255)"
            for key in ("changeStyle", "saveStyle", "resetStyle"):
                assert m[key]["color"] != solid, (key, m[key])
            assert m["changeStyle"]["bg"] == m["saveStyle"]["bg"] == m["resetStyle"]["bg"], m
            assert m["changeStyle"]["weight"] == m["saveStyle"]["weight"], m
            assert m["offStyle"]["color"] != m["changeStyle"]["color"], "Disconnect is red"
        finally:
            browser.close()


def test_skill_pages_have_one_scroller_and_it_scrolls():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(**PHONE)
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("""async () => { document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove()); await switchPanel('skills');
              const md = Array.from({length: 60}, (_, i) => '## Section ' + i + '\\n\\nParagraph ' + i + ' of the skill text.\\n').join('\\n');
              _renderSkillDetail('demo-skill', '---\\nname: demo\\n---\\n' + md, {}); }""")
            page.wait_for_timeout(500)
            nested = page.evaluate("""() => { const b = document.getElementById('skillDetailBody'); return [...b.querySelectorAll('.preview-md')].map((e) => getComputedStyle(e).overflowY); }""")
            assert nested and set(nested) == {"visible"}, nested
            cdp = page.context.new_cdp_session(page)
            send = lambda kind, y: cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [] if kind == "touchEnd" else [{"x": 215, "y": y}]})
            send("touchStart", 700)
            for i in range(1, 12):
                send("touchMove", 700 - i * 40)
                page.wait_for_timeout(16)
            send("touchEnd", 0)
            page.wait_for_timeout(300)
            assert page.evaluate("() => document.getElementById('skillDetailBody').scrollTop") > 100
        finally:
            browser.close()
