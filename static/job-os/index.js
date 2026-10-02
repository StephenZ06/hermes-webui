(function () {
  let aborter = null;
  const root = () => document.getElementById('jobOsRoot');
  async function refresh() {
    const state = window.JobOSState;
    const target = root();
    if (!target) return;
    try {
      const [capability, dashboard, jobs] = await Promise.all([window.JobOSApi.capability(), window.JobOSApi.dashboard(), window.JobOSApi.jobs()]);
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
    root().querySelectorAll('[data-job-os-view]').forEach((button) => button.addEventListener('click', () => { window.JobOSState.activeView = button.dataset.jobOsView; refresh(); }, {signal}));
    root().querySelectorAll('[data-job-os-filter]').forEach((button) => button.addEventListener('click', async () => { window.JobOSState.activeView = 'dashboard'; window.JobOSState.jobs = (await window.JobOSApi.jobs(button.dataset.jobOsFilter)).jobs || []; root().innerHTML = window.JobOSRender.shell(window.JobOSState); bind(); }, {signal}));
    const form = document.getElementById('job-os-import-form');
    if (form) form.addEventListener('submit', async (event) => { event.preventDefault(); const error = document.getElementById('job-os-import-error'); error.textContent = ''; try { await window.JobOSApi.create(Object.fromEntries(new FormData(form))); await refresh(); } catch (err) { error.textContent = err.message || 'Unable to save this job.'; } }, {signal});
  }
  function mount() { refresh(); }
  function unmount() { if (aborter) aborter.abort(); aborter = null; }
  function openJob(jobId) { window.JobOSState.selectedJobId = jobId; window.JobOSState.activeView = 'pipeline'; refresh(); }
  window.JobOS = {mount, refresh, unmount, openJob};
}());
