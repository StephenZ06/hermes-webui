"""_persistent_state_snapshot_after() must skip the expensive skills
rglob+per-file-stat pass when nothing changed during the turn, using a
cheap directory-mtime probe -- and must still detect a real change
correctly when one did happen.

Every completed chat turn calls the skills-snapshot pass twice (before the
turn, after it) purely to power the "skill created/updated" toast. A
profile with ~100 skills paid ~100 stat() calls plus a directory walk for
each pass, every single turn, even on the overwhelming majority of turns
where no skill was touched at all.
"""
from pathlib import Path

from api import streaming


def _write_skill(root: Path, name: str, content: str = "content") -> Path:
    d = root / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    f = d / "SKILL.md"
    f.write_text(content, encoding="utf-8")
    return f


def test_after_snapshot_reuses_before_when_nothing_changed(tmp_path, monkeypatch):
    _write_skill(tmp_path, "alpha")
    _write_skill(tmp_path, "beta")

    before = streaming._persistent_state_snapshot(str(tmp_path))
    probe_before = streaming._skills_tree_light_probe(tmp_path / "skills")

    calls = []
    real_skills_snapshot = streaming._persistent_state_skills_snapshot

    def counting_skills_snapshot(skills_dir):
        calls.append(skills_dir)
        return real_skills_snapshot(skills_dir)

    monkeypatch.setattr(streaming, "_persistent_state_skills_snapshot", counting_skills_snapshot)

    after = streaming._persistent_state_snapshot_after(str(tmp_path), before, probe_before)

    assert calls == [], "the expensive per-file skills walk must not run when nothing changed"
    assert after["skills"] == before["skills"]


def test_after_snapshot_detects_a_new_skill(tmp_path):
    _write_skill(tmp_path, "alpha")

    before = streaming._persistent_state_snapshot(str(tmp_path))
    probe_before = streaming._skills_tree_light_probe(tmp_path / "skills")

    _write_skill(tmp_path, "gamma")  # new skill created "during the turn"

    after = streaming._persistent_state_snapshot_after(str(tmp_path), before, probe_before)
    changes = streaming._persistent_state_changes(before, after)

    created = [c for c in changes["skills"] if c["action"] == "created"]
    assert any(c["name"] == "gamma" for c in created)


def test_after_snapshot_detects_an_edited_skill(tmp_path):
    skill_path = _write_skill(tmp_path, "alpha", content="v1")

    before = streaming._persistent_state_snapshot(str(tmp_path))
    probe_before = streaming._skills_tree_light_probe(tmp_path / "skills")

    # A same-second content edit may not bump mtime on some filesystems --
    # force it forward so this test is not flaky on fast machines.
    import os
    import time
    new_mtime = skill_path.stat().st_mtime + 5
    skill_path.write_text("v2", encoding="utf-8")
    os.utime(skill_path, (new_mtime, new_mtime))
    os.utime(skill_path.parent, (new_mtime, new_mtime))

    after = streaming._persistent_state_snapshot_after(str(tmp_path), before, probe_before)
    changes = streaming._persistent_state_changes(before, after)

    updated = [c for c in changes["skills"] if c["action"] == "updated"]
    assert any(c["name"] == "alpha" for c in updated)


def test_after_snapshot_handles_missing_profile_home():
    assert streaming._persistent_state_snapshot_after(None, None, 0) == {"memory": {}, "skills": {}}


def test_light_probe_changes_when_a_skill_dir_is_added(tmp_path):
    _write_skill(tmp_path, "alpha")
    probe1 = streaming._skills_tree_light_probe(tmp_path / "skills")

    _write_skill(tmp_path, "beta")
    probe2 = streaming._skills_tree_light_probe(tmp_path / "skills")

    assert probe1 != probe2


def test_light_probe_is_stable_when_nothing_changes(tmp_path):
    _write_skill(tmp_path, "alpha")
    probe1 = streaming._skills_tree_light_probe(tmp_path / "skills")
    probe2 = streaming._skills_tree_light_probe(tmp_path / "skills")
    assert probe1 == probe2


def test_light_probe_missing_skills_dir_is_zero(tmp_path):
    assert streaming._skills_tree_light_probe(tmp_path / "no-such-dir") == 0
