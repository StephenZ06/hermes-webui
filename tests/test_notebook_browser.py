"""Notes page (BlockNote): writing, autosave, placement, failure recovery, switching, trash, search."""

import json
import urllib.request
import uuid

import pytest

from tests._pytest_port import BASE


def _api(path, body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "Origin": BASE})
    return json.loads(urllib.request.urlopen(req, timeout=20).read() or b"{}")


def _open(page):
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate("() => { try { localStorage.removeItem('hermes-notebook-last'); } catch (e) {} }")
    page.evaluate("async () => { await switchPanel('notebook'); }")
    page.wait_for_selector("#notebookSidebar .nb-nav", timeout=15000)


def _new_note(page, title):
    page.click(".nb-list-head [data-nb-action=new]")
    page.wait_for_selector(".hermes-note-editor .bn-editor", timeout=30000)
    # newNote() creates the note on the server, opens it, then focuses its
    # empty title. With a note already open the editor selector above matches
    # at once, so on a slow runner the title used to land in the previous note
    # (and the new one never reached "saved"). Wait for the new, empty title.
    page.wait_for_function(
        "() => { const t = document.getElementById('nbTitle'); return !!t && document.activeElement === t && t.value === ''; }",
        timeout=30000)
    page.fill("#nbTitle", title)


def _type_body(page, text):
    page.click(".hermes-note-editor .bn-editor")
    page.keyboard.type(text)


def _saved(page):
    page.wait_for_function("() => document.querySelector('.nb-status') && document.querySelector('.nb-status').dataset.status === 'saved'", timeout=15000)


def _note_by_title(title):
    return next(n for n in _api("/api/notebook/bootstrap")["notes"] if n["title"] == title)


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            tab = browser.new_page(viewport={"width": 1440, "height": 900})
            errors = []
            tab.on("pageerror", lambda e: errors.append(str(e)))
            yield tab
            assert not errors, errors
        finally:
            browser.close()


def test_write_autosave_and_reload(page):
    title = f"Architecture {uuid.uuid4().hex[:6]}"
    _open(page)
    _new_note(page, title)
    _type_body(page, "Design notes for the orchestration layer")
    page.keyboard.press("Enter")
    page.keyboard.type("/heading")
    page.wait_for_selector(".bn-suggestion-menu", timeout=10000)
    page.keyboard.press("Enter")
    page.keyboard.type("Goals")
    _saved(page)
    note = _api("/api/notebook/notes/" + _note_by_title(title)["id"])["note"]
    assert [b["type"] for b in note["content"]][:2] == ["paragraph", "heading"]
    page.reload()
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate("async () => { await switchPanel('notebook'); }")
    page.click(f".nb-item:has-text('{title}')")
    page.wait_for_function("(t) => document.querySelector('#nbTitle') && document.querySelector('#nbTitle').value === t", arg=title, timeout=15000)
    page.wait_for_selector(".hermes-note-editor [data-content-type=heading]", timeout=15000)
    assert "orchestration layer" in page.inner_text(".hermes-note-editor .bn-editor")


def test_notes_are_created_in_the_selected_folder_or_workspace(page):
    folder = _api("/api/notebook/folders/create", {"name": f"Ideas {uuid.uuid4().hex[:4]}"})["folder"]
    project = _api("/api/projects/create", {"name": f"Space {uuid.uuid4().hex[:4]}", "color": "#5fbf9f"})["project"]
    _open(page)
    page.click(f".nb-place-btn[data-nb-kind=folder][data-nb-id='{folder['id']}']")
    _new_note(page, "In a folder")
    _saved(page)
    page.click(f".nb-place-btn[data-nb-kind=project][data-nb-id='{project['project_id']}']")
    _new_note(page, "In a workspace")
    _saved(page)
    placed = {n["title"]: (n["project_id"], n["folder_id"]) for n in _api("/api/notebook/bootstrap")["notes"]}
    assert placed["In a folder"] == (None, folder["id"])
    assert placed["In a workspace"] == (project["project_id"], None)
    # The folder is a Notes-only folder: it is not a workspace anywhere else.
    assert all(p["project_id"] != folder["id"] for p in _api("/api/projects")["projects"])


