"""GOAP-style goal planning for Work Hub.

Lightweight A* planner for turning a user goal into a sequence of work items.
Ported from Ruflo's v3/goal_ui/src/lib/goapPlanner.ts and exposed to the UI.
"""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from typing import Any


class PlanError(ValueError):
    pass


_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2, "none": 3}


def normalize_ai_items(items: object) -> list[dict[str, Any]]:
    """Validate model work items and return a deterministic dependency order."""
    if not isinstance(items, list) or not items:
        raise PlanError("Planner returned no work items")
    normalized = []
    titles: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise PlanError("Planner item must be an object")
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        category = str(item.get("category") or "").strip()
        priority = str(item.get("priority") or "none").strip().lower()
        dependencies = item.get("dependencies")
        criteria = item.get("acceptance_criteria")
        if not title or not description or not category:
            raise PlanError("Planner item needs title, description, and category")
        if len(title) > 240 or priority not in _PRIORITY_ORDER:
            raise PlanError("Planner item has invalid title or priority")
        if not isinstance(dependencies, list) or not all(isinstance(value, str) and value.strip() for value in dependencies):
            raise PlanError("Planner dependencies must be a list of titles")
        if not isinstance(criteria, list) or not all(isinstance(value, str) and value.strip() for value in criteria):
            raise PlanError("Planner acceptance criteria must be a list of text")
        key = title.casefold()
        if key in titles:
            raise PlanError("Duplicate planner item title")
        step = {"title": title, "description": description, "category": category, "priority": priority,
                "dependencies": [value.strip() for value in dependencies], "acceptance_criteria": [value.strip() for value in criteria]}
        titles[key] = step
        normalized.append(step)
    for step in normalized:
        for dependency in step["dependencies"]:
            if dependency.casefold() not in titles:
                raise PlanError("Unknown planner dependency")
    ordered = []
    pending = list(normalized)
    resolved: set[str] = set()
    while pending:
        ready = [step for step in pending if all(dep.casefold() in resolved for dep in step["dependencies"])]
        if not ready:
            raise PlanError("Planner dependencies contain a cycle")
        ready.sort(key=lambda step: (_PRIORITY_ORDER[step["priority"]], step["category"].casefold(), step["title"].casefold()))
        for step in ready:
            pending.remove(step)
            resolved.add(step["title"].casefold())
            acceptance = "; ".join(step["acceptance_criteria"])
            ordered.append({"id": str(len(ordered) + 1), "name": f"step_{len(ordered) + 1}", "title": step["title"],
                            "description": f'{step["description"]}\n\nCategory: {step["category"]}\nAcceptance criteria: {acceptance}'.rstrip(),
                            "status": "backlog", "priority": step["priority"]})
    return ordered


DEFAULT_WORLD_STATE: dict[str, bool] = {
    "goalDefined": False,
    "goalParsed": False,
    "stateAssessed": False,
    "informationGathered": False,
    "documentsAnalyzed": False,
    "knowledgeSynthesized": False,
    "insightsGenerated": False,
    "verified": False,
}


def _parse_goal(goal: str) -> dict[str, Any]:
    lower = goal.lower()
    domain = "general"
    if "quantum" in lower or "computing" in lower:
        domain = "technology"
    elif "market" in lower or "business" in lower:
        domain = "business"
    elif "architecture" in lower or "software" in lower or "code" in lower:
        domain = "software engineering"
    elif "energy" in lower or "renewable" in lower:
        domain = "energy"
    elif "security" in lower or "soc" in lower or "cyber" in lower or "ssh" in lower or "firewall" in lower or "malware" in lower or "phishing" in lower or "intrusion" in lower:
        domain = "cybersecurity"

    action = "research"
    for token, name in [
        ("analyze", "analyze"),
        ("investigate", "investigate"),
        ("compare", "compare"),
        ("evaluate", "evaluate"),
        ("build", "build"),
        ("implement", "build"),
    ]:
        if token in lower:
            action = name
            break

    keywords = [w for w in goal.split() if len(w) > 4][:5]
    return {"domain": domain, "action": action, "keywords": keywords}


