"""new_chat_inherits_workspace=false: non-project New Chats start in the
settings default_workspace instead of the current conversation's / the
profile's last-used workspace. Project chats keep their bound workspace."""

import pytest

import api.workspace as workspace
from tests._pytest_port import BASE


def _settings(monkeypatch, **values):
    import api.config as config
    monkeypatch.setattr(config, "load_settings", lambda: dict(values))


def _terminal(monkeypatch, terminal):
    import api.config as config
    monkeypatch.setattr(config, "get_config", lambda: {"terminal": terminal})


def test_pinned_default_is_used_only_when_inheritance_is_off(monkeypatch, tmp_path):
    pinned = tmp_path / "MiniPC-Main"
    pinned.mkdir()
    _terminal(monkeypatch, {"backend": "local"})

    _settings(monkeypatch, new_chat_inherits_workspace=False, default_workspace=str(pinned))
    assert workspace.pinned_default_workspace() == str(pinned.resolve())

    _settings(monkeypatch, new_chat_inherits_workspace=True, default_workspace=str(pinned))
    assert workspace.pinned_default_workspace() is None
    _settings(monkeypatch, default_workspace=str(pinned))  # key absent = upstream default
    assert workspace.pinned_default_workspace() is None


def test_pinned_default_ignores_missing_dirs_and_remote_profiles(monkeypatch, tmp_path):
    _terminal(monkeypatch, {"backend": "local"})
    _settings(monkeypatch, new_chat_inherits_workspace=False, default_workspace=str(tmp_path / "gone"))
    assert workspace.pinned_default_workspace() is None

    _settings(monkeypatch, new_chat_inherits_workspace=False, default_workspace=str(tmp_path))
    assert workspace.pinned_default_workspace({"backend": "ssh", "cwd": "/srv"}) is None


def test_profile_default_prefers_pin_over_last_used(monkeypatch, tmp_path):
    pinned, last = tmp_path / "pinned", tmp_path / "last"
    pinned.mkdir()
    last.mkdir()
    lw = tmp_path / "last_workspace.txt"
    lw.write_text(str(last), encoding="utf-8")
    monkeypatch.setattr(workspace, "_last_workspace_file", lambda: lw)
    _terminal(monkeypatch, {"backend": "local"})

    _settings(monkeypatch, new_chat_inherits_workspace=False, default_workspace=str(pinned))
    assert workspace.get_profile_default_workspace() == str(pinned.resolve())
    _settings(monkeypatch, new_chat_inherits_workspace=True, default_workspace=str(pinned))
    assert workspace.get_profile_default_workspace() == str(last)


def _new_chat_workspace(page, inherit, project_id=None):
    return page.evaluate(
        """async ([inherit, projectId]) => {
          const sent = [];
          const realFetch = window.fetch;
          window.fetch = async (url, opts) => {
            if (String(url).includes('/api/session/new')) {
              sent.push(JSON.parse(opts.body));
              return new Response(JSON.stringify({session: {session_id: 'n' + sent.length,
                workspace: '/x', messages: [], title: 'Untitled'}}), {status: 200,
                headers: {'Content-Type': 'application/json'}});
            }
            return realFetch(url, opts);
          };
          window._newChatInheritsWorkspace = inherit;
          S._profileDefaultWorkspace = '/pinned/MiniPC-Main';
          S.session = {session_id: 'prev', workspace: '/previous/chat/ws', messages: []};
          if (projectId) { _allProjects = [{project_id: projectId, workspace_path: '/project/ws'}]; }
          try { await newSession(false, projectId ? {project_id: projectId} : {}); } catch (e) {}
          window.fetch = realFetch;
          return sent.length ? sent[0].workspace : null;
        }""",
        [inherit, project_id],
    )


def test_new_chat_uses_pinned_default_and_project_binding_still_wins():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page()
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            pinned = _new_chat_workspace(page, False)
            inherited = _new_chat_workspace(page, True)
            project = _new_chat_workspace(page, False, "p1")
        finally:
            browser.close()
    assert pinned == "/pinned/MiniPC-Main"
    assert inherited == "/previous/chat/ws"
    assert project == "/project/ws"
