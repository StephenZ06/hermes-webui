"""End-of-turn docs check: only project edits without a handoff update count."""

import os
import time

from api.docs_check import docs_check


def _project(tmp_path):
    root = tmp_path / "site"
    (root / ".agent").mkdir(parents=True)
    handoff = root / ".agent" / "ECC_HANDOFF.md"
    handoff.write_text("# Handoff\n")
    old = time.time() - 600
    os.utime(handoff, (old, old))
    return root, handoff


def test_an_edit_without_a_handoff_update_is_flagged(tmp_path):
    root, _ = _project(tmp_path)
    calls = [{"name": "write_file", "args": {"path": "src/index.html"}},
             {"name": "patch", "args": {"mode": "patch", "patch": "*** Begin Patch\n*** Update File: src/app.js\n@@\n*** End Patch"}}]
    assert docs_check(root, calls, time.time() - 5) == {"stale": True, "files": 2}


def test_a_fresh_handoff_or_read_only_turns_or_agent_only_edits_are_not_flagged(tmp_path):
    root, handoff = _project(tmp_path)
    since = time.time() - 5
    assert docs_check(root, [{"name": "read_file", "args": {"path": "src/index.html"}}], since) is None
    assert docs_check(root, [{"name": "write_file", "args": {"path": ".agent/TASKS.md"}}], since) is None
    assert docs_check(root, [{"name": "write_file", "args": {"path": str(tmp_path / "elsewhere.txt")}}], since) is None
    handoff.write_text("# Handoff\nUpdated.\n")
    assert docs_check(root, [{"name": "write_file", "args": {"path": "src/index.html"}}], since) is None


def test_workspaces_without_a_handoff_are_never_checked(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert docs_check(plain, [{"name": "write_file", "args": {"path": "a.txt"}}], time.time() - 5) is None
    assert docs_check("", [], 0) is None
