"""Jobs pipeline cards, the job drawer and the Jobs Settings page, eighth round.

As in the earlier rounds the Settings page is read with an account connected, and nudges are ink on a real
2x display with and without the rule being asked for.
"""

import json
import urllib.request

import pytest
from PIL import Image, ImageChops

from tests._pytest_port import BASE
from tests.test_chat_optical_alignment_browser import _ink, _rect, _shot, browser, pytestmark, real_2x  # noqa: F401
from tests.test_job_os_page_polish_browser import _go, _open_job, seeded  # noqa: F401
from tests.test_jobs_round4_browser import jobs  # noqa: F401
from tests.test_jobs_round7_browser import _connected, _section, settings  # noqa: F401
from tests.test_office_notes_workhub_nudges_browser import _moved


# ── Pipeline card and job drawer ────────────────────────────────────────────

def test_the_card_site_label_reads_a_pixel_lower(jobs):
    page = jobs
    _go(page, "pipeline")
    page.wait_for_selector(".pipe-card .pipe-source", timeout=15000)
    page.wait_for_timeout(400)
    sel = ".pipe-card .pipe-source"
    assert _moved(page, sel, "text", f"#jobOsRoot .pipe-card .pipe-source{{padding-bottom:2px!important}}") == 1


def test_a_check_chip_on_a_card_has_its_icon_a_pixel_and_its_words_half_a_pixel_lower(jobs):
    page = jobs
    _go(page, "pipeline")
    page.wait_for_selector(".pipe-card .pipe-when", timeout=15000)
    page.evaluate("""() => { const card = document.querySelector('.pipe-card'); const icon = card.querySelector('.pipe-fact svg').outerHTML;
      const when = card.querySelector('.pipe-when'); when.id = 'fxWhen';
      when.innerHTML = `<span class="job-check" data-tone="warn" data-check="language" aria-label="Language">${icon}<span>Language</span></span>`; }""")
    page.wait_for_timeout(300)
    chip = "#fxWhen .job-check"
    undo = "#jobOsRoot .pipe-card .job-check{padding-top:0!important}#jobOsRoot .pipe-card .job-check>svg{top:-1px!important}"
    assert _moved(page, chip, "icon", undo) == 1
    assert _moved(page, chip, "text", undo) == .5
    before = _rect(page, chip)
    handle = page.add_style_tag(content=undo)
    page.wait_for_timeout(150)
    after = _rect(page, chip)
    handle.evaluate("e => e.remove()")
    assert (before["y"], before["height"]) == (after["y"], after["height"])  # the chip itself stays


