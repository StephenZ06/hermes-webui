"""OAuth sign-in for Google, Threads and Instagram.

Every business signs in separately, so the same provider on two businesses
holds two independent token sets. Provider specifics live in :data:`APPS`;
endpoints were read from provider documentation on 2026-11-04.

The ``state`` value is random, single use, expires after ten minutes, and is
tied to the WebUI session that started the sign-in. The business a callback
writes to comes from that stored row, never from the callback URL.
"""

from __future__ import annotations

import hashlib
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Callable

from api.business_office import crypto, http_client, registry, store
from api.business_office.errors import ToolError

CALLBACK_PATH = "/api/office/business/oauth/callback"
_REFRESH_MARGIN = 120
_META_REFRESH_WINDOW = 7 * 86_400


@dataclass(frozen=True)
class App:
    id: str
    label: str
    console_url: str
    authorize_url: str
    scopes: tuple[str, ...]
    scope_separator: str = " "
    extra_params: tuple[tuple[str, str], ...] = ()


APPS: dict[str, App] = {
    "google": App("google", "Google", "https://console.cloud.google.com/apis/credentials",
                  "https://accounts.google.com/o/oauth2/v2/auth",
                  (registry.GMAIL_READ, registry.GMAIL_COMPOSE),
                  extra_params=(("access_type", "offline"), ("prompt", "consent"), ("include_granted_scopes", "false"))),
    "threads": App("threads", "Threads", "https://developers.facebook.com/apps/",
                   "https://threads.com/oauth/authorize", ("threads_basic",), ","),
    "instagram": App("instagram", "Instagram", "https://developers.facebook.com/apps/",
                     "https://www.instagram.com/oauth/authorize", ("instagram_business_basic",), ","),
}


def app_for(provider_id: str) -> App:
    provider = registry.provider(provider_id)
    if provider is None or provider.auth != "oauth" or provider.state != "adapter":
        raise store.StoreError("This provider has no sign-in yet", 404)
    return APPS[provider.oauth_app]


def session_hash(cookie_value: str) -> str:
    return hashlib.sha256(str(cookie_value or "").encode("utf-8")).hexdigest()


def redirect_uri(base_url: str) -> str:
    return base_url.rstrip("/") + CALLBACK_PATH


def start(business_id: str, provider_id: str, base_url: str, cookie_value: str) -> str:
    store.get_business(business_id)
    app = app_for(provider_id)
    credentials = store.oauth_app(app.id)
    if credentials is None:
        raise store.StoreError(f"Add your {app.label} client ID and secret first", 409)
    state = secrets.token_urlsafe(32)
    uri = redirect_uri(base_url)
    store.save_oauth_state(state, business_id, provider_id, uri, session_hash(cookie_value))
    params = {"client_id": credentials[0], "redirect_uri": uri, "response_type": "code",
              "scope": app.scope_separator.join(app.scopes), "state": state, **dict(app.extra_params)}
    store.audit(business_id, actor="user", decision="oauth_started", provider=provider_id)
    return f"{app.authorize_url}?{urllib.parse.urlencode(params)}"


def _google(code: str, uri: str, credentials: tuple[str, str]) -> dict[str, Any]:
    client_id, secret = credentials
    tokens = http_client.request_json("POST", "https://oauth2.googleapis.com/token", form={
        "client_id": client_id, "client_secret": secret, "code": code, "grant_type": "authorization_code", "redirect_uri": uri})
    access = str(tokens.get("access_token") or "")
    if not access or not tokens.get("refresh_token"):
        raise ToolError("rejected", "Google did not return offline access. Sign in again and approve every permission.")
    profile = http_client.request_json("GET", "https://gmail.googleapis.com/gmail/v1/users/me/profile", token=access)
    email = str(profile.get("emailAddress") or "")
    return {"tokens": {"access_token": access, "refresh_token": tokens["refresh_token"]},
            "expires_at": time.time() + float(tokens.get("expires_in") or 3600),
            "scopes": str(tokens.get("scope") or "").split(), "account_id": email, "account_label": email}


def _threads(code: str, uri: str, credentials: tuple[str, str]) -> dict[str, Any]:
    client_id, secret = credentials
    short = http_client.request_json("POST", "https://graph.threads.com/oauth/access_token", form={
        "client_id": client_id, "client_secret": secret, "code": code, "grant_type": "authorization_code", "redirect_uri": uri})
    query = urllib.parse.urlencode({"grant_type": "th_exchange_token", "client_secret": secret, "access_token": short.get("access_token", "")})
    long_lived = http_client.request_json("GET", f"https://graph.threads.com/access_token?{query}")
    access = str(long_lived.get("access_token") or "")
    profile = http_client.request_json("GET", "https://graph.threads.com/v1.0/me?fields=id,username", token=access)
    return {"tokens": {"access_token": access}, "expires_at": time.time() + float(long_lived.get("expires_in") or 0),
            "scopes": list(APPS["threads"].scopes), "account_id": str(profile.get("id") or ""),
            "account_label": f"@{profile.get('username')}" if profile.get("username") else ""}


def _instagram(code: str, uri: str, credentials: tuple[str, str]) -> dict[str, Any]:
    client_id, secret = credentials
    short = http_client.request_json("POST", "https://api.instagram.com/oauth/access_token", form={
        "client_id": client_id, "client_secret": secret, "code": code, "grant_type": "authorization_code", "redirect_uri": uri})
    query = urllib.parse.urlencode({"grant_type": "ig_exchange_token", "client_secret": secret, "access_token": short.get("access_token", "")})
    long_lived = http_client.request_json("GET", f"https://graph.instagram.com/access_token?{query}")
    access = str(long_lived.get("access_token") or "")
    profile = http_client.request_json("GET", "https://graph.instagram.com/me?fields=user_id,username", token=access)
    return {"tokens": {"access_token": access}, "expires_at": time.time() + float(long_lived.get("expires_in") or 0),
            "scopes": list(APPS["instagram"].scopes), "account_id": str(profile.get("user_id") or ""),
            "account_label": f"@{profile.get('username')}" if profile.get("username") else ""}


