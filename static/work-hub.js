/* Work Hub: vanilla-JS client for the local state, using curated mx-icons SVGs. */
(() => {
  const DEFAULT_INSPECTOR_WIDTH = 280;
  let currentInspectorWidth = (() => { const raw = localStorage.getItem('workHubInspectorWidth'); return raw ? parseInt(raw, 10) : DEFAULT_INSPECTOR_WIDTH; })();
  const MIN_INSPECTOR_WIDTH = 200;
  const MAX_INSPECTOR_WIDTH = 600;
  const store = { items: [], folders: [], boards: [], profiles: [], statuses: [], workflows: [], revision: 0, stale: false, activeScope: 'all', activeFolderId: null, activeBoardId: null, expandedProjects: {}, activeView: 'board', selectedItemId: null, search: '', boardFilters: {}, boardFilterOpen: null };
  const workspaceExpandedItems = new Set();
  const icon = (name) => window.WorkHubIcons ? window.WorkHubIcons(name) : '';
  const el = (id) => document.getElementById(id);
  const esc = (value) => String(value || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const scopedItems = () => { const folderBoardIds = store.activeFolderId ? new Set(store.boards.filter(board => board.folder_id === store.activeFolderId).map(board => board.id)) : null; return store.items.filter(item => (store.activeScope === 'all' ? true : store.activeScope === 'inbox' ? !item.project_id : folderBoardIds ? folderBoardIds.has(item.board_id) : item.project_id === store.activeScope) && (!store.activeBoardId || item.board_id === store.activeBoardId) && (!store.search || item.title.toLowerCase().includes(store.search))); };

  async function request(path, options) { return api(path, options); }
  async function loadWorkHubPanel() {
    const root = el('workHub'); if (!root) return;
    try {
      const data = await request('/api/work_hub/bootstrap');
      if ((data.revision || 0) < store.revision) return;
      store.items = data.items || []; store.folders = data.folders || []; store.boards = data.boards || []; store.profiles = data.profiles || []; store.statuses = data.statuses || []; store.workflows = data.workflows || []; store.revision = data.revision || 0; store.stale = false;
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
    sidebar.innerHTML = `<nav class="work-hub-nav" aria-label="Work Hub filters"><button class="work-hub-scope ${store.activeScope === 'inbox' ? 'active' : ''}" data-scope="inbox">${icon('inbox')}<span>Inbox</span></button><button class="work-hub-scope ${store.activeScope === 'all' ? 'active' : ''}" data-scope="all">${icon('work')}<span>All work</span></button><div class="work-hub-nav-label work-hub-projects-heading"><span>WORKSPACES</span><button type="button" class="work-hub-project-create" id="workHubProjectCreate" aria-label="Create project" title="Create project">${icon('plus')}</button></div><div id="workHubProjects" class="project-folder-list work-hub-projects" style="flex:1;min-height:0;overflow:auto;"></div></nav><button class="work-hub-plan-goal" id="workHubPlanGoal">${icon('sparkles')}<span>Plan goal</span></button>`;
    const projectList = el('workHubProjects');
    store.folders.forEach(project => {
      const boards = store.boards.filter(board => board.folder_id === project.id); const boardIds = new Set(boards.map(board => board.id)); const count = store.items.filter(item => boardIds.has(item.board_id) && item.status !== 'cancelled').length;
      const expanded = !!store.expandedProjects[project.id];
      const b = document.createElement('button'); b.type = 'button'; b.className = 'project-chip project-folder-row work-hub-project-tile' + (store.activeFolderId === project.id ? ' active' : ''); b.dataset.scope = project.id; b.dataset.projectToggle = project.id; b.setAttribute('aria-expanded', String(expanded)); b.setAttribute('aria-controls', `workHubFolderBoards-${project.id}`);
      b.innerHTML = `<span class="project-folder-chevron work-hub-project-chevron ${expanded ? 'expanded' : ''}">▸</span><span class="color-dot work-hub-project-color" aria-hidden="true"></span><span class="project-folder-name work-hub-project-name"></span><span class="project-folder-count work-hub-project-count" aria-label="${count} work items">${count}</span>`;
      b.querySelector('.work-hub-project-name').textContent = project.name || 'Untitled project';
      b.querySelector('.work-hub-project-color').style.background = project.color || 'var(--accent)';
      projectList.appendChild(b);
      const boardsList = document.createElement('div'); boardsList.id = `workHubFolderBoards-${project.id}`; boardsList.className = 'project-folder-sessions work-hub-project-boards' + (expanded ? ' expanded' : ''); boardsList.inert = !expanded;
      const boardsInner = document.createElement('div'); boardsInner.className = 'project-folder-sessions-inner work-hub-project-boards-inner';
      boards.forEach(board => { const row = document.createElement('div'); row.className = 'work-hub-board-row' + (store.activeBoardId === board.id ? ' active' : ''); row.innerHTML = `<button type="button" data-board-id="${esc(board.id)}" data-folder-id="${esc(project.id)}">${icon('board')}<span>${esc(board.name)}</span></button>${board.default ? '' : `<button type="button" class="work-hub-board-delete" data-delete-board="${esc(board.id)}" aria-label="Delete ${esc(board.name)}">${icon('close')}</button>`}`; boardsInner.appendChild(row); });
      boardsList.appendChild(boardsInner); projectList.appendChild(boardsList);
    });
  }

  async function createWorkHubProject() {
    const name = await showPromptDialog({ title: 'New project', message: 'Name the project workspace.', placeholder: 'Project name', confirmLabel: 'Create' });
    if (!name || !name.trim()) return;
    const colors = ['#7c8cff', '#5fbf9f', '#d5a75f', '#c07ac5', '#d77070'];
    try {
      const result = await request('/api/work_hub/folders/create', { method: 'POST', body: JSON.stringify({ folder: { name: name.trim(), color: colors[store.folders.length % colors.length] }, expected_revision: store.revision }) });
      store.activeFolderId = result.folder.id; store.expandedProjects[result.folder.id] = true; await loadWorkHubPanel();
    } catch (error) {
      store.stale = true; render();
      if (typeof showToast === 'function') showToast(`Project create failed: ${error.message || error}`);
    }
  }
  async function createWorkHubBoard() { if (!store.activeFolderId) { if (typeof showToast === 'function') showToast('Select a project folder before creating a board.'); return; } const name = await showPromptDialog({ title: 'New board', message: 'Name this board.', placeholder: 'Board name', confirmLabel: 'Create' }); if (!name || !name.trim()) return; try { const result = await request('/api/work_hub/boards/create', { method: 'POST', body: JSON.stringify({ board: { name: name.trim(), folder_id: store.activeFolderId }, expected_revision: store.revision }) }); store.activeBoardId = result.board.id; await loadWorkHubPanel(); } catch (error) { store.stale = true; render(); } }
  async function deleteWorkHubBoard(boardId) { if (!await showConfirmDialog({ title: 'Delete board', message: 'Its work items move to the default board. The project workspace stays intact.', confirmLabel: 'Delete', danger: true })) return; try { await request('/api/work_hub/boards/delete', { method: 'POST', body: JSON.stringify({ board_id: boardId, expected_revision: store.revision }) }); if (store.activeBoardId === boardId) store.activeBoardId = null; await loadWorkHubPanel(); } catch (error) { store.stale = true; render(); } }
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
    document.querySelectorAll('.work-hub-project-tile').forEach(button => button.onclick = () => { const projectId = button.dataset.projectToggle; store.expandedProjects[projectId] = !store.expandedProjects[projectId]; store.activeFolderId = projectId; store.activeScope = projectId; store.activeBoardId = null; store.selectedItemId = null; render(); });
    document.querySelectorAll('[data-board-id]').forEach(button => button.onclick = () => { store.activeFolderId = button.dataset.folderId; store.activeScope = button.dataset.folderId; store.expandedProjects[button.dataset.folderId] = true; store.activeBoardId = button.dataset.boardId; store.selectedItemId = null; render(); });
    document.querySelectorAll('[data-delete-board]').forEach(button => button.onclick = () => deleteWorkHubBoard(button.dataset.deleteBoard));
    const createProject = el('workHubProjectCreate'); if (createProject) createProject.onclick = () => { const old = document.querySelector('.work-hub-create-menu'); if (old) return old.remove(); const menu = document.createElement('div'); menu.className = 'work-hub-create-menu'; menu.innerHTML = '<button type="button" data-create-board>New board</button><button type="button" data-create-project>New Project Folder</button>'; createProject.parentElement.appendChild(menu); menu.querySelector('[data-create-board]').onclick = () => { menu.remove(); createWorkHubBoard(); }; menu.querySelector('[data-create-project]').onclick = () => { menu.remove(); createWorkHubProject(); }; };
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
      store.items = store.items.filter(i => i.id !== itemId); store.revision = result.revision; store.selectedItemId = null; document.dispatchEvent(new CustomEvent('work-hub-changed')); render();
      if (typeof showToast === 'function') showToast('Work item deleted');
    } catch (error) { store.stale = true; render(); }
  }
  async function createItem() {
    try {
      const result = await request('/api/work_hub/items/create', { method: 'POST', body: JSON.stringify({ item: { title: 'New work item', status: 'backlog', project_id: store.activeScope !== 'all' && store.activeScope !== 'inbox' ? store.activeScope : null }, expected_revision: store.revision }) });
      store.items.push(result.item); store.revision = result.revision; store.selectedItemId = result.item.id; document.dispatchEvent(new CustomEvent('work-hub-changed')); render();
      // Flash the new card
      setTimeout(() => {
        const card = document.querySelector(`.work-hub-card[data-item-id="${result.item.id}"], .work-hub-list-row[data-item-id="${result.item.id}"]`);
        if (card) { card.classList.add('work-hub-new'); setTimeout(() => card.classList.remove('work-hub-new'), 1200); }
      }, 50);
    } catch (error) { store.stale = true; render(); }
  }
  async function updateItem(itemId, item) { try { const result = await request('/api/work_hub/items/update', { method: 'POST', body: JSON.stringify({ item_id: itemId, item, expected_revision: store.revision }) }); const index = store.items.findIndex(x => x.id === itemId); store.items[index] = result.item; store.revision = result.revision; document.dispatchEvent(new CustomEvent('work-hub-changed')); render(); } catch (error) { store.stale = true; render(); } }
  async function changeWorkflow(workflowId, action) { try { const result = await request(`/api/work_hub/workflows/${workflowId}/${action}`, { method: 'POST', body: JSON.stringify({ expected_revision: store.revision }) }); store.revision = result.revision; await loadWorkHubPanel(); } catch (error) { store.stale = true; render(); } }
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
  async function openWorkHubItem(itemId, projectId) {
    store.activeScope = projectId || 'inbox';
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
      const boardIds = new Set((data.boards || []).filter(board => board.project_id === projectId).map(board => board.id));
      const items = (data.items || []).filter(item => projectId ? boardIds.has(item.board_id) : !item.project_id)
        .filter(item => item.status !== 'cancelled');
      if (scope) scope.textContent = projectId ? 'Current project board work' : 'Inbox work';
      list.innerHTML = '';
      if (!items.length) {
        list.innerHTML = '<div class="workspace-work-hub-empty">No work items in this scope.</div>';
      } else {
        items.forEach(item => {
          const expanded = workspaceExpandedItems.has(item.id);
          const card = document.createElement('article'); card.className = 'workspace-work-hub-item' + (expanded ? ' expanded' : '');
          const toggle = document.createElement('button'); toggle.type = 'button'; toggle.className = 'workspace-work-hub-item-toggle'; toggle.setAttribute('aria-expanded', String(expanded));
          toggle.innerHTML = `<span class="work-hub-status status-${esc(item.status)}"></span><span class="workspace-work-hub-item-copy"><strong></strong><small>${esc((item.status || '').replace('_', ' '))}</small></span><span class="workspace-work-hub-item-chevron" aria-hidden="true">▸</span>`;
          toggle.querySelector('strong').textContent = item.title;
          const details = document.createElement('div'); details.className = 'workspace-work-hub-details'; details.hidden = !expanded;
          const description = document.createElement('p'); description.textContent = item.description || 'No description added.'; details.appendChild(description);
          const meta = document.createElement('small'); meta.textContent = `Priority: ${item.priority || 'none'}`; details.appendChild(meta);
          const openItem = document.createElement('button'); openItem.type = 'button'; openItem.className = 'workspace-work-hub-item-open'; openItem.textContent = 'Open in Work Hub'; openItem.onclick = () => openWorkHubItem(item.id, projectId); details.appendChild(openItem);
          toggle.onclick = () => { if (workspaceExpandedItems.has(item.id)) workspaceExpandedItems.delete(item.id); else workspaceExpandedItems.add(item.id); renderWorkspaceWorkHub(); };
          card.append(toggle, details); list.appendChild(card);
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
