# JOBOS UI Redesign — Implementation Specification

**Status:** Implementation brief for an existing product  
**Scope:** Dashboard, Scout, Pipeline, Resume Studio, Settings; shared shell and mobile behavior  
**Primary rule:** Inspect the running application, repository, APIs, data model, and current tests before changing UI. Preserve functioning logic and persisted user data.

## 1. Intent and visual authority

JOBOS should feel like a focused daily workspace for finding jobs, reviewing them, moving applications forward, tailoring a truthful resume, and maintaining the connections and automations that support that work. The redesign improves hierarchy, scanability, and consistency across five existing pages. It is a visual and interaction refactor unless a specific missing behavior is verified; it does not authorize rebuilding working business logic.

The approved direction is near-black and charcoal surfaces, fine neutral borders, restrained blue accents for primary action and selection, and semantic color only where status demands it. Use gradients sparingly, if at all. Keep a selective terminal flavor in small labels, timestamps, technical metadata, and occasional monospace numerals; use a highly readable sans-serif for body copy, forms, card content, and longer explanations. Avoid terminal styling that makes the main interface tiring to read.

Treat the conversation's screenshots and mockups as visual references, then compare them against the current build. The available source screenshots show the existing Settings connections screen and Resume Studio master resume, skills, match check, and tailored versions. They establish content and workflow, not an exact pixel contract. If a reference image is unavailable, do not invent hidden controls or change established behavior based on a guess. Capture current desktop and mobile screenshots before implementation and use them as the baseline for review.

### Product truths to retain

- Dashboard: KPIs, application funnel, action center, automations, activity, recent jobs.
- Scout: search/filter workflow, result browsing, job detail, and existing source behavior.
- Pipeline: application stages, Kanban, collapsed columns, drag and drop, list view, job/application detail.
- Resume Studio: original/master resume, gained skills, match analysis, job selection, tailored versions, truthful tailoring.
- Settings: section navigation, connection health, Firecrawl, Gmail sender, job sites, Scout schedule, Luna, notifications, profile and related answers.
- Existing terminology, saved values, permissions, profile scope, scoring rules, integrations, and server contracts remain the source of truth until verified in the repository. The labels above name product areas; they are not permission to change backend semantics.

## 2. Discovery and change boundaries

Before estimating or coding, the implementing agent must:

1. Locate the actual JOBOS repository and identify framework, router, component system, styles, breakpoints, state management, API client, test setup, PWA manifest/service worker, and deployment path. Record a concise route-to-component and component-to-endpoint map for the five pages.
2. Run the app in its supported local mode. Capture desktop, narrow tablet, and iPhone-class screenshots for every page and every materially different state. Inspect the supplied references alongside the current build. Inventory loading, empty, error, disconnected, pending, and success states.
3. Check repository status and preserve unrelated changes. Make small, scoped patches. Reuse existing components, hooks, services, API calls, mutations, and tests. Refactor shared UI only where it demonstrably reduces duplication.
4. Trace each interactive control to its existing handler and server effect before redesigning it. Write down any genuine behavior gap separately; do not replace working pipelines, auth, scraping, scheduling, email, AI prompts, scoring, or file generation as part of a visual task.
5. Confirm the authoritative design values with current assets and prior approved mockups. The token values below are starting values, not evidence of values already present in the app.

**Out of scope unless separately approved:** changing job matching formulas, generating new resume claims, reworking provider credentials, altering scheduling cadence, migrating database records, changing email delivery semantics, rebuilding the frontend stack, or adding integrations. No mock data in production views.

## 3. Design system

### 3.1 Proposed tokens

Implement as semantic variables in the app's existing token mechanism. Keep one source of truth; do not scatter hard-coded values. Verify contrast in the actual font and browser rendering.

