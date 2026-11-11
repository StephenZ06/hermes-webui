"""Skills you imported from a hub or a link are marked, so the project builder's
Toolkit step and the Skills page can put them ahead of the built-in ones."""

import json

from api import project_toolkit as tk
from tests.conftest import requires_agent_modules


def _skill(root, category, folder, name):
    path = root / category / folder
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(f"---\nname: {name}\ndescription: d\n---\n", encoding="utf-8")


@requires_agent_modules
def test_hub_and_link_installs_are_marked_imported_and_built_ins_are_not(monkeypatch, tmp_path):
    from api import routes

    skills_dir = tmp_path / "skills"
    _skill(skills_dir, "ui-design", "better-ui", "better-ui")
    _skill(skills_dir, "ui-design", "impeccable", "impeccable")
    # Folder and frontmatter name differ: the lock records the folder path.
    _skill(skills_dir, "motion", "skill", "transitions-agent")
    _skill(skills_dir, "research", "polymarket", "polymarket")
    _skill(skills_dir, "creative", "claude-design", "claude-design")
    (skills_dir / ".hub").mkdir()
    (skills_dir / ".hub" / "lock.json").write_text(json.dumps({"version": 1, "installed": {
        "better-ui": {"trust_level": "community", "install_path": "ui-design/better-ui"},
        "impeccable": {"trust_level": "trusted", "install_path": "ui-design/impeccable"},
        "skill": {"trust_level": "community", "install_path": "motion/skill"},
        "polymarket": {"trust_level": "builtin", "install_path": "research/polymarket"},
    }}), encoding="utf-8")
    monkeypatch.setattr(routes, "_get_disabled_skill_names_for_profile", lambda: set())

    imported = {s["name"]: s["imported"] for s in routes._skills_list_from_dir(skills_dir)["skills"]}

    assert imported == {"better-ui": True, "impeccable": True, "transitions-agent": True,
                        "polymarket": False, "claude-design": False}


@requires_agent_modules
def test_a_broken_lock_file_marks_nothing_imported(monkeypatch, tmp_path):
    from api import routes

    skills_dir = tmp_path / "skills"
    _skill(skills_dir, "ui-design", "better-ui", "better-ui")
    (skills_dir / ".hub").mkdir()
    (skills_dir / ".hub" / "lock.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(routes, "_get_disabled_skill_names_for_profile", lambda: set())

    assert [s["imported"] for s in routes._skills_list_from_dir(skills_dir)["skills"]] == [False]


def test_relevant_imported_skills_come_first_and_are_recommended_first():
    skills = [
        {"name": "popular-web-designs", "category": "creative", "description": "ui ux design web frontend css page"},
        {"name": "claude-design", "category": "creative", "description": "ui ux design web frontend"},
        {"name": "better-ui", "category": "ui-design", "description": "ui polish", "imported": True},
        {"name": "impeccable", "category": "ui-design", "description": "frontend design", "imported": True},
        {"name": "polymarket", "category": "research", "description": "markets"},
        {"name": "slides", "category": "office", "description": "decks", "imported": True},
    ]
    out = tk.suggest_skills(skills, template="website", brief="", limit=3)
    names = [s["name"] for s in out]
    # Imported and relevant first (by score), then the rest by score.
    assert names[:2] == ["impeccable", "better-ui"], names
    assert names[2] == "popular-web-designs", names
    assert [s["name"] for s in out if s["recommended"]] == ["impeccable", "better-ui", "popular-web-designs"]
    # An imported skill that does not fit the project is not pulled up.
    assert names.index("slides") > names.index("claude-design"), names
    assert next(s for s in out if s["name"] == "better-ui")["imported"] is True
    assert next(s for s in out if s["name"] == "claude-design")["imported"] is False
