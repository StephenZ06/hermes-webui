"""Skills page "+" menu: GitHub link parsing, category folders, the import
runner's command line, and the agent core-dependency healer used at start."""

import subprocess
import sys
from pathlib import Path

import pytest

from api import skill_import

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("link,expected", [
    ("https://github.com/anthropics/skills/tree/main/skills/pdf", "anthropics/skills/skills/pdf"),
    ("https://github.com/anthropics/skills/blob/main/skills/pdf/SKILL.md", "anthropics/skills/skills/pdf"),
    ("https://github.com/owner/repo", "owner/repo"),
    ("https://github.com/owner/repo.git", "owner/repo"),
    ("https://raw.githubusercontent.com/o/r/main/x/SKILL.md", "https://raw.githubusercontent.com/o/r/main/x/SKILL.md"),
])
def test_github_links_become_installer_sources(link, expected):
    assert skill_import.skill_source_from_link(link) == expected


@pytest.mark.parametrize("link", [
    "", "http://github.com/o/r", "https://gitlab.com/o/r", "https://github.com/o",
    "https://github.com/o/r/issues/1", "https://raw.githubusercontent.com/o/r/main/README.md",
    "https://github.com/o/r/tree/main/a b", "file:///etc/passwd", "--force",
])
def test_anything_but_a_github_skill_link_is_refused(link):
    with pytest.raises(ValueError):
        skill_import.skill_source_from_link(link)


def test_category_names_are_slugged_and_checked():
    assert skill_import.normalize_category("  My Research ") == "my-research"
    assert skill_import.normalize_category("") == ""
    for bad in ("../x", "a/b", ".hidden", "x" * 49, "--force"):
        with pytest.raises(ValueError):
            skill_import.normalize_category(bad)


def test_a_new_category_is_a_folder_with_a_description_and_is_listed(tmp_path):
    skill_import.create_category(tmp_path, "research", "Finding and checking sources")
    assert (tmp_path / "research" / "DESCRIPTION.md").read_text().strip() == "Finding and checking sources"
    skill_import.create_category(tmp_path, "ops")
    assert (tmp_path / "ops" / "DESCRIPTION.md").read_text().strip() == "Ops skills."
    (tmp_path / "plain-folder").mkdir()  # not a category without DESCRIPTION.md
    assert skill_import.local_categories(tmp_path) == ["ops", "research"]
    with pytest.raises(FileExistsError):
        skill_import.create_category(tmp_path, "ops")


def test_install_runs_the_hermes_cli_for_the_active_profile(monkeypatch, tmp_path):
    calls = []

    class Done:
        returncode = 0
        stdout = "\x1b[1mInstalled\x1b[0m pdf"
        stderr = ""

    monkeypatch.setattr(skill_import, "_gateway_restart_profile_context", lambda: (tmp_path, "work"))
    monkeypatch.setattr(skill_import, "_resolve_hermes_command", lambda: "/bin/hermes")
    monkeypatch.setattr(skill_import.subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw)) or Done())
    result = skill_import.install_skill("anthropics/skills/skills/pdf", "research")
    cmd, kw = calls[0]
    assert cmd == ["/bin/hermes", "--profile", "work", "skills", "install", "anthropics/skills/skills/pdf", "--yes", "--category", "research"]
    assert kw["env"]["HERMES_HOME"] == str(tmp_path) and kw["timeout"] == skill_import.INSTALL_TIMEOUT_SECONDS
    assert result == {"ok": True, "status": "installed", "output": "Installed pdf"}

    Done.stdout, Done.returncode = "Warning: 'pdf' is already installed at x", 0
    assert skill_import.install_skill("a/b/c")["status"] == "exists"
    Done.stdout, Done.returncode = "Blocked by scan", 1
    assert skill_import.install_skill("a/b/c") == {"ok": False, "status": "failed", "output": "Blocked by scan"}


PYPROJECT = '''
[project]
name = "x"
dependencies = [
  "pip==99.0; python_version >= '3.14'",
  "definitely-not-installed-pkg==1.2.3; python_version >= '3.14'",
  "other-missing-pkg[extra]>=1,<2; python_version >= '3.14' and sys_platform == 'nonexistent-os'",
  "third-missing-pkg==0.1",
]
'''


def test_core_dependency_healer_lists_only_missing_pins_and_ignores_the_314_gate(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(PYPROJECT)
    out = subprocess.run([sys.executable, str(REPO / "scripts" / "ensure_agent_core_deps.py"), str(pyproject)],
                         capture_output=True, text=True, check=True).stdout.split()
    # pip is installed (left alone whatever its version); a platform marker that fails still excludes.
    assert out == ["definitely-not-installed-pkg==1.2.3", "third-missing-pkg==0.1"]


def test_docker_start_heals_agent_core_dependencies_without_failing_startup():
    text = (REPO / "docker_init.bash").read_text()
    body = text.split("ensure_agent_runtime_imports() {", 1)[1].split("\n}\n", 1)[0]
    assert "scripts/ensure_agent_core_deps.py" in body
    assert "error_exit" not in body  # a dependency that will not install never stops the WebUI
    assert text.count("\nensure_agent_runtime_imports\n") == 1