def test_the_ive_applied_button_reads_half_a_pixel_lower(jobs, seeded):
    page = jobs
    _open_job(page, seeded["ready"]["title"])
    page.eval_on_selector(".apply-step", "e => e.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(250)
    sel = ".apply-step [data-job-os-action='board-apply']"
    assert _moved(page, sel, "text", f"#jobOsRoot {sel}{{padding-top:0!important}}") == .5


# ── Settings: side panel ────────────────────────────────────────────────────

def test_the_section_list_opens_with_a_general_title_and_every_heading_has_the_same_room_above(settings):
    page = settings
    out = page.evaluate("""() => { const r = e => e.getBoundingClientRect(); const rail = document.querySelector('.settings-rail');
      const title = rail.querySelector('.settings-rail-title'); const head = document.querySelector('#jobOsSidebar').closest('.sidebar,#panelJobs,body').querySelector('.panel-head');
      const heads = [...rail.querySelectorAll('.settings-nav-group>span')];
      return {text: title.textContent, order: title.nextElementSibling.className, titleBottom: r(title).bottom, headBottom: r(head).bottom, titleSize: getComputedStyle(title).fontSize,
        headSize: getComputedStyle(heads[0]).fontSize, tops: heads.map(h => r(h).top), names: heads.map(h => h.textContent)}; }""")
    assert out["text"] == "General" and out["order"] == "settings-nav-group", out
    assert abs(out["titleBottom"] - out["headBottom"]) <= .5, out  # its divider continues the Jobs panel title's
    assert float(out["titleSize"][:-2]) > 11 and float(out["headSize"][:-2]) >= 13, out
    inks = []
    for i in (1, 4):  # the last line before AUTOMATION and before YOU
        page.evaluate("i => { document.querySelectorAll('.settings-nav-item')[i].querySelector('.settings-nav-text small').id = 'fxHint' + i; }", i)
        inks.append(_ink(page, f"#fxHint{i}", "text")["bottom"])
    first = out["tops"][0] - out["titleBottom"]
    others = [out["tops"][1] - inks[0], out["tops"][2] - inks[1]]  # last ink above the heading to the heading's capitals
    for gap in others:
        assert abs(first - gap) <= 2, (first, others)


def test_section_icons_fill_the_tile_they_had_and_have_no_tile(settings):
    page = settings
    out = page.evaluate("""() => [...document.querySelectorAll('.settings-nav-item')].map(item => { const icon = item.querySelector('.settings-nav-icon'); const cs = getComputedStyle(icon);
      const svg = icon.querySelector('svg').getBoundingClientRect(); return {active: item.classList.contains('active'), bg: cs.backgroundColor, w: svg.width, h: svg.height, box: icon.getBoundingClientRect().width, border: cs.borderTopWidth}; })""")
    for icon in out:
        assert icon["bg"] in ("rgba(0, 0, 0, 0)", "transparent") and icon["border"] == "0px", icon
        assert abs(icon["w"] - icon["box"]) <= .5 and abs(icon["h"] - icon["box"]) <= .5, icon
    assert any(icon["active"] for icon in out)


# ── Settings: save bar and Discard ──────────────────────────────────────────

def test_save_settings_reads_two_pixels_higher(settings):
    page = settings
    _section(page, "scout")
    page.fill("input[data-setting='scout.timezone']", "Europe/Paris")
    page.wait_for_timeout(500)
    sel = ".job-os-savebar [data-job-os-action='save-settings']"
    before = _rect(page, sel)
    undo = f"#jobOsRoot {sel}{{padding-top:8px!important;padding-bottom:2px!important}}"
    assert _moved(page, sel, "text", undo) == -2
    handle = page.add_style_tag(content=undo)
    page.wait_for_timeout(150)
    after = _rect(page, sel)
    handle.evaluate("e => e.remove()")
    assert (before["y"], before["height"]) == (after["y"], after["height"])  # the button keeps its size


def test_discard_puts_every_field_back_to_what_was_saved(settings):
    page = settings
    _section(page, "scout")
    fields = "() => [document.querySelector(\"input[data-setting='scout.max_results_per_search']\").value, document.querySelector(\"input[data-setting='scout.timezone']\").value, document.querySelector(\"input[data-setting='scout.quiet_skip']\").checked, document.querySelector('.themed-select-trigger').textContent.trim()]"
    saved = page.evaluate(fields)
    page.fill("input[data-setting='scout.max_results_per_search']", "77")
    page.fill("input[data-setting='scout.timezone']", "Europe/Paris")
    page.click("input[data-setting='scout.quiet_skip'] + .job-os-toggle-track")
    page.click(".set-row .themed-select-trigger")
    page.wait_for_selector(".themed-select-popup .themed-select-option")
    page.click(".themed-select-popup .themed-select-option:nth-child(2)")
    page.wait_for_timeout(400)
    assert page.evaluate(fields) != saved
    assert page.eval_on_selector(".job-os-savebar", "e => e.dataset.dirty") == "true"
    page.click(".job-os-savebar [data-job-os-action='discard-settings']")
    page.wait_for_timeout(900)
    assert page.evaluate(fields) == saved
    assert page.eval_on_selector(".job-os-savebar", "e => e.dataset.dirty") == "false"
    assert page.eval_on_selector(".job-os-savebar [data-job-os-action='save-settings']", "e => e.disabled")


# ── Settings: Connections and Apify ─────────────────────────────────────────

def _dot_top(page, pill):
    """Top of a pill's dot (its ::before) in CSS pixels, from the difference with the dot hidden."""
    box = _rect(page, pill)
    clip = {"x": box["x"] - 2, "y": box["y"] - 2, "width": box["width"] + 4, "height": box["height"] + 4}
    before = _shot(page, clip)
    handle = page.add_style_tag(content=f"{pill}::before{{background:transparent!important}}")
    after = _shot(page, clip)
    handle.evaluate("e => e.remove()")
    box_ = ImageChops.difference(before, after).convert("L").point(lambda v: 255 if v >= 24 else 0).getbbox()
    assert box_, "no dot found"
    return clip["y"] + box_[1] / (before.height / clip["height"])


@pytest.mark.parametrize("section", ["connections", "apify"])
def test_status_pills_have_their_words_a_pixel_and_their_dot_one_and_a_half_pixels_lower(settings, section):
    page = settings
    _section(page, section)
    undo = "#jobOsRoot .settings-page .set-row .job-os-pill{padding:1px 6px 2px!important}#jobOsRoot .settings-page .set-row .job-os-pill::before{top:0!important}"
    for n in range(page.locator(".set-row .job-os-pill").count()):
        page.evaluate("n => document.querySelectorAll('.set-row .job-os-pill')[n].id = 'fxPill' + n", n)
        pill = f"#fxPill{n}"
        assert _moved(page, pill, "text", undo) == 1, (section, n)
        now = _dot_top(page, pill)
        handle = page.add_style_tag(content=undo)
        page.wait_for_timeout(150)
        old = _dot_top(page, pill)
        pill_box = _rect(page, pill)
        handle.evaluate("e => e.remove()")
        assert abs(now - old - 1.5) <= .1, (section, n, now - old)
        assert _rect(page, pill) == pill_box  # the pill keeps its place and size


def test_send_test_and_its_choice_read_half_a_pixel_higher_and_check_now_half_a_pixel_lower(settings):
    page = settings
    _section(page, "connections")
    undo = ("#jobOsRoot .settings-page .set-row .job-os-inline-select .themed-select-trigger{padding-bottom:0!important}"
            ".settings-page .set-group .job-os-btn.small[data-job-os-action='gmail-test']{padding-bottom:0!important}"
            ".settings-page .set-group .job-os-btn.small[data-job-os-action='site-check']{padding-bottom:1px!important}")
    assert _moved(page, ".job-os-inline-select .themed-select-trigger", "text", undo) == -.5
    assert _moved(page, "[data-job-os-action='gmail-test']", "text", undo) == -.5
    page.eval_on_selector("[data-job-os-action='site-check']", "e => e.scrollIntoView({block: 'center'})")
    assert _moved(page, ".set-group [data-job-os-action='site-check']", "text", undo) == .5


FOOT = """() => [...document.querySelectorAll('.set-group')].filter(g => g.querySelector('.set-group-foot .job-os-btn')).map(g => { const r = e => e.getBoundingClientRect(); const gr = r(g);
  const btns = [...g.querySelectorAll('.set-group-foot .set-foot-actions .job-os-btn')]; if (!btns.length) return null;
  const left = Math.min(...btns.map(b => r(b).left)), right = Math.max(...btns.map(b => r(b).right)), top = Math.min(...btns.map(b => r(b).top)), bottom = Math.max(...btns.map(b => r(b).bottom));
  let above = null; g.querySelectorAll('.set-rows input:not([type=checkbox]),.set-rows select,.set-rows textarea,.set-rows button,.set-rows .job-os-pill,.set-rows .themed-select-trigger').forEach(e => { const q = r(e);
    if (q.height && q.right >= left && q.left <= right) above = Math.max(above ?? -1e9, q.bottom); });
  return {title: g.querySelector('.set-group-title').textContent, above: above == null ? null : top - above, below: gr.bottom - 1 - bottom}; }).filter(Boolean)"""


@pytest.mark.parametrize("section", ["connections", "apify"])
def test_buttons_under_a_card_are_as_far_below_the_field_above_them_as_from_the_cards_edge(settings, section):
    page = settings
    _section(page, section)
    feet = page.evaluate(FOOT)
    assert feet
    for foot in feet:
        assert foot["above"] is not None and abs(foot["above"] - foot["below"]) <= .75, foot


# ── Settings: every card ────────────────────────────────────────────────────

CONTROLS = """g => { const r = e => e.getBoundingClientRect(); const gr = r(g); const scope = g.querySelector('.set-group-foot') || g.querySelector('.set-rows').lastElementChild;
  let bottom = 0; scope.querySelectorAll('.set-row-control :is(input:not([type=checkbox]),select,textarea,button,.job-os-pill,.themed-select-trigger,.job-os-toggle-track),.set-foot-actions .job-os-btn')
    .forEach(e => { const q = r(e); if (q.height) bottom = Math.max(bottom, q.bottom); });
  return {top: r(g.querySelector('.set-group-title')).top - gr.top, controls: bottom ? gr.bottom - bottom : null}; }"""


def _card_room(page, group):
    """(room from the card's top edge to its title, room from the card's bottom edge to the nearest thing painted
    above it: a field or button edge, or the last line of text, which ends at its baseline plus any descender)."""
    group.scroll_into_view_if_needed()
    page.evaluate("e => e.scrollIntoView({block: 'center'})", group)
    page.wait_for_timeout(250)
    box = group.bounding_box()
    img = _shot(page, {"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"]})
    scale = img.width / box["width"]
    bg = img.getpixel((int(12 * scale), int(12 * scale)))
    edge = int(3 * scale)
    inner = img.crop((edge, edge, img.width - edge, img.height - edge))
    ink = ImageChops.difference(inner, Image.new("RGB", inner.size, bg)).convert("L").point(lambda v: 255 if v >= 20 else 0).getbbox()
    measured = group.evaluate(CONTROLS)
    text = (img.height - ink[3] - edge) / scale
    bottom = min(text, measured["controls"]) if measured["controls"] is not None else text
    return measured["top"], bottom


