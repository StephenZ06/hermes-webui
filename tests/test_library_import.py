"""Library import: any link is fetched into staging and only read."""

import subprocess

import pytest

from api import library_import as li


def _bare_repo(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "README.md").write_text("# Calm UI\nSoft React animations.")
    (work / "package.json").write_text('{"name":"calm-ui","peerDependencies":{"react":"^18"}}')
    (work / "src").mkdir()
    (work / "src" / "fade.tsx").write_text("export const Fade = () => null")
    # A postinstall script that must never run.
    (work / "install.sh").write_text("touch PWNED")
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"]):
        subprocess.run(cmd, cwd=work, check=True)
    return work


def test_a_git_link_is_shallow_cloned_and_gathered(tmp_path):
    repo = _bare_repo(tmp_path)
    dest = tmp_path / "stage"
    info = li.fetch_source(f"file://{repo}", dest)
    assert info["mode"] == "git"
    got = li.gather(dest)
    assert "Calm UI" in got["readme"] and "calm-ui" in got["package_json"]
    assert "src/fade.tsx" in got["tree"] and ".git" not in " ".join(got["tree"])
    assert not (dest / "source" / ".git").exists()  # history is dropped
    assert not list(tmp_path.rglob("PWNED"))


def test_a_non_git_link_becomes_page_text(tmp_path, monkeypatch):
    monkeypatch.setattr(li, "_is_git", lambda link: False)
    monkeypatch.setattr(li, "_fetch_page", lambda link: "<html><title>Docs</title><p>Bold cards</p></html>")
    dest = tmp_path / "stage"
    assert li.fetch_source("https://example.com/ui", dest)["mode"] == "page"
    assert "Bold cards" in li.gather(dest)["page"] and "<p>" not in li.gather(dest)["page"]


@pytest.mark.parametrize("link", ["", "   ", "--upload-pack=touch x", "-x"])
def test_empty_links_and_option_lookalikes_are_refused(tmp_path, link):
    with pytest.raises(ValueError):
        li.fetch_source(link, tmp_path / "stage")


def test_gather_caps_large_text(tmp_path):
    dest = tmp_path / "stage"
    (dest / "source").mkdir(parents=True)
    (dest / "source" / "README.md").write_text("x" * 50000)
    assert len(li.gather(dest)["readme"]) == 20000
