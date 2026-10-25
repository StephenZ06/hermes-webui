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
            page.evaluate("""() => { const b = document.createElement('span'); b.id = 'tipme'; b.title = 'Helpful hint'; b.textContent = 'x';
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


def test_buttons_show_no_hover_label_and_keep_their_title_as_a_name():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _page(pw)
        try:
            page.evaluate("""() => {
              const make = (id, text) => { const b = document.createElement('button'); b.id = id; b.title = 'Helpful hint'; b.textContent = text;
                Object.assign(b.style, {position: 'fixed', left: id === 'iconbtn' ? '300px' : '400px', top: '300px', zIndex: 99999}); document.body.appendChild(b); };
              make('iconbtn', ''); make('textbtn', 'Save');
            }""")
            page.hover("#iconbtn")
            page.wait_for_timeout(900)
            icon = page.evaluate("""() => { const b = document.querySelector('#iconbtn'); const t = document.querySelector('.mi-tip');
              return [b.getAttribute('title'), b.getAttribute('aria-label'), !!(t && t.classList.contains('is-open'))]; }""")
            page.hover("#textbtn")
            page.wait_for_timeout(900)
            text = page.evaluate("""() => { const b = document.querySelector('#textbtn'); const t = document.querySelector('.mi-tip');
              return [b.getAttribute('title'), b.getAttribute('aria-label'), !!(t && t.classList.contains('is-open'))]; }""")
            rail = page.evaluate("""() => { const b = document.createElement('button'); b.className = 'rail-btn has-tooltip'; b.dataset.tooltip = 'Chat';
              document.body.appendChild(b); return getComputedStyle(b, '::after').content; }""")
        finally:
            browser.close()
    # An icon-only button keeps its title as its accessible name; a labelled one keeps its text.
    assert icon == [None, "Helpful hint", False]
    assert text == [None, None, False]
    assert rail == "none"


def test_controls_show_no_hover_label_except_a_cut_off_name():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _page(pw)
        try:
            page.evaluate("""() => {
              const box = document.createElement('div');
              Object.assign(box.style, {position: 'fixed', left: '200px', top: '200px', zIndex: 99999, display: 'grid', gap: '20px', width: '120px'});
              box.innerHTML = '<select id="sel" title="Conversation model"><option>gpt</option></select>'
                + '<span id="tog" class="skill-toggle" title="Enabled" style="display:inline-block;width:30px;height:16px"></span>'
                + '<a id="cut" href="#x" title="A very long session name that cannot fit" style="display:block;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">A very long session name that cannot fit</a>'
                + '<a id="fits" href="#y" title="Short" style="display:block">Short</a>'
                + '<span id="badge" title="Owner profile: default">default</span>';
              document.body.appendChild(box);
            }""")
            seen = {}
            for target in ("sel", "tog", "cut", "fits", "badge"):
                # The app's themed select covers the native one, so hover it by event.
                if target == "sel":
                    page.dispatch_event("#sel", "pointerover", {"bubbles": True, "pointerType": "mouse"})
                else:
                    page.hover("#" + target)
                page.wait_for_timeout(700)
                seen[target] = page.evaluate("""(id) => { const el = document.getElementById(id); const t = document.querySelector('.mi-tip');
                  return [el.getAttribute('title'), t && t.classList.contains('is-open') ? t.textContent : null]; }""", target)
                if target == "sel":
                    page.dispatch_event("#sel", "pointerout", {"bubbles": True, "pointerType": "mouse"})
                page.mouse.move(5, 5)
                page.wait_for_timeout(450)
        finally:
            browser.close()
    # Controls lose the native title and show no themed tip...
    assert seen["sel"] == [None, None]
    assert seen["tog"] == [None, None]
    assert seen["fits"] == [None, None]
    # ...except a cut-off name, whose tip is the only way to read it.
    assert seen["cut"] == [None, "A very long session name that cannot fit"]
    # Plain text keeps its explanation.
    assert seen["badge"] == [None, "Owner profile: default"]


def test_usage_percent_pops_only_when_its_value_changes():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _page(pw)
        try:
            out = page.evaluate("""async () => {
              const render = (u) => _renderAccountUsage({available: true, provider: 'openai-codex',
                windows: [{label: 'Weekly', used_percent: u}, {label: '5h session', used_percent: u}]});
              const el = () => document.getElementById('chatUsageWidgetPercent');
              const popping = () => el().classList.contains('mi-num-pop');
              render(42); await new Promise((r) => setTimeout(r, 50));
              const first = popping();
              render(42); await new Promise((r) => setTimeout(r, 50));
              const same = popping();
              render(47); await new Promise((r) => setTimeout(r, 50));
              const changed = [popping(), el().textContent];
              await new Promise((r) => setTimeout(r, 700));
              return {first, same, changed, settled: popping()};
            }""")
        finally:
            browser.close()
    # First paint and an unchanged repaint stay still; a new value pops, then the class clears.
    assert out["first"] is False and out["same"] is False
    assert out["changed"] == [True, "53% remaining"]
    assert out["settled"] is False


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
