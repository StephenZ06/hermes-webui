(function () {
  // A read that fails because the server is restarting (agent updates restart
  // it hourly) or the network blinked is tried again before the page gives up.
  const RETRY_DELAYS = [350, 900, 1800];
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function request(path, options) {
    const init = Object.assign({headers: {'Content-Type': 'application/json'}}, options || {});
    const safeToRepeat = !init.method || String(init.method).toUpperCase() === 'GET';
    for (let attempt = 0; ; attempt += 1) {
      const retry = safeToRepeat && attempt < RETRY_DELAYS.length;
      let response;
      try {
        response = await fetch(path, init);
      } catch (error) {
        if (retry) { await sleep(RETRY_DELAYS[attempt]); continue; }
        throw new Error('Job OS could not reach Hermes. Check your connection and try again.');
      }
      const payload = await response.json().catch(() => null);
      if (response.ok && payload) return payload;
      if (retry && (response.status >= 500 || response.ok)) { await sleep(RETRY_DELAYS[attempt]); continue; }
      if (payload && payload.error) throw new Error(payload.error);
      throw new Error(response.status >= 500
        ? 'Hermes is restarting. Try again in a moment.'
        : 'Job OS request failed (' + response.status + ')');
    }
  }
  window.JobOSApi = {
    capability: () => request('/api/job-os/capability'),
    dashboard: () => request('/api/job-os/dashboard'),
    jobs: (status) => request('/api/job-os/jobs' + (status ? '?status=' + encodeURIComponent(status) : '')),
    create: (job) => request('/api/job-os/jobs', {method: 'POST', body: JSON.stringify(job)}),
    settings: () => request('/api/job-os/settings'),
    job: (id) => request('/api/job-os/jobs/' + encodeURIComponent(id)),
    setStatus: (id, status, expectedRevision) => request('/api/job-os/jobs/' + encodeURIComponent(id), {method: 'PATCH', body: JSON.stringify({status, expected_revision: expectedRevision})}),
    analyzeJob: (id, force) => request('/api/job-os/jobs/' + encodeURIComponent(id) + '/analyze', {method: 'POST', body: JSON.stringify({force: !!force})}),
    analyzeNew: () => request('/api/job-os/analyze', {method: 'POST', body: JSON.stringify({scope: 'new'})}),
    fetchDetails: (id) => request('/api/job-os/jobs/' + encodeURIComponent(id) + '/details', {method: 'POST', body: '{}'}),
    resume: () => request('/api/job-os/resume'),
    // Skills gained, kept by the Dashboard (Career); tailoring may add matching ones.
    skillsGained: () => request('/api/dashboard/skills'),
    notifications: () => request('/api/job-os/notifications'),
    sendDigest: () => request('/api/job-os/notifications/digest', {method: 'POST', body: '{}'}),
    checkReplies: () => request('/api/job-os/notifications/check', {method: 'POST', body: '{}'}),
    checkOutcomes: () => request('/api/job-os/notifications/outcomes', {method: 'POST', body: '{}'}),
    checkSites: () => request('/api/job-os/site-health/check', {method: 'POST', body: '{}'}),
    moveJob: (id, column, expectedRevision, status) => request('/api/job-os/jobs/' + encodeURIComponent(id) + '/move', {method: 'POST', body: JSON.stringify({column, expected_revision: expectedRevision, status: status || null})}),
    board: (source) => request('/api/job-os/applications' + (source && source !== 'all' ? '?source=' + encodeURIComponent(source) : '')),
    editJob: (id, job, expectedRevision) => request('/api/job-os/jobs/' + encodeURIComponent(id) + '/edit', {method: 'POST', body: JSON.stringify({job, expected_revision: expectedRevision})}),
    automations: () => request('/api/job-os/automations'),
    automate: (jobIds) => request('/api/job-os/automate', {method: 'POST', body: JSON.stringify({job_ids: jobIds})}),
    applyKit: (id) => request('/api/job-os/jobs/' + encodeURIComponent(id) + '/apply-kit', {method: 'POST', body: '{}'}),
    interviewPrep: (id) => request('/api/job-os/jobs/' + encodeURIComponent(id) + '/interview-prep', {method: 'POST', body: '{}'}),
    markApplied: (id, note) => request('/api/job-os/jobs/' + encodeURIComponent(id) + '/applied', {method: 'POST', body: JSON.stringify({note: note || ''})}),
    overrideCheck: (id, check, on) => request('/api/job-os/jobs/' + encodeURIComponent(id) + '/override', {method: 'POST', body: JSON.stringify({check, on: !!on})}),
    addNote: (id, text) => request('/api/job-os/jobs/' + encodeURIComponent(id) + '/note', {method: 'POST', body: JSON.stringify({text})}),
    timeline: (id) => request('/api/job-os/jobs/' + encodeURIComponent(id) + '/timeline'),
    tailor: (id) => request('/api/job-os/jobs/' + encodeURIComponent(id) + '/tailor', {method: 'POST', body: '{}'}),
    markReady: (id) => request('/api/job-os/jobs/' + encodeURIComponent(id) + '/ready', {method: 'POST', body: '{}'}),
    jobDocuments: (id) => request('/api/job-os/jobs/' + encodeURIComponent(id) + '/documents'),
    documents: () => request('/api/job-os/documents'),
    rescoreDocument: (id) => request('/api/job-os/documents/' + encodeURIComponent(id) + '/score', {method: 'POST', body: '{}'}),
    saveDocument: (id, content, expectedRevision) => request('/api/job-os/documents/' + encodeURIComponent(id), {method: 'POST', body: JSON.stringify({content, expected_revision: expectedRevision})}),
    uploadResume: (filename, contentBase64) => request('/api/job-os/resume', {method: 'POST', body: JSON.stringify({filename, content_base64: contentBase64})}),
    pasteResume: (text) => request('/api/job-os/resume', {method: 'POST', body: JSON.stringify({filename: 'pasted.txt', text})}),
    searches: () => request('/api/job-os/searches'),
    createSearch: (search) => request('/api/job-os/searches', {method: 'POST', body: JSON.stringify({search})}),
    updateSearch: (id, search, expectedRevision) => request('/api/job-os/searches/' + encodeURIComponent(id), {method: 'POST', body: JSON.stringify({search, expected_revision: expectedRevision})}),
    deleteSearch: (id) => request('/api/job-os/searches/' + encodeURIComponent(id) + '/delete', {method: 'POST', body: '{}'}),
    tidySearch: (id) => request('/api/job-os/searches/' + encodeURIComponent(id) + '/tidy', {method: 'POST', body: '{}'}),
    suggestTitles: (id, keywords) => request('/api/job-os/searches/' + encodeURIComponent(id || 'new') + '/suggest', {method: 'POST', body: JSON.stringify({keywords})}),
    runSearch: (id, key) => request('/api/job-os/searches/' + encodeURIComponent(id) + '/run', {method: 'POST', body: JSON.stringify({idempotency_key: key})}),
    runs: (limit) => request('/api/job-os/runs?limit=' + (limit || 20)),
    cancelRun: (id) => request('/api/job-os/runs/' + encodeURIComponent(id) + '/cancel', {method: 'POST', body: '{}'}),
    saveSettings: (settings, expectedRevision) => request('/api/job-os/settings', {method: 'POST', body: JSON.stringify({settings, expected_revision: expectedRevision})}),
    firecrawlHealth: () => request('/api/job-os/firecrawl/health'),
    connectGmail: (address, appPassword) => request('/api/job-os/gmail', {method: 'POST', body: JSON.stringify({address, app_password: appPassword})}),
    disconnectGmail: () => request('/api/job-os/gmail/disconnect', {method: 'POST', body: '{}'}),
    matches: () => request('/api/job-os/matches'),
    apifyUsage: () => request('/api/job-os/apify/usage'),
    matchesSeen: () => request('/api/job-os/matches/seen', {method: 'POST', body: '{}'}),
    connectApify: (token) => request('/api/job-os/apify', {method: 'POST', body: JSON.stringify({token})}),
    disconnectApify: () => request('/api/job-os/apify/disconnect', {method: 'POST', body: '{}'}),
    testApify: () => request('/api/job-os/apify/test', {method: 'POST', body: '{}'}),
    testGmail: (to, context) => request('/api/job-os/gmail/test', {method: 'POST', body: JSON.stringify({to: to || '', context: context || 'jobs'})}),
  };
}());
