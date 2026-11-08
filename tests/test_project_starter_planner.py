"""A new project's planning runs under the Architecture profile on Codex Sol;
adopting an existing project stays with Docs-Git."""

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


def test_brief_review_runs_on_architecture_with_sol(monkeypatch):
    runs = _capture(monkeypatch)
    result = agent.start_analysis(name="demo", brief="A web app", template={"key": "web", "files": ["AGENTS.md"]})
    assert result["complete"] is True
    assert runs[0]["profile"] == "architecture"
    assert runs[0]["model"] == "gpt-5.6-sol" and runs[0]["model_provider"] == "openai-codex"


def test_new_project_docs_are_written_by_architecture_and_adoption_by_docs_git(monkeypatch):
    runs = _capture(monkeypatch)
    project = {"name": "demo", "workspace_path": "/tmp/demo"}
    agent.start_docs_setup(project, adopt=False, template_label="Web App", files=["AGENTS.md"])
    agent.start_docs_setup(project, adopt=True)
    assert runs[0]["profile"] == "architecture" and runs[0]["model"] == "gpt-5.6-sol"
    assert runs[0]["title"].startswith("Architecture: set up")
    assert runs[1]["profile"] == "docs-gits" and "model" not in runs[1]


def test_setup_is_skipped_when_its_own_profile_is_missing(monkeypatch):
    _capture(monkeypatch)
    monkeypatch.setattr(agent, "profile_available", lambda profile: profile == "docs-gits")
    assert agent.start_docs_setup({"name": "x", "workspace_path": "/tmp/x"}, adopt=False) is None
    readiness = agent.planner_readiness()
    assert readiness["ready"] is False and readiness["profile"] == "architecture"
    assert "Architecture" in readiness["message"]
