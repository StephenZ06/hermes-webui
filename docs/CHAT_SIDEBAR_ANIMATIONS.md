# Chat Sidebar Animations — Implementation Guide

This document explains how to add smooth expand/collapse and profile-switch fade
animations to a vanilla-JS sidebar, using the Hermes WebUI implementation as a
reference. It also records the root causes that made the first attempt invisible.

## Problem statement

- **Date-group expand/collapse** (TODAY / THIS WEEK / LAST WEEK / OLDER) snapped
  open/closed with no animation.
- **Usage card profile switch** snapped between providers with no fade.

## Root causes found

1. **Browser coalescing.** Setting a class and then removing it in the same
   synchronous block (or before the element is painted) causes the browser to
   collapse both changes into one style recalculation. No intermediate state is
   rendered, so no transition runs.
2. **Detached DOM manipulation.** Calling the animation helper while the element
   is still in a document fragment (before `appendChild` reaches the live
   document) has the same coalescing effect.
3. **Hidden-element fade.** Adding an `opacity:0` class to an element that still
   carries the `hidden` attribute, then removing both in the same frame, is
   another coalescing case.
4. **PWA service-worker caching.** Static files are version-keyed; without a
   version bump the browser keeps serving the old JS/CSS forever.
5. **`prefers-reduced-motion`.** The animations are intentionally disabled for
   users who have asked for reduced motion. If the user's OS/browser is in that
   mode, the feature is working as designed and will appear static.

## Implementation

### 1. Date-group expand/collapse (grid-template-rows)

The animation uses `grid-template-rows` 0fr ↔ 1fr on a wrapper so the timing
tracks the group's real content height instead of a guessed `max-height`.

**CSS** (`static/style.css`):

```css
.session-date-body{display:grid;grid-template-rows:1fr;
  transition:grid-template-rows .18s cubic-bezier(.2,.8,.2,1);}
.session-date-body.is-collapsed{grid-template-rows:0fr;}
.session-date-body.no-transition{transition:none;}
.session-date-inner{overflow:hidden;min-height:0;}

@media (prefers-reduced-motion:reduce){
  .session-date-body{transition:none;}
}
```

**JS helper** (`static/sessions.js`):

```js
function _applyDateGroupCollapsedState(body, collapsed, animate){
  const inner=body.firstElementChild;
  const hasInner=Boolean(inner&&inner.classList&&inner.classList.contains('session-date-inner'));
  if(hasInner) inner.inert=collapsed;
  if(!animate||_sessionPrefersReducedMotion()){
    body.classList.toggle('no-transition',true);
    body.classList.toggle('is-collapsed',collapsed);
    void body.offsetHeight;
    body.classList.toggle('no-transition',false);
    return;
  }
  body.classList.add('no-transition');
  body.classList.toggle('is-collapsed',!collapsed);
  void body.offsetHeight;
  body.classList.remove('no-transition');
  body.classList.toggle('is-collapsed',collapsed);
}
```

**Render integration** (`renderSessionListFromCache`):

- **Collapse** (the live body still holds its rows): shrink the body in place,
  then commit the state and re-render only after the animation lands.
- **Expand** (a collapsed group renders no rows): rebuild the list with the
  body pre-collapsed, append it to the DOM, then **wait one frame** before
  applying the animation. This is the critical step that makes the transition
  visible:

```js
list.appendChild(wrapper);
if(animateDateGroup&&g.label===animateDateGroup&&!isGroupCollapsed){
  if(typeof requestAnimationFrame==='function'){
    requestAnimationFrame(()=>_applyDateGroupCollapsedState(body,false,true));
  }else{
    _applyDateGroupCollapsedState(body,false,true);
  }
}
```

### 2. Usage-card fade on profile switch

The fade tracks the last provider. When the provider changes, the widget fades
out, updates its content, and fades back in. It also works when the widget was
previously hidden (e.g. local profile → hosted profile).

**CSS** (`static/style.css`):

```css
.chat-usage-widget{transition:opacity .25s ease;}
.chat-usage-widget.is-fading{opacity:0;}
```

**JS** (`static/ui.js`):

```js
let _lastAccountUsageProvider;

function _fadeAccountUsageWidget(callback){
  const widget=$('chatUsageWidget');
  if(!widget){ callback(); return; }
  const reduceMotion=window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if(reduceMotion){ callback(); return; }
  widget.classList.add('is-fading');
  setTimeout(()=>{
    callback();
    // The callback may have just unhidden the widget. Paint the new content at
    // opacity:0 first so removing the class on the next frame produces a real
    // fade-in instead of an instant paint.
    if(typeof requestAnimationFrame==='function'){
      requestAnimationFrame(()=>widget.classList.remove('is-fading'));
    }else{
      widget.classList.remove('is-fading');
    }
  },250);
}

function _renderAccountUsage(data){
  const widget=$('chatUsageWidget');
  if(!widget) return;
  const provider=String(data&&data.provider||'').toLowerCase();
  const providerChanged=_lastAccountUsageProvider!==undefined && provider!==_lastAccountUsageProvider;
  _lastAccountUsageProvider=provider;
  if(providerChanged){
    _fadeAccountUsageWidget(()=>_renderAccountUsageImpl(data));
  }else{
    _renderAccountUsageImpl(data);
  }
}
```

## Common pitfalls

- **Do not call the animation helper before `appendChild`.** The browser may
  not paint the pre-state, and the transition coalesces.
- **Do not remove the fade class in the same task as the content update.** Use
  `requestAnimationFrame` so the browser paints the intermediate state.
- **Respect `prefers-reduced-motion`.** Both animations skip when the user has
  requested reduced motion.
- **Bump the service-worker version.** If the app is a PWA, static files are
  cached by version. Commit or otherwise change the version token, then tell
  the user to reload (possibly twice) or unregister the service worker.

## Testing

- Source-structure tests pin the existence of the CSS rules and the JS helpers.
- Node-harness tests exercise `_applyDateGroupCollapsedState` with a fake
  element to assert the pre-state/target class sequence.
- Browser tests (Playwright) verify the actual opacity / height transitions if
  available.
