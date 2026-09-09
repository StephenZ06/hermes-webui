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
import { buildRoster, businessView } from './roster.js';

// The adapter outlives the panel on purpose. Subagents keep running while the
// user is on the Chat panel, and their events keep arriving; resetting office
// state on unmount would mean every visit to the panel showed an empty floor
// for a run that is very much still going.
const _adapter = createOfficeAdapter();

// Matches Agent Canvas' cadence. Reconciliation is a safety net for events
// missed while the page was closed or the stream was reconnecting, not the
// primary source — that is the live SSE fan-out.
const RECONCILE_MS = 5000;

// Which floor plan is showing. 'projects' draws exactly what delegate_task
// did — a desk per subagent, pods by parent. 'business' draws the same run on
// a standing departmental floor. Both read identical adapter state; only desk
// assignment differs.
const OUTLET_STORAGE_KEY = 'hermes-webui-office-mode';

let _container = null;
let _canvas = null;
let _scene = null;
let _detailEl = null;
let _pillEl = null;
let _hintEl = null;
let _summaryEl = null;
let _lastSummary = '';
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
let _gatewayEnabled = true;
let _outlet = readOutlet();
let _roster = buildRoster([]);
let _rosterLoaded = false;
let _outletBtnEls = {};

// 'live' tracks the running session. 'history' shows a frozen office rebuilt
// from state.db for a finished chat picked in the sidebar — it gets its own
// adapter so the live one keeps accumulating events underneath, untouched.
let _viewMode = 'live';
let _historyAdapter = null;
let _historyParents = [];
let _historyParentId = null;
let _sessionQuery = '';

const STATUS_LABEL = {
  running: 'Running', completed: 'Completed', failed: 'Failed',
  error: 'Error', timeout: 'Timed out', interrupted: 'Interrupted',
  // Inferred, not reported: it left the live registry without a completion
  // event ever reaching us. Named for what we actually know.
  ended: 'Ended · no result reported',
};

const TERMINAL = new Set(['completed', 'failed', 'error', 'timeout', 'interrupted']);

function readOutlet() {
  try {
    return localStorage.getItem(OUTLET_STORAGE_KEY) === 'business' ? 'business' : 'projects';
  } catch (_err) {
    // Private windows and blocked site data throw on access, not on read of a
    // missing key; the office still has to render.
    return 'projects';
  }
}

function writeOutlet(mode) {
  try {
    localStorage.setItem(OUTLET_STORAGE_KEY, mode);
  } catch (_err) { /* a remembered preference is not worth failing over */ }
}

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

/**
 * A running worker has no recorded duration yet, so derive one from its
 * spawn time. A detail panel that shows nothing until a subagent finishes is
 * least useful exactly while someone is watching it work.
 */
function liveDuration(worker) {
  if (!worker) return null;
  if (worker.durationSeconds != null) return worker.durationSeconds;
  if (!worker.spawnedAt) return null;
  return Math.max(0, (Date.now() - worker.spawnedAt) / 1000);
}

/** Every worker below `id` in the delegation tree, deepest last. */
function descendantsOf(id, workers) {
  const out = [];
  const stack = [id];
  while (stack.length) {
    const current = stack.pop();
    for (const worker of workers) {
      if (worker.parentId === current) {
        out.push(worker);
        stack.push(worker.id);
      }
    }
  }
  return out;
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
    // Business is a desk-assignment policy, not a second engine: it rewrites
    // `desks` into roster seats and hands the scene the same shape Projects
    // does, so neither the layout nor the scene knows which outlet is up.
    const view = _outlet === 'business' ? businessView(state, _roster) : state;
    _scene.syncOffice(view);
    renderPill(state);
    renderDetail(state);
    renderSummary(state);
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
  if (_pauseBtnEl) _pauseBtnEl.hidden = !_gatewayEnabled || _viewMode === 'history';
  if (_hintEl) {
    _hintEl.textContent = _viewMode === 'history'
      ? 'A finished run, rebuilt from what Hermes recorded. Click a worker for detail.'
      : "Hermes' real delegation tree, live. Click a worker for detail.";
  }
}

function renderOutletSwitch() {
  Object.keys(_outletBtnEls).forEach(mode => {
    const btn = _outletBtnEls[mode];
    if (btn) btn.classList.toggle('is-active', mode === _outlet);
  });
}

function setOutlet(mode) {
  const next = mode === 'business' ? 'business' : 'projects';
  if (next === _outlet) return;
  _outlet = next;
  writeOutlet(next);
  renderOutletSwitch();
  if (next === 'business') loadRoster();
  scheduleSync();
}

