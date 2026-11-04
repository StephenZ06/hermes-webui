/**
 * Office Integrations: the Business Office control page.
 *
 * Everything shown here comes from /api/office/business/*. The server owns
 * every rule (grants, approvals, connection state), so this page only renders
 * what it is told and sends the owner's choices back.
 */

const FLOOR_NAMES = { email: 'Email', marketing: 'Marketing', operations: 'Operations', documents: 'Documents' };
const FLOOR_ART = { email: 'gmail', marketing: 'marketing', operations: 'operations', documents: 'documents' };
const AGENT_NAMES = { conductor: 'Conductor', email: 'Email agent', marketing: 'Marketing agent', operations: 'Operations agent', documents: 'Documents agent' };
const STATUS_LABELS = {
  planned: 'Planned', not_configured: 'Needs setup', configured: 'Ready to connect', connected: 'Connected',
  degraded: 'Partly connected', unauthorized: 'Sign in again', unavailable: 'Unavailable',
};
const MODE_LABELS = { automatic: 'Automatic', approval: 'Requires approval', disabled: 'Disabled' };
const RISK_LABELS = { read: 'Read', internal_write: 'Internal write', external_write: 'External write', critical: 'Critical' };
const TASK_LABELS = {
  created: 'Created', queued: 'Queued', assigned: 'Assigned', running: 'Running', waiting_dependency: 'Waiting on a task',
  waiting_approval: 'Waiting for approval', completed: 'Completed', failed: 'Failed', cancelled: 'Cancelled',
};
const VAULT_FLAGS = [['can_search', 'Search'], ['can_read', 'Read'], ['can_create', 'Create'], ['can_edit', 'Edit']];
const BUSINESS_KEY = 'hermes-office-business';
const POLL_MS = 4000;

let _ctx = null;
let _data = null;
let _tab = 'floors';
let _filter = '';
let _drawer = null;
let _matrixAgent = '';
let _audit = [];
let _auditFilter = { agent: '', provider: '', outcome: '' };
let _try = {};
let _poll = 0;
let _loading = false;
let _creating = false;
let _reloadWanted = false;
let _error = '';

function selectedBusiness() {
  try { return localStorage.getItem(BUSINESS_KEY) || ''; } catch (_error) { return ''; }
}

function rememberBusiness(id) {
  try { localStorage.setItem(BUSINESS_KEY, id); } catch (_error) { /* per-browser convenience only */ }
}

function host() {
  return document.getElementById('officeIntegrationsContent');
}

function post(path, body) {
  return _ctx.request(`/api/office/business/${path}`, {
    method: 'POST', timeoutToast: false,
    body: JSON.stringify({ business_id: _data ? _data.business.id : '', ...body }),
  });
}

