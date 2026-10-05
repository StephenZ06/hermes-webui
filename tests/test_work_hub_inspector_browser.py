"""The Work Hub item inspector: title, a property list, description, footer.

Save stays disabled until something changes, the header status dot follows
the Status select, Priority is editable and saved, and Ctrl+Enter saves.
"""
import json
import urllib.request
import uuid

import pytest

from tests._pytest_port import BASE


def _call(path, body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "Origin": BASE})
    return json.loads(urllib.request.urlopen(req, timeout=20).read() or b"{}")


def _revision():
    return _call("/api/work_hub/bootstrap")["revision"]


def test_inspector_saves_only_when_dirty_and_saves_priority():
    sync_api = pytest.importorskip("playwright.sync_api")
    title = f"Inspect me {uuid.uuid4().hex[:6]}"
    item = _call("/api/work_hub/items/create",
                 {"item": {"title": title, "status": "todo"}, "expected_revision": _revision()})["item"]
    try:
        with sync_api.sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.goto(BASE + "/", wait_until="domcontentloaded")
                page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
                page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
                page.evaluate("async () => { await switchPanel('notes'); }")
                page.click(f".work-hub-card[data-item-id='{item['id']}']")
                page.wait_for_selector("#workHubInspector #workHubSave", timeout=10000)
                clean = page.evaluate("() => document.getElementById('workHubSave').disabled")
                page.select_option("#workHubPriority", "high")
                dirty = page.evaluate("() => document.getElementById('workHubSave').disabled")
                page.select_option("#workHubStatus", "in_progress")
                dot = page.get_attribute("#workHubStatusDot", "class")
                page.focus("#workHubDescription")
                page.keyboard.type("Ship it")
                page.keyboard.press("Control+Enter")
                page.wait_for_timeout(1200)
            finally:
                browser.close()
        saved = next(i for i in _call("/api/work_hub/bootstrap")["items"] if i["id"] == item["id"])
    finally:
        _call("/api/work_hub/items/delete", {"item_id": item["id"], "expected_revision": _revision()})
    assert clean, "Save starts disabled"
    assert not dirty, "a change enables Save"
    assert "status-in_progress" in dot, dot
    assert saved["priority"] == "high" and saved["status"] == "in_progress" and saved["description"] == "Ship it", saved
