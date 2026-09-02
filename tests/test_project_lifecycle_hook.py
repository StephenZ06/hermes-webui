"""The project-lifecycle instruction must reach every WebUI turn.

The skill is installed and visible to every profile, but availability is not
enforcement: nothing made the agent consult it before editing a mapped
repository, so it was used only when the model happened to judge it relevant.
Claude Code solves this with a per-prompt hook; hermes-agent's equivalent is
the ``pre_llm_call`` plugin hook, whose returned ``{"context": ...}`` is
injected into the current turn's user message.

hermes-webui runs hermes-agent in-process rather than through ``cli.py`` or
``gateway/run.py``, and those two are the only callers that register hooks
from config -- so a ``hooks:`` block in config.yaml never fires here. This
module registers the hook directly on the plugin manager instead, which also
avoids handing arbitrary shell commands a per-turn execution point.
"""
import pytest

from api import project_lifecycle_hook as plh


class _FakeManager:
    def __init__(self):
        self.hooks = {}

    def register_hook(self, name, callback):
        self.hooks.setdefault(name, []).append(callback)
        return object()


@pytest.fixture(autouse=True)
def _reset():
    plh._reset_for_tests()
    yield
    plh._reset_for_tests()


def test_hook_injects_the_project_lifecycle_instruction():
    payload = plh._project_lifecycle_context()

    assert isinstance(payload, dict)
    text = payload["context"]
    assert "project-lifecycle" in text
    # The instruction is worthless if it reads as optional: the whole failure
    # mode is a model deciding a small, already-diagnosed fix does not warrant
    # the workflow.
    assert "before" in text.lower()


def test_registers_on_the_pre_llm_call_hook():
    mgr = _FakeManager()

    assert plh.ensure_project_lifecycle_hook(manager=mgr) is True

    assert list(mgr.hooks) == ["pre_llm_call"]
    assert mgr.hooks["pre_llm_call"][0]() == plh._project_lifecycle_context()


def test_registration_is_idempotent():
    """Called from every turn's agent setup, so it must not stack callbacks.

    A duplicate registration would inject the same paragraph two or three
    times into a single user message.
    """
    mgr = _FakeManager()

    assert plh.ensure_project_lifecycle_hook(manager=mgr) is True
    assert plh.ensure_project_lifecycle_hook(manager=mgr) is False
    assert plh.ensure_project_lifecycle_hook(manager=mgr) is False

    assert len(mgr.hooks["pre_llm_call"]) == 1


def test_registration_failure_is_not_fatal():
    """A turn must still run if the plugin manager is unavailable or angry."""

    class _Broken:
        def register_hook(self, *_a, **_k):
            raise RuntimeError("plugin manager exploded")

    assert plh.ensure_project_lifecycle_hook(manager=_Broken()) is False
    # Still not marked as registered, so a later healthy call can retry.
    mgr = _FakeManager()
    assert plh.ensure_project_lifecycle_hook(manager=mgr) is True


def test_every_agent_setup_site_arms_the_hook():
    """Structural: the hook must be armed wherever a turn's agent is built.

    Mirrors the rollover hook's call sites — a turn whose agent was built on a
    path that forgot to arm this silently loses the instruction, which is
    exactly the failure this module exists to end.
    """
    import pathlib

    repo = pathlib.Path(__file__).resolve().parent.parent
    rollover_sites = 0
    lifecycle_sites = 0
    for name in ("api/routes.py", "api/streaming.py"):
        src = (repo / name).read_text(encoding="utf-8")
        rollover_sites += src.count("attach_rollover_hook(")
        lifecycle_sites += src.count("ensure_project_lifecycle_hook(")

    # Discount the import lines, which are counted by the same substring.
    assert lifecycle_sites >= rollover_sites, (
        "every agent-construction site that attaches the rollover hook must "
        "also arm the project-lifecycle hook"
    )
