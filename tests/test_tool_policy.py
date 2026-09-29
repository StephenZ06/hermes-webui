"""Tests for deterministic optional-tool policy resolution."""

import json

import pytest

from api.tool_policy import resolve_tool_policy


def test_minimal_is_empty_only_when_runtime_supports_restrictive_empty_list():
    resolved = resolve_tool_policy("minimal", None, ["mcp-files", "mcp-web"], empty_means_restrictive=True)

    assert resolved.requested == "minimal"
    assert resolved.toolsets == []
    assert resolved.enforced is True
    assert resolved.reason is None


def test_minimal_fails_closed_when_runtime_empty_list_means_inherit():
    resolved = resolve_tool_policy("minimal", None, ["mcp-web"], empty_means_restrictive=False)

    assert resolved.toolsets == []
    assert resolved.enforced is False
    assert resolved.reason == "minimal_toolset_not_supported"


def test_explicit_toolsets_win_and_unknown_names_are_rejected():
    resolved = resolve_tool_policy("minimal", ["mcp-files"], ["mcp-files"], empty_means_restrictive=True)

    assert resolved.requested == "explicit"
    assert resolved.toolsets == ["mcp-files"]
    with pytest.raises(ValueError, match="Unknown toolset"):
        resolve_tool_policy("explicit", ["mcp-unknown"], ["mcp-files"], empty_means_restrictive=True)


def test_inherit_profile_preserves_the_profile_toolsets():
    resolved = resolve_tool_policy("inherit-profile", None, ["mcp-files", "mcp-web"], empty_means_restrictive=True)

    assert resolved.toolsets == ["mcp-files", "mcp-web"]
    assert resolved.enforced is True


def test_streaming_does_not_treat_an_intentional_empty_override_as_missing():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "api/streaming.py").read_text(encoding="utf-8")

    assert "if _override is not None:" in source


def test_runtime_capability_confirms_empty_toolsets_are_restrictive(monkeypatch):
    import sys
    import types
    import api.agent_runtime as agent_runtime
    from api.tool_policy import runtime_empty_toolsets_are_restrictive

    runtime_empty_toolsets_are_restrictive.cache_clear()
    monkeypatch.setattr(agent_runtime, "get_ai_agent_class", lambda: object)
    monkeypatch.setitem(
        sys.modules,
        "model_tools",
        types.SimpleNamespace(
            get_tool_definitions=lambda **kwargs: []
            if kwargs["enabled_toolsets"] == [] else [object()]
        ),
    )

    assert runtime_empty_toolsets_are_restrictive() is True


def test_session_persists_requested_tool_policy_separately_from_toolsets(tmp_path, monkeypatch):
    import api.models as models

    monkeypatch.setattr(models, "SESSION_DIR", tmp_path)
    session = models.Session(
        session_id="policy-session",
        workspace=str(tmp_path),
        tool_policy="minimal",
        enabled_toolsets=[],
    )
    session.save(touch_updated_at=False)

    payload = json.loads((tmp_path / "policy-session.json").read_text(encoding="utf-8"))
    restored = models.Session.load_metadata_only("policy-session")

    assert payload["tool_policy"] == "minimal"
    assert payload["enabled_toolsets"] == []
    assert restored.tool_policy == "minimal"
    assert restored.compact()["tool_policy"] == "minimal"
