# Hermes Agent Canvas — FounderOS UI Migration & Real Subagent Orchestration

**Purpose:** Replace the existing **Agent Canvas frontend** in the Hermes WebUI with a FounderOS-inspired Conductor / organization UI, while keeping **Hermes Agent as the only real orchestration backend**.

**Reference repositories**
- FounderOS DEMO: https://github.com/Bennettxai/FounderOS-DEMO
- Hermes Agent: https://github.com/NousResearch/hermes-agent

**Reviewed against current upstream code:** 2026-08-18

---

## 1. Goal

Implement the Agent Canvas as a live visual control surface for the real Hermes delegation tree.

The desired behavior is:

```text
User
  |
  v
Main Hermes Session / Conductor
  |
  | Hermes decides to call delegate_task
  |
  +----------------+----------------+----------------+
  |                |                |                |
  v                v                v                v
Subagent A       Subagent B       Subagent C       ...
running          running          queued/running
  |                |
  |                +------ optional nested delegation ------+
  |                                                       |
  v                                                       v
result                                                 grandchild
  \                                                       /
   +--------------------- results -------------------------+
                              |
                              v
                    Main Hermes synthesizes
```

The Agent Canvas must **visualize actual Hermes subagents**. It must not create a fake org chart whose workers exist only in frontend state.

---

# 2. Non-Negotiable Architecture Rule

## Hermes owns orchestration

Do **not** replace Hermes' orchestration logic with FounderOS logic.

FounderOS should be treated as:

- a UI/design reference,
- a source of reusable presentational components,
- a source of layout ideas for the Conductor and agent cards.

Hermes remains responsible for:

- deciding whether to delegate,
- calling `delegate_task`,
- spawning children,
- spawning parallel batches,
- nested orchestration,
- subagent model/tool execution,
- interruption,
- steering,
- task completion,
- final result synthesis.

### Do NOT copy FounderOS orchestration behavior

Do not use or recreate FounderOS' broadcast pattern as the execution engine.

In particular, do not make Agent Canvas depend on:

```text
/api/agents/broadcast
```

or a frontend loop that simply runs every registered agent.

The FounderOS demo describes `/org` as `operator -> conductor -> pillars -> workers`, but its demo runtime is designed around its own agent registry and seeded application model. That is not the source of truth for this project.

The source of truth is the **live Hermes delegation tree**.

---

# 3. What to Reuse From FounderOS

Clone FounderOS only as a reference while implementing the new Agent Canvas.

Example:

```bash
git clone --depth 1 https://github.com/Bennettxai/FounderOS-DEMO /tmp/founderos-ui-reference
```

Do not merge its whole repository into the Hermes WebUI.

Inspect these FounderOS files/components first:

```text
app/org/
components/ConductorCard.tsx
components/ConductorChat.tsx
components/ConductorEmblem.tsx
components/ConductorPanel.tsx
components/AgentActivityFeed.tsx
components/AgentWorkPanel.tsx
components/AgentsTabs.tsx
components/TaskBoard.tsx
components/terminal.tsx
app/globals.css
tailwind.config.ts
```

Use them for:

- Conductor visual hierarchy,
- dark command-center look,
- monospace status text,
- borders/panels,
- agent status cards,
- activity feed,
- task/work detail panels,
- status indicators,
- typography,
- spacing,
- animations,
- expandable details.

### Do not blindly copy

Do not copy:

- FounderOS SQLite/database assumptions,
- FounderOS seeded business data,
- departments such as Sales/Marketing unless they are purely cosmetic,
- its agent registry,
- its agent API routes,
- its broadcast endpoint,
- business connectors,
- G-Brain/Optimal Engine code unless separately requested,
- its global app shell if the existing Hermes WebUI already has navigation/auth/session state.

**Replace only the old Agent Canvas page and the components that belong to that page unless a dependency genuinely requires a wider change.**

---

# 4. First Step: Inspect the Existing Hermes WebUI

Before editing any code, locate the current Agent Canvas implementation.

Search for:

