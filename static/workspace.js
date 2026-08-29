async function api(path,opts={}){
  // Strip leading slash so URL resolves relative to location.href (supports subpath mounts)
  const rel = path.startsWith('/') ? path.slice(1) : path;
  const url=new URL(rel,document.baseURI||location.href);
  const timeoutMs=Object.prototype.hasOwnProperty.call(opts,'timeoutMs')?opts.timeoutMs:30000;
  const timeoutToast=opts.timeoutToast!==false;
  const redirect401=opts.redirect401!==false;
  const maxAttempts=Object.prototype.hasOwnProperty.call(opts,'retries')?Math.max(0,Number(opts.retries)||0)+1:3;
  const retryTimeouts=opts.retryTimeouts===true;
  const retryStatuses=Array.isArray(opts.retryStatuses)?opts.retryStatuses.map(Number).filter(Number.isFinite):[];
  const retryDelayMs=Object.prototype.hasOwnProperty.call(opts,'retryDelayMs')?Math.max(0,Number(opts.retryDelayMs)||0):350;
  // Retry up to 2 times on network errors (e.g. stale keep-alive after long idle).
  // Callers may opt into retrying timeouts / transient server statuses for idempotent GETs.
  let lastErr;
  for(let attempt=0;attempt<maxAttempts;attempt++){
    let controller=null;
    let timeoutId=null;
    let didTimeout=false;
    let upstreamSignal=null;
    let upstreamAbort=null;
    try{
      const fetchOpts={...opts};
      delete fetchOpts.timeoutMs;
      delete fetchOpts.timeoutToast;
      delete fetchOpts.redirect401;
      delete fetchOpts.retries;
      delete fetchOpts.retryTimeouts;
      delete fetchOpts.retryStatuses;
      delete fetchOpts.retryDelayMs;

      const useTimeout=Number.isFinite(Number(timeoutMs))&&Number(timeoutMs)>0;
      if(useTimeout&&typeof AbortController!=='undefined'){
        controller=new AbortController();
        upstreamSignal=fetchOpts.signal||null;
        if(upstreamSignal){
          upstreamAbort=()=>controller.abort(upstreamSignal.reason);
          if(upstreamSignal.aborted) upstreamAbort();
          else upstreamSignal.addEventListener('abort',upstreamAbort,{once:true});
        }
        fetchOpts.signal=controller.signal;
      }
      const requestPromise=(async()=>{
        const res=await fetch(url.href,{credentials:'include',headers:{'Content-Type':'application/json'},...fetchOpts});
        if(!res.ok){
          // 401 means the auth session expired. Redirect to login so the user can
          // re-authenticate. This is especially important for iOS PWA (standalone mode)
          // and for subpath mounts like /hermes/, where /login escapes to the site root.
          if(res.status===401){
            // #5578: if we're ALREADY on the login page, appending
            // window.location.pathname+search (which contains ?next=…) into a
            // fresh next= wraps the login URL into itself and re-encodes it —
            // exponential URL growth on each expired-auth bounce until the tab
            // breaks. On the login page, just reload login WITHOUT a next (the
            // page preserves its own inner next); elsewhere, capture the path.
            if(redirect401){
              // Already on the login page? Reload login WITHOUT a next.
              const _p=(window.location.pathname||'').replace(/\/+$/,'');
              if(/(?:^|\/)login$/.test(_p)){
                window.location.href='login';
              }else{
                window.location.href='login?next='+encodeURIComponent(window.location.pathname+window.location.search);
              }
            }
            // Callers can opt out of navigation and handle the unauthenticated state themselves.
            return;
          }
          const text=await res.text();
          // Parse JSON error body and surface the human-readable message,
          // rather than showing raw JSON like {"error":"Profile 'x' does not exist."}
          let message=text;
          try{const j=JSON.parse(text);message=j.error||j.message||text;}catch(e){}
          // Attach the raw HTTP context so callers can branch on status (404 stale-session
          // cleanup, 401 redirect, 503 retry, etc.) without re-parsing the message string.
          const err=new Error(message);
          err.status=res.status;
          err.statusText=res.statusText;
          err.body=text;
          throw err;
        }
        const ct=res.headers.get('content-type')||'';
        return ct.includes('application/json')?await res.json():await res.text();
      })();
      return useTimeout?await Promise.race([
        requestPromise,
        new Promise((_,reject)=>{
          timeoutId=setTimeout(()=>{
            didTimeout=true;
            if(controller) controller.abort();
            const err=new Error('Request timed out. Please try again.');
            err.name='TimeoutError';
            err.timeout=true;
            reject(err);
          },Number(timeoutMs));
        })
      ]):await requestPromise;
    }catch(e){
      lastErr=e;
      const isTimeout=didTimeout||(e&&(e.timeout===true||e.name==='TimeoutError'));
      if(isTimeout){
        if(retryTimeouts&&attempt<2&&attempt<maxAttempts-1){
          if(retryDelayMs) await new Promise(resolve=>setTimeout(resolve,retryDelayMs*Math.pow(2,attempt)));
          continue;
        }
        const err=(e&&e.name==='TimeoutError')?e:new Error('Request timed out. Please try again.');
        err.name='TimeoutError';
        err.timeout=true;
        if(timeoutToast&&typeof showToast==='function') showToast('Request timed out. Please try again.',5000,'error');
        throw err;
      }
      // Only retry on network errors (TypeError from fetch), not on HTTP errors
      // that were already thrown above. Re-throw 401 redirects immediately.
      if(e.message&&/401/.test(e.message)) throw e;
      if(attempt<2&&attempt<maxAttempts-1 && (e instanceof TypeError || retryStatuses.includes(Number(e.status)))){
        if(retryDelayMs) await new Promise(resolve=>setTimeout(resolve,retryDelayMs*Math.pow(2,attempt)));
        continue;
      }
      throw e;
    }finally{
      if(timeoutId) clearTimeout(timeoutId);
      if(upstreamSignal&&upstreamAbort) upstreamSignal.removeEventListener('abort',upstreamAbort);
    }
  }
  throw lastErr;
}

function recordClientSSEError(source, details={}){
  try{
    const payload={
      event:'sse_error',
      source:String(source||'unknown'),
      ready_state:details.ready_state,
      session_id:details.session_id||null,
      stream_id:details.stream_id||null,
      visibility_state:(typeof document!=='undefined'&&document.visibilityState)||'unknown',
      online:(typeof navigator!=='undefined'&&typeof navigator.onLine==='boolean')?navigator.onLine:null,
      url_path:(typeof location!=='undefined'&&location.pathname)||'/',
      reason:details.reason||'EventSource.onerror',
    };
    void api('/api/client-events/log',{method:'POST',body:JSON.stringify(payload),timeoutMs:3000,timeoutToast:false}).catch(()=>{});
  }catch(_){}
}

// Persist/restore expanded directory state per workspace in localStorage
function _wsExpandKey(){
  const ws=S.session&&S.session.workspace;
  return ws?'hermes-webui-expanded:'+ws:null;
}
function _saveExpandedDirs(){
  const key=_wsExpandKey();if(!key)return;
  try{localStorage.setItem(key,JSON.stringify([...(S._expandedDirs||new Set())]));}catch(e){}
}
function _restoreExpandedDirs(){
  const key=_wsExpandKey();
  if(!key){S._expandedDirs=new Set();return;}
  try{
    const raw=localStorage.getItem(key);
    S._expandedDirs=raw?new Set(JSON.parse(raw)):new Set();
  }catch(e){S._expandedDirs=new Set();}
}

function _escapeGrantStore(){
  if(!S._escapeGrants) S._escapeGrants = Object.create(null);
  return S._escapeGrants;
}

function _normalizeWorkspaceRelPath(path){
  let raw = String(path || '').trim().replace(/\\/g, '/');
  if(!raw || raw === '.') return '.';
  if(raw.startsWith('/')) return '';
  const parts = [];
  for(const part of raw.split('/')){
    if(!part || part === '.') continue;
    if(part === '..'){
      if(parts.length) parts.pop();
      else return '';
      continue;
    }
    parts.push(part);
  }
  return parts.length ? parts.join('/') : '.';
}

function _isSameOrChildPath(base, path){
  const normalizedBase = _normalizeWorkspaceRelPath(base);
  const normalizedPath = _normalizeWorkspaceRelPath(path);
  if(!normalizedBase || !normalizedPath) return false;
  if(normalizedBase === '.') return true;
  return normalizedPath === normalizedBase || normalizedPath.startsWith(`${normalizedBase}/`);
}

function _workspaceEscapeGrantForPath(path){
  const grants = _escapeGrantStore();
  const normalizedPath = _normalizeWorkspaceRelPath(path);
  if(!normalizedPath || !S.session || !S.session.session_id) return null;
  const sessionId = S.session.session_id;
  let best = null;
  for(const root of Object.keys(grants)){
    const grant = grants[root];
    if(!grant || grant.sessionId !== sessionId) continue;
    if(grant.expiresAt && Date.now() >= grant.expiresAt){
      delete grants[root];
      continue;
    }
    if(!_isSameOrChildPath(root, normalizedPath)) continue;
    if(!best || root.length > best.root.length) best = {root, grant};
  }
  return best ? best.grant : null;
}

function _workspaceEscapeExactGrant(path){
  const normalizedPath = _normalizeWorkspaceRelPath(path);
  const grant = _workspaceEscapeGrantForPath(normalizedPath);
  if(!grant) return null;
  return grant.path === normalizedPath ? grant : null;
}

function _storeWorkspaceEscapeGrant(data){
  if(!S.session || !data || !data.token) return null;
  const grants = _escapeGrantStore();
  const root = _normalizeWorkspaceRelPath(data.path || '');
  if(!root) return null;
  const grant = {
    sessionId: S.session.session_id,
    path: root,
    token: String(data.token),
    expiresAt: Number(data.expires_at || 0) * 1000,
    isDir: !!data.is_dir,
  };
  grants[root] = grant;
  return grant;
}

function _clearWorkspaceEscapeGrant(path){
  const grants = S._escapeGrants;
  if(!grants) return;
  const root = _normalizeWorkspaceRelPath(path);
  if(root && grants[root]) delete grants[root];
}

function _workspacePathIsReadOnly(path){
  return !!_workspaceEscapeGrantForPath(path || S.currentDir || '.');
}

