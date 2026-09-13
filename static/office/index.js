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
// fans the SSE events here. Mount is idempotent, so a repeat switch into an
// already-mounted panel just resumes the render loop.
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
import { buildRoster, businessView, departmentFor } from './roster.js';
import { colorForProjectsCluster } from './layout.js';

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
// Whether the Task Status column is collapsed to a slim strip -- remembered
// the same way the outlet choice is, so reclaiming the canvas' width sticks
// across visits rather than resetting itself open every time.
const TASKS_COLLAPSED_STORAGE_KEY = 'hermes-webui-office-tasks-collapsed';

// A stored run whose children never recorded an end is only called live if it
// has been active recently; past that it was cut off, not running.
const LIVE_WINDOW_SECONDS = 900;
// Stand-in id for a delegation running outside any known chat session.
const LIVE_ENTRY_ID = '__live__';
// How often the stored listing is refetched while the panel is open, so a run
// that started elsewhere shows up without a manual refresh.
const SIDEBAR_REFRESH_MS = 15000;

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
// Per-department floating stat cards (Business outlet only). Keyed by
// department key, one DOM element each, repositioned every frame to track
// the pod as the camera pans/zooms (see repositionDepartmentCards below).
let _deptCardsEl = null;
const _deptCardEls = new Map();
// Aggregate Task Status panel: every worker the adapter currently knows
// about, whole-office, independent of which outlet is showing (a subagent is
// the same real subagent whichever floor plan draws it).
let _tasksFiltersEl = null;
let _tasksListEl = null;
let _tasksFilter = 'all';
let _lastTaskStatusWorkers = [];
let _tasksEl = null;
let _tasksCollapseBtnEl = null;
let _tasksCollapsed = readTasksCollapsed();
let _resizeObserver = null;
let _themeObserver = null;
let _visibilityHandler = null;
let _unsubscribe = null;
let _pollTimer = null;
let _sidebarTimer = null;
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
// session id -> the name its last delegation gave it
const _liveSummaries = new Map();
let _historyParentId = null;
// What the open history view was built from, so a listing refresh that brought
// no news does not rebuild it out from under the reader.
let _historySignature = '';
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

function readTasksCollapsed() {
  try {
    return localStorage.getItem(TASKS_COLLAPSED_STORAGE_KEY) === '1';
  } catch (_err) {
    return false;
  }
}

function writeTasksCollapsed(collapsed) {
  try {
    localStorage.setItem(TASKS_COLLAPSED_STORAGE_KEY, collapsed ? '1' : '0');
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
 * The Projects floor, with business-classified work held back for the
 * Business floor instead of appearing on both. A worker's own goal decides
 * it -- the same `departmentFor()` businessView() itself uses to seat a
 * desk, so "would this land in a department" is answered identically on
 * both floors and a run can never be business-classified on one and not
 * the other. Every descendant of a business-classified worker is hidden
 * with it, even one whose own goal reads as generic ("read this file") --
 * it exists because business work delegated it, so it's part of that same
 * branch, not re-classified independently.
 *
 * Outlet-independent state -- the sidebar's live indicator, the detail
 * panel, and the Task Status column -- is untouched; this only reshapes
 * what `_scene.syncOffice()` and the floating stat cards draw.
 */
function projectsFloorView(state) {
  const workers = state.workers || [];
  const hidden = new Set();
  workers.forEach(worker => {
    if (!departmentFor(worker.goal || worker.label || '')) return;
    hidden.add(worker.id);
    descendantsOf(worker.id, workers).forEach(d => hidden.add(d.id));
  });
  const desks = (state.desks || []).filter(desk => !desk.workerId || !hidden.has(desk.workerId));
  return Object.assign({}, state, { desks });
}

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
    const view = _outlet === 'business' ? businessView(state, _roster) : projectsFloorView(state);
    _scene.syncOffice(view);
    renderPill(state);
    renderDetail(state);
    renderSummary(state);
    renderDepartmentCards(view, state);
    renderTaskStatusPanel(state);
    if (_outletFadePending) {
      _outletFadePending = false;
      revealAfterOutletFade();
    }
  });
}

