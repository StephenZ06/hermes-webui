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
      const wantScout = state.activeView === 'scout';
      const wantDetail = state.activeView === 'pipeline' && state.selectedJobId;
      const wantResume = state.activeView === 'resume-studio';
      const [capability, dashboard, jobs, health, settings, searches, runs, detail, resume] = await Promise.all([
        window.JobOSApi.capability(), window.JobOSApi.dashboard(),
        window.JobOSApi.jobs(state.activeView === 'pipeline' ? state.statusFilter : null),
        // Header status only: a Firecrawl outage must not take the page down.
        window.JobOSApi.firecrawlHealth().catch(() => null),
        wantSettings ? window.JobOSApi.settings() : Promise.resolve(null),
        wantScout ? window.JobOSApi.searches() : Promise.resolve(null),
        wantScout ? window.JobOSApi.runs(20) : Promise.resolve(null),
        wantDetail ? window.JobOSApi.job(state.selectedJobId).catch(() => null) : Promise.resolve(null),
        wantResume ? window.JobOSApi.resume().catch(() => null) : Promise.resolve(null),
      ]);
      if (seq !== refreshSeq) return;
      state.capability = capability;
      state.dashboard = dashboard;
      state.jobs = jobs.jobs || [];
      state.firecrawl = health && health.firecrawl;
      if (searches) { state.searches = searches.searches || []; state.searchProvider = searches.search_provider; state.schedule = searches.schedule; }
      if (runs) state.runs = runs.runs || [];
      state.jobDetail = wantDetail ? (detail && detail.job) || null : null;
      if (resume) state.resume = resume.resume;
      if (settings) {
        state.settings = settings.settings;
        state.settingsStatus = settings.status;
        if (settings.status && settings.status.firecrawl) state.firecrawl = settings.status.firecrawl;
        if (!state.settingsDirty) state.settingsDraft = null;
      }
      target.innerHTML = window.JobOSRender.shell(state);
      if (typeof window.animateCounts === 'function') window.animateCounts(target);
      if (wantScout) afterScoutRender(target);
      else stopScoutPolling();
      afterPipelineRender(target);
      if (wantResume) bindResumeUpload();
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
      // Enter in the Gmail fields connects Gmail rather than saving settings.
      settingsForm.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && event.target.closest('#job-os-gmail')) { event.preventDefault(); runAction('gmail-connect'); }
      }, {signal});
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
    if (name.startsWith('scout-') || name === 'job-close') return scoutAction(name, button);
    if (['job-status', 'job-analyze', 'analyze-new', 'job-details'].includes(name) || name.startsWith('resume-')) return pipelineAction(name, button);
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
    } else if (name === 'gmail-connect') {
      const addressEl = document.getElementById('job-os-gmail-address');
      const passwordEl = document.getElementById('job-os-gmail-password');
      if (!addressEl || !passwordEl) return;
      const address = addressEl.value;
      const password = passwordEl.value;
      passwordEl.value = '';
      if (button) { button.disabled = true; button.classList.add('is-busy'); button.textContent = 'Checking with Gmail…'; }
      try {
        const result = await window.JobOSApi.connectGmail(address, password);
        state.settingsStatus = Object.assign({}, state.settingsStatus, {gmail: result.gmail});
        state.gmailEditing = false;
        state.gmailMessage = {tone: 'ok', text: 'Gmail connected. It now works for every profile.'};
        if (typeof window.showToast === 'function') window.showToast('Gmail connected');
        refresh();
      } catch (error) {
        state.gmailMessage = {tone: 'error', text: error.message || 'Unable to connect Gmail.'};
        if (button) { button.disabled = false; button.classList.remove('is-busy'); button.textContent = 'Connect Gmail'; }
        const msg = document.querySelector('#job-os-gmail .job-os-gmail-msg');
        if (msg) { msg.dataset.tone = 'error'; msg.textContent = state.gmailMessage.text; }
      }
    } else if (name === 'gmail-edit' || name === 'gmail-cancel') {
      state.gmailEditing = name === 'gmail-edit';
      state.gmailMessage = null;
      refresh();
    } else if (name === 'gmail-disconnect') {
      const ok = typeof window.showConfirmDialog === 'function'
        ? await window.showConfirmDialog({message: 'Disconnect Gmail? Job notifications and email replies stop for every profile.', confirmLabel: 'Disconnect', danger: true})
        : window.confirm('Disconnect Gmail?');
      if (!ok) return;
      try {
        const result = await window.JobOSApi.disconnectGmail();
        state.settingsStatus = Object.assign({}, state.settingsStatus, {gmail: result.gmail});
        state.gmailMessage = {tone: 'ok', text: 'Gmail disconnected.'};
        refresh();
      } catch (error) {
        state.gmailMessage = {tone: 'error', text: error.message || 'Unable to disconnect Gmail.'};
        refresh();
      }
    } else if (name === 'gmail-test') {
      if (button) { button.disabled = true; button.classList.add('is-busy'); button.textContent = 'Sending…'; }
      try {
        const contextEl = document.getElementById('job-os-gmail-test-context');
        const result = await window.JobOSApi.testGmail('', contextEl ? contextEl.value : 'jobs');
        state.gmailMessage = {tone: 'ok', text: `Test email from ${result.sender_name} sent to ${result.sent_to}.`};
      } catch (error) {
        state.gmailMessage = {tone: 'error', text: error.message || 'Unable to send the test email.'};
      }
      refresh();
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
  // ---- Pipeline: analysis polling, triage, resume ---------------------------
  let analysisTimer = null;
  const busy = (job) => !!(job && job.analysis && ['pending', 'running'].includes(job.analysis.status));
  function afterPipelineRender(target) {
    const state = window.JobOSState;
    const sort = document.getElementById('job-os-sort');
    if (sort) sort.addEventListener('change', () => { state.sortBy = sort.value; refresh(); });
    const watching = ['pipeline', 'dashboard'].includes(state.activeView)
      && ((state.jobs || []).some(busy) || busy(state.jobDetail));
    if (watching && !analysisTimer) analysisTimer = setInterval(() => { if (!document.hidden) refresh(); }, 2500);
    if (!watching && analysisTimer) { clearInterval(analysisTimer); analysisTimer = null; }
    const card = state.jobDetail && target.querySelector(`.job-os-job-card[data-job-id="${CSS.escape(state.jobDetail.id)}"]`);
    if (card) card.classList.add('is-selected');
  }
  function orderedJobIds() {
    return [...document.querySelectorAll('#jobOsRoot .job-os-fill .job-os-job-card[data-job-id]')].map((el) => el.dataset.jobId);
  }
  async function setJobStatus(status) {
    const state = window.JobOSState;
    const job = state.jobDetail;
    if (!job) return;
    try {
      await window.JobOSApi.setStatus(job.id, status, job.revision);
      if (typeof window.showToast === 'function') window.showToast(status === 'shortlisted' ? 'Shortlisted' : status === 'skipped' ? 'Skipped' : 'Updated');
      const ids = orderedJobIds();
      const next = ids[ids.indexOf(job.id) + 1];
      if (status === 'skipped' && next) state.selectedJobId = next;
    } catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not update the job'); }
    refresh();
  }
  function onTriageKey(event) {
    const state = window.JobOSState;
    if (state.activeView !== 'pipeline' || !state.jobDetail || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.target.closest('input,textarea,select,[contenteditable="true"]')) return;
    const key = event.key.toLowerCase();
    const ids = orderedJobIds();
    const i = ids.indexOf(state.jobDetail.id);
    if (key === 'j' || key === 'k') {
      const next = ids[i + (key === 'j' ? 1 : -1)];
      if (next) { event.preventDefault(); openJob(next); }
    } else if (key === 's' && state.jobDetail.status === 'analyzed') { event.preventDefault(); setJobStatus('shortlisted'); }
    else if (key === 'x' && ['discovered', 'scraped', 'analyzed', 'shortlisted'].includes(state.jobDetail.status)) { event.preventDefault(); setJobStatus('skipped'); }
    else if (key === 'a' && state.jobDetail.description) { event.preventDefault(); runAction('job-analyze'); }
    else if (key === 'escape') { event.preventDefault(); runAction('job-close'); }
  }
  document.addEventListener('keydown', onTriageKey);
  function readAsBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || '').split(',')[1] || '');
      reader.onerror = () => reject(new Error('That file could not be read.'));
      reader.readAsDataURL(file);
    });
  }
  async function uploadResumeFile(file) {
    const state = window.JobOSState;
    const drop = document.getElementById('resume-drop');
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { state.resumeError = 'That file is larger than 5 MB.'; refresh(); return; }
    if (drop) { drop.classList.add('is-busy'); drop.querySelector('strong').textContent = `Reading ${file.name}…`; }
    try {
      const result = await window.JobOSApi.uploadResume(file.name, await readAsBase64(file));
      state.resume = result.resume; state.resumeError = ''; state.resumeReplacing = false;
      if (typeof window.showToast === 'function') window.showToast('Resume saved');
    } catch (error) { state.resumeError = error.message || 'Could not read that resume.'; }
    refresh();
  }
  function bindResumeUpload() {
    const drop = document.getElementById('resume-drop');
    const input = document.getElementById('resume-file');
    if (!drop || !input) return;
    drop.addEventListener('click', () => input.click());
    drop.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
    input.addEventListener('change', () => uploadResumeFile(input.files && input.files[0]));
    ['dragenter', 'dragover'].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add('is-over'); }));
    ['dragleave', 'drop'].forEach((t) => drop.addEventListener(t, () => drop.classList.remove('is-over')));
    drop.addEventListener('drop', (e) => { e.preventDefault(); uploadResumeFile(e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]); });
  }
  async function pipelineAction(name, el) {
    const state = window.JobOSState;
    const job = state.jobDetail;
    if (name === 'job-status') return setJobStatus(el.dataset.status);
    if (name === 'job-analyze' && job) {
      try { await window.JobOSApi.analyzeJob(job.id, !!(job.analysis && job.analysis.status === 'done')); }
      catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not analyse this job'); }
      return refresh();
    }
    if (name === 'analyze-new') {
      if (el) { el.disabled = true; el.textContent = 'Queuing…'; }
      try { const r = await window.JobOSApi.analyzeNew(); if (typeof window.showToast === 'function') window.showToast(`Luna is analysing ${r.queued} job${r.queued === 1 ? '' : 's'}`); }
      catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not start analysis'); }
      return refresh();
    }
    if (name === 'job-details' && job) {
      if (el) { el.disabled = true; el.textContent = 'Reading posting…'; }
      try { await window.JobOSApi.fetchDetails(job.id); }
      catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not read that posting'); }
      return refresh();
    }
    if (name === 'resume-replace') { state.resumeReplacing = true; state.resumeError = ''; return refresh(); }
    if (name === 'resume-cancel') { state.resumeReplacing = false; state.resumeError = ''; return refresh(); }
    if (name === 'resume-paste') {
      const text = (document.getElementById('resume-text') || {}).value || '';
      try { const r = await window.JobOSApi.pasteResume(text); state.resume = r.resume; state.resumeError = ''; state.resumeReplacing = false; }
      catch (error) { state.resumeError = error.message || 'Could not save that text.'; }
      return refresh();
    }
    return undefined;
  }
  // ---- Scout -----------------------------------------------------------------
  const ACTIVE = ['queued', 'searching', 'scraping'];
  let pollTimer = null;
  const seenFinds = new Set();
  function stopScoutPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }
  function afterScoutRender(target) {
    // New finds glow in once; the radar keeps running while any run is active.
    target.querySelectorAll('.scout-finds [data-job-id]').forEach((card) => {
      if (!seenFinds.has(card.dataset.jobId)) { seenFinds.add(card.dataset.jobId); if (typeof window.markArrival === 'function') window.markArrival(card); }
    });
    const form = document.getElementById('job-os-search-form');
    if (form) {
      form.addEventListener('submit', (event) => { event.preventDefault(); saveSearchForm(form); });
      const first = form.querySelector('input[name="keywords"]');
      if (first && !first.value) first.focus();
    }
    const anyActive = (window.JobOSState.runs || []).some((run) => ACTIVE.includes(run.status));
    if (anyActive && !pollTimer) pollTimer = setInterval(pollRuns, 1200);
    if (!anyActive) stopScoutPolling();
  }
  async function pollRuns() {
    const state = window.JobOSState;
    if (state.activeView !== 'scout') { stopScoutPolling(); return; }
    let data;
    try { data = await window.JobOSApi.runs(20); } catch (_) { return; }
    const before = new Map((state.runs || []).map((run) => [run.id, run]));
    state.runs = data.runs || [];
    let needsFullRender = false;
    state.runs.forEach((run) => {
      const old = before.get(run.id);
      const panel = document.querySelector(`[data-run-panel="${CSS.escape(run.id)}"]`);
      if (!old || !panel || ACTIVE.includes(old.status) !== ACTIVE.includes(run.status)) { if (old && ACTIVE.includes(old.status)) needsFullRender = true; return; }
      if (old.revision !== run.revision) {
        const body = panel.querySelector('.scout-run-body');
        if (body) body.innerHTML = window.JobOSRender.runBody(run);
        if (typeof window.animateCounts === 'function') window.animateCounts(panel);
      }
    });
    if (needsFullRender || !state.runs.some((run) => ACTIVE.includes(run.status))) { stopScoutPolling(); refresh(); }
  }
  function formFromSearch(search) {
    return search ? {id: search.id, revision: search.revision, name: search.name, keywords: search.keywords,
      locations: (search.locations || []).join(', '), sites: (search.sites || []).join('\n'), remote_only: search.remote_only}
      : {name: '', keywords: '', locations: '', sites: '', remote_only: false};
  }
  async function saveSearchForm(form) {
    const state = window.JobOSState;
    const data = new FormData(form);
    const payload = {name: data.get('name') || '', keywords: data.get('keywords') || '', locations: data.get('locations') || '',
      sites: data.get('sites') || '', remote_only: data.get('remote_only') === 'on'};
    const submit = form.querySelector('button[type="submit"]');
    if (submit) submit.disabled = true;
    try {
      if (state.searchForm && state.searchForm.id) await window.JobOSApi.updateSearch(state.searchForm.id, payload, state.searchForm.revision);
      else await window.JobOSApi.createSearch(payload);
      state.searchForm = null; state.searchError = '';
      refresh();
    } catch (error) {
      state.searchError = error.message || 'Unable to save this search.';
      state.searchForm = Object.assign({}, state.searchForm, payload);
      const err = form.querySelector('.job-os-error');
      if (err) err.textContent = state.searchError;
      if (submit) submit.disabled = false;
    }
  }
  async function scoutAction(name, el) {
    const state = window.JobOSState;
    const searchId = el && el.dataset.searchId;
    const search = (state.searches || []).find((s) => s.id === searchId);
    if (name === 'scout-new') { state.searchForm = formFromSearch(null); state.searchError = ''; refresh(); }
    else if (name === 'scout-edit') { state.searchForm = formFromSearch(search); state.searchError = ''; refresh(); }
    else if (name === 'scout-form-close') { state.searchForm = null; state.searchError = ''; refresh(); }
    else if (name === 'scout-run') {
      el.disabled = true; el.textContent = 'Starting…';
      try { await window.JobOSApi.runSearch(searchId, `${searchId}:${Date.now()}`); }
      catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not start Scout'); }
      refresh();
    } else if (name === 'scout-cancel') {
      el.disabled = true; el.textContent = 'Cancelling…';
      try { await window.JobOSApi.cancelRun(el.dataset.runId); } catch (_) { /* the next poll shows the real state */ }
    } else if (name === 'scout-delete') {
      const ok = typeof window.showConfirmDialog === 'function'
        ? await window.showConfirmDialog({title: 'Delete search', message: `Delete "${search ? search.name : 'this search'}"? Jobs it already found stay in your Pipeline.`, confirmLabel: 'Delete', danger: true})
        : window.confirm('Delete this search?');
      if (!ok) return;
      const card = document.querySelector(`.scout-search[data-search-id="${CSS.escape(searchId)}"]`);
      try {
        await window.JobOSApi.deleteSearch(searchId);
        if (typeof window.animateRemoval === 'function') await window.animateRemoval(card);
      } catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not delete the search'); }
      refresh();
    } else if (name === 'scout-toggle') {
      if (!search) return;
      try { await window.JobOSApi.updateSearch(searchId, {enabled: el.checked}, search.revision); }
      catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not update the search'); }
      refresh();
    } else if (name === 'job-close') { state.selectedJobId = null; state.jobDetail = null; refresh(); }
  }
  function mount() { applyRoute(); refresh(); }
  function unmount() { if (aborter) aborter.abort(); aborter = null; stopScoutPolling(); if (analysisTimer) { clearInterval(analysisTimer); analysisTimer = null; } }
  function openJob(jobId) {
    const state = window.JobOSState;
    // Stay in the current Pipeline filter when opening jobs from it (and with J/K).
    if (state.activeView !== 'pipeline') state.statusFilter = null;
    state.selectedJobId = jobId; state.activeView = 'pipeline';
    replaceRoute('pipeline', state.statusFilter); refresh();
    requestAnimationFrame(() => { const d = document.getElementById('job-os-detail'); if (d && d.scrollIntoView) d.scrollIntoView({block: 'nearest', behavior: 'smooth'}); });
  }
  function resetDraft() { window.JobOSState.importDraft = emptyDraft(); }
  window.JobOS = {mount, refresh, unmount, openJob, resetDraft};
}());
