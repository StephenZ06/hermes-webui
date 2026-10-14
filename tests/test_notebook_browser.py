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
        tab.click(".nb-editor-head [data-nb-action=add-files]")
    chooser.value.set_files([
        {"name": "one.png", "mimeType": "image/png", "buffer": png},
        {"name": "two.png", "mimeType": "image/png", "buffer": png},
        {"name": "Plan.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4\n%%EOF"},
    ])
    tab.wait_for_function("() => Notebook.editor.getBlocks().filter(b => b.type === 'image').length === 2 && Notebook.editor.getBlocks().filter(b => b.type === 'file').length === 1", timeout=15000)
    document = tab.evaluate("() => Notebook.editor.getBlocks().find(b => b.type === 'file').props")
    assert document["name"] == "Plan.pdf" and document["url"].startswith("/api/notebook/files/")
    tab.wait_for_selector(".hermes-note-editor [data-content-type=file]", timeout=10000)
    urls = tab.evaluate("() => Notebook.editor.getBlocks().filter(b => b.type === 'image').map(b => b.props.url)")
    assert all(u.startswith("/api/notebook/files/") for u in urls) and urls[0] != urls[1]
    # They are drawn, not just stored: both images are in the page and decoded.
    tab.wait_for_function("() => { const m = [...document.querySelectorAll('.hermes-note-editor .bn-visual-media')]; return m.length === 2 && m.every(i => i.complete && i.naturalWidth > 0); }", timeout=15000)
    assert tab.evaluate("() => Notebook.editor.getBlocks()[0].content[0].text") == "before"


def test_add_images_button_inserts_each_picked_image_desktop(page):
    _add_images_roundtrip(page)


def test_add_images_button_inserts_each_picked_image_touch(touch_page):
    _add_images_roundtrip(touch_page)


def test_documents_download_and_images_show_inline():
    import base64
    import urllib.request
    pdf = _api("/api/notebook/uploads", {"filename": "Plan.pdf", "content_base64": base64.b64encode(b"%PDF-1.4\n%%EOF").decode()})
    png = _api("/api/notebook/uploads", {"filename": "dot.png", "content_base64": _PNG_1PX})
    doc = urllib.request.urlopen(BASE + pdf["url"], timeout=10)
    assert doc.headers["Content-Disposition"].startswith("attachment; filename*=UTF-8''Plan.pdf")
    assert doc.headers["X-Content-Type-Options"] == "nosniff" and "sandbox" in doc.headers["Content-Security-Policy"]
    assert doc.headers["Content-Type"] == "application/pdf"
    assert urllib.request.urlopen(BASE + png["url"], timeout=10).headers["Content-Disposition"] == "inline"


def _png(width, height):
    import struct
    import zlib
    raw = b"".join(b"\x00" + b"\x40\x80\xc0" * width for _ in range(height))
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def _picture_in_note(tab):
    tab.goto(BASE + "/", wait_until="domcontentloaded")
    tab.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    tab.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    tab.evaluate("async () => { await switchPanel('notebook'); }")
    tab.wait_for_selector(".nb-list-head [data-nb-action=new]", timeout=15000)
    tab.click(".nb-list-head [data-nb-action=new]")
    tab.wait_for_selector(".hermes-note-editor .bn-editor", timeout=30000)
    with tab.expect_file_chooser() as chooser:
        tab.click(".nb-editor-head [data-nb-action=add-files]")
    chooser.value.set_files([{"name": "wide.png", "mimeType": "image/png", "buffer": _png(600, 300)}])
    tab.wait_for_function("() => { const i = document.querySelector('.bn-visual-media'); return i && i.complete && i.naturalWidth > 0; }", timeout=15000)


