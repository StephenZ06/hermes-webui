"""Create-project wizard, round 3: the planner's estimated progress, long option
details centred like short ones, more palettes ending in "Use logo colours"
and "Your own" (a hexagon colour picker), button and type choices that reach
the preview and Create, and the Toolkit's tray of chosen components."""

import io

import pytest

from tests import test_builder_and_skills_polish_browser as pol
from tests import test_builder_steps_567_browser as t
from tests import test_project_builder_palette_browser as palb
from tests import test_project_builder_wizard_browser as wiz
from tests.test_builder_steps_567_browser import page  # noqa: F401  (fixture)
from tests.builder_nav import next_step  # noqa: E402


def test_the_brief_review_shows_an_estimated_percent_that_eases_up_then_completes(page):
    polls = {"n": 0}

    def job(route):
        polls["n"] += 1
        if polls["n"] <= 3:
            return route.fulfill(json={"status": "running", "kind": "analysis", "progress": "Weighing the stack", "percent": 40})
        return route.fulfill(json={"status": "done", "result": {"complete": False, "summary": "", "questions": pol.QUESTIONS, "look": palb.LOOK}})

    page.unroute("**/api/projects/starter/job*")
    page.route("**/api/projects/starter/job*", job)
    page.evaluate("() => { window.__starter = _openProjectStarterWizard(); }")
    page.wait_for_selector(".ps-wizard .ps-choice")
    page.click(".ps-choice >> nth=0")
    next_step(page)
    page.click(".ps-tree-row >> nth=0")
    page.fill(".project-starter-field input", "lex")
    next_step(page)
    page.click(".ps-template >> text=Website")
    next_step(page)
    page.fill(".ps-wizard textarea", "A boutique law firm site with service pages.")
    next_step(page)
    page.wait_for_selector(".ps-review.is-busy .ps-review-pct")
    # It eases toward the figure instead of jumping.
    seen = page.evaluate("""() => new Promise(res => { const out = [], t0 = performance.now();
      const tick = () => { const n = document.querySelector('.ps-review-pct-n'); if (n) out.push(parseInt(n.textContent));
        if (performance.now() - t0 < 2500 && !(out.length && out[out.length - 1] === 40)) requestAnimationFrame(tick); else res(out); };
      tick(); })""")
    assert seen[-1] == 40 and any(0 < v < 40 for v in seen), seen
    assert seen == sorted(seen), seen
    meter = float(page.eval_on_selector(".ps-review-meter span", "e => e.style.transform").strip("scaleX()"))
    assert 0.39 <= meter <= 1, meter  # the meter matches the number (or is already finishing)
    assert page.get_attribute(".ps-review-pct", "aria-label") == "About 40% done (estimate)"
    # Done: the meter fills before the questions show.
    trail = page.evaluate("""() => new Promise(res => { const out = []; const t0 = performance.now();
      const tick = () => { const n = document.querySelector('.ps-review-pct-n'); const v = n ? n.textContent : (document.querySelector('.ps-option') ? 'Q' : '-');
        if (out[out.length - 1] !== v) out.push(v); if (v === 'Q' || performance.now() - t0 > 8000) res(out); else requestAnimationFrame(tick); }; tick(); })""")
    assert "100%" in trail and trail[-1] == "Q", trail
    page.wait_for_selector(".ps-option")


LONG = [{"id": "stack", "question": "Which stack?", "options": ["Astro", "Next.js", "Plain HTML"],
         "details": ["Static pages with content collections, image optimisation, and almost no JavaScript shipped to visitors.",
                     "React", "No build step at all, just files you can open and edit by hand anywhere you like."],
         "hows": ["", "", ""], "other": "Other stack", "recommended": "Astro", "why": "Small.", "examples": []}]


def _card_rows(page, sel):
    """Per card: rows from its top border to the first ink, and from the last
    baseline to its bottom border, read from pixels (borders included)."""
    from PIL import Image, ImageChops
    out = []
    for i in range(page.locator(sel).count()):
        loc = page.locator(sel).nth(i)
        a = Image.open(io.BytesIO(loc.screenshot())).convert("L")
        tag = page.add_style_tag(content="*{-webkit-text-fill-color:transparent!important}")
        b = Image.open(io.BytesIO(loc.screenshot())).convert("L")
        page.evaluate("t => t.remove()", tag)
        ink = ImageChops.difference(a, b).point(lambda v: 255 if v > 20 else 0).getbbox()
        base = loc.evaluate("""e => { const ts = e.querySelectorAll('.ps-option-label, .ps-option-detail'), t = ts[ts.length - 1];
          const p = document.createElement('span'); p.style.cssText = 'display:inline-block;width:0;height:0'; t.appendChild(p);
          const y = p.getBoundingClientRect().top - e.getBoundingClientRect().top; p.remove(); return [y, e.getBoundingClientRect().height]; }""")
        out.append({"above": ink[1], "below": base[1] - base[0]})
    return out


