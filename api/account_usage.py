"""Provider-neutral account-usage snapshots for WebUI-only providers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen

try:  # httpx ships with the agent, not the WebUI: optional here, so the usage
    import httpx  # endpoint (and every page that polls it) works without it.
except ImportError:  # pragma: no cover - depends on the environment
    httpx = None


_NINE_ROUTER_CLI_SECRET = Path.home() / ".9router" / "auth" / "cli-secret"
_NINE_ROUTER_MACHINE_ID = Path.home() / ".9router" / "machine-id"
_NINE_ROUTER_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class AccountUsageWindow:
    label: str
    used_percent: float | None = None
    reset_at: datetime | None = None
    detail: str | None = None


@dataclass(frozen=True)
class AccountUsageSnapshot:
    provider: str
    windows: tuple[AccountUsageWindow, ...] = ()
    plan: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.windows)


class NeuralWattQuotaRateLimited(Exception):
    """The quota endpoint temporarily rejected a refresh with HTTP 429."""


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _weekly_quota(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Find the documented quota payload's weekly allowance without guessing.

    The quota API has used both ``limits`` and ``quota`` containers.  Keep the
    lookup deliberately narrow: unrelated monetary balances must never be
    misrepresented as a weekly allowance.
    """
    key = payload.get("key")
    allowance = key.get("allowance") if isinstance(key, dict) else None
    if isinstance(allowance, dict) and str(allowance.get("period") or "").lower() == "weekly":
        return allowance
    for container_name in ("limits", "quota", "allowances"):
        container = payload.get(container_name)
        if isinstance(container, dict):
            weekly = container.get("weekly")
            if isinstance(weekly, dict):
                return weekly
    return None


def neuralwatt_quota_snapshot(payload: object) -> AccountUsageSnapshot | None:
    """Convert a NeuralWatt ``/v1/quota`` response to the shared shape.

    Energy subscriptions are preferred because their allowance is the actual
    NeuralWatt billing unit.  Per-key dollar allowances remain a compatibility
    fallback for accounts without an energy subscription.
    """
    if not isinstance(payload, dict):
        return None

    subscription = payload.get("subscription")
    if isinstance(subscription, dict):
        included = _number(subscription.get("kwh_included"))
        used = _number(subscription.get("kwh_used"))
        remaining = _number(subscription.get("kwh_remaining"))
        if included is not None and included > 0 and (used is not None or remaining is not None):
            if used is None:
                used = max(0.0, included - (remaining or 0.0))
            if remaining is None:
                remaining = max(0.0, included - used)
            used = max(0.0, min(included, used))
            remaining = max(0.0, min(included, remaining))
            plan = str(subscription.get("plan") or "").strip() or None
            if plan and plan.lower() == "basic":
                plan = "Basic Plan"
            return AccountUsageSnapshot(
                provider="neuralwatt",
                plan=plan,
                windows=(AccountUsageWindow(
                    label="Energy",
                    used_percent=used / included * 100.0,
                    reset_at=_parse_datetime(subscription.get("current_period_end")),
                    detail=None,
                ),),
            )

    weekly = _weekly_quota(payload)
    if weekly is None:
        return None

    allowance = next((_number(weekly.get(key)) for key in ("limit_usd", "limit", "allowance", "total", "maximum")
                      if _number(weekly.get(key)) is not None), None)
    if allowance is None or allowance <= 0:
        return None
    used = next((_number(weekly.get(key)) for key in ("spent_usd", "used", "usage", "consumed")
                 if _number(weekly.get(key)) is not None), None)
    if used is None:
        remaining = next((_number(weekly.get(key)) for key in ("remaining_usd", "remaining", "available", "left")
                          if _number(weekly.get(key)) is not None), None)
        if remaining is None:
            return None
        used = allowance - remaining
    used_percent = max(0.0, min(100.0, used / allowance * 100.0))
    return AccountUsageSnapshot(
        provider="neuralwatt",
        windows=(AccountUsageWindow(label="Weekly", used_percent=used_percent),),
    )


