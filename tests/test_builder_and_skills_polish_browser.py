"""Second pass on the project builder and the Skills page: the reasoning card
follows any chosen option and morphs between them, the Toolkit step searches
and filters, the builder's divider and margins are even, and the Skills page
has even spacing, a filter beside its search, smooth folding, and an add
dialog that eases straight to its new height."""

import pytest

from tests._pytest_port import BASE
from tests.test_project_builder_wizard_browser import KIT, LOOK, TEMPLATES
from tests.builder_nav import next_step  # noqa: E402

QUESTIONS = [{"id": "stack", "question": "Which stack?", "options": ["Astro", "Next.js", "Plain HTML"],
              "details": ["Static", "React", "No build"],
              "hows": ["Astro pages with content collections.", "A Next.js app with static export and an API route.", ""],
              "other": "Other stack", "recommended": "Astro", "why": "Astro ships almost no JavaScript.",
              "examples": ["Pairs with Netlify Forms"]}]


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
            tab.route("**/api/workspaces", lambda r: r.fulfill(json={"workspaces": [{"name": "Home", "path": "/tmp/ws"}]}))
            tab.route("**/api/projects/starter/templates", lambda r: r.fulfill(json=TEMPLATES))
            tab.route("**/api/projects/starter/folders*", lambda r: r.fulfill(json={"folders": []}))
            tab.route("**/api/projects/starter/analyze", lambda r: r.fulfill(json={"job_id": "j1"}))
            tab.route("**/api/projects/starter/job*", lambda r: r.fulfill(json={"status": "done", "result": {
                "complete": False, "summary": "One thing left.", "questions": QUESTIONS, "look": LOOK}}))
            tab.route("**/api/projects/starter/toolkit", lambda r: r.fulfill(json=KIT))
            yield tab
            assert not errors, errors
        finally:
            browser.close()


def _to_details(page):
    page.evaluate("() => { window.__starter = _openProjectStarterWizard(); }")
    page.wait_for_selector(".ps-wizard .ps-choice")
    page.click(".ps-choice >> nth=0")
    next_step(page)
    page.click(".ps-tree-row >> nth=0")
    page.fill(".project-starter-field input", "lex")
    next_step(page)
    page.wait_for_selector(".ps-template")
    page.click(".ps-template >> text=Website")
    next_step(page)
    page.fill(".ps-wizard textarea", "A boutique law firm site with service pages.")
    next_step(page)
    page.wait_for_selector(".ps-option")


def test_the_reasoning_card_explains_whichever_option_is_chosen_and_morphs_between_them(page):
    _to_details(page)
    assert page.inner_text(".ps-rec-why-title") == "Why Astro"
    page.click(".ps-option >> nth=1")
    # Mid-swap: placeholder bars stand where the text was.
    assert page.locator(".ps-rec-why .ps-swap-skel i").count() >= 2
    page.wait_for_function("() => !document.querySelector('.ps-swap-skel')")
    assert page.inner_text(".ps-rec-why-title") == "How Next.js would work"
    assert "static export" in page.inner_text(".ps-rec-why")
    assert "Recommended for this brief: Astro." in page.inner_text(".ps-rec-why")
    # Choosing in place keeps the options (no re-render of the question).
    assert page.evaluate("() => document.querySelector('.ps-option.is-selected').dataset.answer") == "Next.js"
    page.click(".ps-option >> nth=2")
    page.wait_for_function("() => !document.querySelector('.ps-swap-skel')")
    assert "Architecture plans the project around Plain HTML" in page.inner_text(".ps-rec-why")
    page.fill(".ps-option-input", "Eleventy")
    page.wait_for_function("() => !document.querySelector('.ps-swap-skel')")
    assert page.inner_text(".ps-rec-why-title") == "Your own answer"


