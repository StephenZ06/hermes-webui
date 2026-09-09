// Idle behaviour — what a figure does between tool calls.
//
// This is decoration, and it is the one part of the office that shows
// something Hermes never reported. That makes the rule strict: an idle
// behaviour may only ever play over `work` — a subagent that is running but
// not mid-tool-call — and it is cancelled the instant anything real happens.
// A tool call, a completion, a failure or an interrupt all take the figure
// back immediately.
//
// Every idle pose is also visually distinct from every pose that *means*
// something, so a stretch never reads as an error and a sip never reads as a
// finished task.
//
// No three.js and no DOM, so tests/test_office_idle.py drives the real thing
// under node with an injected clock and an injected random.

/** Behaviours that may interrupt plain work, and how long each plays. */
export const IDLE_BEHAVIOURS = [
  { pose: 'lean', ms: 2600 },
  { pose: 'sip', ms: 2000 },
  { pose: 'stretch', ms: 2200 },
  { pose: 'glance', ms: 1500 },
];

/**
 * Roughly how often a figure considers doing one, jittered per worker so a
 * pod never breaks into synchronised calisthenics.
 */
export const IDLE_MIN_GAP_MS = 9000;
export const IDLE_GAP_JITTER_MS = 14000;

function rearm(state, nowMs, rand) {
  state.idlePose = null;
  state.idleUntil = 0;
  state.idleNextAt = nowMs + IDLE_MIN_GAP_MS + rand() * IDLE_GAP_JITTER_MS;
}

/**
 * Resolve the pose to actually render this frame.
 *
 * @param {object} state per-figure scratch (the mesh's `userData`); mutated.
 * @param {string} pose the real pose, from adapter state.
 * @param {number} nowMs
 * @param {Function} [rand] injectable `Math.random`.
 * @returns {string} `pose`, or an idle behaviour playing over it.
 */
export function idlePoseFor(state, pose, nowMs, rand) {
  const random = rand || Math.random;
  if (!state) return pose;

  if (pose !== 'work') {
    // Anything real cancels idling outright, and re-arms the timer so a
    // figure coming off a tool call does not stretch the moment it lands
    // back on plain work.
    rearm(state, nowMs, random);
    return pose;
  }

  if (state.idleUntil && nowMs < state.idleUntil) return state.idlePose;
  if (state.idleUntil) {
    rearm(state, nowMs, random);
    return pose;
  }
  if (!state.idleNextAt) {
    rearm(state, nowMs, random);
    return pose;
  }
  if (nowMs < state.idleNextAt) return pose;

  const choice = IDLE_BEHAVIOURS[Math.floor(random() * IDLE_BEHAVIOURS.length)];
  state.idlePose = choice.pose;
  state.idleUntil = nowMs + choice.ms;
  if (choice.pose === 'glance') state.glanceDir = random() < 0.5 ? 0.85 : -0.85;
  return state.idlePose;
}