| Role | Proposed value | Usage |
|---|---|---|
| `canvas` | `#0B0D10` | App background |
| `surface-1` | `#11151A` | Page panels and navigation |
| `surface-2` | `#171D24` | Raised cards, controls, hover |
| `surface-3` | `#202833` | Selected neutral surface |
| `border` | `#29323D` | Dividers and card boundaries |
| `text-primary` | `#F2F5F8` | Titles, values, primary copy |
| `text-secondary` | `#B2BDC9` | Labels and support copy |
| `text-muted` | `#8896A5` | Metadata, never essential-only information |
| `accent` | `#5FA9E6` | Primary CTA, focus, selected navigation |
| `accent-hover` | `#80BEED` | Hover emphasis |
| `accent-tint` | `#173047` | Selected/pending background |
| `success` | `#56C48A` | Connected, ready, completed |
| `warning` | `#E8B75C` | Needs review, partial issue |
| `danger` | `#EC7377` | Failed, destructive, hard error |
| `info` | `#78B6E8` | Informational status |

Use semantic foreground/background pairs for status chips, not raw status text on the canvas. Check WCAG contrast for normal text (at least 4.5:1) and large text/UI boundaries (at least 3:1). A score category may have semantic color, but its number and plain-language label must communicate the result without color. Do not use purple as an alternate generic accent.

Use an existing licensed/system sans stack as the primary face. Use the incumbent mono face only for narrow metadata and machine-like identifiers. Suggested type scale: 12px metadata, 14px compact controls, 16px body, 20–24px section headings, 28–32px page headings; maintain at least 1.45 line height for prose. Avoid all-caps paragraphs and long monospace explanations. Spacing scale: 4, 8, 12, 16, 24, 32, 40px; radii 8px controls, 12px cards, 16px large drawers. Keep shadows soft and minimal; surfaces should be distinguished mostly by tone and border.

### 3.2 Shared shell and components

- A consistent page header: title, one-sentence purpose, key page action, optional last-updated state. Avoid repeating the same explanation in cards.
- Desktop navigation: existing app shell with clear active route. Preserve route names and browser history. Narrow layouts use the app's established menu pattern, with visible page title and a reliable way back.
- Shared `SectionHeader`, `MetricCard`, `StatusBadge`, `JobRow/Card`, `FilterControl`, `EmptyState`, `InlineAlert`, `Skeleton`, `Confirmation`, `Drawer`, `FormField`, and `ActionMenu` concepts. Use the repository's naming conventions and component library; these names are responsibilities, not mandated files.
- Every control needs default, hover (when relevant), pressed, focus-visible, disabled, loading, success, and error treatment. Status badges show icon/label and timestamp or explanatory detail where useful.
- Use the same job title/company/location/source metadata pattern in Dashboard, Scout, Pipeline, and Resume Studio. Link to a canonical job detail instead of copying inconsistent summaries.
- Place overlays in a top-level portal/dialog layer so drawers, menus, and tooltips cannot be clipped by scroll containers. Define z-index, scroll lock, focus return, Escape close, outside click, and unsaved-edit behavior once.
- Replace generic spinners in content regions with layout-stable skeletons; reserve a small inline spinner for an action in progress. Empty states explain what creates data and offer a valid next action.
- Motion communicates a state change (open drawer, move card, expand column, apply filter). Typical durations 150–250ms; respect reduced-motion preferences. Avoid ambient gradients, glows, and page-load choreography.

## 4. Dashboard

**Purpose:** A daily command view that answers “How is the search going, what needs attention, and what changed?” Above the fold, prioritize decisions over decoration.

### Layout and content

