"""The "Docs not updated" chip under a reply."""

import pytest

from tests._pytest_port import BASE


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            tab = browser.new_page(viewport={"width": 1440, "height": 900})
            errors = []
            tab.on("pageerror", lambda e: errors.append(str(e)))
            tab.goto(BASE + "/", wait_until="domcontentloaded")
            tab.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            tab.evaluate("""() => {
              document.querySelectorAll('#onboardingOverlay,#appTourOverlay,#updateBanner').forEach(e => e.remove());
              S.session = {session_id: 'sid-1'}; S.busy = false;
              const row = document.createElement('div'); row.className = 'msg-row assistant-turn'; row.textContent = 'Done.';
              document.getElementById('messages').append(row);
              window.__sent = []; window.send = async () => { window.__sent.push(document.getElementById('msg').value); };
            }""")
            yield tab
            assert not errors, errors
        finally:
            browser.close()


def test_a_stale_turn_shows_the_chip_under_the_reply_and_update_sends_the_request(page):
    page.evaluate("_setDocsCheck('sid-1', {stale: true, files: 2})")
    page.wait_for_selector(".docs-chip")
    assert page.evaluate("() => document.querySelector('.docs-chip').previousElementSibling.classList.contains('assistant-turn')")
    assert page.inner_text(".docs-chip-text") == "Docs not updated"
    page.click(".docs-chip-update")
    page.wait_for_function("() => window.__sent.length === 1")
    assert "ECC_HANDOFF.md" in page.evaluate("window.__sent[0]")
    page.wait_for_selector(".docs-chip", state="detached")


def test_no_chip_for_another_chat_a_clean_turn_or_after_dismiss(page):
    page.evaluate("_setDocsCheck('other', {stale: true, files: 1})")
    page.wait_for_timeout(100)
    assert page.locator(".docs-chip").count() == 0
    page.evaluate("_setDocsCheck('sid-1', {stale: true, files: 1})")
    page.wait_for_selector(".docs-chip")
    page.evaluate("_setDocsCheck('sid-1', null)")
    page.wait_for_selector(".docs-chip", state="detached")
    page.evaluate("_setDocsCheck('sid-1', {stale: true, files: 1})")
    page.wait_for_selector(".docs-chip")
    page.click(".docs-chip-dismiss")
    page.wait_for_selector(".docs-chip", state="detached")
    assert page.evaluate("window.__sent") == []
