"""The chat composer types smaller, keeps its first line in place, and shows no scrollbar."""

from tests.test_chat_optical_alignment_browser import _ink, _rect, browser, pytestmark, real_2x  # noqa: F401
from tests.test_office_notes_workhub_nudges_browser import _panel

# Where the 16px placeholder's ink centre sat below the textarea's top before
# the composer went to 14px (measured on Zeus 2 at 2x).
PLACEHOLDER_CENTRE = 27.55


def _composer(page):
    return page.evaluate("""() => { const m = document.getElementById('msg'), s = getComputedStyle(m);
      return {size: s.fontSize, bar: s.scrollbarWidth, top: s.paddingTop, height: m.getBoundingClientRect().height}; }""")


def _centre(page):
    box, ink = _rect(page, "#msg"), _ink(page, "#msg", "text")
    return (ink["top"] + ink["bottom"]) / 2 - box["y"]


def test_the_composer_types_at_14px_with_its_line_where_it_was(real_2x):
    page = real_2x
    _panel(page, "chat")
    state = _composer(page)
    assert state["size"] == "14px" and state["height"] == 44
    assert abs(_centre(page) - PLACEHOLDER_CENTRE) <= .5
    page.fill("#msg", "Draft a reply to the vendor")
    assert abs(_centre(page) - PLACEHOLDER_CENTRE) <= .5


def test_a_long_draft_scrolls_without_a_bar(real_2x):
    page = real_2x
    _panel(page, "chat")
    page.fill("#msg", "line\n" * 20)
    page.wait_for_timeout(200)
    assert page.evaluate("() => { const m = document.getElementById('msg'); return m.scrollHeight > m.clientHeight; }")
    assert _composer(page)["bar"] == "none"


def test_the_font_size_setting_still_scales_the_composer(real_2x):
    page = real_2x
    _panel(page, "chat")
    sizes = {}
    for setting in ("small", "large", "xlarge"):
        page.evaluate("(v) => document.documentElement.setAttribute('data-font-size', v)", setting)
        sizes[setting] = _composer(page)["size"]
    page.evaluate("() => document.documentElement.removeAttribute('data-font-size')")
    assert sizes == {"small": "13px", "large": "16px", "xlarge": "18px"}


def test_skins_with_their_own_composer_type_keep_their_padding(real_2x):
    page = real_2x
    _panel(page, "chat")
    page.evaluate("() => document.documentElement.setAttribute('data-skin', 'graphite')")
    assert _composer(page)["top"] == "12px" and _composer(page)["size"] == "14px"
