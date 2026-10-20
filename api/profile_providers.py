"""Per-profile provider setup for the Profiles page.

Every Hermes profile keeps its own ``config.yaml`` (main model, custom
endpoints, fallback chain), ``.env`` (API keys) and ``auth.json`` (OAuth
sign-ins). The Settings provider panel only edits the *active* profile, so a
profile like ``docs-gits`` could be left without credentials and fail at run
time. This module reads and writes one named profile's files directly, without
switching profiles and without leaking one profile's keys into the server
process environment (only the root profile's keys live there).

Secrets are write-only through this API: responses say whether a key is set,
never what it is.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

# Sign-ins the WebUI can run itself (see api/oauth.py). Other OAuth providers
# still need the CLI, and the card says so.
WEB_SIGNIN = {"openai-codex": "OpenAI Codex", "anthropic": "Claude"}
CLI_SIGNIN = {"nous": "Nous Portal", "copilot": "GitHub Copilot", "xai-oauth": "xAI Grok OAuth"}

# Ready-made OpenAI-compatible endpoints. ``dashboard`` is opened by the
# "Open dashboard" button so the router can be configured in its own UI.
ENDPOINT_PRESETS = [
    {"id": "9router", "name": "9Router", "base_url": "http://localhost:20128/v1",
     "dashboard": "http://localhost:20128/dashboard", "needs_key": True,
     "hint": "Open the 9Router dashboard, connect your accounts, then copy its API key here."},
    {"id": "lmstudio", "name": "LM Studio", "base_url": "http://localhost:1234/v1", "needs_key": False,
     "hint": "Start LM Studio's local server and load a model."},
    {"id": "ollama", "name": "Ollama", "base_url": "http://localhost:11434/v1", "needs_key": False,
     "hint": "Run `ollama serve` and pull a model."},
    {"id": "custom", "name": "Other OpenAI-compatible", "base_url": "", "needs_key": True,
     "hint": "Any endpoint that speaks the OpenAI chat-completions API."},
]

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


class ProfileProviderError(ValueError):
    """Rejected request (bad profile, provider, URL, or value)."""


# ── locating a profile's files ──────────────────────────────────────────────

def profile_home(name: str) -> Path:
    """Home of an existing profile; never falls back to another profile."""
    from api.oauth import _oauth_target_home

    try:
        return _oauth_target_home({"profile": name or "default"})
    except ValueError as exc:
        raise ProfileProviderError(str(exc)) from exc


def _is_root_home(home: Path) -> bool:
    from api import profiles

    return Path(home).resolve() == Path(profiles._DEFAULT_HERMES_HOME).resolve()


def _read_config(home: Path) -> dict:
    path = home / "config.yaml"
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _write_config(home: Path, cfg: dict) -> None:
    from api.config import _save_yaml_config_file, invalidate_models_cache

    _save_yaml_config_file(home / "config.yaml", cfg)
    try:
        invalidate_models_cache()
    except Exception:
        pass


def _read_env(home: Path) -> dict[str, str]:
    path = home / ".env"
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip().removeprefix("export ").strip()
        values[key] = value.strip().strip('"').strip("'")
    return values


def _write_env(home: Path, updates: dict[str, str | None]) -> None:
    """Set/remove keys in one profile's .env, atomically, mode 0600.

    Unlike providers._write_env_file this never touches os.environ for a
    non-root profile, so one profile's keys cannot leak into another's runs.
    """
    from api.streaming import _ENV_LOCK

    for key in updates:
        if not _ENV_KEY_RE.fullmatch(key):
            raise ProfileProviderError(f"Invalid environment variable name: {key}")
    path = home / ".env"
    with _ENV_LOCK:
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        remaining = dict(updates)
        out: list[str] = []
        for line in lines:
            stripped = line.strip()
            key = stripped.partition("=")[0].strip().removeprefix("export ").strip() if "=" in stripped else ""
            if key in remaining:
                value = remaining.pop(key)
                if value is not None:
                    out.append(f"{key}={value}")
                continue
            out.append(line)
        new = [f"{k}={v}" for k, v in remaining.items() if v is not None]
        if new:
            if out and out[-1].strip():
                out.append("")
            out.extend(new)
        home.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(home), prefix=".env.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write("\n".join(out) + ("\n" if out else ""))
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        if _is_root_home(home):
            for key, value in updates.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


# ── catalog ────────────────────────────────────────────────────────────────

def api_key_providers() -> list[dict]:
    """Built-in providers that authenticate with a single API key."""
    from api.config import _PROVIDER_DISPLAY
    from api.providers import _provider_env_var_for

    rows = []
    for pid, label in _PROVIDER_DISPLAY.items():
        env_var = _provider_env_var_for(pid)
        if env_var and pid != "openai-codex":  # Anthropic takes a key or a Claude sign-in
            rows.append({"id": pid, "label": label, "env_var": env_var})
    return rows


def _env_var_for(provider: str) -> str | None:
    return next((p["env_var"] for p in api_key_providers() if p["id"] == provider), None)


def _custom_slug(value: str) -> str:
    slug = _SLUG_RE.sub("-", str(value or "").strip().lower()).strip("-")[:40]
    if not slug:
        raise ProfileProviderError("Give the endpoint a name.")
    return slug


def _endpoints(cfg: dict) -> dict[str, dict]:
    providers = cfg.get("providers")
    return providers if isinstance(providers, dict) else {}


def _endpoint_url(entry: dict) -> str:
    return str(entry.get("base_url") or entry.get("api") or entry.get("url") or "").strip()


# ── status ─────────────────────────────────────────────────────────────────

def _route_status(home: Path, cfg: dict, env: dict, provider: str, base_url: str = "") -> dict:
    """Whether a provider route has what it needs to start (no network)."""
    provider = str(provider or "").strip()
    if not provider:
        return {"state": "unset", "message": "No main model chosen."}
    if provider in WEB_SIGNIN:
        env_var = _env_var_for(provider)
        if env_var and (env.get(env_var) or (_is_root_home(home) and os.environ.get(env_var))):
            return {"state": "ready", "message": f"API key saved ({env_var})."}
        if _signed_in(home, provider):
            return {"state": "ready", "message": f"Signed in to {WEB_SIGNIN[provider]}."}
        return {"state": "signin", "message": f"Sign in to {WEB_SIGNIN[provider]}."}
    if provider in CLI_SIGNIN:
        return {"state": "cli", "message": f"{CLI_SIGNIN[provider]} sign-in is done with the Hermes CLI."}
    endpoints = _endpoints(cfg)
    slug = provider.split(":", 1)[1] if provider.startswith("custom:") else provider
    if slug in endpoints and isinstance(endpoints[slug], dict):
        entry = endpoints[slug]
        if not _endpoint_url(entry):
            return {"state": "key", "message": "This endpoint has no URL."}
        return {"state": "ready", "message": f"Uses {entry.get('name') or slug} at {_endpoint_url(entry)}."}
    env_var = _env_var_for(provider)
    if env_var:
        if env.get(env_var) or (_is_root_home(home) and os.environ.get(env_var)):
            return {"state": "ready", "message": f"API key saved ({env_var})."}
        return {"state": "key", "message": f"Add an API key for this provider ({env_var})."}
    if base_url:
        return {"state": "ready", "message": f"Uses {base_url}."}
    return {"state": "unknown", "message": "Hermes can't check this provider from here."}


def overview(name: str) -> dict:
    home = profile_home(name)
    cfg = _read_config(home)
    env = _read_env(home)
    model = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
    main = {
        "provider": str(model.get("provider") or ""),
        "model": str(model.get("default") or ""),
        "base_url": str(model.get("base_url") or ""),
    }
    main["status"] = _route_status(home, cfg, env, main["provider"], main["base_url"])
    keys = []
    for row in api_key_providers():
        has = bool(env.get(row["env_var"]) or (_is_root_home(home) and os.environ.get(row["env_var"])))
        keys.append({**row, "has_key": has})
    endpoints = []
    for slug, entry in _endpoints(cfg).items():
        if not isinstance(entry, dict):
            continue
        endpoints.append({
            "id": slug,
            "provider": slug if slug in {"lmstudio", "ollama"} else f"custom:{slug}",
            "name": str(entry.get("name") or slug),
            "base_url": _endpoint_url(entry),
            "model": str(entry.get("default_model") or entry.get("model") or ""),
            "has_key": bool(entry.get("api_key") or entry.get("key_env")),
        })
    fallbacks = []
    for item in cfg.get("fallback_providers") or []:
        if isinstance(item, dict) and item.get("provider") and item.get("model"):
            fb = {"provider": str(item["provider"]), "model": str(item["model"]), "base_url": str(item.get("base_url") or "")}
            fb["status"] = _route_status(home, cfg, env, fb["provider"], fb["base_url"])
            fallbacks.append(fb)
    signins = [{"id": pid, "label": label, "signed_in": _signed_in(home, pid)} for pid, label in WEB_SIGNIN.items()]
    return {
        "profile": name or "default",
        "main": main,
        "signins": signins,
        "api_keys": keys,
        "endpoints": endpoints,
        "fallbacks": fallbacks,
        "presets": ENDPOINT_PRESETS,
    }


def _signed_in(home: Path, provider: str) -> bool:
    from api.oauth import _read_auth_json

    auth = _read_auth_json(home / "auth.json")
    pool = auth.get("credential_pool") if isinstance(auth.get("credential_pool"), dict) else {}
    providers = auth.get("providers") if isinstance(auth.get("providers"), dict) else {}
    entries = pool.get(provider) if isinstance(pool.get(provider), list) else []
    if provider == "anthropic" and entries:
        return True
    if any(isinstance(e, dict) and e.get("access_token") for e in entries):
        return True
    stored = providers.get(provider)
    if isinstance(stored, dict):
        tokens = stored.get("tokens") if isinstance(stored.get("tokens"), dict) else stored
        return bool(tokens.get("access_token"))
    return False


# ── writes ─────────────────────────────────────────────────────────────────

def set_api_key(name: str, provider: str, api_key: str | None) -> dict:
    home = profile_home(name)
    env_var = _env_var_for(str(provider or ""))
    if not env_var:
        raise ProfileProviderError("That provider does not use an API key.")
    value = str(api_key or "").strip() or None
    if value and ("\n" in value or len(value) > 4096):
        raise ProfileProviderError("That API key doesn't look valid.")
    _write_env(home, {env_var: value})
    return {"ok": True, "provider": provider, "has_key": bool(value)}


def _check_url(url: str) -> str:
    from urllib.parse import urlparse

    url = str(url or "").strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ProfileProviderError("The endpoint URL must start with http:// or https://")
    return url


def save_endpoint(name: str, body: dict) -> dict:
    """Add or update an OpenAI-compatible endpoint in the profile's providers."""
    home = profile_home(name)
    display = str(body.get("display") or "").strip()[:60]
    slug = _custom_slug(body.get("id") or display)
    base_url = _check_url(body.get("base_url"))
    model = str(body.get("model") or "").strip()[:200]
    cfg = _read_config(home)
    providers = cfg.get("providers") if isinstance(cfg.get("providers"), dict) else {}
    entry = dict(providers.get(slug) or {})
    entry.pop("api", None)
    entry.update({"name": display or slug, "base_url": base_url, "transport": entry.get("transport") or "chat_completions"})
    if model:
        entry["default_model"] = model
    if "api_key" in body:
        key = str(body.get("api_key") or "").strip()
        if key:
            entry["api_key"] = key
        elif body.get("clear_key"):
            entry.pop("api_key", None)
    providers[slug] = entry
    cfg["providers"] = providers
    provider_id = slug if slug in {"lmstudio", "ollama"} else f"custom:{slug}"
    if body.get("make_main"):
        if not model:
            raise ProfileProviderError("Choose a model to use this endpoint as the main model.")
        cfg["model"] = {**(cfg.get("model") if isinstance(cfg.get("model"), dict) else {}),
                        "provider": provider_id, "default": model, "base_url": base_url}
    _write_config(home, cfg)
    return {"ok": True, "id": slug, "provider": provider_id}


