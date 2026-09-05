"""The repo does not import through hermes-agent's plugin-compat shim.

`tools/approval.py` keeps a `_PLUGIN_COMPAT_LAZY` map of names that moved to
sibling modules. Importing one still works, but emits

    hermes plugin compat: `tools.approval.X` moved to `tools.approval_context.X`.
    The old path is kept only for external plugins and is removed on
    2026-09-14; update your import.

That shim exists for third-party plugins, not for this repo, which vendors the
agent and can follow it. Two things make importing through it a bad bet here:
the WebUI runs the agent in-process out of a checkout the update path
force-resets, so the removal lands on its own schedule rather than ours; and
this exact failure mode has already bitten twice in one evening -- once when
`set_auto_title_if_empty` went (silently, see
tests/test_state_sync_title_api_drift.py) and once when `_ApprovalEntry` moved
to `tools.approval_gateway_wait` without a shim entry at all, because private
names do not get one.

So this reads the agent's own map and asserts the repo imports from the real
home of every name in it. It needs no updating when the agent moves something
new -- it will just start failing, which is the point.
"""
import ast
import os
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).parent.parent
AGENT = pathlib.Path(
    os.environ.get("HERMES_WEBUI_AGENT_DIR")
    or (pathlib.Path.home() / ".hermes" / "hermes-agent")
)
APPROVAL = AGENT / "tools" / "approval.py"

pytestmark = pytest.mark.skipif(
    not APPROVAL.is_file(), reason="hermes-agent checkout not present"
)


def _compat_map() -> dict:
    """`_PLUGIN_COMPAT_LAZY` read from source, so the agent need not import."""
    tree = ast.parse(APPROVAL.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(getattr(t, "id", None) == "_PLUGIN_COMPAT_LAZY" for t in node.targets):
            return ast.literal_eval(node.value)
    pytest.skip("_PLUGIN_COMPAT_LAZY not found — the shim may itself be gone")


def _repo_sources():
    for sub in ("api", "tests"):
        for p in (REPO / sub).rglob("*.py"):
            if p.name == pathlib.Path(__file__).name:
                continue
            yield p, p.read_text(encoding="utf-8", errors="replace")


def test_no_repo_import_goes_through_the_compat_shim():
    moved = _compat_map()
    assert moved, "expected a non-empty compat map to check against"

    offenders = []
    for path, src in _repo_sources():
        for name, (real_module, _attr) in moved.items():
            # `from tools.approval import ... name ...`, single or parenthesised.
            for m in re.finditer(
                r"from\s+tools\.approval\s+import\s+(\([^)]*\)|[^\n(]+)", src
            ):
                imported = {
                    part.strip().split(" as ")[0].strip()
                    for part in m.group(1).strip("()").split(",")
                }
                if name in imported:
                    line = src[: m.start()].count("\n") + 1
                    offenders.append(
                        f"{path.relative_to(REPO)}:{line} imports {name!r} from "
                        f"tools.approval; it lives in {real_module}"
                    )

    assert not offenders, (
        "these imports resolve only through the removal-dated plugin-compat "
        "shim:\n  " + "\n  ".join(sorted(set(offenders)))
    )
