"""Source-structure pins for the visual-polish pass on top of the department
floor colours: a bloom post-process, a hemisphere+rim lighting rig, and a
per-pod whiteboard and working-pod glow.

scene.js's WebGL setup fails the same way phase 1's plumbing does -- silently,
with a blank or half-drawn panel and no console error -- so these are the same
kind of source-structure invariant as tests/test_office_panel.py, not
behavioural tests. The actual pixels are checked once, by eye, against the
real running app (this repo has no pixel-diffing harness); what breaks
silently on refactor is checked here and in
tests/test_office_browser_smoke.py (HERMES_WEBUI_BROWSER_TESTS=1).

See docs/rfcs/office-visualization.md's "Follow-up same day: visual polish".
"""
import pathlib

REPO = pathlib.Path(__file__).parent.parent
SCENE_SRC = (REPO / "static" / "office" / "scene.js").read_text(encoding="utf-8")
BUILDERS_SRC = (REPO / "static" / "office" / "builders.js").read_text(encoding="utf-8")


# ── bloom ────────────────────────────────────────────────────────────────────

def test_the_render_loop_goes_through_the_composer_not_the_renderer_directly():
    assert "composer.render()" in SCENE_SRC
    assert "renderer.render(scene, camera)" not in SCENE_SRC, (
        "a direct renderer.render() call would skip the bloom pass entirely"
    )


def test_bloom_is_wired_as_render_then_bloom_then_output():
    order = [SCENE_SRC.find(name) for name in (
        "new RenderPass(", "new UnrealBloomPass(", "new OutputPass(",
    )]
    assert all(i >= 0 for i in order), "expected all three passes constructed"
    assert order == sorted(order), "passes must be added in render -> bloom -> output order"


def test_composer_is_resized_and_disposed_alongside_the_renderer():
    assert "composer.setSize(width, height)" in SCENE_SRC, (
        "otherwise the bloom render targets stay at their construction-time "
        "size and the effect goes soft/blurry as the panel resizes"
    )
    at = SCENE_SRC.index("function dispose() {")
    body = SCENE_SRC[at:at + 1600]
    assert "composer.dispose()" in body
    assert "pass.dispose()" in body, (
        "EffectComposer.dispose() only frees its own read/write targets, not "
        "each pass's own render targets/materials -- bloom leaks GPU memory "
        "every panel visit without disposing the passes individually"
    )


def test_overview_zoom_uses_the_actual_viewport_size_for_consistent_framing():
    at = SCENE_SRC.index("function zoomForRadius(")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  // ---- camera motion", at)]
    assert "viewportCoverage" in body
    assert "Math.min(width, height)" in body


def test_tone_mapping_is_set_so_the_hdr_glow_rolls_off_instead_of_clipping():
    assert "renderer.toneMapping = THREE.ACESFilmicToneMapping" in SCENE_SRC


# ── lighting ─────────────────────────────────────────────────────────────────

def test_ambient_light_became_a_hemisphere_light():
    assert "new THREE.HemisphereLight(" in SCENE_SRC
    assert "new THREE.AmbientLight(" not in SCENE_SRC


def test_theme_switch_repaints_the_hemisphere_and_rim_lights():
    at = SCENE_SRC.index("function applyTheme() {")
    body = SCENE_SRC[at:at + 700]
    assert "ambient.color.set(palette.hemiSky)" in body
    assert "ambient.groundColor.set(palette.hemiGround)" in body
    assert "rimLight.color.set(palette.rim)" in body


# ── outline removed ──────────────────────────────────────────────────────────

def test_the_dashed_pod_outline_is_gone():
    # Reported to visibly "stick out" past a pod's corners (an isometric-
    # parallax artifact of its height sitting above the slab top) -- removed
    # from scene.js entirely rather than nudged closer to the surface again.
    # A working pod's glow (below) is the only "this is active" cue on the
    # floor now. makeSlabOutline itself stays defined and tested in
    # test_office_outlines.py as a correct, reusable piece of the same
    # dashed-line machinery the conductor<->pod bridges still use.
    assert "makeSlabOutline" not in SCENE_SRC
    assert "outlineLine" not in SCENE_SRC
    assert "record.outline" not in SCENE_SRC


