"""Kanban office view — multi-agent orchestration mission-control panel
(Priority 2, docs/HERMES_STUDIO_PARITY_PLAN.md).

Scope note baked into the code and asserted here: this visualizes
Kanban-dispatched workers only (task.worker_pid, set by
hermes_cli.kanban_db.dispatch_once, which runs in-process inside hermes-webui's
own container). It deliberately does NOT attempt live delegate_task/subagent
status — that registry (tools/delegate_tool.py's _active_subagents) lives
inside the separate `hermes` container's process memory, which runs a
pre-built image rather than the locally mounted hermes-agent-src, so there is
no reachable endpoint for it. See the comment block above
_kanbanOfficeViewWorkers in static/panels.js for the full reasoning.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
PANELS_JS = (ROOT / "static" / "panels.js").read_text(encoding="utf-8")
STYLE_CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
I18N_JS = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")


def test_kanban_header_exposes_office_view_toggle():
    match = re.search(r'<button[^>]+id="btnKanbanOfficeView"[^>]*>', INDEX_HTML, re.S)
    assert match, "Kanban board header must expose an office-view toggle"
    tag = match.group(0)
    assert 'onclick="toggleKanbanOfficeView()"' in tag
    assert 'aria-pressed="false"' in tag
    assert 'data-i18n-title="kanban_office_view"' in tag

    kanban_start = INDEX_HTML.index('id="mainKanban"')
    office_idx = INDEX_HTML.index('id="btnKanbanOfficeView"', kanban_start)
    view_toggle_idx = INDEX_HTML.index('id="btnKanbanViewToggle"', kanban_start)
    preview_idx = INDEX_HTML.index('id="btnKanbanPreviewDispatcher"', kanban_start)
    assert view_toggle_idx < office_idx < preview_idx


def test_office_view_container_present_alongside_board():
    wrap_idx = INDEX_HTML.index('class="kanban-board-wrap"')
    board_idx = INDEX_HTML.index('id="kanbanBoard"', wrap_idx)
    office_idx = INDEX_HTML.index('id="kanbanOfficeView"', wrap_idx)
    assert board_idx < office_idx
    assert 'style="display:none"' in INDEX_HTML[office_idx: office_idx + 60]


def test_toggle_shows_hides_the_right_containers():
    assert "function toggleKanbanOfficeView()" in PANELS_JS
    idx = PANELS_JS.index("function toggleKanbanOfficeView()")
    end = PANELS_JS.index("\nfunction ", idx + 10)
    body = PANELS_JS[idx:end]
    assert "_kanbanOfficeViewActive = !_kanbanOfficeViewActive" in body
    assert "board.style.display = _kanbanOfficeViewActive ? 'none' : ''" in body
    assert "office.style.display = _kanbanOfficeViewActive ? '' : 'none'" in body
    assert "_kanbanRenderOfficeView();" in body


def test_render_hooked_into_every_board_render_call_site():
    """The office view must stay in sync with the SAME refresh paths that
    already drive the normal board (poll/SSE, filter, lane toggle) — added
    as one call inside _kanbanRenderBoard() rather than needing separate
    wiring at each of its callers."""
    idx = PANELS_JS.index("function _kanbanRenderBoard()")
    end = PANELS_JS.index("\nfunction _kanbanCard(", idx)
    body = PANELS_JS[idx:end]
    assert "if (typeof _kanbanRenderOfficeView === 'function') _kanbanRenderOfficeView();" in body


def test_worker_filter_matches_dispatch_backed_running_tasks_only():
    """Must key off BOTH status==='running' and worker_pid — a task can be
    'running' via manual status edit without ever having been dispatched."""
    idx = PANELS_JS.index("function _kanbanOfficeViewWorkers()")
    end = PANELS_JS.index("\nfunction ", idx + 10)
    body = PANELS_JS[idx:end]
    assert "task.status === 'running' && task.worker_pid" in body


def test_log_fetch_reuses_existing_worker_log_endpoint():
    assert "async function toggleKanbanOfficeLog(taskId)" in PANELS_JS
    idx = PANELS_JS.index("async function toggleKanbanOfficeLog(taskId)")
    end = PANELS_JS.index("\nfunction ", idx + 10)
    body = PANELS_JS[idx:end]
    assert "/api/kanban/tasks/' + encodeURIComponent(taskId) + '/log'" in body
    assert "_kanbanOfficeLogCache.set(taskId" in body


def test_log_cache_prevents_flicker_on_routine_rerender():
    """A poll/SSE-triggered re-render must not blank an already-open log
    panel while a background refetch is pending — render from cache first."""
    idx = PANELS_JS.index("function _kanbanOfficeCard(task)")
    end = PANELS_JS.index("\nasync function ", idx + 10)
    body = PANELS_JS[idx:end]
    assert "_kanbanOfficeLogCache.get(task.id)" in body


def test_expanded_set_pruned_of_workers_no_longer_running():
    idx = PANELS_JS.index("function _kanbanRenderOfficeView()")
    end = PANELS_JS.index("\nasync function hardRefreshWebUIClient", idx)
    body = PANELS_JS[idx:end]
    assert "if (!liveIds.has(id)) _kanbanOfficeExpanded.delete(id)" in body


def test_css_uses_theme_tokens():
    assert ".kanban-office-grid" in STYLE_CSS
    idx = STYLE_CSS.index("/* Office view:")
    block = STYLE_CSS[idx: idx + 2000]
    assert "var(--success)" in block
    assert "var(--border)" in block
    assert "var(--accent)" in block
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", block)


def test_i18n_keys_present_in_all_15_locales():
    required_keys = [
        "kanban_office_view", "kanban_office_empty",
        "kanban_office_view_log", "kanban_office_hide_log",
        # Phase 2 (office-view crew grouping): trailing "Ungrouped" section
        # label and the new crew-filter <select>'s aria-label / default option.
        "kanban_office_ungrouped", "kanban_crew_filter_label", "kanban_all_crews",
    ]
    locale_keys = re.findall(r"^  (?:'([a-zA-Z-]+)'|([a-zA-Z-]+)): \{$", I18N_JS, re.MULTILINE)
    locales = [a or b for a, b in locale_keys]
    assert len(locales) == 15, locales

    starts = [m.start() for m in re.finditer(r"^  (?:'[a-zA-Z-]+'|[a-zA-Z-]+): \{$", I18N_JS, re.MULTILINE)]
    starts.append(len(I18N_JS))
    for name, start, end in zip(locales, starts, starts[1:]):
        block = I18N_JS[start:end]
        missing = [k for k in required_keys if f"{k}:" not in block]
        assert not missing, f"locale {name!r} missing keys: {missing}"


def test_scope_documented_in_source_not_just_docs():
    """Pin the deliberate scope decision (Kanban workers only, not
    delegate_task) as a comment in the code itself, not only in chat/docs,
    so a future contributor doesn't 'fix' this by trying to reach the
    cross-container registry."""
    idx = PANELS_JS.index("_kanbanOfficeViewActive = false;")
    comment_block = PANELS_JS[max(0, idx - 900): idx]
    assert "_active_subagents" in comment_block
    assert "nousresearch/hermes-agent" in comment_block or "pre-built" in comment_block


# ── Phase 2 (v1.1): office-view crew grouping ──
# docs/HERMES_STUDIO_PARITY_PLAN.md, "#### Phase 2 (v1.1) — Office-view crew
# grouping". Purely additive to the office view shipped above: workers are
# grouped by task.workflow_template_id (the dispatching crew's id, set by
# Crews Phase 1's bulk-dispatch) into per-crew sections, with an "Ungrouped"
# section (CLI-created / pre-Crews tasks) always trailing.

def test_workers_grouped_by_workflow_template_id_multiple_crews_interleaved():
    """Two crews' workers dispatched interleaved on the board (crew A, crew
    B, crew A again) must still come back as two contiguous groups, not a
    flat interleaved list -- the whole point of grouping."""
    idx = PANELS_JS.index("function _kanbanOfficeViewWorkers()")
    end = PANELS_JS.index("\nfunction ", idx + 10)
    body = PANELS_JS[idx:end]
    assert "task.status === 'running' && task.worker_pid" in body
    # Buckets keyed by workflow_template_id, built while walking the flat
    # worker list once (so insertion order == first-appearance order, and an
    # interleaved A/B/A ordering still lands both A workers in one bucket).
    assert "task.workflow_template_id" in body
    assert "groups.has(key)" in body and "groups.get(key).push(task)" in body


def test_ungrouped_bucket_is_forced_trailing_not_first_appearance_order():
    """The null (ungrouped) bucket must be appended after every named crew
    group regardless of when its first ungrouped worker appeared in the
    flat list -- so an ungrouped worker claimed before any crew worker still
    renders last, not first."""
    idx = PANELS_JS.index("function _kanbanOfficeViewWorkers()")
    end = PANELS_JS.index("\nfunction ", idx + 10)
    body = PANELS_JS[idx:end]
    assert "const key = task.workflow_template_id || null;" in body
    assert "templateId: null" in body
    # named groups are pushed into `ordered` in one pass; the null bucket is
    # only appended in a second, separate step afterward.
    named_idx = body.index("if (key !== null) ordered.push(")
    null_idx = body.index("if (groups.has(null)) ordered.push(")
    assert named_idx < null_idx


def test_ungrouped_section_uses_dedicated_locale_label():
    assert "function _kanbanOfficeGroupHtml(group)" in PANELS_JS
    idx = PANELS_JS.index("function _kanbanOfficeGroupHtml(group)")
    end = PANELS_JS.index("\nfunction ", idx + 10)
    body = PANELS_JS[idx:end]
    assert "group.templateId ? _kanbanCrewName(group.templateId) : (t('kanban_office_ungrouped')" in body


def test_group_header_name_looked_up_from_already_loaded_crews_list():
    """Group headers resolve a crew's name via the SAME cache Crews'
    loadKanbanCrews() already populates (_kanbanCrewsList) -- no second
    fetch mechanism -- and _kanbanRenderOfficeView() only triggers that
    fetch once (guarded), not on every render."""
    assert "function _kanbanCrewName(templateId)" in PANELS_JS
    idx = PANELS_JS.index("function _kanbanCrewName(templateId)")
    end = PANELS_JS.index("\nfunction ", idx + 10)
    name_body = PANELS_JS[idx:end]
    assert "_kanbanCrewsList" in name_body
    assert "crew.name" in name_body

    idx2 = PANELS_JS.index("function _kanbanRenderOfficeView()")
    end2 = PANELS_JS.index("\nasync function hardRefreshWebUIClient", idx2)
    render_body = PANELS_JS[idx2:end2]
    assert "_kanbanCrewsList === null" in render_body
    assert "_kanbanCrewsListFetchInFlight" in render_body
    assert "loadKanbanCrews()" in render_body
    # still hooked into the existing pruning logic from the flat office view
    assert "if (!liveIds.has(id)) _kanbanOfficeExpanded.delete(id);" in render_body


def test_office_view_renders_one_grid_per_group_not_one_flat_grid():
    idx = PANELS_JS.index("function _kanbanRenderOfficeView()")
    end = PANELS_JS.index("\nasync function hardRefreshWebUIClient", idx)
    body = PANELS_JS[idx:end]
    assert "groups.map(_kanbanOfficeGroupHtml)" in body

    idx2 = PANELS_JS.index("function _kanbanOfficeGroupHtml(group)")
    end2 = PANELS_JS.index("\nfunction ", idx2 + 10)
    group_body = PANELS_JS[idx2:end2]
    assert "kanban-office-group" in group_body
    assert "kanban-office-grid" in group_body
    assert "group.workers.map(_kanbanOfficeCard)" in group_body


def test_crew_filter_select_present_in_kanban_filter_bar():
    match = re.search(r'<select[^>]+id="kanbanCrewFilter"[^>]*>', INDEX_HTML)
    assert match, "Kanban filter bar must expose a crew filter <select>"
    tag = match.group(0)
    assert "kanbanWorkflowTemplateFilter = this.value" in tag
    assert "loadKanban(true)" in tag
    # same UX slot as the existing tenant/assignee filters
    assignee_idx = INDEX_HTML.index('id="kanbanAssigneeFilter"')
    tenant_idx = INDEX_HTML.index('id="kanbanTenantFilter"')
    crew_idx = INDEX_HTML.index('id="kanbanCrewFilter"')
    assert assignee_idx < tenant_idx < crew_idx


def test_crew_filter_options_come_from_loaded_board_not_full_crews_list():
    """Populated from distinct workflow_template_id values actually present
    on _kanbanBoard's tasks -- NOT the full /api/crews list -- so a crew
    with zero currently-visible tasks doesn't appear as a filter option."""
    assert "function _kanbanCrewFilterIds()" in PANELS_JS
    idx = PANELS_JS.index("function _kanbanCrewFilterIds()")
    end = PANELS_JS.index("\nfunction ", idx + 10)
    body = PANELS_JS[idx:end]
    assert "_kanbanBoard" in body
    assert "_kanbanCrewsList" not in body
    assert "task.workflow_template_id" in body
    assert "seen" in body  # de-duplicates so a crew with N running tasks yields one option


