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
import { buildRoster, businessView, projectsView } from './roster.js';
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
let _tasksCountEl = null;
let _lastTaskStatusDoneCount = null;
let _taskCompletionTimer = null;
let _tasksCollapsed = readTasksCollapsed();
let _resizeObserver = null;
let _themeObserver = null;
let _visibilityHandler = null;
let _unsubscribe = null;
let _pollTimer = null;
let _sidebarTimer = null;
let _syncQueued = false;
let _selectedId = null;
let _taskStatusDisclosureAnimating = false;
let _taskStatusDisclosureTimer = null;
let _tasksCollapseAnimating = false;
let _tasksCollapseTimer = null;
let _spawnPaused = false;
let _gatewayEnabled = true;
let _outlet = readOutlet();
let _roster = buildRoster([]);
// Whether the real roster (/api/personalities) has arrived; until it has, the
// Business floor is a placeholder (see scheduleSync's reveal hold).
let _rosterReady = false;
let _rosterLoaded = false;
let _outletBtnEls = {};
let _labelsVisible = true;
// Office owns its subpages so the rail still has one Office destination. The
// floor remains the default; Dashboard and Integrations are focused surfaces
// inside the same themed shell, not unrelated top-level application panels.
let _officeSubview = 'floor';
let _preserveOfficeNavigationOnUnmount = false;
// Department cards live in screen space, unlike the WebGL pods below them.
// In adaptive mode they shrink with a zoomed-out office so their visual weight
// stays proportional to the platform they describe.
let _labelsAdaptive = true;

// 'live' tracks the running session. 'history' shows a frozen office rebuilt
// from state.db for a finished chat picked in the sidebar — it gets its own
// adapter so the live one keeps accumulating events underneath, untouched.
let _viewMode = 'live';
let _historyAdapter = null;
let _historyParents = [];
let _officeProjects = [];
const _dashboardAttentionBySession = new Map();
const _expandedProjectIds = new Set();
const PROJECT_FOLDER_TRANSITION_MS = 240;
let _projectFoldersSignature = '';
let _projectFoldersAnimationUntil = 0;
let _projectFoldersDeferredTimer = null;
// The Office floor is a live WebGL + post-processing scene. A sidebar or
// workspace-panel slide changes the available canvas geometry, so rendering
// through that short layout transition competes for the exact same frame
// budget as the UI animation. The shared panel-motion hook pauses the scene,
// then redraws once at its final dimensions.
let _layoutMotionPauseDepth = 0;
let _resumeSceneAfterLayoutMotion = false;
let _layoutMotionResumeRaf = 0;
// session id -> the name its last delegation gave it
const _liveSummaries = new Map();
let _historyParentId = null;
// What the open history view was built from, so a listing refresh that brought
// no news does not rebuild it out from under the reader.
let _historySignature = '';
let _sessionQuery = '';
// Read-only, ephemeral scheduler rows. They never enter the delegation
// adapter, session history, or persisted office state.
let _scheduledTasks = [];

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

/**
 * Lay the canvas out as wide as the stage gets with the sidebar collapsed:
 * the stage's width plus whatever the in-flow sidebar takes from the row
 * (300px open, its 1px border collapsed). That sum is the same in both
 * sidebar states, so a sidebar slide never resizes the drawing buffer (the
 * stage clips and centres it). Measured only at rest -- mid-slide the
 * sidebar is pinned out of flow.
 */
function syncCanvasSpan() {
  const stage = _container && _container.querySelector('.office-stage');
  if (!stage) return;
  let span = stage.clientWidth;
  const sidebar = document.querySelector('.sidebar');
  if (sidebar) {
    const style = getComputedStyle(sidebar);
    if (style.display !== 'none' && style.position !== 'fixed' && style.position !== 'absolute') {
      span += sidebar.getBoundingClientRect().width;
    }
  }
  stage.style.setProperty('--office-canvas-span', Math.round(span) + 'px');
}

function flushDeferredMotionWork() {
  if (_syncDeferredForMotion) { _syncDeferredForMotion = false; scheduleSync(); }
  if (_sidebarDeferredForMotion) { _sidebarDeferredForMotion = false; renderSidebar(); }
}

function pauseForLayoutMotion() {
  if (_layoutMotionResumeRaf) {
    cancelAnimationFrame(_layoutMotionResumeRaf);
    _layoutMotionResumeRaf = 0;
  }
  _layoutMotionPauseDepth += 1;
  if (_layoutMotionPauseDepth !== 1 || !_scene) return;
  _resumeSceneAfterLayoutMotion = _scene.isRunning();
  if (_resumeSceneAfterLayoutMotion) _scene.stop();
  if (typeof _scene.beginLayoutMotion === 'function') _scene.beginLayoutMotion();
}

