"""Mobile shell layout and route-restoration browser checks.

These assertions use the iPhone 15 Pro Max CSS viewport instead of source
strings so an apparently-correct rule cannot hide behind a later override.
"""

import pytest

from tests._pytest_port import BASE


@pytest.fixture
def phone_page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            context = browser.new_context(
                viewport={"width": 430, "height": 932},
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
            yield page
            assert not errors, errors
        finally:
            browser.close()


def test_mobile_titlebar_is_balanced_and_controls_share_one_footprint(phone_page):
    out = phone_page.evaluate(
        """() => {
          const title = document.querySelector('.app-titlebar-inner').getBoundingClientRect();
          const controls = ['btnCommandPalette', 'btnTitlebarNewChat', 'btnReload']
            .map(id => document.getElementById(id).getBoundingClientRect());
          const profile = document.getElementById('titlebarProfileBtn');
          return {
            titleCenter: title.left + title.width / 2,
            viewportCenter: innerWidth / 2,
            controlSizes: controls.map(r => [Math.round(r.width), Math.round(r.height)]),
            profileVisible: getComputedStyle(profile).display !== 'none' && profile.getBoundingClientRect().width > 0,
          };
        }"""
    )
    assert abs(out["titleCenter"] - out["viewportCenter"]) <= 1
    assert out["controlSizes"] == [[44, 44], [44, 44], [44, 44]]
    assert out["profileVisible"] is True


def test_mobile_office_dashboard_keeps_two_by_two_metrics(phone_page):
    phone_page.evaluate("async () => { await switchPanel('office'); officeSetSubview('dashboard'); }")
    phone_page.wait_for_selector(".office-dashboard-snapshot .office-dashboard-metric")
    phone_page.wait_for_timeout(350)
    out = phone_page.evaluate(
        """() => {
          const cards = [...document.querySelectorAll('.office-dashboard-snapshot .office-dashboard-metric')];
          const tops = cards.map(card => Math.round(card.getBoundingClientRect().top));
          const head = document.querySelector('.office-subview-head');
          const subtitle = head && head.querySelector('p');
          const back = document.querySelector('.office-subview-back');
          return {
            rowCount: new Set(tops).size,
            firstRowCount: tops.filter(top => top === tops[0]).length,
            subtitleVisible: subtitle && getComputedStyle(subtitle).display !== 'none',
            backRightGap: Math.round(innerWidth - back.getBoundingClientRect().right),
            pageOverflow: document.documentElement.scrollWidth - innerWidth,
          };
        }"""
    )
    assert out["rowCount"] == 2
    assert out["firstRowCount"] == 2
    assert out["subtitleVisible"] is False
    assert 8 <= out["backRightGap"] <= 24
    assert out["pageOverflow"] <= 0


def test_current_panel_restores_after_reload(phone_page):
    phone_page.evaluate("async () => { await switchPanel('insights'); }")
    phone_page.wait_for_function("() => document.querySelector('main.main').classList.contains('showing-insights')")
    phone_page.reload(wait_until="domcontentloaded")
    phone_page.wait_for_function(
        "() => typeof S !== 'undefined' && S._bootReady === true && document.querySelector('main.main').classList.contains('showing-insights')",
        timeout=30000,
    )
    assert phone_page.evaluate("() => _currentPanel") == "insights"


def test_jobs_subpage_survives_leaving_and_returning(phone_page):
    phone_page.evaluate("""async () => {
      await switchPanel('jobs');
      JobOSState.activeView = 'scout';
      history.replaceState(history.state, '', location.pathname + location.search + '#jobs/scout');
      await switchPanel('office');
      await switchPanel('jobs');
    }""")
    assert phone_page.evaluate("() => location.hash") == "#jobs/scout"
    phone_page.reload(wait_until="domcontentloaded")
    phone_page.wait_for_function(
        "() => typeof S !== 'undefined' && S._bootReady === true && _currentPanel === 'jobs'",
        timeout=30000,
    )
    assert phone_page.evaluate("() => JobOSState.activeView") == "scout"


def test_unknown_nested_route_fails_closed_to_chat(phone_page):
    phone_page.goto(BASE + "/#office/not-a-view", wait_until="domcontentloaded")
    phone_page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", timeout=30000)
    assert phone_page.evaluate("() => _currentPanel") == "chat"
    assert phone_page.evaluate("() => document.querySelector('main.main').classList.contains('showing-office')") is False