1. **Header:** page title, contextual subtitle, time range or freshness if supported, and the existing primary action (such as opening Scout). Do not imply live updates if data is cached.
2. **KPI strip:** a compact grid of the app's actual measures (for example jobs found/saved, applications in progress, interviews, offers or response rate, only if supported). Each card has a plain label, strong value, definition or tooltip, and period/comparison only when the source supports it. Counts link to the relevant filtered view. Never mix lifetime and period totals without labels.
3. **Application funnel:** stages and counts derived from canonical pipeline statuses. Show direction and conversion only when denominators are meaningful; handle zero counts and unknown stages. Each stage links to Pipeline with its filter. Use labels and values alongside any bars.
4. **Action center:** a short, ranked list of actionable items from existing data: applications awaiting follow-up, jobs needing review, failed automation/connection, unreviewed match, or unsent work as available. Show reason, related job, age/due date, and a one-step action. Deduplicate items that would send the user to the same issue. If no work is pending, show a calm all-clear state.
5. **Automations:** status of Scout schedule, relevant provider health, Luna processes, and notification delivery where the backend exposes them. Show last run, next run, and failure reason only when known. “Running” and “enabled” are distinct. Link to the corresponding Settings section; avoid a fake toggle if no mutation exists.
6. **Activity:** chronological, human-readable events with timestamps, actor/source if available, and links to affected records. Group same-day repetitive events when useful. Preserve a way to see more rather than rendering an enormous feed.
7. **Recent jobs:** a scannable table/list with title, company, location/remote, source, discovered time, match/status as supported, and quick actions already available in Scout or Pipeline. Rows remain navigable independently of quick actions.

### Dashboard states and acceptance

Render KPI and funnel sections independently so a slow feed does not blank the page. A partial API failure shows the last reliable sections plus a localized retry. Empty new-account, no-jobs, and no-activity states have distinct copy. No calculated value may disagree with the canonical Pipeline or Scout view for the same filters. A keyboard user can reach every card link and action in logical reading order.

## 5. Scout

**Purpose:** Find and assess opportunities quickly, without losing a search while inspecting a job.

### Filters and results

- Keep the existing search terms and supported facets. Group primary filters (query, location/remote, source, recency, match or status if real) in the visible toolbar; put less-used filters in an expandable panel. Display the active-filter count and removable chips. “Clear all” must restore the actual default query state, not silently erase saved preferences.
- Inputs have explicit labels and apply semantics. Debounce only controls that already have safe query behavior; use an Apply button where a request is expensive. Show result count, sort choice, last searched/updated time if known, and an honest loading state.
- Results use a consistent job card/row: title, company, location, source, posting/discovery time, salary when genuinely present, concise summary, match/fit if computed, and pipeline state. Avoid empty placeholder labels. Make the title/action target predictable; quick actions must not open the job accidentally.
- Clearly distinguish saved, dismissed, already applied, unavailable, and newly found jobs. Preserve the existing semantics for each action, including undo where supported. Pagination/infinite loading must retain scroll and filters on return from details.
- A zero-result search reports which filters are active and offers a clear adjustment. Search errors provide retry without discarding user input. A job removed upstream remains explainable from locally stored records if the backend supports that.

### Detail drawer

Open from a result without destroying result state. Desktop uses a right drawer sized for readable job content; narrow screens use a full-height sheet/page with safe-area padding. Header contains job title, company, close/back, source link, and supported save/pipeline actions. Body separates overview, location/compensation, description, requirements, match evidence, and provenance only where the data exists. Show original text/source clearly; avoid AI summaries masquerading as posting facts. Sticky actions must not cover content or keyboard focus. Deep links should restore the same job where routing supports them.

## 6. Pipeline

**Purpose:** Track applications by stage and take the next action with confidence.

### Kanban and collapsed columns

- Render columns from the existing stage model in its canonical order and spelling. Each column header shows stage label and count. Cards show job/company, key next-step/date, recent activity, and compact flags, without becoming miniature detail pages.
- Allow users to collapse/expand columns to save horizontal space; the collapsed rail retains title, count, and a clear expand target. Preserve this display preference per profile or browser according to existing settings conventions. Never conflate a collapsed column with an empty column.
- Board scroll is intentional: horizontal for columns, vertical within columns only if the established implementation does so well. Avoid nested scrolling traps. Use visible edge affordance on touch.
- Drag and drop provides clear pickup, destination, and optimistic feedback. A move invokes the existing stage transition/mutation, including validation and side effects. On rejection, restore the original card and announce the reason. Do not silently skip required steps or trigger duplicate mutations. Offer an accessible “Move to…” menu with equivalent behavior for keyboard and touch.
- Keep stable card identity while sorting/filtering. If a stage change is pending, prevent a second conflicting move. Preserve scroll, filters, and selection across successful moves.