// The fade-out is at least this long before the reveal starts, whatever
// scheduleSync's own timing is -- a switch cheap enough to reconcile within
// a couple of frames (most Projects<->Business switches, measured) would
// otherwise remove the class before the browser ever paints the faded-out
// frame, so the whole cross-fade is invisible: add-then-remove within the
// same frame or two is a well-known case of a CSS transition never being
// observed at all, not just a short one. Matches the CSS transition's own
// .22s duration.
const OUTLET_FADE_MIN_MS = 220;

/**
 * Reveal the floor once BOTH scheduleSync has actually finished (so a slow
 * switch -- Business waiting on a `/api/personalities` fetch and a
 * department's worth of floor signs -- never reveals a stale or half-built
 * frame) AND the fade-out has been visible for at least
 * OUTLET_FADE_MIN_MS (so a fast switch doesn't add-then-remove the class
 * within the same frame or two, which a browser can coalesce into no
 * visible transition at all). Whichever of the two takes longer wins.
 */
function revealAfterOutletFade() {
  const elapsed = performance.now() - _outletFadeStartedAt;
  const remaining = OUTLET_FADE_MIN_MS - elapsed;
  const reveal = () => {
    // One more frame so the just-synced floor has actually painted before
    // the fade reveals it -- removing the class in the same callback that
    // just ran scheduleSync's work would sometimes reveal the previous
    // frame's half-drawn state instead.
    window.requestAnimationFrame(() => {
      if (_canvas) _canvas.classList.remove('is-switching-outlet');
    });
  };
  if (remaining > 0) window.setTimeout(reveal, remaining);
  else reveal();
}

// A worker never runs again after one of these (see office/adapter.js's own
// TERMINAL_STATUSES) -- the same vocabulary, duplicated rather than imported
// so this module keeps reading a plain adapter snapshot rather than needing
// the adapter module itself.
const _TERMINAL_STATUSES = new Set([
  'completed', 'failed', 'error', 'timeout', 'interrupted', 'ended',
]);

/**
 * Which pods get a floating stat card, and what to print on it -- the one
 * thing that differs between the outlets. Business has a fixed, named
 * roster; Projects has no fixed identity (a pod is just "whoever's parent
 * spawned this cluster"), so its cards carry no name -- but DO get a
 * colour, the same `colorForProjectsCluster()` derivation the floor itself
 * uses (layout.js's computeLayout), so a card's accent always matches the
 * floor it floats over. Returns null when there is nothing to show (the
 * caller clears any existing cards in that case).
 *
 * Business also includes "The Floor" overflow (roster.js's buildRoster
 * always appends it as a 7th standing entry) -- uncoloured, matching the
 * pod tint.
 */
function officeCardSpecs(view) {
  if (_outlet === 'business') {
    if (!_roster || !Array.isArray(_roster.departments)) return null;
    return _roster.departments.map(dept => ({ key: dept.key, name: dept.name, color: dept.color }));
  }
  // Projects: one card per pod actually on the floor right now -- pods come
  // and go with the live delegation tree, there is no standing list to draw
  // an empty one from the way Business always has all six.
  const clusters = new Set();
  (view.desks || []).forEach(desk => { if (desk.cluster) clusters.add(desk.cluster); });
  if (!clusters.size) return null;
  return Array.from(clusters).map(key => ({ key, name: null, color: colorForProjectsCluster(key) }));
}

/**
 * The floating stat card seen over each pod: an optional name (Business
 * only), seat count, and two honest live counts (active / done) derived
 * from the SAME state the floor itself is drawn from -- no metric this app
 * cannot actually measure (unlike the reference product's "cost per user"
 * style numbers, which have no equivalent here).
 */
