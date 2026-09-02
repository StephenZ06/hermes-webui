"""The WebUI's session-rollover hook must actually rotate, and then get out of the way.

hermes-webui runs hermes-agent in-process, so it never passed through the
gateway platform's wiring of ``_pre_compression_hook``. Without this module a
session only ever got the plain in-loop compaction fallback, with no earlier
checkpointed handoff to a clean successor session — and the failure was silent,
because the whole evaluation is wrapped in a fail-soft except.

The subtle part this pins: the deployment sets ``compression.in_place: true``,
which is right for the 50% fallback but would defeat a rollover entirely — an
in-place compaction rewrites the SAME session, so nothing rotates and the
coordinator reports ``no_rotation``. The hook forces rotation for its own call
and must restore the agent's normal setting afterwards, or every later
compaction on that agent silently changes behaviour.

The summariser itself is not exercised here (that is hermes-agent's own
contract); the stub stands in for ``_compress_context`` and rotates the way a
real rollover does.
"""
import types

import pytest

from api import context_pressure_rollover as cpr


class _StubAgent:
    """Everything the hook touches, with a summariser that rotates."""

    def __init__(self, session_id="sess-under-test", context_length=200_000,
                 rotate=True, blow_up=False):
        self.session_id = session_id
        self.compression_in_place = True
        self.context_compressor = types.SimpleNamespace(context_length=context_length)
        self.seen_in_place = None
        self._rotate = rotate
        self._blow_up = blow_up
        self.calls = 0

    def _compress_context(self, messages, system_message, approx_tokens=None, task_id=None):
        self.calls += 1
        self.seen_in_place = self.compression_in_place
        if self._blow_up:
            raise RuntimeError("summariser exploded")
        if self._rotate:
            self.session_id = f"{self.session_id}-successor"
        return messages[-1:], "compacted system prompt"


# Minimal config that enables the policy, mirroring the deployment's shape:
# api_server.session_rollover.enabled plus a compression threshold the policy
# must agree with (is_compatible_with_lcm_threshold refuses a mismatch).
_ENABLING_CONFIG = {
    "api_server": {
        "session_rollover": {
            "enabled": True,
            # All three thresholds must be supplied together and stay ordered
            # rearm < checkpoint < lcm_fallback; leaving one to its default
            # inverts the ordering and from_config() silently rejects the whole
            # block, handing back a disabled policy. These mirror the values the
            # deployment actually runs.
            "checkpoint_threshold": 0.4,
            "lcm_fallback_threshold": 0.5,
            "rearm_threshold": 0.3,
        }
    },
    # Must equal lcm_fallback_threshold — the policy refuses to run when it
    # disagrees with the configured compression threshold.
    "compression": {"threshold": 0.5},
}


@pytest.fixture
def enabled_policy(tmp_path, monkeypatch):
    """Force the rollover policy on, independently of the host's config.yaml."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(cpr, "_load_gateway_config", lambda: _ENABLING_CONFIG)
    cpr._coordinator = None
    cpr._coordinator_policy = None
    yield
    cpr._coordinator = None
    cpr._coordinator_policy = None


@pytest.fixture
def messages():
    return [{"role": "user", "content": "x" * 200} for _ in range(50)]


def _high_pressure(agent):
    """Token count comfortably over any sane threshold for this context size."""
    return int(agent.context_compressor.context_length * 0.9)


def test_rollover_rotates_and_reports_attempted(enabled_policy, messages):
    agent = _StubAgent()

    attempted, new_messages, new_system = cpr._evaluate_session_rollover(
        agent, messages, "system", _high_pressure(agent), "task")

    assert attempted is True
    assert agent.session_id.endswith("-successor")
    assert new_messages == messages[-1:]
    assert new_system == "compacted system prompt"


def test_in_place_compaction_is_forced_off_then_restored(enabled_policy, messages):
    """The invariant that makes rollover possible at all.

    With compression_in_place left true the agent rewrites the same session and
    nothing rotates; leaving it false afterwards would silently change every
    later 50% fallback compaction on the same agent.
    """
    agent = _StubAgent()

    attempted, _, _ = cpr._evaluate_session_rollover(
        agent, messages, "system", _high_pressure(agent), "task")

    assert attempted is True
    assert agent.seen_in_place is False, "rollover ran with in-place compaction still on"
    assert agent.compression_in_place is True, "agent's own setting was not restored"


def test_no_session_id_is_a_no_op(messages):
    """A turn with no session has nothing to check point or roll over to."""
    agent = _StubAgent(session_id="")

    attempted, out_messages, out_system = cpr._evaluate_session_rollover(
        agent, messages, "system", _high_pressure(agent), "task")

    assert attempted is False
    assert out_messages is messages and out_system is None
    assert agent.calls == 0


def test_zero_context_length_is_a_no_op(messages):
    """Pressure is tokens/context_length — without a context length there is none."""
    agent = _StubAgent(context_length=0)

    attempted, out_messages, out_system = cpr._evaluate_session_rollover(
        agent, messages, "system", 100_000, "task")

    assert attempted is False
    assert out_messages is messages and out_system is None
    assert agent.calls == 0


def test_a_failing_summariser_never_breaks_the_turn(enabled_policy, messages):
    """Fail-soft by contract: retain the session rather than abort the turn."""
    agent = _StubAgent(blow_up=True)

    attempted, out_messages, out_system = cpr._evaluate_session_rollover(
        agent, messages, "system", _high_pressure(agent), "task")

    assert attempted is False
    assert out_messages is messages
    assert out_system is None
    # Even on the failure path the agent's own setting must be handed back intact.
    assert agent.compression_in_place is True


def test_attach_hook_is_idempotent_and_never_raises():
    agent = _StubAgent()
    cpr.attach_rollover_hook(agent)
    first = agent._pre_compression_hook
    cpr.attach_rollover_hook(agent)
    assert agent._pre_compression_hook is first

    class _Hostile:
        __slots__ = ()

    cpr.attach_rollover_hook(_Hostile())  # must not raise
