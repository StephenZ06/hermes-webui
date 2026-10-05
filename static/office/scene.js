// Office visualization — WebGL scene.
//
// Phase 1 built the shell: renderer, isometric camera, lighting, ground, and
// a render loop whose GPU resources are released the moment the panel is
// left. Phase 3 puts the delegation tree on that floor — a pod per cluster,
// a desk per worker, a figure whose posture is the worker's live state.
//
// The scene draws; it does not decide. It is handed adapter state and
// reconciles what is on screen to match. It never fetches, never polls, and
// holds no truth of its own — see docs/rfcs/office-visualization.md.
//
// WebGL inside a long-lived SPA panel leaks aggressively if the loop and the
// GPU resources aren't owned by someone. `createOfficeScene()` returns that
// owner: start/stop bracket the rAF loop, dispose() releases every geometry,
// material and the renderer's own context.
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { computeLayout, walkwaySpan, CONDUCTOR_RADIUS } from './layout.js';
import {
  makePod, makeDesk, makeChair, makeCubicle, setCubicleActive, makePerson, makeNameplate,
  makePlant, makeWhiteboard, makeChatBubble,
  makeWalkway, makeBridgeSegment, BRIDGE_DECK_WIDTH, drawNameplate, drawScreen,
  drawActiveScreen, drawChatBubble, MOOD_ICONS, easeOutCubic,
  poseWorker, poseWalking, hideLegs, disposeTree, disposeSharedCaches,
} from './builders.js';
import {
  createWanderer, createArrival, advanceArrival, arrivalSettle,
} from './motion.js';
import { shouldSleepWhileRunning } from './idle.js';

// Half-height of the orthographic frustum at zoom 1, in world units. The
// office is authored against this so a desk keeps the same on-screen size
// whatever the panel's aspect ratio is.
const FRUSTUM_HALF_HEIGHT = 42;
// Locked isometric view direction. Slightly taller than a true 2:1 iso so
// floor markings stay readable at overview zoom.
const ISO_DIRECTION = new THREE.Vector3(1, 0.92, 1).normalize();
const CAMERA_DISTANCE = 220;
const GROUND_SIZE = 400;
const KEY_LIGHT_INTENSITY = 2.25;
const FILL_LIGHT_INTENSITY = 0.82;
// A low, cool light from behind the key light, so a pod's far side isn't
// pure black — cheap depth cue, no shadow cost (this one never casts).
const RIM_LIGHT_INTENSITY = 0.68;
// A downward spotlight on the conductor adds a controlled highlight to the
// centre of the floor and deepens the contrast between lit platforms and
// shadowed undersides.
const SPOT_LIGHT_INTENSITY = 1.1;
// Bloom only exists to make a working pod's glow (builders.js's
// makePodGlow, pushed past normal 0-1 colour range on purpose) actually
// bloom — everything else in the scene sits well under 1.0 in linear space,
// so a threshold this close to 1 leaves the rest of the office alone.
const BLOOM_STRENGTH = 0.8;
const BLOOM_RADIUS = 0.4;
const BLOOM_THRESHOLD = 1.0;
// Camera motion. A fixed diagram-camera makes the office read as a chart; a
// camera that travels makes it read as a place. Focusing flies to a desk and
// zooms in, and the view returns to the whole floor on Escape or a click on
// empty ground.
const FOCUS_ZOOM = 2.6;
const TWEEN_MS = 850;
// Zoom-driven level of detail. Nameplates are the first thing to overlap into
// noise once the floor is dense, so they go first; the figures themselves are
// the point of the view and stay.
const LOD_NEAR_ZOOM = 0.9;
// Wheel zoom bounds, as a multiple of whatever the auto-framed zoom is.
const ZOOM_MIN = 0.35;
const ZOOM_MAX = 3.2;
// Breathing room left around the office when the camera frames it.
const FRAME_MARGIN = 1.15;
// Extra world units of headroom for the parts that stand up off the floor —
// figures, monitors, nameplates — which the floor radius alone does not
// account for.
const FRAME_HEADROOM = 10;
// Fixed isometric cameras foreshorten the floor: a horizontal distance R
// covers only R * sin(elevation) of screen height. Framing on the raw radius
// therefore leaves the office a small island in the middle of the panel.
const ISO_VERTICAL_SCALE = ISO_DIRECTION.y;
// Screen-right, in world space, for this fixed isometric view. Used to slide
// a focused desk out from under the detail panel, which owns the right edge.
const SCREEN_RIGHT = new THREE.Vector3(1, 0, -1).normalize();
// The conductor's plinth is a square of this side, and pods are their content
// plus this much slab. Both are needed to find where a walkway should stop.
const CONDUCTOR_SLAB = CONDUCTOR_RADIUS * 1.4;
const POD_SLAB_PADDING = 3;
// Keep every platform, including The Floor, at this shared elevation. Besides
// aligning the scene's connected decks, this gives the Floor the same visible
// platform thickness as departments, subagents, and the conductor.
const RAISED_PLATFORM_Y = 0.52;
// Department, Subagents, and Conductor share the platform elevation.
const CONDUCTOR_PLATFORM_Y = RAISED_PLATFORM_Y;
// Standard bridges sit visibly below the raised platform tops. The Floor's
// own ramp/deck route remains governed by floorBridgeRoute().
const LEVEL_BRIDGE_Y = -0.45;
// The endpoint calculation follows a bridge's centreline, but each deck is
// much wider. Tucking it by half that width keeps the entire squared end cap
// beneath rounded platform rims — not just its middle — at diagonal routes.
const BRIDGE_DECK_PLATFORM_OVERLAP = BRIDGE_DECK_WIDTH / 2;
// Palettes are WebGL material colours rather than CSS custom properties:
// they are handed to THREE.Color, not to a stylesheet. The panel's own
// chrome still comes from the app's theme tokens as usual.
const PALETTES = {
  light: {
    ground: '#f2efe8', grid: '#d8d3c8',
    podTop: '#ffffff', podSide: '#e4dfd4', platformBase: '#000000',
    deskTop: '#c9a227', deskLeg: '#8b8b93',
    chair: '#5f6672',
    cubiclePanel: '#dfe2e8', cubicleFrame: '#8a92a0', cubicleGlass: '#ffffff',
    cubicleRugShade: '#2b3140', cubicleRugMix: 0.14,
    shirt: '#6b8fb5', skin: '#e8b98e', hair: '#3b2b1d', trousers: '#3e4048',
    screenBezel: '#2c2c34', screenBg: '#14141c', screenActiveBg: '#f7f7fb',
    screenText: '#8fb9a8', screenTextBright: '#d8f0e4',
    plateBg: 'rgba(255,255,255,0.92)', plateText: '#151414', plateAccent: '#1e9070',
    conductor: '#2b3245',
    floorTitle: '#8d8d95', floorTitleStroke: 'rgba(20,18,14,0.55)',
    pot: '#b07a52', plant: '#5f8a5f', walkway: '#d2cbc0', bridgeDeck: '#090a0c', bridgeBeam: '#020304',
    floorBridgeDeck: '#090a0c', floorBridgeBeam: '#020304',
    outlineIdle: '#a8a294', outlineActive: '#1e9070', connector: '#9a9490',
    board: '#fbfaf6', hemiSky: '#f4f1ea', hemiGround: '#c9c2ae', rim: '#cfe0f7',
    mousePad: '#1a1a24', keyboard: '#24242e', keyboardKey: '#9a9aa8', mouse: '#c9c9d6',
    bubbleBg: 'rgba(20,20,30,0.88)', bubbleStroke: 'rgba(180,180,200,0.55)', bubbleText: '#f2f2f7',
  },
  dark: {
    ground: '#0a0c14', grid: '#1a2133',
    podTop: '#0d172b', podSide: '#0a101e', platformBase: '#000000',
    deskTop: '#a05f1a', deskLeg: '#4a4a58',
    chair: '#2a2f3a',
    cubiclePanel: '#8e97a6', cubicleFrame: '#4b5363', cubicleGlass: '#dbe4f0',
    cubicleRugShade: '#000000', cubicleRugMix: 0.35,
    shirt: '#4f7ca8', skin: '#c68b59', hair: '#1a1a20', trousers: '#2b2d36',
    screenBezel: '#0e0e14', screenBg: '#0a0a12', screenActiveBg: '#f0f0f7',
    screenText: '#5adeb7', screenTextBright: '#b9f5e2',
    plateBg: 'rgba(15,23,42,0.88)', plateText: '#f2f2f7', plateAccent: '#5adeb7',
    conductor: '#e2e8f0',
    floorTitle: '#c9c9da', floorTitleStroke: 'rgba(6,6,12,0.6)',
    pot: '#7a5236', plant: '#3f5f45', walkway: '#111827', bridgeDeck: '#090a0c', bridgeBeam: '#020304',
    floorBridgeDeck: '#090a0c', floorBridgeBeam: '#020304',
    outlineIdle: '#575775', outlineActive: '#5adeb7', connector: '#41415e',
    board: '#34364a', hemiSky: '#4a5d84', hemiGround: '#0a0c14', rim: '#6d94c9',
    mousePad: '#12121a', keyboard: '#1e1e28', keyboardKey: '#8a8a98', mouse: '#b8b8c6',
    bubbleBg: 'rgba(12,12,18,0.9)', bubbleStroke: 'rgba(140,140,170,0.5)', bubbleText: '#f2f2f7',
  },
};

