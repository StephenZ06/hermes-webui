(function () {
  let aborter = null;
  const root = () => document.getElementById('jobOsRoot');
  function applyRoute() {
    const match = String(window.location.hash || '').match(/^#jobs\/(dashboard|scout|pipeline|resume-studio|applications)(?:\?status=([^&]+))?$/);
    if (!match) return;
    window.JobOSState.activeView = match[1];
    window.JobOSState.statusFilter = match[2] ? decodeURIComponent(match[2]) : null;
  }
  function replaceRoute(view, status) {
    const suffix = status ? '?status=' + encodeURIComponent(status) : '';
    window.history.replaceState(window.history.state || null, '', window.location.pathname + window.location.search + '#jobs/' + view + suffix);
  }
  async function refresh() {
    const state = window.JobOSState;
    const target = root();
    if (!target) return;
    try {
      const [capability, dashboard, jobs] = await Promise.all([window.JobOSApi.capability(), window.JobOSApi.dashboard(), window.JobOSApi.jobs(state.activeView === 'pipeline' ? state.statusFilter : null)]);
      state.capability = capability;
      state.dashboard = dashboard;
      state.jobs = jobs.jobs || [];
      target.innerHTML = window.JobOSRender.shell(state);
      bind();
    } catch (error) {
      target.innerHTML = `<div class="job-os-shell"><p class="job-os-error">${String(error.message || 'Unable to load Job OS.')}</p></div>`;
    }
  }
  function bind() {
    if (aborter) aborter.abort();
    aborter = new AbortController();
    const signal = aborter.signal;
    root().querySelectorAll('[data-job-os-view]').forEach((button) => button.addEventListener('click', () => { window.JobOSState.activeView = button.dataset.jobOsView; window.JobOSState.statusFilter = null; replaceRoute(window.JobOSState.activeView); refresh(); }, {signal}));
    root().querySelectorAll('[data-job-os-filter]').forEach((button) => button.addEventListener('click', () => { window.JobOSState.activeView = 'pipeline'; window.JobOSState.statusFilter = button.dataset.jobOsFilter || null; replaceRoute('pipeline', window.JobOSState.statusFilter); refresh(); }, {signal}));
    root().querySelectorAll('[data-job-id]').forEach((button) => button.addEventListener('click', () => openJob(button.dataset.jobId), {signal}));
    const form = document.getElementById('job-os-import-form');
    if (form) form.addEventListener('submit', async (event) => { event.preventDefault(); const error = document.getElementById('job-os-import-error'); error.textContent = ''; try { await window.JobOSApi.create(Object.fromEntries(new FormData(form))); await refresh(); } catch (err) { error.textContent = err.message || 'Unable to save this job.'; } }, {signal});
  }
  function mount() { applyRoute(); refresh(); }
  function unmount() { if (aborter) aborter.abort(); aborter = null; }
  function openJob(jobId) { window.JobOSState.selectedJobId = jobId; window.JobOSState.activeView = 'pipeline'; window.JobOSState.statusFilter = null; replaceRoute('pipeline'); refresh(); }
  window.JobOS = {mount, refresh, unmount, openJob};
}());
