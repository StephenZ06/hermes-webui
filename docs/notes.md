# Notes (BlockNote)

The **Notes** page (rail icon "Notes", panel key `notebook`) is a block-based
note editor built on [BlockNote](https://github.com/TypeCellOS/BlockNote). It
sits next to **Work Hub** (panel key `notes`, kept for saved-state
compatibility), which holds sticky-note work items on kanban boards. Notes holds
long-form documents.

## Layout

- **Side panel** (`#notebookSidebar`) uses the Work Hub panel's markup and
  classes, so the two look and move the same. It contains:
  - scopes: All notes, General, Pinned, Favorites and Trash;
  - **Workspaces**, the shared project registry also listed by Chat and Work Hub;
  - **Folders**, which are Notes-only: they are created here and never appear on other pages;
  - a centred `+` under Folders that opens *New note / New folder / Delete*;
  - tags.

  A click anywhere on a workspace or folder tile selects it and opens or
  closes its list of notes in place (animated). *Delete* enters the shared
  delete mode (`createDeleteMode` in `static/ui.js`): notes and Notes folders
  wiggle with an X, and workspaces stay locked because they belong to Chat
  and Work Hub too. Right-click a folder to rename it.
- **Main view** (`#notebookRoot`) holds the notes list (search, items) and the
  editor. The editor shows the title, status, pin, favorite and a "More" menu,
  then the workspace/folder picker, tags and the BlockNote body.
- Below 900px the list and editor show one at a time, with a back button.

## Architecture

```
static/notebook/index.js   page controller: state, side panel, list, editor host, autosave
static/notebook/api.js     HTTP client (window.NotebookApi)
static/vendor/blocknote/0.55.0/blocknote-hermes.{js,css}   pre-built editor bundle (lazy-loaded)
tools/blocknote/           source + build for that bundle (not used at runtime)
api/notebook.py            storage, validation, search, plain-text extraction, uploads
api/notebook_api.py        /api/notebook/* routes (registered in api/routes.py)
```

The app has no bundler and no React. BlockNote is React, so
`tools/blocknote/src/entry.jsx` wraps it behind a small vanilla API. It is
bundled once with esbuild into an ES module and committed, just as three.js is
vendored. The Notes page imports it the first time a note is opened.

```js
const ctl = mountNoteEditor(element, {content, theme, editable, placeholder, uploadFile, onChange, slashItems});
ctl.getBlocks(); ctl.toMarkdown(); ctl.toHTML(); ctl.parseMarkdown(md); ctl.replaceAll(blocks);
ctl.setTheme('dark'); ctl.setEditable(false); ctl.focus(); ctl.destroy();
```

There is one editor instance per open note, so undo history never crosses
notes. Switching notes saves the pending edits first, then mounts a fresh
editor.

**Packages:**
- `@blocknote/core`, `@blocknote/react` and `@blocknote/mantine` (MPL-2.0);
- React and Mantine (MIT).
- No GPL `@blocknote/xl-*` packages are used.

The licence texts ship as `blocknote-hermes.js.LEGAL.txt`.

### Rebuilding the bundle

```bash
cd tools/blocknote && npm install && npm run build
```

Versions are pinned exactly in `tools/blocknote/package.json` (the repo does not track lockfiles). To upgrade BlockNote, bump the versions in `tools/blocknote/package.json`,
rebuild, and update `EDITOR_VERSION` in `static/notebook/index.js`. The output
directory is named after the version, so caches don't serve the old bundle.

## Obsidian vault (`api/notebook_vault.py`)

With an Obsidian vault connected, **every note is a file in the vault**. The
main view keeps its structure (General, Pinned, Favorites, Workspaces,
Folders), laid out PARA-style in the vault as its `.hermes-brain-rules.md`
asks:

| Main view | Vault folder |
|---|---|
| General | `00 Inbox/` |
| a workspace (e.g. Triple S) | `01 Projects/<workspace>/` (kept if the workspace is renamed later) |
| a folder made on the Notes page | `03 Resources/<folder>/` |

**Obsidian Notes** at the top of the side panel switches to the whole vault
(All notes, Vault root, its folders two levels deep — `01 Projects / Triple S`
sits indented under `01 Projects` — tags, trash), and **‹ Notes** comes back.
It is the same file either way: an edit in one view is the edit in the other.
Notes outside the main view's places (the rest of your vault) appear only on
the Obsidian side. The main view's search, trash and Empty trash cover only
its own places.

Hermes' own notes from before were moved in once (`POST
/api/notebook/vault/import`: notes with content, each in its place; empty ones
left out; never written twice); the old store is kept as a backup and an old
note id still opens from it. Vault ids start with `v`, which is how each
request is routed. The setting
is **Settings → Preferences → Notes · Obsidian vault**: it shows the status,
pre-fills a vault it finds among your saved workspaces (a folder containing
`.obsidian`), and **Connect** / **Change** / **Disconnect** apply at once (an
open Notes page reloads onto the new store). Nothing switches until you press
Connect (config: `notebook_vault.json` in the WebUI state directory,
`{path, enabled}`; Disconnect hides the vault's notes again, and Hermes' own
notes are never affected).

In the vault:

- a note is a `.md` file and its title is the file name; the vault root is
  **Vault root**, each top-level folder is a folder (deeper sub-folders stay
  where they are and show under their top-level folder). The attachment
  folder is not listed as a folder;
- the editor gets the Markdown body; YAML frontmatter is never shown and is
  written back exactly as it was. Tags are the frontmatter `tags:`;
- Images and files can be added on desktop and phone: the attach button in the
  note header (one or many; photo library, camera and Files on a phone), the
  `/image` and `/file` slash commands, paste, and drag-and-drop. A photo the
  store would refuse (over 7 MB, or a HEIC the browser can decode) is redrawn as
  a JPEG (longest side 2560 px) in the browser first. Accepted by content, not
  by name: PNG, JPEG, GIF, WebP (images, 8 MB) and PDF, Word, Excel, PowerPoint,
  ZIP, text, Markdown, CSV and JSON (files, 12 MB). Images show inline; every
  other file is only ever sent as a download (`Content-Disposition: attachment`,
  `nosniff`, a sandboxing CSP). Audio (MP3, M4A, WAV, OGG, FLAC, WebM) and video
  (MP4, MOV, WebM) play inline: they go up as a raw request body to
  `POST uploads/stream` (not JSON, so up to `HERMES_WEBUI_NOTES_MEDIA_MB`, default
  200 MB, with a progress bar) and are served with byte ranges, which iOS needs to
  play or seek. In a vault, media is written to the attachment folder and linked
  as `![name](path)` (Obsidian embeds it); media may be played from anywhere in the
  vault, documents are read back only from the attachment folder.
- A picture or clip is outlined in the accent colour when tapped. On a phone it
  fills the text width until resized, the resize bars appear on a second tap (a
  quick double tap for a clip, since taps also play and pause it) and go away once
  a resize ends. Taps on a player never reach the editor. A clip has its own controls (the browser's
  were unreliable for taps here): a play button, and a bar with play/pause, time, seek,
  mute (volume on a desktop) and full screen. They show while it is paused or finished,
  fade a moment after it starts, and return on a tap; starting one clip stops the others.
  A recording gets the same bar (play/pause, time, seek, mute), always in view, with no
  big button or full screen. The
  width is saved as the block's `previewWidth`, and for a vault picture as
  Obsidian's `![alt|300](...)` / `![[x.png|300]]`.
- `[[wikilinks]]`, `#tags` and `![[image.png]]` embeds survive a save in
  Obsidian's syntax; images in notes are served from the vault
  (`/api/notebook/vault/file?path=`), and pasted images are saved to the
  vault's attachment folder (`attachmentFolderPath`, default `Attachments`);
- **opening a note never writes it** — the file changes only after a real edit
  (the editor compares its Markdown with what was loaded). Bullets are written
  as `-`;
- the revision is the file's modification time: an edit made in Obsidian
  meanwhile is a conflict ("changed in Obsidian or another window": keep mine
  or load theirs), never silently overwritten;
- trash is the vault's `.trash` folder (restore puts the note back where it
  was); deleting a folder that still holds files is refused;
