"""Skills & Tools of a project (api.project_inventory) and project reordering."""

import json

from api import project_inventory as inv
from api import project_toolkit as tk

INSTALLED = {"tdd": {"description": "Test first", "category": "dev"},
             "seo": {"description": "Search", "category": "web"},
             "docs": {"description": "Write docs", "category": "writing"}}


def _proj(path):
    return {"project_id": "p1", "name": "P", "workspace_path": str(path)}


def test_wizard_picks_are_recorded_and_listed_with_folder_skills_packages_and_mcp(tmp_path):
    tk.apply_toolkit(tmp_path, {"skills": ["tdd", "seo"], "components": [], "look": None, "needs": []},
                     libraries_root=tmp_path / "libs")
    manifest = json.loads((tmp_path / ".agent" / "toolkit.json").read_text())
    assert [s["name"] for s in manifest["skills"]] == ["tdd", "seo"]
    skill = tmp_path / ".agents" / "skills" / "repo-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: repo-skill\ndescription: From a repo\n---\nBody\n")
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "^19"}, "devDependencies": {"vite": "6"}}))
    (tmp_path / "requirements.txt").write_text("fastapi>=0.1  # web\n-r other.txt\n")
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"github": {"command": "gh-mcp"}}}))
    out = inv.inventory(_proj(tmp_path), installed=INSTALLED)
    got = {(i["kind"], i["name"], i["source"]) for i in out["items"]}
    assert got == {("skill", "tdd", "wizard"), ("skill", "seo", "wizard"), ("skill", "repo-skill", "folder"),
                   ("package", "react", "folder"), ("package", "vite", "folder"), ("package", "fastapi", "folder"),
                   ("mcp", "github", "folder")}
    assert [a["name"] for a in out["addable"]] == ["docs"]
    tdd = next(i for i in out["items"] if i["name"] == "tdd")
    assert tdd["description"] == "Test first" and tdd["removable"] and tdd["added_at"]


def test_adding_and_removing_skills_rewrites_only_the_skill_lines_of_the_toolkit_block(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Own rules\n\nKeep this.\n")
    tk.apply_toolkit(tmp_path, {"skills": ["tdd"], "components": [], "look": None, "needs": []},
                     libraries_root=tmp_path / "libs")
    names = inv.set_skills(_proj(tmp_path), add=["docs"], remove=["tdd"], installed=set(INSTALLED))
    assert names == ["docs"]
    text = (tmp_path / "AGENTS.md").read_text()
    assert "Keep this." in text and "load the `docs` skill" in text and "`tdd`" not in text
    assert "Skills installed for this project from a repo" in text  # the rest of the block stays
    assert inv.agents_skills(tmp_path) == ["docs"]
    added = next(s for s in inv.read_manifest(tmp_path)["skills"] if s["name"] == "docs")
    assert added["source"] == "added"
    # Removing the last skill drops the intro line too.
    inv.set_skills(_proj(tmp_path), add=[], remove=["docs"], installed=set(INSTALLED))
    assert inv.SKILLS_INTRO not in (tmp_path / "AGENTS.md").read_text()


def test_only_installed_skills_can_be_added_and_a_project_needs_a_folder(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        inv.set_skills(_proj(tmp_path), add=["nope"], remove=[], installed=set(INSTALLED))
    with pytest.raises(ValueError):
        inv.set_skills({"project_id": "p"}, add=["tdd"], remove=[], installed=set(INSTALLED))
    assert inv.inventory({"project_id": "p"}, installed=INSTALLED) == {"folder": None, "items": [], "addable": []}


def test_symlinked_skill_folders_and_files_outside_the_project_are_not_read(tmp_path):
    outside = tmp_path / "outside"
    (outside / "evil").mkdir(parents=True)
    (outside / "evil" / "SKILL.md").write_text("---\nname: evil\n---\n")
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude" / "skills").symlink_to(outside)
    (project / "package.json").symlink_to(outside / "evil" / "SKILL.md")
    assert inv.inventory(_proj(project), installed={})["items"] == []


def test_reorder_moves_only_the_named_projects_among_their_own_slots(monkeypatch, tmp_path):
    from api import routes

    projects = [{"project_id": x, "name": x} for x in ("a", "hidden", "b", "c")]
    saved = {}
    monkeypatch.setattr(routes, "load_projects", lambda: [dict(p) for p in projects])
    monkeypatch.setattr(routes, "save_projects", lambda ps: saved.setdefault("order", [p["project_id"] for p in ps]))
    out = {}
    monkeypatch.setattr(routes, "j", lambda h, data, **k: out.update(data))
    monkeypatch.setattr(routes, "bad", lambda h, msg, status=400: out.update(error=msg, status=status))
    routes._route_post_api_projects_reorder(None, None, {"order": ["b", "a", "c"]}, None)
    assert saved["order"] == ["b", "hidden", "a", "c"], out
    out.clear()
    routes._route_post_api_projects_reorder(None, None, {"order": ["a", "a"]}, None)
    assert out.get("status") == 400
    out.clear()
    routes._route_post_api_projects_reorder(None, None, {"order": ["zzz"]}, None)
    assert out.get("status") == 404
