"""Create-project wizard, Details / Look & feel / Toolkit: option text centred on
its key, Look & feel sections split by evenly spaced dividers with no banner,
stars in the top-right corner of cards, palette preview labels centred, skills
as a table whose "Show all" opens category tabs, and component loops that play
while on screen."""

import base64
import io
import json

import pytest

from tests import test_builder_and_skills_polish_browser as pol
from tests import test_project_builder_palette_browser as palb

SKILLS = [{"name": n, "category": c, "description": n + " does things.", "score": s, "recommended": r}
          for n, c, s, r in [("impeccable", "ui-design", 9, True), ("better-ui", "ui-design", 7, True),
                             ("seo-audit", "marketing", 6, True), ("stop-slop", "writing", 4, False),
                             ("pdf", "documents", 0, False), ("arxiv", "research", 0, False),
                             ("excalidraw", "creative", 0, False), ("ascii-art", "creative", 0, False)]]
# A 1x1 WebP still and a "loop" (any image works for the swap).
PIXEL = base64.b64decode("UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoBAAEAAwA0JaQAA3AA/vuUAAA=")


@pytest.fixture
def page():
    gen = pol.page.__wrapped__()
    tab = next(gen)
    kit = json.loads(json.dumps(palb.KIT))
    kit["skills"] = SKILLS
    for comp in kit["components"]["hero"]:
        comp["preview"] = f"{comp['library']}/previews/{comp['slug']}.webp"
        comp["loop"] = f"{comp['library']}/previews/{comp['slug']}.loop.webp"
    tab.unroute("**/api/projects/starter/job*")
    tab.route("**/api/projects/starter/job*", lambda r: r.fulfill(json={"status": "done", "result": {
        "complete": False, "summary": "One thing left.", "questions": pol.QUESTIONS, "look": palb.LOOK}}))
    tab.unroute("**/api/projects/starter/toolkit")
    tab.route("**/api/projects/starter/toolkit", lambda r: r.fulfill(json=kit))
    tab.route("**/api/libraries/preview*", lambda r: r.fulfill(body=PIXEL, content_type="image/webp"))
    yield tab
    try:
        next(gen)
    except StopIteration:
        pass


def _quiet(page):
    page.add_style_tag(content="*,*::before,*::after{animation:none!important;transition:none!important}")
    page.evaluate("() => document.fonts.ready.then(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))))")
    page.wait_for_timeout(100)


def _ink(page, card_sel, text_sel):
    """Gap from the card's top edge to the text's cap ink, and from the text's
    baseline to the card's bottom edge (the user's centring criterion)."""
    from PIL import Image, ImageChops
    a = Image.open(io.BytesIO(page.screenshot())).convert("L")
    tag = page.add_style_tag(content="*{-webkit-text-fill-color:transparent!important}")
    b = Image.open(io.BytesIO(page.screenshot())).convert("L")
    page.evaluate("t => t.remove()", tag)
    out = []
    for info in page.evaluate("""([cs, ts]) => [...document.querySelectorAll(cs)].map(e => {
        const c = e.getBoundingClientRect(); const texts = ts === ':self' ? [e] : [...e.querySelectorAll(ts)];
        const base = texts.map(t => { const p = document.createElement('span'); p.style.cssText = 'display:inline-block;width:0;height:0';
          t.appendChild(p); const y = p.getBoundingClientRect().top; p.remove(); return y; });
        const rg = document.createRange(); rg.selectNodeContents(texts[0]); const r = rg.getBoundingClientRect(); const k = e.querySelector('.ps-option-key'); const kr = k && k.getBoundingClientRect();
        return {c: [c.left, c.top, c.right, c.bottom], t: [r.left, r.right], base: base[base.length - 1], key: kr ? (kr.top + kr.bottom) / 2 : null}; })""",
                              [card_sel, text_sel]):
        left, top, right, bottom = info["c"]
        box = (round(info["t"][0]), round(top) + 1, round(info["t"][1]), round(bottom) - 1)
        ink = ImageChops.difference(a, b).crop(box).point(lambda v: 255 if v > 20 else 0).getbbox()
        cap = box[1] + ink[1]
        row = {"above": cap - top, "below": bottom - info["base"]}
        if info["key"] is not None:
            row["key"] = info["key"] - (cap + info["base"]) / 2
        out.append(row)
    return out


def _font_of(page, selector):
    cdp = page.context.new_cdp_session(page)
    cdp.send("DOM.enable")
    cdp.send("CSS.enable")
    root = cdp.send("DOM.getDocument")["root"]["nodeId"]
    node = cdp.send("DOM.querySelector", {"nodeId": root, "selector": selector})["nodeId"]
    return " ".join(f["familyName"] for f in cdp.send("CSS.getPlatformFontsForNode", {"nodeId": node})["fonts"])


def _to_look(page):
    pol._to_details(page)
    page.click(".ps-next")
    page.wait_for_selector(".ps-pal-card")


def _to_kit(page):
    _to_look(page)
    page.click(".ps-next")
    page.wait_for_selector(".ps-kit-skill")


def test_option_text_is_centred_on_its_key(page):
    # Zeus 2.0 (Courier New on the user's machine) is where the text sat low.
    page.evaluate("() => _applySkin('zeus-2')")
    pol._to_details(page)
    _quiet(page)
    rows = _ink(page, ".ps-option:not(.ps-option-typed)", ".ps-option-label, .ps-option-detail")
    assert len(rows) == 3
    # The 1px correction is tuned for Courier New (what Zeus 2.0 resolves to on
    # Windows); other monospace fallbacks get a looser check.
    exact = "Courier New" in _font_of(page, ".ps-option-label")
    for row in rows:
        assert abs(row["above"] - row["below"]) <= (1.3 if exact else 2.3), rows
        assert abs(row["key"]) <= (1 if exact else 1.3), rows


