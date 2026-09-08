// Office visualization — panel entry point.
//
// This is the only office module the rest of the app talks to. It is loaded
// as an ES module (static/index.html, via the "three" import map) and, like
// every other feature module here, publishes a plain global for the
// script-tag world to call:
//
//   window.HermesOffice.mount(containerEl)   -- panel became visible
//   window.HermesOffice.unmount()            -- panel was left
//   window.HermesOffice.onSpawn/onToolActivity/onComplete  -- live events
//
// static/panels.js drives mount/unmount from switchPanel(); static/messages.js
// fans the SSE events here alongside Agent Canvas. Mount is idempotent, so a
// repeat switch into an already-mounted panel just resumes the render loop.
//
// Hermes remains the source of truth throughout: this records what it reports
// and draws it. See docs/rfcs/office-visualization.md.
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
let _detailEl = null;
let _pillEl = null;
let _resizeObserver = null;
let _themeObserver = null;
let _visibilityHandler = null;
let _unsubscribe = null;
let _syncQueued = false;
let _selectedId = null;

const STATUS_LABEL = {
  running: 'Running', completed: 'Completed', failed: 'Failed',
  error: 'Error', timeout: 'Timed out', interrupted: 'Interrupted',
};

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function fmtDuration(seconds) {
  if (seconds == null) return '';
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return s + 's';
  const m = Math.floor(s / 60);
  if (m < 60) return m + 'm ' + (s % 60) + 's';
  return Math.floor(m / 60) + 'h ' + (m % 60) + 'm';
}

function fmtTokens(n) {
  if (!n) return '0';
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
  return String(n);
}

function fmtCost(usd) {
  if (usd == null) return '';
  return '$' + Number(usd).toFixed(usd >= 1 ? 2 : 4);
}

// ---- rendering ----------------------------------------------------------

/**
 * Push adapter state at the scene, coalesced to one call per frame. A burst
 * of parallel spawns arrives as a burst of events; rebuilding the floor once
 * per event would rebuild it a dozen times for one visual change.
 */
function scheduleSync() {
  if (_syncQueued || !_scene) return;
  _syncQueued = true;
  window.requestAnimationFrame(() => {
    _syncQueued = false;
    if (!_scene) return;
    const state = _adapter.getState();
    _scene.syncOffice(state);
    renderPill(state);
    renderDetail(state);
  });
}

function renderPill(state) {
  if (!_pillEl) return;
  const live = state.conductor.status === 'orchestrating';
  const running = state.workers.filter(w => w.status === 'running').length;
  _pillEl.textContent = live ? `LIVE · ${running} working` : 'IDLE';
  _pillEl.classList.toggle('is-live', live);
}

function renderDetail(state) {
  if (!_detailEl) return;
  const worker = _selectedId
    ? (state.workers || []).find(w => w.id === _selectedId)
    : null;
  if (!worker) {
    _detailEl.hidden = true;
    _detailEl.innerHTML = '';
    return;
  }
  const rows = [];
  const row = (label, value) => rows.push(
    `<div class="office-detail-row"><span>${esc(label)}</span><span>${esc(value)}</span></div>`,
  );
  row('Status', STATUS_LABEL[worker.status] || worker.status);
  if (worker.model) row('Model', worker.model);
  if (worker.depth != null) row('Depth', worker.depth);
  if (worker.taskIndex != null && worker.taskCount != null) {
    row('Batch task', `${worker.taskIndex + 1} / ${worker.taskCount}`);
  }
  if (worker.durationSeconds != null) row('Duration', fmtDuration(worker.durationSeconds));
  if (worker.apiCalls) row('API calls', worker.apiCalls);
  if (worker.inputTokens || worker.outputTokens) {
    row('Tokens', `${fmtTokens(worker.inputTokens)} in / ${fmtTokens(worker.outputTokens)} out`);
  }
  if (worker.costUsd != null) row('Cost', fmtCost(worker.costUsd));
  if (worker.toolCount) row('Tool calls', worker.toolCount);

  const tool = worker.tool && worker.tool.name
    ? `<div class="office-detail-block"><div class="office-detail-label">Current tool</div>
         <div class="office-detail-tool">${esc(worker.tool.name)}${
  worker.tool.preview ? ` <span>${esc(worker.tool.preview)}</span>` : ''}</div></div>`
    : '';

  _detailEl.hidden = false;
  _detailEl.innerHTML = `
    <div class="office-detail-head">
      <span class="office-detail-title">${esc(worker.label)}</span>
      <button type="button" class="office-detail-close" aria-label="Close">×</button>
    </div>
    ${rows.join('')}
    ${worker.goal ? `<div class="office-detail-block"><div class="office-detail-label">Goal</div><div class="office-detail-goal">${esc(worker.goal)}</div></div>` : ''}
    ${tool}
    ${worker.summary ? `<div class="office-detail-block"><div class="office-detail-label">Summary</div><div class="office-detail-goal">${esc(worker.summary)}</div></div>` : ''}
    ${worker.childSessionId ? '<div class="office-detail-actions"><button type="button" class="office-detail-action" data-action="open-session">Open conversation</button></div>' : ''}
  `;
  const close = _detailEl.querySelector('.office-detail-close');
  if (close) close.onclick = () => { _selectedId = null; scheduleSync(); };
  const open = _detailEl.querySelector('[data-action="open-session"]');
  if (open) open.onclick = () => openWorkerSession(worker);
}

