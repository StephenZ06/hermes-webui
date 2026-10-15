// scroll-fade.js — a strip that scrolls sideways fades out at the edge that has
// more beyond it, so a half-cut label reads as "keeps going" instead of a
// clipped mistake. The fade eases in and out with the scroll position itself
// (full strength 28px from an edge, none at it), so it moves with the finger.
(function () {
  'use strict';
  var FADE = 28;
  var SELECTOR = [
    '[data-scroll-fade]',
    '.pipe-toolbar > .seg:first-child',
    '.office-tasks-filters',
    '.topbar-chips',
    '.settings-nav',
    '.kanban-stats-grid',
    '.composer-left'
  ].join(',');
  var attached = new WeakSet();

  function update(el) {
    var max = el.scrollWidth - el.clientWidth;
    if (max <= 1) {
      if (el.getAttribute('data-scroll-fading') !== null) {
        el.removeAttribute('data-scroll-fading');
        el.style.removeProperty('--fade-l');
        el.style.removeProperty('--fade-r');
      }
      return;
    }
    var left = Math.max(0, Math.min(FADE, el.scrollLeft));
    var right = Math.max(0, Math.min(FADE, max - el.scrollLeft));
    if (el.getAttribute('data-scroll-fading') === null) el.setAttribute('data-scroll-fading', '');
    el.style.setProperty('--fade-l', left.toFixed(1) + 'px');
    el.style.setProperty('--fade-r', right.toFixed(1) + 'px');
  }

  function attach(el) {
    if (!attached.has(el)) {
      attached.add(el);
      el.addEventListener('scroll', function () { update(el); }, { passive: true });
      if (typeof ResizeObserver === 'function') new ResizeObserver(function () { update(el); }).observe(el);
    }
    update(el);
  }

  // Re-measure a page region after it was redrawn (a patch can drop the
  // attribute and inline style this script set).
  function scan(root) {
    var scope = root && root.querySelectorAll ? root : document;
    if (scope.matches && scope.matches(SELECTOR)) attach(scope);
    scope.querySelectorAll(SELECTOR).forEach(attach);
  }

  // Streaming chat rewrites the page constantly: look for new strips at most
  // twice a second rather than on every mutation.
  var pending = 0;
  function scanSoon() {
    if (pending) return;
    pending = setTimeout(function () { pending = 0; scan(document); }, 400);
  }

  window.ScrollFade = { scan: scan, update: update };
  if (typeof MutationObserver === 'function') {
    var start = function () {
      scan(document);
      new MutationObserver(scanSoon).observe(document.body, { childList: true, subtree: true });
    };
    if (document.body) start(); else document.addEventListener('DOMContentLoaded', start);
  }
}());
