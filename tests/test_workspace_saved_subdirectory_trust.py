"""A saved workspace is a root: its subdirectories must be trusted too.

Reported: creating a new conversation with a workspace nested inside an
already-saved workspace failed with

    Path is outside the user home directory, not in the saved workspace list,
    and not under the default workspace: /mnt/c/.../MiniPC-Main/Business/
    Triple_S/Triple_S_POS. Add it via Settings -> Workspaces first.

...even though /mnt/c/.../MiniPC-Main was saved. The saved-workspace check in
`resolve_trusted_workspace` compared with exact set membership
(`candidate in saved_paths`), unlike the user-home check and the boot-default
check, which both use a subpath (`relative_to`) test.

These tests pin both halves: descendants of a saved root are trusted, and
nothing else becomes trusted as a side effect.
"""
import pytest

from api.workspace import resolve_trusted_workspace


def _isolate(monkeypatch, ws_mod, tmp_path, saved_root):
    """Trust nothing by default except the saved root under test."""
    boot_default = tmp_path / "data" / "workspace"
    boot_default.mkdir(parents=True, exist_ok=True)
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(ws_mod, "_BOOT_DEFAULT_WORKSPACE", str(boot_default))
    monkeypatch.setattr(ws_mod, "_home_path", lambda: home)
    monkeypatch.setattr(
        ws_mod, "load_workspaces", lambda: [{"path": str(saved_root), "name": "MiniPC-Main"}]
    )
    return boot_default, home


def test_subdirectory_of_saved_workspace_is_trusted(monkeypatch, tmp_path):
    """The reported case: a nested project folder under a saved workspace."""
    import api.workspace as ws_mod

    saved_root = tmp_path / "MiniPC-Main"
    nested = saved_root / "Business" / "Triple_S" / "Triple_S_POS"
    nested.mkdir(parents=True)
    _isolate(monkeypatch, ws_mod, tmp_path, saved_root)

    assert resolve_trusted_workspace(str(nested)) == nested.resolve()


def test_saved_workspace_root_itself_is_still_trusted(monkeypatch, tmp_path):
    """Exact equality with a saved root must keep working."""
    import api.workspace as ws_mod

    saved_root = tmp_path / "MiniPC-Main"
    saved_root.mkdir(parents=True)
    _isolate(monkeypatch, ws_mod, tmp_path, saved_root)

    assert resolve_trusted_workspace(str(saved_root)) == saved_root.resolve()


def test_sibling_sharing_a_prefix_is_not_trusted(monkeypatch, tmp_path):
    """A lookalike sibling must be rejected — this is why the check uses
    `relative_to` rather than string-prefix matching."""
    import api.workspace as ws_mod

    saved_root = tmp_path / "MiniPC-Main"
    saved_root.mkdir(parents=True)
    sibling = tmp_path / "MiniPC-Main-Backup"
    sibling.mkdir(parents=True)
    _isolate(monkeypatch, ws_mod, tmp_path, saved_root)

    with pytest.raises(ValueError, match="outside the user home"):
        resolve_trusted_workspace(str(sibling))


def test_traversal_escaping_a_saved_workspace_is_rejected(monkeypatch, tmp_path):
    """`saved_root/../private` resolves outside the root and must still be
    rejected, so trusting descendants does not open a traversal hole."""
    import api.workspace as ws_mod

    saved_root = tmp_path / "MiniPC-Main"
    saved_root.mkdir(parents=True)
    outside = tmp_path / "private"
    outside.mkdir(parents=True)
    _isolate(monkeypatch, ws_mod, tmp_path, saved_root)

    with pytest.raises(ValueError, match="outside the user home"):
        resolve_trusted_workspace(str(saved_root / ".." / "private"))


def test_saved_filesystem_root_does_not_trust_everything(monkeypatch, tmp_path):
    """A saved "/" entry must not become blanket trust for anything unblocked."""
    import api.workspace as ws_mod
    from pathlib import Path

    outside = tmp_path / "elsewhere"
    outside.mkdir(parents=True)
    _isolate(monkeypatch, ws_mod, tmp_path, Path("/"))

    with pytest.raises(ValueError, match="outside the user home"):
        resolve_trusted_workspace(str(outside))


def test_parent_of_a_saved_workspace_is_not_trusted(monkeypatch, tmp_path):
    """Trust flows downward only: the parent of a saved root stays rejected."""
    import api.workspace as ws_mod

    saved_root = tmp_path / "MiniPC-Main"
    saved_root.mkdir(parents=True)
    _isolate(monkeypatch, ws_mod, tmp_path, saved_root)

    with pytest.raises(ValueError, match="outside the user home"):
        resolve_trusted_workspace(str(tmp_path))


def test_missing_subdirectory_of_saved_workspace_is_trusted(monkeypatch, tmp_path):
    """A project folder under a saved root may not exist yet; it should still be
    trusted so the agent can create it on demand."""
    import api.workspace as ws_mod

    saved_root = tmp_path / "MiniPC-Main"
    saved_root.mkdir(parents=True)
    nested = saved_root / "Business" / "SaaS" / "Temani"
    _isolate(monkeypatch, ws_mod, tmp_path, saved_root)

    assert resolve_trusted_workspace(str(nested)) == nested.resolve()


def test_missing_subdirectory_of_boot_default_is_trusted(monkeypatch, tmp_path):
    """A missing subdirectory of the boot default is allowed too."""
    import api.workspace as ws_mod

    saved_root = tmp_path / "MiniPC-Main"
    saved_root.mkdir(parents=True)
    _isolate(monkeypatch, ws_mod, tmp_path, saved_root)
    boot_default = tmp_path / "data" / "workspace"
    nested = boot_default / "Projects" / "NewProject"

    assert resolve_trusted_workspace(str(nested)) == nested.resolve()


def test_missing_path_outside_trusted_roots_is_rejected(monkeypatch, tmp_path):
    """A missing path that is not under any trusted root is still rejected."""
    import api.workspace as ws_mod

    saved_root = tmp_path / "MiniPC-Main"
    saved_root.mkdir(parents=True)
    # Ensure the outside dir does not exist.
    outside = tmp_path / "outside" / "missing"
    _isolate(monkeypatch, ws_mod, tmp_path, saved_root)

    with pytest.raises(ValueError, match="Path does not exist"):
        resolve_trusted_workspace(str(outside))
