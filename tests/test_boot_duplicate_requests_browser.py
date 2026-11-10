"""Start-up does not send the same request twice for one answer.

* /api/settings: boot.js fetched it and ran the version-skew check, and the
  skew monitor in panels.js fetched it again at load for the same check.
* /api/projects?all_profiles=1: the sidebar fetches this list, and boot.js
  sent its own identical request to warm the new-chat picker's cache.
* The live-sync stream's first snapshot refetched the sidebar whenever it
  showed WebUI chats only, because that list holds no gateway rows to compare.
"""

from urllib.parse import urlparse

import pytest

from tests._pytest_port import BASE


@pytest.fixture
def booted():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            seen = []
            page.on("request", lambda r: seen.append(r.url) if "/api/" in r.url else None)
            page.goto(BASE + "/", wait_until="load")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.wait_for_timeout(2500)
            yield page, seen
        finally:
            browser.close()


def _count(seen, path, query=None):
    hits = 0
    for url in seen:
        parts = urlparse(url)
        if parts.path.endswith(path) and (query is None or query in parts.query):
            hits += 1
    return hits


def test_settings_are_fetched_once_at_start_up(booted):
    _page, seen = booted
    assert _count(seen, "/api/settings") == 1, seen


def test_the_project_list_is_fetched_only_with_the_sidebar(booted):
    page, seen = booted
    sidebar_loads = _count(seen, "/api/sessions")
    assert sidebar_loads >= 1
    assert _count(seen, "/api/projects", "all_profiles=1") == sidebar_loads, seen
    # The picker's cache is still warm.
    ids = page.evaluate("() => [_allProjectsAllProfiles.map(p => p.project_id).sort(), _allProjects.map(p => p.project_id).sort()]")
    assert ids[0] == ids[1], ids


def test_a_gateway_snapshot_that_cannot_change_a_webui_only_list_is_a_duplicate(booted):
    page, _seen = booted
    result = page.evaluate("""() => {
        const saved = {source: _sessionSourceFilter, show: window._showCliSessions, count: _serverCliSessionCount, all: _allSessions};
        try {
            window._showCliSessions = true;
            _sessionSourceFilter = 'webui';
            _allSessions = [{session_id: 'w1', session_source: 'webui', updated_at: 1, message_count: 1}];
            _serverCliSessionCount = 2;
            const cli = (id, at) => ({session_id: id, source_tag: 'cli', session_source: 'cli', raw_source: 'cli', is_cli_session: true, updated_at: at, message_count: 3});
            return {
                same: _isDuplicateGatewaySessionSnapshot([cli('c1', 5), cli('c2', 6)]),
                updatedOnly: _isDuplicateGatewaySessionSnapshot([cli('c1', 9), cli('c2', 9)]),
                added: _isDuplicateGatewaySessionSnapshot([cli('c1', 5), cli('c2', 6), cli('c3', 7)]),
            };
        } finally {
            _sessionSourceFilter = saved.source; window._showCliSessions = saved.show;
            _serverCliSessionCount = saved.count; _allSessions = saved.all;
        }
    }""")
    assert result == {"same": True, "updatedOnly": True, "added": False}, result
