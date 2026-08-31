// ─────────────────────────────────────────────────────────────────────────────
// motion-ui.js — restrained UI motion built on Motion (static/vendor/motion).
//
// The app has no bundler and no React, so this is a classic script that talks
// to Motion's UMD global. Everything here is additive and optional: if Motion
// failed to load, or the viewer asked for reduced motion, every helper becomes
// a no-op that leaves the element in its final state. Nothing in the app may
// depend on an animation having run.
//
// Scope is deliberately narrow. The app already carries a lot of hand-tuned CSS
// motion (composited panel slides, stream fades, skeletons), and layering a
// second animation system over all of it would fight those transitions and the
// per-frame scroll work during streaming. So this drives entrances, presence
// (enter/exit), pointer feedback and list reordering for a short list of
// surfaces, and leaves everything else to the CSS that already handles it.
//
// Rules enforced here rather than left to call sites:
//   - transform and opacity only, so nothing triggers layout
//   - 150-350ms for interaction motion
//   - inline styles are cleared once an entrance finishes, so hover/active CSS
//     on the same element keeps working afterwards
// ─────────────────────────────────────────────────────────────────────────────

(function(){
  'use strict';

  const DUR = { fast: 0.18, base: 0.24, slow: 0.32 };
  // One spring for every surface that appears — dialogs, menus, popovers — so
  // they all arrive with the same weight instead of each carrying its own
  // hand-tuned duration.
  const ENTER_SPRING = { type: 'spring', stiffness: 620, damping: 38, mass: 0.9 };
  // Same decelerating curve the sidebar and workspace panel slides use, so
  // JS-driven and CSS-driven motion in the same view read as one system.
  const EASE = [0.22, 1, 0.36, 1];

  let _reduceMql = null;
  function prefersReducedMotion(){
    try{
      if(!_reduceMql && window.matchMedia) _reduceMql = window.matchMedia('(prefers-reduced-motion: reduce)');
      return !!(_reduceMql && _reduceMql.matches);
    }catch(_){ return false; }
  }

  function motionLib(){
    return (typeof window !== 'undefined' && window.Motion) || null;
  }

  function enabled(){
    return !!motionLib() && !prefersReducedMotion();
  }

  function toArray(target){
    if(!target) return [];
    if(typeof target === 'string') return Array.from(document.querySelectorAll(target));
    if(target instanceof Element) return [target];
    if(typeof target.length === 'number') return Array.from(target).filter(el => el instanceof Element);
    return [];
  }

  // Entrances set transform/opacity inline; leaving those behind would freeze
  // the element's own hover and active states, so they are cleared on finish.
  function clearInline(el){
    if(!el || !el.style) return;
    el.style.opacity = '';
    el.style.transform = '';
    el.style.willChange = '';
    el.style.transition = '';
  }

  // Several targets carry `transition: all` or a transform transition of their
  // own. Left in place, the browser would transition the values Motion is
  // already animating, layering a second easing on top of the first. Suppressed
  // for the duration of the entrance, then handed straight back.
  function suspendTransition(el){
    if(el && el.style) el.style.transition = 'none';
  }

  /**
   * Staggered fade-and-slide entrance for a set of sections or cards.
   * No-ops (leaving elements visible) when motion is off.
   */
  function enter(target, opts){
    const els = toArray(target);
    if(!els.length) return Promise.resolve();
    const o = opts || {};
    if(!enabled()){
      els.forEach(clearInline);
      return Promise.resolve();
    }
    const M = motionLib();
    const distance = typeof o.y === 'number' ? o.y : 8;
    const each = typeof o.stagger === 'number' ? o.stagger : 0.035;
    // A long list would otherwise take seconds to finish arriving; past a
    // dozen items the stagger stops reading as sequence and starts reading as
    // lag, so the tail arrives together.
    const staggered = els.slice(0, 12);
    const rest = els.slice(12);
    rest.forEach(clearInline);
    els.forEach(el => { el.style.willChange = 'transform, opacity'; suspendTransition(el); });
    const controls = M.animate(
      staggered,
      { opacity: [0, 1], transform: ['translateY(' + distance + 'px)', 'translateY(0px)'] },
      { duration: o.duration || DUR.base, easing: EASE, delay: M.stagger ? M.stagger(each) : 0 }
    );
    const done = (controls && controls.finished) || Promise.resolve();
    return done.then(() => { els.forEach(clearInline); }).catch(() => { els.forEach(clearInline); });
  }

  /**
   * Enter/exit for conditional UI — modals, drawers, dropdowns, toasts.
   * The vanilla stand-in for React's AnimatePresence: `out` resolves only once
   * the exit animation has finished, so the caller can remove or hide the node
   * at the right moment instead of guessing a timeout.
   */
  function presence(el, direction, opts){
    if(!(el instanceof Element)) return Promise.resolve();
    const o = opts || {};
    if(!enabled()){
      clearInline(el);
      return Promise.resolve();
    }
    const M = motionLib();
    const from = o.from || 'bottom';
    const dist = typeof o.distance === 'number' ? o.distance : 8;
    const axis = (from === 'left' || from === 'right') ? 'X' : 'Y';
    const sign = (from === 'top' || from === 'left') ? -1 : 1;
    const offset = 'translate' + axis + '(' + (sign * dist) + 'px)';
    const scaleFrom = o.scale === false ? '' : ' scale(0.98)';
    const hidden = offset + scaleFrom;
    const shown = 'translate' + axis + '(0px)' + (o.scale === false ? '' : ' scale(1)');
    const isIn = direction !== 'out';
    el.style.willChange = 'transform, opacity';
    suspendTransition(el);
    const keyframes = isIn
      ? { opacity: [0, 1], transform: [hidden, shown] }
      : { opacity: [1, 0], transform: [shown, hidden] };
    // Entrances get a spring so a surface arrives with some weight rather than
    // easing to a stop; exits stay short and linear-ish, because a springy
    // dismissal reads as hesitation. animateMini compiles both to WAAPI, which
    // runs off the main thread — the same reason slidePanel uses it.
    const options = isIn
      ? (o.duration ? { duration: o.duration, easing: EASE } : ENTER_SPRING)
      : { duration: o.duration || DUR.fast, easing: 'ease-in' };
    const run = (typeof M.animateMini === 'function' && !o.forceJs) ? M.animateMini : M.animate;
    const controls = run(el, keyframes, options);
    const done = (controls && controls.finished) || Promise.resolve();
    const settle = () => {
      if(isIn) clearInline(el);
      // An exit keeps its final opacity/transform (the node is about to be
      // hidden) but must never keep transition:none, or the element's own CSS
      // animation would be dead the next time it is shown — nor will-change,
      // which would strand a compositor layer on a hidden element.
      else if(el.style){ el.style.transition = ''; el.style.willChange = ''; }
    };
    return done.then(settle).catch(settle);
  }

  /**
   * Subtle pointer feedback for clickable cards and buttons. Uses Motion's
   * hover/press gestures, which are pointer-type aware, so a touch device
   * never gets a stuck hover state.
   */
  function lift(target, opts){
    const els = toArray(target);
    if(!els.length || !enabled()) return () => {};
    const M = motionLib();
    if(typeof M.hover !== 'function') return () => {};
    const o = opts || {};
    const y = typeof o.y === 'number' ? o.y : -2;
    const scale = typeof o.scale === 'number' ? o.scale : 1.012;
    const cleanups = [];
    els.forEach(el => {
      if(el.dataset.motionLift === '1') return; // never bind twice
      el.dataset.motionLift = '1';
      // Motion's hover gesture already ignores pointerType 'touch' in both
      // directions, so a tap can never leave a phone stuck in a hover state.
      // press does fire on touch, which is wanted: it is the tap feedback.
      const settle = () => {
        const controls = M.animate(el, { transform: 'translateY(0px) scale(1)' }, { duration: DUR.base, easing: EASE });
        const done = (controls && controls.finished) || Promise.resolve();
        // Hand the element back to its own CSS. Leaving `transform` inline
        // would outrank any :hover/:active transform the stylesheet defines on
        // it for the rest of the session.
        done.catch(() => {}).then(() => { el.style.transform = ''; });
      };
      const stopHover = M.hover(el, () => {
        M.animate(el, { transform: 'translateY(' + y + 'px) scale(' + scale + ')' }, { duration: DUR.fast, easing: EASE });
        return settle;
      });
      cleanups.push(stopHover);
      if(typeof M.press === 'function'){
        const stopPress = M.press(el, () => {
          M.animate(el, { transform: 'translateY(0px) scale(0.985)' }, { duration: 0.1, easing: 'ease-out' });
          return settle;
        });
        cleanups.push(stopPress);
      }
    });
    return () => cleanups.forEach(fn => { try{ fn(); }catch(_){} });
  }

  /**
   * Animate a list whose contents were just filtered or reordered.
   * Measures before and after, then plays each surviving row from its old
   * position to its new one (FLIP), so rows slide rather than jump. Rows that
   * appeared fade in. Purely transform/opacity — the layout itself is done by
   * the time anything animates.
   */
  function listChange(container, itemSelector, mutate){
    const root = (typeof container === 'string') ? document.querySelector(container) : container;
    const apply = typeof mutate === 'function' ? mutate : function(){};
    if(!(root instanceof Element)) { apply(); return Promise.resolve(); }
    if(!enabled()){ apply(); return Promise.resolve(); }
    const M = motionLib();
    const sel = (typeof itemSelector === 'object' && itemSelector) ? (itemSelector.selector || ':scope > *') : (itemSelector || ':scope > *');
    const keyAttr = (typeof itemSelector === 'object' && itemSelector) ? itemSelector.keyAttr : null;
    const keyOf = el => (keyAttr && el.getAttribute(keyAttr)) || el.dataset.motionKey || el.id;
    const before = new Map();
    root.querySelectorAll(sel).forEach(el => {
      const key = keyOf(el);
      if(key) before.set(key, el.getBoundingClientRect().top);
    });
    apply();
    const moved = [];
    const added = [];
    root.querySelectorAll(sel).forEach(el => {
      const key = keyOf(el);
      const prev = key ? before.get(key) : undefined;
      const next = el.getBoundingClientRect().top;
      if(prev === undefined){ added.push(el); return; }
      const delta = prev - next;
      if(Math.abs(delta) > 1) moved.push([el, delta]);
    });
    moved.forEach(([el, delta]) => {
      M.animate(el,
        { transform: ['translateY(' + delta + 'px)', 'translateY(0px)'] },
        { duration: DUR.base, easing: EASE }
      );
    });
    if(added.length){
      M.animate(added, { opacity: [0, 1] }, { duration: DUR.fast, easing: EASE });
    }
    return Promise.resolve();
  }

  // ───────────────────────────────────────────────────────────────────────────
  // Panel collapse / expand.
  //
  // The sidebar and the workspace panel used to collapse by transitioning
  // `width` from 300px to 0. Width is a layout property, so the browser ran a
  // full layout of the flex row — and therefore of the entire message list —
  // on every frame of the animation. Measured with CDP Performance metrics on a
  // 1440x900 desktop viewport:
  //
  //     800 messages, width transition : 137-173ms of layout over 11 frames
  //                                      (12-16ms per frame — the whole budget)
  //     800 messages, this function    : 6-8ms of layout total, 2-3 layouts
  //
  // The technique is FLIP with the panel taken out of flow. The state change is
  // applied once, so layout runs once; the panel is pinned to its old rect with
  // position:fixed so that single layout cannot make it jump or vanish; and both
  // the panel and the main column are then carried to their new positions on
  // composited transforms, which cost no layout at all.
  //
  // Everything is inline styling that is cleared on completion, and the whole
  // thing degrades to calling apply() directly when Motion is missing or motion
  // is reduced — the CSS width transition still exists and still works.
  const PANEL_SPRING = { type: 'spring', stiffness: 460, damping: 44, mass: 1 };

  // The panel's own CSS width transition has to be off BEFORE the state change,
  // not after: with it live, the rect read straight after the class toggle
  // returns a value from the first frame of the transition rather than the real
  // final geometry, and every measurement downstream is wrong.
  function freezePanel(el){
    el.style.setProperty('transition', 'none', 'important');
  }

  function thawPanel(el){
    // One forced read with transitions still off, so the geometry the element
    // snaps back to when the inline pin is dropped is not itself transitioned.
    try{ void el.offsetWidth; }catch(_){}
    el.style.removeProperty('transition');
  }

  function pinPanel(el, rect){
    // The collapsed rules use `width:0 !important`, so the pin has to be
    // important too or the panel is zero-width the moment the class lands.
    el.style.setProperty('position', 'fixed', 'important');
    el.style.setProperty('left', rect.left + 'px', 'important');
    el.style.setProperty('top', rect.top + 'px', 'important');
    el.style.setProperty('width', rect.width + 'px', 'important');
    el.style.setProperty('height', rect.height + 'px', 'important');
    el.style.setProperty('opacity', '1', 'important');
    el.style.setProperty('z-index', '6', 'important');
  }

  function unpinPanel(el){
    ['position','left','top','width','height','opacity','z-index','transform']
      .forEach(prop => el.style.removeProperty(prop));
    thawPanel(el);
  }

  // Motion's main `animate()` drives these from JS, one style write per frame,
  // and on the composer subtree that provokes a layout every frame (measured:
  // 32 layouts / 58ms). `animateMini` compiles the same spring into a WAAPI
  // animation that runs off the main thread, which does not (5-6 layouts / 9ms).
  // So this uses animateMini and falls back to animate() only if it is missing.
  function springTransform(el, fromTransform, toTransform){
    const M = motionLib();
    const keyframes = { transform: [fromTransform, toTransform] };
    // The element's resting style is set to the END value, so when the WAAPI
    // animation stops filling there is nothing to snap back to.
    el.style.transform = toTransform === 'none' ? '' : toTransform;
    if(M && typeof M.animateMini === 'function'){
      return M.animateMini(el, keyframes, PANEL_SPRING);
    }
    return M.animate(el, keyframes, PANEL_SPRING);
  }

  // side: 'left' for the sidebar, 'right' for the workspace panel  // which way the panel leaves the viewport.
  function slidePanel(panel, apply, opts){
    const options = opts || {};
    const side = options.side === 'right' ? 'right' : 'left';
    const main = options.main || document.querySelector('.main');
    if(typeof apply !== 'function') return;
    if(!panel || !main || !enabled()){ apply(); return; }

    let panelBefore, mainBefore, panelAfter, mainAfter;
    try{
      panelBefore = panel.getBoundingClientRect();
      mainBefore = main.getBoundingClientRect();
      freezePanel(panel);
      apply(); // the one and only layout-invalidating step
      panelAfter = panel.getBoundingClientRect();
      mainAfter = main.getBoundingClientRect();
    }catch(_){
      try{ apply(); }catch(__){}
      try{ thawPanel(panel); }catch(__){}
      return;
    }

    const expanding = panelAfter.width > panelBefore.width;
    const rect = expanding ? panelAfter : panelBefore;
    if(Math.abs(panelAfter.width - panelBefore.width) < 1 || rect.width < 1){
      thawPanel(panel);
      return; // nothing actually moved
    }

    const offscreen = side === 'left' ? -rect.width : rect.width;
    const panelFrom = expanding ? offscreen : 0;
    const panelTo = expanding ? 0 : offscreen;
    // How far the main column jumped when the state was applied. It is carried
    // back and animated to zero so the content glides instead of popping.
    const mainFrom = mainBefore.left - mainAfter.left;

    pinPanel(panel, rect);
    const running = [];
    try{
      running.push(springTransform(panel,
        'translateX(' + panelFrom + 'px)', 'translateX(' + panelTo + 'px)'));
      if(Math.abs(mainFrom) > 0.5){
        running.push(springTransform(main, 'translateX(' + mainFrom + 'px)', 'none'));
      }
    }catch(_){
      unpinPanel(panel);
      main.style.transform = '';
      return;
    }

    const settle = () => {
      unpinPanel(panel);
      main.style.transform = '';
    };
    Promise.all(running.map(a => {
      try{ return a.finished; }catch(_){ return Promise.resolve(); }
    })).then(settle, settle);
  }

  window.MotionUI = {
    enabled,
    prefersReducedMotion,
    enter,
    presence,
    lift,
    listChange,
    slidePanel,
    DUR,
    EASE,
  };
})();