function when(seconds) {
  if (!seconds) return 'Never';
  return new Date(seconds * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
}

async function load() {
  // A change made while a poll is in flight must not be painted over by that
  // older answer: note it and read once more.
  if (_loading) { _reloadWanted = true; return; }
  _loading = true;
  try {
    const id = (_data && _data.business.id) || selectedBusiness();
    const query = id ? `?business_id=${encodeURIComponent(id)}` : '';
    _data = await _ctx.request(`/api/office/business/overview${query}`, { timeoutToast: false });
    _error = '';
    if (_tab === 'activity') await loadAudit();
  } catch (error) {
    if (selectedBusiness() && !_data) rememberBusiness('');
    _error = (error && error.message) || 'The Business Office could not be loaded.';
  } finally {
    _loading = false;
  }
  if (_reloadWanted) { _reloadWanted = false; load(); return; }
  render();
}

async function loadAudit() {
  const params = new URLSearchParams({ business_id: _data.business.id });
  Object.entries(_auditFilter).forEach(([key, value]) => { if (value) params.set(key, value); });
  const data = await _ctx.request(`/api/office/business/audit?${params}`, { timeoutToast: false });
  _audit = data.audit || [];
}

function statusBadge(status) {
  const tone = status === 'connected' ? ' is-connected' : ['degraded', 'unauthorized', 'unavailable'].includes(status) ? ' is-warning' : '';
  return `<span class="office-integration-status${tone}">${_ctx.esc(STATUS_LABELS[status] || status)}</span>`;
}

function providerAction(provider) {
  if (provider.state !== 'adapter') return '';
  const label = provider.status === 'connected' || provider.status === 'degraded' ? 'Manage'
    : provider.auth === 'vault' ? 'Grant folders'
      : provider.status === 'not_configured' ? 'Set up' : provider.status === 'unauthorized' ? 'Sign in' : 'Connect';
  return `<button type="button" class="office-integration-action" data-biz="open" data-provider="${_ctx.esc(provider.id)}">${label}</button>`;
}

function providerRow(provider) {
  const esc = _ctx.esc;
  return `<li class="office-biz-provider${provider.state === 'planned' ? ' is-planned' : ''}">
    <span class="office-biz-provider-text"><strong>${esc(provider.name)}</strong><small>${esc(provider.account || provider.purpose)}</small></span>
    ${statusBadge(provider.status)}${providerAction(provider)}</li>`;
}

function floorSummary(rows) {
  const live = rows.filter(row => row.state === 'adapter');
  const connected = live.filter(row => row.status === 'connected').length;
  const attention = live.filter(row => ['degraded', 'unauthorized', 'unavailable'].includes(row.status)).length;
  const base = live.length ? `${connected} of ${live.length} connected` : `${rows.length} planned`;
  return attention ? `${base}, ${attention} need${attention === 1 ? 's' : ''} attention` : base;
}

function floorsView() {
  const needle = _filter.toLowerCase();
  const cards = _data.floors.map(floor => {
    const all = _data.providers.filter(row => row.floor === floor);
    const rows = all.filter(row => !needle || `${row.name} ${row.purpose} ${row.pricing}`.toLowerCase().includes(needle));
    if (!rows.length) return '';
    const open = _data.tasks.filter(task => all.some(row => task.capability_id.startsWith(`${row.id}.`)) && !['completed', 'failed', 'cancelled'].includes(task.status)).length;
    return `<article class="office-integration-card">
      <div class="office-integration-card-head"><span class="office-integration-provider-icon"><img src="/static/office-integration-${FLOOR_ART[floor]}.png" alt="" aria-hidden="true"></span>
      <span><h2>${FLOOR_NAMES[floor]}</h2><p>${_ctx.esc(floorSummary(all))}${open ? `, ${open} active` : ''}</p></span></div>
      <ul class="office-biz-providers">${rows.map(providerRow).join('')}</ul></article>`;
  }).join('');
  return `<div class="office-biz-filter"><input type="search" class="office-biz-input" data-biz-input="filter" placeholder="Filter providers" aria-label="Filter providers" value="${_ctx.esc(_filter)}"></div>
    <section class="office-integrations-grid">${cards || '<p class="office-biz-empty">No provider matches that filter.</p>'}</section>`;
}

function approvalsView() {
  const esc = _ctx.esc;
  const rows = _data.pending_approvals;
  if (!rows.length) return '<p class="office-biz-empty">Nothing is waiting for your approval.</p>';
  return `<div class="office-biz-list">${rows.map(row => `<article class="office-biz-approval">
    <header><strong>${esc(row.capability_id)}</strong><span>${esc(RISK_LABELS[row.risk] || row.risk)}</span></header>
    <dl><dt>Business</dt><dd>${esc(_data.business.name)}</dd><dt>Agent</dt><dd>${esc(AGENT_NAMES[row.agent_id] || row.agent_id)}</dd>
    <dt>Target</dt><dd>${esc(row.target || 'None')}</dd><dt>Expires</dt><dd>${esc(when(row.expires_at))}</dd></dl>
    <pre class="office-biz-payload">${esc(JSON.stringify(row.payload, null, 2))}</pre>
    <div class="office-biz-actions"><button type="button" class="office-integration-action is-primary" data-biz="approve" data-id="${esc(row.id)}">Approve</button>
    <button type="button" class="office-integration-action" data-biz="reject" data-id="${esc(row.id)}">Reject</button></div></article>`).join('')}</div>`;
}

function auditSelect(key, label, options) {
  const esc = _ctx.esc;
  return `<select class="office-biz-input" data-biz-input="audit-${key}" aria-label="${label}"><option value="">${label}</option>${options.map(([value, text]) => `<option value="${esc(value)}"${_auditFilter[key] === value ? ' selected' : ''}>${esc(text)}</option>`).join('')}</select>`;
}

function activityView() {
  const esc = _ctx.esc;
  const tasks = _data.tasks.slice(0, 20).map(task => `<li><span class="office-biz-provider-text"><strong>${esc(task.goal)}</strong>
    <small>${esc(AGENT_NAMES[task.agent_id] || task.agent_id)}, ${esc(when(task.updated_at))}${task.error ? `, ${esc(task.error)}` : ''}${task.needs_review ? ', needs review' : ''}</small></span>
    <span class="office-integration-status${task.status === 'failed' ? ' is-warning' : task.status === 'completed' ? ' is-connected' : ''}">${esc(TASK_LABELS[task.status] || task.status)}</span>
    ${['queued', 'waiting_dependency', 'waiting_approval'].includes(task.status) ? `<button type="button" class="office-integration-action" data-biz="cancel" data-id="${esc(task.id)}">Cancel</button>` : ''}</li>`).join('');
  const audit = _audit.map(row => `<tr><td>${esc(when(row.ts))}</td><td>${esc(row.actor)}</td><td>${esc(row.capability_id || row.provider || '')}</td><td>${esc(row.target)}</td><td>${esc(row.decision)}</td><td>${esc(row.outcome)}</td></tr>`).join('');
  return `<h2 class="office-biz-heading">Tasks</h2>
    ${tasks ? `<ul class="office-biz-providers office-biz-tasks">${tasks}</ul>` : '<p class="office-biz-empty">No tasks yet for this business.</p>'}
    <h2 class="office-biz-heading">Audit log</h2>
    <div class="office-biz-toolbar-row">
      ${auditSelect('agent', 'All agents', _data.agents.map(id => [id, AGENT_NAMES[id]]))}
      ${auditSelect('provider', 'All providers', _data.providers.filter(row => row.state === 'adapter').map(row => [row.id, row.name]))}
      ${auditSelect('outcome', 'All outcomes', [['ok', 'Succeeded'], ['denied', 'Denied'], ['uncertain', 'Uncertain'], ['failed', 'Failed']])}
    </div>
    ${audit ? `<div class="office-biz-table-wrap"><table class="office-biz-table"><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Target</th><th>Decision</th><th>Outcome</th></tr></thead><tbody>${audit}</tbody></table></div>` : '<p class="office-biz-empty">No matching activity.</p>'}`;
}

function settingsView() {
  const esc = _ctx.esc;
  const business = _data.business;
  const limits = [['max_parallel', 'Tasks at once'], ['max_parallel_per_agent', 'Per agent'], ['max_parallel_per_provider', 'Per provider']];
  const readCaps = _data.providers.flatMap(row => row.capabilities).filter(item => item.risk === 'read' && !item.inputs.some(input => input.required && input.name !== 'query'));
  return `<div class="office-biz-settings">
    <section><h2 class="office-biz-heading">Limits</h2><div class="office-biz-toolbar-row">
      ${limits.map(([key, label]) => `<label class="office-biz-field"><span>${label}</span><input class="office-biz-input" type="number" min="1" max="10" value="${esc(business.settings[key])}" data-biz-input="limit" data-key="${key}"></label>`).join('')}
    </div></section>
    <section><h2 class="office-biz-heading">Emergency stop</h2>
      <p class="office-biz-note">A paused agent starts nothing new. Work already waiting stays in the queue.</p>
      <ul class="office-biz-providers">${[['', 'Whole business', business.paused], ..._data.agents.map(id => [id, AGENT_NAMES[id], business.paused_agents.includes(id)])].map(([id, label, paused]) => `<li><span class="office-biz-provider-text"><strong>${esc(label)}</strong></span>${paused ? '<span class="office-integration-status is-warning">Paused</span>' : ''}
        <button type="button" class="office-integration-action" data-biz="pause" data-agent="${esc(id)}" data-paused="${paused ? '0' : '1'}">${paused ? 'Resume' : 'Pause'}</button></li>`).join('')}</ul></section>
    <section><h2 class="office-biz-heading">Schedules</h2>
      <p class="office-biz-note">Only read actions can run on a schedule.</p>
      ${_data.schedules.length ? `<ul class="office-biz-providers">${_data.schedules.map(row => `<li><span class="office-biz-provider-text"><strong>${esc(row.name)}</strong><small>Every ${esc(row.every_minutes)} minutes, next ${esc(when(row.next_run_at))}</small></span><button type="button" class="office-integration-action" data-biz="schedule-delete" data-id="${esc(row.id)}">Remove</button></li>`).join('')}</ul>` : ''}
      <form class="office-biz-toolbar-row" data-biz-form="schedule">
        <input class="office-biz-input" name="name" placeholder="Name" aria-label="Schedule name" required>
        <select class="office-biz-input" name="capability_id" aria-label="Action">${readCaps.map(item => `<option value="${esc(item.id)}">${esc(item.id)}</option>`).join('')}</select>
        <input class="office-biz-input" name="query" placeholder="Search text, if needed" aria-label="Search text">
        <input class="office-biz-input" name="every_minutes" type="number" min="5" max="10080" value="60" aria-label="Minutes between runs">
        <button type="submit" class="office-integration-action">Add schedule</button></form></section>
    <section><h2 class="office-biz-heading">Secrets</h2><p class="office-biz-note">${_data.key_source === 'env' ? 'Tokens are encrypted with a key from the server environment.' : 'Tokens are encrypted with a key file in the WebUI state folder. Set HERMES_BUSINESS_OFFICE_KEY to keep the key apart from the data.'}</p></section>
  </div>`;
}

function credentialForm(provider) {
  const esc = _ctx.esc;
  const app = _data.oauth_apps[provider.oauth_app];
  return `<section class="office-biz-section"><h3>${esc(app.label)} app</h3>
    <p class="office-biz-note">Add this exact redirect address to your app, then paste its client ID and secret. The secret is stored encrypted and never shown again.</p>
    <div class="office-biz-copy"><code>${esc(_data.redirect_uri)}</code><button type="button" class="office-integration-action" data-biz="copy" data-value="${esc(_data.redirect_uri)}">Copy</button></div>
    ${provider.oauth_app === 'google' ? '<p class="office-biz-note">While the Google app is in Testing, Google ends the sign-in after 7 days. Google needs https, or localhost, for this address.</p>' : ''}
    <a class="office-biz-link" href="${esc(app.console_url)}" target="_blank" rel="noopener noreferrer">Open ${esc(app.label)} console</a>
    <form class="office-biz-form" data-biz-form="app" data-app="${esc(provider.oauth_app)}">
      <label class="office-biz-field"><span>Client ID</span><input class="office-biz-input" name="client_id" autocomplete="off" required></label>
      <label class="office-biz-field"><span>Client secret</span><input class="office-biz-input" name="client_secret" type="password" autocomplete="new-password" required></label>
      <button type="submit" class="office-integration-action">${app.configured ? 'Replace app credentials' : 'Save app credentials'}</button></form></section>`;
}

function connectionSection(provider) {
  const esc = _ctx.esc;
  const signedIn = ['connected', 'degraded', 'unauthorized', 'unavailable'].includes(provider.status);
  const details = signedIn ? `<dl><dt>Account</dt><dd>${esc(provider.account || 'Unknown')}</dd><dt>Last sync</dt><dd>${esc(when(provider.last_sync_at))}</dd>
    <dt>Permissions</dt><dd>${esc(provider.scopes.map(scope => scope.split('/').pop()).join(', ') || 'None')}</dd>${provider.last_error ? `<dt>Problem</dt><dd>${esc(provider.last_error)}</dd>` : ''}</dl>` : '';
  return `<section class="office-biz-section"><h3>Connection</h3>${details}
    <div class="office-biz-actions">
      ${provider.app_configured ? `<button type="button" class="office-integration-action is-primary" data-biz="connect" data-provider="${esc(provider.id)}">${signedIn ? 'Sign in again' : 'Sign in'}</button>` : ''}
      ${signedIn ? `<button type="button" class="office-integration-action" data-biz="disconnect" data-provider="${esc(provider.id)}">Disconnect</button>` : ''}
    </div>${_data.oauth_failure ? `<p class="office-biz-note is-error">${esc(_data.oauth_failure)}</p>` : ''}</section>`;
}

function vaultSection() {
  const esc = _ctx.esc;
  const vault = _data.vault;
  if (!vault.connected) return '<section class="office-biz-section"><h3>Folders</h3><p class="office-biz-note">Connect your Obsidian vault on the Notes page first.</p></section>';
  const granted = new Set(vault.grants.filter(grant => grant.current).map(grant => grant.folder));
  const agent = matrixAgent();
  const grants = vault.grants.map(grant => {
    const flags = grant.agents[agent] || {};
    return `<li class="office-biz-grant${grant.current ? '' : ' is-stale'}"><div class="office-biz-grant-head"><strong>${esc(grant.folder)}</strong><button type="button" class="office-integration-action" data-biz="grant-remove" data-id="${esc(grant.id)}">Remove</button></div>
      ${grant.current ? `<div class="office-biz-flags">${VAULT_FLAGS.map(([key, label]) => `<label><input type="checkbox" data-biz-input="grant-flag" data-id="${esc(grant.id)}" data-key="${key}"${flags[key] ? ' checked' : ''}>${label}</label>`).join('')}</div>` : `<small>Granted on another vault (${esc(grant.vault)}). It gives no access here.</small>`}</li>`;
  }).join('');
  return `<section class="office-biz-section"><h3>Folders for ${esc(_data.business.name)}</h3>
    <p class="office-biz-note">These apply to this business only. Tick what ${esc(AGENT_NAMES[agent])} may do in each folder. A note outside these folders stays out of reach, even if linked.</p>
    ${agentPicker()}
    ${grants ? `<ul class="office-biz-grants">${grants}</ul>` : '<p class="office-biz-empty">No folders granted yet.</p>'}
    <form class="office-biz-toolbar-row" data-biz-form="grant"><select class="office-biz-input" name="folder" aria-label="Vault folder">${vault.folders.filter(folder => !granted.has(folder)).map(folder => `<option value="${esc(folder)}">${esc(folder)}</option>`).join('')}</select>
    <button type="submit" class="office-integration-action">Grant folder</button></form></section>`;
}

function matrixAgent() {
  return _matrixAgent || (_drawer && (_data.providers.find(row => row.id === _drawer) || {}).floor) || 'conductor';
}

function agentPicker() {
  const esc = _ctx.esc;
  const current = matrixAgent();
  return `<label class="office-biz-field"><span>Agent</span><select class="office-biz-input" data-biz-input="matrix-agent">${_data.agents.map(id => `<option value="${esc(id)}"${id === current ? ' selected' : ''}>${esc(AGENT_NAMES[id])}</option>`).join('')}</select></label>`;
}

function tryForm(item) {
  const esc = _ctx.esc;
  const result = _try[item.id];
  const inputs = item.inputs.map(input => `<label class="office-biz-field"><span>${esc(input.name)}${input.required ? '' : ' (optional)'}</span>${input.name === 'body' || input.name === 'replace' || input.name === 'find'
    ? `<textarea class="office-biz-input" name="${esc(input.name)}" rows="3"${input.required ? ' required' : ''}></textarea>`
    : `<input class="office-biz-input" name="${esc(input.name)}" type="${input.kind === 'integer' ? 'number' : 'text'}"${input.required ? ' required' : ''}>`}</label>`).join('');
  return `<details class="office-biz-try"${result ? ' open' : ''}><summary>Run as ${esc(AGENT_NAMES[matrixAgent()])}</summary>
    <form class="office-biz-form" data-biz-form="try" data-capability="${esc(item.id)}">${inputs}<button type="submit" class="office-integration-action">Run</button></form>
    ${result ? `<pre class="office-biz-payload">${esc(result)}</pre>` : ''}</details>`;
}

function matrixSection(provider) {
  const esc = _ctx.esc;
  const agent = matrixAgent();
  const rows = provider.capabilities.map(item => `<li class="office-biz-capability"><div class="office-biz-capability-row"><span class="office-biz-provider-text"><strong>${esc(item.label)}</strong><small>${esc(item.description)} ${esc(RISK_LABELS[item.risk])}.</small></span>
    <select class="office-biz-input" aria-label="${esc(item.label)} for ${esc(AGENT_NAMES[agent])}" data-biz-input="mode" data-capability="${esc(item.id)}">${item.allowed_modes.map(mode => `<option value="${mode}"${item.modes[agent] === mode ? ' selected' : ''}>${MODE_LABELS[mode]}</option>`).join('')}</select></div>${tryForm(item)}</li>`).join('');
  return `<section class="office-biz-section"><h3>What agents may do</h3>${provider.auth === 'vault' ? '' : agentPicker()}<ul class="office-biz-capabilities">${rows}</ul></section>`;
}

function drawerView() {
  const provider = _drawer && _data.providers.find(row => row.id === _drawer);
  if (!provider) return '';
  const esc = _ctx.esc;
  return `<div class="office-biz-scrim" data-biz="close"></div><aside class="office-biz-drawer" role="dialog" aria-modal="true" aria-label="${esc(provider.name)} connection">
    <header><span><h2>${esc(provider.name)}</h2><p>${esc(provider.pricing)}</p></span>${statusBadge(provider.status)}
    <button type="button" class="office-biz-close" data-biz="close" aria-label="Close">${_ctx.icon('close', 'Close')}</button></header>
    <div class="office-biz-drawer-body">
    ${provider.auth === 'oauth' ? connectionSection(provider) + credentialForm(provider) : vaultSection()}
    ${matrixSection(provider)}</div></aside>`;
}

function toolbar() {
  const esc = _ctx.esc;
  const business = _data.business;
  const pending = _data.pending_approvals.length;
  const tabs = [['floors', 'Floors'], ['approvals', pending ? `Approvals (${pending})` : 'Approvals'], ['activity', 'Activity'], ['settings', 'Settings']];
  return `<div class="office-biz-toolbar"><label class="office-biz-business"><span>Business</span>
      <select class="office-biz-input" data-biz-input="business">${_data.businesses.map(row => `<option value="${esc(row.id)}"${row.id === business.id ? ' selected' : ''}>${esc(row.name)}</option>`).join('')}</select></label>
    ${_creating ? '<form class="office-biz-inline" data-biz-form="business"><input class="office-biz-input" name="name" maxlength="80" placeholder="Business name" aria-label="Business name" required><button type="submit" class="office-integration-action">Add</button></form>' : ''}
    <button type="button" class="office-integration-action" data-biz="new-business">${_creating ? 'Cancel' : 'New business'}</button>
    ${business.paused ? '<span class="office-integration-status is-warning">Paused</span>' : ''}
    <div class="office-biz-tabs" role="tablist">${tabs.map(([key, label]) => `<button type="button" role="tab" aria-selected="${_tab === key}" class="office-biz-tab${_tab === key ? ' is-active' : ''}" data-biz="tab" data-tab="${key}">${esc(label)}</button>`).join('')}</div></div>`;
}

function render() {
  const root = host();
  if (!root) return;
  if (!_data) {
    const message = _error ? `<p class="office-biz-empty">${_ctx.esc(_error)}</p>` : '<p class="office-biz-empty">Loading…</p>';
    if (root._officeIntegrationsHtml !== message) { root._officeIntegrationsHtml = message; root.innerHTML = message; }
    return;
  }
  const view = _tab === 'approvals' ? approvalsView() : _tab === 'activity' ? activityView() : _tab === 'settings' ? settingsView() : floorsView();
  const html = `${toolbar()}${_error ? `<p class="office-biz-note is-error">${_ctx.esc(_error)}</p>` : ''}<div class="office-biz-view">${view}</div>${drawerView()}`;
  // Polling repaints only real changes, and never under someone typing.
  if (root._officeIntegrationsHtml === html) return;
  const active = document.activeElement;
  if (active && root.contains(active) && active.matches('input,textarea') && active.dataset.bizInput !== 'filter' && !root._bizForce) return;
  const drawerBody = root.querySelector('.office-biz-drawer-body');
  const scroll = drawerBody ? drawerBody.scrollTop : 0;
  const filterFocused = active && active.dataset && active.dataset.bizInput === 'filter';
  const caret = filterFocused ? active.selectionStart : 0;
  root._bizForce = false;
  root._officeIntegrationsHtml = html;
  root.innerHTML = html;
  const nextBody = root.querySelector('.office-biz-drawer-body');
  if (nextBody) nextBody.scrollTop = scroll;
  if (filterFocused) {
    const input = root.querySelector('[data-biz-input="filter"]');
    if (input) { input.focus(); input.setSelectionRange(caret, caret); }
  }
}

function refresh() {
  const root = host();
  if (root) root._bizForce = true;
  return load();
}

async function act(work) {
  try {
    await work();
    await refresh();
  } catch (error) {
    _ctx.toast((error && error.message) || 'That did not work.');
  }
}

async function waitForTask(id, capability) {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    await new Promise(resolve => setTimeout(resolve, 1000));
    const data = await _ctx.request(`/api/office/business/tasks?business_id=${encodeURIComponent(_data.business.id)}`, { timeoutToast: false });
    const task = (data.tasks || []).find(row => row.id === id);
    if (!task) return;
    if (['completed', 'failed', 'cancelled', 'waiting_approval'].includes(task.status)) {
      _try[capability] = task.status === 'completed' ? JSON.stringify(task.result, null, 2)
        : task.status === 'waiting_approval' ? 'Waiting for your approval. Open the Approvals tab.' : task.error || TASK_LABELS[task.status];
      refresh();
      return;
    }
  }
  _try[capability] = 'Still running. See the Activity tab.';
  refresh();
}

