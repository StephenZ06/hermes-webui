"""Gmail adapter. Message content is untrusted data: it is returned to the
caller and never read for instructions here.

The compose scope can send, so "drafts only" is enforced by the capability
policy in service.py, not by the scope.
"""

from __future__ import annotations

import base64
import urllib.parse
from email.message import EmailMessage
from typing import Any

from api.business_office import http_client, oauth
from api.business_office.errors import ToolError

_API = "https://gmail.googleapis.com/gmail/v1/users/me"
_MAX_BODY = 20_000
_HEADERS = ("From", "To", "Cc", "Subject", "Date")


def _id(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def _headers(payload: dict[str, Any]) -> dict[str, str]:
    found = {}
    for header in payload.get("headers") or []:
        if header.get("name") in _HEADERS:
            found[header["name"].lower()] = str(header.get("value") or "")
    return found


def _decode(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
    except ValueError:
        return ""


def _text(payload: dict[str, Any]) -> str:
    if payload.get("mimeType") == "text/plain" and (payload.get("body") or {}).get("data"):
        return _decode(payload["body"]["data"])
    for part in payload.get("parts") or []:
        text = _text(part)
        if text:
            return text
    return ""


def _message(raw: dict[str, Any]) -> dict[str, Any]:
    payload = raw.get("payload") or {}
    return {"id": raw.get("id"), "thread_id": raw.get("threadId"), "snippet": raw.get("snippet", ""),
            **_headers(payload), "body": _text(payload)[:_MAX_BODY]}


def _raw_message(values: dict[str, Any]) -> str:
    message = EmailMessage()
    message["To"] = values["to"]
    message["Subject"] = values["subject"]
    message.set_content(values["body"])
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


def _draft(token: str, draft_id: str) -> dict[str, Any]:
    raw = http_client.request_json("GET", f"{_API}/drafts/{_id(draft_id)}?format=full", token=token)
    message = _message(raw.get("message") or {})
    return {"draft_id": draft_id, "to": message.get("to", ""), "cc": message.get("cc", ""),
            "subject": message.get("subject", ""), "body": message.get("body", "")}


def preview(capability_id: str, values: dict[str, Any], business_id: str) -> dict[str, Any]:
    """The exact content an approval covers: the draft as it stands, not its id."""
    if capability_id != "gmail.send_draft":
        return dict(values)
    return _draft(oauth.access_token(business_id, "gmail"), values["draft_id"])


def invoke(capability_id: str, values: dict[str, Any], business_id: str) -> dict[str, Any]:
    token = oauth.access_token(business_id, "gmail")
    if capability_id == "gmail.search_messages":
        limit = max(1, min(int(values.get("limit") or 10), 25))
        query = urllib.parse.urlencode({"q": values["query"], "maxResults": limit})
        found = http_client.request_json("GET", f"{_API}/messages?{query}", token=token)
        rows = []
        for item in found.get("messages") or []:
            raw = http_client.request_json("GET", f"{_API}/messages/{_id(item['id'])}?format=metadata", token=token)
            rows.append({key: value for key, value in _message(raw).items() if key != "body"})
        return {"messages": rows}
    if capability_id == "gmail.read_message":
        return _message(http_client.request_json("GET", f"{_API}/messages/{_id(values['message_id'])}?format=full", token=token))
    if capability_id == "gmail.get_thread":
        raw = http_client.request_json("GET", f"{_API}/threads/{_id(values['thread_id'])}?format=full", token=token)
        return {"thread_id": raw.get("id"), "messages": [_message(item) for item in raw.get("messages") or []]}
    if capability_id == "gmail.create_draft":
        message: dict[str, Any] = {"raw": _raw_message(values)}
        if values.get("thread_id"):
            message["threadId"] = values["thread_id"]
        made = http_client.request_json("POST", f"{_API}/drafts", body={"message": message}, token=token)
        return {"draft_id": made.get("id"), "message_id": (made.get("message") or {}).get("id")}
    if capability_id == "gmail.send_draft":
        sent = http_client.request_json("POST", f"{_API}/drafts/send", body={"id": values["draft_id"]}, token=token)
        return {"message_id": sent.get("id"), "thread_id": sent.get("threadId")}
    raise ToolError("denied", "Unknown Gmail capability")
