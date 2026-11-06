"""Jobs pages, fourth round of requested spacing: Dashboard, Scout, Pipeline and Resume Studio.

Nudges are read as ink on a real 2x display with and without the rule being asked for, so
each number is how far the eye sees the thing move. Pieces a seeded server cannot show on
demand (counts, a file-based resume's Original button, a skill-gap report) are fixtures
dropped into the live page, styled by the same selectors the app's own markup uses.
"""

import json

import pytest

from tests.test_chat_optical_alignment_browser import _ink, browser, pytestmark, real_2x  # noqa: F401
from tests.test_job_os_page_polish_browser import _go, _mode, _open_job, seeded  # noqa: F401
from tests.test_office_notes_workhub_nudges_browser import _moved


@pytest.fixture
def jobs(real_2x, seeded):
    page = real_2x
    page.evaluate("async () => { await switchPanel('jobs'); }")
    page.wait_for_selector(".job-os-metrics:not(:has(.is-loading))", timeout=30000)
    page.wait_for_selector("#jobOsRoot .cal", timeout=15000)
    page.wait_for_timeout(600)
    return page


def _fixture(page, html, box="left:520px;top:300px;width:420px"):
    page.evaluate("""([html, box]) => { document.getElementById('fx')?.remove();
      document.querySelector('#jobOsRoot').insertAdjacentHTML('beforeend',
        `<div id="fx" style="position:fixed;${box};z-index:99999;background:#111">${html}</div>`); }""", [html, box])
    page.wait_for_timeout(120)


def _heads(page, section, extra="", count=5):
    _fixture(page, f'<section class="job-os-card {section}"><div class="job-os-card-head"><h2><span class="card-title">TITLE</span>'
                   f'<span class="job-os-count">{count}</span></h2>{extra}</div></section>')


# ── Dashboard ───────────────────────────────────────────────────────────────

def _replies_rows(page):
    return page.evaluate("""() => { const stat = document.querySelector('.cal[data-cal=replies] .cal-stat');
      return {tops: [...stat.children].map(c => Math.round(c.getBoundingClientRect().top)), height: stat.getBoundingClientRect().height}; }""")


def test_interviews_and_rejected_share_a_line_when_the_side_panel_is_closed_and_stack_when_open(jobs):
    page = jobs
    page.evaluate("() => toggleSidebar(false)")
    page.wait_for_timeout(900)
    opened = _replies_rows(page)
    assert opened["tops"][0] != opened["tops"][1], opened  # not enough room beside the panel
    page.evaluate("() => toggleSidebar(true)")
    page.wait_for_timeout(900)
    closed = _replies_rows(page)
    assert closed["tops"][0] == closed["tops"][1], closed
    page.evaluate("() => toggleSidebar(false)")


def test_card_title_counts_sit_a_pixel_higher_in_action_centre_and_new_matches_and_recent_loses_its_drop(jobs):
    page = jobs
    for section in ("action-centre", "match-inbox"):
        _heads(page, section)
        assert _moved(page, f"#fx .{section} .job-os-count", "text",
                      f"#fx .{section} .job-os-count{{padding-bottom:0!important}}", within=f"#fx .{section} .job-os-card-head") == -1, section
    _heads(page, "job-os-recent")
    assert _moved(page, "#fx .job-os-count", "text", "#fx .job-os-recent .job-os-count{padding-top:2px!important}",
                  within="#fx .job-os-card-head") == -1


