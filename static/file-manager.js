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
    requestId: 0,
    mounted: false,
  };

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
  function render() {
    if (!state.root) return;
    state.root.dataset.hasPreview = state.preview ? 'true' : 'false';
    const workspace = currentWorkspace();
    const visibleEntries = state.entries.filter((entry) => !state.filter || String(entry.name || '').toLowerCase().includes(state.filter.toLowerCase()));
    const readOnly = !workspace || workspace.read_only;
    const crumbs = state.path === '.' ? [] : state.path.split('/');
    const crumbMarkup = [`<button type="button" class="files-crumb" data-path=".">Workspace</button>`]
      .concat(crumbs.map((part, index) => `<span class="files-crumb-separator">/</span><button type="button" class="files-crumb" data-path="${esc(crumbs.slice(0, index + 1).join('/'))}">${esc(part)}</button>`)).join('');
    const listRows = visibleEntries.length ? visibleEntries.map((entry) => {
      const selected = state.selected === entry.path;
      const entryIcon = entry.type === 'dir' || entry.is_dir ? icons.folder : icons.file;
      return `<button type="button" class="files-row${selected ? ' is-selected' : ''}" data-file-path="${esc(entry.path)}" data-file-type="${esc(entry.type || '')}">
        <span class="files-row-icon">${entryIcon}</span><span class="files-row-name">${esc(entry.name)}</span>
        <span class="files-row-meta">${entry.type === 'dir' || entry.is_dir ? 'Folder' : prettySize(entry.size)}</span>
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
    state.root.innerHTML = `<div class="file-manager-layout" data-read-only="${readOnly ? 'true' : 'false'}" data-has-preview="${state.preview ? 'true' : 'false'}" data-surface="${esc(state.root.dataset.surface || 'browser')}">
      <aside class="files-workspaces" aria-label="Connected workspaces"><div class="files-section-heading">Connected spaces</div><div class="files-workspace-list">${state.workspaces.map((item) => `<button type="button" class="files-workspace${item.id === state.workspaceId ? ' is-active' : ''}" data-workspace-id="${esc(item.id)}"><span class="files-workspace-dot ${item.available ? 'is-online' : 'is-offline'}"></span><span>${esc(item.name)}</span>${item.read_only ? '<span class="files-read-only-tag">Read only</span>' : ''}</button>`).join('') || '<div class="files-empty-list">No connected spaces</div>'}</div><p class="files-sidebar-caption">Files stays inside the workspaces Hermes already knows.</p></aside>
      <section class="files-browser" aria-label="File browser"><header class="files-toolbar"><div class="files-breadcrumb">${state.path !== '.' ? `<button type="button" class="files-icon-btn" data-action="up" title="Parent folder">${icons.back}</button>` : ''}${crumbMarkup}</div><div class="files-toolbar-actions">${readOnly ? '<span class="files-read-only-tag">Read only</span>' : `<button type="button" class="files-action" data-action="new-file">${icons.plus}<span>New file</span></button><button type="button" class="files-action" data-action="new-folder">${icons.plus}<span>New folder</span></button><button type="button" class="files-action" data-action="upload">${icons.upload}<span>Upload</span></button>`}</div></header><div class="files-list-toolbar"><label class="files-search"><span>${icons.file}</span><input type="search" placeholder="Filter this folder" value="${esc(state.filter)}" aria-label="Filter files"></label><span class="files-item-count">${visibleEntries.length} item${visibleEntries.length === 1 ? '' : 's'}</span></div><div class="files-list" role="list">${listRows}</div></section>
      <aside class="files-inspector" aria-label="File inspector">${previewMarkup}</aside>
    </div>`;
    bindEvents();
  }
  function bindEvents() {
    state.root.querySelectorAll('[data-workspace-id]').forEach((button) => button.addEventListener('click', () => openWorkspace(button.dataset.workspaceId)));
    state.root.querySelectorAll('[data-path]').forEach((button) => button.addEventListener('click', () => openPath(button.dataset.path)));
    state.root.querySelectorAll('[data-file-path]').forEach((button) => button.addEventListener('click', () => openEntry(button.dataset.filePath, button.dataset.fileType)));
    const filter = state.root.querySelector('.files-search input');
    if (filter) filter.addEventListener('input', () => { state.filter = filter.value; render(); });
    state.root.querySelectorAll('[data-action]').forEach((button) => button.addEventListener('click', () => dispatchAction(button.dataset.action)));
  }
  async function loadWorkspaces() {
    const payload = await request('/workspaces');
    state.workspaces = payload.workspaces || [];
    if (!state.workspaces.some((item) => item.id === state.workspaceId)) state.workspaceId = (state.workspaces.find((item) => item.available) || state.workspaces[0] || {}).id || '';
    state.path = '.'; state.entries = []; state.selected = null; state.preview = null;
    if (state.workspaceId) await loadDirectory(); else render();
  }
  async function openWorkspace(workspaceId) {
    if (!workspaceId || workspaceId === state.workspaceId) return;
    state.workspaceId = workspaceId; state.path = '.'; state.entries = []; state.selected = null; state.preview = null; setMobileSurface('browser'); await loadDirectory();
  }
  async function openPath(path) { state.path = path || '.'; state.selected = null; state.preview = null; setMobileSurface('browser'); await loadDirectory(); }
  async function loadDirectory() {
    const requestId = ++state.requestId;
    render();
    try {
      const payload = await request(`/list?workspace_id=${encode(state.workspaceId)}&path=${encode(state.path)}`);
      if (requestId !== state.requestId) return;
      state.path = payload.path || '.'; state.entries = payload.entries || []; render();
    } catch (error) { if (requestId === state.requestId) { state.entries = []; render(); notify(error.message, 'error'); } }
  }
  async function openEntry(path, type) {
    if (type === 'dir') { await openPath(path); return; }
    const requestId = ++state.requestId; state.selected = path; render();
    try {
      const payload = await request(`/read?workspace_id=${encode(state.workspaceId)}&path=${encode(path)}`);
      if (requestId !== state.requestId) return;
      state.preview = payload; state.selected = path; setMobileSurface('preview'); render();
    } catch (error) { if (requestId === state.requestId) { state.preview = null; render(); notify(error.message, 'error'); } }
  }
  async function prompt(options) { return typeof window.showPromptDialog === 'function' ? window.showPromptDialog(options) : window.prompt(options.message || options.title || '', options.value || ''); }
  async function confirm(options) { return typeof window.showConfirmDialog === 'function' ? window.showConfirmDialog(options) : window.confirm(options.message || options.title || 'Continue?'); }
  async function post(path, body) { return request(path, { method: 'POST', body: JSON.stringify(body) }); }
  async function dispatchAction(action) {
    const workspace = currentWorkspace(); if (!workspace) return;
    try {
      if (action === 'up') return openPath(parentPath(state.path));
      if (action === 'close-preview') { state.selected = null; state.preview = null; setMobileSurface('browser'); render(); return; }
      if (action === 'new-file' || action === 'new-folder') {
        const label = action === 'new-file' ? 'New file' : 'New folder'; const name = await prompt({ title: label, message: `Name the ${action === 'new-file' ? 'file' : 'folder'}.`, placeholder: action === 'new-file' ? 'notes.md' : 'folder-name', confirmLabel: 'Create' });
        if (!name || !String(name).trim()) return;
        const path = state.path === '.' ? String(name).trim() : `${state.path}/${String(name).trim()}`;
        await post(action === 'new-file' ? '/create' : '/create-dir', { workspace_id: workspace.id, path }); await loadDirectory(); notify(`${label} created`, 'success'); return;
      }
      if (action === 'upload') { const input = document.createElement('input'); input.type = 'file'; input.onchange = async () => { const file = input.files && input.files[0]; if (!file) return; if (file.size > 25 * 1024 * 1024) { notify('Files must be 25 MB or smaller', 'error'); return; } const data = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = reject; reader.readAsDataURL(file); }); await post('/upload', { workspace_id: workspace.id, path: state.path, filename: file.name, data_base64: data }); await loadDirectory(); notify(`${file.name} uploaded`, 'success'); }; input.click(); return; }
      if (!state.preview) return;
      if (action === 'save') { const editor = state.root.querySelector('.files-editor'); await post('/save', { workspace_id: workspace.id, path: state.preview.path, content: editor ? editor.value : '' }); state.preview.content = editor ? editor.value : state.preview.content; notify('Changes saved', 'success'); return; }
      if (action === 'rename') { const name = await prompt({ title: 'Rename file', message: 'Choose a new name.', value: state.preview.path.split('/').pop(), selectAll: true, confirmLabel: 'Rename' }); if (!name || !String(name).trim()) return; const response = await post('/rename', { workspace_id: workspace.id, path: state.preview.path, new_name: String(name).trim() }); state.preview.path = response.path; state.selected = response.path; await loadDirectory(); await openEntry(response.path, 'file'); return; }
      if (action === 'move') { const destination = await prompt({ title: 'Move file', message: 'Enter a folder path inside this workspace. Use . for the workspace root.', value: state.path, selectAll: true, confirmLabel: 'Move' }); if (destination == null) return; const response = await post('/move', { workspace_id: workspace.id, path: state.preview.path, destination: String(destination).trim() || '.' }); state.preview.path = response.path; state.selected = response.path; await openPath(response.parent_path); await openEntry(response.path, 'file'); return; }
      if (action === 'delete') { const agreed = await confirm({ title: 'Delete file?', message: `“${state.preview.path}” will be permanently deleted.`, confirmLabel: 'Delete', danger: true, focusCancel: true }); if (!agreed) return; await post('/delete', { workspace_id: workspace.id, path: state.preview.path }); state.selected = null; state.preview = null; setMobileSurface('browser'); await loadDirectory(); notify('File deleted', 'success'); return; }
      if (action === 'download') { const response = await fetch(endpoint(`/download?workspace_id=${encode(workspace.id)}&path=${encode(state.preview.path)}`)); if (!response.ok) throw new Error('Download failed'); const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = state.preview.path.split('/').pop() || 'download'; link.click(); URL.revokeObjectURL(url); }
    } catch (error) { notify(error.message || 'Files action failed', 'error'); }
  }
  function mount() { state.root = document.getElementById('fileManagerRoot'); if (!state.root) return; state.mounted = true; state.root.classList.add('files-mounted'); state.root.dataset.surface = 'browser'; loadWorkspaces().catch((error) => { render(); notify(error.message, 'error'); }); }
  function unmount() { state.mounted = false; state.requestId += 1; }
  window.HermesFileManager = { mount, unmount };
}());