def fetch_neuralwatt_account_usage(base_url: str, api_key: str) -> AccountUsageSnapshot | None:
    """Fetch a NeuralWatt quota snapshot.  Errors stay private and fail closed."""
    quota_base_url = str(base_url or "").strip().rstrip("/") or "https://api.neuralwatt.com/v1"
    endpoint = f"{quota_base_url}/quota"
    if not endpoint.startswith(("https://", "http://")) or not api_key:
        return None
    try:
        request = Request(endpoint, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
        with urlopen(request, timeout=8) as response:
            return neuralwatt_quota_snapshot(json.load(response))
    except HTTPError as exc:
        if exc.code == 429:
            raise NeuralWattQuotaRateLimited() from exc
        return None
    except Exception:
        return None


def _nine_router_dashboard_url(base_url: str) -> str | None:
    """Return a loopback 9router dashboard origin for a configured API URL."""
    try:
        parsed = urlparse(str(base_url or "").strip())
        host = (parsed.hostname or "").lower()
    except ValueError:
        return None
    if parsed.scheme != "http" or host not in _NINE_ROUTER_LOOPBACK_HOSTS:
        return None
    if parsed.port != 20128:
        return None
    return f"http://{host}:20128"


def _nine_router_usage_percent(quota: dict[str, Any]) -> float | None:
    remaining = _number(quota.get("remaining"))
    if remaining is None:
        remaining = _number(quota.get("remainingPercentage"))
    if remaining is not None:
        return max(0.0, min(100.0, 100.0 - remaining))
    total = _number(quota.get("total"))
    used = _number(quota.get("used"))
    if total is None or total <= 0 or used is None:
        return None
    return max(0.0, min(100.0, used / total * 100.0))


def _nine_router_claude_usage_snapshot(payload: object) -> AccountUsageSnapshot | None:
    """Convert 9router's Claude Code quota shape to sidebar usage windows."""
    if not isinstance(payload, dict) or not isinstance(payload.get("quotas"), dict):
        return None
    labels = (
        ("five_hour", "5 hours"),
        ("session (5h)", "5 hours"),
        ("seven_day", "Weekly"),
        ("weekly (7d)", "Weekly"),
        ("seven_day_overage_included", "Weekly"),
        ("seven_day_opus", "Opus weekly"),
        ("seven_day_sonnet", "Sonnet weekly"),
    )
    windows: list[AccountUsageWindow] = []
    seen_labels: set[str] = set()
    for key, label in labels:
        quota = payload["quotas"].get(key)
        if not isinstance(quota, dict) or label in seen_labels:
            continue
        used_percent = _nine_router_usage_percent(quota)
        if used_percent is None:
            continue
        windows.append(AccountUsageWindow(
            label=label,
            used_percent=used_percent,
            reset_at=_parse_datetime(quota.get("resetAt") or quota.get("reset_at")),
        ))
        seen_labels.add(label)
    if not windows:
        return None
    return AccountUsageSnapshot(
        provider="9router-claude",
        windows=tuple(windows),
        plan="Claude via 9router",
    )


def fetch_9router_claude_account_usage(base_url: str) -> AccountUsageSnapshot | None:
    """Fetch Claude Code limits from a local 9router instance.

    9router's normal API key only authorizes model requests. Its local CLI
    token is intentionally scoped by the managed gateway to read-only usage
    routes, so no Claude OAuth credential or dashboard session is copied into
    Hermes.
    """
    dashboard_url = _nine_router_dashboard_url(base_url)
    if dashboard_url is None:
        return None
    try:
        cli_secret = _NINE_ROUTER_CLI_SECRET.read_text(encoding="utf-8").strip()
        machine_id = _NINE_ROUTER_MACHINE_ID.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not cli_secret or not machine_id:
        return None
    cli_token = hashlib.sha256(
        f"{machine_id}9r-cli-auth{cli_secret}".encode("utf-8")
    ).hexdigest()[:16]
    headers = {"X-9r-cli-token": cli_token, "Accept": "application/json"}
    try:
        request = Request(
            f"{dashboard_url}/api/providers/client?page=1&pageSize=100&accountStatus=active&sort=priority",
            headers=headers,
        )
        with urlopen(request, timeout=8) as response:
            providers = json.load(response)
        connections = providers.get("connections") if isinstance(providers, dict) else None
        if not isinstance(connections, list):
            return None
        connection_id = next((
            str(connection.get("id") or "").strip()
            for connection in connections
            if isinstance(connection, dict)
            and str(connection.get("provider") or "").strip().lower() == "claude"
            and connection.get("isActive") is not False
            and str(connection.get("id") or "").strip()
        ), "")
        if not connection_id:
            return None
        request = Request(
            f"{dashboard_url}/api/usage/{connection_id}", headers=headers,
        )
        with urlopen(request, timeout=8) as response:
            return _nine_router_claude_usage_snapshot(json.load(response))
    except Exception:
        return None


def _parse_datetime(value: object) -> datetime | None:
    numeric = _number(value)
    if numeric is not None:
        # Rate-limit APIs commonly return Unix seconds, while some return
        # JavaScript-style milliseconds. Normalize both before serializing the
        # sidebar's human-readable "resets in" line.
        if numeric > 10_000_000_000:
            numeric /= 1000
        try:
            return datetime.fromtimestamp(numeric, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def fetch_codex_cli_account_usage(tokens: object) -> AccountUsageSnapshot | None:
    """Fetch Codex limits using the desktop app's token *and account ID*.

    The account ID is required to keep a multi-account desktop login aligned
    with the account selected in Codex itself.
    """
    if not isinstance(tokens, dict):
        return None
    access_token = str(tokens.get("access_token") or "").strip()
    account_id = str(tokens.get("account_id") or "").strip()
    if not access_token:
        return None
    try:
        headers = {
            "Authorization": f"Bearer {access_token}", "Accept": "application/json", "User-Agent": "codex-cli",
        }
        if account_id:
            headers["ChatGPT-Account-Id"] = account_id
        if httpx is None:
            return None
        with httpx.Client(timeout=15) as client:
            response = client.get("https://chatgpt.com/backend-api/wham/usage", headers=headers)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return None
    rate_limit = payload.get("rate_limit") if isinstance(payload, dict) else None
    if not isinstance(rate_limit, dict):
        return None
    windows = []
    for key, label in (("primary_window", "Session"), ("secondary_window", "Weekly")):
        raw = rate_limit.get(key)
        if not isinstance(raw, dict) or _number(raw.get("used_percent")) is None:
            continue
        windows.append(AccountUsageWindow(
            label=label,
            used_percent=max(0.0, min(100.0, _number(raw.get("used_percent")) or 0.0)),
            reset_at=_parse_datetime(raw.get("reset_at")),
        ))
    return AccountUsageSnapshot(provider="openai-codex", windows=tuple(windows)) if windows else None
