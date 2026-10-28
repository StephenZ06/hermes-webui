"""Opening the workspace panel: message text fades out and back in, bubbles stay, nothing is left behind."""
import pytest

from tests._pytest_port import BASE


def test_panel_slide_fades_message_text_but_not_bubbles():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_context(viewport={"width": 1500, "height": 860}).new_page()
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.evaluate("() => { try { localStorage.setItem('hermes-webui-workspace-pinned', '0'); localStorage.setItem('hermes-webui-workspace-panel', 'closed'); } catch (e) {} }")
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('chat'); }")
            page.evaluate("""() => { S.session = S.session || {session_id: 'motion-test', title: 'Motion', messages: []};
                S.messages = [{role: 'user', content: 'A short question'}, {role: 'assistant', content: 'A short answer.'}];
                renderMessages(); if (document.documentElement.dataset.workspacePanel !== 'closed') toggleWorkspacePanel(false); }""")
            page.wait_for_timeout(600)
            probe = """() => { const m = document.getElementById('msgInner');
                const ub = m.querySelector('.msg-row:not(.assistant-turn) > .msg-body'), ab = m.querySelector('.assistant-turn .msg-body');
                const cs = getComputedStyle(ub); const alpha = cs.color.startsWith('rgba') ? parseFloat(cs.color.split(',')[3]) : 1;
                return {alpha, bg: cs.backgroundColor, reply: parseFloat(getComputedStyle(ab).opacity), style: m.getAttribute('style') || '', hold: m.dataset.motionHold || ''}; }"""
            before = page.evaluate(probe)
            page.evaluate("() => { window.__hermesSlideTimeScale = 0.1; toggleWorkspacePanel(true); }")
            page.wait_for_timeout(400)
            mid = page.evaluate(probe)
            page.evaluate("() => { window.__hermesSlideTimeScale = 1; }")
            page.wait_for_selector(".layout.panel-sliding", state="detached", timeout=20000)
            page.wait_for_timeout(600)
            after = page.evaluate(probe)
        finally:
            browser.close()
    assert mid["alpha"] < 0.05 and mid["reply"] < 0.05, mid      # the text is out of sight while the panel moves
    assert mid["bg"] == before["bg"], (before, mid)               # the user bubble itself stays in view
    assert after["alpha"] == 1 and after["reply"] == 1, after     # and the text is back once it lands
    assert after["style"] == "" and after["hold"] == "", after    # no held width or hold marker left behind
