"""Create-project wizard, round 5: Typography before Colours with the colour
previews in the chosen typeface and size, the skills header row centred, and a
larger component preview that can choose the component."""

from tests import test_builder_steps_567_browser as t
from tests import test_project_builder_wizard_browser as wiz
from tests.test_builder_steps_567_browser import page  # noqa: F401  (fixture)

MOCK_TEXT = [".ps-pal-brand", ".ps-pal-hero strong", ".ps-pal-hero > span", ".ps-pal-btn.is-primary", ".ps-pal-tag", ".ps-pal-field"]


def _fonts(page, theme):
    return page.evaluate("""([theme, sels]) => sels.map(s => getComputedStyle(
        document.querySelector(`.ps-pal-pane[data-theme=${theme}] ${s}`)).fontFamily)""", [theme, MOCK_TEXT])


def test_colour_previews_use_the_typeface_and_size_chosen_just_before(page):
    t._to_look(page)
    order = page.eval_on_selector_all(".ps-cz-sec", "els => els.map(e => e.dataset.sec)")
    assert order.index("type") < order.index("colours"), order
    wiz.open_section(page, "type")
    page.click(".ps-cz-opt[data-key=font][data-value=slab]")
    page.click(".ps-cz-opt[data-key=scale][data-value=large]")
    wiz.open_section(page, "colours")
    for theme in ("light", "dark"):
        fonts = _fonts(page, theme)
        # Every piece of text in both previews has one typeface: the chosen one.
        assert len(set(fonts)) == 1 and "Rockwell" in fonts[0], (theme, fonts)
    size = page.eval_on_selector(".ps-pal-pane[data-theme=light] .ps-pal-hero strong", "e => getComputedStyle(e).fontSize")
    assert size == "16px", size


def test_the_skills_header_row_is_centred(page):
    t._to_kit(page)
    aligns = page.eval_on_selector_all(".ps-kit-table:not(.ps-kit-ghost) thead th", "els => els.map(e => getComputedStyle(e).textAlign)")
    assert aligns and set(aligns) == {"center"}, aligns


def test_a_component_opens_a_larger_preview_that_can_choose_it(page):
    t._to_kit(page)
    wiz.open_lib(page, "calm")
    cell = ".ps-cz-sec[data-sec='lib:calm'] .ps-kit-cell"
    first = page.eval_on_selector(f"{cell} .ps-kit-comp", "e => e.dataset.comp")
    was = page.get_attribute(f".ps-kit-comp[data-comp='{first}']", "aria-pressed")
    page.hover(f"{cell} .ps-kit-comp")
    page.click(f"{cell} .ps-kit-peek")
    pop = page.locator(".ps-kit-peekpop")
    page.wait_for_function("() => document.querySelector('.ps-kit-peekpop').matches(':popover-open')")
    name = page.inner_text(f".ps-kit-comp[data-comp='{first}'] .ps-kit-name")
    assert pop.locator(".ps-kit-peek-name").inner_text() == name
    assert ".loop.webp" in pop.locator(".ps-kit-peek-media img").get_attribute("src")
    # The popover fits the viewport.
    box = pop.bounding_box()
    vw, vh = page.evaluate("() => [innerWidth, innerHeight]")
    assert box["x"] >= 0 and box["y"] >= 0 and box["x"] + box["width"] <= vw and box["y"] + box["height"] <= vh, box
    # Choose there toggles the card too.
    pop.locator(".ps-kit-peek-pick").click()
    now = page.get_attribute(f".ps-kit-comp[data-comp='{first}']", "aria-pressed")
    assert now != was and pop.locator(".ps-kit-peek-pick").get_attribute("aria-pressed") == now
    # Escape closes it and gives focus back to the button that opened it.
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.querySelector('.ps-kit-peekpop').matches(':popover-open')")
    assert page.evaluate("() => document.activeElement.classList.contains('ps-kit-peek')")
