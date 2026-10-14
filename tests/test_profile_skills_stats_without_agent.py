"""The profile skill counter is reached from the no-hermes_cli fallbacks
(_default_profile_dict, used by the Work Hub bootstrap and the profile list).
Without the agent installed it must return a count, not raise."""

import builtins

import api.profiles as profiles


def test_skill_stats_without_the_agent_return_zero(monkeypatch, tmp_path):
    (tmp_path / "skills" / "demo").mkdir(parents=True)
    (tmp_path / "skills" / "demo" / "SKILL.md").write_text("---\nname: demo\n---\n", encoding="utf-8")
    real_import = builtins.__import__

    def no_agent(name, *args, **kwargs):
        if name == "agent.skill_utils" or name.startswith("agent.skill_utils"):
            raise ModuleNotFoundError("No module named 'agent'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_agent)
    assert profiles._compute_profile_skills_stats(tmp_path) == (0, 0)