def delete_endpoint(name: str, slug: str) -> dict:
    home = profile_home(name)
    cfg = _read_config(home)
    providers = _endpoints(cfg)
    if slug not in providers:
        raise ProfileProviderError("No such endpoint.")
    provider_id = slug if slug in {"lmstudio", "ollama"} else f"custom:{slug}"
    main = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
    if main.get("provider") == provider_id:
        raise ProfileProviderError("This endpoint is the main model. Pick another main model first.")
    providers.pop(slug)
    cfg["providers"] = providers
    cfg["fallback_providers"] = [f for f in cfg.get("fallback_providers") or []
                                 if not (isinstance(f, dict) and f.get("provider") == provider_id)]
    _write_config(home, cfg)
    return {"ok": True}


def set_main(name: str, provider: str, model: str) -> dict:
    home = profile_home(name)
    provider = str(provider or "").strip()
    model = str(model or "").strip()
    if not provider or not model:
        raise ProfileProviderError("Choose a provider and a model.")
    cfg = _read_config(home)
    main = dict(cfg.get("model") if isinstance(cfg.get("model"), dict) else {})
    slug = provider.split(":", 1)[1] if provider.startswith("custom:") else provider
    entry = _endpoints(cfg).get(slug)
    main.update({"provider": provider, "default": model,
                 "base_url": _endpoint_url(entry) if isinstance(entry, dict) else ""})
    cfg["model"] = main
    _write_config(home, cfg)
    return {"ok": True}


