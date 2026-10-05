/* Work Hub: vanilla-JS client for the local state, using curated mx-icons SVGs. */
(() => {
  const DEFAULT_INSPECTOR_WIDTH = 280;
  let currentInspectorWidth = (() => { const raw = localStorage.getItem('workHubInspectorWidth'); return raw ? parseInt(raw, 10) : DEFAULT_INSPECTOR_WIDTH; })();
  const MIN_INSPECTOR_WIDTH = 200;
  const MAX_INSPECTOR_WIDTH = 600;
  const store = { items: [], folders: [], projects: [], boards: [], profiles: [], statuses: [], workflows: [], revision: 0, stale: false, activeScope: 'all', deleteMode: false, activeFolderId: null, activeBoardId: null, expandedProjects: {}, activeView: 'board', selectedItemId: null, search: '', boardFilters: {}, boardFilterOpen: null };
  const workspaceExpandedBoards = new Set();
  const icon = (name) => window.WorkHubIcons ? window.WorkHubIcons(name) : '';
  const el = (id) => document.getElementById(id);
  const esc = (value) => String(value || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const scopedItems = () => { const projectBoardIds = store.activeFolderId ? new Set(store.boards.filter(board => board.project_id === store.activeFolderId).map(board => board.id)) : null; return store.items.filter(item => (store.activeScope === 'all' ? true : store.activeScope === 'inbox' ? !item.project_id : projectBoardIds ? projectBoardIds.has(item.board_id) : item.project_id === store.activeScope) && (!store.activeBoardId || item.board_id === store.activeBoardId) && (!store.search || item.title.toLowerCase().includes(store.search))); };

  async function request(path, options) { return api(path, options); }
  function notifyWorkHubChanged() { document.dispatchEvent(new CustomEvent('work-hub-changed')); }
  async function loadWorkHubPanel() {
    const root = el('workHub'); if (!root) return;
    try {
      const data = await request('/api/work_hub/bootstrap');
      if ((data.revision || 0) < store.revision) return;
      store.items = data.items || []; store.folders = data.folders || []; store.projects = data.projects || []; store.boards = data.boards || []; store.profiles = data.profiles || []; store.statuses = data.statuses || []; store.workflows = data.workflows || []; store.revision = data.revision || 0; store.stale = false;
    } catch (error) { store.stale = true; }
    render();
  }
  async function refreshWorkHubForProject(projectId) { store.activeScope = projectId || 'inbox'; await loadWorkHubPanel(); }
  function render() {
    const root = el('workHub'); if (!root) return;
    const items = scopedItems();
    root.innerHTML = '';
    const wrap = document.createElement('div'); wrap.className = 'work-hub' + (store.stale ? ' is-stale' : '');
    const inspectorWidth = window.matchMedia('(max-width: 620px)').matches
      ? 220
      : Math.max(MIN_INSPECTOR_WIDTH, Math.min(MAX_INSPECTOR_WIDTH, currentInspectorWidth));
    wrap.style.setProperty('--wh-inspector-width', inspectorWidth + 'px');
    wrap.innerHTML = `<section class="work-hub-canvas"><div class="work-hub-toolbar"><div class="work-hub-view-switch"><button class="${store.activeView === 'board' ? 'active' : ''}" data-view="board">${icon('board')} Board</button><button class="${store.activeView === 'list' ? 'active' : ''}" data-view="list">${icon('list')} List</button></div><label class="work-hub-search">${icon('search')}<input id="workHubSearch" type="search" placeholder="Search work" value="${esc(store.search)}"></label><button class="work-hub-create work-hub-icon-button" id="workHubCreate" aria-label="New item" title="New item">${icon('plus')}</button></div><div class="work-hub-live" role="status">${store.stale ? 'Showing saved data — retrying…' : `${items.length} work item${items.length === 1 ? '' : 's'}`}</div><div id="workHubCanvas"></div></section><div class="work-hub-resizer"></div><aside class="work-hub-inspector" id="workHubInspector" aria-label="Work item details"></aside>`;
    root.appendChild(wrap);
    initResizer(wrap);
    renderWorkHubNavigation();
    renderCanvas(items); renderInspector(); bind();
  }
  function renderWorkHubNavigation() {
    const sidebar = el('workHubSidebar'); if (!sidebar) return;
    sidebar.innerHTML = `<nav class="work-hub-nav" aria-label="Work Hub filters"><button class="work-hub-scope ${store.activeScope === 'inbox' ? 'active' : ''}" data-scope="inbox">${icon('inbox')}<span>Inbox</span></button><button class="work-hub-scope ${store.activeScope === 'all' ? 'active' : ''}" data-scope="all">${icon('work')}<span>All work</span></button><div class="work-hub-nav-label work-hub-projects-heading"><span>WORKSPACES</span></div><div id="workHubProjects" class="project-folder-list work-hub-projects" style="min-height:0;overflow:auto;"></div><div class="work-hub-project-create-row">${store.deleteMode
      ? '<button type="button" class="work-hub-project-delete-done" id="workHubDeleteDone">Done</button>'
      : `<button type="button" class="work-hub-project-create" id="workHubProjectCreate" aria-label="New board, new project or delete project">${icon('plus')}</button>`}</div></nav><button class="work-hub-plan-goal" id="workHubPlanGoal">${icon('sparkles')}<span>Plan goal</span></button>`;
    const projectList = el('workHubProjects');
    projectList.classList.toggle('is-delete-mode', !!store.deleteMode);
    store.projects.forEach(project => {
      const boards = store.boards.filter(board => board.project_id === project.project_id); const count = boards.length;
      const expanded = !!store.expandedProjects[project.project_id];
      const b = document.createElement('button'); b.type = 'button'; b.className = 'project-chip project-folder-row work-hub-project-tile' + (store.activeFolderId === project.project_id ? ' active' : ''); b.dataset.scope = project.project_id; b.dataset.projectToggle = project.project_id; b.setAttribute('aria-expanded', String(expanded)); b.setAttribute('aria-controls', `workHubFolderBoards-${project.project_id}`);
      b.innerHTML = `<span class="project-folder-chevron work-hub-project-chevron ${expanded ? 'expanded' : ''}">▸</span><span class="color-dot work-hub-project-color" aria-hidden="true"></span><span class="project-folder-name work-hub-project-name"></span><span class="project-folder-count work-hub-project-count" aria-label="${count} boards">${count}</span>`;
      b.querySelector('.work-hub-project-name').textContent = project.name || 'Untitled project';
      b.querySelector('.work-hub-project-color').style.background = project.color || 'var(--accent)';
      if (store.deleteMode && project.deletable) {
        const wrap = document.createElement('div');
        wrap.className = 'work-hub-project-delete-wrap is-wiggling';
        // Offset each folder's wiggle so they do not move in lockstep.
        wrap.style.animationDelay = `${-((projectList.children.length * 97) % 300)}ms`;
        const remove = document.createElement('button');
        remove.type = 'button'; remove.className = 'work-hub-project-delete-x'; remove.dataset.deleteProjectId = project.project_id;
        remove.setAttribute('aria-label', `Delete ${project.name || 'project'}`); remove.title = `Delete ${project.name || 'project'}`;
        remove.innerHTML = icon('close');
        wrap.append(b, remove); projectList.appendChild(wrap);
      } else {
        if (store.deleteMode) { b.classList.add('is-locked'); b.title = 'Holds chats or work items -- it stays with the chat page'; }
        projectList.appendChild(b);
      }
      const boardsList = document.createElement('div'); boardsList.id = `workHubFolderBoards-${project.project_id}`; boardsList.className = 'project-folder-sessions work-hub-project-boards' + (expanded ? ' expanded' : ''); boardsList.inert = !expanded;
      const boardsInner = document.createElement('div'); boardsInner.className = 'project-folder-sessions-inner work-hub-project-boards-inner';
      boards.forEach(board => { const row = document.createElement('div'); row.className = 'work-hub-board-row' + (store.activeBoardId === board.id ? ' active' : ''); row.innerHTML = `<button type="button" data-board-id="${esc(board.id)}" data-folder-id="${esc(project.project_id)}">${icon('board')}<span>${esc(board.name)}</span></button><button type="button" class="work-hub-board-rename" data-rename-board="${esc(board.id)}" aria-label="Rename ${esc(board.name)}" title="Rename ${esc(board.name)}">${icon('pencil')}</button><button type="button" class="work-hub-board-delete" data-delete-board="${esc(board.id)}" aria-label="Delete ${esc(board.name)}">${icon('close')}</button>`; boardsInner.appendChild(row); });
      boardsList.appendChild(boardsInner); projectList.appendChild(boardsList);
    });
  }

  async function createWorkHubProject() {
    const name = await showPromptDialog({ title: 'New project', message: 'Name the project workspace.', placeholder: 'Project name', confirmLabel: 'Create' });
    if (!name || !name.trim()) return;
    const colors = ['#7c8cff', '#5fbf9f', '#d5a75f', '#c07ac5', '#d77070'];
    try {
    const result = await request('/api/projects/create', { method: 'POST', body: JSON.stringify({ name: name.trim(), color: colors[store.projects.length % colors.length], work_hub_managed: true }) });
      store.activeFolderId = result.project.project_id; store.expandedProjects[result.project.project_id] = true; await loadWorkHubPanel(); notifyWorkHubChanged();
    } catch (error) {
      store.stale = true; render();
      if (typeof showToast === 'function') showToast(`Project create failed: ${error.message || error}`);
    }
  }
  // Delete mode: like holding an app icon on iOS. Deletable folders (created
  // here, or empty -- the server marks them `deletable`) wiggle with a red
  // outline and an X; the rest stay still. Done, Escape or a click elsewhere
  // leaves it. The X still confirms: a delete removes boards and work items.
  let deleteModeExit = null;
  function enterProjectDeleteMode() {
    if (!store.projects.some(project => project && project.deletable)) {
      if (typeof showToast === 'function') showToast('There are no Work Hub projects to delete.');
      return;
    }
    store.deleteMode = true;
    renderWorkHubNavigation(); bind();
    const onKey = event => { if (event.key === 'Escape') exitProjectDeleteMode(); };
    const onClick = event => {
      if (event.target.closest('.work-hub-projects, .work-hub-project-create-row, .app-dialog-overlay')) return;
      exitProjectDeleteMode();
    };
    document.addEventListener('keydown', onKey);
    setTimeout(() => { if (store.deleteMode) document.addEventListener('click', onClick); }, 0);
    deleteModeExit = () => { document.removeEventListener('keydown', onKey); document.removeEventListener('click', onClick); };
  }
  function exitProjectDeleteMode() {
    if (deleteModeExit) deleteModeExit();
    deleteModeExit = null;
    if (!store.deleteMode) return;
    store.deleteMode = false;
    renderWorkHubNavigation(); bind();
  }
  async function deleteWorkHubProject(projectId) {
    const project = store.projects.find(entry => entry.project_id === projectId && entry.deletable);
    if (!project) return;
    const boardCount = store.boards.filter(board => board.project_id === projectId).length;
    const name = project.name || 'this project';
    const message = `This permanently removes "${name}"${boardCount ? `, its ${boardCount} board${boardCount === 1 ? '' : 's'}` : ''} and every work item in it. Chats filed under it stay, without a project.`;
    if (!await showConfirmDialog({ title: 'Delete project', message, confirmLabel: 'Delete', danger: true })) return;
    try {
      await request('/api/projects/delete', { method: 'POST', body: JSON.stringify({ project_id: projectId }) });
      if (store.activeFolderId === projectId) { store.activeFolderId = null; store.activeScope = 'all'; store.activeBoardId = null; }
      delete store.expandedProjects[projectId];
      await loadWorkHubPanel(); notifyWorkHubChanged();
      if (typeof showToast === 'function') showToast(`Deleted "${name}"`);
      if (!store.projects.some(entry => entry && entry.deletable)) exitProjectDeleteMode();
    } catch (error) {
      store.stale = true; render();
      if (typeof showToast === 'function') showToast(`Project delete failed: ${error.message || error}`);
    }
  }
  function showWorkHubBoardProjectPicker(anchor) { return showWorkHubProjectPicker(anchor, store.projects, 'Create a project workspace before creating a board.'); }
  function showWorkHubProjectPicker(anchor, projects, emptyMessage) { if (!projects.length) { if (typeof showToast === 'function') showToast(emptyMessage); return Promise.resolve(null); } document.querySelectorAll('.work-hub-project-picker').forEach(picker => picker.remove()); return new Promise(resolve => { const host = el('workHubProjectCreate')?.parentElement || anchor?.parentElement; if (!host) return resolve(null); const picker = document.createElement('div'); picker.className = 'project-picker work-hub-project-picker'; let closed = false; const finish = projectId => { if (closed) return; closed = true; picker.remove(); document.removeEventListener('click', close); resolve(projectId); }; const close = event => { if (!picker.contains(event.target) && !anchor?.contains(event.target)) finish(null); }; projects.forEach(project => { const item = document.createElement('div'); item.className = 'project-picker-item'; const dot = document.createElement('span'); dot.className = 'color-dot'; dot.style.cssText = 'width:6px;height:6px;border-radius:50%;background:' + (project.color || 'var(--muted)') + ';flex-shrink:0;'; const name = document.createElement('span'); name.textContent = project.name || 'Untitled project'; item.append(dot, name); item.onclick = () => finish(project.project_id); picker.appendChild(item); }); host.appendChild(picker); setTimeout(() => document.addEventListener('click', close), 0); }); }
  async function createWorkHubBoard(anchor) { const projectId = await showWorkHubBoardProjectPicker(anchor); if (!projectId) return; const name = await showPromptDialog({ title: 'New board', message: 'Name this board.', placeholder: 'Board name', confirmLabel: 'Create' }); if (!name || !name.trim()) return; try { const result = await request('/api/work_hub/boards/create', { method: 'POST', body: JSON.stringify({ board: { name: name.trim(), project_id: projectId }, expected_revision: store.revision }) }); store.activeFolderId = projectId; store.activeScope = projectId; store.activeBoardId = result.board.id; store.expandedProjects[projectId] = true; await loadWorkHubPanel(); notifyWorkHubChanged(); } catch (error) { store.stale = true; render(); } }
  async function renameWorkHubBoard(boardId) { const board = store.boards.find(row => row.id === boardId); if (!board) return; const name = await showPromptDialog({ title: 'Rename board', message: 'Choose a new board name.', placeholder: 'Board name', value: board.name || '', selectAll: true, confirmLabel: 'Rename' }); if (!name || !name.trim() || name.trim() === board.name) return; try { await request('/api/work_hub/boards/rename', { method: 'POST', body: JSON.stringify({ board_id: boardId, board: { name: name.trim() }, expected_revision: store.revision }) }); await loadWorkHubPanel(); notifyWorkHubChanged(); } catch (error) { store.stale = true; render(); if (typeof showToast === 'function') showToast(`Board rename failed: ${error.message || error}`); } }
  async function deleteWorkHubBoard(boardId) { const board = store.boards.find(entry => entry.id === boardId); const message = board?.default ? 'This clears every work item from the main board. The board itself stays as an empty board.' : 'This permanently removes the board and every work item on it.'; if (!await showConfirmDialog({ title: 'Delete board', message, confirmLabel: 'Delete', danger: true })) return; try { await request('/api/work_hub/boards/delete', { method: 'POST', body: JSON.stringify({ board_id: boardId, expected_revision: store.revision }) }); if (store.activeBoardId === boardId) store.activeBoardId = null; await loadWorkHubPanel(); notifyWorkHubChanged(); } catch (error) { store.stale = true; render(); if (typeof showToast === 'function') showToast(`Board delete failed: ${error.message || error}`); } }
  function renderCanvas(items) {
    const canvas = el('workHubCanvas'); if (!canvas) return;
    canvas.innerHTML = '';
    if (store.activeView === 'list') {
      const table = document.createElement('div'); table.className = 'work-hub-list';
      items.forEach(item => { const row = document.createElement('button'); row.className = 'work-hub-list-row'; row.dataset.itemId = item.id; row.innerHTML = `<span class="work-hub-status status-${esc(item.status)}"></span><strong></strong><small>${esc(item.status.replace('_', ' '))}</small>`; row.querySelector('strong').textContent = item.title; table.appendChild(row); });
      canvas.appendChild(table); return;
    }
    const boardWrap = document.createElement('div'); boardWrap.className = 'work-hub-board-wrap';
    const board = document.createElement('div'); board.className = 'work-hub-board';
    store.statuses.forEach(status => {
      const filter = store.boardFilters[status.id] || {};
      const columnItems = items.filter(item => item.status === status.id && (!filter.priority || item.priority === filter.priority) && (!filter.query || item.title.toLowerCase().includes(filter.query)));
      const priorityOption = value => `<option value="${value}" ${filter.priority === value ? 'selected' : ''}>${value[0].toUpperCase() + value.slice(1)}</option>`;
      const filterPanel = store.boardFilterOpen === status.id ? `<div class="work-hub-column-filter"><input data-board-filter-query="${esc(status.id)}" type="search" placeholder="Filter items" value="${esc(filter.query || '')}"><select data-board-filter-priority="${esc(status.id)}"><option value="">All priorities</option>${['high', 'medium', 'low', 'none'].map(priorityOption).join('')}</select></div>` : '';
      const column = document.createElement('section'); column.className = 'work-hub-column'; column.dataset.status = status.id;
      column.innerHTML = `<header><span class="work-hub-status status-${esc(status.id)}"></span><strong>${esc(status.label)}</strong><small>${columnItems.length}</small><button class="work-hub-board-filter" type="button" data-board-filter="${esc(status.id)}" aria-label="Filter ${esc(status.label)}" title="Filter ${esc(status.label)}">${icon('filter')}</button></header>${filterPanel}<div class="work-hub-cards"></div>`;
      const cards = column.querySelector('.work-hub-cards');
      columnItems.forEach(item => { const card = document.createElement('button'); card.className = 'work-hub-card'; card.draggable = true; card.dataset.itemId = item.id; card.innerHTML = `<span class="work-hub-card-title"></span><small>${esc(item.priority || 'none')}</small>`; card.querySelector('.work-hub-card-title').textContent = item.title; cards.appendChild(card); });
      board.appendChild(column);
    });
    boardWrap.appendChild(board);
    canvas.appendChild(boardWrap);
    initDragAndDrop(board);
  }
  function renderInspector() {
    const panel = el('workHubInspector'); if (!panel) return;
    const item = store.items.find(row => row.id === store.selectedItemId);
    if (!item) { panel.innerHTML = `<div class="work-hub-inspector-empty">${icon('work')}<p>Select a work item to see details.</p></div>`; return; }
    const currentSessionId = typeof S !== 'undefined' && S.session ? S.session.session_id : null;
    const missingAgent = item.agent_profile && !store.profiles.some(profile => profile.name === item.agent_profile);
    const workflow = store.workflows.find(run => (run.steps || []).some(step => step.item_id === item.id && ['pending', 'running', 'paused'].includes(run.status)));
    const workflowControl = workflow ? `<div class="work-hub-workflow-state">Workflow: ${esc(workflow.status)}${workflow.pause_reason ? ` — ${esc(workflow.pause_reason)}` : ''}</div>${workflow.status === 'paused' ? '<button id="workHubResume" class="work-hub-save">Resume workflow</button>' : '<button id="workHubPause" class="work-hub-link">Pause workflow</button>'}` : '';
    const locked = !!workflow;
    panel.innerHTML = `<div class="work-hub-inspector-head"><span>WORK ITEM</span><button id="workHubClose" aria-label="Close details">${icon('close')}</button></div>${workflowControl}<label>Title<input id="workHubTitle" type="text" maxlength="160" required ${locked ? 'disabled' : ''}></label><label>Status<select id="workHubStatus" ${locked ? 'disabled' : ''}>${store.statuses.map(s => `<option value="${esc(s.id)}" ${s.id === item.status ? 'selected' : ''}>${esc(s.label)}</option>`).join('')}</select></label><label>Hermes agent<select id="workHubAgent" ${locked ? 'disabled' : ''}><option value="">Unassigned</option>${missingAgent ? `<option value="${esc(item.agent_profile)}" selected>Unavailable: ${esc(item.agent_profile)}</option>` : ''}${store.profiles.map(p => `<option value="${esc(p.name)}" ${p.name === item.agent_profile ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select></label><label>Description<textarea id="workHubDescription" rows="7" placeholder="Add context, decisions, and next steps" ${locked ? 'disabled' : ''}></textarea></label>${currentSessionId && !locked ? '<button id="workHubLinkChat" class="work-hub-link">Link current chat</button>' : ''}${locked ? '' : '<button id="workHubSave" class="work-hub-save">Save changes</button><button id="workHubDelete" class="work-hub-delete" type="button">Delete</button>'}`;
    el('workHubTitle').value = item.title; panel.querySelector('#workHubDescription').value = item.description || '';
    el('workHubClose').onclick = () => { store.selectedItemId = null; renderInspector(); };
    const deleteButton = el('workHubDelete'); if (deleteButton) deleteButton.onclick = () => deleteItem(item.id);
    const linkChat = el('workHubLinkChat');
    if (linkChat) linkChat.onclick = () => updateItem(item.id, { linked_session_ids: [...new Set([...(item.linked_session_ids || []), currentSessionId])] });
    const saveButton = el('workHubSave'); if (saveButton) saveButton.onclick = () => updateItem(item.id, { title: el('workHubTitle').value, status: el('workHubStatus').value, agent_profile: el('workHubAgent').value || null, description: el('workHubDescription').value });
    const pauseButton = el('workHubPause'); if (pauseButton) pauseButton.onclick = () => changeWorkflow(workflow.id, 'pause');
    const resumeButton = el('workHubResume'); if (resumeButton) resumeButton.onclick = () => changeWorkflow(workflow.id, 'resume');
  }
  function bind() {
    document.querySelectorAll('.work-hub-scope').forEach(button => button.onclick = () => { store.activeScope = button.dataset.scope; store.selectedItemId = null; render(); });
    document.querySelectorAll('[data-delete-project-id]').forEach(button => button.onclick = event => { event.stopPropagation(); deleteWorkHubProject(button.dataset.deleteProjectId); });
    const deleteDone = el('workHubDeleteDone'); if (deleteDone) deleteDone.onclick = () => exitProjectDeleteMode();
    document.querySelectorAll('.work-hub-project-tile').forEach(button => button.onclick = (event) => { if (store.deleteMode) return; const projectId = button.dataset.projectToggle; const projectBoards = store.boards.filter(board => board.project_id === projectId); if (projectBoards.length <= 1 && !(event && event.target && event.target.closest && event.target.closest('.work-hub-project-chevron'))) { /* One board needs no disclosure: open it directly. The chevron still reveals the row (rename/delete). */ store.activeFolderId = projectId; store.activeScope = projectId; store.activeBoardId = projectBoards.length ? projectBoards[0].id : null; store.selectedItemId = null; render(); return; } const expanded = !store.expandedProjects[projectId]; store.expandedProjects[projectId] = expanded; store.activeFolderId = projectId; store.activeScope = projectId; store.activeBoardId = null; store.selectedItemId = null; button.classList.add('active'); document.querySelectorAll('.work-hub-project-tile').forEach(other => { if (other !== button) other.classList.remove('active'); }); const chevron = button.querySelector('.work-hub-project-chevron'); if (chevron) chevron.classList.toggle('expanded', expanded); button.setAttribute('aria-expanded', String(expanded)); const boardsList = el(`workHubFolderBoards-${projectId}`); if (boardsList) { boardsList.classList.toggle('expanded', expanded); boardsList.inert = !expanded; } renderCanvas(scopedItems()); renderInspector(); bind(); });
    document.querySelectorAll('[data-board-id]').forEach(button => button.onclick = () => { store.activeFolderId = button.dataset.folderId; store.activeScope = button.dataset.folderId; store.expandedProjects[button.dataset.folderId] = true; store.activeBoardId = button.dataset.boardId; store.selectedItemId = null; render(); });
    document.querySelectorAll('[data-delete-board]').forEach(button => button.onclick = () => deleteWorkHubBoard(button.dataset.deleteBoard));
    document.querySelectorAll('[data-rename-board]').forEach(button => button.onclick = event => { event.stopPropagation(); renameWorkHubBoard(button.dataset.renameBoard); });
    const createProject = el('workHubProjectCreate'); if (createProject) createProject.onclick = () => { const old = document.querySelector('.work-hub-create-menu'); if (old) return old.remove(); const menu = document.createElement('div'); menu.className = 'work-hub-create-menu'; menu.innerHTML = '<button type="button" data-create-board>New board</button><button type="button" data-create-project>New project</button><button type="button" class="is-danger" data-delete-project>Delete project</button>'; createProject.parentElement.appendChild(menu); menu.querySelector('[data-create-board]').onclick = () => { menu.remove(); createWorkHubBoard(createProject); }; menu.querySelector('[data-create-project]').onclick = () => { menu.remove(); createWorkHubProject(); }; menu.querySelector('[data-delete-project]').onclick = () => { menu.remove(); enterProjectDeleteMode(); }; };
    const planGoal = el('workHubPlanGoal');
    if (planGoal) planGoal.onclick = () => openGoalPlannerDialog({ projectId: store.activeScope !== 'all' && store.activeScope !== 'inbox' ? store.activeScope : null, onCreated: () => loadWorkHubPanel() });
    document.querySelectorAll('[data-view]').forEach(button => button.onclick = () => { store.activeView = button.dataset.view; render(); });
    document.querySelectorAll('[data-item-id]').forEach(button => button.onclick = () => { store.selectedItemId = button.dataset.itemId; renderInspector(); });
    const search = el('workHubSearch'); if (search) search.oninput = () => { store.search = search.value.toLowerCase(); renderCanvas(scopedItems()); bind(); };
    const create = el('workHubCreate'); if (create) create.onclick = createItem;
    document.querySelectorAll('[data-board-filter]').forEach(button => button.onclick = () => { store.boardFilterOpen = store.boardFilterOpen === button.dataset.boardFilter ? null : button.dataset.boardFilter; renderCanvas(scopedItems()); bind(); });
    document.querySelectorAll('[data-board-filter-query]').forEach(input => input.oninput = () => { const status = input.dataset.boardFilterQuery; store.boardFilters[status] = { ...(store.boardFilters[status] || {}), query: input.value.toLowerCase() }; renderCanvas(scopedItems()); bind(); });
    document.querySelectorAll('[data-board-filter-priority]').forEach(select => select.onchange = () => { const status = select.dataset.boardFilterPriority; store.boardFilters[status] = { ...(store.boardFilters[status] || {}), priority: select.value }; renderCanvas(scopedItems()); bind(); });
  }
  function initDragAndDrop(board) {
    if (!board) return;
    let draggedId = null;
    board.querySelectorAll('.work-hub-card').forEach(card => {
      card.addEventListener('dragstart', (e) => {
        draggedId = card.dataset.itemId;
        e.dataTransfer.setData('text/plain', draggedId);
        e.dataTransfer.effectAllowed = 'move';
        card.classList.add('dragging');
      });
      card.addEventListener('dragend', () => { card.classList.remove('dragging'); draggedId = null; board.querySelectorAll('.work-hub-column').forEach(c => c.classList.remove('drop-target')); });
    });
    board.querySelectorAll('.work-hub-column').forEach(column => {
      column.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        column.classList.add('drop-target');
      });
      column.addEventListener('dragleave', () => { column.classList.remove('drop-target'); });
      column.addEventListener('drop', (e) => {
        e.preventDefault();
        column.classList.remove('drop-target');
        const itemId = e.dataTransfer.getData('text/plain');
        const status = column.dataset.status;
        if (!itemId || !status) return;
        const item = store.items.find(i => i.id === itemId);
        if (item && item.status !== status) updateItem(itemId, { status });
      });
    });
  }
  async function deleteItem(itemId) {
    if (!await showConfirmDialog({ title: 'Delete work item', message: 'Are you sure you want to delete this work item? This cannot be undone.', confirmLabel: 'Delete', danger: true })) return;
    try {
      const result = await request('/api/work_hub/items/delete', { method: 'POST', body: JSON.stringify({ item_id: itemId, expected_revision: store.revision }) });
      store.items = store.items.filter(i => i.id !== itemId); store.revision = result.revision; store.selectedItemId = null; notifyWorkHubChanged(); render();
      if (typeof showToast === 'function') showToast('Work item deleted');
    } catch (error) { store.stale = true; render(); }
  }
  async function createItem() {
    try {
      const result = await request('/api/work_hub/items/create', { method: 'POST', body: JSON.stringify({ item: { title: 'New work item', status: 'backlog', project_id: store.activeScope !== 'all' && store.activeScope !== 'inbox' ? store.activeScope : null }, expected_revision: store.revision }) });
      store.items.push(result.item); store.revision = result.revision; store.selectedItemId = result.item.id; notifyWorkHubChanged(); render();
      // Flash the new card
      setTimeout(() => {
        const card = document.querySelector(`.work-hub-card[data-item-id="${result.item.id}"], .work-hub-list-row[data-item-id="${result.item.id}"]`);
        if (card) { card.classList.add('work-hub-new'); setTimeout(() => card.classList.remove('work-hub-new'), 1200); }
      }, 50);
    } catch (error) { store.stale = true; render(); }
  }
  async function updateItem(itemId, item) { try { const result = await request('/api/work_hub/items/update', { method: 'POST', body: JSON.stringify({ item_id: itemId, item, expected_revision: store.revision }) }); const index = store.items.findIndex(x => x.id === itemId); store.items[index] = result.item; store.revision = result.revision; notifyWorkHubChanged(); render(); } catch (error) { store.stale = true; render(); } }
  async function changeWorkflow(workflowId, action) { try { const result = await request(`/api/work_hub/workflows/${workflowId}/${action}`, { method: 'POST', body: JSON.stringify({ expected_revision: store.revision }) }); store.revision = result.revision; await loadWorkHubPanel(); notifyWorkHubChanged(); } catch (error) { store.stale = true; render(); } }
  function initResizer(wrap) {
    const resizer = wrap.querySelector('.work-hub-resizer'); if (!resizer) return;
    resizer.addEventListener('mousedown', (e) => {
      e.preventDefault();
      const startX = e.clientX;
      const startWidth = currentInspectorWidth;
      const onMove = (ev) => {
        const delta = startX - ev.clientX;
        const newWidth = Math.max(MIN_INSPECTOR_WIDTH, Math.min(MAX_INSPECTOR_WIDTH, startWidth + delta));
        wrap.style.setProperty('--wh-inspector-width', newWidth + 'px');
      };
      const onUp = (ev) => {
        const delta = startX - ev.clientX;
        currentInspectorWidth = Math.max(MIN_INSPECTOR_WIDTH, Math.min(MAX_INSPECTOR_WIDTH, startWidth + delta));
        wrap.style.setProperty('--wh-inspector-width', currentInspectorWidth + 'px');
        localStorage.setItem('workHubInspectorWidth', String(currentInspectorWidth));
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  }
  async function openWorkHubItem(itemId, projectId, boardId = null) {
    store.activeScope = projectId || 'inbox';
    store.activeFolderId = projectId || null;
    store.activeBoardId = boardId;
    store.selectedItemId = itemId || null;
    if (typeof window.switchPanel === 'function') await window.switchPanel('notes');
    else await loadWorkHubPanel();
    render();
  }
  async function renderWorkspaceWorkHub() {
    const list = el('workspaceWorkHubList'); if (!list) return;
    const scope = el('workspaceWorkHubScope');
    const session = typeof S !== 'undefined' ? S.session : null;
    const projectId = session && session.project_id ? session.project_id : null;
    list.innerHTML = '<div class="workspace-work-hub-loading">Loading work…</div>';
    try {
      const data = await request('/api/work_hub/bootstrap');
      const boards = (data.boards || []).filter(board => board.project_id === projectId);
      const boardIds = new Set(boards.map(board => board.id));
      const itemsByBoard = new Map(boards.map(board => [board.id, []]));
      (data.items || []).filter(item => boardIds.has(item.board_id) && item.status !== 'cancelled').forEach(item => itemsByBoard.get(item.board_id).push(item));
      const project = projectId ? (data.projects || []).find(row => row.project_id === projectId) : null;
      if (scope) { scope.innerHTML = ''; if (projectId) { const dot = document.createElement('span'); dot.className = 'color-dot workspace-work-hub-scope-dot'; dot.style.background = project?.color || 'var(--accent)'; const label = document.createElement('span'); label.textContent = `${project?.name || 'Project work'} · ${boards.length} board${boards.length === 1 ? '' : 's'}`; scope.append(dot, label); } else scope.textContent = `Inbox boards · ${boards.length} board${boards.length === 1 ? '' : 's'}`; }
      list.innerHTML = '';
      if (!boards.length) {
        list.innerHTML = '<div class="workspace-work-hub-empty">No boards in this workspace yet.</div>';
      } else {
        boards.forEach(board => {
          const items = itemsByBoard.get(board.id) || [];
          const expanded = workspaceExpandedBoards.has(board.id);
          const section = document.createElement('section'); section.className = 'workspace-work-hub-board' + (expanded ? ' expanded' : '');
          const toggle = document.createElement('button'); toggle.type = 'button'; toggle.className = 'workspace-work-hub-board-toggle'; toggle.setAttribute('aria-expanded', String(expanded)); toggle.setAttribute('aria-controls', `workspaceWorkHubBoard-${board.id}`);
          toggle.innerHTML = `${icon('board')}<span class="workspace-work-hub-board-copy"><strong></strong><small>${items.length ? `${items.length} task${items.length === 1 ? '' : 's'}` : 'Empty'}</small></span><span class="workspace-work-hub-board-chevron" aria-hidden="true">▸</span>`;
          toggle.querySelector('strong').textContent = board.name || 'Untitled board';
          toggle.onclick = () => { if (workspaceExpandedBoards.has(board.id)) workspaceExpandedBoards.delete(board.id); else workspaceExpandedBoards.add(board.id); renderWorkspaceWorkHub(); };
          const openBoard = document.createElement('button'); openBoard.type = 'button'; openBoard.className = 'workspace-work-hub-board-open'; openBoard.textContent = 'Open'; openBoard.title = `Open ${board.name || 'board'} in Work Hub`; openBoard.onclick = () => openWorkHubItem(null, projectId, board.id);
          const header = document.createElement('div'); header.className = 'workspace-work-hub-board-head'; header.append(toggle, openBoard); section.appendChild(header);
          const tasks = document.createElement('div'); tasks.id = `workspaceWorkHubBoard-${board.id}`; tasks.className = 'workspace-work-hub-tasks'; tasks.hidden = !expanded;
          if (!items.length) { const empty = document.createElement('div'); empty.className = 'workspace-work-hub-board-empty'; empty.textContent = 'No active tasks.'; tasks.appendChild(empty); }
          items.forEach(item => { const task = document.createElement('button'); task.type = 'button'; task.className = 'workspace-work-hub-task'; task.innerHTML = `<span class="work-hub-status status-${esc(item.status)}"></span><span class="workspace-work-hub-task-copy"><strong></strong><small>${esc((item.status || '').replace('_', ' '))}</small></span>`; task.querySelector('strong').textContent = item.title; task.onclick = () => openWorkHubItem(item.id, projectId, board.id); tasks.appendChild(task); });
          section.appendChild(tasks); list.appendChild(section);
        });
      }
      const open = el('workspaceWorkHubOpen');
      if (open) open.onclick = () => openWorkHubItem(null, projectId);
    } catch (error) {
      list.innerHTML = '<div class="workspace-work-hub-empty">Work Hub is unavailable right now.</div>';
    }
  }
  window.loadWorkHubPanel = loadWorkHubPanel; window.refreshWorkHubForProject = refreshWorkHubForProject;
  window.openWorkHubItem = openWorkHubItem; window.renderWorkspaceWorkHub = renderWorkspaceWorkHub;
  document.addEventListener('project-sessions-changed', () => { if (el('workHub')) loadWorkHubPanel(); });
  document.addEventListener('work-hub-changed', () => { if (el('workspaceWorkHubList')) renderWorkspaceWorkHub(); });
  window.addEventListener('focus', () => { if (el('workHub')) loadWorkHubPanel(); });
})();

/* Goal Planner dialog UI. */
(function(){
  const icon = (name) => window.WorkHubIcons ? window.WorkHubIcons(name) : '';
  const esc = (value) => String(value || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  let currentPlan = null;
  let currentOptions = {};
  let createdItems = [];
  let createdRevision = null;
  let uploadTokens = [];

  async function fetchProjects() { try { const data = await api('/api/projects?all_profiles=1'); return (data.projects || []).filter(p => p && p.project_id); } catch (e) { return []; } }

  function closeDialog() { const tokens = uploadTokens; uploadTokens = []; if (tokens.length) api('/api/work_hub/plan/uploads/discard', { method: 'POST', body: JSON.stringify({ upload_tokens: tokens }), timeoutToast: false }).catch(() => {}); const o = document.querySelector('.goal-planner-overlay'); if (o) o.remove(); currentPlan = null; createdItems = []; createdRevision = null; }

  function renderPlanSteps(plan) {
    if (!plan || !plan.steps || !plan.steps.length) return `<div class="goal-planner-empty">Add notes or source files, then Plan creates a smart draft for you to save.</div>`;
    const meta = plan.meta || {};
    return `<div class="goal-planner-meta"><span class="tag">${esc(meta.domain)}</span><span>${esc(meta.action)}</span></div><div class="goal-planner-steps">${plan.steps.map(s => `<div class="goal-planner-step"><div class="goal-planner-step-id">${esc(s.id)}</div><div class="goal-planner-step-body"><div class="goal-planner-step-title">${esc(s.title)}</div><div class="goal-planner-step-desc">${esc(s.description)}</div></div></div>`).join('')}</div>`;
  }

  function buildDialog(projectId, projects) {
    const active = projects.find(p => p.project_id === projectId);
    return `<div class="goal-planner-overlay"><div class="goal-planner-dialog" role="dialog" aria-labelledby="goalPlannerTitle"><div class="goal-planner-head"><h3 id="goalPlannerTitle">${icon('sparkles')} Plan goal</h3><button id="goalPlannerClose" aria-label="Close">${icon('close')}</button></div><div class="goal-planner-body"><div class="goal-planner-field"><div class="goal-planner-dropzone" id="goalPlannerDropzone"><textarea id="goalPlannerInput" placeholder=" "></textarea><span class="goal-planner-dropzone-hint">Create, Paste, or Attach notes to be turned into a structured item</span><input id="goalPlannerFiles" type="file" accept=".txt,.md,.markdown,.docx,.pdf" multiple hidden><div id="goalPlannerUploads" class="goal-planner-uploads"></div></div><button id="goalPlannerBtn" type="button" aria-label="Plan work items" title="Plan work items" class="goal-planner-button-icon">${icon('sparkles')}</button></div><div id="goalPlannerProjectSelect" style="margin-bottom:12px">${renderProjectSelect(active, projects)}</div><div id="goalPlannerResult">${renderPlanSteps(null)}</div></div><div class="goal-planner-actions"><button id="goalPlannerCancel">Cancel</button><button id="goalPlannerSave" class="primary goal-planner-button-icon" disabled aria-label="Save work items" title="Save work items">${icon('check')}</button></div></div></div>`;
  }

  function renderProjectSelect(active, projects) {
    return `<button type="button" class="goal-planner-scope" id="goalPlannerScopeBtn"><span class="tag">scope</span><div>${esc(active ? active.name : 'Inbox (no project)')}</div><small>${esc(active ? (active.description || active.repo_path || active.project_id) : 'Create unassigned work items')}</small></button>`;
  }

  function bindDialog(projects, onCreated) {
    document.getElementById('goalPlannerClose').onclick = closeDialog;
    document.getElementById('goalPlannerCancel').onclick = closeDialog;
    document.getElementById('goalPlannerOverlayClick') && (document.getElementById('goalPlannerOverlayClick').onclick = closeDialog);
    const scopeBtn = document.getElementById('goalPlannerScopeBtn');
    if (scopeBtn) scopeBtn.onclick = () => cycleScope(scopeBtn, projects);
    const dropzone = document.getElementById('goalPlannerDropzone');
    const fileInput = document.getElementById('goalPlannerFiles');
    const uploads = document.getElementById('goalPlannerUploads');
    const renderUploads = () => { uploads.innerHTML = uploadTokens.map(upload => `<button type="button" class="goal-planner-upload" data-token="${esc(upload.token)}">${esc(upload.name)} <span aria-hidden="true">×</span></button>`).join(''); uploads.querySelectorAll('[data-token]').forEach(button => button.onclick = () => { uploadTokens = uploadTokens.filter(upload => upload.token !== button.dataset.token); renderUploads(); }); };
    const addFiles = async files => { for (const file of Array.from(files || [])) { const form = new FormData(); form.append('file', file); const data = await api('/api/work_hub/plan/uploads', { method: 'POST', body: form, headers: {} }); uploadTokens.push(data.upload); renderUploads(); } };
    dropzone.onclick = event => { if (event.target === dropzone || event.target.classList.contains('goal-planner-dropzone-hint')) fileInput.click(); };
    fileInput.onchange = () => addFiles(fileInput.files).catch(error => { document.getElementById('goalPlannerResult').innerHTML = `<div class="goal-planner-empty" style="color:var(--error)">${esc(error.message)}</div>`; });
    ['dragenter', 'dragover'].forEach(type => dropzone.addEventListener(type, event => { event.preventDefault(); dropzone.classList.add('is-dragging'); }));
    ['dragleave', 'drop'].forEach(type => dropzone.addEventListener(type, event => { event.preventDefault(); dropzone.classList.remove('is-dragging'); }));
    dropzone.addEventListener('drop', event => addFiles(event.dataTransfer.files).catch(error => { document.getElementById('goalPlannerResult').innerHTML = `<div class="goal-planner-empty" style="color:var(--error)">${esc(error.message)}</div>`; }));
    document.getElementById('goalPlannerBtn').onclick = async () => {
      const input = document.getElementById('goalPlannerInput');
      const goal = input.value.trim(); if (!goal && !uploadTokens.length) return;
      const btn = document.getElementById('goalPlannerBtn'); btn.disabled = true; btn.classList.add('goal-planner-is-planning'); btn.innerHTML = icon('loader');
      try {
        const data = await api('/api/work_hub/plan/ai', { method: 'POST', body: JSON.stringify({ goal: goal || 'Create work items from the attached sources.', project_id: currentOptions.projectId || null, upload_tokens: uploadTokens.map(upload => upload.token) }) });
        currentPlan = data && data.plan || null;
        if (!currentPlan) throw new Error('No plan returned');
        uploadTokens = [];
        document.getElementById('goalPlannerResult').innerHTML = renderPlanSteps(currentPlan);
        document.getElementById('goalPlannerSave').disabled = false;
      } catch (e) {
        document.getElementById('goalPlannerResult').innerHTML = `<div class="goal-planner-empty" style="color:var(--error)">Failed to plan: ${esc(e.message)}</div>`;
      } finally { btn.disabled = false; btn.classList.remove('goal-planner-is-planning'); btn.innerHTML = icon('sparkles'); }
    };
    document.getElementById('goalPlannerSave').onclick = async () => {
      if (!currentPlan || !Array.isArray(currentPlan.steps) || !currentPlan.steps.length) return;
      const btn = document.getElementById('goalPlannerSave'); btn.disabled = true; btn.classList.add('goal-planner-is-planning'); btn.innerHTML = icon('loader');
      try {
        const data = await api('/api/work_hub/plan/save', { method: 'POST', body: JSON.stringify({ project_id: currentOptions.projectId || null, steps: currentPlan.steps }) });
        createdItems = Array.isArray(data.items) ? data.items : [];
        createdRevision = data.revision;
        if (typeof onCreated === 'function') onCreated(data);
        closeDialog();
      } catch (e) {
        btn.disabled = false; btn.classList.remove('goal-planner-is-planning'); btn.innerHTML = icon('check');
        document.getElementById('goalPlannerResult').insertAdjacentHTML('afterbegin', `<div class="goal-planner-empty" style="color:var(--error);margin-bottom:8px">${esc(e.message)}</div>`);
      }
    };
    document.querySelector('.goal-planner-overlay').addEventListener('click', (e) => { if (e.target === e.currentTarget) closeDialog(); });
    document.getElementById('goalPlannerInput').addEventListener('keydown', (e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') document.getElementById('goalPlannerBtn').click(); });
  }

  function cycleScope(btn, projects) {
    const idx = projects.findIndex(p => p.project_id === currentOptions.projectId);
    const next = projects[(idx + 1) % projects.length];
    currentOptions.projectId = next ? next.project_id : null;
    btn.outerHTML = renderProjectSelect(next || null, projects);
    bindScopeClick(projects);
  }

  function bindScopeClick(projects) { const b = document.getElementById('goalPlannerScopeBtn'); if (b) b.onclick = () => cycleScope(b, projects); }

  async function openGoalPlannerDialog(options = {}) {
    currentOptions = { projectId: options.projectId || null };
    closeDialog();
    const projects = await fetchProjects();
    const wrapper = document.createElement('div'); wrapper.innerHTML = buildDialog(currentOptions.projectId, projects); document.body.appendChild(wrapper.firstElementChild);
    bindDialog(projects, options.onCreated);
  }

  window.openGoalPlannerDialog = openGoalPlannerDialog;
})();
