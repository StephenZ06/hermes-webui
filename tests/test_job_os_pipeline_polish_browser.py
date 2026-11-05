"""Pipeline polish: the compact toolbar on the page background, column heads
whose collapse arrow slides in, steady card hovers, the Tailor resume choice,
the source tabs' re-sort motion, the stage pill in the side panel, list
outlines and the overlays' exits."""
import json

import pytest

from tests._pytest_port import BASE


def _job(n, source, status="analyzed", **extra):
    job = {"id": f"job-{n}", "title": f"Analyst {n}", "company": "Acme", "location": "Kuala Lumpur", "country": "Malaysia",
           "workplace": "", "salary_text": "", "employment_type": "Full-time", "source": source, "status": status, "revision": 1,
           "canonical_url": f"https://jobs.example.test/{n}", "has_description": True,
           "analysis": {"status": "done", "fit_score": 60 + n, "dimensions": {}},
           "checks": [{"key": "eligibility", "tone": "warn", "short": "Right to work?", "label": "Right to work isn't confirmed"}],
           "attention": [], "applied": None, "updated_at": 1793356355 - n, "created_at": 1793356309 - n, "closed_reason": "", "quiet_days": None}
    job.update(extra)
    return job


NEW = [_job(n, ["linkedin", "indeed", "remoteid"][n % 3]) for n in range(6)]
BOARD = {"columns": [{"key": "new", "label": "New", "jobs": NEW},
                     {"key": "favorite", "label": "Favorite", "jobs": [_job(10, "indeed", "shortlisted")]},
                     {"key": "ready", "label": "Ready to apply", "jobs": []}, {"key": "applied", "label": "Applied", "jobs": []},
                     {"key": "rejected", "label": "Rejected", "jobs": []}, {"key": "interview", "label": "Interview", "jobs": []},
                     {"key": "offers", "label": "Offer", "jobs": []}, {"key": "closed", "label": "Closed", "jobs": []}],
         "sources": {"all": 7, "linkedin": 2, "indeed": 3, "remoteid": 2}}
ALL = [job for column in BOARD["columns"] for job in column["jobs"]]


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1899, "height": 990})
        page.route("**/api/job-os/applications*", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(BOARD)))
        page.tailored = []

        def jobs(route):
            path = route.request.url.split("/api/job-os/jobs", 1)[1].split("?", 1)[0]
            reply = lambda body: route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
            if path.endswith("/tailor"):
                page.tailored.append(path.split("/")[1])
                return reply({"status": "tailoring"})
            if route.request.method == "GET" and not path:
                return reply({"jobs": ALL})
            if route.request.method == "GET" and path.count("/") == 1:
                job = next(j for j in ALL if j["id"] == path[1:])
                return reply({"job": dict(job, description="Analyse things.", documents=[], interview=None, apply_kit=None, follow_up=None)})
            return route.fallback()
        page.route("**/api/job-os/jobs**", jobs)
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
        page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
        page.evaluate("async () => { await switchPanel('jobs'); }")
        page.wait_for_selector("#jobOsRoot .dash-main", timeout=30000)
        page.evaluate("() => document.querySelector('[data-job-os-view=pipeline]').click()")
        page.wait_for_selector("#jobOsRoot .pipe-card", timeout=30000)
        page.wait_for_timeout(600)
        try:
            yield page
        finally:
            browser.close()


def test_toolbar_is_compact_on_the_page_background_with_tab_text_centred(page):
    out = page.evaluate("""() => {
        const q = (s) => document.querySelector('#jobOsRoot ' + s), cs = (s) => getComputedStyle(q(s));
        return {body: getComputedStyle(document.body).backgroundColor, bg: [cs('.pipe-toolbar .seg').backgroundColor, cs('.pipe-toolbar .pipe-search').backgroundColor],
                heights: ['.pipe-toolbar .seg', '.pipe-toolbar .pipe-search', '.pipe-toolbar .pipe-add-btn'].map(s => q(s).getBoundingClientRect().height),
                tab: [cs('.pipe-toolbar .seg-btn').paddingTop, cs('.pipe-toolbar .seg-btn').paddingBottom], input: cs('.pipe-search input').paddingBottom};
    }""")
    assert out["bg"] == [out["body"], out["body"]], out
    assert out["heights"] == [32, 32, 32], out
    assert out["tab"] == ["0px", "0px"] and out["input"] == "2px", out


