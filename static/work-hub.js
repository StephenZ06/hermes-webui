/* Work Hub: vanilla-JS client for the local state, using curated mx-icons SVGs. */
(() => {
  const DEFAULT_INSPECTOR_WIDTH = 280;
  let currentInspectorWidth = (() => { const raw = localStorage.getItem('workHubInspectorWidth'); return raw ? parseInt(raw, 10) : DEFAULT_INSPECTOR_WIDTH; })();
  const MIN_INSPECTOR_WIDTH = 200;
  const MAX_INSPECTOR_WIDTH = 600;
  const store = { items: [], projects: [], profiles: [], statuses: [], workflows: [], revision: 0, stale: false, activeScope: 'all', activeView: 'board', selectedItemId: null, search: '' };
  const icon = (name) => window.WorkHubIcons ? window.WorkHubIcons(name) : '';
  const el = (id) => document.getElementById(id);
  const esc = (value) => String(value || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const scopedItems = () => store.items.filter(item => (store.activeScope === 'all' ? true : store.activeScope === 'inbox' ? !item.project_id : item.project_id === store.activeScope) && (!store.search || item.title.toLowerCase().includes(store.search)));

  async function request(path, options) { return api(path, options); }
  async function loadWorkHubPanel() {
    const root = el('workHub'); if (!root) return;
    try {
      const data = await request('/api/work_hub/bootstrap');
      if ((data.revision || 0) < store.revision) return;
      store.items = data.items || []; store.projects = data.projects || []; store.profiles = data.profiles || []; store.statuses = data.statuses || []; store.workflows = data.workflows || []; store.revision = data.revision || 0; store.stale = false;
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
    wrap.innerHTML = `<section class="work-hub-canvas"><div class="work-hub-toolbar"><div class="work-hub-view-switch"><button class="${store.activeView === 'board' ? 'active' : ''}" data-view="board">${icon('board')} Board</button><button class="${store.activeView === 'list' ? 'active' : ''}" data-view="list">${icon('list')} List</button></div><label class="work-hub-search">${icon('search')}<input id="workHubSearch" type="search" placeholder="Search work" value="${esc(store.search)}"></label><button class="work-hub-create" id="workHubCreate">${icon('plus')} New item</button></div><div class="work-hub-live" role="status">${store.stale ? 'Showing saved data — retrying…' : `${items.length} work item${items.length === 1 ? '' : 's'}`}</div><div id="workHubCanvas"></div></section><div class="work-hub-resizer"></div><aside class="work-hub-inspector" id="workHubInspector" aria-label="Work item details"></aside>`;
    root.appendChild(wrap);
    initResizer(wrap);
    renderWorkHubNavigation();
    renderCanvas(items); renderInspector(); bind();
  }
  function renderWorkHubNavigation() {
    const sidebar = el('workHubSidebar'); if (!sidebar) return;
    sidebar.innerHTML = `<nav class="work-hub-nav" aria-label="Work Hub filters"><button class="work-hub-scope ${store.activeScope === 'inbox' ? 'active' : ''}" data-scope="inbox">${icon('inbox')}<span>Inbox</span></button><button class="work-hub-scope ${store.activeScope === 'all' ? 'active' : ''}" data-scope="all">${icon('work')}<span>All work</span></button><div class="work-hub-nav-label">PROJECTS</div><div id="workHubProjects" style="flex:1;min-height:0;overflow:auto;"></div></nav><button class="work-hub-plan-goal" id="workHubPlanGoal">${icon('sparkles')}<span>Plan goal</span></button>`;
    const projectList = el('workHubProjects');
    store.projects.forEach(project => { const b = document.createElement('button'); b.className = 'work-hub-scope' + (store.activeScope === project.project_id ? ' active' : ''); b.dataset.scope = project.project_id; b.innerHTML = `${icon('folder')}<span></span>`; b.querySelector('span').textContent = project.name || 'Untitled project'; projectList.appendChild(b); });
  }
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
    store.statuses.forEach(status => { const column = document.createElement('section'); column.className = 'work-hub-column'; column.dataset.status = status.id; column.innerHTML = `<header><span class="work-hub-status status-${esc(status.id)}"></span><strong>${esc(status.label)}</strong><small>${items.filter(x => x.status === status.id).length}</small></header><div class="work-hub-cards"></div>`; const cards = column.querySelector('.work-hub-cards'); items.filter(x => x.status === status.id).forEach(item => { const card = document.createElement('button'); card.className = 'work-hub-card'; card.draggable = true; card.dataset.itemId = item.id; card.innerHTML = `<span class="work-hub-card-title"></span><small>${esc(item.priority || 'none')}</small>`; card.querySelector('.work-hub-card-title').textContent = item.title; cards.appendChild(card); }); board.appendChild(column); });
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
    const planGoal = el('workHubPlanGoal');
    if (planGoal) planGoal.onclick = () => openGoalPlannerDialog({ projectId: store.activeScope !== 'all' && store.activeScope !== 'inbox' ? store.activeScope : null, onCreated: () => loadWorkHubPanel() });
    document.querySelectorAll('[data-view]').forEach(button => button.onclick = () => { store.activeView = button.dataset.view; render(); });
    document.querySelectorAll('[data-item-id]').forEach(button => button.onclick = () => { store.selectedItemId = button.dataset.itemId; renderInspector(); });
    const search = el('workHubSearch'); if (search) search.oninput = () => { store.search = search.value.toLowerCase(); renderCanvas(scopedItems()); bind(); };
    const create = el('workHubCreate'); if (create) create.onclick = createItem;
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
  window.loadWorkHubPanel = loadWorkHubPanel; window.refreshWorkHubForProject = refreshWorkHubForProject;
})();

/* Goal Planner dialog UI (vanilla JS, depends on window.GoalPlanner in static/goal-planner.js). */
(function(){
  const icon = (name) => window.WorkHubIcons ? window.WorkHubIcons(name) : '';
  const esc = (value) => String(value || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  let currentPlan = null;
  let currentOptions = {};
  let createdItems = [];
  let createdRevision = null;

  async function fetchProjects() { try { const data = await api('/api/projects?all_profiles=1'); return (data.projects || []).filter(p => p && p.project_id); } catch (e) { return []; } }

  function closeDialog() { const o = document.querySelector('.goal-planner-overlay'); if (o) o.remove(); currentPlan = null; createdItems = []; createdRevision = null; }

  function renderPlanSteps(plan) {
    if (!plan || !plan.steps || !plan.steps.length) return `<div class="goal-planner-empty">Enter a goal above and click Plan to see A* generated steps.</div>`;
    const meta = plan.meta || {};
    return `<div class="goal-planner-meta"><span class="tag">${esc(meta.domain)}</span><span>${esc(meta.action)}</span></div><div class="goal-planner-steps">${plan.steps.map(s => `<div class="goal-planner-step"><div class="goal-planner-step-id">${esc(s.id)}</div><div class="goal-planner-step-body"><div class="goal-planner-step-title">${esc(s.title)}</div><div class="goal-planner-step-desc">${esc(s.description)}</div></div></div>`).join('')}</div>`;
  }

  function buildDialog(projectId, projects) {
    const active = projects.find(p => p.project_id === projectId);
    return `<div class="goal-planner-overlay"><div class="goal-planner-dialog" role="dialog" aria-labelledby="goalPlannerTitle"><div class="goal-planner-head"><h3 id="goalPlannerTitle">${icon('sparkles')} Plan goal</h3><button id="goalPlannerClose" aria-label="Close">${icon('close')}</button></div><div class="goal-planner-body"><div class="goal-planner-field"><textarea id="goalPlannerInput" placeholder="Paste notes, a rough task list, or a draft plan and the AI will turn it into structured work items"></textarea><button id="goalPlannerBtn" type="button">Plan</button></div><div id="goalPlannerProjectSelect" style="margin-bottom:12px">${renderProjectSelect(active, projects)}</div><div id="goalPlannerResult">${renderPlanSteps(null)}</div></div><div class="goal-planner-actions"><button id="goalPlannerCancel">Cancel</button><button id="goalPlannerCreate" class="primary" disabled>Create work items</button><button id="goalPlannerRun" class="primary" disabled>Run as workflow</button></div></div></div>`;
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
    document.getElementById('goalPlannerBtn').onclick = async () => {
      const input = document.getElementById('goalPlannerInput');
      const goal = input.value.trim(); if (!goal) return;
      const btn = document.getElementById('goalPlannerBtn'); btn.disabled = true; btn.textContent = 'Planning…';
      try {
        const data = await api('/api/work_hub/plan/ai', { method: 'POST', body: JSON.stringify({ goal, project_id: currentOptions.projectId || null, preview: true }) });
        currentPlan = data && data.plan || null;
        if (!currentPlan) throw new Error('No plan returned');
        document.getElementById('goalPlannerResult').innerHTML = renderPlanSteps(currentPlan);
        document.getElementById('goalPlannerCreate').disabled = false;
      } catch (e) {
        document.getElementById('goalPlannerResult').innerHTML = `<div class="goal-planner-empty" style="color:var(--error)">Failed to plan: ${esc(e.message)}</div>`;
      } finally { btn.disabled = false; btn.textContent = 'Plan'; }
    };
    document.getElementById('goalPlannerCreate').onclick = async () => {
      if (!currentPlan) return;
      const btn = document.getElementById('goalPlannerCreate'); btn.disabled = true; btn.textContent = 'Creating…';
      try {
        const payload = { goal: currentPlan.goal, project_id: currentOptions.projectId || null };
        console.log('[work-hub plan ai create] sending payload', payload);
        const created = await api('/api/work_hub/plan/ai', { method: 'POST', body: JSON.stringify(payload) });
        createdItems = Array.isArray(created.items) ? created.items : [];
        createdRevision = created.revision;
        btn.textContent = 'Created';
        document.getElementById('goalPlannerRun').disabled = !currentOptions.projectId || !createdItems.length;
        if (typeof onCreated === 'function') onCreated(created);
      } catch (e) {
        console.error('[work-hub plan ai create] failed', e.status, e.body, e.message);
        btn.disabled = false; btn.textContent = 'Create work items';
        document.getElementById('goalPlannerResult').insertAdjacentHTML('afterbegin', `<div class="goal-planner-empty" style="color:var(--error);margin-bottom:8px">${esc(e.message)}</div>`);
      }
    };
    document.getElementById('goalPlannerRun').onclick = async () => {
      if (!currentOptions.projectId || !createdItems.length || !currentPlan) return;
      const btn = document.getElementById('goalPlannerRun'); btn.disabled = true; btn.textContent = 'Starting…';
      try {
        await api("/api/work_hub/workflows/start", { method: 'POST', body: JSON.stringify({ project_id: currentOptions.projectId, goal: currentPlan.goal, item_ids: createdItems.map(item => item.id), expected_revision: createdRevision, topology: 'sequential' }) });
        if (typeof onCreated === 'function') onCreated();
        closeDialog();
      } catch (e) {
        btn.disabled = false; btn.textContent = 'Run as workflow';
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