```text
Agent Canvas
AgentCanvas
agent-canvas
agentCanvas
canvas
subagent
delegate
delegation
orchestrator
```

Determine:

1. The Agent Canvas route.
2. The main page component.
3. Any existing graph/canvas library.
4. Existing session state.
5. Existing Hermes connection/transport.
6. Existing WebSocket/SSE client.
7. Existing stores/hooks.
8. Existing theme/layout primitives.
9. Whether Agent Canvas currently uses mock data.
10. Whether the existing backend already proxies Hermes gateway RPCs.

Do not assume filenames from this document.

If the current canvas already has a reliable graph/layout library, **keep it** and restyle/restructure the nodes. Do not introduce another graph library unless the current implementation is unusable.

Create a short migration note before editing:

```text
OLD_AGENT_CANVAS_FILES
NEW_OR_MODIFIED_FILES
EXISTING_HERMES_TRANSPORT
STATE_STORE
GRAPH_LIBRARY
RISKS
```

---

# 5. Hermes Backend: Use the Existing Delegation System

Hermes already has the required backend primitives.

Current Hermes `delegate_task`:

- spawns child `AIAgent` instances,
- gives each child isolated context,
- gives each child its own task/terminal session,
- supports parallel batches,
- tracks parent-child relationships,
- tracks depth,
- supports nested orchestration when enabled,
- propagates interruption,
- exposes live subagent status to the TUI/gateway.

Reference:

```text
Hermes:
tools/delegate_tool.py
```

Important current structure returned by Hermes' active-subagent registry:

```text
subagent_id
parent_id
depth
goal
model
started_at
tool_count
status
```

Do not create a second orchestration engine in the WebUI.

---

# 6. Preferred Transport for Agent Canvas

## Preferred: Hermes TUI Gateway JSON-RPC over WebSocket

Hermes officially exposes its TUI gateway over WebSocket and describes it as the interface for custom hosts needing fine-grained control.

Reference:

```text
tui_gateway/server.py
tui_gateway/ws.py
website/docs/developer-guide/programmatic-integration.md
```

Important gateway RPCs include:

```text
delegation.status
subagent.interrupt
subagent.steer
spawn_tree.save
spawn_tree.list
spawn_tree.load

session.status
session.usage
session.history
session.interrupt
session.steer
```

### Reuse the project's current Hermes client if possible

If the WebUI already uses Hermes' JSON-RPC/WebSocket transport, extend that client.

Do not create a second independent Hermes connection unless necessary.

Current Hermes also has a reusable shared WebSocket/JSON-RPC client in its newer app architecture. Inspect the current upstream implementation before inventing a new protocol layer.

### Browser security

Do not expose an unauthenticated raw Hermes gateway to the public internet.

Use the existing WebUI/backend authentication/session boundary.

If a backend proxy is already present:

```text
Browser Agent Canvas
       |
       v
Existing WebUI backend
       |
       v
Hermes TUI Gateway WebSocket / JSON-RPC
```

keep that architecture.

---

# 7. Use Hermes' Existing TUI as the Source of Truth

Hermes already ships a subagent observability interface.

The current TUI `/agents` overlay includes:

- live subagent tree,
- parent/child hierarchy,
- pause controls,
- kill/interrupt controls,
- per-branch token rollups,
- cost rollups,
- file rollups,
- turn-by-turn history.

Study and port the **data handling**, not the terminal rendering.

Source files to inspect:

```text
ui-tui/src/components/agentsOverlay.tsx
ui-tui/src/app/createGatewayEventHandler.ts
ui-tui/src/app/delegationStore.ts
ui-tui/src/app/spawnHistoryStore.ts
ui-tui/src/app/turnStore.ts
ui-tui/src/lib/subagentTree.ts
ui-tui/src/types.ts
ui-tui/src/gatewayTypes.ts
```

The new browser Agent Canvas should effectively become a graphical/web version of Hermes' `/agents` overlay with FounderOS styling.

---

# 8. Data Model for Agent Canvas