def test_options_with_long_details_are_centred_like_short_ones(page):
    page.unroute("**/api/projects/starter/job*")
    page.route("**/api/projects/starter/job*", lambda r: r.fulfill(json={"status": "done", "result": {
        "complete": False, "summary": "x", "questions": LONG}}))
    pol._to_details(page)
    t._quiet(page)
    for width in (1280, 700):
        page.set_viewport_size({"width": width, "height": 900})
        page.wait_for_timeout(150)
        rows = _card_rows(page, ".ps-option:not(.ps-option-typed)")
        lines = page.eval_on_selector_all(".ps-option-detail", "els => els.map(e => Math.round(e.getBoundingClientRect().height / 16))")
        assert max(lines) >= 3, lines  # the long ones really wrap
        tall = page.eval_on_selector_all(".ps-option:not(.ps-option-typed)", "els => els.map(e => e.classList.contains('is-tall'))")
        assert tall == [n >= 3 for n in lines], (tall, lines)
        for row, lifted in zip(rows, tall):
            # Past two lines, the text sits 1px higher (the user's call on Windows).
            assert abs(row["below"] - row["above"] - (1 if lifted else 0)) <= 1.5, (width, rows)


def _to_colours(page):
    t._to_look(page)
    wiz.open_section(page, "colours")


def test_colours_fill_three_rows_ending_in_logo_then_your_own(page):
    _to_colours(page)
    cards = page.eval_on_selector_all(".ps-pal-card", "els => els.map(e => { const r = e.getBoundingClientRect(); return [e.dataset.pal, Math.round(r.left), Math.round(r.top)]; })")
    assert len(cards) == 12, cards
    assert [c[0] for c in cards[-2:]] == ["logo", "custom"], cards
    rows = sorted({c[2] for c in cards})
    assert len(rows) == 3 and cards[-1][2] == rows[-1] and cards[-2][2] == rows[-1], cards
    assert cards[-1][1] == max(c[1] for c in cards), cards  # Your own: bottom right
    assert page.inner_text(".ps-pal-card[data-pal=logo] .ps-look-name") == "Use logo colours"
    assert page.locator(".ps-pal-card[data-pal=logo] .ps-pal-swatch-tool").count() == 1
    # A recommendation, nine presets (four of them new this round), logo, your own.
    keys = [c[0] for c in cards]
    assert keys[0] == "recommended" and len(set(keys[1:10]) & {"midnight", "rose", "citrus", "mocha"}) >= 3, keys


def test_your_own_opens_a_hexagon_picker_that_paints_the_chosen_role(page):
    _to_colours(page)
    page.click(".ps-pal-card[data-pal=custom]")
    page.wait_for_selector(".ps-pal-editor-wrap.is-open")
    page.wait_for_function("() => !document.querySelector('.ps-pal-editor-wrap').getAnimations({subtree: true}).some(a => a instanceof CSSTransition)")
    assert page.locator(".ps-hex-comb polygon").count() == 127
    assert page.locator(".ps-hex-greys polygon").count() == 11
    page.click(".ps-pal-edit-cell[data-role=accent][data-theme=light] .ps-hex-chip")
    assert "accent (light)" in page.inner_text(".ps-hex-aim")
    cell = page.locator(".ps-hex-comb polygon").nth(5)
    colour = cell.get_attribute("data-c")
    cell.click(force=True)
    assert page.input_value("[aria-label='Accent hex (light)']") == colour
    assert page.get_attribute(".ps-hex-comb polygon.is-on", "data-c") == colour
    # The slider makes the honeycomb lighter or darker.
    before = cell.get_attribute("data-c")
    page.eval_on_selector(".ps-hex-light input", "e => { e.value = '25'; e.dispatchEvent(new Event('input')); }")
    assert cell.get_attribute("data-c") != before
    # Greys work too.
    page.locator(".ps-hex-greys polygon").last.click(force=True)
    assert page.input_value("[aria-label='Accent hex (light)']") == "#ffffff"


def test_logo_card_reads_a_logo_and_becomes_its_palette(page, tmp_path):
    _to_colours(page)
    logo = tmp_path / "logo.png"
    logo.write_bytes(palb._png(16, 16, lambda x, y: (20, 160, 60, 255) if x > 3 else (240, 200, 20, 255)))
    page.set_input_files(".ps-pal input[type=file]", str(logo))
    page.wait_for_selector(".ps-pal-card[data-pal=logo].is-selected", state="attached")
    assert page.inner_text(".ps-pal-card[data-pal=logo] .ps-look-name") == "Your logo"
    assert page.locator(".ps-pal-card[data-pal=logo] .ps-pal-swatch .ps-pal-logo").count() == 1
    assert page.locator(".ps-pal-card").count() == 12


