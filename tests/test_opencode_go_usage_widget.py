"""OpenCode Go's token usage in the Chat sidebar widget (static/index.html's
#chatUsageWidget, populated by static/ui.js's loadAccountUsage() from
GET /api/account_usage).

Codex/Anthropic/OpenRouter have a real percent-based usage API of their own
(agent.account_usage.fetch_account_usage(), a hermes-agent runtime
dependency this repo doesn't own). opencode-go is a flat-namespace
Hermes-hosted reseller with no such API -- only a local pool of
interchangeable keys, each simply available/exhausted/dead (api/config.py's
_pool_entry_payloads(), already used by api/providers.py's
_local_pool_snapshot() for the Settings > Providers quota card).

account_usage_from_pool() (api/providers.py) synthesizes the same
{available, windows:[{label,used_percent,reset_at,detail}]} shape
fetch_account_usage() returns, so api/routes.py's _handle_account_usage()
(and therefore the sidebar widget, unmodified) can show opencode-go
identically to a provider with a real weekly-quota window -- "percent used"
approximated as the exhausted-credential ratio, the closest honest analogue
to "percent of quota used" a pool of keys actually has.

Mirrors tests/test_issue4360_generic_pool_quota.py's mocking approach
(agent.credential_pool.load_pool patched via a small fake-module context
manager) rather than hitting a real credential store.
"""
import sys
import types
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from api.providers import account_usage_from_pool


def _is_ambient_gh_cli_entry_real(source, label, key_source):
    markers = frozenset({"gh_cli", "gh auth token"})
    env_sources = frozenset({"env:github_token", "env:gh_token"})
    source_lower = source.strip().lower()
    return (
        source_lower in markers
        or source_lower in env_sources
        or label.strip().lower() == "gh auth token"
        or key_source.strip().lower() == "gh auth token"
    )


@contextmanager
def _fake_credential_pool(**kwargs):
    """Same fixture as tests/test_issue4360_generic_pool_quota.py -- ensures
    agent.credential_pool and api.config exist and patches load_pool."""
    had_agent = "agent" in sys.modules
    had_cp = "agent.credential_pool" in sys.modules
    had_api = "api" in sys.modules
    had_api_config = "api.config" in sys.modules
    old_agent = sys.modules.get("agent")

    if not had_agent:
        _agent = types.ModuleType("agent")
        _agent.__path__ = []
        sys.modules["agent"] = _agent
    if not had_cp:
        _cp = types.ModuleType("agent.credential_pool")
        sys.modules["agent.credential_pool"] = _cp
        sys.modules["agent"].credential_pool = _cp

    if not had_api:
        _api = types.ModuleType("api")
        _api.__path__ = []
        sys.modules["api"] = _api
    if not had_api_config:
        _api_config = types.ModuleType("api.config")
        _api_config._is_ambient_gh_cli_entry = _is_ambient_gh_cli_entry_real
        sys.modules["api.config"] = _api_config
        sys.modules["api"].config = _api_config
    elif not hasattr(sys.modules["api.config"], "_is_ambient_gh_cli_entry"):
        sys.modules["api.config"]._is_ambient_gh_cli_entry = _is_ambient_gh_cli_entry_real

    cp = sys.modules["agent.credential_pool"]
    if not hasattr(cp, "load_pool"):
        cp.load_pool = None

    with patch("agent.credential_pool.load_pool", **kwargs) as m:
        yield m

    if not had_cp:
        sys.modules.pop("agent.credential_pool", None)
        if had_agent and old_agent is not None and hasattr(old_agent, "credential_pool"):
            delattr(old_agent, "credential_pool")
    if not had_agent:
        sys.modules.pop("agent", None)
    if not had_api_config:
        sys.modules.pop("api.config", None)
    if not had_api:
        sys.modules.pop("api", None)


def _entry(label, status, error_code=None, status_at=None, reset_at=None):
    return SimpleNamespace(
        label=label, source="test", last_status=status,
        last_status_at=status_at, last_error_code=error_code, last_error_reset_at=reset_at,
    )


