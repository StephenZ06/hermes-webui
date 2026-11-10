"""Fourth pass on the project builder: the brief review shows the planner's
latest step as one line, a reasoning card reaches its new height before its
new text shows, the Review step's terminal is black with window dots and the
skills table has a black header row, and scrollbars fade in and out."""

import pytest

from tests._pytest_port import BASE
from tests.test_builder_and_skills_polish_browser import QUESTIONS, _to_details, page, skills  # noqa: F401  (fixtures)
from tests.test_builder_review_and_scrollbars_browser import _to_review


def test_the_brief_review_shows_the_planners_latest_step_in_one_line(page):
    polls = {"n": 0}

    def job(route):
        polls["n"] += 1
        if polls["n"] == 1:
            return route.fulfill(json={"status": "running", "kind": "analysis", "progress": "Reading the brief"})
        if polls["n"] == 2:
            return route.fulfill(json={"status": "running", "kind": "analysis", "progress": "Weighing the stack for a law firm site with service pages, a contact form and a blog that the partners write themselves"})
        return route.fulfill(json={"status": "done", "result": {"complete": False, "summary": "", "questions": QUESTIONS}})

    page.unroute("**/api/projects/starter/job*")
    page.route("**/api/projects/starter/job*", job)
    page.evaluate("() => { window.__starter = _openProjectStarterWizard(); }")
    page.wait_for_selector(".ps-wizard .ps-choice")
    page.click(".ps-choice >> nth=0")
    page.click(".ps-next")
    page.click(".ps-tree-row >> nth=0")
    page.fill(".project-starter-field input", "lex")
    page.click(".ps-next")
    page.wait_for_selector(".ps-template")
    page.click(".ps-template >> text=Website")
    page.click(".ps-next")
    page.fill(".ps-wizard textarea", "A boutique law firm site with service pages.")
    page.click(".ps-next")
    page.wait_for_function("() => (document.querySelector('.ps-review-log')||{}).textContent === 'Reading the brief'")
    page.wait_for_function("() => (document.querySelector('.ps-review-log')||{}).textContent.startsWith('Weighing the stack')")
    line = page.evaluate("""() => { const l = document.querySelector('.ps-review-log'), cs = getComputedStyle(l);
      return {nowrap: cs.whiteSpace, clipped: l.scrollWidth > l.clientWidth, h: Math.round(l.getBoundingClientRect().height)}; }""")
    assert line["nowrap"] == "nowrap" and line["h"] <= 20, line
    page.wait_for_selector(".ps-option")


LONG = [{**QUESTIONS[0],
         "why": "Astro ships almost no JavaScript, which keeps a content site fast and simple to host. You give up some app-like interactivity.",
         "examples": ["The Guardian's Astro microsites", "Pairs with Netlify Forms"],
         "hows": ["", "A Next.js app router project with static export for the service pages and an API route for the form.", ""]}]


def test_the_reasoning_card_reaches_its_new_height_before_the_text_shows(page):
    page.unroute("**/api/projects/starter/job*")
    page.route("**/api/projects/starter/job*", lambda r: r.fulfill(json={"status": "done", "result": {"complete": False, "summary": "", "questions": LONG}}))
    _to_details(page)
    page.wait_for_timeout(500)
    frames = page.evaluate("""() => new Promise(res => { const w = document.querySelector('.ps-rec-why'), out = [], t0 = performance.now();
      const tick = () => { const t = w.querySelector('.ps-rec-why-text');
        out.push({h: w.getBoundingClientRect().height, o: t ? +getComputedStyle(t).opacity : 0});
        if (performance.now() - t0 < 1200) requestAnimationFrame(tick); else res(out); };
      requestAnimationFrame(tick); document.querySelectorAll('.ps-option')[1].click(); })""")
    final = frames[-1]["h"]
    hidden = next(i for i, f in enumerate(frames) if f["o"] < 0.05)  # the old text has gone
    shown = next(i for i, f in enumerate(frames) if i > hidden and f["o"] > 0.05)  # the new text appears
    assert abs(frames[0]["h"] - final) > 8, (frames[0], final)  # the card does change size
    assert all(abs(f["h"] - final) <= 1 for f in frames[shown:]), (final, frames[shown:])


def test_review_terminal_is_black_with_window_dots_and_the_skills_header_is_black(page):
    _to_review(page)
    look = page.evaluate("""() => { const cs = s => getComputedStyle(document.querySelector(s));
      return {term: cs('.ps-term').backgroundColor, dots: [...document.querySelectorAll('.ps-term-dots i')].map(i => getComputedStyle(i).backgroundColor),
              th: cs('.ps-review-table th').backgroundColor, thText: cs('.ps-review-table th').color}; }""")
    assert look["term"] == "rgb(10, 10, 10)", look
    assert look["dots"] == ["rgb(255, 95, 87)", "rgb(254, 188, 46)", "rgb(40, 200, 64)"], look
    assert look["th"] == "rgb(10, 10, 10)" and look["thText"] == "rgb(232, 232, 232)", look


def test_a_scrollbar_fades_in_as_a_scroll_starts_and_out_before_it_hides(skills):
    # Sampled every frame, so a slow machine only stretches the timeline.
    frames = skills.evaluate("""() => new Promise(res => { const list = document.getElementById('skillsList'), out = [], t0 = performance.now();
      const tick = () => { out.push({a: parseFloat(getComputedStyle(list).getPropertyValue('--sb-a')), on: list.classList.contains('is-scrolling')});
        if (performance.now() - t0 < 2500) requestAnimationFrame(tick); else res(out); };
      list.scrollTop = 120; requestAnimationFrame(tick); })""")
    full = next(i for i, f in enumerate(frames) if f["on"] and f["a"] == 1)
    assert any(0 < f["a"] < 1 for f in frames[:full]), frames[:full + 1]  # it rose through the middle
    off = next(i for i, f in enumerate(frames) if i > full and not f["on"])
    assert any(0 < f["a"] < 1 and f["on"] for f in frames[full:off]), frames[full:off + 1]  # and fell before the bar hid
    assert not frames[-1]["on"]
