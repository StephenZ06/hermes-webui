"""Fixed-target controls for local services used by Hermes WebUI.

The browser may only address the two services declared here.  No command,
path, URL, or systemd unit is accepted from a request.
"""

from __future__ import annotations

import http.client
import shutil
import socket
import subprocess
import threading
from pathlib import Path
from typing import Any


_ACTION_LOCK = threading.Lock()
_FIRECRAWL_COMPOSE_DIR = Path.home() / "firecrawl"
_FIRECRAWL_PROJECT = "firecrawl"
_NINE_ROUTER_UNIT = "9router.service"
_NINE_ROUTER_PORT = 20128
_NINE_ROUTER_USAGE_ROUTE = 'aL=["/api/usage/","/api/providers/client","/api/shutdown",'
_NINE_ROUTER_PREVIOUS_USAGE_ROUTE = 'aL=["/api/usage/","/api/shutdown",'
_VALID_SERVICES = {"firecrawl", "9router"}
_VALID_ACTIONS = {"start", "stop", "restart"}
_SYSTEMD_BASE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def _firecrawl_compose_files() -> list[Path]:
    base = _FIRECRAWL_COMPOSE_DIR / "docker-compose.yaml"
    if not base.is_file():
        raise RuntimeError("Firecrawl compose configuration is unavailable")
    files = [base]
    override = _FIRECRAWL_COMPOSE_DIR / "docker-compose.override.yaml"
    if override.is_file():
        files.append(override)
    return files


def _run(command: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        shell=False,
    )


def _http_reachable(host: str, port: int) -> bool:
    try:
        conn = http.client.HTTPConnection(host, port, timeout=1.5)
        conn.request("GET", "/")
        response = conn.getresponse()
        response.read(256)
        conn.close()
        return 200 <= response.status < 500
    except (OSError, http.client.HTTPException):
        return False


def _firecrawl_status() -> dict[str, Any]:
    try:
        result = _run([
            "docker", "ps", "--filter", f"label=com.docker.compose.project={_FIRECRAWL_PROJECT}",
            "--format", "{{.State}}",
        ])
        states = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.SubprocessError):
        states = []
    reachable = _http_reachable("127.0.0.1", 3002)
    if reachable:
        return {"id": "firecrawl", "state": "running", "reachable": True, "detail": "API reachable"}
    if states:
        return {"id": "firecrawl", "state": "starting", "reachable": False, "detail": "Containers are starting"}
    if _FIRECRAWL_COMPOSE_DIR.is_dir():
        return {"id": "firecrawl", "state": "stopped", "reachable": False, "detail": "Stack is stopped"}
    return {"id": "firecrawl", "state": "unavailable", "reachable": False, "detail": "Stack is not configured"}


def _nine_router_executable() -> Path | None:
    raw = shutil.which("9router")
    if not raw:
        return None
    path = Path(raw).resolve()
    # Avoid turning a PATH entry controlled by an arbitrary browser request
    # into a persistent systemd command. The supported local install locations
    # are the current user's home and their Windows npm bridge.
    allowed_roots = (Path.home().resolve(), Path("/mnt/c/Users/Z014/AppData/Roaming/npm"))
    try:
        if any(path.is_relative_to(root) for root in allowed_roots):
            return path
    except ValueError:
        pass
    return None


def _nine_router_node_path() -> Path | None:
    raw = shutil.which("node")
    if not raw:
        return None
    path = Path(raw).resolve()
    try:
        if path.is_relative_to(Path.home().resolve()):
            return path
    except ValueError:
        pass
    return None


def _nine_router_unit_content(executable: Path) -> str:
    node = _nine_router_node_path()
    if node is None:
        raise RuntimeError("9router requires a local Node.js runtime")
    path = f"{node.parent}:{_SYSTEMD_BASE_PATH}"
    return (
        "# Managed by Hermes WebUI\n"
        "[Unit]\nDescription=9router local gateway\n\n"
        "[Service]\nType=simple\n"
        f"Environment=PATH={path}\n"
        f"ExecStart={executable} --host 127.0.0.1 --no-browser --tray\n"
        "Restart=on-failure\nRestartSec=3\n\n"
        "[Install]\nWantedBy=default.target\n"
    )


