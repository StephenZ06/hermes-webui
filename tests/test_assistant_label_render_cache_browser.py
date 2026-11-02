"""A cached transcript never keeps another profile's assistant name.

Switching back to a chat reuses its rendered HTML when the messages are
unchanged. The assistant name in each turn header comes from the active
profile, so a chat first rendered while a switch to another profile was in
flight (rapid clicks across profiles in a project folder) came back later
still labelled with that other profile's name, e.g. "Scout" on a default chat.
"""
import pytest

from tests._pytest_port import BASE


def test_cached_transcript_rerenders_when_the_assistant_name_changes():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            labels = page.evaluate("""() => {
              const msgs = [{role: 'user', content: 'hello', timestamp: 1}, {role: 'assistant', content: 'hi there', timestamp: 2}];
              const show = (sid) => {
                S.session = {session_id: sid, title: sid, message_count: 2, updated_at: 5};
                S.messages = msgs.map(m => Object.assign({}, m));
                S.toolCalls = [];
                renderMessages();
                return [...document.querySelectorAll('.msg-role-name')].map(e => e.textContent);
              };
              const saved = S.activeProfile;
              S.activeProfile = 'scout';
              const first = show('label-cache-a');
              show('label-cache-b');
              S.activeProfile = 'default';
              const back = show('label-cache-a');
              S.activeProfile = saved;
              return {first, back, expected: assistantDisplayName()};
            }""")
        finally:
            browser.close()
    assert labels["first"] == ["Scout"], labels
    assert labels["back"] and all(name != "Scout" for name in labels["back"]), labels