function formValues(form) {
  return Object.fromEntries([...new FormData(form).entries()].filter(([, value]) => value !== ''));
}

const FORMS = {
  app: (form, values) => act(async () => {
    await post('oauth/app', { app: form.dataset.app, ...values });
    form.reset();
    _ctx.toast('App credentials saved.');
  }),
  business: (_form, values) => act(async () => {
    const data = await post('businesses/create', { name: values.name });
    rememberBusiness(data.business.id);
    _data.business.id = data.business.id;
    _creating = false;
  }),
  grant: (_form, values) => act(() => post('vault/grants/add', values)),
  schedule: (_form, values) => {
    const { name, capability_id: capabilityId, query, every_minutes: minutes } = values;
    const item = _data.providers.flatMap(row => row.capabilities).find(row => row.id === capabilityId);
    const agent = _data.providers.find(row => row.id === item.provider).floor;
    return act(() => post('schedules/create', { name, capability_id: capabilityId, agent_id: agent, every_minutes: Number(minutes), input: query ? { query } : {} }));
  },
  try: async (form, values) => {
    const capability = form.dataset.capability;
    const item = _data.providers.flatMap(row => row.capabilities).find(row => row.id === capability);
    item.inputs.filter(input => input.kind === 'integer' && values[input.name]).forEach(input => { values[input.name] = Number(values[input.name]); });
    try {
      const data = await post('tasks/create', { agent_id: matrixAgent(), capability_id: capability, input: values, goal: item.label });
      _try[capability] = 'Running…';
      refresh();
      waitForTask(data.task.id, capability);
    } catch (error) {
      _ctx.toast((error && error.message) || 'That did not work.');
    }
  },
};