def test_toolkit_skill_search_and_category_select_narrow_the_table_and_ticks_update_in_place(page):
    _to_details(page)
    next_step(page)
    page.wait_for_selector(".ps-look-card")
    next_step(page)
    page.wait_for_selector(".ps-kit-skill")
    # The search box and category select sit at the top of the Skills section.
    bar = ".ps-cz-sec[data-sec=skills] .ps-kit-skillbar"
    assert page.locator(f"{bar} input[type=search]").count() == 1
    labels = page.locator(f"{bar} select option").all_inner_texts()
    assert labels[1:] == ["All (3)", "Design (1)", "Documents (1)", "Marketing (1)"], labels
    assert labels[0].startswith("Recommended (") and page.input_value(f"{bar} select") == "picks"
    assert page.locator(".ps-kit-more").count() == 0  # no "Show all" button
    page.select_option(f"{bar} select", "design")
    page.wait_for_function("() => document.querySelectorAll('.ps-kit-table:not(.ps-kit-ghost) .ps-kit-skill').length === 1")
    assert page.evaluate("() => [...document.querySelectorAll('.ps-kit-table:not(.ps-kit-ghost) .ps-kit-skill')].map(c => c.dataset.skill)") == ["ui-polish"]
    comps = page.locator(".ps-kit-comp").count()
    page.select_option(f"{bar} select", "")
    # Searching skills narrows the table only; the component sections keep their cards.
    page.fill(f"{bar} input", "pdf")
    page.wait_for_function("() => document.querySelectorAll('.ps-kit-table:not(.ps-kit-ghost) .ps-kit-skill').length === 1")
    assert page.locator(".ps-kit-comp").count() == comps
    page.fill(f"{bar} input", "")
    page.wait_for_function("() => document.querySelectorAll('.ps-kit-skill').length === 3")
    card = page.locator(".ps-kit-skill[data-skill=pdf]")
    handle = card.element_handle()
    card.click()
    assert card.locator("[role=checkbox]").get_attribute("aria-checked") == "true"
    assert page.evaluate("(el) => el.isConnected", handle)  # toggled in place, not repainted
    # The Skills section's header counts the picks.
    assert page.inner_text(".ps-cz-sec[data-sec=skills] .ps-cz-summary") == "3 chosen"


def test_builder_divider_has_equal_space_each_side_and_the_dialog_even_margins(page):
    _to_details(page)
    page.wait_for_function("() => !document.querySelector('.ps-body').getAnimations().length")
    m = page.evaluate("""() => { const main = document.querySelector('.ps-main'), body = main.querySelector('.ps-body'),
      build = main.querySelector('.ps-build'), line = getComputedStyle(main, '::after');
      const d = document.querySelector('.ps-wizard'), cs = getComputedStyle(d), b = body.getBoundingClientRect(),
        k = build.getBoundingClientRect(), r = main.getBoundingClientRect();
      const x = r.right - parseFloat(line.right) - 1;
      return {left: x - b.right, right: k.left - (x + 1), pad: [cs.paddingTop, cs.paddingRight, cs.paddingBottom, cs.paddingLeft] }; }""")
    assert m["pad"] == ["24px"] * 4, m
    assert abs(m["left"] - m["right"]) <= 1 and m["left"] >= 20, m


def test_review_titles_are_larger_and_the_step_hides_its_scrollbar(page):
    _to_details(page)
    next_step(page)
    next_step(page)
    page.wait_for_selector(".ps-kit-skill")
    next_step(page)
    page.wait_for_selector(".ps-review-card")
    info = page.evaluate("""() => ({size: parseFloat(getComputedStyle(document.querySelector('.ps-review-card h4')).fontSize),
      bar: getComputedStyle(document.querySelector('.ps-body')).scrollbarWidth})""")
    assert info == {"size": 13, "bar": "none"}, info


@pytest.fixture
def skills(page):
    page.evaluate("async () => { await switchPanel('skills'); }")
    page.wait_for_selector("#skillsList .skills-cat-header")
    return page


def test_skills_page_spacing_is_even_and_the_filter_matches_the_search_height(skills):
    m = skills.evaluate("""() => { const r = s => document.querySelector(s).getBoundingClientRect();
      const head = r('#panelSkills .panel-head'), tabs = r('#skillsTabSkills'), line = r('#skillsSectionHeading'),
        search = r('#skillsSearch'), filter = r('#skillsFilterBtn');
      return {above: Math.round(tabs.top - head.bottom), below: Math.round(line.top - tabs.bottom), after: Math.round(search.top - line.bottom),
              searchH: Math.round(search.height * 100) / 100, filterH: Math.round(filter.height * 100) / 100, label: document.querySelector('#skillsSectionHeading').textContent.trim()}; }""")
    assert m["label"] == "CATEGORIES"
    assert m["above"] == m["below"] == m["after"] == 12, m
    assert m["searchH"] == m["filterH"] == 32, m
    skills.evaluate("() => switchSkillsTab('libraries')")
    skills.wait_for_selector(".lib-filters .themed-select-trigger")
    skills.wait_for_function("() => !document.getElementById('librariesPane').getAnimations().length")
    heights = skills.evaluate("() => [...document.querySelectorAll('.lib-filters .themed-select-trigger')].map(t => Math.round(t.getBoundingClientRect().height * 100) / 100)")
    assert heights == [32, 32, 32], heights
    clipped = skills.evaluate("() => [...document.querySelectorAll('.lib-filters .themed-select-trigger')].filter(t => { const l = t.firstElementChild; return l && l.scrollWidth > l.clientWidth; }).length")
    assert clipped == 0
    assert skills.inner_text("#skillsSectionHeading") == "LIBRARIES"


