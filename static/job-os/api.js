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
    saveSettings: (settings, expectedRevision) => request('/api/job-os/settings', {method: 'POST', body: JSON.stringify({settings, expected_revision: expectedRevision})}),
    firecrawlHealth: () => request('/api/job-os/firecrawl/health'),
    connectGmail: (address, appPassword) => request('/api/job-os/gmail', {method: 'POST', body: JSON.stringify({address, app_password: appPassword})}),
    disconnectGmail: () => request('/api/job-os/gmail/disconnect', {method: 'POST', body: '{}'}),
    testGmail: (to, context) => request('/api/job-os/gmail/test', {method: 'POST', body: JSON.stringify({to: to || '', context: context || 'jobs'})}),
  };
}());
