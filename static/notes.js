// Notes panel: multiple sticky-note boards (static/vendor/sticky-board/,
// api/sticky_board.py), each optionally linked to a Project folder (the
// same Projects the Chat sidebar's project-folder rows use). Linking a
// board mirrors its content into that project's workspace AGENTS.md (see
// api/sticky_board.py's docstring) so project chats can see it.
//
// This module renders the same data into two places: the full Notes sidebar
// panel (#panelNotes) and the compact Notes view inside the workspace panel
// (#workspacePlanePane). Both stay in sync through the shared state below.

let _notesProjects = [];
let _notesBoards = [];
let _notesActiveProjectFilter = null; // null = "All"
let _notesActiveBoardId = null;
let _notesPickerEl = null; // the one open move-to-project/board-actions picker, if any
let _notesBoardSearchTerm = '';
let _notesDataRefreshGeneration = 0;
const _workspaceNotesSelectedBoards = new Map();

const NOTES_VIEWS = {
  panel: { foldersId: 'notesProjectFolders', searchId: 'notesBoardSearch', listId: 'notesBoardsList' },
  workspace: { searchId: 'workspaceNotesBoardSearch', listId: 'workspaceNotesBoardsList' },
};

async function _refreshNotesPanelData() {
  const refreshGeneration = ++_notesDataRefreshGeneration;
  try {
    const [projectsRes, boardsRes] = await Promise.all([
      api('/api/projects?all_profiles=1'),
      api('/api/sticky_boards'),
    ]);
    if (refreshGeneration !== _notesDataRefreshGeneration) return false;
    _notesProjects = (projectsRes && projectsRes.projects) || [];
    _notesBoards = (boardsRes && boardsRes.boards) || [];
    return true;
  } catch (e) {
    if (refreshGeneration !== _notesDataRefreshGeneration) return false;
    console.error('loadNotesPanel failed', e);
    _notesProjects = _notesProjects || [];
    _notesBoards = _notesBoards || [];
    return false;
  }
}

async function loadNotesPanel() {
  await _refreshNotesPanelData();
  _restoreOrSelectStickyBoard();
  _renderWorkspaceNotesPane();
}

// "All boards" means the general pool (no project_id) -- a board linked to
// a project only shows up under that project's own folder filter, never in
// both places at once.
function _filteredNotesBoards() {
  return _notesActiveProjectFilter === null
    ? _notesBoards.filter(b => !b.project_id)
    : _notesBoards.filter(b => b.project_id === _notesActiveProjectFilter);
}

function _setNotesProjectFilter(projectId) {
  _notesActiveProjectFilter = projectId;
  _renderAllNotesViews();
  const filtered = _filteredNotesBoards();
  // Switching folders must never leave the previous folder's board showing
  // just because the new folder happens to have none of its own -- always
  // land on a board that's actually IN the new filter (or the empty state).
  if (!filtered.some(b => b.id === _notesActiveBoardId)) {
    selectStickyBoard(filtered.length ? filtered[0].id : null);
  } else {
    _renderNotesBoardsLists();
  }
}

function _restoreOrSelectStickyBoard() {
  let target = null;
  try { target = localStorage.getItem(NOTES_LAST_BOARD_KEY); } catch (e) { /* ignore */ }
  const board = target ? _notesBoards.find(b => b.id === target) : null;
  // Restore into whichever folder the last-open board actually belongs to,
  // so the active filter chip and the shown board never disagree.
  _notesActiveProjectFilter = board ? (board.project_id || null) : null;
  _renderAllNotesViews();
  const filtered = _filteredNotesBoards();
  selectStickyBoard(board ? board.id : (filtered.length ? filtered[0].id : null));
}

function _notesProjectById(projectId) {
  return _notesProjects.find(p => p.project_id === projectId) || null;
}

function _renderAllNotesViews() {
  _renderNotesProjectFolders('panel');
}

function _renderNotesBoardsLists() {
  _renderNotesBoardsList('panel');
  _renderWorkspaceNotesPane();
}

