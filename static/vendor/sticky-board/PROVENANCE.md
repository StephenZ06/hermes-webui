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
  computed CSS custom properties (`--bg`, `--surface`, `--accent`, etc.) and
  applies them locally, with a `MutationObserver` re-syncing on any
  skin/theme change while the panel is open. Note colors themselves
  (yellow/green/pink/blue) stay literal -- they're the user's own note
  colors, like colored paper, not app chrome.

Embedded in hermes-webui via an `<iframe>` in the Notes panel
(`static/index.html`'s `#mainNotes`). Same-origin, so its `fetch()` calls to
`/api/sticky_board` carry the parent page's session cookie automatically.
