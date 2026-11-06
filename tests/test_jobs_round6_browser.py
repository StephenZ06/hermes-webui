"""Chat model picker, Jobs pages and Settings, sixth round.

The page-wide checks (nothing re-places a strip every frame, no node is moved when a section is
picked, the Dashboard's tiles keep their height while loading, the drawer's placeholders are as tall
as the record that replaces them) read what the page does. Nudges are ink on a real 2x display with
and without the rule being asked for, as in the earlier rounds.
"""

import json

import pytest
from PIL import ImageChops

from tests.test_chat_menus_fork_browser import _configured_picker
from tests.test_chat_optical_alignment_browser import _ink, _rect, _shot, browser, pytestmark, real_2x  # noqa: F401
from tests.test_job_os_page_polish_browser import _go, _mode, _open_job, seeded  # noqa: F401
from tests.test_jobs_round4_browser import jobs  # noqa: F401
from tests.test_office_notes_workhub_nudges_browser import _moved

GAPS = {"skill_gaps": {"running": False, "error": "", "reports": [{
    "id": "r1", "jobs": 12, "scope": {}, "created_at": 1793356355, "since_last": None,
    "gaps": [{"label": "Cloud detection", "gap": 7}, {"label": "CISSP", "gap": 4}, {"label": "Kubernetes", "gap": 3}],
    "themes": [{"name": "Cloud", "why": "Most roles want it."}, {"name": "Certs", "why": "Several ask for CISSP."}],
    "plan": [{"step": "Study for CISSP", "detail": "Twelve weeks."}]}]}}


# ── Chat: model picker ──────────────────────────────────────────────────────

def test_custom_id_divider_sits_a_pixel_higher_and_its_box_has_as_much_room_below_as_above(real_2x):
    page = real_2x
    _configured_picker(page)
    page.mouse.move(5, 5)
    page.wait_for_timeout(800)
    page.evaluate("""() => { const d = document.querySelector('#composerModelDropdown');
      d.querySelector('.model-custom-sep').id = 'fxSep'; d.querySelector('.model-custom-input').id = 'fxCustom'; }""")
    # The menu is anchored at its bottom, so positions are read from its own top edge.
    top = lambda sel: page.eval_on_selector(sel, "e => e.getBoundingClientRect().top - document.querySelector('#composerModelDropdown').getBoundingClientRect().top")  # noqa: E731
    inkTop = lambda: _ink(page, "#fxSep", "text")["top"] - page.eval_on_selector("#composerModelDropdown", "e => e.getBoundingClientRect().top")  # noqa: E731
    now = {"sep": top("#fxSep"), "heading": inkTop()}
    handle = page.add_style_tag(content=".model-custom-sep{margin-top:4px!important;padding-top:5px!important}"
                                        "#composerModelDropdown .model-custom-row{padding-top:5px!important;padding-bottom:8px!important}")
    page.wait_for_timeout(150)
    old = {"sep": top("#fxSep"), "heading": inkTop()}
    handle.evaluate("e => e.remove()")
    page.wait_for_timeout(150)
    assert now["sep"] - old["sep"] == -1  # the divider is a pixel higher
    assert now["heading"] - old["heading"] == -.5  # the heading follows by half of it, staying centred
    heading = _ink(page, "#fxSep", "text")
    box = _rect(page, "#fxCustom")
    below = page.evaluate("""() => { const sep = document.querySelector('#fxSep'); let next = sep.nextElementSibling;
      while (next && !next.matches('.model-group')) next = next.nextElementSibling;
      return next.getBoundingClientRect().top; }""")
    above_room = box["y"] - heading["bottom"]
    below_room = below - (box["y"] + box["height"])
    assert abs(above_room - below_room) <= .5, (above_room, below_room)


# ── Jobs: Dashboard ─────────────────────────────────────────────────────────

