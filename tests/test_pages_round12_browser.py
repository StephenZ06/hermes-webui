"""Placeholders, overlays, Jobs Settings, Logs, Activity and Files, twelfth round."""

import pytest

from tests.test_chat_optical_alignment_browser import _ink, _rect, browser, pytestmark, real_2x  # noqa: F401
from tests.test_job_os_page_polish_browser import seeded  # noqa: F401
from tests.test_jobs_round4_browser import jobs  # noqa: F401
from tests.test_jobs_round7_browser import settings  # noqa: F401
from tests.test_office_notes_workhub_nudges_browser import _moved, _panel
from tests.test_pages_round11_browser import _open, _room


def _files_fixture(page, entries=None):
    """A space with folders and a file, served to the page; every /move and /upload is recorded."""
    page.evaluate("() => { window.__files = {reads: 0, posts: []}; }")
    listing = entries or [{"name": "docs", "path": "docs", "type": "dir"}, {"name": "src", "path": "src", "type": "dir"},
                          {"name": "note.md", "path": "note.md", "type": "file", "size": 12}]
    page.route("**/api/file-manager/workspaces*", lambda route: route.fulfill(json={"workspaces": [
        {"id": "a", "name": "Home", "available": True}, {"id": "b", "name": "Pi", "available": True}]}))
    page.route("**/api/file-manager/list*", lambda route: route.fulfill(
        json={"path": "docs" if "path=docs" in route.request.url else ".", "entries": [] if "path=docs" in route.request.url else listing}))
    page.route("**/api/file-manager/move", lambda route: route.fulfill(json={"ok": True, "path": "docs/note.md", "parent_path": "docs"}))
    page.route("**/api/file-manager/upload", lambda route: route.fulfill(json={"ok": True}))


def _dnd(page, source, target):
    """Drive the drag events a browser sends, with one shared DataTransfer."""
    page.evaluate("""([source, target]) => { const a = document.querySelector(source), b = document.querySelector(target), data = new DataTransfer();
      const fire = (el, type) => el.dispatchEvent(new DragEvent(type, {bubbles: true, cancelable: true, dataTransfer: data}));
      fire(a, 'dragstart'); fire(b, 'dragover'); window.__dropLit = b.classList.contains('files-drop-target'); fire(b, 'drop'); fire(a, 'dragend'); }""", [source, target])


# ── Placeholders ────────────────────────────────────────────────────────────

def test_a_kind_of_page_seen_before_opens_on_its_own_lines(real_2x):
    page = real_2x
    _open(page, "agents", "#agentsList .skill-item")
    page.click("#agentsList .skill-item:nth-child(1)")
    page.wait_for_selector("#agentDefDetailBody .detail-card")
    page.wait_for_timeout(900)
    # The second persona has not been opened, so its bars come from the first: where its lines will be.
    out = page.evaluate("""async () => { const list = document.querySelectorAll('#agentsList .skill-item'); list[1].click();
      await new Promise(r => requestAnimationFrame(r));
      const bars = [...document.querySelectorAll('#mainAgents .skel i')].map(b => b.getBoundingClientRect()); return bars.length ? {x: bars[0].left, y: bars[0].top} : null; }""")
    assert out, "no placeholder"
    page.wait_for_timeout(1000)
    line = page.evaluate("""() => { const r = document.createRange(); r.selectNodeContents(document.querySelector('#agentDefDetailBody .detail-card-title')); const b = r.getBoundingClientRect(); return {x: b.left, y: b.top, h: b.height}; }""")
    assert abs(out["x"] - line["x"]) <= 1 and abs(out["y"] - (line["y"] + line["h"] / 2)) <= 8, (out, line)


def test_the_usual_lines_start_inside_the_card_a_page_will_show(real_2x):
    page = real_2x
    _open(page, "memory", "#memoryPanel .side-menu-item")
    page.evaluate("() => { localStorage.removeItem('hermes-skel-shapes-2'); }")
    page.reload()
    page.wait_for_function("typeof switchPanel === 'function'")
    _open(page, "memory", "#memoryPanel .side-menu-item")
    left = page.evaluate("""async () => { document.querySelectorAll('#memoryPanel .side-menu-item')[2].click(); await new Promise(r => requestAnimationFrame(r));
      const bar = document.querySelector('#mainMemory .skel i:not(.gap)'); return bar ? bar.getBoundingClientRect().left : null; }""")
    assert left is not None
    page.wait_for_selector("#memoryDetailBody .detail-card")
    page.wait_for_timeout(900)
    card = _rect(page, "#memoryDetailBody .detail-card")
    assert abs(left - (card["x"] + 21)) <= 1, (left, card)


