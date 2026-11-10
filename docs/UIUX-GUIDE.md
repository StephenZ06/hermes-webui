# UI/UX Guide

This document summarizes UI/UX principles that are already visible in the
repository. It is a contributor guide, not a new design proposal. Source
documents include [`DESIGN.md`](../DESIGN.md), [`README.md`](../README.md),
[`THEMES.md`](../THEMES.md), [`docs/ui-ux/index.html`](ui-ux/index.html),
[`docs/ui-ux/two-stage-proposal.html`](ui-ux/two-stage-proposal.html), and
design comments in `static/style.css`.

Use this guide when a change touches layout, chat rendering, composer chrome,
navigation, theme/skin behavior, responsive behavior, or visual hierarchy. For
purely backend changes, use the runtime/state contracts instead.

## Product shape

Hermes WebUI is a browser workbench for Hermes Agent with near-CLI parity and a
simple implementation shape: Python on the server, vanilla JavaScript in the
browser, no build step, no bundler, and no frontend framework.

The primary layout is three-panel:

- left sidebar for sessions and navigation,
- center panel for chat,
- right panel for workspace file browsing and previews.

Model, profile, workspace, attachments, voice input, context usage, Stop, and
Send controls live in the composer footer. Settings and session-level tools live
in the Hermes Control Center. Preserve this shape unless the change explicitly
justifies a different interaction model.

## Core feeling: calm developer console

The main artifact is the conversation. Tool calls, thinking traces, context
compaction records, token usage, runtime status, and other internals are useful,
but they are transcript metadata. They should sit below user and assistant prose
in visual priority.

Prefer:

- quiet surfaces,
- clear spacing,
- restrained accent use,
- progressive disclosure for debugging detail,
- legible text over decorative chrome.

Avoid turning the interface into a demo page of colorful cards. Errors,
approvals, and other action-required states may be prominent because the user
must notice and respond to them.

## Conversation hierarchy

A chat turn should read as one coherent story:

1. User message: right-aligned, compact bubble.
2. Assistant content: left-aligned, prose-first, not a heavy bubble.
3. Tool, thinking, progress, and context traces: quiet disclosure rows inside or
   adjacent to the assistant turn.
4. Raw logs and verbose details: hidden until explicitly expanded.

Do not render every internal event as a first-class chat card. A turn that used
many tools should summarize the work as inspectable activity, not make the user
read a stack of unrelated-looking cards.

## Tool, thinking, and activity traces

Tool cards are debug event rows, not chat messages. Show the icon, name, short
target or preview, and status first. Arguments, result snippets, and long logs
belong behind expansion, with result snippets truncated and full output behind a
show-more affordance where needed.

Thinking and context cards should share the quiet metadata visual family. They
should not overpower assistant prose. Collapsed activity summaries should be
terse, for example `Activity: 4 tools`, and should not duplicate the thinking
area, list every tool name in the summary, or add redundant trailing count
badges.

Visible interim assistant progress is part of the live conversation timeline,
not raw debug detail. Compact Activity may collapse tool arguments, long tool
results, and low-level reasoning detail, but it must not make concise
user-visible progress text available only inside a collapsed disclosure.

Automatic compression is a live-only context barrier, not a special branded
tool card. Render it as a centered, non-interactive divider with quiet horizontal
rules: `Compressing context` while the compression barrier is active and
`Context auto-compressed` when the agent has continued or the compression
completion event arrives. Do not give it a caret, click target, leading status
dot, or standalone running badge. In settled final history, remove live-only
automatic compression rows unless they explain a visible recovery or error
state.

The existing two-stage proposal in `docs/ui-ux/two-stage-proposal.html` records a
compatible direction for long turns: live work can be grouped as a worklog, then
settled history can collapse while the final answer reads as the calm
conclusion. Treat that page as an existing proposal, not as shipped behavior
unless the code and tests prove it is implemented.

## Typography and content

Use three explicit font tokens:

- `--font-ui`: shell chrome, controls, composer, labels, and ordinary UI text
- `--font-conversation`: user/assistant message prose; by default this is
  `var(--font-ui)` in `static/style.css`
- `--font-mono`: code, file paths, command lines, tool payloads, technical logs,
  and terminal output