### List view and detail drawer

List view is an alternate presentation of the same records and filters, with sortable columns only where supported: job/company, stage, updated date, next step, source or owner if real. Switch views without losing the user's selected record or filter context; remember the view preference. On mobile, default to a compact list or stage selector rather than forcing a tiny Kanban board.

The application drawer shows job details, timeline/notes, stage, next action, resume/version linkage, and existing actions as available. Use one canonical update path for edits from both views. Provide confirmation for destructive actions and visible save/error feedback. Exiting with unsaved edits follows the app's established policy and never silently discards data.

## 7. Resume Studio

**Purpose:** Keep the master resume authoritative, compare it to real jobs, and inspect truthful tailored outputs.

### Master resume and gained skills

- Lead with the master resume card: actual file preview/thumbnail, filename, version/update metadata, status, open/download if supported, and Replace. The screenshot shows an “Original” indicator, a PDF preview, word count, update date, and a “Design kept for tailoring” setting. Preserve the current document and setting values; clarify copy and hierarchy. Replacing a file must confirm accepted type/size, show upload/progress/error, and update dependent analysis only according to existing backend behavior.
- A “Show text” disclosure displays extracted text with readable line wrapping and a way back to the visual preview. Never expose sensitive resume text in logs or unrelated views.
- The gained-skills area shows verified user-entered skills, their provenance (e.g. completed course), and Manage skills. Use clear edit/remove flows and validation. Distinguish these from model-inferred keywords. Tailoring may include a gained skill only when the user's record supports it; no invented experience, certification, dates, employers, or tools.

### Match check and job selection

- Select a job from existing Scout/Pipeline records with searchable title/company and stable identifier. Preserve the selected job when returning to the page, subject to profile scope. If the current UI cycles through jobs, keep previous/next and position (the screenshot shows a count like “1 of 116”), with a direct selector for larger sets.
- Present score as number plus plain-language category and explanation. Keep backend score thresholds and wording unless the owner approves a change; the screenshot's legend is evidence of current categories, not a mandate to recalculate. Do not replace a score with an ornamental gauge alone. Separate matched evidence from missing requirements, with links back to the posting/resume source when supported. Claims must be grounded in actual resume and job text.
- “Score again,” “Open job,” “Tailor & next,” and “Automate all” must keep their existing semantics, queueing, permissions, and failure behavior. Show explicit pending/progress and prevent duplicate requests. A long-running batch must remain observable after navigation if the backend exposes job status. Do not imply success before a version is created.

### Tailored versions

Show each version as a row/card with job title, company, creation date, status (ready, processing, failed), match/keyword metric only if meaningful, and available open/download/retry/delete actions. The screenshot shows both ready and failed items; failure detail and retry should be recoverable without hiding previous successful versions. Selecting a version opens its detail and original job relationship. Keep master versus tailored versions visually and semantically distinct. Preserve existing version history and file identifiers through the redesign.

## 8. Settings

**Purpose:** Make profile-scoped configuration understandable and safe to change. The current screenshot uses a left section navigation with Accounts, Automation, and You; preserve that mental model while improving readability and hierarchy.

### Navigation and common behavior

- Group sections: **Connections** (Firecrawl, Gmail sender, job sites, Apify if present), **Automation** (Scout schedule, Luna, notifications), **You** (profile details, application answers, master resume link). Active section shows label, short status, and focus/selected state. Desktop may retain the left rail; mobile uses a compact section index or anchored tabs that do not trap scrolling.
- Each section starts with a concise explanation and current state. Separate read-only system facts from editable controls. Form values come from the active profile and retain unsaved edits while navigating within the section; switching profiles or leaving with dirty edits follows an explicit confirmation policy.
- Save/test/check actions show pending, success with timestamp, and actionable failure details. Never reveal tokens, passwords, full credentials, or private configuration values in status messages or client logs. Credential operations use established server flows.