- hidden folders and symlinks are never followed, and every path is checked
  to stay inside the vault. Pinned/favourite and stable note ids live in
  `notebook_vault.db` next to the WebUI state, not in your files.

## Data model (`notebook.db` in the WebUI state directory)

| Table | Columns |
|---|---|
| `notebook_notes` | `id`, `title`, `content` (BlockNote block JSON, stored as-is), `plain_text` (extracted on the server), `project_id` *or* `folder_id` (neither = General), `tags` (JSON list), `pinned`, `favorite`, `archived`, `deleted_at` (trash), `revision`, `created_at`, `updated_at` |
| `notebook_folders` | `id`, `name`, `color`, `sort_order`, timestamps |
| `notebook_files` | uploaded images (`id`, `note_id`, `filename`, `mime`, `size`); the bytes live in `notebook_files/<id>.<ext>` |

- If a note's workspace is deleted on another page, the note is shown under
  General. Deleting a Notes folder moves its notes to General.
- `extract_plain_text(blocks)` turns the block JSON into readable lines
  (checklists as `[x]`/`[ ]`, nested blocks indented). It feeds search now and
  is the hook for agent context and embeddings later.

## Autosave

1. Edits mark fields dirty and are debounced for 800ms.
2. Saves go out one at a time. Edits made during a save are sent after it.
3. Every save sends `expected_revision`. The server refuses a stale one with
   409 and the current note, so an older save can never overwrite a newer one.
   That case shows *Changed elsewhere* with **Keep mine / Load theirs**.
