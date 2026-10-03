"""A web-search answer's trailing "Sources" / "References" link list is folded
into a collapsed <details> so it stops dominating the transcript.

Structural checks always run; the behavioural check is an opt-in browser test
(HERMES_WEBUI_BROWSER_TESTS=1) in the same style as the other *_browser tests.
"""
import os
import pathlib
import shutil

import pytest

REPO = pathlib.Path(__file__).parent.parent
UI_JS = (REPO / "static" / "ui.js").read_text(encoding="utf-8")
CSS = (REPO / "static" / "style.css").read_text(encoding="utf-8")


def test_the_fold_runs_in_postprocess():
    at = UI_JS.index("function postProcessRenderedMessages(")
    body = UI_JS[at:at + 600]
    assert "collapseAnswerSources(container)" in body


def test_it_only_touches_settled_assistant_segments():
    at = UI_JS.index("function collapseAnswerSources(")
    body = UI_JS[at:at + 2600]
    # never a live turn (still growing), and idempotent
    assert ".assistant-segment:not([data-live-assistant]) .msg-body" in body
    assert "#liveAssistantTurn" in body
    assert "body.dataset.sourcesCollapsed" in body


def test_a_prose_references_section_is_left_alone():
    at = UI_JS.index("function collapseAnswerSources(")
    body = UI_JS[at:at + 2600]
    # a paragraph with no link aborts the fold
    assert "if (!links) { ok = false; break; }" in body
    assert "linkCount < 1" in body


def test_the_disclosure_is_styled_and_starts_closed():
    assert "details.answer-sources" in CSS
    # no `[open]` on the created element -> starts collapsed
    at = UI_JS.index("const details = document.createElement('details');")
    assert "details.open" not in UI_JS[at:at + 400]


@pytest.mark.skipif(
    os.environ.get("HERMES_WEBUI_BROWSER_TESTS") != "1",
    reason="opt-in: set HERMES_WEBUI_BROWSER_TESTS=1",
)
@pytest.mark.skipif(
    not (shutil.which("chromium") or shutil.which("chromium-browser")),
    reason="needs a chromium",
)
def test_sources_tail_folds_in_the_browser(base_url):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    answer = (
        "Here is the short answer to your question.\n\n"
        "## Sources\n\n"
        "- [Example one](https://example.com/a)\n"
        "- [Example two](https://example.com/b)\n"
        "- [Example three](https://example.com/c)\n"
    )
    with sync_playwright() as p:
        # No WebGL needed: let the suite's CPU-compositing default apply, and
        # wait for boot rather than a fixed delay.
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1200, "height": 900})
        pg.goto(base_url, wait_until="load")
        pg.wait_for_function(
            "() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000
        )
        pg.evaluate('() => document.querySelectorAll(\'#onboardingOverlay,[role="dialog"]\').forEach(e => e.remove())')
        out = pg.evaluate(
            """(answer) => {
              S.messages = [
                { role: 'user', content: 'q', timestamp: 1789067800 },
                { role: 'assistant', content: answer, timestamp: 1789067820 },
              ];
              renderMessages();
              return new Promise(res => setTimeout(() => {
                const d = document.querySelector('.msg-body details.answer-sources');
                res({
                  found: !!d,
                  open: d ? d.open : null,
                  summary: d ? d.querySelector('summary').textContent : null,
                  links: d ? d.querySelectorAll('a[href]').length : 0,
                  strayHeading: !!Array.from(document.querySelectorAll('.msg-body h2'))
                    .find(h => h.textContent.trim().toLowerCase() === 'sources'),
                });
              }, 400));
            }""",
            answer,
        )
        b.close()

    assert out["found"], out
    assert out["open"] is False
    assert out["links"] == 3
    assert "3" in out["summary"]
    assert not out["strayHeading"], "the original heading should be moved into the summary"