### Connections

- **Firecrawl:** status, endpoint origin/override, latency/last test if real, editable URL override if currently supported, Test connection. The screenshot shows an `.env` fallback and local endpoint. Explain whether blank means “use server default”; do not leak server secrets or present localhost as a universal production address. Validate URL and show the effective connection source without exposing protected configuration.
- **Gmail sender:** connected/disconnected state, masked sender address, per-profile sender name/identity if supported, existing test-send choice, Send test email, Replace, Disconnect. Describe exactly where the test goes using the current notification address rule. Confirm disconnect and preserve OAuth/account behavior. A test email must be explicitly user-triggered and report failure honestly.
- **Job sites:** list each configured source and health, last check, change state, and Check now if supported. Explain that Scout reads sites and how scheduled checks relate to active searches, using verified backend behavior. The screenshot shows a remote.id entry and a “checked 7h ago” indicator; use real timestamps and never hard-code a site as healthy.
- **Apify or other existing providers:** keep their current settings and status in the section index, using the same connection card treatment. Do not add an integration merely because it appears in navigation.

### Automation and profile

- **Scout schedule:** enabled state, timezone, cadence, next run, last run, and recent result if exposed. Edits use current scheduling API and validation. Distinguish paused, scheduled, running, completed, and failed; do not invent a next-run time client-side when the server is authoritative.
- **Luna:** model/agent label, availability, permitted automation scope, and existing options. Make potentially costly or batch actions explicit, with current defaults and progress. Do not edit prompts, model, or autonomy silently during a UI pass.
- **Notifications:** channel status, destination (masked where appropriate), event types, quiet hours/digest settings only if already supported, test action if present. Explain dependency on Gmail sender where applicable. Save failures retain user edits.
- **Profile:** details and application answers remain profile-scoped. Provide field labels, validation, save state, and route to master resume. Avoid accidental cross-profile edits and show the active profile visibly.

## 9. Responsive mobile and PWA

- Target narrow screens from approximately 320 CSS px upward, including an iPhone 15 Pro Max in Safari and installed Home Screen mode. Test portrait and landscape where the app supports them; do not rely on a single device pixel size. No horizontal page overflow. Respect text zoom up to 200%.
- Honor `env(safe-area-inset-top/right/bottom/left)` for fixed headers, sheets, sticky actions, bottom navigation, and the home indicator. Do not draw essential controls under the Dynamic Island or home indicator. Keyboard opening must keep focused form fields and save controls reachable.
- Minimum touch target about 44×44 CSS px, with separation for adjacent destructive and primary actions. Tap and long-press behavior should not rely on hover. Prefer explicit menus over mobile drag as the only way to change Pipeline stage.
- KPI cards stack or form a two-column grid when space allows. Dashboard funnel becomes a labeled vertical sequence; activity and recent jobs become compact lists. Scout filters open as a full-height sheet and persist when closed. Job and Pipeline drawers become full-screen or near-full-screen detail views with a clear back action. Resume Studio comparison sections stack in a reading order of score, rationale, matches, missing items, actions. Settings section index stays easy to reach.
- Preserve existing PWA manifest, installability, icons, service worker, and cache strategy. Verify route refresh, back navigation, offline/error presentation, and recovery after an app update. Do not cache private resume text, tokens, or stale mutation responses unintentionally. Ensure viewport and `viewport-fit=cover` behavior is correct for the target device.
- Avoid scroll locking that strands users inside nested panels. Test swipe gestures alongside browser back/forward and the app's own navigation. A horizontal board gesture must not trigger a destructive action.

## 10. Accessibility and content standards