def test_crew_filter_repopulated_on_every_board_render_call_site():
    """Same 'can't drift out of sync' reasoning as the office view itself:
    hooked into _kanbanRenderBoard() so every existing refresh path
    (poll/SSE, filter, lane toggle) keeps the filter's option list current,
    instead of needing separate wiring at each call site."""
    idx = PANELS_JS.index("function _kanbanRenderBoard()")
    end = PANELS_JS.index("\nfunction _kanbanCard(", idx)
    body = PANELS_JS[idx:end]
    assert "_kanbanPopulateCrewFilter();" in body


def test_crew_filter_narrows_the_same_board_query_the_office_view_reads():
    """The filter must reuse _board_payload's ?workflow_template_id= param
    (Phase 1) via the one kanbanWorkflowTemplateFilter variable already read
    by _kanbanCurrentFilters() and forwarded into loadKanban()'s board
    fetch -- narrowing the SAME _kanbanBoard the office view's grouping
    reads from, not a second independently-filtered copy."""
    assert "workflowTemplateId: kanbanWorkflowTemplateFilter || ''" in PANELS_JS
    idx = PANELS_JS.index("async function loadKanban(animate)")
    end = PANELS_JS.index("\nfunction filterKanban", idx)
    body = PANELS_JS[idx:end]
    assert "if (filters.workflowTemplateId) params.set('workflow_template_id', filters.workflowTemplateId);" in body


def test_clear_filters_resets_crew_filter_matching_tenant_pattern():
    """clearKanbanFilters() must reset the new crew filter using the exact
    same shape as the existing tenant-filter reset (value + defaultValue),
    not a parallel reset mechanism."""
    idx = PANELS_JS.index("function clearKanbanFilters()")
    end = PANELS_JS.index("\n}", idx)
    body = PANELS_JS[idx:end]
    tenant_reset = "const te = $('kanbanTenantFilter'); if (te) { te.value = ''; te.dataset.defaultValue = ''; }"
    crew_reset = "const cf = $('kanbanCrewFilter'); if (cf) { cf.value = ''; cf.dataset.defaultValue = ''; }"
    assert tenant_reset in body
    assert crew_reset in body
    assert "kanbanWorkflowTemplateFilter = '';" in body
