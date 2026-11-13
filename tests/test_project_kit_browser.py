"""Project menu: Skills & Tools modal and Move up / Move down (static/project-kit.js,
static/sessions.js). The two toolkit endpoints are answered in the page, the
project list is the test server's own."""

import json
import uuid

import pytest

from tests._pytest_port import BASE

ITEMS = [
    {"kind": "skill", "name": "tdd", "description": "Test first", "source": "wizard", "where": "AGENTS.md", "added_at": 1000, "removable": True},
    {"kind": "skill", "name": "repo-skill", "description": "From a repo", "source": "folder", "where": ".agents/skills/repo-skill/SKILL.md", "added_at": 9000, "removable": False},
    {"kind": "package", "name": "react", "description": "npm ^19", "source": "folder", "where": "package.json", "added_at": 5000, "removable": False},
    {"kind": "mcp", "name": "github", "description": "gh-mcp", "source": "folder", "where": ".mcp.json", "added_at": 4000, "removable": False},
]
ADDABLE = [{"name": "docs", "description": "Write docs", "category": "writing"}, {"name": "seo", "description": "Search", "category": "web"}]


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        tab = browser.new_page(viewport={"width": 1280, "height": 800})
        tab.goto(BASE + "/", wait_until="load")
        tab.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
        tab.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay,#updateBanner').forEach(e => e.remove())")
        try:
            yield tab
        finally:
            browser.close()


def _projects(page, n=3):
    tag = uuid.uuid4().hex[:6]
    ids = []
    for i in range(n):
        out = page.evaluate("(name) => api('/api/projects/create', {method:'POST', body: JSON.stringify({name})})", f"kit-{tag}-{i}")
        ids.append(out["project"]["project_id"])
    page.evaluate("() => { switchPanel('chat'); return renderSessionList(); }")
    page.wait_for_selector(f".project-folder-row[data-project-id='{ids[-1]}']")
    return ids


def _menu(page, pid):
    row = page.locator(f".project-folder-row[data-project-id='{pid}']")
    row.hover()
    row.locator(".project-folder-kebab").click(force=True)
    page.wait_for_selector(".project-ctx-menu:not(.popup-closing)")


def _order(page, ids):
    got = page.eval_on_selector_all(".project-folder-list > .project-folder-row", "els => els.map(e => e.dataset.projectId)")
    return [x for x in got if x in ids]