def _default_step_templates() -> list[dict[str, Any]]:
    return [
        {
            "name": "analyzeGoal",
            "cost": 1,
            "preconditions": {"goalDefined": True},
            "effects": {"goalParsed": True},
            "title": "Goal Analysis",
            "description": lambda goal, meta: f'Analyze "{goal[:80]}" and break it into actionable sub-goals for {meta["domain"]}.',
        },
        {
            "name": "assessState",
            "cost": 1,
            "preconditions": {"goalParsed": True},
            "effects": {"stateAssessed": True},
            "title": "State Assessment",
            "description": lambda goal, meta: f'Evaluate current knowledge about {meta["domain"]} and identify gaps before {meta["action"]}.',
        },
        {
            "name": "gatherInformation",
            "cost": 2,
            "preconditions": {"stateAssessed": True},
            "effects": {"informationGathered": True},
            "title": "Information Gathering",
            "description": lambda goal, meta: f'Collect sources and run searches around {", ".join(meta["keywords"])}.',
        },
        {
            "name": "analyzeDocuments",
            "cost": 2,
            "preconditions": {"informationGathered": True},
            "effects": {"documentsAnalyzed": True},
            "title": "Document Analysis",
            "description": lambda _g, _m: "Extract findings, methodologies, and actionable insights from gathered sources.",
        },
        {
            "name": "synthesizeKnowledge",
            "cost": 2,
            "preconditions": {"documentsAnalyzed": True},
            "effects": {"knowledgeSynthesized": True},
            "title": "Knowledge Synthesis",
            "description": lambda _g, _m: "Weave findings into a coherent picture and identify practical recommendations.",
        },
        {
            "name": "generateInsights",
            "cost": 2,
            "preconditions": {"knowledgeSynthesized": True},
            "effects": {"insightsGenerated": True},
            "title": "Insight Generation",
            "description": lambda _g, _m: "Produce novel insights, risk flags, and strategic options from the synthesized work.",
        },
        {
            "name": "verify",
            "cost": 1,
            "preconditions": {"insightsGenerated": True},
            "effects": {"verified": True},
            "title": "Verification",
            "description": lambda _g, _m: "Re-check the plan against success criteria and finalize deliverables.",
        },
    ]


def _heuristic(state: dict[str, bool], goal: dict[str, bool]) -> int:
    return sum(1 for key, value in goal.items() if value and not state.get(key))


def _preconditions_met(state: dict[str, bool], preconditions: dict[str, bool]) -> bool:
    return all(state.get(key) for key, value in preconditions.items() if value)


def _apply_effects(state: dict[str, bool], effects: dict[str, bool]) -> dict[str, bool]:
    new_state = deepcopy(state)
    new_state.update(effects)
    return new_state


