"""Static contracts for the vanilla-JS goal planner."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


class TestGoalPlannerScript:
    """Tests for static/goal-planner.js source structure."""

    def test_goal_planner_script_included_in_index_html(self):
        page = read("static/index.html")
        assert "static/goal-planner.js" in page
        assert "static/work-hub.js" in page
        # goal-planner.js should load after work-hub.js
        assert page.index("static/work-hub.js") < page.index("static/goal-planner.js")

    def test_goal_planner_exports_plan_parse_goal_default_actions(self):
        script = read("static/goal-planner.js")
        assert "window.GoalPlanner = GoalPlanner" in script
        assert "plan" in script
        assert "parseGoal" in script
        assert "defaultActions" in script

    def test_goal_planner_script_parses_in_supported_node_runtime(self):
        result = subprocess.run(
            ["node", "--check", str(ROOT / "static/goal-planner.js")],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    def test_goal_planner_has_default_state_and_astar_loop(self):
        script = read("static/goal-planner.js")
        assert "DEFAULT_STATE" in script
        assert "preconditionsMet" in script
        assert "applyEffects" in script
        assert "heuristic" in script
        assert "while (openList.length > 0)" in script

    def test_goal_planner_detects_cybersecurity_terms(self):
        script = read("static/goal-planner.js")
        for term in ("security", "soc", "cyber", "ssh", "firewall", "malware", "phishing", "intrusion"):
            assert f"lower.includes('{term}')" in script or f'lower.includes("{term}")' in script


class TestGoalPlannerDialogScript:
    """Tests for the dialog UI wired in static/work-hub.js."""

    def test_work_hub_has_plan_goal_button(self):
        script = read("static/work-hub.js")
        assert "Plan goal" in script
        assert "openGoalPlannerDialog" in script

    def test_plan_goal_button_has_dedicated_class_not_scope(self):
        script = read("static/work-hub.js")
        assert "work-hub-plan-goal" in script
        # It must not be bound as a generic work-hub-scope; otherwise bind() clobbers its onclick.
        assert "data-scope=\"plan-goal\"" not in script

    def test_goal_planner_dialog_dom_structure(self):
        script = read("static/work-hub.js")
        assert "goal-planner-overlay" in script
        assert "goal-planner-dialog" in script
        assert "goalPlannerInput" in script
        assert "goalPlannerBtn" in script
        assert "goalPlannerScopeBtn" in script

    def test_goal_planner_has_source_drop_zone_and_explicit_save(self):
        script = read("static/work-hub.js")
        styles = read("static/style.css")
        assert "Create, Paste, or Attach notes to be turned into a structured item" in script
        assert "goal-planner-dropzone" in script
        assert "/api/work_hub/plan/uploads" in script
        assert "upload_tokens" in script
        assert "dragover" in script
        assert "goal-planner-dropzone" in styles
        assert "border: 1px dashed" in styles
        assert "place-items: center" in styles
        assert "goalPlannerSave" in script
        assert "Save work items" in script
        assert "/api/work_hub/plan/save" in script
        assert "Run as workflow" not in script
        assert "/api/work_hub/workflows/start" not in script

    def test_goal_planner_uses_icon_controls_and_loading_animation(self):
        script = read("static/work-hub.js")
        styles = read("static/style.css")
        assert 'id="goalPlannerBtn" type="button" aria-label="Plan work items"' in script
        assert 'id="goalPlannerSave"' in script
        assert 'aria-label="Save work items"' in script
        assert "goal-planner-is-planning" in script
        assert "goal-planner-button-icon" in styles
        assert "goal-planner-spin" in styles
        assert "border-radius: var(--radius-lg)" in styles

    def test_plan_calls_backend_and_does_not_use_generic_client_planner(self):
        script = read("static/work-hub.js")
        assert "/api/work_hub/plan/ai" in script
        assert "method: 'POST'" in script
        assert "window.GoalPlanner.plan(goal)" not in script

    def test_work_hub_script_parses_in_supported_node_runtime(self):
        result = subprocess.run(
            ["node", "--check", str(ROOT / "static/work-hub.js")],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
