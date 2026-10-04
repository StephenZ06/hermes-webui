"""Structure tests for the Office panel (phase 1 of the office visualization).

Phase 1 ships the plumbing, not the picture: a vendored three.js, an import
map, a new `office` main-view panel, and a WebGL scene whose render loop and
GPU context are released the moment the panel is left. Every one of those is a
source-structure invariant that silently bricks the panel when broken, with no
console error to point at — the same failure class
test_agent_canvas_script_order.py guards for Agent Canvas:

* An import map placed after any `<script type="module">` is ignored for the
  modules that already started resolving, so the bare "three" specifier fails
  and the panel is blank.
* A missing `showing-office` exclusion on the chat-default selector shows the
  chat view stacked underneath the office view.
* A missing unmount hook leaks a WebGL context per panel visit until the
  browser's context cap is hit and every later mount draws nothing.

See docs/rfcs/office-visualization.md.
"""
import pathlib
import re

REPO = pathlib.Path(__file__).parent.parent
INDEX_HTML = (REPO / "static" / "index.html").read_text(encoding="utf-8")
CSS = (REPO / "static" / "style.css").read_text(encoding="utf-8")
PANELS_JS = (REPO / "static" / "panels.js").read_text(encoding="utf-8")
SESSIONS_JS = (REPO / "static" / "sessions.js").read_text(encoding="utf-8")
OFFICE_INDEX_JS = (REPO / "static" / "office" / "index.js").read_text(encoding="utf-8")
OFFICE_SCENE_JS = (REPO / "static" / "office" / "scene.js").read_text(encoding="utf-8")
ESLINT_CONFIG = (REPO / "eslint.runtime-guard.config.mjs").read_text(encoding="utf-8")

THREE_PATH = "static/vendor/three/0.185.1/three.module.min.js"


def test_office_sidebar_restores_project_folders_above_delegated_chat_history():
    folders_at = INDEX_HTML.index('id="officeProjectFolders"')
    history_at = INDEX_HTML.index('id="officeSessionList"')
    assert folders_at < history_at
    assert "function renderProjectFolders(projects, parents)" in OFFICE_INDEX_JS
    assert "parent.project_id === project.project_id" in OFFICE_INDEX_JS
    assert "No delegated tasks yet." in OFFICE_INDEX_JS
    assert 'class="project-folder-sessions-inner"' in OFFICE_INDEX_JS
    assert "row.nextElementSibling" in OFFICE_INDEX_JS
    assert "sessions.classList.toggle('expanded', expanded)" in OFFICE_INDEX_JS
    # The heading sits in its own labelled divider, with matching whitespace
    # before and after the line before the first project chip.
    assert ".office-project-folders{flex:0 0 auto;padding:0 8px;" in CSS
    assert ".office-project-folders-title{margin:20px 0;" in CSS
    assert "officeLabelsBtn" in OFFICE_INDEX_JS
    assert "togglePlatformLabels" in OFFICE_INDEX_JS


def test_office_workspace_section_matches_the_chat_sidebar_hierarchy():
    """Office folders use the same labelled divider language as adjacent sections."""
    assert "officeIcon('workspace-heading')" not in OFFICE_INDEX_JS
    assert '<span>WORKSPACES</span>' in OFFICE_INDEX_JS
    assert ".office-sidebar-section-title,.office-project-folders-title{display:flex;align-items:center;gap:10px;" in CSS
    assert ".office-sidebar-section-title::before,.office-sidebar-section-title::after,.office-project-folders-title::before,.office-project-folders-title::after{content:\"\";height:1px;flex:1;background:var(--border);}" in CSS
    assert ".office-project-folders .project-folder-list{padding:0;gap:3px;}" in CSS
    assert ".project-folder-list .project-chip{width:100%;box-sizing:border-box;border-radius:8px;" in CSS
    assert 'class="project-chip project-folder-row office-project-folder"' in OFFICE_INDEX_JS
    assert ".office-project-folders .project-folder-sessions{margin:0 0 2px;}" in CSS
    assert "host.insertBefore(searchWrap, host.querySelector('.project-folder-list'))" in OFFICE_INDEX_JS


