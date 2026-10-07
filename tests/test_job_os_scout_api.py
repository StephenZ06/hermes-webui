"""Scout HTTP routes."""

from __future__ import annotations

import io
import json
from urllib.parse import urlparse

import pytest

from api import profiles, routes
from api.job_os import scout


class _H:
    def __init__(self, body=None):
        raw = json.dumps(body if body is not None else {}).encode()
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)
        self.wfile = io.BytesIO()
        self.status = None

    def send_response(self, s):
        self.status = s

    def send_header(self, *_):
        pass

    def end_headers(self):
        pass

    def json(self):
        return json.loads(self.wfile.getvalue())


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    monkeypatch.setattr(routes, "_check_csrf", lambda _h: True)
    monkeypatch.setattr(routes, "_guard_request_session_visibility", lambda *a, **k: True)
    started = []
    monkeypatch.setattr(scout, "start_discovery", lambda sid, **k: started.append(sid) or {"id": "run-1", "search_id": sid, "status": "queued"})

    def get(path):
        h = _H()
        assert routes.handle_get(h, urlparse(path)) is True
        return h

    def post(path, body=None):
        h = _H(body)
        assert routes.handle_post(h, urlparse(path)) is True
        return h

    return get, post, started


def test_search_crud_run_and_errors(api):
    get, post, started = api
    assert post("/api/job-os/searches", {"search": {"keywords": "python"}}).status == 400  # no Indeed country
    created = post("/api/job-os/searches", {"search": {"keywords": "python", "country": "de", "locations": "Berlin"}})
    assert created.status == 201
    sid = created.json()["search"]["id"]
    listing = get("/api/job-os/searches").json()
    assert [s["id"] for s in listing["searches"]] == [sid] and listing["schedule"] == {"enabled": False, "hours": 6, "summary": "At 12:30 and 18:30, Saturday once"}
    assert listing["searches"][0]["next_run_at"] is None
    assert listing["searches"][0]["country_name"] == "Germany"
    assert {"code": "my", "name": "Malaysia", "host": "malaysia.indeed.com"} in listing["countries"]
    assert listing["posted_within_days"] == [0, 1, 3, 7, 14]
    assert post("/api/job-os/searches", {"search": {"keywords": ""}}).status == 400
    edit = post(f"/api/job-os/searches/{sid}", {"search": {"name": "Py"}, "expected_revision": 0})
    assert edit.status == 200 and edit.json()["search"]["name"] == "Py"
    assert post(f"/api/job-os/searches/{sid}", {"search": {"name": "X"}, "expected_revision": 0}).status == 409
    assert post(f"/api/job-os/searches/{sid}/run", {}).json()["run"]["id"] == "run-1" and started == [sid]
    assert post("/api/job-os/searches/nope/delete").status == 404
    assert post(f"/api/job-os/searches/{sid}/delete").status == 200
    assert get("/api/job-os/searches").json()["searches"] == []


def test_runs_listing_and_unknown_run(api):
    get, post, _ = api
    assert get("/api/job-os/runs").json() == {"runs": []}
    assert get("/api/job-os/runs/missing").status == 404
    assert post("/api/job-os/runs/missing/cancel").status == 404
