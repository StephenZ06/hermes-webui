"""Profile creation returns JSON when its filesystem provider fails."""

import io
import json
from urllib.parse import urlparse

import api.routes as routes


class _Handler:
    def __init__(self, body):
        self.rfile = io.BytesIO(json.dumps(body).encode())
        self.headers = {"Content-Length": str(len(self.rfile.getvalue())), "Content-Type": "application/json"}
        self.wfile = io.BytesIO()
        self.status = None

    def send_response(self, status): self.status = status
    def send_header(self, *_): pass
    def end_headers(self): pass


def test_profile_create_returns_safe_json_for_filesystem_failure(monkeypatch):
    import api.profiles as profiles

    def fail(*_args, **_kwargs):
        raise OSError("disk unavailable: /private/path")

    monkeypatch.setattr(profiles, "create_profile_api", fail)
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    handler = _Handler({"name": "newprofile"})

    routes.handle_post(handler, urlparse("http://example.test/api/profile/create"))
    assert handler.status == 503
    payload = json.loads(handler.wfile.getvalue())
    assert payload == {"error": "Profile storage is temporarily unavailable. Please try again."}


def _post_with_failing(monkeypatch, attr, path, body):
    import api.profiles as profiles

    def fail(*_args, **_kwargs):
        raise OSError("disk unavailable: /private/path")

    monkeypatch.setattr(profiles, attr, fail)
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    handler = _Handler(body)
    routes.handle_post(handler, urlparse(f"http://example.test{path}"))
    return handler


def test_profile_update_returns_safe_json_for_filesystem_failure(monkeypatch):
    handler = _post_with_failing(monkeypatch, "update_profile_api", "/api/profile/update", {"name": "newprofile"})
    assert handler.status == 503
    assert json.loads(handler.wfile.getvalue()) == {"error": "Profile storage is temporarily unavailable. Please try again."}


def test_profile_delete_returns_safe_json_for_filesystem_failure(monkeypatch):
    handler = _post_with_failing(monkeypatch, "delete_profile_api", "/api/profile/delete", {"name": "newprofile"})
    assert handler.status == 503
    assert json.loads(handler.wfile.getvalue()) == {"error": "Profile storage is temporarily unavailable. Please try again."}