Use Hermes' current `SubagentProgress` shape as the basis.

A normalized WebUI node can look like:

```ts
type AgentCanvasStatus =
  | "queued"
  | "running"
  | "completed"
  | "error"
  | "failed"
  | "interrupted"
  | "timeout";

interface AgentCanvasNode {
  id: string;
  parentId: string | null;

  kind: "conductor" | "orchestrator" | "worker";

  goal: string;
  status: AgentCanvasStatus;
  depth: number;

  model?: string;

  startedAt?: number;
  durationSeconds?: number;
  iteration?: number;

  toolCount: number;
  tools: string[];
  toolsets?: string[];

  apiCalls?: number;

  inputTokens?: number;
  outputTokens?: number;
  reasoningTokens?: number;
  costUsd?: number;

  filesRead: string[];
  filesWritten: string[];

  thinking: string[];
  notes: string[];

  outputTail: {
    tool: string;
    preview: string;
    isError: boolean;
  }[];

  summary?: string;
}
```

Hermes' current frontend model already exposes most of these fields.

Do not reduce the backend data to only:

```text
name
status
```

The extra fields are what make Agent Canvas useful.

---

# 9. Root Conductor Mapping

The main "Conductor" displayed on Agent Canvas is **not another subagent**.

It represents the current main Hermes session.

Create a synthetic root node such as:

```ts
{
  id: `session:${sessionId}`,
  parentId: null,
  kind: "conductor",
  goal: currentUserPromptOrSessionGoal,
  status: currentSessionStatus,
  ...
}
```

Then map Hermes subagents:

```text
Hermes subagent parent_id == null
        ->
attach to current Conductor root
```

Nested children use their real `parent_id`.

Example:

```text
Conductor (current Hermes session)
 |
 +-- A (parent_id = null)
 |
 +-- B (parent_id = null, role=orchestrator)
      |
      +-- B1 (parent_id = B)
      |
      +-- B2 (parent_id = B)
```

The frontend must never fabricate parent relationships based on screen position.

---

# 10. Determine Orchestrator vs Worker

Hermes exposes depth and parent relationships, but the UI does not need to invent permanent job titles.

Recommended classification:

```text
Conductor
  = synthetic root / main Hermes session

Orchestrator
  = subagent that has children
    OR is known from delegation metadata to have role=orchestrator

Worker
  = leaf subagent
```

If role metadata is not available in the event payload, classify based on whether the node currently has descendants.

Do not hardcode:

```text
Sales
Marketing
Engineering
Finance
```

unless a specific project intentionally defines those departments.

For normal Hermes work, display the actual delegated goal, e.g.:

```text
Repository Explorer
Backend Audit
Frontend Review
Security Review
Test Runner
Documentation Reviewer
```

A short display label may be derived from `goal`, but the original goal must remain visible in the details panel.

---

# 11. Event Strategy: Event-Driven + Snapshot Reconciliation

This is important.

Do **not** depend solely on the newer formal event names:

```text
delegate.task_spawned
delegate.task_completed
delegate.task_failed
```

In current Hermes source, these event constants exist but are explicitly marked as reserved for future orchestrator lifecycle events and are not currently emitted.

Therefore:

## On connection / Agent Canvas open

Call:

```text
delegation.status
```

Use it to reconstruct the active tree.

Hermes' own TUI does this when the `/agents` overlay opens.

## During a turn

Subscribe to the same gateway event flow used by:

```text
ui-tui/src/app/createGatewayEventHandler.ts
```

Port/adapt the current upstream subagent progress mapping.

**Do not guess event names.**

Inspect the exact current Hermes version installed in the project and map the same events its own TUI maps.

## Reconciliation

While a Hermes turn is active:

- reconcile against `delegation.status` periodically,
- also reconcile immediately after reconnect,
- reconcile if the event sequence appears incomplete.

Hermes' current TUI throttles delegation-status refreshes rather than trusting only local events.

A WebUI interval around a few seconds is acceptable, but reuse upstream behavior where practical.

---