# ── working-route activity ───────────────────────────────────────────────────

def test_active_work_is_signalled_by_bridge_chevrons_not_platform_glow():
    assert "makePodGlow(slabWidth, slabDepth, color)" not in SCENE_SRC
    assert "glowMaterial:" not in SCENE_SRC
    assert "function pulseGlow(" not in SCENE_SRC
    assert "advanceBridgeFade(bridge, dtMs, t)" in SCENE_SRC


def test_the_conductor_never_glows():
    # Reported as distracting: the conductor's plinth is the one fixed
    # landmark on the floor, there whether anything is running or not, so
    # tinting/pulsing it with activity (the way a pod does) just adds noise.
    # The conductor's own status is still tracked -- the pacing figure uses
    # it -- just no longer wired to a glow.
    assert "conductor.userData.glowMaterial" not in SCENE_SRC
    assert "conductor.userData.status === 'orchestrating'" in SCENE_SRC


def test_platform_names_are_not_painted_on_the_floor():
    start = SCENE_SRC.index("function ensureConductor()")
    conductor = SCENE_SRC[start:SCENE_SRC.index("function ensurePod", start)]
    pod = SCENE_SRC[SCENE_SRC.index("function ensurePod("):SCENE_SRC.index("function setBridgeActive")]
    assert "makeFloorTitle" not in conductor
    assert "makeFloorTitle" not in pod


# ── set dressing ─────────────────────────────────────────────────────────────

def test_the_floor_grid_texture_was_removed():
    # Reported: an extra per-pod texture on top of the already-tinted slab
    # read as visual noise, not polish -- and cost a draw call and a canvas
    # texture upload per pod for it. builders.js no longer defines it at all.
    assert "makeFloorTiles" not in SCENE_SRC
    assert "export function makeFloorTiles" not in BUILDERS_SRC


def test_every_pod_gets_its_department_scenery():
    # One scenery group per pod (walls, shelf, plants, the department's prop,
    # its icon plaque), chosen from the pod's name.
    at = SCENE_SRC.index("function ensurePod(")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  function ", at + 10)]
    assert body.count("makePodScenery(") == 1
    assert "deptKind(label || cluster)" in body

def test_disposetree_releases_every_new_userdata_tagged_resource():
    at = BUILDERS_SRC.index("export function disposeTree(")
    body = BUILDERS_SRC[at:at + 1400]
    assert "userData.podGlow" in body, "disposeTree must know how to free a podGlow"


# ── smoothness ───────────────────────────────────────────────────────────────

def test_bloom_renders_at_the_capped_renderer_pixel_ratio():
    # The composer renders to an off-screen target; keeping it at 1x made
    # zoomed edges look blurry. We now match the renderer's own capped ratio
    # (up to 2x) so MSAA + bloom stay sharp without the uncapped cost of a
    # 3x phone.
    assert "composer.setPixelRatio(renderer.getPixelRatio())" in SCENE_SRC


def test_renderer_uses_srgb_output_for_smoother_model_gradients():
    assert "renderer.outputColorSpace = THREE.SRGBColorSpace" in SCENE_SRC


def test_people_use_smooth_capsule_and_head_geometry():
    assert "new THREE.CapsuleGeometry(radius, length, 4, 12)" in BUILDERS_SRC
    assert "new THREE.SphereGeometry(0.45, 24, 18)" in BUILDERS_SRC