def plan_goal(goal: str, actions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return a GOAP-style plan for the given natural-language goal."""
    meta = _parse_goal(goal)
    initial_state = {**DEFAULT_WORLD_STATE, "goalDefined": True}
    target_state = {**DEFAULT_WORLD_STATE, "verified": True}
    action_list = actions if actions is not None else _default_step_templates()

    open_list: list[dict[str, Any]] = [
        {"state": initial_state, "actions": [], "cost": 0, "heuristic": _heuristic(initial_state, target_state)}
    ]
    closed_list: set[str] = set()

    while open_list:
        open_list.sort(key=lambda node: node["cost"] + node["heuristic"])
        current = open_list.pop(0)
        state_key = json.dumps(current["state"], sort_keys=True)

        if _heuristic(current["state"], target_state) == 0:
            steps = []
            for idx, action in enumerate(current["actions"], start=1):
                steps.append({
                    "id": str(idx),
                    "name": action["name"],
                    "title": action["title"],
                    "description": action["description"](goal, meta),
                    "cost": action["cost"],
                    "status": "backlog",
                })
            return {"goal": goal, "meta": meta, "steps": steps}

        if state_key in closed_list:
            continue
        closed_list.add(state_key)

        for action in action_list:
            if _preconditions_met(current["state"], action["preconditions"]):
                new_state = _apply_effects(current["state"], action["effects"])
                new_state_key = json.dumps(new_state, sort_keys=True)
                if new_state_key not in closed_list:
                    open_list.append({
                        "state": new_state,
                        "actions": [*current["actions"], action],
                        "cost": current["cost"] + action["cost"],
                        "heuristic": _heuristic(new_state, target_state),
                    })

    return {"goal": goal, "meta": meta, "steps": []}


def plan_goal_with_ai(goal: str, model_id: str | None = None, sources: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Use a configured model to turn raw notes into structured work items.

    The interactive source planner is deliberately strict: a missing model or
    malformed response must not create generic boilerplate work items.
    """
    effective_model = (model_id or "").strip() or None
    if not effective_model:
        raise PlanError("Configure a Goal Planner model in Settings first")

    try:
        from api.config import (
            model_with_provider_context,
            resolve_custom_provider_connection,
            resolve_model_provider,
        )
        from api.oauth import resolve_runtime_provider_with_anthropic_env_lock
        from hermes_cli.runtime_provider import resolve_runtime_provider
        from api.routes import require_ai_agent_class

        _main_model, _main_provider, _main_base_url = resolve_model_provider(
            model_with_provider_context(effective_model, None)
        )
        _main_api_key = None
        try:
            _rt = resolve_runtime_provider_with_anthropic_env_lock(
                resolve_runtime_provider,
                requested=_main_provider,
            )
            _main_api_key = _rt.get("api_key")
            if not _main_provider:
                _main_provider = _rt.get("provider")
            if not _main_base_url:
                _main_base_url = _rt.get("base_url")
        except Exception:
            pass
        if isinstance(_main_provider, str) and _main_provider.startswith("custom:"):
            _cp_key, _cp_base = resolve_custom_provider_connection(_main_provider)
            if not _main_api_key and _cp_key:
                _main_api_key = _cp_key
            if not _main_base_url and _cp_base:
                _main_base_url = _cp_base

        system_prompt = (
            "Return ONLY JSON: "
            '{"items":[{"title":"short","description":"brief","category":"Frontend|Backend|QA|Docs","priority":"low|medium|high|none","dependencies":["title"],"acceptance_criteria":["result"]}]}. '
            "Turn the supplied notes into 2-12 implementation work items, grouped by responsibility. "
            "Dependencies name returned titles and contain no cycle. Keep each field brief: titles under 80 characters, "
            "one-sentence descriptions, and one concise acceptance criterion. No markdown or explanation."
        )
        source_text = "\n\n".join(
            f"Source: {str(source.get('name') or 'attachment')[:160]}\n{str(source.get('text') or '')[:12000]}"
            for source in (sources or [])
            if isinstance(source, dict)
        )[:36000]
        combined_goal = f"Notes:\n{goal.strip()[:12000]}" + (f"\n\n{source_text}" if source_text else "")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": goal},
        ]

        AIAgent = require_ai_agent_class()
        agent = AIAgent(
            model=_main_model,
            provider=_main_provider,
            base_url=_main_base_url,
            api_key=_main_api_key,
            platform="webui",
            quiet_mode=True,
            enabled_toolsets=[],
            session_id=f"work-hub-plan-{uuid.uuid4().hex[:8]}",
        )
        result = agent.run_conversation(
            user_message=combined_goal,
            system_message=system_prompt,
            conversation_history=[],
            task_id=f"work-hub-plan-{uuid.uuid4().hex[:8]}",
        )
        text = str(result.get("final_response") or "").strip()
        if not text:
            raise PlanError("Planner returned no response")

        # Extract JSON from possible markdown code fence
        if "```" in text:
            text = text.split("```")[1].strip("json").strip()
        data = json.loads(text)
        items = data.get("items") if isinstance(data, dict) else None
        steps = normalize_ai_items(items)
        return {"goal": goal, "meta": _parse_goal(goal), "steps": steps}
    except PlanError:
        raise
    except Exception as exc:
        raise PlanError("Goal Planner could not create a structured plan") from exc