Use semantic tokens for typography. Keep prose on `--font-conversation` by
default so it tracks `--font-ui` whenever a skin intentionally retunes UI type.
Override `--font-conversation` only for a skin that intentionally wants a
distinct prose face.
Conversation prose must remain the system sans by default. Do not introduce a
global conversation serif through the `--font-conversation` token or
selector-level overrides without explicit design approval plus code and test
evidence; keep distinct editorial prose typography explicitly opt-in or
skin-scoped.
Avoid hard-coding selector-level font stacks when a token already carries the
intent.

Keep scale tight. Avoid introducing near-duplicate one-off font sizes, colors,
radius values, or spacing values when an existing token works.

## Color, depth, and shape

Use one accent at a time. Semantic colors are for semantic state: success,
warning, error, and info. Do not mix many bright colors decoratively in the same
viewport.

Use almost no shadows in the transcript. Reserve shadows for popovers,
dropdowns, modals, and floating controls. Chat cards should usually use either a
subtle border or a subtle tint, not aggressive combinations of both.

Avoid stacks of nested rounded rectangles. Rows and list items should feel
compact; panels and cards may be slightly rounder; true pills are reserved for
chips and badges.

## Composer and controls

The composer is the command surface. Keep it legible, stable, and focused:

- no theatrical hover scaling for routine controls,
- no ambient chrome that crowds the model/workspace/profile controls,
- no new footer buttons on tight layouts without a clear value tradeoff,
- keep Stop/Send and context feedback easy to find while composing.

When adding a control, consider where users will find it on both wide desktop and
mobile. If a setting or quota/control surface does not fit in the composer, route
it through the appropriate Control Center panel instead of squeezing the footer.

## Loading and content swaps

Opening a chat, note, skill, Knowledge item or wiki page swaps one document for
another through `SkeletonEntrance` (`static/ui.js`). It never cuts to a blank
view or a spinner. Pulsing placeholder bars stand where the text will be, and
a bar stands over the title. When the content is written, the bars glide onto
the content's real visible lines, and the title's bar to the title's length
(about 0.18s), then cross-fade into the text.
The title, its count and the note's details fade in on the same transition.
Each item's bar layout is remembered, as positions only and never text, in
`localStorage` under `hermes-skel-shapes` for the 200 most recent items. On a
revisit the placeholder already has that item's lines and title length and
fades straight in. An item last seen empty keeps the usual lines for its body.
The overlay stays pinned to the visible area while a transcript scrolls to its
end beneath it. Reduced motion turns the whole entrance off.

Rows that a text change re-flows, such as the centred titlebar and the
composer's chips, slide their items to their new places (`SlideOnChange`)
instead of letting them jump.

Three shared mechanisms in `static/motion-ui.js` and `static/ui.js` cover
motion that would otherwise need editing at every call site:

- **Popup presence** (`motion-ui.js`): any menu, picker, popover or modal added
  to `<body>` with no animation of its own slides and fades in (menus from
  their trigger, modals rise while the backdrop fades). When one is removed
  without an exit of its own, a pixel-only copy (styles baked inline, every
  class, id and data attribute stripped, inert) fades out in its place, so
  code that looks a popup up by class never mistakes the copy for an open
  popup. Popups that already animate (`.popup-closing`, `.is-leaving`,
  `MotionUI.presence`, a CSS entrance) are left alone.
- **Content arrival** (`motion-ui.js`): when a page writes its data in place of
  a loading bar, spinner or skeleton, the new content fades in (opacity only,
  so positions are final from the first frame). Lists with motion of their own
  and the chat transcript are skipped.
- **Linked deletes** (`rebuildWithExits` in `ui.js`): a side panel rebuilt after
  something was deleted on another page (a workspace deleted in Chat, Work Hub
  or Notes) puts the old row back, inert and stripped of ids and data
  attributes, and collapses it out with `animateRemoval`.

Modal backdrops dim and blur half as much as the original values
(`app-dialog-overlay` 0.31 and 3px), so the page behind stays readable.

On a desktop with a mouse the top bar rests above the window and slides down
when the pointer reaches the top edge, or when keyboard focus lands in it. Touch
screens, phones and installed apps with window controls in the bar keep it in
place, because they have no way to reveal it.

The rail's icons are embedded in `style.css` as `--mark-*` variables, so they arrive
together and fade in once as soon as the rail is parsed, with no image requests and
no timer. Kanban's visibility comes from the last saved choice in `localStorage`
(`hermes-hide-kanban`). After changing a PNG in `static/`, regenerate its 64px copy.

