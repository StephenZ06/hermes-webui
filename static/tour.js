// ── Onboarding tour (Priority 3) ─────────────────────────────────────────────
// A minimal, dependency-free spotlight-and-tooltip walkthrough of the main
// app surfaces, distinct from the first-run setup wizard (static/onboarding.js
// only ever configures a provider/workspace/password -- it never highlights
// live UI). See docs/HERMES_STUDIO_PARITY_PLAN.md, "Onboarding tour".
//
// No framework/dependency added (AGENTS.md rules that out for something this
// small) -- a ghost spotlight div positioned via getBoundingClientRect() plus
// a tooltip card, matching the vanilla-JS/no-build-step constraint the rest
// of this codebase follows.

const APP_TOUR_STEPS=[
  {
    selectors:null, // welcome step: centered card, no spotlight target
    titleKey:'tour_step_welcome_title',
    bodyKey:'tour_step_welcome_body',
  },
  {
    selectors:['#btnNewChat'],
    titleKey:'tour_step_new_chat_title',
    bodyKey:'tour_step_new_chat_body',
    placement:'bottom',
  },
  {
    selectors:['#msg'],
    titleKey:'tour_step_composer_title',
    bodyKey:'tour_step_composer_body',
    placement:'top',
  },
  {
    selectors:['.rail .rail-btn.nav-tab[data-panel="kanban"]','.sidebar-nav .nav-tab[data-panel="kanban"]'],
    titleKey:'tour_step_kanban_title',
    bodyKey:'tour_step_kanban_body',
    placement:'right',
  },
  {
    selectors:['.rail .rail-btn.nav-tab[data-panel="skills"]','.sidebar-nav .nav-tab[data-panel="skills"]'],
    titleKey:'tour_step_skills_title',
    bodyKey:'tour_step_skills_body',
    placement:'right',
  },
  {
    selectors:['.rail .rail-btn.nav-tab[data-panel="settings"]','.sidebar-nav .nav-tab[data-panel="settings"]'],
    titleKey:'tour_step_settings_title',
    bodyKey:'tour_step_settings_body',
    placement:'right',
  },
];

let _appTourIndex=0;
let _appTourActive=false;
let _appTourReposition=null;

function _appTourVisibleTarget(step){
  if(!step||!Array.isArray(step.selectors)) return null;
  for(const sel of step.selectors){
    const el=document.querySelector(sel);
    // offsetParent!==null is the existing hidden-element check used
    // elsewhere in this codebase (e.g. static/ui.js:5433) -- covers
    // display:none and any hidden ancestor, which is exactly what
    // distinguishes the desktop .rail markup from the mobile .sidebar-nav
    // markup at any given viewport width.
    if(el&&el.offsetParent!==null) return el;
  }
  return null;
}

function _appTourEsc(ev){
  if(ev.key==='Escape') _endAppTour(false);
}

function _appTourPositionCard(target,placement){
  const overlay=document.getElementById('appTourOverlay');
  const spotlight=document.getElementById('appTourSpotlight');
  const card=document.getElementById('appTourCard');
  if(!overlay||!spotlight||!card) return;
  if(!target){
    spotlight.style.display='none';
    card.style.top='50%';
    card.style.left='50%';
    card.style.transform='translate(-50%,-50%)';
    return;
  }
  const rect=target.getBoundingClientRect();
  const pad=6;
  spotlight.style.display='block';
  spotlight.style.top=`${rect.top-pad}px`;
  spotlight.style.left=`${rect.left-pad}px`;
  spotlight.style.width=`${rect.width+pad*2}px`;
  spotlight.style.height=`${rect.height+pad*2}px`;
  // Measure the card after it has real content so placement math uses its
  // actual size, not a stale one from the previous step.
  const cardRect=card.getBoundingClientRect();
  const gap=14;
  let top,left;
  const place=placement||'bottom';
  if(place==='right'){
    top=Math.min(Math.max(8,rect.top),window.innerHeight-cardRect.height-8);
    left=Math.min(rect.right+gap,window.innerWidth-cardRect.width-8);
  }else if(place==='top'){
    top=Math.max(8,rect.top-cardRect.height-gap);
    left=Math.min(Math.max(8,rect.left),window.innerWidth-cardRect.width-8);
  }else{
    // 'bottom' default; if there's no room below, flip above.
    const belowTop=rect.bottom+gap;
    top=(belowTop+cardRect.height>window.innerHeight-8)
      ? Math.max(8,rect.top-cardRect.height-gap)
      : belowTop;
    left=Math.min(Math.max(8,rect.left),window.innerWidth-cardRect.width-8);
  }
  card.style.transform='none';
  card.style.top=`${top}px`;
  card.style.left=`${left}px`;
}

