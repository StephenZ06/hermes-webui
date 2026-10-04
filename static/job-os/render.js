(function () {
  const esc = (value) => String(value == null ? '' : value).replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const labels = {dashboard: 'Dashboard', scout: 'Scout', pipeline: 'Pipeline', 'resume-studio': 'Resume Studio', applications: 'Applications'};
  const icons = {
    dashboard: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    scout: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4.2-4.2"/>',
    pipeline: '<path d="M4 6h16M7 12h10M10 18h4"/>',
    'resume-studio': '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
    applications: '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
    total: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
    active: '<path d="M12 3v3M12 18v3M4.6 4.6l2.1 2.1M17.3 17.3l2.1 2.1M3 12h3M18 12h3M4.6 19.4l2.1-2.1M17.3 6.7l2.1-2.1"/>',
    attention: '<circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 16.5v.5"/>',
    applied: '<path d="M20 6 9 17l-5-5"/>',
    import: '<path d="M12 5v14M5 12h14"/>',
  };
  const icon = (name, size) => `<svg width="${size || 16}" height="${size || 16}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || ''}</svg>`;
  // Lifecycle statuses grouped into the tones a reader scans for.
  const tones = {
    discovered: 'neutral', scraped: 'neutral', analyzed: 'neutral', shortlisted: 'info',
    tailoring: 'accent', resume_ready: 'accent', application_ready: 'accent', applying: 'accent',
    awaiting_approval: 'warn',
    submitted: 'info', screening: 'info', interviewing: 'info',
    offer: 'success', offer_accepted: 'success',
    skipped: 'muted', expired: 'muted', closed: 'muted', rejected: 'muted', withdrawn: 'muted', no_response: 'muted',
  };
  const APPLIED = ['submitted', 'screening', 'interviewing', 'offer', 'offer_accepted'];
  const statusOrder = Object.keys(tones);
  const statusLabel = (status) => {
    const text = String(status || '').replace(/_/g, ' ');
    return text.charAt(0).toUpperCase() + text.slice(1);
  };
  const badge = (status) => `<span class="job-os-badge" data-tone="${tones[status] || 'neutral'}">${esc(statusLabel(status))}</span>`;
  function when(epochSeconds) {
    const seconds = Math.max(0, Math.floor(Date.now() / 1000) - Number(epochSeconds || 0));
    if (!epochSeconds) return '';
    if (seconds < 60) return 'Just now';
    if (seconds < 3600) return Math.floor(seconds / 60) + 'm ago';
    if (seconds < 86400) return Math.floor(seconds / 3600) + 'h ago';
    if (seconds < 86400 * 7) return Math.floor(seconds / 86400) + 'd ago';
    return new Date(epochSeconds * 1000).toLocaleDateString(undefined, {month: 'short', day: 'numeric'});
  }
  // The API lists jobs oldest first (created_at ASC); every view here reads newest first.
  const newestFirst = (jobs) => jobs.slice().sort((a, b) => (Number(b.updated_at) || 0) - (Number(a.updated_at) || 0) || (Number(b.created_at) || 0) - (Number(a.created_at) || 0));
  const dashboardOf = (state) => state.dashboard || {total_jobs: 0, active_work: 0, needs_attention: 0, by_status: {}};
  const appliedCount = (byStatus) => APPLIED.reduce((sum, key) => sum + (byStatus[key] || 0), 0);
  function jobCard(job) {
    const initial = String(job.company || job.title || '?').trim().charAt(0).toUpperCase() || '?';
    const meta = [job.company || 'Company to review', job.location].filter(Boolean).map(esc).join(' · ');
    return `<button class="job-os-job-card" type="button" data-job-id="${esc(job.id)}"><span class="job-os-job-avatar" aria-hidden="true">${esc(initial)}</span><span class="job-os-job-main"><strong>${esc(job.title)}</strong><span>${meta}</span></span>${badge(job.status)}<small class="job-os-job-when">${esc(when(job.updated_at))}</small></button>`;
  }
  function jobList(jobs, emptyTitle, emptyBody) {
    return jobs.length
      ? `<div class="job-os-list" role="list">${jobs.map(jobCard).join('')}</div>`
      : `<div class="job-os-empty"><strong>${esc(emptyTitle)}</strong><p>${esc(emptyBody)}</p></div>`;
  }
  function header(title, subtitle, state) {
    const ready = state.capability && state.capability.available;
    return `<header class="job-os-header"><div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><span class="job-os-status" data-ready="${ready ? 'true' : 'false'}">${ready ? 'Ready' : 'Storage unavailable'}</span></header>`;
  }
  // Narrow screens put the side panel in a drawer, so they keep a compact
  // section switcher in the page itself.
  function mobileNav(view) {
    return `<nav class="job-os-tabs" aria-label="Job OS sections">${Object.keys(labels).map((key) => `<button type="button" class="${view === key ? 'active' : ''}" data-job-os-view="${key}">${labels[key]}</button>`).join('')}</nav>`;
  }
  function metric(name, value, label, target) {
    return `<button type="button" class="job-os-metric" ${target}><span class="job-os-metric-icon" data-metric="${name}">${icon(name, 18)}</span><span class="job-os-metric-body"><strong>${esc(value)}</strong><span>${esc(label)}</span></span></button>`;
  }
  function placeholder(view, body) {
    return `<section class="job-os-card job-os-placeholder"><span class="job-os-placeholder-icon">${icon(view, 26)}</span><h2>${esc(labels[view])}</h2><p>${esc(body)}</p><button class="job-os-btn" type="button" data-job-os-view="dashboard">Back to dashboard</button></section>`;
  }
  function shell(state) {
    const view = state.activeView;
    const dashboard = dashboardOf(state);
    const byStatus = dashboard.by_status || {};
    const jobs = newestFirst(state.jobs || []);
    const draft = state.importDraft || {};
    let body;
    if (view === 'dashboard') {
      body = `${header('Dashboard', 'Your job search at a glance.', state)}
        <section class="job-os-metrics" aria-label="Job dashboard">${metric('total', dashboard.total_jobs, 'Total jobs', 'data-job-os-filter=""')}${metric('active', dashboard.active_work, 'Active work', 'data-job-os-filter="tailoring"')}${metric('attention', dashboard.needs_attention, 'Needs attention', 'data-job-os-filter="awaiting_approval"')}${metric('applied', appliedCount(byStatus), 'Applied', 'data-job-os-view="applications"')}</section>
        <div class="job-os-columns">
          <section class="job-os-card job-os-recent"><div class="job-os-card-head"><h2>Recent jobs</h2><button type="button" class="job-os-link" data-job-os-view="pipeline">View pipeline</button></div>${jobList(jobs.slice(0, 12), 'No jobs saved yet', 'Import a role to start tracking it through your pipeline.')}</section>
          <section class="job-os-card job-os-import"><div class="job-os-card-head"><h2>Import a job</h2></div><p class="job-os-card-note">Save a role manually now; Firecrawl discovery arrives in the next release.</p><form id="job-os-import-form"><label>Role title<input name="title" required maxlength="240" placeholder="e.g. Senior Frontend Engineer" value="${esc(draft.title)}"></label><label>Job URL<input name="canonical_url" type="url" required placeholder="https://" value="${esc(draft.canonical_url)}"></label><label>Company<input name="company" maxlength="240" placeholder="Optional" value="${esc(draft.company)}"></label><button class="job-os-btn primary" type="submit">${icon('import', 14)}Save job</button><p id="job-os-import-error" class="job-os-error" role="alert"></p></form></section>
        </div>`;
    } else if (view === 'pipeline') {
      const filter = state.statusFilter;
      body = `${header('Pipeline', filter ? `Jobs currently ${statusLabel(filter).toLowerCase()}.` : 'Every job in this profile, newest first.', state)}
        <section class="job-os-card job-os-fill"><div class="job-os-card-head"><h2>${filter ? `<span class="job-os-filter-label">${esc(statusLabel(filter))}</span>` : 'All jobs'} <span class="job-os-count">${jobs.length}</span></h2>${filter ? '<button type="button" class="job-os-link" data-job-os-filter="">Clear filter</button>' : ''}</div>${jobList(jobs, 'No jobs here', filter ? 'No jobs match this status right now.' : 'Import a role from the dashboard to start your pipeline.')}</section>`;
    } else if (view === 'applications') {
      const applied = jobs.filter((job) => APPLIED.includes(job.status));
      body = `${header('Applications', 'Submitted applications and where each one stands.', state)}
        <section class="job-os-card job-os-fill"><div class="job-os-card-head"><h2>Submitted <span class="job-os-count">${applied.length}</span></h2></div>${jobList(applied, 'No applications yet', 'Prepared applications, approvals, and outcomes will appear here once you apply.')}</section>`;
    } else if (view === 'scout') {
      body = `${header('Scout', 'Find new roles that match your search.', state)}${placeholder('scout', 'Saved searches and Firecrawl discovery will appear here.')}`;
    } else {
      body = `${header('Resume Studio', 'Your master CV and tailored versions.', state)}${placeholder('resume-studio', 'Your master CV and tailored versions will appear here.')}`;
    }
    return `<div class="job-os-shell" data-view="${esc(view)}">${mobileNav(view)}<main class="job-os-content">${body}</main></div>`;
  }
  function sidebar(state) {
    const view = state.activeView;
    const dashboard = dashboardOf(state);
    const byStatus = dashboard.by_status || {};
    const counts = {pipeline: dashboard.total_jobs, applications: appliedCount(byStatus)};
    const nav = Object.keys(labels).map((key) => {
      const active = view === key && !(key === 'pipeline' && state.statusFilter);
      const count = counts[key] ? `<span class="job-os-side-count">${counts[key]}</span>` : '';
      return `<button type="button" class="side-menu-item${active ? ' active' : ''}" data-job-os-view="${key}"${active ? ' aria-current="page"' : ''}>${icon(key)}<span>${labels[key]}</span>${count}</button>`;
    }).join('');
    const stages = statusOrder.filter((status) => byStatus[status]).map((status) => {
      const active = view === 'pipeline' && state.statusFilter === status;
      return `<button type="button" class="side-menu-item job-os-stage${active ? ' active' : ''}" data-job-os-filter="${status}"><span class="job-os-dot" data-tone="${tones[status]}" aria-hidden="true"></span><span>${esc(statusLabel(status))}</span><span class="job-os-side-count">${byStatus[status]}</span></button>`;
    }).join('');
    return `<nav class="side-menu job-os-side-nav" aria-label="Job OS sections">${nav}</nav><div class="job-os-side-section"><div class="job-os-side-heading">Pipeline stages</div><div class="side-menu job-os-side-stages">${stages || '<p class="job-os-side-empty">No jobs yet.</p>'}</div></div>`;
  }
  window.JobOSRender = {shell, sidebar};
}());
