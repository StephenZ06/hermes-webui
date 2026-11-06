"""Work Hub, Notes and Office: requested nudges, measured as ink on a real 2x display.

Each entry names a rule to undo. The ink is read with and without that rule, so the
number is how far the request moved what the eye sees, not what a stylesheet declares.
"""

import json
import urllib.request

import pytest

from tests._pytest_port import BASE
from tests.test_chat_optical_alignment_browser import _ink, browser, pytestmark, real_2x  # noqa: F401


def _moved(page, selector, kind, undo, within=None):
    now = _ink(page, selector, kind, within=within)
    handle = page.add_style_tag(content=undo)
    page.wait_for_timeout(200)
    old = _ink(page, selector, kind, within=within)
    handle.evaluate("e => e.remove()")
    return now["top"] - old["top"]


def _panel(page, name):
    page.evaluate("async name => { await switchPanel(name); }", name)
    page.mouse.move(900, 600)
    page.wait_for_timeout(1500)


def _row(page, host, html):
    page.evaluate("([host, html]) => document.querySelector(host).insertAdjacentHTML('afterbegin', html)", [host, html])
    page.wait_for_timeout(50)


def test_work_hub_nudges(real_2x):
    page = real_2x
    _panel(page, "notes")
    switch = ".work-hub-view-switch > button"
    moved = {
        "board": _moved(page, "[data-view='board']", "icon", f"{switch} svg{{translate:none!important}}"),
        "list": _moved(page, "[data-view='list']", "icon", f"{switch} svg{{translate:none!important}}"),
        "inbox": _moved(page, "#workHubSidebar [data-scope='inbox']", "icon",
                        "#workHubSidebar [data-scope='inbox'] svg{top:-1px!important}"),
    }
    assert moved == {"board": .5, "list": .5, "inbox": 1}
    assert page.evaluate("""() => getComputedStyle(document.querySelector(
      '#workHubSidebar .work-hub-scope-mark--all')).translate""") == "none"
    _row(page, "#workHubSidebar .work-hub-nav", '<div class="work-hub-board-row" id="fxBoard"><button type="button"><span>HEHE</span></button></div>')
    assert _moved(page, "#fxBoard span", "text", "#fxBoard span{top:-1px!important}", within="#fxBoard") == 1
    page.click("#workHubProjectCreate")
    page.wait_for_selector(".work-hub-create-menu button")
    menu = ".work-hub-create-menu > button:first-child"
    assert _moved(page, menu, "text", f"{menu}{{padding-top:7px!important;padding-bottom:7px!important}}") == .5


def test_notes_nudges(real_2x):
    page = real_2x
    _panel(page, "notebook")
    for scope in ("general", "pinned", "favorites"):
        selector = f"#notebookSidebar [data-nb-scope='{scope}']"
        assert _moved(page, selector, "icon", f"{selector} > svg{{translate:none!important}}") == .5, scope
    assert _moved(page, "#nbSearch", "text", "#nbSearch{top:0!important}", within=".nb-search") == -.5
    _row(page, "#notebookSidebar .nb-nav", '<div class="work-hub-board-row nb-tree-note" id="fxNote"><button type="button"><span>HEHE</span></button></div>')
    assert _moved(page, "#fxNote span", "text", "#fxNote span{top:0!important}", within="#fxNote") == 0  # the 1px drop was taken back
    page.evaluate("() => document.getElementById('fxNote').remove()")
    page.click("[data-nb-action='create-menu']")
    page.wait_for_selector(".nb-create-menu button")
    menu = ".nb-create-menu > button:first-child"
    assert _moved(page, menu, "text", f"{menu}{{padding-top:7px!important;padding-bottom:7px!important}}") == .5


def _post(path, body):
    request = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as res:
        return json.load(res)


@pytest.fixture
def vault(tmp_path):
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / "00 Inbox").mkdir()
    (tmp_path / "Root.md").write_text("HEHE")
    (tmp_path / "00 Inbox" / "Inner.md").write_text("HEHE")
    _post("/api/notebook/vault", {"path": str(tmp_path), "enabled": True})
    yield tmp_path
    _post("/api/notebook/vault", {"enabled": False, "path": ""})


