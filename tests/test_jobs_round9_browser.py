"""Side panel titles, the Jobs Settings section list, number units, Replies and Application answers, ninth round.

Nudges are ink on a real 2x display with and without the rule being asked for, as in the earlier rounds.
"""

import pytest

from tests.test_chat_optical_alignment_browser import _ink, _rect, browser, pytestmark, real_2x  # noqa: F401
from tests.test_job_os_page_polish_browser import seeded  # noqa: F401
from tests.test_jobs_round4_browser import jobs  # noqa: F401
from tests.test_jobs_round7_browser import _section, settings  # noqa: F401
from tests.test_office_notes_workhub_nudges_browser import _moved, _panel


# ── Side panel titles ───────────────────────────────────────────────────────

TITLE = ".panel-view.active > .panel-head > span:first-child"


@pytest.mark.parametrize("name,old_translate", [("chat", "none"), ("skills", "none"), ("jobs", "none"), ("dashboard", "none"),
                                                ("tasks", "0 1px"), ("notes", "0 1px")])
def test_side_panel_titles_are_a_little_larger_and_a_pixel_lower(real_2x, name, old_translate):
    page = real_2x
    _panel(page, name)
    assert page.evaluate("s => getComputedStyle(document.querySelector(s)).fontSize", TITLE) == "12px"
    undo = f"{TITLE}{{font-size:11px!important;translate:{old_translate}!important}}"
    now = _ink(page, TITLE, "text")
    handle = page.add_style_tag(content=undo)
    page.wait_for_timeout(200)
    old = _ink(page, TITLE, "text")
    handle.evaluate("e => e.remove()")
    assert now["bottom"] - old["bottom"] == 1  # the baseline sits a pixel lower than it did


# ── Jobs Settings: section list ─────────────────────────────────────────────

def test_section_icons_are_smaller(settings):
    out = settings.evaluate("""() => [...document.querySelectorAll('.settings-nav-item')].map(item => {
      const icon = item.querySelector('.settings-nav-icon').getBoundingClientRect(); const svg = item.querySelector('.settings-nav-icon svg').getBoundingClientRect();
      return [icon.width, icon.height, svg.width, svg.height]; })""")
    assert out and all(box == [20, 20, 20, 20] for box in out), out


def test_every_section_has_the_same_room_above_and_below(settings):
    out = settings.evaluate("""() => { const r = e => e.getBoundingClientRect(); const rail = document.querySelector('.settings-rail');
      const blocks = [{top: r(rail.querySelector('.settings-rail-title')).bottom, bottom: r(rail.querySelector('.settings-rail-title')).bottom, name: 'title'}];
      for (const el of rail.querySelectorAll('.settings-nav-group, .settings-nav-item')) {
        if (el.classList.contains('settings-nav-group')) { const s = r(el.querySelector('span')); blocks.push({top: s.top, bottom: s.bottom, name: el.textContent.trim()}); }
        else { blocks.push({top: r(el.querySelector('strong')).top, bottom: r(el.querySelector('.settings-nav-hint')).bottom, name: el.dataset.section}); } }
      return blocks.map((b, i) => [b.name, i ? +(b.top - blocks[i - 1].bottom).toFixed(2) : 0]).slice(1); }""")
    gaps = [gap for _, gap in out]
    assert len(gaps) >= 10 and all(abs(gap - 18.5) <= .75 for gap in gaps), out  # item to item, heading to item, item to heading, title to heading


# ── Number boxes ────────────────────────────────────────────────────────────

def test_a_unit_is_bold_and_has_as_much_room_to_its_box_as_to_the_cards_edge(settings):
    page = settings
    _section(page, "notifications")
    rows = page.evaluate("""() => [...document.querySelectorAll('.set-number')].map((n, i) => { n.querySelector('em').id = 'fxUnit' + i;
      const g = n.closest('.set-group').getBoundingClientRect(); return {text: n.querySelector('em').textContent, weight: getComputedStyle(n.querySelector('em')).fontWeight,
        boxRight: n.querySelector('input').getBoundingClientRect().right, edge: g.right, id: 'fxUnit' + i}; })""")
    assert [r["text"] for r in rows] == ["%", "matches", ":    00", ":    00"], rows
    for row in rows:
        assert row["weight"] == "700", row
        ink = _ink(page, "#" + row["id"], "text")
        left, right = ink["left"] - row["boxRight"], row["edge"] - ink["right"]
        assert abs(left - right) <= 1.5, (row["text"], left, right)
        assert min(left, right) >= 20, (row["text"], left, right)


# ── Replies ─────────────────────────────────────────────────────────────────

def test_the_replies_status_line_sits_level_with_its_buttons_in_one_row(settings):
    page = settings
    _section(page, "notifications")
    page.evaluate("() => { document.querySelector('.job-os-notify-status > p').id = 'fxStatus'; }")
    box = _rect(page, ".job-os-notify-status")
    ink = _ink(page, "#fxStatus", "text")
    label = _ink(page, "[data-job-os-action='notify-check']", "text")
    assert box["height"] <= 60, box  # one row, no empty space under the text
    assert abs((ink["top"] + ink["bottom"]) / 2 - (label["top"] + label["bottom"]) / 2) <= .75, (ink, label)


@pytest.mark.parametrize("action", ["notify-check", "notify-outcomes"])
def test_check_replies_now_and_check_now_read_half_a_pixel_lower(settings, action):
    page = settings
    _section(page, "notifications")
    sel = f"[data-job-os-action='{action}']"
    page.eval_on_selector(sel, "e => e.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(250)
    assert _moved(page, sel, "text", f".settings-page .set-group .job-os-btn.small{sel}{{padding-top:0!important}}") == .5


# ── Application answers ─────────────────────────────────────────────────────

def test_anything_else_to_mention_runs_out_to_the_cards_margin_and_has_equal_room_above_and_below(settings):
    page = settings
    _section(page, "apply")
    page.evaluate("() => { document.querySelector('.set-row.is-stack .set-row-label').id = 'fxOther'; }")
    out = page.evaluate("""() => { const ta = document.querySelector('textarea[data-setting="apply.other"]'); const row = ta.closest('.set-row'); const g = row.closest('.set-group').getBoundingClientRect();
      const t = ta.getBoundingClientRect(); return {left: t.left - g.left, right: g.right - t.right, top: t.top, rowTop: row.getBoundingClientRect().top}; }""")
    assert abs(out["left"] - 12) <= .5 and abs(out["right"] - 12) <= .5, out
    ink = _ink(page, "#fxOther", "text")
    above, below = ink["top"] - out["rowTop"], out["top"] - ink["bottom"]
    assert abs(above - below) <= .75, (above, below)
