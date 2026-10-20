"""Project starter packs must stay inside a selected trusted workspace."""

from pathlib import Path

from api import project_starter


def test_web_starter_writes_a_personalised_project_context(tmp_path: Path):
    result = project_starter.create_starter_pack(
        workspace_root=tmp_path,
        folder_name="orbit-dashboard",
        template="web",
        brief="A dashboard that helps a small SaaS team understand customer health.",
    )

    root = tmp_path / "orbit-dashboard"
    assert result["path"] == str(root)
    assert (root / "AGENTS.md").is_file()
    assert (root / ".agent" / "ECC_HANDOFF.md").is_file()
    assert (root / "docs" / "ARCHITECTURE.md").is_file()
    assert "customer health" in (root / "docs" / "PRODUCT.md").read_text(encoding="utf-8")
    assert "ECC_HANDOFF.md" in (root / "AGENTS.md").read_text(encoding="utf-8")


def test_starter_rejects_an_unsafe_or_existing_folder(tmp_path: Path):
    (tmp_path / "existing").mkdir()

    try:
        project_starter.create_starter_pack(tmp_path, "../escape", "blank", "")
    except project_starter.ProjectStarterError as exc:
        assert "folder name" in str(exc).lower()
    else:
        raise AssertionError("unsafe folder name was accepted")

    try:
        project_starter.create_starter_pack(tmp_path, "existing", "blank", "")
    except project_starter.ProjectStarterError as exc:
        assert "already exists" in str(exc).lower()
    else:
        raise AssertionError("existing folder was overwritten")


def test_adopting_an_existing_project_only_adds_missing_docs(tmp_path: Path):
    project = tmp_path / "existing-app"
    project.mkdir()
    (project / "README.md").write_text("# Keep me\n", encoding="utf-8")

    result = project_starter.adopt_starter_pack(project, "ios", "A focused iPhone app.")

    assert result["path"] == str(project)
    assert (project / "AGENTS.md").is_file()
    assert (project / "docs" / "IOS.md").is_file()
    assert (project / "README.md").read_text(encoding="utf-8") == "# Keep me\n"