def test_recent_jobs_cards_set_their_three_lines_half_a_pixel_higher(jobs):
    page = jobs
    card = "#jobOsRoot .job-os-recent .job-os-job-card:first-child"
    page.wait_for_selector(card)
    undo = f"{card}>.job-os-job-main{{top:0!important}}"
    page.eval_on_selector(card, "e => e.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(250)
    for part in (".job-os-job-main strong", ".job-os-job-main>span:not(.job-os-chips)", ".job-os-chip"):
        assert _moved(page, f"{card} {part}", "text", undo, within=card) == -.5, part


def test_pipeline_list_cards_set_their_three_lines_half_a_pixel_higher(jobs):
    page = jobs
    _go(page, "pipeline")
    _mode(page, "list")
    card = "#jobOsRoot .job-os-list>.job-os-job-card:first-child"
    page.wait_for_selector(card)
    page.eval_on_selector(card, "e => e.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(250)
    undo = f"{card}>.job-os-job-main{{top:0!important}}"
    for part in (".job-os-job-main strong", ".job-os-job-main>span:not(.job-os-chips)"):
        assert _moved(page, f"{card} {part}", "text", undo, within=card) == -.5, part


# ── Scout ───────────────────────────────────────────────────────────────────

def test_mark_all_seen_label_sits_level_between_its_buttons_edges(jobs):
    page = jobs
    _heads(page, "match-inbox", '<div class="card-head-actions"><button type="button" class="job-os-btn primary" id="fxSeen">Mark all seen</button></div>')
    undo = "#fx .match-inbox .card-head-actions .job-os-btn{padding:6px 12px 2px!important}"
    assert _moved(page, "#fxSeen", "text", undo) == -2  # 2px higher than the original (round 4 took it 2.5, round 5 gave half back)
    box = page.eval_on_selector("#fxSeen", "e => { const r = e.getBoundingClientRect(); return [r.top, r.bottom]; }")
    ink = _ink(page, "#fxSeen", "text")
    assert abs((ink["top"] - box[0]) - (box[1] - ink["bottom"])) <= 1, (box, ink)


def test_job_details_buttons_read_a_pixel_lower_open_postings_icon_and_ive_applied_return_to_the_old_height(jobs, seeded):
    page = jobs
    _open_job(page, f"Analyzed {seeded['marker']}")
    buttons = page.locator(".job-drawer-actions>.job-os-btn")
    assert buttons.count() >= 3
    undo = "#jobOsRoot .job-drawer-actions>.job-os-btn{padding-top:0!important}#jobOsRoot .apply-step .job-os-btn{padding-top:0!important}"
    for n in range(buttons.count()):
        # Round 6 raised the labels half a pixel; round 7 lowered Resume Studio, Applied and Rescore again.
        again = page.eval_on_selector(f".job-drawer-actions>.job-os-btn:nth-of-type({n + 1})", "e => ['studio-open', 'board-apply', 'job-analyze'].includes(e.dataset.jobOsAction)")
        assert _moved(page, f".job-drawer-actions>.job-os-btn:nth-of-type({n + 1})", "text", undo) == (1 if again else .5), n
    page.eval_on_selector(".apply-kit", "e => e.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(250)
    assert _moved(page, ".apply-step [data-job-os-action='apply-kit']", "text", undo) == 1  # raised in round 6, back in round 7
    assert _moved(page, ".apply-step a.job-os-btn", "text", undo) == 1.5  # 1px in round 4, half a pixel more in round 7
    # Open posting's icon: round 4 held it where it was (-1px against the label's +1), round 5 lets it drop 1px.
    assert _moved(page, ".apply-step a.job-os-btn", "icon", "#jobOsRoot .apply-step a.job-os-btn>:is(svg,img){position:relative;top:-1px!important}") == .5  # the undo keeps round 7's extra half pixel of padding; the icon's own top:-.5px takes it back, so against round 5 it has not moved
    # I've applied reads 1px higher again, back where it was before the round-4 drop, and half a pixel lower in round 8.
    assert _moved(page, ".apply-step [data-job-os-action='board-apply']", "text", undo) == .5


# ── Pipeline ────────────────────────────────────────────────────────────────

def test_search_box_runs_on_to_the_add_button(jobs):
    page = jobs
    _go(page, "pipeline")
    page.wait_for_selector(".pipe-toolbar .pipe-add-btn")
    gap = page.evaluate("""() => document.querySelector('.pipe-add-btn').getBoundingClientRect().left
                                 - document.querySelector('.pipe-search').getBoundingClientRect().right""")
    assert gap == 10, gap  # the toolbar's own gap, nothing left over


def _match_check(page, seeded):
    _go(page, "pipeline")
    _mode(page, "match")
    page.wait_for_selector(".match-card .match-actions", timeout=15000)
    page.wait_for_selector(".match-detail .dim-bars, .match-detail .job-os-card-note", timeout=15000)
    page.wait_for_timeout(600)


def test_match_check_placeholders_keep_the_height_the_words_have(jobs, seeded):
    page = jobs
    _match_check(page, seeded)
    held = []
    page.route("**/api/job-os/jobs/*", lambda route: held.append(route) if route.request.method == "GET" else route.fallback())
    box = lambda: page.evaluate("() => document.querySelector('.match-detail').getBoundingClientRect().height")
    loaded = box()
    page.evaluate("() => document.querySelector('[data-job-os-action=match-go]:not([disabled]):last-of-type').click()")
    page.wait_for_selector(".match-skeleton", timeout=5000)
    page.wait_for_timeout(300)
    during = box()
    for route in held:
        route.continue_()
    page.wait_for_function("() => !document.querySelector('.match-skeleton')", timeout=10000)
    after = box()
    assert abs(during - loaded) <= 1, (loaded, during, after)
    assert abs(after - during) <= 1, (loaded, during, after)


def test_match_check_button_nudges_and_automate_icon(jobs, seeded):
    page = jobs
    _match_check(page, seeded)
    bar = ".match-actions"
    undo = (f"{bar} .job-os-btn{{padding-bottom:0!important;top:0!important}}"
            f"{bar} [data-job-os-action=match-tailor]{{padding-bottom:4px!important}}")
    tailor = f"{bar} [data-job-os-action='match-tailor']"
    # Tailor & next: label and icon 1px lower (and the button's own drop of 1px); Score again and Open job: labels
    # 1px higher inside buttons that sit 1px lower, so they do not move.
    # Round 5 then set all three labels 0.5px lower (measured against round 4's own rules); the
    # Tailor & next icon stays where it was.
    prev = (f"{bar} .job-os-btn{{padding-bottom:2px!important}}{bar} [data-job-os-action=match-tailor]>svg{{top:1px!important}}")
    assert _moved(page, f"{tailor} span", "text", prev) == .5
    assert _moved(page, tailor, "icon", prev) == 0
    assert _moved(page, f"{bar} [data-job-os-action='match-score']", "text", prev) == .5
    assert _moved(page, f"{bar} .job-os-btn:last-child", "text", prev) == .5
    # and against the original rules, the labels are 1px lower than before round 4's nudge
    assert _moved(page, f"{tailor} span", "text", undo) == 2.5
    assert _moved(page, f"{bar} .job-os-btn:last-child", "text", undo) == .5
    drop = page.evaluate("() => document.querySelector('.match-actions .job-os-btn').getBoundingClientRect().top")
    handle = page.add_style_tag(content=undo)
    page.wait_for_timeout(150)
    assert drop - page.evaluate("() => document.querySelector('.match-actions .job-os-btn').getBoundingClientRect().top") == 1
    handle.evaluate("e => e.remove()")
    assert _moved(page, "[data-job-os-action=automate-all]", "icon", ".match-card [data-job-os-action=automate-all] .mx-icon{top:1px!important}") == -.5


def test_match_check_description_has_as_much_room_below_as_above(jobs, seeded):
    page = jobs
    _match_check(page, seeded)
    above, below = page.evaluate("""() => { const r = s => document.querySelector(s).getBoundingClientRect();
      return [r('.match-body').top - r('.match-progress').bottom, r('.match-actions').top - r('.match-body').bottom]; }""")
    assert above == below, (above, below)


# ── Resume Studio ───────────────────────────────────────────────────────────

@pytest.fixture
def studio(jobs):
    page = jobs
    _go(page, "resume-studio")
    page.wait_for_selector(".resume-master", timeout=15000)
    page.wait_for_selector(".studio-item", timeout=15000)
    page.wait_for_timeout(600)
    return page


def test_original_replace_and_manage_skills_read_half_a_pixel_lower(studio):
    page = studio
    page.evaluate("""() => document.querySelector('.resume-master .card-head-actions').insertAdjacentHTML('afterbegin',
      '<a class="job-os-btn" id="fxOriginal" href="#"><svg width="16" height="16" viewBox="0 0 16 16"><path d="M2 8h12" stroke="currentColor"/></svg>Original</a>')""")
    page.wait_for_timeout(120)
    undo = ".job-os-shell .resume-master .card-head-actions .job-os-btn{padding-top:0!important}"
    assert _moved(page, "#fxOriginal", "text", undo) == .5
    assert _moved(page, "#fxOriginal", "icon", undo) == .5
    assert _moved(page, "[data-job-os-action=resume-replace]", "text", undo) == .5
    if page.query_selector("[data-job-os-action=skills-manage]"):
        assert _moved(page, "[data-job-os-action=skills-manage]", "text",
                      ".job-os-shell .skills-gained .card-head-actions .job-os-btn{padding-top:0!important}") == .5


def test_skills_gained_count_reads_half_a_pixel_higher(studio):
    _heads(studio, "skills-gained", count=3)
    assert _moved(studio, "#fx .job-os-count", "text", "#fx .skills-gained .job-os-count{padding-bottom:0!important}",
                  within="#fx .job-os-card-head") == -.5


def test_gap_filters_space_their_options_evenly(studio):
    page = studio
    page.evaluate("() => { document.querySelector('.gaps-controls').scrollIntoView({block: 'center'}); }")
    page.wait_for_selector(".gaps-controls .themed-select-trigger")
    for trigger in range(2):
        page.locator(".gaps-controls .themed-select-trigger").nth(trigger).click()
        page.wait_for_selector(".themed-select-popup.is-spaced .themed-select-option")
        page.wait_for_timeout(250)
        out = page.evaluate("""() => { const pop = document.querySelector('.themed-select-popup.is-spaced');
          const opts = [...pop.querySelectorAll('.themed-select-option')].map(o => o.getBoundingClientRect());
          const box = pop.getBoundingClientRect(), cs = getComputedStyle(pop);
          return {above: opts[0].top - box.top - parseFloat(cs.borderTopWidth),
                  below: box.bottom - parseFloat(cs.borderBottomWidth) - opts[opts.length - 1].bottom,
                  between: opts.slice(1).map((r, i) => r.top - opts[i].bottom)}; }""")
        assert all(abs(gap - out["above"]) <= 1 for gap in out["between"] + [out["below"]]), out
        page.keyboard.press("Escape")
        page.wait_for_timeout(250)


REPORT = {"skill_gaps": {"running": False, "error": "", "reports": [{
    "id": "r1", "jobs": 12, "scope": {}, "created_at": 1793356355, "since_last": None,
    "gaps": [{"label": "Cloud detection", "gap": 7}, {"label": "CISSP", "gap": 4}],
    "themes": [{"name": "Cloud", "why": "Most roles want it."}], "plan": [{"step": "Study for CISSP", "detail": "Twelve weeks."}]}]}}


def test_plan_sits_below_frequent_gaps_and_themes_in_one_column(jobs, seeded):
    page = jobs
    page.route("**/api/job-os/skill-gaps", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(REPORT)))
    _go(page, "resume-studio")
    page.wait_for_selector(".gaps-grid", timeout=15000)
    page.wait_for_timeout(400)
    out = page.evaluate("""() => { const grid = document.querySelector('.gaps-grid');
      const [gaps, themes, plan] = [...grid.children].map(c => c.getBoundingClientRect()); const box = grid.getBoundingClientRect();
      return {gaps, themes, plan, box}; }""")
    assert out["themes"]["left"] > out["gaps"]["left"], out  # the two stay side by side
    assert out["plan"]["top"] >= max(out["gaps"]["bottom"], out["themes"]["bottom"]), out
    assert abs(out["plan"]["left"] - out["box"]["left"]) <= 1 and abs(out["plan"]["right"] - out["box"]["right"]) <= 1, out


def test_tailored_versions_chip_and_status_share_a_height_and_sit_lower(studio):
    page = studio
    page.evaluate("""() => { const tags = document.querySelector('.studio-item .studio-item-tags');
      tags.insertAdjacentHTML('afterbegin', '<span class="job-os-chip muted" id="fxKeywords">80% keywords</span>'); }""")
    page.wait_for_timeout(150)
    chip, status = "#fxKeywords", ".studio-item .doc-status"
    heights = page.evaluate("""([a, b]) => [a, b].map(s => document.querySelector(s).getBoundingClientRect().height)""", [chip, status])
    assert heights[0] == heights[1], heights
    undo = "#jobOsRoot .studio-item .studio-item-tags>:is(.job-os-chip,.doc-status){top:0!important}"
    assert _moved(page, status, "text", undo + "#jobOsRoot .studio-item .studio-item-tags>.doc-status{padding:0 8px!important}") == 1  # the bubble's own half pixel, and half again for the label
    # keywords text: half a pixel for the bubble and half again for the text inside it
    both = (undo + "#jobOsRoot .studio-item .studio-item-tags>.job-os-chip{padding:1px 6px 2px!important;height:auto!important}")
    assert _moved(page, chip, "text", both) == 1
