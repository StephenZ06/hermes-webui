"""Jobs page polish: status colours, the job drawer, the dashboard layout, Scout,
the Pipeline's three views and paging, Resume Studio and Settings."""

import json
import sqlite3
import time
import urllib.request
import uuid

import pytest

from tests._pytest_port import BASE, TEST_STATE_DIR

DB = TEST_STATE_DIR / "webui_state" / "job_os" / "job_os.db"
RESUME = "Jane Doe\nSOC Analyst\n\n" + "Triaged SIEM alerts and led incident response for finance teams. " * 10
ANALYSIS = {
    "summary": "Solid triage background, but the role wants deeper cloud detection.",
    "strengths": ["SIEM alert triage", "Incident response lead", "Python playbooks"],
    "gaps": ["No cloud detection", "No CISSP"],
    "must_haves": ["Malaysian right to work", "Three years in a SOC"],
    "seniority": "Senior SOC Analyst",
    "dimensions": {"skills": 40, "experience": 70, "culture": 60, "career": 55},
}


SEEDED = []


def _post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Origin": BASE})
    return json.loads(urllib.request.urlopen(req, timeout=20).read() or b"{}")


def _job(title, status, source="indeed", score=40, offset=0):
    job = _post("/api/job-os/jobs", {"title": title, "company": "Acme", "description": "SIEM, Python, incident response",
                                     "canonical_url": f"https://jobs.example.test/{uuid.uuid4().hex}"})["job"]
    now = int(time.time()) - 86400 - offset  # older than what other tests add, so it never pages theirs away
    SEEDED.append(job["id"])
    with sqlite3.connect(DB) as conn:
        conn.execute("INSERT OR REPLACE INTO job_analyses (job_id, status, fit_score, verdict, data_json, requested_at, finished_at)"
                     " VALUES (?, 'done', ?, '', ?, ?, ?)", (job["id"], score, json.dumps(ANALYSIS), now, now))
        conn.execute("UPDATE jobs SET status=?, source=?, updated_at=? WHERE id=?", (status, source, now, job["id"]))
    return job


def _document(job_id, kind):
    now = int(time.time())
    with sqlite3.connect(DB) as conn:
        conn.execute("INSERT INTO job_documents (id, job_id, kind, status, content, notes_json, revision, created_at, updated_at)"
                     " VALUES (?, ?, ?, 'ready', '# Jane Doe', '{}', 1, ?, ?)", (uuid.uuid4().hex, job_id, kind, now, now))


@pytest.fixture(scope="module")
def seeded():
    _post("/api/job-os/resume", {"filename": "pasted.txt", "text": RESUME})
    marker = uuid.uuid4().hex[:6]
    jobs = {
        "analyzed": _job(f"Analyzed {marker}", "analyzed"),
        "applied": _job(f"Applied {marker}", "submitted", "linkedin"),
        "expired": _job(f"Expired {marker}", "expired"),
        "ready": _job(f"Ready {marker}", "resume_ready"),
    }
    _document(jobs["ready"]["id"], "resume")
    _document(jobs["ready"]["id"], "cover_letter")
    for i in range(24):
        _job(f"Queue {marker} {i}", "analyzed", offset=100 + i)
    jobs["marker"] = marker
    yield jobs
    with sqlite3.connect(DB) as conn:
        for table in ("job_documents", "job_analyses", "job_events"):
            conn.executemany(f"DELETE FROM {table} WHERE job_id=?", [(i,) for i in SEEDED])
        conn.executemany("DELETE FROM jobs WHERE id=?", [(i,) for i in SEEDED])


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        instance = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        yield instance
        instance.close()


@pytest.fixture
def page(browser, seeded):
    context = browser.new_context(viewport={"width": 1470, "height": 956})
    tab = context.new_page()
    tab.goto(BASE + "/#jobs/dashboard", wait_until="domcontentloaded")
    tab.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    tab.evaluate("() => { document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove());"
                 " document.documentElement.dataset.skin = 'zeus-2'; document.documentElement.classList.add('dark'); }")
    tab.evaluate("async () => { await switchPanel('jobs'); }")
    tab.wait_for_selector(".job-os-metrics:not(:has(.is-loading))", timeout=20000)
    yield tab
    context.close()


def _go(page, view):
    page.click(f"#jobOsSidebar [data-job-os-view='{view}']")
    page.wait_for_selector(f".job-os-shell[data-view='{view}']", timeout=15000)


