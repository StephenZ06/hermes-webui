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
  };

  const phoneWidth = window.matchMedia('(max-width:680px)');
  phoneWidth.addEventListener('change', () => { if (state.mounted) render(); });

  const icon = (paths) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
  const icons = {
    folder: icon('<path d="M3 7a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M3 10h18"/>'),
    file: icon('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h6"/>'),
    plus: icon('<path d="M12 5v14M5 12h14"/>'),
    upload: icon('<path d="M12 16V4M8 8l4-4 4 4"/><path d="M4 14v5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"/>'),
    back: icon('<path d="m15 18-6-6 6-6"/>'),
    download: icon('<path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 21h14"/>'),
    save: icon('<path d="M5 3h12l2 2v16H5z"/><path d="M8 3v6h8V3M8 21v-7h8v7"/>'),
    rename: icon('<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>'),
    move: icon('<path d="M7 7h10M13 3l4 4-4 4M17 17H7M11 13l-4 4 4 4"/>'),
    trash: icon('<path d="M3 6h18M8 6V4h8v2m-9 0 1 15h8l1-15"/>'),
    close: icon('<path d="m18 6-12 12M6 6l12 12"/>'),
    search: icon('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>'),
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
      <section class="files-browser" aria-label="File browser"><header class="files-toolbar"><button type="button" class="files-icon-btn files-up" data-action="up" aria-label="Parent folder">${icons.back}</button><div class="files-title"></div><div class="files-toolbar-actions"></div></header><nav class="files-path" aria-label="Folder path"><div class="files-breadcrumb"></div></nav><div class="files-list-toolbar"><label class="files-search"><span>${icons.search}</span><input type="search" placeholder="Filter this folder" aria-label="Filter files"></label><span class="files-item-count"></span></div><div class="files-list" role="list"></div></section>
      <aside class="files-inspector" aria-label="File inspector"><div class="files-inspector-stage"><div class="files-inspector-content"></div></div></aside>
    </div>`;
    layout = state.root.firstElementChild;
    const filter = layout.querySelector('.files-search input');
    filter.value = state.filter;
    filter.addEventListener('input', () => { state.filter = filter.value; render(); });
    return layout;
  }
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
    const listRows = visibleEntries.length ? visibleEntries.map((entry) => {
      const selected = state.selected === entry.path;
      const isDir = entry.type === 'dir' || entry.is_dir;
      return `<button type="button" class="files-row${selected ? ' is-selected' : ''}" data-file-path="${esc(entry.path)}" data-file-type="${esc(entry.type || '')}"${readOnly ? '' : ' draggable="true"'}>
        <span class="files-row-icon">${isDir ? icons.folder : icons.file}</span><span class="files-row-name">${esc(entry.name)}</span>
        <span class="files-row-meta">${isDir ? 'Folder' : prettySize(entry.size)}</span>
      </button>`;
    }).join('') : `<div class="files-empty-list">${state.filter ? 'No matching files' : 'This folder is empty'}</div>`;
    const previewMarkup = !state.preview
      ? `<div class="files-inspector-empty">${icons.file}<strong>Select a file</strong><span>Choose a file to preview, edit, rename, download, or remove it.</span></div>`
      : `<div class="files-inspector-header"><div><div class="files-inspector-name">${esc(state.preview.path)}</div><div class="files-inspector-meta">${prettySize(state.preview.size)} · ${state.preview.lines || 1} line${state.preview.lines === 1 ? '' : 's'}${readOnly ? ' · Read only' : ''}</div></div><div class="files-inspector-actions">
          <button type="button" class="files-icon-btn" data-action="download" title="Download">${icons.download}</button>
          ${readOnly ? '' : `<button type="button" class="files-icon-btn" data-action="rename" title="Rename">${icons.rename}</button><button type="button" class="files-icon-btn" data-action="move" title="Move">${icons.move}</button><button type="button" class="files-icon-btn files-icon-btn-danger" data-action="delete" title="Delete">${icons.trash}</button>`}
          <button type="button" class="files-icon-btn" data-action="close-preview" title="Close preview">${icons.close}</button></div></div>
        <div class="files-preview-wrap">${isTextPreview()
          ? `<textarea class="files-editor" aria-label="File contents" ${readOnly ? 'readonly' : ''}>${esc(state.preview.content)}</textarea>${readOnly ? '' : `<button type="button" class="files-save" data-action="save">${icons.save}<span>Save changes</span></button>`}`
          : `<div class="files-preview-unavailable">${icons.file}<strong>Preview unavailable</strong><span>This format cannot be edited here. Download it to open it locally.</span></div>`}</div>`;
    // The list of spaces stands in the Files side panel. A phone has no side panel on screen, so there it
    // stays the first of the sliding surfaces.
    const spacesMarkup = `<aside class="files-workspaces" aria-label="Connected workspaces"><div class="files-section-heading">Connected spaces</div><div class="files-workspace-list" data-mi-hover=".files-workspace">${state.workspaces.map((item) => `<button type="button" class="files-workspace${item.id === state.workspaceId ? ' is-active' : ''}" data-workspace-id="${esc(item.id)}"><span class="files-workspace-dot ${item.available ? 'is-online' : 'is-offline'}"></span><span>${esc(item.name)}</span>${item.read_only ? '<span class="files-read-only-tag">Read only</span>' : ''}</button>`).join('') || '<div class="files-empty-list">No connected spaces</div>'}</div><p class="files-sidebar-caption">Files stays inside the workspaces Hermes already knows.</p></aside>`;
    const sideHost = document.getElementById('filesSidebarHost');
    const spacesHost = layout.dataset.spaces === 'side-panel' ? sideHost : layout.querySelector('.files-spaces-slot');
    if (write(spacesHost, spacesMarkup) && window.Micro) window.Micro.scan(spacesHost);
    if (sideHost && spacesHost !== sideHost) write(sideHost, '');
    layout.dataset.readOnly = readOnly ? 'true' : 'false';
    layout.dataset.hasPreview = state.preview || state.opening ? 'true' : 'false';
    layout.dataset.surface = state.root.dataset.surface || 'browser';
    layout.querySelector('.files-up').disabled = state.path === '.';
    showTitle(layout.querySelector('.files-title'), state.path === '.' ? (workspace ? workspace.name : 'Files') : crumbs[crumbs.length - 1], workspace);
    showPath(layout.querySelector('.files-path'), crumbMarkup);
    write(layout.querySelector('.files-toolbar-actions'), readOnly ? '<span class="files-read-only-tag">Read only</span>' : `<button type="button" class="files-action" data-action="new-file" aria-label="New file"><i class="files-mask files-mask-file"></i></button><button type="button" class="files-action" data-action="new-folder" aria-label="New folder"><i class="files-mask files-mask-folder"></i></button><button type="button" class="files-action" data-action="upload" aria-label="Upload">${icons.upload}</button>`);
    layout.querySelector('.files-item-count').textContent = `${visibleEntries.length} item${visibleEntries.length === 1 ? '' : 's'}`;
    const list = layout.querySelector('.files-list');
    list.classList.toggle('is-loading', state.loading);
    write(list, listRows);
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
    state.workspaceId = workspaceId; state.path = '.'; state.selected = null; state.preview = null; setMobileSurface('browser'); await loadDirectory('in');
  }
  const depth = (path) => (path === '.' ? 0 : path.split('/').length);
  async function openPath(path) {
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
      if (action === 'upload') { const input = document.createElement('input'); input.type = 'file'; input.multiple = true; input.onchange = () => uploadFiles([...input.files], state.path).catch((error) => notify(error.message || 'Upload failed', 'error')); input.click(); return; }
      if (!state.preview) return;
      if (action === 'save') { const editor = state.root.querySelector('.files-editor'); await post('/save', { workspace_id: workspace.id, path: state.preview.path, content: editor ? editor.value : '' }); state.preview.content = editor ? editor.value : state.preview.content; notify('Changes saved', 'success'); return; }
      if (action === 'rename') { const name = await window.showPromptDialog({ title: 'Rename file', message: 'Choose a new name.', value: state.preview.path.split('/').pop(), selectAll: true, confirmLabel: 'Rename' }); if (!name || !String(name).trim()) return; const response = await post('/rename', { workspace_id: workspace.id, path: state.preview.path, new_name: String(name).trim() }); state.preview.path = response.path; state.selected = response.path; await loadDirectory(); await openEntry(response.path, 'file'); return; }
      if (action === 'move') { const destination = await window.showPromptDialog({ title: 'Move file', message: 'Enter a folder path inside this workspace. Use . for the workspace root.', value: state.path, selectAll: true, confirmLabel: 'Move' }); if (destination == null) return; const response = await post('/move', { workspace_id: workspace.id, path: state.preview.path, destination: String(destination).trim() || '.' }); state.preview.path = response.path; state.selected = response.path; await openPath(response.parent_path); await openEntry(response.path, 'file'); return; }
      if (action === 'delete') { const agreed = await window.showConfirmDialog({ title: 'Delete file?', message: `“${state.preview.path}” will be permanently deleted.`, confirmLabel: 'Delete', danger: true, focusCancel: true }); if (!agreed) return; await post('/delete', { workspace_id: workspace.id, path: state.preview.path }); if (typeof window.animateRemoval === 'function') await window.animateRemoval(document.querySelector(`.files-row[data-file-path="${CSS.escape(state.preview.path)}"]`)); state.selected = null; state.preview = null; setMobileSurface('browser'); await loadDirectory(); notify('File deleted', 'success'); return; }
      if (action === 'download') { const response = await fetch(endpoint(`/download?workspace_id=${encode(workspace.id)}&path=${encode(state.preview.path)}`)); if (!response.ok) throw new Error('Download failed'); const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = state.preview.path.split('/').pop() || 'download'; link.click(); URL.revokeObjectURL(url); }
    } catch (error) { notify(error.message || 'Files action failed', 'error'); }
  }
  function mount() {
    state.root = document.getElementById('fileManagerRoot');
    if (!state.root) return;
    state.mounted = true;
    state.root.classList.add('files-mounted');
    if (!state.dragWired) {
      state.dragWired = true;
      state.root.addEventListener('dragstart', onDragStart);
      state.root.addEventListener('dragover', onDragOver);
      state.root.addEventListener('drop', onDrop);
      state.root.addEventListener('dragend', onDragEnd);
      state.root.addEventListener('dragleave', (event) => { if (!state.root.contains(event.relatedTarget)) clearDropTarget(); });
    }
    wire(state.root);
    wire(document.getElementById('filesSidebarHost'));
    if (state.workspaces.length) { render(); refresh().catch(() => {}); return; }
    state.root.dataset.surface = 'browser';
    loadWorkspaces().catch((error) => { render(); notify(error.message, 'error'); });
  }
  function unmount() { state.mounted = false; state.requestId += 1; state.loading = false; state.opening = null; }
  window.HermesFileManager = { mount, unmount };
}());
