# ── Skills security-scan bridge (read-only) ──
# hermes-agent already ships a complete static-analysis scanner for skills
# (tools/skills_guard.py: threat-pattern regexes, verdicts, trust levels) and
# an install-provenance ledger (tools/skills_hub.py: HubLockFile). WebUI has
# no scanner of its own — it imports the agent's in-process, the same way
# api/routes.py already does for tools.skills_tool / agent.skill_utils, since
# the agent source tree is mounted read-only into this container.
#
# Scope is deliberately scan-only: this module reports a verdict for a skill
# already installed locally. It does not install, browse a marketplace, or
# gate anything — that's the "full marketplace" scope the user explicitly
# did not want for v1 (see docs/HERMES_STUDIO_PARITY_PLAN.md, Security
# scanner section).
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _finding_to_dict(finding) -> dict:
    return {
        "pattern_id": finding.pattern_id,
        "severity": finding.severity,
        "category": finding.category,
        "file": finding.file,
        "line": finding.line,
        "match": finding.match,
        "description": finding.description,
    }


def _lookup_install_source(skill_name: str) -> str:
    """Best-effort provenance lookup via the hub's install lockfile.

    Falls back to "community" (the conservative default — any finding at
    all blocks under that trust level) when the skill wasn't installed via
    the hub, e.g. bundled/seeded skills or ones dropped in manually. There is
    no reliable way to distinguish those cases from this side, so we do not
    guess "builtin"/"trusted" without provenance to back it up.
    """
    try:
        from tools.skills_hub import HubLockFile

        entry = HubLockFile().get_installed(skill_name)
        if entry and entry.get("source"):
            return str(entry["source"])
    except Exception:
        logger.debug("Hub lockfile lookup unavailable for %s", skill_name, exc_info=True)
    return "community"


def scan_installed_skill(skill_dir: Path) -> dict:
    """Scan an already-installed skill directory and return a JSON-safe result.

    Raises ImportError if tools.skills_guard is not importable (caller should
    turn that into a clear 501/error response, not a crash — the agent
    source tree may not always be mounted, e.g. in local dev without Docker).

    Prefers scan_skill_cached() (content-hash-based caching) when the mounted
    hermes-agent source has it, but that's a newer addition — the source tree
    actually mounted into this container's deployment may predate it, so this
    falls back to the always-available scan_skill() (no caching, same result
    shape otherwise). Feature-detect rather than hard-pin to one API surface.
    """
    import tools.skills_guard as skills_guard

    source = _lookup_install_source(skill_dir.name)
    cached = False
    if hasattr(skills_guard, "scan_skill_cached"):
        result, provenance = skills_guard.scan_skill_cached(skill_dir, source=source)
        cached = not provenance.get("fresh", True)
    else:
        result = skills_guard.scan_skill(skill_dir, source=source)
    return {
        "skill_name": result.skill_name,
        "source": result.source,
        "trust_level": result.trust_level,
        "verdict": result.verdict,
        "findings": [_finding_to_dict(f) for f in result.findings],
        "scanned_at": result.scanned_at,
        "summary": result.summary,
        "cached": cached,
    }
