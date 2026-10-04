(function () {
  window.JobOSState = {
    capability: null,
    dashboard: null,
    jobs: [],
    activeView: 'dashboard',
    statusFilter: null,
    selectedJobId: null,
    // Unsaved Import-form text: every refresh rebuilds the page, so the form
    // renders from here rather than losing what was typed.
    importDraft: {title: '', canonical_url: '', company: ''},
  };
}());