# ── Overlays ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,button,body", [
    ("agents", "openAgentDefCreate()", "#agentDefDetailBody"),
    ("skills", "openSkillCreate()", "#skillDetailBody"),
    ("workspaces", "openWorkspaceCreate()", "#workspaceDetailBody"),
])
def test_a_create_form_fades_in(real_2x, name, button, body):
    page = real_2x
    _panel(page, name)
    running = page.evaluate("""([call, body]) => { eval(call); const form = document.querySelector(body + ' .detail-form');
      return getComputedStyle(form).animationName; }""", [button, body])
    assert running == "form-in"


def test_the_palette_fades_in(real_2x):
    page = real_2x
    out = page.evaluate("""() => { openCommandPalette(); return [getComputedStyle(document.getElementById('commandPaletteOverlay')).animationName, getComputedStyle(document.getElementById('commandPaletteModal')).animationName]; }""")
    assert out == ["overlay-in", "dialog-in"]


def test_the_wiki_and_checkpoint_overlays_fade_in_and_out(real_2x):
    page = real_2x
    out = page.evaluate("""async () => { const m = document.createElement('div'); m.id = 'checkpointDiffModal'; m.style.cssText = 'position:fixed;inset:0;display:flex'; m.innerHTML = '<div>x</div>'; document.body.appendChild(m);
      const opened = [getComputedStyle(m).animationName, getComputedStyle(m.firstChild).animationName]; _closeOverlay(m);
      const leaving = getComputedStyle(m).animationName; await new Promise(r => setTimeout(r, 260));
      return {opened, leaving, display: m.style.display}; }""")
    assert out == {"opened": ["overlay-in", "dialog-in"], "leaving": "overlay-out", "display": "none"}


# ── Jobs Settings ───────────────────────────────────────────────────────────

def test_the_description_stands_as_far_above_the_first_card_as_the_cards_stand_apart(settings):
    page = settings
    page.evaluate("() => document.querySelector('[data-job-os-view=settings]').click()")
    page.wait_for_selector("#job-os-settings-connections .set-group")
    page.wait_for_timeout(600)
    out = page.evaluate("""() => { const c = [...document.querySelectorAll('#job-os-settings-connections .set-group')].map(e => e.getBoundingClientRect()), p = document.querySelector('#job-os-settings-connections .set-head p').getBoundingClientRect();
      return {below: c[0].top - p.bottom, between: c[1].top - c[0].bottom}; }""")
    assert out["below"] == out["between"], out


def test_the_section_list_contents_read_a_pixel_lower(settings):
    page = settings
    page.evaluate("() => document.querySelector('[data-job-os-view=settings]').click()")
    page.wait_for_selector(".settings-nav-item")
    page.wait_for_timeout(600)
    undo = "#jobOsRoot .settings-nav-item>*,#jobOsRoot .settings-nav-group{translate:none!important}"
    item = ".settings-nav-item:nth-of-type(2)"
    page.evaluate("s => { document.querySelector(s).id = 'fxNav'; }", ".settings-nav-item")
    assert _moved(page, "#fxNav", "icon", undo) == 1
    assert _moved(page, "#fxNav strong", "text", undo) == 1
    assert _moved(page, ".settings-nav-group>span", "text", undo) == 1


# ── Skills ──────────────────────────────────────────────────────────────────

def test_the_safe_card_is_as_tall_as_the_metadata_card(real_2x):
    page = real_2x
    _open(page, "skills", "#skillsList .skill-item")
    page.click("#skillsList .skill-item")
    page.wait_for_selector("#skillDetailBody .skill-frontmatter")
    page.wait_for_selector(".skill-security-badge", timeout=10000)
    page.wait_for_timeout(600)
    safe, meta = _rect(page, ".skill-security-section"), _rect(page, ".skill-frontmatter")
    assert abs(safe["height"] - meta["height"]) <= 1.5, (safe, meta)


# ── Logs ────────────────────────────────────────────────────────────────────

def test_the_logs_card_has_the_same_room_outside_as_the_other_cards(real_2x):
    page = real_2x
    _panel(page, "logs")
    out = page.evaluate("""() => { const c = document.getElementById('logsOutput').getBoundingClientRect(), b = document.querySelector('.logs-main-body').getBoundingClientRect();
      return [c.top - b.top, b.bottom - c.bottom, c.left - b.left, b.right - c.right]; }""")
    assert out == [24, 24, 24, 24]


# ── Activity ────────────────────────────────────────────────────────────────

def _activity(page):
    sid = page.evaluate("""async () => { const r = await fetch('/api/session/new', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'}); return (await r.json()).session.session_id; }""")
    _panel(page, "audit")
    page.evaluate("""sid => { _wireAuditList(); _renderAuditEntries([{session_id: sid, status: 'completed', content_preview: 'hello', submitted_at: Date.now() / 1000}]); }""", sid)
    page.wait_for_selector(".audit-entry")
    return sid


