// Live "Agent Canvas" panel: force-directed node graph of delegate_task
// subagent lifecycle, fed by 'subagent_spawn'/'subagent_complete' SSE
// events relayed through static/messages.js's _wireSSE. See
// docs/rfcs/agent-canvas-visualization.md for the design.
(function(){
  const GRACE_MS = 5000;             // how long a finished node stays visible before pruning
  const ORPHAN_MS = 15 * 60 * 1000;  // safety net: prune a stuck 'running' node after this long
  const ROOT_ID = '__root__';        // synthetic node representing the top-level agent
  const STATUS_COLOR = {
    running: '#5b9dff',
    completed: '#4caf6d',
    failed: '#e0555b',
    error: '#e0555b',
    timeout: '#e0555b',
    interrupted: '#9aa0a8',
    root: '#8a8f98',
  };

  let _nodes = new Map();   // subagent_id -> node record
  let _container = null;
  let _canvas = null;
  let _ctx = null;
  let _sim = null;
  let _raf = null;
  let _sweepTimer = null;
  let _emptyEl = null;
  let _lastEmptyState = null;

  function _updateEmptyState(){
    if(!_emptyEl) _emptyEl = document.getElementById('agentCanvasEmpty');
    if(!_emptyEl) return;
    // Only the synthetic root persisting after every real subagent has faded
    // out (or nothing has ever spawned) counts as "empty" from the user's view.
    const isEmpty = _nodes.size <= 1;
    if(isEmpty === _lastEmptyState) return;
    _emptyEl.style.display = isEmpty ? '' : 'none';
    _lastEmptyState = isEmpty;
  }

  function _nodesArray(){ return Array.from(_nodes.values()); }

  function _edgesArray(){
    const edges = [];
    for(const n of _nodes.values()){
      if(n.parent_id && _nodes.has(n.parent_id)){
        edges.push({source: n.parent_id, target: n.subagent_id});
      }
    }
    return edges;
  }

  function _rebuildSimulation(){
    if(!window.d3 || !_canvas) return;
    const nodes = _nodesArray();
    const edges = _edgesArray();
    if(!_sim){
      _sim = d3.forceSimulation(nodes)
        .force('charge', d3.forceManyBody().strength(-220))
        .force('link', d3.forceLink(edges).id(d => d.subagent_id).distance(90))
        .force('center', d3.forceCenter(_canvas.width / 2, _canvas.height / 2))
        .force('collide', d3.forceCollide(30));
    } else {
      _sim.nodes(nodes);
      _sim.force('link').links(edges);
      _sim.force('center', d3.forceCenter(_canvas.width / 2, _canvas.height / 2));
      _sim.alpha(0.6).restart();
    }
    const root = _nodes.get(ROOT_ID);
    if(root){
      root.fx = _canvas.width / 2;
      root.fy = _canvas.height / 2;
    }
  }

  function _resize(){
    if(!_container || !_canvas) return;
    const r = _container.getBoundingClientRect();
    _canvas.width = Math.max(1, Math.round(r.width));
    _canvas.height = Math.max(1, Math.round(r.height));
    if(_sim) _sim.force('center', d3.forceCenter(_canvas.width / 2, _canvas.height / 2));
  }

  function _draw(){
    if(!_container || !_container.isConnected || _container.offsetParent === null){
      _raf = null;
      return;
    }
    _raf = requestAnimationFrame(_draw);
    _updateEmptyState();
    if(!_ctx || !_canvas) return;
    const w = _canvas.width, h = _canvas.height;
    _ctx.clearRect(0, 0, w, h);
    const t = performance.now() / 1000;
    const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text').trim() || '#888';

    for(const edge of _edgesArray()){
      const a = _nodes.get(edge.source), b = _nodes.get(edge.target);
      if(!a || !b || a.x == null || b.x == null) continue;
      _ctx.beginPath();
      _ctx.moveTo(a.x, a.y);
      _ctx.lineTo(b.x, b.y);
      _ctx.strokeStyle = b.status === 'running' ? 'rgba(91,157,255,0.55)' : 'rgba(154,160,168,0.25)';
      _ctx.lineWidth = 1.5;
      _ctx.stroke();
      if(b.status === 'running'){
        const frac = (t % 1.2) / 1.2;
        const px = a.x + (b.x - a.x) * frac;
        const py = a.y + (b.y - a.y) * frac;
        _ctx.beginPath();
        _ctx.arc(px, py, 3, 0, Math.PI * 2);
        _ctx.fillStyle = '#5b9dff';
        _ctx.fill();
      }
    }

    for(const n of _nodes.values()){
      if(n.x == null) continue;
      const color = STATUS_COLOR[n.status] || STATUS_COLOR.running;
      const pulse = (n.status === 'running' && !n._isRoot) ? (Math.sin(t * 3 + n._phase) + 1) / 2 : 0;
      const radius = 14 + pulse * 4;
      _ctx.save();
      _ctx.shadowColor = color;
      _ctx.shadowBlur = 8 + pulse * 14;
      _ctx.globalAlpha = n._fadingOut ? 0.35 : 0.9;
      _ctx.beginPath();
      _ctx.arc(n.x, n.y, radius, 0, Math.PI * 2);
      _ctx.fillStyle = color;
      _ctx.fill();
      _ctx.restore();

      _ctx.globalAlpha = 1;
      _ctx.fillStyle = textColor;
      _ctx.font = '11px sans-serif';
      _ctx.textAlign = 'center';
      const label = (n.goal || n.subagent_id || '').slice(0, 28);
      _ctx.fillText(label, n.x, n.y + radius + 12);
    }
  }

  function _scheduleRemoval(id){
    if(id === ROOT_ID) return;
    const n = _nodes.get(id);
    if(!n) return;
    n._fadingOut = true;
    setTimeout(() => {
      _nodes.delete(id);
      _rebuildSimulation();
    }, GRACE_MS);
  }

  function _sweepOrphans(){
    const now = Date.now();
    for(const n of _nodes.values()){
      if(n.status === 'running' && now - n.spawnedAt > ORPHAN_MS){
        onComplete({subagent_id: n.subagent_id, status: 'error'});
      }
    }
  }

  function onSpawn(d){
    if(!d || !d.subagent_id || _nodes.has(d.subagent_id)) return;
    if(!_nodes.has(ROOT_ID)){
      _nodes.set(ROOT_ID, {
        subagent_id: ROOT_ID,
        parent_id: null,
        status: 'root',
        goal: 'Agent',
        _isRoot: true,
      });
    }
    _nodes.set(d.subagent_id, {
      subagent_id: d.subagent_id,
      parent_id: d.parent_id || ROOT_ID,
      depth: d.depth || 0,
      goal: d.goal || '',
      model: d.model || '',
      status: 'running',
      spawnedAt: Date.now(),
      _phase: Math.random() * Math.PI * 2,
    });
    _rebuildSimulation();
  }

  function onComplete(d){
    if(!d || !d.subagent_id) return;
    const n = _nodes.get(d.subagent_id);
    if(!n) return;
    n.status = d.status || 'completed';
    n.completedAt = Date.now();
    _scheduleRemoval(d.subagent_id);
  }

  function mount(container){
    if(!container) return;
    _container = container;
    if(!_canvas){
      _canvas = document.createElement('canvas');
      _canvas.style.width = '100%';
      _canvas.style.height = '100%';
      _canvas.style.display = 'block';
      container.appendChild(_canvas);
      _ctx = _canvas.getContext('2d');
      window.addEventListener('resize', _resize);
    } else if(_canvas.parentElement !== container){
      container.appendChild(_canvas);
    }
    _resize();
    _rebuildSimulation();
    if(!_raf) _draw();
    if(!_sweepTimer) _sweepTimer = setInterval(_sweepOrphans, 60000);
  }

  function reset(){
    _nodes.clear();
    _rebuildSimulation();
  }

  window.AgentCanvas = {mount, onSpawn, onComplete, reset};
})();
