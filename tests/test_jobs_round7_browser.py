"""Jobs side panel, job drawer buttons and the Jobs Settings page, seventh round.

The Settings page is read with an account connected (Gmail, Apify, an offline Firecrawl and two
working job sites), because that is the state the buttons, pills and footers appear in. Nudges are ink
on a real 2x display with and without the rule being asked for, as in the earlier rounds.
"""

import json
import urllib.request

import pytest
from PIL import Image, ImageChops

from tests._pytest_port import BASE
from tests.test_chat_optical_alignment_browser import _ink, _rect, _shot, browser, pytestmark, real_2x  # noqa: F401
from tests.test_job_os_page_polish_browser import _go, _open_job, seeded  # noqa: F401
from tests.test_jobs_round4_browser import jobs  # noqa: F401
from tests.test_office_notes_workhub_nudges_browser import _moved


def _connected(page):
    """Reload with Gmail and Apify connected, Firecrawl offline and two working job sites."""
    def api(route):
        data = json.load(urllib.request.urlopen(BASE + "/api/job-os/" + route.request.url.rsplit("/api/job-os/", 1)[1]))
        if route.request.url.endswith("/settings"):
            status = data["status"]
            status["gmail"].update({"address": True, "app_password": True, "address_hint": "me@gmail.com"})
            status["apify"].update({"token": True, "token_hint": "x9Qa"})
            status["firecrawl"].update({"state": "offline", "detail": "Firecrawl did not answer.", "base_url": "http://x:3002"})
        else:
            sites = [{"site": key, "name": name, "in_use": True, "state": "ok", "since": 1793435566, "failures": 0, "checked": 1793954272}
                     for key, name in (("remoteid", "remote.id"), ("indeed", "Indeed"))]
            (data.get("dashboard") or data)["site_health"] = sites
        route.fulfill(status=200, content_type="application/json", body=json.dumps(data))
    page.route("**/api/job-os/settings", api)
    page.route("**/api/job-os/dashboard", api)
    page.reload(wait_until="domcontentloaded")
    page.evaluate("""async () => { document.querySelectorAll('#onboardingOverlay,#appTourOverlay,#updateBanner').forEach(e => e.remove());
      document.documentElement.dataset.skin = 'zeus-2'; document.documentElement.classList.add('dark'); await switchPanel('jobs'); }""")
    page.wait_for_selector("#jobOsRoot .cal", timeout=30000)
    _go(page, "settings")
    page.wait_for_selector(".settings-nav-item", timeout=15000)
    page.evaluate("() => { document.getElementById('mainJobs').scrollTop = 0; }")
    page.wait_for_timeout(700)


def _section(page, name):
    page.click(f".settings-nav-item[data-section={name}]")
    page.wait_for_selector(f"#job-os-settings-{name}", timeout=10000)
    page.evaluate("() => { document.getElementById('mainJobs').scrollTop = 0; }")
    page.wait_for_timeout(500)


@pytest.fixture
def settings(jobs, seeded):
    _connected(jobs)
    return jobs


# ── Side panel ──────────────────────────────────────────────────────────────

def test_side_panel_icons_and_labels_sit_a_pixel_lower_and_the_count_half_a_pixel(jobs):
    page = jobs
    nav = "#jobOsSidebar .job-os-side-nav .side-menu-item"
    undo = f"{nav}{{padding-top:0!important}}{nav}>.job-os-side-count{{top:0!important}}"
    for view in ("dashboard", "scout", "pipeline", "resume-studio", "settings"):
        item = f"{nav}[data-job-os-view='{view}']"
        assert _moved(page, item, "icon", undo) == 1, view
        assert _moved(page, item, "text", undo, within=item) == 1, view
    count = f"{nav}[data-job-os-view='pipeline'] .job-os-side-count"
    assert _moved(page, count, "text", undo) == .5


# ── Job drawer ──────────────────────────────────────────────────────────────

