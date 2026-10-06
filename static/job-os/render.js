(function () {
  const esc = (value) => String(value == null ? '' : value).replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const labels = {dashboard: 'Dashboard', scout: 'Scout', pipeline: 'Pipeline', 'resume-studio': 'Resume Studio', applications: 'Applications', logistics: 'Logistics', settings: 'Settings'};
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
  const WORKPLACE = {remote: 'Remote', hybrid: 'Hybrid', onsite: 'On-site'};
  function jobChips(job) {
    const chips = [];
    if (job.workplace) chips.push(`<span class="job-os-chip" data-kind="${esc(job.workplace)}">${esc(WORKPLACE[job.workplace] || job.workplace)}</span>`);
    if (job.salary_text) chips.push(`<span class="job-os-chip" data-kind="pay">${esc(job.salary_text)}</span>`);
    if (job.employment_type) chips.push(`<span class="job-os-chip">${esc(job.employment_type)}</span>`);
    return chips.length ? `<span class="job-os-chips">${chips.join('')}</span>` : '';
  }
  // Fit score ring: the arc fills to the score, coloured by verdict.
  const analysing = (job) => !!(job.analysis && (job.analysis.status === 'pending' || job.analysis.status === 'running'));
  function fitRing(a, size) {
    if (!a) return '';
    if (a.status === 'pending' || a.status === 'running') return `<span class="fit-ring ${size || ''} is-busy" title="Luna is analysing this job" aria-label="Analysing"><span>…</span></span>`;
    if (a.status === 'failed') return `<span class="fit-ring ${size || ''} is-failed" title="Analysis failed" aria-label="Analysis failed"><span>!</span></span>`;
    if (a.fit_score == null) return '';
    return `<span class="fit-ring ${size || ''}" data-verdict="${esc(a.verdict)}" style="--fit:${Number(a.fit_score)}" title="Fit ${Number(a.fit_score)}/100 · ${esc(a.verdict)}" aria-label="Fit score ${Number(a.fit_score)}"><span>${Number(a.fit_score)}</span></span>`;
  }
  function jobCard(job) {
    const initial = String(job.company || job.title || '?').trim().charAt(0).toUpperCase() || '?';
    const meta = [job.company || 'Company to review', job.location].filter(Boolean).map(esc).join(' · ');
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
    const applicant = section('applicant', 'Your details', 'Used on tailored resumes and application forms.', `<div class="job-os-grid">
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
    const auto = section('auto-apply', 'Auto-apply', 'Off unless you turn it on. Only standard application forms; anything unusual stops and asks you.', `
      ${toggle('auto_apply.enabled', 'Auto-apply to strong matches', v('auto_apply.enabled'))}
      <fieldset class="job-os-ats"><legend>Allowed application systems</legend>${ATS.map(([key, name]) => `<label><input type="checkbox" data-setting="auto_apply.allowed_ats" value="${key}" ${(v('auto_apply.allowed_ats') || []).includes(key) ? 'checked' : ''}>${esc(name)}</label>`).join('')}</fieldset>
      <div class="job-os-grid">${numberField('auto_apply.daily_cap', 'Daily limit', v('auto_apply.daily_cap'), 1, 50, 'applications')}${numberField('auto_apply.min_fit_score', 'Minimum fit score', v('auto_apply.min_fit_score'), 0, 100, '/ 100')}</div>
      ${toggle('auto_apply.dry_run_first', 'Dry run first', v('auto_apply.dry_run_first'), 'Fill the form and capture a screenshot without sending, before the first real submission to each site')}`);
    const resume = section('resume', 'Resume', 'Your master resume lives in Resume Studio.', '<button type="button" class="job-os-btn" data-job-os-view="resume-studio">Open Resume Studio</button>');
    const bar = `<div class="job-os-savebar" data-dirty="${dirty ? 'true' : 'false'}"><p id="job-os-settings-error" class="job-os-error" role="alert">${esc(state.settingsError || '')}</p><span class="job-os-savebar-note">${dirty ? 'Unsaved changes' : state.settingsSavedAt ? 'Saved' : ''}</span><button type="button" class="job-os-btn" data-job-os-action="discard-settings" ${dirty ? '' : 'disabled'}>Discard</button><button type="button" class="job-os-btn primary" data-job-os-action="save-settings" ${dirty ? '' : 'disabled'}>Save settings</button></div>`;
    return `<form id="job-os-settings-form" class="job-os-settings" novalidate>${firecrawl}${ai}${applicant}${scout}${notify}${auto}${resume}${bar}</form>`;
  }
  const EMAIL_KINDS = {matches: 'Match alert', digest: 'Digest', reply: 'Reply', preview: 'Ready to send'};
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
  // ---- Applications board -------------------------------------------------------
  const NEXT_OUTCOMES = {
    submitted: [['screening', 'Screening'], ['rejected', 'Rejected'], ['no_response', 'No response'], ['withdrawn', 'Withdrawn']],
    screening: [['interviewing', 'Interviewing'], ['rejected', 'Rejected'], ['no_response', 'No response'], ['withdrawn', 'Withdrawn']],
    interviewing: [['offer', 'Offer'], ['rejected', 'Rejected'], ['no_response', 'No response'], ['withdrawn', 'Withdrawn']],
    offer: [['offer_accepted', 'Accepted'], ['offer_declined', 'Declined'], ['withdrawn', 'Withdrawn']],
  };
  function autoPanel(job) {
    const auto = job.auto;
    if (job.status === 'applying' || (auto && auto.status === 'pending')) {
      return `<p class="board-auto is-busy"><span class="auto-dots" aria-hidden="true"><i></i><i></i><i></i></span>${job.status === 'applying' ? 'Sending the application…' : 'Filling the form…'}</p>`;
    }
    if (!auto || !auto.screenshots || !auto.screenshots.length || !['awaiting_approval', 'application_ready'].includes(job.status)) return '';
    const shot = auto.screenshots[auto.screenshots.length - 1];
    const src = `/api/job-os/jobs/${encodeURIComponent(job.id)}/proof/${encodeURIComponent(shot)}`;
    const filled = (auto.filled || []).length ? `<small>Filled ${auto.filled.length}: ${esc(auto.filled.slice(0, 4).join(', '))}${auto.filled.length > 4 ? '…' : ''}</small>` : '';
    return `<a class="board-proof" href="${src}" target="_blank" rel="noopener"><img src="${src}" alt="Screenshot of the filled application form" loading="lazy"><span>${auto.status === 'filled' ? 'Filled form — check before sending' : 'Last attempt'}</span></a>${filled}`;
  }
  let autoApply = null;
  function boardCard(job, column) {
    const applied = job.applied ? `<small class="board-meta">Applied ${esc(when(job.applied.at))}${job.applied.method === 'auto' ? ' · auto' : ''}</small>` : '';
    const outcomes = NEXT_OUTCOMES[job.status];
    const actions = [];
    const auto = job.auto;
    const busy = (auto && auto.status === 'pending') || job.status === 'applying';
    if (job.status === 'application_ready') {
      actions.push(`<button type="button" class="job-os-btn primary small" data-job-os-action="board-apply" data-job-id="${esc(job.id)}" data-url="${esc(job.canonical_url)}">Apply</button>`);
      if (job.ats && autoApply && autoApply.enabled && !busy) actions.push(`<button type="button" class="job-os-btn small" data-job-os-action="board-autofill" data-job-id="${esc(job.id)}" title="Fill the ${esc(job.ats)} form and take a screenshot, without sending">Auto-fill</button>`);
    }
    if (job.status === 'awaiting_approval' && !busy) {
      actions.push(`<button type="button" class="job-os-btn primary small" data-job-os-action="board-approve" data-job-id="${esc(job.id)}">Send application</button>`);
      actions.push(`<button type="button" class="job-os-btn small" data-job-os-action="board-cancel-apply" data-job-id="${esc(job.id)}">Don't send</button>`);
    }
    if (job.status === 'resume_ready') actions.push(`<button type="button" class="job-os-btn small" data-job-os-action="studio-open" data-job-id="${esc(job.id)}">Review resume</button>`);
    if (outcomes) actions.push(`<label class="board-outcome"><span class="sr-only">Update status</span><select data-job-os-change="board-outcome" data-job-id="${esc(job.id)}" data-revision="${Number(job.revision)}"><option value="">Update…</option>${outcomes.map(([v, l]) => `<option value="${v}">${l}</option>`).join('')}</select></label>`);
    return `<article class="board-card" data-board-job="${esc(job.id)}" data-status="${esc(job.status)}"${busy ? ' data-busy="true"' : ''}>
      <button type="button" class="board-card-main" data-job-id="${esc(job.id)}">${fitRing(job.analysis, 'small')}<span><strong>${esc(job.title)}</strong><small>${esc([job.company, job.location].filter(Boolean).join(' · '))}</small></span></button>
      ${(job.attention || []).map((reason) => `<p class="board-attention">${esc(reason)}</p>`).join('')}
      ${autoPanel(job)}${applied}${column === 'closed' || column === 'offers' ? badge(job.status) : ''}
      ${actions.length ? `<div class="board-actions">${actions.join('')}</div>` : ''}</article>`;
  }
  function boardView(state) {
    autoApply = state.autoApply;
    const board = state.board;
    if (!board) return '<section class="job-os-card"><p class="job-os-card-note">Loading…</p></section>';
    const total = board.columns.reduce((n, c) => n + c.jobs.length, 0);
    if (!total) return '<section class="job-os-card job-os-empty"><strong>No applications yet</strong><p>Shortlist jobs in Pipeline and tailor a resume; they appear here, ready to send.</p></section>';
    return `<div class="board" role="list">${board.columns.map((c) => `<section class="board-col" data-col="${esc(c.key)}" role="listitem" aria-label="${esc(c.label)}"><header><h3>${esc(c.label)}</h3><span class="job-os-count">${c.jobs.length}</span></header><div class="board-cards">${c.jobs.map((j) => boardCard(j, c.key)).join('') || '<p class="board-empty">—</p>'}</div></section>`).join('')}</div>`;
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
  function pipelineBar(state, jobs) {
    const unanalysed = jobs.filter((j) => j.status === 'scraped' && j.has_description && !j.analysis).length;
    const busy = jobs.filter(analysing).length;
    return `<div class="scout-bar pipeline-bar"><label class="job-os-inline-select">Sort <select id="job-os-sort" aria-label="Sort jobs"><option value="newest" ${state.sortBy === 'newest' ? 'selected' : ''}>Newest</option><option value="fit" ${state.sortBy === 'fit' ? 'selected' : ''}>Best fit</option></select></label>${busy ? `<span class="job-os-chip muted analysing-chip">Analysing ${busy}…</span>` : ''}<span class="scout-bar-spacer"></span>${unanalysed ? `<button type="button" class="job-os-btn primary" data-job-os-action="analyze-new">Analyse ${unanalysed} new</button>` : ''}</div>`;
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
    const where = [...(search.locations || []), search.remote_only ? 'Remote only' : ''].filter(Boolean);
    const sites = (search.sites || []).length ? `${search.sites.length} site${search.sites.length === 1 ? '' : 's'}` : 'Default job sites';
    const schedule = state.schedule && state.schedule.enabled && search.enabled && search.next_run_at ? `Next ${until(search.next_run_at)}` : '';
    return `<article class="job-os-card scout-search${search.enabled ? '' : ' is-off'}" data-search-id="${esc(search.id)}">
      <div class="scout-search-head"><div class="scout-search-title"><h3>${esc(search.name)}</h3><p>${esc(search.keywords)}</p></div>
        <label class="job-os-toggle compact" title="${search.enabled ? 'Included in scheduled runs' : 'Paused'}"><input type="checkbox" data-job-os-action="scout-toggle" data-search-id="${esc(search.id)}" ${search.enabled ? 'checked' : ''}><span class="job-os-toggle-track" aria-hidden="true"></span><span class="sr-only">Enabled</span></label></div>
      <div class="job-os-chips">${where.map((w) => `<span class="job-os-chip">${esc(w)}</span>`).join('')}<span class="job-os-chip" title="${esc((search.sites || []).join('\n'))}">${esc(sites)}</span>${search.last_run_at ? `<span class="job-os-chip muted">Last run ${esc(when(search.last_run_at))}</span>` : ''}${schedule ? `<span class="job-os-chip muted">${esc(schedule)}</span>` : ''}</div>
      ${runPanel(run)}
      <div class="job-os-actions"><button type="button" class="job-os-btn primary" data-job-os-action="scout-run" data-search-id="${esc(search.id)}" ${active || !ready ? 'disabled' : ''} title="${ready ? '' : 'Firecrawl is not ready — see Settings'}">${active ? 'Running…' : 'Run now'}</button><button type="button" class="job-os-btn" data-job-os-action="scout-edit" data-search-id="${esc(search.id)}">Edit</button><button type="button" class="job-os-btn job-os-btn-danger" data-job-os-action="scout-delete" data-search-id="${esc(search.id)}">Delete</button></div>
    </article>`;
  }
  function searchFormCard(form, state) {
    if (!form) return '';
    const editing = !!form.id;
    return `<section class="job-os-card scout-form" id="scout-form"><div class="job-os-card-head"><h2>${editing ? 'Edit search' : 'New search'}</h2></div>
      <form id="job-os-search-form" novalidate><div class="job-os-grid">
        <label class="job-os-field"><span>Keywords <em>required</em></span><input name="keywords" required maxlength="200" placeholder="e.g. python backend engineer" value="${esc(form.keywords)}"></label>
        <label class="job-os-field"><span>Name</span><input name="name" maxlength="80" placeholder="Defaults to the keywords" value="${esc(form.name)}"></label>
        <label class="job-os-field"><span>Locations</span><input name="locations" placeholder="Comma-separated, e.g. Berlin, London" value="${esc(form.locations)}"></label>
      </div>
      <label class="job-os-field"><span>Sites</span><textarea name="sites" rows="3" placeholder="One per line. A domain (lever.co) is searched; a careers-page URL is read for its job links. Empty = Greenhouse, Lever, Ashby, Workable, SmartRecruiters.">${esc(form.sites)}</textarea></label>
      <label class="job-os-toggle"><input type="checkbox" name="remote_only" ${form.remote_only ? 'checked' : ''}><span class="job-os-toggle-track" aria-hidden="true"></span><span class="job-os-toggle-text"><strong>Remote only</strong><small>Skip postings that are not remote</small></span></label>
      <p class="job-os-error" role="alert">${esc(state.searchError || '')}</p>
      <div class="job-os-actions"><button type="submit" class="job-os-btn primary">${editing ? 'Save search' : 'Create search'}</button><button type="button" class="job-os-btn" data-job-os-action="scout-form-close">Cancel</button></div></form></section>`;
  }
  function scoutView(state) {
    const searches = state.searches || [];
    const fc = state.firecrawl || {};
    const provider = state.searchProvider === 'brave' ? 'Brave Search API' : 'Firecrawl search';
    const sched = state.schedule && state.schedule.enabled ? `Scheduled every ${state.schedule.hours}h` : 'Schedule off';
    const banner = fc.state && fc.state !== 'healthy'
      ? `<div class="scout-banner" role="status">${esc(fc.detail || 'Firecrawl is not ready.')} Scout can't run until it is. <button type="button" class="job-os-link" data-job-os-view="settings">Open Settings</button></div>` : '';
    const recent = (state.runs || []).filter((run) => run.counts && run.counts.saved && !ACTIVE_RUN.includes(run.status)).slice(0, 1)[0];
    const newIds = new Set(recent ? recent.new_job_ids : []);
    const finds = (state.jobs || []).filter((job) => newIds.has(job.id));
    return `${banner}<div class="scout-bar"><span class="job-os-chip muted">Search: ${esc(provider)}</span><button type="button" class="job-os-chip muted as-link" data-job-os-view="settings">${esc(sched)}</button><span class="scout-bar-spacer"></span><button type="button" class="job-os-btn primary" data-job-os-action="scout-new">New search</button></div>
      ${searchFormCard(state.searchForm, state)}
      ${searches.length ? `<div class="scout-searches">${searches.map((s) => searchCard(s, state)).join('')}</div>`
        : (state.searchForm ? '' : '<section class="job-os-card job-os-empty"><strong>No saved searches yet</strong><p>Create one with keywords and, optionally, locations and sites. Scout finds postings on the common job sites and reads each one for title, company, pay and the full description.</p></section>')}
      ${finds.length ? `<section class="job-os-card"><div class="job-os-card-head"><h2>Latest finds <span class="job-os-count">${finds.length}</span></h2><button type="button" class="job-os-link" data-job-os-filter="scraped">View in Pipeline</button></div><div class="job-os-list scout-finds">${finds.map(jobCard).join('')}</div></section>` : ''}`;
  }
  // ---- Job detail -------------------------------------------------------------
  function writingPanel(text) {
    return `<div class="writing-panel" role="status"><span class="writing-pen" aria-hidden="true"></span><div><strong>${esc(text)}</strong><div class="writing-lines"><i></i><i></i><i></i><i></i></div></div></div>`;
  }
  const DOC_STATUS = {pending: 'Queued', running: 'Writing', ready: 'Ready', needs_review: 'Needs review', failed: 'Failed'};
  function docStatus(status) { return `<span class="doc-status" data-status="${esc(status)}">${esc(DOC_STATUS[status] || status)}</span>`; }
  function tailoredList(state) {
    const items = state.tailored || [];
    if (!items.length) return `<section class="job-os-card"><div class="job-os-card-head"><h2>Tailored versions</h2></div><p class="job-os-card-note">Shortlist a job in Pipeline and choose <strong>Tailor resume</strong>. Each tailored resume and cover letter appears here to review, edit and export.</p></section>`;
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
  function tailoredView(state) {
    return state.studioJobId ? studioEditor(state) : tailoredList(state);
  }
  function detailActions(job) {
    const out = [];
    const a = job.analysis;
    if (!job.description) out.push('<button type="button" class="job-os-btn primary" data-job-os-action="job-details">Fetch details</button>');
    if (job.status === 'analyzed') out.push('<button type="button" class="job-os-btn primary" data-job-os-action="job-status" data-status="shortlisted">Shortlist</button>');
    if (['analyzed', 'shortlisted'].includes(job.status) && job.description) out.push(`<button type="button" class="job-os-btn${job.status === 'shortlisted' ? ' primary' : ''}" data-job-os-action="job-tailor">Tailor resume</button>`);
    if (['resume_ready', 'application_ready'].includes(job.status)) out.push(`<button type="button" class="job-os-btn primary" data-job-os-action="studio-open" data-job-id="${esc(job.id)}">Open in Resume Studio</button>`);
    if (job.status === 'resume_ready') out.push('<button type="button" class="job-os-btn" data-job-os-action="job-ready">Ready to apply</button>');
    if (['discovered', 'scraped', 'analyzed', 'shortlisted'].includes(job.status)) out.push('<button type="button" class="job-os-btn" data-job-os-action="job-status" data-status="skipped">Skip</button>');
    if (job.description && !analysing(job)) out.push(`<button type="button" class="job-os-btn" data-job-os-action="job-analyze">${a && a.status === 'done' ? 'Re-analyse' : 'Analyse'}</button>`);
    return out.join('');
  }
  function analysisPanel(job) {
    const a = job.analysis;
    if (!a) return '';
    if (analysing(job)) return '<div class="job-os-analysis is-busy"><span class="fit-ring large is-busy"><span>…</span></span><div><strong>Luna is reading this job against your resume…</strong><div class="analysis-shimmer"><i></i><i></i><i></i></div></div></div>';
    if (a.status === 'failed') return `<div class="job-os-analysis is-failed"><span class="fit-ring large is-failed"><span>!</span></span><div><strong>Analysis failed</strong><p>${esc(a.error || '')}</p></div></div>`;
    const list = (items, cls) => (items || []).length ? `<ul class="analysis-list ${cls}">${items.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>` : '';
    return `<div class="job-os-analysis">${fitRing(a, 'large')}<div class="analysis-body"><div class="analysis-head"><strong class="analysis-verdict" data-verdict="${esc(a.verdict)}">${esc((a.verdict || '').replace(/^./, (c) => c.toUpperCase()))} match</strong>${a.seniority ? `<span class="job-os-chip muted">${esc(a.seniority)}</span>` : ''}</div>
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
  function jobDetail(job) {
    if (!job) return '';
    const meta = [job.company, job.location].filter(Boolean).map(esc).join(' · ');
    return `<section class="job-os-card job-os-detail" id="job-os-detail"><div class="job-os-detail-head"><div><h2>${esc(job.title)}</h2><p>${meta}</p>${jobChips(job)}</div><div class="job-os-detail-side">${badge(job.status)}<button type="button" class="wh-insp-close job-os-detail-close" data-job-os-action="job-close" aria-label="Close details">×</button></div></div>
      <div class="job-os-actions">${detailActions(job)}<a class="job-os-btn" href="${esc(job.canonical_url)}" target="_blank" rel="noopener noreferrer">Open posting</a>${job.posted_at ? `<span class="job-os-chip muted">Posted ${esc(String(job.posted_at).slice(0, 10))}</span>` : ''}<span class="job-os-chip muted">${esc(job.source)}</span></div>
      ${job.status === 'tailoring' ? writingPanel('Luna is tailoring your resume and cover letter for this job…') : ''}
      ${analysisPanel(job)}
      ${job.description ? `<details class="job-os-desc-wrap"${job.analysis && job.analysis.status === 'done' ? '' : ' open'}><summary>Job description</summary><div class="job-os-description">${esc(job.description)}</div></details>` : '<p class="job-os-card-note">No description yet. Fetch details reads the posting page.</p>'}
      <p class="job-os-keys" aria-hidden="true"><kbd>J</kbd><kbd>K</kbd> next/previous · <kbd>S</kbd> shortlist · <kbd>X</kbd> skip · <kbd>A</kbd> analyse · <kbd>Esc</kbd> close</p></section>`;
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
        <section class="job-os-metrics" aria-label="Job dashboard">${metric('total', dashboard.total_jobs, 'Total jobs', 'data-job-os-filter=""')}${metric('active', dashboard.active_work, 'Active work', 'data-job-os-filter="tailoring"')}${metric('attention', dashboard.needs_attention, 'Needs attention', 'data-job-os-view="applications"')}${metric('applied', appliedCount(byStatus), 'Applied', 'data-job-os-view="applications"')}</section>
        ${funnelCard(dashboard.funnel)}
        <div class="job-os-columns">
          <section class="job-os-card job-os-recent"><div class="job-os-card-head"><h2>Recent jobs</h2><button type="button" class="job-os-link" data-job-os-view="pipeline">View pipeline</button></div>${jobList(jobs.slice(0, 12), 'No jobs saved yet', 'Import a role to start tracking it through your pipeline.')}</section>
          <section class="job-os-card job-os-import"><div class="job-os-card-head"><h2>Import a job</h2></div><p class="job-os-card-note">Scout finds jobs for you; save one by hand here.</p><form id="job-os-import-form"><label>Role title<input name="title" required maxlength="240" placeholder="e.g. Senior Frontend Engineer" value="${esc(draft.title)}"></label><label>Job URL<input name="canonical_url" type="url" required placeholder="https://" value="${esc(draft.canonical_url)}"></label><label>Company<input name="company" maxlength="240" placeholder="Optional" value="${esc(draft.company)}"></label><button class="job-os-btn primary" type="submit">${icon('import', 14)}Save job</button><p id="job-os-import-error" class="job-os-error" role="alert"></p></form></section>
        </div>`;
    } else if (view === 'pipeline') {
      const filter = state.statusFilter;
      body = `${header('Pipeline', filter ? `Jobs currently ${statusLabel(filter).toLowerCase()}.` : 'Every job in this profile, newest first.', state)}
        ${jobDetail(state.jobDetail)}
        ${pipelineBar(state, jobs)}
        <section class="job-os-card job-os-fill"><div class="job-os-card-head"><h2>${filter ? `<span class="job-os-filter-label">${esc(statusLabel(filter))}</span>` : 'All jobs'} <span class="job-os-count">${jobs.length}</span></h2>${filter ? '<button type="button" class="job-os-link" data-job-os-filter="">Clear filter</button>' : ''}</div>${jobList(sortJobs(jobs, state.sortBy), 'No jobs here', filter ? 'No jobs match this status right now.' : 'Run a Scout search or import a role to start your pipeline.')}</section>`;
    } else if (view === 'applications') {
      body = `${header('Applications', 'Every application from ready-to-send to offer.', state)}${boardView(state)}`;
    } else if (view === 'logistics') {
      const legend = [['strong', 'Strong fit'], ['good', 'Good fit'], ['stretch', 'Stretch'], ['poor', 'Poor fit'], ['none', 'Not scored']]
        .map(([key, text]) => `<span><i data-verdict="${key}"></i>${text}</span>`).join('');
      body = `${header('Logistics centre', 'Every job is a parcel moving through the warehouse. Click one to open it.', state)}
        <section class="logistics-wrap"><div id="job-os-logistics-slot" class="logistics-stage"></div><div class="logistics-legend" aria-label="Parcel colours">${legend}<span class="logistics-legend-hint">Scroll to zoom</span></div></section>`;
    } else if (view === 'scout') {
      body = `${header('Scout', 'Saved searches find postings on job sites and read each one.', state)}${scoutView(state)}`;
    } else if (view === 'settings') {
      body = `${header('Settings', 'Connections, AI, schedules, notifications and auto-apply for this profile.', state)}${settingsView(state)}`;
    } else {
      body = `${header('Resume Studio', 'Your master resume and the versions tailored from it.', state)}${resumeView(state)}${typeof tailoredView === 'function' ? tailoredView(state) : ''}`;
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
  window.JobOSRender = {shell, sidebar, runBody};
}());