- Meet WCAG 2.2 AA for the redesigned surfaces. Use semantic headings, landmarks, lists/tables, form labels, and buttons/links. All actions are keyboard operable; visible focus meets contrast requirements.
- Drawers and dialogs announce their label, trap focus only while modal, close by Escape where appropriate, and return focus to the trigger. Menus expose expanded state. Drag/drop has the equivalent Move menu and announces source, destination, success, or failure.
- Announce asynchronous saves, connection tests, job moves, score results, and failures through appropriate live regions without repeated chatter. Keep status understandable without color, icon, or motion alone.
- Write concise, specific UI text: “Connection test failed: [safe reason]” and next action where known. Avoid saying “connected,” “ready,” or “sent” until server confirmation. Format dates with timezone context where it affects scheduling. Do not fabricate company, salary, job, score, or resume facts.
- Respect `prefers-reduced-motion`, high zoom, and mobile screen readers. Charts/funnel visualizations have text equivalents and accessible labels.

## 11. State preservation and backend constraints

| State | Preservation rule |
|---|---|
| Active profile | Every query/mutation remains correctly scoped; a profile switch invalidates stale data and prevents cross-profile writes. |
| Scout query, filters, sort, pagination, scroll | Preserve during detail inspection and back navigation; persist only according to current app conventions. |
| Pipeline stage, view, collapsed columns, filters, scroll | Use stable IDs; preserve across view switch and successful mutation. |
| Resume selected job/version and expanded analysis | Preserve across safe navigation; invalidate only when source data or profile changes. |
| Settings draft form values | Do not overwrite with background refresh; warn on relevant unsaved navigation. |
| Async jobs and mutations | Show pending, confirmed success, recoverable failure; prevent duplicate commands and reconcile server state. |

Keep existing endpoint paths, payloads, response shapes, auth, rate limits, error codes, and idempotency semantics. Use the established API client. Do not infer status from a button click. Server data remains authoritative after an optimistic update; rollback on error. Do not add polling unless there is an existing long-running task contract and a bounded update strategy. Confirm how dashboard aggregates relate to source records before displaying derived numbers. If a needed field or endpoint is absent, document the gap and use a truthful fallback state; do not fabricate client data.

## 12. Architecture guidance

Follow the repository's framework and file organization. Build the redesign as a shared token layer and a small number of reusable visual primitives, with page-owned composition and existing domain hooks/services underneath. Keep presentation components ignorant of provider credentials, scoring implementation, and scheduling internals. Route-level data loaders or hooks own fetching; shared UI receives normalized view models and explicit callbacks. Avoid a giant “JobOS page” component and avoid moving backend decisions into CSS or rendering code.

Before creating a new component, find the closest incumbent. Consolidate duplicated job metadata, status chips, drawer behavior, and async action feedback only where the inputs and semantics actually match. Keep data models and API adapters stable. If the app already has a design system, extend its semantic tokens rather than layering a competing theme. Use feature flags or staged route rollout if the repository uses them; the default rollout must preserve existing user data.

## 13. Stepwise execution plan

Each phase produces a reviewable, working state. Record actual repository paths, affected APIs, and test commands after discovery; this brief intentionally does not invent filenames or endpoints.

- [ ] **Phase 0 — Baseline:** map routes/components/API contracts; document current states; capture reference screenshots and responsive behavior; run existing tests; note dirty worktree and data preservation needs.
- [ ] **Phase 1 — Foundation:** implement semantic tokens, type/spacing conventions, shared shell, buttons/fields/status/empty/loading patterns, drawer mechanics, and responsive safe-area primitives. Verify representative views before broad rollout.
- [ ] **Phase 2 — Dashboard:** rebuild hierarchy around KPI strip, funnel, action center, automations, activity, and recent jobs. Verify all values and links against source pages.
- [ ] **Phase 3 — Scout:** refine filters, result density, state chips, and detail drawer; preserve search state and existing mutations.
- [ ] **Phase 4 — Pipeline:** refine Kanban and collapsed columns, stage moves, list view, and detail drawer; verify failure rollback and keyboard/touch alternative.
- [ ] **Phase 5 — Resume Studio:** refine master/skills/match/job selection/versions; verify truthful source mapping and all long-running states.
- [ ] **Phase 6 — Settings:** reorganize section navigation and connection/automation/profile cards, then verify actual integration and save/test flows.
- [ ] **Phase 7 — Cross-page QA:** desktop, tablet, iPhone Safari and installed PWA, keyboard, screen reader, zoom, reduced motion, cross-profile state, slow/offline/error conditions. Fix verified defects and compare against approved visual references.

