"""Jobs pages, fifth round: the job drawer's loading state, its tags and document icons,
the Pipeline search text, Skill gaps columns, a smooth sidebar slide, and the Settings layout.

Nudges are ink on a real 2x display with and without the rule asked for, as in round 4.
"""

import json
import re
from pathlib import Path

import pytest

from tests.test_chat_optical_alignment_browser import _ink, browser, pytestmark, real_2x  # noqa: F401
from tests.test_job_os_page_polish_browser import _go, _mode, _open_job, seeded  # noqa: F401
from tests.test_jobs_round4_browser import REPORT, jobs, studio  # noqa: F401
from tests.test_office_notes_workhub_nudges_browser import _moved

ROOT = Path(__file__).resolve().parents[1]


def test_pipeline_search_text_sits_a_pixel_lower(jobs):
    page = jobs
    _go(page, "pipeline")
    page.wait_for_selector(".pipe-toolbar .pipe-search input")
    sel = "#jobOsRoot .pipe-toolbar .pipe-search input"
    assert _moved(page, sel, "text", f"{sel}{{padding-bottom:2px!important;box-sizing:border-box}}") == 1


def test_job_drawer_opens_on_placeholders_and_fades_the_record_in(jobs, seeded):
    page = jobs
    _go(page, "pipeline")
    _mode(page, "list")
    title = f"Analyzed {seeded['marker']}"
    page.fill("#job-os-pipe-search", title)
    page.wait_for_selector(f".job-os-job-card:has-text('{title}')", timeout=10000)
    held = []
    page.route("**/api/job-os/jobs/*", lambda route: held.append(route) if route.request.method == "GET" else route.fallback())
    page.click(f".job-os-job-card:has-text('{title}')")
    page.wait_for_selector(".job-drawer .job-drawer-body.is-loading .drawer-skeleton", timeout=5000)
    page.wait_for_timeout(500)
    assert page.locator(".job-drawer .apply-kit, .job-drawer .job-drawer-actions").count() == 0  # only what the list knew is real
    assert page.locator(".job-drawer .job-drawer-head h2").inner_text().strip()  # the header is already the job's own
    bars = page.evaluate("() => document.querySelectorAll('.drawer-skeleton .skeleton-bar').length")
    assert bars >= 10, bars
    for route in held:
        route.continue_()
    page.wait_for_selector(".job-drawer .job-drawer-body.is-ready .job-drawer-section", timeout=15000)
    assert page.locator(".drawer-skeleton").count() == 0
    page.wait_for_timeout(500)
    assert page.evaluate("() => getComputedStyle(document.querySelector('.job-drawer-body.is-ready > *')).opacity") == "1"


def test_drawer_tags_read_higher(jobs, seeded):
    page = jobs
    _open_job(page, f"Analyzed {seeded['marker']}")
    tags = ".job-drawer-tags"
    assert _moved(page, f"{tags} .job-os-badge", "text", f"{tags} .job-os-badge>span{{top:0!important}}", within=f"{tags} .job-os-badge") == -.5
    assert _moved(page, f"{tags} .pipe-source", "text", f"{tags} .pipe-source{{padding-bottom:0!important}}", within=f"{tags} .pipe-source") == -1


def test_cover_letter_icon_has_no_plate_and_matches_the_other_document_icons(real_2x):
    page = real_2x
    stats = page.evaluate("""async () => {
      const read = async (name, size) => {
        const bitmap = await createImageBitmap(await (await fetch(`/static/job-os/icons/${name}-${size}.webp`)).blob());
        const c = document.createElement('canvas'); c.width = c.height = size;
        const ctx = c.getContext('2d'); ctx.drawImage(bitmap, 0, 0);
        const px = ctx.getImageData(0, 0, size, size).data;
        let x0 = size, x1 = -1, y0 = size, y1 = -1, faint = 0;
        for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
          const a = px[(y * size + x) * 4 + 3];
          if (a >= 60) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); } else if (a > 0) faint++;
        }
        return {corner: px[3], w: x1 - x0 + 1, h: y1 - y0 + 1, faint};
      };
      const out = {};
      for (const size of [22, 44]) out[size] = {letter: await read('cover-letter', size), docx: await read('word-document', size)};
      return out;
    }""")
    for size, pair in stats.items():
        letter, docx = pair["letter"], pair["docx"]
        assert letter["corner"] == 0, (size, letter)  # the corner is bare: no plate behind the sheet
        assert letter["faint"] <= int(size) * 3, (size, letter)  # only anti-aliased edges, no haze
        assert abs(letter["w"] - docx["w"]) <= 2 and abs(letter["h"] - docx["h"]) <= 2, (size, letter, docx)


def test_skill_gaps_columns_are_equal_and_share_the_card(jobs, seeded):
    page = jobs
    page.route("**/api/job-os/skill-gaps", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(REPORT)))
    _go(page, "resume-studio")
    page.wait_for_selector(".gaps-grid", timeout=15000)
    page.wait_for_timeout(400)
    out = page.evaluate("""() => { const grid = document.querySelector('.gaps-grid'), box = grid.getBoundingClientRect();
      const [gaps, themes] = [...grid.children].map(c => c.getBoundingClientRect());
      return {gaps: [gaps.left, gaps.width], themes: [themes.left, themes.width, themes.right], box: [box.left, box.right]}; }""")
    assert abs(out["gaps"][1] - out["themes"][1]) <= 1, out  # two equal columns
    assert abs(out["themes"][2] - out["box"][1]) <= 1, out  # the second one reaches the card's right edge