# 12. Completed Subagents Need History

`delegation.status` is an **active-subagent snapshot**.

Completed children disappear from the active registry.

Therefore Agent Canvas must preserve terminal nodes:

```text
completed
failed
error
interrupted
timeout
```

Do not remove a card immediately when it disappears from `delegation.status`.

Use one of these approaches, in order of preference:

1. Reuse/port Hermes' current TUI spawn-history behavior.
2. Use the gateway `spawn_tree.save/list/load` facilities after verifying the installed Hermes version.
3. Store the finished tree per Hermes turn/session in the WebUI's existing state/persistence layer.

The canvas should still show the completed delegation structure after the main Hermes response finishes.

---

# 13. Status Precedence

Avoid visual flicker from late/out-of-order progress.

Treat terminal states as terminal:

```text
completed
failed
error
interrupted
timeout
```

Once a node reaches a terminal state, do not downgrade it back to:

```text
queued
running
```

because of a late event or stale snapshot.

Use monotonic status rules.

---

# 14. Agent Canvas UI Layout

Use the FounderOS visual language, but make the hierarchy dynamic.

Recommended layout:

```text
+--------------------------------------------------------------+
| AGENT CANVAS                          LIVE • Hermes connected |
| Session: AI Honeypot / <current project>                     |
+--------------------------------------------------------------+

                     +----------------------+
                     |      CONDUCTOR       |
                     | Hermes Main Session  |
                     | RUNNING              |
                     | tools 12 | $0.04     |
                     +----------+-----------+
                                |
             +------------------+-------------------+
             |                  |                   |
             v                  v                   v
     +---------------+  +---------------+   +---------------+
     | REPO EXPLORER |  | BACKEND AUDIT |   | FRONTEND      |
     | RUNNING       |  | COMPLETED     |   | QUEUED        |
     | 7 tools       |  | 13 tools      |   | 0 tools       |
     +---------------+  +---------------+   +---------------+
                                |
                                v
                        +---------------+
                        | TEST WORKER   |
                        | RUNNING       |
                        +---------------+
```

### Visual requirements

Each agent card should show, at minimum:

- status indicator,
- short task/goal,
- model,
- elapsed time,
- tool count,
- depth or role,
- compact token/cost info when available.

Clicking a card should open a detail panel with:

- full delegated goal,
- parent,
- child count,
- model,
- status,
- iterations,
- tools used,
- output tail,
- files read,
- files written,
- token usage,
- cost,
- summary,
- timestamps.

---

# 15. FounderOS Component Adaptation

Recommended conceptual mapping:

```text
FounderOS ConductorCard
        ->
Hermes main-session Conductor node

FounderOS ConductorPanel
        ->
Conductor/session detail + live delegation controls

FounderOS AgentActivityFeed
        ->
Hermes tool/delegation activity feed

FounderOS AgentWorkPanel
        ->
Selected subagent detail/work panel

FounderOS org hierarchy styling
        ->
Dynamic Hermes parentId tree

FounderOS terminal styling
        ->
Output tail / tool activity presentation
```

Make the copied components **data-driven through props**.

Bad:

```ts
const agents = [
  { name: "Sales" },
  { name: "Marketing" }
];
```

Good:

```tsx
<AgentNode
  node={hermesNode}
  children={childrenFor(node.id)}
/>
```

---

# 16. Recommended Frontend Module Boundary

Adapt names to the actual WebUI structure discovered in Step 4.

A clean structure would be:

```text
agent-canvas/
  AgentCanvasPage.tsx

  components/
    AgentGraph.tsx
    ConductorNode.tsx
    SubagentNode.tsx
    AgentStatusBadge.tsx
    AgentDetailsPanel.tsx
    AgentActivityFeed.tsx
    DelegationToolbar.tsx
    CanvasEmptyState.tsx

  hooks/
    useHermesDelegation.ts
    useAgentCanvasSession.ts

  lib/
    hermesDelegationAdapter.ts
    buildAgentTree.ts
    aggregateAgentTree.ts
    statusPrecedence.ts

  store/
    agentCanvasStore.ts

  types.ts
```

