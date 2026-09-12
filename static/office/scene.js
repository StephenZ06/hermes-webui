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
  makePod, makeDesk, makeChair, makePerson, makeNameplate, makeFloorTitle,
  makeDeptIcon, makePlant, makeFloorTiles, makePodGlow, makeWhiteboard,
  makeWalkway, makeSlabOutline, makeConnector, marchOutline,
  setOutlineActive, advanceDashFade, isDashActive, drawNameplate, drawScreen,
  poseWorker, poseWalking, hideLegs, disposeTree, disposeSharedCaches,
} from './builders.js';
import {
  createWanderer, createArrival, advanceArrival, arrivalSettle,
} from './motion.js';

// Half-height of the orthographic frustum at zoom 1, in world units. The
// office is authored against this so a desk keeps the same on-screen size
// whatever the panel's aspect ratio is.
const FRUSTUM_HALF_HEIGHT = 42;
// Locked isometric view direction. Slightly taller than a true 2:1 iso so
// floor markings stay readable at overview zoom.
const ISO_DIRECTION = new THREE.Vector3(1, 0.92, 1).normalize();
const CAMERA_DISTANCE = 220;
const GROUND_SIZE = 400;
const KEY_LIGHT_INTENSITY = 1.6;
const FILL_LIGHT_INTENSITY = 0.55;
// A low, cool light from behind the key light, so a pod's far side isn't
// pure black — cheap depth cue, no shadow cost (this one never casts).
const RIM_LIGHT_INTENSITY = 0.45;
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
// World units per second the dashes travel. Slow enough to read as "in
// progress" rather than as an alarm.
const OUTLINE_SPEED = 2.4;
// The bridge's charge runs faster than a platform's edge: it is travelling
// somewhere rather than circling, and matching speeds made the two read as one
// continuous line where they meet.
const CONNECTOR_SPEED_RATIO = 1.8;
// How far behind its chair a subagent starts when it spawns. Far enough to
// read as arriving, close enough to be seated before its first tool call.
const ARRIVAL_DISTANCE = 9;
// How far to one side the walk-in starts — out in the aisle between desk
// columns, so the figure clears the monitor and chair of the row behind it
// instead of walking through them.
const ARRIVAL_LATERAL = 5;

