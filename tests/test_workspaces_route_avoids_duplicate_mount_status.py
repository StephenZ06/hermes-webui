"""GET /api/workspaces must not check a remote workspace's mount status
twice per request.

mount_status() stats the mountpoint and shells out to `mountpoint -q` --
real work, and on a stale/unresponsive FUSE endpoint that stat can be
genuinely slow. The route used to compute it once for the `mount_status`
field and then have workspace_availability() recompute the exact same
thing for the `availability` field, doubling that cost for every remote
workspace on every panel load.
"""
import json
from types import SimpleNamespace
from urllib.parse import urlsplit


class _RouteHandler:
    def __init__(self):
        self.wfile = _FakeFile()
        self.headers = {}
        self.client_address = ("127.0.0.1", 0)
        self.responses = []

    def send_response(self, status):
        self.responses.append(status)

    def send_header(self, _name, _value):
        pass

    def end_headers(self):
        pass


class _FakeFile:
    def __init__(self):
        self._buf = b""

    def write(self, data):
        self._buf += data

    def getvalue(self):
        return self._buf


def test_remote_workspace_mount_status_checked_once(monkeypatch):
    import api.routes as routes

    calls = []

    def fake_mount_status(entry):
        calls.append(entry.get("path"))
        return "connected"

    monkeypatch.setattr(
        routes,
        "load_workspaces",
        lambda: [{"path": "/workspace/remote/rp5", "name": "RP5", "kind": "remote"}],
    )
    monkeypatch.setattr(routes, "get_last_workspace", lambda: None)
    monkeypatch.setattr(routes, "get_config", lambda: {})
    monkeypatch.setattr("api.ssh_mount.mount_status", fake_mount_status)
    monkeypatch.setattr("api.ssh_mount.remote_reachability", lambda entry: "reachable")

    handler = _RouteHandler()
    routes.handle_get(handler, urlsplit("/api/workspaces"))
    payload = json.loads(handler.wfile.getvalue().decode("utf-8"))

    assert calls == ["/workspace/remote/rp5"], "mount_status() must be checked exactly once per remote entry"
    assert payload["workspaces"][0]["mount_status"] == "connected"
    assert payload["workspaces"][0]["remote_reachability"] == "reachable"
    assert payload["workspaces"][0]["availability"] == "online"


def test_reachable_signal_marks_a_locally_mounted_but_offline_rp5_offline(monkeypatch):
    import api.routes as routes

    monkeypatch.setattr(
        routes,
        "load_workspaces",
        lambda: [{"path": "/workspace/remote/rp5", "name": "RP5", "kind": "remote"}],
    )
    monkeypatch.setattr(routes, "get_last_workspace", lambda: None)
    monkeypatch.setattr(routes, "get_config", lambda: {})
    # SSHFS may remain mounted while the RP5 itself is powered off. The list
    # dot must use the independent probe rather than incorrectly staying green.
    monkeypatch.setattr("api.ssh_mount.mount_status", lambda entry: "connected")
    monkeypatch.setattr("api.ssh_mount.remote_reachability", lambda entry: "unreachable")

    handler = _RouteHandler()
    routes.handle_get(handler, urlsplit("/api/workspaces"))
    payload = json.loads(handler.wfile.getvalue().decode("utf-8"))

    assert payload["workspaces"][0]["mount_status"] == "connected"
    assert payload["workspaces"][0]["remote_reachability"] == "unreachable"
    assert payload["workspaces"][0]["availability"] == "offline"


def test_local_workspace_still_uses_workspace_availability(monkeypatch, tmp_path):
    import api.routes as routes

    monkeypatch.setattr(
        routes,
        "load_workspaces",
        lambda: [{"path": str(tmp_path), "name": "Local"}],
    )
    monkeypatch.setattr(routes, "get_last_workspace", lambda: None)
    monkeypatch.setattr(routes, "get_config", lambda: {})

    handler = _RouteHandler()
    routes.handle_get(handler, urlsplit("/api/workspaces"))
    payload = json.loads(handler.wfile.getvalue().decode("utf-8"))

    assert payload["workspaces"][0]["availability"] == "online"


def test_disconnected_mount_skips_the_reachability_probe(monkeypatch):
    """A dropped mount is offline regardless; don't spend the SSH probe timeout."""
    import api.routes as routes

    probes = []
    monkeypatch.setattr(
        routes,
        "load_workspaces",
        lambda: [{"path": "/workspace/remote/rp5", "name": "RP5", "kind": "remote"}],
    )
    monkeypatch.setattr(routes, "get_last_workspace", lambda: None)
    monkeypatch.setattr(routes, "get_config", lambda: {})
    monkeypatch.setattr("api.ssh_mount.mount_status", lambda entry: "disconnected")
    monkeypatch.setattr("api.ssh_mount.remote_reachability", lambda entry: probes.append(entry) or "reachable")

    handler = _RouteHandler()
    routes.handle_get(handler, urlsplit("/api/workspaces"))
    payload = json.loads(handler.wfile.getvalue().decode("utf-8"))

    assert probes == []
    assert payload["workspaces"][0]["remote_reachability"] == "unknown"
    assert payload["workspaces"][0]["availability"] == "offline"