function _renderAppTourStep(){
  const step=APP_TOUR_STEPS[_appTourIndex];
  if(!step){ _endAppTour(true); return; }
  const target=_appTourVisibleTarget(step);
  // A step whose target isn't visible in this viewport/layout (e.g. a
  // hidden nav tab) is skipped entirely rather than spotlighting nothing
  // or throwing -- move forward (or finish, if it was the last step).
  if(step.selectors&&!target){
    _appTourIndex++;
    _renderAppTourStep();
    return;
  }
  const titleEl=document.getElementById('appTourTitle');
  const bodyEl=document.getElementById('appTourBody');
  const counterEl=document.getElementById('appTourCounter');
  const backBtn=document.getElementById('appTourBackBtn');
  const nextBtn=document.getElementById('appTourNextBtn');
  if(titleEl) titleEl.textContent=t(step.titleKey);
  if(bodyEl) bodyEl.textContent=t(step.bodyKey);
  if(counterEl) counterEl.textContent=t('tour_step_counter').replace('{n}',String(_appTourIndex+1)).replace('{total}',String(APP_TOUR_STEPS.length));
  if(backBtn) backBtn.style.display=_appTourIndex===0?'none':'';
  if(nextBtn) nextBtn.textContent=_appTourIndex===APP_TOUR_STEPS.length-1?t('tour_done'):t('tour_next');
  _appTourPositionCard(target,step.placement);
}

function nextAppTourStep(){
  _appTourIndex++;
  _renderAppTourStep();
}

function prevAppTourStep(){
  if(_appTourIndex===0) return;
  _appTourIndex--;
  _renderAppTourStep();
}

function startAppTour(){
  const overlay=document.getElementById('appTourOverlay');
  if(!overlay) return;
  _appTourIndex=0;
  _appTourActive=true;
  overlay.style.display='flex';
  document.addEventListener('keydown',_appTourEsc);
  _appTourReposition=()=>_renderAppTourStep();
  window.addEventListener('resize',_appTourReposition);
  window.addEventListener('scroll',_appTourReposition,true);
  _renderAppTourStep();
}

async function _endAppTour(completed){
  const overlay=document.getElementById('appTourOverlay');
  if(overlay) overlay.style.display='none';
  _appTourActive=false;
  document.removeEventListener('keydown',_appTourEsc);
  if(_appTourReposition){
    window.removeEventListener('resize',_appTourReposition);
    window.removeEventListener('scroll',_appTourReposition,true);
    _appTourReposition=null;
  }
  window._tourCompleted=true;
  try{
    await api('/api/settings',{method:'POST',body:JSON.stringify({tour_completed:true})});
  }catch(e){
    // Non-fatal: the tour just gets offered again next boot. Do not block
    // the UI or surface a toast for a background preference save.
    console.warn('tour_completed save failed',e);
  }
}

function skipAppTour(){ _endAppTour(false); }

// Auto-entry, called once from static/boot.js right after the onboarding
// wizard has settled (finished, skipped, or was never needed this boot) --
// see the call site there for why it's a separate, later hook rather than
// part of the wizard itself. Deliberately does nothing if the overlay
// markup isn't present (defensive -- matches this codebase's existing
// pattern of guarding optional DOM lookups rather than assuming the caller
// always has it).
function _maybeAutoStartAppTour(){
  if(window._tourCompleted) return;
  if(!document.getElementById('appTourOverlay')) return;
  // Let the rest of the boot sequence (session list render, model dropdown)
  // settle first so the spotlight measures real, final element positions.
  setTimeout(()=>{ if(!window._tourCompleted) startAppTour(); },600);
}