_EXCHANGE: dict[str, Callable[[str, str, tuple[str, str]], dict[str, Any]]] = {
    "google": _google, "threads": _threads, "instagram": _instagram,
}


def finish(state: str, code: str, cookie_value: str) -> dict[str, Any]:
    """Complete a sign-in. Returns the row's business and provider for the redirect."""
    row = store.take_oauth_state(state)
    if row is None or not secrets.compare_digest(row["session_hash"], session_hash(cookie_value)):
        raise store.StoreError("This sign-in link expired. Start again from Integrations.", 400)
    business_id, provider_id = row["business_id"], row["provider"]
    app = app_for(provider_id)
    credentials = store.oauth_app(app.id)
    if credentials is None:
        raise store.StoreError("The app credentials were removed. Add them and try again.", 409)
    # Meta appends "#_" to the code; it is not part of it.
    clean_code = code[:-2] if code.endswith("#_") else code
    try:
        signed_in = _EXCHANGE[app.id](clean_code, row["redirect_uri"], credentials)
    except ToolError as error:
        store.audit(business_id, actor="user", decision="oauth_finished", provider=provider_id, outcome="failed", detail=error.kind)
        raise
    granted = set(signed_in["scopes"])
    missing = [scope for scope in app.scopes if scope not in granted]
    store.save_connection(business_id, provider_id, tokens=signed_in["tokens"], account_id=signed_in["account_id"],
                          account_label=signed_in["account_label"], scopes=signed_in["scopes"],
                          expires_at=signed_in["expires_at"], status="degraded" if missing else "connected")
    store.audit(business_id, actor="user", decision="oauth_finished", provider=provider_id,
                target=signed_in["account_label"], outcome="degraded" if missing else "ok")
    return {"business_id": business_id, "provider": provider_id}


def _refresh_google(business_id: str, provider_id: str, tokens: dict[str, Any]) -> str:
    credentials = store.oauth_app("google")
    if credentials is None:
        raise ToolError("auth_expired", "The Google app credentials were removed")
    try:
        fresh = http_client.request_json("POST", "https://oauth2.googleapis.com/token", form={
            "client_id": credentials[0], "client_secret": credentials[1],
            "refresh_token": tokens.get("refresh_token", ""), "grant_type": "refresh_token"})
    except ToolError as error:
        if error.kind in ("rejected", "auth_expired"):
            raise ToolError("auth_expired", "Google ended this sign-in. Connect the account again.") from None
        raise
    access = str(fresh.get("access_token") or "")
    store.update_tokens(business_id, provider_id, {**tokens, "access_token": access},
                        time.time() + float(fresh.get("expires_in") or 3600))
    return access


def _refresh_meta(business_id: str, provider_id: str, tokens: dict[str, Any]) -> str:
    host, grant = (("graph.threads.com", "th_refresh_token") if provider_id == "threads"
                   else ("graph.instagram.com", "ig_refresh_token"))
    query = urllib.parse.urlencode({"grant_type": grant, "access_token": tokens.get("access_token", "")})
    fresh = http_client.request_json("GET", f"https://{host}/refresh_access_token?{query}")
    access = str(fresh.get("access_token") or "")
    store.update_tokens(business_id, provider_id, {"access_token": access}, time.time() + float(fresh.get("expires_in") or 0))
    return access


def access_token(business_id: str, provider_id: str) -> str:
    """A usable token, refreshed if needed. Failures mark the connection."""
    connection = store.get_connection(business_id, provider_id)
    if connection is None:
        raise ToolError("not_connected", "This account is not connected")
    try:
        tokens = store.connection_tokens(business_id, provider_id)
    except crypto.SecretError:
        store.mark_connection(business_id, provider_id, "unauthorized", "Stored credentials could not be read")
        raise ToolError("auth_expired", "Stored credentials could not be read. Connect the account again.") from None
    left = connection["expires_at"] - time.time()
    if provider_id == "gmail":
        if left > _REFRESH_MARGIN:
            return str(tokens["access_token"])
        refresh = _refresh_google
    else:
        if left <= 0:
            store.mark_connection(business_id, provider_id, "unauthorized", "Sign-in expired")
            raise ToolError("auth_expired", "This sign-in expired. Connect the account again.")
        if left > _META_REFRESH_WINDOW:
            return str(tokens["access_token"])
        refresh = _refresh_meta
    try:
        return refresh(business_id, provider_id, tokens)
    except ToolError as error:
        if error.kind == "auth_expired":
            store.mark_connection(business_id, provider_id, "unauthorized", str(error))
        raise


def disconnect(business_id: str, provider_id: str) -> None:
    """Forget the account. Google is asked to revoke it; a failure is recorded, not hidden."""
    outcome = "ok"
    if provider_id == "gmail":
        try:
            tokens = store.connection_tokens(business_id, provider_id)
            http_client.request_json("POST", "https://oauth2.googleapis.com/revoke",
                                     form={"token": tokens.get("refresh_token", "")}, allow_empty=True)
        except (ToolError, crypto.SecretError):
            outcome = "revoke_failed"
    store.delete_connection(business_id, provider_id)
    store.audit(business_id, actor="user", decision="disconnected", provider=provider_id, outcome=outcome)
