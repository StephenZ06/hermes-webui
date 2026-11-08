"""The whole wizard (brief review, questions, writing or adopting the\ninstruction files) runs under the Architecture profile on GPT-6.1 Sol."""

from api import project_starter_agent as agent


def _capture(monkeypatch):
    runs = []

    def fake_turn(prompt, **kwargs):
        runs.append(kwargs)
        return '{"complete": true, "summary": "ok", "questions": []}'

    monkeypatch.setattr(agent, "_run_ephemeral_turn", fake_turn)
    monkeypatch.setattr(agent, "profile_available", lambda profile: True)
    monkeypatch.setattr(agent, "_start_job", lambda kind, work: work())
    return runs


def test_brief_review_runs_on_architecture_with_gpt_6_1_sol(monkeypatch):
    runs = _capture(monkeypatch)
    result = agent.start_analysis(name="demo", brief="A web app", template={"key": "web", "files": ["AGENTS.md"]})
    assert result["complete"] is True
    assert runs[0]["profile"] == "architecture"
    assert runs[0]["model"] == "gpt-6.1-sol" and runs[0]["model_provider"] == "openai-codex"


def test_new_and_adopted_projects_are_both_set_up_by_architecture(monkeypatch):
    runs = _capture(monkeypatch)
    project = {"name": "demo", "workspace_path": "/tmp/demo"}
    agent.start_docs_setup(project, adopt=False, template_label="Web App", files=["AGENTS.md"])
    agent.start_docs_setup(project, adopt=True)
    assert all(r["profile"] == "architecture" and r["model"] == "gpt-6.1-sol" for r in runs)
    assert runs[0]["title"].startswith("Architecture: set up") and runs[1]["title"].startswith("Architecture: adopt")


def test_setup_is_skipped_when_its_own_profile_is_missing(monkeypatch):
    _capture(monkeypatch)
    monkeypatch.setattr(agent, "profile_available", lambda profile: profile == "docs-gits")
    assert agent.start_docs_setup({"name": "x", "workspace_path": "/tmp/x"}, adopt=False) is None
    assert agent.start_docs_setup({"name": "x", "workspace_path": "/tmp/x"}, adopt=True) is None
    readiness = agent.planner_readiness()
    assert readiness["ready"] is False and readiness["profile"] == "architecture"
    assert "Architecture" in readiness["message"]


def test_setup_prompts_install_dependencies_and_keep_documents_linked():
    new = agent._new_project_prompt("demo", "Web App", ["AGENTS.md", "docs/ARCHITECTURE.md"])
    adopt = agent._adopt_prompt("demo")
    for prompt in (new, adopt):
        assert "install" in prompt.lower() and "dependencies" in prompt.lower()
        assert "Related documents" in prompt