// ── Project folder filter row ──
function _renderNotesProjectFolders(view) {
  const cfg = NOTES_VIEWS[view];
  const container = $(cfg.foldersId);
  if (!container) return;
  container.innerHTML = '';

  const bar = document.createElement('div');
  bar.className = 'project-folder-list';

  const allChip = document.createElement('span');
  allChip.className = 'project-chip project-folder-row' + (_notesActiveProjectFilter === null ? ' active' : '');
  allChip.textContent = 'All boards';
  allChip.onclick = () => _setNotesProjectFilter(null);
  bar.appendChild(allChip);

  for (const p of _notesProjects) {
    const chip = document.createElement('span');
    chip.className = 'project-chip project-folder-row' + (_notesActiveProjectFilter === p.project_id ? ' active' : '');
    if (p.color) {
      const dot = document.createElement('span');
      dot.className = 'color-dot';
      dot.style.background = p.color;
      chip.appendChild(dot);
    }
    const nameSpan = document.createElement('span');
    nameSpan.className = 'project-folder-name';
    nameSpan.textContent = p.name || p.project_id;
    chip.appendChild(nameSpan);
    const count = _notesBoards.filter(b => b.project_id === p.project_id).length;
    const countSpan = document.createElement('span');
    countSpan.className = 'project-folder-count';
    countSpan.textContent = String(count);
    chip.appendChild(countSpan);
    chip.onclick = () => _setNotesProjectFilter(p.project_id);
    bar.appendChild(chip);
  }
  container.appendChild(bar);
}

// ── Boards list ──
function _renderNotesBoardsList(view) {
  const cfg = NOTES_VIEWS[view];
  const list = $(cfg.listId);
  if (!list) return;
  list.innerHTML = '';
  const term = _notesBoardSearchTerm;
  const boards = _filteredNotesBoards().filter(b => !term || (b.name || '').toLowerCase().includes(term));

  if (!boards.length) {
    const empty = document.createElement('div');
    empty.className = 'notes-boards-empty';
    empty.textContent = term ? 'No boards match your search.' : 'No boards yet. Click + above to create one.';
    list.appendChild(empty);
    return;
  }

  for (const board of boards) {
    list.appendChild(_buildStickyBoardRow(board));
  }
}