Do not force this exact directory if the current project already has conventions.

---

# 17. Hermes Adapter Responsibilities

Create a single adapter between raw Hermes gateway data and UI state.

Example responsibilities:

```ts
interface HermesDelegationAdapter {
  connect(): Promise<void>;
  disconnect(): void;

  getStatus(): Promise<DelegationStatus>;

  interruptSubagent(id: string): Promise<void>;
  steerSubagent(id: string, text: string): Promise<void>;

  pauseSpawning(paused: boolean): Promise<void>;

  subscribe(handler: (event: HermesGatewayEvent) => void): () => void;
}
```

The UI components should not call raw JSON-RPC methods everywhere.

All Hermes-specific translation should live in this adapter/store boundary.

---

# 18. Controls to Implement

## Refresh / reconcile

RPC:

```text
delegation.status
```

## Interrupt one subagent

RPC:

```text
subagent.interrupt
{
  "subagent_id": "<id>"
}
```

Hermes' own TUI uses this.

## Steer a running subagent

RPC:

```text
subagent.steer
```

Use the current gateway schema from the installed Hermes version.

Only show the action while the subagent is live and accepting work.

## Pause new delegation spawns

Hermes' current TUI contains a delegation pause control.

Use the current gateway method/schema from the installed Hermes version rather than inventing it.

Pausing should block **new** spawns; active children should continue.

## Kill subtree

Calculate descendants from `parentId` and interrupt each live descendant.

Prefer deepest descendants first or follow the same strategy as the current Hermes TUI implementation.

Do not kill unrelated sibling branches.

---

# 19. Do Not Let Agent Canvas Become a Second Orchestrator

Agent Canvas is primarily:

```text
observability + control
```

not:

```text
a separate agent scheduler
```

Normal flow:

```text
User sends task through existing Hermes chat
        |
        v
Hermes decides to delegate
        |
        v
Agent Canvas automatically updates
```

Do not require the user to manually create every child agent for normal operation.

Optional manual control can be added later, but it must call Hermes-supported RPC/tool flows rather than spawning fake frontend workers.

---

# 20. Nested Delegation

Current Hermes supports nested delegation when configuration allows it.

A child with:

```text
role="orchestrator"
```

can delegate further when the configured spawn depth permits it.

Therefore the frontend tree must support arbitrary depth.

Do not build the canvas around exactly two levels such as:

```text
Conductor -> Workers
```

Support:

```text
Conductor
  -> Orchestrator
      -> Worker
      -> Orchestrator
          -> Worker
```

Read depth/concurrency configuration from current Hermes status/config where available.

**Do not hardcode a max depth or max number of children in the frontend.**

---

# 21. Parallel Delegation

Hermes supports batch/parallel delegation.

If three children start at roughly the same time, show all three as independent sibling nodes.

Do not serialize their frontend state.

The canvas should make parallelism visually obvious.

Example:

```text
                   Conductor
         +------------+------------+
         |            |            |
       Agent A      Agent B      Agent C
       running      running      running
```

---

# 22. Session Isolation

Agent Canvas must be tied to the active Hermes session.

Never mix subagents from different user sessions into one graph.

When the WebUI switches Hermes sessions:

1. clear or archive the active canvas,
2. load that session's saved tree/history if available,
3. call the correct session/delegation status,
4. subscribe under the correct active-session context.

If the existing Hermes gateway client already manages active session identity, reuse that mechanism.

---

# 23. Activity Feed

The activity feed should be real.

Possible entries:

```text
03:20:04  Backend Audit spawned
03:20:05  Repo Explorer -> terminal
03:20:07  Backend Audit -> read_file
03:20:11  Repo Explorer wrote ARCHITECTURE.md
03:20:16  Backend Audit completed
03:20:18  Security Review failed
```

Build entries from Hermes gateway/delegation/tool events.

Do not seed fake activity.

---

# 24. Output Preview

