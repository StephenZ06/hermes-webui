# Hermes WebUI — handoff (2026-10-06)

This is a handoff for an AI coding assistant picking up this repository with no
prior context. It covers what exists, how to work here safely, what is
unfinished, and what to build next. Read it top to bottom once; it is short on
purpose and points to the longer docs.

---

## 1. What this project is

Hermes WebUI is a self-hosted web interface (Python stdlib HTTP server +
vanilla JavaScript, no build step, no framework) for the **Hermes agent**
(a separate checkout at `~/.hermes/hermes-agent`). It has many panels: Chat,
Office (3D agent visualization), Notes, Knowledge, Tasks, Profiles, and
**Jobs** (the "Job OS"), which is where all recent work happened.

**Job OS** is a personal job-search pipeline:

```
Scout (find postings) → Pipeline (Luna scores fit) → Resume Studio (tailor resume)
→ Applications board (apply manually or gated auto-apply) → interviews/offers
```

"Luna" is the AI model used for analysis/tailoring/interview prep:
`openai-codex / gpt-5.6-luna`, called through the agent's
`agent.auxiliary_client.call_llm` (see `api/job_os/llm.py`).

---

## 2. Live deployment (where the running app is)

- The live UI is a **native user systemd unit**, not Docker:
  `hermes-webui-native.service` → runs `server.py` on port **8787** with the
  agent's venv Python (`~/.hermes/hermes-agent/venv/bin/python`).
- **Redeploy** after a code change: `systemctl --user restart hermes-webui-native.service`
- **Verify** the deployed version: `curl -s localhost:8787/sw.js | grep -o "g[0-9a-f]\{7,\}"`
  should print `g<HEAD short sha>`. Last deployed: `g93917b10f`.
- The live server requires auth (curl to API routes returns 401). To check live
  state, run Python in-process instead:
  `HERMES_WEBUI_STATE_DIR=$HOME/.hermes/webui TMPDIR=/tmp ~/.hermes/hermes-agent/venv/bin/python`
  with `sys.path` containing the repo and `~/.hermes/hermes-agent`.
- **Job OS state is global** (not per profile): `~/.hermes/webui_state/job_os/`
  (`job_os.db` SQLite at schema **v7**, `settings.json`, `notify.json`,
  `resume/`, `applications/<job id>/` screenshots).
- **Shared secrets**: `~/.hermes/shared/secrets.env` (mode 600) is layered
  under every profile's `.env` (see `docs/shared-secrets.md`). Gmail
  credentials live there as `HERMES_GMAIL_ADDRESS` / `HERMES_GMAIL_APP_PASSWORD`.
  **Never print, log or copy secret values.**
- **Firecrawl** (scraping) is self-hosted in Docker at `http://localhost:3002`
  from `~/firecrawl` (upstream compose + `docker-compose.override.yaml`).
  Search uses the Brave Search API (`BRAVE_SEARCH_API_KEY`) because SearXNG gets
  blocked. Details: `docs/job-os-firecrawl.md`.
- Git: branch `master`, **378 commits ahead of upstream, never pushed**. Do not
  push unless the user asks.

---

## 3. Rules of the road (read before editing)

1. Read `AGENTS.md` first — it is binding. Key points:
   - Run tests with `./scripts/test.sh <paths>` (never bare pytest).
   - One logical change per commit; no new frameworks/build tools/dependencies
     without justification.
   - Do not edit `CHANGELOG.md` (release workflow owns it).
   - UI changes need before/after screenshots at desktop and narrow widths.
   - A test must fail before the fix and pass after it (prove red/green; the
     pattern used here is `git stash push -m red <src files>` → run test → pop).
   - Commit trailer: `Co-Authored-By: <model> <noreply@...>`.
2. **Never touch real user data destructively.** Do not delete/overwrite
   `~/.hermes`. Use isolated state for experiments:
   ```
   HERMES_HOME=/tmp/x/home HERMES_WEBUI_STATE_DIR=/tmp/x/webui HERMES_WEBUI_PORT=8795 python3 server.py
   ```
   An isolated server has no Codex auth, so AI calls fail there; seed result rows
   into its SQLite DB to view success UI.
3. **Never submit a real job application or fill a real ATS form** while
   testing. Use the fixture forms in `tests/fixtures/job_os_forms/`.