def _enable_9router_usage_cli_access(middleware_path: Path) -> bool:
    """Grant 9router's existing CLI token access to usage routes only.

    The gateway remains loopback-bound and the patch deliberately targets the
    middleware's existing ``aL`` CLI-only list.  It never opens the dashboard,
    model routes, or provider credentials to Hermes.
    """
    source = middleware_path.read_text(encoding="utf-8")
    if _NINE_ROUTER_USAGE_ROUTE in source:
        return False
    if _NINE_ROUTER_PREVIOUS_USAGE_ROUTE in source:
        temporary_path = middleware_path.with_suffix(".tmp")
        temporary_path.write_text(
            source.replace(_NINE_ROUTER_PREVIOUS_USAGE_ROUTE, _NINE_ROUTER_USAGE_ROUTE, 1),
            encoding="utf-8",
        )
        temporary_path.replace(middleware_path)
        return True
    marker = 'aL=["/api/shutdown",'
    if source.count(marker) != 1:
        raise RuntimeError("9router usage bridge could not verify its middleware target")
    updated = source.replace(marker, _NINE_ROUTER_USAGE_ROUTE, 1)
    temporary_path = middleware_path.with_suffix(".tmp")
    temporary_path.write_text(updated, encoding="utf-8")
    temporary_path.replace(middleware_path)
    return True


def _ensure_9router_usage_bridge(executable: Path) -> None:
    middleware = executable.parent / "node_modules" / "9router" / "app" / ".next-cli-build" / "server" / "middleware.js"
    if not middleware.is_file():
        raise RuntimeError("9router usage bridge is unavailable for this installation")
    _enable_9router_usage_cli_access(middleware)


def _nine_router_status() -> dict[str, Any]:
    reachable = _http_reachable("127.0.0.1", _NINE_ROUTER_PORT)
    if reachable:
        return {"id": "9router", "state": "running", "reachable": True, "detail": "Gateway reachable"}
    if _nine_router_executable() is not None:
        return {"id": "9router", "state": "stopped", "reachable": False, "detail": "Installed but not running"}
    return {"id": "9router", "state": "unavailable", "reachable": False, "detail": "Not installed"}


def managed_services_status() -> dict[str, list[dict[str, Any]]]:
    """Return only safe, UI-ready service state. No paths, output, or secrets."""
    return {"services": [_firecrawl_status(), _nine_router_status()]}


def _ensure_9router_unit() -> None:
    executable = _nine_router_executable()
    if executable is None:
        raise RuntimeError("9router is not installed")
    _ensure_9router_usage_bridge(executable)
    unit_path = Path.home() / ".config" / "systemd" / "user" / _NINE_ROUTER_UNIT
    content = _nine_router_unit_content(executable)
    should_reload = False
    if unit_path.exists():
        existing = unit_path.read_text(encoding="utf-8", errors="replace")
        if "Managed by Hermes WebUI" not in existing:
            return
        if existing != content:
            unit_path.write_text(content, encoding="utf-8")
            should_reload = True
    else:
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        unit_path.write_text(content, encoding="utf-8")
        should_reload = True
    if should_reload:
        _run(["systemctl", "--user", "daemon-reload"])


def _control_firecrawl(action: str) -> None:
    files = _firecrawl_compose_files()
    command = ["docker", "compose", "-p", _FIRECRAWL_PROJECT]
    for file in files:
        command.extend(["-f", str(file)])
    if action == "start":
        command.extend(["up", "-d"])
    else:
        command.append(action)
    result = _run(command, timeout=90.0)
    if result.returncode:
        raise RuntimeError(f"Firecrawl {action} failed")


def _control_9router(action: str) -> None:
    _ensure_9router_unit()
    command = ["systemctl", "--user", action, _NINE_ROUTER_UNIT]
    if action == "start":
        command = ["systemctl", "--user", "enable", "--now", _NINE_ROUTER_UNIT]
    result = _run(command, timeout=45.0)
    if result.returncode:
        raise RuntimeError(f"9router {action} failed")


def control_managed_service(service: str, action: str) -> dict[str, Any]:
    """Run one lifecycle action for a fixed local target."""
    if service not in _VALID_SERVICES:
        raise ValueError("Unknown managed service")
    if action not in _VALID_ACTIONS:
        raise ValueError("Unsupported managed-service action")
    if not _ACTION_LOCK.acquire(blocking=False):
        raise RuntimeError("Another service action is already in progress")
    try:
        if service == "firecrawl":
            _control_firecrawl(action)
        else:
            _control_9router(action)
        status = _firecrawl_status() if service == "firecrawl" else _nine_router_status()
        return {"ok": True, "service": service, "action": action, "status": status}
    finally:
        _ACTION_LOCK.release()
