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


# ── working-pod glow ─────────────────────────────────────────────────────────

def test_every_pod_gets_a_glow_mesh_and_stores_its_material():
    assert "makePodGlow(slabWidth, slabDepth, color)" in SCENE_SRC
    assert "glowMaterial: glow.material" in SCENE_SRC


def test_the_conductor_never_glows():
    # Reported as distracting: the conductor's plinth is the one fixed
    # landmark on the floor, there whether anything is running or not, so
    # tinting/pulsing it with activity (the way a pod does) just adds noise.
    # The conductor's own status is still tracked -- the pacing figure uses
    # it -- just no longer wired to a glow.
    assert "conductor.userData.glowMaterial" not in SCENE_SRC
    assert "conductor.userData.status === 'orchestrating'" in SCENE_SRC


def test_glow_eases_toward_its_target_rather_than_snapping():
    at = SCENE_SRC.index("function pulseGlow(")
    body = SCENE_SRC[at:at + 400]
    assert "material.opacity +=" in body, (
        "an incremental step toward the target, not an outright assignment -- "
        "snapping opacity would make a pod's glow pop on/off instead of fade"
    )


# ── set dressing ─────────────────────────────────────────────────────────────

def test_the_floor_grid_texture_was_removed():
    # Reported: an extra per-pod texture on top of the already-tinted slab
    # read as visual noise, not polish -- and cost a draw call and a canvas
    # texture upload per pod for it. builders.js no longer defines it at all.
    assert "makeFloorTiles" not in SCENE_SRC
    assert "export function makeFloorTiles" not in BUILDERS_SRC


def test_every_pod_gets_exactly_one_whiteboard_and_one_plant():
    # A second plant used to stand on the same corner as the floor sign and
    # covered part of the text.
    at = SCENE_SRC.index("function ensurePod(")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  function ", at + 10)]
    assert body.count("makeWhiteboard(") == 1
    assert body.count("makePlant(") == 1


# ── disposal ─────────────────────────────────────────────────────────────────

def test_disposetree_releases_every_new_userdata_tagged_resource():
    at = BUILDERS_SRC.index("export function disposeTree(")
    body = BUILDERS_SRC[at:at + 1400]
    assert "userData.podGlow" in body, "disposeTree must know how to free a podGlow"


# ── smoothness ───────────────────────────────────────────────────────────────

def test_bloom_renders_at_a_capped_pixel_ratio():
    # Reported: motion got less smooth after this pass landed. Bloom's 5-level
    # blur chain rendering at full device pixel ratio (up to 2x) was the
    # single biggest new per-frame cost -- a soft effect gains no visible
    # sharpness from it, so it is capped independent of the renderer's own
    # (still-uncapped, for everything else) ratio.
    assert "composer.setPixelRatio(1)" in SCENE_SRC


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


def test_an_empty_seats_nameplate_is_hidden_not_just_unlabelled():
    # Reported: an idle Business seat's "<Department> Lead" nameplate only
    # repeated what the floor sign already says. A nameplate now earns its
    # own black bar exactly when there is a real worker to report on --
    # current activity while running, or a summary once done.
    assert "seat.plate.visible = (lod === 'near') && !!worker;" in SCENE_SRC
    at = SCENE_SRC.index("function syncLod() {")
    body = SCENE_SRC[at:at + 300]
    assert "!!seat.workerId" in body, (
        "the zoom-driven LOD toggle must respect the same rule, or zooming "
        "in/out would resurrect an empty seat's nameplate"
    )


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
    assert "animateOutletSwitch()" in body
    assert ".office-canvas.is-switching-outlet{opacity:0;}" in CSS
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
    assert "const OUTLET_FADE_MIN_MS = 220;" in OFFICE_INDEX_SRC
    at = OFFICE_INDEX_SRC.index("function revealAfterOutletFade(")
    body = OFFICE_INDEX_SRC[at:OFFICE_INDEX_SRC.index("\n}", at)]
    assert "performance.now() - _outletFadeStartedAt" in body
    assert "OUTLET_FADE_MIN_MS - elapsed" in body
    assert "window.setTimeout(reveal, remaining)" in body
    assert "classList.remove('is-switching-outlet')" in body