// Worker shirt tints, assigned by desk index so a pod reads as several
// people rather than a row of clones. Deliberately not status colours —
// status is carried by posture and the nameplate glyph.
const TINTS = ['#6b8fb5', '#8a9a5b', '#b5836b', '#7a6bb5', '#5ba69a', '#b56b8f'];

function prefersDark() {
  try {
    return document.documentElement.classList.contains('dark');
  } catch (_err) {
    return true;
  }
}

/**
 * Build the office scene against an existing <canvas>.
 *
 * The caller owns the canvas and the element it sits in; this owns
 * everything inside WebGL. Nothing here reads or writes app state.
 *
 * @param {HTMLCanvasElement} canvas
 * @param {object} [options] `onSelect(workerId)` — a worker was clicked.
 */
export function createOfficeScene(canvas, options) {
  if (!canvas) throw new Error('createOfficeScene: a canvas element is required');
  const config = options || {};

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  // alpha:true and no scene.background: the panel's own themed background
  // shows through, so the scene tracks every skin/light/dark mode for free
  // instead of hard-coding a clear colour per theme.
  renderer.setClearAlpha(0);
  // Capped device-pixel ratio. Uncapped DPR on a 3x phone quadruples the
  // fragment cost for no visible gain and is the single easiest way to make
  // this panel drop frames.
  // At least 1.5x internally (capped at 2x): on a 1x display, thin diagonal
  // edges (bridge rails, the floor grid, slab rims) stair-stepped even with
  // MSAA; rendering above the screen's density and filtering down smooths them.
  renderer.setPixelRatio(Math.min(Math.max(window.devicePixelRatio || 1, 1.5), 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  // PCFSoftShadowMap is deprecated as of r185 and silently falls back to
  // PCFShadowMap with a console warning; ask for what we actually get.
  renderer.shadowMap.type = THREE.PCFShadowMap;
  // ACES lets the bloom pass' deliberately-over-1 glow colours (see
  // builders.js's makePodGlow) roll off softly instead of just clipping to
  // white, and reads as filmic rather than washed out for everything else.
  renderer.toneMapping = THREE.ACESFilmicToneMapping;

  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, -400, 800);
  const cameraTarget = new THREE.Vector3(0, 0, 0);
  let framedCenter = { x: 0, z: 0 };

  // `overview` is where auto-framing wants the camera; `view` is where it
  // actually is. They diverge while focused on a desk or while the user has
  // zoomed by hand, and a tween carries the camera between them.
  const overview = { x: 0, z: 0, zoom: 1 };
  const view = { x: 0, z: 0, zoom: 1 };
  let tween = null;
  let focusedId = null;
  let manualZoom = false;
  let lod = 'near';
  let palette = PALETTES[prefersDark() ? 'dark' : 'light'];

  // Tracked so dispose() can release them without walking the graph and
  // guessing which resources were ours.
  const ownedGeometries = [];
  const ownedMaterials = [];

  // ---- lighting rig -----------------------------------------------------
  // A hemisphere light in place of a flat ambient: a warm-ish sky tone from
  // above and a darker ground tone from below reads as bounced light rather
  // than a uniform fill, which is most of what separated the reference
  // screenshot's floor from a flatly-lit one.
  const ambient = new THREE.HemisphereLight(palette.hemiSky, palette.hemiGround, FILL_LIGHT_INTENSITY);
  scene.add(ambient);

  const keyLight = new THREE.DirectionalLight(0xffffff, KEY_LIGHT_INTENSITY);
  keyLight.position.set(60, 120, 40);
  keyLight.castShadow = true;
  keyLight.shadow.mapSize.set(2048, 2048);
  keyLight.shadow.camera.near = 1;
  keyLight.shadow.camera.far = 500;
  keyLight.shadow.camera.left = -180;
  keyLight.shadow.camera.right = 180;
  keyLight.shadow.camera.top = 180;
  keyLight.shadow.camera.bottom = -180;
  keyLight.shadow.bias = -0.0003;
  keyLight.shadow.normalBias = 0.02;
  // Softens the shadow edge (PCF sample spread, in shadow-map texels).
  keyLight.shadow.radius = 2.5;
  scene.add(keyLight);
  // The light aims at its target's world position; keep it in the scene so
  // moving it with the framed office updates its matrix.
  scene.add(keyLight.target);
  const KEY_LIGHT_OFFSET = keyLight.position.clone();

  /**
   * Fit the shadow map to the office actually on the floor. A fixed 360-unit
   * square spread 2048 texels so thin that desks and figures (about a unit
   * across) cast stair-stepped shadows that shimmered as they moved; a frame
   * around the office's own radius is several times sharper for the same map.
   */
  function fitShadowToOffice() {
    const half = Math.min(180, Math.max(30, framedRadius * 1.25 + 8));
    const cam = keyLight.shadow.camera;
    cam.left = -half;
    cam.right = half;
    cam.top = half;
    cam.bottom = -half;
    cam.updateProjectionMatrix();
    keyLight.target.position.set(framedCenter.x, 0, framedCenter.z);
    keyLight.position.set(framedCenter.x + KEY_LIGHT_OFFSET.x, KEY_LIGHT_OFFSET.y, framedCenter.z + KEY_LIGHT_OFFSET.z);
    keyLight.target.updateMatrixWorld();
  }

  // A low rim light from behind/opposite the key light so a pod's far side
  // isn't flat black. Cheap: no shadow map, no extra render pass.
  const rimLight = new THREE.DirectionalLight(palette.rim, RIM_LIGHT_INTENSITY);
  rimLight.position.set(-70, 50, -60);
  scene.add(rimLight);

  // A soft spotlight pulls the eye to the conductor and gives the glossy
  // platforms a controlled specular highlight. It does not cast shadows — the
  // key light already owns the shadow map — so it adds no extra render pass.
  const spotLight = new THREE.SpotLight(palette.hemiSky, SPOT_LIGHT_INTENSITY);
  spotLight.position.set(0, 90, 0);
  spotLight.target.position.set(0, 0, 0);
  spotLight.angle = Math.PI / 5;
  spotLight.penumbra = 0.5;
  spotLight.distance = 250;
  scene.add(spotLight);
  scene.add(spotLight.target);

  // ---- post-processing ---------------------------------------------------
  // Routing the render through a composer moves it off the canvas' own
  // framebuffer, where `antialias: true` above no longer applies -- WebGL
  // only antialiases the default framebuffer, not an offscreen render target
  // a post-process pipeline draws into. Without this, every edge (a
  // figure's head is where it shows up most) goes jagged the moment bloom
  // lands. `samples: 4` asks for the same kind of multisampling explicitly on
  // the composer's own target; `HalfFloatType` matches what EffectComposer
  // would have created by default and keeps the glow mesh's deliberately
  // over-1.0 colour (see builders.js's makePodGlow) from being clamped to
  // white before bloom ever sees it.
  const composerTarget = new THREE.WebGLRenderTarget(1, 1, {
    // As many MSAA samples as the GPU allows, up to 8.
    samples: Math.max(4, Math.min(8, (renderer.capabilities && renderer.capabilities.maxSamples) || 4)), type: THREE.HalfFloatType,
  });
  // One bloom pass over the whole render. Nothing in the ordinary palette sits
  // near the 1.0 threshold (see BLOOM_THRESHOLD above), so this only lights up
  // a working pod's own glow mesh -- no per-object "selective bloom" layer
  // trick needed.
  const composer = new EffectComposer(renderer, composerTarget);
  composer.addPass(new RenderPass(scene, camera));
  const bloomPass = new UnrealBloomPass(
    new THREE.Vector2(1, 1), BLOOM_STRENGTH, BLOOM_RADIUS, BLOOM_THRESHOLD);
  composer.addPass(bloomPass);
  composer.addPass(new OutputPass());
  // Bloom is a soft, blurred effect, but rendering the whole composer at 1x
  // on a high-DPR display makes every edge look blurry once the camera zooms
  // in. Use the same capped ratio as the renderer (up to 2x) so MSAA + bloom
  // stay sharp without the uncapped cost of a 3x phone.
  composer.setPixelRatio(renderer.getPixelRatio());

  // ---- ground -----------------------------------------------------------
  // A fixed-size floor shows its own edge -- a hard border against the
  // transparent canvas -- the moment a big enough office, zoomed out far
  // enough, outgrows it. Rebuilt larger (never smaller: shrinking it back
  // would flash the edge again the moment a big run's pods are swept) as
  // ensureGroundCovers() sees the framed office actually needs the room.
  let groundHalfSize = GROUND_SIZE / 2;
  let ground = null;
  let groundGeometry = null;
  let groundMaterial = null;
  let grid = null;

  function buildGround(halfSize) {
    const size = halfSize * 2;
    const geometry = new THREE.PlaneGeometry(size, size);
    const material = new THREE.MeshStandardMaterial({
      color: palette.ground, roughness: 0.95, metalness: 0.0,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.rotation.x = -Math.PI / 2;
    mesh.receiveShadow = true;
    // Capped rather than scaled 1:1 with size: past a few hundred divisions
    // the lines are imperceptible anyway (this only grows for a very large,
    // very zoomed-out office), and an uncapped count would turn one big run
    // into thousands of extra line segments for no visible gain.
    const divisions = Math.min(600, Math.max(20, Math.round(size / 5)));
    const gridHelper = new THREE.GridHelper(size, divisions, palette.grid, palette.grid);
    gridHelper.position.y = 0.02;
    if (gridHelper.material) {
      gridHelper.material.transparent = true;
      gridHelper.material.opacity = 1;
    }
    return { mesh, geometry, material, gridHelper };
  }

  function installGround(halfSize) {
    if (ground) {
      scene.remove(ground);
      groundGeometry.dispose();
      groundMaterial.dispose();
    }
    if (grid) {
      scene.remove(grid);
      if (grid.geometry) grid.geometry.dispose();
      if (grid.material) grid.material.dispose();
    }
    const built = buildGround(halfSize);
    groundHalfSize = halfSize;
    ground = built.mesh;
    groundGeometry = built.geometry;
    groundMaterial = built.material;
    grid = built.gridHelper;
    scene.add(ground);
    scene.add(grid);
    // Only these two ever land in these arrays (see dispose() below) --
    // replacing the array contents outright is safe and correct here.
    ownedGeometries.length = 0;
    ownedMaterials.length = 0;
    ownedGeometries.push(groundGeometry);
    ownedMaterials.push(groundMaterial);
    if (grid.geometry) ownedGeometries.push(grid.geometry);
    if (grid.material) ownedMaterials.push(grid.material);
  }

  /**
   * Grow the ground to cover whatever the camera can show of it, including
   * the farthest the user can zoom out (ZOOM_MIN, beyond the office's own
   * auto-framed fit). The x3 folds in wide-monitor aspect ratios (the
   * frustum widens with aspect, not just height) plus slack -- an exact
   * figure isn't worth chasing since this only ever needs to be "clearly
   * enough", not tight.
   */
  function ensureGroundCovers(radius) {
    const needed = Math.max(GROUND_SIZE / 2, (radius * FRAME_MARGIN / ZOOM_MIN) * 3);
    if (needed <= groundHalfSize * 1.05) return;
    installGround(needed);
  }

  installGround(groundHalfSize);

  // ---- office contents --------------------------------------------------
  // Outlet-specific furniture (pods, walkways, seats) lives in `office`; the
  // shared conductor plinth lives in `backdrop` so it stays visible while the
  // floor swaps between Projects and Business.
  let office = new THREE.Group();
  scene.add(office);
  let backdrop = new THREE.Group();
  scene.add(backdrop);

  /** cluster -> {group, width, depth} */
  let pods = new Map();
  /** cluster -> walkway slab joining that pod to the middle of the office */
  let walkways = new Map();
  /** deskId -> {group, person, plate, screen, workerId, pose, tint} */
  let seats = new Map();
  let conductor = null;
  let lastState = null;
  let framedRadius = 0;
  fitShadowToOffice();

  function ensureConductor() {
    if (conductor) return conductor;
    const group = new THREE.Group();
    group.position.y = CONDUCTOR_PLATFORM_Y;
    // A tap on the plinth frames it, the same as a tap on any pod.
    group.userData.podCluster = '__conductor__';
    const pod = makePod(CONDUCTOR_SLAB, CONDUCTOR_SLAB, palette);
    group.add(pod);
    // Unlike a pod, the conductor's plinth never tints/glows with activity --
    // reported as distracting since it's the one fixed landmark on the floor,
    // there whether anything is running or not. The pacing figure (below)
    // already carries the "it's doing something" cue for the conductor.
    const person = makePerson(palette, palette.conductor);
    person.position.y = 0.6;
    group.add(person);
    // Paces its plinth between delegations. Only ever while genuinely idle:
    // a walking figure reads as activity, and the office does not imply work
    // Hermes has not reported.
    group.userData.wanderer = createWanderer({ radius: CONDUCTOR_RADIUS * 0.42 });
    group.userData.person = person;
    backdrop.add(group);
    conductor = group;
    return conductor;
  }

  function ensurePod(cluster, width, depth, label, color) {
    let pod = pods.get(cluster);
    if (pod && pod.width === width && pod.depth === depth && pod.label === label
      && pod.color === color) return pod;
    if (pod) {
      office.remove(pod.group);
      disposeTree(pod.group);
    }
    const slabWidth = width + POD_SLAB_PADDING;
    const slabDepth = depth + POD_SLAB_PADDING;
    const group = makePod(slabWidth, slabDepth, palette, color);
    // A tap on the slab (not on a worker) frames this pod.
    group.userData.podCluster = cluster;

    // One plant, on the corner facing away from the sign (the sign sits on
    // the +z side above), plus a whiteboard on a third corner. Scenery
    // carries no state, so it can never mislead anyone about what Hermes is
    // doing. A second plant used to stand on the sign's own side and covered
    // part of the text.
    const plant = makePlant(palette);
    plant.position.set(-(slabWidth / 2 - 1.1), 0.6, -(slabDepth / 2 - 1.1));
    group.add(plant);
    // The Floor's far edge is occupied by desks, so this decorative board
    // clips against the slab rim there. Other pods retain their whiteboard.
    if (label !== 'The Floor') {
      const whiteboard = makeWhiteboard(palette);
      whiteboard.position.set(slabWidth / 2 - 1.1, 0, -(slabDepth / 2 - 1.1));
      group.add(whiteboard);
    }

    office.add(group);
    pod = {
      group, width, depth, label, color, active: false,
    };
    pods.set(cluster, pod);
    return pod;
  }

  function eachActivityChevron(bridge, fn, root = bridge) {
    if (!bridge) return;
    if (bridge.userData && bridge.userData.activityChevrons) {
      bridge.userData.activityChevrons.forEach((chevron, index, chevrons) => fn(chevron, index, chevrons.length, root));
    }
    bridge.children.forEach(child => eachActivityChevron(child, fn, root));
  }

  function setBridgeActive(bridge, active) {
    if (!bridge) return;
    eachActivityChevron(bridge, chevron => { chevron.userData.active = active; });
  }

  function advanceBridgeFade(bridge, dtMs, elapsed) {
    if (!bridge) return;
    let arrivalWave = 0;
    eachActivityChevron(bridge, (chevron, index, count, root) => {
      const singlePacket = root.userData.singleChevronFlow;
      const activeIndex = Math.floor(elapsed * 5.4) % Math.max(1, count);
      const flowMarkerCount = Math.min(count, root.userData.flowMarkerCount || 1);
      const markerSpacing = Math.max(1, Math.floor(count / flowMarkerCount));
      const flowOffset = (index - activeIndex + count) % Math.max(1, count);
      const isFlowMarker = flowOffset % markerSpacing === 0
        && flowOffset / markerSpacing < flowMarkerCount;
      const wave = chevron.userData.active
        ? (singlePacket ? (isFlowMarker ? 1 : 0) : Math.max(0, Math.sin(elapsed * 9 + chevron.position.z * 4)))
        : 0;
      // A running route has one travelling lit marker, not a permanently
      // illuminated row. Between wave crests each triangle returns to idle.
      const target = 0.72 + wave * 0.28;
      chevron.material.opacity += (target - chevron.material.opacity) * Math.min(1, dtMs * 0.012);
      chevron.material.emissive.set(wave > 0.02 ? chevron.userData.activeColor : '#0b1220');
      chevron.material.emissiveIntensity = wave * 2;
      const pulse = chevron.userData.active ? 1 + wave * 0.28 : 1;
      chevron.scale.set(pulse, pulse, 1);
      // Local +Z points from the conductor to the destination.  When the
      // travelling packet reaches the final marker, its platform's lower
      // coloured delivery layer receives the same pulse.
      if (chevron.userData.active && index === count - 1) arrivalWave = Math.max(arrivalWave, wave);
    });
    return arrivalWave;
  }

  function advanceDeliveryGlow(record, arrivalWave, dtMs) {
    const layer = record && record.group && record.group.userData.deliveryLayer;
    const material = layer && layer.material;
    if (!material || !material.emissive) return;
    record.deliveryGlow = (record.deliveryGlow || 0)
      + ((arrivalWave || 0) - (record.deliveryGlow || 0)) * Math.min(1, dtMs * 0.012);
    const idleIntensity = layer.userData.idleEmissiveIntensity || 0;
    material.emissiveIntensity = idleIntensity + record.deliveryGlow * 1.45;
  }

  /**
   * A walkway from each pod back toward the conductor, so the floor reads as
   * a place with circulation rather than islands floating in a void.
   */
  function ensureWalkway(cluster, pod) {
    let walk = walkways.get(cluster);
    const span = walkwaySpan({
      x: pod.x, z: pod.z,
      halfWidth: (pod.width + POD_SLAB_PADDING) / 2,
      halfDepth: (pod.depth + POD_SLAB_PADDING) / 2,
    }, CONDUCTOR_SLAB / 2, {
      // The deck enters beneath both rounded platform rims, closing the
      // visible gap. Its raised rails stop on the exposed bridge surface.
      overlap: BRIDGE_DECK_PLATFORM_OVERLAP,
      hubRadius: CONDUCTOR_SLAB * 0.12,
      podRadius: Math.min(
        pod.width + POD_SLAB_PADDING,
        pod.depth + POD_SLAB_PADDING,
      ) * 0.12,
    });
    if (!span) {
      if (walk) { office.remove(walk); disposeTree(walk); walkways.delete(cluster); }
      return null;
    }
    if (walk) { office.remove(walk); disposeTree(walk); }
    if (cluster === 'floor') {
      walk = new THREE.Group();
      // The Floor span is a lower-level structure. Draw every part before
      // the pods so Marketing's nearer platform reliably occludes it.
      walk.renderOrder = -1;
      const bridgePalette = floorBridgePalette();
      const floorColor = '#3b82f6';
      floorBridgeRoute(span, pod).forEach(segment => placeBridgeSegment(
        walk, segment, bridgePalette, floorColor, true,
      ));
      walk.userData.singleChevronFlow = true;
      // A broader packet gives the long Floor route enough visible motion
      // without turning every deck segment into an active indicator.
      walk.userData.flowMarkerCount = 3;
    } else {
      const podRecord = pods.get(cluster);
      const railColor = podRecord && podRecord.color ? podRecord.color : null;
      walk = makeWalkway(span.length, palette, railColor);
      const mid = span.start + span.length / 2;
      walk.position.set(Math.sin(span.angle) * mid, LEVEL_BRIDGE_Y, Math.cos(span.angle) * mid);
      walk.rotation.y = span.angle;
      walk.userData.singleChevronFlow = true;
    }
    office.add(walk);
    walkways.set(cluster, walk);
    return span;
  }

  function floorBridgePalette() {
    return {
      ...palette,
      bridgeDeck: palette.floorBridgeDeck,
      bridgeBeam: palette.floorBridgeBeam,
    };
  }

  function floorBridgeRoute(span, pod) {
    // The Floor is physically below the office pods. Its bridge exits through
    // the conductor's underside, slopes down once, then stays on one direct
    // lower deck to the floor slab. That clears every pod instead of turning
    // into an L-shaped surface in the middle of the office.
    // This is deliberately the screen-facing bottom edge of the conductor,
    // not its radial edge toward The Floor. It makes the first ramp leg read
    // as descending out of the plinth before the long diagonal begins.
    const exit = { x: 0, z: CONDUCTOR_SLAB / 2 - 0.6 };
    const length = Math.hypot(pod.x - exit.x, pod.z - exit.z) || 1;
    const rampLength = Math.min(6.4, length * 0.18);
    // A fixed 120-degree first leg gives the visible drop its intended
    // steeper diagonal before the second, straight span goes to The Floor.
    const FLOOR_RAMP_ANGLE = 120 * Math.PI / 180;
    const rampEnd = {
      x: exit.x + Math.sin(FLOOR_RAMP_ANGLE) * rampLength,
      z: exit.z + Math.cos(FLOOR_RAMP_ANGLE) * rampLength,
    };
    // Retract the Floor ramp as one physical unit: its deck edge and rails
    // begin together, two units clear of the conductor platform.
    const FLOOR_CONDUCTOR_TRIM = 3;
    const rampStart = {
      x: exit.x + Math.sin(FLOOR_RAMP_ANGLE) * FLOOR_CONDUCTOR_TRIM,
      z: exit.z + Math.cos(FLOOR_RAMP_ANGLE) * FLOOR_CONDUCTOR_TRIM,
    };
    // Meet the midpoint of the facing Floor edge, never a corner or a desk
    // inside the platform. The approach direction selects the facing side.
    const destination = floorBridgeEntryPoint(rampEnd, pod);
    return [
      // This stays visibly below the pod tops while remaining above the
      // scene ground, so it is a physical lower deck rather than disappearing.
      {
        from: rampStart, to: rampEnd, fromTopY: 0.46, toTopY: 0.18,
      },
      {
        from: rampEnd, to: destination, fromTopY: 0.18, toTopY: 0.18,
      },
    ];
  }

  function floorBridgeEntryPoint(from, pod) {
    const halfWidth = (pod.width + POD_SLAB_PADDING) / 2;
    const halfDepth = (pod.depth + POD_SLAB_PADDING) / 2;
    const dx = from.x - pod.x;
    const dz = from.z - pod.z;
    if (Math.abs(dx) / halfWidth >= Math.abs(dz) / halfDepth) {
      return { x: pod.x + (dx >= 0 ? halfWidth : -halfWidth), z: pod.z };
    }
    return { x: pod.x, z: pod.z + (dz >= 0 ? halfDepth : -halfDepth) };
  }

  function placeBridgeSegment(parent, segment, segmentPalette = palette, railColor, isFloor = false) {
    const dx = segment.to.x - segment.from.x;
    const dz = segment.to.z - segment.from.z;
    const length = Math.hypot(dx, dz);
    if (length < 0.01) return;
    const startCenterY = segment.fromTopY - 0.17;
    const endCenterY = segment.toTopY - 0.17;
    const direction = new THREE.Vector3(dx, endCenterY - startCenterY, dz).normalize();
    const options = isFloor
      ? {
        railColor,
        railTrimStart: segment.railTrimStart || 0,
        railTrimEnd: segment.railTrimEnd || 0,
        segmentColor: segmentPalette.bridgeDeck,
        beamColor: segmentPalette.bridgeBeam,
      }
      : { railColor };
    const deck = makeBridgeSegment(Math.hypot(length, endCenterY - startCenterY), segmentPalette, options);
    deck.position.set(
      (segment.from.x + segment.to.x) / 2,
      (startCenterY + endCenterY) / 2,
      (segment.from.z + segment.to.z) / 2,
    );
    deck.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), direction);
    deck.traverse(part => { part.renderOrder = parent.renderOrder; });
    parent.add(deck);
  }

  function maxDistanceInsidePod(x, z, dx, dz, pod, margin = 0.65) {
    if (!pod) return 0;
    const minX = pod.x - (pod.width + POD_SLAB_PADDING) / 2;
    const maxX = pod.x + (pod.width + POD_SLAB_PADDING) / 2;
    const minZ = pod.z - (pod.depth + POD_SLAB_PADDING) / 2;
    const maxZ = pod.z + (pod.depth + POD_SLAB_PADDING) / 2;
    const distances = [];
    if (dx > 1e-6) distances.push((maxX - x) / dx);
    if (dx < -1e-6) distances.push((minX - x) / dx);
    if (dz > 1e-6) distances.push((maxZ - z) / dz);
    if (dz < -1e-6) distances.push((minZ - z) / dz);
    return Math.max(0, Math.min(...distances.filter(distance => distance >= 0)) - margin);
  }

  function seatArrivalSeed(deskId) {
    let value = 2166136261;
    for (const char of String(deskId || '')) {
      value ^= char.charCodeAt(0);
      value = Math.imul(value, 16777619);
    }
    return (value >>> 0) / 4294967296;
  }

  function configureSeatArrival(seat, spot, pod) {
    if (seat.arrivalConfigured) return;
    seat.arrivalConfigured = true;
    const seed = seatArrivalSeed(seat.group.userData.deskId);
    const heading = { x: Math.sin(spot.rotationY), z: Math.cos(spot.rotationY) };
    const sideways = { x: Math.cos(spot.rotationY), z: -Math.sin(spot.rotationY) };
    const seated = { x: spot.x + heading.x * 1.9, z: spot.z + heading.z * 1.9 };
    const sideSign = seed < 0.5 ? -1 : 1;
    const sideRoom = maxDistanceInsidePod(seated.x, seated.z,
      sideways.x * sideSign, sideways.z * sideSign, pod);
    const lateral = sideSign * Math.min(1.4, sideRoom, 0.45 + seed * 1.1);
    const start = {
      x: seated.x + sideways.x * lateral,
      z: seated.z + sideways.z * lateral,
    };
    const forwardRoom = maxDistanceInsidePod(start.x, start.z, heading.x, heading.z, pod);
    const distance = Math.min(3.1, forwardRoom, 1.1 + seed * 1.6);
    if (distance < 0.35) {
      seat.arrival = createArrival(0);
      seat.arrival.done = true;
      return;
    }
    seat.arrival = createArrival(distance, undefined, lateral);
    seat.person.position.set(lateral, 0, 1.9 + distance);
  }

  function shouldShowNameplate(seat) {
    return lod === 'near' && !!seat.workerId && focusedId === seat.workerId;
  }

  function syncNameplateVisibility() {
    seats.forEach(seat => { seat.plate.visible = shouldShowNameplate(seat); });
  }

  /** (Re)build a desk's cubicle when its platform colour changes. */
  function ensureCubicle(seat, accent) {
    const key = accent || '';
    if (seat.cubicle && seat.cubicleKey === key) return;
    const wasActive = !!(seat.cubicle && seat.cubicle.userData.cubicle.active);
    if (seat.cubicle) seat.group.remove(seat.cubicle);
    seat.cubicle = makeCubicle(palette, accent || null);
    // Seats sit at y=0.6 while pod floors are raised by CONDUCTOR_PLATFORM_Y,
    // so stand the cubicle on the visible floor rather than inside the slab.
    seat.cubicle.position.y = CONDUCTOR_PLATFORM_Y;
    seat.cubicleKey = key;
    if (wasActive) setCubicleActive(seat.cubicle, true);
    seat.group.add(seat.cubicle);
  }

  function ensureSeat(deskId, tintIndex) {
    let seat = seats.get(deskId);
    if (seat) return seat;
    const group = new THREE.Group();
    const desk = makeDesk(palette);
    group.add(desk);
    const chair = makeChair(palette);
    chair.position.z = 1.9;
    group.add(chair);
    const person = makePerson(palette, TINTS[tintIndex % TINTS.length]);
    person.position.set(0, 0, 1.9);
    // Face the desk. makePerson's "work" pose reaches +z; the seat sits the
    // figure on the +z side of the desk, so without this the figure types with
    // its back to the monitor.
    person.rotation.y = Math.PI;
    group.add(person);
    const plate = makeNameplate(palette, '');
    plate.position.set(0, 5.0, 0);
    group.add(plate);

    const bubble = makeChatBubble(palette);
    group.add(bubble);

    // Marks the whole subtree as belonging to a worker so a raycast hit on
    // any child resolves back to one id.
    group.userData.deskId = deskId;
    plate.visible = false;
    office.add(group);
    seat = {
      group, person, plate, screen: desk.userData.screen, arrival: null, bubble,
      arrivalConfigured: false,
      workerId: null, pose: 'idle', label: '', status: '', toolKey: '',
      mood: '', moodUntil: 0, moodIcon: '', lastToolAt: 0, celebrateUntil: 0,
      screenSeed: Math.floor(Math.random() * 10000),
    };
    seats.set(deskId, seat);
    return seat;
  }

  function removeSeat(deskId) {
    const seat = seats.get(deskId);
    if (!seat) return;
    office.remove(seat.group);
    disposeTree(seat.group);
    seats.delete(deskId);
  }

  function removePod(cluster) {
    const pod = pods.get(cluster);
    if (pod) {
      office.remove(pod.group);
      disposeTree(pod.group);
      pods.delete(cluster);
    }
    const walk = walkways.get(cluster);
    if (walk) {
      office.remove(walk);
      disposeTree(walk);
      walkways.delete(cluster);
    }
  }

  function screenLines(worker) {
    if (!worker) return ['idle'];
    const lines = [worker.label || worker.id];
    if (worker.tool && worker.tool.name) {
      lines.push('> ' + worker.tool.name);
      if (worker.tool.preview) lines.push('  ' + worker.tool.preview);
    } else if (worker.status === 'running') {
      lines.push('> working');
    }
    if (worker.status !== 'running') lines.push('· ' + worker.status);
    if (worker.summary) lines.push('  ' + worker.summary);
    return lines;
  }

  function updateSeatMood(seat, mood, nowMs) {
    if (!seat.bubble) return;
    const icon = mood ? (MOOD_ICONS[mood] || '') : '';
    if (mood && mood !== seat.mood) {
      seat.mood = mood;
      seat.moodIcon = icon;
      seat.moodUntil = nowMs + 3200;
      drawChatBubble(seat.bubble, palette, icon);
      seat.bubble.visible = true;
      seat.bubble.scale.set(0.01, 0.01, 0.01);
    }
    if (nowMs >= seat.moodUntil && seat.moodUntil > 0) {
      seat.mood = '';
      seat.moodUntil = 0;
      seat.bubble.visible = false;
    }
  }

  /**
   * Reconcile the floor to a state snapshot from the adapter.
   * Idempotent: calling it twice with the same state changes nothing.
   */
  function syncOffice(state) {
    if (!state) return;
    lastState = state;
    ensureConductor();

    const layout = computeLayout(state.desks || []);
    const podsByCluster = new Map(layout.pods.map(pod => [pod.cluster, pod]));
    const workersById = new Map((state.workers || []).map(w => [w.id, w]));
    const liveClusters = new Set();
    const liveDesks = new Set();

    layout.pods.forEach(pod => {
      liveClusters.add(pod.cluster);
      const podLabel = pod.label
        || (pod.cluster === '__conductor__' ? 'Subagents' : '');
      const record = ensurePod(pod.cluster, pod.width, pod.depth, podLabel, pod.color || null);
      record.group.position.set(pod.x, CONDUCTOR_PLATFORM_Y, pod.z);
      const span = ensureWalkway(pod.cluster, pod);
    });

    (state.desks || []).forEach(desk => {
      const spot = layout.seats[desk.id];
      if (!spot) return;
      liveDesks.add(desk.id);
      const seat = ensureSeat(desk.id, desk.index);
      seat.group.position.set(spot.x, 0.6, spot.z);
      seat.group.rotation.y = spot.rotationY;
      const seatPod = podsByCluster.get(desk.cluster);
      ensureCubicle(seat, seatPod && seatPod.color);
      configureSeatArrival(seat, spot, podsByCluster.get(desk.cluster));

      const worker = desk.workerId ? workersById.get(desk.workerId) : null;
      seat.workerId = worker ? worker.id : null;
      seat.group.userData.workerId = seat.workerId;

      // Resolve the pose the figure should render. The adapter's pose is the
      // baseline; we layer on sleep (running but quiet), celebration (just
      // completed) and frustration (error/failure) for richer animation.
      let pose = worker ? worker.pose : 'idle';
      const nowMs = (typeof performance !== 'undefined' ? performance.now() : Date.now());
      if (worker) {
        if (shouldSleepWhileRunning(worker, nowMs)) pose = 'sleep';
        if (worker.status === 'completed') {
          if (!seat.celebrateUntil) seat.celebrateUntil = nowMs + 2200;
          if (nowMs < seat.celebrateUntil) pose = 'celebrate';
        } else {
          seat.celebrateUntil = 0;
        }
        if ((worker.status === 'failed' || worker.status === 'error' || worker.status === 'timeout') && pose !== 'celebrate') {
          pose = 'frustrated';
        }
      }
      seat.pose = pose;
      // The cubicle's accent strip lifts while its subagent is actually at
      // work -- subtle on purpose: the pods and figures stay the focus.
      if (seat.cubicle) {
        setCubicleActive(seat.cubicle, !!worker && worker.status === 'running'
          && (pose === 'work' || pose === 'tool' || pose === 'think'));
      }

      // Projects desks are anonymous until someone sits at them; Business
      // desks are named by the roster before anyone does. The floor sign
      // already carries the department's name, though, so an empty seat's
      // nameplate would only repeat it -- the nameplate is worth its own
      // black bar exactly when there's a real worker to say something the
      // floor doesn't: what it's doing, or what it finished with.
      const label = worker ? worker.label : (desk.seatLabel || 'Empty desk');
      const status = worker ? worker.status : '';
      if (label !== seat.label || status !== seat.status) {
        seat.label = label;
        seat.status = status;
        drawNameplate(seat.plate, palette, label, status);
      }
      seat.plate.visible = shouldShowNameplate(seat);

      // Choose the mood icon and, when it changes, show the bubble briefly.
      let mood = '';
      if (worker) {
        if (pose === 'sleep') mood = 'sleep';
        else if (pose === 'celebrate') mood = 'done';
        else if (pose === 'frustrated') mood = 'error';
        else if (worker.pose === 'tool') mood = 'tool';
        else mood = 'work';
      }
      updateSeatMood(seat, mood, nowMs);

      // Screens are canvas uploads; only repaint when the text changed.
      const toolKey = worker
        ? `${worker.status}|${worker.tool ? worker.tool.name + worker.tool.preview : ''}|${worker.summary}|${pose}`
        : 'empty';
      if (toolKey !== seat.toolKey) {
        seat.toolKey = toolKey;
        if (worker && worker.status === 'running' && (pose === 'work' || pose === 'tool' || pose === 'sleep')) {
          drawActiveScreen(seat.screen, palette, nowMs / 1000, seat.screenSeed);
        } else {
          drawScreen(seat.screen, palette, screenLines(worker));
        }
      }
    });

    Array.from(seats.keys()).forEach(id => { if (!liveDesks.has(id)) removeSeat(id); });
    Array.from(pods.keys()).forEach(c => { if (!liveClusters.has(c)) removePod(c); });

    // An outline marches only where work is actually happening: a pod whose
    // subagents have all finished goes still, which is what makes the moving
    // ones mean something.
    const liveClustersWithWork = new Set();
    (state.workers || []).forEach(worker => {
      if (worker.status !== 'running') return;
      const desk = (state.desks || []).find(d => d.workerId === worker.id);
      if (desk) liveClustersWithWork.add(desk.cluster);
    });
    pods.forEach((record, cluster) => {
      record.active = liveClustersWithWork.has(cluster);
      // The two edge rails carry the same activity state as the pod they feed.
      const bridge = walkways.get(cluster);
      if (bridge) setBridgeActive(bridge, record.active);
    });

    const conductorStatus = state.conductor ? state.conductor.status : 'idle';
    conductor.userData.status = conductorStatus;

    frameOffice(layout.center, layout.radius);
  }

  // ---- outlet transition --------------------------------------------------
  // When Projects <-> Business switches, fade the outlet-specific furniture
  // in/out while leaving the shared ground/conductor visible. This keeps the
  // scene from flashing to the webapp background colour behind the canvas.
  const OUTLET_FADE_MS = 1200;
  let outletTransition = {
    active: false,
    startK: 1,
    endK: 1,
    startMs: 0,
  };

  function currentContentOpacity() {
    if (!outletTransition.active) return 1;
    const raw = (performance.now() - outletTransition.startMs) / OUTLET_FADE_MS;
    const t = Math.min(1, Math.max(0, raw));
    const ease = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    return outletTransition.startK + (outletTransition.endK - outletTransition.startK) * ease;
  }

  function snapshotContentOpacity() {
    office.traverse(obj => {
      if (!obj.material) return;
      const materials = Array.isArray(obj.material) ? obj.material : [obj.material];
      const clones = materials.map(m => {
        if (m.userData.baseOpacity !== undefined) return m;
        const clone = m.clone();
        clone.userData.baseOpacity = m.opacity;
        clone.userData.baseTransparent = m.transparent;
        clone.userData.originalMaterial = m;
        return clone;
      });
      obj.material = Array.isArray(obj.material) ? clones : clones[0];
    });
  }

  function applyContentOpacity(k) {
    const fullOpaque = k >= 0.998;
    const fullTransparent = k <= 0.002;
    office.traverse(obj => {
      if (!obj.material) return;
      const materials = Array.isArray(obj.material) ? obj.material : [obj.material];
      materials.forEach(m => {
        if (m.userData.baseOpacity === undefined) {
          m.userData.baseOpacity = m.opacity;
          m.userData.baseTransparent = m.transparent;
        }
        const base = m.userData.baseOpacity;
        if (fullOpaque) {
          m.opacity = base;
          if (m.userData.baseTransparent !== undefined) m.transparent = m.userData.baseTransparent;
        } else if (fullTransparent) {
          m.opacity = 0;
          m.transparent = true;
        } else {
          m.transparent = true;
          m.opacity = base * k;
        }
      });
    });
  }

  function restoreContentOpacity() {
    office.traverse(obj => {
      if (!obj.material) return;
      const materials = Array.isArray(obj.material) ? obj.material : [obj.material];
      materials.forEach(m => {
        if (m.userData.baseOpacity !== undefined) {
          m.opacity = m.userData.baseOpacity;
          m.transparent = m.userData.baseTransparent;
        }
      });
    });
  }

  function setOutletTransition(fadingOut) {
    snapshotContentOpacity();
    const now = performance.now();
    // If a fade is already running, pick up from the current visual position
    // rather than snapping to 0/1, but always head toward the new target.
    const currentK = outletTransition.active
      ? Math.min(1, Math.max(0, (now - outletTransition.startMs) / OUTLET_FADE_MS))
      : (fadingOut ? 1 : 0);
    outletTransition.startMs = now;
    outletTransition.startK = currentK;
    outletTransition.endK = fadingOut ? 0 : 1;
    outletTransition.active = true;
    applyContentOpacity(currentK);
  }

  function advanceOutletTransition(now) {
    if (!outletTransition.active) return;
    const raw = (now - outletTransition.startMs) / OUTLET_FADE_MS;
    const t = Math.min(1, Math.max(0, raw));
    // ease-in-out for a smoother, more consistent feel
    const ease = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    const k = outletTransition.startK + (outletTransition.endK - outletTransition.startK) * ease;
    applyContentOpacity(k);
    if (t >= 1) {
      outletTransition.active = false;
      restoreContentOpacity();
    }
  }

  /**
   * Zoom so the whole floor fits. Only ever widens in small steps and never
   * on every frame — a camera that rescales continuously as subagents come
   * and go is unreadable.
   */
  function frameOffice(center, radius) {
    const wanted = Math.max(CONDUCTOR_RADIUS * 2, radius) * FRAME_MARGIN;
    const next = center || { x: 0, z: 0 };
    const moved = Math.hypot(next.x - framedCenter.x, next.z - framedCenter.z);
    // Re-framing on every spawn would make the whole office drift under the
    // user's cursor, so only react once the change is worth a camera move.
    if (Math.abs(wanted - framedRadius) < 2 && moved < 2) return;
    framedRadius = wanted;
    ensureGroundCovers(framedRadius);
    framedCenter = { x: next.x, z: next.z };
    fitShadowToOffice();
    overview.x = framedCenter.x;
    overview.z = framedCenter.z;
    overview.zoom = zoomForRadius(viewWidth || lastWidth, lastHeight, framedRadius);
    // A camera the user has taken control of — focused on a desk, or zoomed by
    // hand — must not be yanked back because another subagent spawned.
    if (focusedId || manualZoom) return;
    if (view.zoom === 1 && view.x === 0 && view.z === 0) applyView(overview);
    else startTween(overview);
  }

  function zoomForRadius(width, height, radius) {
    const aspect = height > 0 ? width / height : 1;
    const halfWidth = FRUSTUM_HALF_HEIGHT * aspect;
    if (!(radius > 0)) return 1;
    // A fit calculated only from the world frustum makes the same office look
    // needlessly tiny on a large monitor and overfills a compact laptop view.
    // Let the available CSS-pixel viewport make a small, bounded adjustment
    // after the geometric fit, so every device gets the same visual density.
    const shortEdge = Math.max(1, Math.min(width, height));
    const viewportCoverage = Math.min(1.1, Math.max(0.92, shortEdge / 840));
    // Fit the floor in both axes: its full radius across, its foreshortened
    // radius (plus standing headroom) down. Whichever is tighter wins.
    return viewportCoverage * Math.min(
      2.2,
      halfWidth / radius,
      FRUSTUM_HALF_HEIGHT / (radius * ISO_VERTICAL_SCALE + FRAME_HEADROOM),
    );
  }

  // ---- camera motion ----------------------------------------------------

  // Slow out of the start, slow into the end: a linear camera move reads as a
  // jump cut at both ends.
  function easeInOutCubic(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }

  function applyView(next) {
    view.x = next.x;
    view.z = next.z;
    view.zoom = next.zoom;
    cameraTarget.set(view.x, 0, view.z);
    applyCamera(lastWidth, lastHeight);
    syncLod();
  }

  function startTween(to) {
    tween = {
      t0: (typeof performance !== 'undefined' ? performance.now() : Date.now()),
      dur: TWEEN_MS,
      from: { x: view.x, z: view.z, zoom: view.zoom },
      to: { x: to.x, z: to.z, zoom: to.zoom },
    };
  }

  function advanceTween(now) {
    if (!tween) return;
    const t = Math.min(1, (now - tween.t0) / tween.dur);
    const k = easeInOutCubic(t);
    applyView({
      x: tween.from.x + (tween.to.x - tween.from.x) * k,
      z: tween.from.z + (tween.to.z - tween.from.z) * k,
      zoom: tween.from.zoom + (tween.to.zoom - tween.from.zoom) * k,
    });
    if (t >= 1) tween = null;
  }

  /**
   * How far to slide a focused desk left, in world units, so the detail panel
   * does not sit on top of the thing it is describing.
   */
  function panelShift(zoom) {
    const px = typeof config.panelInset === 'function' ? (config.panelInset() || 0) : 0;
    if (!px || !lastHeight || !zoom) return 0;
    const pixelsPerUnit = (zoom * lastHeight) / (2 * FRUSTUM_HALF_HEIGHT);
    return pixelsPerUnit > 0 ? (px / 2) / pixelsPerUnit : 0;
  }

  /** Fly to a worker's desk. Unknown ids are ignored rather than guessed at. */
  function focusOnWorker(workerId) {
    const seat = Array.from(seats.values()).find(s => s.workerId === workerId);
    if (!seat) return false;
    focusedId = workerId;
    manualZoom = false;
    syncNameplateVisibility();
    const shift = panelShift(FOCUS_ZOOM);
    startTween({
      x: seat.group.position.x + SCREEN_RIGHT.x * shift,
      z: seat.group.position.z + SCREEN_RIGHT.z * shift,
      zoom: FOCUS_ZOOM,
    });
    return true;
  }

  /**
   * Frame one pod — a tap on the floor of a section, not on a worker. Zooms in
   * far enough to read the desks without leaving the pod's own floor.
   */
  function focusOnPod(cluster) {
    let pos;
    let span;
    if (cluster === '__conductor__' && conductor) {
      pos = conductor.position;
      span = CONDUCTOR_SLAB;
    } else {
      const rec = pods.get(cluster);
      if (!rec) return false;
      pos = rec.group.position;
      span = Math.max(rec.width, rec.depth) + POD_SLAB_PADDING;
    }
    focusedId = null;
    manualZoom = true;
    syncNameplateVisibility();
    const zoom = clampZoom(zoomForRadius(viewWidth || lastWidth, lastHeight, span * 0.62));
    startTween({ x: pos.x, z: pos.z, zoom });
    return true;
  }

  /** Back to the whole floor. */
  function resetView(zoomMultiplier = 1) {
    focusedId = null;
    manualZoom = false;
    syncNameplateVisibility();
    startTween(Object.assign({}, overview, { zoom: overview.zoom * zoomMultiplier }));
  }

  function isFocused() {
    return !!focusedId;
  }

  /**
   * Zoom-driven level of detail. Nameplates are the first thing to collapse
   * into noise on a dense floor, so they are what a zoomed-out view drops;
   * the figures are the point of the picture and always stay.
   */
  function syncLod() {
    const next = view.zoom >= LOD_NEAR_ZOOM ? 'near' : 'far';
    if (next === lod) return;
    lod = next;
    syncNameplateVisibility();
  }

  /**
   * Current camera state, plus the pose each figure is actually rendering.
   *
   * The rendered pose can differ from the adapter's — an idle behaviour plays
   * over plain work — and it is otherwise invisible from outside the scene,
   * which makes it impossible to check without resorting to pixel diffing.
   */
  function getView() {
    const poses = {};
    seats.forEach(seat => {
      if (seat.workerId) poses[seat.workerId] = seat.person.userData.pose;
    });
    return {
      x: view.x, z: view.z, zoom: view.zoom, lod, focusedId,
      tweening: !!tween, poses,
    };
  }

  const _podScreenV = new THREE.Vector3();

  /**
   * Where a pod floats on screen right now, in CSS pixels relative to the
   * canvas's own top-left corner -- so a caller outside this module (the
   * per-department floating stat cards in index.js) can position a plain DOM
   * element over a pod without knowing anything about the camera, zoom, or
   * projection math. Anchored a few world units above the floor rather than
   * on it, so the card reads as floating above the pod rather than sitting
   * on the slab. Returns null for a pod that does not exist (yet), or that
   * has projected behind the camera.
   */
  function podScreenRect(cluster) {
    const pod = cluster === '__conductor__' && conductor
      ? { group: conductor }
      : pods.get(cluster === '__subagents__' ? '__conductor__' : cluster);
    if (!pod || !canvas) return null;
    camera.updateMatrixWorld();
    _podScreenV.set(pod.group.position.x, 8, pod.group.position.z);
    _podScreenV.project(camera);
    if (_podScreenV.z > 1) return null;
    // Relative to the stage, not the canvas: the canvas can be wider than the
    // stage it is centred in (see resize()).
    const rect = canvas.getBoundingClientRect();
    const stage = canvas.parentElement ? canvas.parentElement.getBoundingClientRect() : rect;
    return {
      x: (_podScreenV.x + 1) / 2 * rect.width + (rect.left - stage.left),
      y: (1 - _podScreenV.y) / 2 * rect.height + (rect.top - stage.top),
    };
  }

  function applyCamera(width, height) {
    const aspect = height > 0 ? width / height : 1;
    const halfWidth = FRUSTUM_HALF_HEIGHT * aspect;
    camera.left = -halfWidth;
    camera.right = halfWidth;
    camera.top = FRUSTUM_HALF_HEIGHT;
    camera.bottom = -FRUSTUM_HALF_HEIGHT;
    camera.zoom = view.zoom > 0 ? view.zoom : 1;
    camera.position.copy(cameraTarget).addScaledVector(ISO_DIRECTION, CAMERA_DISTANCE);
    camera.lookAt(cameraTarget);
    camera.updateProjectionMatrix();
  }

  /** Repaint everything for the app's current theme. */
  function applyTheme() {
    const next = PALETTES[prefersDark() ? 'dark' : 'light'];
    if (next === palette) return;
    palette = next;
    groundMaterial.color.set(palette.ground);
    if (grid.material && grid.material.color) grid.material.color.set(palette.grid);
    ambient.color.set(palette.hemiSky);
    ambient.groundColor.set(palette.hemiGround);
    rimLight.color.set(palette.rim);
    spotLight.color.set(palette.hemiSky);
    // Materials are shared and keyed by colour, so a theme change means new
    // ones. Rebuilding the office group is cheaper and more honest than
    // hunting down every mesh that used the old palette.
    rebuild();
  }

  function clearOffice() {
    seats.forEach(seat => disposeTree(seat.group));
    pods.forEach(pod => disposeTree(pod.group));
    walkways.forEach(walk => disposeTree(walk));
    walkways = new Map();
    if (conductor) disposeTree(conductor);
    scene.remove(office);
    scene.remove(backdrop);
    seats = new Map();
    pods = new Map();
    conductor = null;
    office = new THREE.Group();
    backdrop = new THREE.Group();
    scene.add(office);
    scene.add(backdrop);
  }

  function rebuild() {
    const state = lastState;
    clearOffice();
    disposeSharedCaches();
    framedRadius = 0;
    if (state) syncOffice(state);
    else ensureConductor();
  }

  // ---- picking ----------------------------------------------------------
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();

  function objectAt(clientX, clientY, key) {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
    camera.updateMatrixWorld();
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects(office.children.concat(backdrop.children), true);
    for (const hit of hits) {
      let node = hit.object;
      while (node) {
        if (node.userData && node.userData[key] != null) return node.userData[key];
        node = node.parent;
      }
    }
    return null;
  }
  const workerIdAt = (x, y) => objectAt(x, y, 'workerId');
  const podClusterAt = (x, y) => objectAt(x, y, 'podCluster');

  /** Where a screen point lands on the ground plane, in world units. */
  const _groundV = new THREE.Vector3();
  const _groundDir = new THREE.Vector3();
  function groundPoint(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const ndcX = ((clientX - rect.left) / rect.width) * 2 - 1;
    const ndcY = -((clientY - rect.top) / rect.height) * 2 + 1;
    // applyCamera moves the camera without refreshing its world matrix, and
    // unproject reads it directly.
    camera.updateMatrixWorld();
    _groundV.set(ndcX, ndcY, -1).unproject(camera);
    camera.getWorldDirection(_groundDir);
    const t = Math.abs(_groundDir.y) > 1e-6 ? -_groundV.y / _groundDir.y : 0;
    return { x: _groundV.x + _groundDir.x * t, z: _groundV.z + _groundDir.z * t };
  }

  function clampZoom(z) {
    return Math.min(overview.zoom * ZOOM_MAX, Math.max(overview.zoom * ZOOM_MIN, z));
  }

  /** Zoom to `nextZoom` while keeping the world point under (clientX, clientY) fixed. */
  function zoomAbout(clientX, clientY, nextZoom) {
    const before = groundPoint(clientX, clientY);
    applyView({ x: view.x, z: view.z, zoom: clampZoom(nextZoom) });
    const after = groundPoint(clientX, clientY);
    applyView({ x: view.x - (after.x - before.x), z: view.z - (after.z - before.z), zoom: view.zoom });
  }

  function takeManualControl() {
    tween = null;
    focusedId = null;
    manualZoom = true;
    syncNameplateVisibility();
  }

  // ---- gestures: mouse drag + wheel, one-finger pan, two-finger pinch ------
  // One code path for mouse and touch via Pointer Events. A press that never
  // travels far and lifts quickly is a tap (pick a worker, or frame a pod, or
  // pull back out); anything else pans, and a second finger pinches.
  const TAP_SLOP = 6;
  const TAP_MS = 500;
  const pointers = new Map();
  let gesture = null;
  let downAt = 0;
  let downClient = null;
  let travelled = 0;
  let pinchDist = 0;
  let pinchMid = null;

  function onPointerDown(event) {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    try { canvas.setPointerCapture(event.pointerId); } catch (_err) { /* not supported */ }
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.size === 1) {
      downAt = (typeof performance !== 'undefined' ? performance.now() : Date.now());
      downClient = { x: event.clientX, y: event.clientY };
      travelled = 0;
      gesture = null;
      if (event.pointerType === 'mouse') canvas.style.cursor = 'grabbing';
    } else if (pointers.size === 2) {
      const p = Array.from(pointers.values());
      pinchDist = Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y);
      pinchMid = { x: (p[0].x + p[1].x) / 2, y: (p[0].y + p[1].y) / 2 };
      gesture = 'pinch';
      takeManualControl();
    }
  }

  function onPointerMoveGesture(event) {
    const prev = pointers.get(event.pointerId);
    if (!prev) {
      // hover with no button: just the cursor hint
      if (event.pointerType === 'mouse') {
        canvas.style.cursor = workerIdAt(event.clientX, event.clientY)
          || podClusterAt(event.clientX, event.clientY) ? 'pointer' : 'grab';
      }
      return;
    }
    const cur = { x: event.clientX, y: event.clientY };

    if (pointers.size >= 2 && gesture === 'pinch') {
      pointers.set(event.pointerId, cur);
      const p = Array.from(pointers.values());
      const dist = Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y);
      const mid = { x: (p[0].x + p[1].x) / 2, y: (p[0].y + p[1].y) / 2 };
      if (pinchDist > 0) {
        zoomAbout(mid.x, mid.y, view.zoom * (dist / pinchDist));
      }
      if (pinchMid) {
        const a = groundPoint(pinchMid.x, pinchMid.y);
        const b = groundPoint(mid.x, mid.y);
        applyView({ x: view.x - (b.x - a.x), z: view.z - (b.z - a.z), zoom: view.zoom });
      }
      pinchDist = dist;
      pinchMid = mid;
      return;
    }

    travelled += Math.hypot(cur.x - prev.x, cur.y - prev.y);
    pointers.set(event.pointerId, cur);
    if (gesture !== 'pan' && travelled > TAP_SLOP) {
      gesture = 'pan';
      takeManualControl();
    }
    if (gesture === 'pan') {
      const a = groundPoint(prev.x, prev.y);
      const b = groundPoint(cur.x, cur.y);
      applyView({ x: view.x - (b.x - a.x), z: view.z - (b.z - a.z), zoom: view.zoom });
    }
  }

  function endPointer(event) {
    try { canvas.releasePointerCapture(event.pointerId); } catch (_err) { /* fine */ }
    const wasSingle = pointers.size === 1;
    pointers.delete(event.pointerId);

    if (pointers.size === 0) {
      if (event.pointerType === 'mouse') canvas.style.cursor = 'grab';
      const dt = (typeof performance !== 'undefined' ? performance.now() : Date.now()) - downAt;
      if (wasSingle && gesture == null && travelled <= TAP_SLOP && dt <= TAP_MS && downClient) {
        handleTap(downClient.x, downClient.y);
      }
      gesture = null;
      pinchMid = null;
    } else if (pointers.size === 1) {
      // Second finger lifted mid-pinch: keep panning with the one that's left.
      gesture = null;
      pinchMid = null;
    }
  }

  function handleTap(clientX, clientY) {
    const id = workerIdAt(clientX, clientY);
    if (id) {
      focusOnWorker(id);
      if (typeof config.onSelect === 'function') config.onSelect(id);
      return;
    }
    const cluster = podClusterAt(clientX, clientY);
    if (cluster) {
      focusOnPod(cluster);
      if (typeof config.onSelect === 'function') config.onSelect(null);
      return;
    }
    // Empty ground is the way back out — same gesture as dismissing the panel.
    if (focusedId || manualZoom) resetView();
    if (typeof config.onSelect === 'function') config.onSelect(null);
  }

  canvas.addEventListener('pointerdown', onPointerDown);
  canvas.addEventListener('pointermove', onPointerMoveGesture);
  canvas.addEventListener('pointerup', endPointer);
  canvas.addEventListener('pointercancel', endPointer);

  function onWheel(event) {
    event.preventDefault();
    takeManualControl();
    zoomAbout(event.clientX, event.clientY, view.zoom * Math.exp(-event.deltaY * 0.0015));
  }
  canvas.addEventListener('wheel', onWheel, { passive: false });

  function onKeyDown(event) {
    if (event.key !== 'Escape') return;
    if (!focusedId && !manualZoom) return;
    resetView();
    if (typeof config.onSelect === 'function') config.onSelect(null);
  }
  // Keyed to the canvas' owner document so the shortcut works wherever focus
  // sits inside the panel, and is removed with the scene.
  document.addEventListener('keydown', onKeyDown);

  // ---- sizing -----------------------------------------------------------
  let lastWidth = 0;
  let lastHeight = 0;
  // The visible part of the canvas. The canvas is laid out as wide as the
  // stage can get when a side panel collapses and centred in it (the overflow
  // is clipped), so a panel slide changes only this, never the drawing buffer:
  // reallocating the buffer and bloom targets was the slide's whole cost.
  let viewWidth = 0;

  /**
   * Match the drawing buffer to the canvas' laid-out size. Called on every
   * frame as well as from the panel's ResizeObserver, because a panel that
   * was hidden while the window resized reports its real size only once it
   * is displayed again.
   */
  function resize() {
    const width = Math.max(1, canvas.clientWidth || 0);
    const height = Math.max(1, canvas.clientHeight || 0);
    const stageWidth = canvas.parentElement ? canvas.parentElement.clientWidth : width;
    const visible = Math.max(1, Math.min(width, stageWidth || width));
    const bufferChanged = width !== lastWidth || height !== lastHeight;
    if (!bufferChanged && visible === viewWidth) return false;
    const previousOverviewZoom = overview.zoom;
    viewWidth = visible;
    if (bufferChanged) {
      lastWidth = width;
      lastHeight = height;
      // updateStyle=false: the canvas is sized by CSS, and letting three.js
      // write inline width/height styles would fight the flex layout.
      renderer.setSize(width, height, false);
      composer.setSize(width, height);
    }
    // The framed zoom fits the floor into what is visible. A camera the user
    // is driving keeps its own zoom.
    overview.zoom = zoomForRadius(viewWidth, height, framedRadius);
    const following = !focusedId && !manualZoom && !tween;
    // A sidebar slide changes only the visible width. When that leaves the
    // picture as it was (same buffer, and the framed zoom is height-limited
    // or the camera is the user's), there is nothing to redraw.
    if (!bufferChanged && (!following || overview.zoom === previousOverviewZoom)) return false;
    if (following) applyView(overview);
    else applyCamera(width, height);
    return true;
  }
  resize();

  /**
   * Resize and draw one still frame while the loop is stopped. A side-panel
   * slide pauses the loop but commits the new layout up front; without this
   * the stale drawing buffer is stretched over the new canvas box for the
   * whole slide (resizing alone would blank it until the next render).
   */
  function renderNow() {
    if (resize()) composer.render();
  }

  // ---- render loop ------------------------------------------------------
  let rafId = 0;
  let running = false;
  let lastFrameAt = 0;

  function frame(now) {
    if (!running) return;
    rafId = window.requestAnimationFrame(frame);
    resize();

    const t = (now || 0) / 1000;
    const dt = lastFrameAt ? Math.min(0.1, t - lastFrameAt) : 0.016;
    lastFrameAt = t;

    if (tween) advanceTween(now || 0);
    advanceOutletTransition(now || 0);
    const dtMs = dt * 1000;

    // The adapter owns no timer, so its time-dependent poses (a tool call
    // settling back to plain work) only advance because the scene asks.
    if (typeof config.onTick === 'function') config.onTick();

    walkways.forEach((bridge, cluster) => {
      advanceDeliveryGlow(pods.get(cluster), advanceBridgeFade(bridge, dtMs, t), dtMs);
    });
    seats.forEach(seat => {
      // A subagent walks to its desk before it starts; only once seated does
      // its posture describe what Hermes says it is doing.
      if (seat.arrival && !seat.arrival.done) {
        const prevX = seat.person.position.x;
        const prevZ = seat.person.position.z;
        advanceArrival(seat.arrival, dtMs);
        seat.person.position.x = seat.arrival.lateral;
        seat.person.position.z = 1.9 + seat.arrival.offset;
        const dX = seat.person.position.x - prevX;
        const dZ = seat.person.position.z - prevZ;
        if (Math.hypot(dX, dZ) > 1e-4) seat.person.rotation.y = Math.atan2(dX, dZ);
        poseWalking(seat.person, seat.arrival.phase, arrivalSettle(seat.arrival));
        if (seat.arrival.done) {
          hideLegs(seat.person);
          seat.person.position.set(0, 0, 1.9);
          seat.person.rotation.y = Math.PI;
        }
        return;
      }
      poseWorker(seat.person, seat.pose, t, dt);
    });

    // Keep active screens shimmering and chat bubbles popping.
    seats.forEach(seat => {
      if (seat.bubble && seat.bubble.visible) {
        const elapsed = Math.min(1, ((t * 1000) - (seat.moodUntil - 3200)) / 250);
        const k = easeOutCubic(elapsed);
        // Bigger at close range so an action reads immediately, then clamped
        // at overview scale to avoid a bubble becoming wider than its pod.
        const bubbleScale = lod === 'far' ? 1.8 : 2.5;
        seat.bubble.scale.set(bubbleScale * k, bubbleScale * 0.76 * k, 1);
        seat.bubble.position.y = 3.12 + Math.sin(t * 3 + seat.screenSeed) * 0.08;
      }
      if (seat.workerId && seat.pose && (seat.pose === 'work' || seat.pose === 'tool' || seat.pose === 'sleep')) {
        drawActiveScreen(seat.screen, palette, t, seat.screenSeed);
      }
    });

    if (conductor) {
      const person = conductor.userData.person;
      const wanderer = conductor.userData.wanderer;
      const orchestrating = conductor.userData.status === 'orchestrating';
      if (orchestrating) {
        // Back to the middle of the plinth, then to work. It walks there
        // rather than snapping, so the change of state is something you see
        // happen.
        const seated = wanderer.moveTo(0, 0, dtMs);
        person.position.set(wanderer.state.x, 0.6, wanderer.state.z);
        if (seated) {
          poseWorker(person, 'orchestrate', t, dt, { standing: true });
        } else {
          person.rotation.y = wanderer.state.heading;
          poseWalking(person, wanderer.state.phase, 1);
        }
      } else {
        wanderer.update(dtMs);
        person.position.set(wanderer.state.x, 0.6, wanderer.state.z);
        if (wanderer.state.moving) {
          person.rotation.y = wanderer.state.heading;
          poseWalking(person, wanderer.state.phase, 1);
        } else {
          poseWorker(person, 'idle', t, dt, { standing: true });
        }
      }
    }

    composer.render();
  }

  function start() {
    if (running) return;
    // A hidden tab gets no rAF callbacks anyway; not starting keeps the
    // "running" flag honest so visibilitychange can restart cleanly.
    running = true;
    lastFrameAt = 0;
    rafId = window.requestAnimationFrame(frame);
  }

  function stop() {
    running = false;
    if (rafId) window.cancelAnimationFrame(rafId);
    rafId = 0;
  }

  function isRunning() {
    return running;
  }

  function dispose() {
    stop();
    canvas.removeEventListener('pointerdown', onPointerDown);
    canvas.removeEventListener('pointermove', onPointerMoveGesture);
    canvas.removeEventListener('pointerup', endPointer);
    canvas.removeEventListener('pointercancel', endPointer);
    canvas.removeEventListener('wheel', onWheel);
    document.removeEventListener('keydown', onKeyDown);
    clearOffice();
    disposeSharedCaches();
    scene.clear();
    ownedGeometries.forEach(g => { try { g.dispose(); } catch (_err) { /* already gone */ } });
    ownedMaterials.forEach(m => { try { m.dispose(); } catch (_err) { /* already gone */ } });
    ownedGeometries.length = 0;
    ownedMaterials.length = 0;
    // EffectComposer.dispose() only releases its own read/write render
    // targets and copy pass -- each added pass owns further GPU resources
    // (bloom's blur render targets and materials, the output pass' material)
    // and is disposed individually here.
    composer.passes.forEach(pass => {
      if (typeof pass.dispose === 'function') { try { pass.dispose(); } catch (_err) { /* already gone */ } }
    });
    try { composer.dispose(); } catch (_err) { /* already gone */ }
    // Releases the WebGL context itself. Without this, switching in and out
    // of the panel eventually exhausts the browser's context limit and every
    // later mount renders nothing.
    try { renderer.dispose(); } catch (_err) { /* context already lost */ }
    try { renderer.forceContextLoss(); } catch (_err) { /* not supported everywhere */ }
  }

  ensureConductor();

  return {
    start, stop, resize, renderNow, dispose, isRunning, applyTheme, syncOffice,
    workerIdAt, focusOnWorker, focusOnPod, resetView, isFocused, getView,
    podScreenRect, scene, setOutletTransition,
  };
}