function _notesEsc(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// `S` is declared with `const` in ui.js. Global lexical bindings are available
// to sibling scripts but are not properties on `window`, so using `window.S`
// silently lost the current chat context in this pane.
function _workspaceNotesSession() {
  return typeof S !== 'undefined' ? (S.session || null) : null;
}

function _workspaceNotesProjectId() {
  const session = _workspaceNotesSession();
  if (!session) return null;
  // A workspace can be inherited by a general chat. Its path must not make
  // that chat look like it belongs to a Project folder: the sidebar's own
  // project assignment is the authority for the Notes scope.
  return session.project_id || null;
}

function _workspaceFilteredBoards(projectId = _workspaceNotesProjectId()) {
  const pid = projectId;
  if (pid) return _notesBoards.filter(b => b.project_id === pid);
  // General chats own the general Notes pool. Project-linked boards are
  // intentionally excluded here; their task state belongs only to the chat
  // folder that carries the matching project_id.
  return _notesBoards.filter(b => !b.project_id);
}

function _workspaceNotesScopeKey(projectId = _workspaceNotesProjectId()) {
  return projectId || '__all__';
}

function _workspaceNotesSelectedBoard(projectId = _workspaceNotesProjectId()) {
  const selectedId = _workspaceNotesSelectedBoards.get(_workspaceNotesScopeKey(projectId));
  return _workspaceFilteredBoards(projectId).find(board => board.id === selectedId) || null;
}

function _selectWorkspaceNotesBoard(boardId, projectId = _workspaceNotesProjectId()) {
  const boards = _workspaceFilteredBoards(projectId);
  if (!boards.some(board => board.id === boardId)) return;
  _workspaceNotesSelectedBoards.set(_workspaceNotesScopeKey(projectId), boardId);
  _renderWorkspaceNotesPane(projectId);
}

function _renderWorkspaceNotesContext(projectId = _workspaceNotesProjectId()) {
  const container = $('workspaceNotesContext');
  if (!container) return;
  const pid = projectId;
  const project = pid ? _notesProjectById(pid) : null;
  const title = project ? (project.name || 'Project notes') : 'All boards';
  const subtitle = project ? 'Notes linked to this project' : 'Notes available to general chats';
  container.innerHTML = `<div class="workspace-notes-context-title">${_notesEsc(title)}</div>${subtitle ? `<div class="workspace-notes-context-sub">${_notesEsc(subtitle)}</div>` : ''}`;
}

function _renderWorkspaceNotesBoards(projectId = _workspaceNotesProjectId()) {
  const list = $('workspaceNotesBoardsList');
  if (!list) return;
  list.innerHTML = '';
  const term = _notesBoardSearchTerm;
  const boards = _workspaceFilteredBoards(projectId).filter(b => !term || (b.name || '').toLowerCase().includes(term));

  if (!boards.length) {
    const pid = projectId;
    const empty = document.createElement('div');
    empty.className = 'workspace-notes-empty';
    empty.textContent = pid
      ? 'No notes have been linked to this project yet.'
      : 'No boards yet.';
    list.appendChild(empty);
    return;
  }

  for (const board of boards) {
    list.appendChild(_buildWorkspaceNotesBoardSelector(board, projectId));
  }
}

function _buildWorkspaceNotesBoardSelector(board, projectId) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'sticky-board-row workspace-notes-board-selector' +
    (_workspaceNotesSelectedBoard(projectId)?.id === board.id ? ' active' : '');
  button.dataset.boardId = board.id;
  const project = board.project_id ? _notesProjectById(board.project_id) : null;
  if (project && project.color) {
    const dot = document.createElement('span');
    dot.className = 'color-dot';
    dot.style.background = project.color;
    button.appendChild(dot);
  }
  const name = document.createElement('span');
  name.className = 'sticky-board-row-name';
  name.textContent = board.name || 'Untitled board';
  button.appendChild(name);
  button.onclick = () => _selectWorkspaceNotesBoard(board.id, projectId);
  return button;
}

// Workspace preview of exactly the board selected in the active context.
function _renderWorkspaceNotesPreview(projectId = _workspaceNotesProjectId()) {
  const container = $('workspaceNotesBoardPreview');
  if (!container) return;
  container.innerHTML = '';
  const boards = _workspaceFilteredBoards(projectId);
  if (!boards.length) {
    container.innerHTML = '<div class="workspace-notes-preview-empty">No notes to preview for this context.</div>';
    return;
  }
  const board = _workspaceNotesSelectedBoard(projectId);
  if (!board) {
    container.innerHTML = '<div class="workspace-notes-preview-empty">Select a board above to view its notes.</div>';
    return;
  }

  const order = { general: 0, 'in-progress': 1, completed: 2 };
  const columns = board.columns || [];
  const sorted = columns.slice().sort((a, b) => (order[a.id] ?? 99) - (order[b.id] ?? 99));
  for (const col of sorted) {
    const colEl = document.createElement('div');
    colEl.className = 'workspace-notes-col';
    const header = document.createElement('div');
    header.className = 'workspace-notes-col-header';
    header.textContent = col.title || col.id;
    const count = document.createElement('span');
    count.className = 'workspace-notes-col-count';
    count.textContent = String((col.notes || []).length);
    header.appendChild(count);
    colEl.appendChild(header);
    for (const note of col.notes || []) {
      const subtasks = document.createElement('div');
      subtasks.className = 'workspace-notes-subtasks';
      for (const subTask of note.subItems || []) {
        const text = String(subTask || '').trim();
        if (!text) continue;
        const subEl = document.createElement('div');
        subEl.className = 'workspace-notes-subtask';
        subEl.textContent = text;
        subtasks.appendChild(subEl);
      }
      // Empty <details> synthesizes a browser-provided "Details" summary.
      // Use it only when there is genuinely something the title can reveal.
      const noteEl = document.createElement(subtasks.childElementCount ? 'details' : 'div');
      noteEl.className = 'workspace-notes-note';
      if (subtasks.childElementCount) {
        const summary = document.createElement('summary');
        summary.className = 'workspace-notes-note-summary';
        summary.textContent = note.title || 'New Note';
        noteEl.appendChild(summary);
        noteEl.appendChild(subtasks);
      } else {
        const title = document.createElement('div');
        title.className = 'workspace-notes-note-title';
        title.textContent = note.title || 'New Note';
        noteEl.appendChild(title);
      }
      colEl.appendChild(noteEl);
    }
    container.appendChild(colEl);
  }
}

