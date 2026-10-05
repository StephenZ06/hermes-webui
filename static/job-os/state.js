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
    // Gmail form: whether the connected account is being replaced, and the
    // last result line. Credentials themselves are never stored here.
    // Scout: saved searches, recent runs, the open search form, the job detail.
    searches: [],
    searchProvider: '',
    schedule: null,
    runs: [],
    searchForm: null, // null = closed; {id?, name, keywords, locations, sites, remote_only}
    searchError: '',
    jobDetail: null,
    sortBy: 'newest', // Pipeline: 'newest' | 'fit'
    resume: null,
    resumeError: '',
    resumeReplacing: false,
    // Resume Studio tailored versions: the list, the open job, its documents, the tab, unsaved edits.
    tailored: [],
    studioJobId: null,
    studioDocs: null,
    studioTab: 'resume',
    studioDraft: null,
    gmailEditing: false,
    gmailMessage: null,
  };
}());