def test_obsidian_nudges(real_2x, vault):
    page = real_2x
    page.reload(wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", timeout=30000)
    page.evaluate("""() => { document.querySelectorAll('#onboardingOverlay,#appTourOverlay,#updateBanner').forEach(e => e.remove());
      document.documentElement.dataset.skin = 'zeus-2'; document.documentElement.classList.add('dark'); }""")
    page.add_style_tag(content="*,*::before,*::after{transition:none!important;animation-duration:0s!important}")
    _panel(page, "notebook")
    page.click("[data-nb-action='vault-open']")
    page.wait_for_selector(".nb-nav-vault .nb-place-btn", timeout=10000)
    every, root = ".nb-nav-vault [data-nb-scope='all']", ".nb-nav-vault [data-nb-scope='general']"
    label, value = " > span:not(.nb-scope-count)", " > .nb-scope-count"
    folder = ".nb-nav-vault .nb-place-btn"
    moved = {
        "all icon": _moved(page, every, "icon", f"{every} > svg{{top:-1px!important}}"),
        "all text": _moved(page, every + label, "text", f"{every}{label}{{top:-1px!important}}", within=every),
        "all value": _moved(page, every + value, "text", f"{every}{value}{{top:-2px!important}}", within=every),
        "root icon": _moved(page, root, "icon", f"{root} > svg{{translate:none!important}}"),
        "root text": _moved(page, root + label, "text", f"{root}{label}{{top:-1px!important}}", within=root),
        "root value": _moved(page, root + value, "text", f"{root}{value}{{top:-2px!important}}", within=root),
        "folder name": _moved(page, f"{folder} .project-folder-name", "text",
                              f"{folder} .project-folder-name{{top:0!important}}", within=folder),
        "folder count": _moved(page, f"{folder} .project-folder-count", "text",
                               f"{folder} .project-folder-count{{top:0!important}}", within=folder),
    }
    assert moved == {"all icon": 1, "all text": 1, "all value": 1, "root icon": .5, "root text": .5,
                     "root value": 1, "folder name": .5, "folder count": 1}


def test_office_nudges(real_2x):
    page = real_2x
    _panel(page, "office")
    page.evaluate("() => window.officeSetSubview('dashboard')")
    page.wait_for_selector(".office-dashboard-metric")
    page.wait_for_timeout(600)
    assert _moved(page, "#officeSearch", "text", "#officeSearch{padding-top:6px!important;padding-bottom:8px!important}") == .5
    head = ".office-subview-head > h1"
    assert _moved(page, head, "text", f"{head}{{top:0!important}}") == .5
    text = ".office-dashboard-metric:first-child .office-dash-metric-text"
    assert _moved(page, text, "text", ".office-dashboard-metric > *{top:-1px!important}", within=".office-dashboard-metric:first-child") == .5
    page.evaluate("() => window.officeSetSubview('integrations')")
    page.wait_for_selector(".office-biz-provider")
    page.wait_for_timeout(600)
    assert _moved(page, head, "text", f"{head}{{top:0!important}}") == .5
    card = ".office-biz-floors .office-integration-card:first-child"
    row = f"{card} .office-biz-provider:first-child"
    undo = ".office-biz-floors :is(.office-biz-provider-text,.office-integration-status){top:0!important}"
    assert _moved(page, f"{row} strong", "text", undo, within=row) == -.5
    assert _moved(page, f"{row} .office-integration-status", "text", undo, within=row) == -.5
    assert _moved(page, f"{card} h2", "text", undo, within=f"{card} .office-integration-card-head") == 0


def test_office_task_status_nudges(real_2x):
    # The live floor needs WebGL, which a headless browser may lack, so this is the panel's own markup.
    page = real_2x
    page.evaluate("""() => document.body.insertAdjacentHTML('beforeend', `<div class="office-tasks" id="fxTasks"
      style="position:fixed;left:500px;top:300px;width:300px;height:160px;z-index:99999;background:#111"><div class="office-tasks-head">
      <button type="button" class="office-tasks-toggle"><span class="office-tasks-title-group"><span class="office-tasks-title">TASK STATUS</span></span></button></div>
      <div class="office-tasks-filters"><button type="button" class="office-tasks-filter" data-filter="all">All</button></div></div>`)""")
    page.wait_for_timeout(100)
    assert _moved(page, ".office-tasks-title", "text", ".office-tasks-title-group{top:0!important}", within=".office-tasks-head") == .5
    assert _moved(page, ".office-tasks-filter", "text", ".office-tasks-filter{padding-top:4px!important;padding-bottom:4px!important}") == -.5


def test_office_session_rows_nudges(real_2x):
    page = real_2x
    _panel(page, "office")
    assert page.evaluate("""() => {
      const row = host => { const b = document.createElement('button'); b.className = 'office-session-row';
        b.innerHTML = '<span class="office-session-text"><span class="office-session-title">HE</span><span class="office-session-meta">HE</span></span>';
        document.querySelector(host).prepend(b); return b; };
      const top = (b, part) => getComputedStyle(b.querySelector(part)).top;
      const history = row('#officeSessionList'), folder = row('#officeProjectFolders');
      return [top(history, '.office-session-title'), top(history, '.office-session-meta'), top(folder, '.office-session-title'), top(folder, '.office-session-meta')];
    }""") == ["0.5px", "-0.5px", "0px", "-1px"]
