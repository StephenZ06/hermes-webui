"""Files: picking a space changes the list in place, the hover highlight slides, and the spacing."""

from tests.test_chat_optical_alignment_browser import _ink, _rect, browser, pytestmark, real_2x  # noqa: F401
from tests.test_files_previews_browser import _space
from tests.test_pages_round11_browser import _open

ROW = "#filesSidebarHost [data-workspace-id='{}']"
SPACES = [{"id": "a", "name": "Home", "available": True}, {"id": "b", "name": "Pi", "available": True},
          {"id": "c", "name": "Raspberry Pi 5", "available": True}]


def test_picking_a_space_keeps_the_list_on_screen(real_2x):
    page = real_2x
    _space(page, SPACES)
    _open(page, "files", ROW.format("b"))
    page.wait_for_timeout(500)
    page.evaluate("""() => { const list = document.querySelector('#filesSidebarHost .files-workspaces');
      list.__kept = true; list.querySelectorAll('.files-workspace').forEach(row => { row.__kept = true; }); }""")
    page.hover(ROW.format("b"))
    page.wait_for_timeout(200)
    page.evaluate("() => { document.querySelector('#filesSidebarHost .mi-hover-pill').__kept = true; }")
    page.click(ROW.format("b"))
    page.wait_for_selector(ROW.format("b") + ".is-active")
    page.wait_for_selector(".files-list:not(.is-loading)")
    page.wait_for_timeout(200)
    out = page.evaluate("""() => { const list = document.querySelector('#filesSidebarHost .files-workspaces'), pill = list.querySelector('.mi-hover-pill');
      return {list: !!list.__kept, rows: [...list.querySelectorAll('.files-workspace')].every(row => row.__kept),
        pill: !!pill.__kept && pill.style.opacity === '1', active: [...list.querySelectorAll('.is-active')].map(r => r.dataset.workspaceId)}; }""")
    # The highlight under the pointer stays where it is instead of vanishing and popping back.
    assert out == {"list": True, "rows": True, "pill": True, "active": ["b"]}, out


def test_the_hover_highlight_slides_between_spaces_after_a_pick(real_2x):
    page = real_2x
    _space(page, SPACES)
    _open(page, "files", ROW.format("b"))
    # Motion is what is under test, so the harness's freeze comes off.
    page.evaluate("() => document.querySelectorAll('style').forEach(s => { if (s.textContent.includes('transition:none!important')) s.remove(); })")
    page.click(ROW.format("c"))
    page.wait_for_selector(ROW.format("c") + ".is-active")
    page.wait_for_timeout(400)
    box = lambda wid: _rect(page, ROW.format(wid))
    a, b = box("a"), box("b")
    page.mouse.move(a["x"] + 40, a["y"] + a["height"] / 2, steps=4)
    page.wait_for_timeout(400)
    page.evaluate("""() => { window.__moves = []; const t0 = performance.now();
      const tick = () => { const pill = document.querySelector('#filesSidebarHost .mi-hover-pill');
        window.__moves.push(pill ? Math.round(new DOMMatrix(getComputedStyle(pill).transform).f * 10) / 10 : null);
        if (performance.now() - t0 < 450) requestAnimationFrame(tick); };
      requestAnimationFrame(tick); }""")
    page.mouse.move(b["x"] + 40, b["y"] + b["height"] / 2, steps=4)
    page.wait_for_timeout(600)
    moves = page.evaluate("window.__moves")
    start, end = moves[0], moves[-1]
    between = [m for m in moves if m is not None and start < m < end]
    assert end - start == b["y"] - a["y"], moves
    # It glides: several frames land between the two rows instead of one jump.
    assert len(between) >= 3, moves
    assert page.locator("#filesSidebarHost .mi-hover-pill").count() == 1


def test_connected_spaces_has_equal_room_above_and_below(real_2x):
    page = real_2x
    _space(page, SPACES)
    _open(page, "files", ROW.format("a"))
    page.mouse.move(5, 900)
    head = _rect(page, "#panelFiles .panel-head")
    ink = _ink(page, "#filesSidebarHost .files-section-heading", "text")
    row = _rect(page, ROW.format("a"))
    above, below = ink["top"] - (head["y"] + head["height"]), row["y"] - ink["bottom"]
    assert abs(above - below) <= .5, (above, below)


def test_workspace_has_equal_room_above_and_below_and_the_filter_spans_the_column(real_2x):
    page = real_2x
    _space(page, SPACES)
    _open(page, "files", ".files-row")
    page.mouse.move(5, 900)
    bar = _rect(page, ".files-toolbar")
    ink = _ink(page, ".files-path", "text")
    field = _rect(page, ".files-search input")
    above, below = ink["top"] - (bar["y"] + bar["height"]), field["y"] - ink["bottom"]
    assert abs(above - below) <= .5, (above, below)
    out = page.evaluate("""() => { const row = document.querySelector('.files-list-toolbar'), field = document.querySelector('.files-search input').getBoundingClientRect(), r = row.getBoundingClientRect(), cs = getComputedStyle(row);
      return {count: document.querySelectorAll('.files-item-count').length, left: field.left - r.left - parseFloat(cs.paddingLeft), right: r.right - parseFloat(cs.paddingRight) - field.right}; }""")
    assert out == {"count": 0, "left": 0, "right": 0}, out
