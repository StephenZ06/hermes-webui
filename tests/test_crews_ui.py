"""Crews (multi-agent dispatch templates) UI wiring guards.

Structural checks (not a browser test) pinning that the toolbar button,
modal markup, and JS functions introduced for the Crews feature stay wired
together, and that it stays an ADDITIVE extension of the existing Kanban
panel -- no new nav tab, no new MAIN_VIEW_PANELS entry.

See docs/HERMES_STUDIO_PARITY_PLAN.md, "Multi-agent orchestration (Crews +
Conductor)" -> "Phase 1 (v1) -- Crew templates + bulk dispatch".

The dispatch-time {variable} collection dialog (Phase 1 follow-up: the
"Known gap" flagged in that section's "Shipped" note) is covered two ways:
placeholder-detection is executed for real via node (see
test_placeholder_variable_detection_behavior below -- a pure function, no
DOM, so this isn't a live-browser test, just real JS execution instead of a
weaker source-string proxy for it); the dialog's wiring/gating/cancel-path
guarantees stay structural source inspection like the rest of this file.
"""
import json
import re
import subprocess
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


INDEX_HTML = read("static/index.html")
PANELS_JS = read("static/panels.js")
STYLE_CSS = read("static/style.css")
I18N_JS = read("static/i18n.js")
COMMANDS_JS = read("static/commands.js")
ROUTES_PY = read("api/routes.py")
KANBAN_BRIDGE_PY = read("api/kanban_bridge.py")
CREWS_PY = read("api/crews.py")


def test_no_new_nav_tab_or_main_view_panel():
    """Crews must be additive UI inside the Kanban panel, not a new nav tab
    (docs/HERMES_STUDIO_PARITY_PLAN.md's explicit design constraint: a
    separate nav tab would double the poll/SSE wiring surface for zero new
    data)."""
    assert 'data-panel="crews"' not in INDEX_HTML
    assert "'crews'" not in PANELS_JS.split("MAIN_VIEW_PANELS")[1][:200]


def test_toolbar_button_present_next_to_office_view():
    match = re.search(r'<button[^>]+id="btnKanbanCrews"[^>]*>', INDEX_HTML, re.S)
    assert match, "Kanban board header must expose a Crews toolbar button"
    tag = match.group(0)
    assert 'onclick="openKanbanCrews()"' in tag
    assert 'data-i18n-title="kanban_crews"' in tag

    kanban_start = INDEX_HTML.index('id="mainKanban"')
    office_idx = INDEX_HTML.index('id="btnKanbanOfficeView"', kanban_start)
    crews_idx = INDEX_HTML.index('id="btnKanbanCrews"', kanban_start)
    preview_idx = INDEX_HTML.index('id="btnKanbanPreviewDispatcher"', kanban_start)
    assert office_idx < crews_idx < preview_idx


def test_modal_markup_present():
    assert 'id="kanbanCrewsModal"' in INDEX_HTML
    assert 'id="kanbanCrewList"' in INDEX_HTML
    assert 'id="kanbanCrewFormModal"' in INDEX_HTML
    assert 'id="kanbanCrewFormTasks"' in INDEX_HTML
    assert 'onclick="_kanbanAddCrewTaskRow({})"' in INDEX_HTML
    assert 'onclick="submitKanbanCrewForm()"' in INDEX_HTML
    # Same modal shell as the other Kanban modals (openKanbanCreateBoard()/
    # openKanbanCreate()).
    crews_modal_idx = INDEX_HTML.index('id="kanbanCrewsModal"')
    assert 'class="kanban-modal-overlay"' in INDEX_HTML[crews_modal_idx - 60:crews_modal_idx]


