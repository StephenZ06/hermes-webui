// Notes panel: multiple sticky-note boards (static/vendor/sticky-board/,
// api/sticky_board.py), each optionally linked to a Project folder (the
// same Projects the Chat sidebar's project-folder rows use). Linking a
// board mirrors its content into that project's workspace AGENTS.md (see
// api/sticky_board.py's docstring) so project chats can see it.

let _notesProjects = [];
let _notesBoards = [];
let _notesActiveProjectFilter = null; // null = "All"
let _notesActiveBoardId = null;
let _notesPickerEl = null; // the one open move-to-project/board-actions picker, if any

const NOTES_LAST_BOARD_KEY = 'hermes-notes-last-board';

async function loadNotesPanel() {
  try {
    const [projectsRes, boardsRes] = await Promise.all([
      api('/api/projects?all_profiles=1'),
      api('/api/sticky_boards'),
    ]);
    _notesProjects = (projectsRes && projectsRes.projects) || [];
    _notesBoards = (boardsRes && boardsRes.boards) || [];
  } catch (e) {
    console.error('loadNotesPanel failed', e);
    _notesProjects = _notesProjects || [];
    _notesBoards = _notesBoards || [];
  }
  _restoreOrSelectStickyBoard();
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
  _renderNotesProjectFolders();
  const filtered = _filteredNotesBoards();
  // Switching folders must never leave the previous folder's board showing
  // just because the new folder happens to have none of its own -- always
  // land on a board that's actually IN the new filter (or the empty state).
  if (!filtered.some(b => b.id === _notesActiveBoardId)) {
    selectStickyBoard(filtered.length ? filtered[0].id : null);
  } else {
    _renderNotesBoardsList();
  }
}

function _restoreOrSelectStickyBoard() {
  let target = null;
  try { target = localStorage.getItem(NOTES_LAST_BOARD_KEY); } catch (e) { /* ignore */ }
  const board = target ? _notesBoards.find(b => b.id === target) : null;
  // Restore into whichever folder the last-open board actually belongs to,
  // so the active filter chip and the shown board never disagree.
  _notesActiveProjectFilter = board ? (board.project_id || null) : null;
  _renderNotesProjectFolders();
  const filtered = _filteredNotesBoards();
  selectStickyBoard(board ? board.id : (filtered.length ? filtered[0].id : null));
}

function _notesProjectById(projectId) {
  return _notesProjects.find(p => p.project_id === projectId) || null;
}

// ── Project folder filter row ──
function _renderNotesProjectFolders() {
  const container = $('notesProjectFolders');
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
function _renderNotesBoardsList() {
  const list = $('notesBoardsList');
  if (!list) return;
  list.innerHTML = '';
  const boards = _filteredNotesBoards();

  if (!boards.length) {
    const empty = document.createElement('div');
    empty.className = 'notes-boards-empty';
    empty.textContent = 'No boards yet. Click + above to create one.';
    list.appendChild(empty);
    return;
  }

  for (const board of boards) {
    list.appendChild(_buildStickyBoardRow(board));
  }
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
  _renderNotesBoardsList();
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
      _renderNotesProjectFolders();
      _renderNotesBoardsList();
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
    _renderNotesBoardsList();
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
    _renderNotesProjectFolders();
    const filtered = _filteredNotesBoards();
    if (!filtered.some(b => b.id === _notesActiveBoardId)) {
      selectStickyBoard(filtered.length ? filtered[0].id : null);
    } else {
      _renderNotesBoardsList();
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
    _renderNotesProjectFolders();
    _renderNotesBoardsList();
    if (_notesActiveBoardId === board.id) {
      const remaining = _filteredNotesBoards();
      selectStickyBoard(remaining.length ? remaining[0].id : null);
    }
  } catch (e) {
    console.error('deleteStickyBoard failed', e);
    showToast('Failed to delete board');
  }
}
