// Office visualization — WebGL scene shell (phase 1).
//
// Phase 1 deliberately renders only the ground plane and lighting rig. It
// exists to prove the whole no-bundler path end to end: a vendored ES module
// (`three`, resolved through the import map in static/index.html) loaded from
// a panel in an app that has no build step, drawing into a canvas that lives
// inside the SPA's normal main-view container, with a render loop that stops
// dead the moment the panel is hidden.
//
// Desks, workers and their poses arrive in phase 3, driven exclusively by
// HermesOfficeAdapter — see docs/rfcs/office-visualization.md. This module
// must never fetch, never poll and never hold app state: it draws what it is
// told to draw and nothing else.
//
// WebGL inside a long-lived SPA panel leaks aggressively if the loop and the
// GPU resources aren't owned by someone. `createOfficeScene()` returns that
// owner: start/stop bracket the rAF loop, dispose() releases every geometry,
// material and the renderer's own context.
import * as THREE from 'three';

// Half-height of the orthographic frustum at zoom 1, in world units. The
// office is authored against this so a desk keeps the same on-screen size
// whatever the panel's aspect ratio is.
const FRUSTUM_HALF_HEIGHT = 42;
// Locked isometric view direction. Slightly taller than a true 2:1 iso so
// floor markings stay readable at overview zoom.
const ISO_DIRECTION = new THREE.Vector3(1, 0.92, 1).normalize();
const CAMERA_DISTANCE = 220;
const GROUND_SIZE = 150;

// Ground colours per theme. Kept here rather than read from CSS custom
// properties because these are WebGL material colours, not CSS: they have to
// survive being handed to THREE.Color, and the panel's own chrome (headers,
// overlays) still comes from the app's theme tokens as usual.
const GROUND_COLOR = { light: '#f2efe8', dark: '#1b1b2b' };
const GRID_COLOR = { light: '#d8d3c8', dark: '#2b2b40' };
const KEY_LIGHT_INTENSITY = 1.6;
const FILL_LIGHT_INTENSITY = 0.55;

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
 * The caller owns the canvas and the element the canvas sits in; this owns
 * everything inside WebGL. Nothing here reads or writes app state.
 *
 * @param {HTMLCanvasElement} canvas
 * @returns {{start:Function, stop:Function, resize:Function, dispose:Function,
 *            isRunning:Function, applyTheme:Function, scene:THREE.Scene}}
 */
export function createOfficeScene(canvas) {
  if (!canvas) throw new Error('createOfficeScene: a canvas element is required');

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

  // Tracked so dispose() can release them without walking the graph and
  // guessing which resources were ours.
  const ownedGeometries = [];
  const ownedMaterials = [];

  function own(geometry, material) {
    if (geometry) ownedGeometries.push(geometry);
    if (material) ownedMaterials.push(material);
  }

  // ---- lighting rig -----------------------------------------------------
  const ambient = new THREE.AmbientLight(0xffffff, FILL_LIGHT_INTENSITY);
  scene.add(ambient);

  const keyLight = new THREE.DirectionalLight(0xffffff, KEY_LIGHT_INTENSITY);
  keyLight.position.set(60, 120, 40);
  keyLight.castShadow = true;
  keyLight.shadow.mapSize.set(1024, 1024);
  keyLight.shadow.camera.near = 1;
  keyLight.shadow.camera.far = 400;
  keyLight.shadow.camera.left = -120;
  keyLight.shadow.camera.right = 120;
  keyLight.shadow.camera.top = 120;
  keyLight.shadow.camera.bottom = -120;
  scene.add(keyLight);

  // ---- ground -----------------------------------------------------------
  const groundGeometry = new THREE.PlaneGeometry(GROUND_SIZE, GROUND_SIZE);
  const groundMaterial = new THREE.MeshStandardMaterial({
    color: GROUND_COLOR.dark, roughness: 0.95, metalness: 0.0,
  });
  own(groundGeometry, groundMaterial);
  const ground = new THREE.Mesh(groundGeometry, groundMaterial);
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);

  // Faint floor grid. Phase 3 replaces this with department plinths; until
  // then it is what makes the iso projection legible as a floor at all.
  const grid = new THREE.GridHelper(GROUND_SIZE, 30, GRID_COLOR.dark, GRID_COLOR.dark);
  grid.position.y = 0.02;
  if (grid.material) {
    grid.material.transparent = true;
    grid.material.opacity = 0.5;
    ownedMaterials.push(grid.material);
  }
  if (grid.geometry) ownedGeometries.push(grid.geometry);
  scene.add(grid);

  /** Repaint the floor for the app's current theme. Safe to call any time. */
  function applyTheme() {
    const key = prefersDark() ? 'dark' : 'light';
    groundMaterial.color.set(GROUND_COLOR[key]);
    if (grid.material && grid.material.color) grid.material.color.set(GRID_COLOR[key]);
  }
  applyTheme();

  function applyCamera(width, height) {
    const aspect = height > 0 ? width / height : 1;
    camera.left = -FRUSTUM_HALF_HEIGHT * aspect;
    camera.right = FRUSTUM_HALF_HEIGHT * aspect;
    camera.top = FRUSTUM_HALF_HEIGHT;
    camera.bottom = -FRUSTUM_HALF_HEIGHT;
    camera.position.copy(cameraTarget).addScaledVector(ISO_DIRECTION, CAMERA_DISTANCE);
    camera.lookAt(cameraTarget);
    camera.updateProjectionMatrix();
  }

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

  function frame() {
    if (!running) return;
    rafId = window.requestAnimationFrame(frame);
    resize();
    renderer.render(scene, camera);
  }

  function start() {
    if (running) return;
    // A hidden tab gets no rAF callbacks anyway; not starting keeps the
    // "running" flag honest so visibilitychange can restart cleanly.
    running = true;
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

  return { start, stop, resize, dispose, isRunning, applyTheme, scene };
}