/**
 * Load the standing roster the Business floor is drawn from.
 *
 * Personas are the closest thing this app has to a named agent roster today;
 * `/api/personalities` carries a name and a description and nothing else, so
 * departments are inferred from those words (see static/office/roster.js).
 * Failure is not fatal — the six departments still stand, with placeholder
 * desks.
 */
async function loadRoster() {
  if (_rosterLoaded) return;
  _rosterLoaded = true;
  try {
    const data = await request('/api/personalities', { timeoutToast: false });
    _roster = buildRoster((data && data.personalities) || []);
  } catch (_err) {
    _roster = buildRoster([]);
  }
  if (_outlet === 'business') scheduleSync();
}

/**
 * A spoken equivalent of the floor.
 *
 * The office is a canvas, which is opaque to a screen reader — the picture is
 * the whole point of the view, and no amount of ARIA on a <canvas> changes
 * that. This keeps the same facts available as text. It is deliberately not a
 * replacement: Agent Canvas remains the DOM view of the same tree, which is
 * one of the reasons it is not being retired (see the RFC's phase 6).
 */
function renderSummary(state) {
  if (!_summaryEl) return;
  const workers = state.workers || [];
  const running = workers.filter(w => w.status === 'running');
  const parts = [
    _viewMode === 'history' ? 'Historical run.' : 'Live delegation.',
    `${workers.length} subagent${workers.length === 1 ? '' : 's'}, ${running.length} running.`,
  ];
  running.slice(0, 8).forEach(w => {
    parts.push(`${w.label}: ${w.tool && w.tool.name ? 'using ' + w.tool.name : 'working'}.`);
  });
  const text = parts.join(' ');
  // aria-live re-announces on every change, so only write when it moved.
  if (text === _lastSummary) return;
  _lastSummary = text;
  _summaryEl.textContent = text;
}

