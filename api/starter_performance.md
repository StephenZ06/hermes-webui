# Performance checklist

<!-- hermes:performance:begin -->
Run this before calling any task in this project finished. It applies whenever
a change touches something on the list (a new page, screen, list, search box,
API call, image, font, dependency or query).

## How to use it

- **Applicable items are required.** If an item fits the project and the
  change, do it.
- **Skip items that don't fit.** For example, there is no database to index,
  the app runs as one local instance, or there are no images. Give a short
  reason for each skip.
- **Check what already exists first.** Many items may already be in place.
  Verify them instead of re-adding them.
- **Measure where you can.** Check the network panel, payload sizes, query
  counts and render counts before and after. Don't assume an item helps.
- **Dependencies:**
  - Install a library only when an item really needs one and the project
    allows it.
  - This project's own rules win (AGENTS.md, CONTRIBUTING.md, "no new
    dependencies" policies). If they forbid it, use a built-in or hand-rolled
    approach, or skip the item and say why.
  - Ask before adding paid or externally visible infrastructure, such as a
    CDN, a Redis server, load balancers, moving servers or a tracing
    backend.
- **Report at the end.** In the final summary, add a short "Performance
  checklist" note covering:
  - what was applied
  - what was already in place
  - what was skipped, and why

## Checklist

### Loading and rendering

- [ ] Add skeleton loading screens where content loads asynchronously.
- [ ] Render pages on the server or at build time where the stack supports it.
- [ ] Split JavaScript by page or route, so each page loads only its own code.
- [ ] Load third-party scripts after the page (`defer`, `async`, or on idle or interaction).
- [ ] Virtualize long lists.
- [ ] Prevent unnecessary re-renders (memoization, stable references, targeted DOM updates).
- [ ] Update the UI before the server responds (optimistic UI), and roll back on error.
- [ ] Stream AI responses token by token.

### Assets

- [ ] Serve images as WebP or AVIF, keeping a fallback where it's needed.
- [ ] Lazy-load images below the fold (`loading="lazy"`, with explicit width and height).
- [ ] Self-host fonts, and limit the number of weights and subsets (use `font-display: swap`).
- [ ] Enable browser caching for static files (hashed or versioned names, long `Cache-Control`).
- [ ] Serve static files through a CDN.
- [ ] Enable Brotli or Gzip compression.
- [ ] Remove unused dependencies.

### Requests and APIs

- [ ] Prevent duplicate API calls (dedupe in-flight requests, cancel stale ones).
- [ ] Debounce search and autocomplete inputs.
- [ ] Paginate API results.
- [ ] Load independent requests in parallel, not one after another.
- [ ] Set timeouts on calls to external APIs.

### Backend and data

- [ ] Fix N+1 queries.
- [ ] Add database indexes for common queries.
- [ ] Cache frequently accessed data with Redis (or the project's existing cache).
- [ ] Move slow tasks to a background job queue.
- [ ] Trace slow backend requests with OpenTelemetry.
- [ ] Place servers close to the database.
- [ ] Load-balance traffic across multiple app instances.
<!-- hermes:performance:end -->