4. `pkill -f server.py` also kills other server processes — kill by verified
   PID only (check `/proc/<pid>/cwd` and the `HERMES_WEBUI_PORT` env).
5. After code changes run `graphify update .` (keeps `graphify-out/` current).
   For codebase questions try `graphify query "<question>"` before grepping.
6. Headless Chromium on this host (WSL2, no GPU) needs
   `--disable-gpu --disable-software-rasterizer` unless you deliberately test
   WebGL (`--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader`,
   slow).

---

## 4. Job OS map (where things are)

Backend `api/job_os/`:

| File | Role |
|---|---|
| `api.py` | All `/api/job-os/*` routes (GET/POST/PATCH dispatch) |
| `schema.py` | SQLite migrations 1–7 (jobs, events, searches, runs, analyses, documents, reply codes, email log, apply runs, interview preps) |
| `models.py`, `repository.py`, `lifecycle.py` | Job records and the allowed status transitions (state machine) |
| `settings.py` | Revisioned `settings.json` (firecrawl, ai, applicant, scout, notifications, auto_apply); rejects secrets |
| `scout.py`, `search_provider.py`, `firecrawl.py`, `ats_api.py`, `extract.py`, `network_policy.py` | Discovery: searches, durable runs, ATS public APIs, JSON-LD extraction, SSRF-safe URL policy, blocklist + cross-site dedupe |
| `scheduler.py` | One background loop (60 s tick): Scout schedule, `notify.tick()`, `autoapply.tick()` |
| `llm.py` | Single path to the model; `_transport` is the test hook |
| `analysis.py` | Fit-score queue + worker |
| `resume.py`, `tailor.py`, `export.py` | Master resume, tailoring (flags unverified numbers), MD/HTML/PDF/DOCX export |
| `applications.py`, `dashboard.py`, `automations.py` | Board columns, attention reasons, funnel, automation summary |
| `notify.py` (+ `api/mailer.py`) | Match alerts, daily digest, reply-to-proceed codes over IMAP |
| `autoapply.py`, `apply_runner.py` | Gated auto-apply orchestrator + Playwright runner (subprocess) |
| `interview.py` | Luna interview prep queue + worker |

Frontend `static/job-os/`: `state.js` (state), `api.js` (fetch wrappers),
`render.js` (all HTML templates), `index.js` (controller: refresh, polling,
actions), `logistics.js` (three.js ES module, lazy-loaded). Styles are in
`static/style.css` (search for `/* ---- ` section markers).

Docs: `docs/job-os-firecrawl.md`, `docs/job-os-email.md`,
`docs/job-os-auto-apply.md`, `docs/shared-secrets.md`. A longer local design
spec (gitignored) is `docs/superpowers/specs/2026-10-02-hermes-job-os-design.md`.

Tests: `tests/test_job_os_*.py` (~220 tests incl. Playwright browser tests).
Run them all: `./scripts/test.sh tests/test_job_os_*.py -q`.

---

## 5. Current status

### Project workspace starter — implemented, not deployed (2026-10-20)

- Chat → New project now opens a workspace-first intake dialog instead of
  creating an unbound sidebar folder.
- A new project is created inside the selected trusted workspace with a brief
  and a template (`blank`, `web`, `ios`, `api`, or `research`). It writes
  `AGENTS.md`, `.agent/ECC_HANDOFF.md`, `README.md`, and template-specific
  docs without ever merging into an existing destination.
- Existing projects can be adopted by selecting an already-saved workspace;
  Hermes only adds missing continuity/template files and preserves existing
  project documents.
- The generated `AGENTS.md` requires future agents to read and update the
  project ECC handoff for every persisted change, while excluding read-only
  questions. It separates changed/tested/committed/deployed/user-verified.
- Focused verification passed: project starter tests, lifecycle-hook tests,
  route-table parity, original Sprint 15 project tests, and JavaScript syntax.
- Deployment and user verification: pending. No commit or service restart was
  performed for this change.

### Shared sidebar motion — fixed and live (2026-10-06)

- Desktop sidebar collapse/expand now uses one FLIP transform for the sidebar
  and the main workspace. The main workspace interpolates **both** its left
  edge and visible width (`translateX + scaleX` with `transform-origin:left
  top`), so it starts from the correct bounds and settles with the sidebar
  instead of jumping or correcting at the end.
- The layout class still changes once only; no per-frame flex/width reflow is
  introduced. Office's layout-motion pause/resume hook remains active during
  the transition.
