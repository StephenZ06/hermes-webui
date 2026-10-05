"""A chat waiting on a question shows on the Office dashboard's Attention card.

The card now reads /api/office/attention once instead of polling the pending
endpoints chat by chat (which only covered the active profile's delegating
chats and 404'd on chats tagged with another profile).
"""
import json
import urllib.parse
import urllib.request

import pytest

from tests._pytest_port import BASE


def _post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Origin": BASE})
    return json.loads(urllib.request.urlopen(req, timeout=20).read() or b"{}")


def test_a_waiting_chat_shows_on_the_attention_card_with_its_choices():
    sync_api = pytest.importorskip("playwright.sync_api")
    sid = _post("/api/session/new", {})["session"]["session_id"]
    query = urllib.parse.urlencode([("session_id", sid), ("question", "Which file next?"),
                                    ("choices", "README.md"), ("choices", "AGENTS.md")])
    urllib.request.urlopen(BASE + "/api/clarify/inject_test?" + query, timeout=20).read()
    try:
        with sync_api.sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                not_found = []
                page.on("response", lambda r: r.status == 404 and "/pending" in r.url and not_found.append(r.url))
                page.goto(BASE + "/", wait_until="domcontentloaded")
                page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
                page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
                page.evaluate("async () => { await switchPanel('office'); }")
                page.wait_for_function("() => typeof window.officeSetSubview === 'function'", polling=100, timeout=30000)
                page.evaluate("() => window.officeSetSubview('dashboard')")
                card = page.wait_for_selector(f".office-dashboard-attention-card[data-attention-session='{sid}']", timeout=30000)
                text = card.inner_text()
                choices = [b.inner_text() for b in card.query_selector_all("[data-attention-choice]")]
            finally:
                browser.close()
    finally:
        _post("/api/clarify/respond", {"session_id": sid, "response": "README.md"})
    assert "Answer needed" in text.title() or "ANSWER NEEDED" in text.upper()
    assert "Which file next?" in text
    assert choices == ["README.md", "AGENTS.md"]
    assert not not_found, not_found