class TestAccountUsageFromPool(unittest.TestCase):
    def test_no_pool_answers_none(self):
        with _fake_credential_pool(return_value=None):
            assert account_usage_from_pool("opencode-go") is None

    def test_empty_pool_answers_none(self):
        pool = MagicMock()
        pool.entries.return_value = []
        with _fake_credential_pool(return_value=pool):
            assert account_usage_from_pool("opencode-go") is None

    def test_all_available_is_zero_percent_used(self):
        pool = MagicMock()
        pool.entries.return_value = [
            _entry("Key 1", "available"), _entry("Key 2", "available"),
        ]
        with _fake_credential_pool(return_value=pool):
            snapshot = account_usage_from_pool("opencode-go")
        assert snapshot.available is True
        assert len(snapshot.windows) == 1
        assert snapshot.windows[0].used_percent == 0.0

    def test_all_exhausted_is_a_hundred_percent_used(self):
        reset_at = datetime.now(timezone.utc) + timedelta(hours=2)
        pool = MagicMock()
        pool.entries.return_value = [
            _entry("Key 1", "exhausted", error_code="429",
                   status_at=reset_at - timedelta(hours=1), reset_at=reset_at),
        ]
        with _fake_credential_pool(return_value=pool):
            snapshot = account_usage_from_pool("opencode-go")
        assert snapshot.windows[0].used_percent == 100.0

    def test_mixed_pool_computes_the_exhausted_ratio(self):
        reset_at = datetime.now(timezone.utc) + timedelta(hours=1)
        pool = MagicMock()
        pool.entries.return_value = [
            _entry("Key 1", "available"),
            _entry("Key 2", "available"),
            _entry("Key 3", "available"),
            _entry("Key 4", "exhausted", error_code="429",
                   status_at=reset_at - timedelta(hours=1), reset_at=reset_at),
        ]
        with _fake_credential_pool(return_value=pool):
            snapshot = account_usage_from_pool("opencode-go")
        assert snapshot.windows[0].used_percent == 25.0

    def test_dead_credentials_count_toward_used_too(self):
        # A dead credential isn't "exhausted" (it'll never come back), but
        # it's just as unavailable -- both count against the ratio.
        pool = MagicMock()
        pool.entries.return_value = [
            _entry("Key 1", "available"),
            _entry("Key 2", "dead", error_code="401"),
        ]
        with _fake_credential_pool(return_value=pool):
            snapshot = account_usage_from_pool("opencode-go")
        assert snapshot.windows[0].used_percent == 50.0

    def test_reset_at_is_the_earliest_exhausted_credentials_reset(self):
        soon = datetime.now(timezone.utc) + timedelta(minutes=30)
        later = datetime.now(timezone.utc) + timedelta(hours=5)
        pool = MagicMock()
        pool.entries.return_value = [
            _entry("Key 1", "exhausted", error_code="429",
                   status_at=later - timedelta(hours=1), reset_at=later),
            _entry("Key 2", "exhausted", error_code="429",
                   status_at=soon - timedelta(minutes=30), reset_at=soon),
        ]
        with _fake_credential_pool(return_value=pool):
            snapshot = account_usage_from_pool("opencode-go")
        window = snapshot.windows[0]
        assert window.reset_at is not None
        assert abs((window.reset_at - soon).total_seconds()) < 2

    def test_all_available_has_no_reset_time(self):
        pool = MagicMock()
        pool.entries.return_value = [_entry("Key 1", "available")]
        with _fake_credential_pool(return_value=pool):
            snapshot = account_usage_from_pool("opencode-go")
        assert snapshot.windows[0].reset_at is None

    def test_detail_carries_the_pool_summary(self):
        pool = MagicMock()
        pool.entries.return_value = [_entry("Key 1", "available"), _entry("Key 2", "available")]
        with _fake_credential_pool(return_value=pool):
            snapshot = account_usage_from_pool("opencode-go")
        assert "2/2 credentials available" in snapshot.windows[0].detail

    def test_shape_matches_what_handle_account_usage_serializes(self):
        # api/routes.py's _handle_account_usage() reads snapshot.available,
        # .provider, .plan, and per-window .label/.used_percent/.reset_at/
        # .detail -- exactly the native fetch_account_usage() shape, so it
        # needs no changes to serialize this fallback too.
        pool = MagicMock()
        pool.entries.return_value = [_entry("Key 1", "available")]
        with _fake_credential_pool(return_value=pool):
            snapshot = account_usage_from_pool("opencode-go")
        assert hasattr(snapshot, "available")
        assert hasattr(snapshot, "provider")
        assert hasattr(snapshot, "plan")
        assert hasattr(snapshot, "windows")
        window = snapshot.windows[0]
        for attr in ("label", "used_percent", "reset_at", "detail"):
            assert hasattr(window, attr)


class TestHandleAccountUsageWiring(unittest.TestCase):
    """_handle_account_usage() (api/routes.py) falls back to the pool
    synthesis only when hermes-agent's own fetch_account_usage() has
    nothing -- source-pinned since that handler needs a live profile
    config.yaml + cron_profile_context_for_home to exercise end-to-end, and
    no existing test in this repo drives /api/account_usage at the HTTP
    layer to extend."""

    def test_pool_fallback_is_wired_inside_the_native_fetch_attempt(self):
        import pathlib
        src = pathlib.Path("api/routes.py").read_text(encoding="utf-8")
        start = src.index("def _handle_account_usage(")
        body = src[start:src.index("\ndef ", start + 10)]
        assert "from agent.account_usage import fetch_account_usage" in body
        assert "from api.providers import account_usage_from_pool" in body
        assert "account_usage_from_pool(provider)" in body
        # The fallback must only fire when the native fetch came up empty,
        # not unconditionally override a real Codex/Anthropic/OpenRouter
        # window.
        fallback_at = body.index("account_usage_from_pool(provider)")
        guard_at = body.rindex("if snapshot is None or not snapshot.available:", 0, fallback_at)
        assert fallback_at > guard_at
