"""Library import: any link is fetched into staging and only read."""

import subprocess
from pathlib import Path

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


DRAFT = """Here you go:
{"slug": "Calm UI", "library": {"name": "Calm UI", "license": "MIT", "kind": "npm",
 "frameworks": ["react", "angular"], "tailwind": false, "install": "npm i calm-ui"},
 "components": [{"name": "Fade", "role": "text-effect", "style": ["minimal"], "motion": "subtle",
   "platform": ["web"], "demo": "https://calm.dev/fade", "files": ["src/fade.tsx"]},
   {"name": "", "role": "nope"}]}"""


def test_parse_draft_normalizes_and_keeps_only_named_components():
    out = li.parse_draft(DRAFT)
    assert out["slug"] == "calm-ui"
    assert out["library"]["frameworks"] == ["react"]  # unknown framework dropped
    assert [c["name"] for c in out["components"]] == ["Fade"]
    with pytest.raises(ValueError):
        li.parse_draft("no json here")


def test_commit_moves_the_source_and_clears_staging(tmp_path):
    root = tmp_path / "libraries"
    stage = root / li.STAGING_DIR / "job1"
    (stage / "source").mkdir(parents=True)
    (stage / "source" / "README.md").write_text("hi")
    out = li.parse_draft(DRAFT)
    lib_dir = li.commit_import(root, "job1", out["slug"], {**out["library"], "source": "https://x"}, out["components"])
    assert (lib_dir / "source" / "README.md").read_text() == "hi"
    assert not stage.exists()
    from api import library_catalog as lc
    [lib] = lc.list_libraries(root)
    assert lib["slug"] == "calm-ui" and lib["components"][0]["slug"] == "fade"


def test_staging_names_cannot_escape(tmp_path):
    with pytest.raises(ValueError):
        li.commit_import(tmp_path, "../../etc", "x", {"name": "x"}, [])


def test_the_catalog_listing_skips_the_staging_folder(tmp_path):
    (tmp_path / li.STAGING_DIR / "job1").mkdir(parents=True)
    from api import library_catalog as lc
    assert lc.list_libraries(tmp_path) == []


def test_a_failed_draft_still_returns_an_editable_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(li, "fetch_source", lambda link, dest: (Path(dest).mkdir(parents=True, exist_ok=True), {"mode": "page", "link": link})[1])
    monkeypatch.setattr(li, "_draft_with_planner", lambda link, gathered: (_ for _ in ()).throw(RuntimeError("no model")))
    result = li._import_work("https://x.dev/ui", tmp_path, "job9")
    assert result["draft"]["library"]["source"] == "https://x.dev/ui"
    assert result["draft"]["library"]["needs_details"] is True and result["draft_error"] == "no model"


def test_redraft_reads_an_existing_library_source_and_flags_replace(tmp_path, monkeypatch):
    from api import library_catalog as lc
    root = tmp_path / "libraries"
    lc.save_library(root, "calm", {"name": "calm", "source": "https://x/calm"}, [])
    (root / "calm" / "source").mkdir()
    (root / "calm" / "source" / "README.md").write_text("# Calm UI")
    seen = {}
    monkeypatch.setattr(li, "_draft_with_planner", lambda link, gathered: seen.update(gathered) or li.parse_draft(DRAFT))
    out = li._redraft_work(root, "calm")
    assert "Calm UI" in seen["readme"]
    assert out["replace"] is True and out["draft"]["slug"] == "calm"
    assert out["draft"]["library"]["source"] == "https://x/calm"


def test_delete_library_removes_only_that_folder(tmp_path):
    from api import library_catalog as lc
    root = tmp_path / "libraries"
    lc.save_library(root, "a", {"name": "a"}, [])
    lc.save_library(root, "b", {"name": "b"}, [])
    lc.delete_library(root, "a")
    assert [l["slug"] for l in lc.list_libraries(root)] == ["b"]
    with pytest.raises(ValueError):
        lc.delete_library(root, "../x")
    with pytest.raises(FileNotFoundError):
        lc.delete_library(root, "missing")
