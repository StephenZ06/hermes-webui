"""Source-structure pins for the visual-polish pass on top of the department
floor colours: a bloom post-process, a hemisphere+rim lighting rig, a
department icon painted inline on its floor sign, and a per-pod whiteboard
and working-pod glow.

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


# ── department icon ──────────────────────────────────────────────────────────

def test_ensure_pod_threads_an_icon_into_the_floor_sign():
    # An earlier attempt painted the icon in its own band above the name, and
    # separately as a sprite floating above the pod -- both worked as drawing
    # but the extra height/position pushed things into the desk or looked
    # bolted-on. It is now one argument to the same makeFloorTitle() call
    # that already draws the name.
    at = SCENE_SRC.index("function ensurePod(")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  function ", at + 10)]
    assert "makeFloorTitle(label, slabWidth * 0.88, palette, { fit: true, icon })" in body
    assert "makeDeptIcon" not in SCENE_SRC


def test_a_pod_rebuilds_when_only_its_icon_changes():
    # Mirrors label/colour: ensurePod's early-return guard must include icon,
    # or a department that gets an icon (or loses one) after the pod already
    # exists would never repaint it.
    at = SCENE_SRC.index("function ensurePod(")
    guard = SCENE_SRC[at:SCENE_SRC.index(") return pod;", at)]
    assert "pod.icon === icon" in guard


# ── working-pod glow ─────────────────────────────────────────────────────────

def test_every_pod_gets_a_glow_mesh_and_stores_its_material():
    assert "makePodGlow(slabWidth, slabDepth, color)" in SCENE_SRC
    assert "glowMaterial: glow.material" in SCENE_SRC


def test_the_conductor_glow_is_driven_by_orchestrating_status_not_active_clusters():
    assert "conductor.userData.glowMaterial" in SCENE_SRC
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


def test_every_pod_gets_exactly_one_whiteboard_alongside_its_two_plants():
    at = SCENE_SRC.index("function ensurePod(")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  function ", at + 10)]
    assert body.count("makeWhiteboard(") == 1


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


def test_pod_outline_sits_close_to_the_slab_surface():
    # Reported: the dashed outline visibly "stuck out" past a pod's corners.
    # The isometric camera looks down at an angle, so a point held higher
    # above the slab at the same x/z projects further outward on screen than
    # the slab's own edge -- the outline's old 0.66 default (matching the
    # floor sign's height, for no real reason) made that gap noticeable.
    at = BUILDERS_SRC.index("export function makeSlabOutline(")
    body = BUILDERS_SRC[at:BUILDERS_SRC.index("\n}", at)]
    assert "height == null ? 0.605 : height" in body
