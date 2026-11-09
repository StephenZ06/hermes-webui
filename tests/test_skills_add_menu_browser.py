"""Skills page "+": a menu of New skill / Import skill / New category, each
keeping the skill in a chosen category."""

import uuid

import pytest

from tests._pytest_port import BASE


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
            tab.evaluate("async () => { await switchPanel('skills'); }")
            tab.wait_for_timeout(500)
            yield tab
            assert not errors, errors
        finally:
            browser.close()


def test_plus_opens_a_choice_of_three_and_new_skill_opens_the_form_with_a_category_picker(page):
    assert page.evaluate("() => document.querySelector('#panelSkills [onclick=\"openSkillAddMenu()\"], [onclick=\"openSkillAddMenu()\"]') !== null")
    page.evaluate("openSkillAddMenu()")
    page.wait_for_selector(".skill-add-choice")
    assert page.locator(".skill-add-choice strong").all_inner_texts() == ["New skill", "Import", "New category"]
    page.keyboard.press("Escape")
    assert page.locator(".skill-add-overlay").count() == 0
    page.evaluate("openSkillAddMenu()")
    page.click("[data-choice=create]")
    page.wait_for_selector("#skillFormCategory")
    assert page.evaluate("() => document.getElementById('skillFormCategory').tagName") == "SELECT"
    assert page.locator(".skill-add-overlay").count() == 0


def test_a_new_category_appears_in_the_list_and_in_every_picker(page):
    name = f"cat-{uuid.uuid4().hex[:6]}"
    page.evaluate("openSkillAddMenu()")
    page.click("[data-choice=category]")
    page.fill(".skill-add-form [name=name]", name)
    page.click(".skill-add-form [type=submit]")
    page.wait_for_selector(".skill-add-overlay", state="detached")
    page.wait_for_selector(f".skills-cat-header[data-cat='{name}']")
    page.evaluate("openSkillAddMenu()")
    page.click("[data-choice=import]")
    assert name in page.evaluate("() => [...document.querySelectorAll('#skillImportCategory option')].map(o => o.value)")
    # The same name again is refused in the dialog, which stays open.
    page.click("[data-skill-add=back]")
    page.click("[data-choice=category]")
    page.fill(".skill-add-form [name=name]", name)
    page.click(".skill-add-form [type=submit]")
    page.wait_for_selector(".skill-add-status.is-error")
    assert "already exists" in page.inner_text(".skill-add-status")


def test_a_link_from_anywhere_goes_to_the_installer_and_its_answer_stays_in_the_dialog(page):
    page.evaluate("openSkillAddMenu()")
    page.click("[data-choice=import]")
    page.fill(".skill-add-form [name=url]", "https://gitlab.com/owner/repo")
    page.click(".skill-add-form [type=submit]")
    page.wait_for_selector(".skill-add-status.is-error", timeout=60000)
    # Not refused up front any more: the message comes from the installer run.
    assert "Only GitHub links" not in page.inner_text(".skill-add-status")
    assert page.locator(".skill-add-overlay").count() == 1
