"""Wires an in-process AIAgent's ``_pre_compression_hook`` to hermes-agent's
verified API session rollover coordinator (``gateway/api_session_rollover.py``).

hermes-webui runs hermes-agent in-process (no separate ``hermes gateway run``
server), so it never went through ``gateway/platforms/api_server.py``'s own
wiring of this hook — every WebUI session only ever had the plain in-loop
compaction fallback (``compression.threshold`` in config.yaml), with no
earlier checkpointed handoff to a clean successor session. This module is
the WebUI-side equivalent of that platform's ``_evaluate_api_session_rollover``
method, adapted for per-turn AIAgent construction with no persistent
per-connection adapter object to cache state on — hence the module-level
cache here instead of an instance attribute.

Call ``attach_rollover_hook(agent)`` right after every real conversational
turn's AIAgent is constructed or reused (see api/streaming.py and
_handle_chat_sync in api/routes.py). It is cheap and idempotent — safe to
call unconditionally on every turn, cached agent or not.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_coordinator = None
_coordinator_policy = None
_coordinator_lock = threading.Lock()


def _load_gateway_config():
    try:
        from hermes_cli.config import load_config

        return load_config()
    except Exception:
        logger.debug("session_rollover: failed to load config", exc_info=True)
        return {}


def _evaluate_session_rollover(agent, messages, system_message, real_tokens, task_id):
    """Pre-compression hook body — same coordinator/contract as the gateway
    api_server platform's ``_evaluate_api_session_rollover``. Returns
    ``(attempted, messages, system_prompt)``; see conversation_loop.py's
    hook call site for how the return value is consumed.
    """
    global _coordinator, _coordinator_policy

    session_id = getattr(agent, "session_id", None)
    if not session_id:
        return False, messages, None
    try:
        from gateway.api_session_rollover import (
            APISessionRolloverCoordinator,
            APISessionRolloverPolicy,
            effective_lcm_context_threshold,
        )

        config = _load_gateway_config()
        policy = APISessionRolloverPolicy.from_config(config)
        if not policy.enabled:
            return False, messages, None
        threshold = effective_lcm_context_threshold(config)
        if not policy.is_compatible_with_lcm_threshold(threshold):
            logger.warning(
                "session_rollover disabled: policy.lcm_fallback_threshold=%s "
                "does not match the configured compression threshold=%s",
                policy.lcm_fallback_threshold, threshold,
            )
            return False, messages, None

        compressor = getattr(agent, "context_compressor", None)
        try:
            context_length = float(getattr(compressor, "context_length", 0) or 0)
        except (TypeError, ValueError):
            context_length = 0.0
        if context_length <= 0:
            return False, messages, None
        pressure = float(real_tokens) / context_length

        with _coordinator_lock:
            if _coordinator is None or _coordinator_policy != policy:
                home = Path(os.getenv("HERMES_HOME", "~/.hermes")).expanduser()
                _coordinator = APISessionRolloverCoordinator(policy=policy, checkpoint_root=home)
                _coordinator_policy = policy
            coordinator = _coordinator

        # This deployment's compression.in_place=true (config.yaml) makes
        # ordinary 50% compaction rewrite the SAME session in place — correct
        # for that fallback, but it would silently defeat the entire point of
        # a "roll over to a clean successor session" checkpoint here, which
        # needs agent._compress_context to actually rotate. Force rotation
        # for just this one call, then restore whatever the agent's normal
        # in-place setting was so the 50% fallback keeps its own behavior
        # untouched on every other iteration.
        _prior_in_place = getattr(agent, "compression_in_place", True)
        agent.compression_in_place = False
        try:
            outcome, new_messages, new_system_prompt = coordinator.maybe_rollover(
                agent, messages, system_message, pressure,
                approx_tokens=real_tokens, task_id=task_id,
            )
        finally:
            agent.compression_in_place = _prior_in_place
    except Exception:
        logger.exception("session_rollover evaluation failed; retaining current session")
        return False, messages, None

    # "transition_failed" belongs here too: the coordinator hands back the
    # ORIGINAL messages in that case, so reporting the hook as having handled
    # compression would suppress the in-loop 50% fallback and leave the real
    # context pressure unrelieved for the rest of the turn.
    if outcome.reason in ("not_due", "checkpoint_failed", "transition_failed"):
        if outcome.reason != "not_due":
            logger.warning(
                "session_rollover %s for %s; falling back to in-loop compaction",
                outcome.reason, session_id,
            )
        return False, messages, None

    if outcome.renewed:
        logger.info("session_rollover completed: %s -> %s", session_id, outcome.session_id)
    else:
        logger.warning("session_rollover not completed for %s: %s", session_id, outcome.reason)
    return True, new_messages, new_system_prompt


def attach_rollover_hook(agent) -> None:
    """Idempotent — safe to call on every turn, cached agent or freshly built."""
    try:
        agent._pre_compression_hook = _evaluate_session_rollover
    except Exception:
        logger.debug("session_rollover: failed to attach hook", exc_info=True)
