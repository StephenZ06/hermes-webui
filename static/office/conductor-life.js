// What the conductor does while nothing is delegated.
//
// Decoration, under the same rule as idle.js: none of this may suggest work
// that Hermes did not report. So an idle conductor never types or directs;
// it paces its ring, sometimes sits down at one of the hub's desks to lean
// back or sip a coffee, sometimes stops to stretch or look around, and
// shows a small emoji bubble when it starts one of those. The moment a
// delegation starts, scene.js stops calling this and walks the figure to
// the globe (`cancel()` drops whatever it was doing).
//
// No three.js and no DOM: driven with an injected clock and random.

export const WANDER_MIN_S = 7;
export const WANDER_JITTER_S = 7;
export const SIT_MIN_S = 8;
export const SIT_JITTER_S = 6;
export const EMOTE_S = 2.6;

const EMOTES = [
  { pose: 'stretch', icon: '🙆' },
  { pose: 'glance', icon: '👀' },
  { pose: 'coffee', icon: '☕' },
  { pose: 'sip', icon: '🙂' },
];
const SEATED = [
  { pose: 'lean', icon: '😌' },
  { pose: 'sip', icon: '☕' },
  { pose: 'idle', icon: '💭' },
];

export function createConductorLife(options) {
  const rand = (options && options.rand) || Math.random;
  const pick = list => list[Math.floor(rand() * list.length) % list.length];
  const life = { mode: 'wander', until: 0, chair: null, pose: 'idle', icon: '', iconAt: -1 };

  function startWander(t) {
    life.mode = 'wander';
    life.chair = null;
    life.until = t + WANDER_MIN_S + rand() * WANDER_JITTER_S;
  }

  /**
   * Advance one frame.
   * @param {{t:number, dtMs:number, wanderer:object, chairs:Array}} ctx
   * @returns {{x:number, z:number, heading:number, walking:boolean,
   *            seated:boolean, pose:string, icon:string}}
   *   `icon` is non-empty only on the frame a new bubble should pop.
   */
  function step(ctx) {
    const { t, dtMs, wanderer } = ctx;
    const chairs = ctx.chairs || [];
    const s = wanderer.state;
    let icon = '';
    if (!life.until) startWander(t);

    if (life.mode === 'wander') {
      wanderer.update(dtMs);
      if (t >= life.until && !s.moving) {
        if (chairs.length && rand() < 0.45) {
          life.mode = 'toChair';
          life.chair = pick(chairs);
        } else {
          const emote = pick(EMOTES);
          life.mode = 'emote';
          life.pose = emote.pose;
          life.until = t + EMOTE_S;
          icon = emote.icon;
        }
      }
      return { x: s.x, z: s.z, heading: s.heading, walking: s.moving, seated: false, pose: 'idle', icon };
    }

    if (life.mode === 'toChair') {
      const arrived = wanderer.moveTo(life.chair.x, life.chair.z, dtMs);
      if (arrived) {
        const seated = pick(SEATED);
        life.mode = 'sit';
        life.pose = seated.pose;
        life.until = t + SIT_MIN_S + rand() * SIT_JITTER_S;
        icon = seated.icon;
      }
      return { x: s.x, z: s.z, heading: s.heading, walking: !arrived, seated: arrived, pose: life.pose, icon };
    }

    if (life.mode === 'sit') {
      const chair = life.chair;
      if (t >= life.until) startWander(t);
      return { x: chair.x, z: chair.z, heading: chair.facing, walking: false, seated: life.mode === 'sit', pose: life.pose, icon };
    }

    // emote: stand still and play it, then pace again.
    if (t >= life.until) startWander(t);
    return { x: s.x, z: s.z, heading: s.heading, walking: false, seated: false, pose: life.mode === 'emote' ? life.pose : 'idle', icon };
  }

  /** Drop the current activity (a delegation started). */
  function cancel() {
    life.mode = 'wander';
    life.chair = null;
    life.until = 0;
  }

  return { step, cancel, get mode() { return life.mode; } };
}