def test_office_sidebar_includes_empty_project_folders_across_profiles():
    sidebar_at = OFFICE_INDEX_JS.index("async function renderSidebar()")
    sidebar = OFFICE_INDEX_JS[sidebar_at:OFFICE_INDEX_JS.index("// ---- mount", sidebar_at)]
    assert "_officeProjects = allProjects;" in sidebar
    assert "allProjects.filter(p => !p.profile || p.profile === activeProfile)" not in sidebar


def test_sidebar_action_cards_inherit_the_sidebar_background():
    assert ".hermes-cli-card{flex:0 0 auto;margin:6px 8px 8px;padding:8px;border-radius:8px;background:var(--sidebar);" in CSS


def test_office_filter_uses_a_compact_vertical_inset():
    """The Office filter has the same horizontal inset with less empty vertical chrome."""
    assert ".panel-view#panelOffice .sidebar-search{padding:0 8px 6px;}" in CSS
    assert ".panel-view#panelOffice .office-project-folders .sidebar-search{padding:0 0 10px;}" in CSS
    assert ".office-sidebar-list{flex:1;min-height:0;overflow-y:auto;padding:0 8px;" in CSS
    assert ".office-history-title{margin:16px 8px 8px;}" in CSS


def test_empty_chat_landing_does_not_define_a_logo_glow():
    """The landing surface stays solid behind the mark and welcome heading."""
    assert "--logo-glow:" not in CSS
    assert ".empty-state{background:radial-gradient(" not in CSS


def test_office_platform_labels_can_switch_between_adaptive_and_fixed_scale():
    # Cards are screen-space DOM overlays, so their scale must explicitly use
    # the scene zoom rather than accidentally reading as larger than a pod at
    # far camera zoom. The adjacent header control exposes a fixed-size mode.
    assert "let _labelsAdaptive = true;" in OFFICE_INDEX_JS
    assert 'id="officeLabelScaleBtn"' in OFFICE_INDEX_JS
    assert "togglePlatformLabelScale" in OFFICE_INDEX_JS
    assert "_scene.getView().zoom" in OFFICE_INDEX_JS
    assert "el.style.transform = `translate(-50%, -100%) scale(${scale})`;" in OFFICE_INDEX_JS


def test_task_status_collapses_with_a_transition_instead_of_removing_content():
    assert ".office-tasks-body{display:grid;grid-template-rows:minmax(0,1fr);" in CSS
    assert ".office-tasks.is-collapsed .office-tasks-body{pointer-events:none;}" in CSS
    assert "display:none" not in CSS[CSS.index(".office-tasks-body{"):CSS.index(".office-tasks-body-inner{")]


def test_office_sidebar_titles_are_icon_free_labelled_dividers_with_smooth_folder_motion():
    """Office headings are balanced dividers rather than a mismatched icon set."""
    assert 'id="officeToolsTitleIcon"' not in INDEX_HTML
    assert 'id="officeHistoryTitleIcon"' not in INDEX_HTML
    assert ".office-project-folders .project-folder-sessions{\n  will-change:grid-template-rows;" not in CSS
    assert ".office-project-folders .project-folder-sessions-inner{opacity:0;" not in CSS
    assert "transition:grid-template-rows .16s cubic-bezier(.2,.8,.2,1),margin .16s cubic-bezier(.2,.8,.2,1);" in CSS
    assert ".office-sidebar-section-title{margin:20px 8px;" in CSS


