"""Provider-neutral account-usage snapshots for WebUI-only providers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import httpx


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
