// scroll-fade.js — a strip that scrolls sideways fades its *text* out at the
// edge that has more beyond it, so a half-cut label reads as "keeps going"
// instead of a clipped mistake. Only the lettering fades; buttons, pills and
// borders stay solid. The fade eases with the scroll position itself (full
// strength 28px from an edge, none at it), so it moves with the finger.
(function () {
  'use strict';
  var FADE = 28;
  var SELECTOR = [
    '[data-scroll-fade]',
    '.pipe-toolbar > .seg:first-child',
    '.office-tasks-filters',
    '.topbar-chips',
    '.settings-nav'
  ].join(',');
  var attached = new WeakSet();
  var raf = new WeakMap();

  // Lettering sits in its own span so a mask can reach it without touching the
  // button around it.
  function wrapText(strip) {
    var walker = document.createTreeWalker(strip, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        if (!node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
        var parent = node.parentNode;
        if (parent.classList && parent.classList.contains('sf-text')) return NodeFilter.FILTER_REJECT;
        if (parent.closest('script,style,textarea,select,option,[contenteditable="true"]')) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(function (node) {
      var span = document.createElement('span');
      span.className = 'sf-text';
      node.parentNode.insertBefore(span, node);
      span.appendChild(node);
    });
  }

  function clear(strip) {
    strip.removeAttribute('data-scroll-fading');
    strip.querySelectorAll('.sf-text[data-sf]').forEach(function (span) {
      span.removeAttribute('data-sf');
      span.style.removeProperty('--sf-mask');
    });
  }

  function update(strip) {
    var max = strip.scrollWidth - strip.clientWidth;
    if (max <= 1) { if (strip.hasAttribute('data-scroll-fading')) clear(strip); return; }
    wrapText(strip);
    var box = strip.getBoundingClientRect();
    var left = Math.max(0, Math.min(FADE, strip.scrollLeft));
    var right = Math.max(0, Math.min(FADE, max - strip.scrollLeft));
    strip.setAttribute('data-scroll-fading', '');
    strip.querySelectorAll('.sf-text').forEach(function (span) {
      var r = span.getBoundingClientRect();
      var stops = [];
      if (left > 0 && r.left < box.left + left) {
        stops.push('transparent ' + (box.left - r.left).toFixed(1) + 'px', '#000 ' + (box.left + left - r.left).toFixed(1) + 'px');
      }
      if (right > 0 && r.right > box.right - right) {
        stops.push('#000 ' + (box.right - right - r.left).toFixed(1) + 'px', 'transparent ' + (box.right - r.left).toFixed(1) + 'px');
      }
      if (!stops.length) {
        if (span.hasAttribute('data-sf')) { span.removeAttribute('data-sf'); span.style.removeProperty('--sf-mask'); }
        return;
      }
      span.style.setProperty('--sf-mask', 'linear-gradient(90deg,' + stops.join(',') + ')');
      span.setAttribute('data-sf', '');
    });
  }

  function schedule(strip) {
    if (raf.get(strip)) return;
    raf.set(strip, requestAnimationFrame(function () { raf.set(strip, 0); update(strip); }));
  }

  function attach(strip) {
    if (!attached.has(strip)) {
      attached.add(strip);
      strip.addEventListener('scroll', function () { schedule(strip); }, { passive: true });
      if (typeof ResizeObserver === 'function') new ResizeObserver(function () { schedule(strip); }).observe(strip);
    }
    update(strip);
  }

  // Re-measure a page region after it was redrawn (a patch can drop the
  // wrappers and masks this script added).
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