def test_a_failed_save_keeps_the_text_and_retries(page):
    title = f"Offline {uuid.uuid4().hex[:6]}"
    _open(page)
    _new_note(page, title)
    _saved(page)
    page.route("**/api/notebook/notes/*/update", lambda route: route.abort())
    _type_body(page, "written while offline")
    page.wait_for_function("() => document.querySelector('.nb-status').dataset.status === 'error'", timeout=15000)
    draft = page.evaluate("() => Object.keys(localStorage).filter(k => k.startsWith('hermes-notebook-draft:')).length")
    assert "written while offline" in page.inner_text(".hermes-note-editor .bn-editor")
    page.unroute("**/api/notebook/notes/*/update")
    page.click("[data-nb-action=retry]")
    _saved(page)
    note = _api("/api/notebook/notes/" + _note_by_title(title)["id"])["note"]
    assert draft == 1
    assert "written while offline" in json.dumps(note["content"])
    assert page.evaluate("() => Object.keys(localStorage).filter(k => k.startsWith('hermes-notebook-draft:')).length") == 0


def test_switching_notes_mid_edit_saves_the_first(page):
    first, second = f"First {uuid.uuid4().hex[:6]}", f"Second {uuid.uuid4().hex[:6]}"
    _open(page)
    _new_note(page, second)
    _saved(page)
    _new_note(page, first)
    _type_body(page, "typed just before switching")
    page.click(f".nb-item:has-text('{second}')")  # well inside the autosave delay
    page.wait_for_function("(t) => { const e = document.querySelector('#nbTitle'); return !!e && e.value === t; }", arg=second, timeout=15000)
    note = _api("/api/notebook/notes/" + _note_by_title(first)["id"])["note"]
    assert "typed just before switching" in json.dumps(note["content"])


def test_trash_restore_and_search(page):
    title = f"Searchable {uuid.uuid4().hex[:6]}"
    _open(page)
    _new_note(page, title)
    _type_body(page, "zebra quantum bridge")
    _saved(page)
    page.fill("#nbSearch", "quantum bridge")
    page.wait_for_function("(t) => [...document.querySelectorAll('.nb-item strong')].map(e => e.textContent).includes(t)", arg=title, timeout=10000)
    page.fill("#nbSearch", "")
    page.click("[data-nb-action=menu]")
    page.click(".nb-menu-item:has-text('Move to trash')")
    page.wait_for_function("(t) => ![...document.querySelectorAll('.nb-item strong')].map(e => e.textContent).includes(t)", arg=title, timeout=10000)
    assert _note_by_title(title)["deleted_at"]
    page.click("[data-nb-scope=trash]")
    page.click(f".nb-item:has-text('{title}')")
    page.click(".nb-banner [data-nb-action=restore]")
    page.wait_for_function("() => !document.querySelector('.nb-banner [data-nb-action=restore]')", timeout=10000)
    assert _note_by_title(title)["deleted_at"] is None


def test_send_to_chat_prefills_a_chat_without_sending(page):
    title = f"Brief {uuid.uuid4().hex[:6]}"
    _open(page)
    _new_note(page, title)
    _type_body(page, "Fix the white artifacts around the platforms")
    _saved(page)
    page.click("[data-nb-action=menu]")
    page.click(".nb-menu-item:has-text('Send to chat')")
    page.wait_for_function("() => document.querySelector('main.main') && !document.querySelector('main.main.showing-notebook')", timeout=10000)
    page.wait_for_function("(t) => document.querySelector('#msg').value.includes(t)", arg=title, timeout=10000)
    composer = page.input_value("#msg")
    assert "Fix the white artifacts around the platforms" in composer



