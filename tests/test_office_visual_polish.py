"""Source-structure pins for the visual-polish pass on top of the department
floor colours: a bloom post-process, a hemisphere+rim lighting rig, a
department icon badge, and per-pod set dressing (floor tiles, a whiteboard,
a working-pod glow).

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

def test_ensure_pod_threads_an_icon_through_to_a_floating_badge():
    at = SCENE_SRC.index("function ensurePod(")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  function ", at + 10)]
    assert "icon" in body
    assert "makeDeptIcon(icon)" in body


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

def test_every_pod_and_the_conductor_get_floor_tiles():
    assert SCENE_SRC.count("makeFloorTiles(") == 2, (
        "one call in ensurePod, one in ensureConductor"
    )


def test_every_pod_gets_exactly_one_whiteboard_alongside_its_two_plants():
    at = SCENE_SRC.index("function ensurePod(")
    body = SCENE_SRC[at:SCENE_SRC.index("\n  function ", at + 10)]
    assert body.count("makeWhiteboard(") == 1


# ── disposal ─────────────────────────────────────────────────────────────────

def test_disposetree_releases_every_new_userdata_tagged_resource():
    at = BUILDERS_SRC.index("export function disposeTree(")
    body = BUILDERS_SRC[at:at + 1400]
    for tag in ("floorTiles", "podGlow"):
        assert f"userData.{tag}" in body, f"disposeTree must know how to free a {tag}"
