"""Work Hub projects belong to the Work Hub page, and can be deleted from it.

A project created in the Work Hub (work_hub_managed) no longer appears in the
chat sidebar's WORKSPACES, the chat pickers or the Office sidebar; a chat
filed under one shows in the chat list instead of vanishing with the folder.
Deleting one from the Work Hub + menu removes the project with its boards
and work items.
"""
import json
import urllib.error
import urllib.request
import uuid

import pytest

from tests._pytest_port import BASE


def _call(path, body=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Origin": BASE},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read() or b"{}"), response.status
    except urllib.error.HTTPError as error:
        return json.loads(error.read() or b"{}"), error.code


def _revision():
    return _call("/api/work_hub/bootstrap")[0].get("revision")


def _project(name, work_hub):
    body = {"name": name}
    if work_hub:
        body["work_hub_managed"] = True
    return _call("/api/projects/create", body)[0]["project"]


def test_deleting_a_work_hub_project_removes_its_boards_and_items():
    tag = uuid.uuid4().hex[:6]
    project = _project(f"WH delete {tag}", True)
    pid = project["project_id"]
    board = _call("/api/work_hub/boards/create", {
        "board": {"name": "Sprint", "project_id": pid}, "expected_revision": _revision()})[0]["board"]
    _call("/api/work_hub/items/create", {
        "item": {"title": f"task {tag}", "project_id": pid, "board_id": board["id"]},
        "expected_revision": _revision()})

    _, status = _call("/api/projects/delete", {"project_id": pid})
    state = _call("/api/work_hub/bootstrap")[0]

    assert status == 200
    assert not any(p["project_id"] == pid for p in state["projects"])
    assert not any(b.get("project_id") == pid for b in state["boards"]), "its boards must go with it"
    assert not any(i.get("project_id") == pid for i in state["items"]), "its work items must go with it"


def _chat_in(project_id, title):
    session = _call("/api/session/import", {"title": title, "messages": [
        {"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"},
    ]})[0]["session"]
    _call("/api/session/move", {"session_id": session["session_id"], "project_id": project_id})
    return session["session_id"]


def test_a_chat_project_holding_chats_cannot_be_deleted_from_the_work_hub():
    tag = uuid.uuid4().hex[:6]
    project = _project(f"Chat project {tag}", False)
    sid = _chat_in(project["project_id"], f"kept chat {tag}")
    try:
        listed = {p["project_id"]: p for p in _call("/api/work_hub/bootstrap")[0]["projects"]}
        _, status = _call("/api/projects/delete", {"project_id": project["project_id"]})
        projects = _call("/api/projects")[0]["projects"]
        assert listed[project["project_id"]]["deletable"] is False
        assert status == 403
        assert any(p["project_id"] == project["project_id"] for p in projects)
    finally:
        _call("/api/session/delete", {"session_id": sid})


def test_an_empty_project_without_the_work_hub_flag_can_be_deleted():
    """Work Hub projects made before work_hub_managed existed carry no flag;
    an empty one (no chats, no work items) is deletable -- nothing is lost."""
    project = _project(f"legacy {uuid.uuid4().hex[:6]}", False)
    listed = {p["project_id"]: p for p in _call("/api/work_hub/bootstrap")[0]["projects"]}
    _, status = _call("/api/projects/delete", {"project_id": project["project_id"]})
    projects = _call("/api/projects")[0]["projects"]
    assert listed[project["project_id"]]["deletable"] is True
    assert status == 200
    assert not any(p["project_id"] == project["project_id"] for p in projects)


def _page(pw, width=1440):
    browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    page = browser.new_page(viewport={"width": width, "height": 1000})
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    return browser, page


def test_work_hub_projects_stay_off_the_chat_and_office_sidebars():
    sync_api = pytest.importorskip("playwright.sync_api")
    tag = uuid.uuid4().hex[:6]
    wh = _project(f"WH only {tag}", True)
    chat = _project(f"Chat folder {tag}", False)
    try:
        with sync_api.sync_playwright() as pw:
            browser, page = _page(pw)
            try:
                page.evaluate("async () => { await renderSessionList(); }")
                page.wait_for_function("(name) => document.body.innerText.includes(name)", arg=chat["name"], timeout=15000)
                chat_sidebar = page.inner_text("#panelChat")
                page.evaluate("async () => { await switchPanel('office'); }")
                page.wait_for_function("(name) => (document.querySelector('#panelOffice') || document.body).innerText.includes(name)",
                                       arg=chat["name"], timeout=20000)
                office_sidebar = page.evaluate("() => (document.querySelector('#panelOffice') || document.body).innerText")
                page.evaluate("async () => { await switchPanel('notes'); }")
                page.wait_for_function("(name) => document.querySelector('#workHubSidebar').innerText.includes(name)",
                                       arg=wh["name"], timeout=20000)
            finally:
                browser.close()
        assert chat["name"] in chat_sidebar
        assert wh["name"] not in chat_sidebar, "a Work Hub project must not appear in the chat WORKSPACES"
        assert wh["name"] not in office_sidebar, "a Work Hub project must not appear in the Office sidebar"
    finally:
        _call("/api/projects/delete", {"project_id": wh["project_id"]})


def test_the_work_hub_plus_menu_deletes_a_work_hub_project():
    sync_api = pytest.importorskip("playwright.sync_api")
    tag = uuid.uuid4().hex[:6]
    wh = _project(f"WH removable {tag}", True)
    chat = _project(f"Chat keep {tag}", False)
    kept_sid = _chat_in(chat["project_id"], f"menu chat {tag}")
    legacy = _project(f"Legacy empty {tag}", False)
    with sync_api.sync_playwright() as pw:
        browser, page = _page(pw)
        try:
            page.evaluate("async () => { await switchPanel('notes'); }")
            page.wait_for_function("(name) => document.querySelector('#workHubSidebar').innerText.includes(name)",
                                   arg=wh["name"], timeout=20000)
            page.click("#workHubProjectCreate")
            page.click(".work-hub-create-menu [data-delete-project]")
            picker = page.wait_for_selector(".work-hub-project-picker", timeout=10000)
            options = picker.inner_text()
            page.click(f".work-hub-project-picker .project-picker-item:has-text('{wh['name']}')")
            page.wait_for_selector("#appDialogOverlay #appDialogConfirm", state="visible", timeout=10000)
            dialog_text = page.inner_text("#appDialogOverlay")
            page.click("#appDialogConfirm")
            page.wait_for_function("(name) => !document.querySelector('#workHubSidebar').innerText.includes(name)",
                                   arg=wh["name"], timeout=20000)
        finally:
            browser.close()
    projects = _call("/api/projects")[0]["projects"]
    _call("/api/session/delete", {"session_id": kept_sid})
    _call("/api/projects/delete", {"project_id": legacy["project_id"]})
    assert wh["name"] in options
    assert legacy["name"] in options, "an empty unflagged project (pre-flag Work Hub project) is offered"
    assert chat["name"] not in options, "a project holding chats is not offered for deletion"
    assert wh["name"] in dialog_text, "the confirmation names the project being deleted"
    assert not any(p["project_id"] == wh["project_id"] for p in projects)


def test_integration_icons_match_their_title_and_subtitle_height():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _page(pw)
        try:
            page.evaluate("async () => { await switchPanel('office'); }")
            page.wait_for_function("() => typeof window.officeSetSubview === 'function'", timeout=20000)
            page.evaluate("() => window.officeSetSubview('integrations')")
            page.wait_for_selector(".office-integration-provider-icon img", timeout=10000)
            rows = page.evaluate("""() => [...document.querySelectorAll('.office-integration-card-head')].map(head => {
              const icon = head.querySelector('.office-integration-provider-icon img').getBoundingClientRect();
              // The visible text block: top of the title to the bottom of the subtitle.
              const title = head.querySelector('h2').getBoundingClientRect();
              const sub = head.querySelector('h2 + p').getBoundingClientRect();
              return {icon: icon.height, text: sub.bottom - title.top, iconTop: icon.top, textTop: title.top, square: Math.abs(icon.width - icon.height) < 1};
            })""")
        finally:
            browser.close()
    assert len(rows) == 4
    for row in rows:
        assert abs(row["icon"] - row["text"]) < 1, row
        assert abs(row["iconTop"] - row["textTop"]) < 1, row
        assert row["square"], row


def test_a_chat_filed_under_a_work_hub_project_stays_in_the_chat_list():
    sync_api = pytest.importorskip("playwright.sync_api")
    tag = uuid.uuid4().hex[:6]
    wh = _project(f"WH chat home {tag}", True)
    title = f"Filed chat {tag}"
    # The sidebar hides empty chats, so give it a short transcript.
    session = _call("/api/session/import", {"title": title, "messages": [
        {"role": "user", "content": "plan the sprint"},
        {"role": "assistant", "content": "Here is a plan."},
    ]})[0]["session"]
    sid = session["session_id"]
    _call("/api/session/move", {"session_id": sid, "project_id": wh["project_id"]})
    try:
        with sync_api.sync_playwright() as pw:
            browser, page = _page(pw)
            try:
                page.evaluate("async () => { await renderSessionList(); }")
                page.wait_for_function(
                    "(sid) => !!document.querySelector(`#panelChat [data-sid='${sid}']`)",
                    arg=sid, timeout=15000)
                in_folder = page.evaluate(
                    "(sid) => !!document.querySelector(`#panelChat .project-folder-list [data-sid='${sid}']`)",
                    sid)
            finally:
                browser.close()
        assert not in_folder
    finally:
        _call("/api/session/delete", {"session_id": sid})
        _call("/api/projects/delete", {"project_id": wh["project_id"]})
