# Sticky Board (vendored)

Source: https://github.com/rockywuest/sticky-board (MIT license, see LICENSE
in this directory). Single-file, zero-dependency Kanban-style sticky note
board using `localStorage` for persistence.

Modifications from upstream: translated UI strings from German to English,
and replaced the seed data (a real business planning board) with generic
placeholder columns/notes. No functional changes.

Embedded in hermes-webui via an `<iframe>` in the Notes panel
(`static/index.html`'s `#mainNotes`). Data is per-browser (`localStorage`),
matching the upstream project's own zero-server design -- not synced across
devices or persisted server-side.