function _workspaceRouteForPath(path, kind, opts={}){
  // Resolve the app-relative "/api/…" route against document.baseURI so the
  // URLs that are consumed OUTSIDE api() — previewImg.src, the media/pdf/html
  // frame src, the download anchor, window.open — keep working under a subpath
  // mount like /hermes/. A bare "/api/…" string resolves to the server root
  // there and 404s. (api() strips the leading slash and re-resolves against
  // baseURI itself, so routes passed through it are unaffected by already
  // being absolute.)
  const route=_workspaceRouteForPathRel(path, kind, opts);
  if(!route) return route;
  // Non-browser test harnesses have no document/location: keep the app-relative form.
  const base=(typeof document!=='undefined'&&document.baseURI)||(typeof location!=='undefined'&&location.href)||'';
  if(!base||!/^https?:\/\//i.test(base)) return route;
  const rel=route.startsWith('/') ? route.slice(1) : route;
  return new URL(rel, base).href;
}

function _workspaceRouteForPathRel(path, kind, opts={}){
  if(!S.session) return '';
  const normalizedPath = _normalizeWorkspaceRelPath(path);
  const grant = _workspaceEscapeGrantForPath(normalizedPath);
  const sessionId = encodeURIComponent(S.session.session_id);
  const params = new URLSearchParams({session_id:S.session.session_id, path:normalizedPath || '.'});
  if(grant){
    params.set('token', grant.token);
    if(kind === 'raw' && opts.download) params.set('download', '1');
    if(kind === 'raw' && opts.inline) params.set('inline', '1');
    if(kind === 'list') return `/api/escape/list?${params.toString()}`;
    if(kind === 'read') return `/api/escape/file/read?${params.toString()}`;
    if(kind === 'raw') return `/api/escape/file/raw?${params.toString()}`;
  }
  if(kind === 'list') return `/api/list?session_id=${sessionId}&path=${encodeURIComponent(normalizedPath || '.')}`;
  if(kind === 'read') return `/api/file?session_id=${sessionId}&path=${encodeURIComponent(normalizedPath || '.')}`;
  if(kind === 'raw'){
    const extra = [];
    if(opts.download) extra.push('download=1');
    // Inline previews intentionally preserve a literal &inline=1 marker in this file.
    if(opts.inline) extra.push('inline=1');
    const suffix = extra.length ? `&${extra.join('&')}` : '';
    return `/api/file/raw?session_id=${sessionId}&path=${encodeURIComponent(normalizedPath || '.')}${suffix}`;
  }
  return '';
}

async function authorizeWorkspaceEscapeNavigation(item){
  if(!S.session || !item || !item.path) return null;
  const normalizedPath = _normalizeWorkspaceRelPath(item.path);
  const exactGrant = _workspaceEscapeExactGrant(normalizedPath);
  if(!exactGrant){
    const ok = await showConfirmDialog({
      title: item.name || normalizedPath,
      message: t('external_link_open_confirm'),
      confirmLabel: t('dialog_confirm_btn'),
      danger: false,
      hideCancel: true,
      focusCancel: false,
    });
    if(!ok) return null;
  }
  try{
    const data = await api('/api/escape/authorize', {
      method: 'POST',
      body: JSON.stringify({
        session_id: S.session.session_id,
        path: normalizedPath,
      }),
    });
    const grant = _storeWorkspaceEscapeGrant(data);
    if(!grant) throw new Error('Missing escape authorization token');
    showToast(t('external_link_read_only'), 2000);
    return grant;
  }catch(e){
    showToast(t('external_link_grant_expired') || (e && e.message ? e.message : String(e)), 5000, 'error');
    return null;
  }
}

let _workspacePanelActiveTab = 'files';
let _renderSessionArtifactsTimer = null;
let _workspaceTodosLastRenderedHash = null;

function _setWorkspacePanelTabDataset(){
  const panel = document.querySelector('.rightpanel');
  if(panel) panel.dataset.activeTab = _workspacePanelActiveTab;
}

function scheduleRenderSessionArtifacts(){
  if(_renderSessionArtifactsTimer) clearTimeout(_renderSessionArtifactsTimer);
  _renderSessionArtifactsTimer = setTimeout(()=>{
    _renderSessionArtifactsTimer = null;
    renderSessionArtifacts();
  }, 100);
}

function _workspaceTodosHash(items){
  if(!Array.isArray(items)) return '';
  let h=items.length+'|';
  for(let i=0;i<items.length;i++){
    const t=items[i]||{};
    h+=String(t.id==null?'':t.id)+'\x1f'+String(t.content==null?(t.text==null?'':t.text):t.content)+'\x1f'+String(t.status==null?'':t.status)+'\x1e';
  }
  return h;
}

function _workspaceTodosTabIsActive(){
  if(typeof window==='undefined'||window._workspaceTodosTab!==true) return false;
  if(typeof document==='undefined') return false;
  const rightPanel=document.querySelector('.rightpanel');
  if(!rightPanel||!rightPanel.dataset||rightPanel.dataset.activeTab!=='todos') return false;
  const tab=document.getElementById('workspaceTodosTab');
  const panel=document.getElementById('workspaceTodosPanel');
  return !!(tab&&panel&&!tab.hidden&&!panel.hidden);
}

function _resetWorkspaceTodosRenderCache(){
  _workspaceTodosLastRenderedHash=null;
}

function _refreshWorkspacePanelTodos(){
  if(!_workspaceTodosTabIsActive()) return;
  _loadWorkspacePanelTodos();
}

if(typeof document !== 'undefined'){
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _setWorkspacePanelTabDataset, {once:true});
  else _setWorkspacePanelTabDataset();
}

function switchWorkspacePanelTab(tab){
  _workspacePanelActiveTab = tab === 'artifacts' ? 'artifacts' : tab === 'todos' ? 'todos' : 'files';
  _setWorkspacePanelTabDataset();
  const filesTab = $('workspaceFilesTab');
  const artifactsTab = $('workspaceArtifactsTab');
  const todosTab = $('workspaceTodosTab');
  if(filesTab){
    filesTab.classList.toggle('active', _workspacePanelActiveTab === 'files');
    filesTab.setAttribute('aria-selected', _workspacePanelActiveTab === 'files' ? 'true' : 'false');
  }
  if(artifactsTab){
    artifactsTab.classList.toggle('active', _workspacePanelActiveTab === 'artifacts');
    artifactsTab.setAttribute('aria-selected', _workspacePanelActiveTab === 'artifacts' ? 'true' : 'false');
  }
  if(todosTab){
    todosTab.classList.toggle('active', _workspacePanelActiveTab === 'todos');
    todosTab.setAttribute('aria-selected', _workspacePanelActiveTab === 'todos' ? 'true' : 'false');
  }
  const artifacts = $('workspaceArtifacts');
  if(artifacts) artifacts.hidden = _workspacePanelActiveTab !== 'artifacts';
  const todosPanel = $('workspaceTodosPanel');
  if(todosPanel) todosPanel.hidden = _workspacePanelActiveTab !== 'todos';
  if(_workspacePanelActiveTab === 'artifacts') renderSessionArtifacts();
  if(_workspacePanelActiveTab === 'todos') _loadWorkspacePanelTodos();
}

function _loadWorkspacePanelTodos(){
  const panel = $('workspaceTodosPanel');
  if(!panel) return;
  let todos = [];
  try{
    if(S && Array.isArray(S.todos)){
      todos = S.todos;
    } else if(S && S.session && S.session.todo_state && Array.isArray(S.session.todo_state.todos)){
      todos = S.session.todo_state.todos;
    } else if(typeof _legacyTodosFromMessages === 'function'){
      todos = _legacyTodosFromMessages() || [];
    }
  }catch(e){ todos = []; }
  if(!todos.length){
    panel.innerHTML = renderTodoEmptyState({centered:true});
    return;
  }
  panel.innerHTML = renderTodoRows(todos, {metadata:true});
}

