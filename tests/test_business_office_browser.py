"""The Business Office page: real floors, a secret that never comes back, and
an approval that holds an action until the owner decides."""
import json
import urllib.request

import pytest

from tests._pytest_port import BASE


def _post(path, body):
    request = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as res:
        return json.load(res)


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1899, "height": 990})
        page.goto(BASE + "/#office/integrations", wait_until="domcontentloaded")
        page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=20000)
        page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
        page.evaluate("async () => { await switchPanel('office'); window.officeSetSubview('integrations'); }")
        page.wait_for_selector(".office-biz-toolbar", timeout=15000)
        yield page
        browser.close()


@pytest.fixture
def vault(tmp_path):
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / "Business").mkdir()
    _post("/api/notebook/vault", {"path": str(tmp_path), "enabled": True})
    yield tmp_path
    _post("/api/notebook/vault", {"enabled": False, "path": ""})


def test_four_floors_list_their_providers_with_true_states(page):
    assert page.locator(".office-integration-card").count() == 4
    gmail = page.locator(".office-biz-provider", has_text="Gmail")
    assert gmail.locator(".office-integration-status").inner_text() in ("Needs setup", "Ready to connect", "Connected")
    assert page.locator(".office-biz-provider", has_text="ERPNext").locator("button").count() == 0


def test_filter_keeps_focus_and_narrows_providers(page):
    page.fill("[data-biz-input=filter]", "threads")
    page.wait_for_function("() => document.querySelectorAll('.office-biz-provider').length === 1")
    assert page.evaluate("() => document.activeElement.dataset.bizInput") == "filter"


def test_saved_client_secret_never_returns_to_the_page(page):
    page.click("[data-biz=open][data-provider=gmail]")
    page.fill("[name=client_id]", "browser-client")
    page.fill("[name=client_secret]", "browser-secret-value")
    page.click("[data-biz-form=app] button[type=submit]")
    page.wait_for_selector("[data-biz=connect]", timeout=8000)
    assert page.input_value("[name=client_secret]") == ""
    with urllib.request.urlopen(BASE + "/api/office/business/overview", timeout=10) as res:
        assert "browser-secret-value" not in res.read().decode()


def test_the_drawer_shows_the_exact_redirect_address(page):
    page.click("[data-biz=open][data-provider=threads]")
    assert page.inner_text(".office-biz-copy code").endswith("/api/office/business/oauth/callback")
    page.keyboard.press("Escape")
    page.wait_for_selector(".office-biz-drawer", state="detached")


def test_approval_holds_a_note_until_the_owner_approves(page, vault):
    business = _post("/api/office/business/businesses/create", {"name": "Approval Test Shop"})["business"]["id"]
    grant = _post("/api/office/business/vault/grants/add", {"business_id": business, "folder": "Business"})["grant"]
    _post("/api/office/business/vault/grants/agent", {"business_id": business, "grant_id": grant["id"], "agent_id": "documents", "flags": {"can_create": True}})
    _post("/api/office/business/capabilities/mode", {"business_id": business, "agent_id": "documents", "capability_id": "obsidian.create_note", "mode": "approval"})
    _post("/api/office/business/tasks/create", {"business_id": business, "agent_id": "documents", "capability_id": "obsidian.create_note",
                                                "input": {"folder": "Business", "title": "Held", "body": "Waiting body"}})
    page.wait_for_selector(f"[data-biz-input=business] option[value='{business}']", state="attached", timeout=10000)
    page.select_option("[data-biz-input=business]", business, force=True)
    page.click("[data-tab=approvals]")
    page.wait_for_selector("[data-biz=approve]", timeout=15000)
    assert "Waiting body" in page.inner_text(".office-biz-payload")
    assert not (vault / "Business" / "Held.md").exists()
    page.click("[data-biz=approve]")
    page.wait_for_function("() => !document.querySelector('[data-biz=approve]')", timeout=10000)
    for _ in range(40):
        if (vault / "Business" / "Held.md").exists():
            break
        page.wait_for_timeout(250)
    assert (vault / "Business" / "Held.md").read_text() == "Waiting body"


