// Office visualization — panel entry point.
//
// This is the only office module the rest of the app talks to. It is loaded
// as an ES module (static/index.html, via the "three" import map) and, like
// every other feature module here, publishes a plain global for the
// script-tag world to call:
//
//   window.HermesOffice.mount(containerEl)   -- panel became visible
//   window.HermesOffice.unmount()            -- panel was left
//   window.HermesOffice.renderSidebar()      -- history list in the sidebar
//   window.HermesOffice.onSpawn/onToolActivity/onComplete  -- live events
//
// static/panels.js drives mount/unmount from switchPanel(); static/messages.js
// fans the SSE events here alongside Agent Canvas. Mount is idempotent, so a
// repeat switch into an already-mounted panel just resumes the render loop.
//
// This layer owns everything that talks to the network — the adapter, the
// layout and the history translation are all pure — and it uses only the REST
// endpoints Agent Canvas already uses:
//
//   GET  /api/subagents/active        -> reconcile snapshot
//   POST /api/subagents/interrupt     -> subagent.interrupt {subagent_id}
//   POST /api/subagents/pause         -> block/unblock new delegate_task spawns
//   GET  /api/agent-canvas/sessions   -> chats that delegated, for history
//
// Hermes remains the source of truth throughout: this records what it reports
// and draws it. See docs/rfcs/office-visualization.md.
import { createOfficeScene } from './scene.js';
import { createOfficeAdapter } from './adapter.js';
import { applyHistory } from './history.js';

// The adapter outlives the panel on purpose. Subagents keep running while the
// user is on the Chat panel, and their events keep arriving; resetting office
// state on unmount would mean every visit to the panel showed an empty floor
// for a run that is very much still going.
const _adapter = createOfficeAdapter();

// Matches Agent Canvas' cadence. Reconciliation is a safety net for events
// missed while the page was closed or the stream was reconnecting, not the
// primary source — that is the live SSE fan-out.
const RECONCILE_MS = 5000;

let _container = null;
let _canvas = null;
let _scene = null;
let _detailEl = null;
let _pillEl = null;
let _hintEl = null;
let _pauseBtnEl = null;
let _backBtnEl = null;
let _resizeObserver = null;
let _themeObserver = null;
let _visibilityHandler = null;
let _unsubscribe = null;
let _pollTimer = null;
let _syncQueued = false;
let _selectedId = null;
let _spawnPaused = false;

// 'live' tracks the running session. 'history' shows a frozen office rebuilt
// from state.db for a finished chat picked in the sidebar — it gets its own
// adapter so the live one keeps accumulating events underneath, untouched.
let _viewMode = 'live';
let _historyAdapter = null;
let _historyParents = [];
let _historyParentId = null;

const STATUS_LABEL = {
  running: 'Running', completed: 'Completed', failed: 'Failed',
  error: 'Error', timeout: 'Timed out', interrupted: 'Interrupted',
};

const TERMINAL = new Set(['completed', 'failed', 'error', 'timeout', 'interrupted']);

function activeAdapter() {
  return (_viewMode === 'history' && _historyAdapter) ? _historyAdapter : _adapter;
}

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

function toast(message) {
  if (typeof window.showToast === 'function') window.showToast(message);
}

/** The app's fetch helper. Absent only in isolated harnesses. */
function request(path, opts) {
  if (typeof window.api !== 'function') return Promise.reject(new Error('api unavailable'));
  return window.api(path, opts);
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
    const state = activeAdapter().getState();
    _scene.syncOffice(state);
    renderPill(state);
    renderDetail(state);
  });
}

function renderPill(state) {
  if (!_pillEl) return;
  if (_viewMode === 'history') {
    _pillEl.textContent = 'HISTORY';
    _pillEl.classList.remove('is-live');
  } else {
    const live = state.conductor.status === 'orchestrating';
    const running = state.workers.filter(w => w.status === 'running').length;
    _pillEl.textContent = live ? `LIVE · ${running} working` : 'IDLE';
    _pillEl.classList.toggle('is-live', live);
  }
  if (_backBtnEl) _backBtnEl.hidden = _viewMode !== 'history';
  if (_pauseBtnEl) _pauseBtnEl.hidden = _viewMode === 'history';
  if (_hintEl) {
    _hintEl.textContent = _viewMode === 'history'
      ? 'A finished run, rebuilt from what Hermes recorded. Click a worker for detail.'
      : "Hermes' real delegation tree, live. Click a worker for detail.";
  }
}

