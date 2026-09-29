# UI / Motion Taste

- Wants motion and transitions to feel fluid and native-app-like on desktop and mobile, including at 120 Hz on his phone. Confidence: 0.9
- Wants mobile to have full feature parity with desktop, not a reduced set (flags missing controls like the project-folder kebab menu on touch). Confidence: 0.85
- Distrusts abrupt visual changes: flashes/flickers of unstyled or wrong content, elements appearing instead of fading in, janky or stuck gestures, and layout churn while streaming all get called out as bugs. Confidence: 0.8
- Cares about fine visual polish details — spacing/padding symmetry, alignment, text size, rounding, and consistent use of existing app design elements when building something new. Confidence: 0.75
- Wants the UI to be context-aware / "smart" about the active profile: surface information that fits the current provider (e.g. the usage card follows the profile — Codex usage on a Codex profile, NeuralWatt usage on a NeuralWatt profile) and hide it entirely when irrelevant (e.g. no usage card on a local profile). Confidence: 0.6
- In any model selector (profile creation/editing, WorkHub settings, etc.), expects only providers and models that are actually configured to be available, regardless of the currently active profile or context. Confidence: 0.9
- Wants expanding/collapsing of grouped list sections (e.g. the sidebar's TODAY / THIS WEEK / LAST WEEK / OLDER groups) to animate smoothly with a transition rather than an instant show/hide. Confidence: 0.8
- Prefers scrollable containers to be constrained to the viewport: horizontal scrollbars should sit at the bottom of the visible area (not the page), and columns/lists should stretch only to the bottom of the view rather than the full page. Confidence: 0.85
- Prefers the app's own themed in-app dialogs/modals over native browser dialogs such as `window.prompt`, `window.confirm`, or `window.alert`. Confidence: 0.85
- Wants successful actions (e.g., creating an item) to be acknowledged with a smooth visual animation, not just a silent state update. Confidence: 0.8
- Prefers horizontal scrollbars to remain visible at all times and sit below content rather than overlaying it; prefers vertical scrollbars hidden for a cleaner appearance. Confidence: 0.75
- Wants resizable side panels/sidebars to persist their width across refreshes and page navigation. Confidence: 0.85
- Dislikes hover/focus states being clipped by parent containers; expects padding/margin to accommodate visible outlines and shadows. Confidence: 0.7
