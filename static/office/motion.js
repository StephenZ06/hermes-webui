// Moving figures around the floor.
//
// Two kinds of movement, and the distinction is the whole design:
//
// * **Wandering** is what a figure does when it has *nothing* to do. The
//   conductor paces its plinth between delegations. It must never be used for
//   a figure that is working, because a walking figure reads as activity and
//   the office is not allowed to imply work that Hermes did not report.
// * **Arrival** is a subagent walking to its desk when it spawns. That is a
//   real event — the office is showing something that genuinely just
//   happened — and it ends the moment the figure sits down.
//
// No three.js and no DOM: positions are plain numbers, so
// tests/test_office_motion.py drives the real thing under node with an
// injected clock and an injected random.

const TAU = Math.PI * 2;

/** How fast a figure covers ground, in world units per second. */
export const WANDER_SPEED = 2.1;
export const ARRIVAL_SPEED = 6.5;

/**
 * A figure that paces inside a circle, pausing between walks.
 *
 * @param {object} [opts] `radius`, `speed`, `pauseMinMs`, `pauseMaxMs`, `rand`
 */
export function createWanderer(opts) {
  const config = Object.assign({
    radius: 4.2,
    speed: WANDER_SPEED,
    pauseMinMs: 1400,
    pauseMaxMs: 4200,
    rand: Math.random,
  }, opts || {});

  const state = {
    x: 0, z: 0,
    heading: 0,
    moving: false,
    // Distance walked, which is what drives the stride — not elapsed time, so
    // the gait stays right regardless of frame rate.
    phase: 0,
    _target: null,
    _pauseLeft: config.pauseMinMs,
  };

  // With `minRadius` the walk keeps to a ring round something standing in the
  // middle (the hub's pedestal): targets are on the ring and never more than
  // `maxTurn` round it from where the walker is, so a straight walk between
  // them never cuts across the middle.
  const ring = config.minRadius > 0;
  if (ring) {
    const start = config.rand() * TAU;
    const r0 = (config.minRadius + config.radius) / 2;
    state.x = Math.cos(start) * r0;
    state.z = Math.sin(start) * r0;
  }

  function pickTarget() {
    if (ring) {
      const here = Math.atan2(state.z, state.x);
      const turn = (config.rand() * 2 - 1) * (config.maxTurn || Math.PI / 3);
      const r = config.minRadius + config.rand() * (config.radius - config.minRadius);
      state._target = { x: Math.cos(here + turn) * r, z: Math.sin(here + turn) * r };
      return;
    }
    // Uniform over the disc: sqrt keeps the walks from clustering in the
    // middle, which is what a plain random radius would do.
    const angle = config.rand() * TAU;
    const distance = Math.sqrt(config.rand()) * config.radius;
    state._target = { x: Math.cos(angle) * distance, z: Math.sin(angle) * distance };
  }

  function pause() {
    state._target = null;
    state.moving = false;
    state._pauseLeft = config.pauseMinMs
      + config.rand() * Math.max(0, config.pauseMaxMs - config.pauseMinMs);
  }

  /**
   * Advance by `dtMs`. Returns the same state object, mutated.
   */
  function update(dtMs) {
    const dt = Math.max(0, dtMs) / 1000;
    if (!state._target) {
      state._pauseLeft -= dtMs;
      if (state._pauseLeft > 0) return state;
      pickTarget();
      state.moving = true;
    }
    const dx = state._target.x - state.x;
    const dz = state._target.z - state.z;
    const remaining = Math.hypot(dx, dz);
    const step = config.speed * dt;
    if (remaining <= step || remaining < 1e-4) {
      state.x = state._target.x;
      state.z = state._target.z;
      // The last stride is a partial one, and it still covered ground: phase
      // is distance walked, so it has to include it or the gait skips.
      state.phase += remaining;
      pause();
      return state;
    }
    state.x += (dx / remaining) * step;
    state.z += (dz / remaining) * step;
    state.phase += step;
    // Face the direction of travel.
    state.heading = Math.atan2(dx, dz);
    return state;
  }

  /**
   * Walk toward a fixed point instead of pacing — how the conductor returns
   * to the middle of its plinth when a delegation starts.
   * @returns {boolean} true once it has arrived
   */
  function moveTo(x, z, dtMs) {
    const dt = Math.max(0, dtMs) / 1000;
    let aimX = x;
    let aimZ = z;
    if (ring && Math.hypot(x, z) >= config.minRadius * 0.9) {
      // Round the ring toward the spot rather than across the middle.
      const here = Math.atan2(state.z, state.x);
      const there = Math.atan2(z, x);
      let diff = there - here;
      while (diff > Math.PI) diff -= TAU;
      while (diff < -Math.PI) diff += TAU;
      if (Math.abs(diff) > 0.5) {
        const r = Math.max(config.minRadius, Math.hypot(state.x, state.z));
        aimX = Math.cos(here + Math.sign(diff) * 0.5) * r;
        aimZ = Math.sin(here + Math.sign(diff) * 0.5) * r;
      }
    }
    const dx = aimX - state.x;
    const dz = aimZ - state.z;
    const remaining = Math.hypot(dx, dz);
    const step = config.speed * dt;
    if ((remaining <= step || remaining < 1e-3) && aimX === x && aimZ === z) {
      state.x = x;
      state.z = z;
      state.phase += remaining;
      state.moving = false;
      state._target = null;
      state._pauseLeft = config.pauseMinMs;
      return true;
    }
    const move = Math.min(step, remaining);
    if (remaining > 1e-6) {
      state.x += (dx / remaining) * move;
      state.z += (dz / remaining) * move;
      state.heading = Math.atan2(dx, dz);
    }
    state.phase += move;
    state.moving = true;
    return false;
  }

  return { state, update, moveTo };
}