Recommended effort: **high**. Five interdependent pages, profile-scoped state, mobile/PWA behavior, and provider workflows make this a coordinated redesign even though backend logic should stay intact. Implement in small reviewable increments rather than one large visual patch.

## 14. Test and verification matrix

### Automated checks

- Existing unit/integration suites must pass before and after each phase. Add focused tests for new shared components and state transitions only where they prevent a concrete regression.
- Verify route navigation, query/filter restoration, drawer focus/close behavior, Pipeline move success and server rejection, list/Kanban parity, settings unsaved form behavior, and profile switch isolation.
- Add API contract tests only if adapters or request shapes change. Snapshot tests alone are insufficient for interaction correctness.
- Run the repository's lint/type/build checks and accessibility checks. Test semantic status labels and contrast, not merely DOM presence.

### Manual journeys

1. New profile with no jobs/resume/connection: every page gives a clear next step and no fake data.
2. Populated profile: filter Scout, open/close a job, save or act, return with filters and scroll intact; verify Dashboard and Pipeline reflect confirmed server state.
3. Move an application in Kanban and via keyboard/touch menu; reject one invalid move and confirm rollback, error copy, and no duplicate transition.
4. Select a job, inspect match evidence, trigger an allowed rescore/tailor action, and inspect ready and failed versions without losing the master resume.
5. Edit and test each available Settings integration; confirm masked values, success/failure, active profile, and no lost unsaved edits.
6. Repeat critical journeys at narrow width in Safari and installed PWA, including keyboard open, safe areas, browser back, refresh, and app resume.

### Visual review

Capture each page at desktop and iPhone-class viewport in normal, loading, empty, and error states where meaningful. Compare with the approved mockups for surface tone, blue accent restraint, typography hierarchy, spacing, and density. Inspect long job titles, missing salary/location, large counts, lengthy error text, and a long translated/string-expanded label. Repair layout issues in a bounded review pass.

## 15. Acceptance criteria

The redesign is complete when all of the following are true:

- The five pages share the approved near-black/charcoal language and restrained blue action/selection vocabulary; semantic colors are reserved for status and remain readable.
- Every named section and workflow in this brief exists or has an explicit repository-backed reason it is unavailable. Existing actions preserve their original server behavior and profile scope.
- Dashboard values reconcile with Scout/Pipeline sources; no placeholder or speculative data appears as fact.
- Scout filters and result context survive detail inspection; Pipeline view switching and stage moves preserve context, with rollback on failed mutations.
- Resume Studio keeps the master file authoritative, makes match reasoning inspectable, and never presents invented qualifications or a pending output as ready.
- Settings reports verified connection/schedule/notification state, masks sensitive details, retains draft edits, and surfaces actionable failures.
- iPhone-class Safari and installed PWA have no clipped essential controls, unsafe inset placement, accidental horizontal page overflow, or touch-only dead ends.
- Keyboard and screen reader users can complete the core journeys; focus, status announcements, contrast, zoom, and reduced motion have been checked.
- Existing tests plus focused regression tests, lint/type/build checks, and the manual journeys above pass. Record commands, screenshots, and any remaining limitations in the implementation handoff.

## 16. Handoff instructions for the implementing agent

Start by inspecting the repository and its running app. Reconcile this specification with actual routes, components, backend contracts, screenshots, and approved mockups. Keep all functioning logic and data intact. When the UI reference conflicts with a real backend capability, preserve the real capability and flag the design decision. Implement phase by phase, verify server-confirmed behavior, and report separately what was coded, tested, deployed, and user-verified. Do not claim the redesign is live from a passing local build alone.