def test_tabs_hover_blue_and_the_add_button_wears_the_work_hub_tint(page):
    page.hover("#jobOsRoot .pipe-toolbar .seg-btn:not(.active) >> nth=0")
    page.wait_for_timeout(300)
    tab = page.evaluate("() => getComputedStyle(document.querySelector('#jobOsRoot .pipe-toolbar .seg-btn:not(.active):hover')).backgroundColor")
    accent_bg = page.evaluate("() => { const d = document.createElement('div'); d.style.background = 'var(--accent-bg)'; document.body.appendChild(d); const c = getComputedStyle(d).backgroundColor; d.remove(); return c; }")
    assert tab == accent_bg, (tab, accent_bg)
    rest = page.evaluate("() => getComputedStyle(document.querySelector('#jobOsRoot .pipe-add-btn')).backgroundColor")
    page.hover("#jobOsRoot .pipe-add-btn")
    page.wait_for_timeout(400)
    hover = page.evaluate("() => getComputedStyle(document.querySelector('#jobOsRoot .pipe-add-btn')).backgroundColor")
    strong = page.evaluate("() => { const d = document.createElement('div'); d.style.background = 'var(--accent-bg-strong)'; document.body.appendChild(d); const c = getComputedStyle(d).backgroundColor; d.remove(); return c; }")
    assert rest == accent_bg and hover == strong, (rest, hover)


def test_column_heads_keep_filter_and_count_right_and_slide_the_arrow_in(page):
    head = "#jobOsRoot .pipe-col[data-col=new] .pipe-col-head"
    rest = page.evaluate(f"""() => {{ const h = document.querySelector('{head}'), r = h.getBoundingClientRect();
        return [h.querySelector('.pipe-col-fold').getBoundingClientRect().width, r.right - h.querySelector('.job-os-count').getBoundingClientRect().right]; }}""")
    assert rest[0] == 0 and rest[1] < 1, rest
    page.hover(head + " h3")
    page.wait_for_timeout(450)
    hovered = page.evaluate(f"""() => {{ const f = document.querySelector('{head} .pipe-col-fold'); return [f.getBoundingClientRect().width, getComputedStyle(f).opacity]; }}""")
    assert hovered == [24, "1"], hovered
    gap = page.evaluate(f"""() => document.querySelector('#jobOsRoot .pipe-col[data-col=new] .pipe-card').getBoundingClientRect().top - document.querySelector('{head}').getBoundingClientRect().bottom""")
    assert abs(gap - 11) < 0.5, gap


def test_a_pointed_at_card_keeps_its_size_and_its_parts_sit_right(page):
    card = "#jobOsRoot .pipe-col[data-col=new] .pipe-card >> nth=0"
    before = page.locator(card).bounding_box()
    page.hover(card)
    page.wait_for_timeout(300)
    out = page.evaluate("""() => { const c = document.querySelector('#jobOsRoot .pipe-col[data-col=new] .pipe-card:hover'), cs = (e) => getComputedStyle(e);
        const btn = c.querySelector('.pipe-card-actions .job-os-btn');
        return {shadow: cs(c).boxShadow, btn: [cs(btn).paddingTop, cs(btn).paddingBottom], icon: cs(c.querySelector('.job-check > svg')).top,
                source: cs(c.querySelector('.pipe-source')).paddingBottom,
                remote: document.querySelector('#jobOsRoot .pipe-card .pipe-source[data-source=remoteid]').innerText};
    }""")
    after = page.locator(card).bounding_box()
    assert before["width"] == after["width"] and "0px 0px 0px 1px" not in out["shadow"], (before, after, out)
    assert out["btn"] == ["0px", "0px"] and out["icon"] == "-1px" and out["source"] == "2px" and out["remote"] == "REMOTE.ID", out


def test_tailor_resume_asks_for_this_job_or_the_whole_column(page):
    page.click("#jobOsRoot .pipe-col[data-col=new] [data-job-os-action=card-tailor] >> nth=0")
    page.wait_for_selector(".pipe-tailor-menu", timeout=5000)
    items = page.evaluate("() => [...document.querySelectorAll('.pipe-tailor-menu button')].map(b => b.textContent)")
    assert items == ["This job only", "All 6 in New", "Cancel"], items
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.querySelector('.pipe-tailor-menu')", timeout=3000)
    assert page.tailored == []
    page.click("#jobOsRoot .pipe-col[data-col=new] [data-job-os-action=card-tailor] >> nth=0")
    page.click(".pipe-tailor-menu [data-pick=one]")
    page.wait_for_timeout(500)
    assert page.tailored == ["job-0"], page.tailored
    page.click("#jobOsRoot .pipe-col[data-col=new] [data-job-os-action=card-tailor] >> nth=1")
    page.click(".pipe-tailor-menu [data-pick=all]")
    page.wait_for_timeout(1000)
    # Every job in the column that can still start (job-0 already has).
    assert sorted(page.tailored[1:]) == sorted(f"job-{n}" for n in range(1, 6)), page.tailored


