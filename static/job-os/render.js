(function () {
  const esc = (value) => String(value == null ? '' : value).replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const labels = {dashboard: 'Dashboard', scout: 'Scout', pipeline: 'Pipeline', 'resume-studio': 'Resume Studio', applications: 'Applications', settings: 'Settings'};
  const icons = {
    dashboard: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    scout: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4.2-4.2"/>',
    pipeline: '<path d="M4 6h16M7 12h10M10 18h4"/>',
    'resume-studio': '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
    applications: '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
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
  // Firecrawl health, as the server classified it (see api/job_os/firecrawl.py).
  const FIRECRAWL_LABELS = {healthy: 'Firecrawl ready', offline: 'Firecrawl offline', incompatible: 'Firecrawl incompatible', not_configured: 'Firecrawl not set up'};
  function header(title, subtitle, state) {
    const ready = state.capability && state.capability.available;
    const fc = state.firecrawl;
    const chip = !ready
      ? '<span class="job-os-status" data-ready="false">Storage unavailable</span>'
      : fc
        ? `<button type="button" class="job-os-status" data-ready="${fc.state === 'healthy' ? 'true' : 'false'}" data-fc-state="${esc(fc.state)}" data-job-os-view="settings" title="${esc(fc.detail || '')}">${esc(FIRECRAWL_LABELS[fc.state] || 'Firecrawl unknown')}</button>`
        : '<span class="job-os-status" data-ready="true">Ready</span>';
    return `<header class="job-os-header"><div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div>${chip}</header>`;
  }
  // Narrow screens put the side panel in a drawer, so they keep a compact
  // section switcher in the page itself.
  function mobileNav(view) {
    return `<nav class="job-os-tabs" aria-label="Job OS sections">${Object.keys(labels).map((key) => `<button type="button" class="${view === key ? 'active' : ''}" data-job-os-view="${key}">${labels[key]}</button>`).join('')}</nav>`;
  }
  function metric(name, value, label, target) {
    return `<button type="button" class="job-os-metric" ${target}><img class="job-os-metric-icon" data-metric="${name}" src="/static/job-os-metric-${name}.png" alt="" aria-hidden="true"><span class="job-os-metric-body"><strong data-count-key="jobs-${name}">${esc(value)}</strong><span>${esc(label)}</span></span></button>`;
  }
  function placeholder(view, body) {
    return `<section class="job-os-card job-os-placeholder"><span class="job-os-placeholder-icon">${icon(view, 26)}</span><h2>${esc(labels[view])}</h2><p>${esc(body)}</p><button class="job-os-btn" type="button" data-job-os-view="dashboard">Back to dashboard</button></section>`;
  }

  // ---- Settings ----------------------------------------------------------
  // Every input carries data-setting="section.key"; index.js serialises the
  // form back into a partial settings object by that path.
  const ATS = [['greenhouse', 'Greenhouse'], ['lever', 'Lever'], ['ashby', 'Ashby']];
  const get = (obj, path) => path.split('.').reduce((acc, key) => (acc == null ? acc : acc[key]), obj);
  function toggle(path, label, value, hint) {
    return `<label class="job-os-toggle"><input type="checkbox" data-setting="${path}" ${value ? 'checked' : ''}><span class="job-os-toggle-track" aria-hidden="true"></span><span class="job-os-toggle-text"><strong>${esc(label)}</strong>${hint ? `<small>${esc(hint)}</small>` : ''}</span></label>`;
  }
  function numberField(path, label, value, min, max, suffix) {
    return `<label class="job-os-field"><span>${esc(label)}</span><span class="job-os-field-input"><input type="number" data-setting="${path}" value="${esc(value)}" min="${min}" max="${max}" step="1" inputmode="numeric">${suffix ? `<em>${esc(suffix)}</em>` : ''}</span></label>`;
  }
  function textField(path, label, value, placeholderText, type) {
    return `<label class="job-os-field"><span>${esc(label)}</span><input type="${type || 'text'}" data-setting="${path}" value="${esc(value)}" placeholder="${esc(placeholderText || '')}" autocomplete="off" spellcheck="false"></label>`;
  }
  function selectField(path, label, value, options) {
    return `<label class="job-os-field"><span>${esc(label)}</span><select data-setting="${path}">${options.map(([v, t]) => `<option value="${esc(v)}" ${v === value ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select></label>`;
  }
  function pill(ok, text) {
    return `<span class="job-os-pill" data-ok="${ok ? 'true' : 'false'}">${esc(text)}</span>`;
  }
  function section(id, title, note, inner, phase) {
    return `<section class="job-os-card job-os-settings-section" id="job-os-settings-${id}"><div class="job-os-card-head"><h2>${esc(title)}</h2>${phase ? `<span class="job-os-phase" title="Saved now; takes effect when this phase ships">${esc(phase)}</span>` : ''}</div>${note ? `<p class="job-os-card-note">${esc(note)}</p>` : ''}${inner}</section>`;
  }
  // Gmail: verified on the server with a real login, then saved to the shared
  // secrets file every profile reads. The password field is never pre-filled
  // and its value is never kept in page state.
  function gmailBlock(state, gmail, ready) {
    const msg = state.gmailMessage ? `<p class="job-os-gmail-msg" data-tone="${esc(state.gmailMessage.tone)}" role="status">${esc(state.gmailMessage.text)}</p>` : '<p class="job-os-gmail-msg" role="status"></p>';
    if (ready && !state.gmailEditing) {
      return `<div class="job-os-conn" id="job-os-gmail">
        <div class="job-os-conn-head"><strong>Gmail</strong>${pill(true, 'Connected')}</div>
        <p class="job-os-card-note">Connected as <strong>${esc(gmail.address_hint || 'your account')}</strong>. ${gmail.scope === 'shared' ? 'Saved once for every profile.' : 'Saved for this profile.'}</p>
        <div class="job-os-actions"><button type="button" class="job-os-btn" data-job-os-action="gmail-test">Send test email</button><button type="button" class="job-os-btn" data-job-os-action="gmail-edit">Replace</button><button type="button" class="job-os-btn job-os-btn-danger" data-job-os-action="gmail-disconnect">Disconnect</button></div>
        ${msg}
      </div>`;
    }
    return `<div class="job-os-conn" id="job-os-gmail">
      <div class="job-os-conn-head"><strong>Gmail</strong>${pill(false, 'Not connected')}</div>
      <p class="job-os-card-note">Use a Gmail <strong>app password</strong>, not your normal password: Google Account → Security → 2-Step Verification → App passwords (<a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener noreferrer">open</a>). Hermes logs in once to check it, then saves it ${gmail.scope === 'shared' ? 'for every profile' : 'for this profile'}; it is never shown again.</p>
      <div class="job-os-grid">
        <label class="job-os-field"><span>Gmail address</span><input type="email" id="job-os-gmail-address" autocomplete="email" spellcheck="false" placeholder="you@gmail.com"></label>
        <label class="job-os-field"><span>App password</span><input type="password" id="job-os-gmail-password" autocomplete="new-password" spellcheck="false" placeholder="xxxx xxxx xxxx xxxx"></label>
      </div>
      <div class="job-os-actions"><button type="button" class="job-os-btn primary" data-job-os-action="gmail-connect">Connect Gmail</button>${ready ? '<button type="button" class="job-os-btn" data-job-os-action="gmail-cancel">Cancel</button>' : ''}</div>
      ${msg}
    </div>`;
  }
  function settingsView(state) {
    const s = state.settingsDraft || state.settings;
    if (!s) return '<section class="job-os-card"><p class="job-os-card-note">Loading settings…</p></section>';
    const status = state.settingsStatus || {};
    const fc = status.firecrawl || state.firecrawl || {};
    const gmail = status.gmail || {};
    const gmailReady = gmail.address && gmail.app_password;
    const dirty = !!state.settingsDirty;
    const v = (path) => get(s, path);
    const firecrawl = section('connections', 'Connections', '', `
      <div class="job-os-conn">
        <div class="job-os-conn-head"><strong>Firecrawl</strong>${pill(fc.state === 'healthy', FIRECRAWL_LABELS[fc.state] || 'Unknown')}</div>
        <p class="job-os-card-note">${esc(fc.detail || '')}${fc.base_url ? ` Using <code>${esc(fc.base_url)}</code>${fc.source === 'settings' ? ' (set here)' : fc.source ? ' (from your .env settings)' : ''}.` : ''}${fc.latency_ms != null ? ` ${esc(fc.latency_ms)} ms.` : ''}</p>
        ${textField('firecrawl.api_url', 'Firecrawl URL override', v('firecrawl.api_url'), 'Leave empty to use FIRECRAWL_API_URL from your .env settings', 'url')}
        <button type="button" class="job-os-btn" data-job-os-action="test-firecrawl">Test connection</button>
      </div>
      ${gmailBlock(state, gmail, gmailReady)}`);
    const ai = section('ai', 'AI', 'Used for job analysis, fit scores and resume tailoring.', `<div class="job-os-grid">
      ${textField('ai.model', 'Model', v('ai.model'))}
      ${textField('ai.provider', 'Provider', v('ai.provider'))}
      ${selectField('ai.reasoning_effort', 'Reasoning', v('ai.reasoning_effort'), [['low', 'Low'], ['medium', 'Medium'], ['high', 'High']])}</div>`, 'Phase 2');
    const scout = section('scout', 'Scout schedule', 'A scheduled job searches your saved searches on this interval.', `
      ${toggle('scout.enabled', 'Run Scout automatically', v('scout.enabled'))}
      <div class="job-os-grid">${numberField('scout.schedule_hours', 'Every', v('scout.schedule_hours'), 1, 168, 'hours')}${numberField('scout.max_results_per_search', 'Max results per search', v('scout.max_results_per_search'), 1, 100)}</div>`, 'Phase 1');
    const notify = section('notifications', 'Notifications', gmailReady ? '' : 'Set up Gmail above to turn email on.', `
      ${toggle('notifications.email_enabled', 'Email me', v('notifications.email_enabled'), gmailReady ? '' : 'Needs Gmail credentials')}
      <div class="job-os-grid">${textField('notifications.to_address', 'Send to', v('notifications.to_address'), 'you@gmail.com', 'email')}</div>
      ${toggle('notifications.notify_new_matches', 'New matches', v('notifications.notify_new_matches'), 'When Scout finds a job at or above the score below')}
      <div class="job-os-grid">${numberField('notifications.min_fit_score', 'Minimum fit score', v('notifications.min_fit_score'), 0, 100, '/ 100')}</div>
      ${toggle('notifications.daily_digest', 'Daily digest', v('notifications.daily_digest'))}
      <div class="job-os-grid">${numberField('notifications.digest_hour', 'Digest hour', v('notifications.digest_hour'), 0, 23, ':00')}</div>
      ${toggle('notifications.reply_actions', 'Act on replies', v('notifications.reply_actions'), 'Reply TAILOR or APPLY to a job email to start that step')}`, 'Phase 5');
    const auto = section('auto-apply', 'Auto-apply', 'Off unless you turn it on. Only standard application forms; anything unusual stops and asks you.', `
      ${toggle('auto_apply.enabled', 'Auto-apply to strong matches', v('auto_apply.enabled'))}
      <fieldset class="job-os-ats"><legend>Allowed application systems</legend>${ATS.map(([key, name]) => `<label><input type="checkbox" data-setting="auto_apply.allowed_ats" value="${key}" ${(v('auto_apply.allowed_ats') || []).includes(key) ? 'checked' : ''}>${esc(name)}</label>`).join('')}</fieldset>
      <div class="job-os-grid">${numberField('auto_apply.daily_cap', 'Daily limit', v('auto_apply.daily_cap'), 1, 50, 'applications')}${numberField('auto_apply.min_fit_score', 'Minimum fit score', v('auto_apply.min_fit_score'), 0, 100, '/ 100')}</div>
      ${toggle('auto_apply.dry_run_first', 'Dry run first', v('auto_apply.dry_run_first'), 'Fill the form and capture a screenshot without sending, before the first real submission to each site')}`, 'Phase 6');
    const resume = section('resume', 'Resume', 'Your Main Resume is uploaded in Resume Studio.', '<button type="button" class="job-os-btn" data-job-os-view="resume-studio">Open Resume Studio</button>', 'Phase 3');
    const bar = `<div class="job-os-savebar" data-dirty="${dirty ? 'true' : 'false'}"><p id="job-os-settings-error" class="job-os-error" role="alert">${esc(state.settingsError || '')}</p><span class="job-os-savebar-note">${dirty ? 'Unsaved changes' : state.settingsSavedAt ? 'Saved' : ''}</span><button type="button" class="job-os-btn" data-job-os-action="discard-settings" ${dirty ? '' : 'disabled'}>Discard</button><button type="button" class="job-os-btn primary" data-job-os-action="save-settings" ${dirty ? '' : 'disabled'}>Save settings</button></div>`;
    return `<form id="job-os-settings-form" class="job-os-settings" novalidate>${firecrawl}${ai}${scout}${notify}${auto}${resume}${bar}</form>`;
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
    } else if (view === 'settings') {
      body = `${header('Settings', 'Connections, AI, schedules, notifications and auto-apply for this profile.', state)}${settingsView(state)}`;
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