function resumeAfterLayoutMotion() {
  if (_layoutMotionPauseDepth < 1) return;
  _layoutMotionPauseDepth -= 1;
  if (_layoutMotionPauseDepth) return;
  if (!_scene) { flushDeferredMotionWork(); return; }
  const scene = _scene;
  const shouldResume = _resumeSceneAfterLayoutMotion;
  _resumeSceneAfterLayoutMotion = false;
  // The ResizeObserver already handled the visible-width change, so this
  // resize is normally a no-op. Restarting, and the floor/sidebar updates
  // queued during the slide, wait for the settled frame to paint first.
  _layoutMotionResumeRaf = requestAnimationFrame(() => {
    _layoutMotionResumeRaf = requestAnimationFrame(() => {
      _layoutMotionResumeRaf = 0;
      if (_layoutMotionPauseDepth || _scene !== scene) return;
      syncCanvasSpan();
      if (typeof scene.endLayoutMotion === 'function') scene.endLayoutMotion();
      scene.resize();
      repositionDepartmentCards();
      if (shouldResume && !document.hidden) scene.start();
      flushDeferredMotionWork();
    });
  });
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
 * it -- the same `businessWorkerIds()` businessView() itself uses to seat a
 * desk, so the office route is answered identically on both floors. Every
 * descendant of a business-classified worker is hidden with it, even one
 * whose own goal reads as coding ("implement a landing page") -- it exists
 * because business work delegated it, so it stays in that same branch.
 *
 * Outlet-independent state -- the sidebar's live indicator, the detail
 * panel, and the Task Status column -- is untouched; this only reshapes
 * what `_scene.syncOffice()` and the floating stat cards draw.
 */
function projectsFloorView(state) {
  return projectsView(state);
}

/**
 * Push adapter state at the scene, coalesced to one call per frame. A burst
 * of parallel spawns arrives as a burst of events; rebuilding the floor once
 * per event would rebuild it a dozen times for one visual change.
 */
// Floor/card/task-panel and sidebar rebuilds requested while a side panel
// slides. They would repaint inside the moving layer (the intermittent
// stutter), so they wait and run once when the slide settles.
let _syncDeferredForMotion = false;
let _sidebarDeferredForMotion = false;

function scheduleSync() {
  if (_layoutMotionPauseDepth) { _syncDeferredForMotion = true; return; }
  if (_syncQueued || (!_scene && _officeSubview !== 'dashboard')) return;
  _syncQueued = true;
  window.requestAnimationFrame(() => {
    _syncQueued = false;
    // Queued before a slide began: it would still rebuild mid-slide.
    if (_layoutMotionPauseDepth) { _syncDeferredForMotion = true; return; }
    if (!_scene && _officeSubview !== 'dashboard') return;
    const state = activeAdapter().getState();
    if (_officeSubview === 'dashboard') {
      renderOfficeDashboard(state);
      return;
    }
    const scheduledState = (_viewMode === 'live' && _outlet === 'business')
      ? scheduledTaskState(state) : state;
    const view = _outlet === 'business' ? businessView(scheduledState, _roster) : projectsFloorView(state);
    _scene.syncOffice(view);
    renderPill(scheduledState);
    renderSummary(scheduledState);
    renderDepartmentCards(view, scheduledState);
    if (!_taskStatusDisclosureAnimating && !_tasksCollapseAnimating) renderTaskStatusPanel(scheduledState);
    else renderTaskStatusPanel(scheduledState, { skipListUpdate: true });
    // Business is first drawn from a placeholder roster while the real one
    // loads; revealing that and then rebuilding every platform a moment later
    // was the pop after the fade-in. Hold the reveal for the real roster (or
    // at most OUTLET_ROSTER_WAIT_MS).
    const rosterPending = _outlet === 'business' && !_rosterReady
      && performance.now() - _outletFadeStartedAt < OUTLET_ROSTER_WAIT_MS;
    if (_outletFadePending && !rosterPending) {
      _outletFadePending = false;
      revealAfterOutletFade();
    } else if (_outletFadePending) {
      window.setTimeout(scheduleSync, 120);
    }
  });
}

const OUTLET_ROSTER_WAIT_MS = 3000;

function scheduledTaskState(state) {
  const scheduledWorkers = _scheduledTasks.map(task => ({
    id: `scheduled:${task.profile}:${task.job_id}`,
    parentId: '__conductor__',
    label: 'Scheduled Task',
    goal: task.name,
    status: task.status || 'running',
    spawnedAt: Date.parse(task.started_at) || Date.now(),
    scheduledTask: true,
    scheduledJobId: task.job_id,
    scheduledMode: task.mode,
  }));
  return Object.assign({}, state, {
    workers: (state.workers || []).concat(scheduledWorkers),
  });
}

// The fade-out is at least this long before the reveal starts, whatever
// scheduleSync's own timing is -- a switch cheap enough to reconcile within
// a couple of frames (most Projects<->Business switches, measured) would
// otherwise remove the class before the browser ever paints the faded-out
// frame, so the whole cross-fade is invisible: add-then-remove within the
// same frame or two is a well-known case of a CSS transition never being
// observed at all, not just a short one. Matches the CSS transition's own
// .32s duration.
const OUTLET_FADE_MIN_MS = 0;

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
    if (_scene && typeof _scene.setOutletTransition === 'function') {
      _scene.setOutletTransition(false);
    }
    window.requestAnimationFrame(() => {
      if (_canvas) _canvas.classList.remove('is-switching-outlet');
      if (_deptCardsEl) {
        _deptCardsEl.classList.remove('is-fading-out');
        _deptCardsEl.classList.add('is-fading-in');
      }
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
 * roster; Projects now has its own fixed workstream roster, so its cards use
 * the explicit floor label and colour carried by the Projects view. Returns
 * null when there is nothing to show (the caller clears any existing cards
 * in that case).
 *
 * Business also includes "The Floor" overflow (roster.js's buildRoster
 * always appends it as a 7th standing entry) -- uncoloured, matching the
 * pod tint.
 */
function officeCardSpecs(view, state) {
  if (_outlet === 'business') {
    if (!_roster || !Array.isArray(_roster.departments)) return null;
    // The conductor is a platform, not a desk worker, but it should use the
    // same overview card as the named Business departments. This gives the
    // central hub a readable identity at the zoom where floor text is tiny.
    return [
      { key: '__conductor__', name: 'Conductor', color: '#7187be' },
      ..._roster.departments.map(dept => ({ key: dept.key, name: dept.name, color: dept.color })),
    ];
  }
  const projectPods = [];
  const seen = new Set();
  (view.desks || []).forEach(desk => {
    if (!desk || !desk.cluster || seen.has(desk.cluster)) return;
    seen.add(desk.cluster);
    projectPods.push({
      key: desk.cluster,
      name: desk.clusterLabel || desk.cluster,
      color: Object.prototype.hasOwnProperty.call(desk, 'clusterColor')
        ? desk.clusterColor : colorForProjectsCluster(desk.cluster),
    });
  });
  // The central conductor platform anchors the four permanent workstreams.
  return [
    { key: '__conductor__', name: 'Conductor', color: '#7187be' },
    ...projectPods,
  ];
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
  const specs = officeCardSpecs(view, state);
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
    const desks = desksByCluster.get(spec.deskCluster || spec.key) || [];
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
    // Keep the central Conductor card visually above the surrounding pod
    // cards so a subagent label never floats on top of it.
    el.style.zIndex = spec.key === '__conductor__' ? '100' : '1';
    const cardName = spec.title || spec.name;
    el.innerHTML = `
      ${spec.title ? `<div class="office-dept-card-name">${esc(spec.title)}</div>` : (spec.name ? `<div class="office-dept-card-name">${esc(spec.name)}</div>` : '')}
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
  const stageWidth = _deptCardsEl.clientWidth;
  const stageHeight = _deptCardsEl.clientHeight;
  const sceneZoom = _scene.getView().zoom;
  const scale = _labelsAdaptive ? Math.max(0.65, Math.min(1, sceneZoom)) : 1;
  // Read every position and size first, then write: interleaving them forced
  // a layout per card, on every frame of a side-panel slide.
  const plans = [];
  _deptCardEls.forEach((el, cluster) => {
    const rect = _labelsVisible ? _scene.podScreenRect(cluster) : null;
    plans.push({ el, rect, width: el.offsetWidth, height: el.offsetHeight, hidden: el.style.display === 'none' });
  });
  // Runs every frame: a write only when a value changed, so a still camera
  // costs no style recalculation or layout at all.
  const setStyle = (el, prop, value) => { if (el.style[prop] !== value) el.style[prop] = value; };
  const place = (el, rect, width, height) => {
    setStyle(el, 'left', Math.round(Math.max(width / 2 + 8, Math.min(stageWidth - width / 2 - 8, rect.x)) * 2) / 2 + 'px');
    setStyle(el, 'top', Math.round(Math.max(height + 8, Math.min(stageHeight - 8, rect.y)) * 2) / 2 + 'px');
  };
  const shown = [];
  plans.forEach(plan => {
    const { el, rect } = plan;
    if (!rect) { setStyle(el, 'display', 'none'); return; }
    setStyle(el, 'display', '');
    setStyle(el, 'transform', `translate(-50%, -100%) scale(${Math.round(scale * 1000) / 1000})`);
    if (plan.hidden) shown.push(plan); // no size until displayed: measured below
    else place(el, rect, plan.width, plan.height);
  });
  shown.forEach(plan => place(plan.el, plan.rect, plan.el.offsetWidth, plan.el.offsetHeight));
}

function renderPlatformLabelScaleButton() {
  const button = _container && _container.querySelector('#officeLabelScaleBtn');
  if (!button) return;
  button.setAttribute('aria-pressed', String(_labelsAdaptive));
  button.setAttribute('aria-label', _labelsAdaptive
    ? 'Use fixed platform label size'
    : 'Use adaptive platform label size');
  button.title = _labelsAdaptive
    ? 'Use fixed platform label size'
    : 'Use adaptive platform label size';
}

function togglePlatformLabelScale() {
  _labelsAdaptive = !_labelsAdaptive;
  renderPlatformLabelScaleButton();
  repositionDepartmentCards();
}

function togglePlatformLabels() {
  _labelsVisible = !_labelsVisible;
  const button = _container && _container.querySelector('#officeLabelsBtn');
  if (button) button.setAttribute('aria-pressed', String(_labelsVisible));
  repositionDepartmentCards();
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

/** The count badge is a concise whole-office health signal. Running work
 * wins over a completed total, so one active task cannot look settled. */
function taskStatusBadgeState(workers) {
  const counts = taskStatusCounts(workers);
  let tone = 'neutral';
  if (counts.running > 0) tone = 'running';
  else if (counts.all > 0 && counts.done === counts.all) tone = 'complete';
  return { total: counts.all, tone, done: counts.done };
}

/** A dashboard is a projection of the Office's existing truth, not a second
 * task store. The selected outlet determines exactly which seated workers it
 * can count, so Business and Projects never leak into one another. */
function dashboardHistoryWorkers(mode) {
  if (mode !== 'business' && mode !== 'projects') return [];
  const seen = new Set();
  return _historyParents.flatMap(parent => (Array.isArray(parent && parent.children) ? parent.children : [])
    .map(child => {
      const id = String(child && child.session_id || '');
      if (!id || seen.has(id)) return null;
      seen.add(id);
      return {
        id, parentId: String(child.parent_session_id || parent.parent_session_id || ''),
        childSessionId: id, dashboardParentId: String(parent.parent_session_id || ''),
        goal: child.title || parent.title || 'Delegated task', label: child.title || 'Delegated task',
        status: child.status || 'completed', spawnedAt: Number(child.started_at || 0) * 1000,
        endedAt: child.ended_at ? Number(child.ended_at) * 1000 : 0, historical: true,
      };
    }).filter(Boolean));
}

function officeDashboardModel(state, outlet) {
  const source = state || {};
  const mode = outlet === 'business' ? 'business' : 'projects';
  const historicalWorkers = dashboardHistoryWorkers(mode);
  const liveWorkers = Array.isArray(source.workers) ? source.workers : [];
  const byId = new Map(historicalWorkers.map(worker => [worker.id, worker]));
  liveWorkers.forEach(worker => { if (worker && worker.id) byId.set(worker.id, worker); });
  const workers = Array.from(byId.values());
  const selectedView = mode === 'business'
    ? businessView({ workers }, _roster) : projectsFloorView({ workers });
  const visibleIds = new Set((selectedView.desks || [])
    .map(desk => desk && desk.workerId).filter(Boolean));
  const scopedWorkers = workers.filter(worker => worker && visibleIds.has(worker.id));
  const floorMap = new Map();
  (selectedView.desks || []).forEach(desk => {
    if (!desk || !desk.cluster) return;
    if (!floorMap.has(desk.cluster)) {
      floorMap.set(desk.cluster, {
        key: desk.cluster, name: desk.clusterLabel || desk.cluster,
        color: desk.clusterColor || colorForProjectsCluster(desk.cluster), workers: [],
      });
    }
    const worker = scopedWorkers.find(item => item.id === desk.workerId);
    if (worker) floorMap.get(desk.cluster).workers.push(worker);
  });
  const floors = Array.from(floorMap.values()).map(floor => {
    const counts = taskStatusCounts(floor.workers);
    return Object.assign(floor, { active: counts.running, completed: counts.done });
  });
  const counts = taskStatusCounts(scopedWorkers);
  const liveScopedWorkers = scopedWorkers.filter(worker => !worker.historical);
  const liveCounts = taskStatusCounts(liveScopedWorkers);
  const attention = liveScopedWorkers.filter(worker => {
    const bucket = taskStatusBucket(worker.status);
    return bucket === 'stopped' || bucket === 'other';
  });
  const baselineAgents = mode === 'business' ? 21 : 4;
  return {
    mode, workers: scopedWorkers, floors, attention,
    snapshot: { agents: Math.max(baselineAgents, liveScopedWorkers.length), active: liveCounts.running, completed: counts.done, attention: attention.length },
    live: liveScopedWorkers.filter(worker => worker.status === 'running'),
    recent: scopedWorkers.filter(worker => taskStatusBucket(worker.status) === 'done')
      .sort((a, b) => (b.endedAt || b.spawnedAt || 0) - (a.endedAt || a.spawnedAt || 0)).slice(0, 6),
  };
}

function dashboardAttentionItems(model) {
  const queued = Array.from(_dashboardAttentionBySession.values()).filter(item => item && item.mode === model.mode);
  return queued.map(item => Object.assign({}, item, {
    worker: model.workers.find(worker => worker.childSessionId === item.sessionId
      || worker.dashboardParentId === item.sessionId || worker.id === item.sessionId),
  })).concat(model.attention.map(worker => ({ kind: 'status', worker })));
}

function scrollDashboardPanelIntoView(key) {
  const panel = document.querySelector(`[data-dashboard-panel="${key}"]`);
  if (!panel) return;
  panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
  panel.classList.remove('office-dashboard-panel-focus');
  void panel.offsetWidth;
  panel.classList.add('office-dashboard-panel-focus');
  window.setTimeout(() => panel.classList.remove('office-dashboard-panel-focus'), 1450);
}

async function dashboardMetricAction(action, model) {
  if (action === 'agents') {
    transitionDashboardToFloor(model.mode);
    return;
  }
  if (action === 'active') {
    const scheduled = model.live.find(worker => worker.scheduledTask && worker.scheduledJobId);
    if (scheduled) {
      if (typeof window.switchPanel === 'function') await window.switchPanel('tasks');
      if (typeof window.openCronDetail === 'function') window.openCronDetail(scheduled.scheduledJobId);
      return;
    }
    const worker = model.live[0];
    if (worker) {
      openDashboardWorker(worker, model.mode);
      return;
    }
    transitionDashboardToFloor(model.mode);
    return;
  }
  if (action === 'completed') scrollDashboardPanelIntoView('completed');
  if (action === 'attention') scrollDashboardPanelIntoView('attention');
}

function dashboardAttentionCard(item) {
  if (item.kind === 'status') return dashboardWorkerRow(item.worker, 'is-attention');
  const pending = item.pending || {};
  const title = esc(pending.question || pending.command || pending.description || 'Decision required');
  const choices = item.kind === 'clarify' && Array.isArray(pending.choices_offered) ? pending.choices_offered : [];
  const controls = item.kind === 'approval'
    ? ['once', 'session', 'always'].map(choice => `<button type="button" class="office-dashboard-attention-action" data-attention-choice="${choice}" data-attention-session="${esc(item.sessionId)}" data-attention-kind="approval" data-attention-id="${esc(pending.approval_id || '')}">${choice === 'once' ? 'Allow once' : choice === 'session' ? 'Allow this session' : 'Always allow'}</button>`).join('')
    : choices.length
      ? choices.map(choice => `<button type="button" class="office-dashboard-attention-action" data-attention-choice="${esc(choice)}" data-attention-session="${esc(item.sessionId)}" data-attention-kind="clarify" data-attention-id="${esc(pending.clarify_id || '')}">${esc(choice)}</button>`).join('')
      : `<input class="office-dashboard-attention-input" data-attention-input="1" placeholder="Type a response"><button type="button" class="office-dashboard-attention-action" data-attention-choice="__input__" data-attention-session="${esc(item.sessionId)}" data-attention-kind="clarify" data-attention-id="${esc(pending.clarify_id || '')}">Send response</button>`;
  // Answers go through profile-guarded endpoints, so a chat from another
  // profile is opened (which switches profile) rather than answered here.
  const actions = item.sameProfile === false
    ? `<button type="button" class="office-dashboard-attention-action" data-attention-open="${esc(item.sessionId)}">Open chat</button>`
    : controls;
  const where = item.sameProfile === false && item.profile ? ` <em class="office-dashboard-attention-profile">${esc(item.profile)}</em>` : '';
  return `<article class="office-dashboard-attention-card" role="button" tabindex="0" data-attention-focus="1" data-attention-session="${esc(item.sessionId)}"><div><span>${item.kind === 'approval' ? 'Permission required' : 'Answer needed'}${where}</span><strong>${title}</strong></div><div class="office-dashboard-attention-actions">${actions}</div></article>`;
}

async function respondDashboardAttention(button) {
  const kind = button.dataset.attentionKind;
  const sessionId = button.dataset.attentionSession;
  let value = button.dataset.attentionChoice || '';
  if (value === '__input__') value = String(button.closest('.office-dashboard-attention-card')?.querySelector('[data-attention-input]')?.value || '').trim();
  if (!sessionId || !value) return;
  button.disabled = true;
  try {
    const body = kind === 'approval'
      ? { session_id: sessionId, choice: value, approval_id: button.dataset.attentionId || '' }
      : { session_id: sessionId, response: value, clarify_id: button.dataset.attentionId || '' };
    const result = await request(kind === 'approval' ? '/api/approval/respond' : '/api/clarify/respond', {
      method: 'POST', body: JSON.stringify(body), timeoutToast: false,
    });
    if (!result || !result.ok) throw new Error('Response was not accepted');
    _dashboardAttentionBySession.delete(sessionId);
    scheduleSync();
  } catch (err) {
    button.disabled = false;
    toast(err && err.message ? err.message : 'Could not send the response');
  }
}

function dashboardWorkerRow(worker, tone) {
  const label = esc(worker.goal || worker.label || 'Subagent');
  return `<button type="button" class="office-dashboard-worker" data-dashboard-worker-id="${esc(worker.id)}">
    <span class="office-dashboard-worker-dot ${tone}" aria-hidden="true"></span><span>${label}</span>
    <small>${esc(worker.status || '')}</small></button>`;
}

function dashboardPrefersReducedMotion() {
  return typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** Leave the dashboard deliberately, then let the destination floor animate in. */
function transitionDashboardToFloor(outlet, after) {
  const reveal = () => {
    setOfficeSubview('floor');
    if (outlet === 'business') setOutlet('business');
    const container = document.getElementById('officeWrap');
    if (container && !dashboardPrefersReducedMotion()) {
      container.classList.add('office-dashboard-floor-enter');
      window.setTimeout(() => container.classList.remove('office-dashboard-floor-enter'), 360);
    }
    window.requestAnimationFrame(() => { if (typeof after === 'function') after(); });
  };
  const dashboard = document.querySelector('.office-subview');
  if (!dashboard || dashboardPrefersReducedMotion()) {
    reveal();
    return;
  }
  dashboard.classList.add('office-dashboard-transitioning');
  window.setTimeout(reveal, 180);
}

function openDashboardWorker(worker, outlet) {
  if (!worker) {
    transitionDashboardToFloor(outlet);
    return;
  }
  transitionDashboardToFloor(outlet, () => {
    if (worker.historical && worker.dashboardParentId) {
      showHistory(worker.dashboardParentId);
      if (outlet === 'business') setOutlet('business');
    }
    selectTask(worker.id, true);
  });
}

function openDashboardAttention(item, model) {
  if (item && item.worker) { openDashboardWorker(item.worker, model.mode); return; }
  if (item && item.sessionId) openAttentionChat(item.sessionId);
}

// loadSession() switches to the chat's profile when it belongs to another one.
function openAttentionChat(sessionId) {
  if (typeof window.loadSession === 'function') window.loadSession(sessionId);
  if (typeof window.switchPanel === 'function') window.switchPanel('chat');
}

// Work distribution can open one floor's completed tasks inside the card.
// Kept per outlet so a re-render (every live sync) does not close it.
let _dashboardFloorDetail = null; // { outlet, key }

function dashboardFloorDetailKey(model) {
  if (!_dashboardFloorDetail || _dashboardFloorDetail.outlet !== model.mode) return null;
  return model.floors.some(floor => floor.key === _dashboardFloorDetail.key) ? _dashboardFloorDetail.key : null;
}

function dashboardDistributionPanel(model) {
  const openKey = dashboardFloorDetailKey(model);
  const floor = openKey ? model.floors.find(item => item.key === openKey) : null;
  if (floor) {
    const done = floor.workers.filter(worker => taskStatusBucket(worker.status) === 'done')
      .sort((a, b) => (b.endedAt || b.spawnedAt || 0) - (a.endedAt || a.spawnedAt || 0));
    return `<article class="office-dashboard-panel office-dashboard-distribution is-floor-detail" data-dashboard-panel="distribution">
      <div class="office-dashboard-panel-head"><button type="button" class="office-dashboard-floor-back" data-dashboard-floor-back aria-label="Back to all floors" title="Back to all floors"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M10.6 4.6a1.2 1.2 0 0 1 1.75 1.64L7.86 10.8H19a1.2 1.2 0 0 1 0 2.4H7.86l4.49 4.56a1.2 1.2 0 1 1-1.75 1.64l-6.3-6.4a1.5 1.5 0 0 1 0-2.08z"/></svg></button>
      <h2 class="office-dashboard-floor-title"><span class="office-dashboard-floor-dot" style="background:${esc(floor.color || 'var(--accent)')}"></span>${esc(floor.name)}</h2>
      <span>${done.length} completed</span></div>
      <div class="office-dashboard-panel-body office-dashboard-floor-detail">${done.length
        ? done.map(worker => dashboardWorkerRow(worker, 'is-done')).join('')
        : `<div class="office-dashboard-empty">No completed tasks on ${esc(floor.name)} yet.</div>`}</div></article>`;
  }
  return `<article class="office-dashboard-panel office-dashboard-distribution" data-dashboard-panel="distribution"><div class="office-dashboard-panel-head"><h2>Work distribution</h2><span>${model.floors.length} floor${model.floors.length === 1 ? '' : 's'}</span></div><div class="office-dashboard-panel-body">${model.floors.length
    ? model.floors.map(item => `<button type="button" class="office-dashboard-floor" data-dashboard-floor="${esc(item.key)}" aria-label="${esc(item.name)}: show completed tasks"><span class="office-dashboard-floor-dot" style="background:${esc(item.color || 'var(--accent)')}"></span><span><strong>${esc(item.name)}</strong><small>${item.workers.length} assigned</small></span><small>${item.active} active · ${item.completed} done</small><span class="office-dashboard-floor-chevron" aria-hidden="true">›</span></button>`).join('')
    : '<div class="office-dashboard-empty">No delegated work in this office yet.</div>'}</div></article>`;
}

function bindDashboardDistribution(host, state) {
  const card = host.querySelector('[data-dashboard-panel="distribution"]');
  if (!card) return;
  const rerender = focusSelector => {
    renderOfficeDashboard(state);
    const target = focusSelector && document.querySelector(focusSelector);
    if (target) target.focus({ preventScroll: true });
  };
  card.querySelectorAll('[data-dashboard-floor]').forEach(button => {
    button.onclick = () => {
      _dashboardFloorDetail = { outlet: _outlet, key: button.dataset.dashboardFloor };
      rerender('[data-dashboard-floor-back]');
    };
  });
  const back = card.querySelector('[data-dashboard-floor-back]');
  if (back) {
    const key = _dashboardFloorDetail && _dashboardFloorDetail.key;
    const close = () => {
      _dashboardFloorDetail = null;
      rerender(key ? `[data-dashboard-floor="${CSS.escape(key)}"]` : null);
    };
    back.onclick = close;
    card.onkeydown = event => { if (event.key === 'Escape') { event.stopPropagation(); close(); } };
  }
}

function renderOfficeDashboard(state) {
  const host = document.getElementById('officeDashboardContent');
  if (!host) return;
  const dashboardState = _outlet === 'business' ? scheduledTaskState(state) : state;
  const model = officeDashboardModel(dashboardState, _outlet);
  const modeLabel = model.mode === 'business' ? 'Business Office' : 'Projects Office';
  const metrics = [
    ['agents', 'Agents', model.snapshot.agents, 'People currently seated on this floor'],
    ['active', 'Active work', model.snapshot.active, 'Tasks in progress'],
    ['completed', 'Completed', model.snapshot.completed, 'Finished tasks'],
    ['attention', 'Needs attention', model.snapshot.attention, 'Stopped or unknown work'],
  ];
  const rows = (items, tone, empty) => items.length
    ? items.map(worker => dashboardWorkerRow(worker, tone)).join('')
    : `<div class="office-dashboard-empty">${empty}</div>`;
  const attentionItems = dashboardAttentionItems(model);
  host.innerHTML = `<div class="office-dashboard-toolbar"><span>${modeLabel}</span><div class="office-outlet" role="group" aria-label="Dashboard outlet">
    <button type="button" class="office-outlet-btn${_outlet === 'projects' ? ' is-active' : ''}" data-dashboard-outlet="projects">Projects</button>
    <button type="button" class="office-outlet-btn${_outlet === 'business' ? ' is-active' : ''}" data-dashboard-outlet="business">Business</button>
  </div></div>
  <section class="office-dashboard-snapshot">${metrics.map(([action, label, value, detail]) => `<button type="button" class="office-dashboard-metric" data-dashboard-metric-action="${action}"><span>${label}</span><strong data-count-key="office-${model.mode}-${action}">${value}</strong><small>${detail}</small></button>`).join('')}</section>
  <section class="office-dashboard-grid">${dashboardDistributionPanel(model)}
  <article class="office-dashboard-panel"><div class="office-dashboard-panel-head"><h2>Live delegation</h2><span>${model.live.length} active</span></div><div class="office-dashboard-panel-body">${rows(model.live, 'is-live', 'No active delegation right now.')}</div></article>
  <article class="office-dashboard-panel office-dashboard-attention" data-dashboard-panel="attention"><div class="office-dashboard-panel-head"><h2>Attention required</h2><span>${attentionItems.length} item${attentionItems.length === 1 ? '' : 's'}</span></div><div class="office-dashboard-panel-body">${attentionItems.length ? attentionItems.map(dashboardAttentionCard).join('') : '<div class="office-dashboard-empty">Everything is on track.</div>'}</div></article>
  <article class="office-dashboard-panel" data-dashboard-panel="completed"><div class="office-dashboard-panel-head"><h2>Recent completions</h2><span>${model.recent.length} shown</span></div><div class="office-dashboard-panel-body">${rows(model.recent, 'is-done', 'Completed work will appear here.')}</div></article>
  <button type="button" class="office-dashboard-integration" onclick="officeSetSubview('integrations')">${officeIcon('settings', 'Integrations')}<span><strong>Integration health</strong><small>Gmail is ready for setup in the Email floor.</small></span><span aria-hidden="true">›</span></button></section>`;
  host.querySelectorAll('[data-dashboard-outlet]').forEach(button => {
    button.onclick = () => setOutlet(button.dataset.dashboardOutlet);
  });
  bindDashboardDistribution(host, state);
  if (typeof window.animateCounts === 'function') window.animateCounts(host);
  host.querySelectorAll('[data-dashboard-worker-id]').forEach(button => {
    button.onclick = () => openDashboardWorker(model.workers.find(worker => worker.id === button.dataset.dashboardWorkerId), model.mode);
  });
  host.querySelectorAll('[data-dashboard-metric-action]').forEach(button => {
    button.onclick = () => dashboardMetricAction(button.dataset.dashboardMetricAction, model);
  });
  host.querySelectorAll('[data-attention-open]').forEach(button => {
    button.onclick = (event) => { event.stopPropagation(); openAttentionChat(button.dataset.attentionOpen); };
  });
  host.querySelectorAll('[data-attention-choice]').forEach(button => {
    button.onclick = (event) => { event.stopPropagation(); respondDashboardAttention(button); };
  });
  host.querySelectorAll('[data-attention-input]').forEach(input => {
    input.onclick = (event) => event.stopPropagation();
  });
  host.querySelectorAll('[data-attention-focus]').forEach(card => {
    const open = () => openDashboardAttention(
      attentionItems.find(item => item.sessionId === card.dataset.attentionSession), model,
    );
    card.onclick = open;
    card.onkeydown = (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        open();
      }
    };
  });
}

function defaultOfficeIntegrations() {
  return [{ provider: 'gmail', floor: 'emails', status: 'disconnected',
    capabilities: ['search_read', 'summarize', 'draft_reply'], send_requires_approval: true }];
}

function renderOfficeIntegrations(payload) {
  const host = document.getElementById('officeIntegrationsContent');
  if (!host) return;
  const integrations = payload && Array.isArray(payload.integrations)
    ? payload.integrations : defaultOfficeIntegrations();
  const gmail = integrations.find(item => item && item.provider === 'gmail') || defaultOfficeIntegrations()[0];
  const connected = gmail.status === 'connected';
  host.innerHTML = `<div class="office-integrations-intro"><span>BUSINESS OFFICE</span><p>Connections are assigned to a floor and expose only the capabilities you approve.</p></div>
  <section class="office-integrations-grid"><article class="office-integration-card"><div class="office-integration-card-head"><span class="office-integration-provider-icon"><img src="/static/office-integration-gmail.png" alt="" aria-hidden="true"></span><span><h2>Gmail</h2><p>Email floor</p></span><span class="office-integration-status ${connected ? 'is-connected' : ''}">${connected ? 'Connected' : 'Not connected'}</span></div>
    <p class="office-integration-copy">Search, summarize, and draft replies for the Email floor. Sending will always require your approval.</p>
    <div class="office-integration-actions"><button type="button" class="office-integration-action" disabled title="Google OAuth setup is required before an account can be connected">Google OAuth setup required</button><button type="button" class="office-integration-settings" disabled aria-label="Configure Gmail integration" title="Gmail configuration will be available after OAuth setup">${officeIcon('settings', 'Configure Gmail integration')}</button></div></article>
  ${[['Marketing', 'Choose a platform when you are ready to connect campaign or social tools.', 'Choose marketing platform'], ['Operations', 'Calendar and operations providers will be configured here.', 'Choose operations provider'], ['Documents', 'Document storage providers will be configured here.', 'Choose document provider']].map(([name, copy, action]) => `<article class="office-integration-card is-future"><div class="office-integration-card-head"><span class="office-integration-provider-icon"><img src="/static/office-integration-${name.toLowerCase()}.png" alt="" aria-hidden="true"></span><span><h2>${name}</h2><p>Future integration</p></span></div><p class="office-integration-copy">${copy}</p><div class="office-integration-actions"><button type="button" class="office-integration-action" disabled title="Provider setup will be available in a future update">${action}</button><button type="button" class="office-integration-settings" disabled aria-label="Configure ${name} integration" title="Configuration will be available after a provider is selected">${officeIcon('settings', `Configure ${name} integration`)}</button></div></article>`).join('')}</section>`;
}

function loadOfficeIntegrations() {
  renderOfficeIntegrations({ integrations: defaultOfficeIntegrations() });
  request('/api/office/integrations', { timeoutToast: false })
    .then(renderOfficeIntegrations)
    .catch(() => renderOfficeIntegrations({ integrations: defaultOfficeIntegrations() }));
}

/**
 * The Task Status card collapses to its compact label row -- the filters and
 * list stay in the DOM (so a collapse never has to rebuild them), only their
 * visibility follows the state. Remembered per-browser so the chosen view
 * persists across Office visits.
 */
// A Task Status disclosure is a compact operational control, not a slow page
// transition. Its CSS owns one grid disclosure; this duration also
// gates live refreshes so a repaint cannot disturb that single motion.
const TASK_STATUS_TRANSITION_MS = 480;

function renderTasksCollapse() {
  if (!_tasksEl || !_tasksCollapseBtnEl) return;
  const body = document.getElementById('officeTasksBody');
  // Keep a committed 0fr state for one frame before opening. Grid calculates
  // the natural content height itself, so the list never receives a changing
  // inline height on every animation frame.
  const opening = !_tasksCollapsed && _tasksEl.classList.contains('is-collapsed');
  if (opening && body) {
    void body.offsetHeight;
    window.requestAnimationFrame(() => {
      if (!_tasksEl || _tasksCollapsed) return;
      _tasksEl.classList.remove('is-collapsed');
    });
  } else {
    _tasksEl.classList.toggle('is-collapsed', _tasksCollapsed);
  }
  _tasksCollapseBtnEl.setAttribute('aria-expanded', String(!_tasksCollapsed));
  _tasksCollapseBtnEl.setAttribute('aria-label', _tasksCollapsed ? 'Expand Task Status' : 'Collapse Task Status');
  _tasksCollapseBtnEl.title = _tasksCollapsed ? 'Show Task Status' : 'Collapse Task Status';
}

function toggleTasksCollapsed() {
  if (_tasksCollapseTimer) clearTimeout(_tasksCollapseTimer);
  const collapsing = !_tasksCollapsed;
  _tasksCollapsed = collapsing;
  writeTasksCollapsed(_tasksCollapsed);
  renderTasksCollapse();
  _tasksCollapseAnimating = true;
  _tasksCollapseTimer = setTimeout(() => {
    _tasksCollapseAnimating = false;
    _tasksCollapseTimer = null;
    scheduleSync();
  }, TASK_STATUS_TRANSITION_MS);
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
  _tasksListEl.innerHTML = ordered.map(w => {
    const selected = w.id === _selectedId;
    return `<div class="office-tasks-row${selected ? ' is-selected' : ''}" data-worker-id="${esc(w.id)}">
    <button type="button" class="office-tasks-row-select" aria-expanded="${selected}">
      <span class="office-tasks-row-status status-${esc(taskStatusBucket(w.status))}" aria-hidden="true"></span>
      <span class="office-tasks-row-body">
        <span class="office-tasks-row-goal">${esc(w.scheduledTask ? 'Scheduled Task' : (w.goal || w.label || 'Subagent'))}</span>
        <span class="office-tasks-row-meta">${esc(w.status || '')}${taskStatusAge(w) ? ' · ' + esc(taskStatusAge(w)) : ''}</span>
      </span>
    </button>
    <div class="office-tasks-row-detail"${selected ? '' : ' inert'}>
      <div class="office-tasks-row-detail-inner">${taskStatusDetailHtml(w, _lastTaskStatusWorkers)}</div>
    </div>
  </div>`;
  }).join('');
  _tasksListEl.querySelectorAll('.office-tasks-row').forEach(row => {
    const focusRow = () => {
      selectTask(row.dataset.workerId, false);
      if (_scene && typeof _scene.focusOnWorker === 'function') _scene.focusOnWorker(row.dataset.workerId);
    };
    // Keep the row itself keyboard/test-script friendly while the nested
    // button remains the real pointer target for the compact summary.
    row.onclick = event => { if (event.target === row) focusRow(); };
    const select = row.querySelector('.office-tasks-row-select');
    if (select) select.onclick = focusRow;
    const close = row.querySelector('.office-tasks-row-detail-close');
    if (close) close.onclick = () => clearTaskSelection();
    const worker = _lastTaskStatusWorkers.find(w => w.id === row.dataset.workerId);
    const open = row.querySelector('[data-action="open-session"]');
    if (open && worker) open.onclick = () => openWorkerSession(worker);
    const interrupt = row.querySelector('[data-action="interrupt"]');
    if (interrupt && worker) interrupt.onclick = () => interruptWorker(worker.id);
    const branch = row.querySelector('[data-action="interrupt-branch"]');
    if (branch && worker) {
      const descendants = descendantsOf(worker.id, _lastTaskStatusWorkers)
        .filter(w => !TERMINAL.has(w.status)).map(w => w.id);
      branch.onclick = () => interruptBranch(worker.id, descendants);
    }
  });
}

function syncTaskStatusDisclosure() {
  if (!_tasksListEl) return false;
  let changed = false;
  _tasksListEl.querySelectorAll('.office-tasks-row').forEach(row => {
    const selected = row.dataset.workerId === _selectedId;
    if (row.classList.contains('is-selected') === selected) return;
    changed = true;
    row.classList.toggle('is-selected', selected);
    const button = row.querySelector('.office-tasks-row-select');
    if (button) button.setAttribute('aria-expanded', selected ? 'true' : 'false');
    const detail = row.querySelector('.office-tasks-row-detail');
    if (detail) detail.inert = !selected;
  });
  if (!changed) return false;
  _taskStatusDisclosureAnimating = true;
  if (_taskStatusDisclosureTimer) clearTimeout(_taskStatusDisclosureTimer);
  _taskStatusDisclosureTimer = setTimeout(() => {
    _taskStatusDisclosureTimer = null;
    _taskStatusDisclosureAnimating = false;
    scheduleSync();
  }, 300);
  return true;
}

function selectTask(id, focus) {
  if (_selectedId === id) {
    // A second click is a disclosure toggle, not a request to leave the desk.
    // Keep the camera where it is and only collapse the inline task details.
    _selectedId = null;
    syncTaskStatusDisclosure();
    scheduleSync();
    return;
  }
  const worker = _lastTaskStatusWorkers.find(w => w.id === id)
    || (activeAdapter().getState().workers || []).find(w => w.id === id);
  if (!worker) return;
  _selectedId = id;
  if (_tasksFilter !== 'all' && taskStatusBucket(worker.status) !== _tasksFilter) {
    _tasksFilter = 'all';
    renderTaskStatusFilters();
    renderTaskStatusList(_lastTaskStatusWorkers);
  }
  if (_tasksCollapsed) {
    _tasksCollapsed = false;
    writeTasksCollapsed(false);
    renderTasksCollapse();
  }
  if (focus && _scene && typeof _scene.focusOnWorker === 'function') {
    _scene.focusOnWorker(id);
  }
  syncTaskStatusDisclosure();
  scheduleSync();
}

function clearTaskSelection() {
  _selectedId = null;
  syncTaskStatusDisclosure();
  if (_scene) _scene.resetView();
  scheduleSync();
}

function renderTaskStatusBadge(workers) {
  if (!_tasksCountEl) return;
  const badge = taskStatusBadgeState(workers);
  const justCompleted = _lastTaskStatusDoneCount !== null
    && badge.done > _lastTaskStatusDoneCount;
  _lastTaskStatusDoneCount = badge.done;
  _tasksCountEl.dataset.count = String(badge.total);
  _tasksCountEl.textContent = String(badge.total);
  _tasksCountEl.classList.toggle('is-running', badge.tone === 'running');
  _tasksCountEl.classList.toggle('is-complete', badge.tone === 'complete');
  if (!justCompleted) return;
  if (_taskCompletionTimer) clearTimeout(_taskCompletionTimer);
  _tasksCountEl.classList.remove('is-completion-flash');
  void _tasksCountEl.offsetWidth;
  _tasksCountEl.innerHTML = typeof window.WorkHubIcons === 'function'
    ? window.WorkHubIcons('sparkles', 'Task completed')
    : '<span aria-label="Task completed">✦</span>';
  _tasksCountEl.classList.add('is-completion-flash');
  _taskCompletionTimer = setTimeout(() => {
    if (_tasksCountEl) {
      _tasksCountEl.classList.remove('is-completion-flash');
      _tasksCountEl.textContent = _tasksCountEl.dataset.count || '0';
    }
    _taskCompletionTimer = null;
  }, 2400);
}

function renderTaskStatusPanel(state, opts) {
  const options = opts || {};
  const workers = state.workers || [];
  renderTaskStatusBadge(workers);
  if (options.skipListUpdate) return;
  renderTaskStatusFilters();
  renderTaskStatusList(workers);
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

function officeIcon(name, label) {
  return typeof window.WorkHubIcons === 'function'
    ? window.WorkHubIcons(name, label)
    : '';
}

function renderOfficeNavigation() {
  const nav = document.getElementById('officePageNav');
  if (!nav) return;
  const pages = [
    ['dashboard', '/static/office-dashboard-tool.png', 'Dashboard', 'Office overview'],
    ['integrations', '/static/office-integrations-tool.png', 'Integrations', 'Connected accounts'],
  ];
  pages.forEach(([key, iconSrc, label, detail]) => {
    const button = nav.querySelector(`[data-office-subview="${key}"]`);
    if (!button) return;
    button.classList.toggle('is-active', _officeSubview === key);
    button.setAttribute('aria-current', _officeSubview === key ? 'page' : 'false');
    button.innerHTML = `<span class="office-page-nav-icon"><img class="office-page-nav-image" src="${iconSrc}" alt="" aria-hidden="true"></span><span class="office-page-nav-copy"><strong>${label}</strong><small>${detail}</small></span><span class="office-page-nav-arrow" aria-hidden="true">›</span>`;
  });
}

function resetOfficeToDefault({ render = false } = {}) {
  const shouldRenderFloor = render && _officeSubview !== 'floor';
  _officeSubview = 'floor';
  _outlet = 'projects';
  _viewMode = 'live';
  _historyAdapter = null;
  _historyParentId = null;
  _historySignature = '';
  _selectedId = null;
  writeOutlet(_outlet);
  renderOfficeNavigation();
  renderOutletSwitch();
  if (shouldRenderFloor) {
    const container = document.getElementById('officeWrap');
    if (container) renderOfficeSubview(container);
  }
}

function renderOfficeSubview(container) {
  if (!container) return;
  if (_officeSubview === 'floor') {
    mount(container);
    return;
  }
  if (_container) {
    _preserveOfficeNavigationOnUnmount = true;
    unmount();
  }
  const isDashboard = _officeSubview === 'dashboard';
  const title = isDashboard ? 'Office Dashboard' : 'Office Integrations';
  const eyebrow = isDashboard ? 'OFFICE OVERVIEW' : 'CONNECTED WORKSPACE';
  const description = isDashboard
    ? 'A live view of delegation, workload, and what needs attention.'
    : 'Manage the accounts and capabilities available to Business Office floors.';
  container.innerHTML = `<section class="office-subview office-${_officeSubview}" aria-labelledby="officeSubviewTitle">
    <div class="office-subview-head">
      <div><div class="office-subview-eyebrow">${eyebrow}</div><h1 id="officeSubviewTitle">${title}</h1><p>${description}</p></div>
      <button type="button" class="office-subview-back" aria-label="Return to the Office floor" title="Return to the Office floor" onclick="officeSetSubview('floor')">${officeIcon('arrow-left', 'Return to the Office floor')}</button>
    </div>
    ${isDashboard ? '<div id="officeDashboardContent"></div>' : '<div id="officeIntegrationsContent"></div>'}
  </section>`;
  if (isDashboard) renderOfficeDashboard(activeAdapter().getState());
  else loadOfficeIntegrations();
}

function setOfficeSubview(name) {
  const next = name === 'dashboard' || name === 'integrations' ? name : 'floor';
  if (next === 'floor') resetOfficeToDefault();
  else _officeSubview = next;
  renderOfficeNavigation();
  const container = document.getElementById('officeWrap');
  if (container) renderOfficeSubview(container);
  // Keep the sub-page in the URL so a reload reopens it (panels.js restores it).
  try {
    if (/^#office(\/|$)/.test(window.location.hash || '')) {
      const route = next === 'floor' ? '#office' : '#office/' + next;
      window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search + route);
    }
  } catch (_) {}
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
  if (_scene && typeof _scene.setOutletTransition === 'function') {
    _scene.setOutletTransition(true);
  }
  if (_deptCardsEl) {
    _deptCardsEl.classList.remove('is-fading-in');
    _deptCardsEl.classList.add('is-fading-out');
  }
  _outletFadeStartedAt = performance.now();
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
  _rosterReady = true;
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
  _pauseBtnEl.textContent = 'View live';
  _pauseBtnEl.classList.remove('is-paused');
  _pauseBtnEl.hidden = false;
}

function taskStatusDetailHtml(worker, workers) {
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
    ? descendantsOf(worker.id, workers || []).filter(w => !TERMINAL.has(w.status))
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

  return `
    <div class="office-tasks-row-detail-head">
      <span class="office-detail-title">${esc(worker.label)}</span>
      <button type="button" class="office-tasks-row-detail-close" aria-label="Close task details">×</button>
    </div>
    ${rows.join('')}
    ${worker.goal ? `<div class="office-detail-block"><div class="office-detail-label">Goal</div><div class="office-detail-goal">${esc(worker.goal)}</div></div>` : ''}
    ${tool}
    ${worker.summary ? `<div class="office-detail-block"><div class="office-detail-label">Summary</div><div class="office-detail-goal">${esc(worker.summary)}</div></div>` : ''}
    ${tail}
    ${files}
    ${actions.length ? `<div class="office-detail-actions">${actions.join('')}</div>` : ''}
  `;
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
    if (_viewMode === 'live' && _outlet === 'business') {
      try {
        const scheduled = await request('/api/office/scheduled-tasks', { timeoutToast: false });
        _scheduledTasks = Array.isArray(scheduled && scheduled.tasks) ? scheduled.tasks : [];
      } catch (_scheduledError) {
        // Do not erase the last valid snapshot because one read failed.
      }
    }
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
  resetOfficeToDefault({ render: true });
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
  resetOfficeToDefault({ render: true });
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
  // Project-scoped runs belong in the Project Folders section above. Keep
  // this history list for unfiled chats so a run is never duplicated.
  const entries = sidebarEntries().filter(parent => !parent.project_id);
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

function renderProjectFolders(projects, parents) {
  const host = document.getElementById('officeProjectFolders');
  if (!host) return;
  // Keep the existing filter node and its handlers while placing it in the
  // workspace context, between the labelled divider and the folder rows.
  const searchWrap = document.getElementById('officeSearch')?.closest('.session-search');
  const list = Array.isArray(projects) ? projects : [];
  const signature = JSON.stringify(list.map(project => ({
    id: project.project_id,
    name: project.name,
    color: project.color,
    rows: (parents || []).filter(parent => parent.project_id === project.project_id).map(parent => ({
      id: parent.parent_session_id,
      title: parent.title,
      children: Array.isArray(parent.children) ? parent.children.length : 0,
    })),
  })));
  if (signature === _projectFoldersSignature) return;
  const delay = _projectFoldersAnimationUntil - performance.now();
  if (delay > 0) {
    if (_projectFoldersDeferredTimer) clearTimeout(_projectFoldersDeferredTimer);
    _projectFoldersDeferredTimer = setTimeout(() => {
      _projectFoldersDeferredTimer = null;
      renderProjectFolders(_officeProjects, _historyParents);
    }, delay);
    return;
  }
  _projectFoldersSignature = signature;
  host.innerHTML = `<div class="office-project-folders-title"><span>WORKSPACES</span></div>
    <div class="project-folder-list">${list.length ? list.map(project => {
      const rows = (parents || []).filter(parent => parent.project_id === project.project_id);
      const expanded = _expandedProjectIds.has(project.project_id);
      const taskRows = rows.length ? rows.map(parent => {
        const count = Array.isArray(parent.children) ? parent.children.length : 0;
        return `<button type="button" class="office-session-row" data-parent-id="${esc(parent.parent_session_id)}">
          <span class="office-session-text"><span class="office-session-title">${esc(parent.title || 'Untitled chat')}</span>
          <span class="office-session-meta">${count} delegated task${count === 1 ? '' : 's'}</span></span></button>`;
      }).join('') : '<div class="project-folder-empty">No delegated tasks yet.</div>';
      return `<button type="button" class="project-chip project-folder-row office-project-folder" data-project-id="${esc(project.project_id)}">
        <span class="project-folder-chevron${expanded ? ' expanded' : ''}">›</span><span class="color-dot" style="background:${esc(project.color || 'var(--accent)')}"></span>
        <span class="project-folder-name">${esc(project.name)}</span><span class="project-folder-count">${rows.length}</span></button>
        <div class="project-folder-sessions${expanded ? ' expanded' : ''}"><div class="project-folder-sessions-inner">${taskRows}</div></div>`;
    }).join('') : '<div class="project-folder-empty">No projects configured.</div>'}</div>`;
  if (searchWrap) host.insertBefore(searchWrap, host.querySelector('.project-folder-list'));
  host.querySelectorAll('.office-project-folder').forEach(row => {
    row.onclick = () => {
      const id = row.dataset.projectId;
      const expanded = !_expandedProjectIds.has(id);
      if (expanded) _expandedProjectIds.add(id);
      else _expandedProjectIds.delete(id);
      _projectFoldersAnimationUntil = performance.now() + PROJECT_FOLDER_TRANSITION_MS;
      // Retain this DOM node while it moves between its grid rows. Rebuilding
      // the folder list makes the final state appear instantly instead of
      // using the same smooth collapse transition as the Chat sidebar.
      const sessions = row.nextElementSibling;
      const chevron = row.querySelector('.project-folder-chevron');
      if (sessions) sessions.classList.toggle('expanded', expanded);
      if (chevron) chevron.classList.toggle('expanded', expanded);
    };
  });
  host.querySelectorAll('.office-session-row').forEach(row => {
    row.onclick = () => showHistory(row.dataset.parentId);
  });
}

/**
 * Fill the office panel's sidebar with the chats that ever delegated.
 * Called by switchPanel(), mirroring Agent Canvas.
 */
async function renderSidebar() {
  // Render what we already know immediately, then refresh from network.
  renderProjectFolders(_officeProjects, _historyParents);
  renderSessionList();
  try {
    const [sessionsResult, projectsResult] = await Promise.allSettled([
      request('/api/agent-canvas/sessions', { timeoutToast: false }),
      request('/api/projects?all_profiles=1', { timeoutToast: false }),
    ]);
    if (sessionsResult.status === 'fulfilled') {
      const data = sessionsResult.value;
      _historyParents = (data && Array.isArray(data.parents)) ? data.parents : _historyParents;
    } else if (sessionsResult.status === 'rejected') {
      console.warn('[office] agent-canvas/sessions failed:', sessionsResult.reason);
    }
    if (projectsResult.status === 'fulfilled') {
      const payload = projectsResult.value || {};
      const allProjects = (payload.projects && Array.isArray(payload.projects)) ? payload.projects : [];
      // Folder visibility is navigation state, not delegation state. Keep
      // every project visible even with no conversations or another profile --
      // except Work Hub projects, which belong to the Work Hub page only.
      const workHubOnly = typeof window.isWorkHubOnlyProject === 'function'
        ? window.isWorkHubOnlyProject : (project => !!(project && project.work_hub_managed));
      _officeProjects = allProjects.filter(project => !workHubOnly(project));
    } else if (projectsResult.status === 'rejected') {
      console.warn('[office] /api/projects failed:', projectsResult.reason);
    }
  } catch (_err) {
    console.warn('[office] renderSidebar network error:', _err);
  }
  refreshHistory();
  renderProjectFolders(_officeProjects, _historyParents);
  renderSessionList();
  if (_officeSubview === 'dashboard') scheduleSync();
  loadDashboardAttention();
}

async function loadDashboardAttention() {
  // One request for every chat waiting on the user, across all profiles. The
  // old per-chat polling only covered the active profile's delegating chats
  // and 404'd on chats tagged with another profile.
  const data = await request('/api/office/attention', { timeoutToast: false }).catch(() => null);
  if (!data || !Array.isArray(data.items)) return;
  const results = data.items.map(entry => {
    const sessionId = String(entry && entry.session_id || '');
    if (!sessionId || !entry.pending) return null;
    const goal = String(entry.title || '');
    const mode = businessView({ workers: [{ id: sessionId, goal, label: goal, status: 'completed' }] }, _roster)
      .desks.some(desk => desk.workerId === sessionId) ? 'business' : 'projects';
    return { sessionId, mode, kind: entry.kind === 'approval' ? 'approval' : 'clarify', pending: entry.pending,
      title: goal, profile: String(entry.profile || ''), sameProfile: entry.same_profile !== false };
  });
  _dashboardAttentionBySession.clear();
  results.filter(Boolean).forEach(item => _dashboardAttentionBySession.set(item.sessionId, item));
  if (_officeSubview === 'dashboard') scheduleSync();
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
  if (_projectFoldersDeferredTimer) {
    clearTimeout(_projectFoldersDeferredTimer);
    _projectFoldersDeferredTimer = null;
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
/**
 * The panel's live hooks: adapter subscription, resize/theme/visibility
 * observers, polling and the sidebar refresh. Attached on mount and on
 * resume after a suspend; teardownObservers() releases them all.
 */
function attachLiveHooks(container) {
  _unsubscribe = _adapter.subscribe(cmd => {
    if (_viewMode === 'live') scheduleSync();
    // A delegation has to show up in the sidebar the moment it starts, not on
    // the next poll: the stored listing cannot know about it yet.
    if (cmd && (cmd.type === 'worker.spawn' || cmd.type === 'worker.status'
      || cmd.type === 'worker.remove' || cmd.type === 'reset')) renderSessionList();
  });

  if (typeof ResizeObserver === 'function') {
    _resizeObserver = new ResizeObserver(() => {
      if (!_scene) return;
      if (!_layoutMotionPauseDepth) syncCanvasSpan();
      // Resizing clears the WebGL drawing buffer, and this callback runs after
      // the frame's rAF, so a bare resize paints a blank frame -- e.g. when an
      // expand settles while the loop is still waiting to restart. It also
      // covers a panel slide, which pauses the loop but commits its final
      // layout up front: drawing it now lets the floor and its cards travel
      // with the slide instead of stretching a stale frame that snaps at the end.
      _scene.renderNow();
      repositionDepartmentCards();
    });
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
    else if (!_layoutMotionPauseDepth) _scene.start();
  };
  document.addEventListener('visibilitychange', _visibilityHandler);

  // Polling only runs while the panel is up. The live SSE fan-out keeps the
  // office current whether or not anyone is looking at it; this is just the
  // catch-up for what the stream missed.
  _pollTimer = setInterval(reconcile, RECONCILE_MS);
  reconcile();
  // Runs started under another profile, or in another tab, only reach this
  // panel through the stored listing.
  _sidebarTimer = setInterval(() => {
    if (_layoutMotionPauseDepth) { _sidebarDeferredForMotion = true; return; }
    renderSidebar();
  }, SIDEBAR_REFRESH_MS);

  // Render cached/dummy sidebar immediately so project folders show up before
  // the first background poll completes.
  renderSidebar();

}

// Leaving the Office suspends the scene instead of destroying it: the loop
// and polling stop, the WebGL context and every built mesh and compiled
// shader stay, so coming back within SUSPEND_MS is instant instead of a full
// rebuild (seconds on an integrated GPU). Only one Office context ever
// exists, so the browser's context cap is never at risk; staying away longer
// than SUSPEND_MS releases it as before.
const SUSPEND_MS = 5 * 60 * 1000;
let _suspended = false;
let _suspendTimer = null;

function cancelSuspendTimer() {
  if (_suspendTimer) clearTimeout(_suspendTimer);
  _suspendTimer = null;
}

/** Stop drawing and polling, keep the scene; dispose it after SUSPEND_MS. */
function suspend() {
  if (!_scene || !_container) { unmount(); return; }
  const reset = !_preserveOfficeNavigationOnUnmount;
  _preserveOfficeNavigationOnUnmount = false;
  if (reset) resetOfficeToDefault();
  teardownObservers();
  try { _scene.stop(); } catch (_err) { /* already stopped */ }
  _suspended = true;
  cancelSuspendTimer();
  _suspendTimer = setTimeout(() => { _suspendTimer = null; if (_suspended) { _suspended = false; unmount(); } }, SUSPEND_MS);
}

function revealMountedFloor(startedAt) {
  if (!_canvas || !_canvas.classList.contains('is-mounting')) return;
  if (_outlet === 'business' && !_rosterReady && performance.now() - startedAt < OUTLET_ROSTER_WAIT_MS) {
    window.setTimeout(() => revealMountedFloor(startedAt), 120);
    return;
  }
  // Two frames: one for the cards to take their positions, one to paint.
  repositionDepartmentCards();
  window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
    if (_canvas) _canvas.classList.remove('is-mounting');
  }));
}

function mount(container) {
  if (!container) return;
  if (_suspended) {
    cancelSuspendTimer();
    _suspended = false;
    if (container === _container && _scene && _officeSubview === 'floor' && _canvas && container.contains(_canvas)) {
      // Back on the same panel: the scene, its meshes and shaders are intact.
      attachLiveHooks(container);
      renderPauseButton();
      renderOutletSwitch();
      _scene.resize();
      _scene.applyTheme();
      _scene.syncOffice(activeAdapter().getState());
      _scene.start();
      scheduleSync();
      return;
    }
    unmount();
  }
  if (!container) return;
  if (_officeSubview !== 'floor') {
    renderOfficeNavigation();
    renderOfficeSubview(container);
    return;
  }
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
      <button type="button" class="office-header-btn office-labels-btn" id="officeLabelScaleBtn" aria-label="Use fixed platform label size" aria-pressed="true" title="Use fixed platform label size"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="5.5"/><path d="m15 15 5 5M8 8l2.5-2.5L13 8M10.5 5.5V11"/></svg></button>
      <button type="button" class="office-header-btn office-labels-btn" id="officeLabelsBtn" aria-label="Toggle platform labels" aria-pressed="true" title="Toggle platform labels"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.5"/></svg></button>
      <span class="office-outlet" role="group" aria-label="Floor plan">
        <button type="button" class="office-outlet-btn" data-outlet="projects">Projects</button>
        <button type="button" class="office-outlet-btn" data-outlet="business">Business</button>
      </span>
      <button type="button" class="office-header-btn" id="officeBackBtn" hidden>Back to live</button>
      <button type="button" class="office-header-btn" id="officePauseBtn">View live</button>
    </div>
    <div class="office-body">
      <div class="office-stage" data-slide-safe>
        <canvas class="office-canvas is-mounting" id="officeCanvas" role="img"
                aria-label="Isometric floor of the current Hermes delegation tree"></canvas>
        <div class="office-loader" aria-hidden="true">
          <svg class="office-loader-atom" viewBox="0 0 160 160" aria-hidden="true">
            <defs><radialGradient id="officeLoaderCore"><stop offset="0" stop-color="#e0efff"/><stop offset=".45" stop-color="#6ea8ff"/><stop offset="1" stop-color="#2b5fd9" stop-opacity="0"/></radialGradient></defs>
            <circle cx="80" cy="80" r="30" fill="url(#officeLoaderCore)" class="office-loader-core"/>
            <g class="office-loader-orbits"><g transform="rotate(0 80 80)"><ellipse cx="80" cy="80" rx="64" ry="22" class="office-loader-orbit"/><circle r="3.6" class="office-loader-electron"><animateMotion dur="1.6s" begin="0s" repeatCount="indefinite" path="M16,80 a64,22 0 1,0 128,0 a64,22 0 1,0 -128,0"/></circle></g><g transform="rotate(60 80 80)"><ellipse cx="80" cy="80" rx="64" ry="22" class="office-loader-orbit"/><circle r="3.6" class="office-loader-electron"><animateMotion dur="2.1s" begin="-0.4s" repeatCount="indefinite" path="M16,80 a64,22 0 1,0 128,0 a64,22 0 1,0 -128,0"/></circle></g><g transform="rotate(120 80 80)"><ellipse cx="80" cy="80" rx="64" ry="22" class="office-loader-orbit"/><circle r="3.6" class="office-loader-electron"><animateMotion dur="1.85s" begin="-0.9s" repeatCount="indefinite" path="M16,80 a64,22 0 1,0 128,0 a64,22 0 1,0 -128,0"/></circle></g></g>
          </svg>
          <div class="office-loader-caption">Assembling the office<span class="office-loader-dots"><i>.</i><i>.</i><i>.</i></span></div>
        </div>
        <div class="office-dept-cards" id="officeDeptCards" aria-hidden="true"></div>
        <div class="sr-only" id="officeSummary" role="status" aria-live="polite"></div>
        <div class="office-tasks" id="officeTasks">
          <div class="office-tasks-head">
            <button type="button" class="office-tasks-toggle" id="officeTasksCollapseBtn"
                    aria-label="Collapse Task Status" aria-expanded="true" aria-controls="officeTasksBody">
              <span class="office-tasks-title-group">
                <svg class="office-tasks-title-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"/></svg>
                <span class="office-tasks-title">TASK STATUS</span>
              </span>
              <span class="office-tasks-count" id="officeTasksCount">0</span>
            </button>
          </div>
          <div class="office-tasks-body" id="officeTasksBody">
            <div class="office-tasks-body-inner">
              <div class="office-tasks-filters" id="officeTasksFilters" role="tablist" aria-label="Filter by status"></div>
              <div class="office-tasks-list" id="officeTasksList"></div>
            </div>
          </div>
        </div>
      </div>
    </div>`;
  _canvas = container.querySelector('#officeCanvas');
  _pillEl = container.querySelector('#officePill');
  _hintEl = container.querySelector('#officeHint');
  _summaryEl = container.querySelector('#officeSummary');
  _deptCardsEl = container.querySelector('#officeDeptCards');
  _deptCardEls.clear();
  _tasksEl = container.querySelector('#officeTasks');
  _tasksCollapseBtnEl = container.querySelector('#officeTasksCollapseBtn');
  _tasksCountEl = container.querySelector('#officeTasksCount');
  _tasksCollapseBtnEl.addEventListener('click', toggleTasksCollapsed);
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
  _pauseBtnEl.onclick = returnToLive;
  container.querySelector('#officeLabelScaleBtn').onclick = togglePlatformLabelScale;
  container.querySelector('#officeLabelsBtn').onclick = togglePlatformLabels;
  renderPlatformLabelScaleButton();
  _backBtnEl.onclick = returnToLive;
  _outletBtnEls = {};
  container.querySelectorAll('.office-outlet-btn').forEach(btn => {
    _outletBtnEls[btn.dataset.outlet] = btn;
    btn.onclick = () => setOutlet(btn.dataset.outlet);
  });
  renderPauseButton();
  renderOutletSwitch();
  loadRoster();

  syncCanvasSpan();
  try {
    _scene = createOfficeScene(_canvas, {
      onSelect: id => id ? selectTask(id, false) : clearTaskSelection(),
      // Hovering a platform highlights its card (the scene brightens its band).
      onHoverPod: cluster => {
        _deptCardEls.forEach((el, key) => el.classList.toggle('is-hovered', key === cluster));
      },
      onTick: () => { activeAdapter().tick(); repositionDepartmentCards(); },
      // The canvas, its cards and the loader's fade-out all wait for the
      // scene's first frames to have really been drawn -- and on Business
      // for the real roster (the first floor is a placeholder) -- so the
      // floor appears at once instead of labels over an empty canvas.
      onReady: () => revealMountedFloor(performance.now()),
      // The expanded Task Status panel owns the right edge of the stage, so
      // keep a focused desk clear of it. A collapsed status strip needs no
      // inset and an inline task detail never creates a second overlay.
      panelInset: () => {
        if (!_tasksEl || _tasksCollapsed) return 0;
        const measured = _tasksEl.getBoundingClientRect().width;
        if (measured) return measured + 28;
        const stage = _canvas ? _canvas.getBoundingClientRect().width : 0;
        return stage ? Math.min(280, stage - 28) + 28 : 0;
      },
    });
  } catch (err) {
    console.warn('[office] scene could not start:', err && err.message ? err.message : err);
    _scene = null;
    renderUnsupported(container);
    return;
  }

  attachLiveHooks(container);

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
  cancelSuspendTimer();
  _suspended = false;
  const reset = !_preserveOfficeNavigationOnUnmount;
  _preserveOfficeNavigationOnUnmount = false;
  if (reset) resetOfficeToDefault();
  teardownObservers();
  if (_scene) {
    try { _scene.dispose(); } catch (_err) { /* context already lost */ }
    _scene = null;
  }
  if (_layoutMotionResumeRaf) cancelAnimationFrame(_layoutMotionResumeRaf);
  _layoutMotionResumeRaf = 0;
  if (_container) _container.innerHTML = '';
  _container = null;
  _canvas = null;
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
  _tasksCountEl = null;
  _lastTaskStatusDoneCount = null;
  if (_taskCompletionTimer) clearTimeout(_taskCompletionTimer);
  _taskCompletionTimer = null;
  if (_taskStatusDisclosureTimer) clearTimeout(_taskStatusDisclosureTimer);
  _taskStatusDisclosureTimer = null;
  _taskStatusDisclosureAnimating = false;
  if (_tasksCollapseTimer) clearTimeout(_tasksCollapseTimer);
  _tasksCollapseTimer = null;
  _tasksCollapseAnimating = false;
  _tasksFiltersEl = null;
  _tasksListEl = null;
  _tasksFilter = 'all';
  _lastTaskStatusWorkers = [];
  _layoutMotionPauseDepth = 0;
  _resumeSceneAfterLayoutMotion = false;
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
  // Keep the Task Status row disclosure in step with the selection, as
  // selectTask()/clearTaskSelection() do; scheduleSync() may be gated.
  syncTaskStatusDisclosure();
  scheduleSync();
  return true;
}

/** Pull back to the whole floor. */
function resetView() {
  if (_scene) _scene.resetView();
  _selectedId = null;
  syncTaskStatusDisclosure();
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
window.officeSetSubview = setOfficeSubview;

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
  mount, unmount: suspend, dispose: unmount, isRunning, renderSidebar, returnToLive, setOutlet, setOfficeSubview,
  getView, focusWorker, resetView,
  pauseForLayoutMotion, resumeAfterLayoutMotion,
  onSpawn, onToolActivity, onComplete, applySnapshot, reset, getState,
  adapter: _adapter,
};

// If the Office panel was switched to before this ES module finished loading,
// panels.js skipped calling renderSidebar. Re-render now if the panel is active.
if (typeof document !== 'undefined') {
  try {
    renderOfficeNavigation();
    const officeWrap = document.getElementById('officeWrap');
    const officePanel = document.getElementById('mainOffice');
    const isActive = officePanel && !officePanel.classList.contains('hidden')
      && officeWrap && officeWrap.children.length > 0;
    if (isActive) {
      renderSidebar();
    }
  } catch (_err) { /* no-op */ }
}
