"""Create-project wizard as a builder: Look & feel preselected from the brief,
the Toolkit step, the build summary, Review, and Create & start building."""

import json

import pytest

from tests._pytest_port import BASE

TEMPLATES = {
    "templates": [
        {"key": k, "label": l, "description": "d", "files": ["AGENTS.md", "README.md", "docs/UI_UX.md"]}
        for k, l in [("blank", "Blank Project"), ("web", "Web App"), ("ios", "iOS App"), ("android", "Android App"),
                     ("api", "API/Backend"), ("website", "Website"), ("cli", "CLI Tool"), ("research", "Research")]
    ],
    "docs_agent": True,
    "planner": {"profile": "architecture", "label": "Architecture", "available": True},
}
LOOK = {"style": "elegant", "motion": "subtle", "framework": "react", "tailwind": True, "why": "A law firm needs calm trust."}
KIT = {
    "visual": True, "framework": "react", "platform": "web", "libraries": 2, "frameworks": [],
    "skills": [
        {"name": "seo-audit", "category": "marketing", "description": "Search optimisation.", "score": 7, "recommended": True},
        {"name": "ui-polish", "category": "design", "description": "Refine UI.", "score": 4, "recommended": True},
        {"name": "pdf", "category": "documents", "description": "PDF forms.", "score": 0, "recommended": False},
    ],
    "components": {
        "hero": [
            {"library": "calm", "library_name": "Calm UI", "slug": "split", "name": "Split hero", "kind": "npm",
             "style": ["elegant"], "motion": "subtle", "recommended": True, "preview": None, "loop": None},
            {"library": "glow", "library_name": "Glow", "slug": "aurora", "name": "Aurora hero", "kind": "copy-paste",
             "style": ["bold"], "motion": "expressive", "recommended": False, "preview": None, "loop": None},
            {"library": "glow", "library_name": "Glow", "slug": "plain", "name": "Plain hero", "kind": "copy-paste",
             "style": ["minimal"], "motion": "none", "recommended": False, "preview": None, "loop": None},
        ],
    },
}


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            tab = browser.new_page(viewport={"width": 1440, "height": 900})
            errors = []
            tab.on("pageerror", lambda e: errors.append(str(e)))
            tab.goto(BASE + "/", wait_until="domcontentloaded")
            tab.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            tab.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay,#updateBanner').forEach(e => e.remove())")
            tab.created = []
            tab.toolkit_requests = []
            tab.route("**/api/workspaces", lambda r: r.fulfill(json={"workspaces": [{"name": "Home", "path": "/tmp/ws"}]}))
            tab.route("**/api/projects/starter/templates", lambda r: r.fulfill(json=TEMPLATES))
            tab.route("**/api/projects/starter/folders*", lambda r: r.fulfill(json={"folders": []}))
            tab.route("**/api/projects/starter/analyze", lambda r: r.fulfill(json={"job_id": "j1"}))
            tab.route("**/api/projects/starter/job*", lambda r: r.fulfill(json={"status": "done", "result": {
                "complete": True, "summary": "All set.", "questions": [], "look": LOOK}}))

            def toolkit(route):
                tab.toolkit_requests.append(json.loads(route.request.post_data or "{}"))
                route.fulfill(json=KIT)
            tab.route("**/api/projects/starter/toolkit", toolkit)

            def create(route):
                tab.created.append(json.loads(route.request.post_data or "{}"))
                route.fulfill(json={"ok": True, "project": {"project_id": "p1", "name": "lex", "workspace_path": "/tmp/ws/lex"},
                                    "starter": {}, "docs_job": None, "kickoff": "Build version 1 of \"lex\" now."})
            tab.route("**/api/projects/create_starter", create)
            yield tab
            assert not errors, errors
        finally:
            browser.close()


def _to_template(page, key):
    page.evaluate("() => { window.__launched = []; window._startProjectChat = (project, opts) => { window.__launched.push([project.project_id, opts && opts.kickoff || '']); }; window.__starter = _openProjectStarterWizard(); }")
    page.wait_for_selector(".ps-wizard .ps-choice")
    page.click(".ps-choice >> nth=0")
    page.click(".ps-next")
    page.click(".ps-tree-row >> nth=0")
    page.fill(".project-starter-field input", "lex")
    page.click(".ps-next")
    page.wait_for_selector(".ps-template")
    page.click(f".ps-template >> text={key}")


def _through_brief(page):
    page.click(".ps-next")
    page.fill(".ps-wizard textarea", "A boutique law firm site with service pages.")
    page.click(".ps-next")
    page.wait_for_selector(".ps-review.is-ok")
    page.click(".ps-next")


def test_look_is_preselected_from_the_brief_with_its_reason(page):
    _to_template(page, "Website")
    assert "Look & feel" in page.locator(".ps-step-label").all_inner_texts()
    _through_brief(page)
    page.wait_for_selector(".ps-look-card")
    # The stars mark the planner's picks; there is no separate banner.
    assert page.locator(".ps-look-rec").count() == 0
    assert page.get_attribute(".ps-look-card.is-selected", "data-style") == "elegant"
    assert page.get_attribute(".ps-motion-card.is-selected", "data-motion") == "subtle"
    assert page.locator(".ps-look-card[data-style=elegant] .ps-option-star").count() == 1
    assert page.locator(".ps-chip-toggle[data-framework=react].is-on").count() == 1
    assert page.locator(".ps-chip-toggle[data-tailwind].is-on").count() == 1
    page.click(".ps-look-card[data-style=bold]")
    assert page.get_attribute(".ps-look-card.is-selected", "data-style") == "bold"
    assert "Bold · Subtle" in page.inner_text(".ps-build")


