// HermesOfficeAdapter — Hermes delegation events to office state (phase 2).
//
// This is the whole brain of the office view, and it is deliberately dumb
// about how anything looks: no three.js, no DOM, no fetch, no timers. It
// takes the events hermes-webui already receives —
//
//   subagent_spawn / subagent_tool / subagent_complete   (SSE, see
//   api/gateway_chat.py:537-583 for the exact field shapes)
//   GET /api/subagents/active                            (reconcile snapshot)
//
// — and maintains one state object: a conductor, a set of workers, and the
// desks they sit at. Subscribers (the scene, in phase 3) are handed small
// commands describing what changed.
//
// Hermes remains the source of truth for every one of those events. Nothing
// here spawns, decides, retries or infers work that Hermes did not report.
// In particular the three states the office would like but has no event for
// — queued, per-message activity, and handoff — are NOT synthesised here.
// See docs/rfcs/office-visualization.md.
//
// Purity is the point: keeping this module free of the browser is what lets
// tests/test_office_adapter.py drive the real code under node instead of
// asserting on its source text.

/** The conductor is the main session; it has no subagent_id of its own. */
export const ROOT_ID = '__conductor__';

/** Statuses after which a worker never runs again. */
export const TERMINAL_STATUSES = new Set([
  'completed', 'failed', 'error', 'timeout', 'interrupted',
  // 'ended' is inferred, never reported: the subagent left the live registry
  // without us ever seeing its completion event. It finished; we do not know
  // how. Claiming 'completed' would invent a result nobody reported.
  'ended',
]);

// delegate_tool.py reports completion as ok/error/timeout/interrupted/
// failed/completed. Everything else in the app speaks the Agent Canvas
// vocabulary, so translate once, here.
const STATUS_ALIASES = {
  ok: 'completed',
  success: 'completed',
  done: 'completed',
  finished: 'completed',
  cancelled: 'interrupted',
  canceled: 'interrupted',
};

const DEFAULTS = {
  // A tool call keeps a worker in the "tool" pose for this long before it
  // settles back to plain work. Purely presentational, but it lives here so
  // the scene has no state of its own to drift out of sync.
  toolPoseMs: 2600,
  // How many consecutive healthy snapshots a known-running subagent must be
  // absent from before the office concludes it stopped. Two rather than one so
  // a single partial or racing snapshot cannot retire a live worker.
  missingSnapshotsBeforeEnded: 2,
  // Soft ceiling on simultaneous desks. Reached, the office reclaims the
  // desk of the worker that finished longest ago rather than growing without
  // bound. A live worker is never evicted, so the cap can be exceeded when
  // Hermes genuinely runs more subagents than this at once.
  maxDesks: 24,
  now: () => Date.now(),
};

function shortLabel(goal) {
  const g = String(goal || '').trim().replace(/\s+/g, ' ');
  if (!g) return 'Subagent';
  return g.length > 42 ? g.slice(0, 41) + '…' : g;
}

function normaliseStatus(raw) {
  const s = String(raw == null ? '' : raw).trim().toLowerCase();
  if (!s) return '';
  return STATUS_ALIASES[s] || s;
}

function numberOrNull(value) {
  return typeof value === 'number' && isFinite(value) ? value : null;
}

/**
 * @param {object} [options] `toolPoseMs`, `maxDesks`, and `now` (injectable
 *   clock — tests drive time rather than waiting for it).
 */