def test_dashboard_tiles_and_title_keep_their_size_while_loading(real_2x):
    page = real_2x
    page.add_init_script("""window.__frames = []; (function tick() {
      const m = document.querySelector('#jobOsRoot .job-os-metrics'), h = document.querySelector('#jobOsRoot .job-os-header');
      if (m && h) window.__frames.push([Math.round(m.getBoundingClientRect().height * 10) / 10, Math.round((m.getBoundingClientRect().top - h.getBoundingClientRect().bottom) * 10) / 10,
        Math.round(h.getBoundingClientRect().height * 10) / 10, m.querySelector('.is-loading') ? 1 : 0]);
      requestAnimationFrame(tick); })();""")
    page.reload(wait_until="domcontentloaded")
    page.evaluate("async () => { await switchPanel('jobs'); }")
    page.wait_for_selector(".job-os-metrics:not(:has(.is-loading))", timeout=30000)
    page.wait_for_timeout(600)
    frames = page.evaluate("window.__frames")
    assert any(f[3] for f in frames) and any(not f[3] for f in frames), "need both the loading and the loaded state"
    assert len({f[0] for f in frames}) == 1, sorted({f[0] for f in frames})  # the tiles never change height
    assert len({f[1] for f in frames}) == 1, sorted({f[1] for f in frames})  # nor does the title row move against them
    assert len({f[2] for f in frames}) == 1, sorted({f[2] for f in frames})


# ── Jobs: sidebar slide ─────────────────────────────────────────────────────

def test_a_tab_strip_is_not_placed_again_every_frame(jobs):
    page = jobs
    page.wait_for_timeout(500)
    count = page.evaluate("""async () => { let n = 0;
      document.querySelectorAll('[data-mi-tabs]').forEach(c => new MutationObserver(l => { n += l.length; })
        .observe(c, {attributes: true, subtree: true, childList: true, attributeFilter: ['class']}));
      await new Promise(r => setTimeout(r, 700)); return n; }""")
    assert count == 0, count


def test_a_strip_that_left_the_page_is_not_touched_again(jobs):
    page = jobs
    count = page.evaluate("""async () => {
      const strip = document.createElement('div'); strip.dataset.miTabs = '';
      strip.innerHTML = '<button class="active">One</button><button>Two</button>';
      document.body.appendChild(strip); window.Micro.tabs(strip);
      strip.remove();
      let n = 0; new MutationObserver(l => { n += l.length; }).observe(strip, {childList: true, subtree: true, attributes: true});
      strip.firstElementChild.classList.toggle('active');
      await new Promise(r => setTimeout(r, 600)); return n; }""")
    assert count <= 1, count  # the one change above; nothing re-queues the placement


def test_the_jobs_page_is_its_own_layer_for_the_slide_unless_something_is_open_over_it(jobs, seeded):
    page = jobs
    state = page.evaluate("""async () => { window.__hermesSlideTimeScale = 0.05;
      const open = !document.querySelector('.layout').classList.contains('sidebar-collapsed');
      toggleSidebar(open);
      await new Promise(r => setTimeout(r, 200));
      const during = getComputedStyle(document.querySelector('#jobOsRoot')).willChange;
      window.__hermesSlideTimeScale = 1; toggleSidebar(!open);
      await new Promise(r => setTimeout(r, 1200));
      return {during, after: getComputedStyle(document.querySelector('#jobOsRoot')).willChange}; }""")
    assert state["during"] == "transform", state
    assert state["after"] == "auto", state
    _open_job(page, f"Analyzed {seeded['marker']}")
    drawer = page.evaluate("""async () => { window.__hermesSlideTimeScale = 0.05;
      const open = !document.querySelector('.layout').classList.contains('sidebar-collapsed');
      toggleSidebar(open);
      await new Promise(r => setTimeout(r, 200));
      const during = getComputedStyle(document.querySelector('#jobOsRoot')).willChange;
      window.__hermesSlideTimeScale = 1; toggleSidebar(!open);
      await new Promise(r => setTimeout(r, 1200));
      return during; }""")
    assert drawer == "auto", drawer  # a transform hint would carry the drawer, which is fixed to the window, with it


# ── Jobs: job drawer ────────────────────────────────────────────────────────

def _held_drawer(page, seeded, key):
    _go(page, "pipeline")
    _mode(page, "list")
    title = seeded[key]["title"]
    page.fill("#job-os-pipe-search", title)
    page.wait_for_selector(f".job-os-job-card:has-text('{title}')", timeout=10000)
    held = []
    page.route("**/api/job-os/jobs/*", lambda route: held.append(route) if route.request.method == "GET" else route.fallback())
    page.click(f".job-os-job-card:has-text('{title}')")
    page.wait_for_selector(".job-drawer .drawer-skeleton", timeout=5000)
    page.wait_for_timeout(500)
    return held