def set_fallbacks(name: str, items: list) -> dict:
    """Replace the fallback chain; the agent tries these when the main route fails."""
    home = profile_home(name)
    cfg = _read_config(home)
    chain = []
    seen = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or "").strip()
        model = str(item.get("model") or "").strip()
        if not provider or not model:
            continue
        key = (provider.lower(), model.lower())
        if key in seen:
            continue
        seen.add(key)
        entry = {"provider": provider, "model": model}
        slug = provider.split(":", 1)[1] if provider.startswith("custom:") else ""
        endpoint = _endpoints(cfg).get(slug) if slug else None
        if isinstance(endpoint, dict) and _endpoint_url(endpoint):
            entry["base_url"] = _endpoint_url(endpoint)
        chain.append(entry)
        if len(chain) >= 5:
            break
    cfg["fallback_providers"] = chain
    _write_config(home, cfg)
    return {"ok": True, "count": len(chain)}


def copy_credentials(source: str, target: str, provider: str) -> dict:
    """Copy one provider's API key or endpoint from another profile.

    OAuth sign-ins are deliberately not copied: providers like OpenAI rotate
    refresh tokens, so two profiles sharing one token would sign each other
    out. Those profiles sign in separately instead.
    """
    if (source or "default") == (target or "default"):
        raise ProfileProviderError("Pick a different profile to copy from.")
    src_home, dst_home = profile_home(source), profile_home(target)
    provider = str(provider or "").strip()
    if provider == "openai-codex" or provider in CLI_SIGNIN:
        raise ProfileProviderError("Sign-ins can't be shared between profiles; sign this profile in instead.")
    env_var = _env_var_for(provider)
    if env_var:
        value = _read_env(src_home).get(env_var) or (os.environ.get(env_var) if _is_root_home(src_home) else None)
        if not value:
            raise ProfileProviderError(f"'{source}' has no API key for that provider.")
        _write_env(dst_home, {env_var: value})
        return {"ok": True, "copied": env_var}
    slug = provider.split(":", 1)[1] if provider.startswith("custom:") else provider
    entry = _endpoints(_read_config(src_home)).get(slug)
    if not isinstance(entry, dict):
        raise ProfileProviderError(f"'{source}' has no endpoint called {slug}.")
    cfg = _read_config(dst_home)
    providers = cfg.get("providers") if isinstance(cfg.get("providers"), dict) else {}
    providers[slug] = dict(entry)
    cfg["providers"] = providers
    _write_config(dst_home, cfg)
    return {"ok": True, "copied": slug}


