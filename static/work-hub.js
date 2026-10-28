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

  // A chat is working on this item right now (see api/work_hub.mark_working).
  const NEW_ITEM_TITLE = 'New work item';
  const WORKING_BADGE = '<span class="work-hub-spinner" role="img" aria-label="A chat is working on this" title="A chat is working on this"></span>';
  async function request(path, options) { return api(path, options); }
  // Small menus fade out where they are before they go (the entrance is CSS).
  function dismissPopover(node) {
    if (!node || node.classList.contains('is-leaving')) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { node.remove(); return; }
    node.classList.add('is-leaving');
    setTimeout(() => node.remove(), 130);
  }
  function notifyWorkHubChanged() { document.dispatchEvent(new CustomEvent('work-hub-changed')); }
  // options.keepInspector: a background refresh (another page changed
  // projects, the window regained focus) leaves an open work item's panel as
  // it is, edits and all, instead of rebuilding it.
  async function loadWorkHubPanel(options = {}) {
    const root = el('workHub'); if (!root) return;
    try {
      const [data, quests] = await Promise.all([request('/api/work_hub/bootstrap'), request('/api/dashboard/quests').catch(() => null)]);
      store.questIds = new Set((quests && quests.item_ids) || []);
      if ((data.revision || 0) < store.revision) return;
      store.items = data.items || []; store.folders = data.folders || []; store.projects = data.projects || []; store.boards = data.boards || []; store.profiles = data.profiles || []; store.statuses = data.statuses || []; store.workflows = data.workflows || []; store.revision = data.revision || 0; store.stale = false;
    } catch (error) { store.stale = true; }
    render(options);
  }
  async function refreshWorkHubForProject(projectId) { store.activeScope = projectId || 'inbox'; await loadWorkHubPanel(); }
  function render(options = {}) {
    const root = el('workHub'); if (!root) return;
    const shownWrap = root.querySelector('.work-hub');
    if (options.keepInspector && shownWrap && store.selectedItemId && store.items.some(row => row.id === store.selectedItemId)
      && root.querySelector('#workHubInspector .wh-insp')?.dataset.itemId === store.selectedItemId) {
      // Refresh around the open panel without detaching it (that would drop
      // focus and replay its entrance).
      shownWrap.classList.toggle('is-stale', !!store.stale);
      const visible = scopedItems();
      const live = shownWrap.querySelector('.work-hub-live'); if (live) live.textContent = store.stale ? 'Showing saved data — retrying…' : `${visible.length} work item${visible.length === 1 ? '' : 's'}`;
      renderWorkHubNavigation(); renderCanvas(visible); bind();
      return;
    }
    const items = scopedItems();
    // The Board/List switch survives the rebuild, so its pill slides to the
    // new view instead of being drawn there.
    const keptSwitch = root.querySelector('.work-hub-view-switch');
    noteShownCounts(); noteShownItems();
    root.innerHTML = '';
    const wrap = document.createElement('div'); wrap.className = 'work-hub' + (store.stale ? ' is-stale' : '');
    const inspectorWidth = window.matchMedia('(max-width: 620px)').matches
      ? 220
      : Math.max(MIN_INSPECTOR_WIDTH, Math.min(MAX_INSPECTOR_WIDTH, currentInspectorWidth));
    wrap.style.setProperty('--wh-inspector-width', inspectorWidth + 'px');
    wrap.innerHTML = `<section class="work-hub-canvas"><div class="work-hub-toolbar"><div class="work-hub-view-switch" data-mi-tabs><button class="${store.activeView === 'board' ? 'active' : ''}" data-view="board">${icon('board')} Board</button><button class="${store.activeView === 'list' ? 'active' : ''}" data-view="list">${icon('list')} List</button></div><label class="work-hub-search">${icon('search')}<input id="workHubSearch" type="search" placeholder="Search work" value="${esc(store.search)}"></label><button class="work-hub-create work-hub-icon-button" id="workHubCreate" aria-label="New item" title="New item">${icon('plus')}</button></div><div class="work-hub-live" role="status">${store.stale ? 'Showing saved data — retrying…' : `${items.length} work item${items.length === 1 ? '' : 's'}`}</div><div id="workHubCanvas"></div></section><div class="work-hub-resizer"></div><aside class="work-hub-inspector" id="workHubInspector" aria-label="Work item details"></aside>`;
    if (keptSwitch) {
      keptSwitch.querySelectorAll('[data-view]').forEach(button => button.classList.toggle('active', button.dataset.view === store.activeView));
      wrap.querySelector('.work-hub-view-switch').replaceWith(keptSwitch);
    }
    root.appendChild(wrap);
    if (window.Micro && typeof window.Micro.tabs === 'function') window.Micro.tabs(wrap.querySelector('.work-hub-view-switch'));
    initResizer(wrap);
    renderWorkHubNavigation();
    renderCanvas(items); renderInspector(); bind();
    markCanvasEntrance();
  }
  // What the board shows changed (scope, project, board or view), not a
  // re-render from an edit or a refresh: the work items and the counts come
  // in with the Notes text entrance. Coming from the other view, the whole
  // board or list does.
  let lastCanvasKey = null;
  let lastCanvasView = null;
  // The counts on screen just before a redraw, so the new ones count up (or
  // down) from them instead of appearing.
  let shownCounts = null;
  function noteShownCounts() {
    const counts = {};
    document.querySelectorAll('#workHubCanvas .work-hub-column').forEach(column => { counts[column.dataset.status] = parseInt(column.querySelector('header small')?.textContent, 10) || 0; });
    const live = document.querySelector('#workHub .work-hub-live');
    counts.__total = live ? parseInt(live.textContent, 10) || 0 : 0;
    shownCounts = counts;
  }
  function countUp(node, from, to, format) {
    if (!node || from === to) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    // The box keeps the width of the wider of the two numbers, so its outline
    // stays still while the digits change.
    const width = value => { node.textContent = format(value); return node.getBoundingClientRect().width; };
    const held = Math.max(width(from), width(to));
    node.style.boxSizing = 'border-box'; node.style.minWidth = held + 'px';
    const start = performance.now(), duration = 520;
    const frame = now => {
      const t = Math.min(1, Math.max(0, (now - start) / duration));
      const eased = 1 - Math.pow(1 - t, 3);
      node.textContent = format(Math.round(from + (to - from) * eased));
      if (t < 1 && node.isConnected) { requestAnimationFrame(frame); return; }
      // Then the box eases to its own width (a number that lost a digit).
      node.style.minWidth = '';
      const natural = node.getBoundingClientRect().width;
      if (Math.abs(natural - held) < 0.5) { node.style.boxSizing = ''; return; }
      node.style.minWidth = held + 'px'; void node.offsetWidth;
      node.style.transition = 'min-width .2s ease'; node.style.minWidth = natural + 'px';
      setTimeout(() => { node.style.transition = ''; node.style.minWidth = ''; node.style.boxSizing = ''; }, 220);
    };
    node.textContent = format(from);
    requestAnimationFrame(frame);
  }
  function countUpCanvas(fromZero) {
    const from = fromZero ? {} : (shownCounts || {});
    document.querySelectorAll('#workHubCanvas .work-hub-column').forEach(column => {
      const badge = column.querySelector('header small'); const to = parseInt(badge?.textContent, 10) || 0;
      countUp(badge, from[column.dataset.status] || 0, to, String);
    });
    const live = document.querySelector('#workHub .work-hub-live');
    if (!live || store.stale) return;
    const label = n => `${n} work item${n === 1 ? '' : 's'}`;
    const total = scopedItems().length;
    live.textContent = label(total);
    // Screen readers hear the final count once, not every step.
    live.setAttribute('aria-busy', 'true'); setTimeout(() => live.removeAttribute('aria-busy'), 560);
    countUp(live, from.__total || 0, total, label);
  }
  function markCanvasEntrance() {
    const canvasKey = [store.activeScope, store.activeFolderId, store.activeBoardId].join('|');
    const viewChanged = lastCanvasView !== null && store.activeView !== lastCanvasView;
    const scopeChanged = lastCanvasKey !== null && canvasKey !== lastCanvasKey;
    lastCanvasKey = canvasKey; lastCanvasView = store.activeView;
    if (!viewChanged && !scopeChanged) return;
    const canvas = el('workHubCanvas'); if (!canvas) return;
    if (viewChanged) canvas.classList.add('is-entering-all'); else flipShownItems(canvas);
    countUpCanvas(viewChanged);
  }
  // Where each card (or list row) sat just before a redraw. On a scope change
  // the items both scopes share glide from there to their new place. In each
  // column the other cards keep their slots in order and only their text
  // changes, with the Notes text entrance; only the extra cards come in, or
  // fade where they were, so the board changes by the difference instead of
  // being redrawn.
  let shownItems = null;
  let leavingGhosts = [];
  function noteShownItems() {
    leavingGhosts.forEach(ghost => ghost.remove()); leavingGhosts = [];
    const canvas = el('workHubCanvas');
    shownItems = new Map();
    if (!canvas) return;
    canvas.querySelectorAll('.work-hub-card[data-item-id], .work-hub-list-row[data-item-id]').forEach(node => {
      const box = node.getBoundingClientRect();
      const clip = (node.closest('.work-hub-cards') || canvas).getBoundingClientRect();
      // Only what was on screen counts; a card scrolled out of its column has nowhere to leave from.
      if (box.bottom <= clip.top || box.top >= clip.bottom || box.right <= clip.left || box.left >= clip.right) return;
      shownItems.set(node.dataset.itemId, { node, box, clip, group: node.closest('.work-hub-column')?.dataset.status || 'list' });
    });
  }
  function flipShownItems(canvas) {
    const before = shownItems; shownItems = null;
    if (!before || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const easing = 'cubic-bezier(.2,.8,.2,1)';
    const kept = new Set();
    const nodes = [...canvas.querySelectorAll('.work-hub-card[data-item-id], .work-hub-list-row[data-item-id]')];
    nodes.forEach(node => { if (before.has(node.dataset.itemId)) kept.add(node.dataset.itemId); });
    // The slots the old cards leave free, per column, top to bottom.
    const freeSlots = {};
    before.forEach((was, id) => { if (!kept.has(id)) (freeSlots[was.group] = freeSlots[was.group] || []).push(id); });
    const glide = (node, from, box) => {
      const dx = from.left - box.left, dy = from.top - box.top;
      if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return;
      node.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: 'none' }], { duration: 340, easing });
    };
    nodes.forEach(node => {
      const box = node.getBoundingClientRect();
      const was = before.get(node.dataset.itemId);
      if (was) { glide(node, was.box, box); return; }
      const clip = (node.closest('.work-hub-cards') || canvas).getBoundingClientRect();
      if (box.bottom <= clip.top || box.top >= clip.bottom) return;
      const slot = freeSlots[node.closest('.work-hub-column')?.dataset.status || 'list']?.shift();
      if (slot) {
        // Takes over an old card's slot: the card stays, its text changes.
        kept.add(slot); glide(node, before.get(slot).box, box);
        [...node.children].forEach(part => part.animate([{ opacity: 0, filter: 'blur(2px)' }, { opacity: 1, filter: 'none' }], { duration: 240, easing: 'ease-out', fill: 'backwards' }));
        return;
      }
      node.animate([{ opacity: 0, transform: 'translateY(8px) scale(.98)' }, { opacity: 1, transform: 'none' }], { duration: 260, delay: 120, easing, fill: 'backwards' });
    });
    before.forEach(({ node, box, clip }, id) => {
      if (kept.has(id)) return;
      const ghost = node.cloneNode(true);
      ghost.removeAttribute('data-item-id'); ghost.removeAttribute('id'); ghost.setAttribute('aria-hidden', 'true'); ghost.classList.add('work-hub-leaving');
      // Held where it was, clipped to the column it scrolled in.
      Object.assign(ghost.style, { position: 'fixed', left: box.left + 'px', top: box.top + 'px', width: box.width + 'px', height: box.height + 'px', margin: '0', pointerEvents: 'none', zIndex: '5', boxSizing: 'border-box',
        clipPath: `inset(${Math.max(0, clip.top - box.top)}px ${Math.max(0, box.right - clip.right)}px ${Math.max(0, box.bottom - clip.bottom)}px ${Math.max(0, clip.left - box.left)}px)` });
      document.body.appendChild(ghost); leavingGhosts.push(ghost);
      ghost.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'scale(.97)' }], { duration: 180, easing: 'ease-out', fill: 'forwards' })
        .finished.then(() => { ghost.remove(); leavingGhosts = leavingGhosts.filter(entry => entry !== ghost); }, () => {});
    });
  }
  function renderWorkHubNavigation() {
    const sidebar = el('workHubSidebar'); if (!sidebar) return;
    sidebar.innerHTML = `<nav class="work-hub-nav" aria-label="Work Hub filters"><button class="work-hub-scope ${store.activeScope === 'inbox' ? 'active' : ''}" data-scope="inbox">${icon('inbox')}<span>Inbox</span></button><button class="work-hub-scope ${store.activeScope === 'all' ? 'active' : ''}" data-scope="all"><span class="work-hub-scope-mark work-hub-scope-mark--all" aria-hidden="true"></span><span>All work</span></button><div class="work-hub-nav-label work-hub-projects-heading"><span>WORKSPACES</span></div><div id="workHubProjects" class="project-folder-list work-hub-projects" style="min-height:0;overflow:auto;"></div><div class="work-hub-project-create-row">${store.deleteMode
      ? '<button type="button" class="work-hub-project-delete-done" id="workHubDeleteDone">Done</button>'
      : `<button type="button" class="work-hub-project-create" id="workHubProjectCreate" aria-label="New board, new project or delete project">${icon('plus')}</button>`}</div></nav><button class="work-hub-plan-goal" id="workHubPlanGoal">${icon('sparkles')}<span>Plan goal</span></button>`;
    const projectList = el('workHubProjects');
    projectList.classList.toggle('is-delete-mode', !!store.deleteMode);
    store.projects.forEach(project => {
      const boards = store.boards.filter(board => board.project_id === project.project_id); const count = boards.length;
      // Delete mode opens every folder so its boards can be deleted too.
      const expanded = !!store.expandedProjects[project.project_id] || (!!store.deleteMode && count > 0);
      const b = document.createElement('button'); b.type = 'button'; b.className = 'project-chip project-folder-row work-hub-project-tile' + (store.activeFolderId === project.project_id ? ' active' : ''); b.dataset.scope = project.project_id; b.dataset.projectToggle = project.project_id; b.setAttribute('aria-expanded', String(expanded)); b.setAttribute('aria-controls', `workHubFolderBoards-${project.project_id}`);
      b.innerHTML = `<span class="project-folder-chevron work-hub-project-chevron ${expanded ? 'expanded' : ''}">▸</span><span class="color-dot work-hub-project-color" aria-hidden="true"></span><span class="project-folder-name work-hub-project-name"></span><span class="project-folder-count work-hub-project-count" aria-label="${count} boards">${count}</span>`;
      b.querySelector('.work-hub-project-name').textContent = project.name || 'Untitled project';
      b.querySelector('.work-hub-project-color').style.background = project.color || 'var(--accent)';
      if (store.deleteMode && project.deletable) {
        const wrap = document.createElement('div');
        wrap.className = 'work-hub-project-delete-wrap';
        wrap.appendChild(b);
        decorateDeleteModeItem(wrap, { label: `Delete ${project.name || 'project'}`, index: projectList.children.length, onDelete: () => deleteWorkHubProject(project.project_id) });
        wrap.querySelector('.dm-x').dataset.deleteProjectId = project.project_id;
        projectList.appendChild(wrap);
      } else {
        if (store.deleteMode) lockDeleteModeItem(b, 'Holds chats or work items -- it stays with the chat page');
        projectList.appendChild(b);
      }
      const boardsList = document.createElement('div'); boardsList.id = `workHubFolderBoards-${project.project_id}`; boardsList.className = 'project-folder-sessions work-hub-project-boards' + (expanded ? ' expanded' : ''); boardsList.inert = !expanded;
      const boardsInner = document.createElement('div'); boardsInner.className = 'project-folder-sessions-inner work-hub-project-boards-inner';
      boards.forEach(board => { const row = document.createElement('div'); row.className = 'work-hub-board-row' + (store.activeBoardId === board.id ? ' active' : ''); row.innerHTML = `<button type="button" data-board-id="${esc(board.id)}" data-folder-id="${esc(project.project_id)}">${icon('board')}<span>${esc(board.name)}</span></button><button type="button" class="work-hub-board-rename" data-rename-board="${esc(board.id)}" aria-label="Rename ${esc(board.name)}" title="Rename ${esc(board.name)}">${icon('pencil')}</button><button type="button" class="work-hub-board-delete" data-delete-board="${esc(board.id)}" aria-label="Delete ${esc(board.name)}">${icon('close')}</button>`; if (store.deleteMode) { decorateDeleteModeItem(row, { label: `Delete board ${board.name}`, index: boardsInner.children.length + 1, onDelete: () => deleteWorkHubBoard(board.id) }); row.querySelector('.dm-x').dataset.deleteBoardMode = board.id; } boardsInner.appendChild(row); });
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
      markArrival(document.querySelector(`[data-project-toggle="${CSS.escape(result.project.project_id)}"]`));
    } catch (error) {
      store.stale = true; render();
      if (typeof showToast === 'function') showToast(`Project create failed: ${error.message || error}`);
    }
  }
  // Delete mode: like holding an app icon on iOS (shared createDeleteMode in
  // ui.js). Deletable folders (created here, or empty -- the server marks
  // them `deletable`) and every board wiggle with an X; folders holding chats
  // or work stay still. Done, Escape or a click elsewhere leaves it. The X
  // still confirms: a delete removes boards and work items.
  // Created on first use, so the module loads even where ui.js has not.
  let projectDeleteModeRef = null;
  const projectDeleteMode = () => projectDeleteModeRef || (projectDeleteModeRef = createDeleteMode({
    isInside: target => !!target.closest('.work-hub-projects, .work-hub-project-create-row'),
    onChange: active => { store.deleteMode = active; renderWorkHubNavigation(); bind(); },
  }));
  function enterProjectDeleteMode() {
    const anything = store.projects.some(project => project && project.deletable) || store.boards.some(board => board.project_id);
    if (!anything) {
      if (typeof showToast === 'function') showToast('There are no Work Hub projects or boards to delete.');
      return;
    }
    projectDeleteMode().enter();
  }
  function exitProjectDeleteMode() { if (projectDeleteModeRef) projectDeleteModeRef.exit(); }
  function workHubHasDeletables() {
    return store.projects.some(project => project && project.deletable) || store.boards.some(board => board.project_id);
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
      const folder = document.querySelector(`[data-project-toggle="${CSS.escape(projectId)}"]`);
      await Promise.all([animateRemoval(folder && (folder.closest('.work-hub-project-delete-wrap') || folder)), animateRemoval(el(`workHubFolderBoards-${projectId}`))]);
      if (store.activeFolderId === projectId) { store.activeFolderId = null; store.activeScope = 'all'; store.activeBoardId = null; }
      delete store.expandedProjects[projectId];
      await loadWorkHubPanel(); notifyWorkHubChanged();
      if (typeof showToast === 'function') showToast(`Deleted "${name}"`);
      if (!workHubHasDeletables()) exitProjectDeleteMode();
    } catch (error) {
      store.stale = true; render();
      if (typeof showToast === 'function') showToast(`Project delete failed: ${error.message || error}`);
    }
  }
  function showWorkHubBoardProjectPicker(anchor) { return showWorkHubProjectPicker(anchor, store.projects, 'Create a project workspace before creating a board.'); }
  function showWorkHubProjectPicker(anchor, projects, emptyMessage) { if (!projects.length) { if (typeof showToast === 'function') showToast(emptyMessage); return Promise.resolve(null); } document.querySelectorAll('.work-hub-project-picker').forEach(picker => picker.remove()); return new Promise(resolve => { const host = el('workHubProjectCreate')?.parentElement || anchor?.parentElement; if (!host) return resolve(null); const picker = document.createElement('div'); picker.className = 'project-picker work-hub-project-picker'; let closed = false; const finish = projectId => { if (closed) return; closed = true; dismissPopover(picker); document.removeEventListener('click', close); resolve(projectId); }; const close = event => { if (!picker.contains(event.target) && !anchor?.contains(event.target)) finish(null); }; projects.forEach(project => { const item = document.createElement('div'); item.className = 'project-picker-item'; const dot = document.createElement('span'); dot.className = 'color-dot'; dot.style.cssText = 'width:6px;height:6px;border-radius:50%;background:' + (project.color || 'var(--muted)') + ';flex-shrink:0;'; const name = document.createElement('span'); name.textContent = project.name || 'Untitled project'; item.append(dot, name); item.onclick = () => finish(project.project_id); picker.appendChild(item); }); host.appendChild(picker); setTimeout(() => document.addEventListener('click', close), 0); }); }
  async function createWorkHubBoard(anchor) { const projectId = await showWorkHubBoardProjectPicker(anchor); if (!projectId) return; const name = await showPromptDialog({ title: 'New board', message: 'Name this board.', placeholder: 'Board name', confirmLabel: 'Create' }); if (!name || !name.trim()) return; try { const result = await request('/api/work_hub/boards/create', { method: 'POST', body: JSON.stringify({ board: { name: name.trim(), project_id: projectId }, expected_revision: store.revision }) }); store.activeFolderId = projectId; store.activeScope = projectId; store.activeBoardId = result.board.id; store.expandedProjects[projectId] = true; await loadWorkHubPanel(); notifyWorkHubChanged(); const newBoard = document.querySelector(`[data-board-id="${CSS.escape(result.board.id)}"]`); markArrival(newBoard && newBoard.closest('.work-hub-board-row')); } catch (error) { store.stale = true; render(); } }
  async function renameWorkHubBoard(boardId) { const board = store.boards.find(row => row.id === boardId); if (!board) return; const name = await showPromptDialog({ title: 'Rename board', message: 'Choose a new board name.', placeholder: 'Board name', value: board.name || '', selectAll: true, confirmLabel: 'Rename' }); if (!name || !name.trim() || name.trim() === board.name) return; try { await request('/api/work_hub/boards/rename', { method: 'POST', body: JSON.stringify({ board_id: boardId, board: { name: name.trim() }, expected_revision: store.revision }) }); await loadWorkHubPanel(); notifyWorkHubChanged(); } catch (error) { store.stale = true; render(); if (typeof showToast === 'function') showToast(`Board rename failed: ${error.message || error}`); } }
  async function deleteWorkHubBoard(boardId) { const board = store.boards.find(entry => entry.id === boardId); const message = board?.default ? 'This clears every work item from the main board. The board itself stays as an empty board.' : 'This permanently removes the board and every work item on it.'; if (!await showConfirmDialog({ title: 'Delete board', message, confirmLabel: 'Delete', danger: true })) return; try { await request('/api/work_hub/boards/delete', { method: 'POST', body: JSON.stringify({ board_id: boardId, expected_revision: store.revision }) }); const boardRow = document.querySelector(`[data-board-id="${CSS.escape(boardId)}"]`); if (!board?.default || store.boards.filter(entry => entry.project_id === board.project_id).length > 1) await animateRemoval(boardRow && boardRow.closest('.work-hub-board-row')); if (store.activeBoardId === boardId) store.activeBoardId = null; await loadWorkHubPanel(); notifyWorkHubChanged(); if (store.deleteMode && !workHubHasDeletables()) exitProjectDeleteMode(); } catch (error) { store.stale = true; render(); if (typeof showToast === 'function') showToast(`Board delete failed: ${error.message || error}`); } }
  function workHubColumnItems(items, statusId) {
    const filter = store.boardFilters[statusId] || {};
    const rows = items.filter(item => item.status === statusId && (!filter.priority || item.priority === filter.priority) && (!filter.query || item.title.toLowerCase().includes(filter.query)));
    const stamp = (item, key) => Number(item[key] || item.created_at || 0);
    const sorters = { newest: (a, b) => stamp(b, 'created_at') - stamp(a, 'created_at'), oldest: (a, b) => stamp(a, 'created_at') - stamp(b, 'created_at'), updated: (a, b) => stamp(b, 'updated_at') - stamp(a, 'updated_at'), title: (a, b) => String(a.title || '').localeCompare(String(b.title || ''), undefined, { sensitivity: 'base' }) };
    return sorters[filter.sort] ? rows.slice().sort(sorters[filter.sort]) : rows;
  }
  // Beside a column's count: how many of its items a chat is working on now.
  function workingColumnBadge(columnItems) {
    const working = columnItems.filter(item => item.working).length;
    return working ? `<span class="work-hub-column-badge" title="${working} item${working === 1 ? '' : 's'} being worked on by a chat"><span class="work-hub-spinner" aria-hidden="true"></span>${working} working</span>` : '';
  }
  function fillWorkHubCards(cards, columnItems) {
    cards.textContent = '';
    columnItems.forEach(item => { const card = document.createElement('button'); card.className = 'work-hub-card' + (item.working ? ' is-working' : ''); card.draggable = true; card.dataset.itemId = item.id; card.innerHTML = `<span class="work-hub-card-title"></span><small>${item.working ? WORKING_BADGE : ''}${store.questIds && store.questIds.has(item.id) ? '<span class="work-hub-quest-mark" title="On your Dashboard quests" aria-label="Quest">⚔</span>' : ''}${esc(item.priority || 'none')}</small>`; card.querySelector('.work-hub-card-title').textContent = item.title; cards.appendChild(card); });
  }
  // Typing in a column filter updates that column's cards in place. Replacing
  // the input would drop focus, and the iOS keyboard with it.
  function refreshWorkHubColumn(statusId) {
    const column = document.querySelector(`.work-hub-column[data-status="${CSS.escape(statusId)}"]`);
    if (!column) return renderCanvas(scopedItems());
    const columnItems = workHubColumnItems(scopedItems(), statusId);
    const count = column.querySelector('header small'); if (count) count.textContent = columnItems.length;
    const oldBadge = column.querySelector('.work-hub-column-badge'); if (oldBadge) oldBadge.remove();
    if (count) count.insertAdjacentHTML('afterend', workingColumnBadge(columnItems));
    fillWorkHubCards(column.querySelector('.work-hub-cards'), columnItems);
    document.querySelectorAll('[data-item-id]').forEach(button => { if (button.closest('.work-hub-cards') === column.querySelector('.work-hub-cards')) button.onclick = () => { store.selectedItemId = button.dataset.itemId; renderInspector(); }; });
    const board = column.closest('.work-hub-board'); if (board && board._bindCard) column.querySelectorAll('.work-hub-card').forEach(board._bindCard);
  }
  function renderCanvas(items) {
    const canvas = el('workHubCanvas'); if (!canvas) return;
    const oldWrap = canvas.querySelector('.work-hub-board-wrap');
    let prevBoardWrap = null;
    if (oldWrap) {
      const tops = {}; oldWrap.querySelectorAll('.work-hub-column').forEach(col => { const cards = col.querySelector('.work-hub-cards'); if (cards) tops[col.dataset.status] = cards.scrollTop; });
      prevBoardWrap = { left: oldWrap.scrollLeft, tops };
    }
    canvas.dataset.keepScroll = store.keepBoardScroll === false ? '0' : '1';
    // Redraws in place (a poll, a search, a column filter) come in still.
    canvas.classList.remove('is-entering-all');
    canvas.innerHTML = '';
    if (store.activeView === 'list') {
      const table = document.createElement('div'); table.className = 'work-hub-list';
      items.forEach(item => { const row = document.createElement('button'); row.className = 'work-hub-list-row' + (item.working ? ' is-working' : ''); row.dataset.itemId = item.id; row.innerHTML = `<span class="work-hub-status status-${esc(item.status)}"></span><strong></strong><small>${item.working ? WORKING_BADGE : ''}${esc(store.statuses.find(status => status.id === item.status)?.label || item.status.replace('_', ' '))}</small>`; row.querySelector('strong').textContent = item.title; table.appendChild(row); });
      canvas.appendChild(table); return;
    }
    // Rebuilding the board must not throw away where the user is: keep the
    // horizontal scroll (else a far-right column jumps back to Triage) and each
    // column's vertical scroll.
    const prevWrap = canvas.dataset.keepScroll === '1' ? prevBoardWrap : null;
    const boardWrap = document.createElement('div'); boardWrap.className = 'work-hub-board-wrap';
    const board = document.createElement('div'); board.className = 'work-hub-board';
    store.statuses.forEach(status => {
      const filter = store.boardFilters[status.id] || {};
      const columnItems = workHubColumnItems(items, status.id);
      const priorityOption = value => `<option value="${value}" ${filter.priority === value ? 'selected' : ''}>${value === 'none' ? 'No priority' : value[0].toUpperCase() + value.slice(1)}</option>`;
      const sortOption = ([value, label]) => `<option value="${value}" ${(filter.sort || '') === value ? 'selected' : ''}>${label}</option>`;
      const sorts = [['', 'Sort'], ['newest', 'Newest first'], ['oldest', 'Oldest first'], ['updated', 'Recently updated'], ['title', 'Title A–Z']];
      const filterPanel = store.boardFilterOpen === status.id ? `<div class="work-hub-column-filter"><input data-board-filter-query="${esc(status.id)}" type="text" enterkeyhint="search" autocomplete="off" placeholder="Filter items" aria-label="Filter items" value="${esc(filter.query || '')}"><select data-board-filter-priority="${esc(status.id)}" aria-label="Filter by priority"><option value="">Priority</option>${['high', 'medium', 'low', 'none'].map(priorityOption).join('')}</select><select data-board-filter-sort="${esc(status.id)}" aria-label="Sort items">${sorts.map(sortOption).join('')}</select></div>` : '';
      const column = document.createElement('section'); column.className = 'work-hub-column'; column.dataset.status = status.id;
      column.innerHTML = `<header><span class="work-hub-status status-${esc(status.id)}"></span><strong>${esc(status.label)}</strong><small>${columnItems.length}</small>${workingColumnBadge(columnItems)}<button class="work-hub-board-filter" type="button" data-board-filter="${esc(status.id)}" aria-label="Filter ${esc(status.label)}" title="Filter ${esc(status.label)}">${icon('filter')}</button></header>${filterPanel}<div class="work-hub-cards"></div>`;
      fillWorkHubCards(column.querySelector('.work-hub-cards'), columnItems);
      board.appendChild(column);
    });
    boardWrap.appendChild(board);
    canvas.appendChild(boardWrap);
    if (prevWrap) {
      boardWrap.scrollLeft = prevWrap.left;
      boardWrap.querySelectorAll('.work-hub-column').forEach(col => { const cards = col.querySelector('.work-hub-cards'); if (cards && prevWrap.tops[col.dataset.status]) cards.scrollTop = prevWrap.tops[col.dataset.status]; });
    }
    initDragAndDrop(board);
  }
  function workHubRelativeTime(epoch) {
    const seconds = Number(epoch);
    if (!Number.isFinite(seconds) || seconds <= 0) return '';
    const ms = seconds > 1e12 ? seconds : seconds * 1000;
    const diff = Math.max(0, (Date.now() - ms) / 1000);
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
    if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} d ago`;
    return new Date(ms).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }
  // Dashboard quests: an item can be put on (or taken off) the quest list here.
  async function fillQuestToggle(itemId) {
    const host = el('workHubQuest'); if (!host) return;
    let isQuest = false;
    try { isQuest = ((await request('/api/dashboard/quests')).item_ids || []).includes(itemId); } catch (_) { host.closest('.wh-insp-prop').remove(); return; }
    if (store.selectedItemId !== itemId || !el('workHubQuest')) return;
    host.innerHTML = isQuest
      ? '<span class="wh-quest-on">⚔ On your quests</span><button id="workHubQuestToggle" class="wh-insp-inline" type="button">Remove</button>'
      : '<span>Not a quest</span><button id="workHubQuestToggle" class="wh-insp-inline" type="button">Add to quests</button>';
    el('workHubQuestToggle').onclick = async () => {
      try {
        await request(isQuest ? '/api/dashboard/quests/remove' : '/api/dashboard/quests/add', { method: 'POST', body: JSON.stringify(isQuest ? { item_id: itemId } : { item_ids: [itemId] }) });
        if (typeof showToast === 'function') showToast(isQuest ? 'Removed from quests' : 'Added to your quests');
        store.questIds = store.questIds || new Set();
        if (isQuest) store.questIds.delete(itemId); else store.questIds.add(itemId);
        renderCanvas(scopedItems()); bind();
      } catch (error) { if (typeof showToast === 'function') showToast(error.message || 'Could not update quests'); }
      fillQuestToggle(itemId);
    };
  }
  function renderInspector() {
    const panel = el('workHubInspector'); if (!panel) return;
    const item = store.items.find(row => row.id === store.selectedItemId);
    // Phones show the details as a sheet over the board only while an item is selected.
    const hub = panel.closest('.work-hub'); if (hub) hub.classList.toggle('has-selection', !!item);
    if (!item) { panel.innerHTML = '<div class="work-hub-inspector-empty"><span class="work-hub-inspector-empty-mark" aria-hidden="true"></span><p>Select a work item to see details.</p></div>'; return; }
    const currentSessionId = typeof S !== 'undefined' && S.session ? S.session.session_id : null;
    const missingAgent = item.agent_profile && !store.profiles.some(profile => profile.name === item.agent_profile);
    const workflow = store.workflows.find(run => (run.steps || []).some(step => step.item_id === item.id && ['pending', 'running', 'paused'].includes(run.status)));
    const workflowControl = workflow ? `<div class="work-hub-workflow-state">Workflow: ${esc(workflow.status)}${workflow.pause_reason ? ` — ${esc(workflow.pause_reason)}` : ''}</div>${workflow.status === 'paused' ? '<button id="workHubResume" class="work-hub-save">Resume workflow</button>' : '<button id="workHubPause" class="work-hub-link">Pause workflow</button>'}` : '';
    const locked = !!workflow;
    const priorities = ['high', 'medium', 'low', 'none'];
    const itemPriority = priorities.includes(item.priority) ? item.priority : 'none';
    const updated = workHubRelativeTime(item.updated_at || item.created_at);
    const linkedCount = (item.linked_session_ids || []).length;
    const linkedHere = !!(currentSessionId && (item.linked_session_ids || []).includes(currentSessionId));
    // Layout: an editable title, a compact property list, the description, and
    // a pinned footer whose Save only lights up once something has changed.
    panel.innerHTML = `<div class="wh-insp" data-item-id="${esc(item.id)}">
      <header class="wh-insp-head"><span class="wh-insp-kicker"><span class="work-hub-status status-${esc(item.status)}" id="workHubStatusDot"></span>Work item</span><button id="workHubClose" class="wh-insp-close" aria-label="Close details" title="Close">${icon('close')}</button></header>
      ${workflowControl ? `<div class="wh-insp-workflow">${workflowControl}</div>` : ''}
      <input id="workHubTitle" class="wh-insp-title" type="text" maxlength="160" required aria-label="Title" placeholder="Untitled work item" ${locked ? 'disabled' : ''}>
      <dl class="wh-insp-props">
        <div class="wh-insp-prop"><dt>Status</dt><dd><select id="workHubStatus" aria-label="Status" ${locked ? 'disabled' : ''}>${store.statuses.map(s => `<option value="${esc(s.id)}" ${s.id === item.status ? 'selected' : ''}>${esc(s.label)}</option>`).join('')}</select></dd></div>
        <div class="wh-insp-prop"><dt>Hermes agent</dt><dd><select id="workHubAgent" aria-label="Hermes agent" ${locked ? 'disabled' : ''}><option value="">Unassigned</option>${missingAgent ? `<option value="${esc(item.agent_profile)}" selected>Unavailable: ${esc(item.agent_profile)}</option>` : ''}${store.profiles.map(p => `<option value="${esc(p.name)}" ${p.name === item.agent_profile ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select></dd></div>
        <div class="wh-insp-prop"><dt>Priority</dt><dd><select id="workHubPriority" aria-label="Priority" ${locked ? 'disabled' : ''}>${priorities.map(value => `<option value="${value}" ${value === itemPriority ? 'selected' : ''}>${value === 'none' ? 'None' : value[0].toUpperCase() + value.slice(1)}</option>`).join('')}</select></dd></div>
        <div class="wh-insp-prop"><dt>Linked chats</dt><dd class="wh-insp-static"><span>${linkedCount ? `${linkedCount} chat${linkedCount === 1 ? '' : 's'}` : 'None'}</span>${currentSessionId && !locked && !linkedHere ? '<button id="workHubLinkChat" class="wh-insp-inline" type="button">Link current chat</button>' : ''}</dd></div>
        ${updated ? `<div class="wh-insp-prop"><dt>Updated</dt><dd class="wh-insp-static">${esc(updated)}</dd></div>` : ''}
        ${item.status === 'done' || item.status === 'cancelled' ? '' : '<div class="wh-insp-prop"><dt>Quest</dt><dd class="wh-insp-static" id="workHubQuest"><span class="wh-quest-loading">…</span></dd></div>'}
      </dl>
      <section class="wh-insp-section"><label class="wh-insp-section-label" for="workHubDescription">Description</label><textarea id="workHubDescription" rows="7" placeholder="Add context, decisions, and next steps" ${locked ? 'disabled' : ''}></textarea></section>
      ${locked ? '' : `<footer class="wh-insp-foot"><button id="workHubDelete" class="wh-insp-delete" type="button" title="Delete work item">${icon('close')}<span>Delete</span></button><button id="workHubSave" class="work-hub-save" type="button" disabled>Save changes</button></footer>`}
    </div>`;
    // A new item's stand-in title shows as a placeholder, which clears when
    // the field is clicked; left empty, the item keeps that title.
    const untitled = item.title === NEW_ITEM_TITLE;
    el('workHubTitle').value = untitled ? '' : item.title; if (untitled) el('workHubTitle').placeholder = NEW_ITEM_TITLE;
    panel.querySelector('#workHubDescription').value = item.description || '';
    el('workHubClose').onclick = () => { closeInspectorAnimated(); };
    fillQuestToggle(item.id);
    const deleteButton = el('workHubDelete'); if (deleteButton) deleteButton.onclick = () => deleteItem(item.id);
    const linkChat = el('workHubLinkChat');
    if (linkChat) linkChat.onclick = () => updateItem(item.id, { linked_session_ids: [...new Set([...(item.linked_session_ids || []), currentSessionId])] });
    const saveButton = el('workHubSave');
    const fields = ['workHubTitle', 'workHubStatus', 'workHubAgent', 'workHubPriority', 'workHubDescription'].map(el).filter(Boolean);
    const titleValue = () => el('workHubTitle').value.trim() ? el('workHubTitle').value : (untitled ? item.title : '');
    const original = { title: item.title || '', status: item.status, agent: item.agent_profile || '', priority: itemPriority, description: item.description || '' };
    const isDirty = () => titleValue() !== original.title || el('workHubStatus').value !== original.status
      || el('workHubAgent').value !== original.agent || el('workHubPriority').value !== original.priority
      || el('workHubDescription').value !== original.description;
    const syncDirty = () => {
      if (saveButton) saveButton.disabled = !isDirty() || !titleValue().trim();
      const dot = el('workHubStatusDot'); if (dot) dot.className = `work-hub-status status-${el('workHubStatus').value}`;
    };
    fields.forEach(field => { field.addEventListener('input', syncDirty); field.addEventListener('change', syncDirty); });
    // Save: "Saving…", then a "Saved" check, then the panel closes and the
    // card flashes where it now sits. A failed save keeps the panel open.
    const save = async () => {
      if (!saveButton || saveButton.disabled || saveButton.dataset.state) return;
      const label = saveButton.innerHTML;
      saveButton.dataset.state = 'saving'; saveButton.disabled = true; saveButton.innerHTML = '<span class="wh-save-spinner" aria-hidden="true"></span>Saving…';
      const ok = await updateItem(item.id, { title: titleValue(), status: el('workHubStatus').value, agent_profile: el('workHubAgent').value || null, priority: el('workHubPriority').value, description: el('workHubDescription').value }, { deferRender: true });
      if (!ok) { delete saveButton.dataset.state; saveButton.innerHTML = label; syncDirty(); if (typeof showToast === 'function') showToast('Could not save the work item', 4000, 'error'); return; }
      saveButton.dataset.state = 'saved'; saveButton.innerHTML = `${icon('check')}<span>Saved</span>`;
      await new Promise(resolve => setTimeout(resolve, 650));
      await closeInspectorAnimated();
      revealItem(item.id);
    };
    if (saveButton) saveButton.onclick = save;
    // Ctrl/Cmd+Enter saves from anywhere in the panel.
    panel.onkeydown = event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); save(); } };
    const pauseButton = el('workHubPause'); if (pauseButton) pauseButton.onclick = () => changeWorkflow(workflow.id, 'pause');
    const resumeButton = el('workHubResume'); if (resumeButton) resumeButton.onclick = () => changeWorkflow(workflow.id, 'resume');
  }
  function bind() {
    document.querySelectorAll('.work-hub-scope').forEach(button => button.onclick = () => { store.activeScope = button.dataset.scope; store.selectedItemId = null; render(); });
    document.querySelectorAll('[data-delete-project-id]').forEach(button => button.onclick = event => { event.stopPropagation(); deleteWorkHubProject(button.dataset.deleteProjectId); });
    const deleteDone = el('workHubDeleteDone'); if (deleteDone) deleteDone.onclick = () => exitProjectDeleteMode();
    document.querySelectorAll('.work-hub-project-tile').forEach(button => button.onclick = (event) => { if (store.deleteMode) return; const projectId = button.dataset.projectToggle; const projectBoards = store.boards.filter(board => board.project_id === projectId); if (projectBoards.length <= 1 && !(event && event.target && event.target.closest && event.target.closest('.work-hub-project-chevron'))) { /* One board needs no disclosure: open it directly. The chevron still reveals the row (rename/delete). */ store.activeFolderId = projectId; store.activeScope = projectId; store.activeBoardId = projectBoards.length ? projectBoards[0].id : null; store.selectedItemId = null; render(); /* On a phone the drawer folds away so the opened board is what you see. */ if (typeof _closeMobileSidebarAfterPanelSelection === 'function') setTimeout(_closeMobileSidebarAfterPanelSelection, 0); return; } const expanded = !store.expandedProjects[projectId]; store.expandedProjects[projectId] = expanded; store.activeFolderId = projectId; store.activeScope = projectId; store.activeBoardId = null; store.selectedItemId = null; button.classList.add('active'); document.querySelectorAll('.work-hub-project-tile').forEach(other => { if (other !== button) other.classList.remove('active'); }); const chevron = button.querySelector('.work-hub-project-chevron'); if (chevron) chevron.classList.toggle('expanded', expanded); button.setAttribute('aria-expanded', String(expanded)); const boardsList = el(`workHubFolderBoards-${projectId}`); if (boardsList) { boardsList.classList.toggle('expanded', expanded); boardsList.inert = !expanded; } noteShownCounts(); noteShownItems(); renderCanvas(scopedItems()); renderInspector(); bind(); markCanvasEntrance(); });
    document.querySelectorAll('[data-board-id]').forEach(button => button.onclick = () => { if (store.deleteMode) return; store.activeFolderId = button.dataset.folderId; store.activeScope = button.dataset.folderId; store.expandedProjects[button.dataset.folderId] = true; store.activeBoardId = button.dataset.boardId; store.selectedItemId = null; render(); });
    document.querySelectorAll('[data-delete-board]').forEach(button => button.onclick = () => deleteWorkHubBoard(button.dataset.deleteBoard));
    document.querySelectorAll('[data-rename-board]').forEach(button => button.onclick = event => { event.stopPropagation(); renameWorkHubBoard(button.dataset.renameBoard); });
    const createProject = el('workHubProjectCreate'); if (createProject) createProject.onclick = () => { const old = document.querySelector('.work-hub-create-menu:not(.is-leaving)'); if (old) return dismissPopover(old); const menu = document.createElement('div'); menu.className = 'work-hub-create-menu'; menu.innerHTML = '<button type="button" data-create-board>New board</button><button type="button" data-create-project>New project</button><span class="work-hub-create-menu-sep" aria-hidden="true"></span><button type="button" class="is-danger" data-delete-project>Delete</button>'; createProject.parentElement.appendChild(menu); menu.querySelector('[data-create-board]').onclick = () => { dismissPopover(menu); createWorkHubBoard(createProject); }; menu.querySelector('[data-create-project]').onclick = () => { dismissPopover(menu); createWorkHubProject(); }; menu.querySelector('[data-delete-project]').onclick = () => { dismissPopover(menu); enterProjectDeleteMode(); }; };
    const planGoal = el('workHubPlanGoal');
    if (planGoal) planGoal.onclick = () => openGoalPlannerDialog({ projectId: store.activeScope !== 'all' && store.activeScope !== 'inbox' ? store.activeScope : null, onCreated: () => loadWorkHubPanel() });
    document.querySelectorAll('[data-view]').forEach(button => button.onclick = () => { store.activeView = button.dataset.view; render(); });
    document.querySelectorAll('.work-hub-card[data-item-id], .work-hub-list-row[data-item-id]').forEach(button => button.onclick = () => { store.selectedItemId = button.dataset.itemId; renderInspector(); });
    const search = el('workHubSearch'); if (search) search.oninput = () => { store.search = search.value.toLowerCase(); renderCanvas(scopedItems()); bind(); };
    const create = el('workHubCreate'); if (create) create.onclick = createItem;
    document.querySelectorAll('[data-board-filter]').forEach(button => button.onclick = () => { store.boardFilterOpen = store.boardFilterOpen === button.dataset.boardFilter ? null : button.dataset.boardFilter; renderCanvas(scopedItems()); bind(); });
    document.querySelectorAll('[data-board-filter-query]').forEach(input => input.oninput = () => { const status = input.dataset.boardFilterQuery; store.boardFilters[status] = { ...(store.boardFilters[status] || {}), query: input.value.toLowerCase() }; refreshWorkHubColumn(status); });
    document.querySelectorAll('[data-board-filter-sort]').forEach(select => select.onchange = () => { const status = select.dataset.boardFilterSort; store.boardFilters[status] = { ...(store.boardFilters[status] || {}), sort: select.value }; renderCanvas(scopedItems()); bind(); });
    document.querySelectorAll('[data-board-filter-priority]').forEach(select => select.onchange = () => { const status = select.dataset.boardFilterPriority; store.boardFilters[status] = { ...(store.boardFilters[status] || {}), priority: select.value }; renderCanvas(scopedItems()); bind(); });
  }
  function initDragAndDrop(board) {
    if (!board) return;
    let draggedId = null;
    let draggedHeight = 40;
    let draggedStatus = null;
    const bindCard = card => {
      card.addEventListener('dragstart', (e) => {
        draggedId = card.dataset.itemId;
        draggedHeight = card.offsetHeight;
        draggedStatus = (store.items.find(i => i.id === draggedId) || {}).status || null;
        e.dataTransfer.setData('text/plain', draggedId);
        e.dataTransfer.effectAllowed = 'move';
        if (typeof liftDragGhost === 'function') liftDragGhost(e, card);
        // After the drag image is captured, fade the original in place and
        // show which columns can take it (same states as the Jobs pipeline).
        requestAnimationFrame(() => { if (draggedId === card.dataset.itemId) card.classList.add('dragging'); });
        board.classList.add('is-dragging');
        board.querySelectorAll('.work-hub-column').forEach(c => c.classList.toggle('can-drop', c.dataset.status !== draggedStatus));
      });
      card.addEventListener('dragend', () => { card.classList.remove('dragging'); draggedId = null; hideDragSlot(); board.classList.remove('is-dragging'); board.querySelectorAll('.work-hub-column').forEach(c => c.classList.remove('drop-target', 'can-drop')); });
    };
    board.querySelectorAll('.work-hub-card').forEach(bindCard);
    // Cards redrawn in place by a column filter need both kinds of drag again.
    const bindTouchCard = initTouchDrag(board);
    board._bindCard = card => { bindCard(card); bindTouchCard(card); };
    board.querySelectorAll('.work-hub-column').forEach(column => {
      column.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        column.classList.add('drop-target');
        // A slot opens where the card will land (not in its own column).
        if (column.dataset.status !== draggedStatus) showDragSlot(column.querySelector('.work-hub-cards'), draggedHeight);
      });
      column.addEventListener('dragleave', (e) => {
        // Moving over a card inside the column also fires dragleave.
        if (e.relatedTarget && column.contains(e.relatedTarget)) return;
        column.classList.remove('drop-target'); hideDragSlot();
      });
      column.addEventListener('drop', async (e) => {
        e.preventDefault();
        column.classList.remove('drop-target');
        hideDragSlot();
        const itemId = e.dataTransfer.getData('text/plain');
        const status = column.dataset.status;
        if (!itemId || !status) return;
        const item = store.items.find(i => i.id === itemId);
        if (item && item.status !== status) {
          await updateItem(itemId, { status });
          markLanded(document.querySelector(`.work-hub-card[data-item-id="${CSS.escape(itemId)}"]`));
        }
      });
    });
  }
  // Touch: hold a card to pick it up, then drag it to another column. Native
  // HTML drag-and-drop never starts from a touch on iOS, so phones had no way
  // to move a card. A movement before the hold fires is an ordinary scroll; a
  // still tap still opens the card.
  const TOUCH_DRAG_HOLD_MS = 380;
  const TOUCH_DRAG_SLOP = 8;
  const TOUCH_DRAG_EDGE = 48;
  function initTouchDrag(board) {
    const wrap = board.closest('.work-hub-board-wrap') || board.parentElement;
    let drag = null;
    const columnAt = (x, y) => {
      // Clamped into the board: a finger held at the screen edge (where the
      // board auto-scrolls) is past its padding but still means that column.
      const r = wrap.getBoundingClientRect();
      const cx = Math.min(Math.max(x, r.left + 2), r.right - 14);
      const hit = document.elementFromPoint(cx, y);
      return hit && hit.closest ? hit.closest('.work-hub-column') : null;
    };
    const clearTargets = () => board.querySelectorAll('.work-hub-column.drop-target').forEach(c => c.classList.remove('drop-target'));
    const end = async (commit) => {
      const state = drag; drag = null;
      if (!state) return;
      clearTimeout(state.timer);
      if (state.raf) cancelAnimationFrame(state.raf);
      if (!state.active) return;
      state.card.classList.remove('touch-drag-source');
      state.ghost.remove();
      document.documentElement.classList.remove('work-hub-touch-dragging');
      hideDragSlot(); clearTargets();
      // The touch ends on the card: swallow the click it would make.
      state.card.addEventListener('click', (e) => { e.preventDefault(); e.stopImmediatePropagation(); }, { capture: true, once: true });
      const column = commit ? state.column : null;
      const status = column && column.dataset.status;
      const item = store.items.find(i => i.id === state.itemId);
      if (item && status && item.status !== status) {
        await updateItem(state.itemId, { status });
        markLanded(document.querySelector(`.work-hub-card[data-item-id="${CSS.escape(state.itemId)}"]`));
      }
    };
    const autoScroll = () => {
      if (!drag || !drag.active) return;
      const r = wrap.getBoundingClientRect();
      const dx = drag.x < r.left + TOUCH_DRAG_EDGE ? -1 : drag.x > r.right - TOUCH_DRAG_EDGE ? 1 : 0;
      if (dx) { wrap.scrollLeft += dx * 9; track(); }
      drag.raf = requestAnimationFrame(autoScroll);
    };
    const track = () => {
      if (!drag || !drag.active) return;
      drag.ghost.style.transform = `translate3d(${drag.x - drag.offsetX}px,${drag.y - drag.offsetY}px,0) rotate(1.5deg) scale(1.03)`;
      const column = columnAt(drag.x, drag.y);
      if (column !== drag.column) {
        clearTargets(); hideDragSlot();
        drag.column = column;
        if (column) {
          column.classList.add('drop-target');
          if (column.dataset.status !== drag.status) showDragSlot(column.querySelector('.work-hub-cards'), drag.height);
        }
      }
    };
    const bindTouchCard = card => {
      card.addEventListener('touchstart', (e) => {
        if (e.touches.length !== 1) return;
        const t = e.touches[0];
        const itemId = card.dataset.itemId;
        drag = { card, itemId, startX: t.clientX, startY: t.clientY, x: t.clientX, y: t.clientY, active: false, column: null, raf: 0,
          status: (store.items.find(i => i.id === itemId) || {}).status || null, height: card.offsetHeight };
        drag.timer = setTimeout(() => {
          if (!drag || drag.card !== card) return;
          const r = card.getBoundingClientRect();
          const ghost = card.cloneNode(true);
          ghost.classList.add('work-hub-card-ghost'); ghost.removeAttribute('id');
          ghost.style.width = r.width + 'px'; ghost.style.height = r.height + 'px';
          document.body.appendChild(ghost);
          Object.assign(drag, { active: true, ghost, offsetX: drag.x - r.left, offsetY: drag.y - r.top });
          card.classList.add('touch-drag-source');
          document.documentElement.classList.add('work-hub-touch-dragging');
          try { if (navigator.vibrate) navigator.vibrate(8); } catch (_) {}
          track();
          drag.raf = requestAnimationFrame(autoScroll);
        }, TOUCH_DRAG_HOLD_MS);
      }, { passive: true });
      card.addEventListener('touchmove', (e) => {
        if (!drag || drag.card !== card) return;
        const t = e.touches[0];
        drag.x = t.clientX; drag.y = t.clientY;
        if (!drag.active) {
          // Moved before the hold: this is a scroll, not a pick-up.
          if (Math.hypot(drag.x - drag.startX, drag.y - drag.startY) > TOUCH_DRAG_SLOP) { clearTimeout(drag.timer); drag = null; }
          return;
        }
        if (e.cancelable) e.preventDefault();
        track();
      }, { passive: false });
      card.addEventListener('touchend', () => { if (drag && drag.card === card) end(true); });
      card.addEventListener('touchcancel', () => { if (drag && drag.card === card) end(false); });
      // Long-press would otherwise open the iOS callout / text selection.
      card.addEventListener('contextmenu', (e) => { if (drag && drag.active) e.preventDefault(); });
    };
    board.querySelectorAll('.work-hub-card').forEach(bindTouchCard);
    return bindTouchCard;
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
      const result = await request('/api/work_hub/items/create', { method: 'POST', body: JSON.stringify({ item: Object.assign({ title: NEW_ITEM_TITLE, status: 'backlog', project_id: store.activeScope !== 'all' && store.activeScope !== 'inbox' ? store.activeScope : null }, store.activeBoardId ? { board_id: store.activeBoardId } : {}), expected_revision: store.revision }) });
      store.items.push(result.item); store.revision = result.revision; store.selectedItemId = result.item.id; notifyWorkHubChanged(); render();
      // Flash the new card
      setTimeout(() => {
        const card = document.querySelector(`.work-hub-card[data-item-id="${result.item.id}"], .work-hub-list-row[data-item-id="${result.item.id}"]`);
        if (card) { card.classList.add('work-hub-new'); setTimeout(() => card.classList.remove('work-hub-new'), 1200); }
        revealItem(result.item.id);
      }, 50);
    } catch (error) {
      store.stale = true; render();
      if (typeof showToast === 'function') showToast('Could not add the work item: ' + (error && error.message ? error.message : 'unknown error'), 5000, 'error');
    }
  }
  async function updateItem(itemId, item, options = {}) { try { const result = await request('/api/work_hub/items/update', { method: 'POST', body: JSON.stringify({ item_id: itemId, item, expected_revision: store.revision }) }); const index = store.items.findIndex(x => x.id === itemId); store.items[index] = result.item; store.revision = result.revision; notifyWorkHubChanged(); if (!options.deferRender) render(); return true; } catch (error) { store.stale = true; render(); return false; } }
  // The details panel slides away (sheet on phones, fades on the desktop
  // column) before it clears, instead of vanishing.
  // Bring a card into view and flash it. On a phone only one column fits, so a
  // card saved into another column (Backlog, the default) landed off-screen
  // and looked as if it had vanished.
  function revealItem(itemId) {
    const card = document.querySelector(`.work-hub-card[data-item-id="${CSS.escape(itemId)}"], .work-hub-list-row[data-item-id="${CSS.escape(itemId)}"]`);
    if (!card) return;
    const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
    const wrap = card.closest('.work-hub-board-wrap');
    const column = card.closest('.work-hub-column');
    if (wrap && column) {
      const w = wrap.getBoundingClientRect(), c = column.getBoundingClientRect();
      if (c.left < w.left || c.right > w.right) wrap.scrollTo({ left: wrap.scrollLeft + (c.left - w.left) - 4, behavior });
    }
    const list = card.closest('.work-hub-cards') || card.closest('#workHubCanvas');
    if (list) { const l = list.getBoundingClientRect(), r = card.getBoundingClientRect(); if (r.top < l.top || r.bottom > l.bottom) card.scrollIntoView({ block: 'nearest', behavior }); }
    markLanded(card);
  }
  function closeInspectorAnimated() {
    // Desktop: the panel stays put; only its contents fade out and the empty
    // state fades in, so it reads as one motion. Phones keep the sheet slide.
    const panel = el('workHubInspector');
    const phone = window.matchMedia('(max-width: 620px)').matches;
    const done = () => { if (panel) panel.classList.remove('is-closing', 'is-clearing'); store.selectedItemId = null; render(); };
    if (!panel || window.matchMedia('(prefers-reduced-motion: reduce)').matches) { done(); return Promise.resolve(); }
    panel.classList.add(phone ? 'is-closing' : 'is-clearing');
    return new Promise(resolve => setTimeout(() => { done(); resolve(); }, phone ? 260 : 170));
  }
  async function changeWorkflow(workflowId, action) { try { const result = await request(`/api/work_hub/workflows/${workflowId}/${action}`, { method: 'POST', body: JSON.stringify({ expected_revision: store.revision }) }); store.revision = result.revision; await loadWorkHubPanel(); notifyWorkHubChanged(); } catch (error) { store.stale = true; render(); } }
  function initResizer(wrap) {
    const resizer = wrap.querySelector('.work-hub-resizer'); if (!resizer) return;
    // Pointer events cover mouse, pen and touch (the old mouse-only handler
    // never fired for those, so the width was never saved).
    resizer.addEventListener('pointerdown', (e) => {
      if (e.button !== undefined && e.button !== 0) return;
      e.preventDefault();
      const startX = e.clientX;
      const startWidth = currentInspectorWidth;
      let width = startWidth;
      try { resizer.setPointerCapture(e.pointerId); } catch (_) {}
      wrap.classList.add('is-resizing');
      const onMove = (ev) => {
        width = Math.max(MIN_INSPECTOR_WIDTH, Math.min(MAX_INSPECTOR_WIDTH, startWidth + (startX - ev.clientX)));
        wrap.style.setProperty('--wh-inspector-width', width + 'px');
      };
      const onUp = () => {
        currentInspectorWidth = width;
        try { localStorage.setItem('workHubInspectorWidth', String(currentInspectorWidth)); } catch (_) {}
        wrap.classList.remove('is-resizing');
        resizer.removeEventListener('pointermove', onMove);
        resizer.removeEventListener('pointerup', onUp);
        resizer.removeEventListener('pointercancel', onUp);
      };
      resizer.addEventListener('pointermove', onMove);
      resizer.addEventListener('pointerup', onUp);
      resizer.addEventListener('pointercancel', onUp);
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
  document.addEventListener('project-sessions-changed', () => { if (el('workHub')) loadWorkHubPanel({ keepInspector: true }); });
  document.addEventListener('work-hub-changed', () => { if (el('workspaceWorkHubList')) renderWorkspaceWorkHub(); });
  // Coming back to the window refreshes the board around an open work item,
  // so its panel and any unsaved edits stay as they are.
  window.addEventListener('focus', () => {
    if (!el('workHub')) return;
    loadWorkHubPanel({ keepInspector: true });
  });
  // Chats change items from the server side (the work_hub tool), so while the
  // board is on screen it checks for changes every few seconds and redraws
  // the cards only. It holds off while the user is dragging or typing on the
  // board, so a refresh never drops a drag or the keyboard.
  const WORK_HUB_POLL_MS = 3000;
  let workHubPolling = false;
  const workingSignature = items => items.filter(item => item.working).map(item => item.id).sort().join(',');
  async function pollWorkHub() {
    const canvas = el('workHubCanvas');
    if (workHubPolling || document.hidden || !canvas || !canvas.offsetParent) return;
    if (document.documentElement.classList.contains('work-hub-touch-dragging') || document.querySelector('.work-hub-card.dragging')) return;
    const focused = document.activeElement;
    if (focused && focused !== document.body && el('workHub') && el('workHub').contains(focused) && focused.matches('input,textarea,select,[contenteditable="true"]')) return;
    workHubPolling = true;
    try {
      const data = await request('/api/work_hub/items');
      const items = data.items || [];
      const newer = (data.revision || 0) > store.revision;
      if (!newer && workingSignature(items) === workingSignature(store.items)) return;
      if ((data.revision || 0) < store.revision) return;
      store.items = items; store.revision = data.revision || store.revision;
      if (newer) notifyWorkHubChanged();
      const visible = scopedItems();
      renderCanvas(visible); bind();
      const live = document.querySelector('#workHub .work-hub-live'); if (live && !store.stale && !live.hasAttribute('aria-busy')) live.textContent = `${visible.length} work item${visible.length === 1 ? '' : 's'}`;
    } catch (_) { /* the next tick retries */ } finally { workHubPolling = false; }
  }
  // unref: under Node (the panel's script tests) the timer must not keep the process alive.
  { const timer = setInterval(pollWorkHub, WORK_HUB_POLL_MS); if (timer && typeof timer.unref === 'function') timer.unref(); }
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

  // The dialog fades and drops away before it goes; its ids are cleared at
  // once so a dialog opened straight after never finds the old controls.
  function closeDialog() {
    const tokens = uploadTokens; uploadTokens = []; if (tokens.length) api('/api/work_hub/plan/uploads/discard', { method: 'POST', body: JSON.stringify({ upload_tokens: tokens }), timeoutToast: false }).catch(() => {});
    const o = document.querySelector('.goal-planner-overlay:not(.is-leaving)');
    if (o) {
      o.querySelectorAll('[id]').forEach(node => node.removeAttribute('id'));
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) o.remove();
      else { o.classList.add('is-leaving'); setTimeout(() => o.remove(), 180); }
    }
    currentPlan = null; createdItems = []; createdRevision = null;
  }

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
    document.querySelector('.goal-planner-overlay:not(.is-leaving)').addEventListener('click', (e) => { if (e.target === e.currentTarget) closeDialog(); });
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