@pytest.mark.parametrize("key", ["analyzed", "applied"])
def test_drawer_placeholders_are_as_tall_as_the_record_that_replaces_them(jobs, seeded, key):
    page = jobs
    held = _held_drawer(page, seeded, key)
    loading = page.evaluate("() => document.querySelector('.job-drawer-body').scrollHeight")
    for route in held:
        route.continue_()
    page.unroute("**/api/job-os/jobs/*")
    page.wait_for_selector(".job-drawer .job-drawer-body.is-ready .job-os-analysis", timeout=15000)
    page.wait_for_timeout(600)
    loaded = page.evaluate("() => document.querySelector('.job-drawer-body').scrollHeight")
    assert abs(loaded - loading) <= 40, (loading, loaded)


def test_drawer_button_labels_sit_higher_and_the_icons_lower(jobs, seeded):
    page = jobs
    _open_job(page, seeded["analyzed"]["title"])
    page.evaluate("""() => document.querySelector('.job-drawer-body').insertAdjacentHTML('beforeend',
      '<section class="job-drawer-section follow-up"><h3>Follow up</h3><p class="job-os-card-note">No news for 7 days.</p>'
      + '<div class="job-os-actions"><button type="button" class="job-os-btn small primary" id="fxDraft">Draft follow-up</button></div></section>')""")
    buttons = page.evaluate("() => [...document.querySelectorAll('.job-drawer-actions>.job-os-btn')].map((b, i) => (b.dataset.fx = 'a' + i, b.dataset.fx))")
    assert len(buttons) >= 3, buttons
    for tag in buttons:
        assert _moved(page, f"[data-fx={tag}]", "text", ".job-drawer-actions>.job-os-btn{padding-top:2px!important}") == -.5, tag
    for sel, undo in (
        (".apply-step [data-job-os-action=job-tailor]", ".apply-step button.job-os-btn{padding-top:2px!important}"),
        (".apply-step [data-job-os-action=board-apply]", ".apply-step [data-job-os-action=board-apply]{padding-bottom:0!important}"),
    ):
        if not page.query_selector(sel):
            continue
        page.eval_on_selector(sel, "e => e.scrollIntoView({block: 'center'})")
        page.wait_for_timeout(200)
        assert _moved(page, sel, "text", undo) == -.5, sel
    page.eval_on_selector("#fxDraft", "e => e.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(200)
    assert _moved(page, "#fxDraft", "text", ".follow-up .job-os-btn.small{padding:4px 10px 2px!important}") == -1
    page.eval_on_selector(".job-drawer-actions", "e => e.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(200)
    for sel in (".job-drawer-icons [aria-label='Open posting']", ".job-drawer-icons [data-job-os-action=job-form-edit]"):
        assert _moved(page, sel, "icon", ".job-drawer-icons .job-os-icon-btn>svg{top:0!important}") == .5, sel
    heights = page.evaluate("() => [...document.querySelectorAll('.job-drawer-actions>.job-os-btn, .follow-up .job-os-btn')].map(b => b.getBoundingClientRect().height)")
    assert len(set(heights[:-1])) == 1, heights  # the nudges changed no button's size


def test_match_card_has_as_much_room_below_to_the_next_text_as_above(jobs, seeded):
    page = jobs
    _open_job(page, seeded["applied"]["title"])
    out = page.evaluate("""() => { const r = e => e.getBoundingClientRect(); const card = document.querySelector('.job-drawer-body > .job-os-analysis');
      return {above: r(card).top - r(document.querySelector('.job-drawer-actions')).bottom, cardBottom: r(card).bottom}; }""")
    summary = ".job-drawer-body > .job-os-desc-wrap > summary"
    ink = _ink(page, summary, "text")
    below = ink["top"] - out["cardBottom"]
    assert abs(below - out["above"]) <= .5, (below, out)


# ── Resume Studio ───────────────────────────────────────────────────────────

def _insets(page, selector):
    """Distance from a card's inside edge to its nearest ink on each side, in CSS pixels."""
    box = _rect(page, selector)
    scale = page.evaluate("devicePixelRatio")
    clip = {"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"]}
    img = _shot(page, clip)
    bg = img.getpixel((int(24 * scale), int(3 * scale)))
    solid = img.copy()
    solid.paste(bg, (0, 0, img.width, img.height))
    diff = ImageChops.difference(img, solid).convert("L")
    inner = (int(3 * scale), int(3 * scale), img.width - int(3 * scale), img.height - int(3 * scale))
    mask = diff.crop(inner).point(lambda v: 255 if v >= 20 else 0)
    left, top, right, bottom = mask.getbbox()
    pad = 3
    return {"top": top / scale + pad, "left": left / scale + pad,
            "right": (mask.width - right) / scale + pad, "bottom": (mask.height - bottom) / scale + pad}


@pytest.fixture
def studio_with_gaps(jobs, seeded):
    page = jobs
    page.route("**/api/job-os/skill-gaps", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(GAPS)))
    _go(page, "resume-studio")
    page.wait_for_selector(".studio-item", timeout=15000)
    page.wait_for_selector(".gaps-grid", timeout=15000)
    page.wait_for_timeout(800)
    return page


