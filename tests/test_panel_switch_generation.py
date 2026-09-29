"""Regression contracts for stale panel transitions."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_new_panel_intent_invalidates_a_pending_different_panel_load():
    source = read("static/performance.js")
    script = f"""
const fs = require('fs');
global.window = global;
global.performance = {{ now: () => 1, mark: () => {{}} }};
eval(fs.readFileSync({str(ROOT / 'static/performance.js')!r}, 'utf8'));
const first = HermesPerformance.begin('panel', 'tasks');
const second = HermesPerformance.begin('panel', 'notes');
process.stdout.write(JSON.stringify({{ first: HermesPerformance.isCurrent(first), second: HermesPerformance.isCurrent(second) }}));
"""

    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)

    assert result.stdout == '{"first":false,"second":true}'


def test_switch_panel_starts_marks_and_guards_the_current_panel_ticket():
    source = read("static/panels.js")

    assert "HermesPerformance.begin('panel', nextPanel)" in source
    assert "HermesPerformance.mark(panelTicket, 'usable')" in source
    assert "!panelTicketIsCurrent()) return false" in source
