"""Create-project wizard, Look & feel → Colours: the brief's recommended palette,
logo colours read in the browser, presets, your own colours, the light and dark
preview, and what Create sends. Also the Toolkit grouped by library."""

import base64
import json
import struct
import zlib

import pytest

from tests import test_project_builder_wizard_browser as wiz

PALETTE = {"name": "Clay", "why": "Warm clay suits a family bakery.",
           "light": {"bg": "#fbf6f0", "surface": "#ffffff", "text": "#2b1d14", "primary": "#b0502a", "accent": "#2f7d6d"},
           "dark": {"bg": "#17110d", "surface": "#221a15", "text": "#f5ebe2", "primary": "#e58a5f", "accent": "#5cc2ab"}}
LOOK = dict(wiz.LOOK, palette=PALETTE)
KIT = json.loads(json.dumps(wiz.KIT))
for comp in KIT["components"]["hero"]:
    comp["role"] = "hero"
    comp["license"] = {"calm": "MIT", "glow": "Glow licence (personal use)"}[comp["library"]]


def _rgb(hex_):
    return "rgb({}, {}, {})".format(*(int(hex_[i:i + 2], 16) for i in (1, 3, 5)))


def _png(w, h, pixel):
    """A tiny PNG where pixel(x, y) gives (r, g, b, a)."""
    raw = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(w)) for y in range(h))
    chunk = lambda kind, data: struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@pytest.fixture
def page():
    gen = wiz.page.__wrapped__()
    tab = next(gen)
    tab.unroute("**/api/projects/starter/job*")
    tab.route("**/api/projects/starter/job*", lambda r: r.fulfill(json={"status": "done", "result": {
        "complete": True, "summary": "All set.", "questions": [], "look": LOOK}}))
    tab.unroute("**/api/projects/starter/toolkit")
    tab.route("**/api/projects/starter/toolkit", lambda r: r.fulfill(json=KIT))
    yield tab
    try:
        next(gen)
    except StopIteration:
        pass


def _to_look(page):
    wiz._to_template(page, "Website")
    wiz._through_brief(page)
    page.wait_for_selector(".ps-pal-card")


def _settled(page):
    page.wait_for_function("() => [...document.querySelectorAll('.ps-pal-mock')].every(m => !m.getAnimations().length)")


def _mock_bg(page, theme):
    _settled(page)
    return page.eval_on_selector(f".ps-pal-pane[data-theme={theme}] .ps-pal-mock", "e => getComputedStyle(e).backgroundColor")


def _primary_btn(page, theme):
    _settled(page)
    return page.eval_on_selector(f".ps-pal-pane[data-theme={theme}] .ps-pal-btn.is-primary", "e => getComputedStyle(e).backgroundColor")


def test_the_brief_palette_is_recommended_and_previewed_in_both_themes(page):
    _to_look(page)
    assert page.get_attribute(".ps-pal-card.is-selected", "data-pal") == "recommended"
    assert page.locator(".ps-pal-card[data-pal=recommended] .ps-option-star").count() == 1
    assert "family bakery" in page.inner_text(".ps-pal-why")
    assert _mock_bg(page, "light") == _rgb(PALETTE["light"]["bg"])
    assert _mock_bg(page, "dark") == _rgb(PALETTE["dark"]["bg"])
    assert _primary_btn(page, "dark") == _rgb(PALETTE["dark"]["primary"])
    # The style samples paint in the palette too.
    btn = page.eval_on_selector(".ps-look-card[data-style=bold] .ps-look-sample-btn", "e => getComputedStyle(e).backgroundColor")
    assert btn == _rgb(PALETTE["light"]["primary"])
    assert page.locator(".ps-pal-pane[data-theme=light] .ps-pal-check.is-ok").count() == 3
    assert page.locator(".ps-pal-editor").is_hidden()


