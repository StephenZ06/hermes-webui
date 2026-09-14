# Sticky Board (vendored)

Source: https://github.com/rockywuest/sticky-board (MIT license, see LICENSE
in this directory). Single-file, zero-dependency Kanban-style sticky note
board, originally using `localStorage` for persistence.

Modifications from upstream:
- Translated UI strings from German to English, and replaced the seed data
  (a real business planning board) with generic placeholder columns/notes.
- Persistence swapped from `localStorage` to hermes-webui's own backend
  (`api/sticky_board.py`, `STATE_DIR/sticky_boards.json`) so boards are
  shared across every browser/device open on this instance, not just the
  one that created it.
- Multiple named boards, not one implicit board -- managed from the Notes
  sidebar (`static/notes.js`), not from this page. This page only renders
  whichever board its own `?board=<id>` query param names (the sidebar
  changes the board by changing this iframe's `src`); with no id, or an id
  that doesn't exist, it shows an empty state instead of seed content.
- A board can be linked to a Project folder (the same Projects the Chat
  sidebar's project-folder rows use). A linked board's content is mirrored
  into that project's `AGENTS.md` (a clearly delimited, idempotent section
  -- the rest of the file, including a user's own hand-written content, is
  left untouched) whenever the board is saved, renamed, or its own
  project changes; the section is removed if the board is deleted or
  unlinked. AGENTS.md at a project's workspace root is a real,
  already-proven ingestion path (`api/routes.py`'s
  `_project_context_candidates()` confirms hermes-agent looks for it
  there first), so a project's chats can pick up its linked board's
  content without any agent-side changes. Verified live against a real
  project's existing, substantial hand-written AGENTS.md: the section
  appended and removed cleanly, original content untouched throughout.
- Chrome (header, columns, buttons, board background) reskinned to follow
  hermes-webui's active skin/dark-light theme instead of a fixed cream
  palette -- `syncThemeFromParent()` reads the parent `<html>`'s live
  computed CSS custom properties (`--bg`, `--surface`, `--accent`,
  `--font-ui`, etc.) and applies them locally, with a `MutationObserver`
  re-syncing on any skin/theme change while the panel is open. Font is the
  app's own `--font-ui`, not the upstream 'Segoe UI' stack.
- Note text (title, sub-items) is pinned to literal black -- notes stay
  pastel-colored regardless of app theme (like colored paper), so their
  text must not follow a dark-mode --text color that could end up
  light-on-light. Note colors themselves (yellow/green/pink/blue) also
  stay literal for the same reason -- they're the user's own note colors,
  not app chrome.
- Removed the assignee feature entirely (icon, name field, initials,
  associated data) -- unused.
- Removed the inline 4-dot color picker from each note's face. A small
  circular button (showing the note's current color) in note-actions now
  opens a shared color-picker modal instead, with larger swatches to pick
  from; closes on picking a color, the × button, backdrop click, or Escape.
- Pressing Enter in a sub-item field inserts a new empty sub-item directly
  below it and focuses it (checklist-style), rather than doing nothing.

Embedded in hermes-webui via an `<iframe>` in the Notes panel
(`static/index.html`'s `#mainNotes`). Same-origin, so its `fetch()` calls to
`/api/sticky_boards*` carry the parent page's session cookie automatically
(and its CSRF token, pulled from `window.parent.__HERMES_CONFIG__` -- see
the comment above `csrfHeaders()`).

Mobile: columns scroll-snap to near-full-width at <=600px instead of a
wide horizontal strip, and the color-picker modal narrows to fit.