- The same behavior is implemented in the optional Motion UI path
  (`static/motion-ui.js`) and the native/WAAPI fallback (`static/boot.js`),
  including rapid-toggle cleanup and restoring `transform-origin` at rest.
- Regression coverage: `tests/test_sidebar_slide_rail_browser.py` samples the
  moving main rectangle and requires its left edge **and** width to be between
  their before/after values. The focused sidebar + Office layout run passed 41
  checks, and `npm run lint:runtime` passed.
- Live verification at 1280px confirmed the Chat and Office main workspace
  bounds transition together. Deployed commit: `93917b10f`.

**Done and live** (all Job OS phases):

| Area | Status |
|---|---|
| Scout (search + read postings, schedule) | Done, verified live (6 postings from 4 sites in ~22 s) |
| Luna fit analysis | Done, verified live |
| Resume Studio tailoring + exports | Done, verified live (0 invented numbers) |
| Applications board + funnel | Done |
| Email: alerts, digest, reply codes | Done; Gmail connected and notifications enabled in live settings |
| Gated auto-apply (Greenhouse/Lever/Ashby) | Done; **off** in live settings |
| 3D Logistics centre | Done |
| Blocklist, cross-site dedupe, Automations card, interview prep | Done |

**Not verified end to end** (do these first, with the user):
1. **Email reply round-trip** — the user replies `TAILOR <code>` to a real alert.
   Acceptance requires Gmail's topmost `Authentication-Results` to contain
   `dmarc=pass`; if Gmail-to-Gmail replies lack it, they show as "rejected"
   in Settings → Notifications → log, and `notify.authenticated_from` needs a
   reviewed adjustment (do not just loosen it).
2. **Real auto-apply preview** on a live posting, with the user watching and
   approving. Only a read-only form probe was run against real sites.
3. **Full test suite after the final fixes.** The last sharded run found
   regressions that were fixed and re-run individually, not as a full run.

**Known issues**
- `tests/test_issue2545_xai_oauth_provider.py::test_xai_oauth_model_picker_group_uses_live_catalog`
  fails order-dependently in combined runs, with or without the Job OS
  changes (pre-existing). Passes alone.
- Full sharded runs (5 parallel shards) fill the 7.9 GB `/tmp` tmpfs via
  `/tmp/pytest-of-$USER`; ENOSPC then causes random errors. Clear it between runs.
- The live server's Python has no Playwright; auto-apply runs its browser via
  the repo `.venv` in a subprocess (override `HERMES_JOB_OS_BROWSER_PYTHON`).
  If `.venv` is deleted, auto-apply stops with "Browser automation isn't installed".
- The agent checkout (`~/.hermes/hermes-agent`) is force-reset by WebUI
  updates; any local edits there are lost. Keep custom code in this repo.
- The 3D Logistics WebGL test is opt-in (`HERMES_WEBUI_BROWSER_TESTS=1`,
  ~90 s under SwiftShader).

---

## 6. Recommended next steps (in priority order)

1. **Close the verification gaps** in §5 (reply round-trip, one supervised
   auto-apply preview → approve, full suite run with `/tmp` cleared).
2. **Push / back up.** 378 local commits exist only on this machine. Ask the
   user where they should go (fork remote, private branch) — do not push
   without explicit approval.
3. **Auto-apply hardening** once a real run has been observed:
   - handle Greenhouse's custom comboboxes (location, country, yes/no
     React-selects currently read as unlabeled required fields → run stops);
   - let the user save **standard answers** (work authorization, sponsorship,
     notice period, salary expectation, EEO "decline") in Settings so known
     questions can be answered instead of stopping — still stop on anything
     not pre-answered;
   - record each run's filled values in the timeline for audit.
4. **Email polish**: HTML email version of alerts/digest (currently plain
   text); include the Logistics-style status counts in the digest.
5. **Status sync from email**: read recruiter replies (rejections, interview
   invites) from the inbox and suggest a status change on the board (always
   user-confirmed).

---

## 7. Recommended features (backlog ideas)

- **Follow-up drafts**: for applications with no response after 7 days (the
  board already flags these), have Luna draft a short follow-up email for the
  user to send.
- **Calendar hooks**: when a job moves to *Interviewing*, offer to create a
  calendar event and attach the interview prep.
