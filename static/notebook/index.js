/* Notes page: BlockNote documents organised by workspace, Notes folders and General.
 *
 * Side panel (#notebookSidebar): scopes (All notes, General, Pinned,
 * Favorites, Trash), the shared workspaces (projects) and Notes-only folders,
 * each expandable to its notes, plus tags.
 * Main view (#notebookRoot): the notes list for the scope and the editor.
 *
 * The editor is the vendored BlockNote bundle (static/vendor/blocknote/),
 * imported on first use. One editor instance per open note.
 *
 * Saving: edits are debounced (800ms) into one in-flight save at a time. Each
 * save names the revision it was based on; a newer edit made meanwhile is
 * sent after it. If a save fails, the unsaved title/content stay in the editor
 * and in localStorage (per note) and are retried; nothing is dropped. A save
 * refused because the note changed elsewhere (another tab) asks which copy
 * to keep.
 */
(function () {
  'use strict';
  const SAVE_DELAY_MS = 800;
  const RETRY_MS = 5000;
  const DRAFT_KEY = (noteId) => 'hermes-notebook-draft:' + noteId;
  const LAST_KEY = 'hermes-notebook-last';
  const EDITOR_VERSION = '0.55.0';

  const S = {
    loaded: false, loading: false, error: '',
    vault: null, vaultConfig: null, // connected Obsidian vault (api/notebook_vault.py)
    // Which notes the side panel shows: Hermes' own ('notes', the main view)
    // or the Obsidian vault's ('vault', opened from "Obsidian Notes").
    side: 'notes',
    scope: {kind: 'general', id: null},
    search: '', searchResults: null, searchSeq: 0,
    expanded: {}, more: {}, tagFilter: null,
    note: null, noteLoading: false, noteError: '',
    pane: 'list', // narrow screens: 'list' | 'editor'
  };
  const save = {timer: 0, retry: 0, inflight: null, dirty: {}, again: false, status: 'idle', error: '', conflict: null};
  // The two stores, side by side. S.projects / S.folders / S.notes are the
  // active one's, so the tree, list, search and delete code work unchanged.
  const W = {notes: {projects: [], folders: [], notes: []}, vault: {projects: [], folders: [], notes: []}};
  ['projects', 'folders', 'notes'].forEach((key) => Object.defineProperty(S, key, {
    get: () => W[S.side][key], set: (value) => { W[S.side][key] = value; }, enumerable: true,
  }));
  const isVaultNote = (note) => !!note && (note.store === 'vault' || String(note.id || '').startsWith('v'));
  // One vault note, seen from the Obsidian side: its place there is its
  // folder in the vault (two levels: "01 Projects / Triple S"), not the main
  // view's workspace or Notes folder.
  const asVaultView = (note) => Object.assign({}, note, {project_id: null, folder_id: note.vault_folder_id || null});
  function useSide(side) {
    S.side = side === 'vault' && S.vault ? 'vault' : 'notes';
    S.scope = S.side === 'vault' ? {kind: 'all', id: null} : {kind: 'general', id: null};
    S.search = ''; S.searchResults = null; S.tagFilter = null;
    if (S.deleteMode && deleteModeRef) deleteModeRef.exit();
    const search = $('nbSearch'); if (search) search.value = '';
  }
  let editorModule = null;
  let editorCtl = null;
  let editorNoteId = null;
  let themeObserver = null;
  let searchTimer = 0;

  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value == null ? '' : value).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const toast = (message) => { if (typeof window.showToast === 'function') window.showToast(message); };
  const ICONS = {
    note: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="m21 16-5-5-8 8"/>',
    all: '<path d="M4 6h16M4 12h16M4 18h10"/>',
    general: '<path d="M4 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/>',
    folder: '<path d="M4 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/>',
    pin: '<path d="M12 17v5M8 3h8l-1 6 3 3H6l3-3z"/>',
    star: '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
    trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    more: '<circle cx="5" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="19" cy="12" r="1.4"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    back: '<path d="m15 18-6-6 6-6"/>',
    tag: '<path d="M3 12V4h8l9 9-8 8z"/><circle cx="7.5" cy="8.5" r="1.2"/>',
    vault: '<path d="M12 2.5 4.5 7v10L12 21.5l7.5-4.5V7z"/><path d="M12 2.5v19M4.5 7l7.5 4.5L19.5 7"/>',
  };
  const icon = (name, size) => `<svg width="${size || 14}" height="${size || 14}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`;

  function when(seconds) {
    if (!seconds) return '';
    const diff = Math.max(0, Date.now() / 1000 - seconds);
    if (diff < 60) return 'just now';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    if (diff < 86400 * 7) return Math.floor(diff / 86400) + 'd ago';
    return new Date(seconds * 1000).toLocaleDateString(undefined, {month: 'short', day: 'numeric'});
  }
  const projectOf = (id) => S.projects.find((p) => p.project_id === id) || null;
  const folderOf = (id) => S.folders.find((f) => f.id === id) || null;
  function placeLabel(note) {
    // Named for the view it is shown in: the main view's General is the
    // vault's 00 Inbox; only the Obsidian side says "Vault root".
    const root = S.side === 'vault' ? 'Vault root' : 'General';
    if (note.project_id) { const p = projectOf(note.project_id); return p ? p.name : root; }
    if (note.folder_id) { const f = W[S.side].folders.find((x) => x.id === note.folder_id); return f ? f.name : root; }
    return root;
  }
  // The colour of the note's workspace or folder, as on their side-panel dots.
  function placeColor(note) {
    if (note.project_id) { const p = projectOf(note.project_id); return (p && p.color) || 'var(--accent)'; }
    if (note.folder_id) { const f = folderOf(note.folder_id); return (f && f.color) || 'var(--muted)'; }
    return 'var(--muted)';
  }
  const live = (n) => !n.deleted_at;

  // ── scope & filtering ───────────────────────────────────────────────────────
  function inScope(note, scope) {
    switch (scope.kind) {
      case 'trash': return !!note.deleted_at;
      case 'general': return live(note) && !note.project_id && !note.folder_id;
      case 'pinned': return live(note) && note.pinned;
      case 'favorites': return live(note) && note.favorite;
      case 'project': return live(note) && note.project_id === scope.id;
      case 'folder': return live(note) && note.folder_id === scope.id;
      default: return live(note) && !note.archived;
    }
  }
  function visibleNotes() {
    const base = S.searchResults || S.notes;
    return base.filter((n) => inScope(n, S.scope) && (!S.tagFilter || (n.tags || []).includes(S.tagFilter)));
  }
  function scopeTitle() {
    const k = S.scope.kind;
    if (k === 'project') return (projectOf(S.scope.id) || {}).name || 'Workspace';
    if (k === 'folder') return (folderOf(S.scope.id) || {}).name || 'Folder';
    if (S.side === 'vault') return {all: 'Obsidian notes', general: 'Vault root', trash: 'Vault trash'}[k] || 'Obsidian notes';
    return {all: 'All notes', general: 'General', pinned: 'Pinned', favorites: 'Favorites', trash: 'Trash'}[k] || 'Notes';
  }
  // Where a note created in the current scope goes.
  function placeForScope() {
    // view: where a note made here goes in the vault ("notes": the main
    // view's places, 00 Inbox for General; "vault": the Obsidian side).
    const store = S.side === 'vault' ? {store: 'vault', view: 'vault'} : {view: 'notes'};
    if (S.scope.kind === 'project') return Object.assign({project_id: S.scope.id}, store);
    if (S.scope.kind === 'folder') return Object.assign({folder_id: S.scope.id}, store);
    return store;
  }

  // ── data ───────────────────────────────────────────────────────────────────
  async function loadBootstrap() {
    S.loading = true; S.error = '';
    try {
      const data = await window.NotebookApi.bootstrap();
      W.notes = {projects: data.projects || [], folders: data.folders || [], notes: data.notes || []};
      const v = data.vault || null;
      W.vault = {projects: [], folders: (v && v.folders) || [], notes: ((v && v.notes) || []).map(asVaultView)};
      S.vault = v ? (v.vault || {name: 'Vault'}) : null;
      S.vaultConfig = data.vault_config || null;
      if (S.side === 'vault' && !S.vault) useSide('notes');
      S.loaded = true;
    } catch (error) {
      S.error = error.message || 'Notes could not be loaded';
    }
    S.loading = false;
  }
  function upsertSummary(note) {
    const summary = Object.assign({}, note);
    delete summary.content;
    // Connected, a note can be in both lists (main view and Obsidian side),
    // each with its own place; it leaves the main list once it is moved out
    // of the main view's places in the vault.
    const put = (list, item) => {
      const index = list.findIndex((n) => n.id === item.id);
      if (index >= 0) list[index] = Object.assign(list[index], item);
      else list.unshift(item);
    };
    if (isVaultNote(note) && 'vault_folder_id' in note) {
      put(W.vault.notes, asVaultView(summary));
      if (note.in_main) put(W.notes.notes, summary);
      else W.notes.notes = W.notes.notes.filter((n) => n.id !== note.id);
    } else {
      put(W[isVaultNote(note) ? 'vault' : 'notes'].notes, summary);
    }
    if (S.searchResults) {
      const i = S.searchResults.findIndex((n) => n.id === note.id);
      if (i >= 0) S.searchResults[i] = Object.assign(S.searchResults[i], summary);
    }
  }
  function sortNotes() {
    S.notes.sort((a, b) => (b.pinned - a.pinned) || (b.updated_at - a.updated_at));
  }

  // ── rendering: side panel ───────────────────────────────────────────────────
  function count(predicate) { return S.notes.filter(predicate).length; }
  function scopeButton(kind, label, iconName, n, extraClass) {
    const active = S.scope.kind === kind ? ' active' : '';
    return `<button type="button" class="work-hub-scope nb-scope${extraClass ? ' ' + extraClass : ''}${active}" data-nb-scope="${kind}">${icon(iconName)}<span>${esc(label)}</span>${n ? `<span class="nb-scope-count">${n}</span>` : ''}</button>`;
  }
  const TREE_LIMIT = 50;
  function noteRows(notes, key) {
    if (!notes.length) return '<p class="nb-tree-empty">No notes yet</p>';
    const all = !!(key && S.more[key]);
    const shown = all ? notes : notes.slice(0, TREE_LIMIT);
    const more = notes.length > TREE_LIMIT && key
      ? `<button type="button" class="nb-tree-more" data-nb-action="more" data-nb-more="${esc(key)}">${all ? 'Show fewer' : `Show ${notes.length - TREE_LIMIT} more`}</button>` : '';
    return shown.map((n) => `<div class="work-hub-board-row nb-tree-note${S.note && S.note.id === n.id ? ' active' : ''}" data-nb-note-row="${esc(n.id)}"><button type="button" data-nb-open="${esc(n.id)}">${icon('note', 13)}<span>${esc(n.title || 'Untitled')}</span></button></div>`).join('') + more;
  }
  // Same markup and classes as the Work Hub's workspace folders, so the two
  // side panels look and move the same: a whole-tile click selects the place
  // and opens/closes it in place (the grid-rows transition animates).
  function placeGroup(kind, item, notes, childrenHtml) {
    const key = kind + ':' + item.id;
    const expanded = !!S.expanded[key] || (S.deleteMode && notes.length > 0);
    const active = S.scope.kind === kind && S.scope.id === item.id ? ' active' : '';
    const groupId = 'nbGroup-' + key.replace(/[^A-Za-z0-9_-]/g, '_');
    return `<button type="button" class="project-chip project-folder-row work-hub-project-tile nb-place-btn${active}" data-nb-kind="${kind}" data-nb-id="${esc(item.id)}" data-nb-key="${esc(key)}" aria-expanded="${expanded}" aria-controls="${groupId}">`
      + `<span class="project-folder-chevron work-hub-project-chevron${expanded ? ' expanded' : ''}">▸</span>`
      + `<span class="color-dot work-hub-project-color" aria-hidden="true" style="background:${esc(item.color || (kind === 'folder' ? 'var(--muted)' : 'var(--accent)'))}"></span>`
      + `<span class="project-folder-name work-hub-project-name"></span><span class="project-folder-count work-hub-project-count" aria-label="${notes.length} notes">${notes.length}</span></button>`
      + `<div id="${groupId}" class="project-folder-sessions work-hub-project-boards${expanded ? ' expanded' : ''}" ${expanded ? '' : 'inert'}><div class="project-folder-sessions-inner work-hub-project-boards-inner">${noteRows(notes, key)}${childrenHtml || ''}</div></div>`;
  }
  // The store changed (Settings → Preferences → Notes · Obsidian vault): drop
  // the open note, which belongs to the old store, and load the new one.
  async function vaultChanged() {
    await flushSave();
    S.note = null; destroyEditor(); useSide('notes');
    if (!S.loaded) return;
    await loadBootstrap(); render();
  }
  // A vault sub-folder ("01 Projects / Triple S") lives inside its parent's
  // collapsible group, so folding the parent hides it.
  function vaultFolderGroups(liveNotes) {
    const group = (f, kids) => placeGroup('folder', {id: f.id, color: f.color}, liveNotes.filter((n) => n.folder_id === f.id), kids);
    const isChild = (f) => !!f.parent && S.folders.some((p) => !p.parent && p.name === f.parent);
    return S.folders.filter((f) => !isChild(f)).map((f) => group(f, S.folders.filter((c) => isChild(c) && c.parent === f.name).map((c) => group(c, '')).join(''))).join('');
  }
  // The Obsidian side: the vault's folders and notes, with the way back.
  function renderVaultSidebar(side, liveNotes, tags, dm) {
    side.innerHTML = `<nav class="work-hub-nav nb-nav nb-nav-vault" aria-label="Obsidian notes">
      <button type="button" class="nb-vault-back" data-nb-action="vault-close">${icon('back', 14)}<span>Notes</span></button>
      <div class="nb-vault-title" title="${esc((S.vaultConfig && S.vaultConfig.path) || '')}"><span class="nb-vault-mark" aria-hidden="true">${icon('vault', 14)}</span><span><strong>Obsidian</strong><small>${esc((S.vault && S.vault.name) || 'Vault')}</small></span></div>
      ${scopeButton('all', 'All notes', 'all', count((n) => live(n)))}
      ${scopeButton('general', 'Vault root', 'general', count((n) => live(n) && !n.folder_id))}
      <div class="work-hub-nav-label work-hub-projects-heading"><span>FOLDERS</span></div>
      <div class="project-folder-list work-hub-projects nb-folders${dm}">${vaultFolderGroups(liveNotes)}</div>
      <div class="work-hub-project-create-row nb-create-row">${S.deleteMode
        ? '<button type="button" class="work-hub-project-delete-done" data-nb-action="delete-done">Done</button>'
        : `<button type="button" class="work-hub-project-create" data-nb-action="create-menu" aria-label="New note, new folder or delete" aria-haspopup="menu">${icon('plus', 13)}</button>`}</div>
      ${tags.length ? `<div class="work-hub-nav-label work-hub-projects-heading"><span>TAGS</span></div><div class="nb-tag-cloud">${tags.map((t) => `<button type="button" class="nb-tag${S.tagFilter === t ? ' active' : ''}" data-nb-tag="${esc(t)}">#${esc(t)}</button>`).join('')}</div>` : ''}
      <div class="nb-nav-spacer"></div>
      ${scopeButton('trash', 'Trash', 'trash', count((n) => !!n.deleted_at), 'nb-trash-scope')}
    </nav>`;
    side.querySelectorAll('.nb-place-btn').forEach((button) => {
      const item = folderOf(button.dataset.nbId);
      // A folder inside a top-level one ("01 Projects / Triple S") sits
      // indented under it, by its own name.
      const sub = !!(item && item.parent);
      button.querySelector('.project-folder-name').textContent = item ? (sub ? item.name.split(' / ').pop() : item.name) : 'Untitled';
      if (sub) { button.classList.add('nb-subfolder'); button.title = item.name; }
    });
    if (S.deleteMode) decorateDeleteMode(side);
  }
  function renderSidebar() {
    const side = $('notebookSidebar');
    if (!side) return;
    if (!S.loaded) { side.innerHTML = S.error ? `<p class="nb-side-error">${esc(S.error)}</p>` : '<div class="nb-side-loading" aria-busy="true"><i></i><i></i><i></i></div>'; return; }
    const liveNotes = S.notes.filter(live);
    const tags = [...new Set(liveNotes.flatMap((n) => n.tags || []))].sort();
    const dm = S.deleteMode ? ' is-delete-mode' : '';
    if (S.side === 'vault') { renderVaultSidebar(side, liveNotes, tags, dm); return; }
    const vaultCount = W.vault.notes.filter(live).length;
    side.innerHTML = `<nav class="work-hub-nav nb-nav" aria-label="Notes navigation">
      <button type="button" class="work-hub-scope nb-scope nb-obsidian-scope" data-nb-action="vault-open" title="${S.vault ? 'Your Obsidian vault: ' + esc(S.vault.name || '') : 'Connect your Obsidian vault in Settings'}">${icon('vault')}<span>Obsidian Notes</span>${S.vault ? `<span class="nb-scope-count">${vaultCount}</span>` : '<span class="nb-scope-hint">Connect</span>'}<span class="nb-scope-chevron" aria-hidden="true">›</span></button>
      ${scopeButton('general', 'General', 'general', count((n) => live(n) && !n.project_id && !n.folder_id))}
      ${scopeButton('pinned', 'Pinned', 'pin', count((n) => live(n) && n.pinned))}
      ${scopeButton('favorites', 'Favorites', 'star', count((n) => live(n) && n.favorite))}
      <div class="work-hub-nav-label work-hub-projects-heading"><span>WORKSPACES</span></div>
      <div class="project-folder-list work-hub-projects nb-projects${dm}">${S.projects.map((p) => placeGroup('project', {id: p.project_id, color: p.color}, liveNotes.filter((n) => n.project_id === p.project_id))).join('')}</div>
      <div class="work-hub-nav-label work-hub-projects-heading"><span>FOLDERS</span></div>
      <div class="project-folder-list work-hub-projects nb-folders${dm}">${S.folders.map((f) => placeGroup('folder', {id: f.id, color: f.color}, liveNotes.filter((n) => n.folder_id === f.id))).join('')}</div>
      <div class="work-hub-project-create-row nb-create-row">${S.deleteMode
        ? '<button type="button" class="work-hub-project-delete-done" data-nb-action="delete-done">Done</button>'
        : `<button type="button" class="work-hub-project-create" data-nb-action="create-menu" aria-label="New note, new folder or delete" aria-haspopup="menu">${icon('plus', 13)}</button>`}</div>
      ${tags.length ? `<div class="work-hub-nav-label work-hub-projects-heading"><span>TAGS</span></div><div class="nb-tag-cloud">${tags.map((t) => `<button type="button" class="nb-tag${S.tagFilter === t ? ' active' : ''}" data-nb-tag="${esc(t)}">#${esc(t)}</button>`).join('')}</div>` : ''}
      <div class="nb-nav-spacer"></div>
      ${scopeButton('trash', 'Trash', 'trash', count((n) => !!n.deleted_at), 'nb-trash-scope')}
    </nav>`;
    // Names are set as text, never as HTML.
    side.querySelectorAll('.nb-place-btn').forEach((button) => {
      const item = button.dataset.nbKind === 'project' ? projectOf(button.dataset.nbId) : folderOf(button.dataset.nbId);
      button.querySelector('.project-folder-name').textContent = (item && item.name) || 'Untitled';
    });
    if (S.deleteMode) decorateDeleteMode(side);
  }
  // Delete mode (shared createDeleteMode, as on the Work Hub): Notes folders
  // and notes wiggle with an X; workspaces stay still -- they belong to Chat
  // and Work Hub too.
  function decorateDeleteMode(side) {
    let index = 0;
    side.querySelectorAll('.nb-place-btn').forEach((tile) => {
      if (tile.dataset.nbKind === 'project') {
        if (typeof window.lockDeleteModeItem === 'function') window.lockDeleteModeItem(tile, 'Workspaces are shared with Chat and Work Hub');
        return;
      }
      const wrap = document.createElement('div');
      wrap.className = 'work-hub-project-delete-wrap';
      tile.replaceWith(wrap);
      wrap.appendChild(tile);
      const folder = folderOf(tile.dataset.nbId);
      if (typeof window.decorateDeleteModeItem === 'function') {
        window.decorateDeleteModeItem(wrap, {label: `Delete ${(folder && folder.name) || 'folder'}`, index: index++, onDelete: () => deleteFolder(tile.dataset.nbId, wrap)});
      }
    });
    side.querySelectorAll('[data-nb-note-row]').forEach((row) => {
      const note = S.notes.find((n) => n.id === row.dataset.nbNoteRow);
      if (typeof window.decorateDeleteModeItem === 'function') {
        window.decorateDeleteModeItem(row, {label: `Move ${(note && note.title) || 'Untitled'} to trash`, index: index++, onDelete: () => trashNote(row.dataset.nbNoteRow, row)});
      }
    });
  }
  let deleteModeRef = null;
  const deleteMode = () => deleteModeRef || (deleteModeRef = window.createDeleteMode({
    isInside: (target) => !!target.closest('#notebookSidebar .work-hub-projects, #notebookSidebar .nb-create-row'),
    onChange: (active) => { S.deleteMode = active; renderSidebar(); },
  }));
  function enterDeleteMode() {
    if (!S.folders.length && !S.notes.some((n) => live(n) && (n.project_id || n.folder_id))) {
      toast('There are no folders or filed notes to delete.');
      return;
    }
    if (typeof window.createDeleteMode !== 'function') return;
    deleteMode().enter();
  }
  function openCreateMenu(button) {
    const old = document.querySelector('.nb-create-menu');
    if (old) { old.remove(); return; }
    const menu = document.createElement('div');
    menu.className = 'work-hub-create-menu nb-create-menu';
    menu.setAttribute('role', 'menu');
    createMenuItems(menu);
    button.parentElement.appendChild(menu);
    const close = (event) => {
      if (menu.contains(event.target) || button.contains(event.target)) return;
      menu.remove(); document.removeEventListener('click', close, true);
    };
    setTimeout(() => document.addEventListener('click', close, true), 0);
  }
  // New note from the + menu: the same menu turns into a "where" picker.
  function showPlacePicker(menu) {
    const item = (value, name, color) => `<button type="button" role="menuitem" class="nb-pick-item" data-nb-pick="${esc(value)}"><span class="color-dot" aria-hidden="true" style="background:${esc(color)}"></span><span class="nb-pick-name">${esc(name)}</span></button>`;
    menu.classList.add('is-picking');
    menu.innerHTML = `<div class="nb-pick-head"><button type="button" class="nb-pick-back" data-nb-pick-back aria-label="Back to the menu">‹</button><span>Add note to</span></div>
      <div class="nb-pick-list">
        ${item('general', 'General', 'var(--muted)')}
        ${S.projects.length ? `<div class="nb-pick-label">Workspaces</div>${S.projects.map((p) => item('p:' + p.project_id, p.name, p.color || 'var(--accent)')).join('')}` : ''}
        ${S.folders.length ? `<div class="nb-pick-label">Folders</div>${S.folders.map((f) => item('f:' + f.id, f.name, f.color || 'var(--muted)')).join('')}` : ''}
      </div>`;
    const first = menu.querySelector('.nb-pick-item');
    if (first) first.focus();
  }
  function createMenuItems(menu) {
    menu.classList.remove('is-picking');
    menu.innerHTML = '<button type="button" role="menuitem" data-nb-create="note">New note</button><button type="button" role="menuitem" data-nb-create="folder">New folder</button><button type="button" role="menuitem" class="is-danger" data-nb-create="delete">Delete</button>';
  }
  // A workspace or folder tile: select it and open/close it without
  // re-rendering the panel, so the open/close transition plays.
  function toggleTile(tile) {
    const key = tile.dataset.nbKey;
    const expanded = !S.expanded[key];
    S.expanded[key] = expanded;
    S.scope = {kind: tile.dataset.nbKind, id: tile.dataset.nbId};
    S.pane = 'list';
    const side = $('notebookSidebar');
    side.querySelectorAll('.nb-place-btn.active, .nb-scope.active').forEach((other) => { if (other !== tile) other.classList.remove('active'); });
    tile.classList.add('active');
    tile.setAttribute('aria-expanded', String(expanded));
    const chevron = tile.querySelector('.work-hub-project-chevron');
    if (chevron) chevron.classList.toggle('expanded', expanded);
    const group = document.getElementById(tile.getAttribute('aria-controls'));
    if (group) { group.classList.toggle('expanded', expanded); group.inert = !expanded; }
    ensureShell();
    renderList();
  }

  // ── rendering: main ─────────────────────────────────────────────────────────
  function ensureShell() {
    const root = $('notebookRoot');
    if (!root) return null;
    if (!root.querySelector('.nb')) {
      root.innerHTML = `<div class="nb" data-pane="list">
        <section class="nb-list" aria-label="Notes">
          <header class="nb-list-head"><h2 id="nbScopeTitle"></h2><button type="button" class="nb-icon-btn" data-nb-action="new" aria-label="New note" title="New note (Alt+N)">${icon('plus', 16)}</button></header>
          <label class="nb-search">${icon('search', 14)}<input id="nbSearch" type="search" placeholder="Search notes" autocomplete="off" spellcheck="false" aria-label="Search notes"></label>
          <div class="nb-list-items" id="nbListItems" role="list"></div>
        </section>
        <section class="nb-editor" aria-label="Note">
          <div class="nb-editor-head" id="nbEditorHead"></div>
          <div class="nb-editor-scroll"><div class="nb-editor-host" id="nbEditorHost"></div></div>
        </section>
      </div>`;
      $('nbSearch').addEventListener('input', onSearchInput);
    }
    root.querySelector('.nb').dataset.pane = S.pane;
    return root;
  }
  let lastListKey = '';
  function renderList() {
    const host = $('nbListItems');
    if (!host) return;
    // Items fade in when the list changes what it shows (scope, search, tag),
    // not on the re-renders an autosave triggers.
    const listKey = [S.scope.kind, S.scope.id, S.search, S.tagFilter, S.loaded].join('|');
    host.classList.toggle('is-entering', listKey !== lastListKey);
    lastListKey = listKey;
    $('nbScopeTitle').textContent = scopeTitle() + (S.tagFilter ? ` · #${S.tagFilter}` : '');
    if (!S.loaded) { host.innerHTML = S.error ? `<div class="nb-empty"><p>${esc(S.error)}</p><button type="button" class="nb-btn" data-nb-action="reload">Try again</button></div>` : '<div class="nb-skeleton"><i></i><i></i><i></i><i></i></div>'; return; }
    const notes = visibleNotes();
    const trash = S.scope.kind === 'trash';
    if (!notes.length) {
      const message = S.search ? `No notes found for “${esc(S.search)}”.`
        : trash ? 'Trash is empty.'
          : S.scope.kind === 'project' || S.scope.kind === 'folder' ? 'No notes here yet.' : 'No notes yet.';
      host.innerHTML = `<div class="nb-empty"><p>${message}</p>${trash || S.search ? '' : '<button type="button" class="nb-btn primary" data-nb-action="new">New note</button>'}</div>`;
      return;
    }
    host.innerHTML = (trash ? '<div class="nb-trash-bar"><span>Notes here are deleted for good when you empty the trash.</span><button type="button" class="nb-btn small" data-nb-action="empty-trash">Empty trash</button></div>' : '')
      + notes.map((n, i) => `<button type="button" role="listitem" class="nb-item${S.note && S.note.id === n.id ? ' active' : ''}" data-nb-open="${esc(n.id)}" style="--i:${Math.min(i, 12)}">
        <span class="nb-item-title">${n.pinned ? `<span class="nb-flag" title="Pinned">${icon('pin', 12)}</span>` : ''}${n.favorite ? `<span class="nb-flag fav" title="Favorite">${icon('star', 12)}</span>` : ''}<strong>${esc(n.title || 'Untitled')}</strong></span>
        ${n.preview ? `<span class="nb-item-preview">${esc(n.preview)}</span>` : ''}
        <span class="nb-item-meta"><span class="nb-place-dot" aria-hidden="true" style="background:${esc(placeColor(n))}"></span><span class="nb-item-meta-text">${esc(placeLabel(n))} · ${esc(when(n.updated_at))}${(n.tags || []).length ? ` · ${n.tags.slice(0, 3).map((t) => '#' + esc(t)).join(' ')}` : ''}</span></span>
      </button>`).join('');
  }
  function statusText() {
    switch (save.status) {
      case 'unsaved': return 'Unsaved';
      case 'saving': return 'Saving…';
      case 'saved': return 'Saved';
      case 'error': return 'Not saved';
      case 'conflict': return 'Changed elsewhere';
      default: return '';
    }
  }
  function placeOptions(note) {
    const current = note.project_id ? 'p:' + note.project_id : note.folder_id ? 'f:' + note.folder_id : 'general';
    const option = (value, label) => `<option value="${esc(value)}"${value === current ? ' selected' : ''}>${esc(label)}</option>`;
    return option('general', 'General')
      + (S.projects.length ? `<optgroup label="Workspaces">${S.projects.map((p) => option('p:' + p.project_id, p.name)).join('')}</optgroup>` : '')
      + (S.folders.length ? `<optgroup label="Folders">${S.folders.map((f) => option('f:' + f.id, f.name)).join('')}</optgroup>` : '');
  }
  let headNoteId = null;
  function renderEditorHead() {
    const head = $('nbEditorHead');
    if (!head) return;
    const note = S.note;
    // The header eases in when a different note opens, not on every re-render.
    const nextId = note ? note.id : null;
    if (nextId && nextId !== headNoteId) {
      head.classList.remove('is-entering'); void head.offsetWidth; head.classList.add('is-entering');
    }
    headNoteId = nextId;
    if (!note) {
      head.innerHTML = S.noteLoading ? '<div class="nb-skeleton head"><i></i><i></i></div>'
        : S.noteError ? `<div class="nb-empty"><p>${esc(S.noteError)}</p></div>`
          : `<div class="nb-empty nb-editor-empty"><p>${S.loaded && !S.notes.some(live) ? 'Create your first note to get started.' : 'Select a note, or start a new one.'}</p><button type="button" class="nb-btn primary" data-nb-action="new">New note</button></div>`;
      return;
    }
    const trashed = !!note.deleted_at;
    const conflict = save.conflict ? `<div class="nb-banner warn" role="alert"><span>${S.vault ? 'This note was changed in Obsidian or another window.' : 'This note was changed in another window.'}</span><button type="button" class="nb-btn small" data-nb-action="conflict-mine">Keep mine</button><button type="button" class="nb-btn small" data-nb-action="conflict-theirs">Load theirs</button></div>` : '';
    const failed = save.status === 'error' ? `<div class="nb-banner" role="status"><span>${esc(save.error || 'Saving failed')}. Your changes are kept here and retried.</span><button type="button" class="nb-btn small" data-nb-action="retry">Retry now</button></div>` : '';
    head.innerHTML = `${trashed ? '<div class="nb-banner"><span>This note is in the trash.</span><button type="button" class="nb-btn small" data-nb-action="restore">Restore</button><button type="button" class="nb-btn small danger" data-nb-action="purge">Delete forever</button></div>' : ''}${conflict}${failed}
      <div class="nb-head-row">
        <button type="button" class="nb-icon-btn nb-back" data-nb-action="back" aria-label="Back to notes">${icon('back', 16)}</button>
        <input id="nbTitle" class="nb-title" type="text" maxlength="240" placeholder="Untitled" aria-label="Note title" ${trashed ? 'disabled' : ''}>
        <span class="nb-status" data-status="${esc(save.status)}" aria-live="polite">${esc(statusText())}</span>
        <button type="button" class="nb-icon-btn" data-nb-action="add-files" aria-label="Add images or files" title="Add images or files" ${trashed ? 'disabled' : ''}>${icon('image', 16)}</button>
        <button type="button" class="nb-icon-btn${note.pinned ? ' on' : ''}" data-nb-action="toggle-pinned" aria-pressed="${note.pinned}" aria-label="${note.pinned ? 'Unpin' : 'Pin'}" title="${note.pinned ? 'Unpin' : 'Pin'}" ${trashed ? 'disabled' : ''}>${icon('pin', 15)}</button>
        <button type="button" class="nb-icon-btn fav${note.favorite ? ' on' : ''}" data-nb-action="toggle-favorite" aria-pressed="${note.favorite}" aria-label="${note.favorite ? 'Remove from favorites' : 'Add to favorites'}" title="Favorite" ${trashed ? 'disabled' : ''}>${icon('star', 15)}</button>
        <button type="button" class="nb-icon-btn" data-nb-action="menu" aria-label="More actions" aria-haspopup="menu" title="More">${icon('more', 16)}</button>
      </div>
      <div class="nb-meta-row">
        <label class="nb-place-select">${icon('folder', 13)}<select id="nbPlace" aria-label="Where this note lives" ${trashed ? 'disabled' : ''}>${placeOptions(note)}</select></label>
        <div class="nb-tags" id="nbTags">${(note.tags || []).map((t) => `<span class="nb-tag-chip">#${esc(t)}<button type="button" data-nb-untag="${esc(t)}" aria-label="Remove tag ${esc(t)}" ${trashed ? 'disabled' : ''}>×</button></span>`).join('')}${trashed ? '' : `<input id="nbTagInput" class="nb-tag-input" type="text" placeholder="${(note.tags || []).length ? '+ tag' : '+ Add tag'}" maxlength="40" aria-label="Add a tag">`}</div>
        <span class="nb-updated">Edited ${esc(when(note.updated_at))}</span>
      </div>`;
    const title = $('nbTitle');
    title.value = note.title || '';
    title.addEventListener('input', () => { note.title = title.value; queueSave('title'); });
    title.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') { event.preventDefault(); if (editorCtl) editorCtl.focus(); }
    });
    const place = $('nbPlace');
    if (place) place.addEventListener('change', () => {
      const v = place.value;
      note.project_id = v.startsWith('p:') ? v.slice(2) : null;
      note.folder_id = v.startsWith('f:') ? v.slice(2) : null;
      queueSave('place', true);
    });
    const tagInput = $('nbTagInput');
    if (tagInput) {
      fitTagInput(tagInput); tagInput.addEventListener('input', () => fitTagInput(tagInput));
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { if (tagInput.isConnected) fitTagInput(tagInput); });
    }
    if (tagInput) tagInput.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ',') return;
      event.preventDefault();
      const tag = tagInput.value.trim().replace(/^#/, '').toLowerCase().replace(/\s+/g, '-');
      if (!tag || (note.tags || []).includes(tag)) { tagInput.value = ''; return; }
      note.tags = [...(note.tags || []), tag];
      queueSave('tags', true);
      renderEditorHead();
      const again = $('nbTagInput'); if (again) again.focus();
    });
  }
  // The tag box is as wide as what it holds: its placeholder, then the text typed.
  let fitCanvas = null;
  function fitTagInput(input) {
    const cs = getComputedStyle(input);
    fitCanvas = fitCanvas || document.createElement('canvas');
    const ctx = fitCanvas.getContext('2d'); if (!ctx) return;
    ctx.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
    const chrome = ['paddingLeft', 'paddingRight', 'borderLeftWidth', 'borderRightWidth'].reduce((sum, k) => sum + (parseFloat(cs[k]) || 0), 0);
    input.style.width = Math.ceil(ctx.measureText(input.value || input.placeholder).width + chrome + 6) + 'px';
  }
  function syncStatus() {
    const el = document.querySelector('#nbEditorHead .nb-status');
    if (!el) return;
    el.dataset.status = save.status;
    el.textContent = statusText();
  }
  function render() {
    renderSidebar();
    if (!ensureShell()) return;
    const search = $('nbSearch');
    if (search && document.activeElement !== search) search.value = S.search;
    renderList();
    renderEditorHead();
  }

  // ── editor ──────────────────────────────────────────────────────────────────
  function moduleUrl() {
    const own = document.querySelector('script[src*="notebook/index.js"]');
    const query = own ? (own.getAttribute('src').split('?')[1] || '') : '';
    return new URL(`static/vendor/blocknote/${EDITOR_VERSION}/blocknote-hermes.js${query ? '?' + query : ''}`, document.baseURI).href;
  }
  function ensureEditorCss() {
    if (document.getElementById('blocknoteCss')) return;
    const link = document.createElement('link');
    link.id = 'blocknoteCss';
    link.rel = 'stylesheet';
    link.href = moduleUrl().replace(/\.js(\?|$)/, '.css$1');
    document.head.appendChild(link);
  }
  const theme = () => (document.documentElement.classList.contains('dark') ? 'dark' : 'light');
  async function loadEditorModule() {
    if (editorModule) return editorModule;
    ensureEditorCss();
    editorModule = await import(moduleUrl());
    if (!themeObserver) {
      themeObserver = new MutationObserver(() => { if (editorCtl) editorCtl.setTheme(theme()); });
      themeObserver.observe(document.documentElement, {attributes: true, attributeFilter: ['class']});
    }
    return editorModule;
  }
  function destroyEditor() {
    if (editorCtl) { try { editorCtl.destroy(); } catch (_) {} }
    editorCtl = null; editorNoteId = null;
    const host = $('nbEditorHost');
    if (host) host.innerHTML = '';
  }
  // Images are sent as they are when the store accepts them; a photo it would
  // refuse (too large, or a HEIC the browser can decode) is redrawn as a JPEG
  // first, so a phone's camera roll works without thinking about formats.
  const STORE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
  const STORE_LIMIT = 7 * 1024 * 1024;
  const MAX_SIDE = 2560;
  async function prepareImage(file) {
    if (STORE_TYPES.includes(file.type) && file.size <= STORE_LIMIT) return file;
    if (file.type === 'image/gif') return file; // redrawing would freeze it; the store reports the size
    try {
      const bitmap = await createImageBitmap(file);
      const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(bitmap.width * scale); canvas.height = Math.round(bitmap.height * scale);
      canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      if (bitmap.close) bitmap.close();
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.86));
      if (blob && blob.size <= STORE_LIMIT) return new File([blob], (file.name || 'image').replace(/\.[^.]+$/, '') + '.jpg', {type: 'image/jpeg'});
    } catch (_) {}
    return file;
  }
  // The "Add images or files" button: the system picker (photo library, camera
  // and Files on a phone), one or many items, each placed under the cursor:
  // images as pictures, documents as a file block that downloads.
  const FILE_ACCEPT = 'image/*,audio/*,video/*,.mp3,.m4a,.wav,.ogg,.flac,.mp4,.mov,.webm,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.zip,.txt,.md,.csv,.json';
  function pickFiles() {
    if (!editorCtl || !S.note || S.note.deleted_at) return;
    document.querySelectorAll('.nb-file-input').forEach((old) => old.remove());
    const input = document.createElement('input');
    input.className = 'nb-file-input';
    input.type = 'file'; input.accept = FILE_ACCEPT; input.multiple = true;
    // Safari drops the change event of a file input that is not in the page.
    input.hidden = true; document.body.appendChild(input);
    input.addEventListener('cancel', () => input.remove());
    input.addEventListener('change', async () => {
      const files = [...input.files]; input.remove(); if (!files.length || !editorCtl) return;
      const editor = editorCtl.editor;
      const noteId = editorNoteId;
      if (!files.some((f) => mediaKind(f.name, f.type))) toast(files.length === 1 ? 'Adding…' : `Adding ${files.length} items…`);
      let anchor = null;
      try { anchor = editor.getTextCursorPosition().block; } catch (_) {}
      if (!anchor) { const doc = editor.document; anchor = doc[doc.length - 1]; }
      let added = 0;
      for (const file of files) {
        if (editorNoteId !== noteId) return; // switched notes while uploading
        try {
          const url = await uploadFile(file);
          const media = mediaKind(file.name, file.type);
          const isImage = !media && (/^image\//.test(file.type) || /\.(png|jpe?g|gif|webp|heic|heif)$/i.test(file.name || ''));
          const name = file.name || (media || (isImage ? 'image' : 'file'));
          const spec = media ? {type: media, props: {url, name}} : isImage ? {type: 'image', props: {url, name, caption: ''}} : {type: 'file', props: {url, name}};
          const [block] = editor.insertBlocks([spec], anchor, 'after');
          anchor = block || anchor; added += 1;
        } catch (_) { /* uploadFile already told the user why */ }
      }
      if (added) toast(added === 1 ? 'Added' : `${added} items added`);
    });
    input.click();
  }
  // Audio and video are too big to send as JSON: the raw file goes up as the
  // request body, with a progress bar (a phone video can take a while).
  const MEDIA_EXT = /\.(mp3|m4a|wav|ogg|flac|weba|mp4|mov|webm)$/i;
  const VIDEO_EXT = /\.(mp4|mov|webm)$/i;
  const mediaKind = (name, type) => /^video\//.test(type || '') || (!/^audio\//.test(type || '') && VIDEO_EXT.test(name || '')) ? 'video'
    : (/^audio\//.test(type || '') || MEDIA_EXT.test(name || '')) ? 'audio' : null;
  function uploadMedia(file) {
    return new Promise((resolve, reject) => {
      const bar = document.createElement('div');
      bar.className = 'nb-upload'; bar.setAttribute('role', 'status');
      bar.innerHTML = '<span></span><i><b></b></i>';
      const label = bar.firstChild, fill = bar.querySelector('b');
      const show = (text, fraction) => { label.textContent = text; fill.style.width = Math.round(fraction * 100) + '%'; };
      show(`Uploading ${file.name}… 0%`, 0);
      document.body.appendChild(bar);
      const xhr = new XMLHttpRequest();
      const query = new URLSearchParams({filename: file.name || 'media', note_id: (S.note && S.note.id) || ''});
      xhr.open('POST', '/api/notebook/uploads/stream?' + query.toString());
      xhr.setRequestHeader('Content-Type', 'application/octet-stream');
      // fetch() gets the CSRF token from the page's global wrapper; XMLHttpRequest
      // does not, and a signed-in server answers its token-less POST with
      // "Session expired - reload the page".
      const csrf = (window.__HERMES_CONFIG__ && window.__HERMES_CONFIG__.csrfToken) || '';
      if (csrf) xhr.setRequestHeader('X-Hermes-CSRF-Token', csrf);
      xhr.upload.onprogress = (event) => { if (event.lengthComputable) show(`Uploading ${file.name}… ${Math.round(event.loaded / event.total * 100)}%`, event.loaded / event.total); };
      const done = () => setTimeout(() => bar.remove(), 400);
      xhr.onload = () => {
        let payload = {};
        try { payload = JSON.parse(xhr.responseText || '{}'); } catch (_) {}
        if (xhr.status >= 200 && xhr.status < 300 && payload.url) { show('Uploaded', 1); done(); resolve(payload); return; }
        bar.remove();
        const error = new Error(payload.error || 'The file could not be uploaded');
        toast(error.message); reject(error);
      };
      xhr.onerror = () => { bar.remove(); const error = new Error('Hermes could not be reached'); toast(error.message); reject(error); };
      xhr.send(file);
    });
  }
  async function uploadFile(file) {
    if (mediaKind(file.name, file.type)) return (await uploadMedia(file)).url;
    if (/^image\//.test(file.type)) file = await prepareImage(file);
    const data = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
    try {
      const result = await window.NotebookApi.upload({filename: file.name, content_base64: data, note_id: S.note && S.note.id});
      return result.url;
    } catch (error) {
      toast(error.message || 'The image could not be uploaded');
      throw error;
    }
  }
  // A clip that will not play says why: the player's own state goes to the server log
  // (the browser's client-event route, a few small fields) and a failure is shown.
  function reportVideo(video) {
    const note = (name) => {
      const e = video.error;
      const reason = `${name} err=${e ? e.code : '-'} net=${video.networkState} rdy=${video.readyState} t=${(video.currentTime || 0).toFixed(1)}/${Number.isFinite(video.duration) ? video.duration.toFixed(1) : video.duration} ${video.videoWidth}x${video.videoHeight} paused=${video.paused} ${(video.currentSrc || '').split('/').pop().slice(-30)}`;
      try { fetch('/api/client-events/log', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({event: 'notes_video', source: name, visibility_state: document.visibilityState, url_path: location.pathname, reason: reason.slice(0, 158)}), keepalive: true}).catch(() => {}); } catch (_) {}
    };
    ['loadedmetadata', 'canplay', 'play', 'playing', 'pause', 'waiting', 'stalled', 'abort', 'error', 'ended'].forEach((name) => video.addEventListener(name, () => {
      note(name);
      if (name === 'error') toast(`This video could not be played (${video.error ? ['', 'aborted', 'network', 'decode', 'format not supported'][video.error.code] || video.error.code : 'error'}).`);
    }));
  }
  // Touch screens have no hover, so the editor's drag handle (the grip that
  // moves a line on desktop) never shows there. On touch a grip sits beside
  // the line holding the cursor, on the right (the left edge belongs to the
  // swipe-for-sidebar guard); drag it with a finger to move the line. The
  // grip cancels pointerdown, so the editor keeps focus and the keyboard.
  // --nb-bar-top: where the format toolbar's top edge goes so its bottom sits
  // on the keyboard. Fixed boxes are laid out against the layout viewport,
  // which iOS pans under the visual viewport as the page scrolls with the
  // keyboard up; the visual viewport's bottom edge (offsetTop + height) is the
  // one stable reference, so the toolbar is placed by `top` from that, with
  // its own height measured, and never from innerHeight. It is re-read every
  // frame while the editor has focus: viewport events arrive late.
  let keyboardTracked = false;
  function trackKeyboard() {
    const vv = window.visualViewport;
    if (keyboardTracked || !vv) return;
    keyboardTracked = true;
    const root = document.documentElement;
    let last = null, raf = 0;
    const read = () => {
      const bar = document.querySelector('.hermes-note-editor .bn-formatting-toolbar');
      const height = bar ? bar.offsetHeight : 0;
      const top = Math.round(vv.offsetTop + vv.height - height);
      if (top !== last) { last = top; root.style.setProperty('--nb-bar-top', top + 'px'); }
    };
    const loop = () => { read(); raf = requestAnimationFrame(loop); };
    const inEditor = (el) => !!(el && el.closest && el.closest('.hermes-note-editor'));
    document.addEventListener('focusin', (event) => { if (inEditor(event.target) && !raf) loop(); });
    document.addEventListener('focusout', () => setTimeout(() => {
      if (!inEditor(document.activeElement)) { cancelAnimationFrame(raf); raf = 0; read(); }
    }, 250));
    vv.addEventListener('resize', read); vv.addEventListener('scroll', read);
    read();
  }
  function mountBlockGrip(host, note) {
    if (note.deleted_at || !window.matchMedia || !window.matchMedia('(hover: none)').matches) return;
    trackKeyboard();
    const mount = host.querySelector('.nb-editor-mount'); if (!mount) return;
    mount.classList.add('has-grip'); host.classList.add('nb-has-grip');
    const grip = document.createElement('button');
    grip.type = 'button'; grip.className = 'nb-grip'; grip.hidden = true;
    grip.setAttribute('aria-label', 'Drag to move this line'); grip.title = 'Drag to move this line';
    grip.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true"><circle cx="9" cy="6" r="1.7"/><circle cx="15" cy="6" r="1.7"/><circle cx="9" cy="12" r="1.7"/><circle cx="15" cy="12" r="1.7"/><circle cx="9" cy="18" r="1.7"/><circle cx="15" cy="18" r="1.7"/></svg>';
    const line = document.createElement('div'); line.className = 'nb-drop-line'; line.hidden = true;
    // BlockNote hides the format toolbar on every pointerdown and, after a
    // touch scroll (which ends in pointercancel, never pointerup), keeps it
    // hidden. A finger scrolling the page is not a selection gesture, so touch
    // pointers never reach BlockNote's listeners; the selection still drives it.
    ['pointerdown', 'pointercancel'].forEach((type) => mount.addEventListener(type, (event) => { if (event.pointerType === 'touch') event.stopPropagation(); }, true));
    host.append(grip, line); // React owns the mount's children, so these sit beside it
    const blockEl = (id) => mount.querySelector(`.bn-block-outer[data-id="${CSS.escape(id)}"]`);
    let current = null; // id of the block holding the cursor
    // The line to hold the grip is read from the DOM selection itself, not from
    // the editor's cursor state, which trails the selection by a beat and (after
    // a line was moved) pointed at the wrong row.
    const place = () => {
      if (!mount.isConnected) return;
      const sel = window.getSelection();
      const node = sel && sel.rangeCount ? sel.anchorNode : null;
      const origin = node && (node.nodeType === 1 ? node : node.parentElement);
      const el = origin && origin.closest ? origin.closest('.bn-block-outer') : null;
      if (!el || !mount.contains(el) || !mount.contains(document.activeElement)) { if (!drag) grip.hidden = true; return; }
      current = el.dataset.id;
      const box = el.querySelector('.bn-block-content') || el;
      const m = host.getBoundingClientRect(), r = box.getBoundingClientRect();
      grip.style.top = (r.top - m.top + Math.max(0, (Math.min(r.height, 30) - 28) / 2)) + 'px';
      grip.hidden = false;
    };
    document.addEventListener('selectionchange', place);
    mount.addEventListener('focusin', place);
    mount.addEventListener('input', () => requestAnimationFrame(place));
    if (window.ResizeObserver) new ResizeObserver(() => requestAnimationFrame(place)).observe(mount); // lines re-flow (images load, a line moved)
    // Where the dragged line would land: before/after the block under the finger.
    let drag = null;
    const targetAt = (y) => {
      let best = null;
      mount.querySelectorAll('.bn-block-outer').forEach((el) => {
        if (drag.el.contains(el)) return;
        const box = (el.querySelector('.bn-block-content') || el).getBoundingClientRect();
        const dist = y < box.top ? box.top - y : (y > box.bottom ? y - box.bottom : 0);
        if (!best || dist < best.dist) best = {el, box, dist, after: y > box.top + box.height / 2};
      });
      return best;
    };
    const scroller = () => { let n = mount.parentElement; while (n && n !== document.body) { const o = getComputedStyle(n).overflowY; if ((o === 'auto' || o === 'scroll') && n.scrollHeight > n.clientHeight) return n; n = n.parentElement; } return document.scrollingElement; };
    const showLine = (t) => {
      if (!t) { line.hidden = true; return; }
      const m = host.getBoundingClientRect();
      line.style.top = ((t.after ? t.box.bottom : t.box.top) - m.top - 1) + 'px';
      line.hidden = false;
    };
    grip.addEventListener('pointerdown', (event) => {
      if (!current || !blockEl(current)) return;
      event.preventDefault();
      drag = {id: current, el: blockEl(current), target: null, y: event.clientY, scroll: 0, raf: 0};
      grip.setPointerCapture(event.pointerId);
      grip.classList.add('dragging'); drag.el.classList.add('nb-block-lifted');
      const tick = () => {
        if (!drag) return;
        const sc = scroller(); const h = window.innerHeight;
        const edge = drag.y < 90 ? -10 : (drag.y > h - 150 ? 10 : 0);
        if (edge && sc) { sc.scrollTop += edge; drag.target = targetAt(drag.y); showLine(drag.target); }
        drag.raf = requestAnimationFrame(tick);
      };
      drag.raf = requestAnimationFrame(tick);
      drag.target = targetAt(event.clientY); showLine(drag.target);
    });
    grip.addEventListener('pointermove', (event) => {
      if (!drag) return;
      drag.y = event.clientY; drag.target = targetAt(event.clientY); showLine(drag.target);
      const m = host.getBoundingClientRect(); grip.style.top = (event.clientY - m.top - 14) + 'px';
    });
    const finish = (commit) => {
      if (!drag) return;
      const d = drag; drag = null;
      cancelAnimationFrame(d.raf); grip.classList.remove('dragging'); d.el.classList.remove('nb-block-lifted'); line.hidden = true;
      const editor = editorCtl && editorCtl.editor;
      const targetId = d.target && d.target.el.dataset.id;
      if (commit && editor && targetId && targetId !== d.id) {
        try {
          const block = editor.getBlock(d.id);
          const move = (b) => { const {id, children, ...rest} = b; return Object.assign({}, rest, {children: (children || []).map(move)}); };
          const copy = move(block);
          editor.removeBlocks([d.id]);
          const [moved] = editor.insertBlocks([copy], targetId, d.target.after ? 'after' : 'before');
          if (moved) editor.setTextCursorPosition(moved, 'end');
        } catch (_) {}
      }
      if (editor) editor.focus();
      requestAnimationFrame(place); setTimeout(place, 120);
    };
    grip.addEventListener('pointerup', () => finish(true));
    grip.addEventListener('pointercancel', () => finish(false));
    grip.addEventListener('contextmenu', (event) => event.preventDefault());
  }
  // A tapped or clicked picture gets an outline in the theme's accent colour.
  // On a touch screen the resize bars (BlockNote's own, which save the size as the
  // block's previewWidth) stay hidden until the already-selected picture is tapped
  // again, and then stay put -- BlockNote itself hides them whenever the pointer
  // leaves, and rebuilds them (hidden) every time a resize is saved. The outline
  // follows the picture while it grows or shrinks.
  function mountImageOutline(host, note) {
    const mount = host.querySelector('.nb-editor-mount'); if (!mount) return;
    // A tap on a clip or recording belongs to the player. If it reaches the editor,
    // ProseMirror selects the block, focuses the editor and re-renders around the
    // player, and on iOS that first tap never reached the play button, so playing
    // took two. It must be stopped on the way UP, after the player (whose controls
    // are listeners inside the element) has had it: stopping it on the way down
    // starved the controls and the clip could not be played at all.
    const isolate = () => mount.querySelectorAll('.bn-file-block-content-wrapper').forEach((box) => {
      if (box.__nbIsolated || !box.querySelector('video, audio')) return;
      box.__nbIsolated = true;
      ['pointerdown', 'mousedown', 'touchstart', 'click'].forEach((type) => box.addEventListener(type, (event) => {
        if (event.target && /^(VIDEO|AUDIO)$/.test(event.target.tagName)) event.stopPropagation();
      }));
    });
    // iOS draws a clip as a black box until it is played unless it has been told to
    // fetch the start (preload) and is asked for a frame (#t=0.001); playsinline keeps
    // it in the page. DOM only: the saved address is untouched.
    const prepare = () => mount.querySelectorAll('video').forEach((video) => {
      if (video.__nbPrepared && video.isConnected) return;
      video.__nbPrepared = true;
      video.setAttribute('playsinline', ''); video.setAttribute('webkit-playsinline', '');
      video.preload = 'metadata';
      const src = video.getAttribute('src') || '';
      if (src && !/#/.test(src)) video.setAttribute('src', src + '#t=0.001');
      reportVideo(video);
    });
    const tidy = () => { isolate(); prepare(); };
    tidy();
    new MutationObserver(tidy).observe(mount, {childList: true, subtree: true});
    host.classList.add('nb-has-grip'); // the outline is positioned against the host
    const box = document.createElement('div');
    box.className = 'nb-img-outline'; box.hidden = true;
    host.appendChild(box);
    let img = null, watch = null, blockId = null, resizing = false;
    const observe = (el) => {
      if (watch) watch.disconnect();
      if (window.ResizeObserver) { watch = new ResizeObserver(fit); watch.observe(el); } // every frame of a resize
    };
    const markBars = () => {
      mount.querySelectorAll('.bn-resize-handle[data-nb-on]').forEach((h) => { if (!resizing || !h.closest(`.bn-block-outer[data-id="${CSS.escape(blockId || '')}"]`)) h.removeAttribute('data-nb-on'); });
      if (resizing && blockId) mount.querySelectorAll(`.bn-block-outer[data-id="${CSS.escape(blockId)}"] .bn-resize-handle`).forEach((h) => h.setAttribute('data-nb-on', ''));
    };
    function fit() {
      if (img && !img.isConnected && blockId) { // the block re-rendered (a resize is saved): same picture, new element
        const again = mount.querySelector(`.bn-block-outer[data-id="${CSS.escape(blockId)}"] .bn-visual-media`);
        if (again) { img = again; observe(again); }
      }
      if (!img || !img.isConnected) { box.hidden = true; img = null; resizing = false; markBars(); return; }
      const m = host.getBoundingClientRect(), r = img.getBoundingClientRect();
      box.style.cssText = `left:${r.left - m.left}px;top:${r.top - m.top}px;width:${r.width}px;height:${r.height}px`;
      box.hidden = false;
      markBars();
    }
    const clear = () => { img = null; blockId = null; resizing = false; box.hidden = true; if (watch) watch.disconnect(); markBars(); };
    // One tap handler for both ways a tap can arrive. On a phone a quick second tap
    // on a picture starts iOS's own text/image selection, which can swallow the
    // click; the pointer events still arrive, so a tap is read from them, and the
    // click that follows (or the click of a mouse) is ignored as a duplicate.
    let lastTapAt = 0, lastHitAt = 0, skipClick = false, down = null;
    const tap = (target) => {
      if (!mount.isConnected) return;
      const hit = target.closest && target.closest('.bn-visual-media');
      if (hit && mount.contains(hit)) {
        // Tapping the picture that is already selected switches the bars on (and off).
        // "Already selected" is the same block, not the same element: the editor
        // re-renders a tapped picture a moment later. A clip's taps also play and
        // pause it, so only a quick pair counts as the double tap for the bars.
        const id = (hit.closest('.bn-block-outer') || {dataset: {}}).dataset.id || null;
        const now = Date.now(), quick = now - lastHitAt < 450;
        resizing = !!id && id === blockId ? (hit.tagName === 'VIDEO' && !quick ? resizing : !resizing) : false;
        lastHitAt = now;
        img = hit; blockId = id;
        fit(); observe(hit);
      } else if (!(target.closest && target.closest('.bn-resize-handle'))) clear();
    };
    document.addEventListener('pointerdown', (event) => { down = {x: event.clientX, y: event.clientY, target: event.target}; }, true);
    document.addEventListener('pointerup', (event) => {
      const start = down; down = null;
      if (!start || Math.hypot(event.clientX - start.x, event.clientY - start.y) > 10) return; // a drag or a scroll, not a tap
      if (!(start.target.closest && start.target.closest('.bn-visual-media')) && event.pointerType !== 'touch') return; // a mouse click arrives as a click
      lastTapAt = Date.now(); skipClick = true;
      tap(event.target);
    }, true);
    document.addEventListener('click', (event) => {
      const duplicate = skipClick && Date.now() - lastTapAt < 700; // the click that follows a tap already read from its pointer events
      skipClick = false;
      if (!duplicate) tap(event.target);
    });
    // While a resize bar is held the picture must follow the finger exactly: the
    // ease that smooths a release (or a programmatic change) would chase it a
    // beat behind and make it feel rubbery. html.nb-img-dragging switches it off.
    const root = document.documentElement;
    const grab = (event) => { if (event.target.closest && event.target.closest('.bn-resize-handle')) root.classList.add('nb-img-dragging'); };
    // A resize ends with the picture let go of: no outline, no bars, no selection
    // left over (it was still "highlighted" afterwards, and the leftover bars made
    // the next attempt feel stuck). A cancelled touch (iOS takes the finger for a
    // scroll) is passed on to the editor as a touchend, because it only listens
    // for that and would otherwise stay mid-resize.
    const release = (event) => {
      if (!root.classList.contains('nb-img-dragging')) return;
      root.classList.remove('nb-img-dragging');
      if (event && event.type === 'touchcancel') {
        const end = new Event('touchend', {bubbles: true});
        Object.assign(end, {touches: [], targetTouches: [], changedTouches: []}); // the page's other touch handlers read these
        document.dispatchEvent(end);
      }
      setTimeout(() => {
        clear();
        const sel = window.getSelection && window.getSelection();
        if (sel && sel.removeAllRanges && mount.contains(sel.anchorNode)) sel.removeAllRanges();
      }, 120); // after the editor has saved the new width and re-rendered
    };
    ['touchstart', 'mousedown'].forEach((type) => document.addEventListener(type, grab, {capture: true, passive: true}));
    ['touchend', 'touchcancel', 'mouseup'].forEach((type) => document.addEventListener(type, release, true));
    window.addEventListener('blur', () => release(null));
    // A press anywhere but on a bar while a drag is somehow still marked: it is over.
    document.addEventListener('pointerdown', (event) => { if (root.classList.contains('nb-img-dragging') && !(event.target.closest && event.target.closest('.bn-resize-handle'))) release(null); }, true);
    if (window.ResizeObserver) new ResizeObserver(() => requestAnimationFrame(fit)).observe(mount);
    new MutationObserver(() => requestAnimationFrame(fit)).observe(mount, {childList: true, subtree: true});
    mount.addEventListener('load', () => requestAnimationFrame(fit), true);
  }
  // A vault note is Markdown, which has no width for a picture; Obsidian's way is
  // "![caption|300](url)". These carry previewWidth through that spelling.
  const imageBlocks = (blocks, out = []) => { (blocks || []).forEach((b) => { if (b.type === 'image') out.push(b); imageBlocks(b.children, out); }); return out; };
  function editorMarkdown() {
    let md = editorCtl.toMarkdown();
    // The editor writes an audio block as an <audio> tag; Obsidian (and the vault's
    // own Markdown) spells audio and video alike, as an embed link.
    const names = {};
    const blocks = editorCtl.getBlocks();
    const walk = (list) => (list || []).forEach((b) => { if (b.type === 'audio' && b.props.url) names[b.props.url] = b.props.name || 'audio'; walk(b.children); });
    walk(blocks);
    md = md.replace(/<audio src="([^"]*)" controls><\/audio>/g, (all, url) => `![${names[url] || 'audio'}](${url})`);
    let tagFrom = 0;
    const tagged = (list) => (list || []).forEach((b) => {
      if ((b.type === 'video' || b.type === 'audio') && b.props.url && mediaTags.has(b.props.url)) {
        const at = md.indexOf('](' + b.props.url + ')', tagFrom);
        if (at >= 0) { const end = at + 2 + b.props.url.length; md = md.slice(0, end) + mediaTags.get(b.props.url) + md.slice(end); tagFrom = end; }
      }
      tagged(b.children);
    });
    tagged(blocks);
    let from = 0;
    imageBlocks(editorCtl.getBlocks()).forEach((b) => {
      if (!b.props.url) return;
      const at = md.indexOf('](' + b.props.url + ')', from);
      if (at < 0) return;
      const open = md.lastIndexOf('![', at);
      if (open < from) return;
      from = at + 1;
      if (!b.props.previewWidth) return;
      const caption = md.slice(open + 2, at).replace(/\|\d+$/, '');
      md = md.slice(0, open + 2) + caption + '|' + Math.round(b.props.previewWidth) + md.slice(at);
      from += String(Math.round(b.props.previewWidth)).length + 1;
    });
    return md;
  }
  // Parsed Markdown reads an embedded recording or clip as a picture; the file's
  // extension says what it really is.
  const mediaTags = new Map(); // media url -> the "#hermes-src=..." tag the server added
  function withMediaBlocks(blocks) {
    (blocks || []).forEach((b) => {
      if (b.type === 'image') {
        let path = b.props.url || '';
        try { path = decodeURIComponent((new URL(path, location.origin).searchParams.get('path')) || path); } catch (_) {}
        const kind = mediaKind(path, '') || mediaKind(b.props.name || '', '');
        if (kind) {
          // The server tags a vault link with "#hermes-src=<its original spelling>" so a save can
          // restore it. That is no part of a media address (Safari is strict about what follows
          // a media URL's #), so it is kept aside and put back when the note is written.
          const at = b.props.url.indexOf('#hermes-src=');
          let url = b.props.url;
          if (at >= 0) { url = b.props.url.slice(0, at); mediaTags.set(url, b.props.url.slice(at)); }
          b.type = kind; b.props = {url, name: b.props.name || path.split('/').pop()};
        }
      }
      withMediaBlocks(b.children);
    });
    return blocks;
  }
  function withImageWidths(blocks) {
    // Parsed Markdown puts a picture's alt text in `name` ("shot.png|300").
    imageBlocks(blocks).forEach((b) => {
      const m = /^(.*)\|(\d+)$/.exec(b.props.name || '');
      if (m) { b.props.name = m[1]; b.props.previewWidth = Number(m[2]); }
    });
    return blocks;
  }
  async function mountEditor(note, content) {
    const host = $('nbEditorHost');
    if (!host) return;
    let mod;
    try { mod = await loadEditorModule(); } catch (error) {
      host.innerHTML = `<div class="nb-empty"><p>The editor could not load (${esc(String(error && error.message || error).slice(0, 120))}).</p></div>`;
      return;
    }
    if (!S.note || S.note.id !== note.id) return; // switched away while loading
    destroyEditor();
    const mountPoint = document.createElement('div');
    mountPoint.className = 'nb-editor-mount';
    host.appendChild(mountPoint);
    // A vault note arrives as Markdown: the editor parses it once mounted, and
    // the changes that parse makes are not edits (the file is only written
    // when the user changes something).
    const fromMarkdown = note.format === 'markdown' && !(Array.isArray(content) && content.length);
    let settling = fromMarkdown;
    let baseline = null; // the loaded note as the editor writes it back
    editorCtl = mod.mountNoteEditor(mountPoint, {
      content: fromMarkdown ? [] : content,
      theme: theme(),
      editable: !note.deleted_at,
      placeholder: "Write, or type '/' for commands",
      uploadFile,
      onChange: () => {
        if (settling || editorNoteId !== note.id) return;
        if (baseline !== null) {
          // Re-rendering the parsed note is not an edit: only a real change is.
          try { if (editorMarkdown() === baseline) return; } catch (_) {}
          baseline = null;
        }
        queueSave('content');
      },
    });
    editorNoteId = note.id;
    mountBlockGrip(host, note);
    mountImageOutline(host, note);
    if (fromMarkdown) {
      try {
        const blocks = withMediaBlocks(withImageWidths(await Promise.resolve(editorCtl.parseMarkdown(note.markdown || ''))));
        if (editorNoteId === note.id && Array.isArray(blocks) && blocks.length) editorCtl.replaceAll(blocks);
        baseline = editorMarkdown();
      } catch (error) {
        toast('This note could not be read as Markdown');
      }
      setTimeout(() => { settling = false; }, 0);
    }
  }

  // ── saving ──────────────────────────────────────────────────────────────────
  function setStatus(status, error) {
    save.status = status; save.error = error || '';
    syncStatus();
  }
  function writeDraft() {
    const note = S.note;
    if (!note || !Object.keys(save.dirty).length) return;
    try {
      localStorage.setItem(DRAFT_KEY(note.id), JSON.stringify({
        base_revision: note.revision, title: note.title,
        content: editorCtl && editorNoteId === note.id ? editorCtl.getBlocks() : undefined,
        dirty: Object.keys(save.dirty), at: Date.now(),
      }));
    } catch (_) {}
  }
  function clearDraft(noteId) { try { localStorage.removeItem(DRAFT_KEY(noteId)); } catch (_) {} }
  function readDraft(noteId) {
    try { return JSON.parse(localStorage.getItem(DRAFT_KEY(noteId)) || 'null'); } catch (_) { return null; }
  }
  function queueSave(field, immediate) {
    if (!S.note || S.note.deleted_at) return;
    save.dirty[field] = true;
    setStatus('unsaved');
    writeDraft();
    clearTimeout(save.timer);
    save.timer = setTimeout(runSave, immediate ? 0 : SAVE_DELAY_MS);
  }
  function payloadFor(note, fields) {
    const body = {expected_revision: note.revision};
    if (fields.title) body.title = note.title || '';
    if (fields.content && editorCtl && editorNoteId === note.id) {
      // A vault note is saved as Markdown (its file); Hermes' own as blocks.
      if (note.format === 'markdown') body.markdown = editorMarkdown();
      else body.content = editorCtl.getBlocks();
    }
    if (fields.tags) body.tags = note.tags || [];
    if (fields.place) { body.project_id = note.project_id || null; body.folder_id = note.folder_id || null; body.view = S.side; }
    ['pinned', 'favorite', 'archived'].forEach((flag) => { if (fields[flag]) body[flag] = !!note[flag]; });
    return body;
  }
  async function runSave() {
    clearTimeout(save.timer);
    const note = S.note;
    if (!note || !Object.keys(save.dirty).length) return;
    if (save.inflight) { save.again = true; return save.inflight; }
    const sending = save.dirty;
    save.dirty = {};
    const body = payloadFor(note, sending);
    setStatus('saving');
    save.inflight = (async () => {
      try {
        const result = await window.NotebookApi.update(note.id, body);
        if (S.note && S.note.id === note.id) {
          note.revision = result.note.revision;
          note.updated_at = result.note.updated_at;
          note.preview = result.note.preview;
        }
        upsertSummary(result.note);
        if (!Object.keys(save.dirty).length) clearDraft(note.id);
        clearTimeout(save.retry);
        setStatus(Object.keys(save.dirty).length ? 'unsaved' : 'saved');
        renderSidebar(); renderList();
      } catch (error) {
        // Put the fields back so nothing is lost; newer edits merge on top.
        save.dirty = Object.assign({}, sending, save.dirty);
        writeDraft();
        if (error.status === 409 && error.payload && error.payload.note) {
          save.conflict = error.payload.note;
          setStatus('conflict');
          renderEditorHead();
        } else {
          setStatus('error', error.message || 'Saving failed');
          renderEditorHead();
          clearTimeout(save.retry);
          save.retry = setTimeout(runSave, RETRY_MS);
        }
      } finally {
        save.inflight = null;
      }
      if (save.again && !save.conflict) { save.again = false; await runSave(); }
    })();
    return save.inflight;
  }
  // Before leaving a note: send what is pending and wait for it.
  async function flushSave() {
    clearTimeout(save.timer);
    if (save.inflight) await save.inflight;
    if (Object.keys(save.dirty).length && !save.conflict) await runSave();
  }

  // ── actions ─────────────────────────────────────────────────────────────────
  async function openNote(noteId, opts) {
    if (S.note && S.note.id === noteId && !(opts && opts.force)) { S.pane = 'editor'; ensureShell(); return; }
    await flushSave();
    save.dirty = {}; save.conflict = null; clearTimeout(save.retry); setStatus('idle');
    S.noteLoading = true; S.noteError = ''; S.pane = 'editor';
    destroyEditor();
    S.note = null;
    render();
    try {
      const {note} = await window.NotebookApi.get(noteId);
      if (S.side === 'vault' && isVaultNote(note)) Object.assign(note, asVaultView(note));
      S.note = note;
      try { localStorage.setItem(LAST_KEY, noteId); } catch (_) {}
      let content = note.content;
      const draft = readDraft(noteId);
      if (draft && draft.base_revision === note.revision && !note.deleted_at) {
        // Unsaved changes from a failed save or a closed tab: bring them back.
        if (draft.title !== undefined) note.title = draft.title;
        if (Array.isArray(draft.content)) content = draft.content;
        (draft.dirty || []).forEach((f) => { save.dirty[f] = true; });
        toast('Restored unsaved changes');
      } else if (draft) {
        clearDraft(noteId);
      }
      S.noteLoading = false;
      render();
      await mountEditor(note, content);
      if (Object.keys(save.dirty).length) queueSave('content', true);
    } catch (error) {
      S.noteLoading = false;
      S.noteError = error.status === 404 ? 'This note no longer exists.' : (error.message || 'The note could not be loaded');
      render();
    }
  }
  // A new note's list item and side-panel row get the shared arrival glow.
  function arrive(noteId) {
    if (typeof window.markArrival !== 'function') return;
    document.querySelectorAll(`.nb-item[data-nb-open="${CSS.escape(noteId)}"], #notebookSidebar [data-nb-note-row="${CSS.escape(noteId)}"]`).forEach((el) => window.markArrival(el));
  }
  async function newNote(extra) {
    await flushSave();
    try {
      const {note} = await window.NotebookApi.create(Object.assign({title: ''}, placeForScope(), extra || {}));
      upsertSummary(note); sortNotes();
      if (S.scope.kind === 'trash' || S.scope.kind === 'pinned' || S.scope.kind === 'favorites') S.scope = {kind: S.side === 'vault' ? 'all' : 'general', id: null};
      const key = note.project_id ? 'project:' + note.project_id : note.folder_id ? 'folder:' + note.folder_id : null;
      if (key) S.expanded[key] = true;
      await openNote(note.id, {force: true});
      const title = $('nbTitle'); if (title) title.focus();
      arrive(note.id);
      return note;
    } catch (error) { toast(error.message || 'The note could not be created'); return null; }
  }
  async function setFlag(flag) {
    if (!S.note) return;
    S.note[flag] = !S.note[flag];
    upsertSummary(Object.assign({}, S.note)); sortNotes();
    queueSave(flag, true);
    render();
  }
  async function trashCurrent() {
    const note = S.note; if (!note) return;
    const item = document.querySelector(`.nb-item[data-nb-open="${CSS.escape(note.id)}"]`);
    await trashNote(note.id, item);
  }
  async function restoreCurrent() {
    const note = S.note; if (!note) return;
    try {
      const result = await window.NotebookApi.restore(note.id);
      upsertSummary(result.note); sortNotes();
      await openNote(note.id, {force: true});
      toast('Note restored');
    } catch (error) { toast(error.message || 'Could not restore the note'); }
  }
  async function purgeCurrent() {
    const note = S.note; if (!note) return;
    const ok = typeof window.showConfirmDialog === 'function'
      ? await window.showConfirmDialog({title: 'Delete forever?', message: `“${note.title || 'Untitled'}” and its images will be deleted. This can't be undone.`, confirmLabel: 'Delete forever', danger: true})
      : window.confirm('Delete this note forever?');
    if (!ok) return;
    try {
      await window.NotebookApi.purge(note.id);
      S.notes = S.notes.filter((n) => n.id !== note.id);
      destroyEditor(); S.note = null; S.pane = 'list';
      render();
    } catch (error) { toast(error.message || 'Could not delete the note'); }
  }
  async function emptyTrash() {
    const n = S.notes.filter((x) => x.deleted_at).length;
    if (!n) return;
    const ok = typeof window.showConfirmDialog === 'function'
      ? await window.showConfirmDialog({title: 'Empty trash?', message: `${n} note${n === 1 ? '' : 's'} will be deleted for good.`, confirmLabel: 'Empty trash', danger: true})
      : window.confirm('Empty trash?');
    if (!ok) return;
    try {
      await window.NotebookApi.emptyTrash(S.side);
      S.notes = S.notes.filter((x) => !x.deleted_at);
      if (S.note && S.note.deleted_at) { destroyEditor(); S.note = null; }
      render();
    } catch (error) { toast(error.message || 'Could not empty the trash'); }
  }
  async function duplicateCurrent() {
    const note = S.note; if (!note) return;
    await flushSave();
    try {
      const result = await window.NotebookApi.duplicate(note.id);
      upsertSummary(result.note); sortNotes();
      await openNote(result.note.id, {force: true});
    } catch (error) { toast(error.message || 'Could not duplicate the note'); }
  }
  function download(name, type, text) {
    const url = URL.createObjectURL(new Blob([text], {type}));
    const a = document.createElement('a');
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const fileBase = (note) => (note.title || 'untitled').replace(/[^A-Za-z0-9 _-]+/g, '').trim().replace(/\s+/g, '-').slice(0, 60) || 'note';
  function exportCurrent(format) {
    const note = S.note; if (!note || !editorCtl) return;
    const title = note.title || 'Untitled';
    if (format === 'md') download(fileBase(note) + '.md', 'text/markdown', `# ${title}\n\n` + editorCtl.toMarkdown());
    else if (format === 'html') {
      const titleHtml = esc(title);
      download(fileBase(note) + '.html', 'text/html', `<!doctype html><html><head><meta charset="utf-8"><title>${titleHtml}</title></head><body><h1>${titleHtml}</h1>${editorCtl.toHTML()}</body></html>`);
    } else download(fileBase(note) + '.json', 'application/json', JSON.stringify({title, tags: note.tags || [], content: editorCtl.getBlocks()}, null, 2));
  }
  // Hermes integration: hand the note to a fresh chat. The text is placed in
  // the composer, not sent -- the user picks the agent/model and sends it, so
  // the note goes through the normal chat orchestration.
  async function sendToChat() {
    const note = S.note; if (!note || !editorCtl) return;
    await flushSave();
    const text = `Note: ${note.title || 'Untitled'}${note.project_id ? ` (workspace: ${placeLabel(note)})` : ''}\n\n${editorCtl.toMarkdown()}`;
    if (typeof window.switchPanel === 'function') await window.switchPanel('chat');
    if (typeof window._currentSessionIsReusableEmptyChat === 'function' && !window._currentSessionIsReusableEmptyChat()
        && typeof window.newSession === 'function') {
      await window.newSession();
      if (typeof window.renderSessionList === 'function') await window.renderSessionList();
    }
    const box = document.getElementById('msg');
    if (!box) return;
    box.value = text;
    box.dispatchEvent(new Event('input', {bubbles: true}));
    box.focus();
  }
  function importMarkdown() {
    const picker = document.createElement('input');
    picker.type = 'file'; picker.accept = '.md,.markdown,.txt,text/markdown,text/plain';
    picker.onchange = async () => {
      const file = picker.files && picker.files[0];
      if (!file) return;
      if (file.size > 2 * 1024 * 1024) { toast('That file is too large to import (2 MB limit)'); return; }
      const text = await file.text();
      const note = await newNote({title: file.name.replace(/\.(md|markdown|txt)$/i, '').slice(0, 240)});
      if (!note || !editorCtl) return;
      editorCtl.replaceAll(editorCtl.parseMarkdown(text));
    };
    picker.click();
  }
  function openMenu(anchor, items) {
    document.querySelectorAll('.nb-menu').forEach((m) => m.remove());
    const menu = document.createElement('div');
    menu.className = 'nb-menu';
    menu.setAttribute('role', 'menu');
    items.forEach((item) => {
      if (item === '-') { menu.appendChild(Object.assign(document.createElement('hr'), {className: 'nb-menu-sep'})); return; }
      const b = document.createElement('button');
      b.type = 'button'; b.setAttribute('role', 'menuitem');
      b.className = 'nb-menu-item' + (item.danger ? ' danger' : '');
      b.textContent = item.label;
      b.onclick = () => { close(); item.run(); };
      menu.appendChild(b);
    });
    document.body.appendChild(menu);
    const r = anchor.getBoundingClientRect();
    const width = menu.offsetWidth;
    menu.style.left = Math.max(8, Math.min(window.innerWidth - width - 8, r.right - width)) + 'px';
    menu.style.top = Math.min(window.innerHeight - menu.offsetHeight - 8, r.bottom + 4) + 'px';
    const first = menu.querySelector('button'); if (first) first.focus();
    function close() { menu.remove(); document.removeEventListener('mousedown', outside, true); document.removeEventListener('keydown', keys, true); anchor.focus(); }
    function outside(event) { if (!menu.contains(event.target)) close(); }
    function keys(event) {
      const buttons = [...menu.querySelectorAll('button')];
      const i = buttons.indexOf(document.activeElement);
      if (event.key === 'Escape') { event.preventDefault(); close(); }
      else if (event.key === 'ArrowDown') { event.preventDefault(); buttons[(i + 1) % buttons.length].focus(); }
      else if (event.key === 'ArrowUp') { event.preventDefault(); buttons[(i - 1 + buttons.length) % buttons.length].focus(); }
    }
    setTimeout(() => { document.addEventListener('mousedown', outside, true); document.addEventListener('keydown', keys, true); }, 0);
  }
  function noteMenu(anchor) {
    const note = S.note; if (!note) return;
    if (note.deleted_at) {
      openMenu(anchor, [{label: 'Restore', run: restoreCurrent}, {label: 'Delete forever', danger: true, run: purgeCurrent}]);
      return;
    }
    openMenu(anchor, [
      {label: 'Send to chat', run: sendToChat},
      {label: 'Duplicate', run: duplicateCurrent},
      {label: note.archived ? 'Unarchive' : 'Archive (hide from All notes)', run: () => setFlag('archived')},
      '-',
      {label: 'Export as Markdown', run: () => exportCurrent('md')},
      {label: 'Export as HTML', run: () => exportCurrent('html')},
      {label: 'Export as JSON', run: () => exportCurrent('json')},
      {label: 'Import Markdown as a new note', run: importMarkdown},
      '-',
      {label: 'Move to trash', danger: true, run: trashCurrent},
    ]);
  }
  async function newFolder() {
    const name = typeof window.showPromptDialog === 'function'
      ? await window.showPromptDialog({title: 'New folder', message: 'Folders you create here appear only on the Notes page.', placeholder: 'Folder name', confirmLabel: 'Create'})
      : window.prompt('Folder name');
    if (!name || !name.trim()) return;
    try {
      const {folder} = await window.NotebookApi.createFolder(name.trim(), S.side);
      if (S.vault && S.side === 'notes') {
        // It is also a folder on the Obsidian side (03 Resources / <name>).
        W.vault.folders.push(Object.assign({}, folder, {name: folder.path.split('/').join(' / ')}));
      }
      S.folders.push(folder);
      S.scope = {kind: 'folder', id: folder.id};
      render();
      const tile = document.querySelector(`#notebookSidebar .nb-place-btn[data-nb-key="folder:${CSS.escape(folder.id)}"]`);
      if (tile && typeof window.markArrival === 'function') window.markArrival(tile);
    } catch (error) { toast(error.message || 'Could not create the folder'); }
  }
  async function deleteFolder(folderId, el) {
    const folder = folderOf(folderId); if (!folder) return;
    const n = S.notes.filter((x) => x.folder_id === folderId && live(x)).length;
    const ok = typeof window.showConfirmDialog === 'function'
      ? await window.showConfirmDialog({title: 'Delete folder?', message: S.vault
        ? (n ? 'It still has notes in your vault: only an empty folder can be deleted.' : 'The empty folder is removed from your vault.')
        : n ? `Its ${n} note${n === 1 ? '' : 's'} will move to General.` : 'The folder is empty.', confirmLabel: 'Delete folder', danger: true})
      : window.confirm('Delete folder?');
    if (!ok) return;
    try {
      await window.NotebookApi.deleteFolder(folderId);
      if (el && typeof window.animateRemoval === 'function') await window.animateRemoval(el);
      S.folders = S.folders.filter((f) => f.id !== folderId);
      S.notes.forEach((x) => { if (x.folder_id === folderId) x.folder_id = null; });
      if (S.note && S.note.folder_id === folderId) S.note.folder_id = null;
      if (S.scope.kind === 'folder' && S.scope.id === folderId) S.scope = {kind: 'general', id: null};
      if (S.deleteMode && !S.folders.length && !S.notes.some((x) => live(x) && (x.project_id || x.folder_id)) && deleteModeRef) deleteModeRef.exit();
      render();
    } catch (error) { toast(error.message || 'Could not delete the folder'); }
  }
  // Move any note to the trash (it can be restored from Trash).
  async function trashNote(noteId, el) {
    if (S.note && S.note.id === noteId) await flushSave();
    try {
      const result = await window.NotebookApi.trash(noteId);
      if (el && typeof window.animateRemoval === 'function') await window.animateRemoval(el);
      upsertSummary(result.note);
      clearDraft(noteId);
      if (S.note && S.note.id === noteId) { destroyEditor(); S.note = null; S.pane = 'list'; }
      render();
      toast('Moved to trash');
    } catch (error) { toast(error.message || 'Could not move the note to the trash'); }
  }
  async function renameFolder(folderId) {
    const folder = folderOf(folderId); if (!folder) return;
    const name = typeof window.showPromptDialog === 'function'
      ? await window.showPromptDialog({title: 'Rename folder', value: folder.name, confirmLabel: 'Rename'})
      : window.prompt('Folder name', folder.name);
    if (!name || !name.trim()) return;
    try { const result = await window.NotebookApi.renameFolder(folderId, name.trim()); Object.assign(folder, result.folder); renderSidebar(); }
    catch (error) { toast(error.message || 'Could not rename the folder'); }
  }
  // Right-click on a folder tile: the less frequent folder actions.
  function folderMenu(anchor, folderId) {
    if (!folderOf(folderId)) return;
    openMenu(anchor, [
      {label: 'New note here', run: async () => { S.scope = {kind: 'folder', id: folderId}; await newNote(); }},
      {label: 'Rename', run: () => renameFolder(folderId)},
      {label: 'Delete folder', danger: true, run: () => deleteFolder(folderId, anchor)},
    ]);
  }
  async function resolveConflict(keepMine) {
    const theirs = save.conflict; if (!theirs || !S.note) return;
    save.conflict = null;
    if (keepMine) {
      S.note.revision = theirs.revision; // overwrite on top of their version
      setStatus('unsaved');
      await runSave();
      renderEditorHead();
    } else {
      save.dirty = {}; clearDraft(theirs.id);
      await openNote(theirs.id, {force: true});
    }
  }

  // ── search ──────────────────────────────────────────────────────────────────
  function onSearchInput(event) {
    S.search = event.target.value;
    clearTimeout(searchTimer);
    if (!S.search.trim()) { S.searchResults = null; renderList(); return; }
    searchTimer = setTimeout(async () => {
      const seq = ++S.searchSeq;
      try {
        const {notes} = await window.NotebookApi.search(S.search, S.scope.kind === 'trash', S.side);
        if (seq !== S.searchSeq) return;
        S.searchResults = S.side === 'vault' ? notes.map(asVaultView) : notes;
      } catch (error) {
        if (seq !== S.searchSeq) return;
        S.searchResults = [];
        toast(error.message || 'Search failed');
      }
      renderList();
    }, 180);
  }

  // ── events ──────────────────────────────────────────────────────────────────
  async function onClick(event) {
    const t = event.target;
    if (t.closest('.dm-x')) return; // delete-mode X buttons handle themselves
    const tile = t.closest('.nb-place-btn');
    if (tile) { if (!S.deleteMode) toggleTile(tile); return; }
    const back = t.closest('[data-nb-pick-back]');
    if (back) { const menu = back.closest('.nb-create-menu'); if (menu) createMenuItems(menu); return; }
    const pick = t.closest('[data-nb-pick]');
    if (pick) {
      const value = pick.dataset.nbPick;
      const menu = pick.closest('.nb-create-menu'); if (menu) menu.remove();
      const place = value.startsWith('p:') ? {project_id: value.slice(2), folder_id: null}
        : value.startsWith('f:') ? {project_id: null, folder_id: value.slice(2)} : {project_id: null, folder_id: null};
      // Show the new note where it was put.
      S.scope = place.project_id ? {kind: 'project', id: place.project_id} : place.folder_id ? {kind: 'folder', id: place.folder_id} : {kind: 'general', id: null};
      await newNote(place);
      return;
    }
    const create = t.closest('[data-nb-create]');
    if (create) {
      const what = create.dataset.nbCreate;
      const menu = create.closest('.nb-create-menu');
      if (what === 'note' && menu) { showPlacePicker(menu); return; }
      if (menu) menu.remove();
      if (what === 'note') await newNote();
      else if (what === 'folder') await newFolder();
      else enterDeleteMode();
      return;
    }
    if (S.deleteMode && t.closest('[data-nb-open]') && t.closest('#notebookSidebar')) return;
    const open = t.closest('[data-nb-open]');
    if (open) { await openNote(open.dataset.nbOpen); return; }
    const scope = t.closest('[data-nb-scope]');
    if (scope) {
      S.scope = {kind: scope.dataset.nbScope, id: null};
      S.pane = 'list';
      render();
      return;
    }
    const tag = t.closest('[data-nb-tag]');
    if (tag) { S.tagFilter = S.tagFilter === tag.dataset.nbTag ? null : tag.dataset.nbTag; render(); return; }
    const untag = t.closest('[data-nb-untag]');
    if (untag && S.note) {
      S.note.tags = (S.note.tags || []).filter((x) => x !== untag.dataset.nbUntag);
      queueSave('tags', true);
      const chip = untag.closest('.nb-tag-chip');
      if (chip && typeof window.animateRemoval === 'function') await window.animateRemoval(chip, {collapse: false});
      renderEditorHead();
      return;
    }
    const action = t.closest('[data-nb-action]');
    if (!action) return;
    switch (action.dataset.nbAction) {
      case 'new': await newNote(); break;
      case 'new-folder': await newFolder(); break;
      case 'create-menu': openCreateMenu(action); break;
      case 'delete-done': if (deleteModeRef) deleteModeRef.exit(); break;
      case 'menu': noteMenu(action); break;
      case 'add-files': pickFiles(); break;
      case 'toggle-pinned': await setFlag('pinned'); break;
      case 'toggle-favorite': await setFlag('favorite'); break;
      case 'restore': await restoreCurrent(); break;
      case 'purge': await purgeCurrent(); break;
      case 'empty-trash': await emptyTrash(); break;
      case 'retry': await runSave(); renderEditorHead(); break;
      case 'conflict-mine': await resolveConflict(true); break;
      case 'conflict-theirs': await resolveConflict(false); break;
      case 'back': if (document.activeElement && document.activeElement.blur) document.activeElement.blur(); S.pane = 'list'; ensureShell(); break;
      case 'reload': await loadBootstrap(); render(); break;
      case 'vault-open':
        if (!S.vault) {
          toast('Connect your Obsidian vault in Settings → Preferences');
          if (typeof window.switchPanel === 'function') { await window.switchPanel('settings'); if (typeof window.switchSettingsSection === 'function') window.switchSettingsSection('preferences'); }
          break;
        }
        useSide('vault'); S.pane = 'list'; render(); break;
      case 'more': S.more[action.dataset.nbMore] = !S.more[action.dataset.nbMore]; renderSidebar(); break;
      case 'vault-close': useSide('notes'); S.pane = 'list'; render(); break;
      default: break;
    }
  }
  function onKeydown(event) {
    if (!isShowing()) return;
    const mod = event.metaKey || event.ctrlKey;
    if (mod && !event.shiftKey && !event.altKey && (event.key === 's' || event.key === 'S')) {
      event.preventDefault();
      runSave();
    } else if (event.altKey && !mod && (event.key === 'n' || event.key === 'N' || event.code === 'KeyN')) {
      event.preventDefault();
      newNote();
    } else if (mod && event.shiftKey && (event.key === 'f' || event.key === 'F')) {
      event.preventDefault();
      const search = $('nbSearch'); if (search) { S.pane = 'list'; ensureShell(); search.focus(); search.select(); }
    }
  }
  const isShowing = () => !!document.querySelector('main.main.showing-notebook');
  function onBeforeUnload() { if (Object.keys(save.dirty).length) writeDraft(); }

  // Anything that holds a text caret (the editor, the title, the tag box, a
  // search field) owns the keyboard. A tap on a button elsewhere -- the note
  // header, the list, the sidebar, the app's top bar -- first blurs it on iOS:
  // the keyboard folds, the page re-lays out under the finger, and the click
  // never lands, so every button needed a second tap. Cancelling the mousedown
  // keeps the focus where it is and lets the click through. Document-wide, in
  // the capture phase, because the top bar is outside the Notes page.
  let focusKeeperInstalled = false;
  function installFocusKeeper() {
    if (focusKeeperInstalled || !window.matchMedia || !window.matchMedia('(hover: none)').matches) return;
    focusKeeperInstalled = true;
    const typing = (el) => !!el && (el.isContentEditable || el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && !/^(button|checkbox|radio|submit|reset|file|range|color|image)$/i.test(el.type)));
    document.addEventListener('mousedown', (event) => {
      if (!isShowing() || !typing(document.activeElement)) return;
      const target = event.target;
      if (!target.closest || typing(target) || target.closest('.hermes-note-editor, select, label, textarea, input')) return;
      const tap = target.closest('button, [role="button"], a[href], [data-nb-open]');
      if (!tap || tap.dataset.nbAction === 'back') return;
      event.preventDefault();
    }, true);
  }
  let bound = false;
  function bind() {
    if (bound) return;
    bound = true;
    const root = $('notebookRoot'); const side = $('notebookSidebar');
    installFocusKeeper();
    if (root) root.addEventListener('click', onClick);
    if (side) side.addEventListener('click', onClick);
    if (side) side.addEventListener('contextmenu', (event) => {
      const tile = event.target.closest('.nb-place-btn[data-nb-kind="folder"]');
      if (!tile || S.deleteMode) return;
      event.preventDefault();
      folderMenu(tile, tile.dataset.nbId);
    });
    document.addEventListener('keydown', onKeydown);
    window.addEventListener('beforeunload', onBeforeUnload);
    document.addEventListener('visibilitychange', () => { if (document.hidden && Object.keys(save.dirty).length) { writeDraft(); runSave(); } });
  }

  // A note asked for from outside the page (the chat's Workspace panel) opens
  // instead of the last-opened one.
  let pendingOpen = null;
  async function mount() {
    bind();
    const wanted = pendingOpen; pendingOpen = null;
    if (!S.loaded) {
      render();
      await loadBootstrap();
      render();
      let last = wanted;
      if (!last) { try { last = localStorage.getItem(LAST_KEY); } catch (_) {} }
      if (last && S.notes.some((n) => n.id === last && live(n))) { S.pane = window.matchMedia('(max-width: 760px)').matches ? 'list' : 'editor'; await openNote(last); }
    } else {
      render();
      if (wanted) await openNote(wanted);
      else if (S.note && !editorCtl) await mountEditor(S.note, S.note.content);
    }
  }
  async function unmount() { await flushSave(); }
  async function refresh() { await loadBootstrap(); render(); }
  // Open the Notes page on a workspace's notes, and on one note when given.
  async function openFrom(noteId, projectId) {
    if (projectId) { S.scope = {kind: 'project', id: projectId}; S.expanded['project:' + projectId] = true; }
    else S.scope = {kind: 'all', id: null};
    pendingOpen = noteId || null;
    if (typeof window.switchPanel === 'function') await window.switchPanel('notebook');
    else await mount();
  }

  window.Notebook = {mount, unmount, refresh, openFrom, vaultChanged, _state: S, _save: save, _upload: (file) => uploadFile(file), _widths: {write: () => editorMarkdown(), read: (blocks) => withMediaBlocks(withImageWidths(blocks))}};
  // Test/automation hook: the live editor controller (null when no note is open).
  Object.defineProperty(window.Notebook, 'editor', {get: () => editorCtl});
}());