def test_the_row_of_gaps_and_themes_ends_where_its_content_ends(jobs, seeded):
    page = jobs
    tall = json.loads(json.dumps(REPORT))
    tall["skill_gaps"]["reports"][0]["themes"] = [{"name": f"Theme {i}", "why": "Most roles want it. " * 6} for i in range(4)]
    page.route("**/api/job-os/skill-gaps", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(tall)))
    _go(page, "resume-studio")
    page.wait_for_selector(".gaps-grid", timeout=15000)
    page.wait_for_timeout(400)
    out = page.evaluate("""() => { const card = document.querySelector('.skill-gaps'), grid = card.querySelector('.gaps-grid');
      const note = card.querySelector(':scope > .job-os-card-note').getBoundingClientRect();
      const [gaps, themes, plan] = [...grid.children];
      const h = e => e.querySelector('h4').getBoundingClientRect();
      const bottom = Math.max(gaps.querySelector('ul').getBoundingClientRect().bottom, themes.querySelector('ul').getBoundingClientRect().bottom);
      return {above: h(gaps).top - note.bottom, below: h(plan).top - bottom}; }""")
    assert abs(out["above"] - out["below"]) <= .5, out


def test_sidebar_slide_keeps_the_jobs_text_still_while_the_page_glides(jobs):
    page = jobs
    result = page.evaluate("""async () => {
      const root = document.querySelector('#jobOsRoot');
      const els = [...root.querySelectorAll('.job-os-content *')].filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1) && e.getBoundingClientRect().width > 0);
      const open = !document.querySelector('.layout').classList.contains('sidebar-collapsed');
      toggleSidebar(open);
      const t0 = performance.now(), frames = [];
      await new Promise(res => { const tick = () => { frames.push({w: root.getBoundingClientRect().width, p: els.map(e => { const r = e.getBoundingClientRect(); return r.top; })});
        performance.now() - t0 < 900 ? requestAnimationFrame(tick) : res(); }; requestAnimationFrame(tick); });
      let jumps = 0, widths = new Set(frames.map(f => Math.round(f.w)));
      els.forEach((e, i) => { for (let f = 1; f < frames.length; f++) if (Math.abs(frames[f].p[i] - frames[f - 1].p[i]) > 1) jumps++; });
      return {jumps, widths: [...widths].length, frames: frames.length};
    }""")
    assert result["jumps"] == 0, result  # no text re-wraps or hops mid-slide
    assert result["widths"] == 1, result  # the page kept the width it ends at


def _settings(page):
    _go(page, "settings")
    page.wait_for_selector(".settings-layout .settings-nav-item", timeout=15000)
    page.wait_for_timeout(700)


def test_settings_nav_titles_sit_clear_of_their_descriptions(jobs):
    page = jobs
    _settings(page)
    gaps = page.evaluate("""() => [...document.querySelectorAll('.settings-nav-item')].map(b => {
      const t = b.querySelector('strong').getBoundingClientRect(), d = b.querySelector('small').getBoundingClientRect();
      return d.top - t.bottom; })""")
    assert gaps and all(g >= 8 for g in gaps), gaps


def test_settings_list_is_a_full_height_side_panel_and_each_section_one_main_card(jobs):
    page = jobs
    _settings(page)
    out = page.evaluate("""() => { const r = e => e.getBoundingClientRect();
      const rail = document.querySelector('.settings-rail'), page = document.querySelector('.settings-page'), shell = document.querySelector('#mainJobs');
      const main = r(shell), cs = getComputedStyle(rail), pc = getComputedStyle(page);
      return {railLeft: r(rail).left - main.left, railTop: r(rail).top - main.top, railBottom: main.bottom - r(rail).bottom,
        railBorder: [cs.borderRightWidth, cs.borderTopWidth, cs.borderRadius],
        pageBorder: pc.borderTopWidth, pageRadius: pc.borderRadius,
        cardsInside: [...page.querySelectorAll('.set-group')].every(g => page.contains(g)),
        titleInside: page.contains(page.querySelector('.job-os-settings-section > .set-head h2')),
        pageLeft: r(page).left - r(rail).right}; }""")
    assert out["railLeft"] <= 1 and out["railTop"] <= 1 and out["railBottom"] <= 1, out  # flush with the page's edges
    assert out["railBorder"][0] == "1px" and out["railBorder"][1] == "0px" and out["railBorder"][2] == "0px", out
    assert out["pageBorder"] == "1px" and out["pageRadius"] != "0px", out  # the main card has an outline
    assert out["cardsInside"] and out["titleInside"], out  # and holds the title, description and every card
    assert out["pageLeft"] >= 16, out


def test_phone_settings_keep_the_one_column_layout(browser, seeded):
    from tests.test_chat_optical_alignment_browser import _open  # noqa: PLC0415

    context, page = _open(browser, {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True})
    try:
        page.evaluate("async () => { await switchPanel('jobs'); }")
        page.wait_for_selector("#jobOsRoot", timeout=30000)
        page.click(".job-os-tabs [data-job-os-view='settings']")
        page.wait_for_selector(".settings-layout", timeout=15000)
        assert page.evaluate("() => getComputedStyle(document.querySelector('.settings-layout')).display") in ("block", "grid")
        assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
    finally:
        context.close()
