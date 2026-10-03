"""Global workspace list is shared across profiles."""
import json


def test_workspaces_are_global_across_profiles(tmp_path, monkeypatch):
    from api import workspace as ws

    # Point the global file to temp so all file operations stay isolated.
    monkeypatch.setattr(ws, "_GLOBAL_WS_FILE", tmp_path / "workspaces.json")

    # Simulate profile A adding a workspace.
    ws.save_workspaces([{"path": "/mnt/c/Users/Z014/Documents/Obsidian-Vault", "name": "Vault"}])

    # Simulate profile B reading the list.
    loaded = ws.load_workspaces()

    assert len(loaded) == 1
    assert loaded[0]["path"] == "/mnt/c/Users/Z014/Documents/Obsidian-Vault"
    assert (tmp_path / "workspaces.json").exists()


def test_add_workspace_entry_if_missing_is_global(tmp_path, monkeypatch):
    from api import workspace as ws

    monkeypatch.setattr(ws, "_GLOBAL_WS_FILE", tmp_path / "workspaces.json")
    # Seed the global list with one entry so load_workspaces does not fall back.
    ws.save_workspaces([{"path": "/existing", "name": "Existing"}])

    ws.add_workspace_entry_if_missing("/workspace", "Workspace")
    ws.add_workspace_entry_if_missing("/workspace", "Workspace")  # idempotent

    loaded = ws.load_workspaces()
    paths = {entry["path"] for entry in loaded}
    assert paths == {"/existing", "/workspace"}


def test_legacy_per_profile_workspaces_are_merged_into_global(tmp_path, monkeypatch):
    from api import workspace as ws
    from api import profiles as _profiles_mod

    base = tmp_path / ".hermes"
    profiles_dir = base / "profiles"
    (profiles_dir / "coding-neuralwatt" / "webui_state").mkdir(parents=True)
    (profiles_dir / "coding-codex" / "webui_state").mkdir(parents=True)

    (profiles_dir / "coding-neuralwatt" / "webui_state" / "workspaces.json").write_text(
        json.dumps([{"path": "/mnt/c/Users/Z014/Documents/Obsidian-Vault", "name": "Vault"}]),
        encoding="utf-8",
    )
    (profiles_dir / "coding-codex" / "webui_state" / "workspaces.json").write_text(
        json.dumps([{"path": "/workspace", "name": "Workspace"}]),
        encoding="utf-8",
    )

    monkeypatch.setattr(ws, "_GLOBAL_WS_FILE", tmp_path / "workspaces.json")
    monkeypatch.setattr(_profiles_mod, "_DEFAULT_HERMES_HOME", base)

    loaded = ws.load_workspaces()
    paths = {entry["path"] for entry in loaded}

    assert "/mnt/c/Users/Z014/Documents/Obsidian-Vault" in paths
    assert "/workspace" in paths
    assert (tmp_path / "workspaces.json").exists()


def test_global_workspace_files_live_in_the_configured_state_dir():
    """Shared across profiles, but still under HERMES_WEBUI_STATE_DIR.

    STATE_DIR is process-global (not per profile), so it already gives every
    profile one list; deriving the path from the base Hermes home instead
    ignored HERMES_WEBUI_STATE_DIR and split saved workspaces and
    last_workspace.txt away from the rest of the WebUI state.
    """
    import api.config as config
    import api.workspace as ws

    assert ws._GLOBAL_WS_FILE == config.STATE_DIR / "workspaces.json"
    assert ws._profile_state_dir() == config.STATE_DIR