# ── connectivity check ─────────────────────────────────────────────────────

def test_route(name: str, provider: str = "") -> dict:
    """Probe a route: endpoints get a live /models call; others a credential check."""
    home = profile_home(name)
    cfg = _read_config(home)
    env = _read_env(home)
    model = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
    provider = str(provider or model.get("provider") or "").strip()
    slug = provider.split(":", 1)[1] if provider.startswith("custom:") else provider
    entry = _endpoints(cfg).get(slug)
    if isinstance(entry, dict) and _endpoint_url(entry):
        url = _endpoint_url(entry).rstrip("/") + "/models"
        headers = {"Accept": "application/json", "User-Agent": "Hermes-WebUI/1.0"}
        key = str(entry.get("api_key") or (env.get(entry["key_env"]) if entry.get("key_env") else "") or "")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8") or "{}")
            ids = [str(m.get("id")) for m in (data.get("data") or []) if isinstance(m, dict) and m.get("id")]
            return {"ok": True, "message": f"Connected. {len(ids)} model(s) available.", "models": ids[:200]}
        except urllib.error.HTTPError as exc:
            hint = " Check the API key." if exc.code in (401, 403) else ""
            return {"ok": False, "message": f"The endpoint answered HTTP {exc.code}.{hint}"}
        except Exception as exc:
            return {"ok": False, "message": f"Couldn't reach {_endpoint_url(entry)} ({exc.__class__.__name__}). Is it running?"}
    status = _route_status(home, cfg, env, provider, str(model.get("base_url") or ""))
    return {"ok": status["state"] == "ready", "message": status["message"]}
