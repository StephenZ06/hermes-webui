"""Runtime boundary coverage for optional tool policy decisions."""

from types import SimpleNamespace

from api.tool_policy import resolve_tool_policy


class _FakeRunner:
    def __init__(self):
        self.request = None

    def start_run(self, request):
        self.request = request
        return {
            "run_id": "run-policy",
            "stream_id": "stream-policy",
            "session_id": request.session_id,
        }


def test_runtime_contract_records_an_enforceable_empty_toolset_list():
    """An enforceable minimal policy reaches the executor as exactly ``[]``."""
    from api.runtime_adapter import RunnerRuntimeAdapter, StartRunRequest

    policy = resolve_tool_policy(
        "minimal", None, ["web", "terminal"], empty_means_restrictive=True
    )
    runner = _FakeRunner()
    adapter = RunnerRuntimeAdapter(client=runner)

    adapter.start_run(
        StartRunRequest(
            session_id="policy-session",
            message="hello",
            toolsets=policy.toolsets,
            metadata={"tool_policy": policy.requested},
        )
    )

    assert runner.request.toolsets == []
    assert runner.request.metadata["tool_policy"] == "minimal"


def test_start_run_forwards_the_resolved_policy_to_runner(monkeypatch):
    import api.routes as routes

    runner = _FakeRunner()
    session = SimpleNamespace(
        session_id="policy-session",
        profile="policy-profile",
        tool_policy="minimal",
        enabled_toolsets=[],
    )
    monkeypatch.setenv("HERMES_WEBUI_RUNTIME_ADAPTER", "runner-local")
    monkeypatch.setattr(routes, "_runtime_runner_client_factory", lambda: runner)
    # Forwarding contract only: the installed-Agent capability probe is
    # covered in test_tool_policy.py and fails closed when no Agent is loaded.
    monkeypatch.setattr(routes, "runtime_empty_toolsets_are_restrictive", lambda: True)
    monkeypatch.setattr(
        routes,
        "_profile_toolsets_for_session",
        lambda _session: ["web", "terminal"],
    )

    routes._start_run(
        session,
        msg="hello",
        attachments=[],
        workspace="/tmp",
        model="test-model",
        model_provider="test-provider",
        normalized_model=False,
        source="webui",
        route="test",
    )

    assert runner.request.toolsets == []
    assert runner.request.metadata["tool_policy"] == "minimal"