def _mode(page, mode):
    page.click(f"[data-job-os-action='pipe-mode'][data-mode='{mode}']")


def _open_job(page, title):
    _go(page, "pipeline")
    _mode(page, "list")
    page.fill("#job-os-pipe-search", title)
    page.wait_for_selector(f".job-os-job-card:has-text('{title}')", timeout=10000)
    page.click(f".job-os-job-card:has-text('{title}')")
    page.wait_for_selector(".job-drawer .job-drawer-body .job-drawer-section", timeout=15000)
    page.wait_for_timeout(500)


def test_each_status_has_its_own_colour_with_text_centred(page, seeded):
    _go(page, "pipeline")
    _mode(page, "list")
    page.fill("#job-os-pipe-search", seeded["marker"])
    page.wait_for_function("() => ['analyzed', 'submitted', 'expired'].every((s) => document.querySelector(`.job-os-list .job-os-badge[data-status=\"${s}\"]`))", timeout=10000)
    out = page.evaluate("""() => {
      const seen = {};
      for (const b of document.querySelectorAll('.job-os-list .job-os-badge')) {
        const inner = b.querySelector('span');
        const box = b.getBoundingClientRect(), text = inner.getBoundingClientRect();
        seen[b.dataset.status] = {colour: getComputedStyle(b).color, above: text.top - box.top, below: box.bottom - text.bottom,
                                  opacity: getComputedStyle(b).opacity};
      }
      return seen;
    }""")
    assert {"analyzed", "submitted", "expired"} <= set(out)
    assert len({out[k]["colour"] for k in ("analyzed", "submitted", "expired")}) == 3
    for status in ("analyzed", "submitted", "expired"):
        assert abs(out[status]["above"] - out[status]["below"]) <= 0.5, out[status]
        assert out[status]["opacity"] == "1"


def test_kanban_scroll_never_jumps_back(page, seeded):
    _go(page, "pipeline")
    page.wait_for_selector(".pipe-board .pipe-col")
    box = page.evaluate("() => { const r = document.querySelector('.pipe-board').getBoundingClientRect(); return [r.left + 200, r.top + 200]; }")
    page.evaluate("""() => {
      const board = document.querySelector('.pipe-board');
      window.__left = [];
      const tick = () => { window.__left.push(board.scrollLeft); window.__raf = requestAnimationFrame(tick); };
      tick();
    }""")
    page.mouse.move(*box)
    for _ in range(40):
        page.mouse.wheel(30, 0)
        page.wait_for_timeout(8)
    page.wait_for_timeout(500)
    left = page.evaluate("() => { cancelAnimationFrame(window.__raf); return window.__left; }")
    assert left[-1] > 300, left[-1]
    backward = [(a, b) for a, b in zip(left, left[1:]) if b < a - 1]
    assert not backward, backward[:5]
    assert page.evaluate("() => getComputedStyle(document.querySelector('.pipe-board')).scrollSnapType") == "none"


def test_pipeline_list_and_columns_show_twenty_jobs_a_page(page, seeded):
    _go(page, "pipeline")
    page.wait_for_selector(".pipe-col[data-col='new'] .pipe-card")
    assert page.locator(".pipe-col[data-col='new'] .pipe-card").count() == 20
    page.click(".pipe-col[data-col='new'] .pipe-col-pager [aria-label='Next page']")
    page.wait_for_function("() => document.querySelectorAll(\".pipe-col[data-col='new'] .pipe-card\").length < 20 || document.querySelector(\".pipe-col[data-col='new'] .pipe-col-pager\").textContent.includes('21')")
    _mode(page, "list")
    page.wait_for_selector(".job-os-fill .job-os-job-card")
    assert page.locator(".job-os-fill .job-os-job-card").count() == 20
    first = page.inner_text(".job-os-fill .job-os-job-card strong")
    page.click(".job-os-fill .pager [aria-label='Next page']")
    page.wait_for_function("(t) => document.querySelector('.job-os-fill .job-os-job-card strong').textContent !== t", arg=first)