export function createOfficeAdapter(options) {
  const config = Object.assign({}, DEFAULTS, options || {});
  const listeners = new Set();

  /** @type {Map<string, object>} subagent_id -> worker */
  let workers = new Map();
  /** @type {Array<object>} desk records, index is the seat number */
  let desks = [];
  let conductorStatus = 'idle';
  let spawnPaused = false;
  // Events that named a subagent the office has never heard of. Not an
  // error: a page opened mid-run sees tool/complete events for subagents
  // that spawned before the stream was attached. Counted so the condition is
  // visible rather than silent.
  let orphanEvents = 0;
  // Subagents this adapter has actually seen in a healthy snapshot. Only these
  // can be retired by absence: a worker known solely from SSE may simply be
  // outside whatever the snapshot covers, and inferring anything from its
  // absence would be guessing.
  let snapshotSeen = new Set();
  let snapshotMisses = new Map();

  function emit(command) {
    listeners.forEach(fn => {
      try {
        fn(command);
      } catch (err) {
        // A broken subscriber must not stop the others, nor corrupt state
        // that has already been committed.
        console.warn('[office] subscriber threw:', err && err.message ? err.message : err);
      }
    });
  }

  // ---- desks ------------------------------------------------------------

  // Finished workers keep their seats — a completed subagent is part of the
  // record of the run, not litter to sweep up — so desks are only ever taken
  // back under pressure, once the office is at its cap.
  function reclaimableDesk(cluster) {
    // Among desks whose occupant has finished, prefer one from the same
    // cluster so siblings stay together, then the one that finished longest
    // ago. A running worker is never evicted: an office that reseats a live
    // subagent is lying about what Hermes is doing.
    let sameCluster = null;
    let anyCluster = null;
    for (const desk of desks) {
      const occupant = workers.get(desk.workerId);
      if (!occupant || !TERMINAL_STATUSES.has(occupant.status)) continue;
      const candidate = { desk, endedAt: occupant.endedAt || 0 };
      if (desk.cluster === cluster) {
        if (!sameCluster || candidate.endedAt < sameCluster.endedAt) sameCluster = candidate;
      } else if (!anyCluster || candidate.endedAt < anyCluster.endedAt) {
        anyCluster = candidate;
      }
    }
    const chosen = sameCluster || anyCluster;
    return chosen ? chosen.desk : null;
  }

  function allocateDesk(worker) {
    const cluster = worker.parentId || ROOT_ID;
    let desk = null;
    if (desks.length >= config.maxDesks) {
      desk = reclaimableDesk(cluster);
      if (desk) {
        const previousWorkerId = desk.workerId;
        const previous = workers.get(previousWorkerId);
        if (previous) previous.deskId = null;
        emit({ type: 'desk.reclaim', deskId: desk.id, previousWorkerId });
      }
    }
    if (!desk) {
      // Over the cap with nothing to reclaim means Hermes is genuinely
      // running more subagents than the office planned for. Grow.
      desk = { id: 'desk-' + desks.length, index: desks.length, workerId: null, cluster };
      desks.push(desk);
    }
    desk.workerId = worker.id;
    desk.cluster = cluster;
    worker.deskId = desk.id;
    return desk;
  }

  // ---- workers ----------------------------------------------------------

  function poseFor(worker, at) {
    switch (worker.status) {
      case 'completed':
      case 'ended': return 'done';
      case 'interrupted': return 'stopped';
      case 'failed':
      case 'error':
      case 'timeout': return 'error';
      default: break;
    }
    if (worker.lastToolAt && (at - worker.lastToolAt) < config.toolPoseMs) return 'tool';
    return 'work';
  }

  function refreshPose(worker, at) {
    const pose = poseFor(worker, at);
    if (pose === worker.pose) return false;
    worker.pose = pose;
    return true;
  }

  function syncConductor() {
    const next = (() => {
      if (!workers.size) return 'idle';
      for (const worker of workers.values()) {
        if (!TERMINAL_STATUSES.has(worker.status)) return 'orchestrating';
      }
      return 'idle';
    })();
    if (next === conductorStatus) return;
    conductorStatus = next;
    emit({ type: 'conductor', status: conductorStatus });
  }

  function publicWorker(worker) {
    // A plain, serialisable copy. Subscribers get a snapshot they cannot use
    // to reach back into adapter state.
    return Object.assign({}, worker);
  }

  // ---- event intake -----------------------------------------------------

  /**
   * `subagent_spawn`. Allocates a desk and seats a new worker.
   * Repeat spawns for a known id are ignored: the SSE stream and the
   * reconcile snapshot both report the same subagent, and a second desk for
   * one worker would double-count the whole office.
   */
  function onSpawn(payload) {
    const data = payload || {};
    const id = data.subagent_id;
    if (!id) return null;
    const existing = workers.get(id);
    if (existing) return publicWorker(existing);

    const at = config.now();
    const worker = {
      id,
      parentId: data.parent_id || null,
      depth: numberOrNull(data.depth),
      goal: String(data.goal || ''),
      label: shortLabel(data.goal),
      model: data.model || null,
      toolsets: Array.isArray(data.toolsets) ? data.toolsets.slice() : [],
      childSessionId: data.child_session_id || null,
      taskIndex: numberOrNull(data.task_index),
      taskCount: numberOrNull(data.task_count),
      status: 'running',
      pose: 'work',
      deskId: null,
      tool: null,
      toolCount: 0,
      spawnedAt: at,
      lastToolAt: 0,
      endedAt: null,
      durationSeconds: null,
      summary: '',
      inputTokens: null,
      outputTokens: null,
      reasoningTokens: null,
      costUsd: null,
      apiCalls: null,
      filesRead: null,
      filesWritten: null,
      outputTail: null,
    };
    workers.set(id, worker);
    const desk = allocateDesk(worker);
    emit({ type: 'worker.spawn', worker: publicWorker(worker), desk: Object.assign({}, desk) });
    syncConductor();
    return publicWorker(worker);
  }

  /**
   * `subagent_tool`. Records what the worker is touching right now.
   * A tool event for a worker that has already finished is dropped: late
   * events must not resurrect a completed subagent into a working pose.
   */
  function onToolActivity(payload) {
    const data = payload || {};
    const id = data.subagent_id;
    if (!id) return null;
    const worker = workers.get(id);
    if (!worker) { orphanEvents += 1; return null; }
    if (TERMINAL_STATUSES.has(worker.status)) return publicWorker(worker);

    const at = config.now();
    worker.tool = {
      name: String(data.tool || ''),
      preview: String(data.preview || ''),
    };
    worker.toolCount = numberOrNull(data.tool_count) != null
      ? data.tool_count
      : worker.toolCount + 1;
    worker.lastToolAt = at;
    refreshPose(worker, at);
    emit({ type: 'worker.tool', worker: publicWorker(worker), tool: Object.assign({}, worker.tool) });
    return publicWorker(worker);
  }

  /**
   * `subagent_complete`. Terminal, and sticky: once a worker is terminal it
   * stays terminal, whatever arrives afterwards.
   */
  function onComplete(payload) {
    const data = payload || {};
    const id = data.subagent_id;
    if (!id) return null;
    const worker = workers.get(id);
    if (!worker) { orphanEvents += 1; return null; }
    if (TERMINAL_STATUSES.has(worker.status)) return publicWorker(worker);

    const at = config.now();
    const status = normaliseStatus(data.status);
    worker.status = TERMINAL_STATUSES.has(status) ? status : 'completed';
    worker.endedAt = at;
    worker.durationSeconds = numberOrNull(data.duration_seconds);
    worker.summary = String(data.summary || '');
    worker.inputTokens = numberOrNull(data.input_tokens);
    worker.outputTokens = numberOrNull(data.output_tokens);
    worker.reasoningTokens = numberOrNull(data.reasoning_tokens);
    worker.costUsd = numberOrNull(data.cost_usd);
    worker.apiCalls = numberOrNull(data.api_calls);
    worker.filesRead = numberOrNull(data.files_read);
    worker.filesWritten = numberOrNull(data.files_written);
    worker.outputTail = Array.isArray(data.output_tail) ? data.output_tail.slice() : null;
    refreshPose(worker, at);
    emit({ type: 'worker.status', worker: publicWorker(worker) });
    syncConductor();
    return publicWorker(worker);
  }

  /**
   * Reconcile against `GET /api/subagents/active`.
   *
   * Best-effort catch-up, never a source of removals: a subagent missing
   * from the snapshot has finished or was never ours, and either way the
   * office keeps the seat it already drew rather than deleting history the
   * user is looking at.
   */
  function applySnapshot(snapshot) {
    const data = snapshot || {};
    // NOTE: do not skip on `gateway_enabled === false`. That reads like "no
    // data", but the single-container (in-process) deployment reports exactly
    // that while still returning a fully populated `active` list straight from
    // tools.delegate_tool's registry — see api/routes.py's /api/subagents/active
    // in-process branch. Skipping made reconcile a permanent no-op there,
    // which is the one deployment shape that needs it most: it has no separate
    // gateway process, so a fire-and-forget subagent finishing after its
    // parent's stream closed has no other way to be noticed.
    //
    // A 502 from the gateway also returns an empty `active` with
    // spawn_paused:false, which is an error rather than a fact about pausing,
    // so that one field is only trusted when the response carries no error.
    if (!data.error) spawnPaused = !!data.spawn_paused;
    const active = Array.isArray(data.active) ? data.active : [];
    const present = new Set();
    for (const record of active) {
      if (record && record.subagent_id) present.add(record.subagent_id);
    }
    for (const record of active) {
      if (!record || !record.subagent_id) continue;
      let worker = workers.get(record.subagent_id);
      if (!worker) {
        onSpawn({
          subagent_id: record.subagent_id,
          parent_id: record.parent_id,
          depth: record.depth,
          goal: record.goal,
          model: record.model,
        });
        worker = workers.get(record.subagent_id);
        // started_at is unix seconds in the snapshot; the office keeps
        // milliseconds so it can compare against its own clock.
        if (worker && record.started_at) worker.spawnedAt = record.started_at * 1000;
      }
      if (!worker) continue;
      snapshotSeen.add(worker.id);
      snapshotMisses.delete(worker.id);
      if (numberOrNull(record.tool_count) != null) worker.toolCount = record.tool_count;
      const status = normaliseStatus(record.status);
      if (status && status !== worker.status && !TERMINAL_STATUSES.has(worker.status)) {
        worker.status = status;
        worker.endedAt = TERMINAL_STATUSES.has(status) ? config.now() : null;
        refreshPose(worker, config.now());
        emit({ type: 'worker.status', worker: publicWorker(worker) });
      }
    }
    retireVanishedWorkers(present, !data.error);
    syncConductor();
  }

  /**
   * Retire workers that have dropped out of the live registry.
   *
   * A finished subagent does not appear in `/api/subagents/active` with a
   * terminal status — delegate_tool's `_unregister_subagent` removes the
   * record outright when the child finishes (see
   * tools/delegate_tool_child_run.py). So absence is the only signal the
   * snapshot carries about completion, and without acting on it a subagent
   * whose completion event never arrived — a fire-and-forget child that
   * finished after its parent's stream closed — sits at "running" forever.
   *
   * Absence is trusted narrowly: only for workers previously observed in a
   * healthy snapshot, only when this snapshot itself is healthy, and only
   * after several consecutive misses. The status is 'ended', not 'completed':
   * we know it stopped, we never saw how it went, and saying otherwise would
   * invent a result.
   */
  function retireVanishedWorkers(present, healthy) {
    if (!healthy) return;
    for (const worker of workers.values()) {
      if (TERMINAL_STATUSES.has(worker.status)) continue;
      if (!snapshotSeen.has(worker.id)) continue;
      if (present.has(worker.id)) continue;
      const misses = (snapshotMisses.get(worker.id) || 0) + 1;
      snapshotMisses.set(worker.id, misses);
      if (misses < config.missingSnapshotsBeforeEnded) continue;
      worker.status = 'ended';
      worker.endedAt = config.now();
      refreshPose(worker, worker.endedAt);
      emit({ type: 'worker.status', worker: publicWorker(worker) });
    }
  }

  /**
   * Re-evaluate time-dependent poses. The scene calls this from its own
   * loop; the adapter owns no timer of its own, so nothing here runs unless
   * someone asks.
   * @returns {number} how many workers changed pose
   */
  function tick() {
    const at = config.now();
    let changed = 0;
    for (const worker of workers.values()) {
      if (refreshPose(worker, at)) {
        changed += 1;
        emit({ type: 'worker.pose', worker: publicWorker(worker) });
      }
    }
    return changed;
  }

  /** Drop everything — a new run, or a session switch. */
  function reset() {
    workers = new Map();
    desks = [];
    snapshotSeen = new Set();
    snapshotMisses = new Map();
    conductorStatus = 'idle';
    spawnPaused = false;
    orphanEvents = 0;
    emit({ type: 'reset' });
  }

  /** Serialisable snapshot of the whole office. */
  function getState() {
    return {
      conductor: { id: ROOT_ID, status: conductorStatus },
      spawnPaused,
      orphanEvents,
      workers: Array.from(workers.values()).map(publicWorker),
      desks: desks.map(desk => Object.assign({}, desk)),
    };
  }

  function getWorker(id) {
    const worker = workers.get(id);
    return worker ? publicWorker(worker) : null;
  }

  function subscribe(fn) {
    if (typeof fn !== 'function') return () => {};
    listeners.add(fn);
    return () => listeners.delete(fn);
  }

  return {
    onSpawn, onToolActivity, onComplete, applySnapshot,
    tick, reset, getState, getWorker, subscribe,
  };
}
