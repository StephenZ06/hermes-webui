"""The test server's skills folder shows the real skills but keeps every write
to itself: a category or skill a test creates must never land in the real
``~/.hermes/skills`` (the browser tests once left ``cat-xxxxxx`` folders there)."""

from tests.conftest import _seed_test_skills


def _real_skills(tmp_path):
    real = tmp_path / "real"
    (real / "creative" / "poster").mkdir(parents=True)
    (real / "creative" / "poster" / "SKILL.md").write_text("---\nname: poster\n---\n")
    (real / "creative" / "DESCRIPTION.md").write_text("Creative skills.")
    (real / "loose").mkdir()
    (real / "loose" / "SKILL.md").write_text("---\nname: loose\n---\n")
    (real / ".usage.json").write_text("{}")
    return real


def test_seeded_skills_are_readable(tmp_path):
    real = _real_skills(tmp_path)
    test = tmp_path / "test" / "skills"
    _seed_test_skills(real, test)
    assert (test / "creative" / "poster" / "SKILL.md").read_text().startswith("---")
    assert (test / "creative" / "DESCRIPTION.md").read_text() == "Creative skills."
    assert (test / "loose" / "SKILL.md").exists()


def test_writes_to_the_seeded_skills_stay_out_of_the_real_folder(tmp_path):
    real = _real_skills(tmp_path)
    test = tmp_path / "test" / "skills"
    _seed_test_skills(real, test)
    (test / "cat-abc123").mkdir()
    (test / "cat-abc123" / "DESCRIPTION.md").write_text("Cat abc123 skills.")
    (test / "creative" / "new-skill").mkdir()
    (test / "creative" / "DESCRIPTION.md").write_text("Changed.")
    (test / ".usage.json").write_text('{"x": 1}')
    assert sorted(p.name for p in real.iterdir()) == [".usage.json", "creative", "loose"]
    assert sorted(p.name for p in (real / "creative").iterdir()) == ["DESCRIPTION.md", "poster"]
    assert (real / "creative" / "DESCRIPTION.md").read_text() == "Creative skills."
    assert (real / ".usage.json").read_text() == "{}"
