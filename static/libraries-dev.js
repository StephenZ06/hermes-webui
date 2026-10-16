/* On-demand loader for the vendored Libraries.dev effects (see
   static/vendor/libraries-dev/README.md). The React runtime and effects are
   fetched the first time a page asks for them, never on boot. */
(function () {
  'use strict';
  var BASE = 'static/vendor/libraries-dev/bfcb863/';
  var pending = null;
  window.loadLibrariesDev = function () {
    if (!pending) {
      pending = import(new URL(BASE + 'libraries-dev.js', document.baseURI).href).catch(function (error) {
        pending = null;
        throw error;
      });
    }
    return pending;
  };
  window.loadLibrariesDevImage = function () {
    return window.loadLibrariesDev().then(function () {
      return import(new URL(BASE + 'img-fx.js', document.baseURI).href);
    });
  };
}());