def test_an_activity_card_opens_its_conversation(real_2x):
    page = real_2x
    sid = _activity(page)
    page.click(".audit-entry")
    page.wait_for_function("sid => S.session && S.session.session_id === sid", arg=sid, timeout=10000)
    page.wait_for_timeout(300)
    assert page.evaluate("() => _currentPanel") == "chat"


def test_an_activity_card_opens_from_the_keyboard_and_lights_up_under_the_pointer(real_2x):
    page = real_2x
    sid = _activity(page)
    before = page.evaluate("() => getComputedStyle(document.querySelector('.audit-entry')).backgroundColor")
    page.hover(".audit-entry")
    page.wait_for_timeout(300)
    assert page.evaluate("() => getComputedStyle(document.querySelector('.audit-entry')).backgroundColor") != before
    assert page.evaluate("() => getComputedStyle(document.querySelector('.audit-entry')).cursor") == "pointer"
    page.focus(".audit-entry")
    page.keyboard.press("Enter")
    page.wait_for_function("sid => S.session && S.session.session_id === sid", arg=sid, timeout=10000)


# ── Files ───────────────────────────────────────────────────────────────────

def test_the_folder_pane_is_as_wide_as_the_side_panel(real_2x):
    page = real_2x
    _files_fixture(page)
    _open(page, "files", ".files-row")
    assert abs(_rect(page, ".files-browser")["width"] - _rect(page, ".sidebar")["width"]) <= 1


def test_coming_back_to_files_does_not_rebuild_it(real_2x):
    page = real_2x
    _files_fixture(page)
    _open(page, "files", ".files-row")
    page.evaluate("() => { document.querySelector('.files-list').dataset.same = '1'; document.querySelector('.files-row').dataset.same = '1'; document.querySelector('.files-workspace').dataset.same = '1'; }")
    _panel(page, "insights")
    page.evaluate("async () => { await switchPanel('files'); }")
    page.wait_for_timeout(50)
    assert page.evaluate("() => [document.querySelector('.files-row').dataset.same, document.querySelector('.files-workspace').dataset.same]") == ["1", "1"]
    page.wait_for_timeout(700)
    assert page.evaluate("() => [document.querySelector('.files-row').dataset.same, document.querySelector('.files-workspace').dataset.same]") == ["1", "1"]


def test_the_new_file_and_folder_buttons_show_only_the_attached_icons_beside_upload(real_2x):
    page = real_2x
    _files_fixture(page)
    _open(page, "files", ".files-action")
    out = page.evaluate("""() => [...document.querySelectorAll('.files-toolbar-actions .files-action')].map(b => { const i = b.firstElementChild, r = i.getBoundingClientRect(), s = getComputedStyle(i);
      return {text: b.textContent.trim(), w: r.width, h: r.height, label: b.getAttribute('aria-label'), mask: s.maskImage || s.webkitMaskImage, colour: s.backgroundColor, stroke: s.color, box: [b.getBoundingClientRect().width, b.getBoundingClientRect().height]}; })""")
    assert [o["label"] for o in out] == ["New file", "New folder", "Upload"], out
    assert all(not o["text"] and (o["w"], o["h"]) == (15, 15) and o["box"] == [32, 32] for o in out), out
    assert "new-file.png" in out[0]["mask"] and "new-folder.png" in out[1]["mask"], out
    assert out[0]["colour"] == out[2]["stroke"], out


def test_the_space_buttons_are_as_tall_as_other_side_panel_buttons_and_share_a_highlight(real_2x):
    page = real_2x
    _open(page, "memory", "#memoryPanel .side-menu-item")
    height = _rect(page, "#memoryPanel .side-menu-item")["height"]
    _files_fixture(page)
    _open(page, "files", ".files-workspace")
    assert abs(_rect(page, ".files-workspace")["height"] - height) <= 1, (_rect(page, ".files-workspace"), height)
    tops = []
    for row in page.query_selector_all(".files-workspace"):
        row.hover()
        page.wait_for_timeout(420)
        pill = page.evaluate("""() => { const p = document.querySelector('.files-workspace-list .mi-hover-pill'); return {y: p.getBoundingClientRect().top, o: getComputedStyle(p).opacity}; }""")
        assert pill["o"] == "1" and abs(pill["y"] - row.bounding_box()["y"]) <= .5
        tops.append(pill["y"])
    assert tops[0] != tops[1]