4. If a save fails, the dirty fields stay in the editor and are copied to
   `localStorage` (`hermes-notebook-draft:<id>`). They are retried every 5s and
   on **Retry now**. A draft whose base revision still matches is restored the
   next time the note opens. The draft is removed once a save succeeds.
5. `Ctrl/Cmd+S` saves immediately. Leaving the page or hiding the tab flushes
   pending edits.

## API (`/api/notebook/…`)

| Method | Path | Purpose |
|---|---|---|
| GET | `bootstrap` | workspaces, folders, note summaries |
| GET | `notes?q=…[&trash=1]` | search: every word must match the title, text, `#tag`, workspace or folder name |
| GET | `notes/{id}` | full note (with `content`) |
| GET | `notes/{id}/context` | note as agent context: title, plain text, tags, workspace, folder |
| GET | `files/{id}` | an uploaded image (inline) or file (download) |
| POST | `notes/create` | `{title?, content?, project_id? \| folder_id?, tags?}` |
| POST | `notes/{id}/update` | partial update + `expected_revision` |
| POST | `notes/{id}/trash` · `restore` · `purge` · `duplicate` | |
| POST | `trash/empty` | |
| POST | `folders/create` · `folders/{id}/rename` · `folders/{id}/delete` | |
| POST | `uploads/stream` | `?filename=&note_id=`, body = the raw bytes of an audio/video file (`Content-Length` required); reply as `uploads` |
| POST | `uploads` | `{filename, content_base64, note_id?}`: images (at most 8 MB) and documents (at most 12 MB), checked by content; the reply carries `url`, `mime`, `size`, `name` |

## Hermes integration points

- **Send to chat** (More menu) starts a fresh chat and puts the note, as
  Markdown, in the composer. It does not send. The user picks the agent and
  model, so the note goes through the normal chat orchestration.
- **`GET notes/{id}/context`** is the stable shape for future agent actions,
  task creation and retrieval.
- **Custom slash commands:** pass `slashItems` to `mountNoteEditor` (in
  `mountEditor()` in `static/notebook/index.js`). It is a function that
  receives the BlockNote editor and returns extra items, for example:

  ```js
  slashItems: (editor) => [{
    title: 'Insert date', group: 'Hermes', aliases: ['today'], subtext: 'Today’s date',
    onItemClick: () => editor.insertInlineContent(new Date().toLocaleDateString()),
  }],
  ```

  Only add commands that do something real. Agent actions should call
  existing Hermes APIs.

## Keyboard

| Keys | Action |
|---|---|
| `Ctrl/Cmd+S` | save now |
| `Alt+N` | new note |
| `Ctrl/Cmd+Shift+F` | focus note search |
| `/` (in the editor) | BlockNote slash menu |
| `Enter` (in the title) | move to the body |

Ctrl/Cmd+N belongs to the browser and Ctrl/Cmd+K to Chat, so they are not used.

## Tests

- `tests/test_notebook.py`: storage, revisions, places, trash, folders, search,
  uploads and context.
- `tests/test_notebook_browser.py`: writing with the slash menu, autosave and
  reload, placement, failed-save recovery, switching mid-edit, trash, search,
  Send to chat.