function renderDepartmentCards(view, state) {
  if (!_deptCardsEl) return;
  const specs = officeCardSpecs(view);
  if (!specs) {
    if (_deptCardEls.size) { _deptCardsEl.innerHTML = ''; _deptCardEls.clear(); }
    return;
  }
  const workersById = new Map((state.workers || []).map(w => [w.id, w]));
  const desksByCluster = new Map();
  (view.desks || []).forEach(desk => {
    if (!desksByCluster.has(desk.cluster)) desksByCluster.set(desk.cluster, []);
    desksByCluster.get(desk.cluster).push(desk);
  });

  const seen = new Set();
  specs.forEach(spec => {
    seen.add(spec.key);
    const desks = desksByCluster.get(spec.key) || [];
    let active = 0;
    let done = 0;
    desks.forEach(desk => {
      const worker = desk.workerId ? workersById.get(desk.workerId) : null;
      if (!worker) return;
      if (worker.status === 'running') active += 1;
      else if (_TERMINAL_STATUSES.has(worker.status)) done += 1;
    });

    let el = _deptCardEls.get(spec.key);
    if (!el) {
      el = document.createElement('div');
      el.className = 'office-dept-card';
      _deptCardsEl.appendChild(el);
      _deptCardEls.set(spec.key, el);
    }
    if (spec.color) el.style.setProperty('--office-dept-color', spec.color);
    else el.style.removeProperty('--office-dept-color');
    el.innerHTML = `
      ${spec.name ? `<div class="office-dept-card-name">${esc(spec.name)}</div>` : ''}
      <div class="office-dept-card-count">${desks.length}<span>agent${desks.length === 1 ? '' : 's'}</span></div>
      <div class="office-dept-card-stats">
        <span class="office-dept-card-stat"><strong>${active}</strong>active</span>
        <span class="office-dept-card-stat"><strong>${done}</strong>done</span>
      </div>`;
  });

  // A pod that dropped off the floor (Business: a reload with a different
  // config, in principle; Projects: its run simply finished and it was
  // swept) loses its card rather than leaving a stale one floating with
  // nothing to anchor it.
  Array.from(_deptCardEls.keys()).forEach(key => {
    if (seen.has(key)) return;
    const el = _deptCardEls.get(key);
    if (el) el.remove();
    _deptCardEls.delete(key);
  });

  repositionDepartmentCards();
}

/**
 * Keeps each card over its pod as the camera pans/zooms/tweens. Called every
 * frame via the scene's onTick (see createOfficeScene below) -- cheap when
 * there is nothing to reposition, which is whenever the current outlet has
 * no cards up.
 */
function repositionDepartmentCards() {
  if (!_deptCardEls.size) return;
  if (!_scene || typeof _scene.podScreenRect !== 'function') return;
  _deptCardEls.forEach((el, cluster) => {
    const rect = _scene.podScreenRect(cluster);
    if (!rect) { el.style.display = 'none'; return; }
    el.style.display = '';
    el.style.left = rect.x + 'px';
    el.style.top = rect.y + 'px';
  });
}

// ── Task Status panel ──
//
// A whole-office aggregate of the real workers the adapter is tracking, next
// to the floor rather than buried in a per-desk detail click. Independent of
// which outlet is showing: a subagent is the same real subagent whether the
// floor plan draws it as an anonymous desk (Projects) or a department seat
// (Business).

/** Adapter statuses collapse to three buckets a filter chip can show a count
 * for. 'running' stays its own bucket (the one thing worth watching live);
 * 'completed' is 'done'; everything else terminal (failed/error/timeout/
 * interrupted/ended) is 'stopped' -- distinct outcomes in the adapter, but
 * none of them is "still going", which is the only distinction this panel's
 * filter makes below "done". */
function taskStatusBucket(status) {
  if (status === 'running') return 'running';
  if (status === 'completed') return 'done';
  if (_TERMINAL_STATUSES.has(status)) return 'stopped';
  return 'other';
}

const TASK_STATUS_FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'running', label: 'Running' },
  { key: 'done', label: 'Done' },
  { key: 'stopped', label: 'Stopped' },
];

/** Pure so tests/test_office_task_status.py can drive it without a DOM. */
function taskStatusCounts(workers) {
  const counts = { all: 0, running: 0, done: 0, stopped: 0, other: 0 };
  (workers || []).forEach(w => {
    counts.all += 1;
    counts[taskStatusBucket(w.status)] += 1;
  });
  return counts;
}

/**
 * The Task Status column collapses to a slim strip -- the filters and list
 * stay in the DOM (so a collapse never has to rebuild them), only their
 * visibility follows the state. Remembered per-browser so reclaiming the
 * canvas' width sticks across visits.
 */
function renderTasksCollapse() {
  if (!_tasksEl || !_tasksCollapseBtnEl) return;
  _tasksEl.classList.toggle('is-collapsed', _tasksCollapsed);
  _tasksCollapseBtnEl.setAttribute('aria-expanded', String(!_tasksCollapsed));
  _tasksCollapseBtnEl.textContent = _tasksCollapsed ? '‹' : '›';
  _tasksCollapseBtnEl.title = _tasksCollapsed ? 'Show Task Status' : 'Collapse Task Status';
}