def test_drawer_buttons_that_read_higher_in_round_six_read_half_a_pixel_lower_again(jobs, seeded):
    page = jobs
    _open_job(page, seeded["ready"]["title"])
    actions = ".job-drawer-actions>.job-os-btn"
    for action in ("studio-open", "board-apply", "job-analyze"):
        sel = f"{actions}[data-job-os-action='{action}']"
        if page.query_selector(sel):
            assert _moved(page, sel, "text", f"{actions}{{padding-top:1px!important}}") == .5, action
    page.eval_on_selector(".apply-step", "e => e.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(250)
    kit = ".apply-step button.job-os-btn[data-job-os-action='apply-kit']"
    if page.query_selector(kit):
        assert _moved(page, kit, "text", ".apply-step button.job-os-btn{padding-top:1px!important}") == .5
    link = ".apply-step a.job-os-btn"
    assert _moved(page, link, "text", f"{link}{{padding-top:2px!important}}") == .5
    assert _moved(page, link, "icon", f"{link}{{padding-top:2px!important}}{link}>svg{{top:0!important}}") == 0  # the icon stays


# ── Settings: list ──────────────────────────────────────────────────────────

def test_settings_list_headings_have_a_rule_centred_on_their_capitals_and_the_side_panels_margins(settings):
    page = settings
    out = page.evaluate("""() => { const r = e => e.getBoundingClientRect(); const rail = document.querySelector('.settings-rail');
      const side = document.querySelector('#jobOsSidebar .job-os-side-nav .side-menu-item');
      const item = rail.querySelector('.settings-nav-item'), head = rail.querySelector('.settings-nav-group');
      return {railPad: getComputedStyle(rail).padding, sidePad: getComputedStyle(side.parentElement).padding,
        left: r(item).left - r(rail).left, right: r(rail).right - r(item).right - 1,
        top: r(head).top - r(rail).top, size: getComputedStyle(head).fontSize, flex: getComputedStyle(head).display,
        rule: getComputedStyle(head, '::after').content, ruleH: getComputedStyle(head, '::after').height}; }""")
    side = page.evaluate("() => { const r = e => e.getBoundingClientRect(); const nav = document.querySelector('#jobOsSidebar .job-os-side-nav'); const i = nav.querySelector('.side-menu-item'); return r(i).left - r(nav).left; }")
    assert out["railPad"] == "8px" and abs(out["left"] - side) <= .5 and abs(out["right"] - side) <= .5, (out, side)  # the Jobs side panel's margin
    assert abs(out["top"] - side) <= 1, (out, side)
    assert float(out["size"][:-2]) >= 12 and out["flex"] == "flex" and out["rule"] != "none" and out["ruleH"] == "1px", out
    head = ".settings-rail .settings-nav-group"
    box = _rect(page, head)
    clip = {"x": box["x"], "y": box["y"] - 2, "width": box["width"], "height": box["height"] + 4}
    handle = page.add_style_tag(content=f"{head}>span{{-webkit-text-fill-color:transparent!important}}")
    rule = _shot(page, clip)
    handle.evaluate("e => e.remove()")
    flat = Image.new("RGB", rule.size, rule.getpixel((2, 1)))
    rows = ImageChops.difference(rule, flat).convert("L").point(lambda v: 255 if v >= 12 else 0).getbbox()
    assert rows, "no rule found"
    scale = rule.height / clip["height"]
    rule_centre = clip["y"] + (rows[1] + rows[3]) / 2 / scale
    ink = _ink(page, head, "text")
    assert abs((ink["top"] + ink["bottom"]) / 2 - rule_centre) <= .75, (ink, rule_centre)


# ── Settings: page ──────────────────────────────────────────────────────────

def test_settings_page_has_no_title_and_no_card_around_a_section(settings):
    page = settings
    out = page.evaluate("""() => { const head = document.querySelector('.job-os-content>.job-os-header'); const pg = document.querySelector('.settings-page'); const cs = getComputedStyle(pg);
      const r = e => e.getBoundingClientRect(); const main = r(document.querySelector('#mainJobs')); const rail = r(document.querySelector('.settings-rail'));
      const sec = document.querySelector('.job-os-settings-section');
      return {titleShown: getComputedStyle(head.firstElementChild).display, chip: !!head.querySelector('.job-os-status'), border: cs.borderTopWidth, bg: cs.backgroundColor, pad: cs.padding,
        left: r(sec).left - rail.right, right: main.right - r(sec).right, top: r(sec).top - main.top}; }""")
    assert out["titleShown"] == "none" and out["chip"], out  # the title and its description are gone; the status chip stays
    assert out["border"] == "0px" and out["bg"] in ("rgba(0, 0, 0, 0)", "transparent") and out["pad"] == "0px", out
    assert abs(out["left"] - 24) <= .5 and abs(out["right"] - 24) <= .5 and abs(out["top"] - 24) <= .5, out  # the margins stay 24px


@pytest.mark.parametrize("name", ["connections", "apify", "scout", "notifications", "ai", "applicant"])
def test_every_settings_card_keeps_the_same_room_on_all_four_sides(settings, name):
    page = settings
    _section(page, name)
    rows = page.evaluate("""() => [...document.querySelectorAll('.set-group')].map(g => { const r = e => e.getBoundingClientRect(); const gr = r(g);
      const title = g.querySelector('.set-group-title'), rowsEl = g.querySelector('.set-rows'), last = g.lastElementChild;
      return {title: title.textContent, top: r(title).top - gr.top, left: r(rowsEl).left - gr.left, right: gr.right - r(rowsEl).right, bottom: gr.bottom - r(last).bottom}; })""")
    assert rows
    for row in rows:
        for side in ("top", "left", "right", "bottom"):
            assert abs(row[side] - 21) <= .5, (name, row)


# ── Settings: Connections ───────────────────────────────────────────────────

def test_connections_choice_is_as_tall_as_send_test_and_the_card_titles_read_larger(settings):
    page = settings
    _section(page, "connections")
    out = page.evaluate("""() => { const h = s => document.querySelector(s).getBoundingClientRect().height;
      return {send: h('[data-job-os-action=gmail-test]'), choice: h('.job-os-inline-select .themed-select-trigger'),
        title: getComputedStyle(document.querySelector('.set-group-title')).fontSize}; }""")
    assert abs(out["send"] - out["choice"]) <= .1, out
    assert float(out["title"][:-2]) >= 12.5, out


def test_connections_labels_sit_higher_and_the_status_pills_lower(settings):
    page = settings
    _section(page, "connections")
    for action in ("gmail-edit", "gmail-disconnect", "site-check"):
        sel = f".set-group [data-job-os-action='{action}']"
        assert _moved(page, sel, "text", f"{sel}{{padding-bottom:0!important}}") == -.5, action
    for pill in (".set-row .job-os-pill",):
        for n in range(page.locator(pill).count()):
            page.evaluate("n => document.querySelectorAll('.set-row .job-os-pill')[n].id = 'fxPill' + n", n)
            assert _moved(page, f"#fxPill{n}", "text", ".settings-page .set-row .job-os-pill{top:0!important}") == 1, n


def test_replace_and_check_now_wear_the_work_hub_plus_buttons_outline(settings):
    page = settings
    _section(page, "connections")
    same = page.evaluate("""() => { const probe = document.createElement('button'); probe.style.cssText = 'border:1px solid var(--border);border-radius:6px;background:transparent;color:var(--muted);position:fixed;left:0;top:0';
      document.body.appendChild(probe); const want = getComputedStyle(probe);
      const out = ['gmail-edit', 'site-check'].map(a => { const cs = getComputedStyle(document.querySelector(`.set-group [data-job-os-action=${a}]`));
        return [cs.borderTopColor === want.borderTopColor, cs.borderTopLeftRadius === want.borderTopLeftRadius, cs.backgroundColor === want.backgroundColor, cs.color === want.color]; });
      probe.remove(); return out; }""")
    assert all(all(row) for row in same), same


def test_choices_list_has_the_same_gap_above_between_and_below_its_options(settings):
    page = settings
    _section(page, "connections")
    page.click(".job-os-inline-select .themed-select-trigger")
    page.wait_for_selector(".themed-select-popup .themed-select-option")
    gaps = page.evaluate("""() => { const p = document.querySelector('.themed-select-popup'); const r = e => e.getBoundingClientRect(); const o = [...p.querySelectorAll('.themed-select-option')];
      return {spaced: p.classList.contains('is-spaced'), above: r(o[0]).top - r(p).top - 1, between: r(o[1]).top - r(o[0]).bottom, below: r(p).bottom - 1 - r(o[o.length - 1]).bottom}; }""")
    assert gaps["spaced"] and abs(gaps["above"] - gaps["between"]) <= .5 and abs(gaps["below"] - gaps["between"]) <= .5 and gaps["between"] >= 3, gaps


def _ink_gap_above(page, card, button):
    """Pixels between the nearest ink above a button and the button's top edge."""
    box, target = _rect(page, card), _rect(page, button)
    scale = page.evaluate("devicePixelRatio")
    img = _shot(page, {"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"]})
    bg = img.getpixel((int(24 * scale), int(3 * scale)))
    diff = ImageChops.difference(img, Image.new("RGB", img.size, bg)).convert("L").point(lambda v: 255 if v >= 12 else 0)
    top = int((target["y"] - box["y"]) * scale) - 2
    band = diff.crop((int(3 * scale), int(3 * scale), img.width - int(3 * scale), max(top, 1)))
    ink = band.getbbox()
    return (top + 2 - (ink[3] + int(3 * scale))) / scale