def test_side_panel_matches_work_hub_and_its_plus_menu_creates_and_deletes(page):
    folder_name = f"Drafts {uuid.uuid4().hex[:4]}"
    _open(page)
    # Same section markup as the Work Hub: headings with the divider, tiles, a centred + row.
    headings = page.evaluate("() => [...document.querySelectorAll('#notebookSidebar .work-hub-projects-heading span')].map(e => e.textContent)")
    assert headings[:2] == ["WORKSPACES", "FOLDERS"]
    assert not page.query_selector(".nb-new-btn")
    assert "Folders you create here" not in page.inner_text("#notebookSidebar")
    page.click("#notebookSidebar .nb-create-row .work-hub-project-create")
    items = page.evaluate("() => [...document.querySelectorAll('.nb-create-menu button')].map(b => b.textContent)")
    assert items == ["New note", "New folder", "Delete"]
    page.click(".nb-create-menu [data-nb-create=folder]")
    page.fill("#appDialogInput", folder_name)
    page.click("#appDialogConfirm")
    tile = f"#notebookSidebar .nb-place-btn[data-nb-kind=folder]:has-text('{folder_name}')"
    page.wait_for_selector(tile, timeout=10000)
    folder_id = page.get_attribute(tile, "data-nb-id")
    page.click("#notebookSidebar .nb-create-row .work-hub-project-create")
    page.click(".nb-create-menu [data-nb-create=note]")
    # New note turns the same menu into a "where" picker: General, workspaces, folders.
    page.wait_for_selector(".nb-create-menu.is-picking", timeout=5000)
    choices = page.evaluate("() => [...document.querySelectorAll('.nb-create-menu .nb-pick-item')].map(b => b.dataset.nbPick)")
    projects = [p["project_id"] for p in _api("/api/notebook/bootstrap")["projects"]]
    assert choices[0] == "general" and ["p:" + p for p in projects] == [c for c in choices if c.startswith("p:")]
    assert "f:" + folder_id in choices
    page.click(f".nb-create-menu [data-nb-pick='f:{folder_id}']")
    page.wait_for_selector(".hermes-note-editor .bn-editor", timeout=30000)
    page.fill("#nbTitle", "Inside drafts")
    _saved(page)
    assert _note_by_title("Inside drafts")["folder_id"] == folder_id
    # The whole tile toggles its notes in place (no re-render, so it animates).
    tile_by_id = f"#notebookSidebar .nb-place-btn[data-nb-id='{folder_id}']"
    page.evaluate(f"() => {{ window.__tile = document.querySelector(\"{tile_by_id}\"); }}")
    expanded_before = page.get_attribute(tile_by_id, "aria-expanded")
    page.click(tile_by_id)
    state = page.evaluate(f"""() => {{ const t = document.querySelector("{tile_by_id}");
      return {{same: t === window.__tile, expanded: t.getAttribute('aria-expanded'),
               open: document.getElementById(t.getAttribute('aria-controls')).classList.contains('expanded')}}; }}""")
    assert state["same"] and state["expanded"] != expanded_before and state["open"] == (state["expanded"] == "true")
    if state["expanded"] != "true":
        page.click(tile_by_id)
    # Delete mode: notes and Notes folders wiggle with an X; workspaces stay locked.
    page.click("#notebookSidebar .nb-create-row .work-hub-project-create")
    page.click(".nb-create-menu [data-nb-create=delete]")
    page.wait_for_selector("#notebookSidebar .work-hub-project-delete-done", timeout=5000)
    row = f"#notebookSidebar [data-nb-note-row]:has-text('Inside drafts')"
    assert "dm-wiggle" in page.get_attribute(row, "class")
    page.click(f"{row} .dm-x", force=True)  # the row wiggles on purpose
    page.wait_for_function("() => !document.querySelector('#notebookSidebar [data-nb-note-row] span') || ![...document.querySelectorAll('#notebookSidebar [data-nb-note-row] span')].some(e => e.textContent === 'Inside drafts')", timeout=10000)
    assert _note_by_title("Inside drafts")["deleted_at"]
    page.click("#notebookSidebar .work-hub-project-delete-done")
    page.wait_for_selector("#notebookSidebar .nb-create-row .work-hub-project-create", timeout=5000)