function _escHtml(s){
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

const ARTIFACT_IGNORE_RE = /(^|\/)(?:\.git|\.hg|\.svn|node_modules|\.venv|venv|__pycache__|dist|build|\.next|\.cache)(?:\/|$)/;
// Canonical Hermes mutators plus MCP filesystem aliases that can create/edit files.
const ARTIFACT_MUTATION_TOOLS = new Set(['write_file','patch','edit_file','create_file','mcp_filesystem_write_file','mcp_filesystem_edit_file']);

function _normalizeArtifactPath(path){
  if(!path) return '';
  path = String(path).trim().replace(/[\`"'<>),.;:]+$/g,'').replace(/^[\`"'(<]+/g,'');
  if(!path || path.length > 240 || path.includes('://')) return '';
  // Canonicalize workspace-relative prefixes so a file-tree open ("foo.md") and a
  // tool arg recorded as "./foo.md" or "~/foo.md" compare equal for mutation
  // tracking; otherwise an agent edit via a ./-prefixed path leaves the open
  // preview stale (#3262 / pre-release regression-gate finding).
  path = path.replace(/^~\//,'').replace(/^(?:\.\/)+/,'');
  if(!path) return '';
  if(ARTIFACT_IGNORE_RE.test(path)) return '';
  if(!/[./]/.test(path)) return '';
  return path;
}

function _artifactCandidatesFromText(text){
  if(!text || typeof text !== 'string') return [];
  const out = [];
  const seen = new Set();
  const add = (path) => {
    path = _normalizeArtifactPath(path);
    if(!path || seen.has(path)) return;
    seen.add(path); out.push({path, kind:'diff'});
  };
  // Fallback text mining is intentionally narrow: only diff/patch fences imply
  // the session changed a file. Prose mentions such as "edited package.json" are
  // too noisy for an Artifacts list that should track write/edit outputs.
  const fenced = /```(?:diff|patch)\s*\n[\s\S]*?```/gi;
  let m;
  while((m = fenced.exec(text))){
    const block = m[0];
    const fm = block.match(/(?:^|\n)(?:\+\+\+|---)\s+(?:[ab]\/)?([^\n\t]+)/);
    if(fm) add(fm[1].trim());
  }
  return out;
}

function _artifactCandidatesFromToolCall(tc){
  if(!tc) return [];
  const name = String(tc.name || '').replace(/^functions\./,'');
  const args = tc.arguments || tc.args || tc.input || {};
  const result = tc.result || tc.output || tc.snippet || '';
  const out = [];
  const add = (path, source=name || 'tool') => {
    path = _normalizeArtifactPath(path);
    if(path) out.push({path, kind:source});
  };
  if(ARTIFACT_MUTATION_TOOLS.has(name) && args && typeof args === 'object'){
    for(const key of ['path','file_path','source','destination']) add(args[key]);
    if(Array.isArray(args.paths)) args.paths.forEach(p=>add(p));
    if(Array.isArray(args.edits)) args.edits.forEach(e=>add(e&&e.path));
  }
  const resultText = typeof result === 'string' ? result : (result ? JSON.stringify(result) : '');
  // Tool results may include unified diffs from patch-style tools; scan those
  // narrowly after structured args so diff headers can still contribute paths.
  for(const a of _artifactCandidatesFromText(resultText)) out.push(a);
  if(!out.length && ARTIFACT_MUTATION_TOOLS.has(name)){
    const argsText = typeof args === 'string' ? args : JSON.stringify(args || {});
    for(const a of _artifactCandidatesFromText(argsText)) out.push(a);
  }
  return out;
}

const _turnMutatedPreviewPaths = new Set();

function resetTurnWorkspaceMutations(){
  _turnMutatedPreviewPaths.clear();
}

function noteWorkspaceMutationsFromToolCall(tc){
  for(const a of _artifactCandidatesFromToolCall(tc)){
    const path=_normalizeArtifactPath(a.path);
    if(path) _turnMutatedPreviewPaths.add(path);
  }
}

function noteWorkspaceMutationsFromToolCalls(toolCalls){
  if(!Array.isArray(toolCalls)) return;
  for(const tc of toolCalls) noteWorkspaceMutationsFromToolCall(tc);
}

function _isOpenPreviewPathMutated(){
  if(!_previewCurrentPath) return false;
  const current=_normalizeArtifactPath(_previewCurrentPath);
  return !!(current&&_turnMutatedPreviewPaths.has(current));
}

async function refreshOpenPreviewIfMutated(){
  if(typeof _previewDirty!=='undefined'&&_previewDirty) return;
  if(!_isOpenPreviewPathMutated()) return;
  if(!_previewCurrentPath||!S.session) return;
  await openFile(_previewCurrentPath, { bustCache: true });
}

function collectSessionArtifacts(){
  const items = [];
  const seen = new Set();
  const push = (path, source) => {
    path = _normalizeArtifactPath(path);
    if(!path || seen.has(path)) return;
    seen.add(path); items.push({path, source});
  };
  // Source 1: session-level tool call summaries (may be empty when messages
  // carry their own tool metadata — see _syncToolCallsForLoadedMessages).
  for(const tc of (S.toolCalls || [])){
    for(const a of _artifactCandidatesFromToolCall(tc)) push(a.path, a.kind || tc.name || 'tool');
  }
  // Source 2 & 3: message-level data — both text-mined diffs and structured
  // tool_calls / tool_use content blocks that survive the S.toolCalls clear.
  for(const msg of (S.messages || [])){
    if(!msg) continue;
    const text = msg.content || msg.text || msg.message || '';
    // Text-mined diff/patch fences (existing path).
    if(typeof text === 'string'){
      for(const a of _artifactCandidatesFromText(text)) push(a.path, a.kind);
    }
    // Structured tool_calls array (OpenAI format: {function:{name,arguments}}).
    if(Array.isArray(msg.tool_calls)){
      for(const tc of msg.tool_calls){
        if(!tc || typeof tc !== 'object') continue;
        const fn = (tc.function && typeof tc.function === 'object') ? tc.function : tc;
        const name = fn.name || tc.name || '';
        let args = fn.arguments || tc.arguments || tc.args || tc.input || {};
        if(typeof args === 'string'){ try{ args = JSON.parse(args); }catch(_){} }
        const fakeTc = {name, args, result: tc.result || tc.output || ''};
        for(const a of _artifactCandidatesFromToolCall(fakeTc)) push(a.path, a.kind || name || 'tool');
      }
    }
    // Structured content array with tool_use blocks (Anthropic format).
    if(Array.isArray(msg.content)){
      for(const block of msg.content){
        if(!block || block.type !== 'tool_use') continue;
        let inp = block.input || {};
        if(typeof inp === 'string'){ try{ inp = JSON.parse(inp); }catch(_){} }
        const fakeTc = {name: block.name || '', args: inp, result: block.result || ''};
        for(const a of _artifactCandidatesFromToolCall(fakeTc)) push(a.path, a.kind || block.name || 'tool');
      }
    }
  }
  return items.slice(0, 50);
}

function renderSessionArtifacts(){
  const root = $('workspaceArtifacts');
  const count = $('workspaceArtifactsCount');
  if(!root) return;
  const items = collectSessionArtifacts();
  if(count) count.textContent = String(items.length);
  if(!S.session){
    root.innerHTML = '<div class="workspace-artifact-empty">Open a conversation to see files changed in this session.</div>';
    return;
  }
  if(!items.length){
    root.innerHTML = '<div class="workspace-artifact-empty">No artifacts detected yet. Files created or edited during this session will appear here.</div>';
    return;
  }
  // Strip workspace prefix for display so long absolute paths don't clutter the list.
  const ws = S.session && S.session.workspace;
  const normWs = ws ? ws.replace(/\/+$/,'') + '/' : '';
  const displayPath = (p) => {
    if(normWs && p.startsWith(normWs)) return p.slice(normWs.length);
    return p;
  };
  const splitArtifactDisplayPath = (path) => {
    const slash = path.lastIndexOf('/');
    if(slash < 0) return {name: path, head: '', tail: ''};
    const directory = path.slice(0, slash + 1);
    const parentSlash = directory.lastIndexOf('/', directory.length - 2);
    return {
      name: path.slice(slash + 1),
      head: directory.slice(0, parentSlash + 1),
      tail: directory.slice(parentSlash + 1),
    };
  };
  root.innerHTML = items.map(item => {
    const path = displayPath(item.path);
    const parts = splitArtifactDisplayPath(path);
    const directory = (parts.head || parts.tail)
      ? `<div class="workspace-artifact-directory"><span class="workspace-artifact-directory-head">${esc(parts.head)}</span><span class="workspace-artifact-directory-tail">${esc(parts.tail)}</span></div>`
      : '';
    const source = item.source ? esc(item.source) : esc(t('workspace_artifact_source_session') || 'session');
    const sourceAttrs = item.source ? '' : ' data-i18n="workspace_artifact_source_session"';
    return `<button type="button" class="workspace-artifact-item" title="${esc(path)}" data-artifact-path="${esc(item.path)}" onclick="openArtifactPath(this.dataset.artifactPath)"><div class="workspace-artifact-filename">${esc(parts.name)}</div>${directory}<div class="workspace-artifact-meta"${sourceAttrs}>${source}</div></button>`;
  }).join('');
}

async function _workspacePathExists(path){
  if(!S.session||!path) return false;
  const parts=String(path).replace(/\\/g,'/').split('/').filter(Boolean);
  const name=parts.pop();
  if(!name) return false;
  const dir=parts.length?parts.join('/'):'.';
  const data=await api(`/api/list?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(dir)}`);
  return (data.entries||[]).some(entry=>entry&&((entry.path===path)||entry.name===name));
}

async function openArtifactPath(path){
  if(!path) return;
  switchWorkspacePanelTab('files');
  // Normalize backslash separators to '/' first — Windows absolute paths
  // (e.g. "D:\workspace\dir\file") otherwise break prefix-strip and the
  // /api/list existence check (which splits on '/').
  let rel = String(path).replace(/\\/g,'/').replace(/^~\//,'').replace(/^(?:\.\/)+/,'');
  // Strip workspace prefix so /api/list receives a workspace-relative path.
  const ws = (S.session && S.session.workspace || '').replace(/\\/g,'/');
  if(ws){
    const normWs = ws.replace(/\/+$/,'') + '/';
    if(rel.startsWith(normWs)) rel = rel.slice(normWs.length);
    else if(rel === ws.replace(/\/+$/,'')) rel = '.';
  }
  if(!rel) rel = '.';
  try{
    if(!(await _workspacePathExists(rel))){
      setStatus(t('file_open_failed'));
      return;
    }
  }catch(_){
    setStatus(t('file_open_failed'));
    return;
  }
  openFile(rel);
}

// ── Workspace file-tree loading skeleton (#4662 Phase 1) ────────────────────
// During a profile switch the right-hand workspace panel would otherwise keep
// showing the previous profile's file tree until /api/list resolves. Show a
// clean tree-shaped skeleton in its place (panel stays open — hiding it is
// jarring). Varied bar widths + a small indent pattern so it reads as a real
// directory listing rather than a mechanical repeat.
const _WS_SKELETON_ROWS = [
  {w: 38, indent: 0, dir: true},
  {w: 72, indent: 0},
  {w: 44, indent: 1},
  {w: 63, indent: 1},
  {w: 80, indent: 0},
  {w: 51, indent: 1},
  {w: 67, indent: 0},
  {w: 39, indent: 1},
];

// Workspace-tree render generation. loadDir() captures this at call time and
// discards its render/cache writes if a newer generation started meanwhile.
// #4671 CORE: an empty-session profile switch REUSES the same session_id, so
// loadDir()'s session_id guard alone can't reject a pre-switch /api/list response
// that resolves after the new profile's loadDir('.') — it would paint the previous
// workspace's files over the switched-to profile. switchToProfile() bumps this
// UNCONDITIONALLY at switch start (even when the workspace panel is closed, since
// loadDir('.') still runs then), so the stale response is rejected.
let _wsTreeGen = 0;
function bumpWorkspaceTreeGen(){
  _wsTreeGen = (typeof _wsTreeGen === 'number' ? _wsTreeGen : 0) + 1;
  return _wsTreeGen;
}
if(typeof window!=='undefined') window.bumpWorkspaceTreeGen = bumpWorkspaceTreeGen;

function showWorkspaceTreeSkeleton(){
  const tree = $('fileTree');
  if(!tree) return;
  const wrap = document.createElement('div');
  wrap.className = 'skeleton-tree';
  wrap.setAttribute('aria-hidden', 'true');
  for(const spec of _WS_SKELETON_ROWS){
    const row = document.createElement('div');
    row.className = 'skeleton-tree-row';
    if(spec.indent) row.style.paddingLeft = (2 + spec.indent * 16) + 'px';
    const glyph = document.createElement('div');
    glyph.className = 'skeleton-glyph';
    const name = document.createElement('div');
    name.className = 'skeleton-bar skeleton-name';
    name.style.width = spec.w + '%';
    row.appendChild(glyph);
    row.appendChild(name);
    // Files (not dirs) show a size on the right; mirror that on leaf rows.
    if(!spec.dir){
      const size = document.createElement('div');
      size.className = 'skeleton-bar skeleton-size';
      row.appendChild(size);
    }
    wrap.appendChild(row);
  }
  tree.innerHTML = '';
  tree.appendChild(wrap);
  tree.style.display = '';
}

// Clear a stranded workspace-tree skeleton (#4662 Opus gate). showWorkspaceTreeSkeleton()
// is shown up front on a profile switch, but the real loadDir('.') that would
// replace it is skipped when the new profile has no bound workspace — leaving a
// shimmering skeleton forever. Call this on the no-workspace path so the tree
// empties instead. Only touches #fileTree when it still holds a skeleton, so
// it can't clobber a real render.
function clearWorkspaceTreeSkeleton(){
  const tree = $('fileTree');
  if(!tree) return;
  if(tree.querySelector('.skeleton-tree')) tree.innerHTML = '';
}

async function loadDir(path, opts={}){
  const preservePreview=!!(opts&&opts.preservePreview);
  const refreshExpanded=!!(opts&&opts.refreshExpanded);
  if(!S.session)return;
  const sessionId=S.session.session_id;
  const treeGen=_wsTreeGen;  // #4671: capture the workspace-tree generation. A profile
                             // switch bumps it (bumpWorkspaceTreeGen), so a stale response
                             // from the previous workspace — which would pass the session_id
                             // guard because an empty-session switch reuses the same id — is
                             // rejected here instead of painting the wrong profile's files.
  try{
    if(!path||path==='.'||refreshExpanded){
      S._dirCache={};
      _restoreExpandedDirs();  // restore per-workspace expanded state after root and refresh resets
    }
    S.currentDir=path||'.';
    const data=await api(
      _workspaceRouteForPath(path, 'list') ||
      `/api/list?session_id=${encodeURIComponent(sessionId)}&path=${encodeURIComponent(path||'.')}`
    );
    if(!S.session||S.session.session_id!==sessionId||treeGen!==_wsTreeGen)return;
    if(data.workspace_recovered&&data.workspace){
      S.session.workspace=String(data.workspace);
      S._dirCache={};
      _restoreExpandedDirs();
      if(typeof syncWorkspaceDisplays==='function')syncWorkspaceDisplays();
      if(typeof syncTerminalButton==='function')syncTerminalButton();
      showToast(t('workspace_recovered_notice',S.session.workspace),5000,'warning');
    }
    S.entries=data.entries||[];renderBreadcrumb();renderFileTree();
    // #2673 — refresh Artifacts tab when its source data (the file tree) updates.
    if(typeof renderSessionArtifacts==='function') renderSessionArtifacts();
    // Pre-fetch contents of restored expanded dirs so they render without a second click
    // (parallelized — avoids serial waterfall when multiple dirs are expanded)
    if(!path||path==='.'||refreshExpanded){
      const expanded=S._expandedDirs||new Set();
      const pending=[...expanded].filter(dirPath=>!S._dirCache[dirPath]);
      if(pending.length){
        const results=await Promise.all(pending.map(dirPath=>
          api(_workspaceRouteForPath(dirPath, 'list'))
            .then(dc=>({dirPath,entries:dc.entries||[]}))
            .catch(()=>({dirPath,entries:[]}))
        ));
        if(!S.session||S.session.session_id!==sessionId||treeGen!==_wsTreeGen)return;
        for(const {dirPath,entries} of results) S._dirCache[dirPath]=entries;
      }
      if(expanded.size>0)renderFileTree();
    }
    if(!preservePreview&&typeof clearPreview==='function'){
      if(typeof _previewDirty!=='undefined'&&_previewDirty){
        showConfirmDialog({title:t('unsaved_confirm'),message:'',confirmLabel:'Discard',danger:true,focusCancel:true}).then(ok=>{if(ok)clearPreview({keepPanelOpen:true});});
      }else{
        clearPreview({keepPanelOpen:true});
      }
    }else if(preservePreview){
      await refreshOpenPreviewIfMutated();
    }
    // Fetch git info for workspace root (non-blocking)
    if(!path||path==='.'){ _refreshGitBadge(); if(typeof renderBoundProjectControl==='function') renderBoundProjectControl(); if(typeof renderProjectFolderBinding==='function') renderProjectFolderBinding(); }
  }catch(e){
    const grant = _workspaceEscapeGrantForPath(path);
    if(grant && e && e.status===403){
      _clearWorkspaceEscapeGrant(grant.path);
      showToast(t('external_link_grant_expired') || t('file_open_failed'), 5000, 'error');
      return;
    }
    console.warn('loadDir',e);
  }
}

function refreshWorkspacePanel(){
  if(!S.session)return;
  const targetDir = S.currentDir || '.';
  loadDir(targetDir,{refreshExpanded:true});
}

async function _refreshGitBadge(){
  const badge=$('gitBadge');
  if(!badge||!S.session)return;
  const sessionId=S.session.session_id;
  try{
    const data=await api(`/api/git-info?session_id=${encodeURIComponent(sessionId)}`);
    if(!S.session||S.session.session_id!==sessionId)return;
    if(data.git&&data.git.is_git){
      const g=data.git;
      let text=g.branch||'git';
      if(g.dirty>0) text+=` \u00b7 ${g.dirty}\u2206`; // middot + delta
      if(g.behind>0) text+=` \u2193${g.behind}`;
      if(g.ahead>0) text+=` \u2191${g.ahead}`;
      badge.textContent=text;
      badge.className='git-badge'+(g.dirty>0?' dirty':'');
      badge.style.display='';
    } else {
      badge.style.display='none';
      badge.textContent='';
    }
  }catch(e){
    if(!S.session||S.session.session_id!==sessionId)return;
    badge.style.display='none';
  }
}

// ── Project-bound chats ──────────────────────────────────────────────────
// A chat can be bound to a WORKSPACES.yaml registry project (see
// api/project_registry.py). Binding is enforced server-side: every turn
// carries the resolved project context and force-preloads the
// project-lifecycle skill (api/streaming.py:_bound_project_prompt). This
// control just lets the user pick/change the binding for the active chat.
let _boundProjectRegistryCache=null;
let _boundProjectRegistryFetchedAt=0;
const BOUND_PROJECT_REGISTRY_CACHE_MS=15000;

async function _fetchProjectRegistry(force){
  const now=Date.now();
  if(!force && _boundProjectRegistryCache && (now-_boundProjectRegistryFetchedAt)<BOUND_PROJECT_REGISTRY_CACHE_MS){
    return _boundProjectRegistryCache;
  }
  try{
    const data=await api('/api/workspaces/registry');
    _boundProjectRegistryCache=Array.isArray(data.projects)?data.projects:[];
    _boundProjectRegistryFetchedAt=now;
  }catch(e){
    console.warn('_fetchProjectRegistry',e);
    _boundProjectRegistryCache=_boundProjectRegistryCache||[];
  }
  return _boundProjectRegistryCache;
}

async function renderBoundProjectControl(){
  const row=$('boundProjectRow');
  const select=$('boundProjectSelect');
  if(!row||!select||!S.session)return;
  const sessionId=S.session.session_id;
  const projects=await _fetchProjectRegistry();
  if(!S.session||S.session.session_id!==sessionId)return; // session switched mid-fetch

  if(!projects.length){ row.hidden=true; return; }
  row.hidden=false;
  const boundKey=S.session.bound_project_key||'';
  const options=['<option value="">'+t('bound_project_unbound','Unbound')+'</option>'];
  for(const p of projects){
    const label=p.available?p.name:`${p.name} (${p.unavailable_reason||t('bound_project_unavailable','unavailable')})`;
    options.push(`<option value="${_escHtml(p.key)}" ${(!p.available&&p.key!==boundKey)?'disabled':''}>${_escHtml(label)}</option>`);
  }
  // A bound project can be renamed/removed from WORKSPACES.yaml out from
  // under an already-bound chat. The backend still force-injects a visible
  // "PROJECT BINDING ERROR" into every turn's system prompt for this case
  // (api/streaming.py _bound_project_prompt), but without a matching
  // <option>, `select.value=boundKey` below is a silent no-op and the
  // dropdown falls back to showing "Unbound" — giving no visual cue that
  // anything is wrong. Synthesize a disabled option so the UI surfaces the
  // same broken-binding state the model is already being told about.
  if(boundKey && !projects.some(p=>p.key===boundKey)){
    const missingLabel=(t('bound_project_missing')||'Bound project not found: {0}').replace('{0}',boundKey);
    options.push(`<option value="${_escHtml(boundKey)}" disabled>${_escHtml(missingLabel)}</option>`);
  }
  select.innerHTML=options.join('');
  select.value=boundKey;
}

// Shared bind/unbind call used by both the workspace-panel select and the
// composer workspace-switcher dropdown, so there's exactly one code path
// that talks to POST /api/session/bind_project.
async function _bindProjectAndRefresh(projectKey){
  // Mirrors switchToWorkspace()'s blank-page handling (Opus review Q6,
  // panels.js): the composer workspace dropdown — and its Projects section
  // — is reachable before any session exists (the "What can I help with?"
  // landing screen). Without this, clicking a project there silently
  // no-ops (#regression: user saw "nothing happens" clicking Bind).
  if(!S.session){
    try{
      const r=await api('/api/session/new',{method:'POST',body:JSON.stringify({worktree:false})});
      if(r&&r.session){
        S._pendingSessionToolsets=null;
        S.session=r.session;
        S.messages=[];
        if(typeof syncTopbar==='function') syncTopbar();
        if(typeof renderMessages==='function') renderMessages();
        if(typeof renderSessionList==='function') await renderSessionList();
      }
    }catch(e){
      showToast((e&&e.message)||t('bound_project_bind_failed','Failed to update project binding'),5000,'error');
      return false;
    }
    if(!S.session)return false;
  }
  const sessionId=S.session.session_id;
  try{
    const res=await api('/api/session/bind_project',{method:'POST',body:JSON.stringify({session_id:sessionId,project_key:projectKey})});
    if(res && res.session && S.session && S.session.session_id===sessionId){
      Object.assign(S.session,res.session);
      showToast(projectKey?t('bound_project_bound','Chat bound to project'):t('bound_project_unbound_toast','Chat unbound'));
      if(S.session.workspace) loadDir('.');
      if(typeof syncWorkspaceDisplays==='function') syncWorkspaceDisplays();
    }
    return true;
  }catch(e){
    console.warn('_bindProjectAndRefresh',e);
    showToast((e&&e.message)||t('bound_project_bind_failed','Failed to update project binding'),5000,'error');
    return false;
  }
}

// Renders a "Projects" section into the composer workspace-switcher dropdown
// (see renderWorkspaceDropdownInto in panels.js), so a project can be bound
// right at chat start, alongside the folder list — not only from the
// workspace panel later. Reuses the exact same registry data and bind call.
function renderBoundProjectDropdownSection(dd, projects, boundKey){
  if(!dd||!projects||!projects.length)return;
  const section=document.createElement('div');
  section.className='ws-project-section';
  const heading=document.createElement('div');
  heading.className='ws-project-heading';
  heading.textContent=t('bound_project_label','Project');
  section.appendChild(heading);

  const unboundOpt=document.createElement('div');
  unboundOpt.className='ws-opt ws-project-opt'+(boundKey?'':' active');
  unboundOpt.innerHTML=`<span class="ws-opt-name">${_escHtml(t('bound_project_unbound','Unbound'))}</span>`;
  unboundOpt.onclick=async()=>{
    closeWsDropdown();
    await _bindProjectAndRefresh(null);
  };
  section.appendChild(unboundOpt);

  for(const p of projects){
    const opt=document.createElement('div');
    const isActive=p.key===boundKey;
    opt.className='ws-opt ws-project-opt'+(isActive?' active':'')+(p.available?'':' disabled');
    const meta=p.available?(p.access_mode==='ssh'?'ssh':'local'):(p.unavailable_reason||t('bound_project_unavailable','unavailable'));
    opt.innerHTML=`<span class="ws-opt-name">${_escHtml(p.name)}</span><span class="ws-opt-path">${_escHtml(meta)}</span>`;
    if(p.available){
      opt.onclick=async()=>{
        closeWsDropdown();
        await _bindProjectAndRefresh(p.key);
      };
    }
    section.appendChild(opt);
  }
  dd.appendChild(section);
  dd.appendChild(document.createElement('div')).className='ws-divider';
}

async function onBoundProjectSelectChange(selectEl){
  if(!S.session)return;
  const previousKey=S.session.bound_project_key||'';
  selectEl.disabled=true;
  const ok=await _bindProjectAndRefresh(selectEl.value||null);
  if(!ok) selectEl.value=previousKey;
  selectEl.disabled=false;
}

function navigateUp(){
  if(!S.session||S.currentDir==='.')return;
  const parts=S.currentDir.split('/');
  parts.pop();
  loadDir(parts.length?parts.join('/'):'.');
}

// File extension sets for preview routing (must match server-side sets)
const IMAGE_EXTS  = new Set(['.png','.jpg','.jpeg','.gif','.svg','.webp','.ico','.bmp']);
const MD_EXTS     = new Set(['.md','.markdown','.mdown']);
const HTML_EXTS   = new Set(['.html','.htm']);
const PDF_EXTS    = new Set(['.pdf']);
const AUDIO_EXTS  = new Set(['.mp3','.wav','.m4a','.aac','.ogg','.oga','.opus','.flac']);
const VIDEO_EXTS  = new Set(['.mp4','.mov','.m4v','.webm','.ogv','.avi','.mkv']);
const MD_PREVIEW_RICH_RENDER_MAX_BYTES = 256 * 1024;
const MD_PREVIEW_RICH_RENDER_MAX_LINES = 5000;
// Binary formats that should download rather than preview
const DOWNLOAD_EXTS = new Set([
  '.doc','.xls','.ppt','.odt','.ods','.odp',
  '.zip','.tar','.gz','.bz2','.7z','.rar',
  '.exe','.dmg','.pkg','.deb','.rpm',
  '.woff','.woff2','.ttf','.otf','.eot',
  '.bin','.dat','.db','.sqlite','.pyc','.class','.so','.dylib','.dll',
]);

function fileExt(p){ const i=p.lastIndexOf('.'); return i>=0?p.slice(i).toLowerCase():''; }

function markdownPreviewByteLength(content){
  const text=String(content||'');
  if(typeof Blob==='function') return new Blob([text]).size;
  if(typeof TextEncoder==='function') return new TextEncoder().encode(text).length;
  return unescape(encodeURIComponent(text)).length;
}

function markdownPreviewLineCount(content){
  const text=String(content||'');
  if(!text) return 1;
  return text.split('\n').length;
}

function shouldRenderMarkdownPreviewAsPlainText(content){
  return markdownPreviewByteLength(content)>MD_PREVIEW_RICH_RENDER_MAX_BYTES
    || markdownPreviewLineCount(content)>MD_PREVIEW_RICH_RENDER_MAX_LINES;
}

function largeMarkdownPlainTextStatus(content){
  const bytes=markdownPreviewByteLength(content);
  const lines=markdownPreviewLineCount(content);
  const sizeLabel=bytes>=1024?`${Math.round(bytes/1024)} KB`:`${bytes} B`;
  return `Large markdown file (${sizeLabel}, ${lines} lines) shown as plain text. Click "Render as markdown anyway" to force rich rendering, or Edit to view raw.`;
}

function setLargeMarkdownForceRenderVisible(visible){
  const btn=$('btnRenderMarkdownAnyway');
  if(btn) btn.style.display=visible?'inline-flex':'none';
}

function renderMarkdownPreviewContent(data){
  const target=data&&data.el?data.el:$('previewMd');
  if(!data||!data.el) showPreview('md');
  target.innerHTML=renderMd(data.content);
  requestAnimationFrame(()=>{if(typeof renderKatexBlocks==='function')renderKatexBlocks();});
}

function renderCodePreviewContent(path, content){
  showPreview('code');
  const codeEl=document.createElement('code');
  codeEl.textContent=content;
  const lang=_prismLanguageForPath(path);
  if(lang) codeEl.className='language-'+lang;
  const pre=$('previewCode');
  pre.textContent='';
  // Prism.highlightElement() propagates the language-* class onto the
  // parent <pre>, so a previously-previewed code file leaves e.g.
  // "language-css" on #previewCode. A subsequent plain-text file builds a
  // class-less <code>, and Prism walks up to that stale ancestor class and
  // mis-highlights prose. Strip any inherited language-* token from the
  // <pre> before each render so highlighting never leaks across files.
  pre.className=pre.className.replace(/\blanguage-\S+/g,'').replace(/\s+/g,' ').trim();
  pre.appendChild(codeEl);
  // Only invoke Prism when we actually assigned a language; otherwise the
  // class-less <code> would inherit any ancestor language-* class.
  if(lang&&typeof Prism!=='undefined'&&typeof Prism.highlightElement==='function'){
    Prism.highlightElement(codeEl);
  }
}

function renderCsvPreviewContent(path, content){
  if(typeof buildCsvTablePreview!=='function') return false;
  const preview=buildCsvTablePreview(path, content);
  if(!preview) return false;
  showPreview('csv');
  // Preserve the raw CSV text so the Edit flow can repopulate the textarea and
  // a save can re-render the table from the edited source (#4025 review, Codex).
  if(typeof content==='string'){
    _previewRawContent = content;
    _previewRawContentPath = path;
  }
  if(preview.html){
    $('previewMd').innerHTML=preview.html;
    return true;
  }
  if(preview.errorKey&&typeof _csvPreviewErrorHtml==='function'){
    $('previewMd').innerHTML=_csvPreviewErrorHtml(path, preview.errorKey);
    return true;
  }
  return false;
}

function forceRenderMarkdownPreview(){
  // #3378 review (Codex): don't force-render from a dirty/open editor — the
  // cached raw content would not reflect the unsaved edit. Require a saved,
  // non-dirty state and cached content that belongs to the current file.
  if(_previewDirty || $('previewEditArea').style.display!=='none') return;
  if(!_previewRawContent || _previewRawContentPath!==_previewCurrentPath) return;
  openFile(_previewCurrentPath,{forceRichMarkdown:true});
  setStatus('Markdown rendered for this file.');
}

let _previewCurrentPath = '';  // relative path of currently previewed file
let _previewCurrentMode = '';  // 'code' | 'csv' | 'md' | 'image' | 'html' | 'pdf' | 'audio' | 'video'
let _previewDirty = false;     // true when edits are unsaved
let _previewServerEditable = null;  // backend editability metadata when available
let _previewSaveRoute = '/api/file/save';  // current save adapter for the open preview
let _previewOfficeFormat = '';  // current claimed Office format, if any
let _previewPreviewKind = '';  // preview family returned by the backend

function showPreview(mode){
  // mode: 'code' | 'csv' | 'image' | 'md' | 'html' | 'pdf' | 'audio' | 'video'
  $('previewCode').style.display     = mode==='code'  ? '' : 'none';
  $('previewImgWrap').style.display  = mode==='image' ? '' : 'none';
  const mediaWrap=$('previewMediaWrap'); if(mediaWrap) mediaWrap.style.display = (mode==='audio'||mode==='video') ? '' : 'none';
  const pdfWrap=$('previewPdfWrap'); if(pdfWrap) pdfWrap.style.display = mode==='pdf' ? '' : 'none';
  $('previewMd').style.display       = (mode==='md'||mode==='csv') ? '' : 'none';
  $('previewHtmlWrap').style.display = mode==='html'  ? '' : 'none';
  $('previewEditArea').style.display = 'none';  // start in read-only
  const badge=$('previewBadge');
  badge.className='preview-badge '+mode;
  badge.textContent = mode==='image'?'image':mode==='audio'?'audio':mode==='video'?'video':mode==='pdf'?'pdf':mode==='csv'?'csv':mode==='md'?'md':mode==='html'?'html':fileExt($('previewPathText').textContent)||'text';
  _previewCurrentMode = mode;
  _previewDirty = false;
  updateEditBtn();
  // Show "Open in browser" button for iframe-backed document previews
  const openBtn=$('btnOpenInBrowser');
  if(openBtn) openBtn.style.display = (mode==='html'||mode==='pdf')?'inline-flex':'none';
  setLargeMarkdownForceRenderVisible(false);
}

function updateEditBtn(){
  const btn=$('btnEditFile');
  if(!btn)return;
  const editable = !_workspacePathIsReadOnly(_previewCurrentPath)
    && (_previewServerEditable===null
      ? (_previewCurrentMode==='code'||_previewCurrentMode==='md'||_previewCurrentMode==='csv')
      : !!_previewServerEditable);
  btn.style.display = editable?'':'none';
  const editing = $('previewEditArea').style.display!=='none';
  btn.innerHTML = editing ? `&#128190; ${t('save')}` : `&#9998; ${t('edit')}`;
  btn.title = editing ? t('save_title') : t('edit_title');
  btn.style.color = editing ? 'var(--blue)' : '';
  if(_previewDirty) btn.innerHTML = '&#128190; Save*';
}

async function toggleEditMode(){
  const editing = $('previewEditArea').style.display!=='none';
  if(_workspacePathIsReadOnly(_previewCurrentPath)){
    showToast(t('external_link_read_only'), 2000);
    return;
  }
  if(!editing && _previewServerEditable===false){
    showToast('This Office document is preview-only.', 3000, 'error');
    return;
  }
  if(editing){
    // Save
    if(!S.session||!_previewCurrentPath)return;
    const content=$('previewEditArea').value;
    try{
      const saved=await api(_previewSaveRoute||'/api/file/save',{method:'POST',body:JSON.stringify({
        session_id:S.session.session_id, path:_previewCurrentPath, content
      })});
      const savedContent=saved&&typeof saved.content==='string'?saved.content:content;
      if(saved && typeof saved.editable==='boolean') _previewServerEditable = saved.editable;
      if(saved && saved.preview_kind) _previewPreviewKind = saved.preview_kind;
      if(saved && saved.office_format) _previewOfficeFormat = saved.office_format;
      if(saved && saved.preview_kind==='office' && saved.office_format==='docx'){
        _previewSaveRoute = '/api/file/office-save';
      }
      _previewDirty=false;
      // Update read-only views AND the cached raw content so a later
      // "Render as markdown anyway" force-render reflects the just-saved text
      // (not the stale pre-edit fetch). #3378 review (Codex).
      _previewRawContent = savedContent;
      _previewRawContentPath = _previewCurrentPath;
      if(_previewCurrentMode==='code') $('previewCode').textContent=savedContent;
      else if(_previewCurrentMode==='csv') renderCsvPreviewContent(_previewCurrentPath, savedContent);
      else renderMarkdownPreviewContent({content:savedContent});
      $('previewEditArea').style.display='none';
      if(_previewCurrentMode==='code') $('previewCode').style.display='';
      else $('previewMd').style.display='';
      showToast(t('saved'));
    }catch(e){setStatus(t('save_failed')+e.message);}
  }else{
    // Enter edit mode: populate textarea with current content
    const currentText = _previewCurrentMode==='code'
      ? $('previewCode').textContent
      : _previewRawContent||'';
    $('previewEditArea').value=currentText;
    $('previewEditArea').style.display='';
    if(_previewCurrentMode==='code') $('previewCode').style.display='none';
    else $('previewMd').style.display='none';
    // Escape cancels the edit without saving
    $('previewEditArea').onkeydown=e=>{
      if(e.key==='Escape'){e.preventDefault();cancelEditMode();}
    };
  }
  updateEditBtn();
}

let _previewRawContent = '';  // raw text for md files (to populate editor)
let _previewRawContentPath = '';  // path that _previewRawContent belongs to (#3378 force-render cache guard)

function cancelEditMode(){
  // Discard changes and return to read-only view
  $('previewEditArea').style.display='none';
  $('previewEditArea').onkeydown=null;
  if(_previewCurrentMode==='code') $('previewCode').style.display='';
  else $('previewMd').style.display='';
  _previewDirty=false;
  updateEditBtn();
}

// Map file extensions to Prism.js language identifiers.
// Prism autoloader fetches missing language components from CDN on demand.
const _PRISM_LANG_MAP={
  js:'javascript',mjs:'javascript',jsx:'jsx',ts:'typescript',tsx:'tsx',
  py:'python',pyw:'python',pyi:'python',
  rb:'ruby',go:'go',rs:'rust',java:'java',kt:'kotlin',kts:'kotlin',
  c:'c',h:'c',cpp:'cpp',cxx:'cpp',hpp:'cpp',cc:'cpp',
  cs:'csharp',swift:'swift',scala:'scala',
  php:'php',pl:'perl',pm:'perl',r:'r',lua:'lua',
  sh:'bash',bash:'bash',zsh:'bash',fish:'bash',
  ps1:'powershell',psm1:'powershell',
  sql:'sql',graphql:'graphql',
  json:'json',yaml:'yaml',yml:'yaml',toml:'toml',xml:'xml',
  html:'markup',htm:'markup',svg:'markup',vue:'markup',
  css:'css',scss:'scss',sass:'sass',less:'less',
  md:'markdown',markdown:'markdown',
  dockerfile:'docker',makefile:'makefile',cmake:'cmake',
  ini:'ini',cfg:'ini',conf:'ini',properties:'properties',
  diff:'diff',patch:'diff',
  txt:'',log:'',csv:'',tsv:'',
};
const _PRISM_BASENAME_LANG_MAP={
  'dockerfile':'docker','makefile':'makefile','gnumakefile':'makefile',
  'cmakelists.txt':'cmake',
  '.gitignore':'ignore','.dockerignore':'ignore',
};
function _prismLanguageForPath(path){
  const base=String(path||'').split(/[\\/]/).pop().toLowerCase();
  if(base.startsWith('dockerfile.')) return 'docker';
  if(_PRISM_BASENAME_LANG_MAP[base]!==undefined) return _PRISM_BASENAME_LANG_MAP[base];
  const ext=fileExt(path).replace(/^\./,'');
  return _PRISM_LANG_MAP[ext]!==undefined?_PRISM_LANG_MAP[ext]:'plaintext';
}

async function openFile(path, opts={}){
  if(!S.session)return;
  const ext=fileExt(path);
  const bustCache=!!(opts&&opts.bustCache);
  const forceRichMarkdown=!!(opts&&opts.forceRichMarkdown);
  const cacheBust=bustCache?`&_=${Date.now()}`:'';

  // Binary/download-only formats: trigger browser download, don't preview
  if(DOWNLOAD_EXTS.has(ext)){
    downloadFile(path);
    return;
  }

  _previewServerEditable = null;
  _previewSaveRoute = '/api/file/save';
  _previewOfficeFormat = '';
  _previewPreviewKind = '';

  $('previewPathText').textContent=path;
  $('previewArea').classList.add('visible');
  $('fileTree').style.display='none';

  _previewCurrentPath = path;
  renderFileBreadcrumb(path);
  if(IMAGE_EXTS.has(ext)){
    // Image: load via raw endpoint, show as <img>
    showPreview('image');
    const url=_workspaceRouteForPath(path, 'raw') + cacheBust;
    $('previewImg').alt=path;
    $('previewImg').src=url;
    $('previewImg').onerror=()=>setStatus(t('image_load_failed'));
  } else if(AUDIO_EXTS.has(ext)||VIDEO_EXTS.has(ext)){
    const mode=VIDEO_EXTS.has(ext)?'video':'audio';
    showPreview(mode);
    const url=_workspaceRouteForPath(path, 'raw', {inline:true}) + cacheBust;
    const wrap=$('previewMediaWrap');
    if(wrap){
      wrap.innerHTML=(typeof _mediaPlayerHtml==='function')
        ? _mediaPlayerHtml(mode,url,path.split('/').pop()||path)
        : `<${mode} src="${url.replace(/"/g,'%22')}" controls preload="metadata"></${mode}>`;
      if(typeof _applyMediaPlaybackPreferences==='function') _applyMediaPlaybackPreferences(wrap);
    }
  } else if(PDF_EXTS.has(ext)){
    showPreview('pdf');
    const url=_workspaceRouteForPath(path, 'raw', {inline:true}) + cacheBust;
    const frame=$('previewPdfFrame');
    if(frame){
      frame.src=''; // clear first to avoid stale content
      frame.src=url;
      frame.title=`PDF preview: ${path.split('/').pop()||path}`;
    }
  } else if(MD_EXTS.has(ext)){
    // Markdown: fetch text, render with renderMd, display as formatted HTML
    try{
      // #3378 review (Codex): only reuse cached raw content when it actually
      // belongs to the requested path. `path===_previewCurrentPath` is tautological
      // here (_previewCurrentPath was just assigned above), so guard on the
      // dedicated _previewRawContentPath instead — otherwise a force-render after a
      // file switch could re-render the previous file's cached content.
      const data=forceRichMarkdown&&path===_previewRawContentPath&&_previewRawContent
        ? {content:_previewRawContent}
        : await api(_workspaceRouteForPath(path, 'read'));
      _previewRawContent = data.content;
      _previewRawContentPath = path;
      if(!forceRichMarkdown && shouldRenderMarkdownPreviewAsPlainText(data.content)){
        showPreview('code');
        $('previewCode').textContent=data.content;
        setLargeMarkdownForceRenderVisible(true);
        setStatus(largeMarkdownPlainTextStatus(data.content));
        return;
      }
      renderMarkdownPreviewContent(data);
    }catch(e){setStatus(t('file_open_failed'));}
  } else if(HTML_EXTS.has(ext)){
    // HTML: render in sandboxed iframe via raw endpoint.
    // SECURITY TRADEOFF: We use sandbox="allow-scripts" which lets inline JS run
    // but prevents access to the parent frame (origin isolation). This is a
    // deliberate choice — the user is previewing their own workspace files, so
    // blocking scripts entirely would break most HTML documents. The sandbox
    // still prevents the preview from navigating the parent, accessing cookies,
    // or reading other origin data. If a stricter mode is needed, remove
    // allow-scripts (or add sandbox="") to disable all JS execution.
    showPreview('html');
    const url=_workspaceRouteForPath(path, 'raw', {inline:true}) + cacheBust;
    const iframe=$('previewHtmlIframe');
    if(iframe){
      iframe.src=''; // clear first to avoid stale content
      iframe.src=url;
    }
  } else if(ext==='.csv'){
    try{
      const data=await api(_workspaceRouteForPath(path, 'read'));
      if(data.binary){
        downloadFile(path);
        return;
      }
      if(renderCsvPreviewContent(path, data.content)) return;
      renderCodePreviewContent(path, data.content);
    }catch(e){
      downloadFile(path);
    }
  } else {
    // Plain code / text -- but fall back to download if server signals binary
    try{
      const data=await api(_workspaceRouteForPath(path, 'read'));
      if(data.binary){
        // Server flagged this as binary content
        downloadFile(path);
        return;
      }
      if(data.preview_kind==='office'){
        _previewRawContent = data.content || '';
        _previewRawContentPath = path;
        _previewServerEditable = typeof data.editable === 'boolean' ? data.editable : null;
        _previewPreviewKind = data.preview_kind || '';
        _previewOfficeFormat = data.office_format || '';
        _previewSaveRoute = data.preview_kind==='office' ? '/api/file/office-save' : '/api/file/save';
      }
      renderCodePreviewContent(path, data.content);
  }catch(e){
      const grant = _workspaceEscapeGrantForPath(path);
      if(grant && e && e.status===403){
        _clearWorkspaceEscapeGrant(grant.path);
        showToast(t('external_link_grant_expired') || t('file_open_failed'), 5000, 'error');
        return;
      }
      // If it's a 400/too-large error, offer download instead
      downloadFile(path);
    }
  }
}

function downloadFile(path){
  if(!S.session)return;
  // Trigger browser download via the raw file endpoint with content-disposition attachment
  const url=_workspaceRouteForPath(path, 'raw', {download:true});
  const filename=path.split('/').pop();
  const a=document.createElement('a');
  a.href=url;a.download=filename;
  document.body.appendChild(a);a.click();
  setTimeout(()=>document.body.removeChild(a),100);
  showToast(t('downloading',filename),2000);
}


// ── Render breadcrumb for file preview mode ──────────────────────────────────
function renderFileBreadcrumb(filePath) {
  const bar = $('breadcrumbBar');
  if (!bar) return;
  bar.style.display = 'flex';
  const upBtn = $('btnUpDir');
  if (upBtn) upBtn.style.display = '';

  bar.innerHTML = '';
  // Root
  const root = document.createElement('span');
  root.className = 'breadcrumb-seg breadcrumb-link';
  root.textContent = '~';
  root.onclick = () => { loadDir('.'); };
  bar.appendChild(root);

  const parts = filePath.split('/');
  let accumulated = '';
  for (let i = 0; i < parts.length; i++) {
    const sep = document.createElement('span');
    sep.className = 'breadcrumb-sep';
    sep.textContent = '/';
    bar.appendChild(sep);

    accumulated += (accumulated ? '/' : '') + parts[i];
    const seg = document.createElement('span');
    seg.textContent = parts[i];
    if (i < parts.length - 1) {
      seg.className = 'breadcrumb-seg breadcrumb-link';
      const target = accumulated;
      seg.onclick = () => { loadDir(target); };
    } else {
      seg.className = 'breadcrumb-seg breadcrumb-current';
    }
    bar.appendChild(seg);
  }
}

function openInBrowser(){
  if(!_previewCurrentPath||!S.session) return;
  const url=_workspaceRouteForPath(_previewCurrentPath, 'raw', {inline:true});
  window.open(url,'_blank','noopener');
}
// openInBrowser keeps the helper-based raw path, which expands to an explicit &inline=1 URL.

async function copyPreviewRelativePath(){
  if(!_previewCurrentPath) return;
  const btn=$('btnCopyPreviewRelPath');
  if(btn&&btn.disabled) return;
  if(btn) btn.disabled=true;
  try{
    const rel=_normalizeWorkspaceRelPath(_previewCurrentPath)||_previewCurrentPath;
    if(typeof _copyTextWithFallback==='function'){
      await _copyTextWithFallback(rel,t('path_copied'),t('path_copy_failed'));
      return;
    }
    try{
      await navigator.clipboard.writeText(rel);
      showToast(t('path_copied'));
    }catch(clipErr){
      const ta=document.createElement('textarea');
      ta.value=rel;
      ta.style.cssText='position:fixed;left:-9999px;top:-9999px;';
      document.body.appendChild(ta);
      ta.select();
      let copied=false;
      try{copied=document.execCommand('copy');}catch(_){}
      ta.remove();
      if(copied) showToast(t('path_copied'));
      else showToast(t('path_copy_failed')+(clipErr&&clipErr.message?clipErr.message:String(clipErr)));
    }
  }catch(err){
    showToast(t('path_copy_failed')+(err.message||err));
  }finally{
    if(btn) btn.disabled=false;
  }
}

// ── Workspace upload ──────────────────────────────────────────────────
function triggerWorkspaceUpload() {
  if(_workspacePathIsReadOnly(S.currentDir || '.')){
    showToast(t('external_link_read_only'), 2000);
    return;
  }
  const input = $('workspaceFileInput');
  if (!input) return;
  input.value = '';
  input.onchange = async () => {
    const files = input.files;
    if (!files || !files.length) return;
    for (const file of files) {
      await uploadToWorkspace(file, S.currentDir || '.');
    }
    if (S.session) loadDir(S.currentDir);
  };
  input.click();
}

async function uploadToWorkspace(file, dir) {
  if (!S.session) return;
  if(_workspacePathIsReadOnly(dir || '.')){
    showToast(t('external_link_read_only'), 2000);
    return;
  }
  const formData = new FormData();
  formData.append('session_id', S.session.session_id);
  formData.append('path', dir || '.');
  formData.append('file', file, file.name);
  try {
    showToast(t('uploading') || 'Uploading\u2026', 2000);
    const data = await api('/api/workspace/upload', {
      method: 'POST',
      body: formData,
      headers: {},
      timeoutMs: 120000,
    });
    if (data && data.error) {
      showToast(data.error, 5000, 'error');
    } else if (data && (data.extract_error || (Array.isArray(data.files) && data.files.some(function(f){return f && f.extract_error;})))) {
      // Archive was rejected (zip-slip / zip-bomb / corrupt / too-many-members):
      // the file uploaded but extraction failed. Surface it as an error instead
      // of a misleading "Uploaded" success toast.
      var msg = data.extract_error
        || (data.files.find(function(f){return f && f.extract_error;}) || {}).extract_error
        || 'Archive extraction failed';
      showToast(msg, 5000, 'error');
    } else {
      showToast(t('uploaded') || ('Uploaded ' + (data.filename || file.name)), 2000);
    }
  } catch (e) {
    showToast(t('upload_failed') || ('Upload failed: ' + e.message), 5000, 'error');
  }
}

function _isOsFilesDrag(e) {
  return !!(e.dataTransfer && e.dataTransfer.types && e.dataTransfer.types.includes('Files'));
}

function _joinWorkspacePath(base, rel) {
  const b = base || '.';
  const r = (rel || '').replace(/^\/+|\/+$/g, '');
  if (!r) return b;
  return b === '.' ? r : `${b}/${r}`;
}

function _targetDirForRelDir(destDir, relDir) {
  const dirPart = (relDir || '').replace(/\/+$/, '');
  if (!dirPart) return destDir || '.';
  return _joinWorkspacePath(destDir, dirPart);
}

async function _readAllDirectoryEntries(reader) {
  const entries = [];
  while (true) {
    const batch = await new Promise((resolve, reject) => {
      reader.readEntries(resolve, reject);
    });
    if (!batch.length) break;
    entries.push(...batch);
  }
  return entries;
}

async function _collectFilesFromEntry(entry, relPrefix) {
  if (entry.isFile) {
    const file = await new Promise((resolve, reject) => {
      entry.file(resolve, reject);
    });
    return [{ file, relDir: relPrefix || '' }];
  }
  if (!entry.isDirectory) return [];
  const reader = entry.createReader();
  const children = await _readAllDirectoryEntries(reader);
  const dirPrefix = `${relPrefix || ''}${entry.name}/`;
  let out = [];
  for (const child of children) {
    out = out.concat(await _collectFilesFromEntry(child, dirPrefix));
  }
  return out;
}

async function _collectOsDropUploads(dataTransfer) {
  const out = [];
  const items = dataTransfer.items ? [...dataTransfer.items] : [];
  if (items.length && typeof items[0].webkitGetAsEntry === 'function') {
    for (const item of items) {
      if (item.kind !== 'file') continue;
      const entry = item.webkitGetAsEntry();
      if (!entry) continue;
      out.push(...await _collectFilesFromEntry(entry, ''));
    }
    if (out.length) return out;
  }
  for (const file of dataTransfer.files) {
    out.push({ file, relDir: '' });
  }
  return out;
}

async function uploadOsDropToWorkspace(dataTransfer, destDir) {
  if (!S.session || !dataTransfer) return;
  if(_workspacePathIsReadOnly(destDir || '.')){
    showToast(t('external_link_read_only'), 2000);
    return;
  }
  const uploads = await _collectOsDropUploads(dataTransfer);
  for (const { file, relDir } of uploads) {
    await uploadToWorkspace(file, _targetDirForRelDir(destDir, relDir));
  }
  if (S.session) await loadDir(S.currentDir);
}

function _clearWorkspaceOsUploadDragOver() {
  document.querySelectorAll('.file-item.drag-over-upload,.breadcrumb-seg.drag-over-upload').forEach((el) => {
    el.classList.remove('drag-over-upload');
  });
}

function _bindWorkspaceOsUploadDropTarget(el, destDir) {
  // Use addEventListener (not on-property assignment) so these OS-upload
  // handlers COMPOSE with the workspace tree-MOVE handlers bound by
  // _bindWorkspaceMoveDropTarget() on the same element. A property assignment
  // for the drop handler here would overwrite the move handler, and a
  // workspace-file drag would fall through to the document drop (inserting
  // @path into the composer) instead of moving the file. Each handler gates on
  // its own drag type (_isOsFilesDrag vs _isWorkspaceTreeMoveDrag), so only the
  // matching one acts.
  el.addEventListener('dragenter', (e) => {
    if (!_isOsFilesDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    el.classList.add('drag-over-upload');
  });
  el.addEventListener('dragover', (e) => {
    if (!_isOsFilesDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'copy';
    el.classList.add('drag-over-upload');
  });
  el.addEventListener('dragleave', (e) => {
    if (el.contains(e.relatedTarget)) return;
    el.classList.remove('drag-over-upload');
  });
  el.addEventListener('drop', async (e) => {
    if (!_isOsFilesDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    el.classList.remove('drag-over-upload');
    if(_workspacePathIsReadOnly(destDir || '.')){
      showToast(t('external_link_read_only'), 2000);
      return;
    }
    await uploadOsDropToWorkspace(e.dataTransfer, destDir);
  });
}

// Drag-and-drop files onto workspace file tree
if (typeof document !== 'undefined') {
  const _wsUploadInit = () => {
    const tree = $('fileTree');
    if (!tree) return;
    tree.addEventListener('dragenter', (e) => {
      if (e.dataTransfer && e.dataTransfer.types && e.dataTransfer.types.includes('Files')) {
        e.preventDefault();
        e.stopPropagation();
      }
    });
    tree.addEventListener('dragover', (e) => {
      if (e.dataTransfer && e.dataTransfer.types && e.dataTransfer.types.includes('Files')) {
        e.preventDefault();
        e.stopPropagation();
        if (e.target.closest('.file-item[data-ws-type="dir"],.file-item[data-ws-is-dir="true"],.breadcrumb-seg')) return;
        e.dataTransfer.dropEffect = 'copy';
        tree.classList.add('drag-over-upload');
      }
    });
    tree.addEventListener('dragleave', (e) => {
      if (tree.contains(e.relatedTarget)) return;
      tree.classList.remove('drag-over-upload');
    });
    tree.addEventListener('drop', async (e) => {
      tree.classList.remove('drag-over-upload');
      if (!e.dataTransfer || !e.dataTransfer.types || !e.dataTransfer.types.includes('Files')) return;
      if (e.target.closest('.file-item[data-ws-type="dir"],.file-item[data-ws-is-dir="true"],.breadcrumb-seg')) return;
      e.preventDefault();
      e.stopPropagation();
      if(_workspacePathIsReadOnly(S.currentDir || '.')){
        showToast(t('external_link_read_only'), 2000);
        return;
      }
      await uploadOsDropToWorkspace(e.dataTransfer, S.currentDir || '.');
    });
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _wsUploadInit, {once: true});
  } else {
    _wsUploadInit();
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Project workspace binder
//
// The Project three-dot menu's "Workspace Folder" item used to drop a bare
// text input next to the chip, which meant typing an absolute path from
// memory. This replaces it with a project-scoped view inside the right
// workspace panel: registered Spaces for the common case, plus a live folder
// browser so a directory created seconds ago shows up without any re-index —
// every listing is fetched fresh from /api/workspaces/suggest, never from the
// _workspaceList cache the composer dropdown reads.
//
// It reuses the Spaces panel's .ws-row markup and the dropdown's .ws-search-*
// controls; only the container chrome is new. While it is open the right panel
// carries .project-bind-mode, and CSS (not JS) hides the Files/Artifacts/Todos
// body, so renderFileTree() and syncWorkspacePanelUI() can keep running
// underneath without fighting over `hidden` attributes.
// ─────────────────────────────────────────────────────────────────────────────

let _projectBindTarget = null;   // {project_id, name, workspace_path}
let _projectBindSpaces = [];     // fresh /api/workspaces rows
let _projectBindRoots = [];      // trusted roots (empty-prefix suggest)
let _projectBindDir = '';        // directory currently being browsed
let _projectBindChildren = [];   // child directories of _projectBindDir
let _projectBindQuery = '';
let _projectBindHistory = []; // folders visited in this session, for the Back button
let _projectBindPathMode = false; // query is a path, so it drives suggest directly
let _projectBindLoading = false;
let _projectBindSearchTimer = null;
let _projectBindLastAnimatedKey = null; // view identity, so rows animate on navigation, not on keystrokes

function _projectBindStripSlash(p){
  return String(p || '').replace(/\/+$/, '') || String(p || '');
}

function _projectBindParent(p){
  const clean = _projectBindStripSlash(p);
  const cut = clean.lastIndexOf('/');
  if (cut > 0) return clean.slice(0, cut);
  if (cut === 0) return '/';
  return '';
}

function _projectBindLeaf(p){
  const clean = _projectBindStripSlash(p);
  const cut = clean.lastIndexOf('/');
  return cut >= 0 ? clean.slice(cut + 1) || clean : clean;
}

function _projectBindIsPathQuery(q){
  const s = String(q || '').trim();
  return s.startsWith('/') || s.startsWith('~');
}

async function openProjectWorkspaceBinder(proj){
  if (!proj || !proj.project_id) return;
  const panel = document.querySelector('.rightpanel');
  const view = $('projectBindView');
  if (!panel || !view) return;
  _projectBindTarget = {
    project_id: proj.project_id,
    name: proj.name || 'Project',
    workspace_path: proj.workspace_path || '',
  };
  // On a phone the sidebar drawer is stacked above the right panel, so leaving
  // it open would hide the very view the menu item just asked for.
  try{
    if (typeof _isDesktopWidth === 'function' && !_isDesktopWidth() && typeof closeMobileSidebar === 'function') closeMobileSidebar();
  }catch(_){}
  panel.classList.add('project-bind-mode');
  view.hidden = false;
  // openWorkspacePanel('browse') refuses to open with no session and no default
  // workspace; this view is project-scoped, so drive the mode directly.
  try{ _setWorkspacePanelMode('browse'); }catch(_){}
  const title = $('projectBindTitle');
  if (title) title.textContent = _projectBindTarget.name;
  const search = $('projectBindSearch');
  if (search){
    search.value = '';
    search.oninput = _onProjectBindSearchInput;
    search.onkeydown = (e)=>{ if(e.key === 'Escape'){ e.preventDefault(); clearProjectBindSearch(); } };
  }
  _projectBindQuery = '';
  _projectBindPathMode = false;
  _projectBindHistory = [];
  _projectBindDir = '';
  _projectBindLastAnimatedKey = null;
  await refreshProjectWorkspaceBinder();
}

function closeProjectWorkspaceBinder(){
  const panel = document.querySelector('.rightpanel');
  const view = $('projectBindView');
  if (panel) panel.classList.remove('project-bind-mode');
  if (view) view.hidden = true;
  if (_projectBindSearchTimer){ clearTimeout(_projectBindSearchTimer); _projectBindSearchTimer = null; }
  _projectBindTarget = null;
  _projectBindChildren = [];
  _projectBindHistory = [];
  try{ syncWorkspacePanelUI(); }catch(_){}
}

function _projectBindDefaultDir(){
  // Open on the folder that is already bound rather than its parent: the
  // footer then reads "Already bound to this folder" instead of offering to
  // rebind one level up, and `..` is one tap away if the intent was to move.
  const bound = _projectBindTarget && _projectBindTarget.workspace_path;
  if (bound) return _projectBindStripSlash(bound);
  return _projectBindRoots[0] || '';
}

async function refreshProjectWorkspaceBinder(){
  if (!_projectBindTarget) return;
  _projectBindLoading = true;
  _renderProjectBind();
  let spaces = [];
  let roots = [];
  try{
    const data = await api('/api/workspaces');
    spaces = (data && data.workspaces) || [];
  }catch(_){ spaces = []; }
  try{
    const data = await api('/api/workspaces/suggest?prefix=');
    roots = (data && data.suggestions) || [];
  }catch(_){ roots = []; }
  _projectBindSpaces = spaces;
  _projectBindRoots = roots;
  if (!_projectBindDir) _projectBindDir = _projectBindDefaultDir();
  await _loadProjectBindChildren(_projectBindPathMode ? _projectBindQuery : _projectBindDir);
  _projectBindLoading = false;
  _renderProjectBind();
}

// Directory listings always go over the wire so a folder created after the app
// booted is visible immediately.
async function _loadProjectBindChildren(prefix){
  const raw = String(prefix || '').trim();
  if (!raw){ _projectBindChildren = []; return; }
  // A trailing slash makes list_workspace_suggestions() list the directory's
  // children; without one it filters siblings by the trailing segment, which is
  // exactly what a half-typed path query wants.
  const query = _projectBindPathMode ? raw : (_projectBindStripSlash(raw) + '/');
  try{
    const data = await api('/api/workspaces/suggest?limit=200&prefix=' + encodeURIComponent(query));
    const list = (data && data.suggestions) || [];
    if (_projectBindPathMode){
      _projectBindChildren = list;
      return;
    }
    // The endpoint also echoes trusted roots that prefix-match; keep only the
    // direct children of the directory actually being browsed.
    const base = _projectBindStripSlash(raw) + '/';
    _projectBindChildren = list.filter(p => p.startsWith(base) && p.slice(base.length).indexOf('/') < 0);
  }catch(_){ _projectBindChildren = []; }
}

function _onProjectBindSearchInput(e){
  _projectBindQuery = (e && e.target && e.target.value) || '';
  const pathMode = _projectBindIsPathQuery(_projectBindQuery);
  if (_projectBindSearchTimer) clearTimeout(_projectBindSearchTimer);
  if (!pathMode){
    // Plain text filters what is already loaded — no round trip.
    if (_projectBindPathMode){
      _projectBindPathMode = false;
      _projectBindSearchTimer = setTimeout(async ()=>{
        await _loadProjectBindChildren(_projectBindDir);
        _renderProjectBind();
      }, 120);
    }
    _renderProjectBind();
    return;
  }
  _projectBindPathMode = true;
  _projectBindSearchTimer = setTimeout(async ()=>{
    await _loadProjectBindChildren(_projectBindQuery);
    _renderProjectBind();
  }, 180);
}

function clearProjectBindSearch(){
  const search = $('projectBindSearch');
  if (search){ search.value = ''; search.focus(); }
  const wasPathMode = _projectBindPathMode;
  _projectBindQuery = '';
  _projectBindPathMode = false;
  if (wasPathMode){
    _loadProjectBindChildren(_projectBindDir).then(()=>_renderProjectBind());
    return;
  }
  _renderProjectBind();
}

function projectBindGoBack(){
  const previous = _projectBindHistory.pop();
  if (!previous) return;
  _projectBindOpenDir(previous, {replay: true});
}

async function _projectBindOpenDir(dir, opts){
  if (!dir) return;
  // Drilling in records where we came from so Back can retrace it. Going Back
  // must not push, or Back would just toggle between two folders forever.
  const record = !(opts && opts.replay);
  if (record && _projectBindDir && _projectBindStripSlash(dir) !== _projectBindStripSlash(_projectBindDir)){
    _projectBindHistory.push(_projectBindDir);
    if (_projectBindHistory.length > 64) _projectBindHistory.shift();
  }
  _projectBindPathMode = false;
  _projectBindQuery = '';
  const search = $('projectBindSearch');
  if (search) search.value = '';
  _projectBindDir = _projectBindStripSlash(dir);
  _projectBindLoading = true;
  _renderProjectBind();
  await _loadProjectBindChildren(_projectBindDir);
  _projectBindLoading = false;
  _renderProjectBind();
}

async function _bindProjectWorkspacePath(path){
  if (!_projectBindTarget) return;
  const pid = _projectBindTarget.project_id;
  try{
    const res = await api('/api/projects/set_workspace', {
      method: 'POST',
      body: JSON.stringify({ project_id: pid, workspace_path: path || null }),
    });
    if (res && res.project){
      _projectBindTarget.workspace_path = res.project.workspace_path || '';
      showToast(path
        ? ('Workspace bound · ' + (res.sessions_updated || 0) + ' chats updated')
        : 'Workspace cleared');
      // The open chat may be filed under the project just (un)bound, so the
      // workspace panel's indicator is stale until it re-reads the list.
      _projectFolderBindingCache = null;
      if (typeof renderProjectFolderBinding === 'function') renderProjectFolderBinding();
      _renderProjectBind();
      if (typeof renderSessionList === 'function') await renderSessionList();
    }
  }catch(e){
    showToast('Bind failed: ' + ((e && e.message) || e), 5000, 'error');
  }
}

function _projectBindCrumbs(dir){
  // Only offer ancestors that stay inside a trusted root — walking above one
  // just returns an empty listing from the server.
  const clean = _projectBindStripSlash(dir);
  if (!clean) return [];
  const root = _projectBindRoots
    .filter(r => clean === _projectBindStripSlash(r) || clean.startsWith(_projectBindStripSlash(r) + '/'))
    .sort((a, b) => b.length - a.length)[0];
  if (!root) return [{ label: _projectBindLeaf(clean) || clean, path: clean }];
  const rootClean = _projectBindStripSlash(root);
  const crumbs = [{ label: _projectBindLeaf(rootClean) || rootClean, path: rootClean }];
  const rest = clean.slice(rootClean.length).split('/').filter(Boolean);
  let acc = rootClean;
  for (const seg of rest){
    acc = acc + '/' + seg;
    crumbs.push({ label: seg, path: acc });
  }
  return crumbs;
}

function _renderProjectBind(){
  const body = $('projectBindBody');
  const current = $('projectBindCurrent');
  const footer = $('projectBindFooter');
  const clearBtn = $('projectBindSearchClear');
  if (!body || !_projectBindTarget) return;
  if (clearBtn) clearBtn.hidden = !_projectBindQuery;

  const bound = _projectBindTarget.workspace_path || '';
  if (current){
    current.innerHTML = bound
      ? `<div class="project-bind-current-info">
           <div class="project-bind-current-label">Bound folder</div>
           <div class="project-bind-current-path" title="${_escHtml(bound)}">${_escHtml(bound)}</div>
         </div>
         <button type="button" class="project-bind-unbind">Unbind</button>`
      : `<div class="project-bind-current-info">
           <div class="project-bind-current-label">Bound folder</div>
           <div class="project-bind-current-path project-bind-current-none">Not bound — chats use their own workspace</div>
         </div>`;
    const unbind = current.querySelector('.project-bind-unbind');
    if (unbind) unbind.onclick = ()=>_bindProjectWorkspacePath('');
    current.classList.toggle('is-bound', !!bound);
  }

  const q = _projectBindQuery.trim().toLowerCase();
  const filterText = _projectBindPathMode ? '' : q;
  const spaces = _projectBindSpaces.filter(w => !filterText
    || String(w.name || '').toLowerCase().includes(filterText)
    || String(w.path || '').toLowerCase().includes(filterText));
  const children = _projectBindPathMode
    ? _projectBindChildren
    : _projectBindChildren.filter(p => !filterText || _projectBindLeaf(p).toLowerCase().includes(filterText));

  const rows = [];

  if (spaces.length){
    rows.push('<div class="project-bind-section">Spaces</div>');
    for (const w of spaces){
      const isBound = bound && _projectBindStripSlash(w.path) === _projectBindStripSlash(bound);
      // Every Space carries a status dot, not just remote ones: a local bind
      // mount that vanished is just as unusable as a dropped SSHFS mount.
      const online = _projectBindIsOnline(w);
      const dotTitle = online ? 'Online' : 'Offline';
      const dot = `<span class="ws-conn-dot ws-conn-dot-${online ? 'online' : 'offline'}" title="${dotTitle}" aria-hidden="true"></span>`;
      const badge = isBound ? '<span class="project-bind-badge">Bound</span>' : '';
      rows.push(`<div class="ws-row project-bind-row${isBound ? ' active' : ''}${online ? '' : ' is-offline'}" data-bind-path="${_escHtml(w.path)}" role="button" tabindex="0" aria-label="${_escHtml(w.name || _projectBindLeaf(w.path))} — ${dotTitle}">
          <span class="project-bind-icon">${_projectBindSpaceIcon()}</span>
          <div class="ws-row-info">
            <div class="ws-row-name">${dot}${_escHtml(w.name || _projectBindLeaf(w.path))}${badge}</div>
            <div class="ws-row-path">${_escHtml(w.path)}</div>
          </div>
        </div>`);
    }
  }

  const crumbs = _projectBindPathMode ? [] : _projectBindCrumbs(_projectBindDir);
  rows.push('<div class="project-bind-section">' + (_projectBindPathMode ? 'Matching folders' : 'Folders') + '</div>');
  if (crumbs.length){
    const parts = crumbs.map((c, i) =>
      `<button type="button" class="project-bind-crumb${i === crumbs.length - 1 ? ' current' : ''}" data-bind-dir="${_escHtml(c.path)}">${_escHtml(c.label)}</button>`
    ).join('<span class="project-bind-crumb-sep">/</span>');
    const up = _projectBindParent(_projectBindDir);
    const canGoUp = crumbs.length > 1 && up;
    // Back retraces the folders actually visited, which is not the same as ".."
    // -- after jumping to a crumb or drilling in from a Space, the parent is
    // often not where you came from.
    const back = _projectBindHistory.length
      ? `<button type="button" class="project-bind-back-btn" data-bind-back="1" title="Back to ${_escHtml(_projectBindLeaf(_projectBindHistory[_projectBindHistory.length - 1]))}" aria-label="Back to the previous folder">${_projectBindArrowIcon()}<span>Back</span></button>`
      : '';
    rows.push(`<div class="project-bind-nav">${back}<div class="project-bind-crumbs">${canGoUp ? `<button type="button" class="project-bind-crumb up" data-bind-dir="${_escHtml(up)}" title="Parent folder" aria-label="Parent folder">..</button><span class="project-bind-crumb-sep">/</span>` : ''}${parts}</div></div>`);
  }
  if (_projectBindLoading){
    rows.push('<div class="project-bind-empty">Scanning…</div>');
  } else if (!children.length){
    rows.push(`<div class="project-bind-empty">${_projectBindPathMode ? 'No folder matches that path.' : 'No subfolders here.'}</div>`);
  } else {
    for (const p of children){
      const isBound = bound && _projectBindStripSlash(p) === _projectBindStripSlash(bound);
      rows.push(`<div class="ws-row project-bind-row project-bind-dir${isBound ? ' active' : ''}" data-bind-dir="${_escHtml(p)}" role="button" tabindex="0">
          <span class="project-bind-icon">${_projectBindFolderIcon()}</span>
          <div class="ws-row-info">
            <div class="ws-row-name">${_escHtml(_projectBindLeaf(p))}${isBound ? '<span class="project-bind-badge">Bound</span>' : ''}</div>
            <div class="ws-row-path">${_escHtml(p)}</div>
          </div>
          <button type="button" class="project-bind-use" data-bind-path="${_escHtml(p)}" title="Bind this folder" aria-label="Bind this folder">Bind</button>
        </div>`);
    }
  }

  body.innerHTML = rows.join('');

  body.querySelectorAll('[data-bind-back]').forEach(el => {
    el.onclick = (e)=>{ e.stopPropagation(); projectBindGoBack(); };
  });
  body.querySelectorAll('[data-bind-dir]').forEach(el => {
    el.onclick = (e)=>{ e.stopPropagation(); _projectBindOpenDir(el.dataset.bindDir); };
    el.onkeydown = (e)=>{ if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); _projectBindOpenDir(el.dataset.bindDir); } };
  });
  body.querySelectorAll('[data-bind-path]').forEach(el => {
    el.onclick = (e)=>{ e.stopPropagation(); _bindProjectWorkspacePath(el.dataset.bindPath); };
    el.onkeydown = (e)=>{ if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); _bindProjectWorkspacePath(el.dataset.bindPath); } };
  });

  // Animate the row set only when it actually changes -- opening the binder or
  // navigating into a folder -- and never on a keystroke in the search box,
  // where a re-entrance per character would strobe rather than help.
  //
  // Every navigation renders TWICE: once immediately with _projectBindLoading
  // set (the body is just "Scanning…", no folder rows yet), then again once
  // the listing arrives. Keying only on the view meant the first of those
  // burned the key, so the entrance played on rows that were thrown away by
  // the second render's innerHTML rewrite -- and the real rows, the ones you
  // end up looking at, were then skipped by the guard and never animated at
  // all. Skip the loading pass so the entrance lands on the render that
  // actually carries the rows.
  if(window.MotionUI){
    const bindViewKey = (_projectBindPathMode ? 'q' : 'd') + '|' + _projectBindDir;
    if(!_projectBindLoading && bindViewKey !== _projectBindLastAnimatedKey){
      _projectBindLastAnimatedKey = bindViewKey;
      window.MotionUI.enter(body.querySelectorAll('.project-bind-row'), { y: 6, stagger: 0.025 });
    }
    window.MotionUI.lift(body.querySelectorAll('.project-bind-row'), { y: -1, scale: 1.006 });
  }

  // Footer binds the directory you are standing in, so a folder with no
  // subfolders is still selectable after you drill into it.
  if (footer){
    const dir = _projectBindPathMode ? '' : _projectBindDir;
    const alreadyBound = dir && bound && _projectBindStripSlash(dir) === _projectBindStripSlash(bound);
    footer.hidden = !dir;
    if (dir){
      footer.innerHTML = `<button type="button" class="project-bind-primary"${alreadyBound ? ' disabled' : ''}>${alreadyBound ? 'Already bound to this folder' : 'Bind “' + _escHtml(_projectBindLeaf(dir)) + '”'}</button>`;
      const btn = footer.querySelector('.project-bind-primary');
      if (btn && !alreadyBound) btn.onclick = ()=>_bindProjectWorkspacePath(dir);
    }
  }
}

function _projectBindIsOnline(w){
  // The server sends availability for every workspace; mount_status is the
  // older remote-only field, kept as a fallback so a stale cached payload
  // still renders something sensible.
  if (w && typeof w.availability === 'string') return w.availability === 'online';
  if (w && w.kind === 'remote') return w.mount_status === 'connected';
  return true;
}

function _projectBindArrowIcon(){
  return '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>';
}

function _projectBindFolderIcon(){
  return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>';
}

function _projectBindSpaceIcon(){
  return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>';
}

// ─────────────────────────────────────────────────────────────────────────────
// Sidebar Project folder binding indicator
//
// Deliberately separate from renderBoundProjectControl() above. That row binds
// the chat to a WORKSPACES.yaml *registry* project (S.session.bound_project_key,
// which the backend injects into the system prompt); this one reports the
// workspace folder attached to the *sidebar Project* the chat is filed under
// (session.project_id -> project.workspace_path). Two different features that
// both say "project", which is why a chat inside a bound Project still read
// "Project: Unbound" — that row was answering a different question.
//
// It also reports when the chat is not actually working in the bound folder.
// Binding applies to chats created afterwards; one that predates the binding
// keeps its own workspace, and saying "bound to X" while the agent works in Y
// is the confusion worth avoiding.
// ─────────────────────────────────────────────────────────────────────────────

let _projectFolderBindingCache = null;

async function _projectFolderList(){
  // The sidebar owns the canonical list; fall back to the API when the panel
  // renders before the sidebar has populated it.
  if (typeof _allProjects !== 'undefined' && Array.isArray(_allProjects) && _allProjects.length){
    return _allProjects;
  }
  if (_projectFolderBindingCache) return _projectFolderBindingCache;
  try{
    const data = await api('/api/projects');
    _projectFolderBindingCache = (data && data.projects) || [];
  }catch(_){ _projectFolderBindingCache = []; }
  return _projectFolderBindingCache;
}

async function renderProjectFolderBinding(){
  const row = $('projectFolderBindingRow');
  if (!row) return;
  const session = S.session;
  if (!session || !session.project_id){ row.hidden = true; return; }
  const sessionId = session.session_id;
  const projects = await _projectFolderList();
  if (!S.session || S.session.session_id !== sessionId) return; // switched mid-fetch
  const proj = projects.find(p => p && p.project_id === session.project_id);
  if (!proj){ row.hidden = true; return; }

  const dot = $('projectFolderBindingDot');
  const name = $('projectFolderBindingName');
  const path = $('projectFolderBindingPath');
  const useBtn = $('projectFolderBindingUse');
  const bound = proj.workspace_path || '';
  const current = session.workspace || '';
  const strip = p => String(p || '').replace(/\/+$/, '');
  const mismatch = !!bound && strip(bound) !== strip(current);

  row.hidden = false;
  row.classList.toggle('is-bound', !!bound);
  row.classList.toggle('is-mismatch', mismatch);
  if (dot) dot.style.background = proj.color || 'var(--muted)';
  if (name) name.textContent = proj.name || 'Project';
  if (path){
    path.textContent = bound
      ? (mismatch ? 'Bound to ' + bound + ' — this chat is in ' + (current || 'no folder') : bound)
      : 'No workspace folder bound';
    path.title = bound || '';
  }
  if (useBtn){
    useBtn.hidden = !mismatch;
    useBtn.title = mismatch ? 'Switch this chat to ' + bound : '';
  }
}

async function useProjectFolderWorkspace(){
  const session = S.session;
  if (!session || !session.project_id) return;
  const projects = await _projectFolderList();
  const proj = projects.find(p => p && p.project_id === session.project_id);
  if (!proj || !proj.workspace_path) return;
  if (typeof switchToWorkspace === 'function') await switchToWorkspace(proj.workspace_path, proj.name);
  renderProjectFolderBinding();
}
