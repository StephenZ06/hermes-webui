"""Profile-switch interaction-path contracts."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_profile_switch_marks_usable_before_waiting_for_session_refresh():
    source = (ROOT / "static/panels.js").read_text(encoding="utf-8")
    switch = source.split("async function switchToProfile(name)", 1)[1].split("function openProfileCreate", 1)[0]

    assert "HermesPerformance.begin('profile', name)" in switch
    assert "HermesPerformance.mark(profileTicket, 'usable')" in switch
    assert switch.index("HermesPerformance.mark(profileTicket, 'usable')") < switch.index("await renderSessionList()")