def test_office_folder_refreshes_do_not_replace_an_in_flight_disclosure():
    assert "const PROJECT_FOLDER_TRANSITION_MS = 240;" in OFFICE_INDEX_JS
    assert "let _projectFoldersSignature = '';" in OFFICE_INDEX_JS
    at = OFFICE_INDEX_JS.index("function renderProjectFolders(")
    body = OFFICE_INDEX_JS[at:OFFICE_INDEX_JS.index("\n/**", at)]
    assert "if (signature === _projectFoldersSignature) return;" in body
    assert "_projectFoldersAnimationUntil = performance.now() + PROJECT_FOLDER_TRANSITION_MS;" in body


def test_office_tools_use_the_supplied_equal_sized_icon_assets():
    assert "'/static/office-dashboard-tool.png'" in OFFICE_INDEX_JS
    assert "'/static/office-integrations-tool.png'" in OFFICE_INDEX_JS
    assert 'class="office-page-nav-image"' in OFFICE_INDEX_JS
    assert ".office-page-nav-icon{display:grid;place-items:center;flex:0 0 28px;width:28px;height:28px;border:0;background:transparent;color:var(--muted);}" in CSS
    assert ".office-page-nav-image{display:block;width:17px;height:17px;object-fit:contain;}" in CSS
    assert '[data-office-subview="integrations"] .office-page-nav-image{width:18px;height:18px;}' in CSS


# ── vendored three.js ────────────────────────────────────────────────────────

def test_three_is_vendored_at_the_pinned_version():
    vendored = REPO / THREE_PATH
    assert vendored.is_file(), (
        f"expected three.js vendored at {THREE_PATH} — this app has no bundler, "
        "so the office modules resolve three from the repo, not a CDN"
    )
    # Sanity floor: the real r185 module build is ~360KB. A truncated or
    # error-page download would sail past a mere existence check.
    assert vendored.stat().st_size > 200_000


def test_three_core_chunk_is_vendored_alongside_the_module_build():
    # r185's module build is split: three.module.min.js re-exports from
    # three.core.min.js. Vendoring only the entry file 404s at load time and
    # the panel goes silently blank — this cost a debugging round on the
    # first phase-1 browser check.
    core = REPO / "static" / "vendor" / "three" / "0.185.1" / "three.core.min.js"
    assert core.is_file(), "three.module.min.js imports ./three.core.min.js"
    assert core.stat().st_size > 200_000
    module_src = (REPO / THREE_PATH).read_text(encoding="utf-8", errors="ignore")
    assert "three.core.min.js" in module_src, (
        "if a future three.js bump stops splitting the build, drop this test "
        "rather than vendoring a file nothing imports"
    )


def test_vendored_three_carries_its_mit_licence():
    assert (REPO / "static" / "vendor" / "three" / "0.185.1" / "LICENSE.md").is_file(), (
        "vendored dependencies keep their licence alongside them "
        "(see static/vendor/motion/13.1.1/LICENSE.md)"
    )


ADDONS_DIR = REPO / "static" / "vendor" / "three" / "0.185.1" / "addons"


def test_every_addon_scene_js_imports_is_actually_vendored():
    # scene.js's bloom pass pulls in several three.js addon modules via the
    # "three/addons/" import map prefix (see test_import_map_maps_the_addons_
    # prefix_too below) -- each one has to actually exist on disk, the same
    # failure class as the three.core.min.js split above: importing a file
    # that was never vendored 404s at load time and the panel goes silently
    # blank, with nothing here to catch it except checking the files exist.
    imported = re.findall(r"three/addons/([\w./-]+\.js)", OFFICE_SCENE_JS)
    assert imported, "expected at least one 'three/addons/...' import in scene.js"
    for rel in imported:
        assert (ADDONS_DIR / rel).is_file(), f"scene.js imports {rel} but it is not vendored at {ADDONS_DIR}"


def test_import_map_maps_the_addons_prefix_too():
    start = INDEX_HTML.index('<script type="importmap">')
    end = INDEX_HTML.index("</script>", start)
    block = INDEX_HTML[start:end]
    assert '"three/addons/"' in block, (
        "a trailing-slash prefix entry, not a per-file one -- so any addon "
        "module under the vendored tree resolves without a new map entry"
    )
    assert "addons/" in block