def test_platform_finish_softens_edge_specular_hotspots():
    # Tinted pods keep a soft satin finish; untinted pods (Conductor,
    # The Floor) are matte so dark rims don't produce white specular dots.
    assert "isUntinted" in BUILDERS_SRC
    assert "topMatOpts = isUntinted" in BUILDERS_SRC
    assert "rough: 0.92, clearcoat: 0" in BUILDERS_SRC
    assert "rough: 0.72, clearcoat: 0.25" in BUILDERS_SRC

def test_whiteboard_props_never_cast_a_shadow():
    at = BUILDERS_SRC.index("export function makeWhiteboard(")
    body = BUILDERS_SRC[at:BUILDERS_SRC.index("\n}", at)]
    assert body.count("castShadow = false") == 3, (
        "board, frame, and both legs (one assignment, run per leg) must all "
        "skip the shadow pass -- a decorative prop this small isn't worth "
        "rendering four more shadow casters per pod, every frame"
    )


def test_floor_sign_text_is_stroked_for_contrast_against_any_floor_colour():
    # Reported: "Subagents" (and department names) were hard to read against
    # some pod colours -- a fixed fill alone reads fine against a plain
    # palette tone but not against every saturated department/cluster tint.
    at = BUILDERS_SRC.index("export function makeFloorTitle(")
    body = BUILDERS_SRC[at:BUILDERS_SRC.index("\nexport function", at + 10)]
    assert "ctx.strokeText(c" in body
    assert "ctx.strokeStyle = palette.floorTitleStroke" in body
    assert "floorTitleStroke:" in SCENE_SRC, "both palettes must define the stroke colour"


def test_composer_renders_multisampled_so_edges_stay_smooth():
    # Reported: model edges (a figure's head especially) went jagged once
    # bloom landed. WebGL only antialiases the default framebuffer -- routing
    # the render through a composer moves it to an offscreen target, where
    # the renderer's own `antialias: true` no longer applies at all. `samples`
    # asks for multisampling explicitly on the composer's own target instead.
    assert "samples: 4" in SCENE_SRC
    # HalfFloatType must survive alongside it: EffectComposer's own default
    # target used it (for the glow mesh's deliberately over-1.0 colour, see
    # builders.js's makePodGlow), and a custom target that dropped it would
    # clamp that colour to white before bloom ever saw it.
    assert "type: THREE.HalfFloatType" in SCENE_SRC


def test_bridge_deck_has_no_colored_edge_or_segment_decoration():
    # The edge-rail experiment is intentionally removed. Keep the bridge
    # itself clean and structural rather than decorating it with lines.
    at = BUILDERS_SRC.index("export function makeBridgeSegment(")
    body = BUILDERS_SRC[at:BUILDERS_SRC.index("export function makeWalkway(", at)]
    assert "BRIDGE_DECK_WIDTH" in body
    assert "bridgeRail" not in body
    assert "bridgeSegment" not in body


def test_walkways_are_rectangular_decks_tucked_beneath_platform_rims():
    at = BUILDERS_SRC.index("export function makeBridgeSegment(")
    segment = BUILDERS_SRC[at:BUILDERS_SRC.index("export function makeWalkway(", at)]
    assert "makeRectangularBridgeDeck(" in segment
    assert "roundedPlatform(" not in segment
    assert "makeTaperedBridgeDeck(" not in segment
    assert "height: BRIDGE_DECK_HEIGHT" in segment
    at = BUILDERS_SRC.index("export function makeWalkway(")
    walkway = BUILDERS_SRC[at:BUILDERS_SRC.index("\n/* ---------- desk", at)]
    assert "makeBridgeSegment(length, palette, bridgeOptions)" in walkway
    assert "part.position.y += 0.63" in walkway


def test_raised_pod_bridges_end_at_the_actual_rounded_platform_edges():
    # The deck enters below each rounded rim, closing the visible seam. Its
    # taller coloured rails receive that exact overlap as an inset, so their
    # exposed ends stop at the bridge instead of spilling onto either platform.
    at = SCENE_SRC.index("function ensureWalkway(")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  function floorBridgeRoute", at)]
    assert "hubRadius" in body
    assert "podRadius" in body
    assert "BRIDGE_DECK_PLATFORM_OVERLAP = BRIDGE_DECK_WIDTH / 2" in SCENE_SRC
    assert "overlap: BRIDGE_DECK_PLATFORM_OVERLAP" in body
    assert "walk = makeWalkway(span.length, palette, railColor);" in body


