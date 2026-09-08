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

/** A child row that never recorded an end is not live — it was cut off. */
function historicalStatus(child) {
  const status = String((child && child.status) || '').trim().toLowerCase();
  // The raw query calls a row with no ended_at 'running'. In a finished
  // historical session that can only mean it was interrupted, never that it
  // is running right now — Agent Canvas makes the same correction.
  if (!status || status === 'running') return 'interrupted';
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
 * @returns {{spawns: Array<object>, completes: Array<object>}} in the same
 *   payload shape `onSpawn` / `onComplete` take from the live stream. Every
 *   spawn is applied before any completion, so a nested child is never
 *   completed before the parent that seats it exists.
 */
export function historyEventsFromParent(parent) {
  const entry = parent || {};
  const children = Array.isArray(entry.children) ? entry.children : [];
  const spawns = [];
  const completes = [];

  for (const child of children) {
    if (!child || !child.session_id) continue;
    // A direct child of the clicked chat hangs off the conductor; a nested
    // grandchild keeps its real parent, so the office rebuilds the same
    // multi-level shape the run actually had.
    const isDirect = child.parent_session_id === entry.parent_session_id;
    spawns.push({
      subagent_id: child.session_id,
      parent_id: isDirect ? null : (child.parent_session_id || null),
      goal: cleanTitle(child.title),
      model: child.model || null,
      child_session_id: child.session_id,
    });

    const started = Number(child.started_at) || 0;
    const ended = Number(child.ended_at) || 0;
    completes.push({
      subagent_id: child.session_id,
      status: historicalStatus(child),
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
export function applyHistory(adapter, parent) {
  if (!adapter) return;
  const { spawns, completes } = historyEventsFromParent(parent);
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
