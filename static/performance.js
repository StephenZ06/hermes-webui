/* Lightweight, in-memory interaction timings and stale-intent guards. */
(() => {
  const generations = new Map();
  const surfaceGenerations = new Map();

  function cacheKey(surface, profile) {
    return surface + ':' + profile;
  }

  function now() {
    return typeof performance !== 'undefined' && typeof performance.now === 'function'
      ? performance.now()
      : Date.now();
  }

  function mark(ticket, phase) {
    if (!ticket || typeof performance === 'undefined' || typeof performance.mark !== 'function') return;
    performance.mark(`hermes:${ticket.surface}:${ticket.identity}:${phase}:${ticket.generation}`);
  }

  function begin(surface, identity) {
    const key = cacheKey(surface, identity);
    const ticket = {
      surface,
      identity,
      generation: (generations.get(key) || 0) + 1,
      surfaceGeneration: (surfaceGenerations.get(surface) || 0) + 1,
      startedAt: now(),
    };
    generations.set(key, ticket.generation);
    surfaceGenerations.set(surface, ticket.surfaceGeneration);
    mark(ticket, 'intent');
    return ticket;
  }

  function isCurrent(ticket) {
    return !!ticket
      && generations.get(cacheKey(ticket.surface, ticket.identity)) === ticket.generation
      && surfaceGenerations.get(ticket.surface) === ticket.surfaceGeneration;
  }

  window.HermesPerformance = { begin, isCurrent, mark, cacheKey };
})();