def test_trash_is_centred_and_section_dividers_have_equal_space(page):
    _api("/api/notebook/folders/create", {"name": f"Spacing {uuid.uuid4().hex[:4]}"})
    _api("/api/projects/create", {"name": f"Spacing space {uuid.uuid4().hex[:4]}", "color": "#5fbf9f"})
    _open(page)
    trash = page.evaluate("""() => { const b = document.querySelector('#notebookSidebar .nb-trash-scope'); const r = b.getBoundingClientRect();
      const kids = [...b.children].map(e => e.getBoundingClientRect()); const left = Math.min(...kids.map(k => k.left)), right = Math.max(...kids.map(k => k.right));
      return {leftGap: Math.round(left - r.left), rightGap: Math.round(r.right - right)}; }""")
    assert abs(trash["leftGap"] - trash["rightGap"]) <= 2, trash
    gaps = page.evaluate("""() => [...document.querySelectorAll('#notebookSidebar .work-hub-projects-heading')].slice(0, 2).map(h => {
      const line = h.getBoundingClientRect().top + h.getBoundingClientRect().height / 2;
      const prev = h.previousElementSibling;
      const above = prev.matches('.work-hub-scope') ? [prev] : [...prev.querySelectorAll('.work-hub-project-tile, .work-hub-board-row')]
        .filter(e => { const g = e.closest('.project-folder-sessions'); return !g || g.classList.contains('expanded'); });
      const below = h.nextElementSibling.querySelector('.work-hub-project-tile');
      return [Math.round(line - Math.max(...above.map(e => e.getBoundingClientRect().bottom))), below ? Math.round(below.getBoundingClientRect().top - line) : null];
    })""")
    for above, below in gaps:
        if below is not None:
            assert abs(above - below) <= 1, gaps


def test_work_hub_scope_buttons_are_spaced_like_the_notes_ones(page):
    _open(page)
    def spacing(root):
        return page.evaluate("""(root) => { const [a, b] = document.querySelectorAll(root + ' .work-hub-scope');
          return Math.round((b.getBoundingClientRect().top - a.getBoundingClientRect().bottom) * 10) / 10; }""", root)
    notes = spacing("#notebookSidebar")
    page.evaluate("async () => { await switchPanel('notes'); }")
    page.wait_for_selector("#workHubSidebar .work-hub-scope", timeout=15000)
    assert notes > 0 and spacing("#workHubSidebar") == notes


@pytest.mark.parametrize("panel", ["notes", "notebook"])
def test_opening_a_workspace_does_not_slide_its_rows(page, panel):
    """Work Hub and Notes share .project-folder-sessions. A collapsed 5px
    margin-left (zeroed by the expanded rule) made each open slide the child
    rows and their icons 5px sideways while the margin transitioned, and an
    animated 0->2px margin-top made them drift 2px down."""
    project = _api("/api/projects/create", {"name": f"Slide {uuid.uuid4().hex[:4]}", "color": "#7c8cff"})["project"]
    _api("/api/notebook/notes/create", {"title": "Row", "project_id": project["project_id"]})
    # Two boards: a Work Hub folder with one board opens it instead of expanding.
    for name in ("Board A", "Board B"):
        boot = _api("/api/work_hub/bootstrap")
        _api("/api/work_hub/boards/create", {"board": {"name": name, "project_id": project["project_id"]}, "expected_revision": boot["revision"]})
    _open(page)
    page.evaluate(f"async () => {{ await switchPanel('{panel}'); }}")
    tile = (f"#workHubSidebar [data-project-toggle='{project['project_id']}']" if panel == "notes"
            else f"#notebookSidebar .nb-place-btn[data-nb-id='{project['project_id']}']")
    page.wait_for_selector(tile, timeout=15000)
    xs = page.evaluate("""(sel) => new Promise((resolve) => {
      const tile = document.querySelector(sel);
      const group = document.getElementById(tile.getAttribute('aria-controls'));
      const xs = []; const t0 = performance.now();
      tile.click();
      const tick = () => {
        const row = group.querySelector('.work-hub-board-row');
        if (row) {
          const r = row.getBoundingClientRect();
          xs.push([r.left, r.top - tile.getBoundingClientRect().bottom].map((v) => Math.round(v * 10) / 10));
        }
        if (performance.now() - t0 < 400) requestAnimationFrame(tick); else resolve(xs);
      };
      requestAnimationFrame(tick);
    })""", tile)
    lefts, tops = [x for x, _ in xs], [y for _, y in xs]
    assert len(xs) > 5, xs
    assert max(lefts) - min(lefts) < 0.5, xs
    assert max(tops) - min(tops) < 0.5, xs