def test_opening_a_file_stands_as_placeholder_lines_then_fades_in(real_2x):
    page = real_2x
    _files_fixture(page)

    def slow(route):
        page.wait_for_timeout(0)
        route.fulfill(json={"path": "note.md", "content": "hello", "size": 5, "lines": 1})

    page.route("**/api/file-manager/read*", slow)
    _open(page, "files", ".files-row[data-file-path='note.md']")
    seen = page.evaluate("""async () => { document.querySelector(".files-row[data-file-path='note.md']").click(); await new Promise(r => requestAnimationFrame(r));
      return {bars: document.querySelectorAll('.files-inspector .skel i').length, hidden: document.querySelector('.files-inspector-content').dataset.skelHide}; }""")
    assert seen["bars"] > 3 and seen["hidden"] == "loading", seen
    page.wait_for_selector(".files-editor")
    page.wait_for_timeout(900)
    assert page.evaluate("() => [document.querySelectorAll('.files-inspector .skel').length, document.querySelector('.files-editor').value]") == [0, "hello"]


def test_going_into_and_out_of_a_folder_slides_the_list(real_2x):
    page = real_2x
    _files_fixture(page)
    _open(page, "files", ".files-row[data-file-path='docs']")
    page.click(".files-row[data-file-path='docs']")
    page.wait_for_selector(".files-empty-list")
    assert page.evaluate("() => document.querySelector('.files-list').classList.contains('is-in-forward')")
    page.click(".files-crumb[data-path='.']")
    page.wait_for_selector(".files-row")
    assert page.evaluate("() => document.querySelector('.files-list').classList.contains('is-in-back')")


def test_a_file_dragged_onto_a_folder_moves_there(real_2x):
    page = real_2x
    _files_fixture(page)
    _open(page, "files", ".files-row[data-file-path='note.md']")
    with page.expect_request("**/api/file-manager/move", timeout=5000) as move:
        _dnd(page, ".files-row[data-file-path='note.md']", ".files-row[data-file-path='docs']")
    assert move.value.post_data_json["path"] == "note.md" and move.value.post_data_json["destination"] == "docs"
    assert page.evaluate("() => window.__dropLit") is True


def test_a_folder_cannot_be_dropped_on_itself_and_a_file_cannot_be_dropped_on_a_file(real_2x):
    page = real_2x
    _files_fixture(page)
    _open(page, "files", ".files-row[data-file-path='note.md']")
    moves = []
    page.on("request", lambda r: moves.append(r.url) if r.url.endswith("/move") else None)
    _dnd(page, ".files-row[data-file-path='docs']", ".files-row[data-file-path='docs']")
    _dnd(page, ".files-row[data-file-path='docs']", ".files-row[data-file-path='note.md']")
    page.wait_for_timeout(300)
    assert moves == []


def test_a_row_dragged_onto_a_crumb_moves_up(real_2x):
    page = real_2x
    listing = [{"name": "note.md", "path": "docs/note.md", "type": "file", "size": 1}]
    _files_fixture(page)
    page.route("**/api/file-manager/list*", lambda route: route.fulfill(json={"path": "docs" if "path=docs" in route.request.url else ".", "entries": listing if "path=docs" in route.request.url else [{"name": "docs", "path": "docs", "type": "dir"}]}))
    _open(page, "files", ".files-row[data-file-path='docs']")
    page.click(".files-row[data-file-path='docs']")
    page.wait_for_selector(".files-row[data-file-path='docs/note.md']")
    with page.expect_request("**/api/file-manager/move", timeout=5000) as move:
        _dnd(page, ".files-row[data-file-path='docs/note.md']", ".files-crumb[data-path='.']")
    assert move.value.post_data_json["destination"] == "."


def test_a_file_from_the_computer_uploads_to_the_folder_it_lands_on(real_2x):
    page = real_2x
    _files_fixture(page)
    _open(page, "files", ".files-row[data-file-path='docs']")
    with page.expect_request("**/api/file-manager/upload", timeout=5000) as upload:
        page.evaluate("""() => { const data = new DataTransfer(); data.items.add(new File(['hi'], 'hi.txt', {type: 'text/plain'}));
          const row = document.querySelector(".files-row[data-file-path='docs']");
          row.dispatchEvent(new DragEvent('dragover', {bubbles: true, cancelable: true, dataTransfer: data})); row.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: data})); }""")
    assert upload.value.post_data_json["filename"] == "hi.txt" and upload.value.post_data_json["path"] == "docs"


def test_a_read_only_space_offers_no_dragging(real_2x):
    page = real_2x
    _files_fixture(page)
    page.route("**/api/file-manager/workspaces*", lambda route: route.fulfill(json={"workspaces": [{"id": "a", "name": "Home", "available": True, "read_only": True}]}))
    _open(page, "files", ".files-row")
    assert page.evaluate("() => document.querySelectorAll('.files-row[draggable=\"true\"]').length") == 0