const ACTIONS = {
  tab: el => { _tab = el.dataset.tab; refresh(); },
  open: el => {
    _drawer = el.dataset.provider; _matrixAgent = ''; _try = {};
    render();
    const close = document.querySelector('.office-biz-close');
    if (close) close.focus();
  },
  close: () => { _drawer = null; render(); },
  copy: el => { navigator.clipboard.writeText(el.dataset.value).then(() => _ctx.toast('Copied.'), () => _ctx.toast('Copy failed. Select the address instead.')); },
  connect: el => act(async () => {
    const data = await post('oauth/start', { provider: el.dataset.provider });
    window.location.assign(data.url);
  }),
  disconnect: el => act(() => post('connections/disconnect', { provider: el.dataset.provider })),
  approve: el => act(() => post('approvals/decide', { approval_id: el.dataset.id, approve: true })),
  reject: el => act(() => post('approvals/decide', { approval_id: el.dataset.id, approve: false })),
  cancel: el => act(() => post('tasks/cancel', { task_id: el.dataset.id })),
  pause: el => act(() => post('pause', { agent_id: el.dataset.agent, paused: el.dataset.paused === '1' })),
  'grant-remove': el => act(() => post('vault/grants/remove', { grant_id: el.dataset.id })),
  'schedule-delete': el => act(() => post('schedules/delete', { schedule_id: el.dataset.id })),
  'new-business': () => { _creating = !_creating; refresh(); },
};

