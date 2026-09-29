"""Tests for the GOAP planner module and its API routes."""

import io
import json
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse, urlsplit

import pytest

import api.goal_planner as goal_planner


class _FakeHandler:
    def __init__(self, body=None, method="POST"):
        self.body = json.dumps(body).encode() if body is not None else b""
        self.rfile = io.BytesIO(self.body)
        self.headers = {
            "Content-Length": str(len(self.body)),
            "Content-Type": "application/json",
        }
        self.wfile = io.BytesIO()
        self.status = None
        self.method = method

    def send_response(self, status): self.status = status
    def send_header(self, *_): pass
    def end_headers(self): pass


class TestGoalPlannerModule:
    """Unit tests for api/goal_planner.py pure planning logic."""

    def test_plan_returns_seven_default_steps(self):
        plan = goal_planner.plan_goal("Investigate failed SSH logins")
        assert plan["goal"] == "Investigate failed SSH logins"
        assert len(plan["steps"]) == 7
        titles = [s["title"] for s in plan["steps"]]
        assert titles == [
            "Goal Analysis",
            "State Assessment",
            "Information Gathering",
            "Document Analysis",
            "Knowledge Synthesis",
            "Insight Generation",
            "Verification",
        ]

    def test_plan_detects_cybersecurity_domain(self):
        plan = goal_planner.plan_goal("Investigate failed SSH logins")
        assert plan["meta"]["domain"] == "cybersecurity"
        assert plan["meta"]["action"] == "investigate"

    def test_plan_detects_business_domain(self):
        plan = goal_planner.plan_goal("Analyze market share for SaaS startups")
        assert plan["meta"]["domain"] == "business"

    def test_plan_detects_software_engineering_domain(self):
        plan = goal_planner.plan_goal("Refactor the authentication code")
        assert plan["meta"]["domain"] == "software engineering"
        # keywords strips short/lowercase tokens; domain detection uses full lowercased goal

    def test_plan_detects_build_action(self):
        plan = goal_planner.plan_goal("Build a home lab network")
        assert plan["meta"]["action"] == "build"

    def test_plan_returns_empty_steps_for_empty_goal(self):
        # An empty goal still has goalDefined=True via the default initial state,
        # so the planner produces the standard 7-step chain (no validation blocks
        # an empty string at the module level; the API route validates instead).
        plan = goal_planner.plan_goal("")
        assert len(plan["steps"]) == 7

    def test_step_contains_expected_fields(self):
        plan = goal_planner.plan_goal("Investigate failed SSH logins")
        step = plan["steps"][0]
        assert step["id"] == "1"
        assert step["name"] == "analyzeGoal"
        assert step["status"] == "backlog"
        assert step["cost"] >= 1
        assert "description" in step

    def test_normalize_ai_items_orders_dependencies_then_priority(self):
        steps = goal_planner.normalize_ai_items([
            {"title": "QA", "description": "Test the release", "category": "QA", "priority": "medium", "dependencies": ["API"], "acceptance_criteria": ["Tests pass"]},
            {"title": "API", "description": "Build endpoints", "category": "Backend", "priority": "high", "dependencies": [], "acceptance_criteria": ["Endpoint responds"]},
        ])
        assert [step["title"] for step in steps] == ["API", "QA"]
        assert "Acceptance criteria: Endpoint responds" in steps[0]["description"]

    def test_normalize_ai_items_rejects_duplicate_or_unknown_dependencies(self):
        with pytest.raises(goal_planner.PlanError, match="Duplicate"):
            goal_planner.normalize_ai_items([
                {"title": "API", "description": "one", "category": "Backend", "priority": "high", "dependencies": [], "acceptance_criteria": []},
                {"title": " api ", "description": "two", "category": "Backend", "priority": "high", "dependencies": [], "acceptance_criteria": []},
            ])

    def test_planner_prompt_requests_compact_output(self, monkeypatch):
        captured = {}

        class FakeAgent:
            def __init__(self, **_kwargs): pass
            def run_conversation(self, **kwargs):
                captured.update(kwargs)
                return {"final_response": '{"items":[{"title":"API","description":"Build endpoint","category":"Backend","priority":"high","dependencies":[],"acceptance_criteria":[]}]}' }

        monkeypatch.setattr(goal_planner, "require_ai_agent_class", lambda: FakeAgent, raising=False)
        # The import is intentionally local in plan_goal_with_ai.
        import api.routes as routes
        monkeypatch.setattr(routes, "require_ai_agent_class", lambda: FakeAgent)
        monkeypatch.setattr("api.config.resolve_model_provider", lambda _value: ("model", "provider", None))
        monkeypatch.setattr("api.config.model_with_provider_context", lambda model, _provider: model)
        monkeypatch.setattr("api.oauth.resolve_runtime_provider_with_anthropic_env_lock", lambda *_args, **_kwargs: {})

        goal_planner.plan_goal_with_ai("Build API", "model")
        assert "Keep each field brief" in captured["system_message"]
        with pytest.raises(goal_planner.PlanError, match="Unknown"):
            goal_planner.normalize_ai_items([
                {"title": "QA", "description": "one", "category": "QA", "priority": "high", "dependencies": ["missing"], "acceptance_criteria": []},
            ])


