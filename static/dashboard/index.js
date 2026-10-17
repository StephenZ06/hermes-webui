/* Dashboard: Personal, Career and Business at a glance, and the Character page
   (an RPG take on everything you finish). Data comes from /api/dashboard/*;
   effects (thinking orbs, border beams, bot avatars, liquid metal) come from
   the vendored Libraries.dev bundle, loaded only when this page is shown. */
(() => {
  'use strict';
  const ICONS = {
    personal: '<path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    career: '<path d="M4 8h16v12H4z"/><path d="M9 8V5h6v3M4 13h16"/>',
    business: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    character: '<path d="M14.5 17.5 3 6V3h3l11.5 11.5"/><path d="m13 19 6-6M16 16l4 4M19 21l2-2"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    sword: '<path d="M14.5 17.5 3 6V3h3l11.5 11.5"/><path d="m13 19 6-6M16 16l4 4M19 21l2-2"/>',
    heart: '<path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3 .5-4.5 2-1.5-1.5-2.7-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7Z"/>',
    book: '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>',
    chart: '<path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 5-6"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    note: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    trophy: '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/>',
    road: '<path d="M4 20 8 4M20 20 16 4M12 6v2M12 11v2M12 16v2"/>',
    receipt: '<path d="M5 3v18l3-2 2 2 2-2 2 2 2-2 3 2V3z"/><path d="M9 8h6M9 12h6"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
    refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
    funnel: '<path d="M3 4h18l-7 9v6l-4 2v-8z"/>',
    calendar: '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M3 10h18M8 2v4M16 2v4"/>',
    'chevron-left': '<path d="m15 18-6-6 6-6"/>',
    'chevron-right': '<path d="m9 18 6-6-6-6"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    star: '<path d="m12 2 3 7h7l-5.5 4.5L18 21l-6-4-6 4 1.5-7.5L2 9h7z"/>',
    users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
    gem: '<path d="M6 3h12l4 6-10 12L2 9z"/><path d="M11 3 8 9l4 12 4-12-3-6M2 9h20"/>',
    layers: '<path d="M3 7h18M3 12h18M3 17h18"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  };
  const TABS = [
    {key: 'personal', label: 'Personal'},
    {key: 'career', label: 'Career'},
    {key: 'business', label: 'Business'},
  ];
  const VIEWS = ['character', 'personal', 'career', 'business', 'settings'];
  const VIEW_TITLE = {character: 'CHARACTER', personal: 'PERSONAL DASHBOARD', career: 'CAREER DASHBOARD', business: 'BUSINESS DASHBOARD', settings: 'SETTINGS'};
  // Card icons drawn as pixel art (static/dashboard/icons), by card.
  const PIX = (name) => `<img class="dash-pix-icon" data-dash-pix="${name}" src="static/dashboard/icons/${name}.png" alt="" width="24" height="24" draggable="false">`;
  const AREA = {personal: 'Personal', career: 'Career', business: 'Business'};
  const STATUS_LABEL = {in_progress: 'In progress', blocked: 'Blocked', todo: 'To do', triage: 'Triage', backlog: 'Backlog', done: 'Done', cancelled: 'Cancelled'};
  const BOT_TYPES = ['clover', 'star', 'mech', 'flower', 'ghost', 'hexagon', 'circle', 'square'];
  const REFRESH_MS = 15000;
  const LOG_PAGE = 15;

  const state = {tab: 'character', entering: true, data: {}, loading: {}, error: {}, painted: {}, timer: 0, mounted: false, logCategory: 'all', logOffset: 0, forms: {}};
  const effects = [];

  // ── helpers ──────────────────────────────────────────────────────────────
  const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[c]);
  const svg = (name, size = 18) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`;
  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
  function ago(at) {
    if (!at) return '';
    const s = Math.max(0, Date.now() / 1000 - Number(at));
    if (s < 60) return 'just now';
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    if (s < 86400 * 30) return `${Math.floor(s / 86400)}d ago`;
    return new Date(at * 1000).toLocaleDateString();
  }
  function money(cents, currency = 'USD') {
    try { return new Intl.NumberFormat(undefined, {style: 'currency', currency, maximumFractionDigits: (cents || 0) % 100 ? 2 : 0}).format((cents || 0) / 100); }
    catch (_) { return `${((cents || 0) / 100).toFixed(2)} ${currency}`; }
  }
  const root = () => document.getElementById('dashboardRoot');
  const sidebar = () => document.getElementById('dashboardSidebar');
  function readTab() { try { const t = localStorage.getItem('hermes-dashboard-tab'); if (VIEWS.includes(t)) return t; } catch (_) {} return 'character'; }
  function saveTab(tab) { try { localStorage.setItem('hermes-dashboard-tab', tab); } catch (_) {} }
  state.tab = readTab();
  async function post(path, body) { return api(path, {method: 'POST', body: JSON.stringify(body || {})}); }
  function toast(message) { if (message && typeof showToast === 'function') showToast(message); }
  function isDark() {
    const bg = getComputedStyle(document.body).backgroundColor.match(/\d+/g);
    if (!bg) return true;
    const [r, g, b] = bg.map(Number);
    return (0.299 * r + 0.587 * g + 0.114 * b) < 140;
  }

  // ── pieces ───────────────────────────────────────────────────────────────
  const card = (title, body, {icon = '', pix = '', action = '', cls = '', attrs = '', key = ''} = {}) =>
    `<section class="dash-card ${cls}" ${attrs}${key ? ` data-dash-card="${key}"` : ''}><header class="dash-card-head">${pix ? `<span class="dash-card-icon is-pixel">${PIX(pix)}</span>` : icon ? `<span class="dash-card-icon">${svg(icon, 16)}</span>` : ''}<h3>${title}</h3>${action ? `<span class="dash-card-actions">${action}</span>` : ''}</header><div class="dash-card-body">${body}</div></section>`;
  // A stat tile with ``focus`` is a button: it scrolls to that card and makes it pulse.
  const stat = (label, value, note = '', tone = '', pix = '', focus = '') => {
    const tag = focus ? 'button' : 'div';
    const attrs = focus ? ` type="button" data-dash-focus="${focus}" title="Show ${esc(label.toLowerCase())}"` : '';
    return `<${tag} class="dash-stat${tone ? ' is-' + tone : ''}${focus ? ' is-link' : ''}"${attrs}>${pix ? `<span class="dash-stat-icon is-pixel">${PIX(pix)}</span>` : ''}<span class="dash-stat-copy"><small>${esc(label)}</small><b>${value}</b>${note ? `<span>${note}</span>` : ''}</span></${tag}>`;
  };
  const bar = (fraction, tone = '') => `<span class="dash-bar${tone ? ' is-' + tone : ''}"><i style="width:${Math.round(Math.max(0, Math.min(1, fraction || 0)) * 100)}%"></i></span>`;
  const sectionError = (section) => section && section.error ? `<p class="dash-empty">Couldn't read this: ${esc(section.error)}</p>` : '';
  const link = (label, attrs) => `<button type="button" class="dash-link${/data-dash-(go|tab)=/.test(attrs) ? ' dash-nav' : ''}" ${attrs}>${esc(label)}</button>`;
  const btn = (label, attrs, {icon = '', cls = ''} = {}) => `<button type="button" class="dash-btn ${cls}" ${attrs}>${icon ? svg(icon, 14) : ''}${label ? `<span>${esc(label)}</span>` : ''}</button>`;
  const orb = (kind = 'working') => `<span class="dash-orb" data-ld="orb" data-state="${kind}"><span class="work-hub-spinner" aria-hidden="true"></span></span>`;

  function questRow(q, {showArea = true} = {}) {
    return `<div class="dash-quest-row${q.done ? ' is-done' : ''}${q.working ? ' is-working' : ''}" data-quest="${esc(q.id)}">
      <span class="dash-check" data-status="${esc(q.status)}">${q.done ? svg('check', 12) : ''}</span>
      <button type="button" class="dash-quest-open dash-nav" data-dash-item="${esc(q.id)}" data-project="${esc(q.project_id || '')}" data-board="${esc(q.board_id || '')}">
        <strong>${esc(q.title)}</strong><small>${showArea ? `<span class="dash-area-tag is-${esc(q.area)}">${esc(AREA[q.area] || q.area)}</span>` : ''}${esc(q.project || 'General')}${q.priority && q.priority !== 'none' ? ' · ' + esc(q.priority) : ''}</small>
      </button>
      ${q.done ? `<span class="dash-xp-gain">+${esc(q.xp || 0)} XP</span>`
        : q.working ? `<span class="dash-pill is-accent">${orb('working')} Working</span>`
          : `<span class="dash-pill${q.status === 'in_progress' ? ' is-accent' : q.status === 'blocked' ? ' is-bad' : ''}">${esc(STATUS_LABEL[q.status] || q.status)}</span>`}
      <button type="button" class="dash-icon-btn dash-quest-remove" data-quest-remove="${esc(q.id)}" aria-label="Remove from quests" title="Remove from quests">${svg('x', 14)}</button>
    </div>`;
  }

  /* An area's quests, on its own tab (the full quest log is on the Character page). */
  function questStrip(list, area) {
    if (list && list.error) return card('Quests', sectionError(list), {pix: {personal: 'personal-quest', career: 'career-quests', business: 'business-quest'}[area]});
    list = Array.isArray(list) ? list : [];
    const open = list.filter((q) => !q.done);
    const done = list.length - open.length;
    const working = list.some((q) => q.working);
    const body = list.length ? `<div class="dash-quests">${list.map((q) => questRow(q, {showArea: false})).join('')}</div>`
      : `<div class="dash-quest-empty"><p>No ${esc(AREA[area].toLowerCase())} quests yet. Pick Work Hub items to focus on; finishing one as a quest earns 50% bonus XP.</p></div>`;
    const action = `${done ? link('Clear done', 'data-quest-clear') : ''}${link('Quest log', 'data-dash-tab="character"')}${btn('Add', 'data-dash-add-quest', {icon: 'plus', cls: 'is-small'})}`;
    return card(`${AREA[area]} quests${open.length ? ` · ${open.length} open` : ''}`, body, {pix: {personal: 'personal-quest', career: 'career-quests', business: 'business-quest'}[area], action, cls: 'is-quests', key: 'quests', attrs: working ? 'data-ld-beam="md"' : ''});
  }

  // ── Personal ─────────────────────────────────────────────────────────────
  function habitsCard(list) {
    if (list && list.error) return card('Habits', sectionError(list), {pix: 'habits'});
    list = Array.isArray(list) ? list : [];
    const form = state.forms.habit ? `<form class="dash-inline-form" data-form="habit">
        <input name="name" type="text" maxlength="120" placeholder="e.g. Gym, Read 20 pages" required autocomplete="off">
        <select name="cadence" aria-label="How often"><option value="daily">Daily</option><option value="weekly">Weekly</option></select>
        <select name="target" aria-label="Times a week" data-weekly-target hidden>${[1, 2, 3, 4, 5, 6, 7].map((n) => `<option value="${n}"${n === 3 ? ' selected' : ''}>${n === 1 ? 'Once' : `${n} times`} a week</option>`).join('')}</select>
        <button type="submit" class="dash-btn is-small">Add</button><button type="button" class="dash-link" data-form-cancel="habit">Cancel</button>
      </form>` : '';
    const rows = list.map((h) => `<div class="dash-habit${h.done ? ' is-done' : ''}" data-habit="${esc(h.id)}">
        <button type="button" class="dash-habit-check${h.today ? ' is-on' : ''}" data-habit-toggle="${esc(h.id)}" data-on="${h.today ? '1' : '0'}" aria-pressed="${h.today}" aria-label="${h.today ? 'Untick' : 'Tick'} ${esc(h.name)} for today">${svg('check', 14)}</button>
        <span class="dash-row-main"><strong>${esc(h.name)}</strong><small>${h.cadence === 'weekly' ? `${h.week_count}/${h.target} this week` : (h.today ? 'Done today' : 'Not yet today')}${h.streak ? ` · 🔥 ${h.streak} ${h.cadence === 'weekly' ? 'wk' : 'day'}${h.streak === 1 ? '' : 's'}` : ''}</small></span>
        <span class="dash-heat" aria-hidden="true">${(h.recent || []).map((on) => `<i class="${on ? 'on' : ''}"></i>`).join('')}</span>
        <button type="button" class="dash-icon-btn dash-habit-remove" data-habit-archive="${esc(h.id)}" aria-label="Stop tracking ${esc(h.name)}" title="Stop tracking">${svg('x', 13)}</button>
      </div>`).join('');
    const empty = !list.length && !state.forms.habit ? '<p class="dash-empty">Track the things that keep you going. Each one ticked earns 10 XP towards Vitality.</p>' : '';
    return card('Habits', `${form}${empty}<div class="dash-habits">${rows}</div>`, {pix: 'habits', cls: 'is-habits', key: 'habits', action: state.forms.habit ? '' : btn('New habit', 'data-form-open="habit"', {icon: 'plus', cls: 'is-small'})});
  }

  function learningCard(data) {
    if (data && data.error) return card('Learning log', sectionError(data), {pix: 'learning-log'});
    const entries = (data && data.entries) || [];
    const kinds = [['course', 'Course', 40], ['book', 'Book', 30], ['certification', 'Certification', 100], ['skill', 'Skill', 20], ['other', 'Other', 15]];
    const form = `<form class="dash-inline-form is-learning" data-form="learning">
        <input name="title" type="text" maxlength="120" placeholder="What did you learn or finish?" required autocomplete="off">
        <select name="kind" aria-label="Kind">${kinds.map(([k, l, xp]) => `<option value="${k}">${l} · ${xp} XP</option>`).join('')}</select>
        <select name="area" aria-label="Counts towards"><option value="career">Career</option><option value="personal">Personal</option><option value="business">Business</option></select>
        <button type="submit" class="dash-btn is-small">Log it</button>
      </form>`;
    const rows = entries.map((e) => `<div class="dash-row"><span class="dash-area-dot is-${esc(e.area)}"></span><span class="dash-row-main"><strong>${esc(e.title)}</strong><small>${esc(String(e.kind || '').charAt(0).toUpperCase() + String(e.kind || '').slice(1))} · ${esc(AREA[e.area])} · ${ago(e.done_at)}</small></span><span class="dash-xp-gain">+${e.xp} XP</span><button type="button" class="dash-icon-btn" data-learning-remove="${esc(e.id)}" aria-label="Remove" title="Remove">${svg('x', 13)}</button></div>`).join('');
    return card(`Learning log${data && data.total ? ` · ${data.total}` : ''}`, `<div class="dash-learning-entries">${rows || '<p class="dash-empty">Courses, books, certifications and new skills: they level you up and can feed your resume.</p>'}</div>${form}`, {pix: 'learning-log', cls: 'is-learning-log', key: 'learning'});
  }

  function personal(data) {
    const hub = data.work_hub || {};
    const t = hub.totals || {};
    const habits = Array.isArray(data.habits) ? data.habits : [];
    const daily = habits.filter((h) => h.cadence === 'daily');
    const allDone = daily.length && daily.every((h) => h.today);
    const stats = `<div class="dash-stats">
      ${stat('Habits today', `${daily.filter((h) => h.today).length}/${daily.length}`, allDone ? 'All done 🎉' : '', allDone ? 'good' : '', 'habits', 'habits')}
      ${stat('Personal quests', (data.quests || []).length, '', '', 'personal-quest', 'quests')}
      ${stat('In progress', t.in_progress || 0, t.working ? `${orb('working')} ${t.working} with a chat` : '', '', 'project-health', 'project-health')}
      ${stat('Done this week', t.done_this_week || 0, '', t.done_this_week ? 'good' : '', 'this-week', 'project-health')}
    </div>`;
    const projects = (hub.projects || []).filter((p) => p.open || p.done).slice(0, 6).map((p) => `<div class="dash-row">
        <span class="dash-row-main"><strong>${esc(p.name)}</strong><small>${plural(p.open, 'open item')}${p.last_activity ? ' · ' + ago(p.last_activity) : ''}</small></span>
        ${bar(p.progress, p.blocked ? 'bad' : '')}
        <span class="dash-pill${p.blocked ? ' is-bad' : p.in_progress ? ' is-accent' : ''}">${p.blocked ? `${p.blocked} blocked` : p.in_progress ? `${p.in_progress} active` : `${Math.round(p.progress * 100)}%`}</span>
      </div>`).join('') || sectionError(hub) || '<p class="dash-empty">No projects with work items yet.</p>';
    const sch = data.schedules || {};
    const failing = (sch.failing || []).map((f) => `<div class="dash-row is-alert"><span class="dash-dot is-bad"></span><span class="dash-row-main"><strong>${esc(f.name)}</strong><small title="${esc(f.error)}">${esc(f.profile)} · ${esc(f.error || 'failed')}</small></span></div>`).join('');
    const upcoming = (sch.upcoming || []).map((u) => `<div class="dash-row"><span class="dash-dot"></span><span class="dash-row-main"><strong>${esc(u.name)}</strong><small>${esc(u.profile)} · next ${esc(String(u.next_run_at || '').replace('T', ' ').slice(0, 16))}</small></span></div>`).join('');
    const schedules = sectionError(sch) || `${sch.failing_count ? `<p class="dash-callout is-bad">${plural(sch.failing_count, 'scheduled job')} failing</p>` : ''}${failing}${upcoming || (failing ? '' : `<p class="dash-empty">${sch.enabled ? 'No upcoming runs.' : 'No scheduled jobs are switched on.'}</p>`)}`;
    const notes = Array.isArray(data.notes) ? (data.notes.map((n) => `<button type="button" class="dash-row dash-nav" data-dash-note="${esc(n.id)}"><span class="dash-row-main"><strong>${n.pinned ? '📌 ' : ''}${esc(n.title)}</strong><small>${ago(n.updated_at)}</small></span></button>`).join('') || '<p class="dash-empty">No notes yet.</p>') : sectionError(data.notes);
    return `${stats}
      <div class="dash-grid is-wide-left is-personal-focus">
        ${questStrip(data.quests, 'personal')}
        ${habitsCard(data.habits)}
      </div>
      <div class="dash-grid">
        ${learningCard(data.learning)}
        ${card('Project health', projects, {pix: 'project-health', key: 'project-health'})}
      </div>
      <div class="dash-grid">
        ${card('Scheduled jobs', schedules, {pix: 'scheduled-jobs', key: 'schedules', action: link('Open Tasks', 'data-dash-go="tasks"')})}
        ${card('Recent notes', notes, {pix: 'recent-notes', key: 'notes', action: link('Open Notes', 'data-dash-go="notebook"')})}
      </div>`;
  }

  // Skills gained (courses, bootcamps, certifications...): they feed the
  // resume and the Career realm. One choice sets the kind and its XP.
  const SKILL_KINDS = [['course', 'Online course', 40], ['bootcamp', 'Bootcamp', 80], ['certification', 'Certification', 100], ['project', 'Project', 30], ['work', 'On the job', 30], ['self', 'Self-taught', 20]];
  function skillsCard(data) {
    if (data && data.error) return card('Skills gained', sectionError(data), {pix: 'gambling', key: 'skills'});
    const entries = (data && data.entries) || [];
    const label = Object.fromEntries(SKILL_KINDS.map(([k, l]) => [k, l]));
    const rows = entries.map((e) => `<div class="dash-row"><span class="dash-skill-gem" aria-hidden="true"></span><span class="dash-row-main"><strong>${esc(e.name)}</strong><small>${esc(label[e.kind] || e.kind)} · ${ago(e.created_at)}</small></span><span class="dash-xp-gain">+${e.xp} XP</span><button type="button" class="dash-icon-btn" data-skill-remove="${esc(e.id)}" aria-label="Remove ${esc(e.name)}" title="Remove">${svg('x', 13)}</button></div>`).join('');
    const form = `<form class="dash-inline-form is-learning is-skills" data-form="skill">
        <input name="name" type="text" maxlength="80" placeholder="What skills did you learn?" required autocomplete="off">
        <select name="kind" aria-label="Type">${SKILL_KINDS.map(([k, l, xp]) => `<option value="${k}">${l} · ${xp} XP</option>`).join('')}</select>
        <button type="submit" class="dash-btn is-small">Add Skill</button>
      </form>`;
    return card(`Skills gained${data && data.total ? ` · ${data.total}` : ''}`, `<div class="dash-learning-entries">${rows || '<p class="dash-empty">Skills from courses, bootcamps and certifications. They show in Resume Studio, and tailoring adds the ones a job asks for.</p>'}</div>${form}`, {pix: 'gambling', cls: 'is-learning-log is-skills-card', key: 'skills', action: link('Resume Studio', 'data-dash-go="jobs" data-jobs-view="resume-studio"')});
  }

  // ── Career ───────────────────────────────────────────────────────────────
  function career(data) {
    const jobs = data.jobs || {};
    const week = jobs.this_week || {};
    const funnel = jobs.funnel || [];
    const top = Math.max(1, ...funnel.map((f) => f.count || 0));
    const funnelRows = funnel.map((f) => `<div class="dash-row"><span class="dash-row-main"><strong>${esc(f.label)}</strong></span>${bar((f.count || 0) / top)}<span class="dash-num">${f.count || 0}</span></div>`).join('');
    const weekRows = [['found', 'Scout finds'], ['tailored', 'Resumes tailored'], ['applied', 'Applications sent'], ['interview', 'Interviews'], ['rejected', 'Rejections']]
      .map(([k, label]) => `<div class="dash-row"><span class="dash-row-main"><strong>${label}</strong></span><span class="dash-num">${week[k] || 0}</span></div>`).join('');
    const jobsBody = jobs.error ? sectionError(jobs) : `<div class="dash-stats">
        ${stat('Jobs tracked', jobs.total_jobs || 0, '', '', 'funnel', 'funnel')}
        ${stat('Active work', jobs.active_work || 0, '', '', 'career-quests', 'funnel')}
        ${stat('Needs attention', jobs.needs_attention || 0, '', jobs.needs_attention ? 'bad' : '', 'project-health', 'funnel')}
        ${stat('Applied this week', week.applied || 0, '', week.applied ? 'good' : '', 'this-week', 'this-week')}
      </div>`;
    return `${jobsBody}
      <div class="dash-grid">
        ${questStrip(data.quests, 'career')}
        ${skillsCard(data.skills)}
      </div>
      <div class="dash-grid is-wide-left">
        ${card('Funnel', funnelRows || '<p class="dash-empty">No jobs yet.</p>', {pix: 'funnel', key: 'funnel', action: link('Open Jobs', 'data-dash-go="jobs"')})}
        ${card('This week', weekRows, {pix: 'this-week', key: 'this-week'})}
      </div>`;
  }

  // ── Business ─────────────────────────────────────────────────────────────
  function connectPanel(status) {
    const platforms = (status && status.platforms) || [{key: 'lemonsqueezy', label: 'Lemon Squeezy'}, {key: 'gumroad', label: 'Gumroad'}];
    return `<section class="dash-card dash-connect">
      <div class="dash-connect-copy">
        <span class="dash-empty-icon" aria-hidden="true">${svg('link', 26)}</span>
        <div><h3>Connect your sales platform</h3>
        <p>Sales flow in every few minutes and drive your goals, milestones and Business XP. Your key is checked with the platform, kept in your profile's private env file and never shown again. Start with a <strong>test-mode</strong> key: test sales show here but never unlock rewards.</p></div>
      </div>
      <form class="dash-inline-form is-connect" data-form="connect">
        <select name="platform" aria-label="Platform">${platforms.map((p) => `<option value="${esc(p.key)}">${esc(p.label)}</option>`).join('')}</select>
        <input name="key" type="password" autocomplete="off" placeholder="API key / access token" required>
        <span class="dash-cta-host" data-ld-beam="pulse-inner"><button type="submit" class="dash-btn">Connect</button></span>
      </form>
      ${status && status.last_error ? `<p class="dash-callout is-bad">${esc(status.last_error)}</p>` : ''}
      <p class="dash-hint">Lemon Squeezy: Settings → API → new key. Gumroad: Settings → Advanced → Applications → generate an access token. No platform yet? Add sales by hand on the Business page.</p>
    </section>`;
  }

  function business(data) {
    const s = data.sales || {};
    if (s.error) return `${sectionError(s)}${questStrip(data.quests, 'business')}`;
    const status = s.status || {};
    const cur = s.currency || 'USD';
    const t = s.totals || {};
    const delta = t.last_month_revenue ? Math.round(((t.month_revenue - t.last_month_revenue) / t.last_month_revenue) * 100) : null;
    const statusBar = status.connected ? `<div class="dash-connection">
        <span class="dash-dot is-good"></span><strong>${esc(status.label)}</strong>${status.account ? `<span>· ${esc(status.account)}</span>` : ''}
        ${status.test_mode ? '<span class="dash-pill is-warn">Test mode</span>' : ''}
        <span class="dash-connection-sync">${status.last_error ? `<span class="dash-bad-text" title="${esc(status.last_error)}">Last sync failed</span>` : `Synced ${ago(status.last_sync_at) || 'never'}`}</span>
        ${btn('', 'data-sales-sync aria-label="Sync now" title="Sync now"', {icon: 'refresh', cls: 'is-small is-ghost'})}
        ${link('Disconnect', 'data-sales-disconnect')}
      </div>` : `<button type="button" class="dash-connect-hint dash-nav" data-dash-tab="settings"><span class="dash-dot"></span><span><strong>No sales platform connected.</strong> Connect Lemon Squeezy or Gumroad in Settings, or add sales by hand below.</span><span class="dash-connect-go">Settings →</span></button>`;
    const stats = `<div class="dash-stats">
      ${stat('Revenue this month', esc(money(t.month_revenue, cur)), delta == null ? '' : `${delta >= 0 ? '▲' : '▼'} ${Math.abs(delta)}% vs last month`, delta > 0 ? 'good' : '', 'revenue', 'revenue')}
      ${stat('MRR', esc(money(t.mrr, cur)), t.subscribers ? plural(t.subscribers, 'subscriber') : '', '', 'road-to-10k', 'road')}
      ${stat('Sales this week', t.week_sales || 0, `${t.sales || 0} all time`, '', 'recent-sales', 'recent-sales')}
      ${stat('Customers', t.customers || 0, t.refunds ? plural(t.refunds, 'refund') : '', '', 'goals', 'milestones')}
    </div>`;
    const goalForm = state.forms.goal ? `<form class="dash-inline-form" data-form="goal">
        <input name="target" type="number" min="1" step="any" placeholder="5" required aria-label="Target">
        <select name="metric" aria-label="What"><option value="sales">sales</option><option value="revenue">in revenue (${esc(cur)})</option></select>
        <select name="period" aria-label="Per"><option value="week">per week</option><option value="month">per month</option></select>
        <select name="project_id" aria-label="Project"><option value="">No project</option>${(s.projects || []).map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('')}</select>
        <button type="submit" class="dash-btn is-small">Add</button><button type="button" class="dash-link" data-form-cancel="goal">Cancel</button>
      </form>` : '';
    const goals = (s.goals || []).map((g) => {
      const label = g.metric === 'sales' ? `${g.target} sales this ${g.period}` : `${money(g.target, cur)} this ${g.period}`;
      const value = g.metric === 'sales' ? `${g.value} / ${g.target}` : `${money(g.value, cur)} / ${money(g.target, cur)}`;
      return `<div class="dash-goal${g.met ? ' is-met' : ''}"><div class="dash-goal-head"><strong>${esc(label)}</strong>${g.project ? `<span class="dash-area-tag is-project">${esc(g.project)}</span>` : ''}<span class="dash-pill${g.met ? ' is-good' : ' is-accent'}">${g.met ? '✓ Met' : esc(value)}</span><button type="button" class="dash-icon-btn" data-goal-remove="${esc(g.id)}" aria-label="Remove goal" title="Remove goal">${svg('x', 13)}</button></div>${bar(g.progress, g.met ? 'good' : '')}${g.streak ? `<small class="dash-goal-streak">🔥 ${g.streak} ${g.period}${g.streak === 1 ? '' : 's'} in a row</small>` : ''}</div>`;
    }).join('') || (state.forms.goal ? '' : '<p class="dash-empty">Set a target, like 5 sales this week, and build a streak.</p>');
    const newest = (s.milestones || []).filter((m) => m.unlocked_at).sort((a, b) => b.unlocked_at - a.unlocked_at)[0];
    const milestones = (s.milestones || []).map((m) => `<div class="dash-badge${m.unlocked_at ? '' : ' is-locked'}" title="${esc(m.description)}">
        <span class="dash-badge-icon">${svg(m.unlocked_at ? 'trophy' : 'star', 18)}</span><strong>${esc(m.title)}</strong>
        ${newest && newest.key === m.key && m.new ? '<span class="dash-new" data-ld="metal-badge">New</span>' : `<small>${m.unlocked_at ? ago(m.unlocked_at) : 'Locked'}</small>`}
      </div>`).join('');
    const road = s.road || {checkpoints: []};
    const marks = road.checkpoints || [];
    const step = marks.length > 1 ? 100 / (marks.length - 1) : 100;
    // Checkpoints sit evenly along the road; the fill moves between the two around the current MRR.
    const mrr = road.mrr || 0;
    const at = Math.min(marks.length - 1, road.reached || 0);
    const nextMark = marks[at + 1];
    const along = nextMark == null ? 100 : (at + Math.min(1, (mrr - marks[at]) / Math.max(1, nextMark - marks[at]))) * step;
    const roadHtml = `<div class="dash-road"><div class="dash-road-track"><i style="width:${along.toFixed(1)}%"></i></div>
        ${marks.map((c, i) => `<span class="dash-road-node${mrr >= c ? ' is-done' : ''}" style="left:${(i * step).toFixed(1)}%"><small>${c ? esc(money(c, cur)) : 'Start'}</small></span>`).join('')}
      </div><p class="dash-hint">${road.next ? `${esc(money(road.next - (road.mrr || 0), cur))} more to the next checkpoint.` : 'You reached the end of the road. Legendary.'}</p>`;
    const months = s.months || [];
    const topMonth = Math.max(1, ...months.map((m) => m.revenue));
    const chart = `<div class="dash-chart">${months.map((m) => `<div class="dash-chart-col" title="${esc(m.label)}: ${esc(money(m.revenue, cur))}"><span class="dash-chart-val">${m.revenue ? esc(money(m.revenue, cur)) : ''}</span><i class="${m.revenue ? '' : 'is-zero'}" style="height:${m.revenue ? Math.max(4, Math.round(m.revenue / topMonth * 100)) : 2}%"></i><small>${esc(m.label)}</small></div>`).join('')}</div>`;
    const saleForm = state.forms.sale ? `<form class="dash-inline-form" data-form="sale">
        <input name="amount" type="number" min="0.01" step="0.01" placeholder="29.00" required aria-label="Amount">
        <input name="product" type="text" maxlength="120" placeholder="Product" aria-label="Product">
        <input name="date" type="hidden" value=""><button type="button" class="dash-date-btn" data-date-pick aria-haspopup="dialog" aria-label="Sale date">${svg('calendar', 14)}<span>Today</span></button>
        <label class="dash-check-label"><input name="recurring" type="checkbox"> Monthly</label>
        <button type="submit" class="dash-btn is-small">Add</button><button type="button" class="dash-link" data-form-cancel="sale">Cancel</button>
      </form>` : '';
    const recent = (s.recent || []).map((r) => `<div class="dash-row"><span class="dash-dot${r.refunded ? ' is-bad' : ' is-good'}"></span><span class="dash-row-main"><strong>${esc(r.product || 'Sale')}${r.recurring ? ' · monthly' : ''}${r.test ? ' · test' : ''}</strong><small>${esc(r.platform === 'manual' ? 'Added by hand' : r.platform)} · ${ago(r.created_at)}</small></span><span class="dash-num${r.refunded ? ' dash-bad-text' : ''}">${r.refunded ? '−' : ''}${esc(money(r.amount, r.currency))}</span>${r.platform === 'manual' ? `<button type="button" class="dash-icon-btn" data-sale-remove="${esc(r.id)}" aria-label="Remove" title="Remove">${svg('x', 13)}</button>` : ''}</div>`).join('') || (state.forms.sale ? '' : '<p class="dash-empty">No sales yet. Your first one unlocks a milestone.</p>');
    return `${statusBar}${stats}
      <div class="dash-grid">
        ${card('Goals', `${goalForm}<div class="dash-goals">${goals}</div>`, {pix: 'goals', key: 'goals', action: state.forms.goal || (s.goals || []).length >= (s.goal_limit || 12) ? '' : btn('Goal', 'data-form-open="goal"', {icon: 'plus', cls: 'is-small'})})}
        ${card('Road to $10k', roadHtml, {pix: 'road-to-10k', key: 'road'})}
      </div>
      ${card(`Milestones · ${(s.milestones || []).filter((m) => m.unlocked_at).length}/${(s.milestones || []).length}`, `<div class="dash-badges">${milestones}</div>`, {pix: 'milestone', key: 'milestones'})}
      <div class="dash-grid">
        ${card('Revenue · 6 months', chart, {pix: 'revenue', key: 'revenue'})}
        ${card('Recent sales', `${saleForm}${recent}`, {pix: 'recent-sales', key: 'recent-sales', action: state.forms.sale ? '' : btn('Sale', 'data-form-open="sale"', {icon: 'plus', cls: 'is-small'})})}
      </div>
      ${questStrip(data.quests, 'business')}`;
  }

  // ── Settings ─────────────────────────────────────────────────────────────
  function settingsView(data) {
    const status = data.sales_status || {};
    if (status.error) return sectionError(status);
    const connected = status.connected ? `<div class="dash-connection">
        <span class="dash-dot is-good"></span><strong>${esc(status.label)}</strong>${status.account ? `<span>· ${esc(status.account)}</span>` : ''}
        ${status.test_mode ? '<span class="dash-pill is-warn">Test mode</span>' : ''}
        <span class="dash-connection-sync">${status.last_error ? `<span class="dash-bad-text" title="${esc(status.last_error)}">Last sync failed</span>` : `Synced ${ago(status.last_sync_at) || 'never'}`}</span>
        ${btn('', 'data-sales-sync aria-label="Sync now" title="Sync now"', {icon: 'refresh', cls: 'is-small is-ghost'})}
        ${btn('Disconnect', 'data-sales-disconnect', {cls: 'is-small is-danger'})}
      </div>` : '';
    const cats = (data.projects || []).map((pr) => `<div class="dash-row"><span class="dash-row-main"><strong>${esc(pr.name)}</strong></span><select class="dash-select" data-project-category="${esc(pr.project_id)}" aria-label="Realm for ${esc(pr.name)}">${Object.keys(AREA).map((k) => `<option value="${k}"${pr.category === k ? ' selected' : ''}>${AREA[k]}</option>`).join('')}</select></div>`).join('') || '<p class="dash-empty">No projects yet.</p>';
    const realms = Array.isArray(data.projects) ? card('Project realms', `<p class="dash-hint">Which realm each project's finished tasks count towards.</p>${cats}`, {pix: 'realms', key: 'realms'}) : sectionError(data.projects);
    return `${status.connected ? card('Sales platform', `<p class="dash-hint">Connected. Sales are copied in every few minutes and drive Business goals, milestones and XP.</p>${connected}`, {icon: 'link'}) : connectPanel(status)}${realms}`;
  }

  // ── Character (RPG) ──────────────────────────────────────────────────────
  const STATS = ['STR', 'INT', 'CHA', 'VIT', 'DEX'];
  function radar(stats) {
    const max = Math.max(10, ...STATS.map((k) => (stats[k] || {}).value || 0));
    const c = 80, r = 58, n = STATS.length;
    const point = (i, f) => { const a = -Math.PI / 2 + i * 2 * Math.PI / n; return [c + Math.cos(a) * r * f, c + Math.sin(a) * r * f]; };
    const ring = (f) => STATS.map((_, i) => point(i, f).map((v) => v.toFixed(1)).join(',')).join(' ');
    const shape = STATS.map((k, i) => point(i, Math.max(0.06, ((stats[k] || {}).value || 0) / max)).map((v) => v.toFixed(1)).join(',')).join(' ');
    const labels = STATS.map((k, i) => { const [x, y] = point(i, 1.27); return `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" text-anchor="middle" dominant-baseline="middle">${k}</text>`; }).join('');
    return `<svg class="rpg-radar" viewBox="0 0 160 160" role="img" aria-label="Attributes: ${STATS.map((k) => `${k} ${(stats[k] || {}).value || 1}`).join(', ')}">
      ${[0.33, 0.66, 1].map((f) => `<polygon points="${ring(f)}" class="rpg-radar-ring"/>`).join('')}
      ${STATS.map((_, i) => { const [x, y] = point(i, 1); return `<line x1="${c}" y1="${c}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" class="rpg-radar-ring"/>`; }).join('')}
      <polygon points="${shape}" class="rpg-radar-shape"/>${labels}</svg>`;
  }
  const panel = (title, body, {icon = '', pix = '', action = '', cls = ''} = {}) =>
    `<section class="rpg-panel ${cls}"><header class="rpg-panel-head">${pix ? `<span class="rpg-panel-icon is-pixel">${PIX(pix)}</span>` : icon ? `<span class="rpg-panel-icon">${svg(icon, 15)}</span>` : ''}<h3>${title}</h3>${action ? `<span class="rpg-panel-actions">${action}</span>` : ''}</header><div class="dash-card-body">${body}</div></section>`;

  // Total XP needed to reach ``level`` (level n takes 100 + 25(n-1) XP).
  const xpToReach = (level) => { let total = 0; for (let n = 1; n < level; n++) total += 100 + 25 * (n - 1); return total; };
  // One evolution at a time, stepped with the arrows; forms not reached yet
  // are greyed and chained.
  function evolutionView(data) {
    const tiers = data.tiers || [];
    if (!tiers.length) return '';
    const current = Math.max(0, (data.tier || 1) - 1);
    const i = Math.max(0, Math.min(tiers.length - 1, state.evoIndex == null ? current : state.evoIndex));
    const t = tiers[i];
    const locked = data.level < t.level;
    const status = i === current ? 'Current form' : locked ? `Unlocks at Lv ${t.level}` : 'Unlocked';
    const togo = locked ? Math.max(0, xpToReach(t.level) - (data.total_xp || 0)) : 0;
    const dots = tiers.map((_, n) => `<i class="${n === i ? 'on' : ''}${data.level >= tiers[n].level ? ' is-reached' : ''}"></i>`).join('');
    return `<div class="rpg-evo-head"><span>Evolution</span><small>${i + 1} / ${tiers.length}</small></div>
      <div class="rpg-evo-stage">
        <button type="button" class="rpg-evo-arrow" data-evo-step="-1" aria-label="Previous form"${i === 0 ? ' disabled' : ''}>${svg('chevron-left', 14)}</button>
        <div class="rpg-evo-art${locked ? ' is-locked' : ''}${i === current ? ' is-current' : ''}" role="img" aria-label="${esc(t.name)}${locked ? ', locked' : ''}">${window.DashSprite.render(i + 1, 4)}</div>
        <button type="button" class="rpg-evo-arrow" data-evo-step="1" aria-label="Next form"${i === tiers.length - 1 ? ' disabled' : ''}>${svg('chevron-right', 14)}</button>
      </div>
      <strong class="rpg-evo-name">${esc(t.name)}</strong>
      <small class="rpg-evo-status">${esc(status)}${togo ? ` · ${togo.toLocaleString()} XP to go` : ''}</small>
      <div class="rpg-evo-dots" aria-hidden="true">${dots}</div>`;
  }

  function characterView(data) {
    if (!window.DashSprite) return '<p class="dash-empty">Loading the character…</p>';
    const stats = data.stats || {};
    // Attributes as bars against the strongest one (at least 10), so growth shows.
    const statTop = Math.max(10, ...STATS.map((k) => Number((stats[k] || {}).value) || 1));
    const statRows = STATS.map((k) => { const st = stats[k] || {}; const v = Number(st.value) || 1;
      return `<div class="rpg-stat" title="${esc(st.hint || '')}"><strong>${k}</strong><small>${esc(st.label || '')}</small><span class="rpg-stat-bar" aria-hidden="true"><i style="width:${Math.round(v / statTop * 100)}%"></i></span><b>${esc(v)}</b></div>`; }).join('');
    const segments = 20;
    const filled = Math.round((data.progress || 0) * segments);
    const xpbar = `<div class="rpg-xpbar" role="progressbar" aria-valuemin="0" aria-valuemax="${data.level_size}" aria-valuenow="${data.into_level}" aria-label="Experience">${Array.from({length: segments}, (_, i) => `<i class="${i < filled ? 'on' : ''}"></i>`).join('')}</div>`;
    const gold = ((data.shop || {}).gold || {}).balance || 0;
    // One tile per agent profile, two to a row; read on every refresh, so a
    // profile added, renamed or removed shows on the next one.
    const party = (data.party || []).map((m, i) => `<div class="rpg-member${m.busy ? ' is-busy' : ''}">
        <span class="rpg-member-avatar" data-ld="bot" data-type="${BOT_TYPES[i % BOT_TYPES.length]}" data-state="${m.busy ? 'working' : 'default'}"></span>
        <span class="dash-row-main"><strong>${esc(m.name)}</strong><small>${m.busy ? `On a quest · ${plural(m.busy, 'chat')}` : esc(m.model || 'Resting')}</small></span>
        ${m.busy ? '<span class="dash-pill is-accent">Busy</span>' : ''}
      </div>`).join('') || '<p class="dash-empty">No agent profiles yet.</p>';
    const achievements = data.achievements || [];
    const newest = achievements.filter((a) => a.unlocked_at).sort((a, b) => b.unlocked_at - a.unlocked_at)[0];
    const achHtml = achievements.map((a) => `<div class="rpg-ach${a.unlocked_at ? '' : ' is-locked'}" title="${esc(a.description)}">
        <span class="rpg-ach-icon" aria-hidden="true">${esc(a.icon)}</span><strong>${esc(a.title)}</strong>
        ${newest && newest.key === a.key && a.new ? '<span class="dash-new" data-ld="metal-badge">New</span>' : `<small>${a.unlocked_at ? ago(a.unlocked_at) : esc(a.description)}</small>`}
      </div>`).join('');
    const shop = data.shop || {rewards: [], history: []};
    const rewardForm = state.forms.reward ? `<form class="dash-inline-form" data-form="reward">
        <input name="icon" type="text" maxlength="4" placeholder="🎮" aria-label="Icon" class="is-icon">
        <input name="name" type="text" maxlength="120" placeholder="1 hour of gaming" required aria-label="Reward">
        <input name="cost" type="number" min="1" step="1" placeholder="200" required aria-label="Cost in gold" class="is-cost">
        <button type="submit" class="dash-btn is-small">Add</button><button type="button" class="dash-link" data-form-cancel="reward">Cancel</button>
      </form>` : '';
    const rewards = (shop.rewards || []).map((r) => `<div class="rpg-reward${gold >= r.cost ? '' : ' is-short'}">
        <span class="rpg-reward-icon" aria-hidden="true">${esc(r.icon || '🎁')}</span><span class="dash-row-main"><strong>${esc(r.name)}</strong><small>${gold >= r.cost ? 'Affordable' : `${r.cost - gold} gold short`}</small></span>
        <button type="button" class="rpg-buy" data-reward-redeem="${esc(r.id)}"${gold >= r.cost ? '' : ' disabled'}><span class="rpg-coin" aria-hidden="true"></span>${r.cost}</button>
        <button type="button" class="dash-icon-btn" data-reward-remove="${esc(r.id)}" aria-label="Remove reward" title="Remove reward">${svg('x', 13)}</button>
      </div>`).join('') || (state.forms.reward ? '' : '<p class="dash-empty">Add treats you can buy with gold: you earn half your XP as gold, plus 50 per achievement.</p>');
    const history = (shop.history || []).slice(0, 4).map((h) => `<li>${esc(h.name)} <small>−${h.cost} · ${ago(h.at)}</small></li>`).join('');
    const areas = (data.areas || []).map((a) => `<div class="dash-row"><span class="dash-area-dot is-${a.key}"></span><span class="dash-row-main"><strong>${esc(AREA[a.key])} · Lv ${a.level}</strong><small>${a.xp} XP · ${plural(a.tasks, 'deed')}</small></span>${bar(a.progress)}</div>`).join('');
    const filter = state.logCategory || 'all';
    const chips = ['all', 'personal', 'career', 'business'].map((k) => `<button type="button" class="dash-chip${filter === k ? ' on' : ''}" data-log-filter="${k}">${k === 'all' ? 'All' : AREA[k]}</button>`).join('');
    const log = (data.log || []).map((e) => `<div class="dash-row rpg-log-row"><span class="dash-area-dot is-${esc(e.category)}"></span><span class="dash-row-main"><strong>${e.quest ? '⚔ ' : ''}${esc(e.title)}</strong><small>${esc(AREA[e.category] || e.category)} · ${ago(e.at)}</small></span><span class="dash-xp-gain">+${e.xp} XP</span></div>`).join('') || '<p class="dash-empty">Finish a Work Hub item, tick a habit or move a job forward to earn your first XP.</p>';
    const more = data.log_total > (data.log || []).length ? link('Show more', 'data-log-more') : '';
    const toNext = data.level_size - data.into_level;
    return `<div class="rpg">
      <div class="rpg-hero">
        <div class="rpg-stage" data-tier="${data.tier}">
          <i class="rpg-frame-gem is-top" aria-hidden="true"></i><i class="rpg-frame-gem is-bottom" aria-hidden="true"></i><i class="rpg-frame-gem is-left" aria-hidden="true"></i><i class="rpg-frame-gem is-right" aria-hidden="true"></i>
          <div class="rpg-stars" aria-hidden="true"></div>
          <div class="rpg-aura" aria-hidden="true"></div>
          ${window.DashSprite.render(data.tier, 6)}
          <div class="rpg-plate"><span class="rpg-plate-level">LV ${data.level}</span><span class="rpg-plate-class">${esc(data.tier_name)} Warlock</span></div>
        </div>
        <div class="rpg-sheet rpg-panel">
          <div class="rpg-title"><h2><span data-ld="metal-text" data-text="Level ${data.level}">Level ${data.level}</span></h2><span class="rpg-rank">${esc(data.tier_name)}</span><span class="rpg-gold" title="Gold"><span class="rpg-coin" aria-hidden="true"></span>${gold.toLocaleString()}</span></div>
          ${xpbar}
          <div class="rpg-xpline"><span>${data.into_level} / ${data.level_size} XP</span><span>${toNext} XP to level ${data.level + 1}${data.next_tier ? ` · ${esc(data.next_tier.name)} at ${data.next_tier.level}` : ''}</span></div>
          <div class="rpg-body">${radar(stats)}<div class="rpg-stats">${statRows}</div><div class="rpg-evo" data-evo>${evolutionView(data)}</div></div>
          <div class="rpg-badges">
            <div><span class="rpg-badge-icon">${PIX('this-week')}</span><span class="rpg-badge-copy"><b>${data.streak}</b><small>day streak</small></span></div>
            <div><span class="rpg-badge-icon">${PIX('party')}</span><span class="rpg-badge-copy"><b>${(data.total_xp || 0).toLocaleString()}</b><small>total XP</small></span></div>
            <div><span class="rpg-badge-icon">${PIX('milestone')}</span><span class="rpg-badge-copy"><b>+${data.xp_this_week}</b><small>XP this week</small></span></div>
            <div><span class="rpg-badge-icon">${PIX('quest-log')}</span><span class="rpg-badge-copy"><b>${data.quests_done}</b><small>quests done</small></span></div>
          </div>
        </div>
      </div>
      <div class="rpg-columns">
        <div class="rpg-col">
          ${panel(`Achievements · ${achievements.filter((a) => a.unlocked_at).length}/${achievements.length}`, `<div class="rpg-achs">${achHtml}</div>`, {pix: 'achievements'})}
          ${panel('Chronicle', `<div class="dash-chips">${chips}</div>${log}${more}`, {pix: 'chronicle'})}
        </div>
        <div class="rpg-col">
          ${panel('Party', `<div class="rpg-party">${party}</div>`, {pix: 'party'})}
          ${panel('Treasury', `<div class="rpg-purse"><span class="rpg-coin is-big" aria-hidden="true"></span><b>${gold.toLocaleString()}</b><small>gold · ${(((shop.gold || {}).earned) || 0).toLocaleString()} earned</small></div>${rewardForm}<div class="rpg-rewards">${rewards}</div>${history ? `<ul class="rpg-history">${history}</ul>` : ''}`, {pix: 'treasury', action: state.forms.reward ? '' : btn('Reward', 'data-form-open="reward"', {icon: 'plus', cls: 'is-small is-gold'})})}
          ${panel('Realms', areas, {pix: 'realms'})}
        </div>
      </div>
    </div>`;
  }

  // ── Libraries.dev effects ────────────────────────────────────────────────
  function clearEffects() { while (effects.length) { try { effects.pop().unmount(); } catch (_) {} } }
  async function enhance(host) {
    if (typeof window.loadLibrariesDev !== 'function') return;
    if (!host.querySelector('[data-ld],[data-ld-beam]')) return;
    let lib;
    try { lib = await window.loadLibrariesDev(); } catch (_) { return; }
    if (!host.isConnected) return;
    const theme = isDark() ? 'dark' : 'light';
    const reduced = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    const claim = (el) => { if (!el.isConnected || el.dataset.ldOn) return false; el.dataset.ldOn = '1'; return true; };
    host.querySelectorAll('[data-ld="orb"]').forEach((el) => {
      if (!claim(el)) return;
      const slot = document.createElement('span'); slot.className = 'dash-orb-slot';
      el.replaceChildren(slot);
      try { effects.push(lib.mount(slot, 'ThinkingOrb', {state: el.dataset.state || 'working', size: 20, theme, paused: reduced})); } catch (_) {}
    });
    host.querySelectorAll('[data-ld="bot"]').forEach((el) => {
      if (!claim(el)) return;
      try { effects.push(lib.mount(el, 'BotAvatar', {type: el.dataset.type || 'clover', state: el.dataset.state || 'default', size: 48, paused: reduced})); } catch (_) {}
    });
    let metalOk = false;
    try { metalOk = typeof lib.isMetalFxSupported === 'function' ? lib.isMetalFxSupported() : false; } catch (_) {}
    if (metalOk && theme === 'dark') {
      host.querySelectorAll('[data-ld="metal-text"]').forEach((el) => {
        if (!claim(el)) return;
        const style = getComputedStyle(el);
        try { effects.push(lib.mount(el, 'MetalText', {children: el.dataset.text || el.textContent, font: `${style.fontWeight} ${style.fontSize}/1.15 ${style.fontFamily}`, color: '#E8E2FF'})); } catch (_) {}
      });
      host.querySelectorAll('[data-ld="metal-badge"]').forEach((el) => {
        if (!claim(el)) return;
        try { effects.push(lib.mount(el, 'MetalBadge', {children: el.textContent || 'New'})); } catch (_) {}
      });
    }
    host.querySelectorAll('[data-ld-beam]').forEach((el) => {
      if (!claim(el)) return;
      const size = el.dataset.ldBeam || 'md';
      try { effects.push(lib.wrap(el, 'BorderBeam', {size, theme, colorVariant: size === 'md' ? 'colorful' : 'mono', strength: size === 'md' ? 0.85 : 0.7, active: !reduced})); } catch (_) {}
    });
  }

  // ── loading and painting ─────────────────────────────────────────────────
  async function load(tab, {quiet = false, append = false} = {}) {
    // A reload asked for while one is in flight runs once it lands, so a
    // change made meanwhile (a quest finished, a habit ticked) is not lost.
    if (state.loading[tab]) { if (!append) (state.again || (state.again = {}))[tab] = true; return; }
    state.loading[tab] = true;
    if (!quiet) paint();
    try {
      if (tab === 'character') {
        const offset = append ? (state.logOffset || 0) + LOG_PAGE : 0;
        const cat = state.logCategory && state.logCategory !== 'all' ? state.logCategory : '';
        const data = await api(`/api/dashboard/character?category=${encodeURIComponent(cat)}&offset=${offset}`);
        if (append && state.data.character) data.log = (state.data.character.log || []).concat(data.log || []);
        state.logOffset = append ? offset : 0;
        state.data.character = data;
        celebrate(data);
      } else {
        state.data[tab] = await api(`/api/dashboard/summary?tab=${encodeURIComponent(tab)}`);
      }
      state.error[tab] = null;
    } catch (error) {
      state.error[tab] = (error && error.message) || 'Could not load the dashboard';
    } finally { state.loading[tab] = false; }
    if (state.mounted && state.tab === tab) paint();
    if (state.again && state.again[tab]) { state.again[tab] = false; load(tab, {quiet: true}); }
  }

  // A themed level-up card: the new level, the warlock, and a new form when
  // the level crossed a tier. Shown once per level reached on this browser.
  function celebrate(data, {force = false} = {}) {
    const level = data.level;
    let seen = 0;
    try { seen = parseInt(localStorage.getItem('hermes-dashboard-level') || '0', 10) || 0; localStorage.setItem('hermes-dashboard-level', String(level)); } catch (_) {}
    if (!force && (!seen || level <= seen)) return;
    const from = force ? Math.max(1, level - 1) : seen;
    const tiers = data.tiers || [];
    const tierAt = (lv) => tiers.reduce((n, t, i) => (lv >= t.level ? i + 1 : n), 1);
    const newForm = tierAt(level) > tierAt(from);
    document.querySelectorAll('.rpg-levelup').forEach((el) => el.remove());
    const overlay = document.createElement('div');
    overlay.className = 'rpg-levelup';
    const confetti = Array.from({length: 28}, (_, i) => `<i style="--x:${(i * 37) % 100}%;--d:${(i % 7) * 0.12}s;--r:${(i * 53) % 360}deg"></i>`).join('');
    overlay.innerHTML = `<div class="rpg-levelup-card" role="dialog" aria-modal="true" aria-label="Level up: level ${level}">
        <div class="rpg-levelup-rays" aria-hidden="true"></div><div class="rpg-levelup-confetti" aria-hidden="true">${confetti}</div>
        <small class="rpg-levelup-kicker">Level up!</small>
        <div class="rpg-levelup-levels"><span>${from}</span><i aria-hidden="true">▶</i><b>${level}</b></div>
        <div class="rpg-levelup-hero">${window.DashSprite ? window.DashSprite.render(data.tier || 1, 4) : ''}</div>
        <strong class="rpg-levelup-class">${esc(data.tier_name || '')} Warlock</strong>
        ${newForm ? `<div class="rpg-levelup-unlock">New form unlocked: ${esc(data.tier_name || '')}</div>` : ''}
        <p class="rpg-levelup-next">${(data.level_size || 0).toLocaleString()} XP to level ${level + 1}</p>
        <button type="button" class="dash-btn" data-levelup-close>Continue</button>
      </div>`;
    const close = () => { overlay.classList.remove('is-open'); setTimeout(() => overlay.remove(), 250); document.removeEventListener('keydown', key); };
    const key = (event) => { if (event.key === 'Escape' || event.key === 'Enter') close(); };
    overlay.addEventListener('click', (event) => { if (event.target === overlay || event.target.closest('[data-levelup-close]')) close(); });
    document.addEventListener('keydown', key);
    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add('is-open'));
    const button = overlay.querySelector('[data-levelup-close]');
    setTimeout(() => button && button.focus(), 300);
  }

  function levelBadge() {
    let level = state.data.character && state.data.character.level;
    if (!level) { try { level = parseInt(localStorage.getItem('hermes-dashboard-level') || '0', 10) || 0; } catch (_) {} }
    return level ? `<span class="dash-level-badge">Lv ${level}</span>` : '';
  }
  function paintSidebar() {
    const host = sidebar(); if (!host) return;
    const item = (key, label) => `<button type="button" class="side-menu-item${key === state.tab ? ' active' : ''}" data-dash-tab="${key}"${key === state.tab ? ' aria-current="page"' : ''}>${svg(key)}<span class="side-menu-label">${label}</span>${key === 'character' ? levelBadge() : ''}</button>`;
    host.innerHTML = `<nav class="dash-side-nav">${item('character', 'Character')}<div class="dash-side-divider" aria-hidden="true"></div>${TABS.map((t) => item(t.key, t.label)).join('')}<div class="dash-side-divider" aria-hidden="true"></div>${item('settings', 'Settings')}</nav>`;
  }

  function paint({force = false} = {}) {
    paintSidebar();
    const host = root(); if (!host) return;
    const data = state.data[state.tab];
    // A refresh that brought nothing new leaves the page (and its live effects) alone.
    // generated_at changes on every read; it is not news, so it does not repaint.
    const signature = JSON.stringify([state.tab, data, state.error[state.tab], state.forms, state.logCategory], (key, value) => key === 'generated_at' ? undefined : value);
    if (!force && state.painted.signature === signature && host.firstChild) return;
    // Never pull a form out from under someone typing; the next refresh paints.
    if (!force && document.activeElement && host.contains(document.activeElement) && document.activeElement.closest('form')) return;
    state.painted.signature = signature;
    clearEffects();
    let body;
    if (!data && state.error[state.tab]) body = `<p class="dash-empty">${esc(state.error[state.tab])} <button type="button" class="dash-link" data-dash-retry>Retry</button></p>`;
    else if (!data) body = '<div class="dash-skeleton" aria-busy="true"><i></i><i></i><i></i><i></i></div>';
    else body = ({character: characterView, career, business, settings: settingsView, personal})[state.tab](data);
    const isChar = state.tab === 'character';
    const scroller = host.parentElement;
    const scroll = scroller ? scroller.scrollTop : 0;
    const entering = state.entering; state.entering = false;
    host.innerHTML = `<div class="dash is-rpg${isChar ? ' is-character' : ''}">
      <div class="dash-head"><div><h1>${esc(VIEW_TITLE[state.tab])}</h1></div>
        <div class="dash-head-right">
        <button type="button" class="dash-char-btn${isChar ? ' on' : ''}" data-dash-tab="character">${svg('character', 15)}<span>Character</span>${levelBadge()}</button>
        <div class="dash-tabs" role="tablist">${TABS.map((t) => `<button type="button" role="tab" data-dash-tab="${t.key}" aria-selected="${t.key === state.tab}" class="${t.key === state.tab ? 'on' : ''}"><span>${t.label}</span></button>`).join('')}</div></div>
      </div>
      <div class="dash-body${entering ? ' is-entering' : ''}" data-tab="${state.tab}">${body}</div>
    </div>`;
    if (scroller) scroller.scrollTop = scroll;
    const cadence = host.querySelector('[data-form="habit"] select[name=cadence]');
    enhance(host);
    if (cadence) {
      // The themed select's wrapper hides with it (CSS :has(> select[hidden])).
      const target = host.querySelector('[data-weekly-target]');
      const show = () => { target.hidden = cadence.value !== 'weekly'; };
      cadence.addEventListener('change', show); show();
    }
    markScrollable(host);
  }

  // A card whose list scrolls shows a small arrow at its bottom edge while
  // more rows are hidden below; it goes once the list is scrolled to the end.
  const SCROLLERS = '.dash-card-body,.dash-learning-entries';
  function updateMore(el) {
    const card = el.closest('.dash-card,.rpg-panel');
    if (!card) return;
    const more = el.scrollHeight - el.clientHeight - el.scrollTop > 4 && getComputedStyle(el).overflowY !== 'visible';
    let arrow = card.querySelector(':scope > .dash-more');
    if (more && !arrow) {
      arrow = document.createElement('span');
      arrow.className = 'dash-more'; arrow.setAttribute('aria-hidden', 'true');
      card.appendChild(arrow);
    }
    if (!arrow) return;
    arrow.classList.toggle('is-on', more);
    // Sit at the bottom of the list itself (above a footer form, if any).
    const c = card.getBoundingClientRect(), r = el.getBoundingClientRect();
    arrow.style.top = Math.round(r.bottom - c.top - parseFloat(getComputedStyle(card).borderTopWidth) - 9) + 'px';
  }
  function markScrollable(host) {
    requestAnimationFrame(() => { host.querySelectorAll(SCROLLERS).forEach(updateMore); fitAchievements(host); });
  }
  // Achievement tiles are one fixed height; a long title or description
  // steps its type down until the tile's text fits.
  function fitAchievements(host) {
    host.querySelectorAll('.rpg-ach').forEach((tile) => {
      const parts = [...tile.querySelectorAll('strong,small')];
      parts.forEach((el) => { el.style.fontSize = ''; });
      let step = 0;
      while (tile.scrollHeight > tile.clientHeight + 1 && step < 6) {
        step += 1;
        parts.forEach((el) => { el.style.fontSize = `${parseFloat(getComputedStyle(el).fontSize) - 1}px`; });
      }
    });
  }

  function select(tab) {
    if (!VIEWS.includes(tab)) return;
    const changed = tab !== state.tab;
    state.tab = tab; saveTab(tab);
    state.forms = {};
    if (changed) state.entering = true;
    paint({force: true});
    if (changed || !state.data[tab]) load(tab, {quiet: !!state.data[tab]});
  }
  const refresh = () => load(state.tab, {quiet: true});

  // ── quest picker ─────────────────────────────────────────────────────────
  // ``area`` is the tab the picker was opened from: the quests it adds show
  // (and earn XP) there, whatever their project's realm.
  async function openQuestPicker(area) {
    closeQuestPicker();
    area = AREA[area] ? area : '';
    const overlay = document.createElement('div');
    overlay.className = 'dash-picker-overlay';
    overlay.innerHTML = `<div class="dash-picker" role="dialog" aria-modal="true" aria-label="Choose quests">
      <header><h3>Choose ${area ? esc(AREA[area]) + ' ' : ''}quests</h3><button type="button" class="dash-picker-x" data-picker-close aria-label="Close">${svg('x', 16)}</button></header>
      <div class="dash-picker-tools"><label class="dash-picker-search">${svg('search', 15)}<input type="text" placeholder="Search Work Hub items" autocomplete="off" data-picker-search></label>
        <select class="dash-picker-filter" data-picker-filter aria-label="Show items from"><option value="">All folders</option></select></div>
      <div class="dash-picker-list" data-picker-list><div class="dash-skeleton is-list"><i></i><i></i><i></i></div></div>
      <footer><button type="button" class="dash-btn is-ghost" data-picker-close>Cancel</button><button type="button" class="dash-btn" data-picker-add disabled>Add quests</button></footer>
    </div>`;
    document.body.appendChild(overlay);
    const panel = overlay.querySelector('.dash-picker');
    const filter = overlay.querySelector('[data-picker-filter]');
    const search = overlay.querySelector('[data-picker-search]');
    // The panel opens and then grows to fit the list, moving as it does; a
    // dropdown opened mid-way would stay where its button was. Search and the
    // folder filter wait until the list has loaded and the panel has settled.
    const setReady = (on) => {
      search.disabled = !on; filter.disabled = !on;
      overlay.querySelector('.dash-picker-tools').classList.toggle('is-waiting', !on);
      if (window.refreshThemedSelect) window.refreshThemedSelect(filter);
    };
    if (window.enhanceThemedSelect) window.enhanceThemedSelect(filter);
    setReady(false);
    setTimeout(() => overlay.classList.add('is-open'), 16);
    // The panel grows from the loading skeleton to the full list: animate its
    // height between the two instead of jumping.
    const resize = (change, done = () => {}) => {
      const from = panel.getBoundingClientRect().height;
      change();
      if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) { done(); return; }
      panel.style.height = 'auto';
      const to = panel.getBoundingClientRect().height;
      if (Math.abs(to - from) < 2) { panel.style.height = ''; done(); return; }
      panel.style.height = from + 'px';
      void panel.offsetHeight;
      panel.classList.add('is-resizing');
      panel.style.height = to + 'px';
      clearTimeout(panel._resizeTimer);
      panel._resizeTimer = setTimeout(() => { panel.classList.remove('is-resizing'); panel.style.height = ''; done(); }, 320);
    };
    const opened = Date.now();
    const chosen = new Set();
    let items = [], names = {}, already = new Set();
    try {
      // Read fresh each time, so added or deleted project folders show at once.
      const [boot, ids] = await Promise.all([api('/api/work_hub/bootstrap'), api('/api/dashboard/quests')]);
      items = (boot.items || []).filter((i) => !['done', 'cancelled'].includes(i.status));
      (boot.projects || []).forEach((proj) => { names[proj.project_id] = proj.name; });
      already = new Set(ids.item_ids || []);
    } catch (error) {
      resize(() => { overlay.querySelector('[data-picker-list]').innerHTML = `<p class="dash-empty">Couldn't load the Work Hub: ${esc(error.message || error)}</p>`; });
      return;
    }
    if (!overlay.isConnected) return;
    const folders = Object.entries(names).sort((a, b) => String(a[1]).localeCompare(String(b[1])));
    filter.innerHTML = `<option value="">All folders</option><option value="__general">General</option>${folders.map(([id, name]) => `<option value="${esc(id)}">${esc(name)}</option>`).join('')}`;
    if (window.refreshThemedSelect) window.refreshThemedSelect(filter);
    const list = overlay.querySelector('[data-picker-list]');
    const addBtn = overlay.querySelector('[data-picker-add]');
    const draw = () => {
      const q = String(search.value || '').toLowerCase();
      const folder = filter.value;
      const groups = {};
      items.filter((i) => !folder || (folder === '__general' ? !names[i.project_id] : i.project_id === folder))
        .filter((i) => !q || String(i.title || '').toLowerCase().includes(q) || String(names[i.project_id] || '').toLowerCase().includes(q))
        .forEach((i) => { const k = names[i.project_id] ? i.project_id : ''; (groups[k] = groups[k] || []).push(i); });
      const keys = Object.keys(groups).sort((a, b) => String(names[a] || 'General').localeCompare(String(names[b] || 'General')));
      list.innerHTML = keys.map((k) => `<div class="dash-picker-group"><h4>${esc(names[k] || 'General')}</h4>${groups[k].map((i) => {
        const isQuest = already.has(i.id);
        return `<label class="dash-picker-row${isQuest ? ' is-quest' : ''}"><input type="checkbox" value="${esc(i.id)}"${isQuest ? ' disabled checked' : chosen.has(i.id) ? ' checked' : ''}><span class="dash-row-main"><strong>${esc(i.title)}</strong><small>${esc(STATUS_LABEL[i.status] || i.status)}${isQuest ? ' · already a quest' : ''}</small></span></label>`;
      }).join('')}</div>`).join('') || '<p class="dash-empty">No open Work Hub items match.</p>';
    };
    // Enable once grown, and not before the open animation (0.25s) is over.
    resize(draw, () => setTimeout(() => { if (overlay.isConnected) setReady(true); }, Math.max(0, 260 - (Date.now() - opened))));
    list.addEventListener('change', (event) => {
      const box = event.target.closest('input[type=checkbox]'); if (!box || box.disabled) return;
      if (box.checked) chosen.add(box.value); else chosen.delete(box.value);
      addBtn.disabled = !chosen.size;
      addBtn.textContent = chosen.size ? `Add ${chosen.size} quest${chosen.size === 1 ? '' : 's'}` : 'Add quests';
    });
    search.addEventListener('input', () => resize(draw));
    filter.addEventListener('change', () => resize(draw));
    addBtn.addEventListener('click', async () => {
      addBtn.disabled = true;
      try {
        await post('/api/dashboard/quests/add', {item_ids: [...chosen], area});
        closeQuestPicker();
        toast(`${chosen.size} quest${chosen.size === 1 ? '' : 's'} added${area ? ` to ${AREA[area]}` : ''}`);
        refresh();
      } catch (error) { addBtn.disabled = false; toast(error.message || 'Could not add quests'); }
    });
  }

  function closeQuestPicker() {
    document.querySelectorAll('.dash-picker-overlay').forEach((el) => { el.classList.remove('is-open'); setTimeout(() => el.remove(), 200); });
  }

  // ── date picker ──────────────────────────────────────────────────────────
  // A themed calendar for the manual-sale date (the browser's own picker does
  // not follow the dashboard look). Writes YYYY-MM-DD into the hidden input
  // beside the button; no future dates.
  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  function closeDatePicker() {
    document.querySelectorAll('.dash-cal').forEach((el) => { el._cleanup && el._cleanup(); el.remove(); });
  }
  function openDatePicker(button) {
    if (document.querySelector('.dash-cal')) { closeDatePicker(); return; }
    const input = button.parentElement.querySelector('input[name="date"]');
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const picked = input.value ? new Date(input.value + 'T00:00:00') : today;
    let view = new Date(picked.getFullYear(), picked.getMonth(), 1);
    const pop = document.createElement('div');
    pop.className = 'dash-cal';
    pop.setAttribute('role', 'dialog');
    pop.setAttribute('aria-label', 'Choose a date');
    const draw = () => {
      const first = (view.getDay() + 6) % 7; // weeks start on Monday
      const days = new Date(view.getFullYear(), view.getMonth() + 1, 0).getDate();
      const cells = [];
      for (let i = 0; i < first; i++) cells.push('<span></span>');
      for (let d = 1; d <= days; d++) {
        const date = new Date(view.getFullYear(), view.getMonth(), d);
        const value = iso(date);
        const cls = [value === iso(today) ? 'is-today' : '', input.value === value || (!input.value && value === iso(today)) ? 'is-picked' : ''].filter(Boolean).join(' ');
        cells.push(`<button type="button" class="${cls}" data-cal-day="${value}"${date > today ? ' disabled' : ''}>${d}</button>`);
      }
      const nextMonth = new Date(view.getFullYear(), view.getMonth() + 1, 1);
      pop.innerHTML = `<header><button type="button" data-cal-step="-1" aria-label="Previous month">${svg('chevron-left', 14)}</button><strong>${MONTHS[view.getMonth()]} ${view.getFullYear()}</strong><button type="button" data-cal-step="1" aria-label="Next month"${nextMonth > today ? ' disabled' : ''}>${svg('chevron-right', 14)}</button></header>
        <div class="dash-cal-week">${['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'].map((w) => `<span>${w}</span>`).join('')}</div>
        <div class="dash-cal-days">${cells.join('')}</div>
        <footer><button type="button" data-cal-day="${iso(today)}">Today</button></footer>`;
    };
    draw();
    document.body.appendChild(pop);
    const place = () => {
      const r = button.getBoundingClientRect(), w = pop.offsetWidth, h = pop.offsetHeight;
      const left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8));
      const top = r.bottom + 6 + h > window.innerHeight - 8 ? Math.max(8, r.top - 6 - h) : r.bottom + 6;
      pop.style.left = left + 'px'; pop.style.top = top + 'px';
    };
    place();
    requestAnimationFrame(() => pop.classList.add('is-open'));
    pop.addEventListener('click', (event) => {
      const step = event.target.closest('[data-cal-step]');
      if (step && !step.disabled) { view = new Date(view.getFullYear(), view.getMonth() + Number(step.dataset.calStep), 1); draw(); return; }
      const day = event.target.closest('[data-cal-day]');
      if (day && !day.disabled) {
        input.value = day.dataset.calDay === iso(today) ? '' : day.dataset.calDay;
        const d = new Date(day.dataset.calDay + 'T00:00:00');
        button.querySelector('span').textContent = input.value ? d.toLocaleDateString(undefined, {day: 'numeric', month: 'short', year: 'numeric'}) : 'Today';
        closeDatePicker();
        button.focus();
      }
    });
    const outside = (event) => { if (!pop.contains(event.target) && !button.contains(event.target)) closeDatePicker(); };
    const key = (event) => { if (event.key === 'Escape') { closeDatePicker(); button.focus(); } };
    setTimeout(() => document.addEventListener('mousedown', outside), 0);
    document.addEventListener('keydown', key);
    window.addEventListener('resize', place);
    pop._cleanup = () => { document.removeEventListener('mousedown', outside); document.removeEventListener('keydown', key); window.removeEventListener('resize', place); };
  }

  // ── actions ──────────────────────────────────────────────────────────────
  async function act(path, body, {ok = '', after = refresh, row = null} = {}) {
    if (row) row.classList.add('is-leaving');
    try {
      const result = await post(path, body);
      if (ok) toast(typeof ok === 'function' ? ok(result) : ok);
      return result;
    } catch (error) {
      if (row) row.classList.remove('is-leaving');
      toast(error.message || 'Something went wrong');
      return null;
    } finally { if (after) after(); }
  }

  async function submitForm(form) {
    const kind = form.dataset.form;
    const f = Object.fromEntries(new FormData(form).entries());
    const submit = form.querySelector('[type=submit]'); if (submit) submit.disabled = true;
    let result = null;
    if (kind === 'habit') result = await act('/api/dashboard/habits/create', {name: f.name, cadence: f.cadence, target: f.cadence === 'weekly' ? Number(f.target) : 1}, {ok: 'Habit added', after: null});
    else if (kind === 'learning') result = await act('/api/dashboard/learning/add', {title: f.title, kind: f.kind, area: f.area}, {ok: (r) => `+${r.entry.xp} XP: ${r.entry.title}`, after: null});
    else if (kind === 'goal') result = await act('/api/dashboard/goals/add', {metric: f.metric, period: f.period, target: Number(f.target), project_id: f.project_id || ''}, {ok: 'Goal set', after: null});
    else if (kind === 'sale') result = await act('/api/dashboard/sales/add', {amount: f.amount, product: f.product, date: f.date || null, recurring: !!f.recurring}, {ok: 'Sale added', after: null});
    else if (kind === 'skill') result = await act('/api/dashboard/skills/add', {name: f.name, kind: f.kind}, {ok: (r) => `+${r.skill.xp} XP: ${r.skill.name}`, after: null});
    else if (kind === 'reward') result = await act('/api/dashboard/rewards/add', {name: f.name, cost: Number(f.cost), icon: f.icon}, {ok: 'Reward added', after: null});
    else if (kind === 'connect') result = await act('/api/dashboard/sales/connect', {platform: f.platform, key: f.key}, {ok: (r) => `Connected to ${r.label}`, after: null});
    if (submit) submit.disabled = false;
    if (!result) return;
    if (kind === 'learning' || kind === 'skill') form.reset(); else delete state.forms[kind];
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    load(state.tab, {quiet: true});
  }

  function onClick(event) {
    const pick = event.target.closest('[data-date-pick]');
    if (pick) { openDatePicker(pick); return; }
    const evo = event.target.closest('[data-evo-step]');
    if (evo) {
      const data = state.data.character; if (!data) return;
      const current = Math.max(0, (data.tier || 1) - 1);
      state.evoIndex = Math.max(0, Math.min((data.tiers || []).length - 1, (state.evoIndex == null ? current : state.evoIndex) + Number(evo.dataset.evoStep)));
      const host = evo.closest('[data-evo]');
      if (host) { host.innerHTML = evolutionView(data); const again = host.querySelector(`[data-evo-step="${evo.dataset.evoStep}"]`); if (again && !again.disabled) again.focus(); }
      return;
    }
    const t = event.target.closest('[data-dash-focus],[data-skill-remove],[data-dash-tab],[data-dash-go],[data-dash-item],[data-dash-note],[data-dash-retry],[data-dash-add-quest],[data-quest-remove],[data-quest-clear],[data-log-filter],[data-log-more],[data-form-open],[data-form-cancel],[data-habit-toggle],[data-habit-archive],[data-learning-remove],[data-goal-remove],[data-sale-remove],[data-sales-sync],[data-sales-disconnect],[data-reward-redeem],[data-reward-remove]');
    if (!t) return;
    const d = t.dataset;
    // A link to another page glows for a moment before the page changes.
    if (t.classList.contains('dash-nav') && !t.dataset.launched && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      t.dataset.launched = '1'; t.classList.add('is-launching');
      setTimeout(() => { t.classList.remove('is-launching'); t.click(); delete t.dataset.launched; }, 260);
      event.preventDefault();
      return;
    }
    if (d.dashFocus) return focusCard(d.dashFocus);
    if (d.skillRemove) return act('/api/dashboard/skills/remove', {skill_id: d.skillRemove}, {row: t.closest('.dash-row')});
    if (d.dashTab) return select(d.dashTab);
    if (t.hasAttribute('data-dash-retry')) return load(state.tab);
    if (t.hasAttribute('data-dash-add-quest')) return openQuestPicker(AREA[state.tab] ? state.tab : '');
    if (d.questRemove) return act('/api/dashboard/quests/remove', {item_id: d.questRemove}, {row: t.closest('.dash-quest-row')});
    if (t.hasAttribute('data-quest-clear')) return act('/api/dashboard/quests/clear', {});
    if (d.logFilter) { state.logCategory = d.logFilter; return load('character', {quiet: true}); }
    if (t.hasAttribute('data-log-more')) return load('character', {quiet: true, append: true});
    if (d.formOpen) { state.forms[d.formOpen] = true; paint({force: true}); const first = root().querySelector(`[data-form="${d.formOpen}"] input:not([type=checkbox])`); if (first) first.focus(); return; }
    if (d.formCancel) { delete state.forms[d.formCancel]; return paint({force: true}); }
    if (d.habitToggle) {
      const on = d.on !== '1';
      t.classList.toggle('is-on', on); t.dataset.on = on ? '1' : '0'; t.setAttribute('aria-pressed', String(on));
      if (on) { t.classList.add('is-pop'); setTimeout(() => t.classList.remove('is-pop'), 450); }
      return act('/api/dashboard/habits/check', {habit_id: d.habitToggle, done: on}, {ok: on ? '+10 XP' : ''});
    }
    if (d.habitArchive) return act('/api/dashboard/habits/archive', {habit_id: d.habitArchive}, {row: t.closest('.dash-habit'), ok: 'Habit removed'});
    if (d.learningRemove) return act('/api/dashboard/learning/remove', {entry_id: d.learningRemove}, {row: t.closest('.dash-row')});
    if (d.goalRemove) return act('/api/dashboard/goals/remove', {goal_id: d.goalRemove}, {row: t.closest('.dash-goal')});
    if (d.saleRemove) return act('/api/dashboard/sales/remove', {sale_id: d.saleRemove}, {row: t.closest('.dash-row')});
    if (t.hasAttribute('data-sales-sync')) { t.classList.add('is-spinning'); return act('/api/dashboard/sales/sync', {}, {ok: (r) => r.last_error || 'Synced'}); }
    if (t.hasAttribute('data-sales-disconnect')) {
      const ask = typeof showConfirmDialog === 'function'
        ? showConfirmDialog({title: 'Disconnect sales platform', message: 'Your key is removed from this profile. Sales already copied stay on the dashboard.', confirmLabel: 'Disconnect', danger: true})
        : Promise.resolve(window.confirm('Disconnect the sales platform?'));
      return Promise.resolve(ask).then((yes) => yes && act('/api/dashboard/sales/disconnect', {}, {ok: 'Disconnected'}));
    }
    if (d.rewardRedeem) return act('/api/dashboard/rewards/redeem', {reward_id: d.rewardRedeem}, {ok: (r) => `Enjoy: ${r.redeemed}!`});
    if (d.rewardRemove) return act('/api/dashboard/rewards/remove', {reward_id: d.rewardRemove}, {row: t.closest('.rpg-reward')});
    if (d.jobsView && d.dashGo === 'jobs') {
      // Open the Jobs page on a given section (it reads the section from the hash).
      try { history.replaceState(history.state, '', location.pathname + location.search + '#jobs/' + d.jobsView); } catch (_) {}
      if (window.JobOSState) window.JobOSState.activeView = d.jobsView;
    }
    if (d.dashGo && typeof switchPanel === 'function') return switchPanel(d.dashGo);
    if (d.dashItem && typeof window.openWorkHubItem === 'function') return window.openWorkHubItem(d.dashItem, d.project || null, d.board || null);
    if (d.dashNote && window.Notebook && typeof window.Notebook.openFrom === 'function') return window.Notebook.openFrom(d.dashNote, null);
  }

  // A stat tile points at the card it summarises: bring it into view and pulse it.
  function focusCard(key) {
    const target = root() && root().querySelector(`[data-dash-card="${CSS.escape(key)}"]`);
    if (!target) return;
    const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    target.scrollIntoView({behavior: reduced ? 'auto' : 'smooth', block: 'center'});
    target.classList.remove('is-pulsing');
    void target.offsetWidth; // restart the animation on a second click
    target.classList.add('is-pulsing');
    clearTimeout(target._pulseTimer);
    target._pulseTimer = setTimeout(() => target.classList.remove('is-pulsing'), 2000);
  }

  function tick() { if (state.mounted && !document.hidden) refresh(); }
  function mount() {
    state.mounted = true;
    paint({force: true});
    load(state.tab, {quiet: !!state.data[state.tab]});
    clearInterval(state.timer);
    state.timer = setInterval(tick, REFRESH_MS);
    if (state.timer && typeof state.timer.unref === 'function') state.timer.unref();
  }
  function unmount() { state.mounted = false; clearInterval(state.timer); state.timer = 0; clearEffects(); closeDatePicker(); state.painted = {}; }

  document.addEventListener('click', (event) => {
    if (!event.target.closest) return;
    if (event.target.closest('[data-picker-close]') || event.target.classList.contains('dash-picker-overlay')) { closeQuestPicker(); return; }
    if (event.target.closest('#dashboardRoot,#dashboardSidebar')) onClick(event);
  });
  document.addEventListener('submit', (event) => {
    const form = event.target.closest && event.target.closest('#dashboardRoot form[data-form]');
    if (!form) return;
    event.preventDefault();
    submitForm(form);
  });
  document.addEventListener('change', (event) => {
    const picker = event.target.closest && event.target.closest('#dashboardRoot [data-project-category]');
    if (!picker) return;
    act('/api/dashboard/categories', {project_id: picker.dataset.projectCategory, category: picker.value}, {ok: 'Realm updated'});
  });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && document.querySelector('.dash-picker-overlay')) closeQuestPicker(); });
  // A card's scrollbar shows while it scrolls and fades a moment after.
  document.addEventListener('scroll', (event) => {
    const target = event.target && event.target.matches && event.target.matches(SCROLLERS) ? event.target : null;
    if (target) updateMore(target);
    const body = target && target.classList.contains('dash-card-body') ? target : null;
    if (!body) return;
    body.classList.add('is-scrolling');
    clearTimeout(body._scrollTimer);
    body._scrollTimer = setTimeout(() => body.classList.remove('is-scrolling'), 900);
  }, true);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) tick(); });
  window.addEventListener('resize', () => { const host = root(); if (host) markScrollable(host); });
  window.HermesDashboard = {mount, unmount, select, openQuestPicker, refresh, _celebrate: celebrate, _state: state};
})();