@pytest.mark.parametrize("name", ["connections", "apify", "scout", "notifications", "ai", "applicant", "apply"])
def test_every_card_has_as_much_room_under_its_content_as_over_its_title(settings, name):
    page = settings
    _section(page, name)
    for group in page.query_selector_all(".set-group"):
        top, bottom = _card_room(page, group)
        assert -4 <= bottom - top <= 1.5, (name, group.query_selector(".set-group-title").inner_text(), top, bottom)  # (4px: a descender hangs below the baseline)


def test_a_row_switched_off_keeps_its_fields_outline(settings):
    page = settings
    _section(page, "notifications")
    out = page.evaluate("""() => [...document.querySelectorAll('.set-row.is-off .set-number .set-input')].map(i => ({border: getComputedStyle(i).borderTopColor,
      opacity: getComputedStyle(i.closest('.set-row-control')).opacity, text: getComputedStyle(i).color}))""")
    assert out
    for field in out:
        assert field["opacity"] == "1", field  # the outline is not faded with the row...
        assert "/ 0.5" in field["text"], field  # ...while its text is dimmed (half-transparent)


# ── Settings: number boxes, one-line hint, switches, order ──────────────────

def _numbers(page):
    return page.evaluate("""() => [...document.querySelectorAll('.set-row .set-number')].map(n => { const r = e => e.getBoundingClientRect(); const input = n.querySelector('input'), em = n.querySelector('em');
      const rows = n.closest('.set-rows'); return {setting: input.dataset.setting, left: r(input).left, right: r(input).right, em: '#' + (em.id = 'fx' + input.dataset.setting.replace(/\\W/g, '')), rows: r(rows).right, inputSel: 'input[data-setting="' + input.dataset.setting + '"]'}; })""")