def test_a_tapped_picture_gets_a_themed_outline_and_no_corner_dots_desktop(page):
    _picture_in_note(page)
    assert page.query_selector(".nb-img-outline:not([hidden])") is None  # nothing selected yet
    page.click(".bn-visual-media")
    page.wait_for_selector(".nb-img-outline:not([hidden])", timeout=5000)
    outline = page.evaluate("""() => {
        const box = document.querySelector('.nb-img-outline').getBoundingClientRect();
        const img = document.querySelector('.bn-visual-media').getBoundingClientRect();
        const style = getComputedStyle(document.querySelector('.nb-img-outline'));
        const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
        const probe = Object.assign(document.createElement('i'), {}); probe.style.color = accent; document.body.appendChild(probe);
        const expected = getComputedStyle(probe).color; probe.remove();
        return {same: Math.abs(box.width - img.width) < 2 && Math.abs(box.height - img.height) < 2, color: style.borderTopColor, expected, width: style.borderTopWidth};
    }""")
    assert outline["same"] and outline["color"] == outline["expected"] and outline["width"] == "2px", outline
    assert page.query_selector(".nb-img-handle") is None  # the side bars are the only resize handles
    # Growing eases as shrinking does: the picture's wrapper transitions its width.
    assert page.evaluate("() => getComputedStyle(document.querySelector('.bn-visual-media').closest('.bn-file-block-content-wrapper')).transitionProperty") == "width"
    page.click(".nb-editor-head .nb-title")
    page.wait_for_selector(".nb-img-outline", state="hidden", timeout=5000)


