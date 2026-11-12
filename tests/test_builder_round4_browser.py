"""Create-project wizard, round 4: one Components section per library with its own
search box and category select (Recommended first), eight typefaces, chosen
skills shown by their tick alone, and folded sections that skip rendering."""

import json

from tests import test_builder_steps_567_browser as t
from tests import test_project_builder_palette_browser as palb
from tests import test_project_builder_wizard_browser as wiz
from tests.test_builder_steps_567_browser import page  # noqa: F401  (fixture)

ROLES = ["navigation", "cards", "forms", "loaders"]


def _big_kit(page):
    kit = json.loads(json.dumps(palb.KIT))
    kit["skills"] = t.SKILLS
    comps = {}
    for lib, name in [("alpha", "Alpha UI"), ("beta", "Beta UI")]:
        for i in range(20):
            role = ROLES[i % 4]
            comps.setdefault(role, []).append({
                "library": lib, "library_name": name, "slug": f"c{i}", "name": f"{name} item {i}", "role": role,
                "style": ["minimal"], "motion": "subtle", "kind": "copy-paste", "license": "MIT",
                "score": 3 if i < 10 else 0, "recommended": i == 0, "preview": None, "loop": None})
    kit["components"] = comps
    page.unroute("**/api/projects/starter/toolkit")
    page.route("**/api/projects/starter/toolkit", lambda r: r.fulfill(json=kit))


def _cards(page, lib):
    return page.eval_on_selector_all(f".ps-cz-sec[data-sec='lib:{lib}'] .ps-kit-comp", "els => els.map(e => e.dataset.comp)")


def test_each_library_is_its_own_section_with_search_and_a_category_select(page):
    _big_kit(page)
    t._to_kit(page)
    titles = page.eval_on_selector_all(".ps-cz-sec .ps-cz-title", "els => els.map(e => e.textContent)")
    assert titles == ["Skills", "Components 1/2 · Alpha UI", "Components 2/2 · Beta UI"], titles
    wiz.open_lib(page, "alpha")
    sel = ".ps-cz-sec[data-sec='lib:alpha'] .ps-kit-libselect select"
    labels = page.eval_on_selector_all(f"{sel} option", "els => els.map(e => e.textContent)")
    assert labels == ["Recommended (8)", "All (20)", "Navigation (5)", "Cards (5)", "Forms & buttons (5)", "Loading (5)"], labels
    # Recommended: at most eight, the starred one first.
    rec = _cards(page, "alpha")
    assert len(rec) == 8 and rec[0] == "alpha/c0", rec
    page.select_option(sel, "loaders")
    page.wait_for_function("() => document.querySelectorAll(\".ps-cz-sec[data-sec='lib:alpha'] .ps-kit-comp\").length === 5")
    assert all(int(c.split("c")[-1]) % 4 == 3 for c in _cards(page, "alpha"))
    page.select_option(sel, "all")
    page.wait_for_function("() => document.querySelectorAll(\".ps-cz-sec[data-sec='lib:alpha'] .ps-kit-comp\").length === 20")
    heads = page.eval_on_selector_all(".ps-cz-sec[data-sec='lib:alpha'] .ps-kit-cat-head > span:first-child", "els => els.map(e => e.textContent)")
    assert heads == ["Navigation", "Cards", "Forms & buttons", "Loading"], heads
    # Search narrows this library only.
    page.fill(".ps-cz-sec[data-sec='lib:alpha'] .ps-kit-libsearch input", "item 13")
    page.wait_for_function("() => document.querySelectorAll(\".ps-cz-sec[data-sec='lib:alpha'] .ps-kit-comp\").length === 1")
    assert _cards(page, "alpha") == ["alpha/c13"]
    assert len(_cards(page, "beta")) == 8


def test_typography_offers_eight_typefaces_in_rows_of_four_that_reach_create(page):
    t._to_look(page)
    wiz.open_section(page, "type")
    fonts = page.eval_on_selector_all(".ps-cz-opt[data-key=font]", "els => els.map(e => e.dataset.value)")
    assert fonts == ["sans", "serif", "geometric", "mono", "humanist", "slab", "rounded", "condensed"], fonts
    tops = page.eval_on_selector_all(".ps-cz-opt[data-key=font]", "els => els.map(e => Math.round(e.getBoundingClientRect().top))")
    assert len(set(tops[:4])) == 1 and len(set(tops[4:])) == 1 and tops[4] > tops[0], tops
    page.click(".ps-cz-opt[data-key=font][data-value=slab]")
    assert page.get_attribute(".ps-customize", "data-cz-font") == "slab"


def test_a_chosen_skill_row_has_no_fill_and_folded_sections_skip_rendering(page):
    t._to_kit(page)
    row = page.locator(".ps-kit-skill.is-selected").first
    page.mouse.move(0, 0)
    assert row.evaluate("e => getComputedStyle(e).backgroundColor") in ("rgba(0, 0, 0, 0)", "transparent")
    assert row.locator(".ps-kit-check.is-on").count() == 1
    # The Components sections are folded: their content is not rendered.
    vis = page.eval_on_selector_all(".ps-cz-sec[data-sec^='lib:'] .ps-cz-inner", "els => els.map(e => getComputedStyle(e).contentVisibility)")
    assert vis and set(vis) == {"hidden"}, vis
    assert page.eval_on_selector(".ps-cz-sec[data-sec=skills] .ps-cz-inner", "e => getComputedStyle(e).contentVisibility") == "visible"
