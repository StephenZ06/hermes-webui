"""Rendered pieces of the Jobs page, from the real renderer with a given state:
the Apify credit card and header chip, the master-vs-tailored score, and
hiding Logistics."""

import pytest

from tests._pytest_port import BASE


def _render(page, script):
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true && window.JobOSRender", polling=100, timeout=30000)
    return page.evaluate(script)


def test_apify_credit_card_chip_fit_compare_and_hidden_logistics():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            out = _render(page, """() => {
              const host = document.createElement('div');
              const base = {capability: {available: true}, dashboard: null, jobs: [], pipelineSource: 'all', pipelineMode: 'list'};
              const usage = (used) => ({active: true, usage: {used_usd: used, limit_usd: 5, ratio: used / 5, warn: used / 5 >= 0.8, cycle_end: '2026-11-06'}});
              const side = document.createElement('div');
              host.innerHTML = window.JobOSRender.shell({...base, activeView: 'dashboard', apifyUsage: usage(1.19)});
              side.innerHTML = window.JobOSRender.sidebar({activeView: 'dashboard', dashboard: null, apifyUsage: usage(1.19)});
              const calm = {chip: host.querySelector('.job-os-status').textContent, warn: side.querySelector('.job-os-apify-widget').classList.contains('is-warn'),
                            ready: host.querySelector('.job-os-status').dataset.ready, onDashboard: !!host.querySelector('.job-os-apify-widget')};
              host.innerHTML = window.JobOSRender.shell({...base, activeView: 'dashboard', apifyUsage: usage(4.4)});
              side.innerHTML = window.JobOSRender.sidebar({activeView: 'dashboard', dashboard: null, apifyUsage: usage(4.4)});
              const tight = {warn: side.querySelector('.job-os-apify-widget').classList.contains('is-warn'), ready: host.querySelector('.job-os-status').dataset.ready,
                             cells: side.querySelectorAll('.chat-usage-widget-battery-cell.is-filled').length,
                             level: side.querySelector('.chat-usage-widget-battery').dataset.level,
                             note: side.querySelector('.job-os-apify-widget').textContent};
              host.innerHTML = window.JobOSRender.shell({...base, activeView: 'dashboard', apifyUsage: {active: false, usage: null}, firecrawl: {state: 'healthy'}});
              side.innerHTML = window.JobOSRender.sidebar({activeView: 'dashboard', dashboard: null, apifyUsage: {active: false, usage: null}});
              const off = {chip: host.querySelector('.job-os-status').textContent, card: !!side.querySelector('.job-os-apify-widget')};
              const doc = {id: 'd1', status: 'ready', content: '# Jane', revision: 1,
                           notes: {master_fit: 68, tailored_fit: {status: 'done', fit_score: 84}}};
              host.innerHTML = window.JobOSRender.shell({...base, activeView: 'resume-studio', resume: {filename: 'cv.md', text: 'x'},
                studioJobId: 'j1', studioDocs: {resume: doc}, studioTab: 'resume', tailored: []});
              const fit = {gain: host.querySelector('.fit-gain').textContent, rings: [...host.querySelectorAll('.fit-compare .fit-ring')].map((r) => r.textContent)};
              side.innerHTML = window.JobOSRender.sidebar({activeView: 'dashboard', showLogistics: false, dashboard: null});
              const hidden = !side.querySelector('[data-job-os-view="logistics"]');
              side.innerHTML = window.JobOSRender.sidebar({activeView: 'dashboard', dashboard: null});
              return {calm, tight, off, fit, hidden, shown: !!side.querySelector('[data-job-os-view="logistics"]')};
            }""")
        finally:
            browser.close()
    assert out["calm"] == {"chip": "Apify · $1.19 of $5", "warn": False, "ready": "true", "onDashboard": False}
    assert out["tight"]["warn"] and out["tight"]["ready"] == "false" and "$0.60 left of $5.00" in out["tight"]["note"]
    assert out["tight"]["cells"] == 1 and out["tight"]["level"] == "warn"
    assert out["off"] == {"chip": "Firecrawl ready", "card": False}
    assert out["fit"] == {"gain": "+16", "rings": ["68", "84"]}
    assert out["hidden"] and out["shown"]


