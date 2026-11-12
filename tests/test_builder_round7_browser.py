"""Create-project wizard, round 7: the Toolkit is chosen from the whole brief
(the brief plus the planner's questions and the user's answers), its Skills
table starts on "Recommended", and each pick says which words of the brief it
fits."""

import json

from tests import test_builder_steps_567_browser as t
from tests import test_project_builder_wizard_browser as wiz
from tests.test_builder_steps_567_browser import page  # noqa: F401  (fixture)


def _kit_with_reasons(page, sent):
    kit = json.loads(json.dumps(t.palb.KIT))
    kit["skills"] = [dict(s, fit=["booking"] if s["recommended"] else []) for s in t.SKILLS]
    for comp in kit["components"]["hero"]:
        comp["fit"] = ["landing"] if comp["recommended"] else []

    def toolkit(route):
        sent.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(json=kit)
    page.route("**/api/projects/starter/toolkit", toolkit)


def test_the_toolkit_is_asked_with_the_brief_and_the_answers(page):
    sent = []
    _kit_with_reasons(page, sent)
    t._to_kit(page)
    req = sent[-1]
    assert req["brief"] == "A boutique law firm site with service pages."
    # The planner's question and the answer the user kept (its recommendation).
    assert req["answers"] == [{"question": "Which stack?", "answer": "Astro"}], req["answers"]


def test_skills_start_on_recommended_and_picks_say_why(page):
    _kit_with_reasons(page, [])
    t._to_kit(page)
    sel = ".ps-kit-skillbar select"
    assert page.input_value(sel) == "picks"
    rows = page.eval_on_selector_all(".ps-kit-skill", "els => els.map(e => e.dataset.skill)")
    assert rows == [s["name"] for s in t.SKILLS if s["recommended"]], rows
    assert page.inner_text(".ps-kit-skill[data-skill=impeccable] .ps-kit-col-desc .ps-kit-fit") == "Fits your brief: booking"
    # Typing under Recommended searches every skill, not only the picks.
    page.fill(".ps-kit-skillbar input", "pdf")
    page.wait_for_function("() => [...document.querySelectorAll('.ps-kit-table:not(.ps-kit-ghost) .ps-kit-skill')].map(e => e.dataset.skill).join() === 'pdf'")
    page.fill(".ps-kit-skillbar input", "")
    # A recommended component card says why too.
    wiz.open_lib(page, "calm")
    assert "Fits your brief: landing" in page.inner_text(".ps-kit-comp[data-comp='calm/split']")
    # The brief calls for components here, so Recommended lists only those picks.
    cards = page.eval_on_selector_all(".ps-cz-sec[data-sec='lib:calm'] .ps-kit-comp", "els => els.map(e => e.dataset.comp)")
    assert cards == ["calm/split"], cards


def test_the_planners_needs_reach_the_toolkit_and_explain_a_pick(page):
    sent = []
    kit = json.loads(json.dumps(t.palb.KIT))
    kit["skills"] = [dict(s, needs=["Sign-in"] if s["name"] == "impeccable" else []) for s in t.SKILLS]
    for comp in kit["components"]["hero"]:
        comp["needs"] = ["Landing page"] if comp["recommended"] else []

    def toolkit(route):
        sent.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(json=kit)
    page.route("**/api/projects/starter/toolkit", toolkit)
    page.route("**/api/projects/starter/job*", lambda r: r.fulfill(json={"status": "done", "result": {
        "complete": False, "summary": "One thing left.", "questions": t.pol.QUESTIONS, "look": t.palb.LOOK,
        "needs": ["auth", "marketing"]}}))
    t._to_kit(page)
    assert sent[-1]["needs"] == ["auth", "marketing"]
    assert page.inner_text(".ps-kit-skill[data-skill=impeccable] .ps-kit-col-desc .ps-kit-fit") == "Your app needs: Sign-in"
    wiz.open_lib(page, "calm")
    assert "Your app needs: Landing page" in page.inner_text(".ps-kit-comp[data-comp='calm/split']")
