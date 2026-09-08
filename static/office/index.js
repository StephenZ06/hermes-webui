// Office visualization — panel entry point (phase 1).
//
// This is the only office module the rest of the app talks to. It is loaded
// as an ES module (static/index.html, via the "three" import map) and, like
// every other feature module here, publishes a plain global for the
// script-tag world to call:
//
//   window.HermesOffice.mount(containerEl)   -- panel became visible
//   window.HermesOffice.unmount()            -- panel was left
//
// static/panels.js drives both from switchPanel(). Mount is idempotent, so a
// repeat switch into an already-mounted panel just resumes the render loop.
//
// Phase 1 scope: prove the no-bundler ES-module path and the WebGL lifecycle.
// The scene is a lit floor. Phase 2 adds HermesOfficeAdapter (pure state, no
// three.js); phase 3 puts desks and workers on this floor from real
// subagent_spawn / subagent_tool / subagent_complete events. See
// docs/rfcs/office-visualization.md.
import { createOfficeScene } from './scene.js';
import { createOfficeAdapter } from './adapter.js';

// The adapter outlives the panel on purpose. Subagents keep running while the
// user is on the Chat panel, and their events keep arriving; resetting office
// state on unmount would mean every visit to the panel showed an empty floor
// for a run that is very much still going.
const _adapter = createOfficeAdapter();

let _container = null;
let _canvas = null;
let _scene = null;
let _resizeObserver = null;
let _themeObserver = null;
let _visibilityHandler = null;

function teardownObservers() {
  if (_resizeObserver) {
    try { _resizeObserver.disconnect(); } catch (_err) { /* already gone */ }
    _resizeObserver = null;
  }
  if (_themeObserver) {
    try { _themeObserver.disconnect(); } catch (_err) { /* already gone */ }
    _themeObserver = null;
  }
  if (_visibilityHandler) {
    document.removeEventListener('visibilitychange', _visibilityHandler);
    _visibilityHandler = null;
  }
}

function renderUnsupported(container) {
  container.innerHTML = '<div class="office-unsupported">This browser could not start WebGL, '
    + 'so the office view can\'t render. The Agent Canvas panel shows the same delegation '
    + 'tree without WebGL.</div>';
}

/**
 * Mount (or resume) the office scene inside `container`.
 * @param {HTMLElement} container the panel's wrap element
 */
function mount(container) {
  if (!container) return;
  if (_container === container && _scene) {
    // Same panel re-entered: the scene is intact, just start drawing again
    // and re-measure, since the container's size while hidden was 0x0.
    _scene.resize();
    _scene.applyTheme();
    _scene.start();
    return;
  }
  if (_container && _container !== container) unmount();

  _container = container;
  container.innerHTML = '<canvas class="office-canvas" id="officeCanvas"></canvas>';
  _canvas = container.querySelector('#officeCanvas');

  try {
    _scene = createOfficeScene(_canvas);
  } catch (err) {
    console.warn('[office] scene could not start:', err && err.message ? err.message : err);
    _scene = null;
    renderUnsupported(container);
    return;
  }

  if (typeof ResizeObserver === 'function') {
    _resizeObserver = new ResizeObserver(() => { if (_scene) _scene.resize(); });
    _resizeObserver.observe(container);
  }

  // The app toggles `dark` on <html> when the theme changes; repaint the
  // floor materials to match rather than leaving a dark floor on a light UI.
  if (typeof MutationObserver === 'function') {
    _themeObserver = new MutationObserver(() => { if (_scene) _scene.applyTheme(); });
    _themeObserver.observe(document.documentElement, {
      attributes: true, attributeFilter: ['class', 'data-skin'],
    });
  }

  // A backgrounded tab already stops delivering rAF callbacks, but stopping
  // explicitly keeps the running flag truthful and releases the loop for
  // browsers that throttle rather than pause.
  _visibilityHandler = () => {
    if (!_scene) return;
    if (document.hidden) _scene.stop();
    else _scene.start();
  };
  document.addEventListener('visibilitychange', _visibilityHandler);

  _scene.resize();
  _scene.start();
}

/**
 * Leave the office panel: stop drawing and release the WebGL context.
 *
 * Called on every switch away from the panel. Full disposal (rather than
 * merely pausing) is deliberate — browsers cap live WebGL contexts, and a
 * panel the user flips in and out of would exhaust that cap within a
 * session.
 */
function unmount() {
  teardownObservers();
  if (_scene) {
    try { _scene.dispose(); } catch (_err) { /* context already lost */ }
    _scene = null;
  }
  if (_container) _container.innerHTML = '';
  _container = null;
  _canvas = null;
}

/** True while the scene exists and its render loop is running. Used by tests. */
function isRunning() {
  return !!(_scene && _scene.isRunning());
}

// Event intake. static/messages.js fans the live SSE events here alongside
// Agent Canvas; both views read the same Hermes truth, neither owns it.
// Phase 2 records the events into office state; phase 3 puts them on the
// floor. Hermes decides what happens — this only ever describes it.
function onSpawn(payload) { return _adapter.onSpawn(payload); }
function onToolActivity(payload) { return _adapter.onToolActivity(payload); }
function onComplete(payload) { return _adapter.onComplete(payload); }
function applySnapshot(snapshot) { return _adapter.applySnapshot(snapshot); }
function reset() { return _adapter.reset(); }
function getState() { return _adapter.getState(); }

window.HermesOffice = {
  mount, unmount, isRunning,
  onSpawn, onToolActivity, onComplete, applySnapshot, reset, getState,
  adapter: _adapter,
};
