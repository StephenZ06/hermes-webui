"""Files: the top bar's red delete button puts the list in delete mode. Rows
wiggle, taps pick them, and the bar under the list deletes the picked ones
(folders with everything inside). Done, Escape or a click elsewhere ends it."""

import json
from urllib.parse import parse_qsl, urlparse

import pytest

from tests.test_file_manager_browser import _open, browser  # noqa: F401


@pytest.fixture()
def files_page(browser):
    page = _open(browser, viewport={"width": 1470, "height": 956})
    context = page.context
    entries = [{"name": "drafts", "path": "drafts", "type": "dir"},
               {"name": "a.md", "path": "a.md", "type": "file", "size": 100},
               {"name": "b.md", "path": "b.md", "type": "file", "size": 200}]
    deleted = []

    def listing(route):
        path = dict(parse_qsl(urlparse(route.request.url).query)).get("path", ".")
        route.fulfill(json={"path": path, "entries": [e for e in entries if e["path"] not in {d["path"] for d in deleted}]})

    def delete(route):
        deleted.append(json.loads(route.request.post_data))
        route.fulfill(json={"ok": True})

    page.route("**/api/file-manager/workspaces*", lambda route: route.fulfill(json={"workspaces": [{"id": "a", "name": "Home", "available": True}]}))
    page.route("**/api/file-manager/list*", listing)
    page.route("**/api/file-manager/delete", delete)
    page.evaluate("async () => { await switchPanel('files'); }")
    page.wait_for_selector(".files-list:not(.is-loading) .files-row")
    yield page, deleted
    context.close()


def test_the_upload_button_is_now_a_red_delete_button(files_page):
    page, _ = files_page
    assert page.locator(".files-toolbar-actions [data-action='upload']").count() == 0
    look = page.evaluate("""() => { const b = document.querySelector('.files-toolbar-actions [data-action="delete-mode"]'), s = getComputedStyle(b);
      const probe = document.createElement('i'); probe.style.color = 'var(--error, #e5484d)'; document.body.append(probe);
      const red = getComputedStyle(probe).color; probe.remove(); return {color: s.color, border: s.borderTopColor, red, label: b.getAttribute('aria-label')}; }""")
    assert look["color"] == look["red"], look
    assert look["border"] != "rgba(0, 0, 0, 0)" and look["border"].startswith(("rgb", "color(srgb")), look
    assert look["label"] == "Delete files"


def test_delete_buttons_use_the_work_hub_delete_mark(files_page):
    page, _ = files_page
    page.click("[data-action='delete-mode']")
    page.wait_for_selector(".files-select-bar")
    marks = page.evaluate("""() => ['.files-toolbar-actions [data-action="delete-mode"]', '.files-select-delete'].map(sel => {
      const b = document.querySelector(sel), i = b.querySelector('i.files-mask-delete');
      return {svg: !!b.querySelector('svg'), mask: i ? getComputedStyle(i).webkitMaskImage || getComputedStyle(i).maskImage : ''}; })""")
    assert all(not m["svg"] and "work-hub-delete-mark.png" in m["mask"] for m in marks), marks
    ok = page.evaluate("async () => (await fetch('static/work-hub-delete-mark.png')).ok")
    assert ok


def test_picked_rows_are_deleted_together_and_folders_go_recursively(files_page):
    page, deleted = files_page
    page.click("[data-action='delete-mode']")
    page.wait_for_selector(".files-select-bar")
    assert page.evaluate("() => [...document.querySelectorAll('.files-row')].every(r => r.classList.contains('dm-wiggle') && getComputedStyle(r).animationName === 'dm-wiggle')")
    assert "Pick files and folders" in page.inner_text(".files-select-bar")
    assert page.is_disabled(".files-select-delete")

    page.click(".files-row[data-file-path='drafts']", force=True)
    page.click(".files-row[data-file-path='b.md']", force=True)
    # A tap picks; it does not open the folder or preview the file.
    assert page.locator(".files-row.is-picked").count() == 2
    assert page.locator(".files-inspector-empty").count() == 1
    assert "2 selected" in page.inner_text(".files-select-bar")

    page.click(".files-select-delete")
    page.wait_for_selector("#appDialogConfirm", state="visible")
    assert "Folders are deleted with everything inside them" in page.inner_text("#appDialogOverlay")
    page.click("#appDialogConfirm")
    page.wait_for_function("() => !document.querySelector('.files-select-bar') && document.querySelectorAll('.files-row').length === 1")
    assert sorted((d["path"], d["recursive"]) for d in deleted) == [("b.md", False), ("drafts", True)]
    assert page.locator(".files-row.dm-wiggle").count() == 0


def test_escape_ends_delete_mode_without_deleting(files_page):
    page, deleted = files_page
    page.click("[data-action='delete-mode']")
    page.click(".files-row[data-file-path='a.md']", force=True)  # a wiggling row is never "stable"
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.querySelector('.files-select-bar') && !document.querySelector('.files-row.dm-wiggle')")
    assert deleted == []
    # Back to normal: a tap opens the file again.
    page.route("**/api/file-manager/read*", lambda route: route.fulfill(json={"path": "a.md", "content": "hi", "size": 2, "lines": 1}))
    page.click(".files-row[data-file-path='a.md']")
    page.wait_for_selector(".files-inspector-name")


def test_the_filter_has_as_much_room_above_it_as_on_its_sides(files_page):
    page, _ = files_page
    room = page.evaluate("""() => { const f = document.querySelector('.files-search').getBoundingClientRect();
      const path = document.querySelector('.files-path').getBoundingClientRect();
      const col = document.querySelector('.files-list-toolbar').getBoundingClientRect();
      return {above: f.top - path.bottom, left: f.left - col.left, right: col.right - f.right}; }""")
    assert room["above"] == room["left"] == room["right"] == 14, room
