# Sticky Board (vendored)

Source: https://github.com/rockywuest/sticky-board (MIT license, see LICENSE
in this directory). Single-file, zero-dependency Kanban-style sticky note
board, originally using `localStorage` for persistence.

Modifications from upstream:
- Translated UI strings from German to English, and replaced the seed data
  (a real business planning board) with generic placeholder columns/notes.
- Persistence swapped from `localStorage` to hermes-webui's own backend
  (`api/sticky_board.py`, `GET`/`POST /api/sticky_board`,
  `STATE_DIR/sticky_board.json`) so the board is shared across every
  browser/device open on this instance, not just the one that created it.
  `localStorage` is kept only as a fallback (used if the server request
  fails, and as a one-time migration source the first time this page loads
  against an instance with no saved board yet) -- otherwise unchanged.
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
`/api/sticky_board` carry the parent page's session cookie automatically.