def test_number_boxes_stand_in_one_column_and_each_unit_has_equal_room_either_side(settings):
    page = settings
    for section in ("notifications", "apify", "scout"):
        _section(page, section)
        boxes = _numbers(page)
        assert boxes
        assert len({round(b["left"], 1) for b in boxes}) == 1 and len({round(b["right"], 1) for b in boxes}) == 1, boxes
        for b in boxes:
            page.eval_on_selector(b["inputSel"], "e => e.scrollIntoView({block: 'center'})")
            page.wait_for_timeout(200)
            ink = _ink(page, b["em"], "text")
            assert abs((ink["left"] - b["right"]) - (b["rows"] - ink["right"])) <= 2, (section, b, ink)  # (a colon's ink sits off the middle of its cell)


@pytest.mark.parametrize("section,setting", [("apify", "apify.results_per_city"), ("scout", "scout.max_results_per_search"), ("notifications", "notifications.min_fit_score"), ("notifications", "notifications.release_count")])
def test_the_digits_sit_in_the_middle_of_their_number_box(settings, section, setting):
    page = settings
    _section(page, section)
    sel = f"input[data-setting='{setting}']"
    box = _rect(page, sel)
    page.eval_on_selector(sel, "e => e.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(250)
    box = _rect(page, sel)
    ink = _ink(page, sel, "text")
    assert abs((ink["left"] - box["x"]) - (box["x"] + box["width"] - ink["right"])) <= .5, (box, ink)


def test_the_quiet_run_hint_is_one_line(settings):
    page = settings
    _section(page, "scout")
    lines = page.evaluate("""() => { const s = document.querySelector('.set-switch:has([data-setting="scout.quiet_skip"]) .set-row-text small'); const r = document.createRange(); r.selectNodeContents(s);
      return new Set([...r.getClientRects()].map(q => Math.round(q.top))).size; }""")
    assert lines == 1


def test_good_matches_lists_the_email_switch_above_the_match_score(settings):
    page = settings
    _section(page, "notifications")
    labels = page.evaluate("""() => [...document.querySelectorAll('.set-group')].find(g => g.querySelector('.set-group-title').textContent === 'Good matches')
      .querySelectorAll('.set-row-label') ? [...[...document.querySelectorAll('.set-group')].find(g => g.querySelector('.set-group-title').textContent === 'Good matches').querySelectorAll('.set-row-label')].map(e => e.textContent) : []""")
    assert labels[:2] == ["Email good matches", "Good match from"], labels


@pytest.fixture
def classic(browser):
    """A window whose scrollbars take room (the default headless browser hides them), 900px tall."""
    from tests.test_chat_optical_alignment_browser import _open
    real = browser.browser_type.launch(args=["--no-sandbox", "--disable-dev-shm-usage"], ignore_default_args=["--hide-scrollbars"])
    context, page = _open(real, {"viewport": {"width": 1470, "height": 900}})
    yield page
    context.close()
    real.close()


def test_a_card_keeps_its_width_when_a_choice_makes_the_page_long_enough_to_scroll(classic, seeded):
    page = classic
    page.evaluate("async () => { await switchPanel('jobs'); }")
    page.wait_for_selector("#jobOsRoot .cal", timeout=30000)
    _connected(page)
    _section(page, "scout")
    widths = []
    for mode in ("times", "interval", "times"):
        page.evaluate("""m => { const e = document.querySelector("select[data-setting='scout.schedule_mode']"); e.value = m; e.dispatchEvent(new Event('change', {bubbles: true})); }""", mode)
        page.wait_for_timeout(500)
        widths.append(page.evaluate("() => [document.querySelector('.set-group').getBoundingClientRect().width, document.getElementById('mainJobs').scrollHeight > document.getElementById('mainJobs').clientHeight]"))
    assert len({w[0] for w in widths}) == 1, widths
    assert {w[1] for w in widths} == {True, False}, widths  # the two choices really do differ in whether the page scrolls