- **Salary insights**: aggregate `salary_text` across saved jobs into ranges per
  title/location on the dashboard.
- **Company research card**: Firecrawl the company's site/news once per
  company and cache a summary next to the job.
- **Cover-letter tone presets** in Resume Studio (formal / concise / warm).
- **Search quality loop**: let the user thumbs-up/down jobs; feed that back
  into Scout keywords and the analysis prompt.
- **Mobile pass** for the Applications board (works, but cards are dense at
  390 px) and the Logistics view (labels are small).
- **Export**: CSV/Sheets export of the pipeline and applications.
- **Office ↔ Job OS link**: show Job OS background workers (Scout, analysis,
  tailoring, auto-apply) as figures in the Office 3D view.

When building any of these, follow `docs/GUIDELINES.md` (fix the class not the
instance, fail closed when uncertain, test red→green, name the owner of every
piece of state).

---

## 8. Quick command reference

```bash
# tests (Job OS)
./scripts/test.sh tests/test_job_os_*.py -q
# redeploy live UI and check version
systemctl --user restart hermes-webui-native.service
curl -s localhost:8787/sw.js | grep -o "g[0-9a-f]\{7,\}"
# keep the code graph current after changes
graphify update .
# free /tmp after big test runs
rm -rf /tmp/pytest-of-$USER
```

Longer history and gotchas: `.agent/PROJECT_STATUS.md` (newest entries at the top).
# Mobile iOS navigation handoff — 2026-10-13

## Current state

- Work is isolated in `/home/z014/Apps/hermes-webui/.worktrees/mobile-ios` on
  branch `codex/mobile-ios`.
- Current commit: `501bb2094 feat(mobile): finish native iOS navigation`.
- The branch is rebased on current `master` (`086abf6ea`) and the worktree was
  clean at the last status check.
- **It has not been fast-forwarded into `master`, restarted, or deployed.**
- The final `graphify update .` completed successfully after the last code
  changes (56,713 nodes, 109,702 edges, 3,112 communities).

## Implemented

- First recognised left-to-right swipe opens only the icon rail; the second
  opens the full sidebar. There is no partially exposed full drawer.
- Compact-rail icons navigate and close the rail so the selected page is shown.
- Holding a rail icon enables vertical scrub selection with target highlight,
  preview label, light vibration, and one navigation on release. It works in
  compact and full sidebar states.
- Vertical movement before the hold threshold scrolls the overflowing icon
  rail and hands velocity to the existing inertial scroller, keeping lower
  destinations reachable on short phones.
- The iOS edge guard is narrowed while the rail/drawer is visible so it still
  blocks WebKit's back gesture without covering normal icon centres.
- Mobile sidebar page headings and the top title are truly centred. The final
  phone rule resets an older absolute-position transform that previously put
  the top title 72 px right of centre.
- The first-load theme-color fallback is re-synchronised after theme CSS loads,
  addressing the initial Home Screen top-bar colour cover/artifact.
- Jobs keeps its active subpage when the user leaves and returns, and valid
  Jobs/Office deep routes restore after reload. Unknown nested routes fail
  closed to Chat.
- Existing newer main-branch safe-area, bottom-edge, Office, and Resume Studio
  zoom behavior was preserved during rebase rather than replaced by older
  duplicate implementations.
- Tests and UI guidance were added/updated in the same commit.

## Verification already completed

- `npm run lint:runtime` — passed.
- JavaScript syntax checks for `boot.js`, `panels.js`, and Job OS files — passed.
- Focused mobile/PWA/browser suite after final review fixes: **42 passed**.
- Wider mobile suite before the final three review fixes: **57 passed**; the
  affected tests were rerun in the 42-test final set.
- Job OS suite: **256 passed, 3 skipped**.
- Real touch-path standalone gate using the repo Playwright runtime:
  `./.venv/bin/python tests/browser_mobile_edge_swipe.py` — passed after the
  final rail scrolling/edge-guard changes.
- `git diff --check` — passed before the final amend; rerun once more before
  merge.
- Independent review found three Important issues (nested Jobs route loss,
  permissive unknown subroutes, and unreachable lower rail icons). All three
  were fixed and regression tests added. A re-review was requested from
  `/root/mobile_review`, but its final response had not arrived before handoff.

## Remaining steps — do these in order

1. Confirm the mobile worktree is clean:
   `git status --short` and `git diff --check`.