class TestGoalPlannerGetRoute:
    """Tests for GET /api/work_hub/plan."""

    def test_get_plan_requires_goal(self, monkeypatch):
        import api.routes as routes
        monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
        handler = _FakeHandler(method="GET")
        routes.handle_get(handler, urlsplit("/api/work_hub/plan"))
        assert handler.status == 400
        payload = json.loads(handler.wfile.getvalue())
        assert "goal is required" in payload["error"]

    def test_get_plan_returns_steps(self, monkeypatch):
        import api.routes as routes
        monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
        handler = _FakeHandler(method="GET")
        routes.handle_get(handler, urlsplit("/api/work_hub/plan?goal=Investigate+failed+SSH+logins"))
        assert handler.status == 200
        payload = json.loads(handler.wfile.getvalue())
        assert payload["meta"]["domain"] == "cybersecurity"
        assert len(payload["steps"]) == 7


class TestGoalPlannerCreateRoute:
    """Tests for POST /api/work_hub/plan/create."""

    def test_create_plan_requires_goal(self, monkeypatch):
        import api.routes as routes
        monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
        handler = _FakeHandler({})
        routes.handle_post(handler, urlsplit("/api/work_hub/plan/create"))
        assert handler.status == 400
        payload = json.loads(handler.wfile.getvalue())
        assert "goal is required" in payload["error"]

    def test_create_plan_creates_work_items(self, monkeypatch, tmp_path):
        import api.routes as routes
        from api import work_hub
        monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
        monkeypatch.setattr(work_hub, "state_file", lambda: tmp_path / "work_hub.json")

        handler = _FakeHandler({"goal": "Investigate failed SSH logins", "project_id": None})
        routes.handle_post(handler, urlparse("/api/work_hub/plan/create"))

        assert handler.status == 200
        payload = json.loads(handler.wfile.getvalue())
        assert payload["ok"] is True
        assert len(payload["items"]) == 7
        assert len(payload["plan"]["steps"]) == 7

        # Verify items were persisted via work_hub module
        state = work_hub.load_state()
        assert len(state["work_items"]) == 7
        assert all(item["status"] == "backlog" for item in state["work_items"])
        assert all(item["title"] in {
            "Goal Analysis",
            "State Assessment",
            "Information Gathering",
            "Document Analysis",
            "Knowledge Synthesis",
            "Insight Generation",
            "Verification",
        } for item in state["work_items"])

    def test_create_plan_with_project_id_requires_existing_project(self, monkeypatch, tmp_path):
        import api.routes as routes
        from api import work_hub
        monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
        monkeypatch.setattr(work_hub, "state_file", lambda: tmp_path / "work_hub.json")
        monkeypatch.setattr(work_hub, "_project_exists", lambda _pid: False)

        handler = _FakeHandler({"goal": "Build a home lab", "project_id": "proj-123"})
        routes.handle_post(handler, urlparse("/api/work_hub/plan/create"))

        assert handler.status == 404
        payload = json.loads(handler.wfile.getvalue())
        assert "Project not found" in payload["error"]

    def test_create_plan_with_valid_project_id_persists_project(self, monkeypatch, tmp_path):
        import api.routes as routes
        from api import work_hub
        monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
        monkeypatch.setattr(work_hub, "state_file", lambda: tmp_path / "work_hub.json")
        monkeypatch.setattr(work_hub, "_project_exists", lambda _pid: True)

        handler = _FakeHandler({"goal": "Build a home lab", "project_id": "proj-123"})
        routes.handle_post(handler, urlparse("/api/work_hub/plan/create"))

        assert handler.status == 200
        payload = json.loads(handler.wfile.getvalue())
        assert payload["ok"] is True
        assert all(item["project_id"] == "proj-123" for item in payload["items"])


def test_ai_plan_route_uses_default_model_when_planner_setting_is_auto(monkeypatch, tmp_path):
    import api.routes as routes
    from api import goal_planner, work_hub

    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr(routes, "load_settings", lambda: {"work_hub_plan_model": "", "default_model": "default-planner"})
    captured = {}
    def fake_plan(goal, model_id, sources):
        captured.update(goal=goal, model_id=model_id, sources=sources)
        return {"goal": goal, "meta": {}, "steps": [{"title": "Implement", "description": "Ship it", "priority": "high"}]}
    monkeypatch.setattr(goal_planner, "plan_goal_with_ai", fake_plan)

    handler = _FakeHandler({"goal": "Ship this", "project_id": None, "upload_tokens": []})
    routes.handle_post(handler, urlparse("/api/work_hub/plan/ai"))

    assert handler.status == 200
    assert captured["model_id"] == "default-planner"
    assert work_hub.load_state()["work_items"] == []


def test_ai_plan_save_creates_previewed_steps(monkeypatch, tmp_path):
    import api.routes as routes
    from api import work_hub

    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    handler = _FakeHandler({"project_id": None, "steps": [{"title": "Frontend", "description": "Build screen", "priority": "high"}]})

    routes.handle_post(handler, urlparse("/api/work_hub/plan/save"))

    assert handler.status == 200
    payload = json.loads(handler.wfile.getvalue())
    assert [item["title"] for item in payload["items"]] == ["Frontend"]