Hermes' subagent observability code already extracts an output tail from tool results.

Use this in the selected-agent panel.

Display compact entries such as:

```text
terminal
npm test
PASS 42 tests

read_file
src/api/routes.ts
...

write_file
src/components/AgentCanvas.tsx
...
```

Cap output length in the UI.

Do not dump unrestricted terminal history into every node card.

---

# 25. Files Touched

Expose:

```text
filesRead
filesWritten
```

in the details panel.

For coding tasks this is especially useful because the user can immediately see which subagent modified what.

Optional enhancement:

```text
Files changed (4)
  M src/...
  M backend/...
  A tests/...
```

Only implement git diff integration if the project already has a safe backend mechanism for it.

---

# 26. Cost and Token Rollups

Hermes' TUI already has aggregate concepts for:

```text
input tokens
output tokens
cost
tools
files touched
active descendants
duration
```

Port or reproduce the aggregate logic using the current upstream implementation.

For a branch:

```text
Orchestrator B
  self cost:       $0.02
  descendants:     $0.06
  branch total:    $0.08
```

Do not double-count children.

---

# 27. Error Handling

Represent these separately:

```text
failed
error
timeout
interrupted
```

Do not collapse everything into "failed".

A failed child must remain visible so the user understands why the parent may have incomplete results.

On gateway disconnect:

- keep the last known tree,
- mark connection state as stale/disconnected,
- reconnect,
- call `delegation.status`,
- reconcile,
- do not erase history.

---

# 28. Migration Order

Implement in this order.

## Phase 1 — Protect current behavior

1. Create a feature branch.
2. Identify all Agent Canvas files.
3. Capture screenshots/current behavior.
4. Run existing tests.
5. Record existing WebUI/Hermes transport.
6. Do not delete the old canvas yet.

## Phase 2 — Build Hermes delegation adapter

1. Connect to existing TUI gateway transport.
2. Implement `delegation.status`.
3. Parse active subagents.
4. Add parent-child tree construction.
5. Add session root.
6. Verify one real delegated task appears.

At this stage, use a minimal temporary UI if needed.

## Phase 3 — Live events

1. Inspect current Hermes:
   `ui-tui/src/app/createGatewayEventHandler.ts`.
2. Port only the subagent/delegation event mapping needed by the WebUI.
3. Track running state.
4. Track tools/output.
5. Preserve terminal statuses.
6. Reconcile with `delegation.status`.

## Phase 4 — History

1. Preserve completed nodes.
2. Persist per-turn trees.
3. Restore history after switching turns/session.
4. Verify reconnect behavior.

## Phase 5 — FounderOS visual migration

1. Bring over the relevant visual primitives/components.
2. Rename business-specific concepts to Hermes concepts.
3. Convert static data to props.
4. Feed components from the Hermes store.
5. Replace old Agent Canvas page.
6. Keep the rest of the WebUI shell intact.

## Phase 6 — Controls

1. Interrupt one subagent.
2. Kill a branch/subtree.
3. Pause new spawns.
4. Resume spawning.
5. Add steering if supported and correctly authorized by the current gateway.

## Phase 7 — Polish

1. responsive layout,
2. pan/zoom if already available,
3. collapsed branches,
4. selected-node details,
5. status animation,
6. token/cost summaries,
7. activity feed,
8. reconnect indicator.

---

# 29. Acceptance Tests

Do not consider the migration complete until these pass.

## Test A — Single subagent

Prompt Hermes with a task that causes one `delegate_task`.

Expected:

```text
Conductor
  -> one real child
```

Verify:

- real subagent ID,
- real goal,
- status transitions,
- tool count,
- completion summary.

## Test B — Parallel batch

Give Hermes three independent subtasks.

Expected:

```text
Conductor
  +-> A
  +-> B
  +-> C
```

All should be visible concurrently.

## Test C — Nested orchestrator

With nested delegation enabled, use a task where a child receives `role="orchestrator"`.

Expected:

```text
Conductor
  -> Orchestrator
      -> Worker 1
      -> Worker 2
```

