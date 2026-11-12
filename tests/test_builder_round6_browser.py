"""Create-project wizard, round 6: Build summary with even margins, transparent
tool swatches, Colours after Cards & spacing, Next waits for every section, and
the Toolkit's Chosen list (text only, Skills and Components) at the end."""

from tests import test_builder_steps_567_browser as t
from tests import test_project_builder_wizard_browser as wiz
from tests.builder_nav import finish_sections
from tests.test_builder_steps_567_browser import page  # noqa: F401  (fixture)

MARGINS = """() => { const main = document.querySelector('.ps-main'), b = document.querySelector('.ps-build').getBoundingClientRect(),
  d = document.querySelector('.project-starter-dialog'), dr = d.getBoundingClientRect(), pad = parseFloat(getComputedStyle(d).paddingRight),
  m = main.getBoundingClientRect(), line = m.right - parseFloat(getComputedStyle(main, '::after').right),
  top = main.previousElementSibling.getBoundingClientRect().bottom, foot = document.querySelector('.ps-actions').getBoundingClientRect().top;
  return [b.top - top, foot - b.bottom, b.left - line, dr.right - pad - b.right + pad].map(v => Math.round(v)); }"""


def test_the_build_summary_has_the_same_margin_on_every_side(page):
    page.set_viewport_size({"width": 1280, "height": 900})
    t._to_look(page)
    top, bottom, left, right = page.evaluate(MARGINS)
    assert max(top, bottom, left, right) - min(top, bottom, left, right) <= 1, (top, bottom, left, right)


def test_tool_swatches_are_transparent_and_colours_follow_cards_and_spacing(page):
    t._to_look(page)
    order = page.eval_on_selector_all(".ps-cz-sec", "els => els.map(e => e.dataset.sec)")
    assert order == ["style", "type", "buttons", "surfaces", "colours", "motion", "built"], order
    wiz.open_section(page, "colours")
    for card in ("logo", "custom"):
        sw = f".ps-pal-card[data-pal={card}] .ps-pal-swatch-tool"
        bg = page.eval_on_selector(sw, "e => getComputedStyle(e).backgroundImage")
        assert "conic-gradient" in bg, bg  # the checkerboard "no colour" look
        assert page.eval_on_selector(f"{sw} > svg", "e => getComputedStyle(e).top") == "1px"


def test_toolkit_next_waits_for_every_section_and_chosen_lists_skills_and_components_last(page):
    t._to_kit(page)
    assert page.is_disabled(".ps-next")
    # Chosen is the last block, text chips only, under Skills and Components headings.
    last = page.evaluate("() => { const kids = [...document.querySelector('.ps-kit .ps-cz').children].filter(e => !e.classList.contains('ps-cz-progress')); return kids[kids.length - 1].className; }")
    assert "ps-kit-tray" in last, last
    heads = page.eval_on_selector_all(".ps-kit-tray-group:not(.is-empty) .ps-kit-tray-cat > span:first-child", "els => els.map(e => e.textContent)")
    assert heads == ["Skills", "Components"], heads
    assert page.locator(".ps-kit-tray img, .ps-kit-tray-thumb").count() == 0
    skills = page.eval_on_selector_all(".ps-kit-tray-group[data-kind=skills] .ps-kit-tray-chip", "els => els.map(e => e.dataset.skill)")
    ticked = page.eval_on_selector_all(".ps-kit-skill.is-selected", "els => els.map(e => e.dataset.skill)")
    assert skills == ticked and skills, (skills, ticked)
    # Removing a skill from Chosen unticks its row.
    page.click(f".ps-kit-tray-chip[data-skill='{skills[0]}'] .ps-kit-tray-x")
    assert page.get_attribute(f".ps-kit-skill[data-skill='{skills[0]}'] [role=checkbox]", "aria-checked") == "false"
    finish_sections(page)
    page.wait_for_function("() => !document.querySelector('.ps-next').disabled")