// ─────────────────────────────────────────────────────────────────────────────
// Wiring for surfaces that have no natural JS hook.
//
// The empty state's visibility is toggled from half a dozen places in ui.js and
// messages.js, and renderMessages() re-asserts it on every render. Observing
// the element is both less invasive than editing every call site and the only
// way to animate a real reveal rather than every re-render.
// ─────────────────────────────────────────────────────────────────────────────

(function(){
  'use strict';

  function isVisible(el){
    return !!el && el.style.display !== 'none';
  }

  // ── Hero: text shimmer ─────────────────────────────────────────────────
  // Ported from Motion Primitives' TextShimmer (ibelick/motion-primitives),
  // which is a React component and cannot be dropped into a no-bundler vanilla
  // app. The technique is the portable part: a wide gradient masked to the
  // glyphs via background-clip, swept by animating background-position.
  //
  // Two deliberate departures from the original. It runs a single sweep on
  // reveal rather than looping -- a permanent shimmer on a heading you sit in
  // front of is exactly the kind of motion this pass is meant to avoid. And
  // both ends of the gradient are var(--text), so the resting state is the
  // ordinary heading colour and the effect cannot leave the text mis-coloured
  // if the animation is interrupted.
  //
  // The sweep has to end PAST the text, not at its edge. background-position
  // percentages place the image against the box, so with background-size:200%
  // the highlight (the gradient's 50% stop) sits at `-W*P + W` for box width
  // W: at P=0% that is exactly the right edge, which left the accent ramp
  // parked on the final word instead of carrying off the end. P=-30% puts the
  // band's near edge at 1.06W, clear of the text. The class is dropped once
  // the sweep finishes so the heading goes back to being ordinary text rather
  // than permanently gradient-clipped.
  //
  // This is the one effect that exceeds the 150-350ms interaction budget; at
  // 1.1s it reads as arrival polish rather than a control responding.
  function shimmerHeading(heading){
    const MotionUI = window.MotionUI;
    if(!heading || !MotionUI || !MotionUI.enabled()) return;
    if(!window.CSS || !CSS.supports || !CSS.supports('background-clip', 'text')) return;
    const M = window.Motion;
    if(!M || typeof M.animate !== 'function') return;
    heading.classList.add('motion-text-shimmer');
    const controls = M.animate(
      heading,
      { backgroundPosition: ['200% center', '-30% center'] },
      { duration: 1.1, easing: 'ease-in-out' }
    );
    const done = (controls && controls.finished) || Promise.resolve();
    done.catch(() => {}).then(() => {
      heading.style.backgroundPosition = '';
      heading.classList.remove('motion-text-shimmer');
    });
  }

  function animateEmptyState(el){
    const MotionUI = window.MotionUI;
    if(!MotionUI) return;
    const parts = [];
    const logo = el.querySelector('.empty-logo');
    const heading = el.querySelector('h2');
    const sub = el.querySelector('p');
    if(logo) parts.push(logo);
    if(heading) parts.push(heading);
    if(sub) parts.push(sub);
    Array.from(el.querySelectorAll('.suggestion')).forEach(s => parts.push(s));
    MotionUI.enter(parts, { y: 12, stagger: 0.045 });
    // No lift on .suggestion: the stylesheet already gives it a hover
    // treatment including transform:translateX(2px), under transition:all.
    // A JS transform would win by specificity, cancel that translate, and get
    // transitioned a second time by the CSS on top of Motion's own animation.
    if(heading) shimmerHeading(heading);
  }

  function watchEmptyState(){
    const el = document.getElementById('emptyState');
    if(!el) return;
    let wasVisible = isVisible(el);
    if(wasVisible) animateEmptyState(el);
    const observer = new MutationObserver(() => {
      const now = isVisible(el);
      if(now && !wasVisible) animateEmptyState(el);
      wasVisible = now;
    });
    observer.observe(el, { attributes: true, attributeFilter: ['style', 'class'] });
  }

  function init(){
    try{ watchEmptyState(); }catch(_){}
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init, { once: true });
  }else{
    init();
  }
})();
