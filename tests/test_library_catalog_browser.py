"""Skills page Libraries tab: catalog listing, tag editing, import review."""

import json
import shutil

import urllib.error
import urllib.request

import pytest

from tests._pytest_port import BASE, TEST_STATE_DIR

LIBROOT = TEST_STATE_DIR / "libraries"


def _call(path, body=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


@pytest.fixture
def catalog():
    shutil.rmtree(LIBROOT, ignore_errors=True)
    d = LIBROOT / "calm-ui"
    (d / "components").mkdir(parents=True)
    (d / "LIBRARY.md").write_text("---\nname: Calm UI\nsource: https://github.com/x/calm\nlicense: MIT\nkind: npm\nframeworks: [react]\ntailwind: false\ninstall: npm i calm-ui\n---\n")
    (d / "components" / "fade.md").write_text("---\nname: Fade\nrole: text-effect\nstyle: [minimal]\nmotion: subtle\nplatform: [web]\n---\n")
    (d / "components" / "loose.md").write_text("---\nname: Loose\n---\n")
    (d / "components" / "wave.md").write_text("---\nname: Wave\nrole: text-effect\nstyle: [playful]\nmotion: expressive\nplatform: [web]\n---\n")
    yield LIBROOT
    shutil.rmtree(LIBROOT, ignore_errors=True)


def test_libraries_api_lists_vocab_and_edits_tags(catalog):
    _, data = _call("/api/libraries")
    assert data["vocab"]["styles"][0] == "minimal"
    [lib] = data["libraries"]
    assert [c["slug"] for c in lib["components"]] == ["fade", "loose", "wave"]
    code, out = _call("/api/libraries/component", {"library": "calm-ui", "component": "loose",
                      "fields": {"role": "cards", "style": ["bold"], "motion": "expressive", "platform": ["web"]}})
    assert code == 200 and out["component"]["needs_details"] is False
    code, _ = _call("/api/libraries/component", {"library": "../x", "component": "a", "fields": {}})
    assert code in (400, 404)


def test_save_refuses_an_existing_slug_without_replace(catalog):
    body = {"slug": "calm-ui", "library": {"name": "Calm UI", "kind": "npm", "frameworks": ["react"]}, "components": []}
    assert _call("/api/libraries/save", body)[0] == 409
    assert _call("/api/libraries/save", {**body, "replace": True})[0] == 200


@pytest.fixture
def page(catalog):
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
            tab.evaluate("async () => { await switchPanel('skills'); }")
            tab.wait_for_timeout(400)
            yield tab
            assert not errors, errors
        finally:
            browser.close()


def test_libraries_tab_lists_components_grouped_by_role_with_a_needs_details_badge(page):
    page.click("#skillsTabLibraries")
    page.wait_for_selector(".lib-card")
    assert page.locator(".lib-card .lib-name").all_inner_texts() == ["Calm UI"]
    roles = page.locator(".lib-role-head").all_inner_texts()
    assert roles[0].lower().startswith("text effect")
    assert page.locator(".lib-comp[data-comp=loose] .lib-badge-needs").count() == 1
    assert page.locator(".lib-comp[data-comp=fade] .lib-chip").all_inner_texts()[:2] == ["Minimal", "Subtle"]
    page.click("#skillsTabSkills")
    assert page.locator("#skillsList").is_visible() and not page.locator("#librariesList").is_visible()


def test_filters_narrow_components_by_style(page):
    page.click("#skillsTabLibraries")
    page.wait_for_selector(".lib-comp")
    page.select_option("#libFilterStyle", "bold")
    assert page.locator(".lib-comp:visible").count() == 0
    page.select_option("#libFilterStyle", "")
    assert page.locator(".lib-comp:visible").count() == 3


def test_editing_tags_clears_needs_details(page):
    page.click("#skillsTabLibraries")
    page.click(".lib-comp[data-comp=loose] [data-lib-edit]")
    page.wait_for_selector(".lib-tag-form")
    page.select_option(".lib-tag-form [name=role]", "cards")
    page.click(".lib-tag-form [data-style=bold]")
    page.select_option(".lib-tag-form [name=motion]", "expressive")
    page.click(".lib-tag-form [data-platform=web]")
    page.click(".lib-tag-form [type=submit]")
    page.wait_for_selector(".lib-comp[data-comp=loose] .lib-badge-needs", state="detached")


def test_import_has_a_skill_library_switch_and_library_review_saves(page):
    page.evaluate("openSkillAddMenu()")
    page.click("[data-choice=import]")
    page.wait_for_selector(".skill-add-kind")
    assert page.locator(".skill-add-kind button").all_inner_texts() == ["Skill", "Library"]
    # Review form directly from a draft (the planner is not available in tests).
    page.evaluate("""() => _renderLibraryReview(_skillAddOverlay, {staging: '', mode: 'page',
        draft: {slug: 'glow', library: {name: 'Glow', source: 'https://glow.dev', kind: 'link', frameworks: ['vanilla']},
                components: [{name: 'Glow card', role: 'cards', style: ['bold'], motion: 'expressive', platform: ['web']}]}})""")
    page.wait_for_selector(".lib-review")
    page.click(".skill-add-form [type=submit]")
    page.wait_for_selector(".skill-add-overlay", state="detached")
    page.click("#skillsTabLibraries")
    page.wait_for_selector(".lib-card[data-lib=glow]")


@pytest.mark.parametrize("width", [1440, 820, 390])
def test_component_cards_share_one_size_and_sit_on_the_8px_grid(page, width):
    page.set_viewport_size({"width": width, "height": 900})
    if width < 700:  # phones show the panel in the slide-out drawer
        page.evaluate("() => { if (!document.querySelector('.sidebar.mobile-open')) toggleMobileSidebar(); }")
        page.wait_for_timeout(600)
    page.evaluate("switchSkillsTab('libraries')")
    page.wait_for_selector(".lib-comp")
    boxes = page.evaluate("() => [...document.querySelectorAll('.lib-comp')].map(e => {const r = e.getBoundingClientRect(); return [r.width, r.height, r.left]})")
    assert len({round(b[0]) for b in boxes}) == 1 and len({round(b[1]) for b in boxes}) == 1
    gap = page.evaluate("() => { const [a, b] = document.querySelector('.lib-grid').querySelectorAll('.lib-comp'); const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect(); return rb.top > ra.top + 1 ? rb.top - ra.bottom : rb.left - ra.right; }")
    assert gap == 8
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
