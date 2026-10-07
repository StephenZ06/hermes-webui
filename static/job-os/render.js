(function () {
  const esc = (value) => String(value == null ? '' : value).replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const labels = {dashboard: 'Dashboard', scout: 'Scout', pipeline: 'Pipeline', 'resume-studio': 'Resume Studio', logistics: 'Logistics', settings: 'Settings'};
  const icons = {
    dashboard: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    scout: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4.2-4.2"/>',
    pipeline: '<path d="M4 6h16M7 12h10M10 18h4"/>',
    'resume-studio': '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
    applications: '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
    logistics: '<path d="M3 21V9l9-5 9 5v12"/><path d="M7 21v-7h10v7M7 17h10"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    total: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
    active: '<path d="M12 3v3M12 18v3M4.6 4.6l2.1 2.1M17.3 17.3l2.1 2.1M3 12h3M18 12h3M4.6 19.4l2.1-2.1M17.3 6.7l2.1-2.1"/>',
    attention: '<circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 16.5v.5"/>',
    applied: '<path d="M20 6 9 17l-5-5"/>',
    import: '<path d="M12 5v14M5 12h14"/>',
    board: '<rect x="3" y="4" width="5" height="16" rx="1.5"/><rect x="10" y="4" width="5" height="11" rx="1.5"/><rect x="17" y="4" width="4" height="7" rx="1.5"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
    pin: '<path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.3"/>',
    pay: '<rect x="2.5" y="6" width="19" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 9.5v.01M18 14.5v.01"/>',
    briefcase: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18"/>',
    external: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
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
  function until(epochSeconds) {
    const seconds = Number(epochSeconds || 0) - Math.floor(Date.now() / 1000);
    if (!epochSeconds) return '';
    if (seconds < 90) return 'any moment';
    if (seconds < 3600) return 'in ' + Math.round(seconds / 60) + 'm';
    if (seconds < 86400) return 'in ' + Math.round(seconds / 3600) + 'h';
    return 'in ' + Math.round(seconds / 86400) + 'd';
  }
  function automationsCard(items) {
    if (!items) return '';
    const rows = items.map((a, i) => {
      const last = typeof a.last === 'number' ? `Last ${when(a.last)}` : a.last ? `Last ${esc(a.last)}` : '';
      const timing = [last, a.next ? `next ${until(a.next)}` : ''].filter(Boolean).join(' · ');
      const note = a.on ? [a.detail, timing].filter(Boolean).join(' · ') : a.off_reason;
      const tag = a.view ? 'button' : 'div';
      return `<${tag}${a.view ? ` type="button" data-job-os-view="${esc(a.view)}"` : ''} class="automation-row" data-on="${a.on ? 'true' : 'false'}" style="--i:${i}"><span class="automation-dot" aria-hidden="true"></span><span class="automation-main"><strong>${esc(a.label)}</strong><small>${esc(a.schedule)}</small></span><span class="automation-note">${a.on ? '' : '<em>Off</em> '}${esc(note || '')}</span></${tag}>`;
    }).join('');
    return `<section class="job-os-card automations-card"><div class="job-os-card-head"><h2>Automations</h2><button type="button" class="job-os-link" data-job-os-view="settings">Change</button></div><div class="automations">${rows}</div></section>`;
  }
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
  const WORKPLACE = {remote: 'Remote', hybrid: 'Hybrid', onsite: 'On-site'};
  function jobChips(job) {
    const chips = [];
    if (job.workplace) chips.push(`<span class="job-os-chip" data-kind="${esc(job.workplace)}">${esc(WORKPLACE[job.workplace] || job.workplace)}</span>`);
    if (job.salary_text) chips.push(`<span class="job-os-chip" data-kind="pay">${esc(job.salary_text)}</span>`);
    if (job.employment_type) chips.push(`<span class="job-os-chip">${esc(job.employment_type)}</span>`);
    return chips.length ? `<span class="job-os-chips">${chips.join('')}</span>` : '';
  }
  // Match bands for Luna's 0-100 fit score of the master resume against a job:
  // green from 75, yellow from 50, red below.
  const BANDS = [[75, 'good', 'Good match'], [50, 'fair', 'Needs improvement'], [0, 'poor', 'Terrible match']];
  const band = (score) => BANDS.find(([min]) => Number(score) >= min) || BANDS[BANDS.length - 1];
  // Fit score ring: the arc fills to the score, coloured by its band.
  const analysing = (job) => !!(job.analysis && (job.analysis.status === 'pending' || job.analysis.status === 'running'));
  function fitRing(a, size) {
    if (!a) return '';
    if (a.status === 'pending' || a.status === 'running') return `<span class="fit-ring ${size || ''} is-busy" title="Luna is scoring your resume against this job" aria-label="Scoring"><span>…</span></span>`;
    if (a.status === 'failed') return `<span class="fit-ring ${size || ''} is-failed" title="Scoring failed" aria-label="Scoring failed"><span>!</span></span>`;
    if (a.fit_score == null) return '';
    const [, key, text] = band(a.fit_score);
    return `<span class="fit-ring ${size || ''}" data-band="${key}" style="--fit:${Number(a.fit_score)}" title="${esc(text)} · ${Number(a.fit_score)}%" aria-label="${esc(text)}, ${Number(a.fit_score)} percent"><span>${Number(a.fit_score)}</span></span>`;
  }
  const sourceOf = (job) => (job.source === 'manual' ? 'manual' : 'indeed');
  const SOURCE_LABEL = {indeed: 'Indeed', manual: 'Manual'};
  // "Kuala Lumpur, M14, MY" + "Malaysia" reads as "Kuala Lumpur, Malaysia":
  // Indeed's region and country codes add nothing next to the country name.
  function place(job) {
    const parts = String(job.location || '').split(',').map((p) => p.trim()).filter((p) => p && !/^[A-Z0-9]{1,3}$/.test(p));
    if (job.country && !parts.some((p) => p.toLowerCase() === String(job.country).toLowerCase())) parts.push(job.country);
    return parts.join(', ');
  }
  function jobCard(job) {
    const initial = String(job.company || job.title || '?').trim().charAt(0).toUpperCase() || '?';
    const meta = [job.company || 'Company to review', place(job), SOURCE_LABEL[sourceOf(job)]].filter(Boolean).map(esc).join(' · ');
    return `<button class="job-os-job-card${analysing(job) ? ' is-analysing' : ''}" type="button" data-job-id="${esc(job.id)}">${fitRing(job.analysis, 'small') || `<span class="job-os-job-avatar" aria-hidden="true">${esc(initial)}</span>`}<span class="job-os-job-main"><strong>${esc(job.title)}</strong><span>${meta}</span>${jobChips(job)}</span>${badge(job.status)}<small class="job-os-job-when">${esc(when(job.updated_at))}</small></button>`;
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
        <div class="job-os-conn-head"><strong>Gmail sender</strong>${pill(true, 'Connected')}</div>
        <p class="job-os-card-note">Hermes sends from <strong>${esc(gmail.address_hint || 'your account')}</strong>, named after the part of Hermes writing (<em>Hermes Jobs</em>, <em>Hermes Business</em>), to the <em>Send to</em> address under Notifications (this account if that is empty). ${gmail.scope === 'shared' ? 'Saved once for every profile.' : 'Saved for this profile.'}</p>
        <div class="job-os-actions"><label class="job-os-inline-select">Send test as <select id="job-os-gmail-test-context" aria-label="Sender name for the test email"><option value="jobs">Hermes Jobs</option><option value="business">Hermes Business</option></select></label><button type="button" class="job-os-btn" data-job-os-action="gmail-test">Send test email</button><button type="button" class="job-os-btn" data-job-os-action="gmail-edit">Replace</button><button type="button" class="job-os-btn job-os-btn-danger" data-job-os-action="gmail-disconnect">Disconnect</button></div>
        ${msg}
      </div>`;
    }
    return `<div class="job-os-conn" id="job-os-gmail">
      <div class="job-os-conn-head"><strong>Gmail sender</strong>${pill(false, 'Not connected')}</div>
      <p class="job-os-card-note">The account Hermes sends from. A separate Gmail just for Hermes works best; your main address goes in <em>Send to</em> under Notifications. Use a Gmail <strong>app password</strong>, not your normal password: Google Account → Security → 2-Step Verification → App passwords (<a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener noreferrer">open</a>). Hermes logs in once to check it, then saves it ${gmail.scope === 'shared' ? 'for every profile' : 'for this profile'}; it is never shown again.</p>
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
      ${selectField('ai.reasoning_effort', 'Reasoning', v('ai.reasoning_effort'), [['low', 'Low'], ['medium', 'Medium'], ['high', 'High']])}</div>
      ${toggle('ai.auto_analyze', 'Analyse new finds automatically', v('ai.auto_analyze'), 'Scout queues each new job for a fit score against your resume')}`);
    const applicant = section('applicant', 'Your details', 'Used on tailored resumes and cover letters.', `<div class="job-os-grid">
      ${textField('applicant.full_name', 'Full name', v('applicant.full_name'))}
      ${textField('applicant.email', 'Email', v('applicant.email'), 'you@example.com', 'email')}
      ${textField('applicant.phone', 'Phone', v('applicant.phone'), '+1 555 0100', 'tel')}
      ${textField('applicant.location', 'Location', v('applicant.location'), 'City, Country')}
      ${textField('applicant.linkedin_url', 'LinkedIn', v('applicant.linkedin_url'), 'https://linkedin.com/in/…', 'url')}
      ${textField('applicant.portfolio_url', 'Website / portfolio', v('applicant.portfolio_url'), 'https://…', 'url')}</div>`);
    const scout = section('scout', 'Scout schedule', 'A scheduled job searches your saved searches on this interval.', `
      ${toggle('scout.enabled', 'Run Scout automatically', v('scout.enabled'))}
      <div class="job-os-grid">${numberField('scout.schedule_hours', 'Every', v('scout.schedule_hours'), 1, 168, 'hours')}${numberField('scout.max_results_per_search', 'Max results per search', v('scout.max_results_per_search'), 1, 100)}</div>
      <label class="job-os-field"><span>Never show jobs from</span><textarea data-setting="scout.blocked_companies" rows="3" placeholder="One company per line (e.g. your current employer)" spellcheck="false">${esc((v('scout.blocked_companies') || []).join('\n'))}</textarea></label>`);
    const notify = section('notifications', 'Notifications', gmailReady ? '' : 'Set up Gmail above to turn email on.', `
      ${toggle('notifications.email_enabled', 'Email me', v('notifications.email_enabled'), gmailReady ? '' : 'Needs Gmail credentials')}
      <div class="job-os-grid">${textField('notifications.to_address', 'Send to', v('notifications.to_address'), 'you@gmail.com', 'email')}</div>
      ${toggle('notifications.notify_new_matches', 'New matches', v('notifications.notify_new_matches'), 'When Scout finds a job at or above the score below')}
      <div class="job-os-grid">${numberField('notifications.min_fit_score', 'Minimum fit score', v('notifications.min_fit_score'), 0, 100, '/ 100')}</div>
      ${toggle('notifications.daily_digest', 'Daily digest', v('notifications.daily_digest'))}
      <div class="job-os-grid">${numberField('notifications.digest_hour', 'Digest hour', v('notifications.digest_hour'), 0, 23, ':00')}</div>
      ${toggle('notifications.reply_actions', 'Act on replies', v('notifications.reply_actions'), 'Each job in an alert has codes; reply "TAILOR 1A2B3C4D" or "SKIP 1A2B3C4D" from the Send-to address')}
      ${notifyStatus(state.notifications)}`);
    const resume = section('resume', 'Resume', 'Your master resume lives in Resume Studio.', '<button type="button" class="job-os-btn" data-job-os-view="resume-studio">Open Resume Studio</button>');
    const bar = `<div class="job-os-savebar" data-dirty="${dirty ? 'true' : 'false'}"><p id="job-os-settings-error" class="job-os-error" role="alert">${esc(state.settingsError || '')}</p><span class="job-os-savebar-note">${dirty ? 'Unsaved changes' : state.settingsSavedAt ? 'Saved' : ''}</span><button type="button" class="job-os-btn" data-job-os-action="discard-settings" ${dirty ? '' : 'disabled'}>Discard</button><button type="button" class="job-os-btn primary" data-job-os-action="save-settings" ${dirty ? '' : 'disabled'}>Save settings</button></div>`;
    return `<form id="job-os-settings-form" class="job-os-settings" novalidate>${firecrawl}${ai}${applicant}${scout}${notify}${resume}${bar}</form>`;
  }
  const EMAIL_KINDS = {matches: 'Match alert', digest: 'Digest', reply: 'Reply'};
  function notifyStatus(n) {
    if (!n) return '';
    const checked = n.last_poll ? `Replies checked ${esc(when(n.last_poll))}` : 'Replies not checked yet';
    const log = (n.log || []).slice(0, 6);
    return `<div class="job-os-notify-status">
      <p class="job-os-card-note">${n.last_digest ? `Last digest ${esc(n.last_digest)}. ` : ''}${checked}.${n.last_poll_error ? ` <span class="job-os-error">${esc(n.last_poll_error)}</span>` : ''}</p>
      <div class="job-os-actions"><button type="button" class="job-os-btn" data-job-os-action="notify-digest" ${n.ready ? '' : 'disabled'}>Send digest now</button><button type="button" class="job-os-btn" data-job-os-action="notify-check" ${n.ready ? '' : 'disabled'}>Check replies now</button></div>
      ${log.length ? `<ul class="job-os-email-log">${log.map((e) => `<li data-status="${esc(e.status)}"><strong>${esc(EMAIL_KINDS[e.kind] || e.kind)}</strong> ${esc(e.status)}${e.subject ? ` · ${esc(e.subject)}` : ''}${e.detail ? `<small>${esc(e.detail)}</small>` : ''}<time>${esc(when(e.created_at))}</time></li>`).join('')}</ul>` : ''}
    </div>`;
  }
  // ---- Pipeline board -----------------------------------------------------------
  // One column per stage, from new finds to closed. Each card says where the
  // job came from (Scout's Indeed finds or the manual tracker), where it is,
  // what it pays, and the one next step for its stage.
  function cardPrimary(job) {
    const id = esc(job.id);
    const st = job.status;
    if (st === 'discovered') return job.source === 'manual'
      ? `<button type="button" class="job-os-btn small" data-job-os-action="job-form-edit" data-job-id="${id}">Add description</button>`
      : `<button type="button" class="job-os-btn small" data-job-os-action="card-details" data-job-id="${id}">Fetch details</button>`;
    if (['scraped', 'analyzed', 'shortlisted'].includes(st)) return job.has_description
      ? `<button type="button" class="job-os-btn small" data-job-os-action="card-tailor" data-job-id="${id}">Tailor resume</button>` : '';
    if (st === 'tailoring') return '<span class="pipe-busy"><span class="auto-dots" aria-hidden="true"><i></i><i></i><i></i></span>Tailoring</span>';
    if (st === 'resume_ready') return `<button type="button" class="job-os-btn small" data-job-os-action="studio-open" data-job-id="${id}">Review resume</button>`;
    if (['application_ready', 'awaiting_approval', 'applying'].includes(st)) return `<button type="button" class="job-os-btn primary small" data-job-os-action="board-apply" data-job-id="${id}" data-url="${esc(job.canonical_url)}">Apply</button>`;
    return '';
  }
  function moveSelect(job) {
    if (!(job.moves || []).length) return '';
    return `<label class="pipe-move"><span class="sr-only">Move ${esc(job.title)} to</span><select data-job-os-change="board-move" data-job-id="${esc(job.id)}" data-revision="${Number(job.revision)}"><option value="">Move to…</option>${job.moves.map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join('')}</select></label>`;
  }
  function pipeCard(job) {
    const src = sourceOf(job);
    const where = place(job);
    const work = [WORKPLACE[job.workplace], job.employment_type].filter(Boolean).join(' · ');
    const facts = [
      where ? `<span class="pipe-fact">${icon('pin', 13)}<span>${esc(where)}</span></span>` : '',
      job.salary_text ? `<span class="pipe-fact">${icon('pay', 13)}<span>${esc(job.salary_text)}</span></span>` : '',
      work ? `<span class="pipe-fact">${icon('briefcase', 13)}<span>${esc(work)}</span></span>` : '',
    ].join('');
    const primary = cardPrimary(job);
    const move = moveSelect(job);
    const applied = job.applied ? ` · applied ${esc(when(job.applied.at))}` : '';
    return `<article class="pipe-card${analysing(job) ? ' is-analysing' : ''}" data-board-job="${esc(job.id)}" data-status="${esc(job.status)}" data-source="${src}">
      <button type="button" class="pipe-card-main" data-job-id="${esc(job.id)}">
        <span class="pipe-card-head"><span class="pipe-card-title"><strong>${esc(job.title)}</strong><span>${esc(job.company || 'Company not set')}</span></span>${fitRing(job.analysis, 'small')}</span>
        ${facts ? `<span class="pipe-facts">${facts}</span>` : ''}
      </button>
      ${(job.attention || []).map((reason) => `<p class="board-attention">${esc(reason)}</p>`).join('')}
      <div class="pipe-card-meta"><span class="pipe-source" data-source="${src}">${SOURCE_LABEL[src]}</span>${['closed', 'offers'].includes(job.column) ? badge(job.status) : ''}<small>${esc(when(job.updated_at))}${applied}</small></div>
      ${primary || move ? `<div class="pipe-card-actions">${primary}${move}</div>` : ''}</article>`;
  }
  function pipelineBoard(state) {
    const board = state.board;
    if (!board) return '<section class="job-os-card"><p class="job-os-card-note">Loading…</p></section>';
    const total = board.columns.reduce((n, c) => n + c.jobs.length, 0);
    if (!total) return emptyPipeline(state);
    return `<div class="pipe-board" role="list" aria-label="Pipeline stages">${board.columns.map((c) => `<section class="pipe-col" data-col="${esc(c.key)}" role="listitem" aria-label="${esc(c.label)}"><header class="pipe-col-head"><h3>${esc(c.label)}</h3><span class="job-os-count">${c.jobs.length}</span></header><div class="pipe-col-cards">${c.jobs.map((j) => pipeCard(Object.assign({column: c.key}, j))).join('') || '<p class="pipe-empty">Nothing here</p>'}</div></section>`).join('')}</div>`;
  }
  function emptyPipeline(state) {
    const src = state.pipelineSource;
    const title = src === 'manual' ? 'No tracked jobs yet' : src === 'indeed' ? 'No Indeed finds yet' : 'Your pipeline is empty';
    const body = src === 'manual' ? 'Add a job you found yourself — paste its link and description, then score and tailor your resume for it.'
      : src === 'indeed' ? 'Create a Scout search for your job titles and the cities you want; every posting it finds lands here.'
        : 'Scout fills it from Indeed, or add a job you found yourself.';
    const actions = [src !== 'manual' ? '<button type="button" class="job-os-btn" data-job-os-view="scout">Open Scout</button>' : '',
      src !== 'indeed' ? `<button type="button" class="job-os-btn primary" data-job-os-action="job-form-new">${icon('import', 14)}Add job</button>` : ''].join('');
    return `<section class="job-os-card job-os-empty pipe-empty-state"><strong>${title}</strong><p>${body}</p><div class="job-os-actions">${actions}</div></section>`;
  }
  // ---- Job drawer: details, actions, notes -----------------------------------------
  const EVENT_TEXT = {job_created: 'Saved', application_submitted: 'Applied', details_edited: 'Details edited'};
  function activity(state) {
    const items = (state.jobTimeline || []).slice().reverse().filter((e) => e.type === 'note' || e.type === 'status_changed' || EVENT_TEXT[e.type]);
    const rows = items.slice(0, 30).map((e) => {
      const text = e.type === 'note' ? esc(e.data.text) : e.type === 'status_changed' ? `Moved to <strong>${esc(statusLabel(e.data.to))}</strong>` : esc(EVENT_TEXT[e.type]);
      return `<li data-kind="${e.type === 'note' ? 'note' : 'event'}"><span>${text}</span><time>${esc(when(e.at))}</time></li>`;
    }).join('');
    return `<section class="job-drawer-section"><h3>Notes &amp; activity</h3>
      <form id="job-os-note-form" class="job-note-form"><textarea name="text" rows="2" maxlength="2000" placeholder="Add a note — a recruiter call, a referral, a follow-up date"></textarea><button type="submit" class="job-os-btn">Add note</button></form>
      ${rows ? `<ul class="job-activity">${rows}</ul>` : ''}</section>`;
  }
  function jobDrawer(state) {
    const job = state.jobDetail;
    if (!job) return '';
    const src = sourceOf(job);
    const where = place(job);
    const meta = [job.company, where].filter(Boolean).map(esc).join(' · ');
    return `<div class="job-drawer-backdrop" data-job-os-action="job-close"></div>
      <aside class="job-drawer" id="job-os-detail" role="dialog" aria-label="${esc(job.title)}">
        <header class="job-drawer-head"><div class="job-drawer-title"><div class="job-drawer-tags">${badge(job.status)}<span class="pipe-source" data-source="${src}">${SOURCE_LABEL[src]}</span></div><h2>${esc(job.title)}</h2>${meta ? `<p>${meta}</p>` : ''}</div>
          <button type="button" class="wh-insp-close job-os-detail-close" data-job-os-action="job-close" aria-label="Close details">×</button></header>
        <div class="job-drawer-body">
          ${jobChips(job)}
          <div class="job-os-actions">${detailActions(job)}<a class="job-os-btn" href="${esc(job.canonical_url)}" target="_blank" rel="noopener noreferrer">${icon('external', 14)}Open posting</a><button type="button" class="job-os-btn" data-job-os-action="job-form-edit" data-job-id="${esc(job.id)}">${icon('edit', 14)}Edit</button></div>
          ${job.status === 'tailoring' ? writingPanel('Luna is tailoring your resume and cover letter for this job…') : ''}
          ${interviewPanel(job)}
          ${analysisPanel(job)}
          ${job.description ? `<details class="job-os-desc-wrap"${job.analysis && job.analysis.status === 'done' ? '' : ' open'}><summary>Job description</summary><div class="job-os-description">${esc(job.description)}</div></details>`
            : `<p class="job-os-card-note">No description yet. ${src === 'manual' ? 'Edit the job and paste it in to' : 'Fetch details to'} score and tailor your resume for it.</p>`}
          ${activity(state)}
        </div></aside>`;
  }
  // ---- Job form: the manual tracker (add) and editing any job ---------------------------
  const EMPLOYMENT = ['Full time', 'Part time', 'Contract', 'Internship', 'Temporary'];
  function jobForm(state) {
    const f = state.jobForm;
    if (!f) return '';
    const editing = !!f.id;
    const field = (name, label, attrs, wide) => `<label class="job-os-field${wide ? ' wide' : ''}"><span>${label}</span><input name="${name}" value="${esc(f[name])}" ${attrs || ''}></label>`;
    const options = (values, current, blank) => `<option value="">${blank}</option>${values.map(([v, l]) => `<option value="${esc(v)}" ${v === current ? 'selected' : ''}>${esc(l)}</option>`).join('')}`;
    const countries = (state.countries || []).map((c) => `<option value="${esc(c.name)}"></option>`).join('');
    return `<div class="job-drawer-backdrop" data-job-os-action="job-form-close"></div>
      <aside class="job-drawer job-form-drawer" role="dialog" aria-label="${editing ? 'Edit job' : 'Add a job'}">
        <header class="job-drawer-head"><div class="job-drawer-title"><h2>${editing ? 'Edit job' : 'Add a job'}</h2><p>${editing ? 'Correct the details or paste in the description.' : 'Track a job you found yourself. With its description, Luna can score your resume against it and tailor one for it.'}</p></div>
          <button type="button" class="wh-insp-close" data-job-os-action="job-form-close" aria-label="Close">×</button></header>
        <form id="job-os-job-form" class="job-drawer-body job-form" novalidate>
          <div class="job-form-grid">
            ${field('title', 'Job title <em>required</em>', 'required maxlength="240" placeholder="e.g. Data Analyst"', true)}
            ${field('company', 'Company', 'maxlength="240"')}
            ${field('canonical_url', 'Job link <em>required</em>', `type="url" required placeholder="https://" ${editing ? 'disabled' : ''}`)}
            ${field('country', 'Country', 'list="job-os-countries" maxlength="80" placeholder="e.g. Malaysia"')}
            ${field('location', 'City', 'maxlength="240" placeholder="e.g. Kuala Lumpur"')}
            ${field('salary_text', 'Salary', 'maxlength="120" placeholder="e.g. RM 6,000 – 8,000 / month"')}
            <label class="job-os-field"><span>Employment type</span><select name="employment_type">${options(EMPLOYMENT.map((e) => [e, e]), f.employment_type, 'Not set')}</select></label>
            <label class="job-os-field"><span>Workplace</span><select name="workplace">${options([['onsite', 'On-site'], ['hybrid', 'Hybrid'], ['remote', 'Remote']], f.workplace, 'Not set')}</select></label>
            ${editing ? '' : `<label class="job-os-field"><span>Stage</span><select name="stage"><option value="saved" ${f.stage !== 'applied' ? 'selected' : ''}>Saved — not applied yet</option><option value="applied" ${f.stage === 'applied' ? 'selected' : ''}>Already applied</option></select></label>`}
            <label class="job-os-field wide"><span>Job description</span><textarea name="description" rows="9" maxlength="20000" placeholder="Paste the full job description">${esc(f.description)}</textarea></label>
            ${editing ? '' : `<label class="job-os-field wide"><span>Note</span><textarea name="note" rows="2" maxlength="2000" placeholder="Optional — who referred you, where you found it">${esc(f.note)}</textarea></label>`}
          </div>
          <datalist id="job-os-countries">${countries}</datalist>
          <p class="job-os-error" role="alert">${esc(state.jobFormError || '')}</p>
          <div class="job-form-actions"><button type="button" class="job-os-btn" data-job-os-action="job-form-close">Cancel</button><button type="submit" class="job-os-btn primary">${editing ? 'Save changes' : 'Save job'}</button></div>
        </form></aside>`;
  }
  function funnelCard(funnel) {
    if (!funnel || !funnel.length || !funnel[0].count) return '';
    const max = Math.max(...funnel.map((s) => s.count), 1);
    return `<section class="job-os-card funnel-card"><div class="job-os-card-head"><h2>Your funnel</h2></div><div class="funnel">${funnel.map((s, i) => `<div class="funnel-row"><span>${esc(s.label)}</span><div class="funnel-track"><i style="--w:${Math.max(2, Math.round(100 * s.count / max))}%;--i:${i}"></i></div><strong data-count-key="funnel-${esc(s.key)}">${s.count}</strong></div>`).join('')}</div></section>`;
  }
  // ---- Pipeline toolbar ------------------------------------------------------
  function sortJobs(jobs, by) {
    if (by !== 'fit') return jobs;
    const score = (j) => (j.analysis && j.analysis.fit_score != null ? j.analysis.fit_score : -1);
    return jobs.slice().sort((a, b) => score(b) - score(a));
  }
  function pipelineBar(state, jobs, counts) {
    const unanalysed = jobs.filter((j) => j.status === 'scraped' && j.has_description && !j.analysis).length;
    const busy = jobs.filter(analysing).length;
    const tabs = [['all', 'All'], ['indeed', 'Indeed'], ['manual', 'Manual']].map(([key, text]) => {
      const on = state.pipelineSource === key;
      return `<button type="button" role="tab" aria-selected="${on}" class="seg-btn${on ? ' active' : ''}" data-job-os-action="pipe-source" data-source="${key}">${text}<span class="seg-count">${Number(counts[key] || 0)}</span></button>`;
    }).join('');
    const modes = [['board', 'Board'], ['list', 'List']].map(([key, text]) => {
      const on = state.pipelineMode === key;
      return `<button type="button" class="seg-btn icon${on ? ' active' : ''}" aria-pressed="${on}" data-job-os-action="pipe-mode" data-mode="${key}" title="${text}">${icon(key, 15)}<span class="sr-only">${text}</span></button>`;
    }).join('');
    const sort = state.pipelineMode === 'list' ? `<label class="job-os-inline-select">Sort <select id="job-os-sort" aria-label="Sort jobs"><option value="newest" ${state.sortBy === 'newest' ? 'selected' : ''}>Newest</option><option value="fit" ${state.sortBy === 'fit' ? 'selected' : ''}>Best match</option></select></label>` : '';
    return `<div class="pipe-toolbar"><div class="seg" role="tablist" aria-label="Where jobs came from">${tabs}</div><div class="seg" role="group" aria-label="Layout">${modes}</div>${sort}${busy ? `<span class="job-os-chip muted analysing-chip">Scoring ${busy}…</span>` : ''}<span class="scout-bar-spacer"></span>${unanalysed ? `<button type="button" class="job-os-btn" data-job-os-action="analyze-new">Score ${unanalysed} new</button>` : ''}<button type="button" class="job-os-btn primary" data-job-os-action="job-form-new">${icon('import', 14)}Add job</button></div>`;
  }
  // ---- Scout ------------------------------------------------------------
  const RUN_LABELS = {queued: 'Starting', searching: 'Searching job sites', scraping: 'Reading postings', completed: 'Finished',
    cancelled: 'Cancelled', failed: 'Failed', interrupted: 'Interrupted'};
  const ACTIVE_RUN = ['queued', 'searching', 'scraping'];
  const latestRun = (state, searchId) => (state.runs || []).find((run) => run.search_id === searchId) || null;
  function until(epoch) {
    const s = Math.round(Number(epoch || 0) - Date.now() / 1000);
    if (!epoch) return '';
    if (s <= 60) return 'any minute';
    if (s < 3600) return `in ${Math.round(s / 60)}m`;
    return `in ${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`;
  }
  // The run body is the only part repainted while polling, so the radar keeps spinning.
  function runBody(run) {
    const c = run.counts || {};
    const active = ACTIVE_RUN.includes(run.status);
    const stats = [['found', 'Found'], ['scraped', 'Read'], ['saved', 'New'], ['duplicates', 'Known'], ['closed', 'Closed']]
      .map(([key, label]) => `<span class="scout-stat${key === 'saved' && c.saved ? ' is-new' : ''}"><strong data-count-key="scout-${esc(run.id)}-${key}">${Number(c[key] || 0)}</strong>${label}</span>`).join('');
    const blocked = c.blocked ? `<span class="scout-stat"><strong>${Number(c.blocked)}</strong>Blocked</span>` : '';
    const errors = c.errors ? `<span class="scout-stat is-error"><strong>${Number(c.errors)}</strong>Errors</span>` : '';
    return `<div class="scout-run-head"><span class="scout-run-state" data-status="${esc(run.status)}">${esc(RUN_LABELS[run.status] || run.status)}</span><span class="scout-run-detail">${esc(run.stage_detail || '')}</span>${active ? `<button type="button" class="job-os-btn small" data-job-os-action="scout-cancel" data-run-id="${esc(run.id)}">Cancel</button>` : `<small>${esc(when(run.finished_at || run.created_at))}</small>`}</div><div class="scout-stats">${stats}${blocked}${errors}</div>`;
  }
  function runPanel(run) {
    if (!run) return '';
    const active = ACTIVE_RUN.includes(run.status);
    return `<div class="scout-run${active ? ' is-active' : ''}" data-run-panel="${esc(run.id)}" data-status="${esc(run.status)}">${active ? '<span class="scout-radar" aria-hidden="true"><i></i><i></i><i></i></span>' : ''}<div class="scout-run-body" aria-live="polite">${runBody(run)}</div></div>`;
  }
  function searchCard(search, state) {
    const run = latestRun(state, search.id);
    const active = run && ACTIVE_RUN.includes(run.status);
    const ready = state.firecrawl && state.firecrawl.state === 'healthy';
    const where = [...(search.locations || []), search.remote_only ? 'Remote only' : '', POSTED[search.posted_within_days] || ''].filter(Boolean);
    const country = search.country_name ? `${icon('pin', 12)}${esc(search.country_name)}` : 'Choose a country';
    const schedule = state.schedule && state.schedule.enabled && search.enabled && search.next_run_at ? `Next ${until(search.next_run_at)}` : '';
    return `<article class="job-os-card scout-search${search.enabled ? '' : ' is-off'}" data-search-id="${esc(search.id)}">
      <div class="scout-search-head"><div class="scout-search-title"><h3>${esc(search.name)}</h3><p>${esc(search.keywords)}</p></div>
        <label class="job-os-toggle compact" title="${search.enabled ? 'Included in scheduled runs' : 'Paused'}"><input type="checkbox" data-job-os-action="scout-toggle" data-search-id="${esc(search.id)}" ${search.enabled ? 'checked' : ''}><span class="job-os-toggle-track" aria-hidden="true"></span><span class="sr-only">Enabled</span></label></div>
      <div class="job-os-chips"><span class="job-os-chip scout-country"${search.country_name ? '' : ' data-kind="warn"'} title="Searched on ${esc((state.countries || []).find((c) => c.code === search.country)?.host || 'Indeed')}">${country}</span>${where.map((w) => `<span class="job-os-chip">${esc(w)}</span>`).join('')}${search.last_run_at ? `<span class="job-os-chip muted">Last run ${esc(when(search.last_run_at))}</span>` : ''}${schedule ? `<span class="job-os-chip muted">${esc(schedule)}</span>` : ''}</div>
      ${runPanel(run)}
      <div class="job-os-actions"><button type="button" class="job-os-btn primary" data-job-os-action="scout-run" data-search-id="${esc(search.id)}" ${active || !ready ? 'disabled' : ''} title="${ready ? '' : 'Firecrawl is not ready — see Settings'}">${active ? 'Running…' : 'Run now'}</button><button type="button" class="job-os-btn" data-job-os-action="scout-edit" data-search-id="${esc(search.id)}">Edit</button><button type="button" class="job-os-btn job-os-btn-danger" data-job-os-action="scout-delete" data-search-id="${esc(search.id)}">Delete</button></div>
    </article>`;
  }
  const POSTED = {1: 'Last 24 hours', 3: 'Last 3 days', 7: 'Last 7 days', 14: 'Last 14 days'};
  function searchFormCard(form, state) {
    if (!form) return '';
    const editing = !!form.id;
    const countries = (state.countries || []).map((c) => `<option value="${esc(c.code)}" ${c.code === form.country ? 'selected' : ''}>${esc(c.name)}</option>`).join('');
    const posted = (state.postedWithin || [0, 1, 3, 7, 14]).map((d) => `<option value="${d}" ${Number(form.posted_within_days) === d ? 'selected' : ''}>${esc(POSTED[d] || 'Any time')}</option>`).join('');
    const host = ((state.countries || []).find((c) => c.code === form.country) || {}).host;
    return `<section class="job-os-card scout-form" id="scout-form"><div class="job-os-card-head"><div><h2>${editing ? 'Edit search' : 'New Indeed search'}</h2><p class="job-os-card-note">Scout searches ${host ? `<code>${esc(host)}</code>` : 'Indeed'} for these titles in each city and reads every posting it finds.</p></div></div>
      <form id="job-os-search-form" novalidate><div class="scout-form-grid">
        <label class="job-os-field wide"><span>Job titles or keywords <em>required</em></span><input name="keywords" required maxlength="200" placeholder="e.g. data analyst, SQL" value="${esc(form.keywords)}"></label>
        <label class="job-os-field"><span>Country <em>required</em></span><select name="country" required data-job-os-change="scout-country"><option value="">Choose…</option>${countries}</select></label>
        <label class="job-os-field"><span>Cities</span><input name="locations" placeholder="Comma-separated, e.g. Kuala Lumpur, Penang. Empty = whole country" value="${esc(form.locations)}"></label>
        <label class="job-os-field"><span>Date posted</span><select name="posted_within_days">${posted}</select></label>
        <label class="job-os-field"><span>Name</span><input name="name" maxlength="80" placeholder="Defaults to the keywords" value="${esc(form.name)}"></label>
      </div>
      <label class="job-os-toggle"><input type="checkbox" name="remote_only" ${form.remote_only ? 'checked' : ''}><span class="job-os-toggle-track" aria-hidden="true"></span><span class="job-os-toggle-text"><strong>Remote only</strong><small>Search for remote roles and skip postings that are not remote</small></span></label>
      <p class="job-os-error" role="alert">${esc(state.searchError || '')}</p>
      <div class="job-os-actions"><button type="submit" class="job-os-btn primary">${editing ? 'Save search' : 'Create search'}</button><button type="button" class="job-os-btn" data-job-os-action="scout-form-close">Cancel</button></div></form></section>`;
  }
  function scoutView(state) {
    const searches = state.searches || [];
    const fc = state.firecrawl || {};
    const provider = state.searchProvider === 'brave' ? 'Brave Search API' : 'Firecrawl search';  // used only if Indeed refuses its results page
    const sched = state.schedule && state.schedule.enabled ? `Scheduled every ${state.schedule.hours}h` : 'Schedule off';
    const banner = fc.state && fc.state !== 'healthy'
      ? `<div class="scout-banner" role="status">${esc(fc.detail || 'Firecrawl is not ready.')} Scout can't run until it is. <button type="button" class="job-os-link" data-job-os-view="settings">Open Settings</button></div>` : '';
    const recent = (state.runs || []).filter((run) => run.counts && run.counts.saved && !ACTIVE_RUN.includes(run.status)).slice(0, 1)[0];
    const newIds = new Set(recent ? recent.new_job_ids : []);
    const finds = (state.jobs || []).filter((job) => newIds.has(job.id));
    return `${banner}<div class="scout-bar"><span class="job-os-chip muted" title="If Indeed refuses its results page, Scout searches the web for that Indeed site with ${esc(provider)}">Source: Indeed</span><button type="button" class="job-os-chip muted as-link" data-job-os-view="settings">${esc(sched)}</button><span class="scout-bar-spacer"></span><button type="button" class="job-os-btn primary" data-job-os-action="scout-new">New search</button></div>
      ${searchFormCard(state.searchForm, state)}
      ${searches.length ? `<div class="scout-searches">${searches.map((s) => searchCard(s, state)).join('')}</div>`
        : (state.searchForm ? '' : '<section class="job-os-card job-os-empty"><strong>No saved searches yet</strong><p>Create one with the job titles you want, the Indeed country and, optionally, cities. Scout reads every posting it finds — title, company, pay and the full description — and adds it to your Pipeline.</p></section>')}
      ${finds.length ? `<section class="job-os-card"><div class="job-os-card-head"><h2>Latest finds <span class="job-os-count">${finds.length}</span></h2><button type="button" class="job-os-link" data-job-os-view="pipeline">View in Pipeline</button></div><div class="job-os-list scout-finds">${finds.map(jobCard).join('')}</div></section>` : ''}`;
  }
  // ---- Job detail -------------------------------------------------------------
  function writingPanel(text) {
    return `<div class="writing-panel" role="status"><span class="writing-pen" aria-hidden="true"></span><div><strong>${esc(text)}</strong><div class="writing-lines"><i></i><i></i><i></i><i></i></div></div></div>`;
  }
  const DOC_STATUS = {pending: 'Queued', running: 'Writing', ready: 'Ready', needs_review: 'Needs review', failed: 'Failed'};
  function docStatus(status) { return `<span class="doc-status" data-status="${esc(status)}">${esc(DOC_STATUS[status] || status)}</span>`; }
  function tailoredList(state) {
    const items = state.tailored || [];
    if (!items.length) return `<section class="job-os-card"><div class="job-os-card-head"><h2>Tailored versions</h2></div><p class="job-os-card-note">Choose <strong>Tailor resume</strong> on any job with a description. Each tailored resume and cover letter appears here to review, edit and export.</p></section>`;
    return `<section class="job-os-card"><div class="job-os-card-head"><h2>Tailored versions <span class="job-os-count">${items.length}</span></h2></div><div class="job-os-list">${items.map((d) => {
      const cov = d.notes && d.notes.coverage && d.notes.coverage.score;
      return `<button type="button" class="job-os-job-card studio-item" data-job-os-action="studio-open" data-job-id="${esc(d.job_id)}"><span class="job-os-job-avatar" aria-hidden="true">${esc(String(d.job_company || d.job_title || '?').charAt(0).toUpperCase())}</span><span class="job-os-job-main"><strong>${esc(d.job_title)}</strong><span>${esc(d.job_company || '')}</span></span>${cov != null ? `<span class="job-os-chip muted" title="Must-haves the resume mentions">${cov}% keywords</span>` : ''}${docStatus(d.status)}<small class="job-os-job-when">${esc(when(d.updated_at))}</small></button>`;
    }).join('')}</div></section>`;
  }
  function highlightNumbers(text, flags) {
    let out = esc(text);
    (flags || []).forEach((n) => { const e = esc(n).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); out = out.replace(new RegExp(`(^|[^\\w.])(${e})(?![\\w])`, 'g'), '$1<mark title="Not in your master resume">$2</mark>'); });
    return out;
  }
  function studioEditor(state) {
    const docs = state.studioDocs || {};
    const doc = docs[state.studioTab];
    const job = (state.tailored || []).find((d) => d.job_id === state.studioJobId) || {};
    const tabs = ['resume', 'cover_letter'].map((k) => `<button type="button" class="${state.studioTab === k ? 'active' : ''}" data-job-os-action="studio-tab" data-tab="${k}">${k === 'resume' ? 'Resume' : 'Cover letter'}${docs[k] ? ' ' + docStatus(docs[k].status) : ''}</button>`).join('');
    let body;
    if (!doc) body = '<p class="job-os-card-note">Nothing here yet.</p>';
    else if (['pending', 'running'].includes(doc.status)) body = writingPanel('Luna is writing…');
    else if (doc.status === 'failed') body = `<p class="job-os-error">${esc(doc.error || 'Tailoring failed.')}</p><button type="button" class="job-os-btn" data-job-os-action="studio-retry">Try again</button>`;
    else {
      const notes = doc.notes || {};
      const flags = notes.unverified || [];
      const cov = notes.coverage;
      const draft = state.studioDraft != null ? state.studioDraft : doc.content;
      const exportUrl = (fmt) => `/api/job-os/documents/${encodeURIComponent(doc.id)}/export?format=${fmt}`;
      body = `${flags.length ? `<div class="studio-warning" role="alert"><strong>Check before sending:</strong> ${flags.map((f) => `<code>${esc(f)}</code>`).join(' ')} ${flags.length === 1 ? 'is' : 'are'} not in your master resume. Fix or remove ${flags.length === 1 ? 'it' : 'them'}, then save.</div>` : ''}
        <div class="studio-grid"><div class="studio-edit"><textarea id="studio-text" spellcheck="true" aria-label="Edit document">${esc(draft)}</textarea>
          <div class="job-os-actions"><button type="button" class="job-os-btn primary" data-job-os-action="studio-save" ${state.studioDraft == null || state.studioDraft === doc.content ? 'disabled' : ''}>Save edits</button>
          <a class="job-os-btn" href="${exportUrl('docx')}">DOCX</a><a class="job-os-btn" href="${exportUrl('pdf')}" target="_blank" rel="noopener">PDF</a><a class="job-os-btn" href="${exportUrl('md')}">Markdown</a></div></div>
        <aside class="studio-side">${state.studioTab === 'resume' && cov && cov.score != null ? `<div class="studio-box"><h4>Keyword coverage <span class="cov-score">${cov.score}%</span></h4><div class="job-os-chips">${(cov.found || []).map((k) => `<span class="job-os-chip" data-kind="remote">✓ ${esc(k)}</span>`).join('')}${(cov.missing || []).map((k) => `<span class="job-os-chip muted">${esc(k)}</span>`).join('')}</div></div>` : ''}
          ${(notes.changes || []).length ? `<div class="studio-box"><h4>What Luna changed</h4><ul class="analysis-list is-need">${notes.changes.map((c) => `<li><strong>${esc(c.what)}</strong>${c.why ? ` — ${esc(c.why)}` : ''}</li>`).join('')}</ul></div>` : ''}
          ${flags.length ? `<div class="studio-box"><h4>Preview</h4><div class="studio-preview">${highlightNumbers(doc.content, flags)}</div></div>` : ''}</aside></div>`;
    }
    const ready = job.job_status === 'resume_ready';
    return `<section class="job-os-card studio-editor" id="studio-editor"><div class="job-os-card-head"><div><h2>${esc(job.job_title || 'Tailored documents')}</h2><p class="job-os-card-note">${esc(job.job_company || '')}</p></div><div class="job-os-actions">${ready ? '<button type="button" class="job-os-btn primary" data-job-os-action="studio-ready">Ready to apply</button>' : ''}<button type="button" class="job-os-btn" data-job-os-action="studio-close">Back to list</button></div></div>
      <nav class="studio-tabs" aria-label="Document">${tabs}</nav>${body}</section>`;
  }
  // ---- Resume Studio: how well the master resume matches one job ----------------------
  function matchRing(a) {
    if (!a) return '<div class="match-ring is-empty" aria-label="Not scored yet"><span><strong>—</strong><small>Not scored</small></span></div>';
    if (['pending', 'running'].includes(a.status)) return '<div class="match-ring is-busy" aria-label="Scoring"><span><strong>…</strong><small>Scoring</small></span></div>';
    if (a.status === 'failed' || a.fit_score == null) return '<div class="match-ring is-failed" aria-label="Scoring failed"><span><strong>!</strong><small>Failed</small></span></div>';
    const [, key, text] = band(a.fit_score);
    return `<div class="match-ring" data-band="${key}" style="--fit:${Number(a.fit_score)}" role="img" aria-label="${esc(text)}: ${Number(a.fit_score)} percent"><span><strong>${Number(a.fit_score)}%</strong><small>${esc(text)}</small></span></div>`;
  }
  function matchCheck(state) {
    if (!state.resume) return '';
    const jobs = newestFirst(state.jobs || []).filter((j) => j.has_description);
    const head = '<div class="job-os-card-head"><div><h2>Match check</h2><p class="job-os-card-note">How well your master resume matches a job, scored by Luna from the job description.</p></div></div>';
    if (!jobs.length) return `<section class="job-os-card match-card">${head}<p class="job-os-card-note">Save a job with its description — from Scout or with <button type="button" class="job-os-link" data-job-os-action="job-form-new">Add job</button> — to score your resume against it.</p></section>`;
    const job = state.studioMatch && jobs.some((j) => j.id === state.studioMatch.id) ? state.studioMatch : null;
    const picked = job ? job.id : jobs[0].id;
    const a = job ? job.analysis : (jobs[0].analysis || null);
    const list = (items, cls) => (items || []).slice(0, 4).map((i) => `<li>${esc(i)}</li>`).join('') ? `<ul class="analysis-list ${cls}">${(items || []).slice(0, 4).map((i) => `<li>${esc(i)}</li>`).join('')}</ul>` : '';
    const done = a && a.status === 'done';
    const busyNow = a && ['pending', 'running'].includes(a.status);
    const status = (job || jobs[0]).status;
    const canTailor = ['scraped', 'analyzed', 'shortlisted', 'resume_ready', 'application_ready'].includes(status);
    const hasDocs = ['tailoring', 'resume_ready', 'application_ready'].includes(status) || (state.tailored || []).some((d) => d.job_id === picked);
    const actions = [
      busyNow ? '' : `<button type="button" class="job-os-btn${done ? '' : ' primary'}" data-job-os-action="match-score" data-job-id="${esc(picked)}">${done ? 'Score again' : 'Score my resume'}</button>`,
      canTailor ? `<button type="button" class="job-os-btn${done ? ' primary' : ''}" data-job-os-action="card-tailor" data-job-id="${esc(picked)}">${['resume_ready', 'application_ready'].includes(status) ? 'Tailor again' : 'Tailor resume'}</button>` : '',
      hasDocs ? `<button type="button" class="job-os-btn" data-job-os-action="studio-open" data-job-id="${esc(picked)}">Open tailored resume</button>` : '',
    ].join('');
    return `<section class="job-os-card match-card">${head}
      <label class="job-os-field match-pick"><span>Job</span><select data-job-os-change="match-job">${jobs.map((j) => `<option value="${esc(j.id)}" ${j.id === picked ? 'selected' : ''}>${esc(j.title)}${j.company ? ` — ${esc(j.company)}` : ''} (${esc(SOURCE_LABEL[sourceOf(j)])})</option>`).join('')}</select></label>
      <div class="match-body">${matchRing(a)}<div class="match-detail">
        ${done && job && job.analysis.summary ? `<p>${esc(job.analysis.summary)}</p>` : `<p class="job-os-card-note">${busyNow ? 'Luna is reading the job against your resume…' : done ? '' : 'Not scored yet. Scoring takes a few seconds and uses one model call.'}</p>`}
        ${done && job ? `<div class="analysis-cols">${job.analysis.strengths && job.analysis.strengths.length ? `<div><h4>Matches</h4>${list(job.analysis.strengths, 'is-good')}</div>` : ''}${job.analysis.gaps && job.analysis.gaps.length ? `<div><h4>Missing</h4>${list(job.analysis.gaps, 'is-gap')}</div>` : ''}</div>` : ''}
        <div class="job-os-actions">${actions}</div>
        <p class="match-legend" aria-hidden="true"><span data-band="good">75–100 Good match</span><span data-band="fair">50–74 Needs improvement</span><span data-band="poor">0–49 Terrible match</span></p>
      </div></div></section>`;
  }
  function tailoredView(state) {
    return state.studioJobId ? studioEditor(state) : tailoredList(state);
  }
  function detailActions(job) {
    const out = [];
    const a = job.analysis;
    const st = job.status;
    const fresh = ['discovered', 'scraped', 'analyzed', 'shortlisted'].includes(st);
    if (!job.description && sourceOf(job) === 'indeed') out.push('<button type="button" class="job-os-btn primary" data-job-os-action="job-details">Fetch details</button>');
    if (['scraped', 'analyzed'].includes(st)) out.push(`<button type="button" class="job-os-btn${job.description ? '' : ' primary'}" data-job-os-action="job-status" data-status="shortlisted">Shortlist</button>`);
    if (['scraped', 'analyzed', 'shortlisted'].includes(st) && job.description) out.push('<button type="button" class="job-os-btn primary" data-job-os-action="job-tailor">Tailor resume</button>');
    if (['resume_ready', 'application_ready'].includes(st)) out.push(`<button type="button" class="job-os-btn primary" data-job-os-action="studio-open" data-job-id="${esc(job.id)}">Open in Resume Studio</button>`);
    if (st === 'resume_ready') out.push('<button type="button" class="job-os-btn" data-job-os-action="job-ready">Ready to apply</button>');
    if (fresh || ['resume_ready', 'application_ready'].includes(st)) out.push(`<button type="button" class="job-os-btn" data-job-os-action="board-apply" data-job-id="${esc(job.id)}" data-url="${esc(job.canonical_url)}">Mark applied</button>`);
    if (job.description && !analysing(job)) out.push(`<button type="button" class="job-os-btn" data-job-os-action="job-analyze">${a && a.status === 'done' ? 'Score again' : 'Score resume'}</button>`);
    if (fresh) out.push('<button type="button" class="job-os-btn" data-job-os-action="job-status" data-status="skipped">Skip</button>');
    const prep = job.interview;
    if (['screening', 'interviewing', 'offer'].includes(st) && !(prep && ['pending', 'running'].includes(prep.status))) {
      out.unshift(`<button type="button" class="job-os-btn${prep && prep.status === 'done' ? '' : ' primary'}" data-job-os-action="job-interview">${prep && prep.status === 'done' ? 'Refresh interview prep' : 'Prepare for interview'}</button>`);
    }
    return out.join('');
  }
  function analysisPanel(job) {
    const a = job.analysis;
    if (!a) return '';
    if (analysing(job)) return '<div class="job-os-analysis is-busy"><span class="fit-ring large is-busy"><span>…</span></span><div><strong>Luna is scoring your resume against this job…</strong><div class="analysis-shimmer"><i></i><i></i><i></i></div></div></div>';
    if (a.status === 'failed') return `<div class="job-os-analysis is-failed"><span class="fit-ring large is-failed"><span>!</span></span><div><strong>Analysis failed</strong><p>${esc(a.error || '')}</p></div></div>`;
    const list = (items, cls) => (items || []).length ? `<ul class="analysis-list ${cls}">${items.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>` : '';
    return `<div class="job-os-analysis">${fitRing(a, 'large')}<div class="analysis-body"><div class="analysis-head"><strong class="analysis-verdict" data-band="${band(a.fit_score)[1]}">${esc(band(a.fit_score)[2])} · ${Number(a.fit_score)}%</strong>${a.seniority ? `<span class="job-os-chip muted">${esc(a.seniority)}</span>` : ''}</div>
      ${a.summary ? `<p>${esc(a.summary)}</p>` : ''}
      <div class="analysis-cols">${a.strengths && a.strengths.length ? `<div><h4>Strengths</h4>${list(a.strengths, 'is-good')}</div>` : ''}${a.gaps && a.gaps.length ? `<div><h4>Gaps</h4>${list(a.gaps, 'is-gap')}</div>` : ''}${a.must_haves && a.must_haves.length ? `<div><h4>Must-haves</h4>${list(a.must_haves, 'is-need')}</div>` : ''}</div>
      ${a.salary_note ? `<p class="job-os-card-note">${esc(a.salary_note)}</p>` : ''}</div></div>`;
  }
  // ---- Resume Studio ---------------------------------------------------------
  function resumeView(state) {
    const r = state.resume;
    const upload = `<div class="resume-drop" id="resume-drop" tabindex="0" role="button" aria-label="Upload resume"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/></svg><strong>Drop your resume here</strong><span>or click to choose · PDF, DOCX, Markdown or text · up to 5 MB</span><input type="file" id="resume-file" accept=".pdf,.docx,.md,.markdown,.txt" hidden></div>
      <details class="resume-paste"><summary>Paste text instead</summary><textarea id="resume-text" rows="8" placeholder="Paste your resume text"></textarea><button type="button" class="job-os-btn" data-job-os-action="resume-paste">Save pasted resume</button></details>
      <p class="job-os-error" role="alert">${esc(state.resumeError || '')}</p>`;
    if (!r || state.resumeReplacing) {
      return `<section class="job-os-card"><div class="job-os-card-head"><h2>${r ? 'Replace your master resume' : 'Your master resume'}</h2>${r ? '<button type="button" class="job-os-link" data-job-os-action="resume-cancel">Cancel</button>' : ''}</div><p class="job-os-card-note">Everything Hermes tailors comes from this file. It only rephrases, reorders and selects from it; it never adds experience you do not have.</p>${upload}</section>`;
    }
    return `<section class="job-os-card resume-master"><div class="job-os-card-head"><h2>Master resume</h2><button type="button" class="job-os-btn" data-job-os-action="resume-replace">Replace</button></div>
      <div class="job-os-chips"><span class="job-os-chip">${esc(r.filename)}</span><span class="job-os-chip muted">${Number(r.words || 0).toLocaleString()} words</span><span class="job-os-chip muted">Updated ${esc(when(r.uploaded_at))}</span><span class="job-os-chip muted">Version ${Number(r.revision || 1)}</span></div>
      <details class="job-os-desc-wrap"><summary>Show text</summary><div class="job-os-description">${esc(r.text)}</div></details></section>`;
  }
  function interviewPanel(job) {
    const p = job.interview;
    if (!p) return '';
    if (['pending', 'running'].includes(p.status)) return writingPanel('Luna is preparing interview questions, stories and research for this job…');
    if (p.status === 'failed') return `<div class="job-os-analysis is-failed"><div><strong>Interview prep failed</strong><p>${esc(p.error || '')}</p></div></div>`;
    const list = (items) => (items || []).map((i) => `<li>${esc(i)}</li>`).join('');
    const questions = (p.questions || []).map((q) => `<details class="prep-q"${q.supported ? '' : ' data-gap="true"'}><summary>${esc(q.question)}${q.supported ? '' : '<span class="job-os-chip muted">Prepare</span>'}</summary>${q.why ? `<p class="prep-why">${esc(q.why)}</p>` : ''}<p>${esc(q.outline)}</p></details>`).join('');
    const stories = (p.stories || []).map((s) => `<div class="prep-story"><strong>${esc(s.title)}</strong><dl><dt>Situation</dt><dd>${esc(s.situation)}</dd><dt>Action</dt><dd>${esc(s.action)}</dd><dt>Result</dt><dd>${esc(s.result)}</dd></dl>${s.use_for ? `<small>Use for: ${esc(s.use_for)}</small>` : ''}</div>`).join('');
    const block = (title, items) => (items || []).length ? `<div><h4>${title}</h4><ul class="analysis-list">${list(items)}</ul></div>` : '';
    return `<section class="job-os-prep"><div class="job-os-card-head"><h3>Interview prep</h3><a class="job-os-link" href="/api/job-os/jobs/${encodeURIComponent(job.id)}/interview-prep.md" download>Download</a></div>
      <h4>Likely questions</h4><div class="prep-questions">${questions}</div>
      ${stories ? `<h4>Stories to rehearse</h4><div class="prep-stories">${stories}</div>` : ''}
      <div class="analysis-cols">${block('Ask them', p.ask_them)}${block('Research', p.research)}${block('Watch-outs', p.watch_outs)}</div></section>`;
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
        <section class="job-os-metrics" aria-label="Job dashboard">${metric('total', dashboard.total_jobs, 'Total jobs', 'data-job-os-filter=""')}${metric('active', dashboard.active_work, 'Active work', 'data-job-os-filter="tailoring"')}${metric('attention', dashboard.needs_attention, 'Needs attention', 'data-job-os-view="pipeline"')}${metric('applied', appliedCount(byStatus), 'Applied', 'data-job-os-filter="submitted"')}</section>
        ${funnelCard(dashboard.funnel)}
        ${automationsCard(state.automations)}
        <div class="job-os-columns">
          <section class="job-os-card job-os-recent"><div class="job-os-card-head"><h2>Recent jobs</h2><button type="button" class="job-os-link" data-job-os-view="pipeline">View pipeline</button></div>${jobList(jobs.slice(0, 12), 'No jobs saved yet', 'Import a role to start tracking it through your pipeline.')}</section>
          <section class="job-os-card job-os-import"><div class="job-os-card-head"><h2>Track a job</h2></div><p class="job-os-card-note">Found a role on another site? Save its link and description here to score and tailor your resume for it, then follow it through your pipeline.</p><button class="job-os-btn primary" type="button" data-job-os-action="job-form-new">${icon('import', 14)}Add job</button></section>
        </div>${jobForm(state)}`;
    } else if (view === 'pipeline') {
      const filter = state.statusFilter;
      const src = state.pipelineSource || 'all';
      const scoped = jobs.filter((j) => src === 'all' || sourceOf(j) === src);
      const counts = state.board && state.board.sources ? state.board.sources
        : {all: jobs.length, indeed: jobs.filter((j) => sourceOf(j) === 'indeed').length, manual: jobs.filter((j) => sourceOf(j) === 'manual').length};
      const listMode = state.pipelineMode === 'list' || filter;
      const list = `<section class="job-os-card job-os-fill"><div class="job-os-card-head"><h2>${filter ? `<span class="job-os-filter-label">${esc(statusLabel(filter))}</span>` : 'All jobs'} <span class="job-os-count">${scoped.length}</span></h2>${filter ? '<button type="button" class="job-os-link" data-job-os-filter="">Show the board</button>' : ''}</div>${scoped.length ? jobList(sortJobs(scoped, state.sortBy), '', '') : emptyPipeline(state)}</section>`;
      body = `${header('Pipeline', 'Every job from new find to offer — Scout’s Indeed finds and the ones you track yourself.', state)}
        ${pipelineBar(state, jobs, counts)}
        ${listMode ? list : pipelineBoard(state)}
        ${jobDrawer(state)}${jobForm(state)}`;
    } else if (view === 'logistics') {
      const legend = [['strong', 'Strong fit'], ['good', 'Good fit'], ['stretch', 'Stretch'], ['poor', 'Poor fit'], ['none', 'Not scored']]
        .map(([key, text]) => `<span><i data-verdict="${key}"></i>${text}</span>`).join('');
      body = `${header('Logistics centre', 'Every job is a parcel moving through the warehouse. Click one to open it.', state)}
        <section class="logistics-wrap"><div id="job-os-logistics-slot" class="logistics-stage" data-slide-safe></div><div class="logistics-legend" aria-label="Parcel colours">${legend}<span class="logistics-legend-hint">Scroll to zoom</span></div></section>`;
    } else if (view === 'scout') {
      body = `${header('Scout', 'Saved searches find new postings on Indeed and read each one into your Pipeline.', state)}${scoutView(state)}${jobForm(state)}`;
    } else if (view === 'settings') {
      body = `${header('Settings', 'Connections, AI, schedules and notifications for this profile.', state)}${settingsView(state)}`;
    } else {
      body = `${header('Resume Studio', 'Your master resume, how well it matches each job, and the versions tailored from it.', state)}${resumeView(state)}${state.studioJobId ? '' : matchCheck(state)}${tailoredView(state)}${jobForm(state)}`;
    }
    return `<div class="job-os-shell" data-view="${esc(view)}">${mobileNav(view)}<main class="job-os-content">${body}</main></div>`;
  }
  function sidebar(state) {
    const view = state.activeView;
    const dashboard = dashboardOf(state);
    const byStatus = dashboard.by_status || {};
    const counts = {pipeline: dashboard.total_jobs};
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
  window.JobOSRender = {shell, sidebar, runBody};
}());