function _renderWorkspaceNotesPane(projectId = _workspaceNotesProjectId()) {
  _renderWorkspaceNotesContext(projectId);
  _renderWorkspaceNotesBoards(projectId);
  _renderWorkspaceNotesPreview(projectId);
}

function _isWorkspaceNotesSessionCurrent(sessionId) {
  const session = _workspaceNotesSession();
  return !sessionId || !!(session && session.session_id === sessionId);
}

// Render the newly selected chat's known project context before waiting for
// board data. That immediately removes a previous project's boards on a
// session switch, even while the new transcript is still loading.
function renderWorkspaceNotesPaneForSession(options = {}) {
  const session = _workspaceNotesSession();
  const sessionId = options.sessionId || (session && session.session_id) || null;
  if (!_isWorkspaceNotesSessionCurrent(sessionId)) return;
  _renderWorkspaceNotesPane(_workspaceNotesProjectId());
}

// The docked workspace pane can be opened without visiting the full Notes
// page first. Fetch the board list, but bind both sides of that asynchronous
// refresh to the chat that requested it so an older project's response cannot
// overwrite a newer project selection.
async function refreshWorkspaceNotesPane(options = {}) {
  const session = _workspaceNotesSession();
  const sessionId = options.sessionId || (session && session.session_id) || null;
  if (!_isWorkspaceNotesSessionCurrent(sessionId)) return;
  await _refreshNotesPanelData();
  if (!_isWorkspaceNotesSessionCurrent(sessionId)) return;
  _renderWorkspaceNotesPane(_workspaceNotesProjectId());
}

function _buildStickyBoardRow(board) {
  const row = document.createElement('div');
  row.className = 'sticky-board-row' + (board.id === _notesActiveBoardId ? ' active' : '');
  row.dataset.boardId = board.id;

  const project = board.project_id ? _notesProjectById(board.project_id) : null;
  if (project && project.color) {
    const dot = document.createElement('span');
    dot.className = 'color-dot';
    dot.style.background = project.color;
    dot.title = project.name;
    row.appendChild(dot);
  }

  const nameEl = document.createElement('span');
  nameEl.className = 'sticky-board-row-name';
  nameEl.textContent = board.name;
  nameEl.title = project ? (board.name + ' — linked to ' + project.name) : board.name;
  nameEl.onclick = () => selectStickyBoard(board.id);
  row.appendChild(nameEl);

  const kebab = document.createElement('button');
  kebab.type = 'button';
  kebab.className = 'project-folder-kebab sticky-board-kebab';
  kebab.setAttribute('aria-label', 'Board actions');
  kebab.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/></svg>';
  kebab.onclick = (e) => { e.stopPropagation(); _showStickyBoardActions(board, kebab); };
  row.appendChild(kebab);

  return row;
}

let _stickyBoardFrameLoaded = false;