def test_dashboard_activity_sits_under_the_funnel_and_automations_span_both_columns(page, seeded):
    _go(page, "dashboard")
    page.wait_for_selector(".automations-card .automation-row", timeout=15000)
    page.wait_for_selector(".activity", timeout=15000)
    out = page.evaluate("""() => {
      const box = (s) => document.querySelector(s).getBoundingClientRect();
      const funnel = box('.funnel-card'), action = box('.action-centre'), auto = box('.automations-card');
      return {gap: box('.activity').top - box('.funnel').bottom, sameRow: Math.abs(funnel.height - action.height),
              left: Math.abs(auto.left - funnel.left), right: Math.abs(auto.right - action.right), below: auto.top - funnel.bottom};
    }""")
    assert out["gap"] <= 41, out
    assert out["sameRow"] <= 1, out
    assert out["left"] <= 1 and out["right"] <= 1, out
    assert 0 < out["below"] <= 32, out


def test_job_drawer_header_actions_and_analysis(page, seeded):
    _open_job(page, seeded["analyzed"]["title"])
    out = page.evaluate("""() => {
      const q = (s) => document.querySelector('.job-drawer ' + s);
      const box = (n) => n.getBoundingClientRect();
      const row = q('.job-drawer-actions');
      const tops = [...row.querySelectorAll('.job-os-btn,.job-os-icon-btn')].map((b) => Math.round(box(b).top));
      const ring = box(q('.job-os-analysis .fit-ring')), head = box(q('.analysis-head'));
      const panel = box(q('.job-os-analysis'));
      const summary = box(q('.job-os-analysis > p'));
      const table = q('.analysis-table');
      const must = q('.analysis-musts');
      return {
        tagHeights: [box(q('.job-drawer-tags .job-os-badge')).height, box(q('.job-drawer-tags .pipe-source')).height],
        oneLine: new Set(tops).size,
        texts: row.innerText,
        star: !!row.querySelector("[aria-label='Add to Favorite'] svg"),
        order: [...row.querySelectorAll('.job-os-icon-btn')].map((b) => b.getAttribute('aria-label')),
        ringCentre: ring.top + ring.height / 2, headCentre: head.top + head.height / 2,
        above: ring.top - panel.top, below: summary.top - ring.bottom,
        role: q('.analysis-head .analysis-role').textContent,
        tableRadius: getComputedStyle(table).borderTopLeftRadius,
        tableBorder: getComputedStyle(table).borderTopColor,
        cardBorder: getComputedStyle(q('.job-os-analysis')).borderTopColor,
        mustBelow: box(must).top >= box(table).bottom, mustWide: Math.abs(box(must).width - box(table).width) <= 1,
        headings: [...document.querySelectorAll('.job-drawer-section > h3')].map((h) => getComputedStyle(h).textTransform),
      };
    }""")
    assert out["tagHeights"][0] == out["tagHeights"][1], out
    assert out["oneLine"] == 1, out
    assert "Open posting" not in out["texts"] and "Edit" not in out["texts"] and "Add to Favorite" not in out["texts"], out
    assert out["star"] and out["order"] == ["Add to Favorite", "Open posting", "Edit job"], out
    assert abs(out["ringCentre"] - out["headCentre"]) <= 1, out
    assert abs(out["above"] - out["below"]) <= 1, out
    assert out["role"] == "Senior SOC Analyst"
    assert out["tableRadius"] != "0px" and out["tableBorder"] == out["cardBorder"], out
    assert out["mustBelow"] and out["mustWide"], out
    assert set(out["headings"]) == {"uppercase"}, out


def test_tinted_buttons_match_the_work_hub_plus_button(page, seeded):
    _open_job(page, seeded["ready"]["title"])
    out = page.evaluate("""() => {
      const probe = document.createElement('button');
      probe.className = 'work-hub-create';
      document.body.append(probe);
      const want = getComputedStyle(probe);
      const hub = {bg: want.backgroundColor, border: want.borderTopColor, color: want.color};
      probe.remove();
      const b = document.querySelector(".job-drawer-actions .job-os-btn.primary");
      const s = getComputedStyle(b);
      return {hub, text: b.textContent.trim(), bg: s.backgroundColor, border: s.borderTopColor, color: s.color};
    }""")
    assert out["text"] == "Resume Studio", out
    assert (out["bg"], out["border"], out["color"]) == (out["hub"]["bg"], out["hub"]["border"], out["hub"]["color"]), out


