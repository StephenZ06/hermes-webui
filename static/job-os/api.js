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
  };
}());