def test_a_preset_and_your_own_colours_reach_create(page):
    _to_look(page)
    page.click(".ps-pal-card[data-pal=forest]")
    assert _mock_bg(page, "light") == _rgb("#f4f7f2")
    page.click(".ps-pal-card[data-pal=custom]")
    assert page.locator(".ps-pal-editor").is_visible()
    # Starts from the palette that was showing.
    assert page.input_value("[aria-label='Primary hex (light)']") == "#2e6b3f"
    page.fill("[aria-label='Primary hex (light)']", "#123456")
    assert _primary_btn(page, "light") == _rgb("#123456")
    page.fill("[aria-label='Text hex (light)']", "#eeeeee")
    assert page.locator(".ps-pal-pane[data-theme=light] .ps-pal-check.is-low").count() >= 1
    page.fill("[aria-label='Text hex (light)']", "#111111")
    before = _primary_btn(page, "dark")
    page.check(".ps-pal-follow input")
    assert page.locator("[aria-label='Primary hex (dark)']").is_disabled()
    after = _primary_btn(page, "dark")
    assert after != before
    page.click(".ps-next")
    page.wait_for_selector(".ps-kit-skill")
    page.click(".ps-next")
    page.wait_for_selector(".ps-review-pal")
    assert "Custom" in page.inner_text(".ps-review-look")
    page.click(".ps-next")
    page.wait_for_function("() => window.__launched.length === 1", timeout=10000)
    pal = page.created[-1]["toolkit"]["look"]["palette"]
    assert pal["source"] == "custom" and pal["light"]["primary"] == "#123456" and pal["light"]["text"] == "#111111"
    assert set(pal["dark"]) == {"bg", "surface", "text", "primary", "accent"}
    assert _rgb(pal["dark"]["primary"]) == after


def test_logo_colours_become_the_recommended_palette(page, tmp_path):
    _to_look(page)
    # Mostly a strong red mark with a blue stripe, on transparent and white.
    def px(x, y):
        if x < 4:
            return (0, 0, 0, 0)
        if y < 6:
            return (30, 90, 200, 255)
        if x > 28:
            return (255, 255, 255, 255)
        return (210, 30, 40, 255)
    logo = tmp_path / "logo.png"
    logo.write_bytes(_png(32, 24, px))
    page.set_input_files(".ps-pal-logo-row input[type=file]", str(logo))
    page.wait_for_selector(".ps-pal-card[data-pal=logo].is-selected")
    assert page.locator(".ps-pal-card[data-pal=logo] .ps-option-star").count() == 1
    assert page.locator(".ps-pal-card[data-pal=recommended] .ps-option-star").count() == 0
    r, g, b = page.eval_on_selector(".ps-pal-pane[data-theme=light] .ps-pal-btn.is-primary",
                                    "e => getComputedStyle(e).backgroundColor.match(/\\d+/g).map(Number)")
    assert r > g + 60 and r > b + 60, (r, g, b)
    assert page.locator(".ps-pal-pane[data-theme=light] .ps-pal-check.is-ok").count() == 3
    assert page.locator(".ps-pal-pane[data-theme=dark] .ps-pal-check.is-ok").count() == 3


def test_narrow_screens_switch_between_light_and_dark(page):
    page.set_viewport_size({"width": 390, "height": 860})
    _to_look(page)
    assert page.locator(".ps-pal-seg").is_visible()
    assert page.locator(".ps-pal-pane[data-theme=light]").is_visible()
    assert page.locator(".ps-pal-pane[data-theme=dark]").is_hidden()
    page.click(".ps-pal-seg-btn[data-theme=dark]")
    assert page.locator(".ps-pal-pane[data-theme=dark]").is_visible()
    assert page.locator(".ps-pal-pane[data-theme=light]").is_hidden()
    assert page.evaluate("() => { const b = document.querySelector('.ps-body'); return b.scrollWidth <= b.clientWidth + 1; }")


def test_toolkit_components_are_grouped_by_library_with_their_licence(page):
    _to_look(page)
    page.click(".ps-next")
    page.wait_for_selector(".ps-kit-lib")
    heads = page.eval_on_selector_all(".ps-kit-lib", "els => els.map(e => e.innerText.replace(/\\s+/g, ' ').trim())")
    assert heads == ["Calm UI 1 component MIT", "Glow 2 components Glow licence (personal use)"]
    assert page.inner_text(".ps-kit-comp[data-comp='calm/split'] .ps-kit-meta") == "Hero · npm"