The graph must use real `parentId`, not inferred position.

## Test D — Interrupt one

Start multiple children.

Interrupt one from Agent Canvas.

Expected:

- selected child becomes interrupted,
- siblings continue.

## Test E — Interrupt subtree

Interrupt an orchestrator branch.

Expected:

- that branch stops,
- unrelated branches remain alive.

## Test F — Pause

Pause new delegation spawns.

Expected:

- already running children continue,
- new spawn requests are blocked by Hermes,
- UI shows paused state.

Resume and verify normal spawning returns.

## Test G — Completed history

Finish a task.

Expected:

- completed subagents remain visible in the finished turn,
- page refresh/session restore can reconstruct history if persistence is enabled.

## Test H — Reconnect

Disconnect/restart frontend connection during an active delegation.

Expected:

- last state remains,
- reconnect succeeds,
- `delegation.status` rebuilds active nodes,
- no duplicate cards.

## Test I — Out-of-order update

Simulate a terminal state followed by a stale `running` update.

Expected:

- terminal status wins.

## Test J — No fake workers

Search the final Agent Canvas implementation.

There must be no hardcoded demo worker array representing active Hermes agents.

---

# 30. Important Hermes Event Caveat

Current Hermes source defines formal delegation event constants such as:

```text
delegate.task_spawned
delegate.task_progress
delegate.task_completed
delegate.task_failed
delegate.task_thinking
delegate.tool_started
delegate.tool_completed
```

However, the current source explicitly says that:

```text
delegate.task_spawned
delegate.task_completed
delegate.task_failed
```

are reserved for future orchestrator lifecycle events and are not currently emitted.

Therefore the implementation must use **the current installed Hermes event flow** and `delegation.status` reconciliation.

Do not write a new WebUI implementation that waits exclusively for `delegate.task_spawned`.

This is one of the most important compatibility requirements in this document.

---

# 31. Upstream Files That Are the Actual Reference Implementation

When behavior is unclear, inspect these files in the installed/current Hermes source before making assumptions:

```text
tools/delegate_tool.py

tui_gateway/server.py
tui_gateway/ws.py

ui-tui/src/types.ts
ui-tui/src/gatewayTypes.ts
ui-tui/src/components/agentsOverlay.tsx
ui-tui/src/app/createGatewayEventHandler.ts
ui-tui/src/app/delegationStore.ts
ui-tui/src/app/spawnHistoryStore.ts
ui-tui/src/app/turnStore.ts
ui-tui/src/lib/subagentTree.ts

website/docs/developer-guide/programmatic-integration.md
website/docs/user-guide/features/delegation.md
website/docs/user-guide/tui.md
```

For every Hermes RPC or event payload:

> Prefer the current source/schema over assumptions in this document if upstream has changed.

---

# 32. FounderOS License / Attribution

FounderOS' README currently declares the project **MIT licensed**.

If source code is copied rather than merely reimplemented visually:

- preserve the required MIT copyright/license notice,
- keep or add a third-party notices file if appropriate,
- do not remove upstream attribution required by the license.

Do not copy unrelated assets or branding that are not needed for Agent Canvas.

---

# 33. Definition of Done

The feature is complete when:

- [ ] Existing Agent Canvas frontend has been replaced with the new FounderOS-inspired interface.
- [ ] Rest of Hermes WebUI remains functional.
- [ ] Main Conductor represents the real current Hermes session.
- [ ] Every worker card represents a real Hermes subagent ID.
- [ ] Parent-child edges come from real Hermes `parent_id`.
- [ ] Parallel delegation appears in real time.
- [ ] Nested delegation renders correctly.
- [ ] Active statuses update live.
- [ ] Completed/failed/interrupted nodes remain visible in history.
- [ ] Tool activity is real.
- [ ] Output preview is real.
- [ ] Token/cost/file information uses Hermes data when available.
- [ ] Interrupt works.
- [ ] Branch interrupt works.
- [ ] Pause/resume of spawning works.
- [ ] Reconnect/status reconciliation works.
- [ ] No FounderOS `/api/agents/broadcast` dependency exists.
- [ ] No FounderOS database is required for orchestration.
- [ ] No fake seeded agent hierarchy is shown as live execution.
- [ ] Existing Hermes chat/session flow remains the entry point for tasks.
- [ ] Tests/typecheck/build pass.

