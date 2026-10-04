(function () {
  let aborter = null;
  const root = () => document.getElementById('jobOsRoot');
  const sidebarRoot = () => document.getElementById('jobOsSidebar');
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
  function renderSidebar() {
    const side = sidebarRoot();
    if (side) side.innerHTML = window.JobOSRender.sidebar(window.JobOSState);
  }
  async function refresh() {
    const state = window.JobOSState;
    const target = root();
    if (!target) return;
    renderSidebar();
    try {
      const [capability, dashboard, jobs] = await Promise.all([window.JobOSApi.capability(), window.JobOSApi.dashboard(), window.JobOSApi.jobs(state.activeView === 'pipeline' ? state.statusFilter : null)]);
      state.capability = capability;
      state.dashboard = dashboard;
      state.jobs = jobs.jobs || [];
      target.innerHTML = window.JobOSRender.shell(state);
      renderSidebar();
      bind();
    } catch (error) {
      const message = document.createElement('p');
      message.className = 'job-os-error';
      message.textContent = String(error.message || 'Unable to load Job OS.');
      target.innerHTML = '<div class="job-os-shell"></div>';
      target.firstChild.appendChild(message);
    }
  }
  function showView(view) { window.JobOSState.activeView = view; window.JobOSState.statusFilter = null; replaceRoute(view); refresh(); }
  function showStatus(status) { window.JobOSState.activeView = 'pipeline'; window.JobOSState.statusFilter = status || null; replaceRoute('pipeline', window.JobOSState.statusFilter); refresh(); }
  // One delegated listener per container: the page and the side-panel nav
  // re-render on every refresh, so per-button listeners would be rebuilt anyway.
  function onClick(event) {
    const view = event.target.closest('[data-job-os-view]');
    if (view) { showView(view.dataset.jobOsView); return; }
    const filter = event.target.closest('[data-job-os-filter]');
    if (filter) { showStatus(filter.dataset.jobOsFilter); return; }
    const job = event.target.closest('[data-job-id]');
    if (job) openJob(job.dataset.jobId);
  }
  function bind() {
    if (aborter) aborter.abort();
    aborter = new AbortController();
    const signal = aborter.signal;
    root().addEventListener('click', onClick, {signal});
    const side = sidebarRoot();
    if (side) side.addEventListener('click', onClick, {signal});
    const form = document.getElementById('job-os-import-form');
    if (form) form.addEventListener('submit', async (event) => { event.preventDefault(); const error = document.getElementById('job-os-import-error'); error.textContent = ''; try { await window.JobOSApi.create(Object.fromEntries(new FormData(form))); await refresh(); } catch (err) { error.textContent = err.message || 'Unable to save this job.'; } }, {signal});
  }
  function mount() { applyRoute(); refresh(); }
  function unmount() { if (aborter) aborter.abort(); aborter = null; }
  function openJob(jobId) { window.JobOSState.selectedJobId = jobId; window.JobOSState.activeView = 'pipeline'; window.JobOSState.statusFilter = null; replaceRoute('pipeline'); refresh(); }
  window.JobOS = {mount, refresh, unmount, openJob};
}());
