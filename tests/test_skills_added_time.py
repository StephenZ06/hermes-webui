"""Each listed skill carries when its folder was added, so the Skills page can
filter to the recently added ones."""

import os

from tests.conftest import requires_agent_modules


@requires_agent_modules
def test_listed_skills_carry_when_they_were_added(monkeypatch, tmp_path):
    from api import routes

    skills_dir = tmp_path / "skills"
    for name, when in (("old-one", 1_700_000_000), ("new-one", 1_800_000_000)):
        skill_dir = skills_dir / "tools" / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\ndescription: d\n---\n", encoding="utf-8")
        os.utime(skill_dir, (when, when))
    monkeypatch.setattr(routes, "_get_disabled_skill_names_for_profile", lambda: set())

    added = {s["name"]: s["added"] for s in routes._skills_list_from_dir(skills_dir)["skills"]}

    assert added == {"old-one": 1_700_000_000, "new-one": 1_800_000_000}
