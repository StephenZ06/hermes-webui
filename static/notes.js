// Sticky notes for projects (static/index.html's #panelNotes / #mainNotes,
// backed by api/sticky_notes.py). A corkboard of freeform per-project notes,
// independent of chat sessions, Kanban tasks, or Memory.

let _stickyNotes = [];
let _stickyNotesProjects = [];
let _stickyNotesLoaded = false;
const _stickyNoteSaveTimers = {};

const STICKY_NOTE_COLORS = ['yellow', 'pink', 'blue', 'green', 'orange', 'purple'];

async function loadStickyNotes() {
  try {
    const [notesRes, projectsRes] = await Promise.all([
      api('/api/sticky_notes'),
      api('/api/projects?all_profiles=1'),
    ]);
    _stickyNotes = (notesRes && notesRes.notes) || [];
    _stickyNotesProjects = (projectsRes && projectsRes.projects) || [];
  } catch (e) {
    console.error('loadStickyNotes failed', e);
    _stickyNotes = _stickyNotes || [];
    _stickyNotesProjects = _stickyNotesProjects || [];
  }
  _stickyNotesLoaded = true;
  _populateStickyNotesProjectSelect();
  renderStickyNotesBoard();
}

function _populateStickyNotesProjectSelect() {
  const sel = $('notesProjectSelect');
  if (!sel) return;
  const prevValue = sel.value || '';
  const options = ['<option value="">All projects</option>'];
  for (const p of _stickyNotesProjects) {
    options.push(`<option value="${esc(p.project_id)}">${esc(p.name || p.project_id)}</option>`);
  }
  options.push('<option value="__unassigned__">Unassigned</option>');
  sel.innerHTML = options.join('');
  const stillExists = Array.from(sel.options).some(o => o.value === prevValue);
  sel.value = stillExists ? prevValue : '';
}

function _stickyNoteProjectName(projectId) {
  if (!projectId) return 'Unassigned';
  const p = _stickyNotesProjects.find(x => x.project_id === projectId);
  return p ? (p.name || projectId) : projectId;
}

function renderStickyNotesBoard() {
  const board = $('notesBoard');
  if (!board) return;
  if (!_stickyNotesLoaded) {
    board.innerHTML = '<div class="loading-spinner-wrap" role="status"><div class="loading-spinner" aria-hidden="true"></div></div>';
    return;
  }
  const sel = $('notesProjectSelect');
  const filter = sel ? sel.value : '';
  let notes = _stickyNotes.slice();
  if (filter === '__unassigned__') notes = notes.filter(n => !n.project_id);
  else if (filter) notes = notes.filter(n => n.project_id === filter);
  notes.sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));

  if (!notes.length) {
    board.innerHTML = `
      <div class="main-view-empty">
        <svg class="main-view-empty-icon" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 3H3v18h13l5-5V3z"/><path d="M16 21v-5h5"/></svg>
        <div class="main-view-empty-title">No sticky notes yet</div>
        <div class="main-view-empty-sub">Click the + button above to add one.</div>
      </div>`;
    return;
  }

  board.innerHTML = notes.map(n => _renderStickyNoteCard(n)).join('');
}

function _renderStickyNoteCard(note) {
  const color = STICKY_NOTE_COLORS.includes(note.color) ? note.color : 'yellow';
  const swatches = STICKY_NOTE_COLORS.map(c => `
    <button type="button" class="sticky-note-swatch sticky-note-swatch--${c}${c === color ? ' active' : ''}"
      title="${c}" onclick="setStickyNoteColor('${note.id}','${c}')"></button>
  `).join('');
  return `
    <div class="sticky-note sticky-note--${color}" data-note-id="${note.id}">
      <div class="sticky-note-project">${esc(_stickyNoteProjectName(note.project_id))}</div>
      <textarea class="sticky-note-text" placeholder="Write a note..."
        oninput="_onStickyNoteInput('${note.id}', this.value)">${esc(note.text || '')}</textarea>
      <div class="sticky-note-footer">
        <div class="sticky-note-swatches">${swatches}</div>
        <button type="button" class="sticky-note-delete has-tooltip has-tooltip--top" data-tooltip="Delete" aria-label="Delete note" onclick="deleteStickyNote('${note.id}')">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </button>
      </div>
    </div>`;
}

async function createStickyNote() {
  const sel = $('notesProjectSelect');
  const filter = sel ? sel.value : '';
  const project_id = (filter && filter !== '__unassigned__') ? filter : null;
  try {
    const res = await api('/api/sticky_notes/create', { method: 'POST', body: JSON.stringify({ text: '', project_id }) });
    if (res && res.note) _stickyNotes.push(res.note);
    renderStickyNotesBoard();
    const card = document.querySelector(`.sticky-note[data-note-id="${res.note.id}"] textarea`);
    if (card) card.focus();
  } catch (e) {
    console.error('createStickyNote failed', e);
    showToast('Failed to create note');
  }
}

function _onStickyNoteInput(id, text) {
  const note = _stickyNotes.find(n => n.id === id);
  if (note) note.text = text;
  clearTimeout(_stickyNoteSaveTimers[id]);
  _stickyNoteSaveTimers[id] = setTimeout(() => _saveStickyNote(id, { text }), 500);
}

async function _saveStickyNote(id, patch) {
  try {
    await api('/api/sticky_notes/update', { method: 'POST', body: JSON.stringify({ id, ...patch }) });
  } catch (e) {
    console.error('saveStickyNote failed', e);
  }
}

function setStickyNoteColor(id, color) {
  const note = _stickyNotes.find(n => n.id === id);
  if (note) note.color = color;
  renderStickyNotesBoard();
  _saveStickyNote(id, { color });
}

async function deleteStickyNote(id) {
  const ok = await showConfirmDialog({ message: 'Delete this sticky note?', confirmLabel: 'Delete', danger: true });
  if (!ok) return;
  try {
    await api('/api/sticky_notes/delete', { method: 'POST', body: JSON.stringify({ id }) });
    _stickyNotes = _stickyNotes.filter(n => n.id !== id);
    renderStickyNotesBoard();
  } catch (e) {
    console.error('deleteStickyNote failed', e);
    showToast('Failed to delete note');
  }
}
