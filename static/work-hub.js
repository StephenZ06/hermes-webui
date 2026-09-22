/* Work Hub: vanilla-JS client for the local state, using curated mx-icons SVGs. */
(() => {
  const store = { items: [], projects: [], profiles: [], statuses: [], revision: 0, stale: false, activeScope: 'all', activeView: 'board', selectedItemId: null, search: '' };
  const icon = (name) => window.WorkHubIcons ? window.WorkHubIcons(name) : '';
  const el = (id) => document.getElementById(id);
  const esc = (value) => String(value || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const scopedItems = () => store.items.filter(item => (store.activeScope === 'all' || store.activeScope === 'inbox' ? !item.project_id : item.project_id === store.activeScope) && (!store.search || item.title.toLowerCase().includes(store.search)));

  async function request(path, options) { return api(path, options); }
  async function loadWorkHubPanel() {
    const root = el('workHub'); if (!root) return;
    try {
      const data = await request('/api/work_hub/bootstrap');
      store.items = data.items || []; store.projects = data.projects || []; store.profiles = data.profiles || []; store.statuses = data.statuses || []; store.revision = data.revision || 0; store.stale = false;
    } catch (error) { store.stale = true; }
    render();
  }
  async function refreshWorkHubForProject(projectId) { store.activeScope = projectId || 'inbox'; await loadWorkHubPanel(); }
  function render() {
    const root = el('workHub'); if (!root) return;
    const items = scopedItems();
    root.innerHTML = '';
    const wrap = document.createElement('div'); wrap.className = 'work-hub' + (store.stale ? ' is-stale' : '');
    wrap.innerHTML = `<aside class="work-hub-nav"><button class="work-hub-scope ${store.activeScope === 'inbox' ? 'active' : ''}" data-scope="inbox">${icon('inbox')}<span>Inbox</span></button><button class="work-hub-scope ${store.activeScope === 'all' ? 'active' : ''}" data-scope="all">${icon('work')}<span>All work</span></button><div class="work-hub-nav-label">PROJECTS</div><div id="workHubProjects"></div></aside><section class="work-hub-canvas"><div class="work-hub-toolbar"><div class="work-hub-view-switch"><button class="${store.activeView === 'board' ? 'active' : ''}" data-view="board">${icon('board')} Board</button><button class="${store.activeView === 'list' ? 'active' : ''}" data-view="list">${icon('list')} List</button></div><label class="work-hub-search">${icon('search')}<input id="workHubSearch" type="search" placeholder="Search work" value="${esc(store.search)}"></label><button class="work-hub-create" id="workHubCreate">${icon('plus')} New item</button></div><div class="work-hub-live" role="status">${store.stale ? 'Showing saved data — retrying…' : `${items.length} work item${items.length === 1 ? '' : 's'}`}</div><div id="workHubCanvas"></div></section><aside class="work-hub-inspector" id="workHubInspector" aria-label="Work item details"></aside>`;
    root.appendChild(wrap);
    const projectList = el('workHubProjects');
    store.projects.forEach(project => { const b = document.createElement('button'); b.className = 'work-hub-scope' + (store.activeScope === project.project_id ? ' active' : ''); b.dataset.scope = project.project_id; b.innerHTML = `${icon('folder')}<span></span>`; b.querySelector('span').textContent = project.name || 'Untitled project'; projectList.appendChild(b); });
    renderCanvas(items); renderInspector(); bind();
  }
  function renderCanvas(items) {
    const canvas = el('workHubCanvas'); if (!canvas) return;
    if (store.activeView === 'list') {
      const table = document.createElement('div'); table.className = 'work-hub-list';
      items.forEach(item => { const row = document.createElement('button'); row.className = 'work-hub-list-row'; row.dataset.itemId = item.id; row.innerHTML = `<span class="work-hub-status status-${esc(item.status)}"></span><strong></strong><small>${esc(item.status.replace('_', ' '))}</small>`; row.querySelector('strong').textContent = item.title; table.appendChild(row); });
      canvas.appendChild(table); return;
    }
    const board = document.createElement('div'); board.className = 'work-hub-board';
    store.statuses.forEach(status => { const column = document.createElement('section'); column.className = 'work-hub-column'; column.dataset.status = status.id; column.innerHTML = `<header><span class="work-hub-status status-${esc(status.id)}"></span><strong>${esc(status.label)}</strong><small>${items.filter(x => x.status === status.id).length}</small></header><div class="work-hub-cards"></div>`; const cards = column.querySelector('.work-hub-cards'); items.filter(x => x.status === status.id).forEach(item => { const card = document.createElement('button'); card.className = 'work-hub-card'; card.dataset.itemId = item.id; card.innerHTML = `<span class="work-hub-card-title"></span><small>${esc(item.priority || 'none')}</small>`; card.querySelector('.work-hub-card-title').textContent = item.title; cards.appendChild(card); }); board.appendChild(column); });
    canvas.appendChild(board);
  }
  function renderInspector() {
    const panel = el('workHubInspector'); if (!panel) return;
    const item = store.items.find(row => row.id === store.selectedItemId);
    if (!item) { panel.innerHTML = `<div class="work-hub-inspector-empty">${icon('work')}<p>Select a work item to see details.</p></div>`; return; }
    const currentSessionId = typeof S !== 'undefined' && S.session ? S.session.session_id : null;
    panel.innerHTML = `<div class="work-hub-inspector-head"><span>WORK ITEM</span><button id="workHubClose" aria-label="Close details">${icon('close')}</button></div><h2></h2><label>Status<select id="workHubStatus">${store.statuses.map(s => `<option value="${esc(s.id)}" ${s.id === item.status ? 'selected' : ''}>${esc(s.label)}</option>`).join('')}</select></label><label>Hermes agent<select id="workHubAgent"><option value="">Unassigned</option>${store.profiles.map(p => `<option value="${esc(p.name)}" ${p.name === item.agent_profile ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select></label><label>Description<textarea id="workHubDescription" rows="7" placeholder="Add context, decisions, and next steps"></textarea></label>${currentSessionId ? '<button id="workHubLinkChat" class="work-hub-link">Link current chat</button>' : ''}<button id="workHubSave" class="work-hub-save">Save changes</button>`;
    panel.querySelector('h2').textContent = item.title; panel.querySelector('#workHubDescription').value = item.description || '';
    el('workHubClose').onclick = () => { store.selectedItemId = null; renderInspector(); };
    const linkChat = el('workHubLinkChat');
    if (linkChat) linkChat.onclick = () => updateItem(item.id, { linked_session_ids: [...new Set([...(item.linked_session_ids || []), currentSessionId])] });
    el('workHubSave').onclick = () => updateItem(item.id, { status: el('workHubStatus').value, agent_profile: el('workHubAgent').value || null, description: el('workHubDescription').value });
  }
  function bind() {
    document.querySelectorAll('.work-hub-scope').forEach(button => button.onclick = () => { store.activeScope = button.dataset.scope; store.selectedItemId = null; render(); });
    document.querySelectorAll('[data-view]').forEach(button => button.onclick = () => { store.activeView = button.dataset.view; render(); });
    document.querySelectorAll('[data-item-id]').forEach(button => button.onclick = () => { store.selectedItemId = button.dataset.itemId; renderInspector(); });
    const search = el('workHubSearch'); if (search) search.oninput = () => { store.search = search.value.toLowerCase(); renderCanvas(scopedItems()); };
    const create = el('workHubCreate'); if (create) create.onclick = createItem;
  }
  async function createItem() { const title = window.prompt('Work item title'); if (!title || !title.trim()) return; try { const result = await request('/api/work_hub/items/create', { method: 'POST', body: JSON.stringify({ item: { title, project_id: store.activeScope !== 'all' && store.activeScope !== 'inbox' ? store.activeScope : null }, expected_revision: store.revision }) }); store.items.push(result.item); store.revision = result.revision; store.selectedItemId = result.item.id; document.dispatchEvent(new CustomEvent('work-hub-changed')); render(); } catch (error) { store.stale = true; render(); } }
  async function updateItem(itemId, item) { try { const result = await request('/api/work_hub/items/update', { method: 'POST', body: JSON.stringify({ item_id: itemId, item, expected_revision: store.revision }) }); const index = store.items.findIndex(x => x.id === itemId); store.items[index] = result.item; store.revision = result.revision; document.dispatchEvent(new CustomEvent('work-hub-changed')); render(); } catch (error) { store.stale = true; render(); } }
  window.loadWorkHubPanel = loadWorkHubPanel; window.refreshWorkHubForProject = refreshWorkHubForProject;
})();