/**
 * Jump to the subagent's own conversation. delegate_task gives every child a
 * real session, so this is the existing chat view, not an office-only log.
 */
function openWorkerSession(worker) {
  if (!worker || !worker.childSessionId) return;
  try {
    if (typeof window.loadSession === 'function') window.loadSession(worker.childSessionId);
    if (typeof window.switchPanel === 'function') window.switchPanel('chat');
  } catch (err) {
    console.warn('[office] could not open the subagent session:', err && err.message ? err.message : err);
  }
}

// ---- mount / unmount ----------------------------------------------------

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
  if (_unsubscribe) {
    try { _unsubscribe(); } catch (_err) { /* already gone */ }
    _unsubscribe = null;
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
    scheduleSync();
    return;
  }
  if (_container && _container !== container) unmount();

  _container = container;
  container.innerHTML = `
    <div class="office-header">
      <span class="office-pill" id="officePill">IDLE</span>
      <span class="office-hint">Hermes' real delegation tree, live. Click a worker for detail.</span>
    </div>
    <div class="office-stage">
      <canvas class="office-canvas" id="officeCanvas"></canvas>
      <div class="office-detail" id="officeDetail" hidden></div>
    </div>`;
  _canvas = container.querySelector('#officeCanvas');
  _detailEl = container.querySelector('#officeDetail');
  _pillEl = container.querySelector('#officePill');

  try {
    _scene = createOfficeScene(_canvas, {
      onSelect: id => { _selectedId = id; scheduleSync(); },
      onTick: () => _adapter.tick(),
    });
  } catch (err) {
    console.warn('[office] scene could not start:', err && err.message ? err.message : err);
    _scene = null;
    renderUnsupported(container);
    return;
  }

  _unsubscribe = _adapter.subscribe(() => scheduleSync());

  if (typeof ResizeObserver === 'function') {
    _resizeObserver = new ResizeObserver(() => { if (_scene) _scene.resize(); });
    _resizeObserver.observe(container);
  }

  // The app toggles `dark` on <html> when the theme changes; repaint the
  // office to match rather than leaving a dark floor on a light UI.
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
  _scene.syncOffice(_adapter.getState());
  _scene.start();
  scheduleSync();
}

/**
 * Leave the office panel: stop drawing and release the WebGL context.
 *
 * Called on every switch away from the panel. Full disposal (rather than
 * merely pausing) is deliberate — browsers cap live WebGL contexts, and a
 * panel the user flips in and out of would exhaust that cap within a
 * session. Office *state* is untouched: the run is still going.
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
  _detailEl = null;
  _pillEl = null;
}

/** True while the scene exists and its render loop is running. Used by tests. */
function isRunning() {
  return !!(_scene && _scene.isRunning());
}

// Event intake. static/messages.js fans the live SSE events here alongside
// Agent Canvas; both views read the same Hermes truth, neither owns it.
function onSpawn(payload) { return _adapter.onSpawn(payload); }
function onToolActivity(payload) { return _adapter.onToolActivity(payload); }
function onComplete(payload) { return _adapter.onComplete(payload); }
function applySnapshot(snapshot) { return _adapter.applySnapshot(snapshot); }
function reset() { _selectedId = null; return _adapter.reset(); }
function getState() { return _adapter.getState(); }

window.HermesOffice = {
  mount, unmount, isRunning,
  onSpawn, onToolActivity, onComplete, applySnapshot, reset, getState,
  adapter: _adapter,
};
