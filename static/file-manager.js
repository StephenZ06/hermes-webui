/* Workspace-scoped Files page. No session IDs or absolute paths cross this boundary. */
(function () {
  'use strict';

  const state = {
    root: null,
    workspaces: [],
    workspaceId: '',
    path: '.',
    entries: [],
    selected: null,
    preview: null,
    filter: '',
    loading: false,
    opening: null,
    dragging: null,
    dragWired: false,
    requestId: 0,
    mounted: false,
    // Delete mode: rows wiggle, a tap picks one, the bar under the list deletes the picked ones.
    deleteMode: false,
    modeFresh: false,
    picked: new Set(),
  };

  const phoneWidth = window.matchMedia('(max-width:680px)');
  phoneWidth.addEventListener('change', () => { if (state.mounted) render(); });

  const icon = (paths) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
  const icons = {
    folder: icon('<path d="M3 7a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M3 10h18"/>'),
    file: icon('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h6"/>'),
    plus: icon('<path d="M12 5v14M5 12h14"/>'),
    check: icon('<path d="m5 12.5 4.5 4.5L19 7.5"/>'),
    back: icon('<path d="m15 18-6-6 6-6"/>'),
    download: icon('<path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 21h14"/>'),
    save: icon('<path d="M5 3h12l2 2v16H5z"/><path d="M8 3v6h8V3M8 21v-7h8v7"/>'),
    rename: icon('<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>'),
    move: icon('<path d="M7 7h10M13 3l4 4-4 4M17 17H7M11 13l-4 4 4 4"/>'),
    trash: icon('<path d="M3 6h18M8 6V4h8v2m-9 0 1 15h8l1-15"/>'),
    close: icon('<path d="m18 6-12 12M6 6l12 12"/>'),
    search: icon('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>'),
    audio: icon('<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>'),
  };

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
  }
  function encode(value) { return encodeURIComponent(String(value == null ? '' : value)); }
  function notify(message, kind) { if (typeof window.showToast === 'function') window.showToast(message, kind); }
  function endpoint(path) { return '/api/file-manager' + path; }
  async function request(path, options) {
    const response = await fetch(endpoint(path), Object.assign({ headers: { 'Content-Type': 'application/json' } }, options || {}));
    let payload = {};
    try { payload = await response.json(); } catch (_) { /* response status handles this below */ }
    if (!response.ok) throw new Error(payload.error || payload.message || 'Files request failed');
    return payload;
  }
  function currentWorkspace() { return state.workspaces.find((item) => item.id === state.workspaceId) || null; }
  function parentPath(path) {
    if (!path || path === '.') return '.';
    const parts = path.split('/'); parts.pop(); return parts.length ? parts.join('/') : '.';
  }
  function prettySize(size) {
    if (size == null || Number.isNaN(Number(size))) return '—';
    const bytes = Number(size); if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  function isTextPreview() {
    return state.preview && typeof state.preview.content === 'string' && !state.preview.preview_kind;
  }
  // Files the browser draws itself are streamed from the space instead of read as text.
  const MEDIA = {
    image: ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico', '.bmp', '.avif'],
    video: ['.mp4', '.mov', '.m4v', '.webm', '.ogv'],
    audio: ['.mp3', '.wav', '.m4a', '.aac', '.ogg', '.oga', '.opus', '.flac'],
    pdf: ['.pdf'],
  };
  const KIND_LABEL = { image: 'Image', video: 'Video', audio: 'Audio', pdf: 'PDF', office: 'Document', binary: 'Binary file', too_large: 'Large file', remote_media: 'Media' };
  function mediaKind(path) {
    const dot = String(path || '').lastIndexOf('.');
    const ext = dot < 0 ? '' : String(path).slice(dot).toLowerCase();
    return Object.keys(MEDIA).find((kind) => MEDIA[kind].includes(ext)) || '';
  }
  function rawUrl(path, download) {
    return endpoint(`/raw?workspace_id=${encode(state.workspaceId)}&path=${encode(path)}${download ? '&download=1' : ''}`);
  }
  function previewBody(preview, readOnly) {
    const kind = preview.preview_kind || '';
    const name = esc(preview.path.split('/').pop() || preview.path);
    const src = esc(rawUrl(preview.path));
    if (kind === 'image') return `<div class="files-media files-media-image"><img src="${src}" alt="${name}" draggable="false"></div>`;
    if (kind === 'video') return `<div class="files-media files-media-video"><video src="${src}" controls preload="metadata" playsinline></video></div>`;
    if (kind === 'audio') return `<div class="files-media files-media-audio">${icons.audio}<strong>${name}</strong><audio src="${src}" controls preload="metadata"></audio></div>`;
    if (kind === 'pdf') return `<div class="files-media files-media-pdf"><iframe src="${src}" title="${name}"></iframe></div>`;
    if (kind === 'office' && typeof preview.content === 'string') return `<textarea class="files-editor" aria-label="Document text" readonly>${esc(preview.content)}</textarea>`;
    if (isTextPreview()) return `<textarea class="files-editor" aria-label="File contents" ${readOnly ? 'readonly' : ''}>${esc(preview.content)}</textarea>${readOnly ? '' : `<button type="button" class="files-save" data-action="save">${icons.save}<span>Save changes</span></button>`}`;
    const why = kind === 'too_large' ? 'This file is too large to open here.'
      : kind === 'remote_media' ? 'Previews of files on a remote space are not available.'
        : 'This file is not text, so it cannot be shown here.';
    return `<div class="files-preview-unavailable">${icons.file}<strong>Preview unavailable</strong><span>${why} Download it to open it on your computer.</span><button type="button" class="files-action files-download-wide" data-action="download">${icons.download}<span>Download</span></button></div>`;
  }
  function previewMeta(preview, readOnly) {
    const kind = preview.preview_kind || '';
    const parts = [prettySize(preview.size)];
    // An image's pixel size is filled in once it has loaded.
    if (KIND_LABEL[kind]) parts.push(kind === 'image' ? `${KIND_LABEL[kind]}<span class="files-image-size"></span>` : KIND_LABEL[kind]);
    else parts.push(`${preview.lines || 1} line${preview.lines === 1 ? '' : 's'}`);
    if (readOnly || kind === 'office') parts.push('Read only');
    return parts.join(' · ');
  }
  function setMobileSurface(surface) {
    if (!state.root) return;
    state.root.dataset.surface = surface || 'browser';
  }
  // A part of the page is written only when its markup changed, so nothing already on screen is rebuilt: the
  // field keeps its focus, an open editor keeps its text and the highlight keeps gliding.
  const written = new WeakMap();
  function write(el, html) {
    if (!el || written.get(el) === html) return false;
    el.innerHTML = html; written.set(el, html); return true;
  }
  function restart(el, name) {
    if (!el) return;
    el.classList.remove(name); void el.offsetWidth; el.classList.add(name);
  }
  function shell() {
    const placement = spacesInSidePanel() ? 'side-panel' : 'page';
    let layout = state.root.querySelector(':scope > .file-manager-layout');
    if (layout && layout.dataset.spaces === placement) return layout;
    state.root.innerHTML = `<div class="file-manager-layout" data-spaces="${placement}">
      ${placement === 'page' ? '<div class="files-spaces-slot"></div>' : ''}
      <section class="files-browser" aria-label="File browser"><header class="files-toolbar"><button type="button" class="files-icon-btn files-up" data-action="up" aria-label="Parent folder">${icons.back}</button><div class="files-title"></div><div class="files-toolbar-actions"></div></header><nav class="files-path" aria-label="Folder path"><div class="files-breadcrumb"></div></nav><div class="files-list-toolbar"><label class="files-search"><span>${icons.search}</span><input type="search" placeholder="Filter" aria-label="Filter files"></label></div><div class="files-list" role="list"></div><div class="files-select-slot"></div></section>
      <aside class="files-inspector" aria-label="File inspector"><div class="files-inspector-stage"><div class="files-inspector-content"></div></div></aside>
    </div>`;
    layout = state.root.firstElementChild;
    const filter = layout.querySelector('.files-search input');
    filter.value = state.filter;
    filter.addEventListener('input', () => { state.filter = filter.value; render(); });
    return layout;
  }
  // The picked space's highlight slides from the space picked before, as on every other side panel
  // (ui.js playActiveHighlightGlide).
  const SPACE_HIGHLIGHT = {
    selector: '.files-workspace.is-active',
    restSelector: '.files-workspace:not(.is-active)',
    key: (row) => row.dataset.workspaceId || '',
    find: (list, id) => list.querySelector(`.files-workspace[data-workspace-id="${CSS.escape(id)}"]`),
    section: () => 'spaces',
  };
  function spacesInSidePanel() { return !!document.getElementById('filesSidebarHost') && !phoneWidth.matches; }
  function render() {
    if (!state.root) return;
    const layout = shell();
    state.root.dataset.hasPreview = state.preview ? 'true' : 'false';
    const workspace = currentWorkspace();
    const visibleEntries = state.entries.filter((entry) => !state.filter || String(entry.name || '').toLowerCase().includes(state.filter.toLowerCase()));
    const readOnly = !workspace || workspace.read_only;
    const crumbs = state.path === '.' ? [] : state.path.split('/');
    const crumbMarkup = [`<button type="button" class="files-crumb" data-path=".">Workspace</button>`]
      .concat(crumbs.map((part, index) => `<span class="files-crumb-separator">/</span><button type="button" class="files-crumb" data-path="${esc(crumbs.slice(0, index + 1).join('/'))}">${esc(part)}</button>`)).join('');
    const picking = state.deleteMode && !readOnly;
    const listRows = visibleEntries.length ? visibleEntries.map((entry, index) => {
      const selected = state.selected === entry.path;
      const isDir = entry.type === 'dir' || entry.is_dir;
      const picked = picking && state.picked.has(entry.path);
      const mode = picking ? ` dm-wiggle files-pickable${picked ? ' is-picked' : ''}" aria-pressed="${picked}" style="animation-delay:${-((index * 97) % 300)}ms` : '';
      return `<button type="button" class="files-row${selected && !picking ? ' is-selected' : ''}${mode}" data-file-path="${esc(entry.path)}" data-file-type="${esc(entry.type || '')}"${readOnly || picking ? '' : ' draggable="true"'}>
        <span class="files-row-icon">${isDir ? icons.folder : icons.file}</span><span class="files-row-name">${esc(entry.name)}</span>
        <span class="files-row-meta">${isDir ? 'Folder' : prettySize(entry.size)}</span>${picking ? `<span class="files-pick" aria-hidden="true">${icons.check}</span>` : ''}
      </button>`;
    }).join('') : `<div class="files-empty-list">${state.filter ? 'No matching files' : 'This folder is empty'}</div>`;
    const previewMarkup = !state.preview
      ? `<div class="files-inspector-empty">${icons.file}<strong>Select a file</strong><span>Choose a file to preview, edit, rename, download, or remove it.</span></div>`
      : `<div class="files-inspector-header"><div><div class="files-inspector-name">${esc(state.preview.path)}</div><div class="files-inspector-meta">${previewMeta(state.preview, readOnly)}</div></div><div class="files-inspector-actions">
          <button type="button" class="files-icon-btn" data-action="download" title="Download">${icons.download}</button>
          ${readOnly ? '' : `<button type="button" class="files-icon-btn" data-action="rename" title="Rename">${icons.rename}</button><button type="button" class="files-icon-btn" data-action="move" title="Move">${icons.move}</button><button type="button" class="files-icon-btn files-icon-btn-danger" data-action="delete" title="Delete">${icons.trash}</button>`}
          <button type="button" class="files-icon-btn" data-action="close-preview" title="Close preview">${icons.close}</button></div></div>
        <div class="files-preview-wrap" data-kind="${esc(state.preview.preview_kind || 'text')}">${previewBody(state.preview, readOnly)}</div>`;
    // The list of spaces stands in the Files side panel. A phone has no side panel on screen, so there it
    // stays the first of the sliding surfaces.
    // The list is built once per set of spaces. Picking a space or a status change only moves the classes
    // on the rows already there: rebuilding it replayed the panel's fade (a flicker on every pick) and
    // dropped the sliding hover highlight, which lives on the list element.
    const spacesKey = JSON.stringify(state.workspaces.map((item) => [item.id, item.name, !!item.read_only]));
    const spacesMarkup = `<aside class="files-workspaces" aria-label="Connected workspaces" data-spaces-key="${esc(spacesKey)}"><div class="files-section-heading">Connected spaces</div><div class="files-workspace-list" data-mi-hover=".files-workspace">${state.workspaces.map((item) => `<button type="button" class="files-workspace" data-workspace-id="${esc(item.id)}"><span class="files-workspace-dot"></span><span>${esc(item.name)}</span>${item.read_only ? '<span class="files-read-only-tag">Read only</span>' : ''}</button>`).join('') || '<div class="files-empty-list">No connected spaces</div>'}</div><p class="files-sidebar-caption">Files stays inside the workspaces Hermes already knows.</p></aside>`;
    const sideHost = document.getElementById('filesSidebarHost');
    const spacesHost = layout.dataset.spaces === 'side-panel' ? sideHost : layout.querySelector('.files-spaces-slot');
    const listed = spacesHost && spacesHost.querySelector(':scope > .files-workspaces');
    if (!listed || listed.dataset.spacesKey !== spacesKey) {
      if (write(spacesHost, spacesMarkup) && window.Micro) window.Micro.scan(spacesHost);
    }
    if (spacesHost) {
      const byId = new Map(state.workspaces.map((item) => [item.id, item]));
      const list = spacesHost.querySelector('.files-workspace-list');
      const current = list && list.querySelector('.files-workspace.is-active');
      const moving = !!current && current.dataset.workspaceId !== state.workspaceId;
      const from = moving && typeof window.noteActiveHighlight === 'function' ? window.noteActiveHighlight(list, SPACE_HIGHLIGHT) : null;
      spacesHost.querySelectorAll('.files-workspace[data-workspace-id]').forEach((row) => {
        const item = byId.get(row.dataset.workspaceId);
        if (!item) return;
        row.classList.toggle('is-active', item.id === state.workspaceId);
        const dot = row.querySelector('.files-workspace-dot');
        dot.classList.toggle('is-online', !!item.available);
        dot.classList.toggle('is-offline', !item.available);
      });
      if (from && typeof window.playActiveHighlightGlide === 'function') window.playActiveHighlightGlide(list, from, { ...SPACE_HIGHLIGHT, bounds: list });
    }
    if (sideHost && spacesHost !== sideHost) write(sideHost, '');
    layout.dataset.readOnly = readOnly ? 'true' : 'false';
    layout.dataset.hasPreview = state.preview || state.opening ? 'true' : 'false';
    layout.dataset.surface = state.root.dataset.surface || 'browser';
    layout.querySelector('.files-up').disabled = state.path === '.';
    showTitle(layout.querySelector('.files-title'), state.path === '.' ? (workspace ? workspace.name : 'Files') : crumbs[crumbs.length - 1], workspace);
    showPath(layout.querySelector('.files-path'), crumbMarkup);
    write(layout.querySelector('.files-toolbar-actions'), readOnly ? '<span class="files-read-only-tag">Read only</span>' : `<button type="button" class="files-action" data-action="new-file" aria-label="New file"><i class="files-mask files-mask-file"></i></button><button type="button" class="files-action" data-action="new-folder" aria-label="New folder"><i class="files-mask files-mask-folder"></i></button><button type="button" class="files-action files-action-danger${picking ? ' is-active' : ''}" data-action="delete-mode" data-delete-mode-keep aria-label="${picking ? 'Done deleting' : 'Delete files'}" aria-pressed="${picking}">${icons.trash}</button>`);
    const list = layout.querySelector('.files-list');
    list.classList.toggle('is-loading', state.loading);
    layout.querySelector('.files-browser').classList.toggle('is-picking', picking);
    layout.querySelector('.files-browser').classList.toggle('is-mode-entering', picking && state.modeFresh);
    write(list, listRows);
    write(layout.querySelector('.files-select-slot'), picking ? `<div class="files-select-bar${state.modeFresh ? ' is-entering' : ''}" role="toolbar" aria-label="Delete files">
      <div class="files-select-row"><span class="files-select-count" aria-live="polite"></span><button type="button" class="files-select-link" data-action="pick-all"></button>
      <button type="button" class="files-select-done" data-action="delete-mode">Done</button></div>
      <button type="button" class="files-select-delete" data-action="delete-picked">${icons.trash}<span>Delete</span></button></div>` : '');
    if (picking) syncPicked();
    const inspector = layout.querySelector('.files-inspector-content');
    if (write(inspector, previewMarkup) && !state.opening) restart(inspector, 'is-swapping');
  }
  const calm = window.matchMedia('(prefers-reduced-motion: reduce)');
  // The top bar names the folder on screen. A new name comes in from the side the move went: from the right
  // into a folder, from the left out of one, in place for another space.
  function showTitle(el, name, workspace) {
    const key = `${workspace ? workspace.id : ''}:${state.path}`;
    if (el.dataset.key === key) return;
    const before = el.dataset.key, was = el.dataset.depth;
    el.dataset.key = key; el.dataset.depth = String(depth(state.path));
    el.textContent = name;
    if (before === undefined) return;
    el.classList.remove('is-in-forward', 'is-in-back', 'is-in-in');
    const motion = before.split(':')[0] !== key.split(':')[0] ? 'in' : depth(state.path) > Number(was) ? 'forward' : 'back';
    restart(el, `is-in-${motion}`);
  }
  // The full path stands in its own row under the top bar and wraps rather than hiding behind the buttons.
  // A folder entered adds its crumb with a short rise, and the row eases to its new height when it wraps.
  function showPath(section, markup) {
    const trail = section.querySelector('.files-breadcrumb');
    const had = new Set([...trail.querySelectorAll('.files-crumb')].map((crumb) => crumb.dataset.path));
    const first = trail.childElementCount === 0;
    const from = section.getBoundingClientRect().height;
    if (!write(trail, markup) || first) return;
    trail.querySelectorAll('.files-crumb').forEach((crumb) => {
      if (had.has(crumb.dataset.path)) return;
      crumb.classList.add('is-new');
      const separator = crumb.previousElementSibling;
      if (separator && separator.classList.contains('files-crumb-separator')) separator.classList.add('is-new');
    });
    const to = section.getBoundingClientRect().height;
    if (Math.abs(to - from) < 0.5 || calm.matches || !section.animate) return;
    section.animate([{ height: `${from}px` }, { height: `${to}px` }], { duration: 220, easing: 'cubic-bezier(.22,1,.36,1)' });
  }
  // One listener per surface for everything rows, crumbs and buttons do, so rewriting a part costs no rebinding.
  function onClick(event) {
    const target = event.target.closest('[data-workspace-id],[data-path],[data-file-path],[data-action]');
    if (!target) return;
    if (state.deleteMode && target.dataset.filePath) { togglePicked(target); return; }
    if (target.dataset.workspaceId) openWorkspace(target.dataset.workspaceId);
    else if (target.dataset.path) openPath(target.dataset.path);
    else if (target.dataset.filePath) openEntry(target.dataset.filePath, target.dataset.fileType);
    else dispatchAction(target.dataset.action);
  }
  // ── Drag and drop: rows onto a folder or a crumb move them, files from the computer upload ──
  function clearDropTarget() {
    document.querySelectorAll('.files-drop-target').forEach((el) => el.classList.remove('files-drop-target'));
  }
  function folderUnder(node) {
    const row = node.closest ? node.closest('.files-row[data-file-type="dir"]') : null;
    const crumb = node.closest ? node.closest('.files-crumb[data-path]') : null;
    return { el: row || crumb, path: row ? row.dataset.filePath : crumb ? crumb.dataset.path : null };
  }
  function canMoveTo(source, folder) {
    return folder !== null && folder !== source && parentPath(source) !== folder && !folder.startsWith(`${source}/`);
  }
  // ── Delete mode (the shared createDeleteMode lifecycle in ui.js: Done, Escape or a click outside ends it) ──
  let modeRef = null;
  const modeLifecycle = () => modeRef || (modeRef = window.createDeleteMode({
    isInside: (target) => !!target.closest('.files-browser'),
    onChange: (active) => { if (!active) leaveDeleteMode(); },
  }));
  function visiblePaths() {
    return [...(state.root ? state.root.querySelectorAll('.files-list .files-row[data-file-path]') : [])].map((row) => row.dataset.filePath);
  }
  function syncPicked() {
    const paths = visiblePaths();
    [...state.picked].forEach((path) => { if (!paths.includes(path)) state.picked.delete(path); });
    const bar = state.root && state.root.querySelector('.files-select-bar');
    if (!bar) return;
    const n = state.picked.size;
    bar.querySelector('.files-select-count').textContent = n ? `${n} selected` : 'Pick files and folders';
    bar.querySelector('.files-select-link').textContent = n && n === paths.length ? 'None' : 'All';
    bar.querySelector('.files-select-link').hidden = !paths.length;
    bar.querySelector('.files-select-delete').disabled = !n;
  }
  function togglePicked(row) {
    const path = row.dataset.filePath;
    const on = !state.picked.has(path);
    if (on) state.picked.add(path); else state.picked.delete(path);
    row.classList.toggle('is-picked', on);
    row.setAttribute('aria-pressed', String(on));
    syncPicked();
  }
  function enterDeleteMode() {
    const workspace = currentWorkspace();
    if (!workspace || workspace.read_only) return;
    if (!state.entries.length) { notify('This folder is empty.'); return; }
    state.deleteMode = true; state.picked = new Set(); state.modeFresh = !calm.matches;
    modeLifecycle().enter();
    render();
    state.modeFresh = false;
  }
  // Leaving plays the bar and the check circles out first; `now` skips that (the list is about to change anyway).
  function leaveDeleteMode(now = false) {
    if (!state.deleteMode) return;
    const finish = () => {
      if (!state.deleteMode) return;
      state.deleteMode = false; state.picked = new Set();
      if (modeRef && modeRef.active) modeRef.exit();
      const browser = state.root && state.root.querySelector('.files-browser');
      if (browser) browser.classList.remove('is-leaving-mode');
      render();
    };
    const browser = state.root && state.root.querySelector('.files-browser');
    if (now || !browser || calm.matches) { finish(); return; }
    browser.classList.add('is-leaving-mode');
    setTimeout(finish, 180);
  }
  async function deletePicked() {
    const workspace = currentWorkspace();
    const paths = [...state.picked];
    if (!workspace || !paths.length) return;
    const rows = paths.map((path) => state.entries.find((entry) => entry.path === path) || { path, name: path.split('/').pop() });
    const folders = rows.filter((entry) => entry.type === 'dir' || entry.is_dir).length;
    const names = rows.slice(0, 4).map((entry) => `“${entry.name}”`).join(', ') + (rows.length > 4 ? ` and ${rows.length - 4} more` : '');
    const agreed = await window.showConfirmDialog({
      title: rows.length === 1 ? `Delete ${folders ? 'folder' : 'file'}?` : `Delete ${rows.length} items?`,
      message: `${names} will be permanently deleted.${folders ? ' Folders are deleted with everything inside them.' : ''}`,
      confirmLabel: 'Delete', danger: true, focusCancel: true,
    });
    if (!agreed || !state.deleteMode) return;
    const failed = [];
    const gone = [];
    for (const entry of rows) {
      const isDir = entry.type === 'dir' || !!entry.is_dir;
      try { await post('/delete', { workspace_id: workspace.id, path: entry.path, recursive: isDir }); gone.push(entry.path); }
      catch (error) { failed.push(`${entry.name}: ${error.message || 'failed'}`); }
    }
    if (typeof window.animateRemoval === 'function') {
      await Promise.all(gone.map((path) => window.animateRemoval(state.root.querySelector(`.files-row[data-file-path="${CSS.escape(path)}"]`))));
    }
    // An open file that was deleted, or sat in a deleted folder, closes.
    if (state.preview && gone.some((path) => state.preview.path === path || state.preview.path.startsWith(`${path}/`))) {
      state.preview = null; state.selected = null; setMobileSurface('browser');
    }
    leaveDeleteMode(true);
    await loadDirectory();
    if (gone.length) notify(gone.length === 1 ? 'Deleted 1 item' : `Deleted ${gone.length} items`, 'success');
    if (failed.length) notify(`Could not delete ${failed.join('; ')}`, 'error');
  }
  function onDragStart(event) {
    const row = event.target.closest && event.target.closest('.files-row[draggable="true"]');
    if (!row) return;
    state.dragging = row.dataset.filePath;
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', row.querySelector('.files-row-name').textContent);
    requestAnimationFrame(() => row.classList.add('is-dragging'));
  }
  function onDragOver(event) {
    const workspace = currentWorkspace();
    const fromComputer = !state.dragging && [...event.dataTransfer.types].includes('Files');
    if (!state.dragging && !fromComputer) return;
    if (!workspace || workspace.read_only) {
      // Refused here, or the browser would open the dropped file in place of the app.
      event.preventDefault(); event.dataTransfer.dropEffect = 'none'; return;
    }
    const folder = folderUnder(event.target);
    let target = null;
    if (state.dragging) { if (canMoveTo(state.dragging, folder.path)) target = folder.el; }
    else target = folder.el || event.target.closest('.files-browser');
    clearDropTarget();
    if (!target) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = state.dragging ? 'move' : 'copy';
    target.classList.add('files-drop-target');
  }
  function onDragEnd() {
    state.dragging = null; clearDropTarget();
    document.querySelectorAll('.files-row.is-dragging').forEach((row) => row.classList.remove('is-dragging'));
  }
  async function onDrop(event) {
    const source = state.dragging, folder = folderUnder(event.target).path;
    const items = [...(event.dataTransfer.items || [])].map((item) => (item.webkitGetAsEntry ? item.webkitGetAsEntry() : null));
    const files = [...event.dataTransfer.files];
    event.preventDefault(); onDragEnd();
    try {
      if (source) { if (canMoveTo(source, folder)) await moveEntry(source, folder); return; }
      const uploads = files.filter((file, index) => !(items[index] && items[index].isDirectory));
      if (uploads.length < files.length) notify('Folders cannot be uploaded. Drop the files inside them.', 'error');
      await uploadFiles(uploads, folder === null ? state.path : folder);
    } catch (error) { notify(error.message || 'Files action failed', 'error'); }
  }
  async function moveEntry(source, folder) {
    const workspace = currentWorkspace();
    const response = await post('/move', { workspace_id: workspace.id, path: source, destination: folder });
    // An open file that moved, or sits in a folder that moved, keeps its preview under its new path.
    if (state.preview && (state.preview.path === source || state.preview.path.startsWith(`${source}/`))) {
      state.preview.path = response.path + state.preview.path.slice(source.length);
      state.selected = state.preview.path;
    }
    await loadDirectory();
    notify(`Moved to ${folder === '.' ? 'Workspace' : folder}`, 'success');
  }
  async function uploadFiles(files, folder) {
    const workspace = currentWorkspace();
    let done = 0;
    for (const file of files) {
      if (file.size > 25 * 1024 * 1024) { notify(`${file.name} is over 25 MB`, 'error'); continue; }
      const data = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = () => reject(new Error(`Could not read ${file.name}`)); reader.readAsDataURL(file); });
      await post('/upload', { workspace_id: workspace.id, path: folder, filename: file.name, data_base64: data });
      done += 1;
    }
    if (!done) return;
    await loadDirectory();
    notify(done === 1 ? `${files[0].name} uploaded` : `${done} files uploaded`, 'success');
  }
  function wire(surface) {
    if (!surface || surface.dataset.filesWired) return;
    surface.dataset.filesWired = '1';
    surface.addEventListener('click', onClick);
  }
  async function loadWorkspaces() {
    const payload = await request('/workspaces');
    state.workspaces = payload.workspaces || [];
    if (!state.workspaces.some((item) => item.id === state.workspaceId)) state.workspaceId = (state.workspaces.find((item) => item.available) || state.workspaces[0] || {}).id || '';
    state.path = '.'; state.entries = []; state.selected = null; state.preview = null;
    if (state.workspaceId) await loadDirectory('in'); else render();
  }
  // Back on the page: what was on screen stays there, and only what changed since is written.
  async function refresh() {
    const payload = await request('/workspaces');
    if (!state.mounted) return;
    state.workspaces = payload.workspaces || [];
    if (!state.workspaces.some((item) => item.id === state.workspaceId)) { await loadWorkspaces(); return; }
    render();
    await loadDirectory();
  }
  async function openWorkspace(workspaceId) {
    if (!workspaceId || workspaceId === state.workspaceId) return;
    leaveDeleteMode(true);
    state.workspaceId = workspaceId; state.path = '.'; state.selected = null; state.preview = null; setMobileSurface('browser'); await loadDirectory('in');
  }
  const depth = (path) => (path === '.' ? 0 : path.split('/').length);
  async function openPath(path) {
    leaveDeleteMode(true);
    const next = path || '.', motion = depth(next) < depth(state.path) ? 'back' : 'forward';
    state.path = next; state.selected = null; state.preview = null; setMobileSurface('browser'); await loadDirectory(motion);
  }
  // `motion` names how the new listing arrives: 'forward' into a folder, 'back' out of one, 'in' as a fresh list.
  // Without it (after a change on the same folder) the listing is updated where it stands.
  async function loadDirectory(motion) {
    const requestId = ++state.requestId;
    state.loading = !!motion;
    render();
    try {
      const payload = await request(`/list?workspace_id=${encode(state.workspaceId)}&path=${encode(state.path)}`);
      if (requestId !== state.requestId) return;
      state.path = payload.path || '.'; state.entries = payload.entries || []; state.loading = false; render();
      if (motion) {
        const list = state.root.querySelector('.files-list');
        list.classList.remove('is-in-forward', 'is-in-back', 'is-in-in');
        restart(list, `is-in-${motion}`);
      }
    } catch (error) { if (requestId === state.requestId) { state.entries = []; state.loading = false; render(); notify(error.message, 'error'); } }
  }
  async function openEntry(path, type) {
    if (type === 'dir') { await openPath(path); return; }
    const kind = mediaKind(path);
    if (kind) {
      // The browser streams these itself; nothing is read as text first.
      const workspace = currentWorkspace(), entry = state.entries.find((item) => item.path === path) || {};
      ++state.requestId; state.selected = path; state.opening = null;
      state.preview = { path, size: entry.size, preview_kind: workspace && workspace.read_only ? 'remote_media' : kind };
      setMobileSurface('preview'); render(); return;
    }
    const requestId = ++state.requestId; state.selected = path; state.opening = path;
    const inspector = state.root.querySelector('.files-inspector-stage');
    const lines = inspector && inspector.firstElementChild;
    render();
    // The file's lines stand as placeholders until it is written in, then cross-fade into it.
    const token = window.SkeletonEntrance && inspector ? window.SkeletonEntrance.start(inspector, { shape: 'doc', hide: [lines] }) : 0;
    const settle = () => { state.opening = null; render(); };
    try {
      const payload = await request(`/read?workspace_id=${encode(state.workspaceId)}&path=${encode(path)}`);
      if (requestId !== state.requestId) return;
      state.preview = payload; state.selected = path; setMobileSurface('preview'); settle();
      if (token) window.SkeletonEntrance.reveal(inspector, token);
    } catch (error) {
      if (requestId !== state.requestId) return;
      if (token) window.SkeletonEntrance.cancel(inspector);
      state.preview = null; settle(); notify(error.message, 'error');
    }
  }
  async function post(path, body) { return request(path, { method: 'POST', body: JSON.stringify(body) }); }
  async function dispatchAction(action) {
    const workspace = currentWorkspace(); if (!workspace) return;
    try {
      if (action === 'up') return openPath(parentPath(state.path));
      if (action === 'close-preview') { state.selected = null; state.preview = null; setMobileSurface('browser'); render(); return; }
      if (action === 'new-file' || action === 'new-folder') {
        const label = action === 'new-file' ? 'New file' : 'New folder'; const name = await window.showPromptDialog({ title: label, message: `Name the ${action === 'new-file' ? 'file' : 'folder'}.`, placeholder: action === 'new-file' ? 'notes.md' : 'folder-name', confirmLabel: 'Create' });
        if (!name || !String(name).trim()) return;
        const path = state.path === '.' ? String(name).trim() : `${state.path}/${String(name).trim()}`;
        await post(action === 'new-file' ? '/create' : '/create-dir', { workspace_id: workspace.id, path }); await loadDirectory(); notify(`${label} created`, 'success'); return;
      }
      if (action === 'delete-mode') { if (state.deleteMode) leaveDeleteMode(); else enterDeleteMode(); return; }
      if (action === 'pick-all') { const paths = visiblePaths(); const all = state.picked.size === paths.length; state.picked = new Set(all ? [] : paths); state.root.querySelectorAll('.files-list .files-row[data-file-path]').forEach((row) => { row.classList.toggle('is-picked', !all); row.setAttribute('aria-pressed', String(!all)); }); syncPicked(); return; }
      if (action === 'delete-picked') { await deletePicked(); return; }
      if (!state.preview) return;
      if (action === 'save') { const editor = state.root.querySelector('.files-editor'); await post('/save', { workspace_id: workspace.id, path: state.preview.path, content: editor ? editor.value : '' }); state.preview.content = editor ? editor.value : state.preview.content; notify('Changes saved', 'success'); return; }
      if (action === 'rename') { const name = await window.showPromptDialog({ title: 'Rename file', message: 'Choose a new name.', value: state.preview.path.split('/').pop(), selectAll: true, confirmLabel: 'Rename' }); if (!name || !String(name).trim()) return; const response = await post('/rename', { workspace_id: workspace.id, path: state.preview.path, new_name: String(name).trim() }); state.preview.path = response.path; state.selected = response.path; await loadDirectory(); await openEntry(response.path, 'file'); return; }
      if (action === 'move') { const destination = await window.showPromptDialog({ title: 'Move file', message: 'Enter a folder path inside this workspace. Use . for the workspace root.', value: state.path, selectAll: true, confirmLabel: 'Move' }); if (destination == null) return; const response = await post('/move', { workspace_id: workspace.id, path: state.preview.path, destination: String(destination).trim() || '.' }); state.preview.path = response.path; state.selected = response.path; await openPath(response.parent_path); await openEntry(response.path, 'file'); return; }
      if (action === 'delete') { const agreed = await window.showConfirmDialog({ title: 'Delete file?', message: `“${state.preview.path}” will be permanently deleted.`, confirmLabel: 'Delete', danger: true, focusCancel: true }); if (!agreed) return; await post('/delete', { workspace_id: workspace.id, path: state.preview.path }); if (typeof window.animateRemoval === 'function') await window.animateRemoval(document.querySelector(`.files-row[data-file-path="${CSS.escape(state.preview.path)}"]`)); state.selected = null; state.preview = null; setMobileSurface('browser'); await loadDirectory(); notify('File deleted', 'success'); return; }
      if (action === 'download' && !workspace.read_only) { const link = document.createElement('a'); link.href = rawUrl(state.preview.path, true); link.download = state.preview.path.split('/').pop() || 'download'; document.body.append(link); link.click(); link.remove(); return; }
      if (action === 'download') { const response = await fetch(endpoint(`/download?workspace_id=${encode(workspace.id)}&path=${encode(state.preview.path)}`)); if (!response.ok) throw new Error('Download failed'); const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = state.preview.path.split('/').pop() || 'download'; link.click(); URL.revokeObjectURL(url); }
    } catch (error) { notify(error.message || 'Files action failed', 'error'); }
  }
  // While the page is open, each space's dot follows whether it can be reached: a drive that is unplugged
  // or a host that drops off turns red within one poll, and green again when it comes back.
  const STATUS_POLL_MS = 15000;
  let statusTimer = 0;
  async function pollStatus() {
    if (!state.mounted || document.visibilityState !== 'visible') return;
    try {
      const payload = await request('/workspaces');
      if (!state.mounted) return;
      const now = new Map((payload.workspaces || []).map((item) => [item.id, item]));
      if (state.workspaces.length !== now.size || state.workspaces.some((item) => !now.has(item.id))) { state.workspaces = payload.workspaces || []; render(); return; }
      let changed = false;
      state.workspaces = state.workspaces.map((item) => { const next = now.get(item.id); if (next.available !== item.available) changed = true; return next; });
      if (changed) render();
    } catch (_) { /* the next poll tries again */ }
  }
  function startStatusPoll() { clearInterval(statusTimer); statusTimer = setInterval(pollStatus, STATUS_POLL_MS); }
  // Coming back to the tab is when a stale dot is most likely, so it checks at once.
  document.addEventListener('visibilitychange', () => { if (state.mounted && document.visibilityState === 'visible') pollStatus(); });
  function onMediaLoad(event) {
    const img = event.target;
    if (!img || img.tagName !== 'IMG' || !img.closest('.files-media-image')) return;
    img.classList.add('is-loaded');
    const size = state.root && state.root.querySelector('.files-image-size');
    if (size && img.naturalWidth) size.textContent = ` · ${img.naturalWidth} × ${img.naturalHeight}`;
  }
  function onMediaError(event) {
    const media = event.target;
    if (!media || !media.closest || !media.closest('.files-media')) return;
    media.closest('.files-media').classList.add('is-broken');
  }
  function mount() {
    state.root = document.getElementById('fileManagerRoot');
    if (!state.root) return;
    state.mounted = true;
    startStatusPoll();
    state.root.classList.add('files-mounted');
    if (!state.dragWired) {
      state.dragWired = true;
      state.root.addEventListener('dragstart', onDragStart);
      state.root.addEventListener('dragover', onDragOver);
      state.root.addEventListener('drop', onDrop);
      state.root.addEventListener('dragend', onDragEnd);
      state.root.addEventListener('load', onMediaLoad, true);
      state.root.addEventListener('error', onMediaError, true);
      state.root.addEventListener('dragleave', (event) => { if (!state.root.contains(event.relatedTarget)) clearDropTarget(); });
    }
    wire(state.root);
    wire(document.getElementById('filesSidebarHost'));
    if (state.workspaces.length) { render(); refresh().catch(() => {}); return; }
    state.root.dataset.surface = 'browser';
    loadWorkspaces().catch((error) => { render(); notify(error.message, 'error'); });
  }
  function unmount() { leaveDeleteMode(true); clearInterval(statusTimer); state.mounted = false; state.requestId += 1; state.loading = false; state.opening = null; }
  window.HermesFileManager = { mount, unmount };
}());