@pytest.fixture
def touch_page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            ctx = browser.new_context(viewport={"width": 393, "height": 852}, has_touch=True, is_mobile=True)
            yield ctx.new_page()
        finally:
            browser.close()


def _block_texts(page):
    return page.evaluate("() => Notebook.editor.getBlocks().map(b => (b.content || []).map(c => c.text).join(''))")


def test_touch_grip_drags_a_line_to_a_new_place(touch_page):
    page = touch_page
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate("async () => { await switchPanel('notebook'); }")
    page.wait_for_selector(".nb-list-head [data-nb-action=new]", timeout=15000)
    page.click(".nb-list-head [data-nb-action=new]")
    page.wait_for_selector(".hermes-note-editor .bn-editor", timeout=30000)
    page.click(".hermes-note-editor .bn-editor")
    for word in ("one", "two", "three"):
        page.keyboard.type(word)
        page.keyboard.press("Enter")
    page.keyboard.press("Backspace")
    assert _block_texts(page)[:3] == ["one", "two", "three"]
    # Cursor is in "three": drag its grip up above "one".
    page.wait_for_selector(".nb-grip:not([hidden])", timeout=5000)
    grip = page.locator(".nb-grip").bounding_box()
    first = page.locator(".hermes-note-editor .bn-block-content").first.bounding_box()
    page.mouse.move(grip["x"] + 10, grip["y"] + 10)
    page.mouse.down()
    page.mouse.move(grip["x"] + 10, (grip["y"] + first["y"]) / 2, steps=5)
    page.mouse.move(grip["x"] + 10, first["y"] + 2, steps=5)
    page.mouse.up()
    page.wait_for_function("() => Notebook.editor.getBlocks()[0].content[0].text === 'three'", timeout=5000)
    assert _block_texts(page)[:3] == ["three", "one", "two"]
    # After the move the grip follows the line the cursor is really in.
    for index in (1, 2, 0):
        block = page.locator(".hermes-note-editor .bn-block-content").nth(index)
        block.click()
        page.wait_for_timeout(250)
        line = block.bounding_box()
        mark = page.locator(".nb-grip").bounding_box()
        centre = mark["y"] + mark["height"] / 2
        assert line["y"] - 4 <= centre <= line["y"] + line["height"] + 4, (index, line, mark)


def test_desktop_has_no_touch_grip(page):
    _open(page)
    page.click(".nb-list-head [data-nb-action=new]")
    page.wait_for_selector(".hermes-note-editor .bn-editor", timeout=30000)
    assert page.query_selector(".nb-grip") is None


def test_touch_format_toolbar_is_pinned_and_menus_open_upward(touch_page):
    page = touch_page
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate("async () => { await switchPanel('notebook'); }")
    page.wait_for_selector(".nb-list-head [data-nb-action=new]", timeout=15000)
    page.click(".nb-list-head [data-nb-action=new]")
    page.wait_for_selector(".hermes-note-editor .bn-editor", timeout=30000)
    page.click(".hermes-note-editor .bn-editor")
    page.keyboard.type("hello world")
    page.keyboard.press("Control+a")
    page.wait_for_selector(".bn-formatting-toolbar", timeout=5000)
    page.wait_for_timeout(400)
    box = page.locator(".bn-formatting-toolbar").bounding_box()
    height = page.evaluate("() => window.innerHeight")
    # No keyboard here: the visual viewport is the window, so the toolbar sits on its bottom edge.
    assert abs((box["y"] + box["height"]) - height) <= 2, (box, height)
    page.evaluate("() => window.scrollBy(0, 40)")
    page.wait_for_timeout(200)
    again = page.locator(".bn-formatting-toolbar").bounding_box()
    assert abs(again["y"] - box["y"]) <= 1, (box, again)
    page.click(".bn-formatting-toolbar button.mantine-Button-root")
    page.wait_for_selector(".mantine-Menu-dropdown", timeout=5000)
    page.wait_for_timeout(300)
    menu = page.locator(".mantine-Menu-dropdown").bounding_box()
    bar = page.locator(".bn-formatting-toolbar").bounding_box()
    assert menu["y"] + menu["height"] <= bar["y"] + 2, (menu, bar)