def test_the_side_bars_resize_the_picture_and_the_outline_follows(page):
    _picture_in_note(page)
    page.click(".bn-visual-media")
    page.wait_for_selector(".bn-resize-handle", state="visible", timeout=5000)
    before = page.locator(".bn-visual-media").bounding_box()["width"]
    handle = page.locator(".bn-resize-handle").last.bounding_box()
    x, y = handle["x"] + handle["width"] / 2, handle["y"] + handle["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x - 150, y, steps=6)
    page.mouse.up()
    page.wait_for_function("() => Notebook.editor.getBlocks().find(b => b.type === 'image').props.previewWidth > 0", timeout=5000)
    width = page.evaluate("() => Notebook.editor.getBlocks().find(b => b.type === 'image').props.previewWidth")
    assert abs(width - (before - 150)) <= 4, (before, width)
    page.wait_for_function("() => { const o = document.querySelector('.nb-img-outline').getBoundingClientRect(), i = document.querySelector('.bn-visual-media').getBoundingClientRect(); return Math.abs(o.width - i.width) < 2; }", timeout=5000)


def test_picture_width_survives_the_markdown_round_trip_used_for_vault_notes(page):
    _open(page)
    page.click(".nb-list-head [data-nb-action=new]")
    page.wait_for_selector(".hermes-note-editor .bn-editor", timeout=30000)
    result = page.evaluate("""async () => {
        const editor = Notebook.editor.editor;
        editor.replaceBlocks(editor.document, [
            {type: 'image', props: {url: '/api/notebook/files/aa', name: 'one.png', previewWidth: 222}},
            {type: 'image', props: {url: '/api/notebook/files/bb', name: 'two.png'}},
        ]);
        const markdown = Notebook._widths.write();
        const blocks = Notebook._widths.read(await Notebook.editor.parseMarkdown(markdown));
        return {markdown, images: blocks.filter(b => b.type === 'image').map(b => [b.props.name, b.props.previewWidth || null])};
    }""")
    assert "![one.png|222](/api/notebook/files/aa)" in result["markdown"] and "![two.png](/api/notebook/files/bb)" in result["markdown"]
    assert result["images"] == [["one.png", 222], ["two.png", None]]


def test_touch_taps_on_buttons_do_not_steal_focus_from_the_editor(touch_page):
    page = touch_page
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate("async () => { await switchPanel('notebook'); }")
    page.wait_for_selector(".nb-list-head [data-nb-action=new]", timeout=15000)
    page.click(".nb-list-head [data-nb-action=new]")
    page.wait_for_selector(".hermes-note-editor .bn-editor", timeout=30000)
    probe = """(selector) => {
        const el = document.querySelector(selector);
        const event = new MouseEvent('mousedown', {bubbles: true, cancelable: true});
        el.dispatchEvent(event);
        return event.defaultPrevented;
    }"""
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    assert page.evaluate(probe, ".nb-editor-head [data-nb-action=toggle-pinned]") is False  # nothing is typing: leave it alone
    page.click(".hermes-note-editor .bn-editor")
    # The editor holds the keyboard: header buttons, the list and the app's top bar must not blur it.
    for target in (".nb-editor-head [data-nb-action=toggle-pinned]", ".nb-editor-head [data-nb-action=add-files]", ".topbar button, header button"):
        assert page.evaluate(probe, target) is True, target
    assert page.evaluate(probe, ".nb-editor-head [data-nb-action=back]") is False  # back lets go of the keyboard
    assert page.evaluate("() => !!document.activeElement.closest('.hermes-note-editor')")


def test_media_streams_up_and_plays_back_with_byte_ranges():
    import urllib.error
    import urllib.parse
    import urllib.request
    clip = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + bytes(range(256)) * 4096  # ~1 MB, not JSON-sized
    req = urllib.request.Request(BASE + "/api/notebook/uploads/stream?" + urllib.parse.urlencode({"filename": "clip.mp4"}), data=clip,
                                 headers={"Content-Type": "application/octet-stream", "Origin": BASE})
    saved = json.loads(urllib.request.urlopen(req, timeout=20).read())
    assert saved["mime"] == "video/mp4" and saved["size"] == len(clip) and saved["name"] == "clip.mp4"

    def get(range_header=None):
        headers = {"Range": range_header} if range_header else {}
        try:
            return urllib.request.urlopen(urllib.request.Request(BASE + saved["url"], headers=headers), timeout=10)
        except urllib.error.HTTPError as error:
            return error

    whole = get()
    assert whole.status == 200 and whole.headers["Accept-Ranges"] == "bytes" and whole.headers["Content-Disposition"] == "inline"
    assert whole.read() == clip
    part = get("bytes=100-199")
    assert part.status == 206 and part.headers["Content-Range"] == f"bytes 100-199/{len(clip)}" and part.read() == clip[100:200]
    assert get("bytes=-10").read() == clip[-10:]
    assert get(f"bytes={len(clip) - 5}-").read() == clip[-5:]
    assert get(f"bytes={len(clip) + 10}-").status == 416
    # A refused body (not media) is a clean error, not a hung connection.
    bad = urllib.request.Request(BASE + "/api/notebook/uploads/stream?filename=x.mp4", data=b"<html>nope</html>" * 100,
                                 headers={"Content-Type": "application/octet-stream", "Origin": BASE})
    with pytest.raises(urllib.error.HTTPError) as refused:
        urllib.request.urlopen(bad, timeout=10)
    assert refused.value.code == 415


_MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x01" * 4096
_MP3 = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x02" * 2048


def _add_media_roundtrip(tab):
    tab.goto(BASE + "/", wait_until="domcontentloaded")
    tab.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    tab.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    tab.evaluate("async () => { await switchPanel('notebook'); }")
    tab.wait_for_selector(".nb-list-head [data-nb-action=new]", timeout=15000)
    tab.click(".nb-list-head [data-nb-action=new]")
    tab.wait_for_selector(".hermes-note-editor .bn-editor", timeout=30000)
    with tab.expect_file_chooser() as chooser:
        tab.click(".nb-editor-head [data-nb-action=add-files]")
    chooser.value.set_files([
        {"name": "Clip.mp4", "mimeType": "video/mp4", "buffer": _MP4},
        {"name": "Voice.mp3", "mimeType": "audio/mpeg", "buffer": _MP3},
    ])
    tab.wait_for_function("() => { const t = Notebook.editor.getBlocks().map(b => b.type); return t.includes('video') && t.includes('audio'); }", timeout=15000)
    blocks = tab.evaluate("() => Notebook.editor.getBlocks().filter(b => b.type === 'video' || b.type === 'audio').map(b => [b.type, b.props.name, b.props.url])")
    assert {(kind, name) for kind, name, _ in blocks} == {("video", "Clip.mp4"), ("audio", "Voice.mp3")}
    assert all(url.startswith("/api/notebook/files/") for _, _, url in blocks)
    tab.wait_for_selector(".hermes-note-editor video", timeout=10000)
    tab.wait_for_selector(".hermes-note-editor audio", timeout=10000)


def test_add_audio_and_video_desktop(page):
    _add_media_roundtrip(page)


def test_add_audio_and_video_touch(touch_page):
    _add_media_roundtrip(touch_page)


def test_audio_and_video_survive_the_markdown_round_trip_used_for_vault_notes(page):
    _open(page)
    page.click(".nb-list-head [data-nb-action=new]")
    page.wait_for_selector(".hermes-note-editor .bn-editor", timeout=30000)
    result = page.evaluate("""async () => {
        const editor = Notebook.editor.editor;
        editor.replaceBlocks(editor.document, [
            {type: 'audio', props: {url: '/api/notebook/vault/file?path=Attachments%2Fa.mp3', name: 'a.mp3'}},
            {type: 'video', props: {url: '/api/notebook/vault/file?path=Attachments%2Fv.mov', name: 'v.mov'}},
        ]);
        const markdown = Notebook._widths.write();
        const blocks = Notebook._widths.read(await Notebook.editor.parseMarkdown(markdown));
        return {markdown, kinds: blocks.map(b => [b.type, b.props.name])};
    }""")
    assert "![a.mp3](/api/notebook/vault/file?path=Attachments%2Fa.mp3)" in result["markdown"] and "<audio" not in result["markdown"]
    assert result["kinds"] == [["audio", "a.mp3"], ["video", "v.mov"]]


def test_media_upload_carries_the_csrf_token_like_fetch_does(page):
    _open(page)
    page.click(".nb-list-head [data-nb-action=new]")
    page.wait_for_selector(".hermes-note-editor .bn-editor", timeout=30000)
    seen = page.evaluate("""async () => {
        window.__HERMES_CONFIG__ = Object.assign({}, window.__HERMES_CONFIG__, {csrfToken: 'tok-123'});
        const headers = {};
        const original = XMLHttpRequest.prototype.setRequestHeader;
        XMLHttpRequest.prototype.setRequestHeader = function (name, value) { headers[name] = value; return original.call(this, name, value); };
        const file = new File([new Uint8Array([0,0,0,24,102,116,121,112,109,112,52,50,0,0,0,0,109,112,52,50,105,115,111,109,1,1,1,1])], 'c.mp4', {type: 'video/mp4'});
        // the same path the slash menu and paste use: BlockNote's uploadFile hook
        const url = await Notebook._upload(file);
        XMLHttpRequest.prototype.setRequestHeader = original;
        return {headers, url};
    }""")
    assert seen["headers"].get("X-Hermes-CSRF-Token") == "tok-123", seen
    assert seen["url"].startswith("/api/notebook/files/")


def _bars_shown(tab):
    return tab.evaluate("() => [...document.querySelectorAll('.bn-resize-handle')].some(h => getComputedStyle(h).display !== 'none')")


def test_on_a_phone_pictures_fill_the_width_and_the_bars_wait_for_a_second_tap(touch_page):
    tab = touch_page
    _picture_in_note(tab)
    # No size of its own: the 600px picture (and a smaller one would) fills the phone's text width.
    shown = tab.evaluate("() => { const i = document.querySelector('.bn-visual-media').getBoundingClientRect(), e = document.querySelector('.hermes-note-editor .bn-editor').getBoundingClientRect(); return [Math.round(i.width), Math.round(e.width)]; }")
    assert shown[0] >= shown[1] - 70 and shown[0] <= shown[1], shown   # editor padding is 24 + 36
    assert not _bars_shown(tab)
    # A picture is not selectable like text (it has its own outline).
    assert tab.evaluate("() => { const s = getComputedStyle(document.querySelector('.bn-visual-media')); return [s.userSelect, s.webkitUserSelect]; }") == ["none", "none"]
    tab.tap(".bn-visual-media")                       # first tap: outline only
    tab.wait_for_selector(".nb-img-outline:not([hidden])", timeout=5000)
    tab.wait_for_timeout(300)
    assert not _bars_shown(tab)
    # iOS can swallow the click of a quick second tap (it starts its own selection), and the
    # editor re-renders a tapped picture a moment later: send the second tap as pointer events
    # only, onto a replaced element, in one tick, with no click at all.
    tab.evaluate("""() => {
        const i = document.querySelector('.bn-visual-media'); const copy = i.cloneNode(true); i.replaceWith(copy);
        const r = copy.getBoundingClientRect(), at = {clientX: r.x + r.width / 2, clientY: r.y + r.height / 2, pointerType: 'touch', bubbles: true, cancelable: true, composed: true};
        copy.dispatchEvent(new PointerEvent('pointerdown', at));
        copy.dispatchEvent(new PointerEvent('pointerup', at));
    }""")
    tab.wait_for_function("() => [...document.querySelectorAll('.bn-resize-handle')].some(h => getComputedStyle(h).display !== 'none')", timeout=5000)
    before = tab.locator(".bn-visual-media").bounding_box()["width"]
    handle = tab.locator(".bn-resize-handle[data-nb-on]").first.bounding_box()
    x, y = handle["x"] + handle["width"] / 2, handle["y"] + handle["height"] / 2
    tab.mouse.move(x, y)
    tab.mouse.down()
    tab.mouse.move(x + 90, y, steps=6)   # the left bar: dragging right shrinks
    tab.mouse.up()
    tab.wait_for_function("() => Notebook.editor.getBlocks().find(b => b.type === 'image').props.previewWidth > 0", timeout=5000)
    # Let go of the picture after a resize: no outline, bars or selection left behind.
    tab.wait_for_selector(".nb-img-outline", state="hidden", timeout=5000)
    assert not _bars_shown(tab)
    assert tab.evaluate("() => { const s = getSelection(); return s.rangeCount === 0 || s.isCollapsed || !document.querySelector('.hermes-note-editor').contains(s.anchorNode); }")
    assert tab.locator(".bn-visual-media").bounding_box()["width"] < before - 60
    # ...and it can be picked up and resized again (nothing is stuck).
    tab.tap(".bn-visual-media")
    tab.tap(".bn-visual-media")
    tab.wait_for_function("() => [...document.querySelectorAll('.bn-resize-handle')].some(h => getComputedStyle(h).display !== 'none')", timeout=5000)
    narrowed = tab.locator(".bn-visual-media").bounding_box()["width"]
    handle = tab.locator(".bn-resize-handle[data-nb-on]").last.bounding_box()
    x, y = handle["x"] + handle["width"] / 2, handle["y"] + handle["height"] / 2
    tab.mouse.move(x, y)
    tab.mouse.down()
    tab.mouse.move(x + 50, y, steps=5)   # the right bar: dragging right grows
    tab.mouse.up()
    tab.wait_for_function("(w) => document.querySelector('.bn-visual-media').getBoundingClientRect().width > w + 30", arg=narrowed, timeout=5000)
    tab.wait_for_selector(".nb-img-outline", state="hidden", timeout=5000)
    assert not tab.evaluate("() => document.documentElement.classList.contains('nb-img-dragging')")


def test_a_resize_drag_follows_the_pointer_one_to_one_and_eases_only_on_release(page):
    _picture_in_note(page)
    page.click(".bn-visual-media")
    page.wait_for_selector(".bn-resize-handle", state="visible", timeout=5000)
    wrapper = "() => document.querySelector('.bn-visual-media').closest('.bn-file-block-content-wrapper')"
    start = page.evaluate(wrapper + ".offsetWidth")
    handle = page.locator(".bn-resize-handle").last.bounding_box()
    x, y = handle["x"] + handle["width"] / 2, handle["y"] + handle["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    assert page.evaluate("() => document.documentElement.classList.contains('nb-img-dragging')")
    errors = []
    for step in (-20, -45, -80, -50, -10, 25, 60):  # smaller and larger than where it started
        page.mouse.move(x + step, y)
        width = page.evaluate(wrapper + ".offsetWidth")   # read at once: an ease in flight would still be on its way
        errors.append(abs(width - min(start + step, 10_000)))
    assert max(errors) <= 2, errors
    assert page.evaluate(wrapper.replace("() =>", "() => getComputedStyle(") + ").transitionDuration") in ("0s",)
    page.mouse.up()
    assert not page.evaluate("() => document.documentElement.classList.contains('nb-img-dragging')")
    assert page.evaluate(wrapper.replace("() =>", "() => getComputedStyle(") + ").transitionProperty") == "width"


def test_a_cancelled_touch_ends_the_resize_instead_of_leaving_it_stuck(page):
    _picture_in_note(page)
    page.click(".bn-visual-media")
    page.wait_for_selector(".bn-resize-handle", state="visible", timeout=5000)
    handle = page.locator(".bn-resize-handle").last.bounding_box()
    page.mouse.move(handle["x"] + 4, handle["y"] + 10)
    page.mouse.down()
    assert page.evaluate("() => document.documentElement.classList.contains('nb-img-dragging')")
    seen = page.evaluate("""() => new Promise((resolve) => {
        window.addEventListener('touchend', () => resolve('touchend'), {once: true});
        document.dispatchEvent(new Event('touchcancel', {bubbles: true}));  // iOS took the finger for a scroll
        setTimeout(() => resolve('nothing'), 500);
    })""")
    assert seen == "touchend"   # the editor only listens for touchend: it is told the drag is over
    assert not page.evaluate("() => document.documentElement.classList.contains('nb-img-dragging')")
    page.mouse.up()


def _video_in_note(tab):
    tab.goto(BASE + "/", wait_until="domcontentloaded")
    tab.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    tab.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    tab.evaluate("async () => { await switchPanel('notebook'); }")
    tab.wait_for_selector(".nb-list-head [data-nb-action=new]", timeout=15000)
    tab.click(".nb-list-head [data-nb-action=new]")
    tab.wait_for_selector(".hermes-note-editor .bn-editor", timeout=30000)
    with tab.expect_file_chooser() as chooser:
        tab.click(".nb-editor-head [data-nb-action=add-files]")
    chooser.value.set_files([{"name": "Clip.mp4", "mimeType": "video/mp4", "buffer": _MP4}])
    tab.wait_for_selector(".hermes-note-editor video", timeout=15000)
    tab.wait_for_timeout(400)


def test_a_clip_is_taken_by_its_player_and_gets_the_same_outline_bars_and_width(touch_page):
    tab = touch_page
    _video_in_note(tab)
    sized = tab.evaluate("() => { const v = document.querySelector('video').getBoundingClientRect(), e = document.querySelector('.hermes-note-editor .bn-editor').getBoundingClientRect(); return [Math.round(v.width), Math.round(e.width)]; }")
    assert sized[0] >= sized[1] - 70 and sized[0] <= sized[1], sized          # fills the phone's text width
    # A tap on the clip must not reach the editor (it would select the block and re-render around the
    # player, and the first tap never got to play): count what arrives at the editor's own element.
    tab.evaluate("""() => { window.__reached = 0; const editor = document.querySelector('.hermes-note-editor .bn-editor');
        ['pointerdown', 'mousedown', 'touchstart', 'click'].forEach((t) => editor.addEventListener(t, (e) => { if (e.target.tagName === 'VIDEO') window.__reached++; })); }""")
    def centre():   # the clip's box changes as the (placeholder) file fails to load
        box = tab.locator("video").bounding_box()
        return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    tab.touchscreen.tap(*centre())
    tab.wait_for_selector(".nb-img-outline:not([hidden])", timeout=5000)
    assert tab.evaluate("() => window.__reached") == 0
    assert not _bars_shown(tab)
    tab.wait_for_timeout(700)
    tab.touchscreen.tap(*centre())          # a second tap, but slow: play/pause, not the bars
    tab.wait_for_timeout(300)
    assert not _bars_shown(tab)
    tab.wait_for_timeout(700)
    tab.touchscreen.tap(*centre())          # a quick pair is the double tap
    tab.touchscreen.tap(*centre())
    tab.wait_for_function("() => [...document.querySelectorAll('.bn-resize-handle')].some(h => getComputedStyle(h).display !== 'none')", timeout=5000)
    before = tab.locator("video").bounding_box()["width"]
    handle = tab.locator(".bn-resize-handle[data-nb-on]").first.bounding_box()
    x, y = handle["x"] + handle["width"] / 2, handle["y"] + handle["height"] / 2
    tab.mouse.move(x, y)
    tab.mouse.down()
    tab.mouse.move(x + 90, y, steps=6)
    tab.mouse.up()
    tab.wait_for_function("() => Notebook.editor.getBlocks().find(b => b.type === 'video').props.previewWidth > 0", timeout=5000)
    tab.wait_for_selector(".nb-img-outline", state="hidden", timeout=5000)   # let go after a resize
    assert not _bars_shown(tab)
    assert tab.locator("video").bounding_box()["width"] < before - 60
