"""Inject the project-lifecycle instruction into every WebUI turn.

The ``project-lifecycle`` skill is installed and visible to every profile, but
being available is not the same as being used: nothing obliged the agent to
consult it before editing a mapped repository, so it fired only when the model
happened to judge it relevant. The failure mode is precisely the small,
already-diagnosed fix that "obviously" does not need a workflow.

Claude Code enforces this with a per-prompt hook. hermes-agent's equivalent is
the ``pre_llm_call`` plugin hook: a callback's ``{"context": ...}`` is appended
to the current turn's user message, ephemerally, and deliberately NOT to the
system prompt -- that keeps the prompt-cache prefix byte-identical across turns.

Why register directly rather than through the ``hooks:`` config block: shell
hooks are wired up by ``cli.py`` and ``gateway/run.py``, and hermes-webui runs
hermes-agent in-process through neither, so a configured hook would never fire
here (the same structural gap that left the session-rollover hook unwired).
Registering in-process also avoids giving arbitrary shell commands a per-turn
execution point, which is a much larger surface than this needs.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

HOOK_NAME = "pre_llm_call"

_INSTRUCTION = (
    "Before editing, fixing, refactoring, reviewing, or documenting anything "
    "in a mapped repository -- including a single small, well-specified, "
    "already-diagnosed fix -- invoke the project-lifecycle skill first. Its "
    "size decides which mode of that skill applies, not whether it applies."
)

_lock = threading.Lock()
_registered = False


def _project_lifecycle_context() -> dict:
    """The payload handed to the model, in ``pre_llm_call``'s dict form."""
    return {"context": _INSTRUCTION}


def _default_manager():
    from hermes_cli.plugins import get_plugin_manager

    return get_plugin_manager()


def ensure_project_lifecycle_hook(manager=None) -> bool:
    """Arm the hook once per process. Returns True only on the registering call.

    Safe to call on every turn: agents are constructed per turn, but the plugin
    manager is process-global, so a second registration would inject the same
    paragraph twice into one user message.

    Never raises. A turn that cannot arm the hook is worse off without the
    instruction, but it is still a working turn; failing here would break chat
    outright. A failed attempt leaves the flag unset so a later healthy call
    can retry.
    """
    global _registered
    with _lock:
        if _registered:
            return False
        try:
            mgr = manager if manager is not None else _default_manager()
            # Same mechanism agent/shell_hooks.register_from_config() uses to
            # attach a callback that is not part of a packaged plugin:
            # PluginManager exposes invoke_hook/has_hook but no public
            # registrar (register_hook lives on PluginContext, which only a
            # loaded plugin gets). Guard against double-adding our own
            # callback in case the module is re-imported under a new name.
            callbacks = mgr._hooks.setdefault(HOOK_NAME, [])
            if _project_lifecycle_context not in callbacks:
                callbacks.append(_project_lifecycle_context)
        except Exception:
            logger.warning(
                "project-lifecycle hook could not be registered; turns will "
                "run without the instruction",
                exc_info=True,
            )
            return False
        _registered = True
        logger.info("project-lifecycle instruction armed on %s", HOOK_NAME)
        return True


def _reset_for_tests() -> None:
    global _registered
    with _lock:
        _registered = False
