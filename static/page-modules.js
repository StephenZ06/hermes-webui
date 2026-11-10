/* Page scripts that load the first time their page opens, not on every visit
   (docs/superpowers/plans/2026-11-10-load-page-scripts-on-demand.md).

   loadPageModule(name) injects a page's scripts once, in order, and resolves
   when the last one has run; each script still publishes its own window.X
   object (JobOS, Notebook, HermesDashboard, ...) exactly as before. The small
   API/state files other pages also use (job-os/state.js, job-os/api.js,
   notebook/api.js) stay in index.html. */
(function () {
  'use strict';
  var PAGE_MODULES = {
    jobs: ['static/job-os/render.js', 'static/job-os/index.js'],
    notebook: ['static/notebook/index.js'],
    dashboard: ['static/dashboard/sprite.js', 'static/dashboard/index.js'],
    notes: ['static/work-hub.js', 'static/goal-planner.js'],
    files: ['static/file-manager.js']
  };
  var pending = {};

  // The server substitutes the build token already URL-encoded, the same
  // string index.html and sw.js use, so it is appended as it is.
  function version() {
    var v = window.__HERMES_WEBUI_BUNDLE_VERSION__;
    return v && v.indexOf('__') !== 0 ? '?v=' + v : '';
  }

  function alreadyOnPage(path) {
    var scripts = document.scripts;
    for (var i = 0; i < scripts.length; i++) {
      var src = scripts[i].getAttribute('src') || '';
      if (src.split('?')[0].replace(/^\.?\//, '') === path) return true;
    }
    return false;
  }

  function addScript(path) {
    if (alreadyOnPage(path)) return Promise.resolve();
    return new Promise(function (resolve, reject) {
      var el = document.createElement('script');
      el.src = new URL(path + version(), document.baseURI).href;
      el.async = false;
      el.onload = function () { resolve(); };
      el.onerror = function () { el.remove(); reject(new Error('could not load ' + path)); };
      document.head.appendChild(el);
    });
  }

  window.PAGE_MODULES = PAGE_MODULES;
  window.loadPageModule = function (name) {
    var files = Object.prototype.hasOwnProperty.call(PAGE_MODULES, name) ? PAGE_MODULES[name] : null;
    if (!files) return Promise.reject(new Error('unknown page module: ' + name));
    if (!pending[name]) {
      pending[name] = files.reduce(function (chain, path) {
        return chain.then(function () { return addScript(path); });
      }, Promise.resolve()).catch(function (error) {
        delete pending[name]; // the next visit tries again
        throw error;
      });
    }
    return pending[name];
  };

  // For features outside a page that need its code: opening a note from chat,
  // the workspace panel or the Dashboard, and the workspace panel's Work Hub list.
  window.withNotebook = function (fn) {
    return window.loadPageModule('notebook').then(function () { return fn(window.Notebook); });
  };
  window.withWorkHub = function (fn) {
    return window.loadPageModule('notes').then(function () { return fn(window); });
  };

  // The "career" buttons (index.html, Jobs' Manage Skills) call this before the
  // Dashboard may have loaded; dashboard/index.js replaces it with the real one.
  // Like the real one it switches at once (switchPanel loads the page's code)
  // and then selects the Career tab.
  function openCareerDashboardStub() {
    var switching = typeof window.switchPanel === 'function' ? window.switchPanel('dashboard') : null;
    return Promise.resolve(switching).then(function () { return window.loadPageModule('dashboard'); }).then(function () {
      if (window.HermesDashboard) window.HermesDashboard.select('career');
    });
  }
  if (typeof window.openCareerDashboard !== 'function') window.openCareerDashboard = openCareerDashboardStub;

  // Start the landing page's scripts as soon as the app's own scripts have run,
  // instead of after boot reaches restorePanelFromRoute(). Mirrors its rules:
  // the hash, then this tab's remembered page, then the server's start page
  // for a fresh launch. A wrong guess only loads a page early.
  var PANEL_MODULE = { jobs: 'jobs', notebook: 'notebook', dashboard: 'dashboard', notes: 'notes', files: 'files' };
  function landingPanel() {
    var hash = /^#([a-z-]+)/.exec(window.location.hash || '');
    if (hash) return hash[1];
    var saved = '';
    try { saved = sessionStorage.getItem('hermes-webui-panel-route') || ''; } catch (_) {}
    var remembered = /^#([a-z-]+)/.exec(saved);
    if (remembered) return remembered[1];
    if (saved || !document.body || document.body.dataset.startPage !== 'dashboard') return '';
    if (/\/session\//.test(window.location.pathname) || /[?&]action=/.test(window.location.search)) return '';
    return 'dashboard';
  }
  function preloadLanding() {
    var name = PANEL_MODULE[landingPanel()];
    if (name) window.loadPageModule(name).catch(function () {});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', preloadLanding, { once: true });
  else preloadLanding();

  // The Dashboard (the start page) fetches its data in the browser's quiet
  // time so its first open needs no loader. Its code now loads in that same
  // quiet time, after start-up, instead of with the app.
  function preloadDashboardWhenIdle() {
    var go = function () { window.loadPageModule('dashboard').catch(function () {}); };
    setTimeout(function () {
      if (typeof window.requestIdleCallback === 'function') window.requestIdleCallback(go, { timeout: 4000 });
      else go();
    }, 2500);
  }
  if (document.readyState === 'complete') preloadDashboardWhenIdle();
  else window.addEventListener('load', preloadDashboardWhenIdle, { once: true });
}());
