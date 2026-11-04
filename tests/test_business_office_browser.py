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