# ── import map ───────────────────────────────────────────────────────────────

def test_import_map_maps_three_to_the_vendored_file():
    start = INDEX_HTML.index('<script type="importmap">')
    end = INDEX_HTML.index("</script>", start)
    block = INDEX_HTML[start:end]
    assert '"three"' in block, "the import map must define the bare 'three' specifier"
    assert THREE_PATH in block, f"'three' must resolve to {THREE_PATH}"
    # Import-map values must be absolute or start with / ./ ../ — a bare
    # "static/..." is rejected outright by the browser, taking the whole map
    # (and therefore the panel) down with it.
    assert f'"./{THREE_PATH}"' in block


def test_import_map_precedes_every_module_script():
    # Comments are blanked (not removed) so offsets still line up with the
    # real file — several comments here quote script tags verbatim.
    html = re.sub(r"<!--.*?-->", lambda m: " " * len(m.group(0)), INDEX_HTML, flags=re.S)
    map_at = html.index('<script type="importmap">')
    module_positions = [m.start() for m in re.finditer(r'<script\s+type="module"', html)]
    assert module_positions, "expected at least one module script in index.html"
    assert map_at < min(module_positions), (
        "the import map must appear before every <script type=\"module\">: it is "
        "consulted at module-resolution time, so a module graph that starts "
        "loading first resolves 'three' against nothing and the office panel "
        "goes blank with no console error"
    )


def test_office_entry_module_is_loaded_from_index_html():
    assert '<script type="module" src="static/office/index.js' in INDEX_HTML


# ── panel registration ───────────────────────────────────────────────────────

def test_office_is_a_main_view_panel():
    line = next(l for l in PANELS_JS.splitlines() if l.startswith("const MAIN_VIEW_PANELS"))
    assert "'office'" in line, (
        "without an entry in MAIN_VIEW_PANELS, switchPanel() never puts the "
        "showing-office class on <main> and the panel never becomes visible"
    )


def test_rail_and_sidebar_nav_both_expose_the_office_tab():
    rail_start = INDEX_HTML.index('<nav class="rail"')
    rail_end = INDEX_HTML.index("</nav>", rail_start)
    assert 'data-panel="office"' in INDEX_HTML[rail_start:rail_end]

    nav_start = INDEX_HTML.index('<div class="sidebar-nav">')
    nav_end = INDEX_HTML.index('data-panel="settings"', nav_start)
    assert 'data-panel="office"' in INDEX_HTML[nav_start:nav_end], (
        "the mobile sidebar-nav mirrors the rail; a tab present in only one "
        "is unreachable on the other form factor"
    )


def test_the_office_is_the_only_delegation_panel():
    # The Agent Canvas panel was removed once the office covered it. Its
    # module stays loaded, but headless: nothing should reach the panel.
    for start_marker, end_marker in (
        ('<nav class="rail"', "</nav>"),
        ('<div class="sidebar-nav">', 'data-panel="settings"'),
    ):
        start = INDEX_HTML.index(start_marker)
        block = INDEX_HTML[start:INDEX_HTML.index(end_marker, start)]
        assert 'data-panel="office"' in block
        assert 'data-panel="agentCanvas"' not in block

    assert 'id="panelAgentCanvas"' not in INDEX_HTML
    assert 'id="mainAgentCanvas"' not in INDEX_HTML
    assert "'agentCanvas'" not in PANELS_JS.split("MAIN_VIEW_PANELS")[1].split("]")[0]
    assert "showing-agentCanvas" not in CSS