// Over the last this-many units of the walk the figure merges from the aisle
// back onto the desk's centre line, so it curves into the chair instead of
// arriving side-on.
const ARRIVAL_MERGE = 3.4;

/**
 * A subagent walking to its desk.
 *
 * Starts out in the aisle beside the desk — `lateral` units to one side and
 * `distance` behind — and walks in, merging onto the centre line only for the
 * last stretch so it rounds into the chair rather than ploughing straight
 * through the row behind it. Local to the seat, so it works whatever direction
 * that desk faces.
 *
 * @param {number} distance how far behind the chair to start
 * @param {number} [speed]
 * @param {number} [lateral] signed aisle offset to start from; 0 walks straight in
 */
export function createArrival(distance, speed, lateral) {
  return {
    // Local z offset from the seated position; counts down to 0.
    offset: distance,
    // Local x offset from the seated position; derived from `offset` so it
    // tapers to 0 as the figure reaches the chair.
    lateral: lateral || 0,
    lateralStart: lateral || 0,
    distance,
    speed: speed || ARRIVAL_SPEED,
    phase: 0,
    done: false,
  };
}

/**
 * Advance an arrival.
 * @returns {object} the same arrival, mutated. `done` once seated.
 */
export function advanceArrival(arrival, dtMs) {
  if (!arrival || arrival.done) return arrival;
  const step = arrival.speed * (Math.max(0, dtMs) / 1000);
  arrival.offset -= step;
  arrival.phase += step;
  if (arrival.offset <= 0) {
    arrival.offset = 0;
    arrival.done = true;
  }
  // Hold the aisle line until the last ARRIVAL_MERGE units, then ease across.
  const merge = Math.max(0, Math.min(1, arrival.offset / ARRIVAL_MERGE));
  arrival.lateral = arrival.lateralStart * merge;
  return arrival;
}

/**
 * How much of the walk cycle still applies, 0..1.
 *
 * Eased out over the last stretch so a figure settles into its chair instead
 * of stopping mid-stride with a leg in the air.
 */
export function arrivalSettle(arrival, easeOver) {
  if (!arrival || arrival.done) return 0;
  const over = easeOver || 1.2;
  return Math.max(0, Math.min(1, arrival.offset / over));
}

/** Low-gravity hop: how long one takes and how high it goes. */
export const HOP_PERIOD_S = 0.95;
export const HOP_HEIGHT = 0.85;

/**
 * Hops for a figure that moves in low gravity (the conductor). Height is a
 * parabola in *time* (constant, moon-like gravity), and a hop once started
 * always finishes: when the walk it rides on stops, the figure lands, and
 * when the walk starts again it takes off from the floor. Height used to
 * follow distance walked, so every stop mid-hop snapped the figure to the
 * floor and every restart snapped it back into the air -- the stutter.
 */
export function createHopper(opts) {
  const config = Object.assign({ period: HOP_PERIOD_S, height: HOP_HEIGHT }, opts || {});
  const state = { f: 0, airborne: false };
  return {
    state,
    /**
     * @param {number} dtS seconds since the last frame
     * @param {boolean} moving whether the figure wants to travel
     * @returns {number} height above the floor
     */
    update(dtS, moving) {
      if (!state.airborne) {
        if (!moving) return 0;
        state.airborne = true;
        state.f = 0;
      }
      state.f += Math.max(0, dtS) / config.period;
      if (state.f >= 1) {
        if (moving) {
          state.f -= Math.floor(state.f);
        } else {
          state.f = 0;
          state.airborne = false;
          return 0;
        }
      }
      return 4 * config.height * state.f * (1 - state.f);
    },
  };
}
