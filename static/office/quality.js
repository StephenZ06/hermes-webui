// Office render quality governor — dynamic resolution for slow GPUs.
//
// The Office draws a bloom pipeline with MSAA at up to 2x the screen's pixel
// density, every frame. On an integrated GPU that cannot hold 60fps, and a
// scene that stutters reads as sluggish no matter how good each frame looks.
// The governor watches how long frames actually take (the requestAnimationFrame
// interval is what the user sees) and trades internal resolution for frame
// rate: it steps the pixel ratio down while frames are slow and back up only
// after a sustained stretch of headroom, so it never oscillates.
//
// No three.js and no DOM: tests drive it under node with synthetic frame times.

export const STEP = 0.25;
export const WINDOW = 45;            // frames per measurement window
export const SLOW_MS = 21;           // window average above this: below ~48fps
export const FAST_MS = 14.5;         // window average below this: real headroom
export const RAISE_AFTER_WINDOWS = 6; // consecutive fast windows before stepping up
export const SETTLE_MS = 1500;       // ignore frames right after a change/start

export function createQualityGovernor({ base, min }) {
  const top = Math.max(min, base);
  let ratio = top;
  let samples = [];
  let fastWindows = 0;
  let ignoreUntil = 0;

  function reset(nowMs) {
    samples = [];
    fastWindows = 0;
    ignoreUntil = nowMs + SETTLE_MS;
  }

  return {
    get ratio() { return ratio; },
    /** A fresh start (mount, resume, resize): drop stale measurements. */
    reset,
    /**
     * Record one frame interval. Returns the new pixel ratio when it should
     * change, otherwise null.
     */
    sample(dtMs, nowMs) {
      // Multi-second gaps (a paused loop, a stalled tab) say nothing about the
      // GPU. Slower frames still count: a GPU that needs half a second per
      // frame needs the lower resolution most.
      if (nowMs < ignoreUntil || !(dtMs > 0) || dtMs > 2000) return null;
      samples.push(dtMs);
      if (samples.length < WINDOW) return null;
      const sorted = samples.slice().sort((a, b) => a - b);
      // Median: one long GC pause or a tab switch should not cost resolution.
      const typical = sorted[Math.floor(sorted.length / 2)];
      samples = [];
      if (typical > SLOW_MS && ratio > min) {
        ratio = Math.max(min, Math.round((ratio - STEP) * 100) / 100);
        reset(nowMs);
        return ratio;
      }
      if (typical < FAST_MS && ratio < top) {
        fastWindows += 1;
        if (fastWindows >= RAISE_AFTER_WINDOWS) {
          ratio = Math.min(top, Math.round((ratio + STEP) * 100) / 100);
          reset(nowMs);
          return ratio;
        }
      } else {
        fastWindows = 0;
      }
      return null;
    },
  };
}
