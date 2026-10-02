(function () {
  const esc = (value) => String(value == null ? '' : value).replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const labels = {dashboard: 'Dashboard', scout: 'Scout', pipeline: 'Pipeline', 'resume-studio': 'Resume Studio', applications: 'Applications'};
  function jobCard(job) {
    return `<button class="job-os-job-card" type="button" data-job-id="${esc(job.id)}"><strong>${esc(job.title)}</strong><span>${esc(job.company || 'Company to review')}</span><small>${esc(job.status.replace(/_/g, ' '))}</small></button>`;
  }
  function shell(state) {
    const view = state.activeView;
    const dashboard = state.dashboard || {total_jobs: 0, active_work: 0, needs_attention: 0, by_status: {}};
    const content = view === 'dashboard'
      ? `<section class="job-os-metrics" aria-label="Job dashboard"><button type="button" data-job-os-filter="">${dashboard.total_jobs}<span>Total jobs</span></button><button type="button" data-job-os-filter="tailoring">${dashboard.active_work}<span>Active work</span></button><button type="button" data-job-os-filter="awaiting_approval">${dashboard.needs_attention}<span>Needs attention</span></button></section><section class="job-os-import"><h2>Import a job</h2><p>Save a role manually now; Firecrawl discovery arrives in the next release.</p><form id="job-os-import-form"><label>Role title<input name="title" required maxlength="240"></label><label>Job URL<input name="canonical_url" type="url" required placeholder="https://"></label><label>Company<input name="company" maxlength="240"></label><button class="btn primary" type="submit">Save job</button><p id="job-os-import-error" class="job-os-error" role="alert"></p></form></section><section class="job-os-list"><h2>Recent jobs</h2>${state.jobs.length ? state.jobs.map(jobCard).join('') : '<p class="job-os-empty">No jobs saved in this profile yet.</p>'}</section>`
      : view === 'pipeline'
        ? `<section class="job-os-page"><h2>Pipeline${state.statusFilter ? ` <span class="job-os-filter-label">${esc(state.statusFilter.replace(/_/g, ' '))}</span>` : ''}</h2><p>Canonical lifecycle records for this profile${state.statusFilter ? ' matching this status.' : '.'}</p>${state.jobs.length ? `<div class="job-os-list">${state.jobs.map(jobCard).join('')}</div>` : '<p class="job-os-empty">No jobs match this pipeline filter.</p>'}<button class="btn secondary" type="button" data-job-os-view="dashboard">Back to dashboard</button></section>`
        : `<section class="job-os-page"><h2>${labels[view]}</h2><p>${view === 'scout' ? 'Saved searches and Firecrawl discovery will appear here.' : view === 'resume-studio' ? 'Your master CV and tailored versions will appear here.' : 'Prepared applications, approvals, and outcomes will appear here.'}</p><button class="btn secondary" type="button" data-job-os-view="dashboard">Back to dashboard</button></section>`;
    return `<div class="job-os-shell"><header class="job-os-header"><div><p class="job-os-kicker">JOB OS</p><h1>Career workspace</h1></div><span class="job-os-status">${state.capability && state.capability.available ? 'Ready' : 'Storage unavailable'}</span></header><nav class="job-os-tabs" aria-label="Job OS sections">${Object.keys(labels).map((key) => `<button type="button" class="${view === key ? 'active' : ''}" data-job-os-view="${key}">${labels[key]}</button>`).join('')}</nav><main class="job-os-content">${content}</main></div>`;
  }
  window.JobOSRender = {shell};
}());
