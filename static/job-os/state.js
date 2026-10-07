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
    searchForm: null, // null = closed; {id?, name, keywords, country, locations, posted_within_days, remote_only}
    countries: [], // Indeed country sites: [{code, name, host}]
    postedWithin: [0, 1, 3, 7, 14],
    searchError: '',
    jobDetail: null,
    sortBy: 'newest', // Pipeline list: 'newest' | 'fit'
    pipelineSource: 'all', // 'all' | 'indeed' | 'manual'
    pipelineMode: 'board', // 'board' | 'list'
    jobForm: null, // the Add/Edit job drawer: null = closed
    jobFormError: '',
    jobTimeline: [],
    studioMatchId: null, // Resume Studio match check: the job picked
    studioMatch: null,
    resume: null,
    resumeError: '',
    resumeReplacing: false,
    // Resume Studio tailored versions: the list, the open job, its documents, the tab, unsaved edits.
    tailored: [],
    studioJobId: null,
    studioDocs: null,
    studioTab: 'resume',
    studioDraft: null,
    board: null,
    gmailEditing: false,
    apifyEditing: false,
    apifyMessage: null,
    matches: null, // Scout inbox: {waiting, released, release_count, ...}
    apify: null,
    sites: null, // job sites Scout offers: [{key, name, needs_apify, actors}] // {active}: Scout runs on Apify, so Firecrawl is not needed
    gmailMessage: null,
    recentPage: 0, // Dashboard recent jobs, ten a page
    findsPage: 0, // Scout latest finds, ten a page
    resumeOriginal: null, // 'pdf' | 'docx' | ... when the master was uploaded as a file
    resumePreview: null, // full-size preview overlay: {kind: 'pdf'|'html', url, title}
    resumeThumb: null, // {revision, url}: the master's first page, drawn once
    settingsFocus: '', // a Settings section to scroll to after opening Settings
    matchDirection: null, // which way the match check last stepped, for its slide
  };
}());