def test_the_cron_delegation_diagram_still_has_its_renderer():
    # agent-canvas.js is kept loaded for exactly one reason: the Scheduled-jobs
    # page draws each cron run's delegation tree with renderStaticTree. Removing
    # the script would break that page, which is not what "remove the panel"
    # meant.
    assert 'src="static/agent-canvas.js' in INDEX_HTML
    assert "AgentCanvas.renderStaticTree(treeEl" in PANELS_JS
    assert ".agent-canvas-card" in CSS, "and the styles that diagram renders with"


def test_the_office_no_longer_points_at_a_panel_that_is_gone():
    # The no-WebGL fallback used to send people to Agent Canvas.
    office_index = (REPO / "static" / "office" / "index.js").read_text(encoding="utf-8")
    at = office_index.index("function renderUnsupported(")
    body = office_index[at:office_index.index("\n}\n", at)]
    assert "Agent Canvas" not in body


def test_the_landing_panel_is_still_chat():
    # Promoting the office is not the same as booting into it. This is a chat
    # app; opening it into a 3D floor instead of the user's conversations
    # would be a surprising default.
    rail_start = INDEX_HTML.index('<nav class="rail"')
    rail_end = INDEX_HTML.index("</nav>", rail_start)
    rail = INDEX_HTML[rail_start:rail_end]
    active = re.findall(r'<button[^>]*class="[^"]*\bactive\b[^"]*"[^>]*data-panel="([a-zA-Z]+)"', rail)
    assert active == ["chat"], f"exactly the chat tab starts active, got {active}"


def test_office_main_view_and_sidebar_panel_exist():
    assert 'id="mainOffice"' in INDEX_HTML
    assert 'id="officeWrap"' in INDEX_HTML, "the scene mounts into #officeWrap"
    # switchPanel does $('panel' + capitalize(name)); a missing panel-view
    # leaves the whole sidebar blank for this panel (see
    # test_nav_dividers_and_agent_canvas_panel.py).
    assert 'id="panelOffice"' in INDEX_HTML


def test_panel_switch_mounts_and_unmounts_the_office():
    assert "window.HermesOffice.mount($('officeWrap'))" in PANELS_JS
    assert "prevPanel === 'office'" in PANELS_JS and "HermesOffice.unmount()" in PANELS_JS, (
        "leaving the panel must release the WebGL context — browsers cap live "
        "contexts per page, and flipping in and out would exhaust that cap"
    )


def test_loadsession_resets_the_office_on_a_cross_session_switch():
    # The live floor tracks the running session. When loadSession() moves to a
    # different session, the office keeps feeding only from the new session's
    # SSE stream (static/messages.js gates subagent_* on the active sid), so the
    # previous session's still-running desks never receive their completion
    # events and sit frozen — dead connector lines, desks stuck at "working",
    # the idle conductor pacing an otherwise dead floor. The old Agent Canvas
    # reset itself here for exactly this reason; the Office that replaced it
    # must too.
    idx = SESSIONS_JS.find("currentSid !== sid && window.HermesOffice")
    assert idx != -1, (
        "loadSession() must call window.HermesOffice.reset() when switching to a "
        "different session, guarded by `currentSid && currentSid !== sid`"
    )
    window = SESSIONS_JS[idx:idx + 200]
    assert "HermesOffice.reset()" in window


# ── CSS visibility ───────────────────────────────────────────────────────────

def test_office_main_view_css_shows_and_hides_with_the_panel():
    assert "main.main > #mainOffice{display:none;}" in CSS
    assert "main.main.showing-office > #mainOffice{display:flex;}" in CSS


def test_chat_default_selector_excludes_the_office():
    selector = next(l for l in CSS.splitlines() if "> #mainChat{display:flex;}" in l)
    assert ":not(.showing-office)" in selector, (
        "the chat view is the default main view, shown by a chain of :not() "
        "exclusions; without office in that chain, chat renders underneath it"
    )