function selectStickyBoard(boardId) {
  _notesActiveBoardId = boardId;
  try {
    if (boardId) localStorage.setItem(NOTES_LAST_BOARD_KEY, boardId);
  } catch (e) { /* ignore */ }
  _renderNotesBoardsLists();
  const frame = $('stickyBoardFrame');
  if (!frame) return;
  if (_stickyBoardFrameLoaded && frame.contentWindow) {
    // Already loaded -- swap the shown board in place instead of
    // reassigning src, which would reload the whole iframe document (a
    // fresh network request and a visible flash) for what should be an
    // instant switch.
    frame.contentWindow.postMessage({ type: 'sticky-board:select', boardId: boardId }, location.origin);
    return;
  }
  if (!frame.dataset.loadListenerAttached) {
    frame.dataset.loadListenerAttached = '1';
    frame.addEventListener('load', () => { _stickyBoardFrameLoaded = true; });
  }
  frame.src = boardId
    ? 'static/vendor/sticky-board/index.html?board=' + encodeURIComponent(boardId)
    : 'static/vendor/sticky-board/index.html';
}

// ── Create / rename / delete / move-to-project ──
async function createStickyBoard() {
  const name = await showPromptDialog({ title: 'New board', message: 'Board name', placeholder: 'e.g. Sprint planning' });
  if (name === null) return;
  const project_id = _notesActiveProjectFilter || null;
  try {
    const res = await api('/api/sticky_boards/create', { method: 'POST', body: JSON.stringify({ name: name.trim() || 'New Board', project_id }) });
    if (res && res.board) {
      _notesBoards.push(res.board);
      _renderAllNotesViews();
      selectStickyBoard(res.board.id);
    }
  } catch (e) {
    console.error('createStickyBoard failed', e);
    showToast('Failed to create board');
  }
}

function _startStickyBoardRename(board, nameEl) {
  const input = document.createElement('input');
  input.className = 'project-create-input sticky-board-rename-input';
  input.value = board.name;
  nameEl.replaceWith(input);
  input.focus();
  input.select();

  const finish = async (save) => {
    input.removeEventListener('keydown', onKeydown);
    input.removeEventListener('blur', onBlur);
    const newName = input.value.trim();
    if (save && newName && newName !== board.name) {
      try {
        const res = await api('/api/sticky_boards/rename', { method: 'POST', body: JSON.stringify({ id: board.id, name: newName }) });
        if (res && res.board) board.name = res.board.name;
      } catch (e) {
        console.error('renameStickyBoard failed', e);
      }
    }
    _renderNotesBoardsLists();
  };
  const onKeydown = (e) => {
    if (e.key === 'Enter') { e.preventDefault(); finish(true); }
    else if (e.key === 'Escape') { e.preventDefault(); finish(false); }
  };
  const onBlur = () => finish(true);
  input.addEventListener('keydown', onKeydown);
  input.addEventListener('blur', onBlur);
}

function _closeStickyBoardPicker() {
  if (_notesPickerEl) { _notesPickerEl.remove(); _notesPickerEl = null; }
  document.removeEventListener('click', _closeStickyBoardPicker);
}

