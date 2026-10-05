"""On a phone the Work Hub board gets the full width.

The details panel was a fixed 220px column even with nothing selected, which
squeezed the board into a ~150px strip and cut off its search box. Below
620px it is now hidden until an item is selected, then covers the board as a
sheet, and closing it brings the board back.
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


def test_phone_board_is_full_width_and_details_open_as_a_sheet():
    sync_api = pytest.importorskip("playwright.sync_api")
    rev = _call("/api/work_hub/bootstrap")["revision"]
    item = _call("/api/work_hub/items/create", {"item": {"title": f"Phone {uuid.uuid4().hex[:6]}", "status": "todo"},
                                                 "expected_revision": rev})["item"]
    try:
        with sync_api.sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                page = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
                page.goto(BASE + "/", wait_until="domcontentloaded")
                page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
                page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
                page.evaluate("async () => { await switchPanel('notes'); }")
                page.wait_for_selector(f".work-hub-card[data-item-id='{item['id']}']", state="attached", timeout=20000)
                measure = """() => { const c = document.querySelector('.work-hub-canvas').getBoundingClientRect();
                  const i = document.getElementById('workHubInspector'); const r = i.getBoundingClientRect();
                  return {canvas: Math.round(c.width), hub: Math.round(document.querySelector('.work-hub').getBoundingClientRect().width),
                          inspectorShown: getComputedStyle(i).display !== 'none' && r.width > 0, inspectorWidth: Math.round(r.width)}; }"""
                idle = page.evaluate(measure)
                page.evaluate(f"() => document.querySelector(\".work-hub-card[data-item-id='{item['id']}']\").click()")
                page.wait_for_selector("#workHubTitle", timeout=10000)
                selected = page.evaluate(measure)
                page.click("#workHubClose")
                page.wait_for_timeout(200)
                closed = page.evaluate(measure)
            finally:
                browser.close()
    finally:
        _call("/api/work_hub/items/delete", {"item_id": item["id"], "expected_revision": _call("/api/work_hub/bootstrap")["revision"]})
    assert idle["canvas"] == idle["hub"] and not idle["inspectorShown"], idle
    assert selected["inspectorShown"] and selected["inspectorWidth"] == selected["hub"], selected
    assert closed["canvas"] == closed["hub"] and not closed["inspectorShown"], closed
