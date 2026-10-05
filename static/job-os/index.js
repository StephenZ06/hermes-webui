(function () {
  let aborter = null;
  // Each refresh takes a number; only the newest may render, so a slow
  // earlier response (e.g. a filtered list) cannot land on a newer view.
  let refreshSeq = 0;
  const emptyDraft = () => ({title: '', canonical_url: '', company: ''});
  const root = () => document.getElementById('jobOsRoot');
  const sidebarRoot = () => document.getElementById('jobOsSidebar');
  function applyRoute() {
    const match = String(window.location.hash || '').match(/^#jobs\/(dashboard|scout|pipeline|resume-studio|applications|settings)(?:\?status=([^&]+))?$/);
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
    const seq = ++refreshSeq;
    renderSidebar();
    try {
      const wantSettings = state.activeView === 'settings';
      const [capability, dashboard, jobs, health, settings] = await Promise.all([
        window.JobOSApi.capability(), window.JobOSApi.dashboard(),
        window.JobOSApi.jobs(state.activeView === 'pipeline' ? state.statusFilter : null),
        // Header status only: a Firecrawl outage must not take the page down.
        window.JobOSApi.firecrawlHealth().catch(() => null),
        wantSettings ? window.JobOSApi.settings() : Promise.resolve(null),
      ]);
      if (seq !== refreshSeq) return;
      state.capability = capability;
      state.dashboard = dashboard;
      state.jobs = jobs.jobs || [];
      state.firecrawl = health && health.firecrawl;
      if (settings) {
        state.settings = settings.settings;
        state.settingsStatus = settings.status;
        if (settings.status && settings.status.firecrawl) state.firecrawl = settings.status.firecrawl;
        if (!state.settingsDirty) state.settingsDraft = null;
      }
      target.innerHTML = window.JobOSRender.shell(state);
      if (typeof window.animateCounts === 'function') window.animateCounts(target);
      renderSidebar();
      bind();
    } catch (error) {
      if (seq !== refreshSeq) return;
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
    const action = event.target.closest('[data-job-os-action]');
    if (action) { runAction(action.dataset.jobOsAction, action); return; }
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
    const settingsForm = document.getElementById('job-os-settings-form');
    if (settingsForm) {
      settingsForm.addEventListener('input', onSettingsEdit, {signal});
      settingsForm.addEventListener('change', onSettingsEdit, {signal});
      settingsForm.addEventListener('submit', (event) => { event.preventDefault(); runAction('save-settings'); }, {signal});
    }
    const form = document.getElementById('job-os-import-form');
    if (!form) return;
    form.addEventListener('input', (event) => {
      const name = event.target && event.target.name;
      if (name && Object.prototype.hasOwnProperty.call(window.JobOSState.importDraft, name)) window.JobOSState.importDraft[name] = event.target.value;
    }, {signal});
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const error = document.getElementById('job-os-import-error');
      const submit = form.querySelector('button[type="submit"]');
      error.textContent = '';
      if (submit) submit.disabled = true;
      try {
        await window.JobOSApi.create(Object.fromEntries(new FormData(form)));
        window.JobOSState.importDraft = emptyDraft();
        await refresh();
      } catch (err) {
        error.textContent = err.message || 'Unable to save this job.';
        if (submit) submit.disabled = false;
      }
    }, {signal});
  }
  // ---- Settings editing ----------------------------------------------------
  const clone = (value) => JSON.parse(JSON.stringify(value));
  function setPath(obj, path, value) {
    const keys = path.split('.');
    const last = keys.pop();
    keys.reduce((acc, key) => acc[key], obj)[last] = value;
  }
  function readControl(form, control) {
    const path = control.dataset.setting;
    if (path === 'auto_apply.allowed_ats') {
      return [...form.querySelectorAll('[data-setting="auto_apply.allowed_ats"]')].filter((box) => box.checked).map((box) => box.value);
    }
    if (control.type === 'checkbox') return control.checked;
    if (control.type === 'number') return control.value === '' ? control.value : Number(control.value);
    return control.value;
  }
  // Edits update the draft in place and only repaint the save bar, so typing
  // never loses focus to a full re-render.
  function onSettingsEdit(event) {
    const control = event.target.closest('[data-setting]');
    if (!control) return;
    const state = window.JobOSState;
    if (!state.settingsDraft) state.settingsDraft = clone(state.settings);
    setPath(state.settingsDraft, control.dataset.setting, readControl(event.currentTarget, control));
    state.settingsDirty = JSON.stringify(state.settingsDraft) !== JSON.stringify(state.settings);
    state.settingsError = '';
    syncSaveBar();
  }
  function syncSaveBar() {
    const state = window.JobOSState;
    const bar = document.querySelector('.job-os-savebar');
    if (!bar) return;
    bar.dataset.dirty = state.settingsDirty ? 'true' : 'false';
    bar.querySelector('.job-os-savebar-note').textContent = state.settingsDirty ? 'Unsaved changes' : (state.settingsSavedAt ? 'Saved' : '');
    bar.querySelectorAll('[data-job-os-action]').forEach((button) => { button.disabled = !state.settingsDirty; });
    const error = document.getElementById('job-os-settings-error');
    if (error) error.textContent = state.settingsError || '';
  }
  async function runAction(name, button) {
    const state = window.JobOSState;
    if (name === 'discard-settings') {
      state.settingsDraft = null; state.settingsDirty = false; state.settingsError = '';
      refresh();
    } else if (name === 'save-settings') {
      if (!state.settingsDirty || !state.settingsDraft) return;
      const patch = clone(state.settingsDraft);
      delete patch.revision;
      const saveButton = document.querySelector('[data-job-os-action="save-settings"]');
      if (saveButton) saveButton.disabled = true;
      try {
        const saved = await window.JobOSApi.saveSettings(patch, state.settings.revision);
        state.settings = saved.settings; state.settingsStatus = saved.status;
        state.settingsDraft = null; state.settingsDirty = false; state.settingsError = '';
        state.settingsSavedAt = Date.now();
        if (typeof window.showToast === 'function') window.showToast('Jobs settings saved');
        refresh();
      } catch (error) {
        state.settingsError = error.message || 'Unable to save settings.';
        syncSaveBar();
      }
    } else if (name === 'test-firecrawl') {
      if (button) { button.disabled = true; button.classList.add('is-busy'); button.textContent = 'Testing…'; }
      try {
        const result = await window.JobOSApi.settings();
        state.settingsStatus = result.status;
        state.firecrawl = result.status && result.status.firecrawl;
      } catch (_error) { /* the status pill keeps its last value */ }
      refresh();
    }
  }
  function mount() { applyRoute(); refresh(); }
  function unmount() { if (aborter) aborter.abort(); aborter = null; }
  function openJob(jobId) { window.JobOSState.selectedJobId = jobId; window.JobOSState.activeView = 'pipeline'; window.JobOSState.statusFilter = null; replaceRoute('pipeline'); refresh(); }
  function resetDraft() { window.JobOSState.importDraft = emptyDraft(); }
  window.JobOS = {mount, refresh, unmount, openJob, resetDraft};
}());
