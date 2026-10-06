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
    page.wait_for_selector(".nb-new-btn", timeout=15000)


def _new_note(page, title):
    page.click(".nb-new-btn")
    page.wait_for_selector(".hermes-note-editor .bn-editor", timeout=30000)
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
    page.click(f"[data-nb-scope=folder][data-nb-id='{folder['id']}']")
    _new_note(page, "In a folder")
    _saved(page)
    page.click(f"[data-nb-scope=project][data-nb-id='{project['project_id']}']")
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