@pytest.mark.parametrize("button,card", [("[data-job-os-action=gmail-edit]", "#job-os-gmail"), ("[data-job-os-action=test-firecrawl]", ".set-group:has([data-job-os-action=test-firecrawl])")])
def test_footer_buttons_have_as_much_room_above_them_as_below(settings, button, card):
    page = settings
    _section(page, "connections")
    page.eval_on_selector(card, "e => e.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(300)
    above = _ink_gap_above(page, card, button)
    box, target = _rect(page, card), _rect(page, button)
    below = box["y"] + box["height"] - 1 - (target["y"] + target["height"])
    assert abs(above - below) <= 1, (above, below)


def test_the_first_job_site_is_not_set_off_from_the_title_by_a_rule(settings):
    page = settings
    _section(page, "connections")
    assert page.evaluate("() => getComputedStyle(document.querySelector('.set-rows>.site-health-row')).borderTopWidth") == "0px"


# ── Settings: Apify and Scout schedule ──────────────────────────────────────

def test_apify_token_labels_sit_higher(settings):
    page = settings
    _section(page, "apify")
    for action in ("apify-test", "apify-edit", "apify-disconnect"):
        sel = f".set-group [data-job-os-action='{action}']"
        assert _moved(page, sel, "text", f"{sel}{{padding-bottom:0!important}}") == -.5, action


@pytest.mark.parametrize("section,setting", [("apify", "apify.results_per_city"), ("scout", "scout.max_results_per_search")])
def test_number_boxes_fit_their_digits_with_the_same_room_either_side(settings, section, setting):
    page = settings
    _section(page, section)
    sel = f"input[data-setting='{setting}']"
    box = _rect(page, sel)
    assert box["width"] <= 64, box
    page.eval_on_selector(sel, "e => e.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(250)
    ink = _ink(page, sel, "text")
    left, right = ink["left"] - box["x"], box["x"] + box["width"] - ink["right"]
    assert abs(left - right) <= 1.5, (left, right)


def test_switch_rows_do_not_highlight_and_the_dependent_one_is_not_indented(settings):
    page = settings
    for section, setting in (("apify", "apify.enabled"), ("apify", "apify.indeed_fallback"), ("scout", "scout.enabled"), ("scout", "scout.quiet_skip")):
        _section(page, section)
        row = f".set-switch:has(input[data-setting='{setting}'])"
        page.eval_on_selector(row, "e => e.scrollIntoView({block: 'center'})")
        before = page.eval_on_selector(row, "e => getComputedStyle(e).backgroundColor")
        page.hover(row)
        page.wait_for_timeout(300)
        assert page.eval_on_selector(row, "e => getComputedStyle(e).backgroundColor") == before == "rgba(0, 0, 0, 0)", setting
        page.mouse.move(5, 5)
    texts = page.evaluate("""() => { const r = e => e.getBoundingClientRect(); const row = document.querySelector('.set-switch:has(input[data-setting="scout.quiet_skip"])');
      const first = document.querySelector('.set-group .set-row-text'); return r(row.querySelector('.set-row-text')).left - r(first).left; }""")
    assert abs(texts) <= .5, texts