const INPUTS = {
  business: el => { rememberBusiness(el.value); _data.business.id = el.value; _drawer = null; _try = {}; refresh(); },
  'matrix-agent': el => { _matrixAgent = el.value; _try = {}; render(); },
  mode: el => act(() => post('capabilities/mode', { agent_id: matrixAgent(), capability_id: el.dataset.capability, mode: el.value })),
  limit: el => act(() => post('settings', { settings: { [el.dataset.key]: Number(el.value) } })),
  'grant-flag': el => {
    const grant = _data.vault.grants.find(row => row.id === el.dataset.id);
    const flags = { ...(grant.agents[matrixAgent()] || {}), [el.dataset.key]: el.checked };
    act(() => post('vault/grants/agent', { grant_id: grant.id, agent_id: matrixAgent(), flags }));
  },
  'audit-agent': el => { _auditFilter.agent = el.value; refresh(); },
  'audit-provider': el => { _auditFilter.provider = el.value; refresh(); },
  'audit-outcome': el => { _auditFilter.outcome = el.value; refresh(); },
};

function bind(root) {
  if (root._bizBound) return;
  root._bizBound = true;
  root.addEventListener('click', event => {
    const el = event.target.closest('[data-biz]');
    if (el && ACTIONS[el.dataset.biz]) ACTIONS[el.dataset.biz](el);
  });
  root.addEventListener('change', event => {
    const el = event.target.closest('[data-biz-input]');
    if (el && el.dataset.bizInput !== 'filter' && INPUTS[el.dataset.bizInput]) INPUTS[el.dataset.bizInput](el);
  });
  root.addEventListener('input', event => {
    if (event.target.dataset.bizInput === 'filter') { _filter = event.target.value; render(); }
  });
  root.addEventListener('submit', event => {
    const form = event.target.closest('[data-biz-form]');
    if (!form) return;
    event.preventDefault();
    FORMS[form.dataset.bizForm](form, formValues(form));
  });
  // On the document: opening the drawer repaints, so focus may be on nothing.
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && _drawer && host()) { _drawer = null; render(); }
  });
}

/** Open the page. ``ctx`` supplies request, esc, icon and toast from the Office. */
export function mountBusinessOffice(ctx) {
  _ctx = ctx;
  const root = host();
  if (!root) return;
  bind(root);
  render();
  load();
  clearInterval(_poll);
  _poll = setInterval(() => {
    if (!host()) { clearInterval(_poll); return; }
    if (!document.hidden) load();
  }, POLL_MS);
}
