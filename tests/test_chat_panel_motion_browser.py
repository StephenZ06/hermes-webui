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


def test_user_bubbles_travel_with_the_opening_panel_and_never_sit_under_it():
    """At a width where the chat column has no max width, opening the panel narrows the text. The held
    messages must not leave right-aligned bubbles under the panel until landing: they follow the column's
    edge every frame, and land without a jump."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_context(viewport={"width": 1200, "height": 800}).new_page()
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.evaluate("() => { try { localStorage.setItem('hermes-webui-workspace-pinned', '0'); localStorage.setItem('hermes-webui-workspace-panel', 'closed'); } catch (e) {} }")
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('chat'); }")
            page.evaluate("""() => { S.session = S.session || {session_id: 'motion-test', title: 'Motion', messages: []};
                S.messages = [];
                for (let i = 0; i < 6; i++) { S.messages.push({role: 'user', content: 'Question ' + i + ' about how the workspace panel slides over the conversation'});
                                              S.messages.push({role: 'assistant', content: 'An answer. '.repeat(30)}); }
                renderMessages(); if (document.documentElement.dataset.workspacePanel !== 'closed') toggleWorkspacePanel(false);
                _setMessageScrollToBottom(); }""")
            page.wait_for_timeout(600)
            page.evaluate("""() => { window.__edges = []; const m = document.getElementById('msgInner');
                const view = m.parentElement.getBoundingClientRect();
                const bubble = [...m.querySelectorAll('.msg-row:not(.assistant-turn) > .msg-body')].filter(e => { const r = e.getBoundingClientRect(); return r.top > view.top && r.bottom < view.bottom; }).pop();
                const panel = document.querySelector('.rightpanel'); const t0 = performance.now();
                const host = m.parentElement;
                (function f() { const r = bubble.getBoundingClientRect(); window.__edges.push([r.right, panel.getBoundingClientRect().left, r.top,
                    m.dataset.motionHold ? null : host.scrollHeight - host.scrollTop - host.clientHeight]);
                    if (performance.now() - t0 < 800) requestAnimationFrame(f); })();  // the slide and the landing glide
                toggleWorkspacePanel(true); }""")
            page.wait_for_timeout(1300)
            edges = page.evaluate("() => window.__edges")
        finally:
            browser.close()
    rights = [right for right, _, _, _ in edges]
    tops = [top for _, _, top, _ in edges]
    assert all(right <= left + 0.5 for right, left, _, _ in edges), edges  # never under the panel
    landed = [gap for *_, gap in edges[1:] if gap is not None]
    assert landed and max(landed) < 16, landed                              # still at the bottom from the landing frame on
    assert landed[-1] <= 1, landed                                          # and truly at the bottom once settled
    vertical = [b - a for a, b in zip(tops, tops[1:])]
    assert max(abs(v) for v in vertical) < 40, vertical                     # the scroll stays anchored: no jump on landing
    moves = [v for v in vertical if abs(v) >= 0.5]
    assert all(v < 0 for v in moves) or all(v > 0 for v in moves), vertical  # one vertical move, never a step back
    steps = [abs(b - a) for a, b in zip(rights, rights[1:])]
    assert max(steps) < 80, steps                                           # one glide, no landing jump
    assert rights[-1] < rights[0] - 100, rights                             # it really moved left with the panel


def test_jump_to_response_button_rides_the_column_right_edge():
    """The jump-to-response button sits on the right of a reply's footer. While the panel opens it must
    keep its distance from the column's right edge (not ride under the panel) and land without a jump. A
    reader at the bottom stays on the composer, so the button may step with the composer, never on its own."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_context(viewport={"width": 1200, "height": 800}).new_page()
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.evaluate("() => { try { localStorage.setItem('hermes-webui-workspace-pinned', '0'); localStorage.setItem('hermes-webui-workspace-panel', 'closed'); } catch (e) {} }")
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('chat'); }")
            page.evaluate("""() => { S.session = S.session || {session_id: 'motion-test', title: 'Motion', messages: []};
                S.messages = [];
                for (let i = 0; i < 6; i++) { S.messages.push({role: 'user', content: 'Question ' + i, timestamp: 1700000000 + i});
                                              S.messages.push({role: 'assistant', content: 'An answer. '.repeat(30), timestamp: 1700000000 + i}); }
                renderMessages(); if (document.documentElement.dataset.workspacePanel !== 'closed') toggleWorkspacePanel(false);
                _setMessageScrollToBottom(); }""")
            page.wait_for_timeout(600)
            frames = page.evaluate("""() => new Promise(done => { const host = document.getElementById('messages'); const view = host.getBoundingClientRect();
                const btn = [...document.querySelectorAll('.msg-question-jump-btn')].filter(e => { const r = e.getBoundingClientRect(); return r.top > view.top && r.bottom < view.bottom; }).pop();
                const out = []; const t0 = performance.now(); const composer = document.getElementById('composerBox');
                (function f() { const r = btn.getBoundingClientRect(); out.push([host.getBoundingClientRect().right - r.right, r.top - composer.getBoundingClientRect().top]);
                    if (performance.now() - t0 < 800) requestAnimationFrame(f); else done(out); })();
                toggleWorkspacePanel(true); })""")
        finally:
            browser.close()
    gaps = [gap for gap, _ in frames[2:]]
    assert min(gaps) >= 0, gaps                                              # never under the panel
    assert max(abs(b - a) for a, b in zip(gaps, gaps[1:])) < 25, gaps        # follows the right edge, no snap on landing
    tops = [top for _, top in frames[2:]]   # measured from the composer's top edge
    moves = [b - a for a, b in zip(tops, tops[1:]) if abs(b - a) >= 0.5]
    assert all(v < 0 for v in moves) or all(v > 0 for v in moves), tops     # one vertical glide, no snap and return
    assert max((abs(v) for v in moves), default=0) < 8, tops


