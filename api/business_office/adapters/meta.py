"""Threads and Instagram: account identity only until publishing is approved."""

from __future__ import annotations

from typing import Any

from api.business_office import http_client, oauth
from api.business_office.errors import ToolError

_PROFILE = {
    "threads.get_profile": ("threads", "https://graph.threads.com/v1.0/me?fields=id,username,name"),
    "instagram.get_profile": ("instagram", "https://graph.instagram.com/me?fields=user_id,username,account_type"),
}


def preview(capability_id: str, values: dict[str, Any], business_id: str) -> dict[str, Any]:
    return dict(values)


def invoke(capability_id: str, values: dict[str, Any], business_id: str) -> dict[str, Any]:
    if capability_id not in _PROFILE:
        raise ToolError("denied", "Unknown capability")
    provider, url = _PROFILE[capability_id]
    return http_client.request_json("GET", url, token=oauth.access_token(business_id, provider))
