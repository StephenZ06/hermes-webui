"""Route-side enforcement of the per-session optional-tool policy.

docs/CONTRACTS.md: ``api.routes._start_run()`` owns resolution and passes the
same exact list to the runner (``StartRunRequest``) and to legacy streaming; a
Minimal policy that the installed Agent cannot enforce is refused, never run
with a broadened toolset while presented as Minimal.
"""

import json
import queue
from types import SimpleNamespace

import pytest

import api.config as config
import api.routes as routes


@pytest.fixture
def restrictive_runtime(monkeypatch):
    monkeypatch.setattr(routes, "runtime_empty_toolsets_are_restrictive", lambda: True)


@pytest.fixture
def permissive_runtime(monkeypatch):
    monkeypatch.setattr(routes, "runtime_empty_toolsets_are_restrictive", lambda: False)


# ── policy/body validation shared by /api/session/toolsets and /api/session/new ──


def test_minimal_policy_stores_an_empty_list(restrictive_runtime):
    assert routes._session_tool_policy_from_body([], "minimal") == ([], "minimal")
    assert routes._session_tool_policy_from_body(None, "minimal") == ([], "minimal")


def test_minimal_policy_is_refused_when_the_runtime_cannot_enforce_it(permissive_runtime):
    with pytest.raises(routes.ToolPolicyUnavailable):
        routes._session_tool_policy_from_body([], "minimal")


def test_inherit_profile_clears_any_override(restrictive_runtime):
    assert routes._session_tool_policy_from_body(None, "inherit-profile") == (None, "inherit-profile")


def test_explicit_policy_requires_a_list(restrictive_runtime):
    assert routes._session_tool_policy_from_body(["web"], "explicit") == (["web"], "explicit")
    with pytest.raises(ValueError):
        routes._session_tool_policy_from_body(None, "explicit")


def test_legacy_callers_without_a_policy_keep_the_old_contract(restrictive_runtime):
    assert routes._session_tool_policy_from_body(["web"], None) == (["web"], None)
    assert routes._session_tool_policy_from_body(None, None) == (None, None)
    with pytest.raises(ValueError):
        routes._session_tool_policy_from_body([], None)


def test_unknown_policy_names_are_rejected(restrictive_runtime):
    with pytest.raises(ValueError):
        routes._session_tool_policy_from_body(None, "everything")


# ── /api/session/toolsets ──


class _Handler:
    def __init__(self):
        self.status = None
        self._body = bytearray()

    def send_response(self, status):
        self.status = status

    def send_header(self, *_args):
        pass

    def end_headers(self):
        pass

    @property
    def wfile(self):
        return self

    def write(self, data):
        self._body.extend(data)

    def payload(self):
        return json.loads(self._body.decode("utf-8"))


class _Session:
    def __init__(self):
        self.session_id = "policy-route-session"
        self.enabled_toolsets = None
        self.tool_policy = None
        self.saved = 0

    def save(self, *args, **kwargs):
        self.saved += 1


def _post_toolsets(monkeypatch, body):
    session = _Session()
    monkeypatch.setattr(routes, "get_session", lambda sid: session)
    monkeypatch.setattr(routes, "_session_is_subagent_view_only", lambda sid: False)
    handler = _Handler()
    routes._route_post_api_session_toolsets(
        handler, SimpleNamespace(path="/api/session/toolsets", query=""),
        {"session_id": session.session_id, **body}, None,
    )
    return handler, session


def test_toolsets_route_persists_and_returns_minimal(monkeypatch, restrictive_runtime):
    handler, session = _post_toolsets(monkeypatch, {"toolsets": [], "tool_policy": "minimal"})

    assert handler.status == 200
    assert handler.payload() == {"ok": True, "enabled_toolsets": [], "tool_policy": "minimal"}
    assert (session.enabled_toolsets, session.tool_policy) == ([], "minimal")


def test_toolsets_route_refuses_unenforceable_minimal_without_saving(monkeypatch, permissive_runtime):
    handler, session = _post_toolsets(monkeypatch, {"toolsets": [], "tool_policy": "minimal"})

    assert handler.status == 409
    assert handler.payload()["code"] == "minimal_toolset_not_supported"
    assert session.saved == 0
    assert session.tool_policy is None


