"""Security scanner (Priority 1, scan-only scope) wiring guards.

Structural checks pinning the API/UI wiring together, plus one behavioral
test of the bridge module gated on hermes-agent's scanner actually being
importable (skipped otherwise — same class of test as the 30 other
agent-dependent tests this suite already skips in a hermes-agent-less
environment). See docs/HERMES_STUDIO_PARITY_PLAN.md, Security scanner
section: scope is scan-only for already-installed skills, no marketplace
browse/install path.
"""
from pathlib import Path
import re

import pytest

REPO = Path(__file__).resolve().parent.parent


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def test_bridge_module_shape():
    src = read("api/skills_hub_bridge.py")
    assert "def scan_installed_skill(skill_dir: Path) -> dict" in src
    assert "import tools.skills_guard as skills_guard" in src
    assert "from tools.skills_hub import HubLockFile" in src
    # Feature-detected rather than hard-pinned: the hermes-agent source tree
    # actually mounted in some deployments predates scan_skill_cached.
    assert 'hasattr(skills_guard, "scan_skill_cached")' in src
    assert "skills_guard.scan_skill(" in src
    # Conservative default when a skill has no hub install provenance.
    assert 'return "community"' in src


def test_route_wired_and_defensive():
    routes = read("api/routes.py")
    assert '"/api/skills/scan"' in routes
    idx = routes.index('"/api/skills/scan"')
    block = routes[idx: idx + 1200]
    assert "_find_skill_in_dirs(name, _active_skill_search_dirs(skills_dir))" in block
    assert 'return bad(handler, "Skill not found", 404)' in block
    assert "from api.skills_hub_bridge import scan_installed_skill" in block
    # Must not 500 when the agent source tree isn't mounted (local dev without
    # Docker) — degrade to a clear error instead of crashing the handler.
    assert "except ImportError:" in block
    assert "501" in block


def test_frontend_wiring():
    js = read("static/panels.js")
    assert "async function _loadSkillScan(name)" in js
    assert "function _renderSkillScan(scan)" in js
    assert "/api/skills/scan?name=" in js
    # Every path that repaints the security-section placeholder must also
    # re-trigger the fetch, or the card gets stuck on "Scanning…" forever.
    for anchor in (
        "_renderSkillDetail(name, data.content || '', data.linked_files || {});\n    _loadSkillScan(name);",
        "_renderSkillDetail(_currentSkillDetail.name, _currentSkillDetail.content, _currentSkillDetail.linked_files);\n          _loadSkillScan(_currentSkillDetail.name);",
        "_renderSkillDetail(snap.name, snap.content || '', snap.linked_files || {});\n    _loadSkillScan(snap.name);",
    ):
        assert anchor in js, f"missing rescan trigger: {anchor!r}"


def test_css_uses_theme_tokens_not_hardcoded_colors():
    css = read("static/style.css")
    assert ".skill-security-section" in css
    idx = css.index("/* Skill security scan card */")
    block = css[idx: idx + 2200]
    assert "var(--success)" in block
    assert "var(--warning)" in block
    assert "var(--error)" in block
    # No hex colors introduced by this feature block specifically.
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", block)


def test_i18n_keys_present_in_all_15_locales():
    src = read("static/i18n.js")
    required_keys = [
        "skill_security_scanning", "skill_security_verdict_safe",
        "skill_security_verdict_caution", "skill_security_verdict_dangerous",
        "skill_security_trust_builtin", "skill_security_trust_trusted",
        "skill_security_trust_community", "skill_security_trust_agent_created",
        "skill_security_unavailable",
    ]
    locale_keys = re.findall(r"^  (?:'([a-zA-Z-]+)'|([a-zA-Z-]+)): \{$", src, re.MULTILINE)
    locales = [a or b for a, b in locale_keys]
    assert len(locales) == 15, locales

    starts = [m.start() for m in re.finditer(r"^  (?:'[a-zA-Z-]+'|[a-zA-Z-]+): \{$", src, re.MULTILINE)]
    starts.append(len(src))
    for name, start, end in zip(locales, starts, starts[1:]):
        block = src[start:end]
        missing = [k for k in required_keys if f"{k}:" not in block]
        assert not missing, f"locale {name!r} missing keys: {missing}"


@pytest.mark.parametrize("verdict", ["safe", "caution", "dangerous"])
def test_verdict_badge_classes_present_for_every_verdict(verdict):
    js = read("static/panels.js")
    assert f"skill_security_verdict_{verdict}" in js
    css = read("static/style.css")
    assert f".skill-security-badge-{verdict}" in css


def test_scan_installed_skill_against_a_real_builtin_skill(tmp_path):
    """Behavioral check of the bridge against the real scanner.

    Skipped when hermes-agent's scanner isn't importable (matches this
    suite's existing convention for the ~30 other agent-dependent tests).
    """
    pytest.importorskip("tools.skills_guard")
    import sys
    sys.path.insert(0, str(REPO))
    from api.skills_hub_bridge import scan_installed_skill

    skill_dir = tmp_path / "harmless-test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: harmless-test-skill\ndescription: does nothing risky\n---\n"
        "# Harmless\nJust prints a greeting.\n",
        encoding="utf-8",
    )
    result = scan_installed_skill(skill_dir)
    assert result["skill_name"] == "harmless-test-skill"
    assert result["verdict"] == "safe"
    assert result["trust_level"] == "community"  # no hub lockfile entry → conservative default
    assert result["findings"] == []
    assert "scanned_at" in result