def test_non_visual_templates_skip_look_and_show_skills_only(page):
    _to_template(page, "CLI Tool")
    assert "Look & feel" not in page.locator(".ps-step-label").all_inner_texts()
    KIT_CLI = dict(KIT, visual=False, components={})
    page.unroute("**/api/projects/starter/toolkit")
    page.route("**/api/projects/starter/toolkit", lambda r: r.fulfill(json=KIT_CLI))
    _through_brief(page)
    page.wait_for_selector(".ps-kit-skill")
    assert page.locator(".ps-kit-comp").count() == 0


def test_toolkit_ticks_recommendations_and_create_sends_them_then_starts_building(page):
    _to_template(page, "Website")
    _through_brief(page)
    page.wait_for_selector(".ps-look-card")
    page.click(".ps-next")
    page.wait_for_selector(".ps-kit-skill")
    req = page.toolkit_requests[-1]
    assert (req["template"], req["style"], req["motion"], req["framework"], req["tailwind"]) == ("website", "elegant", "subtle", "react", True)
    assert sorted(page.eval_on_selector_all(".ps-kit-skill.is-selected", "els => els.map(e => e.dataset.skill)")) == ["seo-audit", "ui-polish"]
    assert page.eval_on_selector_all(".ps-kit-comp.is-selected", "els => els.map(e => e.dataset.comp)") == ["calm/split"]
    page.click(".ps-kit-skill[data-skill=ui-polish]")
    page.click(".ps-kit-comp[data-comp='glow/aurora']")
    assert "1" in page.inner_text(".ps-build-row:has(dt:text('Skills')) dd")
    page.click(".ps-next")
    page.wait_for_selector(".ps-review-card")
    assert page.inner_text(".ps-extra") == "Create project"
    assert page.inner_text(".ps-next") == "Create & start building"
    assert "vendor/ui/glow/" in page.inner_text(".ps-files")
    page.click(".ps-next")
    page.wait_for_function("() => window.__launched.length === 1", timeout=10000)
    body = page.created[-1]
    assert body["toolkit"]["skills"] == ["seo-audit"]
    assert body["toolkit"]["components"] == [{"library": "calm", "slug": "split"}, {"library": "glow", "slug": "aurora"}]
    assert body["toolkit"]["look"]["style"] == "elegant"
    assert page.evaluate("window.__launched") == [["p1", "Build version 1 of \"lex\" now."]]


def test_create_project_alone_sends_no_build_message(page):
    _to_template(page, "Website")
    _through_brief(page)
    page.wait_for_selector(".ps-look-card")
    page.click(".ps-next")
    page.wait_for_selector(".ps-kit-skill")
    page.click(".ps-next")
    page.click(".ps-extra")
    page.wait_for_selector(".ps-done-actions .project-starter-submit:not([disabled])")
    page.wait_for_timeout(900)
    assert page.evaluate("window.__launched") == []


@pytest.mark.parametrize("width", [1440, 820, 390])
def test_builder_cards_share_sizes_on_the_8px_grid_without_overflow(page, width):
    page.set_viewport_size({"width": width, "height": 900})
    _to_template(page, "Website")
    _through_brief(page)
    page.wait_for_selector(".ps-look-card")
    page.wait_for_function("() => document.querySelector('.ps-body').getAnimations({subtree: true}).every(a => a.playState === 'finished' || a.effect.getTiming().iterations === Infinity)")
    for sel in (".ps-look-grid", ".ps-motion-grid"):
        geo = page.evaluate("""(sel) => { const cards = [...document.querySelector(sel).children];
          return cards.map(c => { const r = c.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }); }""", sel)
        rows = {}
        for left, top, w, h in geo:
            rows.setdefault(round(top), []).append((left, w, h))
        for row in rows.values():
            assert len({round(w) for _, w, _ in row}) == 1 and len({round(h) for _, _, h in row}) == 1, (sel, row)
            lefts = sorted(row)
            for (l1, w1, _), (l2, _, _) in zip(lefts, lefts[1:]):
                assert round(l2 - (l1 + w1)) == 8, (sel, lefts)
    assert page.evaluate("() => { const b = document.querySelector('.ps-body'); return b.scrollWidth <= b.clientWidth + 1; }")
    bar_shown = page.evaluate("() => getComputedStyle(document.querySelector('.ps-build-bar')).display !== 'none'")
    assert bar_shown == (width < 900)


def test_start_project_chat_sends_the_kickoff_as_the_first_message(page):
    sent = page.evaluate("""async () => {
      const calls = [];
      window.newSession = async () => { calls.push('new'); };
      window.renderSessionList = async () => {};
      window.send = async () => { calls.push(['send', document.getElementById('msg').value]); };
      await _startProjectChat({project_id: 'p1'}, {kickoff: 'Build version 1 now.'});
      await _startProjectChat({project_id: 'p2'});
      return calls; }""")
    assert sent == ["new", ["send", "Build version 1 now."], "new"]