def test_apply_kit_uses_document_icons_and_even_spacing(page, seeded):
    _open_job(page, seeded["ready"]["title"])
    out = page.evaluate("""() => {
      const kit = document.querySelector('.job-drawer .apply-kit');
      const docs = [...kit.querySelectorAll('.apply-doc')];
      const note = [...kit.querySelectorAll('.apply-step')][1].querySelector('.job-os-card-note');
      const prev = note.previousElementSibling.getBoundingClientRect(), next = note.nextElementSibling.getBoundingClientRect();
      const box = note.getBoundingClientRect();
      return {labels: docs.map((d) => d.getAttribute('aria-label')), images: docs.map((d) => !!d.querySelector('img')),
              texts: docs.map((d) => d.textContent.trim()), steps: [...kit.querySelectorAll('h4')].map((h) => h.textContent),
              studio: kit.querySelector("[data-job-os-action='studio-open']").textContent.trim(),
              above: box.top - prev.bottom, below: next.top - box.bottom};
    }""")
    assert out["labels"] == ["Resume DOCX", "Resume PDF", "Cover letter DOCX"], out
    assert all(out["images"]) and not any(out["texts"]), out
    assert out["steps"][1] == "Screening Answers" and out["studio"] == "Resume Studio", out
    assert abs(out["above"] - out["below"]) <= 1, out


def test_note_input_and_plus_button_sit_side_by_side(page, seeded):
    _open_job(page, seeded["analyzed"]["title"])
    out = page.evaluate("""() => {
      const form = document.querySelector('#job-os-note-form');
      const input = form.querySelector('textarea').getBoundingClientRect(), add = form.querySelector('button').getBoundingClientRect();
      return {sameHeight: input.height === add.height, square: add.width === add.height, right: add.left >= input.right,
              sameTop: input.top === add.top, label: form.querySelector('button').getAttribute('aria-label'), text: form.querySelector('button').textContent.trim()};
    }""")
    assert out == {"sameHeight": True, "square": True, "right": True, "sameTop": True, "label": "Add note", "text": ""}


def test_suggest_shows_progress_and_a_toast(page, seeded):
    _go(page, "scout")
    page.route("**/api/job-os/searches/*/suggest*", lambda route: (time.sleep(0.5), route.fulfill(json={"titles": ["Threat Analyst"]})))
    page.click("[data-job-os-action='scout-new']")
    page.wait_for_selector("#job-os-search-form")
    page.fill("#job-os-search-form [name='keywords']", "SOC Analyst")
    page.click("[data-job-os-action='scout-suggest']")
    page.wait_for_selector("[data-job-os-action='scout-suggest'].is-loading .btn-spinner", timeout=3000)
    page.wait_for_function("() => /Threat Analyst/.test(document.querySelector(\"#job-os-search-form [name='related_titles']\").value)", timeout=8000)
    assert page.locator("[data-job-os-action='scout-suggest'].is-loading").count() == 0
    assert "related title" in page.inner_text("#toast").lower()


def test_search_form_sections_have_even_dividers(page, seeded):
    _go(page, "scout")
    page.click("[data-job-os-action='scout-new']")
    page.wait_for_selector("#job-os-search-form .scout-form-rule")
    out = page.evaluate("""() => [...document.querySelectorAll('.scout-form-rule')].map((rule) => {
      const box = rule.getBoundingClientRect();
      return [box.top - rule.previousElementSibling.getBoundingClientRect().bottom, rule.nextElementSibling.getBoundingClientRect().top - box.bottom];
    })""")
    assert len(out) >= 3
    for above, below in out:
        assert abs(above - below) <= 1, out
    assert page.evaluate("() => getComputedStyle(document.querySelector('.scout-form .job-os-toggle-text strong')).textTransform") == "uppercase"


def test_match_check_is_a_pipeline_view_with_a_loading_placeholder(page, seeded):
    _go(page, "resume-studio")
    page.wait_for_selector(".resume-master")
    assert page.locator(".match-card").count() == 0
    _go(page, "pipeline")
    page.fill("#job-os-pipe-search", seeded["marker"])
    _mode(page, "match")
    page.wait_for_selector(".match-card .match-ring", timeout=15000)
    page.wait_for_selector(".match-detail .dim-bars", timeout=15000)
    page.route("**/api/job-os/jobs/*", lambda route: (time.sleep(0.4), route.continue_()))
    page.click(".match-step[aria-label='Next job']")
    page.wait_for_selector(".match-detail .match-skeleton", timeout=2000)
    page.wait_for_selector(".match-detail .dim-bars", timeout=8000)
    assert page.locator(".match-skeleton").count() == 0
    head = page.evaluate("""() => {
      const card = document.querySelector('.match-card').getBoundingClientRect();
      const art = document.querySelector('.match-card .card-icon img');
      const box = art.getBoundingClientRect();
      return {src: art.getAttribute('src'), top: box.top - card.top, left: box.left - card.left};
    }""")
    assert "match-check" in head["src"], head
    assert abs(head["top"] - head["left"]) <= 1, head
    assert page.inner_text("[data-job-os-action='automate-all']").strip().lower() == "automate all"


