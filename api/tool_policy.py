"""Resolve optional toolsets without silently broadening agent capability."""

from dataclasses import dataclass
from functools import lru_cache


POLICIES = {"minimal", "inherit-profile", "explicit"}
MINIMAL_UNAVAILABLE = "minimal_toolset_not_supported"


@dataclass(frozen=True)
class ResolvedToolPolicy:
    requested: str
    toolsets: list[str]
    enforced: bool
    reason: str | None = None


def _toolsets(values):
    return [value for value in (values or []) if isinstance(value, str) and value]


def validate_tool_policy(policy):
    """Normalize a persisted/requested policy without accepting aliases."""
    if policy is None:
        return None
    if not isinstance(policy, str) or policy not in POLICIES:
        raise ValueError("tool_policy must be minimal, inherit-profile, explicit, or null")
    return policy


@lru_cache(maxsize=1)
def runtime_empty_toolsets_are_restrictive():
    """Verify the installed Agent preserves ``[]`` as an empty tool surface.

    ``None`` has historically meant "all available tools" in Hermes Agent, so
    this capability must be proven against the installed runtime instead of
    assumed from the WebUI's own resolver.  Any import/signature/runtime error
    is deliberately unavailable rather than permissive.
    """
    try:
        # Load through WebUI's agent-runtime seam so the Agent checkout is on
        # sys.path even in isolated server/test processes.
        from api.agent_runtime import get_ai_agent_class
        if get_ai_agent_class() is None:
            return False
        from model_tools import get_tool_definitions

        return not get_tool_definitions(
            enabled_toolsets=[],
            quiet_mode=True,
            skip_tool_search_assembly=True,
        )
    except Exception:
        return False


def resolve_tool_policy(policy, explicit_toolsets, profile_toolsets, *, empty_means_restrictive):
    """Return an exact optional-toolset decision for one agent run."""
    available = _toolsets(profile_toolsets)
    explicit = _toolsets(explicit_toolsets)
    requested = validate_tool_policy(policy) or "inherit-profile"

    if explicit:
        unknown = [toolset for toolset in explicit if toolset not in available]
        if unknown:
            raise ValueError(f"Unknown toolset: {unknown[0]}")
        return ResolvedToolPolicy("explicit", explicit, True)

    if requested == "minimal":
        if empty_means_restrictive:
            return ResolvedToolPolicy("minimal", [], True)
        return ResolvedToolPolicy("minimal", [], False, MINIMAL_UNAVAILABLE)

    if requested == "explicit":
        raise ValueError("Explicit tool policy requires at least one configured toolset")
    return ResolvedToolPolicy("inherit-profile", available, True)