2. Obtain/read the requested final review from `/root/mobile_review`. Fix any
   remaining Critical/Important findings and rerun affected tests.
3. Rerun final gates from the mobile worktree:

   ```bash
   npm run lint:runtime
   ./scripts/test.sh -q tests/test_mobile*.py tests/test_pwa_sidebar_swipe.py
   ./scripts/test.sh -q tests/test_job_os*.py
   ./.venv/bin/python tests/browser_mobile_edge_swipe.py
   ```

4. Perform final visual QA at 430x932 for Chat closed/icons/full drawer and at
   least Office plus one content-heavy page. The automated browser checks use
   this viewport, but physical iPhone Home Screen Safari remains the one manual
   device check that cannot be proven here.
5. Fast-forward only after all gates are green:

   ```bash
   cd /home/z014/Apps/hermes-webui
   git merge --ff-only codex/mobile-ios
   systemctl --user restart hermes-webui-native.service
   ```

6. Verify the actual live runtime, not just the checkout:

   ```bash
   systemctl --user --no-pager --full status hermes-webui-native.service
   curl -fsS http://127.0.0.1:8787/health
   curl -fsS http://127.0.0.1:8787/static/boot.js | grep -F "sidebar-nav-scrub-preview"
   curl -fsS http://127.0.0.1:8787/ | grep -F "data-initial-theme-color-sync"
   ```

7. Smoke-test the live 8787 page at mobile width, then record the deployed
   commit and results in this handoff. Do not claim live deployment before the
   service and served-asset checks succeed.

## Optional mobile improvements to discuss, not yet implemented

- A bottom tab bar for the 3–5 most frequently used destinations.
- Bottom sheets in place of centered dialogs on phones.
- A consistent pressed/haptic language and sticky large page titles.
- Offline/reconnect banners and skeleton loading states.
- Compact density modes for Logs, Knowledge, and Tasks.
- A documented nested swipe-back policy for inner detail views.

## Outcome — 2026-10-13 (continued from this handoff)

- Final review (stood in for the unreachable `/root/mobile_review`): one
  Important finding fixed in `a3d9b2033` — while the icon rail was out, the
  edge guard was only 8px and the rail's touch listeners were passive, so a
  left-to-right swipe starting on an icon inside WebKit's ~30px edge zone
  could still become iOS Back. The rail's touchstart now cancels touches in
  that zone and replays a still tap as a click. The edge-swipe gate gained a
  check (failed before, passes after).
- Gates on the branch: `npm run lint:runtime` passed; mobile + PWA swipe
  tests 60 passed; Job OS 256 passed, 3 skipped;
  `tests/browser_mobile_edge_swipe.py` passed.
- Visual QA at 430 wide (873 tall web view, as the opaque status bar gives):
  icon strip, full drawer, Office and Insights looked right. Playwright
  `page.screenshot` stalls on this host for this context (also on master);
  CDP `Page.captureScreenshot` works.
- `master` fast-forwarded to `a3d9b2033`, service restarted, live
  `sw.js` reports `ga3d9b2033`, `/health` ok, served `boot.js` contains the
  scrub preview and the edge-zone guard.
- Not done: live 8787 mobile smoke test and the `data-initial-theme-color-sync`
  check on `/` — both need a logged-in session (`/` redirects to login).
  Physical iPhone Home Screen check still pending with the user.

## Outcome — 2026-10-20: Files page

- Added a dedicated **Files** destination in `e5b888dfc` (now fast-forwarded
  into `master`). It resolves only registered local Spaces and available
  project-registry workspaces; the browser never supplies an absolute root.
- Local spaces support browse, preview/edit/save, create file/folder, rename,
  move, upload (25 MB cap), download, and confirmed delete using existing
  anchored file helpers. SSH registry projects deliberately remain browse and
  text-preview only because `api/ssh_workspace.py` is explicitly read-only;
  no remote write shell commands were introduced.
- Verification in the feature worktree: focused backend, authorization,
  workspace-symlink, route-table, desktop-browser, and phone-browser tests:
  **74 passed**; `npm run lint:runtime` and `git diff --check` passed.
- `graphify update .` completed. `hermes-webui-native.service` was restarted;
  `/health` returned `ok` and the live server serves `static/file-manager.js`.
  The API itself requires the normal logged-in browser session, so an unauthenticated
  curl to `/api/file-manager/workspaces` correctly returned 401.