def test_bottom_reader_moves_with_the_composer_and_cards_keep_to_the_column():
    """Recorded case: opening the panel makes the composer 10px taller part-way through.
    The messages must move with it then, not settle 10px after landing, and a background-delegation
    card must keep inside the column (not be pushed off its left edge and snap back at landing)."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_context(viewport={"width": 1200, "height": 800}).new_page()
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.evaluate("() => { try { localStorage.setItem('hermes-webui-workspace-pinned', '0'); localStorage.setItem('hermes-webui-workspace-panel', 'closed'); } catch (e) {} }")
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('chat'); }")
            page.evaluate("""() => { S.session = S.session || {session_id: 'motion-test', title: 'Motion', messages: []};
                S.messages = [];
                for (let i = 0; i < 4; i++) { S.messages.push({role: 'user', content: 'Question ' + i, timestamp: 1700000000 + i});
                                              S.messages.push({role: 'assistant', content: 'An answer. '.repeat(40), timestamp: 1700000000 + i}); }
                S.messages.push({role: 'user', content: '[ASYNC DELEGATION COMPLETE] deleg_test', display_kind: 'async_delegation_complete',
                                 display_metadata: {delegation_id: 'deleg_test', task_count: 1, completed_count: 1, duration_seconds: 20.5}, timestamp: 1700000010});
                S.messages.push({role: 'user', content: 'Summarise it', timestamp: 1700000011});
                S.messages.push({role: 'assistant', content: 'A closing answer. '.repeat(40), timestamp: 1700000012});
                renderMessages(); if (document.documentElement.dataset.workspacePanel !== 'closed') toggleWorkspacePanel(false);
                _setMessageScrollToBottom(); }""")
            page.wait_for_timeout(700)
            page.evaluate("""() => { window.__s = []; const m = document.getElementById('msgInner'), host = m.parentElement;
                const view = host.getBoundingClientRect();
                const btn = [...m.querySelectorAll('.msg-question-jump-btn')].filter(e => { const r = e.getBoundingClientRect(); return r.top > view.top && r.bottom < view.bottom; }).pop();
                const card = m.querySelector('.async-delegation-card');
                const role = [...m.querySelectorAll('.assistant-turn .msg-role')].filter(e => { const r = e.getBoundingClientRect(); return r.top > view.top && r.bottom < view.bottom; }).pop();
                const composer = document.querySelector('.composer-box') || document.getElementById('composerWrap');
                toggleWorkspacePanel(true);
                // The recorded composer drops to its taller layout part-way through; do the same here.
                setTimeout(() => { composer.style.paddingTop = '10px'; }, 150);
                // Created after the motion hold's own observer, so each sample sees what that frame paints.
                const sample = () => { const c = card.getBoundingClientRect(), b = btn.getBoundingClientRect();
                    window.__s.push({hold: !!m.dataset.motionHold, btn: btn.getBoundingClientRect().top, composer: composer.getBoundingClientRect().top,
                        cardLeft: c.left - role.getBoundingClientRect().left, cardRight: b.right - c.right}); };
                new ResizeObserver(sample).observe(host); }""")
            page.wait_for_selector(".layout.panel-sliding", state="detached", timeout=20000)
            page.wait_for_timeout(900)
            final = page.evaluate("""() => { const m = document.getElementById('msgInner'), host = m.parentElement;
                const view = host.getBoundingClientRect();
                const btn = [...m.querySelectorAll('.msg-question-jump-btn')].filter(e => { const r = e.getBoundingClientRect(); return r.top > view.top && r.bottom < view.bottom; }).pop();
                return btn.getBoundingClientRect().top; }""")
            samples = page.evaluate("() => window.__s")
        finally:
            browser.close()
    held = [s for s in samples if s["hold"]]
    composer_moves = held[-1]["composer"] - held[0]["composer"]
    assert abs(composer_moves) >= 4, samples                              # the composer does change height mid-slide here
    # the card spans the column as it moves: its edges keep their distance to the replies' left edge and the jump button
    edges = [(round(s["cardLeft"] - held[0]["cardLeft"]), round(s["cardRight"] - held[0]["cardRight"])) for s in held]
    assert all(abs(left) <= 1 and abs(right) <= 1 for left, right in edges), edges
    assert abs(final - held[-1]["btn"]) < 1.5, (final, held[-1])           # nothing left to settle after landing