def test_the_chat_workspace_rightpanel_is_hidden_on_the_office():
    # Reported: the chat-only Files/Artifacts/Todos/Canvas/Live/Plane
    # workspace panel (`<aside class="rightpanel">`) kept showing next to
    # the Office. It's a sibling of <main>, not a child, so none of the
    # per-view `main.main.showing-X > #mainX` rules above ever touched it --
    # it needs its own rule, keyed off the same showing-office class via a
    # general sibling combinator.
    assert 'main.main.showing-office ~ .rightpanel' in CSS
    assert 'main.main.showing-office ~ #btnWorkspacePanelEdgeToggle' in CSS


# ── scene lifecycle ──────────────────────────────────────────────────────────

def test_office_entry_publishes_the_global_the_panel_calls():
    assert "window.HermesOffice = {" in OFFICE_INDEX_JS
    for name in ("mount", "unmount"):
        assert name in OFFICE_INDEX_JS


def test_scene_caps_pixel_ratio():
    assert "setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))" in OFFICE_SCENE_JS, (
        "uncapped DPR on a 3x display quadruples fragment cost for no visible "
        "gain and is the quickest way to make this panel drop frames"
    )


def test_scene_dispose_releases_gpu_resources_and_the_context():
    dispose_at = OFFICE_SCENE_JS.index("function dispose()")
    body = OFFICE_SCENE_JS[dispose_at:]
    assert "renderer.dispose()" in body
    assert "forceContextLoss()" in body
    assert "g.dispose()" in body and "m.dispose()" in body, (
        "geometries and materials are not freed by renderer.dispose()"
    )


def test_the_spoken_summary_is_not_deduped_across_a_remount():
    # renderSummary skips writing when the text has not changed, because
    # aria-live re-announces on every write. mount() builds a brand-new
    # element, so the guard has to be cleared or a remount whose state has not
    # moved leaves the summary empty.
    mount_at = OFFICE_INDEX_JS.index("function mount(container)")
    body = OFFICE_INDEX_JS[mount_at:OFFICE_INDEX_JS.index("\n}\n", mount_at)]
    assert "_lastSummary = ''" in body


def test_render_loop_stops_when_the_tab_is_hidden():
    assert "visibilitychange" in OFFICE_INDEX_JS
    assert "document.hidden" in OFFICE_INDEX_JS


def test_render_loop_pauses_during_shared_panel_layout_motion():
    """The WebGL composer must not contend with a sidebar slide.

    Office renders a post-processed 3D scene every frame. Pausing it for the
    very short shared sidebar/workspace-panel transition keeps per-frame GPU
    composition from stealing animation frames. The slide commits its final
    layout up front, so the paused scene redraws once at that size in the
    first frame (behaviour: tests/test_office_layout_motion_browser.py) rather
    than stretching a stale frame and snapping when the slide settles.
    """
    assert "function pauseForLayoutMotion" in OFFICE_INDEX_JS
    assert "function resumeAfterLayoutMotion" in OFFICE_INDEX_JS
    assert "_scene.stop()" in OFFICE_INDEX_JS
    assert "_scene.resize()" in OFFICE_INDEX_JS
    assert "_scene.start()" in OFFICE_INDEX_JS
    assert "_layoutMotionResumeRaf = requestAnimationFrame" in OFFICE_INDEX_JS, (
        "The final Office redraw must wait until the slide's settled frame has painted"
    )

    resize_observer_at = OFFICE_INDEX_JS.index("new ResizeObserver")
    resize_observer = OFFICE_INDEX_JS[resize_observer_at:resize_observer_at + 700]
    assert "_scene.renderNow()" in resize_observer, (
        "A resize must redraw in the same frame: a bare resize clears the canvas, "
        "and a paused scene would otherwise stretch a stale frame"
    )


