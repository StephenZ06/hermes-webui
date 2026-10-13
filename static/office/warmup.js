// Compile every material's shader program off the first frame.
//
// three.js r185 has renderer.compileAsync for this, but it polls
// properties.get(material).currentProgram.isReady() in a bare timer: a
// material that three.js skipped while compiling, or one disposed because the
// floor was rebuilt mid warm-up, has no program, so the timer threw
// "Cannot read properties of undefined (reading 'isReady')" into the console
// and the warm-up never settled. This does the same work with a poll that
// treats a missing program as done and can never throw.
//
// No three.js import: node tests drive it with a fake renderer.

export function compileInBackground(renderer, scene, camera, options) {
  const interval = (options && options.interval) || 10;
  const onPoll = options && options.onPoll;
  let pending;
  try {
    pending = renderer.compile(scene, camera);
  } catch (_) {
    return Promise.resolve();
  }
  if (!pending || typeof pending.forEach !== 'function' || !renderer.properties) return Promise.resolve();
  return new Promise(resolve => {
    const poll = () => {
      try {
        if (onPoll) onPoll();
        pending.forEach(material => {
          const program = (renderer.properties.get(material) || {}).currentProgram;
          if (!program || typeof program.isReady !== 'function' || program.isReady()) pending.delete(material);
        });
      } catch (_) {
        pending.clear();
      }
      if (pending.size === 0) resolve();
      else setTimeout(poll, interval);
    };
    poll();
  });
}
