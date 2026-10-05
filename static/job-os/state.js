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
    // Firecrawl health shown in every page header; refreshed with the page.
    firecrawl: null,
    // Settings as saved, plus the unsaved edits being made to them.
    settings: null,
    settingsStatus: null,
    settingsDraft: null,
    settingsDirty: false,
    settingsError: '',
    settingsSavedAt: 0,
  };
}());