function _showStickyBoardActions(board, anchorEl) {
  _closeStickyBoardPicker();
  const picker = document.createElement('div');
  picker.className = 'project-picker';

  const renameItem = document.createElement('div');
  renameItem.className = 'project-picker-item';
  renameItem.textContent = 'Rename';
  renameItem.onclick = (e) => {
    e.stopPropagation();
    _closeStickyBoardPicker();
    const row = anchorEl.closest('.sticky-board-row');
    const nameEl = row && row.querySelector('.sticky-board-row-name');
    if (nameEl) _startStickyBoardRename(board, nameEl);
  };
  picker.appendChild(renameItem);

  const noProjectItem = document.createElement('div');
  noProjectItem.className = 'project-picker-item' + (!board.project_id ? ' active' : '');
  noProjectItem.textContent = 'No project';
  noProjectItem.onclick = (e) => { e.stopPropagation(); _moveStickyBoardToProject(board, null); };
  picker.appendChild(noProjectItem);

  for (const p of _notesProjects) {
    const item = document.createElement('div');
    item.className = 'project-picker-item' + (board.project_id === p.project_id ? ' active' : '');
    if (p.color) {
      const dot = document.createElement('span');
      dot.className = 'color-dot';
      dot.style.background = p.color;
      item.appendChild(dot);
    }
    const label = document.createElement('span');
    label.textContent = p.name || p.project_id;
    item.appendChild(label);
    item.onclick = (e) => { e.stopPropagation(); _moveStickyBoardToProject(board, p.project_id); };
    picker.appendChild(item);
  }

  const deleteItem = document.createElement('div');
  deleteItem.className = 'project-picker-item sticky-board-delete-item';
  deleteItem.textContent = 'Delete board';
  deleteItem.onclick = (e) => { e.stopPropagation(); _closeStickyBoardPicker(); _deleteStickyBoard(board); };
  picker.appendChild(deleteItem);

  anchorEl.parentElement.style.position = 'relative';
  anchorEl.parentElement.appendChild(picker);
  _notesPickerEl = picker;
  setTimeout(() => document.addEventListener('click', _closeStickyBoardPicker), 0);
}

async function _moveStickyBoardToProject(board, projectId) {
  _closeStickyBoardPicker();
  try {
    const res = await api('/api/sticky_boards/set_project', { method: 'POST', body: JSON.stringify({ id: board.id, project_id: projectId }) });
    if (res && res.board) board.project_id = res.board.project_id;
    _renderAllNotesViews();
    const filtered = _filteredNotesBoards();
    if (!filtered.some(b => b.id === _notesActiveBoardId)) {
      selectStickyBoard(filtered.length ? filtered[0].id : null);
    } else {
      _renderNotesBoardsLists();
    }
  } catch (e) {
    console.error('moveStickyBoardToProject failed', e);
    showToast('Failed to move board');
  }
}

async function _deleteStickyBoard(board) {
  const ok = await showConfirmDialog({ message: 'Delete board "' + board.name + '"? This cannot be undone.', confirmLabel: 'Delete', danger: true });
  if (!ok) return;
  try {
    await api('/api/sticky_boards/delete', { method: 'POST', body: JSON.stringify({ id: board.id }) });
    _notesBoards = _notesBoards.filter(b => b.id !== board.id);
    _renderAllNotesViews();
    _renderNotesBoardsLists();
    if (_notesActiveBoardId === board.id) {
      const remaining = _filteredNotesBoards();
      selectStickyBoard(remaining.length ? remaining[0].id : null);
    }
  } catch (e) {
    console.error('deleteStickyBoard failed', e);
    showToast('Failed to delete board');
  }
}

function _attachNotesSearch(view) {
  const cfg = NOTES_VIEWS[view];
  const input = $(cfg.searchId);
  if (!input) return;
  input.addEventListener('input', (e) => {
    _notesBoardSearchTerm = e.target.value.trim().toLowerCase();
    _renderNotesBoardsLists();
  });
}
_attachNotesSearch('panel');
_attachNotesSearch('workspace');

// Keep the workspace preview in sync when the sticky-board iframe saves changes.
window.addEventListener('message', (e) => {
  if (e.origin !== location.origin) return;
  if (e.data && e.data.type === 'sticky-board:saved') {
    // The iframe posts the exact snapshot acknowledged by the save endpoint.
    // Apply it first so the workspace mirror updates immediately, then fetch
    // in the background to reconcile board/project metadata. Neither path
    // selects the iframe board, so typing remains uninterrupted.
    const savedBoard = _notesBoards.find(board => board.id === e.data.boardId);
    if (savedBoard && Array.isArray(e.data.columns)) {
      savedBoard.columns = e.data.columns;
    }
    _renderNotesBoardsList('panel');
    _renderWorkspaceNotesPane();
    _refreshNotesPanelData().then((didRefresh) => {
      if (!didRefresh) return;
      _renderNotesBoardsList('panel');
      _renderWorkspaceNotesPane();
    });
  }
});