def test_panels_js_core_wiring_present():
    for fn in (
        "openKanbanCrews", "closeKanbanCrewsModal", "loadKanbanCrews",
        "_renderKanbanCrewList", "_kanbanCrewCard", "openKanbanCrewForm",
        "closeKanbanCrewFormModal", "_kanbanAddCrewTaskRow",
        "_kanbanRemoveCrewTaskRow", "_kanbanCollectCrewFormTasks",
        "submitKanbanCrewForm", "duplicateKanbanCrew", "deleteKanbanCrew",
        "dispatchKanbanCrew",
    ):
        assert f"function {fn}(" in PANELS_JS, f"{fn} not defined in panels.js"
    assert re.search(r"api\('/api/crews'\)", PANELS_JS)
    assert re.search(r"api\('/api/crews/create',\s*\{\s*method:\s*'POST'", PANELS_JS)
    assert re.search(r"api\('/api/crews/update',\s*\{\s*method:\s*'POST'", PANELS_JS)
    assert re.search(r"api\('/api/crews/delete',\s*\{\s*method:\s*'POST'", PANELS_JS)
    assert re.search(r"api\('/api/crews/duplicate',\s*\{\s*method:\s*'POST'", PANELS_JS)
    assert "'/api/crews/' + encodeURIComponent(id) + '/dispatch'" in PANELS_JS


def test_dispatch_requires_confirm_dialog():
    """Cost-consuming action -- must gate on showConfirmDialog, same pattern
    as runKanbanDispatcher(), before ever POSTing to the dispatch endpoint."""
    idx = PANELS_JS.index("async function dispatchKanbanCrew(id)")
    end = PANELS_JS.index("\nfunction _kanbanSelectedTaskIds", idx)
    body = PANELS_JS[idx:end]
    assert "await showConfirmDialog(" in body
    confirm_idx = body.index("await showConfirmDialog(")
    dispatch_call_idx = body.index("/dispatch'")
    assert confirm_idx < dispatch_call_idx
    assert "if (!ok) return;" in body


def test_dispatch_never_calls_dispatch_once_or_run_dispatcher():
    """Regression: bulk-creating a crew's tasks must never itself trigger the
    dispatcher/dispatch_once -- a human must still click Run Dispatcher
    separately (docs/HERMES_STUDIO_PARITY_PLAN.md's explicit design
    constraint)."""
    idx = PANELS_JS.index("async function dispatchKanbanCrew(id)")
    end = PANELS_JS.index("\nfunction _kanbanSelectedTaskIds", idx)
    body = PANELS_JS[idx:end]
    # Check for actual call syntax, not just the substring -- explanatory
    # comments in this function legitimately reference dispatch_once by name
    # to document why it is deliberately NOT called here.
    assert "dispatch_once(" not in body
    assert "/api/kanban/dispatch" not in body


def test_assignee_select_reuses_shared_helper_not_a_copy():
    """Crew task rows must reuse _kanbanPopulateAssigneeSelect() (extended
    with an optional target-element param) rather than a parallel
    profile-lookup implementation (GUIDELINES rule 8)."""
    assert "async function _kanbanPopulateAssigneeSelect(currentValue, selEl)" in PANELS_JS
    idx = PANELS_JS.index("async function _kanbanAddCrewTaskRow(taskSpec)")
    end = PANELS_JS.index("\nfunction _kanbanRemoveCrewTaskRow", idx)
    body = PANELS_JS[idx:end]
    assert "_kanbanPopulateAssigneeSelect(" in body
    assert "/api/profiles" not in body  # no separate profile fetch in this function


def test_css_uses_theme_tokens():
    assert ".kanban-crew-card" in STYLE_CSS
    idx = STYLE_CSS.index("/* Crews:")
    block = STYLE_CSS[idx: idx + 1800]
    assert "var(--border)" in block
    assert "var(--accent" in block
    assert "var(--muted)" in block
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", block)


