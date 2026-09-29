"""Regression coverage for Spaces refreshes when an SSHFS mount goes stale."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PANELS = (ROOT / "static" / "panels.js").read_text(encoding="utf-8")
NODE = shutil.which("node")


def _extract_async_function(source: str, name: str) -> str:
    marker = f"async function {name}("
    start = source.find(marker)
    assert start >= 0, f"{name} not found"
    depth = 0
    body_start = -1
    for idx in range(start, len(source)):
        if source[idx] == "{":
            depth += 1
            if body_start < 0:
                body_start = idx
        elif source[idx] == "}":
            depth -= 1
            if depth == 0 and body_start >= 0:
                return source[start : idx + 1]
    raise AssertionError(f"could not extract {name}")


def _run_node(script: str) -> dict:
    result = subprocess.run([NODE, "-e", script], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


@pytest.mark.skipif(NODE is None, reason="node is required")
def test_workspace_list_fetch_failure_keeps_last_successful_rows_and_marks_them_stale():
    """A transient status failure must not turn Spaces into an empty page."""
    load_workspace_list = _extract_async_function(PANELS, "loadWorkspaceList")
    script = f"""
let _workspaceList=[];
let calls=0;
async function api(){{
  calls++;
  if(calls===1)return {{workspaces:[{{path:'/workspace/remote/rp5',name:'RP5',kind:'remote'}}]}};
  throw new Error('RP5 status refresh timed out');
}}
function syncWorkspaceDisplays(){{}}
function syncTerminalButton(){{}}
{load_workspace_list}
(async()=>{{
  const first=await loadWorkspaceList();
  const failed=await loadWorkspaceList();
  process.stdout.write(JSON.stringify({{first,failed,cached:_workspaceList}}));
}})().catch(error=>{{console.error(error);process.exit(1);}});
"""
    result = _run_node(script)

    assert result["first"]["workspaces"][0]["name"] == "RP5"
    assert result["failed"]["workspaces"] == result["first"]["workspaces"]
    assert result["cached"] == result["first"]["workspaces"]
    assert result["failed"]["workspace_list_stale"] is True


def test_spaces_status_is_explicitly_a_local_mount_not_remote_reachability():
    """The UI must not call a local SSHFS mount health signal a remote connection."""
    detail = PANELS[PANELS.index("function _renderWorkspaceDetail"):PANELS.index("function _setWorkspaceHeaderButtons")]
    assert 'Mount status' in detail
    assert 'Connection</div>' not in detail


def test_spaces_panel_has_an_active_only_refresh_lifecycle():
    """A visible Spaces panel owns a refresh timer and stops it when hidden."""
    assert "function _syncWorkspacesPanelAutoRefresh" in PANELS
    sync = PANELS[PANELS.index("function _syncWorkspacesPanelAutoRefresh"):]
    sync = sync[:sync.index("\n}") + 2]
    assert "_currentPanel === 'workspaces'" in sync
    assert "document.hidden" in sync
    assert "setInterval" in sync
    assert "clearInterval" in sync