def test_skills_filter_narrows_to_a_category_and_folding_is_animated(skills):
    cats = skills.evaluate("() => [...document.querySelectorAll('#skillsList .skills-cat-header')].map(h => h.dataset.cat)")
    skills.click("#skillsFilterBtn")
    texts = skills.locator(".filter-menu-item .filter-menu-text").all_inner_texts()
    assert texts[:5] == ["All skills", "Recently added", "Imported", "Turned on", "Turned off"], texts
    skills.click(f".filter-menu-item >> text={cats[-1]}")
    assert skills.evaluate("() => [...document.querySelectorAll('#skillsList .skills-cat-header')].map(h => h.dataset.cat)") == [cats[-1]]
    skills.click("#skillsFilterBtn")
    skills.click(".filter-menu-item >> text=Recently added")
    assert skills.evaluate("() => [...document.querySelectorAll('#skillsList .skills-cat-header')].map(h => h.dataset.cat)") == ["Recently added"]
    skills.click("#skillsFilterBtn")
    skills.click(".filter-menu-item >> text=All skills")
    skills.click("#skillsList .skills-cat-header >> nth=0")
    assert skills.evaluate("() => document.querySelector('#skillsList .skills-cat-items').getAnimations().length") == 1
    skills.wait_for_function("() => document.querySelector('#skillsList .skills-cat-items').hidden")


IMPORTED = {"skills": [
    {"name": "arxiv", "category": "research", "description": "Papers"},
    {"name": "claude-design", "category": "creative", "description": "Built-in design"},
    {"name": "banner-design", "category": "creative", "description": "Banners", "imported": True},
    {"name": "ascii-art", "category": "creative", "description": "Art"},
    {"name": "better-ui", "category": "ui-design", "description": "UI polish", "imported": True},
], "categories": ["creative", "research", "ui-design"]}


def test_imported_skills_lead_the_skills_page_and_have_their_own_filter(page):
    page.route("**/api/skills", lambda r: r.fulfill(json=IMPORTED))
    page.evaluate("async () => { _skillsData = null; _skillsFilter = ''; await switchPanel('skills'); }")
    page.wait_for_selector("#skillsList .skills-cat-header")
    cats = page.evaluate("() => [...document.querySelectorAll('#skillsList .skills-cat-header')].map(h => h.dataset.cat)")
    # Categories holding an imported skill first, then the rest, each alphabetical.
    assert cats == ["creative", "ui-design", "research"], cats
    names = page.eval_on_selector_all("#skillsList .skills-category >> nth=0", "els => [...els[0].querySelectorAll('.skill-name')].map(e => e.textContent)")
    assert names == ["banner-design", "ascii-art", "claude-design"], names
    page.click("#skillsFilterBtn")
    page.click(".filter-menu-item >> text=Imported")
    shown = page.eval_on_selector_all("#skillsList .skill-name", "els => els.map(e => e.textContent)")
    assert shown == ["banner-design", "better-ui"], shown


def test_add_dialog_eases_straight_to_its_new_height_without_a_snap(skills):
    skills.evaluate("openSkillAddMenu()")
    skills.wait_for_selector(".skill-add-choice")
    skills.wait_for_timeout(400)
    heights = skills.evaluate("""() => new Promise(res => { const d = document.querySelector('.skill-add-dialog'), out = [], t0 = performance.now();
      const tick = () => { out.push(d.getBoundingClientRect().height); if (performance.now() - t0 < 600) requestAnimationFrame(tick); else res(out); };
      requestAnimationFrame(tick); document.querySelector('[data-choice=import]').click(); })""")
    rising = [b - a for a, b in zip(heights, heights[1:])]
    assert all(step >= -0.5 for step in rising), heights  # grows, never overshoots and snaps back
