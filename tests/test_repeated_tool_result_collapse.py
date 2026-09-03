"""Byte-identical tool results are sent once, then referenced.

Measured on the live transcript: tool results are 92.1% of everything sent to
the model, and 9.1% of that content is byte-identical output repeated WITHIN a
single session -- overwhelmingly ``skill_view`` re-reading the same skill body
several times in one conversation. The model gains nothing from the second and
third copies; it pays full price for each.

This is a content collapse, not a message drop. The duplicate messages must
survive: a tool message is paired to a preceding assistant ``tool_calls`` entry
by ``tool_call_id``, and strict providers reject a history where that pairing
is broken. Only the body is replaced, with a pointer back to the first copy.
"""
import copy

from api.streaming import _collapse_repeated_tool_results


def _tool(content, call_id, name="skill_view"):
    return {"role": "tool", "content": content, "tool_call_id": call_id, "tool_name": name}


BIG = "SKILL BODY " * 400  # ~4.4KB, comfortably over the threshold


def test_second_identical_result_is_replaced_with_a_pointer():
    msgs = [_tool(BIG, "call-1"), _tool(BIG, "call-2")]

    out = _collapse_repeated_tool_results(msgs)

    assert out[0]["content"] == BIG, "the first copy must be sent in full"
    assert out[1]["content"] != BIG
    assert "identical" in out[1]["content"].lower()
    assert len(out[1]["content"]) < 200


def test_pairing_fields_survive_the_collapse():
    """Dropping these would make strict providers reject the whole history."""
    msgs = [_tool(BIG, "call-1"), _tool(BIG, "call-2")]

    out = _collapse_repeated_tool_results(msgs)

    assert out[1]["role"] == "tool"
    assert out[1]["tool_call_id"] == "call-2"
    assert out[1]["tool_name"] == "skill_view"


def test_third_and_later_copies_are_collapsed_too():
    msgs = [_tool(BIG, f"call-{i}") for i in range(4)]

    out = _collapse_repeated_tool_results(msgs)

    assert out[0]["content"] == BIG
    assert all(m["content"] != BIG for m in out[1:])


def test_different_content_is_never_collapsed():
    """A re-read that returned something else is real new information."""
    msgs = [_tool(BIG, "call-1"), _tool(BIG + " CHANGED", "call-2")]

    out = _collapse_repeated_tool_results(msgs)

    assert out[0]["content"] == BIG
    assert out[1]["content"] == BIG + " CHANGED"


def test_same_bytes_from_a_different_tool_is_not_collapsed():
    """Identical text from another tool is a different fact about the world."""
    msgs = [_tool(BIG, "call-1", name="read_file"),
            _tool(BIG, "call-2", name="terminal")]

    out = _collapse_repeated_tool_results(msgs)

    assert out[1]["content"] == BIG


def test_small_results_are_left_alone():
    """Below the threshold the pointer is not meaningfully cheaper than the body."""
    small = "ok"
    msgs = [_tool(small, "call-1"), _tool(small, "call-2")]

    out = _collapse_repeated_tool_results(msgs)

    assert [m["content"] for m in out] == [small, small]


def test_non_tool_roles_are_untouched():
    """Two identical assistant turns are two things the assistant actually said."""
    msgs = [
        {"role": "assistant", "content": BIG},
        {"role": "assistant", "content": BIG},
        {"role": "user", "content": BIG},
    ]

    out = _collapse_repeated_tool_results(msgs)

    assert [m["content"] for m in out] == [BIG, BIG, BIG]


def test_structured_content_is_skipped():
    """Multimodal parts are not a byte string; leave them entirely alone."""
    parts = [{"type": "text", "text": BIG}]
    msgs = [_tool(parts, "call-1"), _tool(copy.deepcopy(parts), "call-2")]

    out = _collapse_repeated_tool_results(msgs)

    assert out[0]["content"] == parts
    assert out[1]["content"] == parts


def test_input_is_not_mutated():
    """The stored transcript must never be rewritten by an outbound concern."""
    msgs = [_tool(BIG, "call-1"), _tool(BIG, "call-2")]
    before = copy.deepcopy(msgs)

    _collapse_repeated_tool_results(msgs)

    assert msgs == before


def test_collapse_is_idempotent():
    """Re-running over its own output must not rewrite the pointer again.

    Every turn re-composes the payload from the stored transcript, so a
    non-idempotent transform would churn the prefix and break prompt caching.
    """
    msgs = [_tool(BIG, "call-1"), _tool(BIG, "call-2")]

    once = _collapse_repeated_tool_results(msgs)
    twice = _collapse_repeated_tool_results(once)

    assert once == twice


def test_it_actually_saves_bytes():
    msgs = [_tool(BIG, f"call-{i}") for i in range(5)]
    import json

    before = len(json.dumps(msgs))
    after = len(json.dumps(_collapse_repeated_tool_results(msgs)))

    assert after < before * 0.35, f"expected a large saving, got {before} -> {after}"