def test_slash_command_wired_list_only():
    assert "name:'crews'" in COMMANDS_JS.replace(" ", "")
    assert "async function cmdCrews(" in COMMANDS_JS
    assert "/api/crews" in COMMANDS_JS
    # v1 is list-only -- dispatch-via-slash-command is explicitly
    # optional/deferrable per the plan; must not silently bypass the
    # confirm-dialog dispatch flow.
    assert "/api/crews/" not in COMMANDS_JS.split("async function cmdCrews(")[1].split("\nasync function ")[0]


def test_backend_caps_present():
    assert "NAME_MAX = 128" in CREWS_PY
    assert "DESCRIPTION_MAX = 512" in CREWS_PY
    assert "MAX_CREWS = 50" in CREWS_PY
    assert "MAX_TASKS_PER_CREW = 20" in CREWS_PY


def test_routes_wired():
    assert '"/api/crews"' in ROUTES_PY
    assert '"/api/crews/create"' in ROUTES_PY
    assert '"/api/crews/update"' in ROUTES_PY
    assert '"/api/crews/delete"' in ROUTES_PY
    assert '"/api/crews/duplicate"' in ROUTES_PY
    assert "_CREWS_DISPATCH_PREFIX" in ROUTES_PY
    assert "endswith(\"/dispatch\")" in ROUTES_PY


def test_dispatch_route_never_calls_dispatch_once():
    """Same regression as the frontend guard, pinned server-side: the request
    handler for /api/crews/*/dispatch must never touch the dispatcher."""
    idx = ROUTES_PY.index("_CREWS_DISPATCH_PREFIX = \"/api/crews/\"")
    end = ROUTES_PY.index("\n    if parsed.path == \"/api/agent-definitions/apply\"", idx)
    body = ROUTES_PY[idx:end]
    # Check for actual call syntax, not just the substring -- an explanatory
    # comment in this block legitimately references dispatch_once by name to
    # document why it is deliberately NOT called here.
    assert "dispatch_once(" not in body
    assert "dispatch_crew" in body


def test_kanban_bridge_extension_point_present():
    assert "workflow_template_id" in KANBAN_BRIDGE_PY
    assert "current_step_key" in KANBAN_BRIDGE_PY
    assert "inspect.signature(kb.create_task)" in KANBAN_BRIDGE_PY
    assert "UPDATE tasks SET workflow_template_id = ?, current_step_key = ? WHERE id = ?" in KANBAN_BRIDGE_PY


def test_i18n_keys_present_in_all_15_locales():
    required_keys = [
        "kanban_crews", "kanban_crews_hint", "kanban_crews_empty", "kanban_new_crew",
        "kanban_crew_name", "kanban_crew_name_placeholder", "kanban_crew_icon",
        "kanban_crew_color", "kanban_crew_description", "kanban_crew_description_placeholder",
        "kanban_crew_tasks", "kanban_crew_add_task", "kanban_crew_task_title",
        "kanban_crew_task_title_placeholder", "kanban_crew_task_body", "kanban_crew_task_assignee",
        "kanban_crew_task_skills", "kanban_crew_task_skills_placeholder", "kanban_crew_task_priority",
        "kanban_crew_remove_task", "kanban_crew_task_singular", "kanban_crew_task_plural",
        "kanban_crew_dispatch", "kanban_crew_duplicate", "kanban_crew_close",
        "kanban_crew_name_required", "kanban_crew_tasks_required", "kanban_crew_created",
        "kanban_crew_updated", "kanban_crew_duplicated", "kanban_crew_deleted",
        "kanban_crew_delete_confirm", "kanban_crew_dispatch_confirm_title",
        "kanban_crew_dispatch_confirm_message", "kanban_crew_dispatch_result", "cmd_crews",
        # Dispatch-time {variable} collection dialog (Phase 1 follow-up).
        "kanban_crew_dispatch_vars_title", "kanban_crew_dispatch_vars_hint",
        "kanban_crew_dispatch_vars_label", "kanban_crew_dispatch_vars_placeholder",
        "kanban_crew_dispatch_vars_required",
        # Phase 1.2: templates gallery search + last-dispatched recency.
        "kanban_crews_search_placeholder", "kanban_crews_no_match",
        "kanban_crew_last_dispatched", "kanban_crew_never_dispatched",
    ]
    locale_keys = re.findall(r"^  (?:'([a-zA-Z-]+)'|([a-zA-Z-]+)): \{$", I18N_JS, re.MULTILINE)
    locales = [a or b for a, b in locale_keys]
    assert locales == [
        "en", "it", "ja", "ru", "es", "de", "zh", "zh-Hant", "pt", "ko",
        "fr", "cs", "tr", "pl", "vi",
    ], locales

    starts = [m.start() for m in re.finditer(r"^  (?:'[a-zA-Z-]+'|[a-zA-Z-]+): \{$", I18N_JS, re.MULTILINE)]
    starts.append(len(I18N_JS))
    for i, locale in enumerate(locales):
        block = I18N_JS[starts[i]:starts[i + 1]]
        for key in required_keys:
            count = len(re.findall(rf"^    {re.escape(key)}: ", block, re.MULTILINE))
            assert count == 1, f"{locale} locale: expected exactly one '{key}', found {count}"


