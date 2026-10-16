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
  const CHARACTER = {key: 'character', label: 'Character', icon: '<path d="M14.5 17.5 3 6V3h3l11.5 11.5"/><path d="m13 19 6-6M16 16l4 4M19 21l2-2"/>'};
  const VIEWS = TABS.map((t) => t.key).concat('character');
  const REFRESH_MS = 15000;
  const state = {tab: 'personal', data: {}, loading: {}, error: {}, timer: 0, mounted: false, logCategory: 'all', logOffset: 0};

  function readTab() {
    try { const t = localStorage.getItem('hermes-dashboard-tab'); if (VIEWS.includes(t)) return t; } catch (_) {}
    return 'personal';
  }
  function levelBadge() {
    let level = state.data.character && state.data.character.level;
    if (!level) { try { level = parseInt(localStorage.getItem('hermes-dashboard-level') || '0', 10) || 0; } catch (_) {} }
    return level ? `<span class="dash-level-badge">Lv ${level}</span>` : '';
  }
  function saveTab(tab) { try { localStorage.setItem('hermes-dashboard-tab', tab); } catch (_) {} }
  state.tab = readTab();
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
    if (tab === 'character') return loadCharacter({quiet});
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

  const QUEST_ICON = '<path d="M14.5 17.5 3 6V3h3l11.5 11.5"/><path d="m13 19 6-6M16 16l4 4M19 21l2-2"/>';
  function questsCard(list) {
    if (list && list.error) return card('Quests', sectionError(list), {icon: QUEST_ICON});
    list = Array.isArray(list) ? list : [];
    const done = list.filter((q) => q.done).length;
    const rows = list.map((q) => `<div class="dash-quest-row${q.done ? ' is-done' : ''}${q.working ? ' is-working' : ''}" data-quest="${esc(q.id)}">
        <span class="dash-check" data-status="${esc(q.status)}">${q.done ? svg('<path d="M20 6 9 17l-5-5"/>', 12) : ''}</span>
        <button type="button" class="dash-quest-open" data-dash-item="${esc(q.id)}" data-project="${esc(q.project_id || '')}" data-board="${esc(q.board_id || '')}">
          <strong>${esc(q.title)}</strong><small>${esc(q.project || 'General')}${q.priority && q.priority !== 'none' ? ' · ' + esc(q.priority) : ''}</small>
        </button>
        ${q.done
          ? `<span class="dash-xp-gain">+${esc(q.xp || 0)} XP</span>`
          : `<span class="dash-pill${q.status === 'in_progress' ? ' is-accent' : q.status === 'blocked' ? ' is-bad' : ''}">${q.working ? '<span class="work-hub-spinner" aria-hidden="true"></span> Working' : esc(STATUS_LABEL[q.status] || q.status)}</span>`}
        <button type="button" class="dash-quest-remove" data-quest-remove="${esc(q.id)}" aria-label="Remove from quests" title="Remove from quests">${svg('<path d="M18 6 6 18M6 6l12 12"/>', 14)}</button>
      </div>`).join('');
    const empty = `<div class="dash-quest-empty"><p>Pick the Work Hub items you feel like doing. No dates, no pressure: they stay here until they're done, and finishing one earns 50% bonus XP.</p><button type="button" class="dash-btn" data-dash-add-quest>${svg('<path d="M12 5v14M5 12h14"/>', 14)} Choose quests</button></div>`;
    const actions = `<span class="dash-card-actions">${done ? `<button type="button" class="dash-link" data-quest-clear>Clear done</button>` : ''}${list.length ? `<button type="button" class="dash-btn is-small" data-dash-add-quest>${svg('<path d="M12 5v14M5 12h14"/>', 13)} Add</button>` : ''}</span>`;
    return card(`Quests${list.length ? ` · ${list.length - done} open` : ''}`, `<div class="dash-quests">${rows || empty}</div>`, {icon: QUEST_ICON, action: actions, cls: 'is-quests'});
  }

  function personal(data) {
    const hub = data.work_hub || {};
    const t = hub.totals || {};
    const stats = hub.error ? '' : `<div class="dash-stats">
      ${stat('Open items', t.open || 0)}
      ${stat('In progress', t.in_progress || 0, t.working ? `<span class="work-hub-spinner" aria-hidden="true"></span> ${t.working} with a chat` : '')}
      ${stat('Done this week', t.done_this_week || 0, '', t.done_this_week ? 'good' : '')}
      ${stat('Blocked', t.blocked || 0, '', t.blocked ? 'bad' : '')}
    </div>`;
    const quests = questsCard(data.quests);
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
        ${quests}
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

  // ── quests: picker and actions ───────────────────────────────────────────
  async function post(path, body) {
    return api(path, {method: 'POST', body: JSON.stringify(body || {})});
  }
  function toast(message) { if (typeof showToast === 'function') showToast(message); }

  async function openQuestPicker() {
    closeQuestPicker();
    const overlay = document.createElement('div');
    overlay.className = 'dash-picker-overlay';
    overlay.innerHTML = `<div class="dash-picker" role="dialog" aria-modal="true" aria-label="Choose quests">
      <header><h3>Choose quests</h3><button type="button" class="dash-picker-x" data-picker-close aria-label="Close">${svg('<path d="M18 6 6 18M6 6l12 12"/>', 16)}</button></header>
      <label class="dash-picker-search">${svg('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>', 15)}<input type="text" placeholder="Search Work Hub items" autocomplete="off" data-picker-search></label>
      <div class="dash-picker-list" data-picker-list><div class="dash-skeleton is-list"><i></i><i></i><i></i></div></div>
      <footer><button type="button" class="dash-btn is-ghost" data-picker-close>Cancel</button><button type="button" class="dash-btn" data-picker-add disabled>Add quests</button></footer>
    </div>`;
    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add('is-open'));
    const chosen = new Set();
    let items = [], names = {}, already = new Set();
    try {
      const [boot, ids] = await Promise.all([api('/api/work_hub/bootstrap'), api('/api/dashboard/quests')]);
      items = (boot.items || []).filter((i) => !['done', 'cancelled'].includes(i.status));
      (boot.projects || []).forEach((proj) => { names[proj.project_id] = proj.name; });
      already = new Set(ids.item_ids || []);
    } catch (error) {
      overlay.querySelector('[data-picker-list]').innerHTML = `<p class="dash-empty">Couldn't load the Work Hub: ${esc(error.message || error)}</p>`;
      return;
    }
    const list = overlay.querySelector('[data-picker-list]');
    const addBtn = overlay.querySelector('[data-picker-add]');
    const draw = (query) => {
      const q = String(query || '').toLowerCase();
      const groups = {};
      items.filter((i) => !q || String(i.title || '').toLowerCase().includes(q) || String(names[i.project_id] || '').toLowerCase().includes(q))
        .forEach((i) => { (groups[i.project_id || ''] = groups[i.project_id || ''] || []).push(i); });
      const keys = Object.keys(groups).sort((a, b) => String(names[a] || 'General').localeCompare(String(names[b] || 'General')));
      list.innerHTML = keys.map((k) => `<div class="dash-picker-group"><h4>${esc(names[k] || 'General')}</h4>${groups[k].map((i) => {
        const isQuest = already.has(i.id);
        return `<label class="dash-picker-row${isQuest ? ' is-quest' : ''}"><input type="checkbox" value="${esc(i.id)}"${isQuest ? ' disabled checked' : chosen.has(i.id) ? ' checked' : ''}><span class="dash-row-main"><strong>${esc(i.title)}</strong><small>${esc(STATUS_LABEL[i.status] || i.status)}${isQuest ? ' · already a quest' : ''}</small></span></label>`;
      }).join('')}</div>`).join('') || '<p class="dash-empty">No open Work Hub items match.</p>';
    };
    draw('');
    list.addEventListener('change', (event) => {
      const box = event.target.closest('input[type=checkbox]'); if (!box || box.disabled) return;
      if (box.checked) chosen.add(box.value); else chosen.delete(box.value);
      addBtn.disabled = !chosen.size;
      addBtn.textContent = chosen.size ? `Add ${chosen.size} quest${chosen.size === 1 ? '' : 's'}` : 'Add quests';
    });
    overlay.querySelector('[data-picker-search]').addEventListener('input', (event) => draw(event.target.value));
    addBtn.addEventListener('click', async () => {
      addBtn.disabled = true;
      try {
        await post('/api/dashboard/quests/add', {item_ids: [...chosen]});
        closeQuestPicker();
        toast(`${chosen.size} quest${chosen.size === 1 ? '' : 's'} added`);
        load('personal', {quiet: true});
      } catch (error) { addBtn.disabled = false; toast(error.message || 'Could not add quests'); }
    });
  }
  function closeQuestPicker() {
    document.querySelectorAll('.dash-picker-overlay').forEach((el) => {
      el.classList.remove('is-open'); setTimeout(() => el.remove(), 200);
    });
  }
  async function removeQuest(id, row) {
    if (row) row.classList.add('is-leaving');
    try { await post('/api/dashboard/quests/remove', {item_id: id}); } catch (error) { toast(error.message || 'Could not remove'); }
    load('personal', {quiet: true});
  }
  async function clearDone() {
    try { await post('/api/dashboard/quests/clear', {}); } catch (error) { toast(error.message || 'Could not clear'); }
    load('personal', {quiet: true});
  }

  // ── character page ───────────────────────────────────────────────────────
  const AREA = {personal: {label: 'Personal', stat: 'STR'}, career: {label: 'Career', stat: 'INT'}, business: {label: 'Business', stat: 'CHA'}};
  function radar(stats) {
    const keys = ['STR', 'INT', 'CHA', 'DEX'];
    const max = Math.max(10, ...keys.map((k) => (stats[k] || {}).value || 0));
    const c = 70, r = 54;
    const point = (i, f) => { const a = -Math.PI / 2 + i * Math.PI / 2; return [c + Math.cos(a) * r * f, c + Math.sin(a) * r * f]; };
    const ring = (f) => keys.map((_, i) => point(i, f).join(',')).join(' ');
    const shape = keys.map((k, i) => point(i, Math.max(0.06, ((stats[k] || {}).value || 0) / max)).join(',')).join(' ');
    const labels = keys.map((k, i) => { const [x, y] = point(i, 1.24); return `<text x="${x}" y="${y}" text-anchor="middle" dominant-baseline="middle">${k}</text>`; }).join('');
    return `<svg class="char-radar" viewBox="0 0 140 140" role="img" aria-label="Attribute chart">
      ${[0.33, 0.66, 1].map((f) => `<polygon points="${ring(f)}" class="char-radar-ring"/>`).join('')}
      <polygon points="${shape}" class="char-radar-shape"/>${labels}</svg>`;
  }
  function characterView(data) {
    if (!window.DashSprite) return '<p class="dash-empty">Loading the character…</p>';
    const tiers = data.tiers || [];
    const statRows = ['STR', 'INT', 'CHA', 'DEX'].map((k) => { const st = (data.stats || {})[k] || {}; return `<div class="char-stat" title="${esc(st.hint || '')}"><b>${esc(st.value || 1)}</b><span><strong>${k}</strong><small>${esc(st.label || '')}</small></span></div>`; }).join('');
    const areas = (data.areas || []).map((a) => `<div class="dash-row"><span class="char-area-dot is-${a.key}"></span><span class="dash-row-main"><strong>${esc(AREA[a.key].label)} · Lv ${a.level}</strong><small>${a.xp} XP · ${plural(a.tasks, 'task')}</small></span>${bar(a.progress)}</div>`).join('');
    const path = tiers.map((t, i) => { const reached = data.level >= t.level; const current = data.tier === i + 1;
      return `<div class="char-tier${reached ? ' is-reached' : ''}${current ? ' is-current' : ''}">${window.DashSprite.render(i + 1, 3)}<strong>${esc(t.name)}</strong><small>${reached ? (current ? 'Now' : 'Unlocked') : `Level ${t.level}`}</small></div>`; }).join('');
    const filter = state.logCategory || 'all';
    const chips = ['all', 'personal', 'career', 'business'].map((k) => `<button type="button" class="dash-chip${filter === k ? ' on' : ''}" data-log-filter="${k}">${k === 'all' ? 'All' : AREA[k].label}</button>`).join('');
    const log = (data.log || []).map((e) => `<div class="dash-row char-log-row"><span class="char-area-dot is-${esc(e.category)}"></span><span class="dash-row-main"><strong>${e.quest ? '⚔ ' : ''}${esc(e.title)}</strong><small>${esc(AREA[e.category] ? AREA[e.category].label : e.category)} · ${ago(e.at)}</small></span><span class="dash-xp-gain">+${e.xp} XP</span></div>`).join('') || '<p class="dash-empty">Finish a Work Hub item or move a job forward to earn your first XP.</p>';
    const more = data.log_total > (data.log || []).length + (state.logOffset || 0) ? `<button type="button" class="dash-link is-more" data-log-more>Show more</button>` : '';
    const cats = (data.projects || []).map((pr) => `<div class="dash-row"><span class="dash-row-main"><strong>${esc(pr.name)}</strong></span><select class="dash-select" data-project-category="${esc(pr.project_id)}" aria-label="Area for ${esc(pr.name)}">${Object.keys(AREA).map((k) => `<option value="${k}"${pr.category === k ? ' selected' : ''}>${AREA[k].label}</option>`).join('')}</select></div>`).join('') || '<p class="dash-empty">No projects yet.</p>';
    const toNext = data.level_size - data.into_level;
    return `<div class="char-hero">
        <div class="char-stage" data-tier="${data.tier}">
          <div class="char-aura" aria-hidden="true"></div>
          ${window.DashSprite.render(data.tier, 8)}
          <div class="char-plate"><span class="char-level">Lv ${data.level}</span><span class="char-class">${esc(data.tier_name)} Warlock</span></div>
        </div>
        <div class="char-panel">
          <div class="char-title"><h2>Level ${data.level} <small>${esc(data.tier_name)}</small></h2><span class="char-total">${data.total_xp.toLocaleString()} XP</span></div>
          <div class="char-xpbar"><i style="width:${Math.round(data.progress * 100)}%"></i></div>
          <div class="char-xpline"><span>${data.into_level} / ${data.level_size} XP</span><span>${toNext} XP to level ${data.level + 1}${data.next_tier ? ` · ${esc(data.next_tier.name)} at ${data.next_tier.level}` : ''}</span></div>
          <div class="char-body">${radar(data.stats || {})}<div class="char-stats">${statRows}</div></div>
          <div class="char-badges">
            <div><b>🔥 ${data.streak}</b><small>day streak</small></div>
            <div><b>+${data.xp_this_week}</b><small>XP this week</small></div>
            <div><b>${data.tasks_done}</b><small>tasks done</small></div>
            <div><b>⚔ ${data.quests_done}</b><small>quests done</small></div>
          </div>
        </div>
      </div>
      <div class="dash-grid is-wide-left">
        ${card('XP log', `<div class="dash-chips">${chips}</div>${log}${more}`, {icon: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>'})}
        <div class="dash-stack">
          ${card('Areas', areas, {icon: '<circle cx="12" cy="12" r="9"/><path d="M12 3v9l6 4"/>'})}
          ${card('Evolution', `<div class="char-tiers">${path}</div>`, {icon: '<path d="m12 2 3 7h7l-5.5 4.5L18 21l-6-4-6 4 1.5-7.5L2 9h7z"/>'})}
          ${card('Project areas', `<p class="dash-hint">Which area each project's finished tasks count towards.</p>${cats}`, {icon: '<path d="M3 7h18M3 12h18M3 17h18"/>'})}
        </div>
      </div>`;
  }
  async function loadCharacter({quiet = false, append = false} = {}) {
    if (state.loading.character) return;
    state.loading.character = true;
    if (!quiet) paint();
    try {
      const offset = append ? (state.logOffset || 0) + 50 : 0;
      const cat = state.logCategory && state.logCategory !== 'all' ? state.logCategory : '';
      const data = await api(`/api/dashboard/character?category=${encodeURIComponent(cat)}&offset=${offset}`);
      if (append && state.data.character) data.log = (state.data.character.log || []).concat(data.log || []);
      state.logOffset = append ? offset : 0;
      state.data.character = data;
      state.error.character = null;
      celebrate(data.level);
    } catch (error) {
      state.error.character = (error && error.message) || 'Could not load your character';
    } finally { state.loading.character = false; }
    if (state.mounted) paint();
  }
  function celebrate(level) {
    let seen = 0;
    try { seen = parseInt(localStorage.getItem('hermes-dashboard-level') || '0', 10) || 0; localStorage.setItem('hermes-dashboard-level', String(level)); } catch (_) {}
    if (!seen || level <= seen) return;
    const burst = document.createElement('div');
    burst.className = 'char-levelup';
    burst.innerHTML = `<div><small>LEVEL UP</small><b>${level}</b></div>`;
    document.body.appendChild(burst);
    setTimeout(() => burst.remove(), 2600);
  }

  // ── paint ────────────────────────────────────────────────────────────────
  function paintSidebar() {
    const host = sidebar(); if (!host) return;
    const item = (t) => `<button type="button" class="side-menu-item${t.key === state.tab ? ' active' : ''}" data-dash-tab="${t.key}"${t.key === state.tab ? ' aria-current="page"' : ''}>${svg(t.icon)}<span class="side-menu-label">${t.label}</span>${t.key === 'character' ? levelBadge() : ''}</button>`;
    host.innerHTML = `<nav class="dash-side-nav">${TABS.map(item).join('')}<div class="dash-side-divider" aria-hidden="true"></div>${item(CHARACTER)}</nav>`;
  }
  function paint() {
    paintSidebar();
    const host = root(); if (!host) return;
    const data = state.data[state.tab];
    const label = state.tab === 'character' ? 'Your character' : (TABS.find((t) => t.key === state.tab) || TABS[0]).label + ' at a glance';
    let body;
    if (!data && state.error[state.tab]) body = `<p class="dash-empty">${esc(state.error[state.tab])} <button type="button" class="dash-link" data-dash-retry>Retry</button></p>`;
    else if (!data) body = '<div class="dash-skeleton" aria-busy="true"><i></i><i></i><i></i><i></i></div>';
    else body = state.tab === 'character' ? characterView(data) : state.tab === 'career' ? career(data) : state.tab === 'business' ? business(data) : personal(data);
    const scroll = host.parentElement ? host.parentElement.scrollTop : 0;
    host.innerHTML = `<div class="dash">
      <div class="dash-head"><div><h1>${state.tab === 'character' ? 'Character' : 'Dashboard'}</h1><p>${label}.</p></div>
        <div class="dash-head-right"><div class="dash-tabs" role="tablist">${TABS.map((t) => `<button type="button" role="tab" data-dash-tab="${t.key}" aria-selected="${t.key === state.tab}" class="${t.key === state.tab ? 'on' : ''}">${t.label}</button>`).join('')}</div>
        <button type="button" class="dash-char-btn${state.tab === 'character' ? ' on' : ''}" data-dash-tab="character">${svg('<path d="M14.5 17.5 3 6V3h3l11.5 11.5"/><path d="m13 19 6-6M16 16l4 4M19 21l2-2"/>', 15)}<span>Character</span>${levelBadge()}</button></div>
      </div>
      <div class="dash-body" data-tab="${state.tab}">${body}</div>
    </div>`;
    if (host.parentElement) host.parentElement.scrollTop = scroll;
  }

  function select(tab) {
    if (!VIEWS.includes(tab)) return;
    const changed = tab !== state.tab;
    state.tab = tab; saveTab(tab);
    paint();
    if (changed || !state.data[tab]) load(tab, {quiet: !!state.data[tab]});
  }

  function onClick(event) {
    const target = event.target.closest('[data-dash-tab],[data-dash-go],[data-dash-item],[data-dash-note],[data-dash-retry],[data-dash-add-quest],[data-quest-remove],[data-quest-clear],[data-log-filter],[data-log-more]');
    if (!target) return;
    if (target.hasAttribute('data-dash-add-quest')) return openQuestPicker();
    if (target.dataset.questRemove) return removeQuest(target.dataset.questRemove, target.closest('.dash-quest-row'));
    if (target.hasAttribute('data-quest-clear')) return clearDone();
    if (target.dataset.logFilter) { state.logCategory = target.dataset.logFilter; return loadCharacter({quiet: true}); }
    if (target.hasAttribute('data-log-more')) return loadCharacter({quiet: true, append: true});
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
  document.addEventListener('change', async (event) => {
    const select = event.target.closest && event.target.closest('[data-project-category]');
    if (!select) return;
    try { await post('/api/dashboard/categories', {project_id: select.dataset.projectCategory, category: select.value}); toast('Area updated'); }
    catch (error) { toast(error.message || 'Could not update'); }
    loadCharacter({quiet: true});
  });
  document.addEventListener('click', (event) => {
    if (!event.target.closest) return;
    if (event.target.closest('[data-picker-close]') || event.target.classList.contains('dash-picker-overlay')) closeQuestPicker();
  });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && document.querySelector('.dash-picker-overlay')) closeQuestPicker(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) tick(); });
  window.HermesDashboard = {mount, unmount, select, openQuestPicker, _state: state};
})();
