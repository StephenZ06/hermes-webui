// Rebuilding a finished run's office from state.db rows (phase 4).
//
// `GET /api/agent-canvas/sessions` returns the chats that ever delegated,
// each with the subagent child rows recorded in hermes-agent's state.db (see
// api/agent_sessions.py's list_parents_with_subagent_children). Those rows
// carry the same facts the live SSE events do, just after the fact — so the
// historical office is built by replaying them through an ordinary adapter
// rather than by teaching the adapter a second, frozen mode.
//
// Pure translation, no DOM and no fetch, so tests/test_office_history.py can
// run it under node.

/**
 * What a child row's status means once the run is over — or while it is not.
 *
 * The raw query calls a row with no ended_at 'running'. In a FINISHED session
 * that can only mean it was interrupted, never that it is running right now —
 * Agent Canvas makes the same correction.
 *
 * `live` is the exception, and it is not hypothetical: the cross-profile
 * ledger records a delegation at spawn (status 'running', no ended_at), so the
 * sidebar listing carries those rows for the whole run. Correcting them the
 * same way made a run that completed perfectly well replay as three
 * 'Interrupted' desks.
 */
function historicalStatus(child, live) {
  const status = String((child && child.status) || '').trim().toLowerCase();
  if (!status || status === 'running') return live ? 'running' : 'interrupted';
  return status;
}

function cleanTitle(title) {
  const t = String(title || '').replace(/^Subagent:\s*/, '').trim();
  return t || 'Subagent';
}

/**
 * Translate one history entry into adapter events.
 *
 * @param {object} parent `{parent_session_id, children: [...]}`
 * @param {object} [options] `live` — the run is still going, so a child with
 *   no recorded end is working, not cut off.
 * @returns {{spawns: Array<object>, completes: Array<object>}} in the same
 *   payload shape `onSpawn` / `onComplete` take from the live stream. Every
 *   spawn is applied before any completion, so a nested child is never
 *   completed before the parent that seats it exists.
 */
export function historyEventsFromParent(parent, options) {
  const entry = parent || {};
  const live = !!(options && options.live);
  const children = Array.isArray(entry.children) ? entry.children : [];
  const spawns = [];
  const completes = [];

  for (const child of children) {
    if (!child || !child.session_id) continue;
    // A direct child of the clicked chat hangs off the conductor; a nested
    // grandchild keeps its real parent, so the office rebuilds the same
    // multi-level shape the run actually had.
    //
    // `cluster` is the exception, and only for a direct child: a
    // delegate_to_profile row records `profile:<name>`, which is what the LIVE
    // floor seats it under. Without it the replay would drop every cross-
    // profile child onto the conductor and lose the one thing that floor shows
    // most plainly — which profile did the work. Real nesting still wins:
    // a grandchild belongs under its own parent, not under a profile sign.
    const isDirect = child.parent_session_id === entry.parent_session_id;
    const cluster = isDirect ? (child.cluster || null) : null;
    spawns.push({
      subagent_id: child.session_id,
      parent_id: isDirect ? cluster : (child.parent_session_id || null),
      goal: cleanTitle(child.title),
      model: child.model || null,
      child_session_id: child.session_id,
    });

    const status = historicalStatus(child, live);
    if (status === 'running') {
      // Still working. The adapter seats a spawn as 'running' and treats every
      // completion as terminal ('running' would be coerced to 'completed'), so
      // the honest thing is to send no completion at all until there is one.
      continue;
    }

    const started = Number(child.started_at) || 0;
    const ended = Number(child.ended_at) || 0;
    completes.push({
      subagent_id: child.session_id,
      status,
      duration_seconds: (started && ended) ? Math.max(0, ended - started) : null,
      input_tokens: child.input_tokens ?? null,
      output_tokens: child.output_tokens ?? null,
      reasoning_tokens: child.reasoning_tokens ?? null,
      cost_usd: child.cost_usd ?? null,
      api_calls: child.api_call_count ?? null,
    });
  }

  return { spawns, completes };
}

/**
 * Replay a history entry into an adapter. The adapter is ordinary — the
 * "frozen" part is only that nothing is ever fed to it afterwards.
 */
export function applyHistory(adapter, parent, options) {
  if (!adapter) return;
  const { spawns, completes } = historyEventsFromParent(parent, options);
  spawns.forEach(payload => adapter.onSpawn(payload));
  completes.forEach(payload => adapter.onComplete(payload));
}

/** Tool-call totals are recorded per child; the adapter counts live ones. */
export function historyToolCounts(parent) {
  const entry = parent || {};
  const children = Array.isArray(entry.children) ? entry.children : [];
  const counts = {};
  for (const child of children) {
    if (!child || !child.session_id) continue;
    counts[child.session_id] = Number(child.tool_call_count) || 0;
  }
  return counts;
}
