"""Regression test: a background delegate_task must wake an already-open tab.

Before this, ``delegate_task`` completion (``tool.completed`` relayed by
api/gateway_chat.py) was ONLY pushed to the turn-scoped STREAMS queue. A
delegate_task spawned with ``background=true`` can keep running -- and
complete -- after the visible turn's SSE stream has already closed (Agent
Canvas stays in sync via its own reconciliation poll, but the chat
transcript's tool-call card has no equivalent). The persistent per-session
SSE channel's ``session-updated`` self-heal only ever fires once, at
(re)connect time -- so an already-open tab that never disconnects never
learns the delegate_task result landed, and the user has to hard-refresh to
see it in chat history.

Pins: ``_notify_session_stream_of_delegate_completion`` (called from both
gateway_chat.py relay call sites right after ``put_gateway_event``) pushes a
live ``session-updated`` frame onto the persistent per-session channel via
``_emit_to_session_streams`` -- the SAME channel/event name the existing
reconnect self-heal uses -- whenever a ``delegate_task`` tool call completes,
so the frontend's existing ``session-updated`` handler (messages.js) picks it
up without a refresh.
"""
from api.gateway_chat import _notify_session_stream_of_delegate_completion


def test_ignores_non_tool_complete_events(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "api.background_process._emit_to_session_streams",
        lambda *a, **k: calls.append((a, k)),
    )
    _notify_session_stream_of_delegate_completion(
        "sid-1", "tool", {"name": "delegate_task"}
    )
    assert calls == []


def test_ignores_non_delegate_task_tools(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "api.background_process._emit_to_session_streams",
        lambda *a, **k: calls.append((a, k)),
    )
    _notify_session_stream_of_delegate_completion(
        "sid-1", "tool_complete", {"name": "read_file"}
    )
    assert calls == []


def test_skips_emit_when_persisted_count_unknown(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "api.background_process.persisted_message_count_for_session",
        lambda sid: None,
    )
    monkeypatch.setattr(
        "api.background_process._emit_to_session_streams",
        lambda *a, **k: calls.append((a, k)),
    )
    _notify_session_stream_of_delegate_completion(
        "sid-1", "tool_complete", {"name": "delegate_task"}
    )
    assert calls == []


def test_emits_session_updated_on_delegate_task_completion(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "api.background_process.persisted_message_count_for_session",
        lambda sid: 42,
    )
    monkeypatch.setattr(
        "api.background_process._emit_to_session_streams",
        lambda *a, **k: calls.append((a, k)),
    )
    _notify_session_stream_of_delegate_completion(
        "sid-1", "tool_complete", {"name": "delegate_task", "tid": "t1"}
    )
    assert len(calls) == 1
    args, kwargs = calls[0]
    session_id, event, data = args
    assert session_id == "sid-1"
    assert event == "session-updated"
    assert data["message_count"] == 42
    assert data["session_id"] == "sid-1"


def test_swallows_emit_failure(monkeypatch):
    def _boom(sid):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(
        "api.background_process.persisted_message_count_for_session", _boom
    )
    # Must not raise -- a notify failure must never break the tool-progress
    # relay it's piggybacked onto.
    _notify_session_stream_of_delegate_completion(
        "sid-1", "tool_complete", {"name": "delegate_task"}
    )
