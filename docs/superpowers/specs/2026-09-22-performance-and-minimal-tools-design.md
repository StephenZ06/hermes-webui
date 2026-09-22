# Performance and minimal-tools design

## Intent

Hermes WebUI should feel immediate when users navigate, switch profiles, or interact with animated controls. Agent runs should expose only the smallest tool capability set required by the task, reducing tool-schema/context cost without preventing valid work.

This design applies to every browser profile, including Conductor. It preserves profile isolation, session replay, accessibility, and the existing user ability to intentionally select a session toolset.

## Goals

- Make common cached navigation responsive without replacing the vanilla JavaScript architecture or adding a framework.
- Avoid stale asynchronous panel and profile work changing the newly selected view.
- Make animation smooth by limiting interactive motion to compositor-friendly properties and by respecting reduced-motion settings.
- Default new sessions to a minimal tool policy; expand toolsets only when a concrete task need or an explicit user choice requires them.
- Make the effective tool policy observable in run metadata without exposing message content, secrets, or tool arguments.

## Non-goals

- No blanket ban on browser, shell, network, delegation, or verification tools. Those remain necessary for some tasks.
- No model-based classifier before every turn; such a classifier would itself add latency and token cost.
- No claim that the WebUI can enforce individual Hermes Agent tools when the runtime only supports toolset-level capability filtering.
- No process-global profile cache or policy state. Browser/profile and session isolation remain the authority boundaries.

## Architecture

### Interaction performance

Introduce a small client-side performance coordinator, owned by the browser:

1. `switchPanel` and profile-switch code emit `performance.mark` pairs for intent, first usable paint, and settled noncritical refresh.
2. A per-surface generation token makes asynchronous loads cancellable in effect: only the latest request for a panel/profile can mutate its DOM.
3. Panels retain their last successful, profile-scoped presentation cache. Opening a panel renders that cache immediately, then refreshes it only when stale. Expensive nonvisible panel data stays lazy.
4. Profile switching commits the profile identity and essential composer state first. Model catalogs, quota data, and inactive panels refresh afterwards; older profile responses are discarded rather than delaying or overwriting the active profile.

The coordinator stores only timing aggregates and generation numbers in memory. It does not send telemetry or persist user content.

### Motion budget

Existing `MotionUI` and CSS remain the single motion system. Interactive transitions use `opacity` and `transform` only, target a short shared duration, and cancel/restart cleanly when a new navigation or profile selection wins. Layout-affecting animation is reserved for the few components where the visual state requires it and is measured before retention. Reduced-motion keeps its existing immediate, accessible behavior.

### Minimal tool policy

Add a policy resolver at the run-context boundary rather than scattered UI checks. The resolver accepts profile defaults and the configured toolset catalog, any explicit per-session `enabled_toolsets` override, a deterministic policy choice (`minimal`, `inherit-profile`, or explicit toolsets), and the run source so delegated/background work cannot silently inherit a broader browser-session policy.

`minimal` exposes no optional MCP/external toolsets. Normal built-in agent capabilities remain subject to the Hermes Agent runtime's own policy. An explicit toolset selection wins over `minimal`; an unknown or unavailable toolset fails closed with a clear error. `inherit-profile` preserves current compatibility behavior for existing sessions and becomes a deliberate opt-in rather than the default for new sessions.

The resolved policy and allowed toolsets travel in the existing `StartRunRequest.toolsets` / run metadata flow. Session persistence records the user's policy selection separately from the resolved set so a later profile catalog change cannot silently broaden a historical session.

The WebUI must first verify Hermes Agent semantics for an empty toolset list. If the Agent interprets `[]` as "inherit all" instead of "no optional toolsets", the WebUI must not pretend minimal mode is enforced. It must use a supported restrictive sentinel/API or show minimal mode as unavailable until the runtime contract is extended. Exact per-tool filtering is explicitly an Agent-runtime follow-up, not a WebUI-only approximation.

### Agent tool discipline

For runtimes that accept the existing profile/system guidance, append a compact tool-discipline directive: inspect locally first, use a tool only when it advances the requested outcome, avoid duplicate searches/reads, and escalate to network, writes, delegation, or broad verification only when the task demands it. This is advisory behavior; enforcement remains the resolved toolset boundary. The directive must be injected once per run, never appended to stored conversation history, preventing prompt accumulation.

## State ownership and invariants

| State | Owner | Invariant |
| --- | --- | --- |
| Active panel/profile intent generation | browser | Older responses never alter the current surface. |
| Cached panel data | browser, keyed by profile and panel | A cache entry cannot appear under another profile. |
| Session tool policy | session persistence | Explicit session selection survives reload/branch and cannot broaden silently. |
| Resolved toolsets | run request/runtime | The executor receives the same resolved capability set shown to the user. |
| Individual tool authorization | Hermes Agent runtime | WebUI never claims stricter enforcement than the runtime provides. |

## Rollout

1. Establish timing baselines and stale-response guards without changing user policy defaults.
2. Optimise panel/profile fast paths behind measured assertions.
3. Add the minimal policy resolver as opt-in and verify runtime semantics using an isolated test profile.
4. Make minimal the default for newly created sessions only after compatibility and delegation tests pass. Existing sessions retain their stored/inherited behavior.
5. Surface a compact composer indicator for the resolved policy and a clear unavailable state when the runtime cannot enforce it.

## Verification

- Unit tests prove generation-based stale loads cannot overwrite a later panel or profile choice, and profile caches are completely scoped.
- Browser-level tests measure that cached panel/profile transitions complete without synchronous catalog reloads in the intent path.
- Motion tests assert reduced-motion remains immediate and interactive motion avoids layout-changing properties.
- Contract tests cover `minimal`, inherited, explicit, unavailable, delegated, and profile-switched tool-policy states.
- Runtime integration tests verify the exact toolset payload observed by the executor. A test must fail if minimal mode resolves to a broader set than the UI reports.
