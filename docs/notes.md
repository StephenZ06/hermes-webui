# Notes (BlockNote)

The **Notes** page (rail icon "Notes", panel key `notebook`) is a block-based
note editor built on [BlockNote](https://github.com/TypeCellOS/BlockNote). It
sits next to **Work Hub** (panel key `notes`, kept for saved-state
compatibility), which holds sticky-note work items on kanban boards. Notes holds
long-form documents.

## Layout

- **Side panel** (`#notebookSidebar`) contains:
  - *New note*;
  - scopes: All notes, General, Pinned, Favorites and Trash;
  - **Workspaces**, the shared project registry also listed by Chat and Work Hub;
  - **Folders**, which are Notes-only: they are created here and never appear on other pages;
  - tags.

  Workspaces and folders expand to list their notes, the same way Work Hub
  folders list boards.
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
cd tools/blocknote && npm ci && npm run build
```

To upgrade BlockNote, bump the versions in `tools/blocknote/package.json`,
rebuild, and update `EDITOR_VERSION` in `static/notebook/index.js`. The output
directory is named after the version, so caches don't serve the old bundle.

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
| GET | `files/{id}` | an uploaded image |
| POST | `notes/create` | `{title?, content?, project_id? \| folder_id?, tags?}` |
| POST | `notes/{id}/update` | partial update + `expected_revision` |
| POST | `notes/{id}/trash` · `restore` · `purge` · `duplicate` | |
| POST | `trash/empty` | |
| POST | `folders/create` · `folders/{id}/rename` · `folders/{id}/delete` | |
| POST | `uploads` | `{filename, content_base64, note_id?}`: PNG/JPEG/GIF/WebP only, checked by content, at most 8 MB |

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
