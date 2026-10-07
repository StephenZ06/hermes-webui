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
              host.innerHTML = window.JobOSRender.shell({...base, activeView: 'dashboard', apifyUsage: usage(1.19)});
              const calm = {chip: host.querySelector('.job-os-status').textContent, warn: host.querySelector('.apify-usage').classList.contains('is-warn'),
                            ready: host.querySelector('.job-os-status').dataset.ready};
              host.innerHTML = window.JobOSRender.shell({...base, activeView: 'dashboard', apifyUsage: usage(4.4)});
              const tight = {warn: host.querySelector('.apify-usage').classList.contains('is-warn'), ready: host.querySelector('.job-os-status').dataset.ready,
                             bar: host.querySelector('.apify-usage-track i').style.width,
                             note: host.querySelector('.apify-usage .job-os-card-note').textContent};
              host.innerHTML = window.JobOSRender.shell({...base, activeView: 'dashboard', apifyUsage: {active: false, usage: null}, firecrawl: {state: 'healthy'}});
              const off = {chip: host.querySelector('.job-os-status').textContent, card: !!host.querySelector('.apify-usage')};
              const doc = {id: 'd1', status: 'ready', content: '# Jane', revision: 1,
                           notes: {master_fit: 68, tailored_fit: {status: 'done', fit_score: 84}}};
              host.innerHTML = window.JobOSRender.shell({...base, activeView: 'resume-studio', resume: {filename: 'cv.md', text: 'x'},
                studioJobId: 'j1', studioDocs: {resume: doc}, studioTab: 'resume', tailored: []});
              const fit = {gain: host.querySelector('.fit-gain').textContent, rings: [...host.querySelectorAll('.fit-compare .fit-ring')].map((r) => r.textContent)};
              const side = document.createElement('div');
              side.innerHTML = window.JobOSRender.sidebar({activeView: 'dashboard', showLogistics: false, dashboard: null});
              const hidden = !side.querySelector('[data-job-os-view="logistics"]');
              side.innerHTML = window.JobOSRender.sidebar({activeView: 'dashboard', dashboard: null});
              return {calm, tight, off, fit, hidden, shown: !!side.querySelector('[data-job-os-view="logistics"]')};
            }""")
        finally:
            browser.close()
    assert out["calm"] == {"chip": "Apify · $1.19 of $5", "warn": False, "ready": "true"}
    assert out["tight"]["warn"] and out["tight"]["ready"] == "false" and "Only $0.60 left" in out["tight"]["note"]
    assert out["tight"]["bar"] == "88%"
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
