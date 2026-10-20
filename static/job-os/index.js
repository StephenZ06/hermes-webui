(function () {
  let aborter = null;
  // Each refresh takes a number; only the newest may render, so a slow
  // earlier response (e.g. a filtered list) cannot land on a newer view.
  let refreshSeq = 0;
  let lastView = null;
  const emptyDraft = () => ({title: '', canonical_url: '', company: ''});
  const root = () => document.getElementById('jobOsRoot');
  const sidebarRoot = () => document.getElementById('jobOsSidebar');
  function applyRoute() {
    const match = String(window.location.hash || '').match(/^#jobs\/(dashboard|scout|pipeline|resume-studio|applications|logistics|settings)(?:\?status=([^&]+))?$/);
    if (!match) return;
    // The Applications board became the Pipeline board, and the Logistics
    // centre was removed (its progress shows on the Pipeline): old links land there.
    window.JobOSState.activeView = ['applications', 'logistics'].includes(match[1]) ? 'pipeline' : match[1];
    window.JobOSState.statusFilter = match[2] ? decodeURIComponent(match[2]) : null;
  }
  function replaceRoute(view, status) {
    const suffix = status ? '?status=' + encodeURIComponent(status) : '';
    window.history.replaceState(window.history.state || null, '', window.location.pathname + window.location.search + '#jobs/' + view + suffix);
    try { sessionStorage.setItem('hermes-webui-panel-route', '#jobs/' + view + suffix); } catch (_) {}
  }
  // Each container keeps the HTML it last drew: polling that changes nothing
  // leaves the DOM alone. A change is patched into the page node by node
  // (morph), so what stayed the same keeps its focus, scroll, listeners and
  // running animations, and entry animations never play twice. A new view
  // (replace) is drawn from scratch.
  function paint(el, html, replace) {
    if (!el || el._jobOsHtml === html) return false;
    if (replace || !el.firstChild) el.innerHTML = html;
    else {
      const next = document.createElement('template');
      next.innerHTML = html;
      morphChildren(el, next.content);
    }
    el._jobOsHtml = html;
    return true;
  }
  // Classes the page adds at run time (entry, selection, drag, drawn previews):
  // a patch keeps them where the new HTML doesn't say otherwise.
  const RUNTIME_CLASSES = ['is-entering', 'dragging', 'drop-target', 'can-drop', 'is-dragging',
    'is-focus', 'is-leaving', 'is-paging', 'is-sent', 'is-over', 'is-closing', 'item-arrive', 'card-landed', 'is-scrolling', 'is-panning',
    'is-focused', 'mi-tabs', 'mi-tabs-ready', 'mi-shake', 'mi-busy', 'mi-done'];
  // Nodes micro.js adds or holds (the tab pill, a button showing "Saved"): a patch leaves them be.
  const kept = (node) => node.nodeType === 1 && node.hasAttribute('data-mi-keep');
  const keyOf = (node) => (node.nodeType === 1 ? node.getAttribute('data-key') || node.id || null : null);
  function morphChildren(from, to) {
    const old = [...from.childNodes];
    const keyed = new Map();
    old.forEach((node) => { const k = keyOf(node); if (k) keyed.set(k, node); });
    const used = new Set();
    let cursor = 0;
    let ref = from.firstChild;
    [...to.childNodes].forEach((node) => {
      const k = keyOf(node);
      let match = null;
      if (k) {
        const candidate = keyed.get(k);
        if (candidate && !used.has(candidate) && candidate.nodeName === node.nodeName) match = candidate;
      } else {
        while (cursor < old.length) {
          const candidate = old[cursor++];
          if (!used.has(candidate) && !keyOf(candidate) && !kept(candidate) && candidate.nodeName === node.nodeName) { match = candidate; break; }
        }
      }
      if (match) {
        used.add(match);
        morphNode(match, node);
        if (match === ref) ref = ref.nextSibling;
        else from.insertBefore(match, ref);
      } else from.insertBefore(node, ref);
    });
    old.forEach((node) => { if (!used.has(node) && !kept(node) && node.parentNode === from) from.removeChild(node); });
  }
  function morphNode(from, to) {
    if (from.nodeType !== 1) { if (from.nodeValue !== to.nodeValue) from.nodeValue = to.nodeValue; return; }
    // data-keep: the page draws inside this node itself (PDF pages, the 3D scene).
    if (from.hasAttribute('data-keep') && from.getAttribute('data-keep') === to.getAttribute('data-keep')) return;
    if (from.hasAttribute('data-mi-hold')) return;
    const runtime = RUNTIME_CLASSES.filter((c) => from.classList.contains(c));
    // A <details> stays open or shut the way you left it.
    // While its tooltip shows, an element's title is parked in data-mi-title (micro.js).
    const parked = from.hasAttribute('data-mi-title');
    const own = (name) => (name === 'open' && from.nodeName === 'DETAILS') || (parked && (name === 'data-mi-title' || name === 'aria-describedby'));
    [...from.attributes].forEach(({name}) => { if (!to.hasAttribute(name) && !own(name)) from.removeAttribute(name); });
    [...to.attributes].forEach(({name, value}) => {
      const target = parked && name === 'title' ? 'data-mi-title' : name;
      if (from.getAttribute(target) !== value) from.setAttribute(target, value);
    });
    runtime.forEach((c) => { if (!to.classList.contains(c)) from.classList.add(c); });
    const focused = from === document.activeElement;
    if (from.nodeName === 'TEXTAREA') {
      if (!focused && from.value !== to.value) from.value = to.value;
      return;
    }
    morphChildren(from, to);
    if (focused) return;
    if (from.nodeName === 'INPUT') {
      if (from.type === 'checkbox' || from.type === 'radio') from.checked = to.hasAttribute('checked');
      else if (from.value !== (to.getAttribute('value') || '') && from.type !== 'file' && from.type !== 'password') from.value = to.getAttribute('value') || '';
    } else if (from.nodeName === 'SELECT') {
      const picked = [...to.querySelectorAll('option')].findIndex((o) => o.hasAttribute('selected'));
      from.selectedIndex = picked < 0 ? 0 : picked;
    }
  }
  // Listeners bound to elements inside the page survive a patch, so each is bound once.
  const boundOnce = new WeakMap();
  function once(el, name) {
    if (!el) return false;
    const names = boundOnce.get(el) || new Set();
    if (names.has(name)) return false;
    names.add(name); boundOnce.set(el, names);
    return true;
  }
  function renderSidebar() {
    paint(sidebarRoot(), window.JobOSRender.sidebar(window.JobOSState));
  }
  // Slow-changing reads are reused for a while instead of being asked for on
  // every refresh; actions that change them call forget().
  const cache = new Map();
  function cached(key, ttlMs, load) {
    const hit = cache.get(key);
    if (hit && Date.now() - hit.at < ttlMs) return hit.value;
    const value = load().then((result) => result, (error) => { cache.delete(key); throw error; });
    cache.set(key, {at: Date.now(), value});
    return value;
  }
  function forget(...keys) { (keys.length ? keys : [...cache.keys()]).forEach((key) => cache.delete(key)); }
  // Draw the page the moment its view changes, from what is already known, so
  // a click never waits on the network; the fetch then fills in what is new.
  function paintNow() {
    const target = root();
    if (!target || !window.JobOSState.capability) return;
    renderSidebar();
    const moved = lastView !== window.JobOSState.activeView;
    paint(target, window.JobOSRender.shell(window.JobOSState), moved);
    target._jobOsHtml = null;  // the fetch that follows patches in what changed and binds the page
    const content = target.querySelector('.job-os-content');
    if (content && moved) { content.classList.add('is-entering'); lastView = window.JobOSState.activeView; }
    if (moved) bindPage(target);
  }
  let refreshRetries = 0;
  // Everything that makes a freshly drawn page live: counts, listeners, Scout polling, drag.
  function afterPaint(target, changed) {
    const state = window.JobOSState;
    if (changed) {
      if (typeof window.animateCounts === 'function') window.animateCounts(target);
      bindPage(target);
    }
    if (state.activeView === 'scout') afterScoutRender(target, changed);
    else stopScoutPolling();
    afterPipelineRender(target, changed);
    renderSidebar();
    bind();
    if (window.ScrollFade) window.ScrollFade.scan(target);
  }
  async function refresh() {
    const state = window.JobOSState;
    const target = root();
    if (!target) return;
    const seq = ++refreshSeq;
    // First open: the app's loading bar until the page has something to show.
    if (!target.firstElementChild && !state.capability) target.innerHTML = window.JobOSRender.LOADING;
    renderSidebar();
    // A tap that changed the page's state shows its result now, from what is
    // already loaded; the fetch below only fills in what is new. Without this a
    // slow link makes every button look dead and gets pressed twice.
    if (state.capability && target.firstElementChild && !dragging) afterPaint(target, paint(target, window.JobOSRender.shell(state), false));
    try {
      const wantSettings = state.activeView === 'settings';
      const wantScout = state.activeView === 'scout';
      const wantDetail = ['pipeline', 'scout', 'dashboard'].includes(state.activeView) && state.selectedJobId;
      const wantResume = state.activeView === 'resume-studio';
      const wantStudioDocs = wantResume && state.studioJobId;
      // A remembered tab for a job site that is no longer offered falls back to All.
      if (state.sites && !['all', 'manual', ...state.sites.map((site) => site.key)].includes(state.pipelineSource)) state.pipelineSource = 'all';
      const wantBoard = state.activeView === 'pipeline' && state.pipelineMode === 'board' && !state.statusFilter;
      const wantAutomations = state.activeView === 'dashboard';
      // Countries feed the Scout form and the tracker's country list; they never change.
      const wantCountries = !state.countries.length;
      // Firecrawl only matters while Scout reads Indeed itself (Apify off).
      const wantFirecrawl = wantScout || wantSettings || !(state.apifyUsage && state.apifyUsage.active);
      const [capability, dashboard, jobs, health, settings, searches, runs, detail, resume, tailored, studioDocs, board, notifications, automations, timeline, matches, apifyUsage, skillsGained] = await Promise.all([
        cached('capability', 10 * 60 * 1000, window.JobOSApi.capability), window.JobOSApi.dashboard(),
        window.JobOSApi.jobs(state.activeView === 'pipeline' && !window.JobOSRender.STATUS_GROUPS[state.statusFilter] ? state.statusFilter : null),
        // Header status only: a Firecrawl outage must not take the page down.
        wantFirecrawl ? cached('firecrawl', 60 * 1000, window.JobOSApi.firecrawlHealth).catch(() => null) : Promise.resolve(null),
        wantSettings ? window.JobOSApi.settings() : Promise.resolve(null),
        wantScout || wantCountries ? window.JobOSApi.searches().catch(() => null) : Promise.resolve(null),
        wantScout ? window.JobOSApi.runs(20) : Promise.resolve(null),
        wantDetail ? window.JobOSApi.job(state.selectedJobId).catch(() => null) : Promise.resolve(null),
        wantResume ? cached('resume', 30 * 1000, window.JobOSApi.resume).catch(() => null) : Promise.resolve(null),
        wantResume ? window.JobOSApi.documents().catch(() => null) : Promise.resolve(null),
        wantStudioDocs ? window.JobOSApi.jobDocuments(state.studioJobId).catch(() => null) : Promise.resolve(null),
        // The whole board comes once; the site tabs and the search box filter it in the page.
        wantBoard ? window.JobOSApi.board().catch(() => null) : Promise.resolve(null),
        wantSettings ? window.JobOSApi.notifications().catch(() => null) : Promise.resolve(null),
        wantAutomations ? cached('automations', 20 * 1000, window.JobOSApi.automations).catch(() => null) : Promise.resolve(null),
        wantDetail ? window.JobOSApi.timeline(state.selectedJobId).catch(() => null) : Promise.resolve(null),
        // The Scout inbox feeds the side-panel badge on every page.
        cached('matches', 20 * 1000, window.JobOSApi.matches).catch(() => null),
        // Apify status and spend for the header chip and the side panel (cached on the server too).
        cached('apify', 60 * 1000, window.JobOSApi.apifyUsage).catch(() => null),
        // Skills gained (Dashboard) for the Resume Studio card; missing is not an error.
        wantResume ? window.JobOSApi.skillsGained().catch(() => null) : Promise.resolve(null),
      ]);
      if (seq !== refreshSeq) return;
      // Resume Studio's match check reads the full analysis of the job it is on:
      // the one stepped to, or the first on the board.
      let match = null;
      if (wantResume && !state.studioJobId && resume && resume.resume) {
        const queue = window.JobOSRender.matchQueue(jobs.jobs || []);
        const pick = queue.find((j) => j.id === state.studioMatchId) || queue[0];
        if (pick) {
          state.studioMatchId = pick.id;
          match = await window.JobOSApi.job(pick.id).catch(() => null);
        }
        if (seq !== refreshSeq) return;
      }
      if (wantResume) state.studioMatch = match && match.job;
      state.capability = capability;
      state.dashboard = dashboard;
      noticeSiteProblems(dashboard && dashboard.site_health);
      state.jobs = jobs.jobs || [];
      if (health) state.firecrawl = health.firecrawl;
      if (searches) {
        state.searches = searches.searches || []; state.searchProvider = searches.search_provider; state.schedule = searches.schedule;
        state.countries = searches.countries || []; state.postedWithin = searches.posted_within_days || state.postedWithin;
        state.apify = searches.apify || null;
        state.sites = searches.sites || state.sites;
      }
      state.jobTimeline = timeline ? timeline.timeline || [] : [];
      if (matches) state.matches = matches.matches;
      if (apifyUsage) state.apifyUsage = apifyUsage.apify;
      if (runs) state.runs = runs.runs || [];
      state.jobDetail = wantDetail ? (detail && detail.job) || null : null;
      if (resume) { state.resume = resume.resume; state.resumeOriginal = resume.original || null; }
      if (skillsGained) state.skillsGained = skillsGained.entries || [];
      if (tailored) state.tailored = tailored.documents || [];
      if (studioDocs) state.studioDocs = studioDocs.documents || {};
      state.board = board || (wantBoard ? state.board : null);
      if (notifications) state.notifications = notifications.notifications;
      if (automations) state.automations = automations.automations;
      if (settings) {
        state.settings = settings.settings;
        state.settingsStatus = settings.status;
        if (settings.status && settings.status.firecrawl) state.firecrawl = settings.status.firecrawl;
        if (!state.settingsDirty) state.settingsDraft = null;
      }
      // While a card is being dragged the board is left alone: the next refresh after the drop draws it.
      if (dragging && !dragging.card.isConnected) dragging = null;
      if (dragging) { repaintAfterDrag = true; return; }
      // A job drawer is still sliding in: patching the page under it now would stutter it.
      const settle = (state.drawerUntil || 0) - Date.now();
      if (settle > 0) { await new Promise((resolve) => setTimeout(resolve, settle)); if (seq !== refreshSeq) return; if (dragging) { repaintAfterDrag = true; return; } }
      const moved = lastView !== state.activeView;
      const changed = paint(target, window.JobOSRender.shell(state), moved);
      if (moved) {
        const content = target.querySelector('.job-os-content');
        if (content) content.classList.add('is-entering');
        lastView = state.activeView;
      }
      afterPaint(target, changed);
      refreshRetries = 0;
    } catch (error) {
      if (seq !== refreshSeq) return;
      // A page already on screen stays put (the next refresh heals it); only a
      // first open with nothing to show gets the error, with a way to retry.
      refreshRetries += 1;
      if (refreshRetries <= 2) { setTimeout(() => { if (seq === refreshSeq) refresh(); }, 2500 * refreshRetries); }
      if (state.capability && target.firstElementChild) return;
      const message = document.createElement('p');
      message.className = 'job-os-error';
      message.textContent = String(error.message || 'Unable to load Job OS.');
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.className = 'job-os-btn job-os-error-retry';
      retry.textContent = 'Try again';
      retry.addEventListener('click', () => { refreshRetries = 0; refresh(); });
      target.innerHTML = '<div class="job-os-shell"></div>';
      target._jobOsHtml = null;
      target.firstChild.appendChild(message);
      target.firstChild.appendChild(retry);
    }
  }
  function showView(view) {
    const state = window.JobOSState;
    const moved = state.activeView !== view;
    // Opening Settings from elsewhere starts at its section list on a phone
    // (the first section on desktop) unless a row asked for a section.
    if (moved && view === 'settings' && !state.settingsFocus) state.settingsSection = null;
    state.activeView = view; state.statusFilter = null; state.resumePreview = null; state.focusColumn = null; replaceRoute(view);
    if (moved) { state.selectedJobId = null; state.jobDetail = null; }
    if (moved) { paintNow(); const main = document.getElementById('mainJobs'); if (main) main.scrollTop = 0; }
    refresh();
  }
  // A removed card fades out, then the cards after it glide into the space it left (FLIP).
  async function closeGap(card) {
    if (!card || !card.isConnected) return;
    if (typeof window.animateRemoval === 'function') await window.animateRemoval(card, {collapse: false});
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const rest = [...card.parentElement.children].filter((el) => el !== card);
    const before = new Map(rest.map((el) => [el, el.getBoundingClientRect()]));
    card.remove();
    if (reduce) return;
    await Promise.all(rest.map((el) => {
      const a = before.get(el), b = el.getBoundingClientRect();
      const dx = a.left - b.left, dy = a.top - b.top;
      if (!dx && !dy) return null;
      return el.animate([{transform: `translate(${dx}px,${dy}px)`}, {transform: 'none'}],
        {duration: 320, easing: 'cubic-bezier(.22,1,.36,1)'}).finished.catch(() => {});
    }));
  }
  // A job site that stopped reading correctly pops up once (per problem, per
  // browser) besides its banner: the email may be off or unread.
  function noticeSiteProblems(sites) {
    (sites || []).filter((site) => site.state && site.state !== 'ok' && site.in_use !== false).forEach((site) => {
      const key = `hermes-jobs-site-notice:${site.site}:${site.since || 0}`;
      try { if (localStorage.getItem(key)) return; localStorage.setItem(key, '1'); } catch (_) { return; }
      const text = site.state === 'changed' ? `${site.name} changed its pages: Scout can no longer read it` : `${site.name} isn't loading for Scout`;
      if (typeof window.showToast === 'function') window.showToast(text, 8000, 'error');
    });
  }
  // A side-panel stage: the board, scrolled to that column (opened if folded), which flashes once.
  function showStage(key) {
    const state = window.JobOSState;
    state.activeView = 'pipeline'; state.statusFilter = null; state.pipelineMode = 'board'; state.resumePreview = null;
    state.focusColumn = key; state.focusPending = key;
    state.collapsedColumns = (state.collapsedColumns || []).filter((c) => c !== key);
    savePrefs(); replaceRoute('pipeline'); paintNow(); refresh();
  }
  // Redraw from the state already loaded (a tab, a filter, typing in a search box).
  function repaint() {
    const target = root();
    if (!target) return;
    const changed = paint(target, window.JobOSRender.shell(window.JobOSState));
    if (changed) bindPage(target);
    afterPipelineRender(target, changed);
  }
  function bindPage(target) {
    const state = window.JobOSState;
    if (window.Micro) { window.Micro.scan(target); window.Micro.scan(sidebarRoot()); }
    bindJobForms(target);
    afterBoardRender(target);
    if (state.activeView === 'resume-studio') { bindResumeUpload(); afterStudioRender(target); }
    afterSettingsRender(target);
  }
  function showStatus(status) { window.JobOSState.activeView = 'pipeline'; window.JobOSState.statusFilter = status || null; replaceRoute('pipeline', window.JobOSState.statusFilter); paintNow(); refresh(); }
  // One delegated listener per container: the page and the side-panel nav
  // re-render on every refresh, so per-button listeners would be rebuilt anyway.
  // A column's filter (text, minimum match, order) redraws that board from what is loaded.
  function setColumnFilter(control) {
    const state = window.JobOSState;
    const col = control.dataset.col;
    state.colFilters = state.colFilters || {};
    state.colFilters[col] = Object.assign({}, state.colFilters[col], {[control.dataset.colFilter]: control.value});
    savePrefs();
    repaint();
  }
  async function onChange(event) {
    const state = window.JobOSState;
    const colControl = event.target.closest('[data-col-filter]');
    if (colControl) { setColumnFilter(colControl); return; }
    const country = event.target.closest('[data-job-os-change="scout-country"]');
    if (country) {
      const form = country.form;
      state.searchForm = Object.assign({}, state.searchForm, searchPayload(form));
      refresh();
      return;
    }
  }
  // The Pipeline search box filters as you type (a frame at a time, never a fetch).
  let searchFrame = 0;
  function onInput(event) {
    const colBox = event.target.closest('input[data-col-filter]');
    if (colBox) { cancelAnimationFrame(searchFrame); searchFrame = requestAnimationFrame(() => setColumnFilter(colBox)); return; }
    const box = event.target.closest('#job-os-pipe-search');
    if (!box) return;
    window.JobOSState.pipelineQuery = box.value;
    cancelAnimationFrame(searchFrame);
    searchFrame = requestAnimationFrame(repaint);
  }
  // After a board move, the card glows in its new column.
  let flashId = null;
  function flash(jobId) { flashId = jobId; }
  function afterBoardRender(target) {
    if (!flashId) return;
    const card = target.querySelector(`.pipe-card[data-board-job="${CSS.escape(flashId)}"]`);
    if (card && typeof window.markArrival === 'function') window.markArrival(card);
    flashId = null;
  }
  // Paper plane from the card to the Applied column.
  function swoosh(fromEl) {
    const to = document.querySelector('.pipe-col[data-col="applied"] header');
    if (!fromEl || !to || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return Promise.resolve();
    const a = fromEl.getBoundingClientRect(), b = to.getBoundingClientRect();
    const plane = document.createElement('span');
    plane.className = 'apply-plane';
    plane.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/></svg>';
    plane.style.left = `${a.left + a.width / 2}px`; plane.style.top = `${a.top + a.height / 2}px`;
    document.body.appendChild(plane);
    const anim = plane.animate([
      {transform: 'translate(-50%,-50%) scale(.6) rotate(0deg)', opacity: 0},
      {transform: 'translate(-50%,-50%) scale(1.1) rotate(-12deg)', opacity: 1, offset: .2},
      {transform: `translate(calc(-50% + ${b.left + b.width / 2 - a.left - a.width / 2}px), calc(-50% + ${b.top + b.height / 2 - a.top - a.height / 2}px)) scale(.7) rotate(18deg)`, opacity: 0},
    ], {duration: 700, easing: 'cubic-bezier(.3,.7,.2,1)'});
    return anim.finished.catch(() => {}).then(() => plane.remove());
  }
  // Button feedback from micro.js: a spinner while working, a drawn tick when
  // done, a shake when it failed. Without micro.js the button is only disabled.
  function pending(button, text) {
    if (!button) return;
    if (window.Micro) window.Micro.busy(button, text); else button.disabled = true;
  }
  function finished(button, ok, text) {
    if (!button || !window.Micro) return;
    if (ok) window.Micro.done(button, text); else window.Micro.fail(button);
  }
  function onClick(event) {
    const copy = event.target.closest('[data-copy-text]');
    if (copy) {
      const done = () => {
        if (typeof window._showCopiedFeedback === 'function') window._showCopiedFeedback(copy, 14);
        if (typeof window.showToast === 'function') window.showToast('Copied');
      };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(copy.dataset.copyText).then(done, () => {});
      return;
    }
    const action = event.target.closest('[data-job-os-action]');
    if (action) { runAction(action.dataset.jobOsAction, action); return; }
    const view = event.target.closest('[data-job-os-view]');
    if (view) { showView(view.dataset.jobOsView); return; }
    const stage = event.target.closest('[data-job-os-stage]');
    if (stage) { showStage(stage.dataset.jobOsStage); return; }
    const filter = event.target.closest('[data-job-os-filter]');
    if (filter) { showStatus(filter.dataset.jobOsFilter); return; }
    if (event.target.closest('select, [data-job-os-change]')) return;
    const job = event.target.closest('[data-job-id]');
    if (job) openJob(job.dataset.jobId);
  }
  function bind() {
    if (aborter) aborter.abort();
    aborter = new AbortController();
    const signal = aborter.signal;
    root().addEventListener('click', onClick, {signal});
    root().addEventListener('change', onChange, {signal});
    root().addEventListener('input', onInput, {signal});
    // A button that showed "Saved" hands back to the page: draw what is current.
    root().addEventListener('mi:released', () => { const t = root(); if (t) { t._jobOsHtml = null; repaint(); } }, {signal});
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
        if (event.key === 'Enter' && event.target.closest('#job-os-apify')) { event.preventDefault(); runAction('apify-connect', document.querySelector('[data-job-os-action="apify-connect"]')); }
      }, {signal});
    }
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
    if (path === 'scout.blocked_companies') return control.value.split('\n');
    if (path === 'scout.run_times') return control.value.split(/[,\s]+/).filter(Boolean);
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
    if (['page', 'settings-focus', 'settings-section', 'activity-month', 'automate-all', 'settings-list', 'match-go', 'match-tailor', 'resume-preview', 'resume-preview-close', 'doc-preview', 'preview-zoom'].includes(name)) return studioAction(name, button);
    if (name.startsWith('scout-') || name === 'job-close') return scoutAction(name, button);
    if (['job-status', 'job-analyze', 'analyze-new', 'job-details', 'job-tailor', 'job-ready', 'job-interview', 'board-apply', 'card-tailor', 'card-details', 'match-score', 'apply-kit'].includes(name) || name.startsWith('resume-') || name.startsWith('studio-')) return pipelineAction(name, button);
    if (name.startsWith('pipe-') || name.startsWith('job-form-')) return trackerAction(name, button);
    if (name === 'discard-settings') {
      state.settingsDraft = null; state.settingsDirty = false; state.settingsError = '';
      refresh();
    } else if (name === 'save-settings') {
      if (!state.settingsDirty || !state.settingsDraft) return;
      const patch = clone(state.settingsDraft);
      delete patch.revision;
      const saveButton = document.querySelector('[data-job-os-action="save-settings"]');
      pending(saveButton, 'Saving…');
      try {
        const saved = await window.JobOSApi.saveSettings(patch, state.settings.revision);
        state.settings = saved.settings; state.settingsStatus = saved.status;
        state.settingsDraft = null; state.settingsDirty = false; state.settingsError = '';
        state.settingsSavedAt = Date.now();
        forget();
        if (typeof window.showToast === 'function') window.showToast('Jobs settings saved');
        finished(saveButton, true, 'Saved');
        refresh();
      } catch (error) {
        state.settingsError = error.message || 'Unable to save settings.';
        finished(saveButton, false);
        syncSaveBar();
      }
    } else if (name === 'gmail-connect') {
      const addressEl = document.getElementById('job-os-gmail-address');
      const passwordEl = document.getElementById('job-os-gmail-password');
      if (!addressEl || !passwordEl) return;
      const address = addressEl.value;
      const password = passwordEl.value;
      passwordEl.value = '';
      pending(button, 'Checking with Gmail…');
      try {
        const result = await window.JobOSApi.connectGmail(address, password);
        state.settingsStatus = Object.assign({}, state.settingsStatus, {gmail: result.gmail});
        state.gmailEditing = false;
        state.gmailMessage = {tone: 'ok', text: 'Gmail connected. It now works for every profile.'};
        if (typeof window.showToast === 'function') window.showToast('Gmail connected');
        refresh();
      } catch (error) {
        state.gmailMessage = {tone: 'error', text: error.message || 'Unable to connect Gmail.'};
        finished(button, false);
        if (window.Micro) { window.Micro.invalid(addressEl); window.Micro.invalid(passwordEl); }
        const msg = document.querySelector('#job-os-gmail .job-os-gmail-msg');
        if (msg) { msg.dataset.tone = 'error'; msg.textContent = state.gmailMessage.text; }
      }
    } else if (name === 'matches-seen') {
      forget('matches');
      try { const r = await window.JobOSApi.matchesSeen(); state.matches = r.matches; } catch (_) { /* the next refresh shows it */ }
      refresh();
    } else if (name.startsWith('apify-')) {
      return apifyAction(name, button);
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
      pending(button, 'Sending…');
      try {
        const contextEl = document.getElementById('job-os-gmail-test-context');
        const result = await window.JobOSApi.testGmail('', contextEl ? contextEl.value : 'jobs');
        state.gmailMessage = {tone: 'ok', text: `Test email from ${result.sender_name} sent to ${result.sent_to}.`};
        finished(button, true, 'Sent');
      } catch (error) {
        state.gmailMessage = {tone: 'error', text: error.message || 'Unable to send the test email.'};
        finished(button, false);
      }
      refresh();
    } else if (name === 'notify-outcomes') {
      pending(button, 'Reading…');
      try {
        const result = await window.JobOSApi.checkOutcomes();
        state.notifications = result.notifications;
        toast(result.moved ? `Moved ${result.moved} job${result.moved === 1 ? '' : 's'} from employer replies` : 'No new employer replies');
        forget('board');
        finished(button, true, 'Checked');
      } catch (error) { toast(error.message || 'Could not read the inbox'); finished(button, false); }
      refresh();
    } else if (name === 'notify-digest' || name === 'notify-check') {
      pending(button, name === 'notify-digest' ? 'Sending…' : 'Checking…');
      try {
        const result = name === 'notify-digest' ? await window.JobOSApi.sendDigest() : await window.JobOSApi.checkReplies();
        state.notifications = result.notifications;
        const text = name === 'notify-digest'
          ? (result.sent ? 'Digest sent.' : 'Nothing new to put in a digest yet.')
          : (result.handled ? `Acted on ${result.handled} repl${result.handled === 1 ? 'y' : 'ies'}.` : 'No new replies.');
        if (typeof window.showToast === 'function') window.showToast(text);
        finished(button, true, name === 'notify-digest' && result.sent ? 'Sent' : 'Done');
      } catch (error) {
        if (typeof window.showToast === 'function') window.showToast(error.message || 'Email step failed');
        finished(button, false);
      }
      refresh();
    } else if (name === 'site-check') {
      pending(button, 'Checking…');
      try {
        const result = await window.JobOSApi.checkSites();
        if (state.dashboard) state.dashboard = Object.assign({}, state.dashboard, {site_health: result.status});
        const bad = (result.status || []).filter((site) => site.state !== 'ok');
        finished(button, !bad.length, bad.length ? 'Still failing' : 'Working');
        toast(bad.length ? `${bad.map((site) => site.name).join(', ')} still can't be read` : 'Every job site reads correctly');
      } catch (error) { finished(button, false); toast(error.message || 'Could not check the job sites'); }
      refresh();
    } else if (name === 'test-firecrawl') {
      pending(button, 'Testing…');
      try {
        const result = await window.JobOSApi.settings();
        state.settingsStatus = result.status;
        state.firecrawl = result.status && result.status.firecrawl;
        finished(button, !!(state.firecrawl && state.firecrawl.state === 'healthy'), 'Reachable');
      } catch (_error) { finished(button, false); /* the status pill keeps its last value */ }
      refresh();
    }
  }
  // ---- Apify token ------------------------------------------------------------
  async function apifyAction(name, button) {
    const state = window.JobOSState;
    const say = (tone, text) => { state.apifyMessage = {tone, text}; };
    if (name === 'apify-edit' || name === 'apify-cancel') { state.apifyEditing = name === 'apify-edit'; state.apifyMessage = null; return refresh(); }
    if (name === 'apify-disconnect') {
      const ok = typeof window.showConfirmDialog === 'function'
        ? await window.showConfirmDialog({message: 'Disconnect Apify? Scout goes back to reading Indeed itself.', confirmLabel: 'Disconnect', danger: true})
        : window.confirm('Disconnect Apify?');
      if (!ok) return undefined;
    }
    const input = document.getElementById('job-os-apify-token');
    const value = input ? input.value : '';
    if (input) input.value = '';
    pending(button, name === 'apify-connect' ? 'Checking with Apify…' : name === 'apify-test' ? 'Testing…' : 'Disconnecting…');
    try {
      let result;
      if (name === 'apify-connect') { result = await window.JobOSApi.connectApify(value); say('ok', `Connected${result.apify.username ? ` as ${result.apify.username}` : ''}. Turn on “Search Indeed through Apify” and save.`); state.apifyEditing = false; }
      else if (name === 'apify-test') { result = await window.JobOSApi.testApify(); say('ok', `The token works${result.apify.username ? ` (${result.apify.username}${result.apify.plan ? `, ${result.apify.plan} plan` : ''})` : ''}.`); }
      else { result = await window.JobOSApi.disconnectApify(); say('ok', 'Apify disconnected.'); }
      state.settingsStatus = Object.assign({}, state.settingsStatus, {apify: result.apify});
      forget('apify', 'firecrawl');
      finished(button, true, name === 'apify-connect' ? 'Connected' : name === 'apify-test' ? 'Works' : 'Done');
    } catch (error) {
      say('error', error.message || 'Apify request failed.');
      finished(button, false);
      if (name === 'apify-connect' && window.Micro) window.Micro.invalid(document.getElementById('job-os-apify-token'));
    }
    return refresh();
  }
  // ---- Pipeline: analysis polling, triage, resume ---------------------------
  let analysisTimer = null;
  let dashboardTimer = null;
  const busy = (job) => !!(job && job.analysis && ['pending', 'running'].includes(job.analysis.status));
  function afterPipelineRender(target, changed) {
    const state = window.JobOSState;
    const docBusy = Object.values(state.studioDocs || {}).some((d) => ['pending', 'running'].includes(d.status)
      || (d.notes && d.notes.tailored_fit && d.notes.tailored_fit.status === 'running'))
      || (state.tailored || []).some((d) => ['pending', 'running'].includes(d.status));
    const watching = (['pipeline', 'dashboard'].includes(state.activeView)
      && ((state.jobs || []).some(busy) || (state.jobs || []).some((j) => j.status === 'tailoring' || j.status === 'applying') || busy(state.jobDetail)
        || !!(state.jobDetail && state.jobDetail.interview && ['pending', 'running'].includes(state.jobDetail.interview.status))
        || !!(state.jobDetail && state.jobDetail.apply_kit && state.jobDetail.apply_kit.status === 'running')))
      || (state.activeView === 'resume-studio' && (docBusy || busy(state.studioMatch)
        || (state.jobs || []).some((j) => busy(j) || j.status === 'tailoring')) && state.studioDraft == null);
    if (watching && !analysisTimer) analysisTimer = setInterval(() => { if (!document.hidden) refresh(); }, 2500);
    if (!watching && analysisTimer) { clearInterval(analysisTimer); analysisTimer = null; }
    // The dashboard also checks in every 30s while nothing is busy, so a score
    // or a job that Scout or the analysis queue added in the background shows
    // up on its own instead of after a reload.
    const idle = state.activeView === 'dashboard' && !watching;
    if (idle && !dashboardTimer) dashboardTimer = setInterval(() => { if (!document.hidden) refresh(); }, 30000);
    if (!idle && dashboardTimer) { clearInterval(dashboardTimer); dashboardTimer = null; }
    if (!changed) return;
    const sort = document.getElementById('job-os-sort');
    if (once(sort, 'sort')) sort.addEventListener('change', () => { state.sortBy = sort.value; refresh(); });
    initBoardDrag(target);
    const editor = document.getElementById('studio-text');
    if (once(editor, 'edit')) editor.addEventListener('input', () => {
      state.studioDraft = editor.value;
      const save = document.querySelector('[data-job-os-action="studio-save"]');
      const doc = (state.studioDocs || {})[state.studioTab];
      if (save) save.disabled = !doc || editor.value === doc.content;
    });
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
      if (typeof window.showToast === 'function') window.showToast(status === 'shortlisted' ? 'Added to Favorite' : status === 'skipped' ? 'Skipped' : 'Updated');
      const ids = orderedJobIds();
      const next = ids[ids.indexOf(job.id) + 1];
      if (status === 'skipped' && next) state.selectedJobId = next;
    } catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not update the job'); }
    refresh();
  }
  function onTriageKey(event) {
    const state = window.JobOSState;
    // Some embedded WebViews dispatch synthetic keydown events without a
    // `key` string. Treat those as an unrecognised shortcut rather than
    // throwing globally and disabling every following keyboard interaction.
    const key=String(event.key||'').toLowerCase();
    if ((state.activeView !== 'pipeline' && key !== 'escape') || !state.jobDetail || state.jobForm || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.target.closest('input,textarea,select,[contenteditable="true"]')) return;
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
  // Esc closes the job form wherever it is open.
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && window.JobOSState.jobForm && document.getElementById('job-os-job-form')) { event.preventDefault(); trackerAction('job-form-close'); return; }
    const search = document.getElementById('job-os-pipe-search');
    if (!search) return;
    if (event.key === 'Escape' && event.target === search && search.value) { event.preventDefault(); trackerAction('pipe-search-clear'); }
    // "/" jumps to the Pipeline search box, as in most web apps.
    else if (event.key === '/' && !event.target.closest('input,textarea,select,[contenteditable="true"]') && !event.metaKey && !event.ctrlKey) { event.preventDefault(); search.focus(); search.select(); }
  });
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
      forget('resume');
      if (typeof window.showToast === 'function') window.showToast('Resume saved');
    } catch (error) { state.resumeError = error.message || 'Could not read that resume.'; }
    refresh();
  }
  function bindResumeUpload() {
    const drop = document.getElementById('resume-drop');
    const input = document.getElementById('resume-file');
    if (!drop || !input || !once(drop, 'upload')) return;
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
    if (name === 'job-interview' && job) {
      try { await window.JobOSApi.interviewPrep(job.id); }
      catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not start interview prep'); }
      return refresh();
    }
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
    if ((name === 'job-tailor' && job) || name === 'card-tailor') {
      const id = name === 'card-tailor' ? el.dataset.jobId : job.id;
      if (el) el.disabled = true;
      try { await window.JobOSApi.tailor(id); if (typeof window.showToast === 'function') window.showToast('Luna is tailoring your resume'); }
      catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not start tailoring'); }
      return refresh();
    }
    if (name === 'apply-kit' && job) {
      if (el) el.disabled = true;
      try { await window.JobOSApi.applyKit(job.id); }
      catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not prepare the answers'); }
      return refresh();
    }
    if (name === 'card-details') {
      el.disabled = true; el.textContent = 'Reading…';
      try { await window.JobOSApi.fetchDetails(el.dataset.jobId); flash(el.dataset.jobId); }
      catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not read that posting'); }
      return refresh();
    }
    if (name === 'match-score') {
      el.disabled = true;
      state.studioMatchId = el.dataset.jobId;
      try { await window.JobOSApi.analyzeJob(el.dataset.jobId, true); }
      catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not score your resume'); }
      return refresh();
    }
    if ((name === 'job-ready' && job) || name === 'studio-ready') {
      const id = name === 'studio-ready' ? state.studioJobId : job.id;
      try { await window.JobOSApi.markReady(id); if (typeof window.showToast === 'function') window.showToast('Ready to apply'); }
      catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not update the job'); }
      return refresh();
    }
    if (name === 'studio-open') {
      const id = el.dataset.jobId;
      if (state.studioDraft != null && state.studioJobId && state.studioJobId !== id && !window.confirm('Discard unsaved edits?')) return undefined;
      state.studioJobId = id; state.studioDocs = null; state.studioDraft = null; state.studioTab = 'resume';
      state.activeView = 'resume-studio'; state.statusFilter = null; replaceRoute('resume-studio');
      return refresh();
    }
    if (name === 'studio-close' || name === 'studio-tab') {
      if (state.studioDraft != null && !window.confirm('Discard unsaved edits?')) return undefined;
      state.studioDraft = null;
      if (name === 'studio-close') { state.studioJobId = null; state.studioDocs = null; } else state.studioTab = el.dataset.tab;
      paintNow();
      return refresh();
    }
    if (name === 'studio-save') {
      const doc = (state.studioDocs || {})[state.studioTab];
      if (!doc || state.studioDraft == null) return undefined;
      try {
        const saved = await window.JobOSApi.saveDocument(doc.id, state.studioDraft, doc.revision);
        state.studioDocs[state.studioTab] = saved.document; state.studioDraft = null;
        if (typeof window.showToast === 'function') window.showToast(saved.document.status === 'ready' ? 'Saved' : 'Saved — some numbers still need checking');
      } catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not save'); }
      return refresh();
    }
    if (name === 'studio-rescore') {
      const doc = (state.studioDocs || {}).resume;
      if (!doc) return undefined;
      try { const r = await window.JobOSApi.rescoreDocument(doc.id); state.studioDocs.resume = r.document; }
      catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not score it'); }
      return refresh();
    }
    if (name === 'studio-retry') {
      try { await window.JobOSApi.tailor(state.studioJobId); } catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not retry'); }
      return refresh();
    }
    if (name === 'board-apply') {
      const id = el.dataset.jobId;
      // From a card the posting opens to apply there; from the drawer the
      // application already went out and is only being recorded.
      const fromCard = !!el.closest('.pipe-card');
      if (fromCard) window.open(el.dataset.url, '_blank', 'noopener');
      const ok = typeof window.showConfirmDialog === 'function'
        ? await window.showConfirmDialog(fromCard
          ? {title: 'Did you submit it?', message: 'The posting opened in a new tab. Once you have sent the application there, record it here.', confirmLabel: 'I applied', cancelLabel: 'Not yet'}
          : {title: 'Mark as applied?', message: 'Record that you sent the application for this job. It moves to Applied.', confirmLabel: 'Mark applied', cancelLabel: 'Cancel'})
        : window.confirm('Did you submit the application?');
      if (!ok) return undefined;
      try {
        const card = el.closest('.pipe-card') || document.querySelector(`.pipe-card[data-board-job="${CSS.escape(id)}"]`);
        await window.JobOSApi.markApplied(id);
        if (card) card.classList.add('is-sent');
        await swoosh(card);
        flash(id);
        if (typeof window.showToast === 'function') window.showToast('Application recorded');
      } catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not record it'); }
      return refresh();
    }
    if (name === 'skills-manage') {
      // Skills are kept on the Dashboard's Career tab; open it there.
      if (typeof window.switchPanel === 'function') window.switchPanel('dashboard');
      if (window.HermesDashboard) window.HermesDashboard.select('career');
      return;
    }
    if (name === 'resume-replace') { state.resumeReplacing = true; state.resumeError = ''; return refresh(); }
    if (name === 'resume-cancel') { state.resumeReplacing = false; state.resumeError = ''; return refresh(); }
    if (name === 'resume-paste') {
      const text = (document.getElementById('resume-text') || {}).value || '';
      forget('resume');
      try { const r = await window.JobOSApi.pasteResume(text); state.resume = r.resume; state.resumeError = ''; state.resumeReplacing = false; }
      catch (error) { state.resumeError = error.message || 'Could not save that text.'; }
      return refresh();
    }
    return undefined;
  }
  // ---- Pages, settings shortcuts, the match check and resume previews -------------------
  const toast = (text) => { if (typeof window.showToast === 'function') window.showToast(text); };
  async function studioAction(name, el) {
    const state = window.JobOSState;
    if (name === 'page') {
      const key = el.dataset.pager === 'finds' ? 'findsPage' : 'recentPage';
      state[key] = Math.max(0, Number(el.dataset.page) || 0);
      paint(root(), window.JobOSRender.shell(state));
      const card = root().querySelector(`[data-job-os-action="page"][data-pager="${el.dataset.pager}"]`);
      const section = card && card.closest('.job-os-card');
      const list = section && section.querySelector('.job-os-list');
      if (list) { list.classList.remove('is-paging'); void list.offsetWidth; list.classList.add('is-paging'); }
      return undefined;
    }
    if (name === 'settings-focus') {
      state.settingsFocus = el.dataset.section || '';
      if (state.settingsFocus) state.settingsSection = window.JobOSRender.settingsPageOf(state.settingsFocus);
      return showView('settings');
    }
    if (name === 'settings-list') {
      state.settingsSection = null;
      repaint();
      const main = document.getElementById('mainJobs');
      if (main) main.scrollTo({top: 0, behavior: 'smooth'});
      return undefined;
    }
    if (name === 'settings-section') {
      state.settingsSection = el.dataset.section || 'connections';
      repaint();
      const main = document.getElementById('mainJobs');
      if (main && main.scrollTop > 120) main.scrollTo({top: 0, behavior: 'smooth'});
      return undefined;
    }
    if (name === 'activity-month') {
      state.activityMonth = Math.max(0, Math.min(5, (state.activityMonth || 0) + Number(el.dataset.step || 0)));
      return repaint();
    }
    if (name === 'match-go') {
      if (!el.dataset.jobId) return undefined;
      state.studioMatchId = el.dataset.jobId;
      state.matchDirection = el.closest('.match-step') && el.getAttribute('aria-label') === 'Previous job' ? 'back' : 'forward';
      return refresh();
    }
    if (name === 'match-tailor') {
      el.disabled = true;
      try { await window.JobOSApi.tailor(el.dataset.jobId); toast('Luna is tailoring your resume'); }
      catch (error) { toast(error.message || 'Could not start tailoring'); }
      if (el.dataset.nextId) { state.studioMatchId = el.dataset.nextId; state.matchDirection = 'forward'; }
      forget('resume');
      return refresh();
    }
    if (name === 'automate-all') {
      const queue = window.JobOSRender.matchQueue(state.jobs || []).filter((j) => ['scraped', 'analyzed', 'shortlisted'].includes(j.status));
      if (!queue.length) { toast('Every job here is already tailored or under way'); return undefined; }
      const ok = typeof window.showConfirmDialog === 'function'
        ? await window.showConfirmDialog({title: 'Automate all?', confirmLabel: 'Automate all',
          message: `Luna tailors a resume for all ${queue.length} job${queue.length === 1 ? '' : 's'} here not yet tailored, scoring any without a score first. It runs in the background, one job at a time, and each finished job moves to Ready to apply. Nothing is sent; you apply when you have time.`})
        : window.confirm('Score and tailor every job here?');
      if (!ok) return undefined;
      el.disabled = true;
      try {
        const r = (await window.JobOSApi.automate(queue.map((j) => j.id))).automate;
        const parts = [r.tailoring && `${r.tailoring} tailoring now`, r.scoring && `${r.scoring} being scored first`].filter(Boolean);
        toast(parts.length ? parts.join(' · ') : 'Nothing to automate');
      } catch (error) { toast(error.message || 'Could not start'); }
      return refresh();
    }
    if (name === 'resume-preview') {
      state.resumePreview = el.dataset.kind === 'pdf'
        ? {kind: 'pdf', url: '/api/job-os/resume/original', title: state.resume ? state.resume.filename : 'Master resume'}
        : {kind: 'html', url: '/api/job-os/resume/preview', title: state.resume ? state.resume.filename : 'Master resume'};
      return openPreview();
    }
    if (name === 'doc-preview') {
      state.resumePreview = {kind: 'html', url: el.dataset.url, title: el.dataset.title || 'Preview'};
      return openPreview();
    }
    if (name === 'resume-preview-close') {
      // Zoomed in, a tap on the page is a pan, not a close: only the close
      // button (or Esc) closes then.
      if ((state.previewZoom || 1) > 1 && !el.classList.contains('resume-preview-ctl')) return undefined;
      return closePreview();
    }
    if (name === 'preview-zoom') {
      const step = el.dataset.step;
      const now = state.previewZoom || 1;
      setPreviewZoom(step === 'reset' ? 1 : now * (step === 'in' ? 1.25 : 0.8));
      return undefined;
    }
    return undefined;
  }
  // Preview zoom is applied in place (CSS zoom on the pages), never by a
  // re-render, so the drawn PDF pages and the scroll position survive it.
  const PREVIEW_ZOOM_MIN = 1;
  const PREVIEW_ZOOM_MAX = 4;
  function setPreviewZoom(value, anchor) {
    const state = window.JobOSState;
    const overlay = document.querySelector('.resume-preview');
    const before = state.previewZoom || 1;
    const next = Math.min(PREVIEW_ZOOM_MAX, Math.max(PREVIEW_ZOOM_MIN, Math.round(value * 100) / 100));
    state.previewZoom = next;
    if (!overlay) return;
    // Keep the point under the fingers (or the centre) where it is.
    const ax = anchor ? anchor.x : overlay.clientWidth / 2;
    const ay = anchor ? anchor.y : overlay.clientHeight / 2;
    const cx = (overlay.scrollLeft + ax) / before;
    const cy = (overlay.scrollTop + ay) / before;
    overlay.style.setProperty('--preview-zoom', String(next));
    overlay.classList.toggle('is-zoomed', next > 1);
    const level = overlay.querySelector('.resume-preview-level');
    if (level) level.textContent = `${Math.round(next * 100)}%`;
    fitPreviewFrame(overlay);
    overlay.scrollLeft = cx * next - ax;
    overlay.scrollTop = cy * next - ay;
  }
  // An HTML resume (same-origin frame) is magnified inside its frame and the
  // frame grows to its full height, so the overlay, not the frame, scrolls.
  function fitPreviewFrame(scope) {
    const frame = scope && scope.querySelector('.resume-preview-pages iframe');
    if (!frame) return;
    try {
      const doc = frame.contentDocument;
      doc.documentElement.style.zoom = String(window.JobOSState.previewZoom || 1);
      frame.style.height = `${doc.documentElement.scrollHeight * (window.JobOSState.previewZoom || 1) + 8}px`;
    } catch (_) { /* cross-origin: leave the frame as it is */ }
  }
  // Two-finger pinch on the preview (phones). The app behind never zooms:
  // the overlay is touch-action:pan-x pan-y and the pinch is handled here.
  let pinch = null;
  const touchGap = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
  document.addEventListener('touchstart', (event) => {
    const overlay = event.touches.length === 2 && event.target.closest ? event.target.closest('.resume-preview') : null;
    if (!overlay) return;
    const box = overlay.getBoundingClientRect();
    pinch = {gap: touchGap(event.touches) || 1, zoom: window.JobOSState.previewZoom || 1,
      x: (event.touches[0].clientX + event.touches[1].clientX) / 2 - box.left,
      y: (event.touches[0].clientY + event.touches[1].clientY) / 2 - box.top};
  }, {passive: true});
  document.addEventListener('touchmove', (event) => {
    if (!pinch || event.touches.length !== 2) return;
    if (event.cancelable) event.preventDefault();
    setPreviewZoom(pinch.zoom * (touchGap(event.touches) / pinch.gap), pinch);
  }, {passive: false});
  document.addEventListener('touchend', (event) => { if (event.touches.length < 2) pinch = null; }, {passive: true});
  document.addEventListener('touchcancel', () => { pinch = null; }, {passive: true});
  // Safari's own pinch would zoom the whole app behind the preview.
  document.addEventListener('gesturestart', (event) => { if (event.target.closest && event.target.closest('.resume-preview')) event.preventDefault(); });
  function openPreview() {
    window.JobOSState.previewZoom = 1;
    paint(root(), window.JobOSRender.shell(window.JobOSState));
    root()._jobOsHtml = null;
    afterStudioRender(root());
    const overlay = document.querySelector('.resume-preview');
    if (overlay) overlay.focus({preventScroll: true});
  }
  function closePreview() {
    const overlay = document.querySelector('.resume-preview');
    window.JobOSState.resumePreview = null;
    const done = () => { paint(root(), window.JobOSRender.shell(window.JobOSState)); root()._jobOsHtml = null; afterStudioRender(root()); };
    if (!overlay || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return done();
    overlay.classList.add('is-closing');
    setTimeout(done, 170);
    return undefined;
  }
  document.addEventListener('keydown', (event) => {
    const state = window.JobOSState;
    if (event.key === 'Escape' && state.resumePreview) { event.preventDefault(); closePreview(); return; }
    if (state.resumePreview && (event.metaKey || event.ctrlKey) && ['=', '+', '-', '0'].includes(event.key)) {
      event.preventDefault();
      setPreviewZoom(event.key === '0' ? 1 : (state.previewZoom || 1) * (event.key === '-' ? 0.8 : 1.25));
      return;
    }
    if (state.activeView !== 'resume-studio' || state.studioJobId || state.resumePreview || event.metaKey || event.ctrlKey || event.altKey) return;
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key) || event.target.closest('input,textarea,select,[contenteditable="true"]')) return;
    const step = document.querySelector(`.match-step[aria-label="${event.key === 'ArrowLeft' ? 'Previous job' : 'Next job'}"]:not([disabled])`);
    if (step) { event.preventDefault(); studioAction('match-go', step); }
  });
  // PDF pages are drawn with PDF.js, loaded the same way as the chat's PDF
  // previews (shared window._pdfjsLib).
  let pdfjs = null;
  function loadPdfJs() {
    if (window._pdfjsLib) return Promise.resolve(window._pdfjsLib);
    if (pdfjs) return pdfjs;
    pdfjs = new Promise((resolve, reject) => {
      const src = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.9.155/build/pdf.min.mjs';
      const worker = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.9.155/build/pdf.worker.min.mjs';
      const blob = new Blob([`import*as p from'${src}';p.GlobalWorkerOptions.workerSrc='${worker}';window._pdfjsLib=p;window._pdfjsReady=true;window.dispatchEvent(new Event('pdfjs-ready'));`], {type: 'application/javascript'});
      const script = document.createElement('script');
      script.type = 'module';
      script.src = URL.createObjectURL(blob);
      window.addEventListener('pdfjs-ready', () => resolve(window._pdfjsLib), {once: true});
      script.onerror = () => { pdfjs = null; reject(new Error('PDF viewer unavailable')); };
      document.head.appendChild(script);
      setTimeout(() => { if (!window._pdfjsLib) { pdfjs = null; reject(new Error('PDF viewer timed out')); } }, 15000);
    });
    return pdfjs;
  }
  let pdfDoc = null; // {revision, promise}
  function masterPdf() {
    const revision = (window.JobOSState.resume || {}).revision;
    if (!pdfDoc || pdfDoc.revision !== revision) {
      pdfDoc = {revision, promise: loadPdfJs().then((lib) => fetch('/api/job-os/resume/original').then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.arrayBuffer();
      }).then((buf) => lib.getDocument({data: buf, isEvalSupported: false}).promise))};
      pdfDoc.promise.catch(() => { pdfDoc = null; });
    }
    return pdfDoc.promise;
  }
  async function drawPages(host, {scale, max}) {
    try {
      const pdf = await masterPdf();
      if (!host.isConnected) return;
      const canvases = [];
      for (let i = 1; i <= Math.min(pdf.numPages, max); i += 1) {
        const page = await pdf.getPage(i);
        const viewport = page.getViewport({scale: scale * (window.devicePixelRatio || 1)});
        const canvas = document.createElement('canvas');
        canvas.width = viewport.width; canvas.height = viewport.height;
        canvas.className = 'resume-page-canvas';
        await page.render({canvasContext: canvas.getContext('2d'), viewport}).promise;
        canvases.push(canvas);
      }
      if (!host.isConnected) return;
      host.replaceChildren(...canvases);
      host.classList.add('is-drawn');
      if (max === 1 && canvases[0]) window.JobOSState.resumeThumb = {revision: (window.JobOSState.resume || {}).revision, url: canvases[0].toDataURL('image/png')};
    } catch (_) {
      // Offline or blocked: show the text in its design instead.
      host.dataset.kind = 'html';
      host.innerHTML = '<iframe src="/api/job-os/resume/preview" title="Resume" tabindex="-1"></iframe>';
    }
  }
  function afterStudioRender(target) {
    const thumb = target.querySelector('#resume-thumb[data-kind="pdf"]');
    if (thumb && !thumb.classList.contains('is-drawn')) drawPages(thumb, {scale: 0.36, max: 1});
    const pages = target.querySelector('#resume-preview-pages');
    if (pages && pages.dataset.kind === 'pdf') drawPages(pages, {scale: 1.35, max: 6});
    // HTML previews grow to their full height so the overlay scrolls, not the frame.
    if (pages && pages.dataset.kind === 'html') {
      const frame = pages.querySelector('iframe');
      if (once(frame, 'fit')) frame.addEventListener('load', () => fitPreviewFrame(pages.parentElement), {once: true});
    }
    const match = target.querySelector('.match-body');
    if (match && window.JobOSState.matchDirection) {
      match.dataset.enter = window.JobOSState.matchDirection;
      window.JobOSState.matchDirection = null;
    }
  }
  // A Settings section asked for (an automation row, a Scout tile) scrolls into view and glows.
  function afterSettingsRender(target) {
    const state = window.JobOSState;
    if (!state.settingsFocus || state.activeView !== 'settings') return;
    const section = target.querySelector(`#job-os-settings-${CSS.escape(state.settingsFocus)}`);
    if (!section) return;
    state.settingsFocus = '';
    requestAnimationFrame(() => {
      section.scrollIntoView({block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
      section.classList.remove('is-focus'); void section.offsetWidth; section.classList.add('is-focus');
    });
  }
  // ---- Board drag and drop -----------------------------------------------------------
  // Any card but one Luna is tailoring can go to any other column, back as well
  // as forward; the server gives the job the status that column means for it.
  // While a card is in the air the board is not redrawn (a refresh would drop
  // it); the refresh that was due runs after the drop.
  let dragging = null;
  let repaintAfterDrag = false;
  function endDrag(board) {
    if (!dragging) return;
    dragging.card.classList.remove('dragging');
    board.classList.remove('is-dragging');
    board.querySelectorAll('.pipe-col').forEach((col) => col.classList.remove('can-drop', 'drop-target'));
    if (typeof hideDragSlot === 'function') hideDragSlot();
    dragging = null;
    if (repaintAfterDrag) { repaintAfterDrag = false; setTimeout(refresh, 0); }
  }
  // The board's own scrollbar sits under its tallest column, often off screen;
  // a twin pinned to the bottom of the view scrolls it, and dragging empty
  // board space with the mouse pans it.
  function initBoardScroll(target) {
    const board = target.querySelector('.pipe-board');
    const bar = target.querySelector('.pipe-hscroll');
    if (!board || !bar) return;
    const state = window.JobOSState;
    const focus = state.focusPending && board.querySelector(`.pipe-col[data-col="${state.focusPending}"]`);
    if (focus) {
      state.focusPending = null;
      const left = focus.offsetLeft - board.offsetLeft - 12;
      board.scrollTo({left: Math.max(0, left), behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
      focus.classList.remove('is-focused'); void focus.offsetWidth; focus.classList.add('is-focused');
      setTimeout(() => focus.classList.remove('is-focused'), 1500);
    }
    const sync = () => {
      bar.firstElementChild.style.width = `${board.scrollWidth}px`;
      bar.classList.toggle('is-idle', board.scrollWidth <= board.clientWidth + 1);
      if (Math.abs(bar.scrollLeft - board.scrollLeft) > 1) bar.scrollLeft = board.scrollLeft;
    };
    sync();
    if (!once(board, 'scroll')) return;
    board.addEventListener('scroll', () => { if (Math.abs(bar.scrollLeft - board.scrollLeft) > 1) bar.scrollLeft = board.scrollLeft; }, {passive: true});
    bar.addEventListener('scroll', () => { if (Math.abs(board.scrollLeft - bar.scrollLeft) > 1) board.scrollLeft = bar.scrollLeft; }, {passive: true});
    if (typeof ResizeObserver === 'function') new ResizeObserver(sync).observe(board);
    // A column's own scrollbar shows while it scrolls, then fades away.
    board.addEventListener('scroll', (event) => {
      const list = event.target.classList && event.target.classList.contains('pipe-col-cards') ? event.target : null;
      if (!list) return;
      list.classList.add('is-scrolling');
      clearTimeout(list._scrollFade);
      list._scrollFade = setTimeout(() => list.classList.remove('is-scrolling'), 900);
    }, {capture: true, passive: true});
    let pan = null;
    board.addEventListener('pointerdown', (event) => {
      if (event.pointerType !== 'mouse' || event.button !== 0 || dragging) return;
      if (event.target.closest('.pipe-card, button, a, input, select, textarea, label, .pipe-drop-menu')) return;
      if (board.scrollWidth <= board.clientWidth) return;
      pan = {x: event.clientX, left: board.scrollLeft, id: event.pointerId, moved: false};
    });
    board.addEventListener('pointermove', (event) => {
      if (!pan || event.pointerId !== pan.id) return;
      const dx = event.clientX - pan.x;
      if (!pan.moved && Math.abs(dx) < 4) return;
      if (!pan.moved) { pan.moved = true; board.setPointerCapture(pan.id); board.classList.add('is-panning'); }
      board.scrollLeft = pan.left - dx;
    });
    const stop = (event) => {
      if (!pan || event.pointerId !== pan.id) return;
      if (pan.moved && board.hasPointerCapture(pan.id)) board.releasePointerCapture(pan.id);
      board.classList.remove('is-panning');
      pan = null;
    };
    board.addEventListener('pointerup', stop);
    board.addEventListener('pointercancel', stop);
  }
  function initBoardDrag(target) {
    initBoardScroll(target);
    const board = target.querySelector('.pipe-board');
    if (!board || !once(board, 'drag')) return;
    // Near the board's left or right edge, a dragged card scrolls the board so
    // columns off screen can be reached.
    let edge = 0;
    let edgeLoop = 0;
    const scrollEdge = () => {
      if (!dragging || !edge) { edgeLoop = 0; return; }
      board.scrollLeft += edge;
      edgeLoop = requestAnimationFrame(scrollEdge);
    };
    const columnAt = (event) => {
      const col = event.target.closest && event.target.closest('.pipe-col');
      return col && dragging && col.dataset.col !== dragging.from ? col : null;
    };
    board.addEventListener('dragstart', (event) => {
      const card = event.target.closest('.pipe-card[draggable="true"]');
      if (!card) return;
      dragging = {id: card.dataset.boardJob, from: card.closest('.pipe-col').dataset.col, height: card.offsetHeight, card};
      event.dataTransfer.setData('text/plain', dragging.id);
      event.dataTransfer.effectAllowed = 'move';
      requestAnimationFrame(() => { if (dragging && dragging.card === card) card.classList.add('dragging'); });
      board.classList.add('is-dragging');
      board.querySelectorAll('.pipe-col').forEach((col) => col.classList.toggle('can-drop', col.dataset.col !== dragging.from));
    });
    board.addEventListener('dragend', () => { edge = 0; endDrag(board); });
    board.addEventListener('dragover', (event) => {
      if (!dragging) return;
      const box = board.getBoundingClientRect();
      const zone = Math.min(80, box.width / 6);
      edge = event.clientX < box.left + zone ? -Math.ceil((box.left + zone - event.clientX) / 6)
        : event.clientX > box.right - zone ? Math.ceil((event.clientX - (box.right - zone)) / 6) : 0;
      if (edge && !edgeLoop) edgeLoop = requestAnimationFrame(scrollEdge);
      const col = columnAt(event);
      if (!col) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';
      if (!col.classList.contains('drop-target')) {
        board.querySelectorAll('.pipe-col.drop-target').forEach((other) => other.classList.remove('drop-target'));
        col.classList.add('drop-target');
        const list = col.querySelector('.pipe-col-cards');
        if (typeof showDragSlot === 'function' && list) {
          showDragSlot(list, dragging.height);
          // The slot sits where the card will land: at the top, in place of "Drop a job here".
          const slot = list.querySelector('.drag-slot');
          if (slot && slot !== list.firstElementChild) list.prepend(slot);
        }
      }
    });
    board.addEventListener('dragleave', (event) => {
      if (!board.contains(event.relatedTarget)) {
        edge = 0;
        board.querySelectorAll('.pipe-col.drop-target').forEach((col) => col.classList.remove('drop-target'));
        if (typeof hideDragSlot === 'function') hideDragSlot();
      }
    });
    board.addEventListener('drop', (event) => {
      const col = columnAt(event);
      if (!col) return;
      event.preventDefault();
      const {card} = dragging;
      edge = 0;
      endDrag(board);
      dropOn(card, col.dataset.col, col);
    });
    initTouchDrag(board);
  }
  // Touch: hold a card to pick it up, then drag it onto another column. A move
  // before the hold fires is an ordinary scroll; a still tap still opens the card.
  const TOUCH_HOLD_MS = 380;
  const TOUCH_SLOP = 8;
  const TOUCH_EDGE = 64;
  function scrollParent(node) {
    for (let el = node.parentElement; el; el = el.parentElement) {
      const y = getComputedStyle(el).overflowY;
      if ((y === 'auto' || y === 'scroll') && el.scrollHeight > el.clientHeight + 1) return el;
    }
    return document.scrollingElement;
  }
  function initTouchDrag(board) {
    let hold = null;
    // Geometry, not what is under the finger: a short column grows and shrinks
    // as the drop slot opens in it, and a hit test would flicker between the
    // column and the board behind it.
    const target = (x, y) => {
      const cols = [...board.querySelectorAll('.pipe-col')];
      if (!cols.length) return null;
      const rects = cols.map((col) => col.getBoundingClientRect());
      const stacked = cols.length > 1 && rects[1].top > rects[0].top + 4;
      const frame = board.getBoundingClientRect();
      if (x < frame.left - 12 || x > frame.right + 12 || y < frame.top - 12 || y > frame.bottom + 12) return null;
      const at = rects.findIndex((r) => (stacked ? y >= r.top - 6 && y <= r.bottom + 6 : x >= r.left - 6 && x <= r.right + 6));
      const col = at < 0 ? null : cols[at];
      return col && hold && col.dataset.col !== hold.from ? col : null;
    };
    const aim = (col) => {
      if (col === hold.col) return;
      board.querySelectorAll('.pipe-col.drop-target').forEach((other) => other.classList.remove('drop-target'));
      if (typeof hideDragSlot === 'function') hideDragSlot();
      hold.col = col;
      if (!col) return;
      col.classList.add('drop-target');
      const list = col.querySelector('.pipe-col-cards');
      if (typeof showDragSlot === 'function' && list) {
        showDragSlot(list, hold.height);
        const slot = list.querySelector('.drag-slot');
        if (slot && slot !== list.firstElementChild) list.prepend(slot);
      }
    };
    const follow = () => {
      if (!hold || !hold.active) return;
      hold.ghost.style.transform = `translate3d(${hold.x - hold.offsetX}px,${hold.y - hold.offsetY}px,0) rotate(1.5deg) scale(1.03)`;
      aim(target(hold.x, hold.y));
    };
    const autoScroll = () => {
      if (!hold || !hold.active) return;
      const box = hold.scroller === document.scrollingElement ? {top: 0, bottom: innerHeight} : hold.scroller.getBoundingClientRect();
      const dy = hold.y < box.top + TOUCH_EDGE ? -1 : hold.y > box.bottom - TOUCH_EDGE ? 1 : 0;
      const wide = board.getBoundingClientRect();
      const dx = board.scrollWidth > board.clientWidth + 1 ? (hold.x < wide.left + TOUCH_EDGE ? -1 : hold.x > wide.right - TOUCH_EDGE ? 1 : 0) : 0;
      if (dy) hold.scroller.scrollTop += dy * 10;
      if (dx) board.scrollLeft += dx * 10;
      if (dy || dx) follow();
      hold.raf = requestAnimationFrame(autoScroll);
    };
    const finish = (commit) => {
      const current = hold; hold = null;
      if (!current) return;
      clearTimeout(current.timer);
      if (!current.active) return;
      cancelAnimationFrame(current.raf);
      current.ghost.remove();
      document.documentElement.classList.remove('job-os-touch-dragging');
      const col = commit ? current.col : null;
      // The finger lifts on the card: swallow the click it would make.
      const swallow = (event) => { event.preventDefault(); event.stopImmediatePropagation(); };
      board.addEventListener('click', swallow, {capture: true, once: true});
      setTimeout(() => board.removeEventListener('click', swallow, true), 450);
      board.querySelectorAll('.pipe-col.drop-target').forEach((el) => el.classList.remove('drop-target'));
      endDrag(board);
      if (col) dropOn(current.card, col.dataset.col, col);
    };
    board.addEventListener('touchstart', (event) => {
      const card = event.target.closest && event.target.closest('.pipe-card[data-movable="true"]');
      if (!card || event.touches.length !== 1 || dragging) return;
      const touch = event.touches[0];
      const from = card.closest('.pipe-col').dataset.col;
      hold = {card, from, height: card.offsetHeight, startX: touch.clientX, startY: touch.clientY, x: touch.clientX, y: touch.clientY, active: false, col: null, raf: 0, scroller: scrollParent(board)};
      hold.timer = setTimeout(() => {
        if (!hold || hold.card !== card) return;
        const box = card.getBoundingClientRect();
        const ghost = card.cloneNode(true);
        ghost.classList.add('pipe-card-ghost'); ghost.removeAttribute('data-key'); ghost.removeAttribute('data-board-job');
        ghost.style.width = `${box.width}px`; ghost.style.height = `${box.height}px`;
        document.body.appendChild(ghost);
        Object.assign(hold, {active: true, ghost, offsetX: hold.x - box.left, offsetY: hold.y - box.top});
        dragging = {id: card.dataset.boardJob, from, height: hold.height, card};
        card.classList.add('dragging');
        board.classList.add('is-dragging');
        board.querySelectorAll('.pipe-col').forEach((col) => col.classList.toggle('can-drop', col.dataset.col !== from));
        document.documentElement.classList.add('job-os-touch-dragging');
        try { if (navigator.vibrate) navigator.vibrate(8); } catch (_) { /* not everywhere */ }
        follow();
        hold.raf = requestAnimationFrame(autoScroll);
      }, TOUCH_HOLD_MS);
    }, {passive: true});
    board.addEventListener('touchmove', (event) => {
      if (!hold) return;
      const touch = event.touches[0];
      hold.x = touch.clientX; hold.y = touch.clientY;
      if (!hold.active) {
        // Moved before the hold: a scroll, not a pick-up.
        if (Math.hypot(hold.x - hold.startX, hold.y - hold.startY) > TOUCH_SLOP) { clearTimeout(hold.timer); hold = null; }
        return;
      }
      if (event.cancelable) event.preventDefault();
      follow();
    }, {passive: false});
    board.addEventListener('touchend', () => finish(true));
    board.addEventListener('touchcancel', () => finish(false));
    // Long-press would otherwise open the iOS callout or select text.
    board.addEventListener('contextmenu', (event) => { if (hold && (hold.active || event.target.closest('.pipe-card'))) event.preventDefault(); });
  }
  const CLOSE_LABELS = {no_response: 'No response', withdrawn: 'Withdrawn', skipped: 'Not for me'};
  function pickClosed(col) {
    return new Promise((resolve) => {
      const menu = document.createElement('div');
      menu.className = 'pipe-drop-menu';
      menu.setAttribute('role', 'menu');
      menu.innerHTML = `<p>Close it as</p>${Object.entries(CLOSE_LABELS).map(([m, label]) => `<button type="button" role="menuitem" data-move="${m}">${label}</button>`).join('')}<button type="button" class="is-cancel" data-move="">Cancel</button>`;
      col.querySelector('.pipe-col-head').after(menu);
      const finish = (value) => { menu.remove(); document.removeEventListener('pointerdown', outside, true); resolve(value); };
      const outside = (event) => { if (!menu.contains(event.target)) finish(null); };
      menu.addEventListener('click', (event) => { const b = event.target.closest('[data-move]'); if (b) finish(b.dataset.move || null); });
      setTimeout(() => document.addEventListener('pointerdown', outside, true));
      menu.querySelector('button').focus();
    });
  }
  // The card lands in its new column at once; the server's answer follows.
  function landCard(card, col) {
    const list = col.querySelector('.pipe-col-cards');
    const from = card.closest('.pipe-col');
    if (!list || !from) return;
    list.querySelector('.pipe-empty')?.remove();
    list.prepend(card);
    const count = (el, d) => { const n = el.querySelector('.pipe-col-head .job-os-count'); if (n) n.textContent = String(Math.max(0, Number(n.textContent) + d)); };
    count(from, -1); count(col, 1);
    if (typeof window.markLanded === 'function') window.markLanded(card);
  }
  async function dropOn(card, column, col) {
    const id = card.dataset.boardJob;
    const revision = Number(card.dataset.revision);
    const sent = card.dataset.applied === 'true';
    let status = null;
    try {
      if (column === 'closed' && sent) {
        status = await pickClosed(col);
        if (!status) return;
      }
      if (column === 'applied' && !sent) {
        const ok = typeof window.showConfirmDialog === 'function'
          ? await window.showConfirmDialog({title: 'Mark as applied?', message: 'Record that you sent the application for this job.', confirmLabel: 'Mark applied', cancelLabel: 'Cancel'})
          : window.confirm('Mark as applied?');
        if (!ok) return;
      }
      landCard(card, col);
      await window.JobOSApi.moveJob(id, column, revision, status);
      if (column === 'applied' && !sent) toast('Application recorded');
      flash(id);
    } catch (error) { toast(error.message || 'Could not move the job'); }
    forget('automations', 'board');
    refresh();
  }
  // ---- Pipeline layout and the manual tracker ------------------------------------------
  const PREFS = 'hermes-job-os-pipeline';
  function savePrefs() {
    const state = window.JobOSState;
    try { localStorage.setItem(PREFS, JSON.stringify({source: state.pipelineSource, mode: state.pipelineMode, collapsed: state.collapsedColumns, filters: state.colFilters || {}})); } catch (_) { /* private window */ }
  }
  function loadPrefs() {
    const state = window.JobOSState;
    try {
      const saved = JSON.parse(localStorage.getItem(PREFS) || '{}');
      if (typeof saved.source === 'string' && /^[a-z]{1,20}$/.test(saved.source)) state.pipelineSource = saved.source;
      if (['board', 'list'].includes(saved.mode)) state.pipelineMode = saved.mode;
      if (saved.filters && typeof saved.filters === 'object') {
        const MIN = ['85', '75', '65', 'none'];
        const SORT = ['newest', 'oldest', 'best', 'updated'];
        state.colFilters = {};
        Object.entries(saved.filters).slice(0, 16).forEach(([col, f]) => {
          if (!/^[a-z_]{1,20}$/.test(col) || !f || typeof f !== 'object') return;
          const clean = {};
          if (typeof f.query === 'string' && f.query.trim()) clean.query = f.query.slice(0, 80);
          if (MIN.includes(f.min)) clean.min = f.min;
          if (SORT.includes(f.sort)) clean.sort = f.sort;
          if (Object.keys(clean).length) state.colFilters[col] = clean;
        });
      }
      if (Array.isArray(saved.collapsed)) state.collapsedColumns = saved.collapsed.filter((c) => typeof c === 'string' && /^[a-z]{1,20}$/.test(c)).slice(0, 12);
    } catch (_) { /* defaults */ }
  }
  const FORM_FIELDS = ['title', 'company', 'canonical_url', 'country', 'location', 'salary_text', 'employment_type', 'workplace', 'description'];
  const emptyJobForm = () => ({title: '', company: '', canonical_url: '', country: '', location: '', salary_text: '', employment_type: '', workplace: '', description: '', note: '', stage: 'saved'});
  async function trackerAction(name, el) {
    const state = window.JobOSState;
    // Site tabs and the layout switch redraw from what is loaded: no wait on the server.
    if (name === 'pipe-source') { state.pipelineSource = el.dataset.source; state.statusFilter = null; savePrefs(); replaceRoute('pipeline'); return repaint(); }
    if (name === 'pipe-mode') {
      state.pipelineMode = el.dataset.mode; state.statusFilter = null; savePrefs(); replaceRoute('pipeline');
      return state.pipelineMode === 'board' && !state.board ? refresh() : repaint();
    }
    // A column folds to a slim strip (and back); it still takes drops.
    if (name === 'pipe-collapse') {
      const set = new Set(state.collapsedColumns || []);
      if (set.has(el.dataset.col)) set.delete(el.dataset.col); else set.add(el.dataset.col);
      state.collapsedColumns = [...set]; savePrefs();
      return repaint();
    }
    if (name === 'pipe-col-filter') {
      const closing = state.colFilterOpen === el.dataset.col;
      const panel = closing ? document.querySelector(`.pipe-col[data-col="${CSS.escape(el.dataset.col)}"] .pipe-col-filter`) : null;
      if (panel && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
        // Fold away first, then redraw without it.
        panel.classList.add('is-leaving');
        const col = el.dataset.col;
        setTimeout(() => { if (state.colFilterOpen === col) { state.colFilterOpen = null; repaint(); } }, 180);
        return undefined;
      }
      state.colFilterOpen = closing ? null : el.dataset.col;
      repaint();
      const opened = state.colFilterOpen && document.querySelector(`.pipe-col[data-col="${CSS.escape(state.colFilterOpen)}"] .pipe-col-filter`);
      if (opened && !matchMedia('(prefers-reduced-motion: reduce)').matches && typeof opened.animate === 'function') {
        // Explicit animation: a keyframe rule on the freshly inserted node was lost to the focus and
        // viewport work that follows a tap on iOS.
        opened.animate([
          {opacity: 0, transform: 'translateY(-6px)', maxHeight: '0px', paddingTop: '0px', paddingBottom: '0px'},
          {opacity: 1, transform: 'none', maxHeight: '160px', paddingTop: '2px', paddingBottom: '4px'},
        ], {duration: 260, easing: 'cubic-bezier(.22,1,.36,1)'});
      }
      // A finger gets the filter without a keyboard flying up over it; a keyboard user lands in the box.
      if (opened && matchMedia('(hover: hover)').matches) opened.querySelector('[data-col-filter="query"]')?.focus({preventScroll: true});
      return undefined;
    }
    if (name === 'pipe-col-filter-clear') { if (state.colFilters) delete state.colFilters[el.dataset.col]; savePrefs(); repaint(); return undefined; }
    if (name === 'pipe-search-clear') { state.pipelineQuery = ''; repaint(); document.getElementById('job-os-pipe-search')?.focus(); return undefined; }
    if (name === 'job-form-new') { state.jobForm = Object.assign(emptyJobForm(), window.JobOSState.importDraft || {}); state.jobFormError = ''; return refresh(); }
    if (name === 'job-form-edit') {
      const id = el.dataset.jobId;
      const job = state.jobDetail && state.jobDetail.id === id ? state.jobDetail : (await window.JobOSApi.job(id).catch(() => null) || {}).job;
      if (!job) return undefined;
      state.jobForm = Object.assign(emptyJobForm(), Object.fromEntries(FORM_FIELDS.map((f) => [f, job[f] || ''])), {id: job.id, revision: job.revision});
      state.jobFormError = '';
      return refresh();
    }
    if (name === 'job-form-close') { state.jobForm = null; state.jobFormError = ''; paintNow(); return refresh(); }
    return undefined;
  }
  function readJobForm(form) {
    const data = new FormData(form);
    const out = {};
    FORM_FIELDS.concat(['note', 'stage']).forEach((f) => { if (data.has(f)) out[f] = String(data.get(f) || '').trim(); });
    return out;
  }
  async function saveJobForm(form) {
    const state = window.JobOSState;
    const values = readJobForm(form);
    const editing = state.jobForm && state.jobForm.id;
    const error = form.querySelector('.job-os-error');
    const submit = form.querySelector('button[type="submit"]');
    if (!values.title || (!editing && !values.canonical_url)) {
      error.textContent = 'A job title and its link are required.';
      if (window.Micro) {
        if (!values.title) window.Micro.invalid(form.querySelector('input[name="title"]'));
        if (!editing && !values.canonical_url) window.Micro.invalid(form.querySelector('input[name="canonical_url"]'));
      }
      return;
    }
    if (submit) submit.disabled = true;
    try {
      let id;
      if (editing) {
        const changes = {};
        FORM_FIELDS.filter((f) => f !== 'canonical_url').forEach((f) => { changes[f] = values[f] || ''; });
        await window.JobOSApi.editJob(state.jobForm.id, changes, state.jobForm.revision);
        id = state.jobForm.id;
      } else {
        const payload = {};
        FORM_FIELDS.forEach((f) => { if (values[f]) payload[f] = values[f]; });
        const created = await window.JobOSApi.create(payload);
        id = created.job.id;
        if (values.note) await window.JobOSApi.addNote(id, values.note);
        if (values.stage === 'applied') await window.JobOSApi.markApplied(id, values.note || '');
        state.importDraft = emptyDraft();
        if (state.activeView !== 'pipeline' || state.pipelineSource === 'indeed') state.pipelineSource = 'all';
        state.activeView = 'pipeline'; state.statusFilter = null; replaceRoute('pipeline');
      }
      state.jobForm = null; state.jobFormError = '';
      flash(id);
      if (typeof window.showToast === 'function') window.showToast(editing ? 'Job updated' : 'Job saved to your pipeline');
      refresh();
    } catch (err) {
      state.jobForm = Object.assign({}, state.jobForm, values);
      error.textContent = err.message || 'Unable to save this job.';
      if (submit) submit.disabled = false;
    }
  }
  function bindJobForms(target) {
    const form = target.querySelector('#job-os-job-form');
    if (once(form, 'job-form')) {
      form.addEventListener('submit', (event) => { event.preventDefault(); saveJobForm(form); });
      form.addEventListener('input', () => { window.JobOSState.jobForm = Object.assign({}, window.JobOSState.jobForm, readJobForm(form)); });
      const first = form.querySelector('input[name="title"]');
      if (first && !first.value) first.focus();
    }
    const note = target.querySelector('#job-os-note-form');
    if (once(note, 'note')) note.addEventListener('submit', async (event) => {
      event.preventDefault();
      const text = note.elements.text.value.trim();
      const job = window.JobOSState.jobDetail;
      if (!text || !job) return;
      note.querySelector('button').disabled = true;
      try { await window.JobOSApi.addNote(job.id, text); }
      catch (err) { if (typeof window.showToast === 'function') window.showToast(err.message || 'Could not save the note'); }
      refresh();
    });
  }
  // ---- Scout -----------------------------------------------------------------
  const ACTIVE = ['queued', 'searching', 'scraping'];
  let pollTimer = null;
  const seenFinds = new Set();
  function stopScoutPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }
  function afterScoutRender(target, changed) {
    // New finds glow in once; the radar keeps running while any run is active.
    target.querySelectorAll('.scout-finds [data-job-id]').forEach((card) => {
      if (!seenFinds.has(card.dataset.jobId)) { seenFinds.add(card.dataset.jobId); if (typeof window.markArrival === 'function') window.markArrival(card); }
    });
    const form = document.getElementById('job-os-search-form');
    if (changed && once(form, 'search-form')) {
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
    // A new search starts in the country of the last one made.
    const last = (window.JobOSState.searches || []).slice(-1)[0];
    return search ? {id: search.id, revision: search.revision, name: search.name === String(search.keywords || '').slice(0, 80) ? '' : search.name, keywords: search.keywords, country: search.country, sites: search.sites,
      locations: (search.locations || []).join(', '), posted_within_days: search.posted_within_days, remote_only: search.remote_only,
      title_filter: (search.title_filter || []).join(', '), related_titles: (search.related_titles || []).join(', '), strict_titles: search.strict_titles !== false}
      : {name: '', keywords: '', country: last ? last.country : '', sites: last ? last.sites : ['indeed'], locations: '', posted_within_days: 0, remote_only: false, title_filter: '',
        related_titles: '', strict_titles: true};
  }
  function searchPayload(form) {
    const data = new FormData(form);
    return {name: data.get('name') || '', keywords: data.get('keywords') || '', country: data.get('country') || '',
      locations: data.get('locations') || '', posted_within_days: Number(data.get('posted_within_days') || 0),
      sites: data.getAll('sites'), title_filter: data.get('title_filter') || '',
      related_titles: data.get('related_titles') || '', strict_titles: data.get('strict_titles') === 'on',
      remote_only: data.get('remote_only') === 'on'};
  }
  async function saveSearchForm(form) {
    const state = window.JobOSState;
    const payload = searchPayload(form);
    // New job titles get fresh related titles unless those were edited as well.
    const saved = state.searchForm && state.searchForm.id && (state.searches || []).find((x) => x.id === state.searchForm.id);
    if (saved && payload.keywords.trim() !== saved.keywords && payload.related_titles === (saved.related_titles || []).join(', ')) payload.related_titles = '';
    const submit = form.querySelector('button[type="submit"]');
    if (submit) submit.disabled = true;
    try {
      if (state.searchForm && state.searchForm.id) await window.JobOSApi.updateSearch(state.searchForm.id, payload, state.searchForm.revision);
      else await window.JobOSApi.createSearch(payload);
      state.searchForm = null; state.searchError = '';
      refresh();
    } catch (error) {
      state.searchError = error.message || 'Unable to save this search.';
      if (window.Micro) window.Micro.shake(form.querySelector('.job-os-actions') || form);
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
    else if (name === 'scout-form-close') { state.searchForm = null; state.searchError = ''; paintNow(); refresh(); }
    else if (name === 'scout-run') {
      pending(el, 'Starting…');
      try { await window.JobOSApi.runSearch(searchId, `${searchId}:${Date.now()}`); if (window.Micro) window.Micro.restore(el); }
      catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not start Scout'); finished(el, false); }
      refresh();
    } else if (name === 'scout-cancel') {
      el.disabled = true; el.textContent = 'Cancelling…';
      try { await window.JobOSApi.cancelRun(el.dataset.runId); } catch (_) { /* the next poll shows the real state */ }
    } else if (name === 'scout-delete') {
      // A search is small to lose and easy to make again: confirm in place (micro.js),
      // with the dialog as the fallback. Jobs it found stay in the Pipeline either way.
      if (window.Micro) { if (!window.Micro.arm(el, 'Delete search?')) return; }
      else if (!window.confirm('Delete this search? Jobs it already found stay in your Pipeline.')) return;
      const card = document.querySelector(`.scout-search[data-search-id="${CSS.escape(searchId)}"]`);
      try {
        await window.JobOSApi.deleteSearch(searchId);
        state.searches = (state.searches || []).filter((s) => s.id !== searchId);
        await closeGap(card);
      } catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not delete the search'); }
      refresh();
    } else if (name === 'scout-toggle') {
      if (!search) return;
      forget('automations');
      try { await window.JobOSApi.updateSearch(searchId, {enabled: el.checked}, search.revision); }
      catch (error) { if (typeof window.showToast === 'function') window.showToast(error.message || 'Could not update the search'); }
      refresh();
    } else if (name === 'scout-tidy') {
      el.disabled = true;
      try {
        const r = await window.JobOSApi.tidySearch(searchId);
        toast(r.skipped ? `Moved ${r.skipped} off-target find${r.skipped === 1 ? '' : 's'} to Closed` : 'Nothing to tidy');
      } catch (error) { toast(error.message || 'Could not tidy the search'); }
      refresh();
    } else if (name === 'scout-suggest') {
      const form = document.getElementById('job-os-search-form');
      if (!form) return;
      const keywords = form.elements.keywords.value.trim();
      if (!keywords) { toast('Type the job titles first'); return; }
      el.disabled = true; el.classList.add('is-busy');
      try {
        const r = await window.JobOSApi.suggestTitles(state.searchForm && state.searchForm.id, keywords);
        const field = form.elements.related_titles;
        const have = field.value.split(',').map((t) => t.trim()).filter(Boolean);
        const merged = [...have, ...r.titles.filter((t) => !have.some((h) => h.toLowerCase() === t.toLowerCase()))].slice(0, 15);
        field.value = merged.join(', ');
        state.searchForm = Object.assign({}, state.searchForm, searchPayload(form));
      } catch (error) { toast(error.message || 'Luna could not suggest titles'); }
      el.disabled = false; el.classList.remove('is-busy');
    } else if (name === 'job-close') { state.selectedJobId = null; state.jobDetail = null; paintNow(); refresh(); }
  }
  function mount() { loadPrefs(); applyRoute(); refresh(); }
  function unmount() { if (aborter) aborter.abort(); aborter = null; stopScoutPolling(); if (analysisTimer) { clearInterval(analysisTimer); analysisTimer = null; } if (dashboardTimer) { clearInterval(dashboardTimer); dashboardTimer = null; } }
  // The job opens over the page it was tapped on (Dashboard, Scout or Pipeline)
  // at once, from what the list already knows; the full record fills in after
  // the drawer has finished sliding in.
  function openJob(jobId) {
    const state = window.JobOSState;
    const keep = ['dashboard', 'scout', 'pipeline'].includes(state.activeView);
    if (!keep) { state.activeView = 'pipeline'; state.statusFilter = null; }
    const known = (state.jobs || []).find((job) => job.id === jobId)
      || ((state.matches && state.matches.released) || []).find((job) => job.id === jobId);
    if (!state.jobDetail || state.jobDetail.id !== jobId) state.jobTimeline = [];
    state.selectedJobId = jobId;
    if (known && !(state.jobDetail && state.jobDetail.id === jobId)) state.jobDetail = Object.assign({}, known);
    state.drawerUntil = state.jobDetail && !document.getElementById('job-os-detail') ? Date.now() + 300 : 0;
    replaceRoute(state.activeView, state.activeView === 'pipeline' ? state.statusFilter : undefined);
    refresh();
  }
  function resetDraft() { window.JobOSState.importDraft = emptyDraft(); window.JobOSState.jobForm = null; }
  window.JobOS = {mount, refresh, unmount, openJob, resetDraft};
}());