## Project builder wizard and the library catalog

The create-project wizard is laid out as a builder: the step on the left and a
live Build summary on the right (at 900px and below it folds into a bar under the
step). Website, Web app, iOS and Android projects get a Look & feel step
preselected from the brief, with the reason shown, then every template gets a
Toolkit step (recommended skills ticked; visual templates also get catalog
components by role) and a Review step whose primary action is Create & start
building. Between 721px and 1023px the stepper shows only the current label.

Cards in these steps sit on an 8px grid and share one size per row; the browser
tests measure this at 1440, 820 and 390 widths. Recommendations reuse the star
artwork (`static/wizard/star.png`) at top/right 8px, as on the Details step.

The Skills page has Skills / Libraries tabs. Library components show their
preview (the loop plays on hover, never under reduced motion), tag chips and a
Needs details badge; clicking a card opens its tag form, which can also replace
the picture. The "Docs not updated" chip under a reply uses the warning colour,
fades in, and never sends anything unless Update now is pressed.

Builder cards sit on the page background (`var(--bg)`); the dialog keeps a 24px
margin on every side, and a 1px divider sits in the 49px gap before the build
summary so the space on each side is equal. On the Details step the card under
the options explains whichever option is chosen (why for the recommendation,
how it would be built for the others, using the planner's per-option `how`),
and its text changes through the Notes page's placeholder-bar motion
(`_psSwapText` in `static/sessions.js`). Choosing an option updates in place;
it does not re-render the question.

A filter sits beside a search box as a 32px square with an accent outline
(`.filter-btn`); its menu (`openFilterMenu` in `static/ui.js`) offers one choice
at a time in labelled groups. The Toolkit step and the Skills page use it. On
the Skills page the tabs, the labelled "Categories" divider and the search row
are 12px apart; library filters match the search box's 32px height and are as
wide as their labels. Category folding animates its height.

The builder dialog reaches its new size before a step's content enters: when a
step change makes the dialog glide (340ms), the step and its card staggers wait
220ms (`--ps-enter-delay`), and the Details card's text shows only after its
height has settled. The Location step fetches and decodes the Template step's
art (`_psPreloadArt`). On wide screens the Build summary card runs to the bottom
of the step. Review shows each part as a preview: the project as a small
terminal (name, type, directory, then the command and the files it writes, as
on the Jobs page's Scout panel), the chosen style and motion as the Look & feel
step's own samples, skills in a rounded table, and component preview tiles.
The Review terminal is black in both themes with red, amber and green window
dots, and the skills table's header row is black. While Architecture reviews
the brief, the line under it shows what the planner is doing now (its latest
tool call, reasoning heading or "Writing up its questions"), one line, from the
job's `progress` field. The setup step does the same under its "installs
dependencies" task until the agent finishes.

Deleting a project the wizard created deletes its folder too, and the confirm
dialog names the folder. Before the folder goes, the setup agent's turn is
cancelled, the processes it registered are killed, and any other process
working inside the folder is stopped (`api/project_cleanup.py`), so an install
still running cannot write the folder back. The registry entry the wizard added
is removed. Deleting that folder on the Files page does the same and drops the
project when it has no chats or work items. Adopted projects never lose their
folder. In the Files page's delete bar, Done is a plain text button like All;
only Delete stands out. Text swaps in a card (`_psSwapText`) measure the new
height with the height transition off, because the root's `interpolate-size`
would otherwise report a mid-glide height. While the wizard is open the page
under its blurred backdrop pauses its animations (`html.ps-wizard-open`), so the
blur is not redrawn every frame. On phones Review's main button takes its own
row above Back and Create project.

Scrollbars stay hidden until their element scrolls: `static/ui.js` adds
`.is-scrolling` to whatever scrolls and removes it 900ms after the last scroll;
pointing at a hidden thumb still shows it so it can be grabbed. The thumb
fades in over 160ms and out over 280ms: the listener eases the registered
`--sb-a` property while `.sb-fading` is on the element, and the thumb uses it
as its opacity. Firefox, which has no thumb pseudo-element, shows and hides at
once.

Under Zeus 2.0 everything uses the skin's typeface: `--font-mono` follows
`--font-ui`, and the Dashboard's pixel fonts are replaced by the same local
faces scaled with `size-adjust` so its tuned sizes still fit.

## Responsive behavior

Mobile is not an afterthought. The repository documents a responsive layout with
a hamburger sidebar, mobile-accessible top tabs, a right-edge file slide-over,
full-height chat/composer behavior on phones, and touch-friendly controls.

On phone-sized standalone/PWA views, the left navigation is progressive: the
first edge swipe reveals only the clickable icon rail, and a second edge swipe
promotes it to the full sidebar. Do not expose a partially dragged full panel on
the first gesture. Both compact and full navigation support press-and-hold,
vertical scrub selection with a visible target preview; release activates the
selected destination. Drawer motion should preserve spatial continuity using
composited transforms or clipping, respect reduced-motion preferences, and keep
every navigation target at least 44 by 44 CSS pixels.

Mobile title bars reserve balanced space on both sides so the active page title
is centered in the viewport, not merely centered in the leftover flex space.
The profile switcher remains available on mobile, and browser/status-bar colors
must be synchronized before first paint to avoid a startup chrome flash.

For UI changes, verify the relevant states:

- wide desktop,
- ordinary laptop width,
- narrow/mobile width,
- open and closed side panels when relevant,
- long chat content and live streaming when relevant.

Controls should remain usable at touch sizes, and mobile navigation should not
steal chat height unnecessarily.

### Laptops (short and narrow desktop windows)

A 13" laptop browser leaves roughly 1280-1470px of width and 650-860px of
height once the browser's own toolbars are counted. Check 1470x850, 1470x750,
1366x768 and 1280x720 as well as a desktop monitor.

- The icon rail must reach Settings at any height: its buttons shrink from
  36px to 28px (`flex:0 1 36px`) before the rail is allowed to scroll (below
  ~690px tall), and its gaps tighten under 860px.
- The side panel is `clamp(268px, 12.5vw + 100px, 300px)`: full width from
  1600px, giving up to 32px to the page on smaller windows. Content in it must
  hold at 268px (Session usage title row, Office page buttons stack their icon
  above the label below 1400px).
- Office: when a platform or its department card would sit under the Task
  Status card, the overview frames the floor in the width left of the card
  (`overviewFor` / `podUnderCard` in `static/office/scene.js`); otherwise it
  stays centred. Folding or growing the card re-frames it.
- Dialogs use `max-height: calc(100dvh - 48px)` with a scrolling body, so the
  footer actions stay on screen in a 720px window.

### Phones (installed iPhone app first)

The reference device is an iPhone 15 Pro Max (430×932) running the app from
the Home Screen. Shared rules live in the "Phone foundation" block at the end
of `static/style.css`; page blocks after it only add what is particular to a
page.

- **Status bar.** Opaque `default`, tinted by `theme-color`, which boot.js
  keeps equal to the top bar's colour (`--sidebar`, remembered in
  localStorage for the next launch), so the band behind the clock and the
  Dynamic Island reads as part of the bar. Never `black-translucent`: on
  iOS 26 (WebKit bug 301108) a Home Screen app drawn under the status bar
  gets a web view one status bar short, and the band left at the bottom is
  outside the web view (no CSS or JS can paint it; measured 59px on an
  iPhone 15 Pro Max). Existing installs may need removing and re-adding.
- **Safe areas.** `viewport-fit=cover` is on, and `:root` exposes
  `--app-titlebar-safe-top`, `--app-safe-bottom`, `--app-safe-left` and
  `--app-safe-right` (env() values, 0 in a browser tab that has its own
  chrome). Every page except chat (the composer pads itself) and Jobs (its own
  bottom tab bar) ends above the home indicator. Landscape pads `.layout`.
- **Top bar.** A 7-column grid: three 44px cells each side, the logo + title
  in the true centre. Right-side actions share one footprint (44px, 20px
  icon). The profile switcher sits beside the menu button on phones.
- **Drawer.** Three stages: closed → icon strip (first left-to-right swipe;
  folds itself after 5 s idle or a tap elsewhere) → full drawer (second swipe).
  The strip slides in with `transform`; the panel unrolls with `clip-path`.
  While the drawer is out, the left-edge guard covers the whole edge so a
  swipe can never become Back. A swipe that crosses the claim threshold wins
  over the button it started on (its click is swallowed); a still tap presses
  the button. Choosing a page or section in the drawer closes it.
  The icon strip is a floating bar (inset 8px, translucent with a blur, corner
  radius concentric with its buttons: button radius + inset = 15px) rather
  than a full-height column; the panel stays hidden unless the drawer is fully
  open, and the bar keeps its floating look while it slides away
  (`.mobile-icons-leaving`). A short leftward flick (24px) folds it, the full
  drawer needs 64px. Chat rows swipe right only (archive); there is no
  swipe-left-to-delete, so a leftward swipe anywhere in the drawer closes it. Once a drawer swipe is claimed, boot.js
  sets `html.drawer-gesture`: the page (opening) or the drawer contents
  (closing) stop taking pointer events and selection until the finger lifts,
  and drawer contents only pan vertically. In the open drawer any touch in
  the first 30px of the rail — on an icon or between two — is cancelled in
  touchstart so it cannot become Back.
- **Page background.** On phones `body` uses the top bar's colour (`--sidebar`)
  and `.layout` carries `--bg`: iOS 26 paints the status bar and its soft top
  fade from the page background, so a mismatch shows as a dark band fading
  into the bar.
- **Toasts.** On phones they drop in below the top bar (never inside the
  status-bar area) and carry a shadow only while showing.
- **Microphone.** On touch devices the granted stream is kept for the page
  and muted between recordings (released after 10 idle minutes or on
  `pagehide`), because WebKit asks again for every new `getUserMedia` after
  a stop.
- **Routes.** The open page lives in the URL hash (`#office`,
  `#office/dashboard`, `#jobs/scout`), written with `replaceState`, so a
  reload returns to the same page and page switches never add Back entries.
  The route is also kept in `sessionStorage` for the tab, so code that resets
  the URL (clearing a stale conversation) cannot lose the page on reload.
- **No sideways drag.** Main views clip the horizontal axis; only explicit
  horizontal scrollers (chip rows, boards, a zoomed preview) scroll sideways.
- **Selection.** Chrome (buttons, bars, tabs, nav) never shows the selection
  callout; inputs, editable text and the transcript keep normal selection.

QA harness pattern: Playwright Chromium with `is_mobile`, `has_touch` and CDP
`Emulation.setSafeAreaInsetsOverride` (top 59, bottom 34; landscape left/right
59). It cannot show iOS font metrics or WebKit-only behaviour, so check the
real device for those.

## Themes and skins

Theme and skin work should use the existing variable system. `THEMES.md` points
to the core palette variables in `static/style.css`; skin comments in the CSS
show the expected pattern for full palette rewrites and accent-only changes.

Current implementation has two appearance axes, sourced from `static/boot.js`:
`theme` is only `light`, `dark`, or `system` and resolves to the `.dark` class
for dark mode; `skin` is a separate axis applied with `data-skin` and currently
includes `default`, `ares`, `mono`, `slate`, `poseidon`, `sisyphus`,
`charizard`, `sienna`, `catppuccin`, `nous`, and `geist-contrast` / Geist Contrast. `slate` is both an active skin
and a legacy theme-name migration target; `solarized`, `monokai`, `nord`, and
`oled` are legacy theme names mapped to current theme/skin pairs. Do not follow
stale `data-theme`-only guidance without first proving the current
`static/boot.js`, `static/index.html`, and `static/style.css` contracts still
support it.

Do not hardcode new colors, radii, shadows, or typography values into isolated
components when a token or existing variable can carry the intent. If a token is
missing, explain why a new one is needed.

## Evidence expected for UI changes

For any interface or interaction change:

- include before/after images or a short video,
- mention the tested viewport sizes and responsive states,
- reference the affected visual inventory or design source when applicable,
- add or update tests for behavior, state persistence, or regression-prone DOM
  structure where practical,
- keep stable class or data hooks when they help future visual regression tests.

## Do / don't summary

Do:

- keep the conversation primary,
- collapse noisy internals by default when settled,
- make debugging details accessible without making them visually dominant,
- use existing tokens, variables, and component patterns,
- protect action-required states such as errors and approvals.

Don't:

- make every tool call look like a separate chat message,
- add decorative color or motion without a user-facing reason,
- introduce a frontend framework, bundler, or build step for ordinary UI work,
- hide important recovery, error, or approval state,
- treat proposal mockups as shipped behavior without code/test evidence.