def test_touch_scroll_does_not_hide_the_format_toolbar_and_tag_box_fits_its_text(touch_page):
    page = touch_page
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate("async () => { await switchPanel('notebook'); }")
    page.wait_for_selector(".nb-list-head [data-nb-action=new]", timeout=15000)
    page.click(".nb-list-head [data-nb-action=new]")
    page.wait_for_selector(".hermes-note-editor .bn-editor", timeout=30000)
    page.evaluate("() => document.fonts.ready")
    page.wait_for_timeout(300)
    width = page.evaluate("() => document.getElementById('nbTagInput').getBoundingClientRect().width")
    placeholder = page.evaluate("() => { const i = document.getElementById('nbTagInput'); const c = document.createElement('canvas').getContext('2d'); const s = getComputedStyle(i); c.font = s.fontStyle + ' ' + s.fontWeight + ' ' + s.fontSize + ' ' + s.fontFamily; return c.measureText(i.placeholder).width; }")
    assert placeholder < width < placeholder + 40, (width, placeholder)
    page.click(".hermes-note-editor .bn-editor")
    page.keyboard.type("hello world")
    page.keyboard.press("Control+a")
    page.wait_for_selector(".bn-formatting-toolbar", timeout=5000)
    # A finger that starts scrolling: pointerdown, then pointercancel.
    page.evaluate("""() => {
        const el = document.querySelector('.hermes-note-editor .bn-editor');
        const opts = {pointerType: 'touch', bubbles: true, cancelable: true, composed: true};
        el.dispatchEvent(new PointerEvent('pointerdown', opts));
        el.dispatchEvent(new PointerEvent('pointercancel', opts));
    }""")
    page.wait_for_timeout(500)
    assert page.query_selector(".bn-formatting-toolbar") is not None


_PNG_1PX = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def _add_images_roundtrip(tab):
    import base64
    tab.goto(BASE + "/", wait_until="domcontentloaded")
    tab.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    tab.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    tab.evaluate("async () => { await switchPanel('notebook'); }")
    tab.wait_for_selector(".nb-list-head [data-nb-action=new]", timeout=15000)
    tab.click(".nb-list-head [data-nb-action=new]")
    tab.wait_for_selector(".hermes-note-editor .bn-editor", timeout=30000)
    png = base64.b64decode(_PNG_1PX)
    tab.click(".hermes-note-editor .bn-editor")
    tab.keyboard.type("before")
    with tab.expect_file_chooser() as chooser:
        tab.click(".nb-editor-head [data-nb-action=add-image]")
    chooser.value.set_files([
        {"name": "one.png", "mimeType": "image/png", "buffer": png},
        {"name": "two.png", "mimeType": "image/png", "buffer": png},
    ])
    tab.wait_for_function("() => Notebook.editor.getBlocks().filter(b => b.type === 'image').length === 2", timeout=15000)
    urls = tab.evaluate("() => Notebook.editor.getBlocks().filter(b => b.type === 'image').map(b => b.props.url)")
    assert all(u.startswith("/api/notebook/files/") for u in urls) and urls[0] != urls[1]
    # They are drawn, not just stored: both images are in the page and decoded.
    tab.wait_for_function("() => { const m = [...document.querySelectorAll('.hermes-note-editor .bn-visual-media')]; return m.length === 2 && m.every(i => i.complete && i.naturalWidth > 0); }", timeout=15000)
    assert tab.evaluate("() => Notebook.editor.getBlocks()[0].content[0].text") == "before"


def test_add_images_button_inserts_each_picked_image_desktop(page):
    _add_images_roundtrip(page)


def test_add_images_button_inserts_each_picked_image_touch(touch_page):
    _add_images_roundtrip(touch_page)