def test_skill_gaps_and_tailored_versions_keep_the_same_room_on_every_side(studio_with_gaps):
    page = studio_with_gaps
    page.evaluate("""() => { const cards = [...document.querySelectorAll('.job-os-shell[data-view="resume-studio"] .job-os-card')];
      cards.find(c => c.matches('.skill-gaps')).id = 'fxGaps'; cards[cards.length - 1].id = 'fxTailored'; }""")
    for card in ("#fxGaps", "#fxTailored"):
        page.eval_on_selector(card, "e => e.scrollIntoView({block: 'center'})")
        page.wait_for_timeout(300)
        sides = _insets(page, card)
        assert max(sides.values()) - min(sides.values()) <= 1.5, (card, sides)


def test_page_ends_with_the_gap_that_separates_the_cards(studio_with_gaps):
    page = studio_with_gaps
    out = page.evaluate("""async () => { const r = e => e.getBoundingClientRect(); const main = document.getElementById('mainJobs');
      const cards = [...document.querySelectorAll('.job-os-shell[data-view="resume-studio"] .job-os-card')];
      const between = r(cards[cards.length - 1]).top - r(cards[cards.length - 2]).bottom;
      main.scrollTo({top: main.scrollHeight}); await new Promise(res => setTimeout(res, 400));
      return {between, below: Math.min(r(main).bottom, innerHeight) - r(cards[cards.length - 1]).bottom}; }""")
    assert abs(out["below"] - out["between"]) <= .5, out


# ── Settings ────────────────────────────────────────────────────────────────

def _settings(page):
    _go(page, "settings")
    page.wait_for_selector(".settings-layout .settings-nav-item", timeout=15000)
    page.wait_for_timeout(700)


def test_picking_a_settings_section_does_not_move_the_other_list_items(jobs):
    page = jobs
    _settings(page)
    moved = page.evaluate("""async () => { let n = 0; const nav = document.querySelector('.settings-rail .settings-nav');
      new MutationObserver(l => { n += l.filter(m => [...m.addedNodes, ...m.removedNodes].some(x => x.nodeType === 1 && x.matches('.settings-nav-item, .settings-nav-group'))).length; })
        .observe(nav, {childList: true});
      document.querySelectorAll('.settings-rail .settings-nav-item')[2].click();
      await new Promise(r => setTimeout(r, 600)); return n; }""")
    assert moved == 0, moved  # a node taken out of the page and put back restarts its transitions and flashes


def test_settings_panels_keep_the_same_margin_on_all_four_sides(jobs):
    page = jobs
    _settings(page)
    page.evaluate("() => { document.getElementById('mainJobs').scrollTop = 0; }")
    page.wait_for_timeout(300)
    out = page.evaluate("""() => { const r = e => e.getBoundingClientRect(); const q = s => document.querySelector(s);
      const rail = q('.settings-rail'), nav = q('.settings-rail .settings-nav'), page = q('.settings-page'), head = q('.job-os-content>.job-os-header'), main = r(q('#mainJobs'));
      const first = q('.settings-rail .settings-nav-group'), item = q('.settings-rail .settings-nav-item');
      return {railPad: getComputedStyle(rail).padding, navPad: getComputedStyle(nav).padding,
        railLeft: r(item).left - r(rail).left, railRight: r(rail).right - r(item).right - 1,
        pageLeft: r(head).left - r(rail).right, pageRight: main.right - r(page).right, headTop: r(head).top - main.top}; }""")
    ink = _ink(page, ".settings-rail .settings-nav-group", "text")
    rail = _rect(page, ".settings-rail")
    assert out["railPad"] == "24px" and out["navPad"] == "0px", out
    assert abs(out["railLeft"] - 24) <= .5 and abs(out["railRight"] - 24) <= .5, out
    assert abs(ink["top"] - rail["y"] - 24) <= 1, (ink, rail)
    assert abs(out["pageLeft"] - 24) <= .5 and abs(out["pageRight"] - 24) <= .5 and abs(out["headTop"] - 24) <= .5, out