# ─────────────────────────────────────────────────────────────────────────
# Dispatch-time {variable} collection dialog (Phase 1 follow-up).
#
# api/crews.py's _substitute_variables does a single flat str.format-style
# pass over a caller-supplied `variables` dict at dispatch time. Before this
# follow-up, dispatchKanbanCrew() always sent `variables: {}`, so a template
# using {topic}-style placeholders either dispatched with the literal
# "{topic}" left in the task, or (confirmed by reading _substitute_variables/
# dispatch_crew) raised KeyError per-task-spec, caught by dispatch_crew's
# `except Exception` and surfaced as that one spec's {ok: false, error: ...}
# without aborting sibling specs.
# ─────────────────────────────────────────────────────────────────────────


def _run_node_extraction(js_body: str) -> None:
    """Runs a script that extracts one or more panels.js functions by
    scanning for balanced braces (same technique already used by other
    node-execution tests in this suite, e.g. tests/test_issue4496_plugin_badge_state.py)
    and asserts real behavior on them -- not source-string matching."""
    proc = subprocess.run(
        ["node", "-e", js_body],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"node script failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"


def test_placeholder_variable_detection_behavior():
    """Executes the real _kanbanCrewTemplateVariables() extracted from
    static/panels.js (a pure function -- no DOM, so this is not a live-browser
    test, just real JS execution) against title-only, body-only, both,
    none, and duplicate-name-across-specs cases."""
    script = textwrap.dedent(
        f"""
        const fs = require('fs');
        const assert = require('assert');
        const src = fs.readFileSync({json.dumps(str(REPO / "static" / "panels.js"))}, 'utf8');

        function extractFunction(name) {{
          const marker = 'function ' + name;
          const start = src.indexOf(marker);
          if (start < 0) throw new Error('missing function ' + name);
          const brace = src.indexOf('{{', start);
          let depth = 1;
          let i = brace + 1;
          while (depth && i < src.length) {{
            if (src[i] === '{{') depth += 1;
            else if (src[i] === '}}') depth -= 1;
            i += 1;
          }}
          return src.slice(start, i);
        }}

        eval(extractFunction('_kanbanCrewTemplateVariables'));

        // title-only
        assert.deepStrictEqual(
          _kanbanCrewTemplateVariables({{tasks: [{{title: 'Research: {{topic}} — angle', body: ''}}]}}),
          ['topic']
        );

        // body-only
        assert.deepStrictEqual(
          _kanbanCrewTemplateVariables({{tasks: [{{title: 'Research', body: 'Focus on {{topic}}.'}}]}}),
          ['topic']
        );

        // both title and body, distinct names, in first-seen order
        assert.deepStrictEqual(
          _kanbanCrewTemplateVariables({{tasks: [{{title: '{{topic}} report', body: 'for {{client}}'}}]}}),
          ['topic', 'client']
        );

        // none
        assert.deepStrictEqual(
          _kanbanCrewTemplateVariables({{tasks: [{{title: 'Plain title', body: 'Plain body'}}]}}),
          []
        );

        // duplicate variable names across specs collapse to one entry
        assert.deepStrictEqual(
          _kanbanCrewTemplateVariables({{tasks: [
            {{title: 'Research: {{topic}} — market angle', body: ''}},
            {{title: 'Research: {{topic}} — technical angle', body: 'CC {{stakeholder}}'}},
          ]}}),
          ['topic', 'stakeholder']
        );

        // no tasks at all
        assert.deepStrictEqual(_kanbanCrewTemplateVariables({{tasks: []}}), []);
        assert.deepStrictEqual(_kanbanCrewTemplateVariables({{}}), []);

        console.log('OK');
        """
    )
    _run_node_extraction(script)


def test_zero_placeholder_crews_skip_dialog_and_dispatch_unaffected():
    """A crew whose task specs contain no {variable} placeholders must
    dispatch immediately with variables: {} -- same behavior as before this
    follow-up, no extra dialog step."""
    idx = PANELS_JS.index("async function dispatchKanbanCrew(id)")
    end = PANELS_JS.index("\nfunction _kanbanSelectedTaskIds", idx)
    body = PANELS_JS[idx:end]
    assert "let variables = {};" in body
    assert "_kanbanCrewTemplateVariables(crew)" in body
    # The vars dialog is only opened inside a `variableNames.length` guard --
    # zero placeholders means openKanbanCrewDispatchVarsModal is never called.
    gate_idx = body.index("if (variableNames.length) {")
    modal_call_idx = body.index("openKanbanCrewDispatchVarsModal(variableNames)")
    dispatch_call_idx = body.index("/dispatch'")
    assert gate_idx < modal_call_idx < dispatch_call_idx
    # The dispatch POST body always carries a `variables` field (an empty
    # object when the gate above never ran) -- not omitted.
    assert "const dispatchBody = {variables};" in body


def test_dispatch_vars_dialog_cancel_never_dispatches():
    """Cancelling the variable-collection dialog (Cancel button / overlay
    click / Esc, all routed through closeKanbanCrewDispatchVarsModal) must
    resolve the pending Promise with null, which dispatchKanbanCrew()
    must treat as an abort -- never reaching the /dispatch POST."""
    idx = PANELS_JS.index("async function dispatchKanbanCrew(id)")
    end = PANELS_JS.index("\nfunction _kanbanSelectedTaskIds", idx)
    body = PANELS_JS[idx:end]
    collect_idx = body.index("await openKanbanCrewDispatchVarsModal(variableNames)")
    abort_idx = body.index("if (!collected) return;")
    dispatch_call_idx = body.index("/dispatch'")
    assert collect_idx < abort_idx < dispatch_call_idx

    # closeKanbanCrewDispatchVarsModal (the cancel path) resolves the pending
    # promise with null and must never itself call the dispatch API.
    close_idx = PANELS_JS.index("function closeKanbanCrewDispatchVarsModal(){")
    close_end = PANELS_JS.index("\n}", close_idx)
    close_body = PANELS_JS[close_idx:close_end]
    assert "resolve(null);" in close_body
    assert "api(" not in close_body
    assert "/dispatch" not in close_body

    # The submit path (_kanbanSubmitCrewDispatchVars) resolves with the
    # collected map, and it also never calls the dispatch API directly --
    # dispatching only happens back in dispatchKanbanCrew after the awaited
    # Promise resolves.
    submit_idx = PANELS_JS.index("function _kanbanSubmitCrewDispatchVars(){")
    submit_end = PANELS_JS.index("\n}", submit_idx)
    submit_body = PANELS_JS[submit_idx:submit_end]
    assert "resolve(variables);" in submit_body
    assert "api(" not in submit_body
    assert "/dispatch" not in submit_body


def test_dispatch_vars_modal_markup_present():
    assert 'id="kanbanCrewDispatchVarsModal"' in INDEX_HTML
    assert 'id="kanbanCrewDispatchVarsFields"' in INDEX_HTML
    assert 'id="kanbanCrewDispatchVarsError"' in INDEX_HTML
    assert 'onclick="closeKanbanCrewDispatchVarsModal()"' in INDEX_HTML
    assert 'onclick="_kanbanSubmitCrewDispatchVars()"' in INDEX_HTML
    # Same modal shell as the other Kanban modals.
    modal_idx = INDEX_HTML.index('id="kanbanCrewDispatchVarsModal"')
    assert 'class="kanban-modal-overlay"' in INDEX_HTML[modal_idx - 60:modal_idx]


def test_dispatch_vars_panels_js_functions_present():
    for fn in (
        "_kanbanCrewTemplateVariables", "openKanbanCrewDispatchVarsModal",
        "closeKanbanCrewDispatchVarsModal", "_kanbanSubmitCrewDispatchVars",
        "_kanbanHideCrewDispatchVarsModal",
    ):
        assert f"function {fn}(" in PANELS_JS, f"{fn} not defined in panels.js"


# ─────────────────────────────────────────────────────────────────────────
# Phase 1.2: crew templates gallery -- search/filter + last-dispatched
# recency sort. Deliberately does NOT touch dispatchKanbanCrew()'s body, the
# {variable} collection dialog, or the create/edit form (see the plan's
# "Deliberately not touched" note -- another agent owns that code path
# concurrently).
# ─────────────────────────────────────────────────────────────────────────


def test_crews_search_input_present_and_wired():
    assert 'id="kanbanCrewsSearch"' in INDEX_HTML
    match = re.search(r'<input[^>]+id="kanbanCrewsSearch"[^>]*>', INDEX_HTML, re.S)
    assert match, "Crews modal must expose a search input"
    tag = match.group(0)
    assert 'oninput="filterKanbanCrews()"' in tag
    assert 'data-i18n-placeholder="kanban_crews_search_placeholder"' in tag
    # Sits above the list inside the Crews modal, reusing the shared
    # .sidebar-search component (same one #kanbanSearch/#agentsSearch use)
    # rather than a new search-box implementation.
    modal_idx = INDEX_HTML.index('id="kanbanCrewsModal"')
    search_idx = INDEX_HTML.index('id="kanbanCrewsSearch"')
    list_idx = INDEX_HTML.index('id="kanbanCrewList"')
    assert modal_idx < search_idx < list_idx
    assert "sidebar-search" in INDEX_HTML[search_idx - 400:search_idx]


def test_filter_and_sort_panels_js_functions_present():
    for fn in ("filterKanbanCrews", "_kanbanFilterCrews", "_kanbanSortCrews"):
        assert f"function {fn}(" in PANELS_JS, f"{fn} not defined in panels.js"
    # filterKanbanCrews mirrors filterAgentDefinitions()'s call-render-again
    # pattern rather than re-implementing filtering inline at the call site.
    idx = PANELS_JS.index("function filterKanbanCrews(")
    end = PANELS_JS.index("\n}", idx)
    assert "_renderKanbanCrewList()" in PANELS_JS[idx:end]
    # _renderKanbanCrewList must actually read the search box and use both
    # new pure helpers, not duplicate their logic inline.
    render_idx = PANELS_JS.index("function _renderKanbanCrewList(")
    render_end = PANELS_JS.index("\n}", render_idx)
    render_body = PANELS_JS[render_idx:render_end]
    assert "kanbanCrewsSearch" in render_body
    assert "_kanbanFilterCrews(" in render_body
    assert "_kanbanSortCrews(" in render_body


def test_card_reuses_shared_relative_time_formatter_not_a_copy():
    """The last-dispatched meta line must reuse
    _formatRelativeSessionTime() (static/sessions.js) rather than a second
    relative-time formatter (GUIDELINES rule 8)."""
    idx = PANELS_JS.index("function _kanbanCrewCard(crew)")
    end = PANELS_JS.index("\n}", idx)
    body = PANELS_JS[idx:end]
    assert "crew.last_dispatched_at" in body
    assert "_formatRelativeSessionTime(" in body
    assert "kanban_crew_last_dispatched" in body
    assert "kanban_crew_never_dispatched" in body


def test_backend_last_dispatched_field_present():
    assert "last_dispatched_at" in CREWS_PY
    assert "def _touch_crew_dispatched(" in CREWS_PY


def _run_node_script(js_body: str) -> None:
    proc = subprocess.run(["node", "-e", js_body], cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 0, f"node script failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"


def test_filter_and_sort_behavior_real_execution():
    """Executes the real _kanbanFilterCrews()/_kanbanSortCrews() extracted
    from static/panels.js (pure functions, no DOM) against synthetic crew
    lists -- not a source-string proxy."""
    script = textwrap.dedent(
        f"""
        const fs = require('fs');
        const assert = require('assert');
        const src = fs.readFileSync({json.dumps(str(REPO / "static" / "panels.js"))}, 'utf8');

        function extractFunction(name) {{
          const marker = 'function ' + name;
          const start = src.indexOf(marker);
          if (start < 0) throw new Error('missing function ' + name);
          const brace = src.indexOf('{{', start);
          let depth = 1;
          let i = brace + 1;
          while (depth && i < src.length) {{
            if (src[i] === '{{') depth += 1;
            else if (src[i] === '}}') depth -= 1;
            i += 1;
          }}
          return src.slice(start, i);
        }}

        eval(extractFunction('_kanbanFilterCrews'));
        eval(extractFunction('_kanbanSortCrews'));

        const crews = [
          {{id: 'a', name: 'Research crew', description: 'Market angles', created_at: 10, last_dispatched_at: null}},
          {{id: 'b', name: 'Deploy crew', description: 'Ship it', created_at: 20, last_dispatched_at: 500}},
          {{id: 'c', name: 'Review crew', description: 'Research follow-up', created_at: 30, last_dispatched_at: null}},
          {{id: 'd', name: 'Ops crew', description: '', created_at: 5, last_dispatched_at: 900}},
        ];

        // Case-insensitive substring match against name OR description.
        assert.deepStrictEqual(
          _kanbanFilterCrews(crews, 'research').map(c => c.id).sort(),
          ['a', 'c']
        );
        assert.deepStrictEqual(
          _kanbanFilterCrews(crews, 'DEPLOY').map(c => c.id),
          ['b']
        );
        // Empty/whitespace query returns everything, unfiltered, same order.
        assert.deepStrictEqual(_kanbanFilterCrews(crews, '').map(c => c.id), ['a', 'b', 'c', 'd']);
        assert.deepStrictEqual(_kanbanFilterCrews(crews, '   ').map(c => c.id), ['a', 'b', 'c', 'd']);
        // No match.
        assert.deepStrictEqual(_kanbanFilterCrews(crews, 'nonexistent'), []);

        // Sort: last_dispatched_at descending, never-dispatched (null) last,
        // tied by created_at descending.
        assert.deepStrictEqual(
          _kanbanSortCrews(crews).map(c => c.id),
          ['d', 'b', 'c', 'a']
        );

        console.log('OK');
        """
    )
    _run_node_script(script)


def test_css_search_and_last_dispatched_use_theme_tokens():
    idx = STYLE_CSS.index("/* Crews:")
    block = STYLE_CSS[idx: idx + 3000]
    assert ".kanban-crews-search" in block
    assert ".kanban-crew-card-last-dispatched" in block
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", block)
