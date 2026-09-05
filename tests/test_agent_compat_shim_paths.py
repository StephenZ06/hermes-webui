"""The repo does not import through hermes-agent's plugin-compat shims.

hermes-agent's Sep 2026 decomposition (its PR #102117) moved most internals
into ``<stem>_<topic>`` sibling modules. The old import paths keep resolving
through PLUGIN-COMPAT blocks until ``hermes_cli.plugin_compat``'s
``COMPAT_REMOVAL_DATE``, at which point, in that module's own words, "the
commit that added them is reverted". That date is a single global one for all
335 facades, so everything still on an old path breaks on the same day.

The shims exist for *external* plugins. This repo vendors the agent and can
follow it, and the agent says so itself -- ``compat_manifest.json`` carries the
note "scripts/check_compat_pointers.py forbids in-tree use". This test is that
rule applied to the WebUI.

It is worth having as a test rather than a one-off sweep because the WebUI runs
the agent in-process out of a checkout the update path force-resets, so the
agent's API moves on its own schedule rather than ours, and an import that
still resolves today is not evidence of anything. In one evening that drift
broke session-title sync silently (``set_auto_title_if_empty``, see
tests/test_state_sync_title_api_drift.py), took ``_ApprovalEntry`` out from
under six test files, and left nine production imports pointed at paths with a
nine-day fuse -- of which nothing was failing and nothing would have, until the
day they all stopped.

Reading the manifest rather than a hand-written list means this needs no
maintenance when the agent moves something new. It will simply start failing,
which is the point.
"""
import json
import os
import pathlib
import re
from collections import defaultdict

import pytest

REPO = pathlib.Path(__file__).parent.parent
AGENT = pathlib.Path(
    os.environ.get("HERMES_WEBUI_AGENT_DIR")
    or (pathlib.Path.home() / ".hermes" / "hermes-agent")
)
MANIFEST = AGENT / "compat_manifest.json"

pytestmark = pytest.mark.skipif(
    not MANIFEST.is_file(),
    reason="hermes-agent checkout has no compat_manifest.json (pre- or post-decomposition)",
)

# `from <facade> import a, b` / `from <facade> import (a, b)`. A shimmed name
# is only reachable by importing it off the facade, so this is the shape that
# matters; `import <facade>` followed by attribute access resolves the same way
# but is not used against these names in this repo.
_IMPORT = r"from\s+{}\s+import\s+(\([^)]*\)|[^\n(]+)"


def _manifest() -> dict:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    out = defaultdict(dict)
    for entry in data.get("entries", ()):
        out[entry["facade"]][entry["name"]] = entry.get("target", "?")
    return out


def _repo_sources():
    for sub in ("api", "tests"):
        for path in (REPO / sub).rglob("*.py"):
            if path.name == pathlib.Path(__file__).name:
                continue
            yield path, path.read_text(encoding="utf-8", errors="replace")


def test_no_repo_import_resolves_only_through_a_compat_shim():
    facades = _manifest()
    assert facades, "expected a non-empty compat manifest to check against"

    sources = list(_repo_sources())
    offenders = set()
    for facade, names in facades.items():
        pattern = re.compile(_IMPORT.format(re.escape(facade)))
        for path, src in sources:
            if facade not in src:          # cheap reject before the regex
                continue
            for match in pattern.finditer(src):
                imported = {
                    part.strip().split(" as ")[0].strip()
                    for part in match.group(1).strip("()").split(",")
                }
                for name in imported & set(names):
                    line = src[: match.start()].count("\n") + 1
                    offenders.add(
                        f"{path.relative_to(REPO)}:{line} imports {name!r} from "
                        f"{facade}; it lives in {names[name]}"
                    )

    assert not offenders, (
        "these imports resolve only through hermes-agent's plugin-compat shims, "
        "which are removed on COMPAT_REMOVAL_DATE:\n  "
        + "\n  ".join(sorted(offenders))
    )
