"""The sidebar usage gauge refreshes after a terminal chat turn."""

from pathlib import Path


MESSAGES = (Path(__file__).parent.parent / "static" / "messages.js").read_text(encoding="utf-8")
UI = (Path(__file__).parent.parent / "static" / "ui.js").read_text(encoding="utf-8")


def test_usage_fetch_can_be_explicitly_forced_for_the_active_profile():
    assert "async function loadAccountUsage(profile, options={})" in UI
    assert "refresh=1" in UI


def test_terminal_stream_completion_forces_one_usage_refresh():
    done_handler = MESSAGES[MESSAGES.index("source.addEventListener('done'"):
                            MESSAGES.index("source.addEventListener('error'", MESSAGES.index("source.addEventListener('done'"))]
    assert "refreshAccountUsageAfterTerminalTurn" in done_handler


def test_usage_widget_ignores_a_late_response_for_a_previous_profile():
    assert "let _accountUsageRequestGeneration=0;" in UI
    assert "const requestGeneration=++_accountUsageRequestGeneration;" in UI
    assert "if(requestGeneration!==_accountUsageRequestGeneration) return;" in UI
