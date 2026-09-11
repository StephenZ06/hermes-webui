"""Browser check: an async-delegation batch delivered as a process_wakeup turn
renders as the collapsed delegation card, not the process-wakeup wall or a user
bubble.

Opt-in: HERMES_WEBUI_BROWSER_TESTS=1.
"""
import os
import shutil

import pytest

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("HERMES_WEBUI_BROWSER_TESTS") != "1",
        reason="opt-in: set HERMES_WEBUI_BROWSER_TESTS=1",
    ),
    pytest.mark.skipif(
        not (shutil.which("chromium") or shutil.which("chromium-browser")),
        reason="needs a chromium",
    ),
]

BATCH_TEXT = (
    "[ASYNC DELEGATION BATCH COMPLETE — deleg_ad48fad3]\n"
    "A background fan-out unit you dispatched earlier — 2 subagent(s) — has finished; "
    "its consolidated results are below.\n\n"
    "Dispatched: 2026-09-10 19:16:16 (33s ago)\n"
    "Role: leaf   Model: ?   Total duration: 34.46s\n\n"
    "--- ✓ TASK 1/2: Read AGENTS.md (status=completed, api_calls=2, 14.37s) ---\n"
    "File found. Rules...\n"
    "--- ✓ TASK 2/2: List entries (status=completed, api_calls=6, 33.76s) ---\n"
    "Top-level entries...\n"
)


def test_process_wakeup_delivered_batch_renders_as_the_delegation_card(base_url):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=swiftshader"])
        pg = b.new_page(viewport={"width": 1200, "height": 900})
        pg.goto(base_url, wait_until="load")
        pg.wait_for_timeout(2500)
        pg.evaluate('() => document.querySelectorAll(\'#onboardingOverlay, [role="dialog"]\').forEach(e => e.remove())')

        dom = pg.evaluate(
            """(batch) => {
              S.messages = [
                { role: 'user', content: 'do the fan-out', timestamp: 1789067800 },
                { role: 'assistant', content: 'dispatched', timestamp: 1789067801 },
                { role: 'user', content: batch, _source: 'process_wakeup', timestamp: 1789067825 },
              ];
              renderMessages();
              const q = s => !!document.querySelector(s);
              const bubbleTexts = [...document.querySelectorAll('.msg-row.user .msg-body, .msg-row[data-role="user"] .msg-body')]
                .map(n => n.textContent || '');
              return {
                delegationCard: q('.async-delegation-row .async-delegation-card'),
                collapsed: (() => { const d = document.querySelector('.async-delegation-row details'); return d ? !d.open : null; })(),
                processWakeupWall: q('.process-wakeup-row .process-wakeup-text'),
                batchInAUserBubble: bubbleTexts.some(t => t.includes('ASYNC DELEGATION BATCH COMPLETE')),
                rowRole: (document.querySelector('.async-delegation-row') || {}).getAttribute
                  ? document.querySelector('.async-delegation-row').dataset.role : null,
              };
            }""",
            BATCH_TEXT,
        )
        b.close()

    print("dom", dom)
    assert dom["delegationCard"], "the batch must render as the async-delegation card"
    assert dom["collapsed"] is True, "the card is collapsed by default"
    assert dom["rowRole"] == "async_delegation", "the row must not claim to be a user message"
    assert not dom["processWakeupWall"], "must not fall through to the process-wakeup wall"
    assert not dom["batchInAUserBubble"], "must not render as a message the user sent"
