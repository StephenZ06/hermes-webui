"""Third pass on the project builder and the Skills page: the Review step shows
each part of the build as a preview (a terminal for the project, the style and
motion samples, a skills table, component tiles); the dialog reaches its new
size before a step's content enters; the Template step's art is fetched while
the Location step is open; the Build summary runs to the bottom of the step;
scrollbars only show while something scrolls; the Libraries list sits as far
under its divider as the divider sits under the tabs."""

from tests.test_builder_and_skills_polish_browser import _to_details, page, skills  # noqa: F401  (fixtures)


def _to_review(page):
    _to_details(page)
    page.click(".ps-next")
    page.wait_for_selector(".ps-look-card")
    page.click(".ps-next")
    page.wait_for_selector(".ps-kit-skill")
    page.click(".ps-next")
    page.wait_for_selector(".ps-review-card")


def test_review_shows_a_project_terminal_previews_a_skills_table_and_component_tiles(page):
    _to_review(page)
    facts = page.evaluate("() => [...document.querySelectorAll('.ps-term-fact')].map(r => [r.querySelector('dt').textContent, r.querySelector('dd').textContent])")
    assert facts == [["Project Name:", "lex"], ["Project Type:", "Website"], ["Directory:", "Home / lex"]], facts
    assert page.inner_text(".ps-term-cmd").startswith("$ hermes project create")
    assert "AGENTS.md" in page.inner_text(".ps-term .ps-files")
    assert page.locator(".ps-review-look .ps-look-sample[data-style=elegant]").count() == 1
    assert page.locator(".ps-review-look .ps-motion-demo[data-motion=subtle]").count() == 1
    rows = page.evaluate("() => [...document.querySelectorAll('.ps-review-table tbody tr')].map(tr => [...tr.cells].map(c => c.textContent))")
    assert [r[0] for r in rows] == ["seo-audit", "ui-polish"], rows
    assert rows[0][1] == "Marketing"
    assert page.evaluate("() => getComputedStyle(document.querySelector('.ps-review-table')).borderTopLeftRadius") == "10px"
    assert page.inner_text(".ps-review-skills .ps-review-count") == "2"
    assert page.evaluate("() => [...document.querySelectorAll('.ps-review-comp-name')].map(n => n.textContent)") == ["Split hero"]


def test_build_summary_runs_to_the_bottom_of_the_step(page):
    _to_details(page)
    gap = page.evaluate("() => document.querySelector('.ps-main').getBoundingClientRect().bottom - document.querySelector('.ps-build').getBoundingClientRect().bottom")
    assert abs(gap) <= 1, gap


def test_a_step_enters_after_the_dialog_glides_to_its_new_size(page):
    page.evaluate("() => { window.__starter = _openProjectStarterWizard(); }")
    page.wait_for_selector(".ps-wizard .ps-choice")
    page.click(".ps-choice >> nth=0")
    page.click(".ps-next")
    page.click(".ps-tree-row >> nth=0")
    page.fill(".project-starter-field input", "lex")
    page.click(".ps-next")  # Location -> Template: the dialog grows
    timing = page.evaluate("""() => { const d = document.querySelector('.ps-wizard'), b = document.querySelector('.ps-body');
      const enter = b.getAnimations().find(a => a.animationName && a.animationName.startsWith('ps-step-in'));
      return {gliding: d.getAnimations().some(a => !a.animationName), delay: enter && enter.effect.getTiming().delay}; }""")
    assert timing == {"gliding": True, "delay": 220}, timing


def test_template_art_is_fetched_while_the_location_step_is_open(page):
    art = []
    page.on("request", lambda r: art.append(r.url.rsplit("/", 1)[-1]) if "/static/project-starter/" in r.url else None)
    page.evaluate("() => { window.__starter = _openProjectStarterWizard(); }")
    page.wait_for_selector(".ps-wizard .ps-choice")
    page.click(".ps-choice >> nth=0")
    page.click(".ps-next")
    page.wait_for_selector(".ps-tree-row")
    page.wait_for_timeout(300)
    for key in ("web", "ios", "android", "api", "website", "cli", "research"):
        assert f"{key}.webp" in art, art


def test_a_scrollbar_shows_only_while_its_element_scrolls(skills):
    state = skills.evaluate("""async () => { const list = document.getElementById('skillsList');
      const before = list.classList.contains('is-scrolling');
      list.scrollTop = 120; await new Promise(r => setTimeout(r, 60));
      const during = list.classList.contains('is-scrolling');
      await new Promise(r => setTimeout(r, 1100));
      return {before, during, after: list.classList.contains('is-scrolling')}; }""")
    assert state == {"before": False, "during": True, "after": False}, state


def test_libraries_sit_as_far_under_their_divider_as_the_divider_under_the_tabs_and_options_are_spaced(skills):
    skills.evaluate("() => switchSkillsTab('libraries')")
    skills.wait_for_selector(".lib-filters .themed-select-trigger")
    skills.wait_for_function("() => !document.getElementById('librariesPane').getAnimations().length")
    m = skills.evaluate("""() => { const r = s => document.querySelector(s).getBoundingClientRect();
      return {above: Math.round(r('#skillsSectionHeading').top - r('#skillsTabSkills').bottom),
              below: Math.round(r('.lib-filters .themed-select-trigger').top - r('#skillsSectionHeading').bottom)}; }""")
    assert m["above"] == m["below"] == 12, m
    skills.click(".lib-filters .themed-select-trigger >> nth=0")
    skills.wait_for_function("() => { const p = document.querySelector('.themed-select-popup'); return p && !p.getAnimations().length; }")
    gap = skills.evaluate("""() => { const o = [...document.querySelectorAll('.themed-select-popup .themed-select-option')];
      return Math.round((o[1].getBoundingClientRect().top - o[0].getBoundingClientRect().bottom) * 10) / 10; }""")
    assert gap == 2, gap
