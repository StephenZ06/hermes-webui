"""Safe, provider-neutral status metadata for Office integrations.

OAuth ownership and token persistence are deliberately outside this module.
This contract only tells the Office UI whether a narrow provider capability is
available; unknown data therefore always becomes a disconnected integration.
"""

from __future__ import annotations

_GMAIL_CAPABILITIES = ["search_read", "summarize", "draft_reply"]
_SAFE_STATUSES = {"disconnected", "needs_reconnect"}


def gmail_integration_metadata() -> dict:
    """Return the default Email-floor Gmail card before OAuth is configured."""
    return {
        "provider": "gmail",
        "floor": "emails",
        "status": "disconnected",
        "capabilities": list(_GMAIL_CAPABILITIES),
        "send_requires_approval": True,
    }


def safe_integration_metadata(raw: object) -> dict:
    """Validate persisted/provider input without ever returning credentials.

    A connected state has no meaning until an OAuth implementation can prove
    it. Treat it as disconnected for now rather than giving the Email floor
    permission based on unverified metadata.
    """
    default = gmail_integration_metadata()
    if not isinstance(raw, dict):
        return default
    if raw.get("provider") != "gmail" or raw.get("floor") != "emails":
        return default
    if raw.get("status") not in _SAFE_STATUSES:
        return default
    safe = dict(default)
    safe["status"] = raw["status"]
    return safe


def list_office_integrations() -> dict:
    """Return public, non-secret integration status for the Office UI."""
    return {"integrations": [gmail_integration_metadata()]}
