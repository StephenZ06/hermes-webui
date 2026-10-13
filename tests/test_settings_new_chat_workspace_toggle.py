"""Settings > Preferences exposes new_chat_inherits_workspace as "Start new
chats in the default workspace" (checked = inheritance off)."""

import json
import urllib.request

import pytest

from tests._pytest_port import BASE


def _post_settings(body):
    req = urllib.request.Request(BASE + "/api/settings", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def _get_settings():
    return json.loads(urllib.request.urlopen(BASE + "/api/settings", timeout=10).read())


def test_toggle_reflects_and_saves_the_setting():
    sync_api = pytest.importorskip("playwright.sync_api")
    _post_settings({"new_chat_inherits_workspace": False})
    try:
        with sync_api.sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.goto(BASE + "/", wait_until="domcontentloaded")
                page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
                assert page.evaluate("() => window._newChatInheritsWorkspace") is False
                page.evaluate("async () => { await switchPanel('settings'); switchSettingsSection('preferences'); }")
                page.wait_for_function("() => { const c=document.getElementById('settingsNewChatDefaultWorkspace'); return c && c.checked; }", timeout=15000)
                shown = page.evaluate("() => document.getElementById('settingsNewChatDefaultWorkspacePath').textContent")
                page.evaluate("() => document.getElementById('settingsNewChatDefaultWorkspace').click()")
                assert page.evaluate("() => window._newChatInheritsWorkspace") is True
                page.wait_for_function("async () => (await (await fetch('/api/settings')).json()).new_chat_inherits_workspace === true", timeout=15000)
            finally:
                browser.close()
        assert shown == _get_settings()["default_workspace"]
    finally:
        _post_settings({"new_chat_inherits_workspace": True})


def test_side_panels_use_the_work_hub_gutter():
    css = open("static/style.css", encoding="utf-8").read()
    block = css[css.index("/* Side-panel gutter: every page's side panel follows Work Hub"):]
    for rule in (".chat-usage-widget{margin:8px 8px 0;}",
                 "#sessionList .session-search.sidebar-search{padding:0 0 8px;}",
                 "#sessionList .project-folder-list{padding-left:0;padding-right:0;}",
                 ".office-page-nav{padding:8px 8px 0;}",
                 ".sidebar .skills-search.sidebar-search{padding:8px 8px 8px;}",
                 ".sidebar .panel-head-sub{padding:8px;}",
                 ".logs-control-panel{padding:8px;}",
                 "#settingsMenu .settings-search.sidebar-search{padding:0 0 8px;}",
                 "#jobOsSidebar .job-os-apify-widget{margin:8px;}",
                 "#jobOsSidebar .job-os-side-stages{padding:8px 0 0;}",
                 ".work-hub-nav{padding:8px;}",
                 "#settingsMenu .settings-search .sidebar-search-icon{left:10px;top:calc(50% - 4px);}",
                 ".sidebar .skills-search .sidebar-search-icon{left:18px;}"):
        assert rule in block, rule
