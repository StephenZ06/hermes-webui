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
}());