def test_manage_skills_opens_the_career_dashboard(page, seeded):
    _go(page, "resume-studio")
    page.wait_for_selector("[data-job-os-action='skills-manage']")
    assert page.inner_text("[data-job-os-action='skills-manage']").strip() in ("Manage Skills", "MANAGE SKILLS")
    page.click("[data-job-os-action='skills-manage']")
    page.wait_for_function("() => document.querySelector('.dash-side-nav [data-tab=\"career\"].active, .dash [data-tab=\"career\"].active') || /CAREER DASHBOARD/.test(document.body.innerText)", timeout=8000)
    assert page.evaluate("() => document.querySelector('#jobOsRoot')?.offsetParent === null")


def test_resume_studio_titles_and_head_buttons(page, seeded):
    _go(page, "resume-studio")
    page.wait_for_selector(".skill-gaps .job-os-btn")
    page.wait_for_timeout(600)
    out = page.evaluate("""() => ({
      transforms: [...document.querySelectorAll('.job-os-card-head .card-title')].map((t) => getComputedStyle(t).textTransform),
      heights: [...document.querySelectorAll('.card-head-actions .job-os-btn, .gaps-controls .themed-select-trigger')].map((b) => Math.round(b.getBoundingClientRect().height)),
      said: document.querySelector('.resume-master').innerText.includes('Every tailored resume comes from this file'),
      align: getComputedStyle(document.querySelector('.gaps-controls .themed-select-trigger')).justifyContent,
    })""")
    assert set(out["transforms"]) == {"uppercase"}, out
    assert len(set(out["heights"])) == 1, out
    assert out["said"] is False
    assert out["align"] == "center", out


def test_tailored_versions_show_ten_a_page(page, seeded):
    for i in range(11):
        job = _job(f"Tailored {seeded['marker']} {i}", "resume_ready", offset=500 + i)
        _document(job["id"], "resume")
    _go(page, "resume-studio")
    page.wait_for_selector(".studio-item", timeout=15000)
    assert page.locator(".studio-item").count() == 10
    assert page.locator(".pager [aria-label='Next page']").count() == 1


def test_settings_rail_reaches_the_bottom_and_groups_are_cards(page, seeded):
    _go(page, "settings")
    page.wait_for_selector(".settings-rail .settings-nav-item", timeout=15000)
    out = page.evaluate("""() => {
      const main = document.getElementById('mainJobs').getBoundingClientRect();
      const content = document.querySelector('.job-os-content').getBoundingClientRect();
      const rail = document.querySelector('.settings-rail').getBoundingClientRect();
      const pagebox = document.querySelector('.settings-page').getBoundingClientRect();
      const group = getComputedStyle(document.querySelector('.settings-page .set-group'));
      const main2 = document.getElementById('mainJobs');
      return {left: rail.left - main.left, right: pagebox.left - rail.right,
              reach: main2.scrollHeight - (rail.bottom - main.top + main2.scrollTop),
              border: group.borderTopWidth, radius: group.borderTopLeftRadius, padding: group.paddingTop};
    }""")
    # the section list is a side panel now: flush with the page's left edge, the cards a gutter away from it
    assert out["left"] <= 1 and out["right"] >= 16, out
    assert out["reach"] <= 90, out
    assert out["border"] == "1px" and out["radius"] != "0px" and out["padding"] != "0px", out


def test_all_jobs_title_sits_as_far_from_the_top_as_from_the_left(page, seeded):
    _go(page, "pipeline")
    _mode(page, "list")
    page.wait_for_selector(".job-os-fill .card-title")
    page.wait_for_timeout(400)
    out = page.evaluate("""() => {
      const card = document.querySelector('.job-os-fill').getBoundingClientRect();
      const title = document.querySelector('.job-os-fill .card-title');
      const box = title.getBoundingClientRect();
      return {top: box.top - card.top, left: box.left - card.left, transform: getComputedStyle(title).textTransform};
    }""")
    assert abs(out["top"] - out["left"]) <= 1, out
    assert out["transform"] == "uppercase"
