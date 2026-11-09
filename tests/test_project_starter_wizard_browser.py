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


def _to_template_step(page, templates=TEMPLATES):
    page.route("**/api/workspaces", lambda route: route.fulfill(json={"workspaces": [{"name": "Home", "path": "/tmp/ws"}]}))
    page.route("**/api/projects/starter/templates", lambda route: route.fulfill(json=templates))
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


QUESTIONS = {"status": "done", "result": {"complete": False, "summary": "A shop", "questions": [{
    "id": "stack", "question": "Which stack?", "options": ["Next.js", "Django", "Rails"],
    "details": ["React with server rendering", "Python, batteries included", ""],
    "other": "Other stack (type it)", "recommended": "Next.js",
    "why": "Server rendering keeps product pages fast and indexable.",
    "examples": ["Vercel deploys it in one step", "Stripe has a ready Next.js starter"]}]}}


def _to_details_step(page):
    _to_template_step(page)
    page.route("**/api/projects/starter/analyze", lambda route: route.fulfill(json={"job_id": "j1"}))
    page.route("**/api/projects/starter/job?*", lambda route: route.fulfill(json=QUESTIONS))
    page.click(".ps-template >> nth=1")
    page.click(".ps-next")
    page.fill(".ps-brief", "An online candle shop.")
    page.click(".ps-next")
    page.wait_for_selector(".ps-options")


def test_details_step_types_the_fourth_answer_in_place_and_explains_the_pick(real_2x):
    page = real_2x
    _to_details_step(page)
    assert page.locator(".ps-other").count() == 0  # no separate "type your own" box below
    keys = page.evaluate("() => [...document.querySelectorAll('.ps-options .ps-option-key img')].map(i => new URL(i.src).pathname)")
    assert keys == [f"/static/wizard/key-{n}.png" for n in range(1, 5)]
    assert page.evaluate("() => [...document.querySelectorAll('.ps-options .ps-option-key img')].every(i => i.complete && i.naturalWidth > 0)")
    field = page.locator(".ps-options .ps-option-typed input")
    assert field.get_attribute("placeholder") == "Other stack (type it)"
    assert "React with server rendering" in page.inner_text(".ps-options")
    why = page.inner_text(".ps-rec-why")
    assert "Why Next.js" in why and "indexable" in why and "Stripe has a ready Next.js starter" in why

    field.click()
    page.wait_for_timeout(250)  # the placeholder fades out over 150ms
    assert page.evaluate("() => document.activeElement.classList.contains('ps-option-input')")
    # The placeholder disappears as soon as the field is focused.
    assert page.evaluate("() => getComputedStyle(document.querySelector('.ps-option-input'), '::placeholder').color") == "rgba(0, 0, 0, 0)"
    field.type("SvelteKit")
    assert page.evaluate("() => [...document.querySelectorAll('.ps-option.is-selected')].map(n => n.classList.contains('ps-option-typed'))") == [True]
    assert page.is_enabled(".ps-next")
    # Picking a listed choice clears the typed one; key 4 jumps back to the field.
    page.click(".ps-option >> nth=1")
    assert page.input_value(".ps-option-input") == ""
    page.wait_for_function("() => document.activeElement.classList.contains('is-selected')")
    page.keyboard.press("4")
    assert page.evaluate("() => document.activeElement.classList.contains('ps-option-input')")


PROMPT_GAPS = """() => { const s = document.querySelector('.ps-wizard .ps-stepper').getBoundingClientRect(),
  p = document.querySelector('.ps-wizard .ps-prompt'), r = p.getBoundingClientRect(),
  n = p.nextElementSibling.getBoundingClientRect(); return {top: r.top - s.bottom, bottom: n.top - r.bottom}; }"""


def test_step_prompt_has_the_same_room_above_and_below(real_2x):
    page = real_2x
    _to_template_step(page)
    gap = page.evaluate(PROMPT_GAPS)
    assert abs(gap["top"] - gap["bottom"]) <= 0.5, gap
    page.click(".ps-prev")
    page.wait_for_timeout(400)
    page.click(".ps-prev")
    page.wait_for_timeout(400)
    gap = page.evaluate(PROMPT_GAPS)  # step 1, "Please pick one:"
    assert abs(gap["top"] - gap["bottom"]) <= 0.5, gap


def test_each_template_icon_shows_its_own_centred_spinner_until_it_loads(real_2x):
    page = real_2x
    held = []
    page.route("**/static/project-starter/*.webp", lambda route: held.append(route))
    _to_template_step(page)
    slots = page.evaluate("""() => [...document.querySelectorAll('.ps-template .ps-art-wrap')].map(w => {
      const b = w.getBoundingClientRect(), a = getComputedStyle(w, '::after'), img = w.querySelector('img');
      return {loading: w.classList.contains('is-loading'), spin: a.animationName, w: a.width, h: a.height,
        box: [b.width, b.height], hidden: getComputedStyle(img).opacity}; })""")
    assert len(slots) == 4 and all(s["loading"] and s["spin"] == "ps-art-spin" for s in slots), slots
    assert all(s["box"] == [34, 34] and s["w"] == "18px" and s["h"] == "18px" for s in slots), slots
    # The spinner is centred in the icon's box: inset 0 with auto margins.
    centred = page.evaluate("""() => { const w = document.querySelector('.ps-template .ps-art-wrap'), a = getComputedStyle(w, '::after');
      return [a.position, a.top, a.bottom, a.marginTop, a.marginBottom]; }""")
    assert centred[0] == "absolute" and centred[1] == centred[2] == "0px" and centred[3] == centred[4], centred
    # Releasing one image clears only that slot; the others keep spinning.
    first = next(r for r in held if r.request.url.endswith("/web.webp"))
    first.continue_()
    page.wait_for_function("() => document.querySelectorAll('.ps-template .ps-art-wrap.is-loading').length === 3")
    assert page.evaluate("() => !document.querySelector('.ps-art-web').parentElement.classList.contains('is-loading')")
    for route in held:
        if route is not first:
            route.continue_()
    page.wait_for_function("() => !document.querySelector('.ps-art-wrap.is-loading')")


def test_data_ml_artwork_is_scaled_down_to_match_its_neighbours(real_2x):
    page = real_2x
    TEMPLATES_WITH_DATA = dict(TEMPLATES, templates=TEMPLATES["templates"] + [
        {"key": "data", "label": "Data/ML", "description": "Notebooks and models.", "files": ["AGENTS.md"]}])
    _to_template_step(page, TEMPLATES_WITH_DATA)
    sizes = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('.ps-template .ps-art')].map(i =>
      [i.src.split('/').pop(), i.getBoundingClientRect().width]))""")
    assert sizes["data.webp"] < sizes["web.webp"] - 4, sizes
    assert len({w for k, w in sizes.items() if k != "data.webp"}) == 1


def test_recommended_choice_wears_a_star_in_its_top_right_corner(real_2x):
    page = real_2x
    _to_details_step(page)
    assert "Recommended" not in page.inner_text(".ps-options")
    star = page.evaluate("""() => { const o = document.querySelector('.ps-option.is-recommended'), s = o.querySelector('.ps-option-star'),
      a = o.getBoundingClientRect(), b = s.getBoundingClientRect();
      return {top: b.top - a.top, right: a.right - b.right, w: b.width, ok: s.complete && s.naturalWidth > 0,
        src: new URL(s.src).pathname, stars: document.querySelectorAll('.ps-option-star').length}; }""")
    assert star["src"] == "/static/wizard/star.png" and star["ok"] and star["stars"] == 1, star
    assert star["w"] == 18 and abs(star["top"] - star["right"]) <= 0.5, star
