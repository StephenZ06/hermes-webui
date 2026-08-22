from pathlib import Path

import pytest

import api.project_registry as project_registry


def _write_registry(path: Path, yaml_text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml_text, encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_scope_filtering_by_default(monkeypatch):
    """Disable project-scope filtering unless a test explicitly opts in.

    Scope filtering (see the "Project scope filtering" tests below) is an
    orthogonal WebUI-picker concern layered on top of registry parsing —
    every other test in this file uses arbitrary tmp_path locations that
    would otherwise be silently filtered out by the real default scope
    roots (/workspace/MiniPC-Main, /workspace/rp5). A test that wants scope
    filtering sets HERMES_WEBUI_PROJECT_SCOPE_ROOTS itself, which still
    takes priority over this default override.
    """
    monkeypatch.setattr(project_registry, "_DEFAULT_PROJECT_SCOPE_ROOTS", ())


def test_list_registry_projects_missing_file_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(project_registry, "WORKSPACES_REGISTRY_FILE", tmp_path / "missing.yaml")

    assert project_registry.list_registry_projects() == []


def test_list_registry_projects_normalizes_local_and_ssh(monkeypatch, tmp_path):
    local_repo = tmp_path / "confirmed-repo"
    local_repo.mkdir()
    registry_file = tmp_path / "WORKSPACES.yaml"
    _write_registry(
        registry_file,
        f"""
version: 1
projects:
  confirmed:
    repo_path: {local_repo}
    access_mode: local
    status: confirmed project root
    required_docs:
      - .hermes.md

  remote-project:
    access_mode: ssh
    status: confirmed project root
    ssh:
      target: user@host
      key: /keys/id_rsa
      remote_path: /srv/app

  candidate:
    repo_path: NEEDS_CONFIRMATION
    candidate_path: {tmp_path / "candidate"}
    status: candidate directory is empty; project root not confirmed
""",
    )
    monkeypatch.setattr(project_registry, "WORKSPACES_REGISTRY_FILE", registry_file)

    projects = {p["key"]: p for p in project_registry.list_registry_projects()}

    assert projects["confirmed"]["available"] is True
    assert projects["confirmed"]["repo_path"] == str(local_repo)
    assert projects["confirmed"]["required_docs"] == [".hermes.md"]

    assert projects["remote-project"]["available"] is True
    assert projects["remote-project"]["access_mode"] == "ssh"
    assert projects["remote-project"]["ssh"] == {
        "target": "user@host",
        "key": "/keys/id_rsa",
        "remote_path": "/srv/app",
    }

    assert projects["candidate"]["available"] is False
    assert "not confirmed" in projects["candidate"]["unavailable_reason"]


def test_list_registry_projects_local_path_missing_on_disk_is_unavailable(monkeypatch, tmp_path):
    registry_file = tmp_path / "WORKSPACES.yaml"
    missing_repo = tmp_path / "does-not-exist"
    _write_registry(
        registry_file,
        f"""
projects:
  ghost:
    repo_path: {missing_repo}
    access_mode: local
    status: confirmed project root
""",
    )
    monkeypatch.setattr(project_registry, "WORKSPACES_REGISTRY_FILE", registry_file)

    project = project_registry.resolve_registry_project("ghost")

    assert project["available"] is False
    assert "does not exist" in project["unavailable_reason"]


def test_list_registry_projects_ssh_missing_config_is_unavailable(monkeypatch, tmp_path):
    registry_file = tmp_path / "WORKSPACES.yaml"
    _write_registry(
        registry_file,
        """
projects:
  half-configured:
    access_mode: ssh
    status: confirmed project root
    ssh:
      target: user@host
""",
    )
    monkeypatch.setattr(project_registry, "WORKSPACES_REGISTRY_FILE", registry_file)

    project = project_registry.resolve_registry_project("half-configured")

    assert project["available"] is False
    assert "ssh config missing" in project["unavailable_reason"]


def test_resolve_registry_project_unknown_key_returns_none(monkeypatch, tmp_path):
    registry_file = tmp_path / "WORKSPACES.yaml"
    _write_registry(registry_file, "projects: {}\n")
    monkeypatch.setattr(project_registry, "WORKSPACES_REGISTRY_FILE", registry_file)

    assert project_registry.resolve_registry_project("nope") is None


def test_read_project_lifecycle_skill_text_missing_file_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(
        project_registry, "PROJECT_LIFECYCLE_SKILL_FILE", tmp_path / "missing" / "SKILL.md"
    )

    assert project_registry.read_project_lifecycle_skill_text() is None


def test_read_project_lifecycle_skill_text_reads_file(monkeypatch, tmp_path):
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("# Project Lifecycle\n\nBody text.", encoding="utf-8")
    monkeypatch.setattr(project_registry, "PROJECT_LIFECYCLE_SKILL_FILE", skill_file)

    assert "Body text." in project_registry.read_project_lifecycle_skill_text()


# ── Real-world WORKSPACES.yaml schema shapes ────────────────────────────
# These pin the actual authoring conventions used by the agent-side registry
# tooling, discovered by diffing this module's assumptions against a real
# registry file: SSH config as flat top-level keys (not nested under `ssh:`),
# access_mode often omitted for local projects, and NEEDS_* sentinel values
# other than NEEDS_CONFIRMATION (e.g. NEEDS_REMOTE_ACCESS for SSH-only
# projects with no local repo_path).


def test_ssh_config_read_from_flat_top_level_keys(monkeypatch, tmp_path):
    registry_file = tmp_path / "WORKSPACES.yaml"
    _write_registry(
        registry_file,
        """
projects:
  ai-honeypot:
    display_name: Synapse AI Honeypot
    access_mode: ssh
    ssh_target: zola@192.168.18.80
    ssh_key: /opt/data/home/.ssh/hermes_rp5
    remote_path: /home/zola/Documents/CyberProjects/AI-Honeypot/ai-honeypot
    repo_path: NEEDS_REMOTE_ACCESS
""",
    )
    monkeypatch.setattr(project_registry, "WORKSPACES_REGISTRY_FILE", registry_file)

    project = project_registry.resolve_registry_project("ai-honeypot")

    assert project["name"] == "Synapse AI Honeypot"
    assert project["available"] is True
    assert project["access_mode"] == "ssh"
    assert project["ssh"] == {
        "target": "zola@192.168.18.80",
        "key": "/opt/data/home/.ssh/hermes_rp5",
        "remote_path": "/home/zola/Documents/CyberProjects/AI-Honeypot/ai-honeypot",
    }
    # NEEDS_REMOTE_ACCESS is a placeholder, not a real path.
    assert project["repo_path"] is None


def test_missing_access_mode_infers_local_when_repo_path_confirmed(monkeypatch, tmp_path):
    repo = tmp_path / "triple-s-pos"
    repo.mkdir()
    registry_file = tmp_path / "WORKSPACES.yaml"
    _write_registry(
        registry_file,
        f"""
projects:
  triple-s:
    repo_path: {repo}
    status: confirmed project root
""",
    )
    monkeypatch.setattr(project_registry, "WORKSPACES_REGISTRY_FILE", registry_file)

    project = project_registry.resolve_registry_project("triple-s")

    assert project["access_mode"] == "local"
    assert project["available"] is True
    assert project["repo_path"] == str(repo)


def test_missing_access_mode_infers_ssh_from_ssh_target(monkeypatch, tmp_path):
    registry_file = tmp_path / "WORKSPACES.yaml"
    _write_registry(
        registry_file,
        """
projects:
  implicit-ssh:
    ssh_target: user@host
    ssh_key: /keys/id_rsa
    remote_path: /srv/app
""",
    )
    monkeypatch.setattr(project_registry, "WORKSPACES_REGISTRY_FILE", registry_file)

    project = project_registry.resolve_registry_project("implicit-ssh")

    assert project["access_mode"] == "ssh"
    assert project["available"] is True


def test_no_repo_path_and_no_ssh_config_is_unknown_access_mode(monkeypatch, tmp_path):
    registry_file = tmp_path / "WORKSPACES.yaml"
    _write_registry(
        registry_file,
        """
projects:
  bare:
    status: some status
""",
    )
    monkeypatch.setattr(project_registry, "WORKSPACES_REGISTRY_FILE", registry_file)

    project = project_registry.resolve_registry_project("bare")

    assert project["access_mode"] is None
    assert project["available"] is False
    assert "unknown access_mode" in project["unavailable_reason"]


# ── Project scope filtering (WebUI-only picker restriction) ────────────


def test_scope_excludes_projects_outside_configured_roots(monkeypatch, tmp_path):
    in_scope_repo = tmp_path / "workspace" / "MiniPC-Main" / "job-os"
    in_scope_repo.mkdir(parents=True)
    out_of_scope_repo = tmp_path / "workspace" / "hermes-core-custom"
    out_of_scope_repo.mkdir(parents=True)
    registry_file = tmp_path / "WORKSPACES.yaml"
    _write_registry(
        registry_file,
        f"""
projects:
  job-os:
    repo_path: {in_scope_repo}
    access_mode: local
    status: confirmed project root
  hermes-core-custom:
    repo_path: {out_of_scope_repo}
    access_mode: local
    status: approved local Hermes core source checkout
""",
    )
    monkeypatch.setattr(project_registry, "WORKSPACES_REGISTRY_FILE", registry_file)
    monkeypatch.setenv(
        "HERMES_WEBUI_PROJECT_SCOPE_ROOTS", f"{tmp_path / 'workspace' / 'MiniPC-Main'},{tmp_path / 'workspace' / 'rp5'}"
    )

    keys = {p["key"] for p in project_registry.list_registry_projects()}

    assert keys == {"job-os"}


def test_scope_keeps_unconfirmed_project_in_scope_via_candidate_path(monkeypatch, tmp_path):
    scope_root = tmp_path / "workspace" / "MiniPC-Main"
    scope_root.mkdir(parents=True)
    registry_file = tmp_path / "WORKSPACES.yaml"
    _write_registry(
        registry_file,
        f"""
projects:
  saas:
    repo_path: NEEDS_CONFIRMATION
    candidate_path: {scope_root / "Business" / "SaaS"}
    status: candidate directory is empty; project root not confirmed
""",
    )
    monkeypatch.setattr(project_registry, "WORKSPACES_REGISTRY_FILE", registry_file)
    monkeypatch.setenv("HERMES_WEBUI_PROJECT_SCOPE_ROOTS", f"{scope_root},{tmp_path / 'workspace' / 'rp5'}")

    project = project_registry.resolve_registry_project("saas")

    # Still surfaced (in scope via candidate_path) so the picker can show
    # WHY it can't be bound yet, rather than silently vanishing.
    assert project is not None
    assert project["available"] is False


def test_scope_drops_project_with_no_local_path_at_all(monkeypatch, tmp_path):
    scope_root = tmp_path / "workspace" / "rp5"
    scope_root.mkdir(parents=True)
    registry_file = tmp_path / "WORKSPACES.yaml"
    _write_registry(
        registry_file,
        """
projects:
  ai-honeypot:
    access_mode: ssh
    ssh_target: user@host
    ssh_key: /keys/id_rsa
    remote_path: /home/user/ai-honeypot
    repo_path: NEEDS_REMOTE_ACCESS
""",
    )
    monkeypatch.setattr(project_registry, "WORKSPACES_REGISTRY_FILE", registry_file)
    monkeypatch.setenv("HERMES_WEBUI_PROJECT_SCOPE_ROOTS", f"{tmp_path / 'workspace' / 'MiniPC-Main'},{scope_root}")

    assert project_registry.resolve_registry_project("ai-honeypot") is None


def test_scope_roots_unset_env_means_no_filtering(monkeypatch, tmp_path):
    repo = tmp_path / "anywhere"
    repo.mkdir()
    registry_file = tmp_path / "WORKSPACES.yaml"
    _write_registry(
        registry_file,
        f"""
projects:
  anywhere-project:
    repo_path: {repo}
    access_mode: local
    status: confirmed project root
""",
    )
    monkeypatch.setattr(project_registry, "WORKSPACES_REGISTRY_FILE", registry_file)
    monkeypatch.delenv("HERMES_WEBUI_PROJECT_SCOPE_ROOTS", raising=False)
    monkeypatch.setattr(project_registry, "_DEFAULT_PROJECT_SCOPE_ROOTS", ())

    keys = {p["key"] for p in project_registry.list_registry_projects()}

    assert keys == {"anywhere-project"}
