"""Create-project wizard: green finished steps, the step-number nudge, icon-on-top
template cards, the centred "Pick a template" line, and the brief drop zone."""

import pytest

from tests.test_chat_optical_alignment_browser import _open, browser  # noqa: F401


@pytest.fixture()
def real_2x(browser):
    # These checks are layout and behaviour, not font ink, so they run without Courier New.
    context, page = _open(browser, {"viewport": {"width": 1470, "height": 956}, "device_scale_factor": 2})
    yield page
    context.close()

TEMPLATES = {
    "templates": [
        {"key": "blank", "label": "Blank Project", "description": "Just the continuity files; shape it later.", "files": ["AGENTS.md"]},
        {"key": "web", "label": "Web App", "description": "Sites, dashboards and SaaS front ends.", "files": ["AGENTS.md", "README.md"]},
        {"key": "ios", "label": "iOS App", "description": "iPhone and iPad apps in Swift.", "files": ["AGENTS.md"]},
        {"key": "cli", "label": "CLI Tool", "description": "Command-line tools and automation scripts.", "files": ["AGENTS.md"]},
    ],
    "docs_agent": True,
    "planner": {"profile": "architecture", "label": "Architecture", "available": True},
}


def _to_template_step(page):
    page.route("**/api/workspaces", lambda route: route.fulfill(json={"workspaces": [{"name": "Home", "path": "/tmp/ws"}]}))
    page.route("**/api/projects/starter/templates", lambda route: route.fulfill(json=TEMPLATES))
    page.route("**/api/projects/starter/folders*", lambda route: route.fulfill(json={"folders": []}))
    page.evaluate("() => { window.__starter = _openProjectStarterWizard(); }")
    page.wait_for_selector(".ps-wizard .ps-choice")
    page.click(".ps-choice >> nth=0")
    page.click(".ps-next")
    page.click(".ps-tree-row >> nth=0")
    page.fill(".project-starter-field input", "demo")
    page.click(".ps-next")
    page.wait_for_selector(".ps-template")
    page.wait_for_timeout(450)


def test_finished_steps_are_green_and_current_numbers_sit_half_a_pixel_up(real_2x):
    page = real_2x
    _to_template_step(page)
    dots = page.evaluate("""() => [...document.querySelectorAll('.ps-wizard .ps-step')].map(step => {
      const dot = step.querySelector('.ps-step-dot'), s = getComputedStyle(dot);
      return {cls: step.className, bg: s.backgroundColor, pad: s.paddingBottom, sizing: s.boxSizing}; })""")
    success = page.evaluate("() => { const p = document.createElement('i'); p.style.color = 'var(--success)'; document.body.append(p); const c = getComputedStyle(p).color; p.remove(); return c; }")
    done = [d for d in dots if "is-done" in d["cls"]]
    current = [d for d in dots if "is-current" in d["cls"]]
    upcoming = [d for d in dots if "is-done" not in d["cls"] and "is-current" not in d["cls"]]
    assert len(done) == 2 and all(d["bg"] == success for d in done)
    # One pixel of bottom padding in a border-box circle lifts its number by half a pixel.
    assert all(d["pad"] == "1px" and d["sizing"] == "border-box" for d in done + current)
    assert upcoming and all(d["pad"] == "0px" for d in upcoming)


def test_template_icons_sit_on_top_centred_with_even_room_above_and_below(real_2x):
    page = real_2x
    _to_template_step(page)
    cards = page.evaluate("""() => [...document.querySelectorAll('.ps-wizard .ps-template')].map(card => {
      const c = card.getBoundingClientRect(), i = card.querySelector('.ps-template-icon').getBoundingClientRect(),
        l = card.querySelector('.ps-template-label').getBoundingClientRect();
      return {above: i.top - c.top, below: l.top - i.bottom, left: i.left - c.left, right: c.right - i.right}; })""")
    assert len(cards) == 4
    for card in cards:
        assert card["below"] >= 0, card  # the icon is above the title, not beside it
        assert abs(card["left"] - card["right"]) <= 1, card
        assert abs(card["above"] - card["below"]) <= 1.5, card
    tops = {round(c["above"], 1) for c in cards}
    assert len(tops) == 1  # every icon starts at the same height in its row


def test_pick_a_template_line_is_vertically_centred(real_2x):
    page = real_2x
    _to_template_step(page)
    gap = page.evaluate("""() => { const e = document.querySelector('.ps-files-empty').getBoundingClientRect(),
      f = document.querySelector('.ps-files').getBoundingClientRect(); return {top: e.top - f.top, bottom: f.bottom - e.bottom}; }""")
    assert abs(gap["top"] - gap["bottom"]) <= 1, gap


def test_a_brief_file_dropped_on_the_dashed_zone_fills_the_brief(real_2x):
    page = real_2x
    _to_template_step(page)
    page.click(".ps-template >> nth=1")
    page.click(".ps-next")
    page.wait_for_selector(".ps-dropzone")
    zone = page.evaluate("() => { const s = getComputedStyle(document.querySelector('.ps-dropzone')); return [s.borderTopStyle, s.borderRadius]; }")
    assert zone[0] == "dashed" and zone[1] != "0px"
    assert page.is_visible(".ps-dropzone button:text-is('Attach brief file')")
    lit = page.evaluate("""() => { const z = document.querySelector('.ps-dropzone'), dt = new DataTransfer();
      dt.items.add(new File(['x'], 'brief.md', {type: 'text/markdown'}));
      z.dispatchEvent(new DragEvent('dragover', {dataTransfer: dt, bubbles: true, cancelable: true}));
      return z.classList.contains('is-dragging'); }""")
    assert lit
    page.evaluate("""() => { const z = document.querySelector('.ps-dropzone'), dt = new DataTransfer();
      dt.items.add(new File(['# Brief\\nA habit tracker for nurses.'], 'brief.md', {type: 'text/markdown'}));
      z.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true})); }""")
    page.wait_for_function("() => document.querySelector('.ps-brief').value.includes('habit tracker')")
    assert "Using brief.md" in page.inner_text(".ps-dropzone")
    assert not page.evaluate("() => document.querySelector('.ps-dropzone').classList.contains('is-dragging')")
    # A file that is not a text brief is refused and the brief is left alone.
    page.evaluate("""() => { const z = document.querySelector('.ps-dropzone'), dt = new DataTransfer();
      dt.items.add(new File(['PNG'], 'shot.png', {type: 'image/png'}));
      z.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true})); }""")
    page.wait_for_timeout(100)
    assert "Only .md or .txt" in page.inner_text(".ps-dropzone")
    assert "habit tracker" in page.input_value(".ps-brief")
    # The planner named in the subtitle is the Architecture profile.
    assert "Architecture" in page.inner_text(".project-starter-header")


def test_provider_wizard_cards_keep_their_side_by_side_layout(real_2x):
    page = real_2x
    from tests.test_pages_round13_browser import PROVIDERS

    page.route("**/api/profiles/providers?*", lambda route: route.fulfill(json=PROVIDERS))
    page.evaluate("() => { window.__wizard = openProviderWizard('default', {}); }")
    page.wait_for_selector(".pw-choice")
    direction = page.evaluate("() => getComputedStyle(document.querySelector('.pw-choice')).flexDirection")
    assert direction == "row"