def test_toolsets_route_profile_defaults(monkeypatch, restrictive_runtime):
    handler, session = _post_toolsets(monkeypatch, {"toolsets": None, "tool_policy": "inherit-profile"})

    assert handler.status == 200
    assert (session.enabled_toolsets, session.tool_policy) == (None, "inherit-profile")


# ── _start_run resolution ──


def _policy_session(policy, toolsets):
    return SimpleNamespace(
        session_id="policy-run-session",
        profile=None,
        tool_policy=policy,
        enabled_toolsets=toolsets,
    )


def _start(monkeypatch, session, *, gateway=False):
    captured = {}

    def fake_stream(s, **kwargs):
        captured.update(kwargs)
        return {"stream_id": "s", "session_id": s.session_id, "_status": 200}

    monkeypatch.delenv("HERMES_WEBUI_RUNTIME_ADAPTER", raising=False)
    monkeypatch.setattr(routes, "_start_chat_stream_for_session", fake_stream)
    monkeypatch.setattr(routes, "_profile_toolsets_for_session", lambda _s: ["web", "terminal"])
    result = routes._start_run(
        session, msg="hi", attachments=[], workspace="/tmp", model="m",
        model_provider="p", normalized_model=False, source="webui", route="test",
        gateway_chat_enabled=gateway,
    )
    return result, captured


def test_legacy_stream_receives_the_exact_minimal_list(monkeypatch, restrictive_runtime):
    _result, captured = _start(monkeypatch, _policy_session("minimal", []))
    assert captured["resolved_toolsets"] == []


def test_legacy_stream_receives_profile_toolsets_for_inherit(monkeypatch, restrictive_runtime):
    _result, captured = _start(monkeypatch, _policy_session("inherit-profile", None))
    assert captured["resolved_toolsets"] == ["web", "terminal"]


def test_sessions_without_a_policy_keep_legacy_resolution(monkeypatch, restrictive_runtime):
    _result, captured = _start(monkeypatch, _policy_session(None, ["web"]))
    assert captured["resolved_toolsets"] is None


def test_unenforceable_minimal_is_refused_not_broadened(monkeypatch, permissive_runtime):
    result, captured = _start(monkeypatch, _policy_session("minimal", []))
    assert result["_status"] == 409
    assert result["code"] == "minimal_toolset_not_supported"
    assert captured == {}


def test_gateway_backend_refuses_a_restricting_policy(monkeypatch, restrictive_runtime):
    result, captured = _start(monkeypatch, _policy_session("minimal", []), gateway=True)
    assert result["_status"] == 409
    assert result["code"] == "tool_policy_unsupported_backend"
    assert captured == {}


def test_unknown_explicit_toolset_is_a_client_error(monkeypatch, restrictive_runtime):
    result, captured = _start(monkeypatch, _policy_session("explicit", ["not-configured"]))
    assert result["_status"] == 400
    assert captured == {}


# ── the worker actually gets the list ──


def test_stream_worker_is_started_with_the_resolved_list(monkeypatch, tmp_path):
    config.STREAMS.clear()
    config.ACTIVE_RUNS.clear()
    config.SESSION_AGENT_LOCKS.clear()

    class ChatStartSession:
        session_id = "policy-worker-session"

        def __init__(self):
            self.active_stream_id = None
            self.pending_user_message = None
            self.pending_attachments = []
            self.pending_started_at = None
            self.messages = []
            self.title = "Policy"
            self.worktree_path = None
            self.workspace = None
            self.model = None
            self.model_provider = None

        def save(self, *args, **kwargs):
            return None

    started = {}

    class CapturingThread:
        def __init__(self, *args, **kwargs):
            started.update(kwargs)

        def start(self):
            return None

    monkeypatch.setattr(routes.uuid, "uuid4", lambda: type("FakeUuid", (), {"hex": "policy-stream"})())
    monkeypatch.setattr(routes, "set_last_workspace", lambda workspace: None)
    monkeypatch.setattr(routes, "create_stream_channel", lambda: queue.Queue())
    monkeypatch.setattr(routes.threading, "Thread", CapturingThread)
    try:
        response = routes._start_chat_stream_for_session(
            ChatStartSession(), msg="hi", attachments=[], workspace=str(tmp_path),
            model="m", model_provider=None, external_runtime_owned=False,
            resolved_toolsets=[],
        )
        assert "error" not in response
        assert started["kwargs"]["resolved_toolsets"] == []
    finally:
        routes.STREAMS.pop("policy-stream", None)
