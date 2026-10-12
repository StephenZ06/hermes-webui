"""Cross-page mobile containment checks at target portrait and landscape sizes."""

import pytest

from tests._pytest_port import BASE


PANELS = [
    "chat", "notes", "office", "jobs", "tasks", "agents", "profiles",
    "memory", "knowledge", "skills", "workspaces", "notebook", "insights",
    "logs", "audit", "settings",
]


@pytest.mark.parametrize("viewport", [(430, 932), (932, 430)])
def test_all_primary_pages_stay_inside_the_mobile_viewport(viewport):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            context = browser.new_context(
                viewport={"width": viewport[0], "height": viewport[1]},
                is_mobile=True,
                has_touch=True,
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function(
                "() => typeof S !== 'undefined' && S._bootReady === true",
                timeout=30000,
            )
            page.evaluate(
                "() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(el => el.remove())"
            )
            failures = []
            for panel in PANELS:
                if not page.locator(f".nav-tab[data-panel='{panel}']").count():
                    continue
                page.evaluate("panel => switchPanel(panel)", panel)
                page.wait_for_timeout(250)
                result = page.evaluate(
                    """panel => {
                      const main = document.querySelector('main.main');
                      const visible = [...main.children].filter(el => {
                        const style = getComputedStyle(el);
                        return style.display !== 'none' && style.visibility !== 'hidden';
                      });
                      return {
                        panel,
                        documentOverflow: document.documentElement.scrollWidth - innerWidth,
                        bodyOverflow: document.body.scrollWidth - innerWidth,
                        mainRight: Math.round(main.getBoundingClientRect().right - innerWidth),
                        visible: visible.map(el => el.id || el.className),
                      };
                    }""",
                    panel,
                )
                if result["documentOverflow"] > 1 or result["bodyOverflow"] > 1 or result["mainRight"] > 1:
                    failures.append(result)
            assert not failures, failures
            assert not errors, errors
        finally:
            browser.close()