@pytest.fixture
def wpage():
    """The wizard fixture that records what Create sends."""
    gen = palb.page.__wrapped__()
    tab = next(gen)
    yield tab
    try:
        next(gen)
    except StopIteration:
        pass


def test_button_and_type_choices_reach_the_preview_and_create(wpage):
    page = wpage
    palb._to_look(page)
    wiz.open_section(page, "buttons")
    page.click(".ps-cz-opt[data-key=btnShape][data-value=pill]")
    page.click(".ps-cz-opt[data-key=btnFill][data-value=outline]")
    wiz.open_section(page, "type")
    page.click(".ps-cz-opt[data-key=font][data-value=serif]")
    wiz.open_section(page, "colours")
    page.wait_for_function("() => getComputedStyle(document.querySelector('.ps-pal-pane[data-theme=light] .ps-pal-btn.is-primary')).borderTopLeftRadius === '999px'")
    btn = page.eval_on_selector(".ps-pal-pane[data-theme=light] .ps-pal-btn.is-primary", "e => getComputedStyle(e).backgroundColor")
    assert btn == "rgba(0, 0, 0, 0)", btn  # outline: no fill
    font = page.eval_on_selector(".ps-pal-hero strong", "e => getComputedStyle(e).fontFamily")
    assert "Georgia" in font, font
    next_step(page)
    page.wait_for_selector(".ps-kit-skill")
    next_step(page)
    page.wait_for_selector(".ps-review-look")
    review = page.inner_text(".ps-review-look")
    assert "Pill · Outline" in review and "Classic serif" in review, review
    next_step(page)
    page.wait_for_function("() => window.__launched.length === 1", timeout=10000)
    custom = page.created[-1]["toolkit"]["look"]["custom"]
    assert custom["btnShape"] == "pill" and custom["btnFill"] == "outline" and custom["font"] == "serif", custom


def test_the_toolkit_lists_the_chosen_components_and_a_chip_removes_one(page):
    t._to_kit(page)
    wiz.open_lib(page, "calm")
    chips = lambda: page.eval_on_selector_all(".ps-kit-tray-group[data-kind=comps] .ps-kit-tray-chip:not(.is-leaving)", "els => els.map(e => e.dataset.comp)")  # noqa: E731
    chosen = page.eval_on_selector_all(".ps-kit-comp.is-selected", "els => els.map(e => e.dataset.comp)")
    assert chosen and chips() == chosen
    wiz.open_lib(page, "glow")
    other = page.eval_on_selector_all(".ps-cz-sec[data-sec='lib:glow'] .ps-kit-comp:not(.is-selected)", "els => els.map(e => e.dataset.comp)")[0]
    page.click(f".ps-kit-comp[data-comp='{other}']")
    assert chips() == chosen + [other]
    sums = page.eval_on_selector_all(".ps-cz-sec[data-sec^='lib:'] .ps-cz-summary", "els => els.map(e => parseInt(e.textContent))")
    assert sum(sums) == len(chosen) + 1, sums
    page.click(f".ps-kit-tray-chip[data-comp='{chosen[0]}'] .ps-kit-tray-x")
    page.wait_for_function("id => !document.querySelector(`.ps-kit-tray-chip[data-comp='${id}']`)", arg=chosen[0])
    assert page.get_attribute(f".ps-kit-comp[data-comp='{chosen[0]}']", "aria-pressed") == "false"
    # A chip scrolls to and flashes its card.
    page.click(f".ps-kit-tray-chip[data-comp='{other}'] .ps-kit-tray-go")
    assert "is-flash" in page.get_attribute(f".ps-kit-comp[data-comp='{other}']", "class")
    # A chip whose library is folded opens that section first.
    page.click(".ps-cz-sec[data-sec='lib:glow'] > .ps-cz-head")
    page.wait_for_function("() => !document.querySelector(\".ps-cz-sec[data-sec='lib:glow']\").classList.contains('is-open')")
    page.click(f".ps-kit-tray-chip[data-comp='{other}'] .ps-kit-tray-go")
    page.wait_for_selector(".ps-cz-sec[data-sec='lib:glow'].is-open")
    page.wait_for_function("id => document.querySelector(`.ps-kit-comp[data-comp='${id}']`).classList.contains('is-flash')", arg=other)
