"""Static contracts for the native Work Hub screen."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_work_hub_uses_native_panel_and_curated_mx_icons():
    page = read("static/index.html")
    script = read("static/work-hub.js")

    assert 'id="panelNotes"' in page
    assert "Work Hub" in page
    assert "static/work-hub.js" in page
    assert "mx-icons" in script
    assert "react" not in script.lower()


def test_work_hub_owns_the_main_notes_surface_not_the_sidebar_panel():
    page = read("static/index.html")
    main_notes = page.split('<div id="mainNotes"', 1)[1].split('</div>', 1)[0]
    sidebar_notes = page.split('<div class="panel-view" id="panelNotes">', 1)[1].split('<!-- Profiles panel -->', 1)[0]

    assert 'id="workHub"' in main_notes
    assert 'stickyBoardFrame' not in main_notes
    assert 'id="workHub"' not in sidebar_notes


def test_work_hub_scope_navigation_lives_in_the_notes_sidebar_only():
    page = read("static/index.html")
    script = read("static/work-hub.js")
    sidebar_notes = page.split('<div class="panel-view" id="panelNotes">', 1)[1].split('<!-- Profiles panel -->', 1)[0]

    assert 'id="workHubSidebar"' in sidebar_notes
    assert 'renderWorkHubNavigation' in script
    assert '<aside class="work-hub-nav">' not in script
    assert 'grid-template-columns:' in read("static/style.css") and 'var(--wh-inspector-width)' in read("static/style.css")


def test_work_hub_board_uses_the_notes_surface_without_an_outer_card():
    css = read("static/style.css")
    root_rule = css.split("#workHub {", 1)[1].split("}", 1)[0]
    outer_rule = css.split(".work-hub {", 1)[1].split("}", 1)[0]

    assert "padding: 0" in root_rule
    assert " border: " not in outer_rule
    assert "border-radius" not in outer_rule


def test_work_hub_uses_hermes_theme_tokens_not_blue_fallback_palette():
    css = read("static/style.css")
    work_hub_css = css.split('/* ── Work Hub', 1)[1].split('/* ── Touch responsiveness', 1)[0]

    for token in ("var(--bg)", "var(--surface)", "var(--text)", "var(--muted)", "var(--border)"):
        assert token in work_hub_css
    for fallback in ("--bg-primary", "--text-primary", "--text-secondary", "#0d1424", "#edf3ff"):
        assert fallback not in work_hub_css


def test_work_hub_has_reduced_motion_and_narrow_drawer_rules():
    css = read("static/style.css")

    assert ".work-hub" in css
    assert "prefers-reduced-motion" in css
    assert "@media" in css


def test_work_hub_script_parses_in_supported_node_runtime():
    result = subprocess.run(
        ["node", "--check", str(ROOT / "static/work-hub.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_work_hub_post_bodies_use_the_shared_json_api_contract():
    script = read("static/work-hub.js")

    assert "body: JSON.stringify({ item:" in script
    assert "body: JSON.stringify({ item_id:" in script


def test_work_hub_exposes_current_chat_link_action():
    script = read("static/work-hub.js")

    assert "Link current chat" in script
    assert "linked_session_ids" in script


def test_all_work_scope_does_not_exclude_project_items_or_clear_missing_agent():
    script = read("static/work-hub.js")

    assert "store.activeScope === 'all' ? true" in script
    assert "Unavailable: ${esc(item.agent_profile)}" in script


def test_work_hub_refresh_does_not_overwrite_a_newer_local_revision():
    script = read("static/work-hub.js")

    assert "if ((data.revision || 0) < store.revision) return;" in script


def test_work_hub_search_replaces_results_and_rebinds_item_actions():
    script = read("static/work-hub.js")

    assert "canvas.innerHTML = '';" in script
    assert "renderCanvas(scopedItems()); bind();" in script


def test_new_item_opens_right_inspector_with_editable_title():
    script = read("static/work-hub.js")
    css = read("static/style.css")

    assert 'id="workHubTitle"' in script
    assert "title: el('workHubTitle').value" in script

    inspector_rule = css.split(".work-hub-inspector {", 1)[1].split("}", 1)[0]
    assert "grid-column: 2" in inspector_rule
    assert "grid-row: 1" in inspector_rule


def test_work_hub_updates_revision_after_delete():
    script = read("static/work-hub.js")

    delete_body = script.split("async function deleteItem", 1)[1].split("async function createItem", 1)[0]
    assert "const result = await request('/api/work_hub/items/delete'" in delete_body
    assert "store.revision = result.revision" in delete_body


def test_narrow_work_hub_uses_css_inspector_width():
    script = read("static/work-hub.js")

    assert "window.matchMedia('(max-width: 620px)').matches" in script


def test_goal_planner_can_launch_its_created_project_items_as_a_workflow():
    script = read("static/work-hub.js")

    assert 'id="goalPlannerRun"' in script
    assert '"/api/work_hub/workflows/start"' in script
    assert "item_ids: createdItems.map(item => item.id)" in script
    assert "createdRevision = created.revision" in script
    assert "expected_revision: createdRevision" in script