// Palettes are WebGL material colours rather than CSS custom properties:
// they are handed to THREE.Color, not to a stylesheet. The panel's own
// chrome still comes from the app's theme tokens as usual.
const PALETTES = {
  light: {
    ground: '#f2efe8', grid: '#d8d3c8',
    podTop: '#ffffff', podSide: '#e4dfd4',
    deskTop: '#c9a227', deskLeg: '#8b8b93',
    chair: '#5f6672',
    shirt: '#6b8fb5', skin: '#e8b98e', hair: '#3b2b1d', trousers: '#3e4048',
    screenBezel: '#2c2c34', screenBg: '#14141c',
    screenText: '#8fb9a8', screenTextBright: '#d8f0e4',
    plateBg: 'rgba(255,255,255,0.92)', plateText: '#151414', plateAccent: '#1e9070',
    conductor: '#2b3245',
    floorTitle: '#8d8d95', pot: '#b07a52', plant: '#5f8a5f', walkway: '#eae5da',
    outlineIdle: '#a8a294', outlineActive: '#1e9070', connector: '#9a9490',
    board: '#fbfaf6', hemiSky: '#f4f1ea', hemiGround: '#c9c2ae', rim: '#cfe0f7',
  },
  dark: {
    ground: '#1b1b2b', grid: '#2b2b40',
    podTop: '#24243a', podSide: '#1a1a2a',
    deskTop: '#8a6d1f', deskLeg: '#4a4a58',
    chair: '#3a3f4b',
    shirt: '#4f7ca8', skin: '#c68b59', hair: '#1a1a20', trousers: '#2b2d36',
    screenBezel: '#0e0e14', screenBg: '#0a0a12',
    screenText: '#5adeb7', screenTextBright: '#b9f5e2',
    plateBg: 'rgba(20,20,37,0.92)', plateText: '#f2f2f7', plateAccent: '#5adeb7',
    conductor: '#8fd3f4',
    floorTitle: '#6f6f86', pot: '#7a5236', plant: '#3f5f45', walkway: '#202032',
    outlineIdle: '#575775', outlineActive: '#5adeb7', connector: '#41415e',
    board: '#2a2a38', hemiSky: '#39456b', hemiGround: '#0e0e18', rim: '#3f5f8f',
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
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
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
  keyLight.shadow.mapSize.set(1024, 1024);
  keyLight.shadow.camera.near = 1;
  keyLight.shadow.camera.far = 400;
  keyLight.shadow.camera.left = -140;
  keyLight.shadow.camera.right = 140;
  keyLight.shadow.camera.top = 140;
  keyLight.shadow.camera.bottom = -140;
  scene.add(keyLight);

  // A low rim light from behind/opposite the key light so a pod's far side
  // isn't flat black. Cheap: no shadow map, no extra render pass.
  const rimLight = new THREE.DirectionalLight(palette.rim, RIM_LIGHT_INTENSITY);
  rimLight.position.set(-70, 50, -60);
  scene.add(rimLight);

  // ---- post-processing ---------------------------------------------------
  // One bloom pass over the whole render. Nothing in the ordinary palette sits
  // near the 1.0 threshold (see BLOOM_THRESHOLD above), so this only lights up
  // a working pod's own glow mesh -- no per-object "selective bloom" layer
  // trick needed.
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloomPass = new UnrealBloomPass(
    new THREE.Vector2(1, 1), BLOOM_STRENGTH, BLOOM_RADIUS, BLOOM_THRESHOLD);
  composer.addPass(bloomPass);
  composer.addPass(new OutputPass());

  // ---- ground -----------------------------------------------------------
  const groundGeometry = new THREE.PlaneGeometry(GROUND_SIZE, GROUND_SIZE);
  const groundMaterial = new THREE.MeshStandardMaterial({
    color: palette.ground, roughness: 0.95, metalness: 0.0,
  });
  ownedGeometries.push(groundGeometry);
  ownedMaterials.push(groundMaterial);
  const ground = new THREE.Mesh(groundGeometry, groundMaterial);
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);

  const grid = new THREE.GridHelper(GROUND_SIZE, 80, palette.grid, palette.grid);
  grid.position.y = 0.02;
  if (grid.material) {
    grid.material.transparent = true;
    grid.material.opacity = 0.45;
    ownedMaterials.push(grid.material);
  }
  if (grid.geometry) ownedGeometries.push(grid.geometry);
  scene.add(grid);

  // ---- office contents --------------------------------------------------
  // Everything that represents delegation state hangs off one group, so a
  // theme change or a reset can drop it wholesale and rebuild.
  let office = new THREE.Group();
  scene.add(office);

  /** cluster -> {group, width, depth} */
  let pods = new Map();
  /** cluster -> walkway slab joining that pod to the middle of the office */
  let walkways = new Map();
  /** cluster -> the line showing that pod is attached to the conductor */
  let connectors = new Map();
  /** deskId -> {group, person, plate, screen, workerId, pose, tint} */
  let seats = new Map();
  let conductor = null;
  let lastState = null;
  let framedRadius = 0;

  function ensureConductor() {
    if (conductor) return conductor;
    const group = new THREE.Group();
    // A tap on the plinth frames it, the same as a tap on any pod.
    group.userData.podCluster = '__conductor__';
    const pod = makePod(CONDUCTOR_SLAB, CONDUCTOR_SLAB, palette);
    group.add(pod);
    group.add(makeFloorTiles(CONDUCTOR_SLAB, CONDUCTOR_SLAB, palette));
    const outline = makeSlabOutline(CONDUCTOR_SLAB, CONDUCTOR_SLAB, palette);
    group.add(outline);
    group.userData.outlineLine = outline;
    // Same glow a working pod gets, driven by orchestrating status rather
    // than by liveClustersWithWork -- see the render loop.
    const glow = makePodGlow(CONDUCTOR_SLAB, CONDUCTOR_SLAB, palette.conductor);
    group.add(glow);
    group.userData.glowMaterial = glow.material;
    const person = makePerson(palette, palette.conductor);
    person.position.y = 0.6;
    group.add(person);
    // Paces its plinth between delegations. Only ever while genuinely idle:
    // a walking figure reads as activity, and the office does not imply work
    // Hermes has not reported.
    group.userData.wanderer = createWanderer({ radius: CONDUCTOR_RADIUS * 0.42 });
    // Its name is painted on the plinth, the way the Business floor names a
    // department — a floating nameplate over the one figure at the centre read
    // as a label on a person rather than on the space.
    const sign = makeFloorTitle('Conductor', CONDUCTOR_SLAB * 0.82, palette, { fit: true });
    if (sign) {
      sign.position.z = CONDUCTOR_SLAB / 2 - sign.geometry.parameters.height / 2 - 0.8;
      group.add(sign);
    }
    group.userData.person = person;
    office.add(group);
    conductor = group;
    return conductor;
  }

  function ensurePod(cluster, width, depth, label, color, icon) {
    let pod = pods.get(cluster);
    if (pod && pod.width === width && pod.depth === depth && pod.label === label
      && pod.color === color && pod.icon === icon) return pod;
    if (pod) {
      office.remove(pod.group);
      disposeTree(pod.group);
    }
    const slabWidth = width + POD_SLAB_PADDING;
    const slabDepth = depth + POD_SLAB_PADDING;
    const group = makePod(slabWidth, slabDepth, palette, color);
    // A tap on the slab (not on a worker) frames this pod.
    group.userData.podCluster = cluster;

    // A faint grid on the floor itself, under everything else -- see
    // builders.js's makeFloorTiles.
    group.add(makeFloorTiles(slabWidth, slabDepth, palette));

    // Signage, only where there is a real name to paint. The catch-all pods
    // ("Subagents", "The Floor") keep the original fixed size; the named ones
    // (departments, profiles) auto-fit larger so a short name is not dwarfed.
    const plainSign = label === 'Subagents' || label === 'The Floor';
    const title = plainSign
      ? makeFloorTitle(label, slabWidth * 0.8, palette)
      : makeFloorTitle(label, slabWidth * 0.88, palette, { fit: true });
    if (title) {
      title.position.z = plainSign
        ? slabDepth / 2 - 1.6
        : slabDepth / 2 - title.geometry.parameters.height / 2 - 0.8;
      group.add(title);
    }
    // A department's glyph floats well above the pod -- high enough that it
    // never overlaps a seated figure or the desk between them (see
    // makeDeptIcon's own comment for why this isn't part of the floor sign).
    if (icon) {
      const badge = makeDeptIcon(icon);
      badge.scale.multiplyScalar(0.7);
      badge.position.set(0, 8.5, slabDepth / 2 - 1.4);
      group.add(badge);
    }

    // Two plants on opposite corners, and a whiteboard on a third. Scenery
    // carries no state, so it can never mislead anyone about what Hermes is
    // doing.
    [[-1, -1], [1, 1]].forEach(([sx, sz]) => {
      const plant = makePlant(palette);
      plant.position.set(sx * (slabWidth / 2 - 1.1), 0.6, sz * (slabDepth / 2 - 1.1));
      group.add(plant);
    });
    const whiteboard = makeWhiteboard(palette);
    whiteboard.position.set(slabWidth / 2 - 1.1, 0, -(slabDepth / 2 - 1.1));
    group.add(whiteboard);

    const outline = makeSlabOutline(slabWidth, slabDepth, palette);
    group.add(outline);

    // A soft coloured wash, only visible while the pod is doing real work --
    // toggled in syncOffice, pulsed in the render loop. Starts invisible.
    const glow = makePodGlow(slabWidth, slabDepth, color);
    group.add(glow);

    office.add(group);
    pod = {
      group, width, depth, label, color, icon, outline, active: false,
      glowMaterial: glow.material,
    };
    pods.set(cluster, pod);
    return pod;
  }

  /**
   * The line saying a pod is attached to the conductor.
   *
   * Drawn between the same two platform edges the walkway spans, just above
   * it, so the two cues agree rather than crossing each other.
   */
  function ensureConnector(cluster, pod, span) {
    let line = connectors.get(cluster);
    // Rebuilt only when the geometry actually moves. Recreating it on every
    // sync would reset the line's live state and restart its fade, so a busy
    // run would show a bridge perpetually switching on and never lit.
    const key = span ? `${span.angle.toFixed(4)}|${span.start.toFixed(3)}|${span.end.toFixed(3)}` : '';
    if (line && line.userData.spanKey === key) return;
    if (line) { office.remove(line); disposeTree(line); connectors.delete(cluster); }
    if (!span) return;
    const from = { x: Math.sin(span.angle) * span.start, z: Math.cos(span.angle) * span.start };
    const to = { x: Math.sin(span.angle) * span.end, z: Math.cos(span.angle) * span.end };
    line = makeConnector(from.x, from.z, to.x, to.z, palette);
    line.userData.spanKey = key;
    office.add(line);
    connectors.set(cluster, line);
    // A pod that is already working when its bridge is (re)built lights up
    // with it rather than waiting for the next state change.
    const record = pods.get(cluster);
    if (record && record.active) setOutlineActive(line, true);
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
    }, CONDUCTOR_SLAB / 2);
    if (!span) {
      if (walk) { office.remove(walk); disposeTree(walk); walkways.delete(cluster); }
      return null;
    }
    if (walk) { office.remove(walk); disposeTree(walk); }
    walk = makeWalkway(span.length, palette);
    const mid = span.start + span.length / 2;
    walk.position.set(Math.sin(span.angle) * mid, 0.04, Math.cos(span.angle) * mid);
    walk.rotation.y = span.angle;
    office.add(walk);
    walkways.set(cluster, walk);
    return span;
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
    // A desk only ever appears because a subagent just spawned, so every seat
    // starts with its occupant walking in — from the aisle to one side, sides
    // alternating so a pod does not fill from one direction.
    const side = (tintIndex % 2 === 0) ? 1 : -1;
    const arrival = createArrival(ARRIVAL_DISTANCE, undefined, side * ARRIVAL_LATERAL);
    person.position.set(arrival.lateral, 0, 1.9 + arrival.offset);
    const plate = makeNameplate(palette, '');
    plate.position.set(0, 5.0, 0);
    group.add(plate);
    // Marks the whole subtree as belonging to a worker so a raycast hit on
    // any child resolves back to one id.
    group.userData.deskId = deskId;
    plate.visible = (lod === 'near');
    office.add(group);
    seat = {
      group, person, plate, screen: desk.userData.screen, arrival,
      workerId: null, pose: 'idle', label: '', status: '', toolKey: '',
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
    const line = connectors.get(cluster);
    if (line) {
      office.remove(line);
      disposeTree(line);
      connectors.delete(cluster);
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

  /**
   * Reconcile the floor to a state snapshot from the adapter.
   * Idempotent: calling it twice with the same state changes nothing.
   */
  function syncOffice(state) {
    if (!state) return;
    lastState = state;
    ensureConductor();

    const layout = computeLayout(state.desks || []);
    const workersById = new Map((state.workers || []).map(w => [w.id, w]));
    const liveClusters = new Set();
    const liveDesks = new Set();

    layout.pods.forEach(pod => {
      liveClusters.add(pod.cluster);
      // The pod holding the conductor's own direct children is "Subagents";
      // Business pods carry a department name; everything else (a nested
      // subagent's own children) has no name worth painting.
      const podLabel = pod.label
        || (pod.cluster === '__conductor__' ? 'Subagents' : '');
      const record = ensurePod(pod.cluster, pod.width, pod.depth, podLabel, pod.color || null, pod.icon || null);
      record.group.position.set(pod.x, 0, pod.z);
      const span = ensureWalkway(pod.cluster, pod);
      ensureConnector(pod.cluster, pod, span);
    });

    (state.desks || []).forEach(desk => {
      const spot = layout.seats[desk.id];
      if (!spot) return;
      liveDesks.add(desk.id);
      const seat = ensureSeat(desk.id, desk.index);
      seat.group.position.set(spot.x, 0.6, spot.z);
      seat.group.rotation.y = spot.rotationY;

      const worker = desk.workerId ? workersById.get(desk.workerId) : null;
      seat.workerId = worker ? worker.id : null;
      seat.group.userData.workerId = seat.workerId;
      seat.pose = worker ? worker.pose : 'idle';

      // Projects desks are anonymous until someone sits at them; Business
      // desks are named by the roster before anyone does, which is what makes
      // an idle departmental floor read as a company rather than a void.
      const label = worker ? worker.label : (desk.seatLabel || 'Empty desk');
      const status = worker ? worker.status : '';
      if (label !== seat.label || status !== seat.status) {
        seat.label = label;
        seat.status = status;
        drawNameplate(seat.plate, palette, label, status);
      }
      // Screens are canvas uploads; only repaint when the text changed.
      const toolKey = worker
        ? `${worker.status}|${worker.tool ? worker.tool.name + worker.tool.preview : ''}|${worker.summary}`
        : 'empty';
      if (toolKey !== seat.toolKey) {
        seat.toolKey = toolKey;
        drawScreen(seat.screen, palette, screenLines(worker));
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
      setOutlineActive(record.outline, record.active);
      const link = connectors.get(cluster);
      // The bridge carries the same charge as the pod it feeds.
      if (link) setOutlineActive(link, record.active);
    });

    const conductorStatus = state.conductor ? state.conductor.status : 'idle';
    setOutlineActive(conductor.userData.outlineLine,
      conductorStatus === 'orchestrating');
    // The plinth outline (lit above) carries the orchestrating cue now; the
    // status is still tracked because the pacing logic in the render loop
    // reads it.
    conductor.userData.status = conductorStatus;

    frameOffice(layout.center, layout.radius);
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
    framedCenter = { x: next.x, z: next.z };
    overview.x = framedCenter.x;
    overview.z = framedCenter.z;
    overview.zoom = zoomForRadius(lastWidth, lastHeight, framedRadius);
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
    // Fit the floor in both axes: its full radius across, its foreshortened
    // radius (plus standing headroom) down. Whichever is tighter wins.
    return Math.min(
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
    const zoom = clampZoom(zoomForRadius(lastWidth, lastHeight, span * 0.62));
    startTween({ x: pos.x, z: pos.z, zoom });
    return true;
  }

  /** Back to the whole floor. */
  function resetView() {
    focusedId = null;
    manualZoom = false;
    startTween(overview);
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
    seats.forEach(seat => { seat.plate.visible = (lod === 'near'); });
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
    const pod = pods.get(cluster);
    if (!pod || !canvas) return null;
    camera.updateMatrixWorld();
    _podScreenV.set(pod.group.position.x, 8, pod.group.position.z);
    _podScreenV.project(camera);
    if (_podScreenV.z > 1) return null;
    const rect = canvas.getBoundingClientRect();
    return {
      x: (_podScreenV.x + 1) / 2 * rect.width,
      y: (1 - _podScreenV.y) / 2 * rect.height,
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
    // Materials are shared and keyed by colour, so a theme change means new
    // ones. Rebuilding the office group is cheaper and more honest than
    // hunting down every mesh that used the old palette.
    rebuild();
  }

  function clearOffice() {
    seats.forEach(seat => disposeTree(seat.group));
    pods.forEach(pod => disposeTree(pod.group));
    walkways.forEach(walk => disposeTree(walk));
    connectors.forEach(line => disposeTree(line));
    walkways = new Map();
    connectors = new Map();
    if (conductor) disposeTree(conductor);
    scene.remove(office);
    seats = new Map();
    pods = new Map();
    conductor = null;
    office = new THREE.Group();
    scene.add(office);
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
    const hits = raycaster.intersectObjects(office.children, true);
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

  /**
   * Match the drawing buffer to the canvas' laid-out size. Called on every
   * frame as well as from the panel's ResizeObserver, because a panel that
   * was hidden while the window resized reports its real size only once it
   * is displayed again.
   */
  function resize() {
    const width = Math.max(1, canvas.clientWidth || 0);
    const height = Math.max(1, canvas.clientHeight || 0);
    if (width === lastWidth && height === lastHeight) return;
    lastWidth = width;
    lastHeight = height;
    // updateStyle=false: the canvas is sized by CSS, and letting three.js
    // write inline width/height styles would fight the flex layout.
    renderer.setSize(width, height, false);
    composer.setSize(width, height);
    // The framed zoom depends on aspect ratio, so a resize re-derives it. A
    // camera the user is driving keeps its own zoom.
    overview.zoom = zoomForRadius(width, height, framedRadius);
    if (!focusedId && !manualZoom && !tween) applyView(overview);
    else applyCamera(width, height);
  }
  resize();

  // ---- render loop ------------------------------------------------------
  let rafId = 0;
  let running = false;
  let lastFrameAt = 0;

  /**
   * Ease a pod/conductor glow's opacity toward its target (lit, pulsing
   * gently, or off) rather than snapping -- the same reasoning as the
   * outline's own dash fade.
   */
  function pulseGlow(material, active, t, dt) {
    if (!material) return;
    const target = active ? 0.16 + 0.1 * (0.5 + 0.5 * Math.sin(t * 2.4)) : 0;
    material.opacity += (target - material.opacity) * Math.min(1, dt * 4);
  }

  function frame(now) {
    if (!running) return;
    rafId = window.requestAnimationFrame(frame);
    resize();

    const t = (now || 0) / 1000;
    const dt = lastFrameAt ? Math.min(0.1, t - lastFrameAt) : 0.016;
    lastFrameAt = t;

    if (tween) advanceTween(now || 0);
    const dtMs = dt * 1000;

    // The adapter owns no timer, so its time-dependent poses (a tool call
    // settling back to plain work) only advance because the scene asks.
    if (typeof config.onTick === 'function') config.onTick();

    // The dashes travel only where something is running; a still outline on a
    // finished pod is the point of the cue. The fade runs regardless — it is
    // how a line comes up or goes quiet, and cutting it short mid-transition
    // would leave a half-lit colour on screen.
    const marchOffset = t * OUTLINE_SPEED;
    pods.forEach(record => {
      advanceDashFade(record.outline, dtMs);
      if (record.active) marchOutline(record.outline, marchOffset);
      // The glow eases toward its target opacity rather than snapping, same
      // reasoning as the outline's own fade, and gently pulses while active
      // so a working pod reads as alive rather than a static coloured patch.
      pulseGlow(record.glowMaterial, record.active, t, dt);
    });
    connectors.forEach(link => {
      advanceDashFade(link, dtMs);
      // Charge travels out from the conductor toward the pod.
      if (isDashActive(link)) marchOutline(link, marchOffset * CONNECTOR_SPEED_RATIO);
    });
    const conductorOutline = conductor && conductor.userData.outlineLine;
    if (conductorOutline) {
      advanceDashFade(conductorOutline, dtMs);
      if (isDashActive(conductorOutline)) marchOutline(conductorOutline, marchOffset);
    }
    if (conductor) {
      pulseGlow(conductor.userData.glowMaterial, conductor.userData.status === 'orchestrating', t, dt);
    }

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
          poseWorker(person, 'work', t, dt);
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
          poseWorker(person, 'idle', t, dt);
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
    start, stop, resize, dispose, isRunning, applyTheme, syncOffice,
    workerIdAt, focusOnWorker, focusOnPod, resetView, isFocused, getView,
    podScreenRect, scene,
  };
}
