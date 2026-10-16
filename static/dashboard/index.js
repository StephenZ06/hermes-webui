/* Dashboard: Personal, Career and Business at a glance.
   Phase 1 shows what the app already knows (Work Hub, schedules, Notes, the
   Jobs pipeline). Game layers (character, milestones, quests) build on it. */
(() => {
  'use strict';
  const TABS = [
    {key: 'personal', label: 'Personal', icon: '<path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z"/><path d="M4 21a8 8 0 0 1 16 0"/>'},
    {key: 'career', label: 'Career', icon: '<path d="M4 8h16v12H4z"/><path d="M9 8V5h6v3M4 13h16"/>'},
    {key: 'business', label: 'Business', icon: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>'},
  ];
  const REFRESH_MS = 30000;
  const state = {tab: readTab(), data: {}, loading: {}, error: {}, timer: 0, mounted: false};

  function readTab() {
    try { const t = localStorage.getItem('hermes-dashboard-tab'); if (TABS.some((x) => x.key === t)) return t; } catch (_) {}
    return 'personal';
  }
  function saveTab(tab) { try { localStorage.setItem('hermes-dashboard-tab', tab); } catch (_) {} }
  const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[c]);
  const svg = (paths, size = 18) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
  function ago(at) {
    if (!at) return '';
    const s = Math.max(0, Date.now() / 1000 - Number(at));
    if (s < 60) return 'just now';
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  }
  const root = () => document.getElementById('dashboardRoot');
  const sidebar = () => document.getElementById('dashboardSidebar');

  async function load(tab, {quiet = false} = {}) {
    if (state.loading[tab]) return;
    state.loading[tab] = true;
    if (!quiet) paint();
    try {
      state.data[tab] = await api(`/api/dashboard/summary?tab=${encodeURIComponent(tab)}`);
      state.error[tab] = null;
    } catch (error) {
      state.error[tab] = (error && error.message) || 'Could not load the dashboard';
    } finally {
      state.loading[tab] = false;
    }
    if (state.mounted) paint();
  }

  // ── pieces ───────────────────────────────────────────────────────────────
  const card = (title, body, {icon = '', action = '', cls = ''} = {}) =>
    `<section class="dash-card ${cls}"><header class="dash-card-head">${icon ? `<span class="dash-card-icon">${svg(icon, 16)}</span>` : ''}<h3>${esc(title)}</h3>${action}</header>${body}</section>`;
  const stat = (label, value, note = '', tone = '') =>
    `<div class="dash-stat${tone ? ' is-' + tone : ''}"><small>${esc(label)}</small><b>${esc(value)}</b>${note ? `<span>${note}</span>` : ''}</div>`;
  const bar = (fraction, tone = '') => `<span class="dash-bar${tone ? ' is-' + tone : ''}"><i style="width:${Math.round(Math.max(0, Math.min(1, fraction)) * 100)}%"></i></span>`;
  const sectionError = (section) => section && section.error ? `<p class="dash-empty">Couldn't read this: ${esc(section.error)}</p>` : '';
  const link = (label, attrs) => `<button type="button" class="dash-link" ${attrs}>${esc(label)}</button>`;
  const STATUS_LABEL = {in_progress: 'In progress', blocked: 'Blocked', todo: 'To do', triage: 'Triage', backlog: 'Backlog'};

  function personal(data) {
    const hub = data.work_hub || {};
    const t = hub.totals || {};
    const stats = hub.error ? '' : `<div class="dash-stats">
      ${stat('Open items', t.open || 0)}
      ${stat('In progress', t.in_progress || 0, t.working ? `<span class="work-hub-spinner" aria-hidden="true"></span> ${t.working} with a chat` : '')}
      ${stat('Done this week', t.done_this_week || 0, '', t.done_this_week ? 'good' : '')}
      ${stat('Blocked', t.blocked || 0, '', t.blocked ? 'bad' : '')}
    </div>`;
    const quests = (hub.quests || []).map((q) => `<button type="button" class="dash-row dash-quest" data-dash-item="${esc(q.id)}" data-project="${esc(q.project_id || '')}" data-board="${esc(q.board_id || '')}">
        <span class="dash-check" data-status="${esc(q.status)}"></span>
        <span class="dash-row-main"><strong>${esc(q.title)}</strong>${q.project ? `<small>${esc(q.project)}</small>` : ''}</span>
        <span class="dash-pill${q.status === 'in_progress' ? ' is-accent' : q.status === 'blocked' ? ' is-bad' : ''}">${q.working ? '<span class="work-hub-spinner" aria-hidden="true"></span> Working' : esc(STATUS_LABEL[q.status] || q.status)}</span>
      </button>`).join('') || '<p class="dash-empty">Nothing open in the Work Hub. Add an item there to see it here.</p>';
    const projects = (hub.projects || []).filter((p) => p.open || p.done).slice(0, 6).map((p) => `<div class="dash-row">
        <span class="dash-row-main"><strong>${esc(p.name)}</strong><small>${plural(p.open, 'open item')}${p.last_activity ? ' · ' + ago(p.last_activity) : ''}</small></span>
        ${bar(p.progress, p.blocked ? 'bad' : '')}
        <span class="dash-pill${p.blocked ? ' is-bad' : p.in_progress ? ' is-accent' : ''}">${p.blocked ? `${p.blocked} blocked` : p.in_progress ? `${p.in_progress} active` : `${Math.round(p.progress * 100)}%`}</span>
      </div>`).join('') || '<p class="dash-empty">No projects with work items yet.</p>';
    const sch = data.schedules || {};
    const failing = (sch.failing || []).map((f) => `<div class="dash-row is-alert"><span class="dash-dot is-bad"></span><span class="dash-row-main"><strong>${esc(f.name)}</strong><small title="${esc(f.error)}">${esc(f.profile)} · ${esc(f.error || 'failed')}</small></span></div>`).join('');
    const upcoming = (sch.upcoming || []).map((u) => `<div class="dash-row"><span class="dash-dot"></span><span class="dash-row-main"><strong>${esc(u.name)}</strong><small>${esc(u.profile)} · next ${esc(String(u.next_run_at || '').replace('T', ' ').slice(0, 16))}</small></span></div>`).join('');
    const schedules = sectionError(sch) || `${sch.failing_count ? `<p class="dash-callout is-bad">${plural(sch.failing_count, 'scheduled job')} failing</p>` : ''}${failing}${upcoming || (failing ? '' : `<p class="dash-empty">${sch.enabled ? 'No upcoming runs.' : 'No scheduled jobs are switched on.'}</p>`)}`;
    const notes = Array.isArray(data.notes) ? (data.notes.map((n) => `<button type="button" class="dash-row" data-dash-note="${esc(n.id)}"><span class="dash-row-main"><strong>${n.pinned ? '📌 ' : ''}${esc(n.title)}</strong><small>${ago(n.updated_at)}</small></span></button>`).join('') || '<p class="dash-empty">No notes yet.</p>') : sectionError(data.notes);
    return `${sectionError(hub)}${stats}
      <div class="dash-grid is-wide-left">
        ${card("Today's quests", quests, {icon: '<path d="m9 11 3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>', action: link('Open Work Hub', 'data-dash-go="notes"')})}
        ${card('Project health', projects, {icon: '<path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 5-6"/>'})}
      </div>
      <div class="dash-grid">
        ${card('Scheduled jobs', schedules, {icon: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', action: link('Open Tasks', 'data-dash-go="tasks"')})}
        ${card('Recent notes', notes, {icon: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>', action: link('Open Notes', 'data-dash-go="notebook"')})}
      </div>`;
  }

  function career(data) {
    const jobs = data.jobs || {};
    if (jobs.error) return sectionError(jobs);
    const week = jobs.this_week || {};
    const funnel = jobs.funnel || [];
    const top = Math.max(1, ...funnel.map((f) => f.count || 0));
    const funnelRows = funnel.map((f) => `<div class="dash-row"><span class="dash-row-main"><strong>${esc(f.label)}</strong></span>${bar((f.count || 0) / top)}<span class="dash-num">${f.count || 0}</span></div>`).join('');
    const weekRows = [['found', 'Scout finds'], ['tailored', 'Resumes tailored'], ['applied', 'Applications sent'], ['interview', 'Interviews'], ['rejected', 'Rejections']]
      .map(([k, label]) => `<div class="dash-row"><span class="dash-row-main"><strong>${label}</strong></span><span class="dash-num">${week[k] || 0}</span></div>`).join('');
    return `<div class="dash-stats">
        ${stat('Jobs tracked', jobs.total_jobs || 0)}
        ${stat('Active work', jobs.active_work || 0)}
        ${stat('Needs attention', jobs.needs_attention || 0, '', jobs.needs_attention ? 'bad' : '')}
        ${stat('Applied this week', week.applied || 0, '', week.applied ? 'good' : '')}
      </div>
      <div class="dash-grid">
        ${card('Your character', `<div class="dash-teaser"><span class="dash-teaser-art" aria-hidden="true">🧙</span><p>Your pixel character, levels and skill tree arrive in the next phase, earning XP from the skills on your resume and from this pipeline.</p></div>`, {icon: '<path d="M12 2 4 6v6c0 5 3.5 8.5 8 10 4.5-1.5 8-5 8-10V6z"/>', cls: 'is-teaser'})}
        ${card('This week', weekRows, {icon: '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M3 10h18M8 2v4M16 2v4"/>'})}
      </div>
      ${card('Funnel', funnelRows || '<p class="dash-empty">No jobs yet.</p>', {icon: '<path d="M3 4h18l-7 9v6l-4 2v-8z"/>', action: link('Open Jobs', 'data-dash-go="jobs"')})}`;
  }

  function business() {
    return `<div class="dash-empty-state">
      <span class="dash-empty-icon" aria-hidden="true">${svg('<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>', 30)}</span>
      <h3>Connect your sales platform</h3>
      <p>Revenue, goals like "5 sales this week", the road to $10k MRR and milestone achievements arrive in the business phase. They're built on a Lemon Squeezy or Gumroad connection, in test mode first.</p>
    </div>`;
  }

  // ── paint ────────────────────────────────────────────────────────────────
  function paintSidebar() {
    const host = sidebar(); if (!host) return;
    host.innerHTML = `<nav class="dash-side-nav">${TABS.map((t) => `<button type="button" class="side-menu-item${t.key === state.tab ? ' active' : ''}" data-dash-tab="${t.key}"${t.key === state.tab ? ' aria-current="page"' : ''}>${svg(t.icon)}<span class="side-menu-label">${t.label}</span></button>`).join('')}</nav>`;
  }
  function paint() {
    paintSidebar();
    const host = root(); if (!host) return;
    const data = state.data[state.tab];
    const label = (TABS.find((t) => t.key === state.tab) || TABS[0]).label;
    let body;
    if (!data && state.error[state.tab]) body = `<p class="dash-empty">${esc(state.error[state.tab])} <button type="button" class="dash-link" data-dash-retry>Retry</button></p>`;
    else if (!data) body = '<div class="dash-skeleton" aria-busy="true"><i></i><i></i><i></i><i></i></div>';
    else body = state.tab === 'career' ? career(data) : state.tab === 'business' ? business(data) : personal(data);
    const scroll = host.parentElement ? host.parentElement.scrollTop : 0;
    host.innerHTML = `<div class="dash">
      <div class="dash-head"><div><h1>Dashboard</h1><p>${label} at a glance.</p></div>
        <div class="dash-tabs" role="tablist">${TABS.map((t) => `<button type="button" role="tab" data-dash-tab="${t.key}" aria-selected="${t.key === state.tab}" class="${t.key === state.tab ? 'on' : ''}">${t.label}</button>`).join('')}</div>
      </div>
      <div class="dash-body" data-tab="${state.tab}">${body}</div>
    </div>`;
    if (host.parentElement) host.parentElement.scrollTop = scroll;
  }

  function select(tab) {
    if (!TABS.some((t) => t.key === tab)) return;
    const changed = tab !== state.tab;
    state.tab = tab; saveTab(tab);
    paint();
    if (changed || !state.data[tab]) load(tab, {quiet: !!state.data[tab]});
  }

  function onClick(event) {
    const target = event.target.closest('[data-dash-tab],[data-dash-go],[data-dash-item],[data-dash-note],[data-dash-retry]');
    if (!target) return;
    if (target.dataset.dashTab) return select(target.dataset.dashTab);
    if (target.hasAttribute('data-dash-retry')) return load(state.tab);
    if (target.dataset.dashGo && typeof switchPanel === 'function') return switchPanel(target.dataset.dashGo);
    if (target.dataset.dashItem) {
      if (typeof window.openWorkHubItem === 'function') window.openWorkHubItem(target.dataset.dashItem, target.dataset.project || null, target.dataset.board || null);
      return;
    }
    if (target.dataset.dashNote) {
      if (window.Notebook && typeof window.Notebook.openFrom === 'function') window.Notebook.openFrom(target.dataset.dashNote, null);
    }
  }

  function tick() {
    if (!state.mounted || document.hidden) return;
    load(state.tab, {quiet: true});
  }

  function mount() {
    state.mounted = true;
    paint();
    load(state.tab, {quiet: !!state.data[state.tab]});
    clearInterval(state.timer);
    state.timer = setInterval(tick, REFRESH_MS);
    if (state.timer && typeof state.timer.unref === 'function') state.timer.unref();
  }
  function unmount() { state.mounted = false; clearInterval(state.timer); state.timer = 0; }

  document.addEventListener('click', (event) => {
    if (event.target.closest && event.target.closest('#dashboardRoot,#dashboardSidebar')) onClick(event);
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) tick(); });
  window.HermesDashboard = {mount, unmount, select, _state: state};
})();
