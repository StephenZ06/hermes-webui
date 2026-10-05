(function () {
  async function request(path, options) {
    const response = await fetch(path, Object.assign({headers: {'Content-Type': 'application/json'}}, options || {}));
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || 'Job OS request failed');
    return payload;
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
    uploadResume: (filename, contentBase64) => request('/api/job-os/resume', {method: 'POST', body: JSON.stringify({filename, content_base64: contentBase64})}),
    pasteResume: (text) => request('/api/job-os/resume', {method: 'POST', body: JSON.stringify({filename: 'pasted.txt', text})}),
    searches: () => request('/api/job-os/searches'),
    createSearch: (search) => request('/api/job-os/searches', {method: 'POST', body: JSON.stringify({search})}),
    updateSearch: (id, search, expectedRevision) => request('/api/job-os/searches/' + encodeURIComponent(id), {method: 'POST', body: JSON.stringify({search, expected_revision: expectedRevision})}),
    deleteSearch: (id) => request('/api/job-os/searches/' + encodeURIComponent(id) + '/delete', {method: 'POST', body: '{}'}),
    runSearch: (id, key) => request('/api/job-os/searches/' + encodeURIComponent(id) + '/run', {method: 'POST', body: JSON.stringify({idempotency_key: key})}),
    runs: (limit) => request('/api/job-os/runs?limit=' + (limit || 20)),
    cancelRun: (id) => request('/api/job-os/runs/' + encodeURIComponent(id) + '/cancel', {method: 'POST', body: '{}'}),
    saveSettings: (settings, expectedRevision) => request('/api/job-os/settings', {method: 'POST', body: JSON.stringify({settings, expected_revision: expectedRevision})}),
    firecrawlHealth: () => request('/api/job-os/firecrawl/health'),
    connectGmail: (address, appPassword) => request('/api/job-os/gmail', {method: 'POST', body: JSON.stringify({address, app_password: appPassword})}),
    disconnectGmail: () => request('/api/job-os/gmail/disconnect', {method: 'POST', body: '{}'}),
    testGmail: (to, context) => request('/api/job-os/gmail/test', {method: 'POST', body: JSON.stringify({to: to || '', context: context || 'jobs'})}),
  };
}());
