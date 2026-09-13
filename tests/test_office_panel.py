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

def test_the_conductor_is_named_on_the_floor_not_on_a_nameplate():
    # A floating plate over the one figure at the centre read as a label on a
    # person; painted on the plinth it reads as the name of the space, matching
    # the Business floor.
    assert "makeFloorTitle('Conductor'" in OFFICE_SCENE_JS
    assert "makeNameplate(palette, 'Conductor')" not in OFFICE_SCENE_JS
    assert "conductor.userData.plate" not in OFFICE_SCENE_JS


def test_the_conductors_own_pod_is_labelled_subagents():
    assert "'Subagents'" in OFFICE_SCENE_JS
    assert "__conductor__" in OFFICE_SCENE_JS


def test_the_catch_all_pod_signs_keep_the_original_size():
    # "Subagents" and "The Floor" sit on large slabs and were fine at the fixed
    # size; only the named pods (departments, profiles) and the conductor
    # auto-fit larger.
    assert "label === 'Subagents' || label === 'The Floor'" in OFFICE_SCENE_JS
    assert "makeFloorTitle('Conductor', CONDUCTOR_SLAB * 0.82, palette, { fit: true })" in OFFICE_SCENE_JS


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