function renderPauseButton() {
  if (!_pauseBtnEl) return;
  _pauseBtnEl.textContent = _spawnPaused ? 'Resume spawning' : 'Pause spawning';
  _pauseBtnEl.classList.toggle('is-paused', _spawnPaused);
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

  // Interrupting is a live control. A historical office is a record of
  // something that already finished; there is nothing there to stop.
  const canInterrupt = _viewMode === 'live' && !TERMINAL.has(worker.status);
  const actions = [];
  if (canInterrupt) {
    actions.push('<button type="button" class="office-detail-action danger" data-action="interrupt">Interrupt</button>');
  }
  if (worker.childSessionId) {
    actions.push('<button type="button" class="office-detail-action" data-action="open-session">Open conversation</button>');
  }

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
    ${actions.length ? `<div class="office-detail-actions">${actions.join('')}</div>` : ''}
  `;
  const close = _detailEl.querySelector('.office-detail-close');
  if (close) close.onclick = () => { _selectedId = null; scheduleSync(); };
  const open = _detailEl.querySelector('[data-action="open-session"]');
  if (open) open.onclick = () => openWorkerSession(worker);
  const interrupt = _detailEl.querySelector('[data-action="interrupt"]');
  if (interrupt) interrupt.onclick = () => interruptWorker(worker.id);
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

// ---- live controls ------------------------------------------------------

async function interruptWorker(subagentId) {
  if (!subagentId) return;
  try {
    await request('/api/subagents/interrupt', {
      method: 'POST', body: JSON.stringify({ subagent_id: subagentId }),
    });
    toast('Interrupt sent');
  } catch (err) {
    toast('Interrupt failed: ' + (err && err.message ? err.message : err));
  }
}

async function toggleSpawnPaused() {
  try {
    const data = await request('/api/subagents/pause', {
      method: 'POST', body: JSON.stringify({ paused: !_spawnPaused }),
    });
    _spawnPaused = !!(data && data.spawn_paused);
    toast(_spawnPaused ? 'New subagent spawns paused' : 'Spawning resumed');
    renderPauseButton();
  } catch (err) {
    toast('Failed to toggle pause: ' + (err && err.message ? err.message : err));
  }
}

/**
 * Catch up with `GET /api/subagents/active`.
 *
 * Best-effort: a transient failure must never blow away the office already
 * built from live events, so nothing here throws outward.
 */
async function reconcile() {
  try {
    const data = await request('/api/subagents/active', { timeoutToast: false });
    if (!data || data.gateway_enabled === false) return;
    _adapter.applySnapshot(data);
    if (_spawnPaused !== !!data.spawn_paused) {
      _spawnPaused = !!data.spawn_paused;
      renderPauseButton();
    }
    if (_viewMode === 'live') scheduleSync();
  } catch (_err) {
    // Reconciliation is background polling; failure is not an event.
  }
}

// ---- history ------------------------------------------------------------

/**
 * Show the frozen office for a finished chat. The live adapter is untouched
 * and keeps accumulating; only what is drawn changes.
 */
function showHistory(parentSessionId) {
  const parent = _historyParents.find(p => p.parent_session_id === parentSessionId);
  if (!parent) return;
  // A finished run can be far larger than the live desk cap, and nothing
  // should be reclaimed in a record of what happened.
  _historyAdapter = createOfficeAdapter({ maxDesks: 400 });
  applyHistory(_historyAdapter, parent);
  _viewMode = 'history';
  _historyParentId = parentSessionId;
  _selectedId = null;
  renderSessionList();
  scheduleSync();
}

/** Leave the frozen view and track the running session again. */
function returnToLive() {
  _viewMode = 'live';
  _historyAdapter = null;
  _historyParentId = null;
  _selectedId = null;
  renderSessionList();
  reconcile();
  scheduleSync();
}

function renderSessionList() {
  const list = document.getElementById('officeSessionList');
  if (!list) return;
  if (!_historyParents.length) {
    list.innerHTML = '<div class="office-sidebar-note">No chat has delegated to a subagent yet. '
      + 'When one does, it appears here and can be replayed on the floor.</div>';
    return;
  }
  list.innerHTML = _historyParents.map(parent => {
    const id = parent.parent_session_id;
    const count = Array.isArray(parent.children) ? parent.children.length : 0;
    const active = id === _historyParentId ? ' is-active' : '';
    return `<button type="button" class="office-session-row${active}" data-parent-id="${esc(id)}">
      <span class="office-session-title">${esc(parent.title || 'Untitled chat')}</span>
      <span class="office-session-meta">${count} subagent${count === 1 ? '' : 's'}</span>
    </button>`;
  }).join('');
  list.querySelectorAll('.office-session-row').forEach(row => {
    row.onclick = () => showHistory(row.dataset.parentId);
  });
}

/**
 * Fill the office panel's sidebar with the chats that ever delegated.
 * Called by switchPanel(), mirroring Agent Canvas.
 */
async function renderSidebar() {
  renderSessionList();
  try {
    const data = await request('/api/agent-canvas/sessions', { timeoutToast: false });
    _historyParents = (data && Array.isArray(data.parents)) ? data.parents : [];
  } catch (_err) {
    _historyParents = [];
  }
  renderSessionList();
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
  if (_pollTimer) {
    clearInterval(_pollTimer);
    _pollTimer = null;
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
      <span class="office-hint" id="officeHint">Hermes' real delegation tree, live. Click a worker for detail.</span>
      <button type="button" class="office-header-btn" id="officeBackBtn" hidden>Back to live</button>
      <button type="button" class="office-header-btn" id="officePauseBtn">Pause spawning</button>
    </div>
    <div class="office-stage">
      <canvas class="office-canvas" id="officeCanvas"></canvas>
      <div class="office-detail" id="officeDetail" hidden></div>
    </div>`;
  _canvas = container.querySelector('#officeCanvas');
  _detailEl = container.querySelector('#officeDetail');
  _pillEl = container.querySelector('#officePill');
  _hintEl = container.querySelector('#officeHint');
  _pauseBtnEl = container.querySelector('#officePauseBtn');
  _backBtnEl = container.querySelector('#officeBackBtn');
  _pauseBtnEl.onclick = toggleSpawnPaused;
  _backBtnEl.onclick = returnToLive;
  renderPauseButton();

  try {
    _scene = createOfficeScene(_canvas, {
      onSelect: id => { _selectedId = id; scheduleSync(); },
      onTick: () => activeAdapter().tick(),
    });
  } catch (err) {
    console.warn('[office] scene could not start:', err && err.message ? err.message : err);
    _scene = null;
    renderUnsupported(container);
    return;
  }

  _unsubscribe = _adapter.subscribe(() => { if (_viewMode === 'live') scheduleSync(); });

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

  // Polling only runs while the panel is up. The live SSE fan-out keeps the
  // office current whether or not anyone is looking at it; this is just the
  // catch-up for what the stream missed.
  _pollTimer = setInterval(reconcile, RECONCILE_MS);
  reconcile();

  _scene.resize();
  _scene.syncOffice(activeAdapter().getState());
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
  _hintEl = null;
  _pauseBtnEl = null;
  _backBtnEl = null;
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
function getState() { return activeAdapter().getState(); }

// Small global wrapper so the "View live" button on the office sidebar card
// can be a plain onclick="" attribute like every other sidebar card in this
// app. A function declared in a module is not a global, so this is explicit.
window.officeReturnToLive = returnToLive;

window.HermesOffice = {
  mount, unmount, isRunning, renderSidebar, returnToLive,
  onSpawn, onToolActivity, onComplete, applySnapshot, reset, getState,
  adapter: _adapter,
};