def test_raised_platforms_occlude_bridge_rail_ends_without_lifting_the_floor():
    conductor_at = SCENE_SRC.index("function ensureConductor()")
    conductor = SCENE_SRC[conductor_at:SCENE_SRC.index("function ensurePod", conductor_at)]
    sync_at = SCENE_SRC.index("function syncOffice(")
    sync = SCENE_SRC[sync_at:SCENE_SRC.index("function frame", sync_at)]

    assert "const RAISED_PLATFORM_Y = 0.52" in SCENE_SRC
    assert "const CONDUCTOR_PLATFORM_Y = RAISED_PLATFORM_Y" in SCENE_SRC
    assert "const LEVEL_BRIDGE_Y = -0.45" in SCENE_SRC
    assert "group.position.y = CONDUCTOR_PLATFORM_Y;" in conductor
    assert "record.group.position.set(pod.x, CONDUCTOR_PLATFORM_Y, pod.z);" in sync


def test_all_platform_types_reuse_the_four_layer_pod_builder():
    conductor_at = SCENE_SRC.index("function ensureConductor()")
    conductor = SCENE_SRC[conductor_at:SCENE_SRC.index("function ensurePod", conductor_at)]
    sync_at = SCENE_SRC.index("function syncOffice(")
    sync = SCENE_SRC[sync_at:SCENE_SRC.index("function frame", sync_at)]
    assert "makePod(CONDUCTOR_SLAB, CONDUCTOR_SLAB, palette, null, { band: HUB_COLOR" in conductor
    assert "const record = ensurePod(" in sync
    assert "record.group.position.set(pod.x, CONDUCTOR_PLATFORM_Y, pod.z);" in sync
    assert "addLayer('top'" in BUILDERS_SRC
    assert "addLayer('upper-base'" in BUILDERS_SRC
    assert "addLayer('delivery'" in BUILDERS_SRC
    assert "addLayer('lower-base'" in BUILDERS_SRC


def test_non_floor_bridges_share_the_raised_platform_level():
    at = SCENE_SRC.index("walk = makeWalkway(")
    body = SCENE_SRC[at:SCENE_SRC.index("walk.userData.singleChevronFlow", at)]
    assert "LEVEL_BRIDGE_Y" in body


def test_the_floor_always_has_a_platform_seat_even_when_empty():
    roster = (REPO / "static" / "office" / "roster.js").read_text(encoding="utf-8")
    assert "if (!overflowSeats.length)" in roster
    assert "id: `seat-${OVERFLOW.key}-lead`" in roster
    assert "departments.push({ key: OVERFLOW.key" in roster




def test_the_floor_uses_a_lowered_ramp_then_a_single_straight_bridge():
    assert "function floorBridgeRoute(" in SCENE_SRC
    at = SCENE_SRC.index("function ensureWalkway(")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  function maxDistanceInsidePod", at)]
    assert "cluster === 'floor'" in body
    assert "floorBridgeRoute(span, pod)" in body
    assert "placeBridgeSegment" in body
    assert "floorBridgeSegments" not in SCENE_SRC
    route_at = SCENE_SRC.index("function floorBridgeRoute(")
    route = SCENE_SRC[route_at:SCENE_SRC.index("\n  function placeBridgeSegment", route_at)]
    assert "const exit = { x: 0, z: CONDUCTOR_SLAB / 2 - 0.6 }" in route
    assert "destination = floorBridgeEntryPoint(rampEnd, pod)" in route
    assert "const FLOOR_RAMP_ANGLE = 120 * Math.PI / 180" in route
    assert "Math.sin(FLOOR_RAMP_ANGLE) * rampLength" in route
    assert "Math.cos(FLOOR_RAMP_ANGLE) * rampLength" in route
    assert "fromTopY: 0.46" in route
    assert "toTopY: 0.18" in route


