"""Shared micro-interactions (static/micro.js): the sliding tab pill, button
busy/done states, the error shake, themed tooltips and stacked toasts."""

import pytest

from tests._pytest_port import BASE


def _page(pw):
    browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true && window.Micro", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    return browser, page


def test_pill_follows_the_active_tab_and_buttons_show_busy_then_done():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _page(pw)
        try:
            out = page.evaluate("""async () => {
              const box = document.createElement('div');
              box.innerHTML = '<div class="seg" data-mi-tabs><button class="seg-btn active">One</button><button class="seg-btn">Two two</button></div><button id="b">Save</button><input id="f">';
              document.body.appendChild(box);
              window.Micro.scan(box);
              const seg = box.querySelector('.seg'), pill = seg.querySelector('.mi-pill'), [one, two] = seg.querySelectorAll('.seg-btn');
              const at = () => [Math.round(pill.getBoundingClientRect().left) === Math.round(document.querySelector('.seg-btn.active').getBoundingClientRect().left),
                                Math.round(pill.getBoundingClientRect().width) === Math.round(document.querySelector('.seg-btn.active').getBoundingClientRect().width)];
              const first = at();
              one.classList.remove('active'); two.classList.add('active');
              await new Promise((r) => setTimeout(r, 500));
              const moved = at();
              const b = box.querySelector('#b');
              window.Micro.busy(b, 'Saving…');
              const busy = [b.textContent, b.disabled, !!b.querySelector('.mi-spin')];
              const finished = window.Micro.done(b, 'Saved', 200);
              const done = [b.textContent, !!b.querySelector('.mi-tick')];
              await finished;
              const back = [b.textContent, b.disabled];
              const f = box.querySelector('#f');
              window.Micro.invalid(f);
              const invalid = [f.getAttribute('aria-invalid'), f.classList.contains('mi-shake')];
              f.dispatchEvent(new Event('input'));
              const cleared = f.hasAttribute('aria-invalid');
              box.remove();
              return {first, moved, busy, done, back, invalid, cleared};
            }""")
        finally:
            browser.close()
    assert out["first"] == [True, True] and out["moved"] == [True, True]
    assert out["busy"] == ["Saving…", True, True] and out["done"] == ["Saved", True] and out["back"] == ["Save", False]
    assert out["invalid"] == ["true", True] and out["cleared"] is False


def test_tooltips_replace_the_native_one_and_toasts_stack():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _page(pw)
        try:
            page.evaluate("""() => { const b = document.createElement('button'); b.id = 'tipme'; b.title = 'Helpful hint'; b.textContent = 'x';
              Object.assign(b.style, {position: 'fixed', left: '300px', top: '300px', zIndex: 99999}); document.body.appendChild(b); }""")
            page.hover("#tipme")
            page.wait_for_selector(".mi-tip.is-open", timeout=3000)
            shown = page.evaluate("() => [document.querySelector('.mi-tip').textContent, document.querySelector('#tipme').hasAttribute('title')]")
            page.mouse.move(5, 600)
            page.wait_for_function("() => !document.querySelector('.mi-tip.is-open')", timeout=2000)
            restored = page.evaluate("() => document.querySelector('#tipme').getAttribute('title')")
            page.evaluate("() => { showToast('First'); }")
            page.wait_for_timeout(250)
            page.evaluate("() => { showToast('Second'); }")
            page.wait_for_timeout(200)
            ghosts = page.evaluate("() => [...document.querySelectorAll('.mi-toast-ghost')].map((g) => g.textContent.includes('First'))")
        finally:
            browser.close()
    assert shown == ["Helpful hint", False], "the native tooltip is parked while the themed one shows"
    assert restored == "Helpful hint"
    assert ghosts == [True]


def test_effort_meter_fills_to_the_level_and_jobs_busy_states_use_the_working_line():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _page(pw)
        try:
            out = page.evaluate("""() => {
              document.getElementById('composerReasoningWrap').style.display = '';
              _applyReasoningChip('low');
              const chip = document.querySelector('#composerReasoningChip .mi-effort').dataset.level;
              _applyReasoningChip('high', {supported_efforts: ['low', 'medium', 'high']});
              const meters = [...document.querySelectorAll('#composerReasoningDropdown .reasoning-option')]
                .map((o) => [o.dataset.effort, o.querySelector('.mi-effort') && o.querySelector('.mi-effort').dataset.level, o.textContent]);
              const html = window.JobOSRender.shell({capability: {available: true}, jobs: [], activeView: 'pipeline', pipelineSource: 'all', pipelineMode: 'board',
                board: {columns: [{key: 'favorite', label: 'Favorite', jobs: [{id: 't', title: 'T', status: 'tailoring', revision: 1, source: 'indeed'}]}], sources: {}}});
              const host = document.createElement('div'); host.innerHTML = html;
              const line = host.querySelector('.pipe-busy .mi-status');
              return {chip, after: document.querySelector('#composerReasoningChip .mi-effort').dataset.level, meters,
                      steps: line ? [...line.querySelectorAll('.mi-status-line')].map((l) => l.textContent) : null};
            }""")
        finally:
            browser.close()
    assert out["chip"] == "2" and out["after"] == "4"
    assert ["high", "4", "High"] in out["meters"] and ["", "0", "Default"] in out["meters"]
    assert out["steps"] == ["Tailoring your resume", "Matching the posting", "Checking the numbers"]


def test_delete_asks_in_place_and_settles_back():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _page(pw)
        try:
            out = page.evaluate("""async () => {
              const b = document.createElement('button'); b.innerHTML = '<svg></svg>'; b.setAttribute('aria-label', 'Delete');
              document.body.appendChild(b);
              const first = window.Micro.arm(b, 'Delete search?', 300);
              const asking = [b.textContent, b.classList.contains('mi-armed')];
              await new Promise((r) => setTimeout(r, 400));
              const settled = [b.textContent, b.classList.contains('mi-armed'), b.getAttribute('aria-label')];
              window.Micro.arm(b, 'Delete search?');
              const second = window.Micro.arm(b, 'Delete search?');
              b.remove();
              return {first, asking, settled, second};
            }""")
            page.evaluate("() => openShortcutsHelp()")
            sheet = page.inner_text("#shortcutsHelpBody")
        finally:
            browser.close()
    assert out["first"] is False and out["asking"] == ["Delete search?", True]
    assert out["settled"] == ["", False, "Delete"] and out["second"] is True
    assert "JOBS" in sheet.upper() and "Search the Pipeline" in sheet
