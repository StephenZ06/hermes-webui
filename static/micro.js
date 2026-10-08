// ─────────────────────────────────────────────────────────────────────────────
// micro.js — small, shared interaction feedback for every page.
//
// Ideas from transitions.dev, designspells.com, ObsidianUI and Rare UI, rebuilt
// here in plain CSS and JavaScript (no code copied: those are React/Tailwind
// libraries with their own licences). Each helper is optional and safe to call
// on a missing element; with reduced motion asked for, the end state is shown
// without the movement.
//
//   Micro.tabs(container)        a pill that slides to the active tab
//   Micro.scan(root)             wire every [data-mi-tabs] under root
//   Micro.busy(button, label)    "Saving…" with a spinner, width held
//   Micro.done(button, label)    spinner turns into a drawn tick, then restores
//   Micro.fail(button)           restores the label and shakes the button
//   Micro.shake(el)              one short horizontal shake (errors)
//   Micro.invalid(field)         marks a field invalid until it is edited
//   Micro.ghostToast(toast)      leaves the outgoing toast stacked under the new one
//   Micro.status(messages)       HTML for a shimmering "working" line that steps
//                                through messages (Luna scoring, Scout running)
//   Micro.confetti(el)           a short burst from an element (milestones; unused
//                                until the app has a milestone check)
//   themed tooltips              replace the browser's plain title tooltip
// ─────────────────────────────────────────────────────────────────────────────
(function () {
  'use strict';
  const reduced = () => !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  // ---- sliding tab pill ---------------------------------------------------
  // The container keeps its own buttons; one extra span (data-mi-keep, so a
  // re-render that patches the DOM leaves it in place) slides under the active
  // one. data-mi-tabs="y" slides vertically (side menus).
  const ACTIVE = '.active, [aria-selected="true"], [aria-current="page"], [aria-pressed="true"]';
  const wired = new WeakMap();
  function placePill(container, instant) {
    const state = wired.get(container);
    if (!state) return;
    const pill = state.pill;
    if (!pill.isConnected || pill.parentNode !== container) container.prepend(pill);
    const active = [...container.children].find((c) => c !== pill && c.matches && c.matches(ACTIVE) && c.offsetParent !== null);
    if (!active) { pill.style.opacity = '0'; return; }
    const vertical = container.dataset.miTabs === 'y';
    const box = { x: active.offsetLeft, y: active.offsetTop, w: active.offsetWidth, h: active.offsetHeight };
    if (instant || reduced() || !state.placed) pill.classList.add('mi-pill-instant');
    pill.style.opacity = '1';
    pill.style.width = `${box.w}px`;
    pill.style.height = `${box.h}px`;
    pill.style.transform = vertical ? `translate(${box.x}px, ${box.y}px)` : `translate(${box.x}px, ${box.y}px)`;
    if (pill.classList.contains('mi-pill-instant')) { void pill.offsetWidth; pill.classList.remove('mi-pill-instant'); }
    state.placed = true;
    container.classList.add('mi-tabs-ready');
  }
  function tabs(container) {
    if (!container || wired.has(container)) { if (container) placePill(container); return; }
    const pill = document.createElement('span');
    pill.className = 'mi-pill';
    pill.setAttribute('aria-hidden', 'true');
    pill.setAttribute('data-mi-keep', '');
    container.classList.add('mi-tabs');
    const state = { pill, placed: false };
    wired.set(container, state);
    container.prepend(pill);
    let frame = 0;
    const later = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(() => placePill(container)); };
    state.observer = new MutationObserver(later);
    state.observer.observe(container, { attributes: true, subtree: true, childList: true, attributeFilter: ['class', 'aria-selected', 'aria-current', 'aria-pressed'] });
    if (typeof ResizeObserver === 'function') new ResizeObserver(later).observe(container);
    placePill(container, true);
  }
  function scan(root) {
    (root || document).querySelectorAll('[data-mi-tabs]').forEach(tabs);
  }

  // ---- button states ---------------------------------------------------------
  const SPIN = '<svg class="mi-spin" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6"/></svg>';
  const TICK = '<svg class="mi-tick" viewBox="0 0 16 16" aria-hidden="true"><path pathLength="1" d="M3.5 8.5l3 3 6-7"/></svg>';
  function swap(button, html) {
    const label = document.createElement('span');
    label.className = 'mi-label';
    label.innerHTML = html;
    button.replaceChildren(label);
  }
  function busy(button, text) {
    if (!button) return;
    if (button._miOriginal == null) button._miOriginal = button.innerHTML;
    clearTimeout(button._miRestore);
    button.style.minWidth = `${button.offsetWidth}px`;
    button.setAttribute('data-mi-hold', '');
    button.classList.add('mi-busy');
    button.disabled = true;
    swap(button, `${SPIN}<span>${escapeHtml(text || button.textContent.trim())}</span>`);
  }
  function restore(button) {
    if (!button) return;
    clearTimeout(button._miRestore);
    if (button._miOriginal != null) swap(button, button._miOriginal);
    button._miOriginal = null;
    button.classList.remove('mi-busy', 'mi-done');
    button.style.minWidth = '';
    button.disabled = false;
    button.removeAttribute('data-mi-hold');
    button.dispatchEvent(new CustomEvent('mi:released', { bubbles: true }));
  }
  function done(button, text, ms) {
    if (!button) return Promise.resolve();
    if (button._miOriginal == null) button._miOriginal = button.innerHTML;
    button.classList.remove('mi-busy');
    button.classList.add('mi-done');
    button.setAttribute('data-mi-hold', '');
    swap(button, `${TICK}<span>${escapeHtml(text || 'Done')}</span>`);
    return new Promise((resolve) => { button._miRestore = setTimeout(() => { restore(button); resolve(); }, ms || 1300); });
  }
  function fail(button) {
    if (!button) return;
    restore(button);
    shake(button);
  }

  // ---- errors ------------------------------------------------------------------
  function shake(el) {
    if (!el || reduced()) return;
    el.classList.remove('mi-shake');
    void el.offsetWidth;
    el.classList.add('mi-shake');
    el.addEventListener('animationend', () => el.classList.remove('mi-shake'), { once: true });
  }
  function invalid(field) {
    if (!field) return;
    field.setAttribute('aria-invalid', 'true');
    shake(field);
    const clear = () => field.removeAttribute('aria-invalid');
    field.addEventListener('input', clear, { once: true });
    field.addEventListener('change', clear, { once: true });
  }

  // ---- toasts stack ------------------------------------------------------------
  // The live toast stays one element (#toast); when a new message replaces a
  // visible one, a copy of the old one is left just under it and fades out.
  const ghosts = [];
  function ghostToast(toast) {
    if (!toast || !toast.classList.contains('show') || reduced()) return;
    const box = toast.getBoundingClientRect();
    if (!box.width) return;
    const ghost = toast.cloneNode(true);
    ghost.removeAttribute('id');
    ghost.classList.add('mi-toast-ghost');
    ghost.setAttribute('aria-hidden', 'true');
    ghost.querySelectorAll('[id]').forEach((n) => n.removeAttribute('id'));
    Object.assign(ghost.style, { top: `${box.top}px`, left: `${box.left}px`, right: 'auto', bottom: 'auto', width: `${box.width}px` });
    document.body.appendChild(ghost);
    ghosts.unshift({ el: ghost, height: box.height });
    while (ghosts.length > 2) ghosts.pop().el.remove();
    let offset = box.height + 8;
    ghosts.forEach((g, i) => {
      g.el.style.transform = `translateY(${offset}px) scale(${1 - 0.04 * (i + 1)})`;
      g.el.style.opacity = String(0.8 - 0.25 * i);
      offset += 10;
    });
    setTimeout(() => {
      ghost.style.opacity = '0';
      setTimeout(() => { ghost.remove(); const at = ghosts.findIndex((g) => g.el === ghost); if (at >= 0) ghosts.splice(at, 1); }, 260);
    }, 2400);
  }

  // ---- a "working" line ------------------------------------------------------------
  // A shimmering status that steps through what is happening, the same
  // everywhere Luna or Scout works ("Reading the posting…", "Scoring…").
  function status(messages, extraClass) {
    const list = (Array.isArray(messages) ? messages : [messages]).filter(Boolean).map(String);
    const lines = list.map((m, i) => `<span class="mi-status-line" style="--n:${list.length};--i:${i}">${escapeHtml(m)}</span>`).join('');
    return `<span class="mi-status${extraClass ? ` ${extraClass}` : ''}${list.length > 1 ? ' is-stepping' : ''}" role="status" aria-label="${escapeHtml(list[0] || '')}"><span class="mi-status-dot" aria-hidden="true"></span><span class="mi-status-lines">${lines}</span></span>`;
  }

  // ---- confetti --------------------------------------------------------------------
  // For milestones (first interview, an offer). Kept ready; nothing calls it
  // until the app records milestones.
  function confetti(el, count) {
    if (!el || reduced()) return;
    const box = el.getBoundingClientRect();
    const colours = ['#a78bfa', '#60a5fa', '#4ade80', '#f5b84b', '#f07878', '#2dd4bf'];
    for (let i = 0; i < (count || 28); i += 1) {
      const bit = document.createElement('i');
      bit.className = 'mi-confetti';
      bit.style.left = `${box.left + box.width / 2}px`;
      bit.style.top = `${box.top + box.height / 2}px`;
      bit.style.background = colours[i % colours.length];
      document.body.appendChild(bit);
      const angle = Math.random() * Math.PI * 2;
      const speed = 80 + Math.random() * 120;
      const dx = Math.cos(angle) * speed;
      const dy = Math.sin(angle) * speed - 90;
      bit.animate([
        { transform: 'translate(-50%,-50%) rotate(0deg)', opacity: 1 },
        { transform: `translate(calc(-50% + ${dx}px), calc(-50% + ${dy + 160}px)) rotate(${Math.random() * 720 - 360}deg)`, opacity: 0 },
      ], { duration: 900 + Math.random() * 500, easing: 'cubic-bezier(.2,.7,.3,1)' }).finished.finally(() => bit.remove());
    }
  }

  // ---- themed tooltips ---------------------------------------------------------------
  // Any element with a title shows a themed tooltip after a short wait, moves
  // straight to the next one while you keep pointing, and closes at once. The
  // title is parked in data-mi-title while the tip shows, so the browser's
  // own tooltip never doubles it.
  let tip = null;
  let tipFor = null;
  let showTimer = 0;
  let lastHide = 0;
  function tipEl() {
    if (!tip) {
      tip = document.createElement('div');
      tip.className = 'mi-tip';
      tip.setAttribute('role', 'tooltip');
      tip.id = 'miTooltip';
      document.body.appendChild(tip);
    }
    return tip;
  }
  function park(el) {
    const text = el.getAttribute('title');
    if (text == null) return el.getAttribute('data-mi-title');
    el.setAttribute('data-mi-title', text);
    el.removeAttribute('title');
    return text;
  }
  function unpark(el) {
    if (!el || !el.hasAttribute('data-mi-title')) return;
    if (!el.hasAttribute('title')) el.setAttribute('title', el.getAttribute('data-mi-title'));
    el.removeAttribute('data-mi-title');
  }
  function showTip(el) {
    const text = (el.getAttribute('data-mi-title') || '').trim();
    if (!text || !el.isConnected) return;
    const t = tipEl();
    t.textContent = text;
    t.classList.remove('is-below');
    t.style.left = '0px'; t.style.top = '0px';
    t.classList.add('is-open');
    const box = el.getBoundingClientRect();
    const tb = t.getBoundingClientRect();
    let top = box.top - tb.height - 8;
    if (top < 6) { top = box.bottom + 8; t.classList.add('is-below'); }
    const left = Math.min(window.innerWidth - tb.width - 6, Math.max(6, box.left + box.width / 2 - tb.width / 2));
    t.style.left = `${Math.round(left)}px`;
    t.style.top = `${Math.round(top)}px`;
    el.setAttribute('aria-describedby', 'miTooltip');
  }
  function hideTip() {
    clearTimeout(showTimer);
    if (tip && tip.classList.contains('is-open')) { tip.classList.remove('is-open'); lastHide = performance.now(); }
    if (tipFor) { tipFor.removeAttribute('aria-describedby'); unpark(tipFor); }
    tipFor = null;
  }
  function targetOf(node) {
    const el = node && node.closest ? node.closest('[title], [data-mi-title]') : null;
    if (!el || el.closest('.mi-tip, iframe, svg title') || el.tagName === 'IFRAME') return null;
    return el;
  }
  function onOver(event) {
    if (event.pointerType === 'touch') return;
    const el = targetOf(event.target);
    if (el === tipFor) return;
    if (tipFor) hideTip();
    if (!el) return;
    if (!park(el)) return;
    tipFor = el;
    // Moving from one tip to the next shows it straight away.
    const warm = performance.now() - lastHide < 400;
    showTimer = setTimeout(() => { if (tipFor === el) showTip(el); }, warm ? 0 : 450);
  }
  function onOut(event) {
    if (!tipFor) return;
    if (event.relatedTarget && tipFor.contains(event.relatedTarget)) return;
    hideTip();
  }
  function onFocus(event) {
    const el = targetOf(event.target);
    if (!el || el !== event.target || !el.matches(':focus-visible')) return;
    if (tipFor) hideTip();
    if (!park(el)) return;
    tipFor = el;
    showTip(el);
  }
  if (typeof document !== 'undefined') {
    document.addEventListener('pointerover', onOver, true);
    document.addEventListener('pointerout', onOut, true);
    document.addEventListener('pointerdown', hideTip, true);
    document.addEventListener('focusin', onFocus, true);
    document.addEventListener('focusout', (e) => { if (tipFor && e.target === tipFor) hideTip(); }, true);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hideTip(); }, true);
    window.addEventListener('scroll', hideTip, true);
    window.addEventListener('blur', hideTip);
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>'"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
  }

  window.Micro = { tabs, scan, busy, done, fail, restore, shake, invalid, ghostToast, status, confetti, hideTip };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => scan(document));
  else scan(document);
}());
