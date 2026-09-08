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
import { computeLayout, CONDUCTOR_RADIUS } from './layout.js';
import {
  makePod, makeDesk, makeChair, makePerson, makeNameplate,
  drawNameplate, drawScreen, poseWorker, disposeTree, disposeSharedCaches,
} from './builders.js';

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

// Palettes are WebGL material colours rather than CSS custom properties:
// they are handed to THREE.Color, not to a stylesheet. The panel's own
// chrome still comes from the app's theme tokens as usual.
const PALETTES = {
  light: {
    ground: '#f2efe8', grid: '#d8d3c8',
    podTop: '#ffffff', podSide: '#e4dfd4',
    deskTop: '#c9a227', deskLeg: '#8b8b93',
    chair: '#5f6672',
    shirt: '#6b8fb5', skin: '#e8b98e', hair: '#3b2b1d',
    screenBezel: '#2c2c34', screenBg: '#14141c',
    screenText: '#8fb9a8', screenTextBright: '#d8f0e4',
    plateBg: 'rgba(255,255,255,0.92)', plateText: '#151414', plateAccent: '#1e9070',
    conductor: '#2b3245',
  },
  dark: {
    ground: '#1b1b2b', grid: '#2b2b40',
    podTop: '#24243a', podSide: '#1a1a2a',
    deskTop: '#8a6d1f', deskLeg: '#4a4a58',
    chair: '#3a3f4b',
    shirt: '#4f7ca8', skin: '#c68b59', hair: '#1a1a20',
    screenBezel: '#0e0e14', screenBg: '#0a0a12',
    screenText: '#5adeb7', screenTextBright: '#b9f5e2',
    plateBg: 'rgba(20,20,37,0.92)', plateText: '#f2f2f7', plateAccent: '#5adeb7',
    conductor: '#8fd3f4',
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

  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, -400, 800);
  const cameraTarget = new THREE.Vector3(0, 0, 0);
  let framedCenter = { x: 0, z: 0 };
  let palette = PALETTES[prefersDark() ? 'dark' : 'light'];

  // Tracked so dispose() can release them without walking the graph and
  // guessing which resources were ours.
  const ownedGeometries = [];
  const ownedMaterials = [];

  // ---- lighting rig -----------------------------------------------------
  const ambient = new THREE.AmbientLight(0xffffff, FILL_LIGHT_INTENSITY);
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
  /** deskId -> {group, person, plate, screen, workerId, pose, tint} */
  let seats = new Map();
  let conductor = null;
  let lastState = null;
  let framedRadius = 0;

  function ensureConductor() {
    if (conductor) return conductor;
    const group = new THREE.Group();
    const pod = makePod(CONDUCTOR_RADIUS * 1.4, CONDUCTOR_RADIUS * 1.4, palette);
    group.add(pod);
    const person = makePerson(palette, palette.conductor);
    person.position.y = 0.6;
    group.add(person);
    const plate = makeNameplate(palette, 'Conductor');
    plate.position.set(0, 5.4, 0);
    group.add(plate);
    group.userData.person = person;
    group.userData.plate = plate;
    office.add(group);
    conductor = group;
    return conductor;
  }

  function ensurePod(cluster, width, depth) {
    let pod = pods.get(cluster);
    if (pod && pod.width === width && pod.depth === depth) return pod;
    if (pod) {
      office.remove(pod.group);
      disposeTree(pod.group);
    }
    const group = makePod(width + 3, depth + 3, palette);
    office.add(group);
    pod = { group, width, depth };
    pods.set(cluster, pod);
    return pod;
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
    group.add(person);
    const plate = makeNameplate(palette, '');
    plate.position.set(0, 5.0, 0);
    group.add(plate);
    // Marks the whole subtree as belonging to a worker so a raycast hit on
    // any child resolves back to one id.
    group.userData.deskId = deskId;
    office.add(group);
    seat = {
      group, person, plate, screen: desk.userData.screen,
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
    if (!pod) return;
    office.remove(pod.group);
    disposeTree(pod.group);
    pods.delete(cluster);
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
      const record = ensurePod(pod.cluster, pod.width, pod.depth);
      record.group.position.set(pod.x, 0, pod.z);
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

    const conductorStatus = state.conductor ? state.conductor.status : 'idle';
    if (conductor.userData.status !== conductorStatus) {
      conductor.userData.status = conductorStatus;
      drawNameplate(conductor.userData.plate, palette, 'Conductor',
        conductorStatus === 'orchestrating' ? 'running' : '');
    }

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
    cameraTarget.set(framedCenter.x, 0, framedCenter.z);
    applyCamera(lastWidth, lastHeight);
  }

  function applyCamera(width, height) {
    const aspect = height > 0 ? width / height : 1;
    const halfWidth = FRUSTUM_HALF_HEIGHT * aspect;
    camera.left = -halfWidth;
    camera.right = halfWidth;
    camera.top = FRUSTUM_HALF_HEIGHT;
    camera.bottom = -FRUSTUM_HALF_HEIGHT;
    // Fit the floor in both axes: its full radius across, its foreshortened
    // radius (plus standing headroom) down. Whichever is tighter wins.
    camera.zoom = framedRadius > 0
      ? Math.min(
        2.2,
        halfWidth / framedRadius,
        FRUSTUM_HALF_HEIGHT / (framedRadius * ISO_VERTICAL_SCALE + FRAME_HEADROOM),
      )
      : 1;
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
    // Materials are shared and keyed by colour, so a theme change means new
    // ones. Rebuilding the office group is cheaper and more honest than
    // hunting down every mesh that used the old palette.
    rebuild();
  }

  function clearOffice() {
    seats.forEach(seat => disposeTree(seat.group));
    pods.forEach(pod => disposeTree(pod.group));
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

  function workerIdAt(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects(office.children, true);
    for (const hit of hits) {
      let node = hit.object;
      while (node) {
        if (node.userData && node.userData.workerId) return node.userData.workerId;
        node = node.parent;
      }
    }
    return null;
  }

  function onClick(event) {
    const id = workerIdAt(event.clientX, event.clientY);
    if (id && typeof config.onSelect === 'function') config.onSelect(id);
  }
  canvas.addEventListener('click', onClick);

  function onPointerMove(event) {
    canvas.style.cursor = workerIdAt(event.clientX, event.clientY) ? 'pointer' : '';
  }
  canvas.addEventListener('pointermove', onPointerMove);

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
    applyCamera(width, height);
  }
  resize();

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

    // The adapter owns no timer, so its time-dependent poses (a tool call
    // settling back to plain work) only advance because the scene asks.
    if (typeof config.onTick === 'function') config.onTick();

    seats.forEach(seat => poseWorker(seat.person, seat.pose, t, dt));
    if (conductor) {
      poseWorker(conductor.userData.person,
        conductor.userData.status === 'orchestrating' ? 'work' : 'idle', t, dt);
    }

    renderer.render(scene, camera);
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
    canvas.removeEventListener('click', onClick);
    canvas.removeEventListener('pointermove', onPointerMove);
    clearOffice();
    disposeSharedCaches();
    scene.clear();
    ownedGeometries.forEach(g => { try { g.dispose(); } catch (_err) { /* already gone */ } });
    ownedMaterials.forEach(m => { try { m.dispose(); } catch (_err) { /* already gone */ } });
    ownedGeometries.length = 0;
    ownedMaterials.length = 0;
    // Releases the WebGL context itself. Without this, switching in and out
    // of the panel eventually exhausts the browser's context limit and every
    // later mount renders nothing.
    try { renderer.dispose(); } catch (_err) { /* context already lost */ }
    try { renderer.forceContextLoss(); } catch (_err) { /* not supported everywhere */ }
  }

  ensureConductor();

  return {
    start, stop, resize, dispose, isRunning, applyTheme, syncOffice,
    workerIdAt, scene,
  };
}