def test_look_sections_are_split_by_even_dividers_and_the_banner_is_gone(page):
    _to_look(page)
    _quiet(page)
    assert page.locator(".ps-look-rec").count() == 0
    gaps = page.evaluate("""() => [...document.querySelectorAll('.ps-look-sec+.ps-look-sec')].map(sec => {
      const prev = sec.previousElementSibling.lastElementChild.getBoundingClientRect(); const s = sec.getBoundingClientRect();
      const l = sec.querySelector('.ps-look-label').getBoundingClientRect(); const line = parseFloat(getComputedStyle(sec).borderTopWidth);
      return [sec.dataset.sec, Math.round(s.top - prev.bottom), Math.round(l.top - s.top - line), line]; })""")
    assert [g[0] for g in gaps] == ["colours", "motion", "built with"], gaps
    for _name, above, below, line in gaps:
        assert line >= 1 and above == below, gaps


def test_stars_sit_in_the_top_right_corner_of_their_cards(page):
    _to_look(page)
    _quiet(page)
    spots = page.evaluate("""() => [...document.querySelectorAll(':is(.ps-look-card,.ps-pal-card,.ps-motion-card) .ps-option-star')].map(s => {
      const c = s.parentElement.getBoundingClientRect(), r = s.getBoundingClientRect();
      return {top: r.top - c.top, right: c.right - r.right, inside: r.left >= c.left && r.top >= c.top && r.right <= c.right}; })""")
    assert len(spots) == 3, spots  # style, colours, motion
    for spot in spots:
        assert spot["inside"] and 4 <= spot["top"] <= 16 and 4 <= spot["right"] <= 16, spots


def test_palette_preview_labels_are_centred_in_their_buttons(page):
    _to_look(page)
    page.evaluate("() => document.querySelector('.ps-pal-preview').scrollIntoView({block: 'center', behavior: 'instant'})")
    _quiet(page)
    page.wait_for_timeout(300)
    rows = _ink(page, ".ps-pal-pane[data-theme=light] :is(.ps-pal-btn,.ps-pal-tag,.ps-pal-field)", ":self")
    assert len(rows) == 4
    for row in rows:
        assert abs(row["above"] - row["below"]) <= 1.2, rows


def test_skills_are_a_table_and_show_all_opens_category_tabs_that_slide_the_rows(page):
    _to_kit(page)
    assert page.locator(".ps-kit-rec").count() == 0
    heads = page.eval_on_selector_all(".ps-kit-table thead th", "els => els.map(e => e.innerText.trim().toLowerCase())")
    assert heads[1:4] == ["skill", "category", "what it does"], heads
    assert page.locator(".ps-kit-skill").count() == 6
    assert page.locator(".ps-kit-skill[data-skill=impeccable] .ps-kit-col-star .ps-option-star").count() == 1
    assert page.locator(".ps-kit-skill[data-skill=pdf] .ps-option-star").count() == 0
    assert not page.evaluate("() => document.querySelector('.ps-kit-cats-wrap').classList.contains('is-open')")
    page.click(".ps-kit-more")
    page.wait_for_function("() => document.querySelectorAll('.ps-kit-skill').length === 8")
    assert page.evaluate("() => document.querySelector('.ps-kit-cats-wrap').classList.contains('is-open')")
    tabs = page.eval_on_selector_all(".ps-kit-cat .ps-kit-cat-label", "els => els.map(e => e.textContent)")
    assert tabs == ["All", "Creative", "Documents", "Marketing", "Research", "UI design", "Writing"], tabs
    page.click(".ps-kit-cat[data-cat=ui-design]")
    # The rows slide across and the frame eases to its new height.
    assert page.evaluate("() => document.querySelector('.ps-kit-table-frame').getAnimations().length") >= 1
    assert page.eval_on_selector_all(".ps-kit-table:not(.ps-kit-ghost) .ps-kit-skill", "els => els.map(e => e.dataset.skill)") == ["impeccable", "better-ui"]
    page.wait_for_function("() => !document.querySelector('.ps-kit-ghost')")
    row = page.locator(".ps-kit-skill[data-skill=better-ui]")
    row.click()
    assert row.locator("[role=checkbox]").get_attribute("aria-checked") == "false"
    page.click(".ps-kit-more")
    page.wait_for_function("() => document.querySelectorAll('.ps-kit-skill').length === 6")
    assert not page.evaluate("() => document.querySelector('.ps-kit-cats-wrap').classList.contains('is-open')")


def test_component_loops_play_while_on_screen_and_stars_replace_the_pill(page):
    _to_kit(page)
    page.evaluate("() => document.querySelector('.ps-kit-comp').scrollIntoView({block: 'center'})")
    page.wait_for_function("() => [...document.querySelectorAll('.ps-kit-comp .ps-kit-thumb img')].some(i => i.getAttribute('src').includes('.loop.webp'))")
    assert page.locator(".ps-kit-comp .ps-kit-live").count() == 3
    assert page.locator(".ps-kit-comp[data-comp='calm/split'] .ps-option-star").count() == 1
    spot = page.evaluate("""() => { const s = document.querySelector(".ps-kit-comp[data-comp='calm/split'] .ps-option-star");
      const c = s.parentElement.getBoundingClientRect(), r = s.getBoundingClientRect(); return [r.top - c.top, c.right - r.right]; }""")
    assert all(4 <= v <= 16 for v in spot), spot
    page.evaluate("() => { const b = document.querySelector('.ps-body'); b.scrollTop = 0; }")
    page.wait_for_function("() => [...document.querySelectorAll('.ps-kit-comp .ps-kit-thumb img')].every(i => !i.getAttribute('src').includes('.loop.webp'))")
