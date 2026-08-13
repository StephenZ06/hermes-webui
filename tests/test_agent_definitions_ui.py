"""Personas (agent definitions) UI wiring guards.

Structural checks (not a browser test) pinning that the nav tab, panel
container, main detail pane, and JS functions introduced for the Personas
feature stay wired together. See docs/HERMES_STUDIO_PARITY_PLAN.md,
"Priority 1 -- Personas".
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def test_nav_tab_and_panel_containers_present():
    html = read("static/index.html")
    assert 'data-panel="agents"' in html
    assert "onclick=\"switchPanel('agents'" in html
    assert 'id="panelAgents"' in html
    assert 'id="mainAgents"' in html
    assert 'id="agentsList"' in html
    assert 'id="agentsSearch"' in html
    assert 'id="agentDefDetailTitle"' in html
    assert 'id="agentDefDetailBody"' in html
    assert 'id="agentDefDetailEmpty"' in html


def test_apply_to_session_buttons_present():
    html = read("static/index.html")
    assert 'id="btnApplyAgentDefDetail"' in html
    assert 'onclick="applyAgentDefToSession()"' in html
    assert 'id="btnClearAgentDefDetail"' in html
    assert 'onclick="clearAppliedAgentDef()"' in html


def test_main_view_css_wiring_present():
    css = read("static/style.css")
    assert "main.main > #mainAgents" in css
    assert "main.main.showing-agents > #mainAgents{display:flex;}" in css
    assert ":not(.showing-agents)" in css


def test_panels_js_core_wiring_present():
    js = read("static/panels.js")
    for fn in (
        "loadAgentDefinitions", "renderAgentDefinitions", "filterAgentDefinitions",
        "openAgentDefDetail", "_renderAgentDefDetail", "openAgentDefCreate",
        "editCurrentAgentDef", "_renderAgentDefForm", "saveAgentDefForm",
        "duplicateAgentDef", "deleteAgentDef", "_setAgentDefHeaderButtons",
        "cancelAgentDefForm", "applyAgentDefToSession", "clearAppliedAgentDef",
    ):
        assert f"function {fn}(" in js, f"{fn} not defined in panels.js"
    assert "'agents'" in js.split("MAIN_VIEW_PANELS")[1][:200]
    assert re.search(r"api\('/api/agent-definitions/create',\s*\{\s*method:'POST'", js)
    assert re.search(r"api\('/api/agent-definitions/update',\s*\{\s*method:'POST'", js)
    assert re.search(r"api\('/api/agent-definitions/delete',\s*\{\s*method:'POST'", js)
    assert re.search(r"api\('/api/agent-definitions/duplicate',\s*\{\s*method:'POST'", js)
    assert re.search(r"api\('/api/agent-definitions/apply',\s*\{\s*method:'POST'", js)


def test_apply_button_visibility_keyed_on_session_state():
    js = read("static/panels.js")
    assert "S.session.agent_definition_id === def.id" in js
    assert "btnApplyAgentDefDetail" in js
    assert "btnClearAgentDefDetail" in js


def test_builtin_personas_cannot_be_edited_in_ui():
    js = read("static/panels.js")
    assert "_currentAgentDefDetail.builtin) return;" in js


def test_builtin_personas_can_be_deleted_in_ui():
    """Delete is a persistent soft-hide for builtins (agent_definitions.py
    delete_definition), not a real removal -- BUILTIN_DEFINITIONS is a Python
    source constant. The UI must not special-case builtins out of delete."""
    js = read("static/panels.js")
    delete_fn_start = js.find("async function deleteAgentDef()")
    assert delete_fn_start != -1, "deleteAgentDef() not found"
    delete_fn_end = js.find("\n}\n", delete_fn_start)
    delete_fn_body = js[delete_fn_start:delete_fn_end]
    assert "builtin" not in delete_fn_body, (
        "deleteAgentDef() must not early-return on .builtin -- builtin delete "
        "is now a supported soft-hide, gated server-side instead"
    )
    assert "show(delBtn);" in js, (
        "the delete button must be shown unconditionally in read mode, "
        "not hidden for builtin personas"
    )


def test_slash_command_wired():
    js = read("static/commands.js")
    assert "name:'personas'" in js.replace(" ", "")
    assert "function cmdPersonas(" in js
    assert "/api/agent-definitions" in js


def test_backend_caps_present():
    module = read("api/agent_definitions.py")
    assert "NAME_MAX = 128" in module
    assert "SYSTEM_PROMPT_MAX = 8000" in module
    assert "MAX_CUSTOM_DEFINITIONS = 100" in module
    assert "Built-in agent definitions cannot" in module


def test_apply_endpoint_and_chokepoint_wired():
    module = read("api/agent_definitions.py")
    assert "def get_definition(" in module

    routes = read("api/routes.py")
    assert '"/api/agent-definitions/apply"' in routes
    assert "s.agent_definition_id = def_id if def_id else None" in routes

    models = read("api/models.py")
    assert "agent_definition_id" in models

    streaming = read("api/streaming.py")
    assert "_persona_prompt" in streaming
    assert "agent_definitions.get_definition(_persona_id)" in streaming
    # Must extend the existing chokepoint, not add a parallel prompt-injection
    # path — docs/HERMES_STUDIO_PARITY_PLAN.md's explicit design constraint.
    assert "_webui_ephemeral_system_prompt(\n                _combined_personality_prompt," in streaming


def test_i18n_keys_present_in_all_15_locales():
    src = read("static/i18n.js")
    required_keys = [
        "tab_agents", "new_agent_def", "search_agent_defs", "agent_def_empty_title",
        "agent_def_empty_sub", "agent_def_duplicate", "agent_def_no_match",
        "agent_def_builtin_hint", "agent_def_type", "agent_def_builtin_badge",
        "agent_def_role", "agent_def_tags", "agent_def_system_prompt",
        "agent_def_no_system_prompt", "agent_def_name", "agent_def_name_placeholder",
        "agent_def_emoji", "agent_def_color", "agent_def_color_hint",
        "agent_def_role_placeholder", "agent_def_tags_placeholder",
        "agent_def_system_prompt_placeholder", "agent_def_name_required",
        "agent_def_updated", "agent_def_created", "agent_def_duplicated",
        "agent_def_deleted", "agent_def_delete_confirm", "cmd_personas",
        "agent_def_apply", "agent_def_clear", "agent_def_status",
        "agent_def_applied_badge", "agent_def_applied", "agent_def_cleared",
        "agent_def_apply_hint",
    ]
    locale_keys = re.findall(r"^  (?:'([a-zA-Z-]+)'|([a-zA-Z-]+)): \{$", src, re.MULTILINE)
    locales = [a or b for a, b in locale_keys]
    assert locales == [
        "en", "it", "ja", "ru", "es", "de", "zh", "zh-Hant", "pt", "ko",
        "fr", "cs", "tr", "pl", "vi",
    ], locales

    # Split into per-locale blocks by locale-start line, then confirm every
    # required key is present exactly once in each block.
    starts = [m.start() for m in re.finditer(r"^  (?:'[a-zA-Z-]+'|[a-zA-Z-]+): \{$", src, re.MULTILINE)]
    starts.append(len(src))
    for i, locale in enumerate(locales):
        block = src[starts[i]:starts[i + 1]]
        for key in required_keys:
            count = len(re.findall(rf"^    {re.escape(key)}: ", block, re.MULTILINE))
            assert count == 1, f"{locale} locale: expected exactly one '{key}', found {count}"