function toggleTasksCollapsed() {
  _tasksCollapsed = !_tasksCollapsed;
  writeTasksCollapsed(_tasksCollapsed);
  renderTasksCollapse();
}

function renderTaskStatusFilters() {
  if (!_tasksFiltersEl) return;
  const counts = taskStatusCounts((_lastTaskStatusWorkers || []));
  _tasksFiltersEl.innerHTML = TASK_STATUS_FILTERS.map(f => `
    <button type="button" class="office-tasks-filter${_tasksFilter === f.key ? ' is-active' : ''}"
            data-filter="${f.key}" role="tab" aria-selected="${_tasksFilter === f.key}">
      ${esc(f.label)} <span>${counts[f.key]}</span>
    </button>`).join('');
  _tasksFiltersEl.querySelectorAll('.office-tasks-filter').forEach(btn => {
    btn.onclick = () => {
      _tasksFilter = btn.dataset.filter;
      renderTaskStatusFilters();
      renderTaskStatusList(_lastTaskStatusWorkers || []);
    };
  });
}

/** How long ago, in the same short-form the rest of the app uses for a live
 * run ("42s", "3m") -- not a full timestamp, which would be noise in a list
 * meant to be scanned at a glance. */
function taskStatusAge(worker) {
  const from = worker.spawnedAt;
  if (!from) return '';
  const end = worker.endedAt || Date.now();
  const seconds = Math.max(0, Math.round((end - from) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  return `${Math.round(minutes / 60)}h`;
}

function renderTaskStatusList(workers) {
  _lastTaskStatusWorkers = workers || [];
  if (!_tasksListEl) return;
  const rows = _lastTaskStatusWorkers.filter(w =>
    _tasksFilter === 'all' || taskStatusBucket(w.status) === _tasksFilter);
  if (!rows.length) {
    _tasksListEl.innerHTML = '<div class="office-tasks-empty">Nothing here yet.</div>';
    return;
  }
  // Most recently spawned first -- what just started is what someone opening
  // this panel most likely wants to see.
  const ordered = rows.slice().sort((a, b) => (b.spawnedAt || 0) - (a.spawnedAt || 0));
  _tasksListEl.innerHTML = ordered.map(w => `
    <button type="button" class="office-tasks-row" data-worker-id="${esc(w.id)}">
      <span class="office-tasks-row-status status-${esc(taskStatusBucket(w.status))}" aria-hidden="true"></span>
      <span class="office-tasks-row-body">
        <span class="office-tasks-row-goal">${esc(w.goal || w.label || 'Subagent')}</span>
        <span class="office-tasks-row-meta">${esc(w.status || '')}${taskStatusAge(w) ? ' · ' + esc(taskStatusAge(w)) : ''}</span>
      </span>
    </button>`).join('');
  _tasksListEl.querySelectorAll('.office-tasks-row').forEach(row => {
    row.onclick = () => {
      if (_scene && typeof _scene.focusOnWorker === 'function') _scene.focusOnWorker(row.dataset.workerId);
    };
  });
}

function renderTaskStatusPanel(state) {
  renderTaskStatusFilters();
  renderTaskStatusList(state.workers || []);
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
    if (_scene && _scene.isFocused()) {
      _hintEl.textContent = 'Focused on one desk — Esc, or click the floor, to pull back out.';
    } else {
      _hintEl.textContent = _viewMode === 'history'
        ? 'A finished run, rebuilt from what Hermes recorded. Click a worker to fly to it.'
        : "Hermes' real delegation tree, live. Click a worker to fly to it.";
    }
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
  animateOutletSwitch();
  scheduleSync();
}

// Set while a fade-out is waiting on the *next* scheduleSync to actually
// finish reconciling the new outlet's floor -- see scheduleSync() below.
let _outletFadePending = false;
// When that fade-out started, so the reveal can also wait out a minimum
// visible duration (see OUTLET_FADE_MIN_MS/revealAfterOutletFade below).
let _outletFadeStartedAt = 0;

/**
 * A brief fade rather than the floor instantly swapping under the camera:
 * desks/pods are added and removed the moment scheduleSync's next frame
 * reconciles the new outlet's view, which otherwise reads as a hard cut --
 * furniture and figures blinking away and others popping in mid-frame.
 * Hiding the canvas for one beat while that reconciliation happens turns it
 * into a deliberate transition instead.
 *
 * The reveal is tied to scheduleSync() actually completing, not a fixed
 * timer: switching to Business can mean waiting on a `/api/personalities`
 * fetch and rebuilding a department's worth of floor signs, which measured
 * well past a first guess of "220ms ought to cover it" under load -- a
 * timer that fires before the new floor is actually drawn reveals a stale
 * or half-built frame instead of masking the swap.
 */
function animateOutletSwitch() {
  if (!_canvas) return;
  _canvas.classList.add('is-switching-outlet');
  _outletFadeStartedAt = performance.now();
  // setOutlet() calls scheduleSync() right after this; that's what actually
  // clears the flag once the new floor is drawn (see scheduleSync() below).
  _outletFadePending = true;
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
 * that. This keeps the same facts available as text.
 *
 * It carries more weight than it used to: the Agent Canvas panel, which was
 * the DOM rendering of this same tree, has been removed, so this summary is
 * now the only non-visual account of a delegation. Keep it accurate.
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
  if (close) {
    close.onclick = () => {
      _selectedId = null;
      // Closing the panel and leaving the camera buried in one desk would
      // strand the user zoomed in with nothing selected.
      if (_scene) _scene.resetView();
      scheduleSync();
    };
  }
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
 * What the office drawn for a run depends on, as one comparable string.
 *
 * Which children there are and how each one ended — nothing else changes the
 * floor, so nothing else should cost the user their camera and their open
 * detail panel on a listing refresh that brought no news.
 */
function historySignature(parent) {
  const children = (parent && Array.isArray(parent.children)) ? parent.children : [];
  return children
    .map(c => `${(c && c.session_id) || ''}:${(c && c.status) || ''}:${(c && c.ended_at) || ''}`)
    .join('|');
}

/** Build the frozen office for one listing entry. No camera, no view mode. */
function buildHistoryOffice(parent) {
  // A historical office is a record, not a live floor: it can be far larger
  // than the live desk cap, nothing is swept and nothing is reclaimed.
  _historyAdapter = createOfficeAdapter({ maxDesks: 400, completedLingerMs: 0 });
  // A run that is still going has children with no recorded end. Replayed as
  // history those read as "cut off"; told the run is live, they read as
  // working — which is what they are.
  applyHistory(_historyAdapter, parent, { live: looksLive(parent) });
  _historySignature = historySignature(parent);
}

/**
 * Rebuild the open history view when its run has moved on.
 *
 * A history office is built once, from the listing as it stood when the row
 * was clicked. Clicked while the run was still going — which the cross-profile
 * ledger made easy, since it lists a delegation from the moment it starts —
 * it froze every child as unfinished and nothing ever corrected it. Called
 * from the listing refresh, so the frozen floor catches up on its own.
 */
function refreshHistory() {
  if (_viewMode !== 'history' || !_historyParentId) return;
  const parent = _historyParents.find(p => p.parent_session_id === _historyParentId);
  if (!parent || historySignature(parent) === _historySignature) return;
  buildHistoryOffice(parent);
  scheduleSync();
}

/**
 * Show the frozen office for a finished chat. The live adapter is untouched
 * and keeps accumulating; only what is drawn changes.
 */
function showHistory(parentSessionId) {
  const parent = _historyParents.find(p => p.parent_session_id === parentSessionId);
  if (!parent) return;
  buildHistoryOffice(parent);
  _viewMode = 'history';
  _historyParentId = parentSessionId;
  _selectedId = null;
  // The camera was framed on — possibly zoomed into a desk of — a different
  // run. Carrying that over would leave it pointed at a worker that no longer
  // exists, on a floor the user has never seen.
  if (_scene) _scene.resetView();
  renderSessionList();
  scheduleSync();
}

/** Leave the frozen view and track the running session again. */
function returnToLive() {
  _viewMode = 'live';
  _historyAdapter = null;
  _historyParentId = null;
  _historySignature = '';
  _selectedId = null;
  if (_scene) _scene.resetView();
  renderSessionList();
  reconcile();
  scheduleSync();
}

/**
 * A one-line summary of what a run is actually doing, built from the goals of
 * its subagents.
 *
 * The chat's own title is about the conversation, not the delegation — two
 * different fan-outs from the same chat are indistinguishable under it — so
 * the goals are what names the row. Falls back to the chat title when there
 * are no goals to read.
 */
function delegationSummary(goals, fallback) {
  const cleaned = (goals || [])
    .map(g => String(g || '').replace(/^Subagent:\s*/, '').trim())
    .filter(Boolean);
  if (!cleaned.length) return String(fallback || 'Untitled chat');
  const head = cleaned[0].length > 44 ? cleaned[0].slice(0, 43) + '…' : cleaned[0];
  return cleaned.length > 1 ? `${head} +${cleaned.length - 1} more` : head;
}

/** True while a stored run still has subagents that never recorded an end. */
function looksLive(parent) {
  const children = Array.isArray(parent.children) ? parent.children : [];
  if (!children.some(c => c && !c.ended_at)) return false;
  // A row that never recorded an end is either genuinely running or was cut
  // off long ago; only recent activity can tell them apart, and claiming a
  // dead run is live is worse than missing a live one.
  const latest = Number(parent.latest_at) || 0;
  if (!latest) return false;
  return (Date.now() / 1000 - latest) < LIVE_WINDOW_SECONDS;
}

/**
 * The run happening right now, as a sidebar entry.
 *
 * A delegation has to appear the moment it starts, and the stored listing
 * cannot supply that: those rows land in state.db as the children are
 * created, and the listing is only refetched periodically. This is built from
 * the live adapter instead, and is replaced by the stored entry once that
 * catches up.
 */
function liveEntry() {
  if (_viewMode !== 'live') return null;
  const state = _adapter.getState();
  if (!state.workers.length) return null;
  const session = (typeof window.S === 'object' && window.S && window.S.session) || null;
  const running = state.workers.filter(w => w.status === 'running').length;
  const id = (session && session.session_id) || LIVE_ENTRY_ID;
  const title = delegationSummary(state.workers.map(w => w.goal), session && session.title);
  // Kept so the row keeps its name in the window between the workers being
  // swept and the stored listing catching up.
  _liveSummaries.set(id, title);
  return {
    parent_session_id: id,
    title,
    children: state.workers.map(w => ({ session_id: w.id })),
    latest_at: Date.now() / 1000,
    _live: running > 0,
    _isLiveEntry: true,
  };
}

/**
 * The name a stored run should carry.
 *
 * Named from its children's goals for the same reason the live row is: the
 * chat's own title describes the conversation, and an untitled chat has none
 * at all — which is how a row that read "read README.md +2 more" while running
 * reverted to "Untitled chat" the moment its live workers were swept.
 *
 * `_liveSummaries` covers the gap in between: the stored listing is refetched
 * on a timer, so for a few seconds after a run ends there may be neither live
 * workers nor a stored row carrying the children yet.
 */
function storedTitle(parent) {
  const children = Array.isArray(parent.children) ? parent.children : [];
  const remembered = _liveSummaries.get(parent.parent_session_id);
  return delegationSummary(children.map(c => c && c.title),
    remembered || parent.title);
}

/** Stored listing plus the run in flight, newest first, without duplicates. */
function sidebarEntries() {
  const live = liveEntry();
  // When the adapter is tracking a live run, that run is the *only* live row.
  // `looksLive` is a heuristic over unclosed child rows + a 15-minute activity
  // window, and the cross-profile ledger leaves 'running' rows behind for a
  // delegation that has actually finished — so a chat you delegated from a few
  // minutes ago would keep a pulsing dot and, sitting right under the current
  // run, read as "the chat below is also live". The adapter knows precisely
  // which run is in flight; defer to it and only fall back to the heuristic in
  // history view, where there is no adapter truth to defer to.
  const stored = _historyParents.map(p => Object.assign({}, p, {
    _live: live ? false : looksLive(p), title: storedTitle(p),
  }));
  if (!live) return stored;
  const at = stored.findIndex(p => p.parent_session_id === live.parent_session_id);
  if (at >= 0) {
    // The stored row exists but is behind: keep its identity, take the live
    // run's freshness.
    stored[at] = Object.assign({}, stored[at], {
      title: live.title, children: live.children, _live: live._live,
    });
    return [stored[at]].concat(stored.slice(0, at), stored.slice(at + 1));
  }
  return [live].concat(stored);
}

function renderSessionList() {
  const list = document.getElementById('officeSessionList');
  if (!list) return;
  const entries = sidebarEntries();
  const query = _sessionQuery.trim().toLowerCase();
  const visible = query
    ? entries.filter(p => String(p.title || '').toLowerCase().includes(query))
    : entries;
  if (query && !visible.length) {
    list.innerHTML = '<div class="office-sidebar-note">No delegating chat matches that filter.</div>';
    return;
  }
  if (!entries.length) {
    list.innerHTML = '<div class="office-sidebar-note">No chat has delegated to a subagent yet. '
      + 'When one does, it appears here and can be replayed on the floor.</div>';
    return;
  }
  list.innerHTML = visible.map(parent => {
    const id = parent.parent_session_id;
    const count = Array.isArray(parent.children) ? parent.children.length : 0;
    const active = id === _historyParentId ? ' is-active' : '';
    // The dot sits to the right of the row and is the only thing that
    // distinguishes a run happening now from one that finished — these
    // listings mix profiles, so "which of these is live" is not otherwise
    // answerable from the row.
    const dot = parent._live
      ? '<span class="office-session-live" title="Subagents running now" aria-label="live"></span>'
      : '';
    return `<button type="button" class="office-session-row${active}${parent._live ? ' is-live' : ''}" data-parent-id="${esc(id)}"${parent._isLiveEntry ? ' data-live-entry="1"' : ''}>
      <span class="office-session-text">
        <span class="office-session-title">${esc(parent.title || 'Untitled chat')}</span>
        <span class="office-session-meta">${count} subagent${count === 1 ? '' : 's'}</span>
      </span>${dot}
    </button>`;
  }).join('');
  list.querySelectorAll('.office-session-row').forEach(row => {
    row.onclick = () => {
      // The live row is the office you are already looking at; there is no
      // stored run to replay yet, so clicking it returns to the live view.
      if (row.dataset.liveEntry) returnToLive();
      else showHistory(row.dataset.parentId);
    };
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
  refreshHistory();
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
  if (_sidebarTimer) {
    clearInterval(_sidebarTimer);
    _sidebarTimer = null;
  }
}

function renderUnsupported(container) {
  // Nothing to redirect to any more: the office is the delegation view. Say
  // what is wrong and what would fix it rather than pointing at a panel that
  // no longer exists.
  container.innerHTML = '<div class="office-unsupported">This browser could not start WebGL, '
    + 'so the office floor can\'t render. Delegation still runs normally — enable hardware '
    + 'acceleration, or open the WebUI in a browser with WebGL, to see it.</div>';
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
    <div class="office-body">
      <div class="office-stage">
        <canvas class="office-canvas" id="officeCanvas" role="img"
                aria-label="Isometric floor of the current Hermes delegation tree"></canvas>
        <div class="office-dept-cards" id="officeDeptCards" aria-hidden="true"></div>
        <div class="office-detail" id="officeDetail" hidden></div>
        <div class="sr-only" id="officeSummary" role="status" aria-live="polite"></div>
      </div>
      <div class="office-tasks" id="officeTasks">
        <div class="office-tasks-head">
          <div class="office-tasks-head-row">
            <span class="office-tasks-title">Task Status</span>
            <button type="button" class="office-tasks-collapse-btn" id="officeTasksCollapseBtn"
                    aria-expanded="true" aria-controls="officeTasksFilters officeTasksList">›</button>
          </div>
          <div class="office-tasks-filters" id="officeTasksFilters" role="tablist" aria-label="Filter by status"></div>
        </div>
        <div class="office-tasks-list" id="officeTasksList"></div>
      </div>
    </div>`;
  _canvas = container.querySelector('#officeCanvas');
  _detailEl = container.querySelector('#officeDetail');
  _pillEl = container.querySelector('#officePill');
  _hintEl = container.querySelector('#officeHint');
  _summaryEl = container.querySelector('#officeSummary');
  _deptCardsEl = container.querySelector('#officeDeptCards');
  _deptCardEls.clear();
  _tasksEl = container.querySelector('#officeTasks');
  _tasksCollapseBtnEl = container.querySelector('#officeTasksCollapseBtn');
  _tasksCollapseBtnEl.onclick = toggleTasksCollapsed;
  renderTasksCollapse();
  _tasksFiltersEl = container.querySelector('#officeTasksFilters');
  _tasksListEl = container.querySelector('#officeTasksList');
  _tasksFilter = 'all';
  renderTaskStatusFilters();
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
      onTick: () => { activeAdapter().tick(); repositionDepartmentCards(); },
      // The detail panel owns the right edge of the stage; the camera slides
      // a focused desk clear of it rather than flying to a spot the panel
      // then covers.
      // Measured when the panel is up; otherwise derived from the same rule
      // its CSS uses. A click focuses before the panel has rendered, so
      // asking a hidden element for its width would always answer 0 and the
      // camera would fly to a spot the panel then covers.
      panelInset: () => {
        if (!_detailEl) return 0;
        const measured = _detailEl.getBoundingClientRect().width;
        if (measured) return measured + 28;
        const stage = _canvas ? _canvas.getBoundingClientRect().width : 0;
        return stage ? Math.min(320, stage - 28) + 28 : 0;
      },
    });
  } catch (err) {
    console.warn('[office] scene could not start:', err && err.message ? err.message : err);
    _scene = null;
    renderUnsupported(container);
    return;
  }

  _unsubscribe = _adapter.subscribe(cmd => {
    if (_viewMode === 'live') scheduleSync();
    // A delegation has to show up in the sidebar the moment it starts, not on
    // the next poll: the stored listing cannot know about it yet.
    if (cmd && (cmd.type === 'worker.spawn' || cmd.type === 'worker.status'
      || cmd.type === 'worker.remove' || cmd.type === 'reset')) renderSessionList();
  });

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
  // Runs started under another profile, or in another tab, only reach this
  // panel through the stored listing.
  _sidebarTimer = setInterval(() => { renderSidebar(); }, SIDEBAR_REFRESH_MS);

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
  _deptCardsEl = null;
  _deptCardEls.clear();
  _outletFadePending = false;
  _tasksEl = null;
  _tasksCollapseBtnEl = null;
  _tasksFiltersEl = null;
  _tasksListEl = null;
  _tasksFilter = 'all';
  _lastTaskStatusWorkers = [];
}

/** True while the scene exists and its render loop is running. Used by tests. */
function isRunning() {
  return !!(_scene && _scene.isRunning());
}

// Event intake. static/messages.js fans the live SSE events here. Hermes
// remains the source of truth; this only records what it reports.
function onSpawn(payload) { return _adapter.onSpawn(payload); }
function onToolActivity(payload) { return _adapter.onToolActivity(payload); }
function onComplete(payload) { return _adapter.onComplete(payload); }
function applySnapshot(snapshot) { return _adapter.applySnapshot(snapshot); }
function reset() { _selectedId = null; return _adapter.reset(); }

/** Camera state — diagnostics, and what the browser tests assert on. */
function getView() { return _scene ? _scene.getView() : null; }

/** Fly to a worker's desk from outside the canvas (sidebar, tests). */
function focusWorker(id) {
  if (!_scene || !_scene.focusOnWorker(id)) return false;
  _selectedId = id;
  scheduleSync();
  return true;
}

/** Pull back to the whole floor. */
function resetView() {
  if (_scene) _scene.resetView();
  _selectedId = null;
  scheduleSync();
}
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
//
// "View live" means: show me the live floor. That is a main-view switch, not
// just a view-mode reset — pressed from a chat (or a history replay) it must
// land on the office, mount it if needed, then track the running session.
window.officeReturnToLive = function officeReturnToLive() {
  if (typeof window.switchPanel === 'function') {
    Promise.resolve(window.switchPanel('office')).then(returnToLive);
  } else {
    returnToLive();
  }
};

window.HermesOffice = {
  mount, unmount, isRunning, renderSidebar, returnToLive, setOutlet,
  getView, focusWorker, resetView,
  onSpawn, onToolActivity, onComplete, applySnapshot, reset, getState,
  adapter: _adapter,
};
