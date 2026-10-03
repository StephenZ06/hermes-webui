"""The in-flight turn marker is cleared as one unit, through one helper.

``active_stream_id`` plus the four ``pending_*`` prompt fields describe one
running turn. They were cleared by ~20 hand-written blocks (some as
attribute-by-attribute ``hasattr`` chains), so a site that dropped one field
would leave a half-cleared turn: a stale pending prompt or attachment list
replayed after the stream had ended.
"""

import ast
import pathlib
from types import SimpleNamespace

from api.models import Session, clear_pending_turn_fields

REPO = pathlib.Path(__file__).resolve().parents[1]
_PENDING = ("active_stream_id", "pending_user_message", "pending_attachments",
            "pending_started_at", "pending_user_source")


def _running(session):
    session.active_stream_id = "stream-1"
    session.pending_user_message = "hello"
    session.pending_attachments = [{"name": "a.txt"}]
    session.pending_started_at = 123.0
    session.pending_user_source = "webui"
    return session


def test_session_clear_pending_turn_drops_the_whole_marker(tmp_path):
    session = _running(Session(session_id="pending-unit", workspace=str(tmp_path)))

    session.clear_pending_turn()

    assert session.active_stream_id is None
    assert session.pending_user_message is None
    assert session.pending_attachments == []
    assert session.pending_started_at is None
    assert session.pending_user_source is None


def test_stub_objects_only_get_the_fields_they_carry():
    stub = SimpleNamespace(active_stream_id="stream-1", pending_user_message="hi")

    clear_pending_turn_fields(stub)

    assert stub.active_stream_id is None
    assert stub.pending_user_message is None
    assert not hasattr(stub, "pending_attachments")
    assert not hasattr(stub, "pending_started_at")


def test_no_module_hand_clears_the_pending_turn_fields():
    """Clears go through clear_pending_turn()/clear_pending_turn_fields()."""
    offenders = []
    for path in sorted((REPO / "api").glob("*.py")):
        if path.name == "models.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not (isinstance(target, ast.Attribute) and target.attr in _PENDING):
                continue
            value = ast.unparse(node.value)
            if value in ("None", "[]"):
                offenders.append(f"{path.name}:{node.lineno} {ast.unparse(target)} = {value}")
    assert offenders == []


def test_btw_repairs_a_dead_stream_marker_through_the_shared_repair(monkeypatch):
    """/btw used to drop only active_stream_id, stranding the dead turn's
    pending prompt; it now runs the same stale-stream repair as chat/start."""
    import api.routes as routes

    parent = SimpleNamespace(session_id="btw-parent", active_stream_id="dead-stream",
                             workspace="/tmp", model="m", model_provider=None, messages=[])
    repaired = []
    monkeypatch.setattr(routes, "get_session", lambda sid: parent)
    monkeypatch.setattr(routes, "_agent_runtime_barrier_response", lambda **_kw: None)
    monkeypatch.setattr(routes, "_session_is_subagent_view_only", lambda sid: False)
    monkeypatch.setattr(routes, "_clear_stale_stream_state", lambda s: repaired.append(s) or True)

    class _Stop(Exception):
        pass

    def stop(**_kwargs):
        raise _Stop

    monkeypatch.setattr("api.models.new_session", stop)
    routes.STREAMS.pop("dead-stream", None)
    try:
        routes._handle_btw(object(), {"session_id": "btw-parent", "question": "why?"})
    except _Stop:
        pass

    assert repaired == [parent]
