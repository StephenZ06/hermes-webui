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
    projects: [], folders: [], notes: [],
    scope: {kind: 'all', id: null},
    search: '', searchResults: null, searchSeq: 0,
    expanded: {}, tagFilter: null,
    note: null, noteLoading: false, noteError: '',
    pane: 'list', // narrow screens: 'list' | 'editor'
  };
  const save = {timer: 0, retry: 0, inflight: null, dirty: {}, again: false, status: 'idle', error: '', conflict: null};
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
    if (note.project_id) { const p = projectOf(note.project_id); return p ? p.name : 'General'; }
    if (note.folder_id) { const f = folderOf(note.folder_id); return f ? f.name : 'General'; }
    return 'General';
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
    return {all: 'All notes', general: 'General', pinned: 'Pinned', favorites: 'Favorites', trash: 'Trash'}[k] || 'Notes';
  }
  // Where a note created in the current scope goes.
  function placeForScope() {
    if (S.scope.kind === 'project') return {project_id: S.scope.id};
    if (S.scope.kind === 'folder') return {folder_id: S.scope.id};
    return {};
  }

  // ── data ───────────────────────────────────────────────────────────────────
  async function loadBootstrap() {
    S.loading = true; S.error = '';
    try {
      const data = await window.NotebookApi.bootstrap();
      S.projects = data.projects || []; S.folders = data.folders || []; S.notes = data.notes || [];
      S.loaded = true;
    } catch (error) {
      S.error = error.message || 'Notes could not be loaded';
    }
    S.loading = false;
  }
  function upsertSummary(note) {
    const summary = Object.assign({}, note);
    delete summary.content;
    const index = S.notes.findIndex((n) => n.id === note.id);
    if (index >= 0) S.notes[index] = Object.assign(S.notes[index], summary);
    else S.notes.unshift(summary);
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
  function scopeButton(kind, label, iconName, n) {
    const active = S.scope.kind === kind ? ' active' : '';
    return `<button type="button" class="work-hub-scope nb-scope${active}" data-nb-scope="${kind}">${icon(iconName)}<span>${esc(label)}</span>${n ? `<span class="nb-scope-count">${n}</span>` : ''}</button>`;
  }
  function noteRows(notes) {
    if (!notes.length) return '<p class="nb-tree-empty">No notes yet</p>';
    return notes.slice(0, 50).map((n) => `<div class="work-hub-board-row nb-tree-note${S.note && S.note.id === n.id ? ' active' : ''}"><button type="button" data-nb-open="${esc(n.id)}">${icon('note', 13)}<span>${esc(n.title || 'Untitled')}</span></button></div>`).join('');
  }
  function placeGroup(kind, item, notes) {
    const key = kind + ':' + item.id;
    const expanded = !!S.expanded[key];
    const active = S.scope.kind === kind && S.scope.id === item.id ? ' active' : '';
    const dot = kind === 'project'
      ? `<span class="color-dot nb-dot" style="background:${esc(item.color || 'var(--accent)')}" aria-hidden="true"></span>`
      : `<span class="nb-folder-icon" aria-hidden="true">${icon('folder', 13)}</span>`;
    const more = kind === 'folder' ? `<button type="button" class="nb-row-more" data-nb-folder-menu="${esc(item.id)}" aria-label="Folder options">${icon('more', 14)}</button>` : '';
    return `<div class="nb-place" data-nb-place="${esc(key)}">
      <div class="nb-place-row"><button type="button" class="project-chip project-folder-row work-hub-project-tile nb-place-btn${active}" data-nb-scope="${kind}" data-nb-id="${esc(item.id)}" aria-expanded="${expanded}">
        <span class="project-folder-chevron nb-chevron${expanded ? ' expanded' : ''}" data-nb-toggle="${esc(key)}" aria-label="${expanded ? 'Collapse' : 'Expand'}">▸</span>${dot}<span class="project-folder-name"></span><span class="project-folder-count">${notes.length}</span></button>${more}</div>
      <div class="project-folder-sessions${expanded ? ' expanded' : ''}" ${expanded ? '' : 'inert'}><div class="project-folder-sessions-inner">${noteRows(notes)}</div></div>
    </div>`;
  }
  function renderSidebar() {
    const side = $('notebookSidebar');
    if (!side) return;
    if (!S.loaded) { side.innerHTML = S.error ? `<p class="nb-side-error">${esc(S.error)}</p>` : '<div class="nb-side-loading" aria-busy="true"><i></i><i></i><i></i></div>'; return; }
    const liveNotes = S.notes.filter(live);
    const tags = [...new Set(liveNotes.flatMap((n) => n.tags || []))].sort();
    side.innerHTML = `<nav class="work-hub-nav nb-nav" aria-label="Notes navigation">
      <button type="button" class="nb-new-btn" data-nb-action="new">${icon('plus', 14)}<span>New note</span></button>
      ${scopeButton('all', 'All notes', 'all', count((n) => live(n) && !n.archived))}
      ${scopeButton('general', 'General', 'general', count((n) => live(n) && !n.project_id && !n.folder_id))}
      ${scopeButton('pinned', 'Pinned', 'pin', count((n) => live(n) && n.pinned))}
      ${scopeButton('favorites', 'Favorites', 'star', count((n) => live(n) && n.favorite))}
      <div class="work-hub-nav-label nb-nav-label"><span>WORKSPACES</span></div>
      <div class="nb-places">${S.projects.length ? S.projects.map((p) => placeGroup('project', {id: p.project_id, color: p.color}, liveNotes.filter((n) => n.project_id === p.project_id))).join('') : '<p class="nb-tree-empty">No workspaces yet</p>'}</div>
      <div class="work-hub-nav-label nb-nav-label nb-label-row"><span>FOLDERS</span><button type="button" class="work-hub-project-create nb-folder-create" data-nb-action="new-folder" aria-label="New folder" title="New folder">${icon('plus', 13)}</button></div>
      <div class="nb-places">${S.folders.length ? S.folders.map((f) => placeGroup('folder', {id: f.id}, liveNotes.filter((n) => n.folder_id === f.id))).join('') : '<p class="nb-tree-empty">Folders you create here stay on the Notes page.</p>'}</div>
      ${tags.length ? `<div class="work-hub-nav-label nb-nav-label"><span>TAGS</span></div><div class="nb-tag-cloud">${tags.map((t) => `<button type="button" class="nb-tag${S.tagFilter === t ? ' active' : ''}" data-nb-tag="${esc(t)}">#${esc(t)}</button>`).join('')}</div>` : ''}
      <div class="nb-nav-spacer"></div>
      ${scopeButton('trash', 'Trash', 'trash', count((n) => !!n.deleted_at))}
    </nav>`;
    // Names are set as text, never as HTML.
    side.querySelectorAll('.nb-place-btn').forEach((button) => {
      const item = button.dataset.nbScope === 'project' ? projectOf(button.dataset.nbId) : folderOf(button.dataset.nbId);
      button.querySelector('.project-folder-name').textContent = (item && item.name) || 'Untitled';
    });
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
        <span class="nb-item-meta">${esc(placeLabel(n))} · ${esc(when(n.updated_at))}${(n.tags || []).length ? ` · ${n.tags.slice(0, 3).map((t) => '#' + esc(t)).join(' ')}` : ''}</span>
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
  function renderEditorHead() {
    const head = $('nbEditorHead');
    if (!head) return;
    const note = S.note;
    if (!note) {
      head.innerHTML = S.noteLoading ? '<div class="nb-skeleton head"><i></i><i></i></div>'
        : S.noteError ? `<div class="nb-empty"><p>${esc(S.noteError)}</p></div>`
          : `<div class="nb-empty nb-editor-empty"><p>${S.loaded && !S.notes.some(live) ? 'Create your first note to get started.' : 'Select a note, or start a new one.'}</p><button type="button" class="nb-btn primary" data-nb-action="new">New note</button></div>`;
      return;
    }
    const trashed = !!note.deleted_at;
    const conflict = save.conflict ? `<div class="nb-banner warn" role="alert"><span>This note was changed in another window.</span><button type="button" class="nb-btn small" data-nb-action="conflict-mine">Keep mine</button><button type="button" class="nb-btn small" data-nb-action="conflict-theirs">Load theirs</button></div>` : '';
    const failed = save.status === 'error' ? `<div class="nb-banner" role="status"><span>${esc(save.error || 'Saving failed')}. Your changes are kept here and retried.</span><button type="button" class="nb-btn small" data-nb-action="retry">Retry now</button></div>` : '';
    head.innerHTML = `${trashed ? '<div class="nb-banner"><span>This note is in the trash.</span><button type="button" class="nb-btn small" data-nb-action="restore">Restore</button><button type="button" class="nb-btn small danger" data-nb-action="purge">Delete forever</button></div>' : ''}${conflict}${failed}
      <div class="nb-head-row">
        <button type="button" class="nb-icon-btn nb-back" data-nb-action="back" aria-label="Back to notes">${icon('back', 16)}</button>
        <input id="nbTitle" class="nb-title" type="text" maxlength="240" placeholder="Untitled" aria-label="Note title" ${trashed ? 'disabled' : ''}>
        <span class="nb-status" data-status="${esc(save.status)}" aria-live="polite">${esc(statusText())}</span>
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
  async function uploadFile(file) {
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
    editorCtl = mod.mountNoteEditor(mountPoint, {
      content,
      theme: theme(),
      editable: !note.deleted_at,
      placeholder: "Write, or type '/' for commands",
      uploadFile,
      onChange: () => { if (editorNoteId === note.id) queueSave('content'); },
    });
    editorNoteId = note.id;
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
    if (fields.content && editorCtl && editorNoteId === note.id) body.content = editorCtl.getBlocks();
    if (fields.tags) body.tags = note.tags || [];
    if (fields.place) { body.project_id = note.project_id || null; body.folder_id = note.folder_id || null; }
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
  async function newNote(extra) {
    await flushSave();
    try {
      const {note} = await window.NotebookApi.create(Object.assign({title: ''}, placeForScope(), extra || {}));
      upsertSummary(note); sortNotes();
      if (S.scope.kind === 'trash' || S.scope.kind === 'pinned' || S.scope.kind === 'favorites') S.scope = {kind: 'all', id: null};
      const key = note.project_id ? 'project:' + note.project_id : note.folder_id ? 'folder:' + note.folder_id : null;
      if (key) S.expanded[key] = true;
      await openNote(note.id, {force: true});
      const title = $('nbTitle'); if (title) title.focus();
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
    await flushSave();
    try {
      const result = await window.NotebookApi.trash(note.id);
      upsertSummary(result.note);
      clearDraft(note.id);
      destroyEditor(); S.note = null; S.pane = 'list';
      render();
      toast('Moved to trash');
    } catch (error) { toast(error.message || 'Could not move the note to the trash'); }
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
      await window.NotebookApi.emptyTrash();
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
      const {folder} = await window.NotebookApi.createFolder(name.trim());
      S.folders.push(folder);
      S.scope = {kind: 'folder', id: folder.id};
      S.expanded['folder:' + folder.id] = true;
      render();
    } catch (error) { toast(error.message || 'Could not create the folder'); }
  }
  function folderMenu(anchor, folderId) {
    const folder = folderOf(folderId); if (!folder) return;
    openMenu(anchor, [
      {label: 'New note here', run: async () => { S.scope = {kind: 'folder', id: folderId}; await newNote(); }},
      {label: 'Rename', run: async () => {
        const name = typeof window.showPromptDialog === 'function'
          ? await window.showPromptDialog({title: 'Rename folder', value: folder.name, confirmLabel: 'Rename'})
          : window.prompt('Folder name', folder.name);
        if (!name || !name.trim()) return;
        try { const result = await window.NotebookApi.renameFolder(folderId, name.trim()); Object.assign(folder, result.folder); render(); }
        catch (error) { toast(error.message || 'Could not rename the folder'); }
      }},
      {label: 'Delete folder', danger: true, run: async () => {
        const n = S.notes.filter((x) => x.folder_id === folderId && live(x)).length;
        const ok = typeof window.showConfirmDialog === 'function'
          ? await window.showConfirmDialog({title: 'Delete folder?', message: n ? `Its ${n} note${n === 1 ? '' : 's'} will move to General.` : 'The folder is empty.', confirmLabel: 'Delete folder', danger: true})
          : window.confirm('Delete folder?');
        if (!ok) return;
        try {
          await window.NotebookApi.deleteFolder(folderId);
          S.folders = S.folders.filter((f) => f.id !== folderId);
          S.notes.forEach((x) => { if (x.folder_id === folderId) x.folder_id = null; });
          if (S.note && S.note.folder_id === folderId) S.note.folder_id = null;
          if (S.scope.kind === 'folder' && S.scope.id === folderId) S.scope = {kind: 'general', id: null};
          render();
        } catch (error) { toast(error.message || 'Could not delete the folder'); }
      }},
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
        const {notes} = await window.NotebookApi.search(S.search, S.scope.kind === 'trash');
        if (seq !== S.searchSeq) return;
        S.searchResults = notes;
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
    const toggle = t.closest('[data-nb-toggle]');
    if (toggle) {
      event.preventDefault(); event.stopPropagation();
      const key = toggle.dataset.nbToggle;
      S.expanded[key] = !S.expanded[key];
      renderSidebar();
      return;
    }
    const open = t.closest('[data-nb-open]');
    if (open) { await openNote(open.dataset.nbOpen); return; }
    const scope = t.closest('[data-nb-scope]');
    if (scope) {
      S.scope = {kind: scope.dataset.nbScope, id: scope.dataset.nbId || null};
      if (S.scope.id) S.expanded[S.scope.kind + ':' + S.scope.id] = true;
      S.pane = 'list';
      render();
      return;
    }
    const tag = t.closest('[data-nb-tag]');
    if (tag) { S.tagFilter = S.tagFilter === tag.dataset.nbTag ? null : tag.dataset.nbTag; render(); return; }
    const untag = t.closest('[data-nb-untag]');
    if (untag && S.note) {
      S.note.tags = (S.note.tags || []).filter((x) => x !== untag.dataset.nbUntag);
      queueSave('tags', true); renderEditorHead();
      return;
    }
    const folderMenuBtn = t.closest('[data-nb-folder-menu]');
    if (folderMenuBtn) { folderMenu(folderMenuBtn, folderMenuBtn.dataset.nbFolderMenu); return; }
    const action = t.closest('[data-nb-action]');
    if (!action) return;
    switch (action.dataset.nbAction) {
      case 'new': await newNote(); break;
      case 'new-folder': await newFolder(); break;
      case 'menu': noteMenu(action); break;
      case 'toggle-pinned': await setFlag('pinned'); break;
      case 'toggle-favorite': await setFlag('favorite'); break;
      case 'restore': await restoreCurrent(); break;
      case 'purge': await purgeCurrent(); break;
      case 'empty-trash': await emptyTrash(); break;
      case 'retry': await runSave(); renderEditorHead(); break;
      case 'conflict-mine': await resolveConflict(true); break;
      case 'conflict-theirs': await resolveConflict(false); break;
      case 'back': S.pane = 'list'; ensureShell(); break;
      case 'reload': await loadBootstrap(); render(); break;
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

  let bound = false;
  function bind() {
    if (bound) return;
    bound = true;
    const root = $('notebookRoot'); const side = $('notebookSidebar');
    if (root) root.addEventListener('click', onClick);
    if (side) side.addEventListener('click', onClick);
    document.addEventListener('keydown', onKeydown);
    window.addEventListener('beforeunload', onBeforeUnload);
    document.addEventListener('visibilitychange', () => { if (document.hidden && Object.keys(save.dirty).length) { writeDraft(); runSave(); } });
  }

  async function mount() {
    bind();
    if (!S.loaded) {
      render();
      await loadBootstrap();
      render();
      let last = null;
      try { last = localStorage.getItem(LAST_KEY); } catch (_) {}
      if (last && S.notes.some((n) => n.id === last && live(n))) { S.pane = window.matchMedia('(max-width: 760px)').matches ? 'list' : 'editor'; await openNote(last); }
    } else {
      render();
      if (S.note && !editorCtl) await mountEditor(S.note, S.note.content);
    }
  }
  async function unmount() { await flushSave(); }
  async function refresh() { await loadBootstrap(); render(); }

  window.Notebook = {mount, unmount, refresh, _state: S, _save: save};
  // Test/automation hook: the live editor controller (null when no note is open).
  Object.defineProperty(window.Notebook, 'editor', {get: () => editorCtl});
}());