def test_skills_and_tools_sits_below_workspace_and_lists_searches_filters_and_adds(page):
    pid = _projects(page, 1)[0]
    posted = []
    state = {"items": list(ITEMS), "addable": list(ADDABLE)}
    page.route("**/api/projects/toolkit?*", lambda r: r.fulfill(json={"folder": "/w/kit", **state}))

    def post(route):
        body = json.loads(route.request.post_data)
        posted.append(body)
        for n in body.get("add") or []:
            state["items"].append({"kind": "skill", "name": n, "description": "", "source": "added", "where": "AGENTS.md", "added_at": 99999, "removable": True})
            state["addable"] = [a for a in state["addable"] if a["name"] != n]
        state["items"] = [i for i in state["items"] if i["name"] not in (body.get("remove") or [])]
        route.fulfill(json={"ok": True, "folder": "/w/kit", **state})
    page.route("**/api/projects/toolkit/skills", post)

    _menu(page, pid)
    labels = page.eval_on_selector_all(".project-ctx-menu:not(.popup-closing) > div", "els => els.map(e => e.textContent.trim())")
    assert labels[1] == "Skills & Tools" and labels[0].startswith(("Workspace", "Set Workspace")), labels
    page.click(".project-ctx-kit")
    page.wait_for_selector(".pkit-row:not(.pkit-skel)")
    names = lambda: page.eval_on_selector_all(".pkit-list-view .pkit-row .pkit-name", "els => els.map(e => e.firstChild.textContent)")
    assert names() == ["repo-skill", "react", "github", "tdd"]  # most recent first
    assert page.eval_on_selector_all(".pkit-chip", "els => els.map(e => e.dataset.kind)") == ["all", "skill", "package", "mcp"]
    page.click(".pkit-chip[data-kind=skill]")
    assert names() == ["repo-skill", "tdd"]
    page.fill(".pkit-q", "repo")
    assert names() == ["repo-skill"]
    page.fill(".pkit-q", "")
    page.click(".pkit-chip[data-kind=all]")
    # Only the skills the project lists can be taken off; folder items cannot.
    assert page.eval_on_selector_all(".pkit-remove", "els => els.map(e => e.dataset.name)") == ["tdd"]
    page.click(".pkit-add")
    page.wait_for_selector(".pkit-add-view:not([hidden])")
    assert page.is_disabled(".pkit-confirm")
    page.click(".pkit-pick-btn[data-name=docs]")
    assert page.text_content(".pkit-confirm") == "Add 1 to project"
    page.click(".pkit-confirm")
    page.wait_for_selector(".pkit-list-view:not([hidden])")
    assert posted[-1] == {"project_id": pid, "add": ["docs"], "remove": []}
    assert "docs" in names()
    page.locator(".pkit-row", has=page.locator(".pkit-remove[data-name=tdd]")).hover()
    page.click(".pkit-remove[data-name=tdd]")
    page.wait_for_function("() => ![...document.querySelectorAll('.pkit-list-view .pkit-name')].some(e => e.firstChild.textContent === 'tdd')")
    assert posted[-1] == {"project_id": pid, "add": [], "remove": ["tdd"]}
    page.keyboard.press("Escape")
    page.wait_for_selector(".pkit-overlay", state="detached")


def test_a_project_without_a_folder_offers_to_set_one(page):
    pid = _projects(page, 1)[0]
    page.route("**/api/projects/toolkit?*", lambda r: r.fulfill(json={"folder": None, "items": [], "addable": []}))
    _menu(page, pid)
    page.click(".project-ctx-kit")
    page.wait_for_selector(".pkit-set-folder")
    assert page.is_disabled(".pkit-add")


def test_move_up_and_down_reorder_the_folders_and_survive_a_reload(page):
    ids = _projects(page, 3)
    before = _order(page, ids)
    first, last = before[0], before[-1]
    every = page.eval_on_selector_all(".project-folder-list > .project-folder-row", "els => els.map(e => e.dataset.projectId)")
    _menu(page, every[0])  # the top folder cannot go up, the bottom one cannot go down
    assert page.get_attribute(".project-ctx-menu:not(.popup-closing) .project-ctx-move[data-dir='-1']", "aria-disabled") == "true"
    page.keyboard.press("Escape")
    page.mouse.click(5, 790)
    _menu(page, every[-1])
    assert page.get_attribute(".project-ctx-menu:not(.popup-closing) .project-ctx-move[data-dir='1']", "aria-disabled") == "true"
    page.mouse.click(5, 790)
    page.wait_for_selector(".project-ctx-menu", state="detached")
    _menu(page, first)
    page.click(".project-ctx-menu:not(.popup-closing) .project-ctx-move[data-dir='1']")
    page.wait_for_function("""(a) => { const o = [...document.querySelectorAll('.project-folder-list > .project-folder-row')]
        .map(e => e.dataset.projectId).filter(x => a.ids.includes(x)); return o[1] === a.first; }""", arg={"ids": ids, "first": first})
    moved = _order(page, ids)
    assert moved == [before[1], first, before[2]], (before, moved)
    _menu(page, last)
    page.click(".project-ctx-menu:not(.popup-closing) .project-ctx-move[data-dir='-1']")
    page.wait_for_timeout(400)
    assert _order(page, ids) == [before[1], last, first]
    page.reload(wait_until="load")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => { switchPanel('chat'); return renderSessionList(); }")
    page.wait_for_selector(f".project-folder-row[data-project-id='{first}']")
    assert _order(page, ids) == [before[1], last, first]