def test_toolbar_is_one_line_of_equal_height_controls(page):
    page.wait_for_selector(".office-biz-tabs .mi-pill", state="attached")
    boxes = page.evaluate("""() => ['.office-biz-business .themed-select-trigger', '.office-biz-add', '.office-biz-filter', '.office-biz-tab']
      .map(selector => { const r = document.querySelector(selector).getBoundingClientRect(); return [r.top, r.height]; })""")
    assert {height for _, height in boxes} == {30}
    assert len({top for top, _ in boxes}) == 1
    work_hub_plus = page.evaluate("""() => { const b = document.createElement('button'); b.className = 'work-hub-create work-hub-icon-button';
      document.body.append(b); const s = getComputedStyle(b); const out = [s.borderTopColor, s.backgroundColor, s.color]; b.remove(); return out; }""")
    plus = page.evaluate("() => { const s = getComputedStyle(document.querySelector('.office-biz-add')); return [s.borderTopColor, s.backgroundColor, s.color]; }")
    assert plus == work_hub_plus
    assert page.locator(".office-biz-add").inner_text() == ""
    assert page.get_attribute(".office-biz-add", "aria-label") == "New business"
    assert page.locator(".office-biz-filter svg").count() == 1


def test_new_business_form_opens_and_cancels_from_the_plus(page):
    page.click(".office-biz-add")
    page.wait_for_selector("[data-biz-form=business] input")
    assert page.get_attribute(".office-biz-add", "aria-label") == "Cancel new business"
    page.click(".office-biz-add")
    page.wait_for_selector("[data-biz-form=business]", state="detached")


def test_tab_highlight_slides_rather_than_redraws(page):
    page.wait_for_selector(".office-biz-tabs .mi-pill", state="attached")
    page.evaluate("() => { window.__pill = document.querySelector('.office-biz-tabs .mi-pill'); }")
    start = page.evaluate("() => window.__pill.getBoundingClientRect().left")
    page.click("[data-tab=settings]")
    page.wait_for_selector("[data-tab=settings].is-active")
    page.wait_for_timeout(60)
    assert page.evaluate("() => window.__pill.isConnected && document.querySelector('.office-biz-tabs .mi-pill') === window.__pill")
    page.wait_for_function("""() => { const t = document.querySelector('[data-tab=settings]').getBoundingClientRect();
      return Math.abs(window.__pill.getBoundingClientRect().left - t.left) < 1; }""")
    assert page.evaluate("() => window.__pill.getBoundingClientRect().left") > start
    assert page.evaluate("() => getComputedStyle(document.querySelector('.office-biz-tabs > .mi-pill')).transitionProperty").find("transform") >= 0


def test_every_status_bubble_on_the_floors_has_a_tint(page):
    tints = page.evaluate("""() => [...document.querySelectorAll('.office-biz-floors .office-integration-status')]
      .map(e => [e.textContent, getComputedStyle(e).backgroundColor])""")
    assert tints and all(colour != "rgba(0, 0, 0, 0)" for _, colour in tints), tints
    assert len({colour for text, colour in tints if text == "Planned"}) == 1


def test_provider_buttons_answer_a_hover(page):
    button = page.locator(".office-biz-floors .office-integration-action").first
    rest = button.evaluate("e => getComputedStyle(e).backgroundColor")
    button.hover()
    page.wait_for_timeout(250)
    assert button.evaluate("e => getComputedStyle(e).backgroundColor") != rest


@pytest.mark.parametrize("tab,titles", [
    ("approvals", ["Approvals"]),
    ("activity", ["Tasks", "Audit log"]),
    ("settings", ["Limits", "Secrets", "Emergency stop", "Schedules"]),
])
def test_other_tabs_are_cards_with_art(page, tab, titles):
    page.click(f"[data-tab={tab}]")
    page.wait_for_selector(".office-biz-card")
    cards = page.evaluate("""() => [...document.querySelectorAll('.office-biz-card')].map(card => {
      const img = card.querySelector('.office-integration-provider-icon img');
      return [card.querySelector('h2').textContent, img.complete && img.naturalWidth > 0]; })""")
    page.wait_for_function("""() => [...document.querySelectorAll('.office-biz-card img')].every(i => i.complete && i.naturalWidth > 0)""")
    assert [title for title, _ in cards] == titles
    assert page.locator("[data-biz-input=filter]").count() == 0