def test_the_scene_pans_zooms_and_frames_a_pod():
    # Drag pans, wheel/pinch zoom, a stationary press is a tap that picks a
    # worker or frames the pod under it.
    for hook in ("pointerdown", "pointermove", "pointerup", "pointercancel"):
        assert f"canvas.addEventListener('{hook}'" in OFFICE_SCENE_JS
    assert "function focusOnPod(" in OFFICE_SCENE_JS
    assert "podClusterAt" in OFFICE_SCENE_JS and "group.userData.podCluster" in OFFICE_SCENE_JS
    assert "function zoomAbout(" in OFFICE_SCENE_JS, "wheel/pinch zoom toward the cursor"
    # The canvas must own the touch axes or the page scrolls instead of the floor.
    assert ".office-canvas{" in CSS
    canvas_rule = CSS[CSS.index(".office-canvas{"):]
    canvas_rule = canvas_rule[:canvas_rule.index("}")]
    assert "touch-action:none" in canvas_rule


# ── floor signage and seated figures ────────────────────────────────────────

def test_the_conductor_has_only_the_floating_status_card_not_legacy_scene_labels():
    # The shared floating card is now the conductor's label. A floor title and
    # old nameplate duplicate it at overview zoom, so neither belongs on the
    # three-dimensional conductor group.
    at = OFFICE_SCENE_JS.index("function ensureConductor()")
    body = OFFICE_SCENE_JS[at:OFFICE_SCENE_JS.index("\n  function ensurePod", at)]
    assert "makeFloorTitle('Conductor'" not in body
    assert "makeNameplate(palette, 'Conductor')" not in body
    assert "userData.plate" not in body


def test_conductor_uses_the_same_floating_card_system_as_business_departments():
    # Finance/Operations are DOM cards positioned from a pod screen rect, not
    # the small 3D nameplate used by desk workers. The conductor needs that
    # same card treatment for a consistent overview.
    assert "{ key: '__conductor__', name: 'Conductor'" in OFFICE_INDEX_JS


def test_conductor_card_has_a_scene_anchor_like_an_ordinary_pod_card():
    at = OFFICE_SCENE_JS.index("function podScreenRect(cluster)")
    body = OFFICE_SCENE_JS[at:OFFICE_SCENE_JS.index("\n  function applyCamera", at)]
    assert "cluster === '__conductor__'" in body
    assert "conductor.group" not in body


def test_the_conductors_own_pod_is_labelled_conductor():
    # Projects uses the central conductor platform itself and should label it
    # Conductor, just like Business, instead of giving it a separate "Subagents"
    # overlay.
    assert "key: '__conductor__'" in OFFICE_INDEX_JS
    assert "name: 'Conductor'" in OFFICE_INDEX_JS
    # podScreenRect still routes the conductor cluster to the shared conductor.
    assert "cluster === '__conductor__' && conductor" in OFFICE_SCENE_JS


def test_platform_identity_lives_in_floating_cards_not_scene_text():
    # Platform names remain readable at overview scale in the DOM cards; no
    # flat label should compete with desks or bridge geometry in the scene.
    assert "name: 'Conductor'" in OFFICE_INDEX_JS
    assert "makeFloorTitle" not in OFFICE_SCENE_JS


def test_a_seated_figure_faces_its_monitor():
    # makePerson's "work" pose reaches +z and the seat sits the figure on the
    # +z side of the desk; without the turn it types with its back to the screen.
    at = OFFICE_SCENE_JS.index("function ensureSeat(")
    body = OFFICE_SCENE_JS[at:at + 1400]
    assert "person.rotation.y = Math.PI" in body


# ── lint gate ────────────────────────────────────────────────────────────────

def test_runtime_lint_parses_office_modules_as_esm():
    assert '"static/office/**/*.js"' in ESLINT_CONFIG, (
        "static/office/* are the app's only first-party ES modules; parsed as "
        "'script' their import/export statements are syntax errors and the "
        "whole runtime-lint gate fails"
    )
    office_at = ESLINT_CONFIG.index('"static/office/**/*.js"')
    assert 'sourceType: "module"' in ESLINT_CONFIG[office_at:]
