"""The shared iOS-style delete mode on Work Hub boards, scheduled jobs, Spaces
and personas.

Each page enters the mode from its trash button (Work Hub: + > Delete
project); deletable items wiggle with an X, locked ones stay still; the X
confirms then deletes; Done/Escape leaves the mode. The wiggle plays even
with reduced motion.
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


def _open(pw, panel):
    browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate(f"async () => {{ await switchPanel('{panel}'); }}")
    return browser, page


def _confirm(page):
    page.wait_for_selector("#appDialogOverlay #appDialogConfirm", state="visible", timeout=10000)
    text = page.inner_text("#appDialogOverlay")
    page.click("#appDialogConfirm")
    return text


def _mode_state(page, list_selector):
    return page.evaluate("""(sel) => {
      const list = document.querySelector(sel);
      return {
        wiggling: [...list.querySelectorAll('.dm-item')].map(e => getComputedStyle(e).animationName),
        xs: list.querySelectorAll('.dm-item > .dm-x').length,
        locked: list.querySelectorAll('.dm-locked').length,
        text: list.innerText,
      };
    }""", list_selector)


def test_work_hub_delete_mode_also_deletes_boards():
    sync_api = pytest.importorskip("playwright.sync_api")
    tag = uuid.uuid4().hex[:6]
    project = _call("/api/projects/create", {"name": f"WH boards {tag}", "work_hub_managed": True})[0]["project"]
    pid = project["project_id"]
    keep = _call("/api/work_hub/boards/create", {"board": {"name": f"Keep {tag}", "project_id": pid}, "expected_revision": _revision()})[0]["board"]
    drop = _call("/api/work_hub/boards/create", {"board": {"name": f"Drop {tag}", "project_id": pid}, "expected_revision": _revision()})[0]["board"]
    try:
        with sync_api.sync_playwright() as pw:
            browser, page = _open(pw, "notes")
            try:
                page.wait_for_function("(name) => document.querySelector('#workHubSidebar').innerText.includes(name)",
                                       arg=project["name"], timeout=20000)
                page.click("#workHubProjectCreate")
                page.click(".work-hub-create-menu [data-delete-project]")
                page.wait_for_selector(f"[data-delete-board-mode='{drop['id']}']", timeout=10000)
                state = _mode_state(page, "#workHubProjects")
                page.click(f"[data-delete-board-mode='{drop['id']}']", force=True)
                _confirm(page)
                page.wait_for_function("(name) => !document.querySelector('#workHubProjects').innerText.includes(name)",
                                       arg=drop["name"], timeout=20000)
                after = page.inner_text("#workHubProjects")
            finally:
                browser.close()
        boards = [b["id"] for b in _call("/api/work_hub/bootstrap")[0]["boards"]]
        assert keep["name"] in state["text"] and drop["name"] in state["text"], "delete mode opens folders to show their boards"
        assert state["wiggling"] and set(state["wiggling"]) == {"dm-wiggle"}
        assert state["xs"] == len(state["wiggling"])
        assert drop["id"] not in boards and keep["id"] in boards
        assert keep["name"] in after
    finally:
        _call("/api/projects/delete", {"project_id": pid})


def test_scheduled_jobs_delete_mode():
    sync_api = pytest.importorskip("playwright.sync_api")
    tag = uuid.uuid4().hex[:6]
    jobs = []
    for name in (f"Job keep {tag}", f"Job drop {tag}"):
        data, status = _call("/api/crons/create", {"name": name, "schedule": "0 9 * * *", "prompt": "say hi"})
        assert status == 200, data
        jobs.append((data.get("job") or data)["id"])
    try:
        with sync_api.sync_playwright() as pw:
            browser, page = _open(pw, "tasks")
            try:
                page.wait_for_function("(name) => document.querySelector('#cronList').innerText.includes(name)",
                                       arg=f"Job drop {tag}", timeout=20000)
                page.click("#cronDeleteModeBtn")
                page.wait_for_selector("#cronList .dm-item", timeout=10000)
                button_text = page.inner_text("#cronDeleteModeBtn")
                state = _mode_state(page, "#cronList")
                page.click(f"#cronList .dm-item:has-text('Job drop {tag}') .dm-x", force=True)
                dialog = _confirm(page)
                page.wait_for_function("(name) => !document.querySelector('#cronList').innerText.includes(name)",
                                       arg=f"Job drop {tag}", timeout=20000)
                page.keyboard.press("Escape")
                page.wait_for_function("() => !document.querySelector('#cronList .dm-item')", timeout=10000)
                done_after = page.get_attribute("#cronDeleteModeBtn", "aria-pressed")
            finally:
                browser.close()
        remaining = [j["id"] for j in _call("/api/crons")[0].get("jobs", [])]
        assert button_text.strip() == "Done"
        assert set(state["wiggling"]) == {"dm-wiggle"} and state["xs"] == len(state["wiggling"])
        assert f"Job drop {tag}" in dialog, "the confirmation names the job"
        assert jobs[1] not in remaining and jobs[0] in remaining
        assert done_after == "false", "Escape leaves delete mode"
    finally:
        for job_id in jobs:
            _call("/api/crons/delete", {"job_id": job_id})


def test_spaces_delete_mode_removes_without_touching_files(tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    tag = uuid.uuid4().hex[:6]
    keep = tmp_path / f"keep-{tag}"
    drop = tmp_path / f"drop-{tag}"
    for folder in (keep, drop):
        folder.mkdir()
        (folder / "note.txt").write_text("stays")
        added, status = _call("/api/workspaces/add", {"path": str(folder)})
        assert status == 200, added
    try:
        with sync_api.sync_playwright() as pw:
            browser, page = _open(pw, "workspaces")
            try:
                page.wait_for_function("(p) => document.querySelector('#workspacesPanel').innerText.includes(p)",
                                       arg=str(drop), timeout=20000)
                page.click("#workspaceDeleteModeBtn")
                page.wait_for_selector("#workspacesPanel .dm-item", timeout=10000)
                state = _mode_state(page, "#workspacesPanel")
                draggable = page.evaluate("() => [...document.querySelectorAll('#workspacesPanel .ws-row')].some(r => r.draggable)")
                page.click(f"#workspacesPanel .ws-row[data-path='{drop}'] .dm-x", force=True)
                _confirm(page)
                page.wait_for_function("(p) => !document.querySelector('#workspacesPanel').innerText.includes(p)",
                                       arg=str(drop), timeout=20000)
            finally:
                browser.close()
        paths = [w["path"] for w in _call("/api/workspaces")[0].get("workspaces", [])]
        assert set(state["wiggling"]) == {"dm-wiggle"} and state["xs"] == len(state["wiggling"])
        assert not draggable, "rows cannot be dragged while deleting"
        assert str(drop) not in paths and str(keep) in paths
        assert (drop / "note.txt").exists(), "removing a Space never touches its files"
    finally:
        for folder in (keep, drop):
            _call("/api/workspaces/remove", {"path": str(folder)})


def test_personas_delete_mode_keeps_built_ins_still():
    sync_api = pytest.importorskip("playwright.sync_api")
    tag = uuid.uuid4().hex[:6]
    created = _call("/api/agent-definitions/create", {"name": f"Persona {tag}", "role": "tester", "system_prompt": "Be a test."})[0]["definition"]
    try:
        with sync_api.sync_playwright() as pw:
            browser, page = _open(pw, "agents")
            try:
                page.wait_for_function("(name) => document.querySelector('#agentsList').innerText.includes(name)",
                                       arg=created["name"], timeout=20000)
                page.click("#agentDefDeleteModeBtn")
                page.wait_for_selector("#agentsList .dm-item", timeout=10000)
                state = _mode_state(page, "#agentsList")
                builtin_locked = page.evaluate("""() => [...document.querySelectorAll('#agentsList .skill-item')]
                  .filter(e => (e.dataset.agentDefId || '').startsWith('builtin:'))
                  .every(e => e.classList.contains('dm-locked') && !e.querySelector('.dm-x'))""")
                page.click(f"#agentsList [data-agent-def-id='{created['id']}'] .dm-x", force=True)
                _confirm(page)
                page.wait_for_function("(name) => !document.querySelector('#agentsList').innerText.includes(name)",
                                       arg=created["name"], timeout=20000)
            finally:
                browser.close()
        ids = [d["id"] for d in _call("/api/agent-definitions")[0].get("definitions", [])]
        assert set(state["wiggling"]) == {"dm-wiggle"} and state["xs"] == len(state["wiggling"])
        assert state["locked"] >= 1 and builtin_locked, "built-in personas stay still, without an X"
        assert created["id"] not in ids
    finally:
        _call("/api/agent-definitions/delete", {"id": created["id"]})
