"""The project builder's brief review reports what the planner is doing as
one short line: the tool it called, the heading or latest sentence of its
reasoning, or that it is writing up its answer."""

import threading

from api import project_starter_agent as agent


def test_tool_calls_read_as_short_plain_lines():
    assert agent.tool_progress_line({"name": "read_file", "args": {"path": "/srv/app/src/main.py"}}) == "Reading main.py"
    assert agent.tool_progress_line({"name": "web_search", "args": {"query": "astro content collections"}}) == "Searching the web for astro content collections"
    assert agent.tool_progress_line({"name": "terminal", "args": {"command": "ls -la"}}) == "Running ls -la"
    assert agent.tool_progress_line({"name": "todo", "args": {"todos": []}}) == "Updating its plan"
    assert agent.tool_progress_line({"name": "vision_analyze", "args": {}}) == "Using vision analyze"
    assert agent.tool_progress_line({"name": ""}) == ""
    long = agent.tool_progress_line({"name": "web_search", "args": {"query": "x " * 200}})
    assert len(long) <= 120 and "\n" not in long


def test_reasoning_reads_as_its_latest_heading_or_finished_sentence():
    assert agent.reasoning_progress_line("**Reading the brief**\n\nThe firm wants...\n\n**Weighing the stack**\n\nAstro") == "Weighing the stack"
    assert agent.reasoning_progress_line("The brief names a contact form. It does not say where it is hosted. Next I") == "It does not say where it is hosted."
    assert agent.reasoning_progress_line("ok") == ""


def test_a_running_job_returns_its_latest_progress_line():
    release = threading.Event()
    reported = threading.Event()

    def work(report, _on_run):
        report("Reading the brief")
        report("Weighing the stack")
        reported.set()
        release.wait(5)
        return {"ok": True}

    job_id = agent._start_job("analysis", work, with_progress=True)
    assert reported.wait(5)
    assert agent.get_job(job_id) == {"status": "running", "kind": "analysis", "progress": "Weighing the stack"}
    release.set()
    for _ in range(100):
        if agent.get_job(job_id)["status"] == "done":
            break
        threading.Event().wait(0.02)
    assert agent.get_job(job_id)["result"] == {"ok": True}


def test_the_hidden_turn_reports_its_tool_calls_reasoning_and_answer(monkeypatch, tmp_path):
    import api.models
    import api.routes

    class _Session:
        session_id = "s1"
        workspace = str(tmp_path)
        path = str(tmp_path / "s1.json")

        def save(self):
            pass

    def fake_stream(session_id, prompt, model, workspace, stream_id, _attachments, **_kw):
        channel = api.routes.STREAMS[stream_id]
        channel.put_nowait(("reasoning", {"text": "**Reading the brief**\n\nIt is a law firm."}))
        channel.put_nowait(("tool", {"name": "read_file", "args": {"path": "/x/brief.md"}}))
        channel.put_nowait(("token", {"text": "{"}))
        channel.put_nowait(("done", {"answer": "{}"}))

    monkeypatch.setattr(agent, "profile_available", lambda _p: True)
    monkeypatch.setattr(api.models, "new_session", lambda **_kw: _Session())
    monkeypatch.setattr(api.routes, "_run_agent_streaming", fake_stream)
    lines = []
    answer = agent._run_ephemeral_turn("p", timeout=5, model="m", model_provider="x", progress=lines.append,
                                       answer_label="Writing up its questions")
    assert answer == "{}"
    assert lines == ["Starting Docs-Git", "Reading the brief", "Reading brief.md", "Writing up its questions"], lines
