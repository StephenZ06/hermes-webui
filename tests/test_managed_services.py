"""Safety and UI coverage for the Settings → Systems managed-service cards."""

from __future__ import annotations

import subprocess
from pathlib import Path


def test_managed_service_status_is_sanitized_and_has_only_known_targets(monkeypatch):
    from api import managed_services

    monkeypatch.setattr(managed_services, "_firecrawl_status", lambda: {"id": "firecrawl", "state": "running", "reachable": True, "detail": "API reachable"})
    monkeypatch.setattr(managed_services, "_nine_router_status", lambda: {"id": "9router", "state": "stopped", "reachable": False, "detail": "Not running"})

    payload = managed_services.managed_services_status()

    assert payload == {"services": [
        {"id": "firecrawl", "state": "running", "reachable": True, "detail": "API reachable"},
        {"id": "9router", "state": "stopped", "reachable": False, "detail": "Not running"},
    ]}
    assert "/home/" not in repr(payload)
    assert "token" not in repr(payload).lower()


def test_firecrawl_restart_uses_fixed_compose_project_without_browser_input(monkeypatch, tmp_path):
    from api import managed_services

    compose_dir = tmp_path / "firecrawl"
    compose_dir.mkdir()
    (compose_dir / "docker-compose.yaml").write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setattr(managed_services, "_FIRECRAWL_COMPOSE_DIR", compose_dir)
    calls = []
    monkeypatch.setattr(managed_services.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)) or subprocess.CompletedProcess(command, 0, stdout="", stderr=""))
    monkeypatch.setattr(managed_services, "_firecrawl_status", lambda: {"id": "firecrawl", "state": "running", "reachable": True, "detail": "API reachable"})

    result = managed_services.control_managed_service("firecrawl", "restart")

    assert result["ok"] is True
    assert calls[0][0] == ["docker", "compose", "-p", "firecrawl", "-f", str(compose_dir / "docker-compose.yaml"), "restart"]
    assert calls[0][1]["shell"] is False


def test_unknown_service_or_action_never_spawns_a_command(monkeypatch):
    from api import managed_services

    monkeypatch.setattr(managed_services.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not run")))

    for service, action in (("anything-else", "start"), ("firecrawl", "delete")):
        try:
            managed_services.control_managed_service(service, action)
        except ValueError:
            pass
        else:
            raise AssertionError("unknown target must be rejected")


def test_9router_service_unit_adds_the_detected_node_directory_to_its_path(monkeypatch):
    from api import managed_services

    executable = Path("/mnt/c/Users/Z014/AppData/Roaming/npm/9router")
    node = Path("/home/z014/.hermes/node/bin/node")
    monkeypatch.setattr(managed_services, "_nine_router_node_path", lambda: node)

    content = managed_services._nine_router_unit_content(executable)

    assert "ExecStart=/mnt/c/Users/Z014/AppData/Roaming/npm/9router --host 127.0.0.1 --no-browser --tray" in content
    assert "Environment=PATH=/home/z014/.hermes/node/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" in content


def test_systems_page_includes_managed_service_cards_and_stop_confirmation():
    root = Path(__file__).resolve().parents[1]
    panels = (root / "static" / "panels.js").read_text(encoding="utf-8")
    index = (root / "static" / "index.html").read_text(encoding="utf-8")

    assert 'id="managedServicesList"' in index
    assert "loadManagedServices" in panels
    assert "/api/system/services" in panels
    assert "confirm(" in panels
    assert "MANAGED_SERVICES_INTERVAL_MS" in panels
    assert "_syncManagedServicesPolling" in panels
