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
