"""HTTP boundary tests for the first Job OS API endpoints."""

from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.parse import urlparse

from api import profiles, routes
from api.job_os.api import handle_job_os_get, handle_job_os_patch, handle_job_os_post


class _Handler:
    def __init__(self, body: bytes = b"{}") -> None:
        self.headers = {"Content-Length": str(len(body))}
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.status: int | None = None

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, _name: str, _value: str) -> None:
        pass

    def end_headers(self) -> None:
        pass


def _json(handler: _Handler) -> dict:
    return json.loads(handler.wfile.getvalue())


def _body(payload: object) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _use_profile_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(profiles, "get_active_profile_name", lambda: "research")
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path / "research")


def test_job_os_routes_expose_capability_and_validate_bad_job_payloads(tmp_path, monkeypatch):
    """The registered prefix exposes capability while malformed job input is a 400."""
    _use_profile_home(monkeypatch, tmp_path)
    monkeypatch.setattr(routes, "_guard_request_session_visibility", lambda *args, **kwargs: True)
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)

    capability = _Handler()
    assert routes.handle_get(capability, urlparse("/api/job-os/capability")) is True
    assert capability.status == 200
    assert _json(capability)["available"] is True

    malformed = _Handler(b"{not-json")
    assert routes.handle_post(malformed, urlparse("/api/job-os/jobs")) is True
    assert malformed.status == 400
    assert "title" in _json(malformed)["error"]


def test_job_os_create_duplicate_read_and_patch_contract(tmp_path, monkeypatch):
    """Create, duplicate detection, item reads, and revisioned updates use truthful statuses."""
    _use_profile_home(monkeypatch, tmp_path)
    payload = {"title": "Platform Engineer", "canonical_url": "https://jobs.example.test/platform"}

    created = _Handler()
    assert handle_job_os_post(created, urlparse("/api/job-os/jobs"), payload) is True
    created_payload = _json(created)
    assert created.status == 201
    job_id = created_payload["job"]["id"]

    duplicate = _Handler()
    handle_job_os_post(duplicate, urlparse("/api/job-os/jobs"), payload)
    assert duplicate.status == 409
    assert _json(duplicate)["existing_id"] == job_id

    missing = _Handler()
    handle_job_os_get(missing, urlparse("/api/job-os/jobs/missing"))
    assert missing.status == 404

    updated = _Handler()
    handle_job_os_patch(
        updated,
        urlparse(f"/api/job-os/jobs/{job_id}"),
        {"status": "scraped", "expected_revision": 0},
    )
    assert updated.status == 200
    assert _json(updated)["job"]["status"] == "scraped"

    stale = _Handler()
    handle_job_os_patch(
        stale,
        urlparse(f"/api/job-os/jobs/{job_id}"),
        {"status": "analyzed", "expected_revision": 0},
    )
    assert stale.status == 409


def test_job_os_list_rejects_unknown_filter_values(tmp_path, monkeypatch):
    """Unrecognized filter values do not silently broaden a job listing."""
    _use_profile_home(monkeypatch, tmp_path)
    handler = _Handler()

    handle_job_os_get(handler, urlparse("/api/job-os/jobs?status=not-a-status"))

    assert handler.status == 400
