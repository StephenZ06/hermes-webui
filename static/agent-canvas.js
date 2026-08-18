// Agent Canvas: a live org-chart of the real Hermes delegation tree for the
// current chat session — a Conductor root (the main session) with subagent
// branches hanging below it, styled after the FounderOS Conductor/org UI
// (see "Agent Canvas FounderOS Migration.md") but built from hermes-webui's
// own theme tokens so it stays correct across every skin/light/dark mode.
//
// Data flow: gateway_chat.py relays the upstream 'subagent.start' /
// 'subagent.tool' / 'subagent.complete' events (emitted by
// tools/delegate_tool.py's child_progress_cb) as SSE events
// 'subagent_spawn' / 'subagent_tool' / 'subagent_complete', wired in
// static/messages.js's _wireSSE to AgentCanvas.onSpawn/onToolActivity/onComplete.
//
// This module intentionally does NOT talk to the Hermes TUI gateway
// WebSocket/JSON-RPC transport described as "preferred" in the migration
// doc — hermes-webui has no existing client for that transport anywhere,
// and the doc itself says not to open a second connection unless
// necessary. The existing /v1/chat/completions SSE relay carries live
// events; reconciliation (open/reconnect) and controls use the REST
// equivalents hermes-agent already exposes and hermes-webui already
// proxies with auth:
//   GET  /api/subagents/active     -> delegation.status snapshot
//   POST /api/subagents/interrupt  -> subagent.interrupt {subagent_id}
//   POST /api/subagents/pause      -> block/unblock new delegate_task spawns
(function(){
  const TERMINAL_STATUSES = new Set(['completed', 'failed', 'error', 'interrupted', 'timeout']);
  const ROOT_ID = '__root__';
  const FEED_MAX = 80;
  const OUTPUT_TAIL_MAX = 6;

  const STATUS_LABEL = {
    queued: 'Queued',
    running: 'Running',
    completed: 'Completed',
    failed: 'Failed',
    error: 'Error',
    timeout: 'Timed out',
    interrupted: 'Interrupted',
    root: 'Conductor',
    idle: 'Waiting for task',
    orchestrating: 'Orchestrating',
  };

  let _nodes = new Map();        // subagent_id -> node record
  let _feed = [];                // activity feed entries, newest first
  let _selectedId = null;
  let _spawnPaused = false;
  let _reconcileTimer = null;
  let _container = null;
  let _wrapEl = null;
  let _treeEl = null;
  let _feedEl = null;
  let _detailEl = null;
  let _livePillEl = null;
  let _pauseBtnEl = null;
  let _emptyEl = null;
  let _renderQueued = false;
  let _lastActivityAt = 0;
  let _liveTimer = null;
  // 'live' tracks the real active session via SSE + reconcile() polling.
  // 'history' shows a frozen diagram rebuilt from state.db for a finished
  // chat clicked in the sidebar — see renderSidebar()/showHistoricalTree().
  let _viewMode = 'live';
  let _lastCanvasParents = [];   // cached /api/agent-canvas/sessions result, reused by sidebar clicks
  // Sidebar project-folder expand state, survives re-renders. Tracks
  // EXPANDED ids (default = collapsed) to match the Chat sidebar's own
  // default (static/sessions.js: `Boolean(_projectFoldersExpanded[id])`,
  // false unless a prior expand was persisted) — tracking collapsed ids
  // instead meant every folder here rendered expanded-by-default, which is
  // why folder-to-folder spacing looked different: real folders sit as
  // single-line collapsed chips with just the list gap between them, not
  // interleaved with their (usually short) nested session lists.
  let _expandedProjectIds = new Set();

  // ---- helpers ----------------------------------------------------------

  function esc(s){
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
      '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;',
    }[c]));
  }

  function shortLabel(goal){
    const g = String(goal || '').trim().replace(/\s+/g, ' ');
    if(!g) return 'Subagent';
    return g.length > 42 ? g.slice(0, 41) + '…' : g;
  }

  function fmtDuration(seconds){
    if(seconds == null) return '';
    const s = Math.max(0, Math.round(seconds));
    if(s < 60) return s + 's';
    const m = Math.floor(s / 60), r = s % 60;
    if(m < 60) return m + 'm ' + r + 's';
    const h = Math.floor(m / 60);
    return h + 'h ' + (m % 60) + 'm';
  }

  function fmtCost(usd){
    if(usd == null) return '';
    return '$' + Number(usd).toFixed(usd >= 1 ? 2 : 4);
  }

  function fmtTokens(n){
    if(!n) return '0';
    if(n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if(n >= 1000) return (n / 1000).toFixed(1) + 'k';
    return String(n);
  }

  function liveDuration(node){
    if(node.durationSeconds != null) return node.durationSeconds;
    if(!node.spawnedAt) return null;
    return (Date.now() - node.spawnedAt) / 1000;
  }

  // Monotonic status update: once a node is terminal, later non-terminal
  // (or differently-terminal) updates are ignored — a late/out-of-order
  // 'running' snapshot must never resurrect a node that already finished.
  function applyStatus(node, nextStatus){
    if(!nextStatus) return;
    if(TERMINAL_STATUSES.has(node.status) && node.status !== nextStatus) return;
    node.status = nextStatus;
  }

  function pushFeed(entry){
    _feed.unshift({ ts: Date.now(), ...entry });
    if(_feed.length > FEED_MAX) _feed.length = FEED_MAX;
    _lastActivityAt = Date.now();
  }

  function scheduleRender(){
    if(_renderQueued) return;
    _renderQueued = true;
    requestAnimationFrame(() => { _renderQueued = false; render(); });
  }

  // ---- node ops -----------------------------------------------------------

  function ensureRoot(){
    if(_nodes.has(ROOT_ID)) return _nodes.get(ROOT_ID);
    const root = {
      subagent_id: ROOT_ID, parent_id: null, depth: -1,
      goal: 'Main session', model: '', status: 'idle',
      toolCount: 0, tools: [], lastTool: null,
      inputTokens: 0, outputTokens: 0, reasoningTokens: 0, apiCalls: 0, costUsd: null,
      filesRead: [], filesWritten: [], outputTail: [], summary: '',
      spawnedAt: Date.now(), _isRoot: true,
    };
    _nodes.set(ROOT_ID, root);
    return root;
  }

  // The Conductor's own status is never pushed by an event — it's derived
  // live from its children each render: orchestrating while any child is
  // still non-terminal, idle (waiting for the next task) otherwise. This is
  // what lets it sit there glowing between turns instead of only existing
  // once a subagent has spawned.
  function _updateConductorStatus(){
    if(_viewMode === 'history') return; // frozen — status set explicitly by showHistoricalTree()
    const root = _nodes.get(ROOT_ID);
    if(!root) return;
    const hasActive = childrenOf(ROOT_ID).some(k => !TERMINAL_STATUSES.has(k.status));
    root.status = hasActive ? 'orchestrating' : 'idle';
  }

  function childrenOf(id){
    const out = [];
    for(const n of _nodes.values()){
      if(n.subagent_id !== ROOT_ID && (n.parent_id || ROOT_ID) === id) out.push(n);
    }
    out.sort((a, b) => (a.spawnedAt || 0) - (b.spawnedAt || 0));
    return out;
  }

  function onSpawn(d){
    if(!d || !d.subagent_id || _nodes.has(d.subagent_id)) return;
    // A genuine live spawn event can only fire for the currently-loaded
    // session's active stream (see messages.js's SSE gating) — if one
    // arrives while a historical diagram is showing, that session just
    // started a real new turn, so snap back to live instead of injecting
    // a live node into a frozen dataset.
    if(_viewMode === 'history'){
      _nodes.clear();
      _feed = [];
      _viewMode = 'live';
    }
    ensureRoot();
    _nodes.set(d.subagent_id, {
      subagent_id: d.subagent_id,
      parent_id: d.parent_id || null,
      depth: typeof d.depth === 'number' ? d.depth : 0,
      goal: d.goal || '',
      model: d.model || '',
      taskIndex: typeof d.task_index === 'number' ? d.task_index : null,
      taskCount: typeof d.task_count === 'number' ? d.task_count : null,
      toolsets: Array.isArray(d.toolsets) ? d.toolsets : null,
      childSessionId: d.child_session_id || null,
      status: 'running',
      toolCount: 0, tools: [], lastTool: null,
      inputTokens: 0, outputTokens: 0, reasoningTokens: 0, apiCalls: 0, costUsd: null,
      filesRead: [], filesWritten: [], outputTail: [], summary: '',
      spawnedAt: Date.now(), completedAt: null, durationSeconds: null,
      _phase: Math.random() * Math.PI * 2,
    });
    pushFeed({ kind: 'spawn', subagentId: d.subagent_id, text: shortLabel(d.goal) + ' spawned' });
    scheduleRender();
  }

  function onToolActivity(d){
    if(!d || !d.subagent_id) return;
    const n = _nodes.get(d.subagent_id);
    if(!n) return;
    n.toolCount = typeof d.tool_count === 'number' ? d.tool_count : n.toolCount + 1;
    const toolName = d.tool || d.tool_name || 'tool';
    if(!n.tools.includes(toolName)) n.tools.push(toolName);
    n.lastTool = { tool: toolName, preview: d.preview || '', isError: !!d.is_error };
    n.outputTail.push(n.lastTool);
    if(n.outputTail.length > OUTPUT_TAIL_MAX) n.outputTail.shift();
    pushFeed({
      kind: 'tool', subagentId: d.subagent_id,
      text: toolName + (d.preview ? ' — ' + shortLabel(d.preview) : ''),
      isError: !!d.is_error,
    });
    scheduleRender();
  }

  function onComplete(d){
    if(!d || !d.subagent_id) return;
    const n = _nodes.get(d.subagent_id);
    if(!n) return;
    applyStatus(n, d.status || 'completed');
    n.completedAt = Date.now();
    n.durationSeconds = typeof d.duration_seconds === 'number'
      ? d.duration_seconds
      : (n.spawnedAt ? (n.completedAt - n.spawnedAt) / 1000 : null);
    n.summary = d.summary || n.summary || '';
    if(typeof d.input_tokens === 'number') n.inputTokens = d.input_tokens;
    if(typeof d.output_tokens === 'number') n.outputTokens = d.output_tokens;
    if(typeof d.reasoning_tokens === 'number') n.reasoningTokens = d.reasoning_tokens;
    if(typeof d.api_calls === 'number') n.apiCalls = d.api_calls;
    if(typeof d.cost_usd === 'number') n.costUsd = d.cost_usd;
    if(Array.isArray(d.files_read)) n.filesRead = d.files_read;
    if(Array.isArray(d.files_written)) n.filesWritten = d.files_written;
    if(Array.isArray(d.output_tail) && d.output_tail.length) n.outputTail = d.output_tail.slice(-OUTPUT_TAIL_MAX);
    pushFeed({
      kind: 'complete', subagentId: d.subagent_id,
      text: shortLabel(n.goal) + ' ' + (STATUS_LABEL[n.status] || n.status).toLowerCase(),
      isError: n.status !== 'completed',
    });
    scheduleRender();
  }

  // ---- rendering ----------------------------------------------------------

  function statusDotHtml(status){
    return `<span class="agent-canvas-dot status-${esc(status)}" aria-hidden="true"></span>`;
  }

  function buildCard(node){
    const isRoot = !!node._isRoot;
    const dur = liveDuration(node);
    const statusText = STATUS_LABEL[node.status] || node.status;
    const kids = childrenOf(node.subagent_id);
    const statCells = [];
    if(node.toolCount) statCells.push(`<span class="agent-canvas-stat">🔧 ${node.toolCount}</span>`);
    if(node.inputTokens || node.outputTokens) statCells.push(`<span class="agent-canvas-stat">${fmtTokens((node.inputTokens||0)+(node.outputTokens||0))} tok</span>`);
    if(node.costUsd != null) statCells.push(`<span class="agent-canvas-stat">${fmtCost(node.costUsd)}</span>`);
    if(dur != null && !(isRoot && node.status === 'idle')) statCells.push(`<span class="agent-canvas-stat">${fmtDuration(dur)}</span>`);
    if(kids.length) statCells.push(`<span class="agent-canvas-stat">${kids.length} child${kids.length===1?'':'ren'}</span>`);

    const card = document.createElement('div');
    card.className = 'agent-canvas-card status-' + node.status + (isRoot ? ' is-conductor' : '') + (node.subagent_id === _selectedId ? ' selected' : '');
    card.dataset.subagentId = node.subagent_id;
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');
    card.innerHTML = `
      <div class="agent-canvas-card-head">
        ${statusDotHtml(node.status)}
        <span class="agent-canvas-card-label">${isRoot ? 'Conductor' : esc(shortLabel(node.goal))}</span>
      </div>
      ${isRoot ? '<div class="agent-canvas-card-sub">Main Hermes session</div>' : (node.model ? `<div class="agent-canvas-card-sub">${esc(node.model)}</div>` : '')}
      <div class="agent-canvas-card-status">${esc(statusText)}</div>
      ${statCells.length ? `<div class="agent-canvas-card-stats">${statCells.join('')}</div>` : ''}
    `;
    const open = () => { _selectedId = node.subagent_id; scheduleRender(); };
    card.addEventListener('click', open);
    card.addEventListener('keydown', e => { if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); open(); } });
    return card;
  }

  function buildBranch(node){
    const branch = document.createElement('div');
    branch.className = 'agent-canvas-branch' + (!TERMINAL_STATUSES.has(node.status) ? ' is-flowing' : '');
    branch.appendChild(buildCard(node));
    const kids = childrenOf(node.subagent_id);
    if(kids.length){
      branch.appendChild(buildChildrenRow(kids));
    }
    return branch;
  }

  function buildChildrenRow(kids){
    const wrap = document.createElement('div');
    wrap.className = 'agent-canvas-children-wrap';
    const rail = document.createElement('div');
    rail.className = 'agent-canvas-rail';
    wrap.appendChild(rail);
    const row = document.createElement('div');
    row.className = 'agent-canvas-children';
    for(const k of kids) row.appendChild(buildBranch(k));
    wrap.appendChild(row);
    return wrap;
  }

  function renderTree(){
    if(!_treeEl) return;
    _treeEl.innerHTML = '';
    const root = _nodes.get(ROOT_ID);
    if(!root){
      return;
    }
    const rootCol = document.createElement('div');
    rootCol.className = 'agent-canvas-root-col';
    rootCol.appendChild(buildCard(root));
    const kids = childrenOf(ROOT_ID);
    if(kids.length){
      const trunk = document.createElement('div');
      trunk.className = 'agent-canvas-trunk' + (root.status === 'orchestrating' ? ' is-flowing' : '');
      rootCol.appendChild(trunk);
      rootCol.appendChild(buildChildrenRow(kids));
    }
    _treeEl.appendChild(rootCol);
  }

  function renderFeed(){
    if(!_feedEl) return;
    if(!_feed.length){
      _feedEl.innerHTML = '<div class="agent-canvas-feed-empty">No activity yet.</div>';
      return;
    }
    const html = _feed.map(entry => {
      const node = _nodes.get(entry.subagentId);
      const name = node ? shortLabel(node.goal) : entry.subagentId;
      const time = new Date(entry.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      const kindCls = entry.kind + (entry.isError ? ' is-error' : '');
      return `<div class="agent-canvas-feed-item ${esc(kindCls)}">
        <span class="agent-canvas-feed-time">${esc(time)}</span>
        <span class="agent-canvas-feed-kind">${esc(entry.kind)}</span>
        <span class="agent-canvas-feed-text" title="${esc(name + ' — ' + entry.text)}">${esc(entry.text)}</span>
      </div>`;
    }).join('');
    _feedEl.innerHTML = html;
  }

  function fileListHtml(label, files){
    if(!files || !files.length) return '';
    const items = files.slice(0, 20).map(f => `<li>${esc(f)}</li>`).join('');
    return `<div class="agent-canvas-detail-block">
      <div class="agent-canvas-detail-label">${esc(label)} (${files.length})</div>
      <ul class="agent-canvas-detail-files">${items}</ul>
    </div>`;
  }

  function renderDetail(){
    if(!_detailEl) return;
    const node = _selectedId ? _nodes.get(_selectedId) : null;
    if(!node){
      _detailEl.innerHTML = '<div class="agent-canvas-detail-empty">Select a card to see full detail.</div>';
      return;
    }
    const dur = liveDuration(node);
    const outputTail = (node.outputTail || []).map(o => `<div class="agent-canvas-detail-tool-entry${o.isError ? ' is-error' : ''}">
      <span class="agent-canvas-detail-tool-name">${esc(o.tool)}</span>
      ${o.preview ? `<span class="agent-canvas-detail-tool-preview">${esc(o.preview)}</span>` : ''}
    </div>`).join('');
    _detailEl.innerHTML = `
      <div class="agent-canvas-detail-head">
        ${statusDotHtml(node.status)}
        <span class="agent-canvas-detail-title">${node._isRoot ? 'Conductor' : esc(node.goal || node.subagent_id)}</span>
        <button type="button" class="agent-canvas-detail-close" aria-label="Close">×</button>
      </div>
      <div class="agent-canvas-detail-row"><span>Status</span><span>${esc(STATUS_LABEL[node.status] || node.status)}</span></div>
      ${node.model ? `<div class="agent-canvas-detail-row"><span>Model</span><span>${esc(node.model)}</span></div>` : ''}
      ${!node._isRoot ? `<div class="agent-canvas-detail-row"><span>Depth</span><span>${esc(node.depth)}</span></div>` : ''}
      ${(node.taskIndex != null && node.taskCount != null) ? `<div class="agent-canvas-detail-row"><span>Batch task</span><span>${esc(node.taskIndex + 1)} / ${esc(node.taskCount)}</span></div>` : ''}
      ${(dur != null && !(node._isRoot && node.status === 'idle')) ? `<div class="agent-canvas-detail-row"><span>Duration</span><span>${esc(fmtDuration(dur))}</span></div>` : ''}
      ${node.apiCalls ? `<div class="agent-canvas-detail-row"><span>API calls</span><span>${esc(node.apiCalls)}</span></div>` : ''}
      ${(node.inputTokens || node.outputTokens) ? `<div class="agent-canvas-detail-row"><span>Tokens</span><span>${esc(fmtTokens(node.inputTokens))} in / ${esc(fmtTokens(node.outputTokens))} out${node.reasoningTokens ? ' / ' + esc(fmtTokens(node.reasoningTokens)) + ' reasoning' : ''}</span></div>` : ''}
      ${node.costUsd != null ? `<div class="agent-canvas-detail-row"><span>Cost</span><span>${esc(fmtCost(node.costUsd))}</span></div>` : ''}
      ${node.goal ? `<div class="agent-canvas-detail-block"><div class="agent-canvas-detail-label">Goal</div><div class="agent-canvas-detail-goal">${esc(node.goal)}</div></div>` : ''}
      ${node.summary ? `<div class="agent-canvas-detail-block"><div class="agent-canvas-detail-label">Summary</div><div class="agent-canvas-detail-goal">${esc(node.summary)}</div></div>` : ''}
      ${outputTail ? `<div class="agent-canvas-detail-block"><div class="agent-canvas-detail-label">Recent tool activity</div>${outputTail}</div>` : ''}
      ${fileListHtml('Files read', node.filesRead)}
      ${fileListHtml('Files written', node.filesWritten)}
      ${(!node._isRoot && !TERMINAL_STATUSES.has(node.status)) ? `
      <div class="agent-canvas-detail-actions">
        <button type="button" class="agent-canvas-detail-action" data-action="interrupt">Interrupt</button>
        ${descendantsOf(node.subagent_id).length ? '<button type="button" class="agent-canvas-detail-action danger" data-action="interrupt-branch">Interrupt branch</button>' : ''}
      </div>` : ''}
    `;
    const closeBtn = _detailEl.querySelector('.agent-canvas-detail-close');
    if(closeBtn) closeBtn.onclick = () => { _selectedId = null; scheduleRender(); };
    const interruptBtn = _detailEl.querySelector('[data-action="interrupt"]');
    if(interruptBtn) interruptBtn.onclick = () => interruptSubagent(node.subagent_id);
    const interruptBranchBtn = _detailEl.querySelector('[data-action="interrupt-branch"]');
    if(interruptBranchBtn) interruptBranchBtn.onclick = () => interruptBranch(node.subagent_id);
  }

  function renderLivePill(){
    if(_viewMode === 'history'){
      if(_livePillEl){
        _livePillEl.classList.remove('is-live');
        _livePillEl.textContent = 'HISTORY';
      }
      const sidebarStatus = document.getElementById('agentCanvasCardStatus');
      if(sidebarStatus) sidebarStatus.hidden = true;
      return;
    }
    const stale = _lastActivityAt && (Date.now() - _lastActivityAt > 30000);
    const hasActivity = _nodes.size > 1;
    const isLive = hasActivity && !stale;
    if(_livePillEl){
      _livePillEl.classList.toggle('is-live', isLive);
      _livePillEl.textContent = hasActivity ? (stale ? 'IDLE' : 'LIVE') : 'IDLE';
    }
    // Mirror onto the Agent Canvas sidebar's "Canvas" card so it's visible
    // at a glance even while its "View" button is showing something else
    // (e.g. a historical session).
    const sidebarStatus = document.getElementById('agentCanvasCardStatus');
    if(sidebarStatus) sidebarStatus.hidden = !isLive;
  }

  function updateEmptyState(){
    if(!_emptyEl) return;
    if(_viewMode === 'history'){ _emptyEl.style.display = 'none'; return; }
    _emptyEl.style.display = childrenOf(ROOT_ID).length ? 'none' : '';
  }

  // The Conductor card is always present — idle-but-glowing while waiting,
  // lit up while orchestrating — so the canvas never goes blank between
  // turns. Only the hint text and feed/detail panels react to whether any
  // subagent has actually run.
  function render(){
    _updateConductorStatus();
    updateEmptyState();
    renderLivePill();
    renderTree();
    renderFeed();
    renderDetail();
  }

  // ---- reconciliation + controls --------------------------------------------
  // GET/POST /api/subagents/* — hermes-webui's authenticated proxy onto
  // hermes-agent's GET/POST /v1/subagents/active|interrupt|pause, which read
  // and act on the live _active_subagents registry in tools/delegate_tool.py.

  function descendantsOf(id){
    const out = [];
    const stack = [id];
    while(stack.length){
      const cur = stack.pop();
      for(const n of _nodes.values()){
        if(n.parent_id === cur){ out.push(n); stack.push(n.subagent_id); }
      }
    }
    return out;
  }

  async function interruptSubagent(subagentId){
    try{
      await api('/api/subagents/interrupt', { method: 'POST', body: JSON.stringify({ subagent_id: subagentId }) });
      if(typeof showToast === 'function') showToast('Interrupt sent');
    }catch(err){
      if(typeof showToast === 'function') showToast('Interrupt failed: ' + (err && err.message ? err.message : err));
    }
  }

  async function interruptBranch(subagentId){
    const targets = [subagentId, ...descendantsOf(subagentId).map(n => n.subagent_id)]
      .filter(id => { const n = _nodes.get(id); return n && !TERMINAL_STATUSES.has(n.status); });
    // Deepest descendants first, per the migration doc's kill-subtree guidance,
    // so a parent isn't left interrupting into children that already stopped.
    targets.reverse();
    for(const id of targets) await interruptSubagent(id);
  }

  async function toggleSpawnPaused(){
    try{
      const data = await api('/api/subagents/pause', { method: 'POST', body: JSON.stringify({ paused: !_spawnPaused }) });
      _spawnPaused = !!(data && data.spawn_paused);
      if(typeof showToast === 'function') showToast(_spawnPaused ? 'New subagent spawns paused' : 'Spawning resumed');
      renderPauseButton();
    }catch(err){
      if(typeof showToast === 'function') showToast('Failed to toggle pause: ' + (err && err.message ? err.message : err));
    }
  }

  function renderPauseButton(){
    if(!_pauseBtnEl) return;
    _pauseBtnEl.classList.toggle('is-paused', _spawnPaused);
    _pauseBtnEl.textContent = _spawnPaused ? 'Resume spawning' : 'Pause spawning';
  }

  async function reconcile(){
    if(_viewMode === 'history') return; // don't let live polling clobber a frozen historical view
    try{
      const data = await api('/api/subagents/active', { timeoutToast: false });
      if(!data || data.gateway_enabled === false) return;
      _spawnPaused = !!data.spawn_paused;
      renderPauseButton();
      const active = Array.isArray(data.active) ? data.active : [];
      if(!active.length) return;
      ensureRoot();
      for(const rec of active){
        if(!rec || !rec.subagent_id) continue;
        let n = _nodes.get(rec.subagent_id);
        if(!n){
          onSpawn({
            subagent_id: rec.subagent_id, parent_id: rec.parent_id,
            depth: rec.depth, goal: rec.goal, model: rec.model,
          });
          n = _nodes.get(rec.subagent_id);
          if(n && rec.started_at) n.spawnedAt = rec.started_at * 1000;
        }
        if(!n) continue;
        if(typeof rec.tool_count === 'number') n.toolCount = rec.tool_count;
        applyStatus(n, rec.status);
      }
      scheduleRender();
    }catch(_err){
      // Reconciliation is best-effort background polling — a transient
      // failure must never blow away the tree already built from live events.
    }
  }

  // ---- lifecycle ------------------------------------------------------------

  function mount(container){
    if(!container){ return; }
    if(_container === container){ reconcile(); scheduleRender(); return; }
    _container = container;
    container.innerHTML = `
      <div class="agent-canvas-header">
        <span class="agent-canvas-live-pill" id="agentCanvasLivePill">IDLE</span>
        <span class="agent-canvas-header-hint">Live view of Hermes' real delegation tree for this session</span>
        <button type="button" class="agent-canvas-pause-btn" id="agentCanvasPauseBtn">Pause spawning</button>
      </div>
      <div class="agent-canvas-empty" id="agentCanvasEmpty">Conductor is idle — waiting for Hermes to delegate a task. Subagents will branch off below, live, and stay here after they finish.</div>
      <div class="agent-canvas-body">
        <div class="agent-canvas-tree-scroll"><div class="agent-canvas-tree" id="agentCanvasTree"></div></div>
        <div class="agent-canvas-side">
          <div class="agent-canvas-detail" id="agentCanvasDetail"></div>
          <div class="agent-canvas-feed-head">Activity</div>
          <div class="agent-canvas-feed" id="agentCanvasFeed"></div>
        </div>
      </div>
    `;
    _wrapEl = container;
    _emptyEl = container.querySelector('#agentCanvasEmpty');
    _treeEl = container.querySelector('#agentCanvasTree');
    _feedEl = container.querySelector('#agentCanvasFeed');
    _detailEl = container.querySelector('#agentCanvasDetail');
    _livePillEl = container.querySelector('#agentCanvasLivePill');
    _pauseBtnEl = container.querySelector('#agentCanvasPauseBtn');
    _pauseBtnEl.onclick = toggleSpawnPaused;
    if(!_liveTimer) _liveTimer = setInterval(renderLivePill, 5000);
    if(!_reconcileTimer) _reconcileTimer = setInterval(reconcile, 5000);
    ensureRoot();
    reconcile();
    render();
  }

  function reset(){
    _nodes.clear();
    _feed = [];
    _selectedId = null;
    _lastActivityAt = 0;
    // sessions.js calls this on every session switch. A switch triggered by
    // clicking a history entry re-enters 'history' mode right after (see
    // renderSidebar()'s click handler, which runs showHistoricalTree()
    // synchronously after this) — but any OTHER session switch (the normal
    // chat sidebar, a new chat, etc.) must drop back to live, or Agent
    // Canvas would stay frozen on stale history forever.
    _viewMode = 'live';
    ensureRoot();
    scheduleRender();
  }

  // ---- sidebar: chats that have used Agent Canvas -------------------------
  // Subagent child sessions never get a WebUI-side sidecar JSON file (they're
  // spawned entirely inside hermes-agent's own process, never through any
  // WebUI session-creation path), so they never show up in `_allSessions`
  // no matter how it's scoped — confirmed directly against a live payload:
  // zero 'subagent'-sourced rows in either the main list or the archived
  // reference list, even with all_profiles+include_archived. An earlier
  // version of this function scanned `_allSessions` for them; that could
  // never have worked. GET /api/agent-canvas/sessions reads Hermes's
  // state.db directly instead (see list_parents_with_subagent_children() in
  // api/agent_sessions.py) and returns {parent_session_id, children[]} —
  // the parent IS a normal WebUI chat (it does have a sidecar), so its
  // title/project/profile come from the already-loaded `_allSessions`
  // cache; only the raw parent id + child summaries come from the backend.

  function _canvasSessionCategory(s){
    if(s && s.project_id){
      const projects = (typeof _allProjects !== 'undefined' && Array.isArray(_allProjects)) ? _allProjects : [];
      const proj = projects.find(p => p && p.project_id === s.project_id);
      return proj ? proj.name : 'Project';
    }
    return 'General';
  }

  async function _fetchCanvasParents(){
    try{
      const data = await api('/api/agent-canvas/sessions', { timeoutToast: false });
      return Array.isArray(data && data.parents) ? data.parents : [];
    }catch(_err){
      return [];
    }
  }

  // Reuses the real Chat sidebar's row anatomy (.session-item > .session-text
  // > .session-title-row[title + time] + .session-meta) instead of a custom
  // stacked-card layout, so this list is visually the same component as the
  // Chat page's — not just "similarly organized." The .agent-canvas-
  // sidebar-item class only supplies the button-reset (width/border/
  // background/text-align) and hover/loading states layered on top.
  function _sidebarRowHtml(p, webuiSession, activeSid){
    const title = _canvasRowTitle(p, webuiSession);
    const category = webuiSession ? _canvasSessionCategory(webuiSession) : 'General';
    const profile = (webuiSession && webuiSession.profile) || '';
    const childCount = Array.isArray(p.children) ? p.children.length : 0;
    const tsMs = webuiSession && typeof _sessionTimestampMs === 'function'
      ? _sessionTimestampMs(webuiSession)
      : (p.latest_at ? p.latest_at * 1000 : 0);
    const time = (tsMs && typeof _formatRelativeSessionTime === 'function') ? _formatRelativeSessionTime(tsMs) : '';
    const isActive = activeSid === p.parent_session_id;
    const metaParts = [esc(category.toUpperCase())];
    if(profile) metaParts.push(esc(profile.toUpperCase()));
    metaParts.push(`${childCount} subagent${childCount === 1 ? '' : 's'}`);
    return `<button type="button" class="session-item agent-canvas-sidebar-item${isActive ? ' active' : ''}" data-sid="${esc(p.parent_session_id)}">
      <div class="session-text">
        <div class="session-title-row">
          <span class="session-title">${esc(title)}</span>
          <span class="session-time">${esc(time)}</span>
        </div>
        <div class="session-meta">${metaParts.join(' · ')}</div>
      </div>
    </button>`;
  }

  // Same title resolution _sidebarRowHtml uses, factored out so the search
  // filter matches against exactly what the row displays.
  function _canvasRowTitle(p, webuiSession){
    if(webuiSession){
      return typeof _sessionDisplayTitle === 'function' ? _sessionDisplayTitle(webuiSession) : (webuiSession.title || 'Untitled');
    }
    const firstChildTitle = p.children && p.children[0] && p.children[0].title;
    return firstChildTitle ? String(firstChildTitle).replace(/^Subagent:\s*/, '') : p.parent_session_id;
  }

  let _agentCanvasSearchQuery = '';

  function _syncAgentCanvasSearchClear(){
    const clearBtn = document.getElementById('agentCanvasSearchClear');
    if(clearBtn) clearBtn.hidden = !_agentCanvasSearchQuery;
  }

  // Mirrors the Chat sidebar's "Filter conversations" box — client-side
  // title filter only (no debounced content-search API call; there's no
  // canvas-scoped equivalent of /api/sessions/search, and this list is
  // already small — every row here is a chat that delegated to a subagent).
  function filterAgentCanvasSessions(){
    const input = document.getElementById('agentCanvasSearch');
    _agentCanvasSearchQuery = (input && input.value || '').trim();
    _syncAgentCanvasSearchClear();
    const listEl = document.getElementById('agentCanvasSessionList');
    if(listEl) _renderSidebarFromCache(listEl, _lastCanvasParents);
  }

  function clearAgentCanvasSearch(){
    const input = document.getElementById('agentCanvasSearch');
    if(!input) return;
    if(input.value){
      input.value = '';
      filterAgentCanvasSessions();
    }
    input.focus();
  }

  // Grouped the same way the Chat sidebar groups sessions — a collapsible
  // folder per project (reusing its exact .project-chip/.project-folder-*
  // classes for visual parity) plus a flat "General" bucket — but built
  // fresh from the already-loaded `_allProjects`/`_allSessions` on every
  // render rather than kept as separate state, so a project created on the
  // Chat page shows up here the next time this panel renders with zero
  // extra sync code.
  async function renderSidebar(){
    const listEl = document.getElementById('agentCanvasSessionList');
    if(!listEl) return;
    if(!_lastCanvasParents.length) listEl.innerHTML = '<div class="loading-spinner-wrap" role="status"><div class="loading-spinner" aria-hidden="true"></div><span class="sr-only">Loading…</span></div>';
    const parents = await _fetchCanvasParents();
    // A slower fetch racing a fast panel-switch-back-and-forth could land
    // its result after the user has navigated away and the container was
    // torn down/replaced — bail rather than write into a stale/detached list.
    if(!document.body.contains(listEl)) return;
    _lastCanvasParents = parents;
    _renderSidebarFromCache(listEl, parents);
  }

  // Rebuilds the sidebar DOM from already-fetched data — used after a chat
  // click (to update the active-row highlight) so it doesn't refetch and
  // flash the whole list while the tree-loading spinner is already showing
  // for the thing the user actually clicked. Also the redraw path for the
  // search filter, which never needs a refetch.
  function _renderSidebarFromCache(listEl, allParents){
    if(!allParents.length){
      listEl.innerHTML = '<div class="agent-canvas-sidebar-empty">No chats have delegated to subagents yet. Once Hermes runs a multi-agent task, it\'ll show up here — even after it finishes.</div>';
      return;
    }
    const all = (typeof _allSessions !== 'undefined' && Array.isArray(_allSessions)) ? _allSessions : [];
    const bySid = new Map();
    for(const s of all){ if(s && s.session_id) bySid.set(s.session_id, s); }
    const projects = (typeof _allProjects !== 'undefined' && Array.isArray(_allProjects)) ? _allProjects : [];
    const activeSid = (window.S && S.session && S.session.session_id) || null;

    const q = _agentCanvasSearchQuery.toLowerCase();
    const parents = q
      ? allParents.filter(p => _canvasRowTitle(p, bySid.get(p.parent_session_id)).toLowerCase().includes(q))
      : allParents;
    if(!parents.length){
      listEl.innerHTML = `<div class="agent-canvas-sidebar-empty">No delegated chats match "${esc(_agentCanvasSearchQuery)}".</div>`;
      return;
    }

    const byProject = new Map(); // project_id -> parent entries
    const general = [];
    for(const p of parents){
      const webuiSession = bySid.get(p.parent_session_id);
      const pid = webuiSession && webuiSession.project_id;
      if(pid){
        if(!byProject.has(pid)) byProject.set(pid, []);
        byProject.get(pid).push(p);
      }else{
        general.push(p);
      }
    }

    let html = '';
    // Mirrors the Chat sidebar's actual structure (static/sessions.js's
    // project-folder-list block): every project the user has gets a folder
    // row unconditionally — including ones with zero matching chats here,
    // shown with an empty-state line — not just ones that happen to have a
    // subagent chat. The unfoldered/general sessions render as a plain flat
    // list below with no header label, because the real sidebar doesn't
    // have one either — it's just the date-grouped list sitting under the
    // folder bar.
    if(projects.length){
      // .project-folder-list is the real Chat sidebar's wrapper class — its
      // sizing rule (static/style.css) is `.project-folder-list .project-chip{...}`,
      // a descendant selector that only applies inside this exact wrapper.
      // Without it here, rows fell back to the tiny generic `.project-chip`
      // pill styling used elsewhere in the app (10px font, 3px padding) —
      // same class name, wrong size, because the DOM shape didn't match.
      html += '<div class="project-folder-list">';
      for(const proj of projects){
        const rows = byProject.get(proj.project_id) || [];
        const collapsed = !_expandedProjectIds.has(proj.project_id);
        html += `<div class="project-chip project-folder-row agent-canvas-project-row" data-project-id="${esc(proj.project_id)}">
          <span class="project-folder-chevron${collapsed ? '' : ' expanded'}">&#9656;</span>
          ${proj.color ? `<span class="color-dot" style="background:${esc(proj.color)}"></span>` : ''}
          <span class="project-folder-name">${esc(proj.name || 'Project')}</span>
          <span class="project-folder-count">${rows.length}</span>
        </div>
        <div class="agent-canvas-project-sessions${collapsed ? '' : ' expanded'}"><div class="agent-canvas-project-sessions-inner">${
          rows.length
            ? rows.map(p => _sidebarRowHtml(p, bySid.get(p.parent_session_id), activeSid)).join('')
            : '<div class="agent-canvas-sidebar-empty agent-canvas-project-empty">No delegated chats in this project yet.</div>'
        }</div></div>`;
      }
      html += '</div>';
    }
    html += general.map(p => _sidebarRowHtml(p, bySid.get(p.parent_session_id), activeSid)).join('');
    listEl.innerHTML = html;

    listEl.querySelectorAll('.agent-canvas-project-row').forEach(row => {
      row.onclick = () => {
        const pid = row.dataset.projectId;
        const chevron = row.querySelector('.project-folder-chevron');
        const sessionsEl = row.nextElementSibling;
        const expanded = chevron.classList.toggle('expanded');
        if(sessionsEl) sessionsEl.classList.toggle('expanded', expanded);
        if(expanded) _expandedProjectIds.add(pid); else _expandedProjectIds.delete(pid);
      };
    });
    listEl.querySelectorAll('.agent-canvas-sidebar-item').forEach(btn => {
      btn.onclick = async () => {
        if(btn.classList.contains('loading')) return;
        const sid = btn.dataset.sid;
        const entry = _lastCanvasParents.find(p => p.parent_session_id === sid);
        btn.classList.add('loading');
        _showTreeLoading();
        try{
          if(typeof loadSession === 'function') await loadSession(sid);
          if(entry) showHistoricalTree(entry);
        }finally{
          // Cheap re-render from the data already in hand — just updates
          // the active-row highlight. No refetch, no flashing the list the
          // user is looking at while the tree-loading spinner is already up.
          _renderSidebarFromCache(listEl, _lastCanvasParents);
        }
      };
    });
  }

  function _showTreeLoading(){
    if(_treeEl) _treeEl.innerHTML = '<div class="agent-canvas-tree-loading"><div class="loading-spinner" aria-hidden="true"></div><span>Loading delegation history…</span></div>';
    if(_emptyEl) _emptyEl.style.display = 'none';
  }

  // ---- historical diagram (finished-state view for a past delegation) -----

  function showHistoricalTree(parentEntry){
    _nodes.clear();
    _selectedId = null;
    _feed = [];
    const children = Array.isArray(parentEntry.children) ? parentEntry.children : [];
    const firstStart = children.length ? Math.min(...children.map(c => c.started_at || Infinity)) : 0;
    const lastEnd = children.length ? Math.max(...children.map(c => c.ended_at || 0)) : 0;
    _nodes.set(ROOT_ID, {
      subagent_id: ROOT_ID, parent_id: null, depth: -1,
      goal: 'Main session', model: '', status: 'completed',
      toolCount: 0, tools: [], lastTool: null,
      inputTokens: 0, outputTokens: 0, reasoningTokens: 0, apiCalls: 0, costUsd: null,
      filesRead: [], filesWritten: [], outputTail: [], summary: '',
      spawnedAt: firstStart && Number.isFinite(firstStart) ? firstStart * 1000 : Date.now(),
      completedAt: lastEnd ? lastEnd * 1000 : null,
      durationSeconds: (firstStart && Number.isFinite(firstStart) && lastEnd) ? (lastEnd - firstStart) : null,
      _isRoot: true,
    });
    for(const c of children){
      // Direct children of the clicked chat map to the root (childrenOf()
      // treats a null parent_id as ROOT_ID); a nested grandchild keeps its
      // real parent so it nests under its own parent card, reconstructing
      // the same multi-level tree nested delegation actually produced.
      const isDirectChild = c.parent_session_id === parentEntry.parent_session_id;
      _nodes.set(c.session_id, {
        subagent_id: c.session_id,
        parent_id: isDirectChild ? null : c.parent_session_id,
        depth: 0,
        goal: String(c.title || '').replace(/^Subagent:\s*/, '') || 'Subagent',
        model: '',
        // A child state.db never got a completion event recorded shows as
        // 'running' from the raw query — but this is a FINISHED historical
        // session, so that can only mean it was cut off, not that it's
        // live right now. Show it as interrupted, not running.
        status: c.status === 'running' ? 'interrupted' : c.status,
        toolCount: 0, tools: [], lastTool: null,
        inputTokens: 0, outputTokens: 0, reasoningTokens: 0, apiCalls: 0, costUsd: null,
        filesRead: [], filesWritten: [], outputTail: [], summary: '',
        spawnedAt: (c.started_at || 0) * 1000,
        completedAt: c.ended_at ? c.ended_at * 1000 : null,
        durationSeconds: (c.started_at && c.ended_at) ? (c.ended_at - c.started_at) : null,
      });
    }
    _viewMode = 'history';
    render();
  }

  // "View" on the Agent Canvas sidebar's Canvas card — leaves whatever
  // historical diagram is showing and returns to tracking the real active
  // session live again.
  function returnToLiveView(){
    if(_viewMode !== 'history'){ scheduleRender(); return; }
    _nodes.clear();
    _selectedId = null;
    _feed = [];
    _lastActivityAt = 0;
    _viewMode = 'live';
    ensureRoot();
    reconcile();
    render();
  }

  window.AgentCanvas = { mount, onSpawn, onToolActivity, onComplete, reset, renderSidebar, returnToLiveView, filterAgentCanvasSessions, clearAgentCanvasSearch };
})();

// Small global wrappers so the sidebar search box's oninput/onclick
// attributes can be plain onclick=""/oninput="" like every other sidebar
// search in this app, without needing an inline `window.AgentCanvas && ...`
// guard at every call site.
function filterAgentCanvasSessions(){
  if(window.AgentCanvas && typeof window.AgentCanvas.filterAgentCanvasSessions === 'function') window.AgentCanvas.filterAgentCanvasSessions();
}
function clearAgentCanvasSearch(){
  if(window.AgentCanvas && typeof window.AgentCanvas.clearAgentCanvasSearch === 'function') window.AgentCanvas.clearAgentCanvasSearch();
}

// Small global wrapper so the "View" button on the Agent Canvas sidebar's
// Canvas card can be a plain onclick="" attribute like every other sidebar
// card in this app, without needing an inline `window.AgentCanvas && ...` guard.
function agentCanvasReturnToLive(){
  if(window.AgentCanvas && typeof window.AgentCanvas.returnToLiveView === 'function') window.AgentCanvas.returnToLiveView();
}