def test_a_source_tab_re_sorts_the_cards_with_motion(page):
    page.evaluate("""() => { window.__moves = []; const real = window.playListItemChange;
        window.playListItemChange = (before, nodes, opts) => { window.__moves.push([before.size, nodes.length]); return real(before, nodes, opts); }; }""")
    page.click("#jobOsRoot .pipe-toolbar [data-source=indeed]")
    page.wait_for_timeout(200)
    moves = page.evaluate("() => window.__moves")
    shown = page.evaluate("() => document.querySelectorAll('#jobOsRoot .pipe-card').length")
    assert moves and moves[0][0] == 7 and moves[0][1] == shown == 3, (moves, shown)


def test_side_panel_stages_slide_a_highlight_pill(page):
    page.click("#jobOsSidebar [data-job-os-stage=favorite]")
    page.wait_for_timeout(500)
    out = page.evaluate("""() => { const g = document.querySelector('#jobOsSidebar .job-os-side-stages'), pill = g.querySelector('.mi-pill');
        return {tabs: g.getAttribute('data-mi-tabs'), pill: !!pill, at: pill && Math.round(pill.getBoundingClientRect().top) === Math.round(g.querySelector('.active').getBoundingClientRect().top)}; }""")
    assert out == {"tabs": "y", "pill": True, "at": True}, out


def test_list_view_cards_have_outlines(page):
    page.click("#jobOsRoot [data-job-os-action=pipe-mode][data-mode=list]")
    page.wait_for_selector("#jobOsRoot .job-os-list > .job-os-job-card", timeout=10000)
    border = page.evaluate("() => { const c = getComputedStyle(document.querySelector('#jobOsRoot .job-os-list > .job-os-job-card')); return [c.borderTopWidth, c.borderTopColor]; }")
    assert border[0] == "1px" and border[1] != "rgba(0, 0, 0, 0)", border


def test_the_drawer_is_wider_and_slides_out_right_and_the_add_window_fades(page):
    page.click("#jobOsRoot .pipe-card-main >> nth=0")
    page.wait_for_selector("#jobOsRoot .job-drawer", timeout=10000)
    page.wait_for_timeout(400)
    assert page.evaluate("() => document.querySelector('#jobOsRoot .job-drawer').getBoundingClientRect().width") == 720
    page.evaluate("() => document.querySelector('#jobOsRoot .job-drawer [data-job-os-action=job-close]').click()")
    page.wait_for_timeout(120)
    drawer = page.evaluate("""() => { const g = document.querySelector('.job-drawer.is-closing'); if (!g) return null;
        const r = g.getBoundingClientRect(); return [getComputedStyle(g).animationName, getComputedStyle(g).animationDuration, r.left > innerWidth - 720]; }""")
    assert drawer == ["job-drawer-out", "0.3s", True], drawer
    page.click("#jobOsRoot .pipe-add-btn")
    page.wait_for_selector("#jobOsRoot .job-form-modal", timeout=5000)
    page.wait_for_timeout(400)
    page.evaluate("() => document.querySelector('#jobOsRoot .job-form-modal [data-job-os-action=job-form-close]').click()")
    page.wait_for_timeout(60)
    modal = page.evaluate("() => { const g = document.querySelector('.job-form-modal.is-closing'); return g && [getComputedStyle(g).animationName, getComputedStyle(g).animationDuration, Number(getComputedStyle(g).opacity) < 1]; }")
    assert modal == ["job-modal-out", "0.26s", True], modal


def test_drawer_buttons_share_one_height_with_the_primary_label_lifted(page):
    page.click("#jobOsRoot .pipe-card-main >> nth=0")
    page.wait_for_selector("#jobOsRoot .job-drawer .job-os-actions .job-os-btn.primary", timeout=10000)
    page.wait_for_timeout(400)
    out = page.evaluate("""() => { const row = document.querySelector('#jobOsRoot .job-drawer .job-os-actions');
        return [...row.querySelectorAll(':scope > .job-os-btn')].map(b => [b.textContent.trim(), Math.round(b.getBoundingClientRect().height * 10) / 10]); }""")
    assert len({h for _, h in out}) == 1, out
