"""Files: the path gets its own row under the top bar, and the top bar's buttons are even squares."""

from urllib.parse import parse_qsl, urlparse

import pytest

from tests.test_chat_optical_alignment_browser import browser, pytestmark, real_2x  # noqa: F401
from tests.test_pages_round11_browser import _open

DEEP = "projects/hermes-webui/static/office/assets/textures"


def _deep_space(page):
    """A space whose folders nest six deep, one folder and three files at each level."""
    def listing(route):
        path = dict(parse_qsl(urlparse(route.request.url).query)).get("path", ".")
        parts, level = DEEP.split("/"), 0 if path == "." else len(path.split("/"))
        base = "" if path == "." else path + "/"
        entries = [{"name": parts[level], "path": base + parts[level], "type": "dir"}] if level < len(parts) else []
        entries += [{"name": f"file{i}.md", "path": f"{base}file{i}.md", "type": "file", "size": 1200} for i in range(3)]
        route.fulfill(json={"path": path, "entries": entries})
    page.route("**/api/file-manager/workspaces*", lambda route: route.fulfill(json={"workspaces": [
        {"id": "a", "name": "Home", "available": True}, {"id": "b", "name": "Pi", "available": True}]}))
    page.route("**/api/file-manager/list*", listing)


def _enter(page, times):
    for _ in range(times):
        page.wait_for_selector(".files-list:not(.is-loading) .files-row[data-file-type='dir']")
        page.click(".files-row[data-file-type='dir']")
        page.wait_for_selector(".files-list:not(.is-loading)")
        page.wait_for_timeout(350)


def test_the_whole_path_shows_in_its_own_row_between_the_top_bar_and_the_filter(real_2x):
    page = real_2x
    _deep_space(page)
    _open(page, "files", ".files-action")
    _enter(page, 6)
    out = page.evaluate("""() => { const r = s => document.querySelector(s).getBoundingClientRect();
      const row = r('.files-path'), crumbs = [...document.querySelectorAll('.files-path .files-crumb')].map(c => c.getBoundingClientRect());
      return {inBar: document.querySelectorAll('.files-toolbar .files-crumb').length, order: r('.files-toolbar').bottom <= row.top && row.bottom <= r('.files-list-toolbar').top,
        names: [...document.querySelectorAll('.files-path .files-crumb')].map(c => c.textContent),
        inside: crumbs.every(c => c.left >= row.left && c.right <= row.right + .5 && c.top >= row.top && c.bottom <= row.bottom + .5),
        title: document.querySelector('.files-toolbar .files-title').textContent}; }""")
    assert out == {"inBar": 0, "order": True, "names": ["Workspace"] + DEEP.split("/"), "inside": True, "title": "textures"}, out


def test_the_top_bar_buttons_are_squares_with_equal_room_on_every_side(real_2x):
    page = real_2x
    _deep_space(page)
    _open(page, "files", ".files-action")
    _enter(page, 2)
    out = page.evaluate("""() => { const bar = document.querySelector('.files-toolbar'), b = bar.getBoundingClientRect();
      const inner = {top: b.top, bottom: b.bottom - parseFloat(getComputedStyle(bar).borderBottomWidth), left: b.left, right: b.right};
      const buttons = [...bar.querySelectorAll('.files-up, .files-action')].map(e => e.getBoundingClientRect());
      return {sizes: buttons.map(r => [r.width, r.height]), radius: getComputedStyle(bar.querySelector('.files-action')).borderTopLeftRadius,
        top: buttons.map(r => r.top - inner.top), bottom: buttons.map(r => inner.bottom - r.bottom),
        left: buttons[0].left - inner.left, right: inner.right - buttons[buttons.length - 1].right,
        gaps: buttons.slice(2).map((r, i) => r.left - buttons[i + 1].right)}; }""")
    assert out["sizes"] == [[32, 32]] * 4, out
    assert out["radius"] == "7px", out
    room = {*out["top"], *out["bottom"], out["left"], out["right"], *out["gaps"]}
    assert room == {4}, out


def test_navigating_slides_the_title_and_brings_in_new_crumbs(real_2x):
    page = real_2x
    _deep_space(page)
    _open(page, "files", ".files-action")
    title = page.locator(".files-toolbar .files-title")
    assert title.text_content() == "Home"
    assert page.locator(".files-up").is_disabled()
    _enter(page, 2)
    assert title.text_content() == "hermes-webui"
    assert "is-in-forward" in title.get_attribute("class")
    assert page.locator(".files-path .files-crumb.is-new").all_text_contents() == ["hermes-webui"]
    page.click(".files-path .files-crumb[data-path='.']")
    page.wait_for_selector(".files-list:not(.is-loading)")
    assert title.text_content() == "Home"
    assert "is-in-back" in title.get_attribute("class")
    page.click("#filesSidebarHost [data-workspace-id='b']")
    page.wait_for_function("() => document.querySelector('.files-toolbar .files-title').textContent === 'Pi'")
    assert "is-in-in" in title.get_attribute("class")


@pytest.mark.parametrize("width", [800, 390])
def test_narrow_and_phone_keep_one_row_of_square_buttons(browser, width):
    context = browser.new_context(viewport={"width": width, "height": 844}, device_scale_factor=2, is_mobile=width < 500, has_touch=width < 500)
    page = context.new_page()
    from tests._pytest_port import BASE
    _deep_space(page)
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach((node) => node.remove())")
    page.evaluate("async () => { await switchPanel('files'); }")
    page.wait_for_selector("#fileManagerRoot .files-list .files-row", timeout=15000)
    _enter(page, 3)
    out = page.evaluate("""() => { const bar = document.querySelector('.files-toolbar'), host = document.getElementById('mainFiles');
      const buttons = [...bar.querySelectorAll('.files-up, .files-action')].map(e => e.getBoundingClientRect());
      return {rows: new Set(buttons.map(r => Math.round(r.top))).size, square: buttons.every(r => r.width === r.height),
        overflow: host.scrollWidth > host.clientWidth + 1, path: document.querySelector('.files-path').getBoundingClientRect().height > 0}; }""")
    assert out == {"rows": 1, "square": True, "overflow": False, "path": True}, out
    context.close()