---

# 34. Final Architecture

```text
+------------------------------------------------------------------+
|                        HERMES WEBUI                               |
|                                                                  |
|  Existing Chat / Session                      Agent Canvas        |
|  +----------------------+          +---------------------------+  |
|  | User -> Main Hermes  |          | FounderOS-inspired UI     |  |
|  +----------+-----------+          |                           |  |
|             |                      | Conductor                 |  |
|             |                      |   |                       |  |
|             |                      |   +-- Subagent A          |  |
|             |                      |   +-- Subagent B          |  |
|             |                      |        +-- Worker B1      |  |
|             |                      +-------------^-------------+  |
|             |                                    |                |
+-------------|------------------------------------|----------------+
              |                                    |
              v                                    |
+------------------------------------------------------------------+
|                   Hermes TUI Gateway / Runtime                    |
|                                                                  |
| prompt/session                  JSON-RPC / WebSocket              |
|       |                                                          |
|       v                                                          |
| Main AIAgent                                                     |
|       |                                                          |
|       v                                                          |
| delegate_task                                                    |
|       |                                                          |
|       +---- active subagent registry ----------------------------+
|       |          id / parent_id / depth / goal / status          |
|       |                                                          |
|       +--> child AIAgent                                         |
|       +--> child AIAgent -> optional nested children             |
|                                                                  |
| RPC: delegation.status / subagent.interrupt / subagent.steer     |
+------------------------------------------------------------------+
```

**The WebUI observes and controls Hermes. It does not replace Hermes.**

---

# 35. Instruction to the Coding Agent

Execute this migration autonomously, but follow these rules:

1. Inspect the existing project before editing.
2. Do not guess existing paths, state management, or transport.
3. Keep Hermes as the orchestration backend.
4. Reuse current Hermes gateway/event behavior instead of inventing a parallel protocol.
5. Use FounderOS only for the Agent Canvas presentation layer.
6. Do not bring FounderOS' broadcast orchestration or seeded DB into the Hermes execution path.
7. Implement the backend/data adapter before the visual rewrite.
8. Prove the canvas works against a **real `delegate_task` run** before removing the old frontend.
9. Run existing tests/typecheck/build after each major phase.
10. Add tests for tree construction, terminal-state precedence, reconnect reconciliation, and controls.
11. Preserve existing unrelated WebUI behavior.
12. Do not mark the work complete until the acceptance tests in this document have been verified.

---

## Source References

### Hermes
- https://github.com/NousResearch/hermes-agent/blob/main/tools/delegate_tool.py
- https://github.com/NousResearch/hermes-agent/blob/main/tui_gateway/server.py
- https://github.com/NousResearch/hermes-agent/blob/main/tui_gateway/ws.py
- https://github.com/NousResearch/hermes-agent/blob/main/ui-tui/src/components/agentsOverlay.tsx
- https://github.com/NousResearch/hermes-agent/blob/main/ui-tui/src/app/createGatewayEventHandler.ts
- https://github.com/NousResearch/hermes-agent/blob/main/ui-tui/src/types.ts
- https://github.com/NousResearch/hermes-agent/blob/main/ui-tui/README.md
- https://github.com/NousResearch/hermes-agent/blob/main/website/docs/developer-guide/programmatic-integration.md
- https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/delegation.md
- https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/tui.md

### FounderOS
- https://github.com/Bennettxai/FounderOS-DEMO
- https://github.com/Bennettxai/FounderOS-DEMO/tree/main/components
- https://github.com/Bennettxai/FounderOS-DEMO/tree/main/app/org
- https://github.com/Bennettxai/FounderOS-DEMO/blob/main/lib/agents/runtime.ts
