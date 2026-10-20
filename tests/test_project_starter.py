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


def _rejects(callable_, *args):
    try:
        callable_(*args)
    except project_starter.ProjectStarterError as exc:
        return str(exc)
    raise AssertionError(f"accepted {args!r}")


def test_folder_names_that_break_on_disk_or_hide_are_rejected(tmp_path: Path):
    for bad in (".hidden", "trailing.", "a:b", "what?", "con", "NUL.txt", "tab\tname"):
        _rejects(project_starter.create_starter_pack, tmp_path, bad, "blank", "")
    assert list(tmp_path.iterdir()) == []


def test_create_never_merges_into_a_folder_that_appears_late(tmp_path: Path, monkeypatch):
    # Simulate another process creating the folder after the existence check.
    real_exists = Path.exists
    monkeypatch.setattr(Path, "exists", lambda self: False if self.name == "late" else real_exists(self))
    (tmp_path / "late").mkdir()
    (tmp_path / "late" / "keep.txt").write_text("mine", encoding="utf-8")

    _rejects(project_starter.create_starter_pack, tmp_path, "late", "web", "")

    assert sorted(p.name for p in (tmp_path / "late").iterdir()) == ["keep.txt"]


def test_failed_adopt_removes_only_the_documents_it_added(tmp_path: Path, monkeypatch):
    project = tmp_path / "app"
    (project / "docs").mkdir(parents=True)
    (project / "docs" / "NOTES.md").write_text("keep", encoding="utf-8")
    real_write = project_starter._write
    calls = {"n": 0}

    def flaky(root, path, content):
        calls["n"] += 1
        if calls["n"] == 4:
            raise OSError("disk full")
        real_write(root, path, content)

    monkeypatch.setattr(project_starter, "_write", flaky)
    try:
        project_starter.adopt_starter_pack(project, "web", "")
    except OSError:
        pass
    else:
        raise AssertionError("write failure was swallowed")

    assert sorted(str(p.relative_to(project)) for p in project.rglob("*")) == ["docs", "docs/NOTES.md"]


def test_rollback_after_adopt_restores_the_original_folder(tmp_path: Path):
    project = tmp_path / "app"
    project.mkdir()
    (project / "README.md").write_text("# Keep me\n", encoding="utf-8")

    result = project_starter.adopt_starter_pack(project, "api", "")
    project_starter.rollback_adopted(project, result)

    assert sorted(p.name for p in project.iterdir()) == ["README.md"]


def test_a_folder_that_is_already_a_project_is_found(tmp_path: Path):
    project = tmp_path / "app"
    project.mkdir()
    projects = [{"project_id": "a", "name": "Other", "workspace_path": str(tmp_path / "other")},
                {"project_id": "b", "name": "App", "workspace_path": str(project) + "/"}]

    assert project_starter.project_using_path(projects, project)["project_id"] == "b"
    assert project_starter.project_using_path(projects, tmp_path / "new") is None


def test_select_popups_open_above_the_project_starter_modal():
    import re

    css = (Path(__file__).resolve().parents[1] / "static" / "style.css").read_text(encoding="utf-8")

    def z(selector):
        match = re.search(re.escape(selector) + r"\{[^}]*z-index:(\d+)", css)
        assert match, selector
        return int(match.group(1))

    assert z(".themed-select-popup") > z(".project-starter-overlay")