function renderPauseButton() {
  if (!_pauseBtnEl) return;
  _pauseBtnEl.textContent = _spawnPaused ? 'Resume spawning' : 'Pause spawning';
  _pauseBtnEl.classList.toggle('is-paused', _spawnPaused);
  _pauseBtnEl.hidden = !_gatewayEnabled || _viewMode === 'history';
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
  const duration = liveDuration(worker);
  if (duration != null) row('Duration', fmtDuration(duration));
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

  const tail = Array.isArray(worker.outputTail) && worker.outputTail.length
    ? `<div class="office-detail-block"><div class="office-detail-label">Recent tool activity</div>${
  worker.outputTail.map(entry => `<div class="office-detail-tool${entry && entry.isError ? ' is-error' : ''}">${
    esc(entry && entry.tool)}${entry && entry.preview ? ` <span>${esc(entry.preview)}</span>` : ''}</div>`).join('')}</div>`
    : '';

  const files = ['filesRead', 'filesWritten'].map((key, i) => {
    const list = worker[key];
    if (!Array.isArray(list) || !list.length) return '';
    return `<div class="office-detail-block"><div class="office-detail-label">${
      i === 0 ? 'Files read' : 'Files written'}</div>${
      list.map(f => `<div class="office-detail-tool">${esc(f)}</div>`).join('')}</div>`;
  }).join('');

  // Interrupting is a live control. A historical office is a record of
  // something that already finished; there is nothing there to stop.
  const canInterrupt = _viewMode === 'live' && !TERMINAL.has(worker.status);
  const liveDescendants = canInterrupt
    ? descendantsOf(worker.id, state.workers || []).filter(w => !TERMINAL.has(w.status))
    : [];
  const actions = [];
  if (canInterrupt) {
    actions.push('<button type="button" class="office-detail-action danger" data-action="interrupt">Interrupt</button>');
  }
  if (liveDescendants.length) {
    actions.push('<button type="button" class="office-detail-action danger" data-action="interrupt-branch">Interrupt branch</button>');
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
    ${tail}
    ${files}
    ${actions.length ? `<div class="office-detail-actions">${actions.join('')}</div>` : ''}
  `;
  const close = _detailEl.querySelector('.office-detail-close');
  if (close) close.onclick = () => { _selectedId = null; scheduleSync(); };
  const open = _detailEl.querySelector('[data-action="open-session"]');
  if (open) open.onclick = () => openWorkerSession(worker);
  const interrupt = _detailEl.querySelector('[data-action="interrupt"]');
  if (interrupt) interrupt.onclick = () => interruptWorker(worker.id);
  const branch = _detailEl.querySelector('[data-action="interrupt-branch"]');
  if (branch) {
    branch.onclick = () => interruptBranch(worker.id, liveDescendants.map(w => w.id));
  }
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

/**
 * Stop a subagent and everything below it, deepest first — a parent should
 * not be left interrupting into children that already stopped.
 */
async function interruptBranch(subagentId, descendantIds) {
  const targets = (descendantIds || []).slice().reverse().concat([subagentId]);
  for (const id of targets) await interruptWorker(id);
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
    if (!data) return;
    _adapter.applySnapshot(data);
    // Pausing spawns is a gateway-process control: the in-process deployment
    // answers POST /api/subagents/pause with 409. Offering a button that can
    // only ever error is worse than not offering it.
    const gatewayEnabled = data.gateway_enabled !== false;
    if (_gatewayEnabled !== gatewayEnabled) {
      _gatewayEnabled = gatewayEnabled;
      renderPauseButton();
    }
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
  const query = _sessionQuery.trim().toLowerCase();
  const visible = query
    ? _historyParents.filter(p => String(p.title || '').toLowerCase().includes(query))
    : _historyParents;
  if (query && !visible.length) {
    list.innerHTML = '<div class="office-sidebar-note">No delegating chat matches that filter.</div>';
    return;
  }
  if (!_historyParents.length) {
    list.innerHTML = '<div class="office-sidebar-note">No chat has delegated to a subagent yet. '
      + 'When one does, it appears here and can be replayed on the floor.</div>';
    return;
  }
  list.innerHTML = visible.map(parent => {
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
      <span class="office-outlet" role="group" aria-label="Floor plan">
        <button type="button" class="office-outlet-btn" data-outlet="projects">Projects</button>
        <button type="button" class="office-outlet-btn" data-outlet="business">Business</button>
      </span>
      <button type="button" class="office-header-btn" id="officeBackBtn" hidden>Back to live</button>
      <button type="button" class="office-header-btn" id="officePauseBtn">Pause spawning</button>
    </div>
    <div class="office-stage">
      <canvas class="office-canvas" id="officeCanvas" role="img"
              aria-label="Isometric floor of the current Hermes delegation tree"></canvas>
      <div class="office-detail" id="officeDetail" hidden></div>
      <div class="sr-only" id="officeSummary" role="status" aria-live="polite"></div>
    </div>`;
  _canvas = container.querySelector('#officeCanvas');
  _detailEl = container.querySelector('#officeDetail');
  _pillEl = container.querySelector('#officePill');
  _hintEl = container.querySelector('#officeHint');
  _summaryEl = container.querySelector('#officeSummary');
  // The dedup guard below is keyed on text, and the element is brand new, so
  // a remount whose state has not changed would otherwise leave it empty.
  _lastSummary = '';
  _pauseBtnEl = container.querySelector('#officePauseBtn');
  _backBtnEl = container.querySelector('#officeBackBtn');
  _pauseBtnEl.onclick = toggleSpawnPaused;
  _backBtnEl.onclick = returnToLive;
  _outletBtnEls = {};
  container.querySelectorAll('.office-outlet-btn').forEach(btn => {
    _outletBtnEls[btn.dataset.outlet] = btn;
    btn.onclick = () => setOutlet(btn.dataset.outlet);
  });
  renderPauseButton();
  renderOutletSwitch();
  loadRoster();

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
  _summaryEl = null;
  _pauseBtnEl = null;
  _backBtnEl = null;
  _outletBtnEls = {};
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

/** Sidebar filter box, mirroring the Agent Canvas one. */
function filterOfficeSessions() {
  const input = document.getElementById('officeSearch');
  _sessionQuery = input ? input.value : '';
  const clear = document.getElementById('officeSearchClear');
  if (clear) clear.hidden = !_sessionQuery;
  renderSessionList();
}

function clearOfficeSearch() {
  const input = document.getElementById('officeSearch');
  if (input) input.value = '';
  filterOfficeSessions();
}

window.filterOfficeSessions = filterOfficeSessions;
window.clearOfficeSearch = clearOfficeSearch;

// Small global wrapper so the "View live" button on the office sidebar card
// can be a plain onclick="" attribute like every other sidebar card in this
// app. A function declared in a module is not a global, so this is explicit.
window.officeReturnToLive = returnToLive;

window.HermesOffice = {
  mount, unmount, isRunning, renderSidebar, returnToLive, setOutlet,
  onSpawn, onToolActivity, onComplete, applySnapshot, reset, getState,
  adapter: _adapter,
};