def test_the_floor_flow_trace_reuses_the_decks_exact_route():
    at = SCENE_SRC.index("function ensureWalkway(")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  function floorBridgeRoute", at)]
    assert "floorBridgeRoute(span, pod)" in body
    assert "placeBridgeSegment(" in body
    assert "floorBridgePalette()" in body


def test_the_floor_uses_three_evenly_spaced_chevrons_per_active_packet():
    at = SCENE_SRC.index("function ensureWalkway(")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  function maxDistanceInsidePod", at)]
    floor_at = body.index("if (cluster === 'floor')")
    floor_body = body[floor_at:body.index("\n    } else", floor_at)]
    assert "walk.userData.singleChevronFlow = true;" in floor_body
    assert "walk.userData.flowMarkerCount = 3;" in floor_body


def test_bridge_chevrons_advance_faster_for_all_routes():
    at = SCENE_SRC.index("function advanceBridgeFade(")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  /**", at)]
    assert "elapsed * 5.4" in body
    assert "elapsed * 9" in body
    assert "flowMarkerCount" in body


def test_the_floor_bridge_is_drawn_below_pods_with_a_dark_grey_material():
    at = SCENE_SRC.index("function ensureWalkway(")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  function floorBridgeRoute", at)]
    assert "walk.renderOrder = -1" in body
    assert "floorBridgePalette()" in body
    assert "floorBridgeDeck:" in SCENE_SRC
    assert "floorBridgeBeam:" in SCENE_SRC


def test_all_bridge_decks_share_the_lit_charcoal_finish():
    assert SCENE_SRC.count("bridgeDeck: '#090a0c'") == 2
    assert SCENE_SRC.count("floorBridgeDeck: '#090a0c'") == 2


def test_bridge_decks_do_not_select_destination_colored_rails():
    assert "FLOOR_BRIDGE_EDGE_COLOR" not in SCENE_SRC
    assert "bridgeEdgeColor(" not in SCENE_SRC
    assert "makeBridgeTube(" not in SCENE_SRC
    assert "makeConnector(" not in SCENE_SRC


def test_floor_bridge_retracts_its_rail_and_deck_three_units_from_the_conductor():
    at = SCENE_SRC.index("function floorBridgeRoute(")
    route = SCENE_SRC[at:SCENE_SRC.index("\n  function floorBridgeEntryPoint", at)]
    assert "const FLOOR_CONDUCTOR_TRIM = 3" in route
    assert "const rampStart" in route
    assert "from: rampStart, to: rampEnd" in route
    assert "railTrimStart" not in route
    assert "railTrimEnd" not in route
    at = SCENE_SRC.index("function placeBridgeSegment(")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  function maxDistanceInsidePod", at)]
    assert "railTrimStart: segment.railTrimStart || 0" in body
    assert "railTrimEnd: segment.railTrimEnd || 0" in body


def test_the_floor_bridge_terminates_at_the_middle_of_its_approached_edge():
    assert "function floorBridgeEntryPoint(from, pod)" in SCENE_SRC
    at = SCENE_SRC.index("function floorBridgeEntryPoint(from, pod)")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  function placeBridgeSegment", at)]
    assert "halfWidth" in body and "halfDepth" in body
    assert "z: pod.z" in body
    assert "x: pod.x" in body


def test_the_ground_keeps_its_normal_depth_layer_when_the_floor_bridge_is_visible():
    at = SCENE_SRC.index("function buildGround(")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  function installGround", at)]
    assert "depthWrite: false" not in body
    assert "gridHelper.material.depthWrite = false" not in body
    assert "renderOrder = -1" not in body


def test_the_office_background_grid_remains_fully_opaque():
    at = SCENE_SRC.index("function buildGround(")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  function installGround", at)]
    assert "gridHelper.material.opacity = 1;" in body


def test_office_platforms_cast_shadows_but_bridges_do_not():
    assert "slab.castShadow = true;" in BUILDERS_SRC
    assert "deck.castShadow = false;" in BUILDERS_SRC
    assert "beam.castShadow = false;" in BUILDERS_SRC
    assert "const topHeight = 1.2;" in BUILDERS_SRC


def test_platform_bases_use_black_in_both_office_themes():
    assert SCENE_SRC.count("platformBase: '#000000'") == 2


def test_active_bridge_work_uses_chevrons_instead_of_pulsing_the_colored_rails():
    # Side rails remain physical trim. Work state belongs to the centred cable
    # layer, which is shared by straight and routed bridges.
    at = BUILDERS_SRC.index("export function makeBridgeSegment(")
    body = BUILDERS_SRC[at:BUILDERS_SRC.index("export function makeWalkway(", at)]
    assert "makeBridgeActivityChevrons" in body
    at = SCENE_SRC.index("function setBridgeActive(")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  function advanceBridgeFade", at)]
    assert "eachActivityChevron" in body
    assert "eachRailMaterial" not in body


def test_mood_bubbles_are_enlarged_and_clamped_at_far_zoom():
    assert "const bubbleScale = lod === 'far' ? 1.8 : 2.5;" in SCENE_SRC
    assert "seat.bubble.scale.set(bubbleScale * k, bubbleScale * 0.76 * k, 1);" in SCENE_SRC


def test_every_bridge_has_a_first_interior_transverse_panel_line():
    at = BUILDERS_SRC.index("export function makeBridgeSegment(")
    body = BUILDERS_SRC[at:BUILDERS_SRC.index("export function makeWalkway(", at)]
    assert "for (let i = 1; i < panelCount - 1; i++)" in body


def test_the_floor_pod_gets_open_scenery_that_keeps_its_desk_edges_clear():
    at = SCENE_SRC.index("function ensurePod(")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  function setBridgeActive", at)]
    assert "{ open: label === 'The Floor' }" in body

def test_task_nameplates_only_appear_for_the_focused_worker():
    # Full task strings are useful when inspecting one desk, but at overview
    # scale they overlap neighbouring desks and the bridges between pods.
    assert "focusedId === seat.workerId" in SCENE_SRC
    assert "seat.plate.visible = shouldShowNameplate(seat);" in SCENE_SRC
    at = SCENE_SRC.index("function syncLod() {")
    body = SCENE_SRC[at:at + 300]
    assert "syncNameplateVisibility();" in body


# ── ground grows with the office ────────────────────────────────────────────

def test_the_ground_grows_to_cover_the_worst_case_zoomed_out_view():
    # Reported: zooming out far enough on a large office showed the ground
    # plane's own edge -- a hard border against the transparent canvas. A
    # fixed-size floor can never rule that out for an arbitrarily large
    # delegation tree, so it's grown instead, keyed to the same radius
    # frameOffice() already recomputes on every sync.
    assert "function ensureGroundCovers(radius)" in SCENE_SRC
    assert "ensureGroundCovers(framedRadius)" in SCENE_SRC
    at = SCENE_SRC.index("function frameOffice(")
    body = SCENE_SRC[at:at + 700]
    assert "ensureGroundCovers(framedRadius)" in body


def test_ground_growth_is_never_shrunk_and_replaces_the_old_one():
    # Shrinking it back the moment a big run's pods are swept would flash
    # the edge into view again; installGround() must fully retire the old
    # geometry/material rather than leaking it.
    at = SCENE_SRC.index("function ensureGroundCovers(radius) {")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  }", at)]
    assert "needed <= groundHalfSize * 1.05" in body, "small growth must not trigger a rebuild"
    at2 = SCENE_SRC.index("function installGround(halfSize) {")
    body2 = SCENE_SRC[at2:SCENE_SRC.index("\n  }", at2)]
    assert "groundGeometry.dispose()" in body2
    assert "groundMaterial.dispose()" in body2
    assert "grid.geometry.dispose()" in body2
    assert "grid.material.dispose()" in body2


# ── outlet-switch animation ──────────────────────────────────────────────────

def test_switching_outlets_fades_the_canvas_instead_of_a_hard_cut():
    OFFICE_INDEX_SRC = (REPO / "static" / "office" / "index.js").read_text(encoding="utf-8")
    CSS = (REPO / "static" / "style.css").read_text(encoding="utf-8")
    at = OFFICE_INDEX_SRC.index("function setOutlet(")
    body = OFFICE_INDEX_SRC[at:OFFICE_INDEX_SRC.index("\n}", at)]
    assert "setOutletTransition" in body or "animateOutletSwitch()" in body
    canvas_rule_start = CSS.index(".office-canvas{")
    canvas_rule = CSS[canvas_rule_start:CSS.index("}", canvas_rule_start)]
    assert "transition:opacity" in canvas_rule, (
        "an instant opacity jump reads as a glitch, not a deliberate cross-fade"
    )


def test_the_fade_reveal_waits_for_the_real_sync_not_just_a_timer():
    # A first attempt used only a fixed setTimeout, sized to "220ms ought to
    # cover it". Measured: switching to Business can mean waiting on a
    # /api/personalities fetch and rebuilding a department's worth of floor
    # signs, which blew well past that guess under load -- the timer fired
    # before the new floor was actually drawn, revealing a stale or
    # half-built frame instead of masking the swap. animateOutletSwitch()
    # itself no longer starts any timer; it only flags the fade as pending.
    OFFICE_INDEX_SRC = (REPO / "static" / "office" / "index.js").read_text(encoding="utf-8")
    animate_start = OFFICE_INDEX_SRC.index("function animateOutletSwitch(")
    animate_body = OFFICE_INDEX_SRC[animate_start:OFFICE_INDEX_SRC.index("\n}", animate_start)]
    assert "window.setTimeout" not in animate_body
    assert "_outletFadePending = true" in animate_body
    sync_start = OFFICE_INDEX_SRC.index("function scheduleSync(")
    sync_body = OFFICE_INDEX_SRC[sync_start:OFFICE_INDEX_SRC.index("\n  });", sync_start)]
    assert "_outletFadePending" in sync_body
    assert "revealAfterOutletFade()" in sync_body


def test_the_fade_reveal_also_waits_out_a_minimum_visible_duration():
    # Measured separately: a switch cheap enough to reconcile within a
    # couple of animation frames (most Projects<->Business switches) let
    # scheduleSync remove the class before the browser ever painted the
    # faded-out frame -- add-then-remove within the same frame or two is a
    # known case of a CSS transition never being visibly observed at all,
    # confirmed by sampling getComputedStyle('.office-canvas').opacity every
    # 10ms through a real switch: it never left "1" until this guard was
    # added. revealAfterOutletFade() now waits out whichever is longer,
    # OUTLET_FADE_MIN_MS or the real sync time.
    OFFICE_INDEX_SRC = (REPO / "static" / "office" / "index.js").read_text(encoding="utf-8")
    assert "const OUTLET_FADE_MIN_MS = 0;" in OFFICE_INDEX_SRC
    at = OFFICE_INDEX_SRC.index("function revealAfterOutletFade(")
    body = OFFICE_INDEX_SRC[at:OFFICE_INDEX_SRC.index("\n}", at)]
    assert "performance.now() - _outletFadeStartedAt" in body
    assert "OUTLET_FADE_MIN_MS - elapsed" in body
    assert "window.setTimeout(reveal, remaining)" in body
    assert "classList.remove('is-switching-outlet')" in body