def test_the_apply_kit_lists_documents_answers_and_the_apply_steps():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            out = _render(page, """() => {
              const host = document.createElement('div');
              const job = {id: 'j1', title: 'SOC Analyst', company: 'Ooredoo', status: 'resume_ready', source: 'bayt', description: 'x',
                canonical_url: 'https://www.bayt.com/en/qatar/jobs/soc-analyst-1234567/', revision: 1,
                documents: {resume: {id: 'r1', status: 'ready'}, cover_letter: {id: 'c1', status: 'ready'}},
                apply_kit: {status: 'done', answers: [{question: 'Notice period?', answer: 'One month.'},
                                                      {question: 'Relocate?', answer: 'Not provided — fill in before sending'}]}};
              const base = {capability: {available: true}, dashboard: null, jobs: [], pipelineSource: 'all', pipelineMode: 'list', activeView: 'pipeline'};
              host.innerHTML = window.JobOSRender.shell({...base, jobDetail: job});
              const kit = host.querySelector('.apply-kit');
              const result = {steps: [...kit.querySelectorAll('.apply-step h4')].map((h) => h.textContent),
                docs: [...kit.querySelectorAll('a.job-os-btn')].map((a) => a.getAttribute('href')),
                copies: [...kit.querySelectorAll('[data-copy-text]')].map((b) => b.dataset.copyText),
                missing: kit.querySelectorAll('[data-missing="true"]').length,
                applied: !!kit.querySelector('[data-job-os-action="board-apply"]')};
              host.innerHTML = window.JobOSRender.shell({...base, jobDetail: {...job, status: 'submitted'}});
              result.afterApplying = !!host.querySelector('.apply-kit');
              return result;
            }""")
        finally:
            browser.close()
    assert out["steps"] == ["Documents", "Screening answers", "Apply on the site"]
    assert "/api/job-os/documents/r1/export?format=docx" in out["docs"] and "/api/job-os/documents/c1/export?format=docx" in out["docs"]
    assert "https://www.bayt.com/en/qatar/jobs/soc-analyst-1234567/" in out["docs"]
    assert out["copies"] == ["One month.", "Not provided — fill in before sending"] and out["missing"] == 1
    assert out["applied"] and not out["afterApplying"], "the kit is for applying; it goes once you have"


def test_settings_toggles_keep_their_hidden_checkbox_inside_the_label():
    """Focusing a toggle's hidden checkbox must not scroll the app shell: its
    containing block is the toggle itself, not a far-off ancestor."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            out = _render(page, """() => {
              const host = document.createElement('div');
              document.body.appendChild(host);
              const settings = {revision: 1, scout: {enabled: false, schedule_mode: 'times', run_times: ['12:30'], weekend: 'saturday', blocked_companies: []},
                notifications: {}, ai: {}, applicant: {}, apply: {}, apify: {}, firecrawl: {}, display: {}};
              host.innerHTML = window.JobOSRender.shell({capability: {available: true}, jobs: [], activeView: 'settings', settings});
              const inputs = [...host.querySelectorAll('.job-os-toggle input')];
              const result = {count: inputs.length, outside: inputs.filter((i) => i.offsetParent !== i.closest('.job-os-toggle')).length};
              host.remove();
              return result;
            }""")
        finally:
            browser.close()
    assert out["count"] > 3 and out["outside"] == 0


def test_pagers_drop_targets_the_match_queue_and_idle_search_cards():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            out = _render(page, """() => {
              const host = document.createElement('div');
              const jobs = Array.from({length: 23}, (_, i) => ({id: 'j' + i, title: 'Job ' + i, status: i % 3 ? 'analyzed' : 'shortlisted',
                has_description: i !== 5, updated_at: 1000 + i, created_at: 1000 + i, source: 'indeed'}));
              const base = {capability: {available: true}, dashboard: null, jobs, pipelineSource: 'all', pipelineMode: 'board'};
              host.innerHTML = window.JobOSRender.shell({...base, activeView: 'dashboard', recentPage: 2});
              const recent = {rows: host.querySelectorAll('.job-os-recent .job-os-job-card').length, range: host.querySelector('.pager-range').textContent,
                              current: host.querySelector('.pager-num.active').textContent,
                              nextDisabled: host.querySelector('[data-pager="recent"][aria-label="Next page"]').disabled};
              const queue = window.JobOSRender.matchQueue(jobs).map((j) => j.stage + ':' + j.id);
              const card = (job) => { host.innerHTML = window.JobOSRender.shell({...base, activeView: 'pipeline',
                board: {columns: [{key: job.column, label: 'X', jobs: [job]}]}}); return host.querySelector('.pipe-card'); };
              const fresh = card({id: 'a', title: 'A', status: 'analyzed', column: 'new', has_description: true, revision: 1,
                moves: [['shortlisted', 'Shortlisted'], ['submitted', 'Applied'], ['skipped', 'Skipped']]});
              const done = card({id: 'b', title: 'B', status: 'offer_accepted', column: 'offers', revision: 1, moves: []});
              host.innerHTML = window.JobOSRender.shell({...base, activeView: 'scout', searches: [{id: 's1', name: 'SOC', keywords: 'SOC Analyst',
                enabled: true, sites: ['indeed'], locations: [], title_filter: []}], runs: []});
              return {recent, queue: [queue.length, queue[0], queue[queue.length - 1]], drops: fresh.dataset.drops, draggable: fresh.draggable,
                      fixed: done.hasAttribute('draggable'), idle: host.querySelector('.scout-run.is-empty .scout-run-state').textContent,
                      facts: [...host.querySelectorAll('.scout-facts dt')].length};
            }""")
        finally:
            browser.close()
    assert out["recent"] == {"rows": 3, "range": "21–23 of 23", "current": "3", "nextDisabled": True}
    # Board order: shortlisted jobs come after every new one; the job without a description is left out.
    assert out["queue"] == [22, "new:j22", "shortlisted:j0"]
    assert out["drops"] == "shortlisted resume applied closed" and out["draggable"] and not out["fixed"]
    assert out["idle"] == "Not run yet" and out["facts"] == 6
