let _currentPanel = 'chat';
let _renamingAppTitlebar = false;  // guard against re-entrant rename
let _kanbanBoard = null;
let _kanbanLatestEventId = 0;
let _kanbanPollTimer = null;
let _kanbanCurrentTaskId = null;
let _kanbanLanesByProfile = true;
// Multi-board state. _kanbanCurrentBoard is the slug of the active board
// the UI is currently viewing. null means "use whatever the server reports
// as active" (i.e. don't pin a specific board in API calls). The UI
// persists the last-viewed slug to localStorage so refresh stays put.
let _kanbanCurrentBoard = null;
let _kanbanBoardsList = null;
let _kanbanBoardMenuOpen = false;
// Crews (docs/HERMES_STUDIO_PARITY_PLAN.md, Phase 1): scopes the board/office
// view to one just-dispatched crew's tasks. Same UX slot as the tenant/
// assignee filters above, but with no dedicated <select> yet in Phase 1 --
// set programmatically by dispatchKanbanCrew(); Phase 2 adds the filter
// dropdown that lets a user pick it manually.
let kanbanWorkflowTemplateFilter = '';
let _kanbanIsDispatching = false;
let _kanbanSuppressCardClickUntil = 0;
// SSE event stream — replaces the 30s polling cadence with a long-lived
// /api/kanban/events/stream connection. Falls back to polling when the
// EventSource fails to connect (proxy that strips text/event-stream, etc).
let _kanbanEventSource = null;
let _kanbanEventSourceFailures = 0;
let _skillsData = null; // cached skills list
let _agentDefsData = null; // cached persona (agent definition) list
let _currentAgentDefDetail = null; // full persona object
let _agentDefMode = 'empty'; // 'empty' | 'read' | 'create' | 'edit'
let _agentDefPreFormDetail = null; // snapshot of prior selection when entering a form
let _editingAgentDefId = null;
let _knowledgeItems = null; // cached knowledge browser list (array, snippet-only rows)
let _knowledgeSearchResults = null; // active search results, or null when not searching
let _knowledgeSearchSeq = 0; // guards against out-of-order debounced search responses
let _knowledgeSearchDebounce = null;
let _currentKnowledgeItemId = null;
let _cronList = null; // cached cron jobs (array)
let _currentCronDetail = null; // full cron job object
let _currentCronDetailKey = '';
let _cronMode = 'empty'; // 'empty' | 'read' | 'create' | 'edit'
let _cronPreFormDetail = null; // snapshot of prior selection when entering a form
let _showAllCronProfiles = false;
let _cronOtherProfileCount = 0;
let _currentWorkspaceDetail = null; // { path, name, is_default }
let _workspaceMode = 'empty'; // 'empty' | 'read' | 'create' | 'edit'
let _workspacePreFormDetail = null;
let _currentProfileDetail = null; // full profile object
let _profileMode = 'empty'; // 'empty' | 'read' | 'create'
let _profilePreFormDetail = null;
// Mirrors api.config.VALID_REASONING_EFFORTS plus 'none' (explicit off),
// in the same order as the composer's own #composerReasoningDropdown options.
const REASONING_EFFORT_LEVELS = ['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'];
let _pendingSettingsTargetPanel = null; // destination selected while settings had unsaved changes
let _logsAutoRefreshTimer = null;
let _lastLogsLines = [];
let _logsSeverityFilter = 'all';

// Map of panel names → i18n keys for the app titlebar label.
const APP_TITLEBAR_KEYS = {
  chat: 'tab_chat', tasks: 'tab_tasks', skills: 'tab_skills', agents: 'tab_agents',
  memory: 'tab_memory', knowledge: 'tab_knowledge', workspaces: 'tab_workspaces',
  profiles: 'tab_profiles', todos: 'tab_todos', insights: 'tab_insights', analytics: 'tab_analytics', logs: 'tab_logs', audit: 'tab_audit', settings: 'tab_settings',
};
const MAIN_VIEW_PANELS = ['settings','skills','agents','memory','knowledge','tasks','kanban','workspaces','profiles','insights','analytics','logs','audit','plugin'];
const MAIN_VIEW_SIDEBAR_PANEL_FALLBACKS = { plugin: 'settings' };

/**
 * Update the top app titlebar to reflect the current page or selected conversation.
 * On the chat panel, a selected session's title takes precedence over the page name.
 */
function syncAppTitlebar() {
  const titleEl = document.getElementById('appTitlebarTitle');
  const subEl = document.getElementById('appTitlebarSub');
  if (!titleEl) return;
  const panel = (typeof _currentPanel === 'string' && _currentPanel) ? _currentPanel : 'chat';
  let mainText = '';
  let subText = '';
  let sourceLabel = '';
  if (panel === 'chat' && typeof S !== 'undefined' && S && S.session) {
    mainText = S.session.title || (typeof t === 'function' ? t('untitled') : 'Untitled');
    const vis = Array.isArray(S.messages) ? S.messages.filter(m => m && m.role && m.role !== 'tool') : [];
    subText = String(vis.length);
    sourceLabel = S.session.source_label || S.session.source_tag || S.session.raw_source || '';
    // Recovered sidecars stamp source_label 'WebUI' (api/session_recovery.py); don't badge a native session as its own source (#3338).
    if (/^webui$/i.test(sourceLabel)) sourceLabel = '';
  } else {
    const key = APP_TITLEBAR_KEYS[panel];
    mainText = key && typeof t === 'function' ? t(key) : (panel.charAt(0).toUpperCase() + panel.slice(1));
  }

  // Don't touch the element while an inline rename is in progress — replacing
  // the span with an input would fire a MutationObserver that calls
  // syncAppTitlebar again, destroying the input before the user finishes.
  if (_renamingAppTitlebar) return;

  titleEl.textContent = mainText;
  if (panel !== 'chat') {
    const bot = typeof assistantDisplayName === 'function' ? assistantDisplayName() : '';
    document.title = bot ? mainText + ' \u2014 ' + bot : mainText;
  }
  if (subEl) {
    if (subText) {
      subEl.textContent = subText;
      if (sourceLabel) {
        const badge = document.createElement('span');
        badge.className = 'topbar-source-badge';
        badge.textContent = sourceLabel + (S.session && S.session.read_only ? ' · read-only' : '');
        subEl.appendChild(document.createTextNode(' '));
        subEl.appendChild(badge);
      }
      subEl.hidden = false;
    }
    else { subEl.textContent = ''; subEl.hidden = true; }
  }

  // Double-click on the titlebar title → rename the active session (same behaviour
  // as double-clicking a session title in the sidebar).  Only active on the chat
  // panel when a session is open.
  titleEl.ondblclick = null;  // remove any previous handler before adding a fresh one
  if (panel === 'chat' && typeof S !== 'undefined' && S && S.session && !(S.session.read_only || S.session.is_read_only)) {
    titleEl.ondblclick = (e) => {
      e.stopPropagation();
      e.preventDefault();
      if (_renamingAppTitlebar) return;
      _renamingAppTitlebar = true;

      const inp = document.createElement('input');
      inp.type = 'text';
      inp.className = 'app-titlebar-rename-input';
      inp.value = S.session.title || (typeof t === 'function' ? t('untitled') : 'Untitled');

      // Prevent click/dblclick on the input from bubbling — we don't want
      // panel switches, session switches, or any other handler firing.
      ['click', 'mousedown', 'dblclick', 'pointerdown'].forEach(ev =>
        inp.addEventListener(ev, e2 => e2.stopPropagation())
      );

      const finish = async (save) => {
        _renamingAppTitlebar = false;
        if (save) {
          const newTitle = inp.value.trim() || (typeof t === 'function' ? t('untitled') : 'Untitled');
          S.session.title = newTitle;
          syncTopbar();   // update #topbarTitle in the chat header
          syncAppTitlebar();
          // Update the sidebar list so the renamed title appears immediately.
          // _renderOneSession reads from _allSessions cache, so patch it there too.
          try {
            const _cached = typeof _allSessions !== 'undefined' && _allSessions.find(s => s && s.session_id === S.session.session_id);
            if (_cached) _cached.title = newTitle;
          } catch (_) {}
          if (typeof renderSessionListFromCache === 'function') renderSessionListFromCache();
          try {
            await api('/api/session/rename', {
              method: 'POST',
              body: JSON.stringify({ session_id: S.session.session_id, title: newTitle })
            });
          } catch (err) {
            if (typeof setStatus === 'function') setStatus('Rename failed: ' + err.message);
          }
        }
        inp.replaceWith(titleEl);
        syncAppTitlebar();
      };

      inp.onkeydown = e2 => {
        if (e2.key === 'Enter') { e2.preventDefault(); e2.stopPropagation(); finish(true); }
        if (e2.key === 'Escape') { e2.preventDefault(); e2.stopPropagation(); finish(false); }
      };
      inp.onblur = () => finish(false);

      titleEl.replaceWith(inp);
      inp.focus();
      inp.select();
    };
  }

  // Dismiss stale popover on session/panel switch
  const _existingPop = document.querySelector('.app-titlebar-title-popover');
  if (_existingPop) {
    _existingPop.remove(); titleEl._titlePopover = null;
    if (titleEl._popoverOutsideHandler) {
      document.removeEventListener('click', titleEl._popoverOutsideHandler, true);
      titleEl._popoverOutsideHandler = null;
    }
  }

  // Mobile touch interactions
  if ('ontouchstart' in window) {
    // Tap-to-reveal full title popover — wired once per element lifetime
    if (!titleEl._mobileTouchWired) {
      titleEl._mobileTouchWired = true;
      titleEl._titlePopover = null;
      const _dismissTitlePopover = () => {
        if (titleEl._titlePopover) { titleEl._titlePopover.remove(); titleEl._titlePopover = null; }
        if (titleEl._popoverOutsideHandler) {
          document.removeEventListener('click', titleEl._popoverOutsideHandler, true);
          titleEl._popoverOutsideHandler = null;
        }
      };
      titleEl.addEventListener('click', function _onTitleClick(e) {
        if (_renamingAppTitlebar) return;
        if (titleEl._titlePopover) {
          _dismissTitlePopover();
          return;
        }
        e.stopPropagation();
        const pop = document.createElement('div');
        pop.className = 'app-titlebar-title-popover';
        pop.textContent = (S && S.session && S.session.title) ||
          (typeof t === 'function' ? t('untitled') : 'Untitled');
        document.body.appendChild(pop);
        const rect = titleEl.getBoundingClientRect();
        pop.style.top = (rect.bottom + 6) + 'px';
        pop.style.left = Math.max(8, rect.left) + 'px';
        pop.style.maxWidth = (window.innerWidth - 16) + 'px';
        titleEl._titlePopover = pop;
        const _outside = titleEl._popoverOutsideHandler = (ev) => {
          if (!pop.contains(ev.target) && ev.target !== titleEl) {
            _dismissTitlePopover();
            document.removeEventListener('click', _outside, true);
            titleEl._popoverOutsideHandler = null;
          }
        };
        setTimeout(() => document.addEventListener('click', _outside, true), 0);
      }, { passive: true });
    }

    // Long-press → session action menu (re-evaluated each sync so late-arriving sessions attach)
    if (!titleEl._mobileLpWired && panel === 'chat' && S && S.session &&
        !S.session.read_only && !S.session.is_read_only &&
        typeof _openSessionActionMenu === 'function') {
      titleEl._mobileLpWired = true;
      let _lpTimer = null;
      let _lpHandled = false;
      let _lpStartX = 0, _lpStartY = 0;
      const _lpDelay = typeof SESSION_LONG_PRESS_DELAY_MS !== 'undefined' ?
        SESSION_LONG_PRESS_DELAY_MS : 400;
      titleEl.addEventListener('touchstart', (e) => {
        const touch = e.changedTouches && e.changedTouches[0];
        if (!touch) return;
        if (_lpTimer) { clearTimeout(_lpTimer); _lpTimer = null; }
        _lpHandled = false; _lpStartX = touch.clientX; _lpStartY = touch.clientY;
        titleEl.classList.add('long-pressing');
        _lpTimer = setTimeout(() => {
          _lpTimer = null;
          if (_lpHandled) return;
          _lpHandled = true;
          titleEl.classList.remove('long-pressing');
          _openSessionActionMenu(S.session, titleEl);
        }, _lpDelay);
      }, { passive: true });
      titleEl.addEventListener('touchmove', (e) => {
        if (!_lpTimer) return;
        const touch = e.changedTouches && e.changedTouches[0];
        if (!touch) return;
        if (Math.abs(touch.clientX - _lpStartX) > 10 || Math.abs(touch.clientY - _lpStartY) > 10) {
          clearTimeout(_lpTimer); _lpTimer = null;
          titleEl.classList.remove('long-pressing');
        }
      }, { passive: true });
      titleEl.addEventListener('touchend', (e) => {
        clearTimeout(_lpTimer); _lpTimer = null;
        titleEl.classList.remove('long-pressing');
        if (_lpHandled) { e.preventDefault(); e.stopPropagation(); }
      }, { passive: false });
      titleEl.addEventListener('touchcancel', () => {
        clearTimeout(_lpTimer); _lpTimer = null; _lpHandled = false;
        titleEl.classList.remove('long-pressing');
      }, { passive: true });
    }
  }
}

function _beginSettingsPanelSession() {
  _settingsIndex = null;
  _settingsIndexPromise = null;
  // Invalidate any in-flight search render from a PRIOR Settings session and
  // reset the search UI, so a slow index build that resolves after the panel
  // was closed/reopened can't paint stale results into the dropdown. #4340
  // review fix (filterSettings() bails when its captured seq != current).
  ++_settingsSearchSeq;
  const _searchInput = $('settingsSearch');
  if (_searchInput) _searchInput.value = '';
  const _searchResults = $('settingsSearchResults');
  if (_searchResults) {
    _searchResults.style.display = 'none';
    _searchResults.innerHTML = '';
  }
  _settingsDirty = false;
  _settingsThemeOnOpen = localStorage.getItem('hermes-theme') || 'dark';
  _settingsSkinOnOpen = localStorage.getItem('hermes-skin') || 'default';
  _settingsFontSizeOnOpen = localStorage.getItem('hermes-font-size') || 'default';
  _pendingSettingsTargetPanel = null;
  if (_settingsAppearanceAutosaveTimer) {
    clearTimeout(_settingsAppearanceAutosaveTimer);
    _settingsAppearanceAutosaveTimer = null;
  }
  _settingsAppearanceAutosaveRetryPayload = null;
  if (!_settingsSearchDismissListenerRegistered) {
    _settingsSearchDismissListenerRegistered = true;
    document.addEventListener('click', e => {
      if (!e.target.closest('#settingsMenu')) {
        // Invalidate an in-flight first-build too, so it can't resurrect the
        // dropdown after an outside-click dismiss. #4340 review fix.
        ++_settingsSearchSeq;
        const r = $('settingsSearchResults');
        if (r) {
          r.style.display = 'none';
          r.innerHTML = '';
        }
      }
    });
  }
  _resetSettingsPanelState();
}

function _beforePanelSwitch(nextPanel) {
  if (_currentPanel !== 'settings' || nextPanel === 'settings') return true;
  if (_settingsDirty) {
    _pendingSettingsTargetPanel = nextPanel || 'chat';
    _showSettingsUnsavedBar();
    return false;
  }
  _revertSettingsPreview();
  _pendingSettingsTargetPanel = null;
  _resetSettingsPanelState();
  return true;
}

function _consumeSettingsTargetPanel(fallback = 'chat') {
  const target = (_pendingSettingsTargetPanel && _pendingSettingsTargetPanel !== 'settings')
    ? _pendingSettingsTargetPanel
    : fallback;
  _pendingSettingsTargetPanel = null;
  return target;
}

function _resyncChatSidebarAfterPanelSwitch() {
  if (_currentPanel !== 'chat') return;
  if (typeof renderSessionListFromCache !== 'function') return;
  const run = () => {
    if (_currentPanel !== 'chat') return;
    if (typeof _renamingSid !== 'undefined' && _renamingSid) return;
    // If the user opens the per-conversation action menu immediately after
    // returning to Chat, do not let the deferred sidebar resync tear it down.
    // renderSessionListFromCache() intentionally closes that menu before it
    // rebuilds rows, which is correct for normal list refreshes but hostile to
    // this one-shot panel-transition repair.
    if (typeof _sessionActionMenu !== 'undefined' && _sessionActionMenu) return;
    renderSessionListFromCache();
  };
  if (typeof requestAnimationFrame === 'function') requestAnimationFrame(run);
  else run();
}

function _closeMobileSidebarAfterPanelSelection(){
  if(typeof closeMobileSidebar!=='function')return;
  if(typeof _isDesktopWidth==='function'&&_isDesktopWidth())return;
  closeMobileSidebar();
}

function _panelFromCurrentMainView(){
  const mainEl=document.querySelector('main.main');
  if(!mainEl)return _currentPanel||'chat';
  for(const panel of MAIN_VIEW_PANELS){
    if(mainEl.classList.contains('showing-'+panel))return MAIN_VIEW_SIDEBAR_PANEL_FALLBACKS[panel]||panel;
  }
  if(_currentPanel&&$('panel'+_currentPanel.charAt(0).toUpperCase()+_currentPanel.slice(1)))return _currentPanel;
  return 'chat';
}

function _syncMobileSidebarPanelFromMainView(){
  const panel=_panelFromCurrentMainView();
  if(!panel)return _currentPanel||'chat';
  const panelEl=$('panel'+panel.charAt(0).toUpperCase()+panel.slice(1));
  if(!panelEl)return _currentPanel||'chat';
  _currentPanel=panel;
  document.querySelectorAll('[data-panel]').forEach(t=>t.classList.toggle('active',t.dataset.panel===panel));
  document.querySelectorAll('.panel-view').forEach(p=>p.classList.remove('active'));
  panelEl.classList.add('active');
  return panel;
}

async function switchPanel(name, opts = {}) {
  const nextPanel = name || 'chat';
  const prevPanel = _currentPanel;
  // ── Desktop sidebar collapse toggle (rail-click only) ──
  // If the click came from a rail icon AND we're on desktop, the rail icon
  // does double duty: clicking the already-active panel collapses the sidebar;
  // clicking any panel while collapsed expands first. Programmatic switches
  // (no opts.fromRailClick) are unaffected so legacy callers preserve
  // behaviour exactly.
  if (opts.fromRailClick && typeof _isSidebarCollapsed === 'function'
      && typeof _isDesktopWidth === 'function' && _isDesktopWidth()) {
    if (_isSidebarCollapsed()) {
      // Expand first, then continue to the normal panel switch below so
      // the clicked panel becomes (or stays) active in the same gesture.
      expandSidebar();
    } else if (prevPanel === nextPanel) {
      // Same panel clicked while sidebar is open → collapse and short-circuit.
      // Skip the guard/cleanup work below; nothing about the active panel
      // is changing, only the visibility of the panel container.
      toggleSidebar(true);
      return false;
    }
  }
  if (!opts.bypassSettingsGuard && !_beforePanelSwitch(nextPanel)) return false;
  if (prevPanel !== 'settings' && nextPanel === 'settings') _beginSettingsPanelSession();
  // Close any long-lived Kanban SSE stream when leaving the kanban panel
  // so we don't keep a stale connection open in the background.
  if (prevPanel === 'kanban' && nextPanel !== 'kanban') {
    if (typeof _kanbanStopPolling === 'function') _kanbanStopPolling();
  }
  _currentPanel = nextPanel;
  // Update nav tabs (rail + mobile sidebar-nav share data-panel)
  document.querySelectorAll('[data-panel]').forEach(t => t.classList.toggle('active', t.dataset.panel === nextPanel));
  // Refresh aria-expanded on the newly-active rail button to mirror sidebar state.
  if (typeof _syncSidebarAria === 'function') _syncSidebarAria();
  // Update panel views
  document.querySelectorAll('.panel-view').forEach(p => p.classList.remove('active'));
  const panelEl = $('panel' + nextPanel.charAt(0).toUpperCase() + nextPanel.slice(1));
  if (panelEl) panelEl.classList.add('active');
  // Update main content view. Each entry in MAIN_VIEW_PANELS gets a matching
  // showing-<name> class on <main>; no class means chat (the default).
  const mainEl = document.querySelector('main.main');
  if (mainEl) {
    MAIN_VIEW_PANELS.forEach(p => {
      mainEl.classList.toggle('showing-' + p, nextPanel === p);
    });
  }
  // Lazy-load panel data
  if (nextPanel === 'tasks') await loadCrons();
  if (nextPanel === 'kanban') await loadKanban();
  if (nextPanel === 'skills') await loadSkills();
  if (nextPanel === 'agents') await loadAgentDefinitions();
  if (nextPanel === 'memory') await loadMemory();
  if (nextPanel === 'knowledge') await loadKnowledgeItems();
  if (nextPanel === 'workspaces') await loadWorkspacesPanel();
  if (nextPanel === 'profiles') await loadProfilesPanel();
  if (nextPanel === 'todos') loadTodos();
  if (nextPanel === 'insights') await loadInsights();
  if (nextPanel === 'analytics') await loadAnalytics();
  if (nextPanel === 'logs') await loadLogs();
  if (nextPanel === 'audit') await loadAuditTrail();
  _syncLogsAutoRefresh();
  if (typeof _syncSystemHealthMonitorVisibility === 'function') _syncSystemHealthMonitorVisibility();
  if (nextPanel === 'settings') {
    switchSettingsSection(_currentSettingsSection);
    loadSettingsPanel();
  }
  if (opts.fromRailClick && typeof _isDesktopWidth === 'function' && !_isDesktopWidth()) {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
      sidebar.classList.remove('mobile-session-page');
      sidebar.classList.add('mobile-panel-drawer', 'mobile-open');
    }
  }
  _resyncChatSidebarAfterPanelSwitch();
  if (nextPanel === 'chat' && typeof syncTopbar === 'function') syncTopbar();
  else syncAppTitlebar();
  return true;
}

// ── Cron panel ──
function _isRecurringCronJob(job) {
  const kind = job && job.schedule && job.schedule.kind;
  return kind === 'cron' || kind === 'interval';
}

function _cronScheduleKindForInput(value) {
  const schedule = String(value || '').trim();
  if (!schedule) return '';
  const lower = schedule.toLowerCase();
  if (lower.startsWith('every ')) return 'interval';
  if (lower.startsWith('@')) return 'cron';
  const parts = schedule.split(/\s+/);
  if (parts.length >= 5 && parts.slice(0, 5).every(p => /^[\d*\-,/]+$/.test(p))) return 'cron';
  if (schedule.includes('T') || /^\d{4}-\d{2}-\d{2}/.test(schedule)) return 'once';
  if (/^\d+\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)$/i.test(schedule)) return 'once';
  return '';
}

function _syncCronScheduleWarning() {
  const input = $('cronFormSchedule');
  const warning = $('cronFormScheduleOnceWarning');
  if (!input || !warning) return;
  warning.style.display = _cronScheduleKindForInput(input.value) === 'once' ? '' : 'none';
  _syncCronSchedulePreview();
}

// Live preview of the generated cron expression in the preset hint line (the
// cron-job.org / GitHub-schedule-editor convention) so a cron-literate user sees
// exactly what the friendly controls produce. Empty on Custom (the raw field is shown).
function _syncCronSchedulePreview() {
  const preview = $('cronFormSchedulePreview');
  const presetEl = $('cronFormSchedulePreset');
  const scheduleEl = $('cronFormSchedule');
  if (!preview) return;
  const presetId = presetEl ? presetEl.value : 'custom';
  const expr = String((scheduleEl && scheduleEl.value) || '').trim();
  preview.textContent = (presetId !== 'custom' && expr) ? `${expr} · ` : '';
}

const CRON_SCHEDULE_PRESETS = [
  { id: 'hourly', label: 'cron_schedule_preset_hourly', fallback: 'Hourly', fields: ['minute'], defaults: { minute: 0 } },
  { id: 'daily', label: 'cron_schedule_preset_daily', fallback: 'Daily', fields: ['time'], defaults: { hour: 9, minute: 0 } },
  { id: 'weekdays', label: 'cron_schedule_preset_weekdays', fallback: 'Weekdays (Mon–Fri)', fields: ['time'], defaults: { hour: 9, minute: 0 } },
  { id: 'weekly', label: 'cron_schedule_preset_weekly', fallback: 'Weekly', fields: ['weekday', 'time'], defaults: { hour: 9, minute: 0, weekday: 1 } },
  { id: 'monthly', label: 'cron_schedule_preset_monthly', fallback: 'Monthly', fields: ['monthDay', 'time'], defaults: { hour: 9, minute: 0, monthDay: 1 } },
  { id: 'custom', label: 'cron_schedule_preset_custom', fallback: 'Custom', fields: [] },
];

function _cronSchedulePresetOptionHtml() {
  return CRON_SCHEDULE_PRESETS
    .map((preset) => `<option value="${preset.id}">${esc(t(preset.label) || preset.fallback)}</option>`)
    .join('');
}

function _cronSchedulePresetForId(presetId) {
  return CRON_SCHEDULE_PRESETS.find((entry) => entry.id === presetId) || null;
}

function _cronSchedulePresetControlIds() {
  return {
    time: 'cronFormScheduleTime',
    minute: 'cronFormScheduleMinute',
    weekday: 'cronFormScheduleWeekday',
    monthDay: 'cronFormScheduleMonthDay',
  };
}

// Which visible control wrapper each logical field lives in. `hour`+`minute` for
// time-based presets share the single #cronFormScheduleTime picker (in the Time
// field); `minute` alone (Hourly) uses the standalone Minute field.
function _cronSchedulePresetFieldWrapId(field) {
  if (field === 'time' || field === 'hour') return 'cronFormScheduleTimeField';
  if (field === 'minute') return 'cronFormScheduleMinuteField';
  if (field === 'weekday') return 'cronFormScheduleWeekdayField';
  if (field === 'monthDay') return 'cronFormScheduleMonthDayField';
  return '';
}

function _cronSchedulePresetFieldId(field) {
  const ids = _cronSchedulePresetControlIds();
  return ids[field] || '';
}

function _cronSchedulePresetFieldEl(field) {
  const id = _cronSchedulePresetFieldId(field);
  return id ? $(id) : null;
}

function _cronSchedulePresetBounds(field) {
  if (field === 'hour') return { min: 0, max: 23 };
  if (field === 'minute') return { min: 0, max: 59 };
  if (field === 'weekday') return { min: 0, max: 6 };
  if (field === 'monthDay') return { min: 1, max: 31 };
  return { min: 0, max: 999 };
}

function _cronSchedulePresetNormalizeValue(field, value, fallback) {
  const bounds = _cronSchedulePresetBounds(field);
  const parsed = parseInt(String(value ?? '').trim(), 10);
  const fallbackParsed = parseInt(String(fallback ?? bounds.min).trim(), 10);
  const safeFallback = Number.isFinite(fallbackParsed) ? fallbackParsed : bounds.min;
  const n = Number.isFinite(parsed) ? parsed : safeFallback;
  return String(Math.min(bounds.max, Math.max(bounds.min, n)));
}

function _cronSchedulePresetValueForField(field, fallback) {
  // hour/minute for time-based presets come from the single #cronFormScheduleTime
  // picker ("HH:MM"); the standalone Minute box (Hourly) still reads directly.
  if (field === 'hour' || field === 'minute') {
    const timeEl = $('cronFormScheduleTime');
    const minuteBox = $('cronFormScheduleMinute');
    // Hourly uses the standalone minute box; if the Time picker isn't the visible
    // source for minute, prefer the minute box when it's the shown control.
    if (field === 'minute' && minuteBox && (!timeEl || _cronScheduleMinuteBoxIsActive())) {
      return _cronSchedulePresetNormalizeValue('minute', minuteBox.value, fallback);
    }
    if (timeEl && /^\d{1,2}:\d{2}$/.test(String(timeEl.value || '').trim())) {
      const [h, m] = String(timeEl.value).trim().split(':');
      return _cronSchedulePresetNormalizeValue(field, field === 'hour' ? h : m, fallback);
    }
    return _cronSchedulePresetNormalizeValue(field, fallback, fallback);
  }
  const el = _cronSchedulePresetFieldEl(field);
  const raw = el ? String(el.value || '').trim() : '';
  return _cronSchedulePresetNormalizeValue(field, raw, fallback);
}

// The standalone Minute box is the active minute source only for the Hourly preset
// (the only preset whose visible fields include a bare 'minute').
function _cronScheduleMinuteBoxIsActive() {
  const presetEl = $('cronFormSchedulePreset');
  return !!(presetEl && presetEl.value === 'hourly');
}

function _cronSchedulePresetRawFieldInBounds(field, value) {
  const raw = String(value || '').trim();
  if (!/^\d+$/.test(raw)) return false;
  const bounds = _cronSchedulePresetBounds(field);
  const parsed = parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed >= bounds.min && parsed <= bounds.max;
}

function _cronSchedulePresetApplyValues(values) {
  // Write hour/minute into the single time picker as zero-padded HH:MM.
  if (values.hour != null || values.minute != null) {
    const timeEl = $('cronFormScheduleTime');
    if (timeEl) {
      const h = _cronSchedulePresetNormalizeValue('hour', values.hour, values.hour ?? 9);
      const m = _cronSchedulePresetNormalizeValue('minute', values.minute, values.minute ?? 0);
      timeEl.value = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
    }
  }
  if (values.minute != null) {
    const minuteBox = $('cronFormScheduleMinute');
    if (minuteBox) minuteBox.value = _cronSchedulePresetNormalizeValue('minute', values.minute, values.minute);
  }
  ['weekday', 'monthDay'].forEach((field) => {
    const el = _cronSchedulePresetFieldEl(field);
    if (!el || values[field] == null) return;
    el.value = _cronSchedulePresetNormalizeValue(field, values[field], values[field]);
  });
}

function _cronSchedulePresetSyncVisibility(presetId) {
  const wrapper = $('cronFormSchedulePresetParams');
  const customRow = $('cronFormScheduleCustomRow');
  const preset = _cronSchedulePresetForId(presetId);
  const showFields = preset && Array.isArray(preset.fields) ? preset.fields : [];
  const isCustom = presetId === 'custom';
  // Preset param controls hide entirely on Custom; the raw cron expression row
  // shows ONLY on Custom (kept in the DOM as a hidden field otherwise).
  if (wrapper) wrapper.style.display = isCustom ? 'none' : '';
  if (customRow) customRow.style.display = isCustom ? '' : 'none';
  ['time', 'minute', 'weekday', 'monthDay'].forEach((field) => {
    const fieldWrap = $(_cronSchedulePresetFieldWrapId(field));
    if (fieldWrap) fieldWrap.style.display = showFields.includes(field) ? '' : 'none';
  });
}

function _cronSchedulePresetValuesForSelection(presetId) {
  const preset = _cronSchedulePresetForId(presetId);
  const defaults = (preset && preset.defaults) || {};
  if (presetId === 'hourly') {
    return { minute: _cronSchedulePresetValueForField('minute', defaults.minute) };
  }
  if (presetId === 'daily' || presetId === 'weekdays') {
    return {
      hour: _cronSchedulePresetValueForField('hour', defaults.hour),
      minute: _cronSchedulePresetValueForField('minute', defaults.minute),
    };
  }
  if (presetId === 'weekly') {
    return {
      hour: _cronSchedulePresetValueForField('hour', defaults.hour),
      minute: _cronSchedulePresetValueForField('minute', defaults.minute),
      weekday: _cronSchedulePresetValueForField('weekday', defaults.weekday),
    };
  }
  if (presetId === 'monthly') {
    return {
      hour: _cronSchedulePresetValueForField('hour', defaults.hour),
      minute: _cronSchedulePresetValueForField('minute', defaults.minute),
      monthDay: _cronSchedulePresetValueForField('monthDay', defaults.monthDay),
    };
  }
  return {};
}

function _cronSchedulePresetValueForSelection(presetId, selectedValues) {
  const values = selectedValues || _cronSchedulePresetValuesForSelection(presetId);
  if (presetId === 'hourly') return `${values.minute} * * * *`;
  if (presetId === 'daily') return `${values.minute} ${values.hour} * * *`;
  if (presetId === 'weekdays') return `${values.minute} ${values.hour} * * 1-5`;
  if (presetId === 'weekly') return `${values.minute} ${values.hour} * * ${values.weekday}`;
  if (presetId === 'monthly') return `${values.minute} ${values.hour} ${values.monthDay} * *`;
  return '';
}

function _cronSchedulePresetStateForInput(value) {
  const schedule = String(value || '').trim();
  if (!schedule) return { presetId: 'custom' };
  if (/^every\s+1h$/i.test(schedule)) {
    return { presetId: 'hourly', minute: '0' };
  }
  if (schedule.startsWith('@')) return { presetId: 'custom' };
  const parts = schedule.split(/\s+/);
  if (parts.length !== 5) return { presetId: 'custom' };
  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;
  if (!_cronSchedulePresetRawFieldInBounds('minute', minute)) return { presetId: 'custom' };
  if (_cronSchedulePresetRawFieldInBounds('hour', hour) && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
    return { presetId: 'daily', minute, hour };
  }
  if (_cronSchedulePresetRawFieldInBounds('hour', hour) && dayOfMonth === '*' && month === '*' && dayOfWeek === '1-5') {
    return { presetId: 'weekdays', minute, hour };
  }
  if (hour === '*' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
    return { presetId: 'hourly', minute };
  }
  if (_cronSchedulePresetRawFieldInBounds('hour', hour) && dayOfMonth === '*' && month === '*' && (_cronSchedulePresetRawFieldInBounds('weekday', dayOfWeek) || dayOfWeek === '7')) {
    return { presetId: 'weekly', minute, hour, weekday: dayOfWeek === '7' ? '0' : dayOfWeek };
  }
  if (_cronSchedulePresetRawFieldInBounds('hour', hour) && _cronSchedulePresetRawFieldInBounds('monthDay', dayOfMonth) && month === '*' && dayOfWeek === '*') {
    return { presetId: 'monthly', minute, hour, monthDay: dayOfMonth };
  }
  return { presetId: 'custom' };
}

function _cronSchedulePresetIdForValue(value) {
  return _cronSchedulePresetStateForInput(value).presetId;
}

function _syncCronSchedulePresetFromInput() {
  const presetEl = $('cronFormSchedulePreset');
  const scheduleEl = $('cronFormSchedule');
  if (!presetEl || !scheduleEl) return;
  const state = _cronSchedulePresetStateForInput(scheduleEl.value);
  presetEl.value = state.presetId;
  _cronSchedulePresetSyncVisibility(state.presetId);
  if (state.presetId !== 'custom') _cronSchedulePresetApplyValues(state);
}

function _syncCronSchedulePresetAndWarning() {
  _syncCronSchedulePresetFromInput();
  _syncCronScheduleWarning();
}

function _applyCronSchedulePresetSelection() {
  const presetEl = $('cronFormSchedulePreset');
  const scheduleEl = $('cronFormSchedule');
  if (!presetEl || !scheduleEl) return;
  const presetId = presetEl.value;
  if (presetId !== 'custom') {
    const values = _cronSchedulePresetValuesForSelection(presetId);
    _cronSchedulePresetApplyValues(values);
    scheduleEl.value = _cronSchedulePresetValueForSelection(presetId, values);
    _cronSchedulePresetSyncVisibility(presetId);
    _syncCronScheduleWarning();
    return;
  }
  _cronSchedulePresetSyncVisibility(presetId);
  _syncCronScheduleWarning();
}

// Regenerate the cron expression from the current field values WITHOUT writing the
// clamped values back into the field the user is editing — so typing into the Minute
// box (or the time picker) doesn't snap a half-entered value to the default/clamp
// mid-keystroke. Value clamping still happens on `change`/blur via the full apply.
function _regenCronScheduleFromFields() {
  const presetEl = $('cronFormSchedulePreset');
  const scheduleEl = $('cronFormSchedule');
  if (!presetEl || !scheduleEl) return;
  const presetId = presetEl.value;
  if (presetId === 'custom') return;
  scheduleEl.value = _cronSchedulePresetValueForSelection(presetId);
  _syncCronScheduleWarning();
}

function _initCronSchedulePresetControls() {
  const presetEl = $('cronFormSchedulePreset');
  const scheduleEl = $('cronFormSchedule');
  if (!presetEl || !scheduleEl) return;
  presetEl.addEventListener('change', _applyCronSchedulePresetSelection);
  if ($('cronFormSchedulePresetParams')) {
    ['cronFormScheduleTime', 'cronFormScheduleMinute', 'cronFormScheduleWeekday', 'cronFormScheduleMonthDay'].forEach((id) => {
      const el = $(id);
      if (!el) return;
      // On `change`/blur, clamp + normalize (writes values back). On `input`
      // (per-keystroke), only regenerate the expression — never rewrite the field
      // being typed into, so partial input like clearing Hour to type "14" isn't
      // snapped to the default (#5554 UX fix).
      el.addEventListener('change', _applyCronSchedulePresetSelection);
      el.addEventListener('input', _regenCronScheduleFromFields);
    });
  }
  // On raw-cron `input` (only reachable on Custom, where the raw row is shown),
  // update ONLY the warning + preview — do NOT re-detect the preset or sync
  // visibility, or a partial value momentarily matching a preset (e.g. typing
  // "0 9 * * 1,3" transiently equals Weekly's "0 9 * * 1") would switch the preset
  // and hide the focused raw field mid-keystroke (#5554). Preset re-detection runs
  // on initial render and on `change`/blur.
  scheduleEl.addEventListener('input', _syncCronScheduleWarning);
  scheduleEl.addEventListener('change', _syncCronSchedulePresetAndWarning);
  _syncCronSchedulePresetAndWarning();
}

function _hasUnlimitedRepeat(job) {
  return !!(job && job.repeat && job.repeat.times == null);
}

function _isCronNeedsAttention(job) {
  return _isRecurringCronJob(job) &&
    _hasUnlimitedRepeat(job) &&
    job.enabled === false &&
    job.state === 'completed' &&
    !job.next_run_at;
}

function _isCronScheduleError(job) {
  return _isRecurringCronJob(job) &&
    !job.next_run_at &&
    (job.state === 'error' || job.last_status === 'error');
}

function _cronStatusMeta(job) {
  if (_isCronNeedsAttention(job)) return {
    state: 'needs_attention',
    listClass: 'attention',
    detailClass: 'warn',
    label: t('cron_status_needs_attention'),
  };
  if (_isCronScheduleError(job)) return {
    state: 'schedule_error',
    listClass: 'attention',
    detailClass: 'warn',
    label: t('cron_status_needs_attention'),
  };
  if (job.state === 'paused') return {
    state: 'paused',
    listClass: 'paused',
    detailClass: 'warn',
    label: t('cron_status_paused'),
  };
  if (job.enabled === false) return {
    state: 'off',
    listClass: 'disabled',
    detailClass: 'warn',
    label: t('cron_status_off'),
  };
  if (job.last_status === 'error') return {
    state: 'error',
    listClass: 'error',
    detailClass: 'err',
    label: t('cron_status_error'),
  };
  return {
    state: 'active',
    listClass: 'active',
    detailClass: 'ok',
    label: t('cron_status_active'),
  };
}


function _cronProfileName(profile){
  return (profile || '').toString().trim();
}

function _cronProfileLabel(profile){
  const name = _cronProfileName(profile);
  return name || (t('cron_profile_server_default') || 'server default');
}

function _cronProfileTitle(profile){
  const name = _cronProfileName(profile);
  if (name) return (t('cron_profile_label') || 'Profile') + ': ' + name;
  return t('cron_profile_server_default_hint') || 'Uses the WebUI server default profile at run time';
}

function _cronOwnerProfileName(job){
  return _cronProfileName(job && (job.owner_profile ?? job.profile));
}

function _cronJobKey(job){
  return `${_cronOwnerProfileName(job)}\u0000${String(job && job.id || '')}`;
}

function _cronItemId(job){
  return 'cron-' + encodeURIComponent(_cronJobKey(job));
}

function _cronDetailMatches(jobId, detailKey){
  return !!(
    detailKey &&
    _currentCronDetail &&
    !_currentCronDetail.read_only &&
    String(_currentCronDetail.id) === String(jobId) &&
    _currentCronDetailKey === detailKey &&
    _cronJobKey(_currentCronDetail) === detailKey
  );
}

function _findCronJob(jobOrId){
  if (jobOrId && typeof jobOrId === 'object') return jobOrId;
  const id = String(jobOrId || '');
  if (!_cronList || !id) return null;
  return _cronList.find(j => !j.read_only && String(j.id) === id) ||
    _cronList.find(j => String(j.id) === id) ||
    null;
}

function _appendCronProfileToggle(parent){
  if (!parent || (!_showAllCronProfiles && _cronOtherProfileCount <= 0)) return;
  const wrap = document.createElement('div');
  wrap.style.cssText = 'padding:10px 0 0';
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'sm-btn';
  btn.style.cssText = 'width:100%;justify-content:center';
  btn.textContent = _showAllCronProfiles
    ? 'Show active profile only'
    : `Show ${_cronOtherProfileCount} from other profiles`;
  btn.onclick = async () => {
    _showAllCronProfiles = !_showAllCronProfiles;
    await loadCrons();
  };
  wrap.appendChild(btn);
  parent.appendChild(wrap);
}

async function loadCronProfiles(){
  if (_cronProfilesCache) return _cronProfilesCache;
  try {
    const data = await api('/api/profiles');
    _cronProfilesCache = Array.isArray(data.profiles) ? data.profiles : [];
  } catch(e) {
    _cronProfilesCache = [];
  }
  return _cronProfilesCache;
}

function _cronProfileOptions(selected){
  const current = _cronProfileName(selected);
  const profiles = Array.isArray(_cronProfilesCache) ? _cronProfilesCache : [];
  const seen = new Set(['']);
  const opts = [`<option value=""${current ? '' : ' selected'}>${esc(t('cron_profile_server_default') || 'server default')}</option>`];
  for (const p of profiles) {
    const name = _cronProfileName(p && p.name);
    if (!name || seen.has(name)) continue;
    seen.add(name);
    const label = p && p.is_default ? `${name} (${t('default') || 'default'})` : name;
    opts.push(`<option value="${esc(name)}"${current === name ? ' selected' : ''}>${esc(label)}</option>`);
  }
  if (current && !seen.has(current)) {
    opts.push(`<option value="${esc(current)}" selected>${esc(current)} (${esc(t('not_available') || 'not available')})</option>`);
  }
  return opts.join('');
}

function _refreshCronProfileSelect(selected){
  const sel = $('cronFormProfile');
  if (!sel) return;
  const keep = selected === undefined ? sel.value : selected;
  sel.innerHTML = _cronProfileOptions(keep);
}

function _cronDiagnostics(job) {
  const fields = {
    id: job.id,
    name: job.name || null,
    schedule: job.schedule || null,
    schedule_display: job.schedule_display || null,
    enabled: job.enabled,
    state: job.state,
    next_run_at: job.next_run_at || null,
    last_run_at: job.last_run_at || null,
    last_status: job.last_status || null,
    last_error: job.last_error || null,
    last_delivery_error: job.last_delivery_error || null,
    repeat: job.repeat || null,
    deliver: job.deliver || null,
  };
  return JSON.stringify(fields, null, 2);
}

function _gatewayStatusReason(status) {
  const health = status && typeof status.health === 'object' ? status.health : null;
  if (!health) return '';
  return typeof health.reason === 'string' ? health.reason.trim() : '';
}

function _cronGatewayNoticeHtml(status) {
  if (!status || (status.configured && status.running)) return '';
  const reason = _gatewayStatusReason(status);
  const isStaleMetadata = reason === 'gateway_stale_running_state';
  const isRemoteUnreachable = reason === 'remote_gateway_unreachable';
  const notConfigured = !status.configured;
  const title = notConfigured
    ? 'Gateway not configured'
    : isStaleMetadata
      ? 'Gateway metadata stale'
      : isRemoteUnreachable
        ? 'Gateway endpoint not reachable'
        : 'Gateway not running';
  const body = notConfigured
    ? 'In Hermes WebUI, scheduled jobs require the Hermes gateway daemon. If this is a single-container Docker install, jobs can be created and run manually here, but scheduled ticks need a gateway container or `hermes gateway` running outside the WebUI.'
    : isStaleMetadata
      ? 'The gateway is marked as configured, but its health metadata has gone stale. In Docker, scheduled jobs require a live gateway daemon that refreshes runtime metadata while ticking cron.'
      : isRemoteUnreachable
        ? 'The gateway health endpoint is not reachable from WebUI. Verify the configured gateway URL env var (`GATEWAY_HEALTH_URL`, `HERMES_GATEWAY_HEALTH_URL`, `HERMES_API_URL`, or `HERMES_WEBUI_GATEWAY_BASE_URL`) points to a reachable gateway service and network path before relying on cron ticking.'
        : 'In Hermes WebUI, scheduled jobs require the Hermes gateway daemon to be running. Start the gateway container or `hermes gateway` before relying on offline scheduled runs.';
  const docsHref = 'https://github.com/nesquena/hermes-webui/blob/master/docs/docker.md#scheduled-jobs-and-the-gateway-daemon';
  const helpLink = notConfigured || isRemoteUnreachable || isStaleMetadata
    ? `<p><a href="${docsHref}" target="_blank" rel="noopener">How to enable scheduled jobs in Docker ↗</a></p>`
    : '';
  return `
    <div class="detail-alert-title">${esc(title)}</div>
    <p>${esc(body)}</p>
    ${helpLink}
  `;
}

async function loadCronGatewayNotice() {
  const box = $('cronGatewayNotice');
  if (!box) return;
  try {
    const status = await api('/api/gateway/status');
    const html = _cronGatewayNoticeHtml(status);
    if (html) {
      box.innerHTML = html;
      box.style.display = '';
    } else {
      box.innerHTML = '';
      box.style.display = 'none';
    }
  } catch (_) {
    box.innerHTML = '';
    box.style.display = 'none';
  }
}

async function loadCrons(animate) {
  const box = $('cronList');
  const refreshBtn = $('cronRefreshBtn');
  loadCronGatewayNotice();
  if (animate && refreshBtn) {
    refreshBtn.style.opacity = '0.5';
    refreshBtn.disabled = true;
  }
  try {
    await loadCronProfiles();
    const allProfilesQS = _showAllCronProfiles ? '?all_profiles=1' : '';
    const data = await api('/api/crons' + allProfilesQS);
    _cronList = data.jobs || [];
    _cronOtherProfileCount = Number(data.other_profile_count || 0);
    if (_showAllCronProfiles && !_cronList.some(job => job && job.read_only)) {
      _showAllCronProfiles = false;
      _cronOtherProfileCount = 0;
    }
    box.innerHTML = '';
    // Partition active vs paused so paused jobs don't drown the list (#4026).
    // _cronList stays the single source of truth — only the render is split,
    // which keeps openCronDetail, _cronNewJobIds, and detail refresh untouched.
    const _activeJobs = [];
    const _pausedJobs = [];
    for (const job of _cronList) {
      const status = _cronStatusMeta(job);
      (status.state === 'paused' ? _pausedJobs : _activeJobs).push({ job, status });
    }
    const _appendCronItem = (parent, { job, status }) => {
      const item = document.createElement('div');
      item.className = 'cron-item';
      item.id = _cronItemId(job);
      if (job.read_only) {
        item.classList.add('readonly');
        item.style.opacity = '0.78';
      }
      const isNewRun = !job.read_only && _cronNewJobIds.has(String(job.id));
      const isAgentMode = !job.no_agent;
      const ownerProfileLabel = _cronProfileLabel(_cronOwnerProfileName(job));
      const ownerProfileTitle = `Owner profile: ${ownerProfileLabel}`;
      const readOnlyBadge = job.read_only
        ? '<span class="cron-status disabled" title="Read-only from another profile">Read-only</span>'
        : '';
      item.innerHTML = `
        <div class="cron-header">
          ${isNewRun ? '<span class="cron-new-dot" title="New run"></span>' : ''}
          ${isAgentMode ? '<span class="cron-agent-badge" title="Agent mode">🤖</span>' : `<span class="cron-script-badge" title="${esc(t('cron_script_badge_title') || 'Script job (no agent)')}">📜</span>`}
          <span class="cron-name" title="${esc(job.name)}">${esc(job.name)}</span>
          <span class="cron-profile-badge" title="${esc(ownerProfileTitle)}">${esc(ownerProfileLabel)}</span>
          <span class="cron-status ${status.listClass}">${esc(status.label)}</span>
          ${readOnlyBadge}
        </div>`;
      item.onclick = () => openCronDetail(job, item);
      if (_currentCronDetailKey && _currentCronDetailKey === _cronJobKey(job)) item.classList.add('active');
      parent.appendChild(item);
    };
    if (!_cronList.length) {
      const emptyText = (!_showAllCronProfiles && _cronOtherProfileCount > 0)
        ? 'No cron jobs in the active profile.'
        : (t('cron_no_jobs') || 'No jobs yet');
      box.innerHTML = `<div style="padding:16px;color:var(--muted);font-size:12px">${esc(emptyText)}</div>`;
      _appendCronProfileToggle(box);
      if (_cronMode !== 'create' && _cronMode !== 'edit') _clearCronDetail();
      return;
    }
    for (const entry of _activeJobs) _appendCronItem(box, entry);
    if (_pausedJobs.length) {
      let collapsed = true;
      try { collapsed = localStorage.getItem('cron-paused-collapsed') !== '0'; } catch (_e) {}
      const details = document.createElement('details');
      details.className = 'cron-paused-section';
      if (!collapsed) details.open = true;
      const pausedLabel = t('cron_status_paused') || 'paused';
      const headerLabel = pausedLabel.charAt(0).toUpperCase() + pausedLabel.slice(1);
      const summary = document.createElement('summary');
      summary.className = 'cron-paused-summary';
      summary.textContent = `${headerLabel} (${_pausedJobs.length})`;
      details.appendChild(summary);
      details.addEventListener('toggle', () => {
        try { localStorage.setItem('cron-paused-collapsed', details.open ? '0' : '1'); } catch (_e) {}
      });
      const inner = document.createElement('div');
      inner.className = 'cron-paused-inner';
      details.appendChild(inner);
      for (const entry of _pausedJobs) _appendCronItem(inner, entry);
      box.appendChild(details);
    }
    _appendCronProfileToggle(box);
    // Re-render current detail with fresh data if we have one and we're not in a form
    if (_currentCronDetail && _cronMode !== 'create' && _cronMode !== 'edit') {
      const refreshed = _cronList.find(j => _cronJobKey(j) === _currentCronDetailKey);
      if (refreshed) _renderCronDetail(refreshed);
      else _clearCronDetail();
    }
  } catch(e) { box.innerHTML = `<div style="padding:12px;color:var(--accent);font-size:12px">${esc(t('error_prefix'))}${esc(e.message)}</div>`; }
  finally {
    if (animate && refreshBtn) {
      refreshBtn.style.opacity = '';
      refreshBtn.disabled = false;
    }
  }
}

function _cronPanelExpandKey(jobId, suffix){
  return `hermes-webui-cron-${suffix}-expanded-${encodeURIComponent(String(jobId||''))}`;
}

function _cronRunExpandKey(jobId, filename){
  return `${_cronPanelExpandKey(jobId, 'run')}-${encodeURIComponent(String(filename||''))}`;
}

function _cronExpansionGet(key){
  try { return localStorage.getItem(key) === '1'; } catch(_) { return false; }
}

function _cronExpansionSet(key, expanded){
  try { localStorage.setItem(key, expanded ? '1' : '0'); } catch(_) {}
}

function toggleCronPromptExpanded(jobId){
  const key = _cronPanelExpandKey(jobId, 'prompt');
  _cronExpansionSet(key, !_cronExpansionGet(key));
  if (_currentCronDetail && String(_currentCronDetail.id) === String(jobId)) {
    _renderCronDetail(_currentCronDetail);
  }
}

function toggleCronRunExpanded(jobId, filename, runId){
  const key = _cronRunExpandKey(jobId, filename);
  const expanded = !_cronExpansionGet(key);
  _cronExpansionSet(key, expanded);
  const item = document.getElementById(runId);
  const body = item ? item.querySelector('.detail-run-body') : null;
  const btn = item ? item.querySelector('.detail-expand-toggle') : null;
  if (body) body.classList.toggle('expanded', expanded);
  if (btn) {
    btn.textContent = expanded ? '▴' : '▾';
    btn.title = expanded ? (t('cron_collapse_output') || 'Collapse output') : (t('cron_expand_output') || 'Expand output');
    btn.setAttribute('aria-label', btn.title);
  }
}

function _isCronScriptJob(job){
  return !!(job && job.no_agent);
}

function _cronModeLabel(job){
  return _isCronScriptJob(job)
    ? (t('cron_mode_script') || 'Script')
    : (t('cron_mode_agent') || 'Agent');
}

function _cronOutputTitle(job){
  return _isCronScriptJob(job)
    ? (t('cron_script_output') || 'Script output')
    : (t('cron_last_output') || 'Last output');
}

function _cronScriptJobBannerHtml(){
  return `<div class="detail-alert cron-script-job-banner">
        <div class="detail-alert-title">${esc(t('cron_mode_script') || 'Script')}</div>
        <p>${esc(t('cron_script_job_banner') || 'Runs a script on schedule — stdout is delivered to the target. No agent, prompt, or skills.')}</p>
      </div>`;
}

function _cronScriptCardHtml(job){
  const script = String(job && job.script || '').trim() || '—';
  const workdir = String(job && job.workdir || '').trim();
  const workdirRow = workdir
    ? `<div class="detail-row"><div class="detail-row-label">${esc(t('cron_workdir_label') || 'Working directory')}</div><div class="detail-row-value"><code>${esc(workdir)}</code></div></div>`
    : '';
  return `<div class="detail-card cron-script-card">
        <div class="detail-card-title">${esc(t('cron_script_card_title') || 'Script')}</div>
        <div class="detail-script">${esc(script)}</div>
        ${workdirRow}
        <div class="detail-hint cron-script-card-hint">${esc(t('cron_script_path_hint') || 'Resolved under ~/.hermes/scripts/ unless an absolute path. Edit the script file on the server to change behavior.')}</div>
      </div>`;
}

function _cronAgentPromptCardHtml(job){
  const promptExpanded = _cronExpansionGet(_cronPanelExpandKey(job.id, 'prompt'));
  const promptToggleLabel = promptExpanded ? (t('cron_collapse_prompt') || 'Collapse prompt') : (t('cron_expand_prompt') || 'Expand prompt');
  return `<div class="detail-card">
        <div class="detail-card-title detail-card-title-row">
          <span>${esc(t('cron_prompt_label') || 'Prompt')}</span>
          <button type="button" class="detail-expand-toggle" onclick="toggleCronPromptExpanded('${esc(job.id)}')" title="${esc(promptToggleLabel)}" aria-label="${esc(promptToggleLabel)}">${esc(promptExpanded ? '▴' : '▾')}</button>
        </div>
        <div class="detail-prompt ${promptExpanded ? 'expanded' : ''}">${esc(job.prompt || '')}</div>
      </div>`;
}

function _renderCronDetail(job){
  _currentCronDetail = job;
  _currentCronDetailKey = _cronJobKey(job);
  const title = $('taskDetailTitle');
  const body = $('taskDetailBody');
  const empty = $('taskDetailEmpty');
  if (!title || !body) return;
  title.textContent = job.name || job.schedule_display || '(unnamed)';
  const status = _cronStatusMeta(job);
  const nextRun = job.next_run_at ? new Date(job.next_run_at).toLocaleString() : t('not_available');
  const lastRun = job.last_run_at ? new Date(job.last_run_at).toLocaleString() : t('never');
  const schedule = job.schedule_display || (job.schedule && job.schedule.expression) || '';
  const skills = Array.isArray(job.skills) && job.skills.length ? job.skills.join(', ') : '—';
  const deliver = job.deliver || 'local';
  const isNoAgent = _isCronScriptJob(job);
  const isReadOnly = !!job.read_only;
  const cronJobMode = _cronModeLabel(job);
  const modelProvider =
    job.provider && job.model ? `${esc(job.provider)}/${esc(job.model)}` :
    job.model ? esc(job.model) :
    job.provider ? esc(job.provider) :
    isNoAgent ? '' : esc(t('cron_model_use_default') || 'Use profile default');
  const profileLabel = _cronProfileLabel(job.profile);
  const profileTitle = _cronProfileTitle(job.profile);
  const ownerProfileName = _cronOwnerProfileName(job);
  const ownerProfileLabel = _cronProfileLabel(ownerProfileName);
  const ownerProfileTitle = `Owner profile: ${ownerProfileLabel}`;
  const showOwnerRow = !!ownerProfileName && (isReadOnly || ownerProfileName !== _cronProfileName(job.profile));
  const lastError = job.last_error ? `<div class="detail-row"><div class="detail-row-label">${esc(t('error_prefix').replace(/:\s*$/,''))}</div><div class="detail-row-value" style="color:var(--accent-text)">${esc(job.last_error)}</div></div>` : '';
  const attention = status.state === 'needs_attention' || status.state === 'schedule_error';
  const croniterHint = job.last_error && /croniter/i.test(job.last_error)
    ? `<p>${esc(t('cron_attention_croniter_hint'))}</p>`
    : '';
  const attentionBanner = !isReadOnly && attention ? `
      <div class="detail-alert cron-attention-panel">
        <div class="detail-alert-title">${esc(t('cron_status_needs_attention'))}</div>
        <p>${esc(t('cron_attention_desc'))}</p>
        ${croniterHint}
        <div class="detail-alert-actions">
          <button type="button" class="cron-btn run" onclick="resumeCurrentCron()">${esc(t('cron_attention_resume'))}</button>
          <button type="button" class="cron-btn" onclick="runCurrentCron()">${esc(t('cron_attention_run_once'))}</button>
          <button type="button" class="cron-btn" onclick="copyCurrentCronDiagnostics()">${esc(t('cron_attention_copy_diagnostics'))}</button>
        </div>
      </div>` : '';
  const readOnlyBanner = isReadOnly ? `
      <div class="detail-alert">
        <div class="detail-alert-title">Read-only from another profile</div>
        <p>Switch to ${esc(ownerProfileLabel)} to run, edit, or inspect live status and output for this cron job.</p>
      </div>` : '';
  const toastNotifications = job.toast_notifications !== false;
  const outputTitle = _cronOutputTitle(job);
  const skillsRow = isNoAgent ? '' : `<div class="detail-row"><div class="detail-row-label">${esc(t('cron_skills_label') || 'Skills')}</div><div class="detail-row-value">${esc(skills)}</div></div>`;
  const instructionCard = isNoAgent ? _cronScriptCardHtml(job) : _cronAgentPromptCardHtml(job);
  body.innerHTML = `
    <div class="main-view-content">
      ${attentionBanner}
      ${readOnlyBanner}
      ${isNoAgent ? _cronScriptJobBannerHtml() : ''}
      <div class="detail-card">
        <div class="detail-card-title">${esc(t('cron_status_active').replace(/./,c=>c.toUpperCase()))}</div>
        <div class="detail-row"><div class="detail-row-label">Status</div><div class="detail-row-value"><span class="detail-badge ${status.detailClass}">${esc(status.label)}</span></div></div>
        <div class="detail-row"><div class="detail-row-label">Schedule</div><div class="detail-row-value"><code>${esc(schedule)}</code></div></div>
        <div class="detail-row"><div class="detail-row-label">${esc(t('cron_next'))}</div><div class="detail-row-value">${esc(nextRun)}</div></div>
        <div class="detail-row"><div class="detail-row-label">${esc(t('cron_last'))}</div><div class="detail-row-value">${esc(lastRun)}</div></div>
        <div class="detail-row"><div class="detail-row-label">Deliver</div><div class="detail-row-value">${esc(deliver)}</div></div>
        <div class="detail-row"><div class="detail-row-label">${esc(t('cron_mode_label') || 'Mode')}</div><div class="detail-row-value"><span class="detail-badge cron-mode-badge ${isNoAgent ? 'script' : 'agent'}" id="cronJobMode">${esc(cronJobMode)}</span>${modelProvider ? ` <code>${modelProvider}</code>` : ''}</div></div>
        ${showOwnerRow ? `<div class="detail-row"><div class="detail-row-label">Owner profile</div><div class="detail-row-value"><span class="detail-badge active" title="${esc(ownerProfileTitle)}">${esc(ownerProfileLabel)}</span></div></div>` : ''}
        <div class="detail-row"><div class="detail-row-label">${esc(t('cron_profile_label') || 'Profile')}</div><div class="detail-row-value"><span class="detail-badge active" title="${esc(profileTitle)}">${esc(profileLabel)}</span></div></div>
        <div class="detail-row"><div class="detail-row-label">${esc(t('cron_toast_notifications_label') || 'Completion toasts')}</div><div class="detail-row-value"><span class="detail-badge ${toastNotifications ? 'active' : ''}">${esc(toastNotifications ? (t('cron_toast_notifications_enabled') || 'Enabled') : (t('cron_toast_notifications_disabled') || 'Disabled'))}</span></div></div>
        ${skillsRow}
        ${lastError}
      </div>
      ${instructionCard}
      <div class="detail-card ${!isReadOnly && _cronNewJobIds.has(String(job.id)) ? 'has-new-run' : ''}" id="cronDetailRuns">
        <div class="detail-card-title">${esc(outputTitle)}</div>
        <div style="color:var(--muted);font-size:12px">${esc(isReadOnly ? 'Live output is available only when this profile is active here.' : (t('loading') || 'Loading'))}</div>
      </div>
    </div>`;
  body.style.display = '';
  if (empty) empty.style.display = 'none';
  _cronMode = 'read';
  _setCronHeaderButtons('read', job);
  // Load runs asynchronously
  if (!isReadOnly) _loadCronDetailRuns(job.id, _currentCronDetailKey);
}

function _setCronHeaderButtons(mode, job) {
  const runBtn = $('btnRunTaskDetail');
  const pauseBtn = $('btnPauseTaskDetail');
  const resumeBtn = $('btnResumeTaskDetail');
  const editBtn = $('btnEditTaskDetail');
  const dupBtn = $('btnDuplicateTaskDetail');
  const delBtn = $('btnDeleteTaskDetail');
  const cancelBtn = $('btnCancelTaskDetail');
  const saveBtn = $('btnSaveTaskDetail');
  const header = $('mainTasks') && $('mainTasks').querySelector('.main-view-header');
  const hide = b => b && (b.style.display = 'none');
  const show = b => b && (b.style.display = '');
  if (mode === 'read') {
    if (header) header.style.display = 'flex';
    if (job && job.read_only) {
      [runBtn,pauseBtn,resumeBtn,editBtn,dupBtn,delBtn,cancelBtn,saveBtn].forEach(hide);
      return;
    }
    show(runBtn);
    const status = job ? _cronStatusMeta(job) : null;
    const resumable = job && (
      job.state === 'paused' ||
      (status && (status.state === 'needs_attention' || status.state === 'schedule_error'))
    );
    if (resumable) { hide(pauseBtn); show(resumeBtn); }
    else { show(pauseBtn); hide(resumeBtn); }
    show(editBtn); show(dupBtn); show(delBtn); hide(cancelBtn); hide(saveBtn);
  } else if (mode === 'create' || mode === 'edit') {
    if (header) header.style.display = 'flex';
    hide(runBtn); hide(pauseBtn); hide(resumeBtn); hide(editBtn); hide(dupBtn); hide(delBtn);
    show(cancelBtn); show(saveBtn);
  } else {
    [runBtn,pauseBtn,resumeBtn,editBtn,dupBtn,delBtn,cancelBtn,saveBtn].forEach(hide);
    if (header) header.style.display = 'none';
  }
}

async function _loadCronDetailRuns(jobId, detailKey){
  try {
    const data = await api(`/api/crons/history?job_id=${encodeURIComponent(jobId)}&limit=50`);
    if (!_cronDetailMatches(jobId, detailKey)) return;
    const card = $('cronDetailRuns');
    if (!card) return;
    const outputTitle = _cronOutputTitle(_currentCronDetail);
    const isScriptJob = _isCronScriptJob(_currentCronDetail);
    if (!data.runs || !data.runs.length) {
      card.innerHTML = `<div class="detail-card-title">${esc(outputTitle)}</div><div style="color:var(--muted);font-size:12px">${esc(t('cron_no_runs_yet'))}</div>`;
      return;
    }
    const rows = data.runs.map((run, i) => {
      const ts = run.filename.replace('.md','').replace(/_/g,' ');
      const sizeStr = run.size > 1024 ? (run.size/1024).toFixed(1)+' KB' : run.size+' B';
      const dateStr = new Date(run.modified * 1000).toLocaleString();
      const rid = `cron-det-run-${jobId}-${i}`;
      const usageStrip = isScriptJob ? '' : _formatCronRunUsageStrip(run.usage);
      const runExpanded = _cronExpansionGet(_cronRunExpandKey(jobId, run.filename));
      const runToggleLabel = runExpanded ? (t('cron_collapse_output') || 'Collapse output') : (t('cron_expand_output') || 'Expand output');
      return `<div class="detail-run-item" id="${rid}">
        <div class="detail-run-head" onclick="_loadRunContent('${esc(jobId)}','${esc(run.filename)}','${rid}')">
          <span><span style="opacity:.7">${esc(ts)}</span> <span style="opacity:.4;font-size:11px">${esc(sizeStr)}</span>${usageStrip ? ` <span class="cron-run-usage-strip">${esc(usageStrip)}</span>` : ''}</span>
          <span class="detail-run-actions">
            <button type="button" class="detail-expand-toggle" onclick="event.stopPropagation();toggleCronRunExpanded('${esc(jobId)}','${esc(run.filename)}','${rid}')" title="${esc(runToggleLabel)}" aria-label="${esc(runToggleLabel)}">${esc(runExpanded ? '▴' : '▾')}</button>
            <span style="opacity:.6">▸</span>
          </span>
        </div>
        <div class="detail-run-body ${runExpanded ? 'expanded' : ''}" style="color:var(--muted);font-size:12px">${esc(t('loading'))}</div>
      </div>`;
    }).join('');
    const countLabel = data.total > 50 ? ` (${data.total} runs, showing latest 50)` : ` (${data.total} runs)`;
    card.innerHTML = `<div class="detail-card-title">${esc(outputTitle)}${countLabel}</div>${rows}`;
  } catch(e) { /* ignore */ }
}

async function _loadRunContent(jobId, filename, runId){
  const body = document.querySelector(`#${runId} .detail-run-body`);
  if (!body) return;
  const item = document.getElementById(runId);
  if (item.classList.contains('open')) {
    // Already open → collapse and return (toggle behaviour)
    item.classList.remove('open');
    body.classList.remove('expanded');
    _cronExpansionSet(_cronRunExpandKey(jobId, filename), false);
    const btn = item ? item.querySelector('.detail-expand-toggle') : null;
    if (btn) {
      btn.textContent = '▾';
      btn.title = (t('cron_expand_output') || 'Expand output');
      btn.setAttribute('aria-label', btn.title);
    }
    return;
  }
  item.classList.add('open');
  body.classList.toggle('expanded', _cronExpansionGet(_cronRunExpandKey(jobId, filename)));
  body.innerHTML = `<span style="opacity:.5">${esc(t('loading'))}</span>`;
  try {
    const data = await api(`/api/crons/run?job_id=${encodeURIComponent(jobId)}&filename=${encodeURIComponent(filename)}`);
    if (data.error) {
      body.textContent = data.error;
      return;
    }
    const expanded = _cronExpansionGet(_cronRunExpandKey(jobId, filename));
    const output = expanded ? (data.content || data.snippet || '') : (data.snippet || data.content || '');
    body.classList.toggle('expanded', expanded);
    // Cron run output is never authored Markdown — render as literal
    // preformatted text using DOM-created <pre><code> so all content
    // (including shapes starting with #, |, >, ``` and embedded fences)
    // renders verbatim without Markdown interpretation.
    body.innerHTML = '';
    const pre = document.createElement('pre');
    pre.className = 'cron-run-pre';
    const code = document.createElement('code');
    code.textContent = output;
    pre.appendChild(code);
    body.appendChild(pre);
    const usageStrip = _formatCronRunUsageStrip(data.usage);
    if (usageStrip) {
      const usage = document.createElement('div');
      usage.className = 'cron-run-usage-strip cron-run-usage-footer';
      usage.textContent = usageStrip;
      body.appendChild(usage);
    }
    // Show "View full output" button only for collapsed previews. Expanded rows render the full body inline.
    if (!expanded && data.content && data.snippet && data.content.length > data.snippet.length) {
      const btn = document.createElement('button');
      btn.style.cssText = 'margin-top:8px;padding:4px 12px;border-radius:var(--radius-btn);border:1px solid var(--border-subtle);background:var(--surface-subtle);color:var(--text-secondary);cursor:pointer;font-size:12px';
      btn.textContent = t('cron_view_full_output') || 'View full output';
      btn.onclick = () => {
        _cronExpansionSet(_cronRunExpandKey(jobId, filename), true);
        body.classList.add('expanded');
        body.innerHTML = '';
        const pre = document.createElement('pre');
        pre.className = 'cron-run-pre';
        const code = document.createElement('code');
        code.textContent = data.content || '';
        pre.appendChild(code);
        body.appendChild(pre);
        const usageStrip = _formatCronRunUsageStrip(data.usage);
        if (usageStrip) {
          const usage = document.createElement('div');
          usage.className = 'cron-run-usage-strip cron-run-usage-footer';
          usage.textContent = usageStrip;
          body.appendChild(usage);
        }
        btn.remove();
      };
      body.appendChild(btn);
    }
  } catch(e) {
    body.textContent = 'Error: ' + e.message;
  }
}

function openCronDetail(jobOrId, el){
  const job = _findCronJob(jobOrId);
  if (!job) return;
  const detailKey = _cronJobKey(job);
  document.querySelectorAll('.cron-item').forEach(e => e.classList.remove('active'));
  const target = el || $(_cronItemId(job));
  if (target) target.classList.add('active');
  // Remove new-run dot from this job since user is now viewing it
  if (!job.read_only) _clearCronUnreadForJob(job.id);
  const dot = target && target.querySelector('.cron-new-dot');
  if (dot && !job.read_only) dot.remove();
  _cronPreFormDetail = null;
  _editingCronId = null;
  _stopCronWatch();
  _renderCronDetail(job);
  if (!job.read_only) _checkCronWatchOnDetail(job.id, detailKey);
  _closeMobileSidebarAfterPanelSelection();
}

function _clearCronDetail(){
  _currentCronDetail = null;
  _currentCronDetailKey = '';
  _cronMode = 'empty';
  _stopCronWatch();
  const title = $('taskDetailTitle');
  const body = $('taskDetailBody');
  const empty = $('taskDetailEmpty');
  if (title) title.textContent = '';
  if (body) { body.innerHTML = ''; body.style.display = 'none'; }
  if (empty) empty.style.display = '';
  _setCronHeaderButtons('empty');
}

async function runCurrentCron(){ if (_currentCronDetail) await cronRun(_currentCronDetail.id); }
async function pauseCurrentCron(){ if (_currentCronDetail) await cronPause(_currentCronDetail.id); }
async function resumeCurrentCron(){ if (_currentCronDetail) await cronResume(_currentCronDetail.id); }
async function copyCurrentCronDiagnostics(){
  if (!_currentCronDetail) return;
  try {
    await _copyText(_cronDiagnostics(_currentCronDetail));
    showToast(t('cron_diagnostics_copied'));
  } catch(e) { showToast(t('copy_failed'), 4000); }
}
function editCurrentCron(){
  if (!_currentCronDetail) return;
  openCronEdit(_currentCronDetail);
}
function duplicateCurrentCron(){
  if (!_currentCronDetail) return;
  const job = _currentCronDetail;
  if (typeof switchPanel === 'function' && _currentPanel !== 'tasks') switchPanel('tasks');
  _cronPreFormDetail = { ...job };
  _editingCronId = null;
  _cronMode = 'create';
  _cronIsDuplicate = true;
  _cronSelectedSkills = Array.isArray(job.skills) ? [...job.skills] : [];
  // Deduplicate name: append "(copy)", "(copy 2)", "(copy 3)" etc.
  const baseName = job.name || '';
  let dupName = baseName + ' (copy)';
  if (_cronList && _cronList.length) {
    const taken = new Set(_cronList.filter(j => j.name).map(j => j.name));
    if (taken.has(dupName)) {
      let n = 2;
      while (taken.has(baseName + ' (copy ' + n + ')')) n++;
      dupName = baseName + ' (copy ' + n + ')';
    }
  }
  _renderCronForm({
    name: dupName,
    schedule: job.schedule_display || (job.schedule && job.schedule.expression) || '',
    prompt: job.prompt || '',
    deliver: job.deliver || 'local',
    profile: job.profile || '',
    toast_notifications: job.toast_notifications !== false,
    no_agent: !!job.no_agent,
    script: job.script || '',
    model: job.model || '',
    provider: job.provider || '',
    isEdit: false,
  });
  if (!_cronSkillsCache) {
    api('/api/skills').then(d=>{_cronSkillsCache=d.skills||[]; _bindCronSkillPicker();}).catch(()=>{});
  } else {
    _bindCronSkillPicker();
  }
}
async function deleteCurrentCron(){
  if (!_currentCronDetail) return;
  const id = _currentCronDetail.id;
  const _ok = await showConfirmDialog({title:t('cron_delete_confirm_title'),message:t('cron_delete_confirm_message'),confirmLabel:t('delete_title'),danger:true,focusCancel:true});
  if(!_ok) return;
  try {
    await api('/api/crons/delete', {method:'POST', body: JSON.stringify({job_id: id})});
    showToast(t('cron_job_deleted'));
    _clearCronDetail();
    await loadCrons();
  } catch(e) { showToast(t('delete_failed') + e.message, 4000); }
}

let _cronSelectedSkills=[];
let _cronIsDuplicate = false;
let _cronSkillsCache=null;
let _cronProfilesCache=null;
let _cronDeliveryOptionsCache=null;

function openCronCreate(){
  if (typeof switchPanel === 'function' && _currentPanel !== 'tasks') switchPanel('tasks');
  _cronPreFormDetail = _currentCronDetail ? { ..._currentCronDetail } : null;
  _editingCronId = null;
  _cronMode = 'create';
  _cronIsDuplicate = false;
  _cronSelectedSkills = [];
  _renderCronForm({ name:'', schedule:'0 9 * * *', prompt:'', deliver:'local', profile:'', toast_notifications:true, model:'', provider:'', isEdit:false });
  _cronSkillsCache = null;
  api('/api/skills').then(d=>{_cronSkillsCache=d.skills||[]; _bindCronSkillPicker();}).catch(()=>{});
  loadCronProfiles().then(()=>_refreshCronProfileSelect('')).catch(()=>{});
}

function openCronEdit(job){
  if (!job) return;
  _cronPreFormDetail = { ...job };
  _editingCronId = job.id;
  _cronMode = 'edit';
  _cronSelectedSkills = Array.isArray(job.skills) ? [...job.skills] : [];
  _renderCronForm({
    name: job.name || '',
    schedule: job.schedule_display || (job.schedule && job.schedule.expression) || '',
    prompt: job.prompt || '',
    deliver: job.deliver || 'local',
    profile: job.profile || '',
    toast_notifications: job.toast_notifications !== false,
    no_agent: !!job.no_agent,
    script: job.script || '',
    model: job.model || '',
    provider: job.provider || '',
    isEdit: true,
  });
  if (!_cronSkillsCache) {
    api('/api/skills').then(d=>{_cronSkillsCache=d.skills||[]; _bindCronSkillPicker();}).catch(()=>{});
  } else {
    _bindCronSkillPicker();
  }
  loadCronProfiles().then(()=>_refreshCronProfileSelect(job.profile || '')).catch(()=>{});
}

function _renderCronForm({ name, schedule, prompt, deliver, profile, toast_notifications=true, no_agent=false, script='', model='', provider='', isEdit }){
  const title = $('taskDetailTitle');
  const body = $('taskDetailBody');
  const empty = $('taskDetailEmpty');
  if (!body || !title) return;
  const isNoAgent = !!no_agent;
  const toastNotifications = toast_notifications !== false;
  title.textContent = isEdit ? (t('edit') + ' · ' + (name || schedule || t('scheduled_jobs'))) : t('new_job');
  const promptBlock = isNoAgent ? '' : `
        <div class="detail-form-row">
          <label for="cronFormPrompt">${esc(t('cron_prompt_label') || 'Prompt')}</label>
          <textarea id="cronFormPrompt" rows="6" placeholder="${esc(t('cron_prompt_placeholder') || 'Must be self-contained')}" required>${esc(prompt || '')}</textarea>
        </div>`;
  const scriptBlock = isNoAgent ? `
        <div class="detail-form-row">
          <label for="cronFormScript">${esc(t('cron_script_path_label') || 'Script path')}</label>
          <input type="text" id="cronFormScript" value="${esc(script || '')}" readonly autocomplete="off">
          <div class="detail-form-hint">${esc(t('cron_script_path_hint') || 'Resolved under ~/.hermes/scripts/ unless an absolute path. Edit the script file on the server to change behavior.')}</div>
        </div>` : '';
  const skillsBlock = isNoAgent ? '' : `
        <div class="detail-form-row">
          <label for="cronFormSkillSearch">${esc(t('cron_skills_label') || 'Skills')}</label>
          <div class="skill-picker-wrap">
            <input type="text" id="cronFormSkillSearch" placeholder="${esc(t('cron_skills_placeholder') || 'Add skills (optional)...')}" autocomplete="off" ${isEdit ? 'disabled' : ''}>
            <div id="cronFormSkillDropdown" class="skill-picker-dropdown" style="display:none"></div>
            <div id="cronFormSkillTags" class="skill-picker-tags"></div>
          </div>
          ${isEdit ? `<div class="detail-form-hint">${esc(t('cron_skills_edit_hint') || 'Skill list is not editable after creation.')}</div>` : ''}
        </div>`;
  body.innerHTML = `
    <div class="main-view-content">
      ${isNoAgent ? _cronScriptJobBannerHtml() : ''}
      <form class="detail-form" onsubmit="event.preventDefault(); saveCronForm();">
        <div class="detail-form-row">
          <label for="cronFormName">${esc(t('cron_name_label') || 'Name')}</label>
          <input type="text" id="cronFormName" value="${esc(name || '')}" placeholder="${esc(t('cron_name_placeholder') || 'Optional')}" autocomplete="off">
        </div>
        <div class="detail-form-row">
          <label for="cronFormSchedulePreset">${esc(t('cron_schedule_preset_label') || 'Schedule')}</label>
          <div class="cron-schedule-preset-shell">
            <select id="cronFormSchedulePreset" class="cron-schedule-preset-select">
              ${_cronSchedulePresetOptionHtml()}
            </select>
            <div id="cronFormSchedulePresetParams" class="cron-schedule-preset-params" style="display:none">
              <div class="cron-schedule-preset-field" id="cronFormScheduleWeekdayField">
                <span class="cron-schedule-preset-conj" aria-hidden="true">${esc(t('cron_schedule_conj_on') || 'on')}</span>
                <select id="cronFormScheduleWeekday" aria-label="${esc(t('cron_schedule_weekday_label') || 'Day of week')}">
                  <option value="0">${esc(t('cron_weekday_sun') || 'Sunday')}</option>
                  <option value="1" selected>${esc(t('cron_weekday_mon') || 'Monday')}</option>
                  <option value="2">${esc(t('cron_weekday_tue') || 'Tuesday')}</option>
                  <option value="3">${esc(t('cron_weekday_wed') || 'Wednesday')}</option>
                  <option value="4">${esc(t('cron_weekday_thu') || 'Thursday')}</option>
                  <option value="5">${esc(t('cron_weekday_fri') || 'Friday')}</option>
                  <option value="6">${esc(t('cron_weekday_sat') || 'Saturday')}</option>
                </select>
              </div>
              <div class="cron-schedule-preset-field" id="cronFormScheduleMonthDayField">
                <span class="cron-schedule-preset-conj" aria-hidden="true">${esc(t('cron_schedule_conj_on_day') || 'on day')}</span>
                <select id="cronFormScheduleMonthDay" aria-label="${esc(t('cron_schedule_month_day_label') || 'Day of month')}">
                  ${Array.from({length:31},(_,i)=>`<option value="${i+1}">${i+1}</option>`).join('')}
                </select>
              </div>
              <div class="cron-schedule-preset-field" id="cronFormScheduleTimeField">
                <span class="cron-schedule-preset-conj" aria-hidden="true">${esc(t('cron_schedule_conj_at') || 'at')}</span>
                <input type="time" id="cronFormScheduleTime" value="09:00" step="60" autocomplete="off" aria-label="${esc(t('cron_schedule_time_label') || 'Time')}">
              </div>
              <div class="cron-schedule-preset-field" id="cronFormScheduleMinuteField">
                <span class="cron-schedule-preset-conj" aria-hidden="true">${esc(t('cron_schedule_conj_at_minute') || 'at minute')}</span>
                <input type="number" id="cronFormScheduleMinute" min="0" max="59" step="1" value="0" autocomplete="off" aria-label="${esc(t('cron_schedule_minute_label') || 'Minute')}">
              </div>
              <div class="detail-form-hint cron-schedule-preset-time-hint"><span id="cronFormSchedulePreview" class="cron-schedule-preview"></span>${esc(t('cron_schedule_time_hint') || 'Time is server time; cron runs server-side.')}</div>
            </div>
          </div>
        </div>
        <div class="detail-form-row" id="cronFormScheduleCustomRow" style="display:none">
          <label for="cronFormSchedule">${esc(t('cron_schedule_label') || 'Cron expression')}</label>
          <input type="text" id="cronFormSchedule" value="${esc(schedule || '')}" placeholder="0 9 * * *  —  every 1h  —  @daily" autocomplete="off" required>
          <div class="detail-form-hint">${esc(t('cron_schedule_hint') || "Cron expression or shorthand like 'every 1h'.")}</div>
          <div id="cronFormScheduleOnceWarning" class="detail-form-warning cron-once-warning" style="display:none">${esc(t('cron_schedule_once_warning') || "Duration forms like '30m' run once and are removed after running. Use 'every 30m' to keep a recurring job.")}</div>
        </div>
        ${scriptBlock}
        ${promptBlock}
        <div class="detail-form-row">
          <label for="cronFormDeliver">${esc(t('cron_deliver_label') || 'Deliver output to')}</label>
          <select id="cronFormDeliver">
            <option value="" disabled>loading...</option>
          </select>
        </div>
        <div class="detail-form-row">
          <label for="cronFormProfile">${esc(t('cron_profile_label') || 'Profile')}</label>
          <select id="cronFormProfile">
            ${_cronProfileOptions(profile)}
          </select>
          <div class="detail-form-hint">${esc(t('cron_profile_server_default_hint') || 'Uses the WebUI server default profile at run time')}</div>
        </div>
        <div class="detail-form-row">
          <label for="cronFormModel">${esc(t('cron_model_label') || 'Model')}</label>
          <select id="cronFormModel"${isNoAgent ? ' disabled' : ''}>
            <option value="">loading...</option>
          </select>
          <div class="detail-form-hint">${esc(isNoAgent ? (t('cron_model_no_agent_hint') || 'No-agent jobs run the configured script directly; model is unused.') : (t('cron_model_hint') || 'Use the profile default model at run time, or pin this job to a specific provider/model.'))}</div>
        </div>
        <div class="detail-form-row">
          <label for="cronFormToastNotifications">${esc(t('cron_toast_notifications_label') || 'Completion toasts')}</label>
          <label class="detail-form-check" for="cronFormToastNotifications">
            <input type="checkbox" id="cronFormToastNotifications" ${toastNotifications ? 'checked' : ''}>
            <span>${esc(t('cron_toast_notifications_hint') || 'Show a toast when this cron finishes.')}</span>
          </label>
        </div>
        ${skillsBlock}
        <div id="cronFormError" class="detail-form-error" style="display:none"></div>
      </form>
    </div>`;
  body.style.display = '';
  if (empty) empty.style.display = 'none';
  _setCronHeaderButtons(isEdit ? 'edit' : 'create');
  _populateCronDeliverOptions(deliver, isEdit);
  _populateCronFormModelSelect(model, provider, isNoAgent);
  if (!isNoAgent) _renderCronSkillTags();
  _initCronSchedulePresetControls();
  const focusEl = $('cronFormName');
  if (focusEl) focusEl.focus();
}

async function _populateCronDeliverOptions(selectedValue, isEdit) {
  var sel = $('cronFormDeliver');
  if (!sel) return;
  sel.disabled = true;
  try {
    if (!_cronDeliveryOptionsCache) {
      var res = await api('/api/crons/delivery-options');
      _cronDeliveryOptionsCache = res && res.platforms ? res.platforms : [];
    }
    sel.innerHTML = '';
    for (var i = 0; i < _cronDeliveryOptionsCache.length; i++) {
      var p = _cronDeliveryOptionsCache[i];
      var opt = document.createElement('option');
      opt.value = p.value;
      opt.textContent = p.label;
      if (p.value === selectedValue) opt.selected = true;
      sel.appendChild(opt);
    }
    if (selectedValue && !sel.querySelector('option[value="' + CSS.escape(selectedValue) + '"]')) {
      var opt = document.createElement('option');
      opt.value = selectedValue;
      opt.textContent = selectedValue + ' *';
      opt.selected = true;
      sel.prepend(opt);
    }
  } catch (e) {
    sel.innerHTML = '<option value="local">Local (save output only)</option>';
  }
  sel.disabled = false;
}

async function _populateCronFormModelSelect(selectedModel, selectedProvider, disabled){
  const sel = $('cronFormModel');
  if (!sel) return;
  delete sel.dataset.loaded;
  sel.disabled = true;
  sel.innerHTML = `<option value="">${esc(t('cron_model_use_default') || 'Default (use profile/system default)')}</option>`;
  try {
    const data = await api('/api/models');
    const groups = (Array.isArray(data && data.groups) && data.groups.length) ? data.groups : [];
    for (const g of groups) {
      const og = document.createElement('optgroup');
      og.label = g.provider || g.provider_id || 'Configured';
      if (g.provider_id) og.dataset.provider = g.provider_id;
      for (const m of [...(Array.isArray(g.models) ? g.models : []), ...(Array.isArray(g.extra_models) ? g.extra_models : [])]) {
        if (!m || !m.id) continue;
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = m.label || m.id;
        if (g.provider_id) opt.dataset.provider = g.provider_id;
        og.appendChild(opt);
      }
      if (og.children.length) sel.appendChild(og);
    }

    let found = false;
    if (selectedModel) {
      if (typeof _applyModelToDropdown === 'function') {
        found = !!_applyModelToDropdown(selectedModel, sel, selectedProvider || null);
      }
      if (!found) {
        for (const opt of sel.options) {
          if (opt.value !== selectedModel) continue;
          const prov = opt.dataset.provider || (opt.parentElement && opt.parentElement.dataset.provider) || '';
          if (!selectedProvider || prov === selectedProvider) {
            opt.selected = true;
            found = true;
            break;
          }
        }
      }
    } else {
      found = true;
    }

    if (selectedModel && !found) {
      const opt = document.createElement('option');
      opt.value = selectedModel;
      opt.textContent = `${selectedModel} (${t('not_available') || 'not available'})`;
      if (selectedProvider) opt.dataset.provider = selectedProvider;
      opt.selected = true;
      sel.appendChild(opt);
    }
    sel.dataset.loaded = '1';
  } catch (e) {
    console.warn('Failed to load cron model picker:', e.message);
    // Load failed: dataset.loaded stays unset so saveCronForm omits model/provider
    // and preserves any existing override. Keep the select DISABLED rather than
    // re-enabling it showing only "Default" — an enabled "Default"-only select
    // would let the user think they cleared the override when a save actually
    // preserves it (Opus advisor, stage-345). A reopen retries the load.
    sel.disabled = true;
    return;
  }
  sel.disabled = !!disabled;
}

function _renderCronSkillTags(){
  const wrap=$('cronFormSkillTags');
  if(!wrap)return;
  wrap.innerHTML='';
  for(const name of _cronSelectedSkills){
    const tag=document.createElement('span');
    tag.className='skill-tag';
    tag.dataset.skill=name;
    const rm=document.createElement('span');
    rm.className='remove-tag';rm.textContent='×';
    rm.onclick=()=>{_cronSelectedSkills=_cronSelectedSkills.filter(s=>s!==name);tag.remove();};
    tag.appendChild(document.createTextNode(name));
    tag.appendChild(rm);
    wrap.appendChild(tag);
  }
}

function _bindCronSkillPicker(){
  const search=$('cronFormSkillSearch');
  const dropdown=$('cronFormSkillDropdown');
  if(!search||!dropdown)return;
  search.oninput=()=>{
    const q=search.value.trim().toLowerCase();
    if(!q||!_cronSkillsCache){dropdown.style.display='none';return;}
    const matches=_cronSkillsCache.filter(s=>
      !_cronSelectedSkills.includes(s.name)&&
      (s.name.toLowerCase().includes(q)||(s.category||'').toLowerCase().includes(q))
    ).slice(0,8);
    if(!matches.length){dropdown.style.display='none';return;}
    dropdown.innerHTML='';
    for(const s of matches){
      const opt=document.createElement('div');
      opt.className='skill-opt';
      opt.textContent=s.name+(s.category?' ('+s.category+')':'');
      opt.onclick=()=>{
        _cronSelectedSkills.push(s.name);
        _renderCronSkillTags();
        search.value='';
        dropdown.style.display='none';
      };
      dropdown.appendChild(opt);
    }
    dropdown.style.display='';
  };
  search.onblur=()=>setTimeout(()=>{dropdown.style.display='none';},150);
}

function cancelCronForm(){
  _editingCronId = null;
  if (_cronPreFormDetail) {
    const snap = _cronPreFormDetail;
    _cronPreFormDetail = null;
    _renderCronDetail(snap);
    return;
  }
  _cronPreFormDetail = null;
  _clearCronDetail();
}

function _cronModelBareName(model, provider) {
  // Strip @provider: prefix from a model value when provider is stored separately.
  // The model dropdown may contain values like "@custom:9router:chat" (from
  // _apply_provider_prefix) but cron jobs store model and provider separately,
  // so the model should be just "chat".
  if (model && provider && model.startsWith('@' + provider + ':')) {
    return model.slice(('@' + provider + ':').length);
  }
  return model;
}

async function saveCronForm(){
  const nameEl=$('cronFormName');
  const schEl=$('cronFormSchedule');
  const promptEl=$('cronFormPrompt');
  const delivEl=$('cronFormDeliver');
  const profileEl=$('cronFormProfile');
  const toastEl=$('cronFormToastNotifications');
  const errEl=$('cronFormError');
  if(!schEl||!errEl) return;
  const isNoAgent = !!(_cronPreFormDetail && _cronPreFormDetail.no_agent);
  if(!isNoAgent && !promptEl) return;
  const name=(nameEl?nameEl.value:'').trim();
  const schedule=schEl.value.trim();
  const prompt=promptEl ? promptEl.value.trim() : '';
  const deliver=delivEl?delivEl.value:'local';
  const profile=profileEl?profileEl.value:'';
  const toastNotifications=toastEl?!!toastEl.checked:true;
  errEl.style.display='none';
  if(!schedule){errEl.textContent=t('cron_schedule_required_example');errEl.style.display='';return;}
  if(!isNoAgent && !prompt){errEl.textContent=t('cron_prompt_required');errEl.style.display='';return;}
  try{
    const modelEl = $('cronFormModel');
    const modelLoaded = !!(modelEl && modelEl.dataset.loaded === '1');
    const selectedModel = modelEl ? (modelEl.value || '').trim() : '';
    if (_editingCronId) {
      const updates = {job_id: _editingCronId, schedule, profile: profile, toast_notifications: toastNotifications};
      if (!isNoAgent) updates.prompt = prompt;
      if (name) updates.name = name;
      if (deliver) updates.deliver = deliver;
      if (modelEl) {
        if (selectedModel && modelLoaded) {
          const modelState = (typeof _modelStateForSelect === 'function')
            ? _modelStateForSelect(modelEl, selectedModel)
            : { model: selectedModel, model_provider: null };
          updates.model = _cronModelBareName(modelState.model, modelState.model_provider) || null;
          updates.provider = modelState.model_provider || null;
        } else if (modelLoaded) {
          updates.model = null;
          updates.provider = null;
        }
        // else: select not yet populated — omit model/provider to preserve saved value
      }
      await api('/api/crons/update', {method:'POST', body: JSON.stringify(updates)});
      const editedId = _editingCronId;
      _editingCronId = null;
      _cronPreFormDetail = null;
      showToast(t('cron_job_updated'));
      await loadCrons();
      const job = _cronList && _cronList.find(j => j.id === editedId);
      if (job) openCronDetail(job);
      return;
    }
    const body={schedule,prompt,deliver,profile: profile, toast_notifications: toastNotifications};
    if(_cronIsDuplicate) body.enabled=false;
    if(name)body.name=name;
    if(_cronSelectedSkills.length)body.skills=_cronSelectedSkills;
    if (modelEl && modelLoaded) {
      if (selectedModel) {
        const modelState = (typeof _modelStateForSelect === 'function')
          ? _modelStateForSelect(modelEl, selectedModel)
          : { model: selectedModel, model_provider: null };
        body.model = _cronModelBareName(modelState.model, modelState.model_provider) || null;
        body.provider = modelState.model_provider || null;
      }
    } else if (_cronIsDuplicate && _cronPreFormDetail && _cronPreFormDetail.model) {
      body.model = _cronModelBareName(_cronPreFormDetail.model, _cronPreFormDetail.provider) || null;
      body.provider = _cronPreFormDetail.provider || null;
    }
    const res = await api('/api/crons/create',{method:'POST',body:JSON.stringify(body)});
    _cronPreFormDetail = null;
    _cronIsDuplicate = false;
    showToast(t('cron_job_created'));
    await loadCrons();
    const newId = res && (res.id || (res.job && res.job.id));
    if (newId) openCronDetail(newId);
    else if (_cronList && _cronList.length) openCronDetail(_cronList[_cronList.length - 1]);
  }catch(e){
    errEl.textContent=t('error_prefix')+e.message;errEl.style.display='';
  }
}

// Back-compat aliases for any stale callers
const submitCronCreate = saveCronForm;
function toggleCronForm(){ openCronCreate(); }

function _cronOutputSnippet(content) {
  // Extract the response body from a cron output .md file
  const lines = content.split('\n');
  const responseIdx = lines.findIndex(l => l.startsWith('## Response') || l.startsWith('# Response'));
  const body = (responseIdx >= 0 ? lines.slice(responseIdx + 1) : lines).join('\n').trim();
  return body.slice(0, 600) || '(empty)';
}

function _formatCronRunUsageStrip(usage) {
  if (!usage || typeof usage !== 'object') return '';
  const parts = [];
  const fmt = n => {
    const value = Number(n || 0);
    if (!Number.isFinite(value) || value <= 0) return '';
    if (value >= 1000000) return (value / 1000000).toFixed(value >= 10000000 ? 0 : 1).replace(/\.0$/, '') + 'M';
    if (value >= 1000) return (value / 1000).toFixed(value >= 10000 ? 0 : 1).replace(/\.0$/, '') + 'k';
    return String(Math.round(value));
  };
  const input = fmt(usage.input_tokens);
  const output = fmt(usage.output_tokens);
  const total = fmt(usage.total_tokens);
  if (input || output) parts.push(`${input || '0'} in · ${output || '0'} out`);
  else if (total) parts.push(`${total} tokens`);
  const cost = Number(usage.estimated_cost_usd);
  if (Number.isFinite(cost) && cost > 0) parts.push(`$${cost < 0.01 ? cost.toFixed(4) : cost.toFixed(3)}`);
  if (usage.model) parts.push(String(usage.model));
  return parts.join(' · ');
}

// ── Cron run watch ────────────────────────────────────────────────────────────
let _cronWatchInterval = null;
let _cronWatchStart = null;
let _cronWatchTimerInterval = null;

function _startCronWatch(jobId, detailKey) {
  _stopCronWatch();
  _cronWatchStart = Date.now();
  _cronWatchInterval = setInterval(async () => {
    try {
      const data = await api(`/api/crons/status?job_id=${encodeURIComponent(jobId)}`,{timeoutToast:false});
      if (!data.running) {
        _stopCronWatch();
        if (_cronDetailMatches(jobId, detailKey)) {
          _loadCronDetailRuns(jobId, detailKey);
        }
        return;
      }
      // Still running — update elapsed
      if (_cronDetailMatches(jobId, detailKey)) {
        const el = $('cronRunningIndicator');
        if (el) el.querySelector('.cron-watch-elapsed').textContent = _formatElapsed(data.elapsed);
      }
    } catch(e) { /* ignore poll errors */ }
  }, 3000);
  // Timer update every second
  _cronWatchTimerInterval = setInterval(() => {
    if (_cronDetailMatches(jobId, detailKey) && _cronWatchStart) {
      const el = $('cronRunningIndicator');
      if (el) el.querySelector('.cron-watch-elapsed').textContent = _formatElapsed((Date.now() - _cronWatchStart) / 1000);
    }
  }, 1000);
  // Inject running indicator into detail card
  if (_cronDetailMatches(jobId, detailKey)) {
    _injectRunningIndicator();
  }
}

function _stopCronWatch() {
  if (_cronWatchInterval) { clearInterval(_cronWatchInterval); _cronWatchInterval = null; }
  if (_cronWatchTimerInterval) { clearInterval(_cronWatchTimerInterval); _cronWatchTimerInterval = null; }
  _cronWatchStart = null;
  const el = $('cronRunningIndicator');
  if (el) el.remove();
}

function _injectRunningIndicator() {
  const card = $('cronDetailRuns');
  if (!card || $('cronRunningIndicator')) return;
  const div = document.createElement('div');
  div.id = 'cronRunningIndicator';
  div.className = 'cron-running-indicator';
  div.innerHTML = `<span class="cron-watch-spinner"></span><span>${esc(t('cron_status_running'))}</span><span class="cron-watch-elapsed">0s</span>`;
  card.insertAdjacentElement('beforebegin', div);
}

function _formatElapsed(seconds) {
  if (seconds < 60) return Math.round(seconds) + 's';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return m + 'm ' + s + 's';
}

function _checkCronWatchOnDetail(jobId, detailKey) {
  // When opening a detail view, check if job is running
  api(`/api/crons/status?job_id=${encodeURIComponent(jobId)}`,{timeoutToast:false}).then(data => {
    if (data.running && _cronDetailMatches(jobId, detailKey)) {
      _startCronWatch(jobId, detailKey);
    }
  }).catch(() => {});
}

async function cronRun(id) {
  try {
    await api('/api/crons/run', {method:'POST', body: JSON.stringify({job_id: id})});
    showToast(t('cron_job_triggered'));
    _startCronWatch(id, _currentCronDetailKey);
  } catch(e) { showToast(t('failed_colon') + e.message, 4000); }
}

async function cronPause(id) {
  try {
    await api('/api/crons/pause', {method:'POST', body: JSON.stringify({job_id: id})});
    showToast(t('cron_job_paused'));
    await loadCrons();
  } catch(e) { showToast(t('failed_colon') + e.message, 4000); }
}

async function cronResume(id) {
  try {
    await api('/api/crons/resume', {method:'POST', body: JSON.stringify({job_id: id})});
    showToast(t('cron_job_resumed'));
    await loadCrons();
  } catch(e) { showToast(t('failed_colon') + e.message, 4000); }
}

let _editingCronId = null;

// ── Kanban panel (read-only) ──
function _kanbanColumnLabel(name){ return t('kanban_status_' + name) || name; }
function _kanbanTaskTitle(task){ return task.title || task.summary || task.id || t('kanban_task'); }
function _kanbanTaskBody(task){ return task.body || task.description || task.prompt || ''; }
function _kanbanTaskMeta(task){
  const bits = [];
  bits.push(task.assignee ? task.assignee : t('kanban_unassigned'));
  if (task.tenant) bits.push(task.tenant);
  if (task.priority !== undefined && task.priority !== null) bits.push('P' + task.priority);
  if (task.comment_count) bits.push('💬 ' + task.comment_count);
  if (task.link_counts && task.link_counts.children) bits.push('↳ ' + task.link_counts.children);
  return bits;
}

function _kanbanCurrentFilters(){
  const q = $('kanbanSearch') ? $('kanbanSearch').value.trim().toLowerCase() : '';
  const assigneeEl = $('kanbanAssigneeFilter');
  const tenantEl = $('kanbanTenantFilter');
  const assignee = assigneeEl ? (assigneeEl.value || assigneeEl.dataset.defaultValue || '') : '';
  const tenant = tenantEl ? (tenantEl.value || tenantEl.dataset.defaultValue || '') : '';
  const includeArchived = !!($('kanbanIncludeArchived') && $('kanbanIncludeArchived').checked);
  const onlyMine = !!($('kanbanOnlyMine') && $('kanbanOnlyMine').checked);
  return {q, assignee, tenant, includeArchived, onlyMine, workflowTemplateId: kanbanWorkflowTemplateFilter || ''};
}

function _kanbanApplyConfigDefaults(config){
  if (!config) return;
  _kanbanLanesByProfile = config.lane_by_profile === true;
  syncKanbanViewToggle();
  if (_kanbanConfigApplied) return;
  if ($('kanbanTenantFilter') && config.default_tenant) $('kanbanTenantFilter').dataset.defaultValue = config.default_tenant;
  if ($('kanbanIncludeArchived') && config.include_archived_by_default === true) $('kanbanIncludeArchived').checked = true;
  _kanbanConfigApplied = true;
}
let _kanbanConfigApplied = false;

function syncKanbanViewToggle(){
  const btn = $('btnKanbanViewToggle');
  if (!btn) return;
  const consolidated = !_kanbanLanesByProfile;
  const label = t('kanban_view_consolidated');
  btn.setAttribute('aria-pressed', consolidated ? 'true' : 'false');
  btn.setAttribute('aria-label', label);
  btn.setAttribute('data-i18n-title', 'kanban_view_consolidated');
  btn.setAttribute('data-i18n-aria-label', 'kanban_view_consolidated');
  if (typeof _setButtonTooltip === 'function') _setButtonTooltip(btn, label);
  else btn.setAttribute('data-tooltip', label);
}

async function toggleKanbanViewMode(){
  const btn = $('btnKanbanViewToggle');
  const nextLaneByProfile = !_kanbanLanesByProfile;
  if (btn) btn.disabled = true;
  try {
    const saved = await api('/api/kanban/config', {method: 'PATCH', body: JSON.stringify({lane_by_profile: nextLaneByProfile})});
    _kanbanLanesByProfile = saved.lane_by_profile === true;
    syncKanbanViewToggle();
    _kanbanRenderBoard();
    showToast(t(_kanbanLanesByProfile ? 'kanban_view_lanes_saved' : 'kanban_view_consolidated_saved'));
  } catch(e) {
    showToast(t('kanban_view_update_failed') + (e.message || e), 4000, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

function _kanbanSetSelectOptions(el, values, allLabelKey){
  if (!el) return;
  const current = el.value || el.dataset.defaultValue || '';
  const opts = [`<option value="">${esc(t(allLabelKey))}</option>`]
    .concat((values || []).map(v => `<option value="${esc(v)}">${esc(v)}</option>`));
  el.innerHTML = opts.join('');
  if ([...el.options].some(o => o.value === current)) el.value = current;
}

// Distinct workflow_template_id values actually present in the currently
// loaded board's tasks -- NOT the full /api/crews list, so a crew with zero
// currently-visible tasks doesn't show up as a filter option.
function _kanbanCrewFilterIds(){
  const columns = (_kanbanBoard && _kanbanBoard.columns) || [];
  const ids = [];
  const seen = new Set();
  for (const col of columns) {
    for (const task of (col.tasks || [])) {
      const id = task.workflow_template_id;
      if (id && !seen.has(id)) { seen.add(id); ids.push(id); }
    }
  }
  return ids;
}

// Unlike _kanbanSetSelectOptions (value === label), each option's label here
// is the crew's name (falling back to its raw id), so it isn't reused as-is.
// kanbanWorkflowTemplateFilter -- not the <select> element -- stays the one
// authoritative value (also set directly by dispatchKanbanCrew() and reset by
// clearKanbanFilters()); this only re-syncs the visible option to match it.
function _kanbanPopulateCrewFilter(){
  const el = $('kanbanCrewFilter');
  if (!el) return;
  const ids = _kanbanCrewFilterIds();
  const opts = [`<option value="">${esc(t('kanban_all_crews') || 'All crews')}</option>`]
    .concat(ids.map(id => `<option value="${esc(id)}">${esc(_kanbanCrewName(id))}</option>`));
  el.innerHTML = opts.join('');
  el.value = ids.includes(kanbanWorkflowTemplateFilter) ? kanbanWorkflowTemplateFilter : '';
}

function _kanbanVisibleTasks(){
  const filters = _kanbanCurrentFilters();
  const columns = (_kanbanBoard && _kanbanBoard.columns) || [];
  return columns.map(col => {
    const tasks = (col.tasks || []).filter(task => {
      if (!filters.q) return true;
      const haystack = [task.id, _kanbanTaskTitle(task), _kanbanTaskBody(task), task.assignee, task.tenant]
        .filter(Boolean).join(' ').toLowerCase();
      return haystack.includes(filters.q);
    });
    return {...col, tasks};
  });
}

function _kanbanRenderSidebar(columns){
  const list = $('kanbanList');
  if (!list) return;
  const tasks = columns.flatMap(col => (col.tasks || []).map(task => ({...task, status: task.status || col.name})));
  if (!tasks.length) {
    list.innerHTML = `<div class="kanban-empty" data-i18n="kanban_no_matching_tasks">${esc(t('kanban_no_matching_tasks'))}</div>`;
    return;
  }
  list.innerHTML = tasks.map(task => {
    const meta = _kanbanTaskMeta(task);
    return `<button class="kanban-list-item" onclick="loadKanbanTask('${esc(task.id)}')">
      <span class="kanban-list-status">${esc(_kanbanColumnLabel(task.status))}</span>
      <span class="kanban-list-title">${esc(_kanbanTaskTitle(task))}</span>
      ${meta.length ? `<span class="kanban-meta">${esc(meta.join(' · '))}</span>` : ''}
    </button>`;
  }).join('');
}


/**
 * Render inline markdown (bold, italic, code, links, strikethrough).
 * Input is already HTML-escaped.
 */
function _kanbanRenderMarkdownInline(escaped){
  return String(escaped || '')
    .replace(/~~([^~\n]+)~~/g, (_m, text) => `<del>${text}</del>`)
    .replace(/`([^`\n]+)`/g, (_m, code) => `<code>${code}</code>`)
    .replace(/\*\*([^*\n]+)\*\*/g, (_m, text) => `<strong>${text}</strong>`)
    .replace(/(^|[^*a-zA-Z0-9])\*([^*\n]+)\*/g, (_m, prefix, text) => `${prefix}<em>${text}</em>`)
    .replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+|mailto:[^\s)]+)\)/g, (_m, text, href) => `<a href="${href}" target="_blank" rel="noopener noreferrer">${text}</a>`);
}

/**
 * Render full markdown block content: headings, code blocks, lists, tables,
 * task lists, blockquotes, horizontal rules, paragraphs + inline formatting.
 */
function _kanbanRenderMarkdown(source){
  if (!source) return '';
  const lines = esc(source).split(/\r?\n/);
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // ── Code block ──
    if (/^```/.test(trimmed)) {
      const lang = trimmed.slice(3).trim();
      const codeLines = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i].trim())) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // skip closing ```
      const codeHtml = codeLines.join('\n');
      out.push(lang
        ? `<pre class="hermes-kanban-code"><code class="language-${_kanbanRenderMarkdownInline(lang)}">${codeHtml}</code></pre>`
        : `<pre class="hermes-kanban-code"><code>${codeHtml}</code></pre>`);
      continue;
    }

    // ── Horizontal rule ──
    if (/^(-{3,}|\*{3,}|_{3,})\s*$/.test(trimmed)) {
      out.push('<hr>');
      i++;
      continue;
    }

    // ── Heading ──
    const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      out.push(`<h${level}>${_kanbanRenderMarkdownInline(headingMatch[2])}</h${level}>`);
      i++;
      continue;
    }

    // ── Blockquote ──
    if (/^>\s?/.test(trimmed)) {
      const quoteLines = [];
      while (i < lines.length && /^>\s?/.test(lines[i].trim())) {
        quoteLines.push(lines[i].trim().replace(/^>\s?/, ''));
        i++;
      }
      out.push(`<blockquote>${_kanbanRenderMarkdownInline(quoteLines.join('<br>'))}</blockquote>`);
      continue;
    }

    // ── Table row ──
    if (/^\|.+\|$/.test(trimmed)) {
      const tableRows = [];
      const tableAligns = [];
      while (i < lines.length && /^\|.+\|$/.test(lines[i].trim())) {
        const row = lines[i].trim();
        // Detect alignment separator row
        if (/^\|[\s:]*-{3,}[\s:]*\|/.test(row)) {
          const cells = row.split('|').filter(c => c.trim().length > 0);
          cells.forEach(c => {
            const t = c.trim();
            if (t.startsWith(':') && t.endsWith(':')) tableAligns.push('center');
            else if (t.endsWith(':')) tableAligns.push('right');
            else tableAligns.push('left');
          });
        } else {
          const cells = row.split('|').filter(c => c.trim().length > 0);
          tableRows.push(cells.map((c, ci) => {
            const align = tableAligns[ci] ? ` style="text-align:${tableAligns[ci]}"` : '';
            return `<td${align}>${_kanbanRenderMarkdownInline(c.trim())}</td>`;
          }).join(''));
        }
        i++;
      }
      if (tableRows.length) {
        out.push(`<table><tbody>${tableRows.map(r => `<tr>${r}</tr>`).join('')}</tbody></table>`);
      }
      continue;
    }

    // ── Task list item ──
    const taskMatch = trimmed.match(/^[-*+]\s+\[( |x|X)\]\s+(.+)$/);
    if (taskMatch) {
      const checked = taskMatch[1] !== ' ';
      const text = taskMatch[2];
      const items = [];
      items.push(`<li class="hermes-kanban-task${checked ? ' checked' : ''}"><input type="checkbox"${checked ? ' checked' : ''} disabled> ${_kanbanRenderMarkdownInline(text)}</li>`);
      i++;
      // Collect continuation items
      while (i < lines.length) {
        const next = lines[i].trim();
        const nextTask = next.match(/^[-*+]\s+\[( |x|X)\]\s+(.+)$/);
        const nextLi = next.match(/^[-*+]\s+(.+)$/);
        if (nextTask) {
          const c = nextTask[1] !== ' ';
          items.push(`<li class="hermes-kanban-task${c ? ' checked' : ''}"><input type="checkbox"${c ? ' checked' : ''} disabled> ${_kanbanRenderMarkdownInline(nextTask[2])}</li>`);
          i++;
        } else if (nextLi) {
          items.push(`<li>${_kanbanRenderMarkdownInline(nextLi[1])}</li>`);
          i++;
        } else {
          break;
        }
      }
      out.push(`<ul>${items.join('')}</ul>`);
      continue;
    }

    // ── Unordered list item ──
    const ulMatch = trimmed.match(/^[-*+]\s+(.+)$/);
    if (ulMatch) {
      const items = [];
      items.push(`<li>${_kanbanRenderMarkdownInline(ulMatch[1])}</li>`);
      i++;
      while (i < lines.length) {
        const next = lines[i].trim();
        const nextUl = next.match(/^[-*+]\s+(.+)$/);
        const nextTask = next.match(/^[-*+]\s+\[( |x|X)\]\s+(.+)$/);
        if (nextTask) break; // let task list handler get it
        if (nextUl) {
          items.push(`<li>${_kanbanRenderMarkdownInline(nextUl[1])}</li>`);
          i++;
        } else {
          break;
        }
      }
      out.push(`<ul>${items.join('')}</ul>`);
      continue;
    }

    // ── Ordered list item ──
    const olMatch = trimmed.match(/^\d+\.\s+(.+)$/);
    if (olMatch) {
      const items = [];
      items.push(`<li>${_kanbanRenderMarkdownInline(olMatch[1])}</li>`);
      i++;
      while (i < lines.length) {
        const next = lines[i].trim();
        const nextOl = next.match(/^\d+\.\s+(.+)$/);
        if (nextOl) {
          items.push(`<li>${_kanbanRenderMarkdownInline(nextOl[1])}</li>`);
          i++;
        } else {
          break;
        }
      }
      out.push(`<ol>${items.join('')}</ol>`);
      continue;
    }

    // ── Empty line ──
    if (!trimmed) {
      out.push('');
      i++;
      continue;
    }

    // ── Paragraph ──
    out.push(`<p>${_kanbanRenderMarkdownInline(trimmed)}</p>`);
    i++;
  }
  return `<div class="hermes-kanban-md">${out.join('\n')}</div>`;
}

function _kanbanFormatDuration(seconds){
  const n = Number(seconds);
  if (!Number.isFinite(n) || n <= 0) return '';
  if (n < 60) return Math.round(n) + 's';
  if (n < 3600) return Math.round(n / 60) + 'm';
  if (n < 86400) return Math.round(n / 3600) + 'h';
  return Math.round(n / 86400) + 'd';
}

function _kanbanTaskAge(task){
  const age = task && (task.age_seconds || task.age);
  if (Number.isFinite(Number(age))) return _kanbanFormatDuration(age);
  return '';
}

function _kanbanCardStalenessClass(task){
  const age = Number(task && (task.age_seconds || task.age));
  const status = task && task.status;
  if (!Number.isFinite(age)) return '';
  if ((status === 'running' && age > 3600) || (status === 'blocked' && age > 86400)) return 'kanban-card-stale-red';
  if ((status === 'running' && age > 600) || (status === 'ready' && age > 3600) || (status === 'blocked' && age > 3600)) return 'kanban-card-stale-amber';
  return '';
}

function _kanbanCardQuickActions(task){
  const id = esc(task.id || '');
  const status = task.status || '';
  const complete = status !== 'done' && status !== 'archived' ? `<button type="button" class="kanban-card-action" onclick="quickKanbanCardAction(event,'${id}','done')">${esc(t('kanban_card_complete'))}</button>` : '';
  const archive = status !== 'archived' ? `<button type="button" class="kanban-card-action danger" onclick="quickKanbanCardAction(event,'${id}','archived')">${esc(t('kanban_card_archive'))}</button>` : '';
  return `<div class="kanban-card-actions" onclick="event.stopPropagation()">${complete}${archive}</div>`;
}

async function quickKanbanCardAction(event, taskId, status){
  if (event) event.stopPropagation();
  return updateKanbanTask(taskId, {status});
}

function _kanbanSuppressNextCardClick(){
  _kanbanSuppressCardClickUntil = Date.now() + 700;
}

function dragKanbanTask(event, taskId){
  _kanbanSuppressNextCardClick();
  if (!event.dataTransfer) return;
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/plain', taskId);
}

function finishKanbanDrag(event){
  if (event) _kanbanSuppressNextCardClick();
}

function openKanbanCard(event, taskId){
  if (Date.now() < _kanbanSuppressCardClickUntil) {
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }
    return false;
  }
  loadKanbanTask(taskId);
  return false;
}

function allowKanbanDrop(event){
  // Don't accept drops into the 'running' column. Entering 'running' is owned
  // by the dispatcher/claim_task path (sets claim_lock + claim_expires +
  // started_at + worker_pid). A drag-drop would bypass that contract and the
  // bridge would reject the resulting PATCH with HTTP 400 anyway. Refuse the
  // drop visually so users see immediate feedback.
  const target = event.currentTarget;
  if (target && target.dataset && target.dataset.kanbanStatus === 'running') {
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'none';
    return;
  }
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
}

function clearKanbanDrop(event){
  if (event && event.currentTarget) event.currentTarget.classList.remove('drop-target');
}

async function dropKanbanTask(event, status){
  _kanbanSuppressNextCardClick();
  event.preventDefault();
  event.stopPropagation();
  clearKanbanDrop(event);
  const taskId = event.dataTransfer ? event.dataTransfer.getData('text/plain') : '';
  if (taskId && status) await updateKanbanTask(taskId, {status}, {openDetail: false});
  _kanbanSuppressNextCardClick();
}

const KANBAN_UNASSIGNED_LANE = '__unassigned__';
function _kanbanLaneKey(task){ return task && task.assignee ? String(task.assignee) : KANBAN_UNASSIGNED_LANE; }
function _kanbanLaneLabel(lane){ return lane === KANBAN_UNASSIGNED_LANE ? t('kanban_unassigned') : lane; }

function _kanbanLaneNames(columns){
  const names = new Set();
  columns.forEach(col => (col.tasks || []).forEach(task => names.add(_kanbanLaneKey(task))));
  const assigned = Array.from(names).filter(n => n !== KANBAN_UNASSIGNED_LANE).sort((a, b) => {
    if (a === 'default') return -1;
    if (b === 'default') return 1;
    return String(a).localeCompare(String(b));
  });
  if (names.has(KANBAN_UNASSIGNED_LANE)) assigned.push(KANBAN_UNASSIGNED_LANE);
  return assigned;
}

function _kanbanRenderColumn(col){
  const tasks = col.tasks || [];
  return `<section class="kanban-column" data-status="${esc(col.name)}" data-kanban-status="${esc(col.name)}" ondragover="allowKanbanDrop(event)" ondragenter="event.currentTarget.classList.add('drop-target')" ondragleave="clearKanbanDrop(event)" ondrop="dropKanbanTask(event, '${esc(col.name)}')">
      <div class="kanban-column-head">
        <span>${esc(_kanbanColumnLabel(col.name))}</span>
        <span class="kanban-count">${tasks.length}</span>
      </div>
      <div class="kanban-column-body">
        ${tasks.length ? tasks.map(task => _kanbanCard(task, col.name)).join('') : `<div class="kanban-empty">${esc(t('kanban_empty'))}</div>`}
      </div>
    </section>`;
}

function _kanbanRenderProfileLanes(columns){
  const lanes = _kanbanLaneNames(columns);
  if (!lanes.length) return columns.map(_kanbanRenderColumn).join('');
  return `<div class="kanban-profile-lanes">${lanes.map(lane => {
    const laneCols = columns.map(col => ({...col, tasks: (col.tasks || []).filter(task => _kanbanLaneKey(task) === lane)}));
    const count = laneCols.reduce((sum, col) => sum + (col.tasks || []).length, 0);
    const laneClass = lane === KANBAN_UNASSIGNED_LANE ? ' kanban-profile-lane-unassigned' : '';
    return `<section class="kanban-profile-lane${laneClass}" data-kanban-lane="${esc(lane)}"><header class="kanban-profile-lane-head"><span>${esc(_kanbanLaneLabel(lane))}</span><span class="kanban-count">${count}</span></header><div class="kanban-board kanban-board-in-lane">${laneCols.map(_kanbanRenderColumn).join('')}</div></section>`;
  }).join('')}</div>`;
}

function _kanbanEmptyBoardHtml(){
  return `<div class="main-view-empty"><div class="main-view-empty-title">${esc(t('kanban_no_data'))}</div><div class="main-view-empty-sub">${esc(t('kanban_work_queue_hint'))}</div></div>`;
}

function _kanbanHiddenByFiltersHtml(){
  return `<div class="main-view-empty"><div class="main-view-empty-title">${esc(t('kanban_tasks_hidden_by_filters'))}</div><div class="main-view-empty-sub"><button class="btn-link" onclick="clearKanbanFilters()">${esc(t('kanban_clear_filters'))}</button></div></div>`;
}

function clearKanbanFilters(){
  const s = $('kanbanSearch'); if (s) s.value = '';
  const a = $('kanbanAssigneeFilter'); if (a) { a.value = ''; a.dataset.defaultValue = ''; }
  const te = $('kanbanTenantFilter'); if (te) { te.value = ''; te.dataset.defaultValue = ''; }
  const cf = $('kanbanCrewFilter'); if (cf) { cf.value = ''; cf.dataset.defaultValue = ''; }
  const ai = $('kanbanIncludeArchived'); if (ai) ai.checked = false;
  const om = $('kanbanOnlyMine'); if (om) om.checked = false;
  kanbanWorkflowTemplateFilter = '';
  loadKanban(true);
}

function _kanbanRenderBoard(){
  const board = $('kanbanBoard');
  if (!board) return;
  // Office view is a separate container toggled alongside the normal board;
  // kept as an additive branch here (rather than touching each of this
  // function's early-return paths) so it stays in sync for free with every
  // existing call site — loadKanban's poll/SSE refresh, filterKanban, the
  // lane-view toggle — without needing its own wiring at each one. The crew
  // filter's option list is repopulated here for the same reason: it must
  // track whatever board data is currently loaded, not a separately-triggered
  // refresh.
  if (typeof _kanbanRenderOfficeView === 'function') _kanbanRenderOfficeView();
  _kanbanPopulateCrewFilter();
  if (!_kanbanBoard || !_kanbanBoard.columns) {
    board.innerHTML = _kanbanEmptyBoardHtml();
    return;
  }
  board.classList.toggle('kanban-board-consolidated', !_kanbanLanesByProfile);
  const columns = _kanbanVisibleTasks();
  const total = columns.reduce((n, col) => n + (col.tasks || []).length, 0);
  if ($('kanbanSummary')) $('kanbanSummary').textContent = String(t('kanban_visible_tasks')).replace('{0}', total);
  _kanbanRenderSidebar(columns);
  if (total === 0) {
    const unfilteredTotal = (_kanbanBoard.columns || []).reduce((n, col) => n + (col.tasks || []).length, 0);
    board.innerHTML = unfilteredTotal > 0 ? _kanbanHiddenByFiltersHtml() : _kanbanEmptyBoardHtml();
    return;
  }
  board.innerHTML = _kanbanLanesByProfile ? _kanbanRenderProfileLanes(columns) : columns.map(_kanbanRenderColumn).join('');
}

function _kanbanCard(task, status){
  const priority = Number(task.priority || 0);
  const links = task.link_counts || {};
  const linkTotal = Number(links.parents || 0) + Number(links.children || 0);
  const comments = Number(task.comment_count || 0);
  const age = _kanbanTaskAge(task);
  const stale = _kanbanCardStalenessClass(task);
  const body = _kanbanTaskBody(task);
  const assignee = task.assignee ? `<span class="kanban-card-assignee">@${esc(task.assignee)}</span>` : `<span class="kanban-card-unassigned">${esc(t('kanban_unassigned'))}</span>`;
  return `<article class="kanban-card ${esc(stale)}" data-kanban-task-id="${esc(task.id)}" draggable="true" ondragstart="dragKanbanTask(event, '${esc(task.id)}')" ondragend="finishKanbanDrag(event)" onclick="return openKanbanCard(event, '${esc(task.id)}')" tabindex="0" role="button" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();loadKanbanTask('${esc(task.id)}')}">
    <div class="kanban-card-topline"><span class="kanban-card-id">${esc(task.id || '')}</span>${priority ? `<span class="kanban-badge priority">P${priority}</span>` : ''}${task.tenant ? `<span class="kanban-badge tenant">${esc(task.tenant)}</span>` : ''}</div>
    <div class="kanban-card-title">${esc(_kanbanTaskTitle(task))}</div>
    ${body ? `<div class="kanban-card-body">${_kanbanRenderMarkdown(body)}</div>` : ''}
    <div class="kanban-card-meta">${assignee}${comments ? `<span class="kanban-card-metric">💬 ${comments}</span>` : ''}${linkTotal ? `<span class="kanban-card-metric">↔ ${linkTotal}</span>` : ''}${age ? `<span class="kanban-card-age">${esc(age)}</span>` : ''}</div>
    ${_kanbanCardQuickActions(task)}
  </article>`;
}

// ── Office view: a "mission control" grid of live Kanban-dispatched workers ──
// Priority 2 (docs/HERMES_STUDIO_PARITY_PLAN.md, multi-agent orchestration).
// Scope note: this visualizes Kanban-dispatched workers ONLY (task.worker_pid
// set by hermes_cli.kanban_db.dispatch_once, which runs in-process inside
// this same webui container). It deliberately does NOT show delegate_task
// subagents — that live registry (tools/delegate_tool.py's _active_subagents)
// lives inside the separate `hermes` container's process memory, which runs
// from a pre-built nousresearch/hermes-agent image rather than the locally
// mounted hermes-agent-src, so there is no reachable endpoint for it today.
let _kanbanOfficeViewActive = false;
const _kanbanOfficeExpanded = new Set(); // task ids with their log panel open
const _kanbanOfficeLogCache = new Map(); // task id -> last-fetched log text, so a
                                          // routine poll/SSE re-render doesn't
                                          // blank an open log while refetching

function toggleKanbanOfficeView(){
  _kanbanOfficeViewActive = !_kanbanOfficeViewActive;
  const btn = $('btnKanbanOfficeView');
  if (btn) btn.setAttribute('aria-pressed', _kanbanOfficeViewActive ? 'true' : 'false');
  const board = $('kanbanBoard');
  const office = $('kanbanOfficeView');
  if (board) board.style.display = _kanbanOfficeViewActive ? 'none' : '';
  if (office) office.style.display = _kanbanOfficeViewActive ? '' : 'none';
  _kanbanRenderOfficeView();
}

function _kanbanOfficeViewWorkers(){
  // Returns crew-grouped worker sections rather than a flat list: an array of
  // {templateId, workers} in first-seen order, with an untagged group
  // (templateId: null, "Ungrouped" -- CLI-created or pre-Crews tasks) always
  // last regardless of when its first worker appeared, so grouping stays
  // stable across renders.
  const columns = (_kanbanBoard && _kanbanBoard.columns) || [];
  const workers = [];
  for (const col of columns) {
    for (const task of (col.tasks || [])) {
      if (task.status === 'running' && task.worker_pid) workers.push(task);
    }
  }
  const groups = new Map();
  for (const task of workers) {
    const key = task.workflow_template_id || null;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(task);
  }
  const ordered = [];
  for (const [key, tasks] of groups) {
    if (key !== null) ordered.push({templateId: key, workers: tasks});
  }
  if (groups.has(null)) ordered.push({templateId: null, workers: groups.get(null)});
  return ordered;
}

function _kanbanOfficeCard(task){
  const age = _kanbanTaskAge(task);
  const assignee = task.assignee ? `@${esc(task.assignee)}` : esc(t('kanban_unassigned'));
  const expanded = _kanbanOfficeExpanded.has(task.id);
  const cachedLog = _kanbanOfficeLogCache.get(task.id);
  const logInner = cachedLog !== undefined
    ? (cachedLog ? `<pre class="kanban-office-log-pre">${esc(cachedLog)}</pre>` : `<div class="kanban-empty">${esc(t('kanban_empty') || 'Nothing here yet.')}</div>`)
    : '';
  return `<article class="kanban-office-card" data-office-task-id="${esc(task.id)}">
    <div class="kanban-office-card-head">
      <span class="kanban-office-pulse" aria-hidden="true"></span>
      <span class="kanban-office-assignee">${assignee}</span>
      ${age ? `<span class="kanban-office-age">${esc(age)}</span>` : ''}
    </div>
    <div class="kanban-office-title">${esc(_kanbanTaskTitle(task))}</div>
    <button type="button" class="kanban-office-log-toggle" onclick="toggleKanbanOfficeLog('${esc(task.id)}')">${expanded ? esc(t('kanban_office_hide_log') || 'Hide log') : esc(t('kanban_office_view_log') || 'View log')}</button>
    <div class="kanban-office-log" id="kanban-office-log-${esc(task.id)}" style="display:${expanded ? '' : 'none'}">${logInner}</div>
  </article>`;
}

async function toggleKanbanOfficeLog(taskId){
  if (_kanbanOfficeExpanded.has(taskId)) {
    _kanbanOfficeExpanded.delete(taskId);
    _kanbanRenderOfficeView();
    return;
  }
  _kanbanOfficeExpanded.add(taskId);
  _kanbanRenderOfficeView();
  const logEl = document.getElementById('kanban-office-log-' + taskId);
  if (logEl && _kanbanOfficeLogCache.get(taskId) === undefined) {
    logEl.innerHTML = `<div class="kanban-office-log-loading">${esc(t('loading') || 'Loading…')}</div>`;
  }
  try {
    const data = await api('/api/kanban/tasks/' + encodeURIComponent(taskId) + '/log' + _kanbanBoardQuery({tail: 8192}));
    _kanbanOfficeLogCache.set(taskId, data.content || '');
    if (_kanbanOfficeExpanded.has(taskId)) _kanbanRenderOfficeView();
  } catch(e) {
    const el = document.getElementById('kanban-office-log-' + taskId);
    if (el) el.textContent = (t('error_prefix') || 'Error: ') + e.message;
  }
}

// Crew name for a group header: looked up from the already-loaded /api/crews
// list (loadKanbanCrews(), cached in _kanbanCrewsList) rather than a second
// fetch mechanism. Falls back to the raw template id when the list hasn't
// been loaded yet or the crew was since deleted.
function _kanbanCrewName(templateId){
  const crew = (_kanbanCrewsList || []).find(c => c.id === templateId);
  return (crew && crew.name) ? crew.name : templateId;
}

let _kanbanCrewsListFetchInFlight = false;

function _kanbanOfficeGroupHtml(group){
  const label = group.templateId ? _kanbanCrewName(group.templateId) : (t('kanban_office_ungrouped') || 'Ungrouped');
  return `<section class="kanban-office-group" data-office-group-id="${esc(group.templateId || '')}">
    <h3 class="kanban-office-group-title">${esc(label)}</h3>
    <div class="kanban-office-grid">${group.workers.map(_kanbanOfficeCard).join('')}</div>
  </section>`;
}

function _kanbanRenderOfficeView(){
  const container = $('kanbanOfficeView');
  if (!container || !_kanbanOfficeViewActive) return;
  const groups = _kanbanOfficeViewWorkers();
  const workers = groups.flatMap(g => g.workers);
  const liveIds = new Set(workers.map(w => w.id));
  for (const id of Array.from(_kanbanOfficeExpanded)) if (!liveIds.has(id)) _kanbanOfficeExpanded.delete(id);
  if (!workers.length) {
    container.innerHTML = `<div class="kanban-office-empty">${esc(t('kanban_office_empty') || 'No workers currently running. Dispatch Ready tasks to see them here.')}</div>`;
    return;
  }
  // Lazily fetch crew names once (not on every render) so group headers can
  // show a crew's name instead of its raw id; reuses loadKanbanCrews() --
  // the same function the Crews modal uses -- rather than a parallel fetch.
  if (_kanbanCrewsList === null && !_kanbanCrewsListFetchInFlight) {
    _kanbanCrewsListFetchInFlight = true;
    loadKanbanCrews().then(() => { _kanbanCrewsListFetchInFlight = false; _kanbanRenderOfficeView(); });
  }
  container.innerHTML = groups.map(_kanbanOfficeGroupHtml).join('');
}

async function hardRefreshWebUIClient(){
  try {
    if (navigator.serviceWorker) {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map(r => r.unregister()));
    }
  } catch(_) {}
  try {
    if (window.caches) {
      const keys = await caches.keys();
      await Promise.all(keys.map(k => caches.delete(k)));
    }
  } catch(_) {}
  window.location.reload();
}

function _normalizeWebUIVersion(value){
  if(!value) return '';
  const s=String(value).trim();
  if(!s) return '';
  // Suppress placeholder / non-version sentinels (case-insensitive) so a real
  // client version never "mismatches" against a server that couldn't detect its
  // own version. api/updates.py can emit 'unknown' (git describe failure in a
  // Docker/CI image); comparing a real version against 'unknown' would FALSELY
  // fire the stale-client banner. (Codex #5480 gate)
  const lower=s.toLowerCase();
  if(lower==='__webui_version__'||lower==='not detected'||lower==='unknown') return '';
  return s;
}

function _currentWebUIBundleVersion(){
  try{
    const raw=window.__HERMES_WEBUI_BUNDLE_VERSION__;
    if(!raw) return '';
    let s=String(raw);
    try{ s=decodeURIComponent(s.replace(/\+/g,' ')); }catch(_){}
    return _normalizeWebUIVersion(s);
  }catch(_){ return ''; }
}

function _showStaleWebUIClientBanner(clientVersion,serverVersion){
  const banner=document.getElementById('staleClientBanner');
  if(!banner) return;
  const msg=document.getElementById('staleClientMessage');
  const versions=document.getElementById('staleClientVersions');
  if(msg) msg.textContent='This tab is running a different WebUI version. Hard refresh to restore full functionality.';
  if(versions) versions.textContent='Running: '+clientVersion+' → Server: '+serverVersion;
  banner.style.display='flex';
}

function checkWebUIVersionSkew(settings){
  try{
    if(!settings) return;
    const client=_currentWebUIBundleVersion();
    const server=_normalizeWebUIVersion(settings.webui_version);
    if(!client||!server) return;
    if(client===server) return;
    _showStaleWebUIClientBanner(client,server);
  }catch(_){}
}
window.checkWebUIVersionSkew=checkWebUIVersionSkew;

function _startWebUIVersionSkewMonitor(){
  let _pollTimer=null;
  function _isBannerVisible(){
    const banner=document.getElementById('staleClientBanner');
    return !!(banner&&banner.style.display==='flex');
  }
  function _check(){
    if(_isBannerVisible()) return;
    Promise.resolve().then(function(){ return api('/api/settings'); }).then(function(s){ checkWebUIVersionSkew(s); }).catch(function(){});
  }
  function _startPoll(){
    if(_pollTimer||document.hidden) return;
    _pollTimer=setInterval(function(){
      if(document.hidden){ clearInterval(_pollTimer); _pollTimer=null; return; }
      if(_isBannerVisible()){ clearInterval(_pollTimer); _pollTimer=null; return; }
      _check();
    },60000);
  }
  _check();
  document.addEventListener('visibilitychange',function(){
    if(!document.hidden){ _check(); _startPoll(); }
    else if(_pollTimer){ clearInterval(_pollTimer); _pollTimer=null; }
  });
  window.addEventListener('focus',function(){ _check(); });
  _startPoll();
}
_startWebUIVersionSkewMonitor();

function _kanbanLooksLikeStaleClientError(err){
  const msg = String((err && err.message) || err || '').toLowerCase();
  return !!(err && err.status === 404 && (
    msg === 'not found' ||
    msg.includes('unknown kanban endpoint') ||
    msg.includes('stale cached bundle')
  ));
}

function _kanbanUnavailableHtml(err){
  const raw = String((err && err.message) || err || '');
  if (_kanbanLooksLikeStaleClientError(err)) {
    return `<div class="main-view-empty"><div class="main-view-empty-title">Kanban needs a hard refresh</div><div class="main-view-empty-subtitle">The server rejected an obsolete Kanban endpoint. This usually means the browser or Mac app is still running a stale cached WebUI bundle after an update.</div><button class="btn primary" type="button" onclick="hardRefreshWebUIClient()">${esc(t('update_hard_refresh_now')||'Hard refresh now')}</button><div class="main-view-empty-subtitle">Original error: ${esc(raw || 'not found')}</div></div>`;
  }
  const msg = `${esc(t('kanban_unavailable'))}: ${esc(raw)}`;
  return `<div class="main-view-empty"><div class="main-view-empty-title">${msg}</div></div>`;
}

async function loadKanban(animate){
  const board = $('kanbanBoard');
  const list = $('kanbanList');
  try {
    if (animate && board) board.innerHTML = `<div style="padding:16px;color:var(--muted);font-size:13px">${esc(t('loading'))}</div>`;
    // Resolve the active board before board-scoped requests. If another CLI or
    // tab archived the previous board, /boards can fall back to default instead
    // of leaving config/board pinned to a ghost slug.
    await loadKanbanBoards();
    const config = await api('/api/kanban/config' + _kanbanBoardQuery());
    let assignees = null;
    try { assignees = await api('/api/kanban/assignees' + _kanbanBoardQuery()); } catch(e) { assignees = null; }
    _kanbanApplyConfigDefaults(config);
    const filters = _kanbanCurrentFilters();
    const params = new URLSearchParams();
    if (filters.assignee) params.set('assignee', filters.assignee);
    if (filters.tenant) params.set('tenant', filters.tenant);
    if (filters.includeArchived) params.set('include_archived', '1');
    if (filters.onlyMine) params.set('only_mine', '1');
    if (filters.workflowTemplateId) params.set('workflow_template_id', filters.workflowTemplateId);
    if (_kanbanCurrentBoard) params.set('board', _kanbanCurrentBoard);
    const path = '/api/kanban/board' + (params.toString() ? '?' + params.toString() : '');
    const data = await api(path);
    if (data && data.changed === false && _kanbanBoard) { _kanbanRenderBoard(); return; }
    _kanbanBoard = data || {columns: []};
    if ((!_kanbanBoard.columns || !_kanbanBoard.columns.length) && config && config.columns) {
      _kanbanBoard.columns = config.columns.map(name => ({name, tasks: []}));
    }
    _kanbanLatestEventId = Number(_kanbanBoard.latest_event_id || 0);
    // Toggle the "Read-only view" banner based on the bridge's read_only flag.
    // Bridge sets read_only=true only when the kanban_db connection cannot accept
    // writes (e.g. dispatcher contention or library missing). Hide otherwise.
    try {
      const ro = document.querySelector('.kanban-readonly');
      if (ro) ro.style.display = _kanbanBoard.read_only ? '' : 'none';
    } catch(_) {}
    _kanbanSetSelectOptions($('kanbanAssigneeFilter'), _kanbanBoard.assignees || (assignees && assignees.assignees) || (config && config.assignees), 'kanban_all_assignees');
    _kanbanSetSelectOptions($('kanbanTenantFilter'), _kanbanBoard.tenants, 'kanban_all_tenants');
    await loadKanbanStats();
    // Note: PR #1828 (v0.51.20) moved the boards refresh to the start of
    // loadKanban() so the active board is resolved BEFORE board-scoped
    // requests fire. The previous tail-of-function refresh has been removed
    // to avoid doubling /api/kanban/boards traffic during SSE-driven
    // refreshes (debounced at 250ms via _scheduleKanbanRefresh). The
    // 30-second poll started by _kanbanStartPolling() picks up any board
    // state changes that arrive after this render.
    _kanbanStartPolling();
    _kanbanRenderBoard();
  } catch(e) {
    const html = _kanbanUnavailableHtml(e);
    if (board) board.innerHTML = html;
    if (list) list.innerHTML = html;
  }
}

function filterKanban(){ _kanbanRenderBoard(); }

async function loadKanbanStats(){
  try {
    const stats = await api('/api/kanban/stats' + _kanbanBoardQuery());
    const el = $('kanbanStats');
    if (!el) return;
    const byStatus = (stats && stats.by_status) || {};
    const total = Object.values(byStatus).reduce((a, b) => a + Number(b || 0), 0);
    const cells = Object.entries(byStatus).sort(([a], [b]) => a.localeCompare(b)).map(([status, count]) =>
      `<span class="kanban-stat-cell"><strong>${esc(String(count))}</strong> ${esc(_kanbanColumnLabel(status))}</span>`
    ).join('');
    el.innerHTML = `<div class="kanban-stats-grid"><span class="kanban-stat-cell total"><strong>${esc(String(total))}</strong> ${esc(t('kanban_stats'))}</span>${cells}</div>`;
  } catch(e) { /* stats are best-effort */ }
}

async function refreshKanbanEvents(){
  if (_currentPanel !== 'kanban' || !_kanbanLatestEventId) return;
  try {
    const eventsEndpoint = '/api/kanban/events';
    const events = await api(eventsEndpoint + _kanbanBoardQuery({since: _kanbanLatestEventId}));
    if (events && Array.isArray(events.events) && events.events.length) {
      _kanbanLatestEventId = Number(events.latest_event_id || events.cursor || _kanbanLatestEventId);
      await loadKanban(true);
      if (_kanbanCurrentTaskId && events.events.some(ev => ev.task_id === _kanbanCurrentTaskId)) await loadKanbanTask(_kanbanCurrentTaskId);
    }
  } catch(e) { /* polling should not spam toasts */ }
}

function _kanbanStartPolling(){
  // Prefer SSE for low-latency live updates. Fall back to polling on
  // browsers without EventSource or after repeated stream failures.
  if (typeof EventSource === 'undefined' || _kanbanEventSourceFailures >= 3) {
    if (_kanbanPollTimer) return;
    _kanbanPollTimer = setInterval(refreshKanbanEvents, 30000);
    return;
  }
  _kanbanStartEventStream();
}

function _kanbanStopPolling(){
  if (_kanbanPollTimer) { clearInterval(_kanbanPollTimer); _kanbanPollTimer = null; }
  if (_kanbanEventSource) { try { if(_kanbanEventSource.readyState!==2)_kanbanEventSource.close(); } catch(_) {} _kanbanEventSource = null; }
}

function _kanbanStartEventStream(){
  // Tear down any prior stream before opening a new one (board switch,
  // login change, etc.).
  if (_kanbanEventSource) { try { if(_kanbanEventSource.readyState!==2)_kanbanEventSource.close(); } catch(_) {} _kanbanEventSource = null; }
  const since = Number(_kanbanLatestEventId || 0);
  let url = '/api/kanban/events/stream' + _kanbanBoardQuery({since: since});
  let es;
  try {
    es = new EventSource(url);
  } catch(e) {
    _kanbanEventSourceFailures += 1;
    if (_kanbanEventSourceFailures < 3 && !_kanbanPollTimer) {
      _kanbanPollTimer = setInterval(refreshKanbanEvents, 30000);
    }
    return;
  }
  _kanbanEventSource = es;
  es.addEventListener('hello', (ev) => {
    // Reset the failure counter on a successful handshake.
    _kanbanEventSourceFailures = 0;
  });
  es.addEventListener('events', async (ev) => {
    if (_currentPanel !== 'kanban') return;  // ignore while user is on another panel
    let data;
    try { data = JSON.parse(ev.data); } catch(_) { return; }
    if (!data || !Array.isArray(data.events) || !data.events.length) return;
    _kanbanLatestEventId = Number(data.cursor || _kanbanLatestEventId);
    // Re-fetch the board so the visual state reflects the new events.
    // Throttle: if events are arriving faster than ~1/sec we coalesce.
    _scheduleKanbanRefresh(data.events);
  });
  es.onerror = () => {
    _kanbanEventSourceFailures += 1;
    if (_kanbanEventSourceFailures >= 3) {
      // Give up on SSE for this session — fall back to HTTP polling.
      try { es.close(); } catch(_) {}
      _kanbanEventSource = null;
      if (!_kanbanPollTimer) _kanbanPollTimer = setInterval(refreshKanbanEvents, 30000);
    }
    // EventSource auto-reconnects under the hood; nothing more to do here
    // until we hit the failure limit.
  };
}

let _kanbanRefreshScheduled = false;
let _kanbanRefreshPendingTaskIds = new Set();
function _scheduleKanbanRefresh(events){
  for (const ev of events) {
    if (ev && ev.task_id) _kanbanRefreshPendingTaskIds.add(ev.task_id);
  }
  if (_kanbanRefreshScheduled) return;
  _kanbanRefreshScheduled = true;
  // 250ms debounce — keeps a burst of N events from triggering N reloads.
  setTimeout(async () => {
    _kanbanRefreshScheduled = false;
    const taskIds = Array.from(_kanbanRefreshPendingTaskIds);
    _kanbanRefreshPendingTaskIds.clear();
    if (_currentPanel !== 'kanban') return;
    try {
      await loadKanban(true);
      if (_kanbanCurrentTaskId && taskIds.includes(_kanbanCurrentTaskId)) {
        await loadKanbanTask(_kanbanCurrentTaskId);
      }
    } catch(_) { /* swallow — SSE refresh shouldn't toast */ }
  }, 250);
}

// Build a "?board=<slug>" or "?since=N&board=<slug>" query string fragment
// based on the active board. Empty when the user is on the default board
// AND nobody has explicitly switched (so we don't pin to "default" and
// override a hypothetical server-side switch).
function _kanbanBoardQuery(extra){
  const params = new URLSearchParams();
  if (extra) {
    for (const [k, v] of Object.entries(extra)) {
      if (v !== null && v !== undefined && v !== '') params.set(k, String(v));
    }
  }
  if (_kanbanCurrentBoard) params.set('board', _kanbanCurrentBoard);
  const s = params.toString();
  return s ? '?' + s : '';
}

async function nudgeKanbanDispatcher(){
  if (_kanbanIsDispatching) return;
  // Dry-run dispatch: show what WOULD be spawned, without actually spawning
  // workers.  Uses ?dry_run=1 so the dispatcher reports its plan without
  // mutating the board.  The result shape includes spawned/skipped_unassigned/
  // skipped_nonspawnable/promoted/auto_blocked so users can diagnose why a
  // Ready task isn't being picked up before they commit to a real run.
  _kanbanIsDispatching = true;
  _setKanbanDispatcherButtonsDisabled(true);
  try {
    const dispatchEndpoint = '/api/kanban/dispatch';
    const result = await api(
      dispatchEndpoint + '?dry_run=1&max=8' + (_kanbanCurrentBoard ? '&board=' + encodeURIComponent(_kanbanCurrentBoard) : ''),
      {method: 'POST'},
    );
    showToast(_kanbanFormatDispatchResult(result, true), 'info', 6000);
    await loadKanban(true);
  } catch(e) {
    showToast(t('kanban_unavailable') + ': ' + (e.message || e), 'error');
  } finally {
    _kanbanIsDispatching = false;
    _setKanbanDispatcherButtonsDisabled(false);
  }
}

async function runKanbanDispatcher(){
  if (_kanbanIsDispatching) return;
  // Real dispatch: claims Ready tasks and spawns worker subprocesses
  // (one `hermes -p <assignee>` per claimed row, up to max=8 per call).
  // Confirmation dialog first because this actually consumes API budget on
  // each spawned worker.  Result toast surfaces what happened so users see
  // the dispatcher actually doing work.

  _kanbanIsDispatching = true;
  _setKanbanDispatcherButtonsDisabled(true);
  try {
    const ok = await showConfirmDialog({
      title: t('kanban_run_dispatcher') || 'Run dispatcher',
      message: t('kanban_run_dispatcher_confirm')
        || 'This will claim Ready tasks on this board and spawn worker subprocesses (one per task, up to 8 per click). Continue?',
      confirmLabel: t('kanban_run_dispatcher') || 'Run dispatcher',
    });
    if (!ok) return;
    const dispatchEndpoint = '/api/kanban/dispatch';
    const result = await api(
      dispatchEndpoint + '?max=8' + (_kanbanCurrentBoard ? '&board=' + encodeURIComponent(_kanbanCurrentBoard) : ''),
      {method: 'POST'},
    );
    showToast(_kanbanFormatDispatchResult(result, false), 'info', 8000);
    await loadKanban(true);
  } catch(e) {
    showToast(t('kanban_unavailable') + ': ' + (e.message || e), 'error');
  } finally {
    _kanbanIsDispatching = false;
    _setKanbanDispatcherButtonsDisabled(false);
  }
}

function _setKanbanDispatcherButtonsDisabled(disabled){
  document.querySelectorAll('.kanban-run-dispatch-btn, .kanban-nudge-dispatch-btn').forEach((btn) => {
    btn.disabled = !!disabled;
    btn.classList.toggle('disabled', !!disabled);
  });
}

function _kanbanFormatDispatchResult(result, dryRun){
  // Produce a human-readable one-line summary of dispatch_once's output so
  // users can see exactly what happened rather than a generic "OK" toast.
  const r = result || {};
  const spawned = (r.spawned || []).length;
  const promoted = r.promoted || 0;
  const reclaimed = r.reclaimed || 0;
  const skippedUnassigned = (r.skipped_unassigned || []).length;
  const skippedNonspawnable = (r.skipped_nonspawnable || []).length;
  const autoBlocked = (r.auto_blocked || []).length;
  const timedOut = (r.timed_out || []).length;
  const crashed = (r.crashed || []).length;
  const verb = dryRun ? (t('kanban_dispatch_preview_prefix') || 'Preview:') : (t('kanban_dispatch_run_prefix') || 'Dispatched:');
  const parts = [];
  parts.push(spawned + ' ' + (t('kanban_dispatch_spawned') || 'spawned'));
  if (promoted) parts.push(promoted + ' ' + (t('kanban_dispatch_promoted') || 'promoted'));
  if (reclaimed) parts.push(reclaimed + ' ' + (t('kanban_dispatch_reclaimed') || 'reclaimed'));
  if (skippedUnassigned) parts.push(skippedUnassigned + ' ' + (t('kanban_dispatch_skipped_unassigned') || 'skipped (no assignee)'));
  if (skippedNonspawnable) parts.push(skippedNonspawnable + ' ' + (t('kanban_dispatch_skipped_nonspawnable') || 'skipped (unknown profile)'));
  if (autoBlocked) parts.push(autoBlocked + ' ' + (t('kanban_dispatch_auto_blocked') || 'auto-blocked'));
  if (timedOut) parts.push(timedOut + ' ' + (t('kanban_dispatch_timed_out') || 'timed out'));
  if (crashed) parts.push(crashed + ' ' + (t('kanban_dispatch_crashed') || 'crashed'));
  return verb + ' ' + parts.join(', ');
}

// ────────────────────────────────────────────────────────────────────────────
// Crews (multi-agent dispatch templates) -- docs/HERMES_STUDIO_PARITY_PLAN.md,
// "Multi-agent orchestration (Crews + Conductor)" -> Phase 1.
//
// Additive UI *inside* the existing Kanban panel (no new nav tab, no new
// MAIN_VIEW_PANELS entry) -- the same `.kanban-modal-overlay` shell as
// openKanbanCreateBoard()/openKanbanCreate() so it looks and behaves like the
// rest of Kanban's modals. A crew is a named, ordered list of Kanban task
// specs; dispatching one bulk-CREATEs those tasks (tagged with a shared
// workflow_template_id/current_step_key) -- it deliberately does NOT call the
// dispatcher/dispatch_once, matching runKanbanDispatcher's separate
// explicit-confirm-then-click pattern for anything that spawns/queues actual
// worker subprocesses.
// ────────────────────────────────────────────────────────────────────────────

let _kanbanCrewsList = null;          // cached list from GET /api/crews
let _kanbanCrewDispatchVarsModalFocusCleanup = null;
let _kanbanCrewDispatchVarsResolve = null; // pending Promise resolver for the open vars dialog
let _kanbanCrewFormMode = 'create';   // 'create' | 'edit'
let _kanbanCrewFormEditingId = null;
let _kanbanCrewFormTaskSeq = 0;       // monotonic id source for dynamic task rows
let _kanbanCrewsModalFocusCleanup = null;
let _kanbanCrewFormModalFocusCleanup = null;

async function openKanbanCrews(){
  if (typeof switchPanel === 'function' && _currentPanel !== 'kanban') switchPanel('kanban');
  const modal = document.getElementById('kanbanCrewsModal');
  if (!modal) return;
  modal.hidden = false;
  if (_kanbanCrewsModalFocusCleanup) { _kanbanCrewsModalFocusCleanup(); _kanbanCrewsModalFocusCleanup = null; }
  _kanbanCrewsModalFocusCleanup = _trapModalFocus(modal);
  document.addEventListener('keydown', _kanbanCrewsModalEsc);
  await loadKanbanCrews();
}

function _kanbanCrewsModalEsc(ev){ if (ev.key === 'Escape') closeKanbanCrewsModal(); }

function closeKanbanCrewsModal(){
  const modal = document.getElementById('kanbanCrewsModal');
  if (modal) modal.hidden = true;
  if (_kanbanCrewsModalFocusCleanup) { _kanbanCrewsModalFocusCleanup(); _kanbanCrewsModalFocusCleanup = null; }
  document.removeEventListener('keydown', _kanbanCrewsModalEsc);
}

async function loadKanbanCrews(){
  const errEl = document.getElementById('kanbanCrewsModalError');
  if (errEl) errEl.textContent = '';
  try {
    const data = await api('/api/crews');
    _kanbanCrewsList = (data && Array.isArray(data.crews)) ? data.crews : [];
    _renderKanbanCrewList();
  } catch(e) {
    if (errEl) errEl.textContent = (e && (e.message || e.error)) || String(e);
    const listEl = document.getElementById('kanbanCrewList');
    if (listEl) listEl.innerHTML = '';
  }
}

// Phase 1.2 (docs/HERMES_STUDIO_PARITY_PLAN.md, "templates gallery: search +
// last-dispatched recency"): pure functions, no DOM access, so they can be
// executed directly by tests/test_crews_ui.py's node-extraction harness
// rather than only checked as source strings.

// Case-insensitive substring match against name OR description. An
// empty/whitespace-only query returns the input list unfiltered, in order.
function _kanbanFilterCrews(crews, query){
  const q = (query || '').trim().toLowerCase();
  if (!q) return crews;
  return crews.filter(c =>
    (c.name || '').toLowerCase().includes(q) ||
    (c.description || '').toLowerCase().includes(q)
  );
}

// Most-recently-dispatched first; never-dispatched (null) crews sort last;
// ties (including "never dispatched" vs "never dispatched") broken by
// created_at descending, so a fresh list still reads newest-first.
function _kanbanSortCrews(crews){
  return [...crews].sort((a, b) => {
    const ad = a.last_dispatched_at, bd = b.last_dispatched_at;
    if (ad != null && bd != null) {
      if (ad !== bd) return bd - ad;
    } else if (ad != null) {
      return -1;
    } else if (bd != null) {
      return 1;
    }
    return (b.created_at || 0) - (a.created_at || 0);
  });
}

function filterKanbanCrews(){
  _renderKanbanCrewList();
}

function _renderKanbanCrewList(){
  const listEl = document.getElementById('kanbanCrewList');
  if (!listEl) return;
  const all = _kanbanCrewsList || [];
  if (!all.length) {
    listEl.innerHTML = `<div class="kanban-empty">${esc(t('kanban_crews_empty') || 'No crews yet. Create one to bulk-dispatch a set of tasks together.')}</div>`;
    return;
  }
  const searchEl = document.getElementById('kanbanCrewsSearch');
  const query = (searchEl && searchEl.value) || '';
  const crews = _kanbanSortCrews(_kanbanFilterCrews(all, query));
  if (!crews.length) {
    listEl.innerHTML = `<div class="kanban-empty">${esc(t('kanban_crews_no_match') || 'No crews match your search.')}</div>`;
    return;
  }
  listEl.innerHTML = crews.map(_kanbanCrewCard).join('');
}

function _kanbanCrewCard(crew){
  const icon = crew.icon ? esc(crew.icon) : '👥';
  const taskCount = Array.isArray(crew.tasks) ? crew.tasks.length : 0;
  const color = crew.color ? esc(crew.color) : 'var(--accent)';
  const taskWord = taskCount === 1 ? (t('kanban_crew_task_singular') || 'task') : (t('kanban_crew_task_plural') || 'tasks');
  // Reuses _formatRelativeSessionTime (static/sessions.js) rather than a
  // second relative-time formatter -- already generic despite the name, and
  // its session_time_* i18n keys are already present in all 15 locales.
  const lastDispatchedText = crew.last_dispatched_at
    ? (t('kanban_crew_last_dispatched') || 'Last dispatched: {0}').replace('{0}', _formatRelativeSessionTime(crew.last_dispatched_at * 1000))
    : (t('kanban_crew_never_dispatched') || 'Never dispatched');
  return `<article class="kanban-crew-card" style="--kanban-crew-color:${color}" data-crew-id="${esc(crew.id)}">
    <div class="kanban-crew-card-head">
      <span class="kanban-crew-card-icon" aria-hidden="true">${icon}</span>
      <span class="kanban-crew-card-name">${esc(crew.name || '')}</span>
    </div>
    ${crew.description ? `<div class="kanban-crew-card-desc">${esc(crew.description)}</div>` : ''}
    <div class="kanban-crew-card-meta">${esc(String(taskCount))} ${esc(taskWord)}</div>
    <div class="kanban-crew-card-last-dispatched">${esc(lastDispatchedText)}</div>
    <div class="kanban-crew-card-actions">
      <button type="button" class="btn primary" onclick="dispatchKanbanCrew('${esc(crew.id)}')" data-i18n="kanban_crew_dispatch">Dispatch</button>
      <button type="button" class="btn secondary" onclick="openKanbanCrewForm('${esc(crew.id)}')" data-i18n="edit">Edit</button>
      <button type="button" class="btn secondary" onclick="duplicateKanbanCrew('${esc(crew.id)}')" data-i18n="kanban_crew_duplicate">Duplicate</button>
      <button type="button" class="btn danger" onclick="deleteKanbanCrew('${esc(crew.id)}')" data-i18n="delete_title">Delete</button>
    </div>
  </article>`;
}

async function openKanbanCrewForm(crewId){
  const modal = document.getElementById('kanbanCrewFormModal');
  if (!modal) return;
  const errEl = document.getElementById('kanbanCrewFormError');
  if (errEl) errEl.textContent = '';
  const tasksContainer = document.getElementById('kanbanCrewFormTasks');
  if (tasksContainer) tasksContainer.innerHTML = '';
  _kanbanCrewFormTaskSeq = 0;
  if (crewId) {
    const crew = (_kanbanCrewsList || []).find(c => c.id === crewId) || null;
    _kanbanCrewFormMode = 'edit';
    _kanbanCrewFormEditingId = crewId;
    document.getElementById('kanbanCrewFormModalTitle').textContent = (t('edit') || 'Edit') + (crew && crew.name ? ': ' + crew.name : '');
    document.getElementById('kanbanCrewFormId').value = crewId;
    document.getElementById('kanbanCrewFormName').value = (crew && crew.name) || '';
    document.getElementById('kanbanCrewFormIcon').value = (crew && crew.icon) || '';
    document.getElementById('kanbanCrewFormColor').value = (crew && crew.color) || '#7cb9ff';
    document.getElementById('kanbanCrewFormDescription').value = (crew && crew.description) || '';
    const tasks = (crew && Array.isArray(crew.tasks) && crew.tasks.length) ? crew.tasks : [{}];
    for (const taskSpec of tasks) await _kanbanAddCrewTaskRow(taskSpec);
  } else {
    _kanbanCrewFormMode = 'create';
    _kanbanCrewFormEditingId = null;
    document.getElementById('kanbanCrewFormModalTitle').textContent = t('kanban_new_crew') || 'New crew';
    document.getElementById('kanbanCrewFormId').value = '';
    document.getElementById('kanbanCrewFormName').value = '';
    document.getElementById('kanbanCrewFormIcon').value = '';
    document.getElementById('kanbanCrewFormColor').value = '#7cb9ff';
    document.getElementById('kanbanCrewFormDescription').value = '';
    await _kanbanAddCrewTaskRow({});
  }
  modal.hidden = false;
  if (_kanbanCrewFormModalFocusCleanup) { _kanbanCrewFormModalFocusCleanup(); _kanbanCrewFormModalFocusCleanup = null; }
  _kanbanCrewFormModalFocusCleanup = _trapModalFocus(modal);
  document.addEventListener('keydown', _kanbanCrewFormModalEsc);
  setTimeout(() => { const el = document.getElementById('kanbanCrewFormName'); if (el) el.focus(); }, 50);
}

function _kanbanCrewFormModalEsc(ev){ if (ev.key === 'Escape') closeKanbanCrewFormModal(); }

function closeKanbanCrewFormModal(){
  const modal = document.getElementById('kanbanCrewFormModal');
  if (modal) modal.hidden = true;
  if (_kanbanCrewFormModalFocusCleanup) { _kanbanCrewFormModalFocusCleanup(); _kanbanCrewFormModalFocusCleanup = null; }
  document.removeEventListener('keydown', _kanbanCrewFormModalEsc);
}

async function _kanbanAddCrewTaskRow(taskSpec){
  const container = document.getElementById('kanbanCrewFormTasks');
  if (!container) return;
  const rowId = 'kanbanCrewTaskRow' + (_kanbanCrewFormTaskSeq++);
  const spec = taskSpec || {};
  const row = document.createElement('div');
  row.className = 'kanban-crew-task-row';
  row.id = rowId;
  row.innerHTML = `
    <div class="kanban-modal-row">
      <label data-i18n="kanban_crew_task_title">Title</label>
      <input type="text" class="kanban-crew-task-title" maxlength="200" value="${esc(spec.title || '')}" data-i18n-placeholder="kanban_crew_task_title_placeholder" placeholder="Task title — supports {variable} placeholders">
    </div>
    <div class="kanban-modal-row">
      <label data-i18n="kanban_crew_task_body">Description</label>
      <textarea class="kanban-crew-task-body" maxlength="4000">${esc(spec.body || '')}</textarea>
    </div>
    <div class="kanban-modal-row-inline">
      <div class="kanban-modal-row">
        <label data-i18n="kanban_crew_task_assignee">Assignee</label>
        <select class="kanban-crew-task-assignee" id="${rowId}-assignee"></select>
      </div>
      <div class="kanban-modal-row">
        <label data-i18n="kanban_crew_task_priority">Priority</label>
        <input type="number" class="kanban-crew-task-priority" value="${Number(spec.priority || 0)}" min="-100" max="100" step="1">
      </div>
    </div>
    <div class="kanban-modal-row">
      <label data-i18n="kanban_crew_task_skills">Skills</label>
      <input type="text" class="kanban-crew-task-skills" maxlength="255" value="${esc(Array.isArray(spec.skills) ? spec.skills.join(', ') : '')}" data-i18n-placeholder="kanban_crew_task_skills_placeholder" placeholder="Comma-separated skill names">
    </div>
    <button type="button" class="btn secondary kanban-crew-task-remove" onclick="_kanbanRemoveCrewTaskRow('${rowId}')" data-i18n="kanban_crew_remove_task">Remove</button>
  `;
  container.appendChild(row);
  // Reuses _kanbanPopulateAssigneeSelect() verbatim (via its optional target
  // param) rather than a parallel profile-lookup implementation -- each task
  // row gets its own <select> since a crew form can have several rows open
  // at once, unlike the single-task modal.
  await _kanbanPopulateAssigneeSelect(spec.assignee || '', document.getElementById(rowId + '-assignee'));
}

function _kanbanRemoveCrewTaskRow(rowId){
  const row = document.getElementById(rowId);
  const container = document.getElementById('kanbanCrewFormTasks');
  if (row && container && container.children.length > 1) row.remove();
}

function _kanbanCollectCrewFormTasks(){
  const rows = document.querySelectorAll('#kanbanCrewFormTasks .kanban-crew-task-row');
  const tasks = [];
  rows.forEach(row => {
    const title = (row.querySelector('.kanban-crew-task-title').value || '').trim();
    if (!title) return;
    const body = (row.querySelector('.kanban-crew-task-body').value || '').trim();
    const assignee = (row.querySelector('.kanban-crew-task-assignee').value || '').trim();
    const priority = Number(row.querySelector('.kanban-crew-task-priority').value || 0);
    const skillsRaw = (row.querySelector('.kanban-crew-task-skills').value || '').trim();
    const skills = skillsRaw ? skillsRaw.split(',').map(s => s.trim()).filter(Boolean) : [];
    tasks.push({title, body, assignee: assignee || null, priority, skills});
  });
  return tasks;
}

async function submitKanbanCrewForm(){
  const errEl = document.getElementById('kanbanCrewFormError');
  if (errEl) errEl.textContent = '';
  const name = (document.getElementById('kanbanCrewFormName').value || '').trim();
  const icon = (document.getElementById('kanbanCrewFormIcon').value || '').trim();
  const color = (document.getElementById('kanbanCrewFormColor').value || '').trim();
  const description = (document.getElementById('kanbanCrewFormDescription').value || '').trim();
  const tasks = _kanbanCollectCrewFormTasks();
  if (!name) { if (errEl) errEl.textContent = t('kanban_crew_name_required') || 'Name is required'; return; }
  if (!tasks.length) { if (errEl) errEl.textContent = t('kanban_crew_tasks_required') || 'At least one task spec (with a title) is required'; return; }
  const submitBtn = document.getElementById('kanbanCrewFormSubmit');
  if (submitBtn) submitBtn.disabled = true;
  try {
    const body = {name, icon, color, description, tasks};
    if (_kanbanCrewFormMode === 'edit' && _kanbanCrewFormEditingId) {
      body.id = _kanbanCrewFormEditingId;
      await api('/api/crews/update', {method: 'POST', body: JSON.stringify(body)});
      showToast(t('kanban_crew_updated') || 'Crew updated', 'success');
    } else {
      await api('/api/crews/create', {method: 'POST', body: JSON.stringify(body)});
      showToast(t('kanban_crew_created') || 'Crew created', 'success');
    }
    closeKanbanCrewFormModal();
    await loadKanbanCrews();
  } catch(e) {
    if (errEl) errEl.textContent = (e && (e.message || e.error)) || String(e);
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

async function duplicateKanbanCrew(id){
  try {
    await api('/api/crews/duplicate', {method: 'POST', body: JSON.stringify({id})});
    showToast(t('kanban_crew_duplicated') || 'Crew duplicated', 'success');
    await loadKanbanCrews();
  } catch(e) {
    showToast((e && (e.message || e.error)) || String(e), 'error');
  }
}

async function deleteKanbanCrew(id){
  const crew = (_kanbanCrewsList || []).find(c => c.id === id);
  const label = (crew && crew.name) || id;
  const ok = await showConfirmDialog({
    title: t('delete_title') || 'Delete',
    message: (t('kanban_crew_delete_confirm') || 'Delete crew "{0}"?').replace('{0}', label),
    confirmLabel: t('delete_title') || 'Delete',
    danger: true,
    focusCancel: true,
  });
  if (!ok) return;
  try {
    await api('/api/crews/delete', {method: 'POST', body: JSON.stringify({id})});
    showToast(t('kanban_crew_deleted') || 'Crew deleted', 'success');
    await loadKanbanCrews();
  } catch(e) {
    showToast((e && (e.message || e.error)) || String(e), 'error');
  }
}

function _kanbanCrewTemplateVariables(crew){
  const names = [];
  const seen = new Set();
  const specs = (crew && Array.isArray(crew.tasks)) ? crew.tasks : [];
  const re = /\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g;
  for (const spec of specs) {
    for (const text of [String((spec && spec.title) || ''), String((spec && spec.body) || '')]) {
      let m;
      re.lastIndex = 0;
      while ((m = re.exec(text))) {
        const name = m[1];
        if (!seen.has(name)) { seen.add(name); names.push(name); }
      }
    }
  }
  return names;
}

function _kanbanHideCrewDispatchVarsModal(){
  const modal = document.getElementById('kanbanCrewDispatchVarsModal');
  if (modal) modal.hidden = true;
  if (_kanbanCrewDispatchVarsModalFocusCleanup) { _kanbanCrewDispatchVarsModalFocusCleanup(); _kanbanCrewDispatchVarsModalFocusCleanup = null; }
  document.removeEventListener('keydown', _kanbanCrewDispatchVarsModalEsc);
}

function _kanbanCrewDispatchVarsModalEsc(ev){ if (ev.key === 'Escape') closeKanbanCrewDispatchVarsModal(); }

// Cancel path (Cancel button, overlay click, or Esc) -- resolves the pending
// Promise with null so the caller (dispatchKanbanCrew) knows to abort without
// ever reaching the dispatch POST.
function closeKanbanCrewDispatchVarsModal(){
  _kanbanHideCrewDispatchVarsModal();
  const resolve = _kanbanCrewDispatchVarsResolve;
  _kanbanCrewDispatchVarsResolve = null;
  if (resolve) resolve(null);
}

// Opens the one-input-per-variable form and returns a Promise that resolves
// to {name: value, ...} on submit, or null if the dialog is cancelled.
function openKanbanCrewDispatchVarsModal(variableNames){
  const modal = document.getElementById('kanbanCrewDispatchVarsModal');
  const fields = document.getElementById('kanbanCrewDispatchVarsFields');
  const errEl = document.getElementById('kanbanCrewDispatchVarsError');
  if (errEl) errEl.textContent = '';
  if (!modal || !fields) return Promise.resolve(null);
  fields.innerHTML = variableNames.map(name => `
    <div class="kanban-modal-row">
      <label for="kanbanCrewDispatchVar-${esc(name)}">${esc((t('kanban_crew_dispatch_vars_label') || 'Value for {0}').replace('{0}', name))}</label>
      <input type="text" class="kanban-crew-dispatch-var-input" id="kanbanCrewDispatchVar-${esc(name)}" data-var-name="${esc(name)}" data-i18n-placeholder="kanban_crew_dispatch_vars_placeholder" placeholder="${esc(t('kanban_crew_dispatch_vars_placeholder') || 'Enter a value…')}" autocomplete="off">
    </div>`).join('');
  modal.hidden = false;
  if (_kanbanCrewDispatchVarsModalFocusCleanup) { _kanbanCrewDispatchVarsModalFocusCleanup(); _kanbanCrewDispatchVarsModalFocusCleanup = null; }
  _kanbanCrewDispatchVarsModalFocusCleanup = _trapModalFocus(modal);
  document.addEventListener('keydown', _kanbanCrewDispatchVarsModalEsc);
  return new Promise(resolve => {
    _kanbanCrewDispatchVarsResolve = resolve;
    setTimeout(() => { const el = fields.querySelector('input'); if (el) el.focus(); }, 50);
  });
}

// Submit path -- validates every field is non-empty (an unfilled variable
// would otherwise hit api/crews.py's _substitute_variables KeyError and turn
// into a silent per-task-spec dispatch failure), then resolves the pending
// Promise with the collected {name: value} map.
function _kanbanSubmitCrewDispatchVars(){
  const errEl = document.getElementById('kanbanCrewDispatchVarsError');
  if (errEl) errEl.textContent = '';
  const inputs = document.querySelectorAll('#kanbanCrewDispatchVarsFields .kanban-crew-dispatch-var-input');
  const variables = {};
  for (const el of inputs) {
    const name = el.getAttribute('data-var-name');
    const value = (el.value || '').trim();
    if (!value) {
      if (errEl) errEl.textContent = t('kanban_crew_dispatch_vars_required') || 'All variables must have a value';
      return;
    }
    variables[name] = value;
  }
  _kanbanHideCrewDispatchVarsModal();
  const resolve = _kanbanCrewDispatchVarsResolve;
  _kanbanCrewDispatchVarsResolve = null;
  if (resolve) resolve(variables);
}

async function dispatchKanbanCrew(id){
  const crew = (_kanbanCrewsList || []).find(c => c.id === id);
  const taskCount = (crew && Array.isArray(crew.tasks)) ? crew.tasks.length : 0;
  // Cost-consuming-action confirm — same wording pattern as
  // runKanbanDispatcher(). This only bulk-CREATEs the crew's tasks (staged
  // Ready); it deliberately does NOT call the dispatcher/dispatch_once, so it
  // does not by itself spawn any worker subprocess. A human still clicks Run
  // Dispatcher separately to actually run the newly created tasks.
  const ok = await showConfirmDialog({
    title: t('kanban_crew_dispatch_confirm_title') || 'Dispatch crew',
    message: (t('kanban_crew_dispatch_confirm_message') || 'This will create {0} task(s) on the board (staged as Ready). Continue?').replace('{0}', String(taskCount)),
    confirmLabel: t('kanban_crew_dispatch') || 'Dispatch',
  });
  if (!ok) return;
  // If the crew's task specs reference any {variable} placeholders, collect
  // real values before dispatching -- otherwise api/crews.py's
  // _substitute_variables either leaves the literal "{name}" in the created
  // task or raises KeyError (surfaced as a per-task-spec dispatch failure).
  // Zero-placeholder crews skip this step entirely and dispatch exactly as
  // before, with an empty variables map.
  let variables = {};
  const variableNames = _kanbanCrewTemplateVariables(crew);
  if (variableNames.length) {
    const collected = await openKanbanCrewDispatchVarsModal(variableNames);
    if (!collected) return; // cancelled -- never reach the dispatch call
    variables = collected;
  }
  try {
    const dispatchBody = {variables};
    if (_kanbanCurrentBoard) dispatchBody.board = _kanbanCurrentBoard;
    const result = await api('/api/crews/' + encodeURIComponent(id) + '/dispatch', {
      method: 'POST',
      body: JSON.stringify(dispatchBody),
    });
    const results = (result && result.results) || [];
    const okCount = results.filter(r => r && r.ok).length;
    showToast(
      (t('kanban_crew_dispatch_result') || 'Dispatched {0} of {1} tasks')
        .replace('{0}', String(okCount)).replace('{1}', String(results.length)),
      'info', 8000,
    );
    kanbanWorkflowTemplateFilter = id;
    closeKanbanCrewsModal();
    await loadKanban(true);
  } catch(e) {
    showToast((e && (e.message || e.error)) || String(e), 'error');
  }
}

function _kanbanSelectedTaskIds(){
  const selected = Array.from(document.querySelectorAll('.kanban-card.selected')).map(card => card.dataset.kanbanTaskId).filter(Boolean);
  return selected.length ? selected : (_kanbanCurrentTaskId ? [_kanbanCurrentTaskId] : []);
}

async function bulkUpdateKanban(){
  const ids = _kanbanSelectedTaskIds();
  const status = $('kanbanBulkStatus') ? $('kanbanBulkStatus').value : '';
  if (!ids.length || !status) return;
  try {
    await api('/api/kanban/tasks/bulk' + _kanbanBoardQuery(), {method: 'POST', body: JSON.stringify({ids, status})});
    showToast(t('kanban_bulk_action'));
    await loadKanban(true);
  } catch(e) { showToast(t('kanban_unavailable') + ': ' + (e.message || e), 'error'); }
}

async function blockKanbanTask(taskId){
  try {
    await api('/api/kanban/tasks/' + encodeURIComponent(taskId) + '/block' + _kanbanBoardQuery(), {method: 'POST', body: JSON.stringify({reason: 'blocked from WebUI'})});
    await loadKanbanTask(taskId);
    await loadKanban(true);
  } catch(e) { showToast(t('kanban_unavailable') + ': ' + (e.message || e), 'error'); }
}

async function unblockKanbanTask(taskId){
  try {
    await api('/api/kanban/tasks/' + encodeURIComponent(taskId) + '/unblock' + _kanbanBoardQuery(), {method: 'POST', body: JSON.stringify({})});
    await loadKanbanTask(taskId);
    await loadKanban(true);
  } catch(e) { showToast(t('kanban_unavailable') + ': ' + (e.message || e), 'error'); }
}

function closeKanbanTaskDetail(){
  _kanbanCurrentTaskId = null;
  const preview = $('kanbanTaskPreview');
  if (preview) {
    preview.style.display = 'none';
    preview.innerHTML = '';
  }
  const board = $('kanbanBoard');
  if (board) board.querySelectorAll('.kanban-card').forEach(card => card.classList.remove('selected'));
}

function _kanbanFormatTimestamp(value){
  if (value === undefined || value === null || value === '') return '';
  let date = null;
  if (typeof value === 'number') date = new Date(value > 100000000000 ? value : value * 1000);
  else if (/^\d+(?:\.\d+)?$/.test(String(value).trim())) {
    const n = Number(value);
    date = new Date(n > 100000000000 ? n : n * 1000);
  } else {
    date = new Date(value);
  }
  if (!date || Number.isNaN(date.getTime())) return String(value);
  try { return date.toLocaleString(); } catch(e) { return date.toISOString(); }
}

function _kanbanEventSummary(event){
  const kind = event.kind || event.type || 'event';
  const payload = event.payload || event.data || {};
  if (payload && typeof payload === 'object') {
    const parts = [];
    if (payload.status) parts.push(String(payload.status));
    if (payload.reason) parts.push(String(payload.reason));
    if (payload.summary) parts.push(String(payload.summary));
    if (payload.fields && Array.isArray(payload.fields)) parts.push(payload.fields.join(', '));
    if (parts.length) return `${kind}: ${parts.join(' · ')}`;
  }
  return String(kind);
}

function _kanbanFormatDetailValue(value){
  if (value === undefined || value === null || value === '') return '';
  if (typeof value === 'object') {
    try { return JSON.stringify(value, null, 2); } catch(e) { return String(value); }
  }
  return String(value);
}

function _kanbanDetailSection(cls, title, inner, emptyKey){
  const content = inner || `<div class="kanban-detail-empty">${esc(t(emptyKey))}</div>`;
  return `<section class="kanban-detail-section ${cls}">
    <h3>${esc(title)}</h3>
    ${content}
  </section>`;
}

function _kanbanCommentHtml(comment){
  const body = comment.body || comment.text || comment.content || '';
  const by = comment.author || comment.created_by || comment.actor || '';
  const at = _kanbanFormatTimestamp(comment.created_at || comment.ts || '');
  return `<div class="kanban-detail-row">
    <div class="kanban-detail-row-main">${_kanbanRenderMarkdown(body)}</div>
    <div class="kanban-detail-row-meta">${esc([by, at].filter(Boolean).join(' · '))}</div>
  </div>`;
}

function _kanbanEventHtml(event){
  const at = _kanbanFormatTimestamp(event.created_at || event.ts || '');
  const payload = _kanbanFormatDetailValue(event.payload || event.data || '');
  return `<div class="kanban-detail-row">
    <div class="kanban-detail-row-main">${esc(_kanbanEventSummary(event))}</div>
    ${payload ? `<pre class="kanban-detail-pre">${esc(payload)}</pre>` : ''}
    <div class="kanban-detail-row-meta">${esc(at)}</div>
  </div>`;
}

function _kanbanRunHtml(run){
  const status = run.status || run.state || run.result || '';
  const label = run.run_id || run.id || run.worker || t('kanban_task');
  const started = _kanbanFormatTimestamp(run.started_at || run.created_at || '');
  const finished = _kanbanFormatTimestamp(run.finished_at || run.completed_at || '');
  const detail = run.error || run.summary || run.log_tail || '';
  return `<div class="kanban-detail-row">
    <div class="kanban-detail-row-main">${esc(label)}${status ? ` · ${esc(status)}` : ''}</div>
    ${detail ? `<pre class="kanban-detail-pre">${esc(_kanbanFormatDetailValue(detail))}</pre>` : ''}
    <div class="kanban-detail-row-meta">${esc([started, finished].filter(Boolean).join(' → '))}</div>
  </div>`;
}

function _kanbanJsArg(s){
  // Encode a value for safe interpolation inside an inline on* handler's JS
  // string literal. JSON.stringify quotes/escapes for JS context; esc() then
  // makes it safe inside the HTML attribute. Without this, a task id containing
  // a quote breaks out of the handler (esc() alone is HTML-escaping, which the
  // browser decodes BEFORE executing the inline handler). (#3797)
  return esc(JSON.stringify(String(s == null ? '' : s)));
}
function _kanbanLinkableTaskOptions(excludeId){
  // Datalist of existing task ids (with title as the option label) so the
  // dependency field is a pick-from-real-tasks autocomplete rather than a blind
  // free-text opaque-id box. Mirrors the tenant datalist pattern.
  const cols = (_kanbanBoard && _kanbanBoard.columns) || [];
  const seen = new Set();
  const opts = [];
  for (const col of cols) {
    for (const task of (col.tasks || [])) {
      const id = task && task.id;
      if (!id || id === excludeId || seen.has(id)) continue;
      seen.add(id);
      opts.push(`<option value="${esc(id)}">${esc(_kanbanTaskTitle(task))}</option>`);
    }
  }
  return opts.join('');
}
function _kanbanLinksHtml(links){
  const parents = (links && links.parents) || [];
  const children = (links && links.children) || [];
  const taskId = _kanbanCurrentTaskId;
  const item = (id, isParent) => {
    const parentId = isParent ? id : taskId;
    const childId = isParent ? taskId : id;
    return `<code>${esc(id)} <button class="btn mini" onclick="removeKanbanDependency(${_kanbanJsArg(parentId)},${_kanbanJsArg(childId)})" data-i18n="kanban_remove_dependency" title="${esc(t('kanban_remove_dependency') || 'Remove')}">✕</button></code>`;
  };
  const hasLinks = parents.length || children.length;
  return `<div class="kanban-detail-links-section">
    ${hasLinks ? `<div class="kanban-detail-links-grid">
      <div><strong>${esc(t('kanban_parents'))}</strong><div>${parents.length ? parents.map(id => item(id, true)).join(' ') : esc(t('kanban_empty'))}</div></div>
      <div><strong>${esc(t('kanban_children'))}</strong><div>${children.length ? children.map(id => item(id, false)).join(' ') : esc(t('kanban_empty'))}</div></div>
    </div>` : ''}
    <div class="kanban-detail-links-controls">
      <input type="text" id="kanbanDependencyInput" class="kanban-detail-links-input" list="kanbanDependencyOptions" maxlength="255" autocomplete="off" data-i18n-placeholder="kanban_dependency_placeholder" placeholder="Task ID to link">
      <datalist id="kanbanDependencyOptions">${_kanbanLinkableTaskOptions(taskId)}</datalist>
      <button class="btn secondary" onclick="addKanbanDependency(${_kanbanJsArg(taskId)})" data-i18n="kanban_add_dependency">Add dependency</button>
    </div>
  </div>`;
}

async function createKanbanTask(){
  const input = document.getElementById('kanbanNewTaskTitle');
  const title = input ? input.value.trim() : '';
  if (!title) {
    // Empty inline input (or a click on the panel-head "+" via openKanbanCreate)
    // — open the full create-task modal so the user has somewhere obvious to
    // type and configure the task. Mirrors the cron / skills pattern of routing
    // header "+" clicks through to a clearly-modal create surface.
    openKanbanCreate();
    return;
  }
  try {
    const created = await api('/api/kanban/tasks' + _kanbanBoardQuery(), {
      method: 'POST',
      body: JSON.stringify({title}),
    });
    if (input) input.value = '';
    await loadKanban(true);
    if (created && created.task && created.task.id) await loadKanbanTask(created.task.id);
  } catch(e) { showToast(t('kanban_unavailable') + ': ' + (e.message || e), 'error'); }
}

// ────────────────────────────────────────────────────────────────────────────
// Kanban: create-task modal (panel-head "+" button entry point).
//
// Same `.kanban-modal-overlay` shell as openKanbanCreateBoard() so the two
// flows look and behave identically (centered card, dim backdrop, ESC closes,
// click-on-backdrop closes). The modal markup lives in static/index.html as
// #kanbanTaskModal — see the section just above </body>. Submit hits the
// existing /api/kanban/tasks POST endpoint (which already accepts title, body,
// assignee, tenant, priority, status — see api/kanban_bridge.py:306).
// ────────────────────────────────────────────────────────────────────────────

// ────────────────────────────────────────────────────────────────────────────
// Kanban: create-task / edit-task modal (panel-head "+" + task-detail Edit
// button entry points).
//
// Single modal serves both flows.  Title + submit-button labels and the
// underlying submit verb (POST vs PATCH) flip based on `_kanbanTaskModalMode`.
//
// Same `.kanban-modal-overlay` shell as openKanbanCreateBoard() so the two
// flows look and behave identically (centered card, dim backdrop, ESC closes,
// click-on-backdrop closes). The modal markup lives in static/index.html as
// #kanbanTaskModal — see the section just above </body>.
//
// The assignee field auto-completes against the union of (a) live Hermes
// profile names from /api/profiles and (b) historical assignees on the
// active board, with an inline hint that explains the dispatcher claim
// contract — most users will pick a profile name from the dropdown rather
// than type one.
// ────────────────────────────────────────────────────────────────────────────

let _kanbanTaskModalMode = 'create';   // 'create' | 'edit'
let _kanbanTaskModalEditingId = null;  // task id when mode === 'edit'
let _kanbanProfileNamesCache = null;   // populated lazily on first modal open
let _kanbanProfileNamesCacheAt = 0;
const _KANBAN_PROFILE_NAMES_CACHE_TTL_MS = 30000;
function _invalidateKanbanProfileCache() {
  _kanbanProfileNamesCache = null;
  _kanbanProfileNamesCacheAt = 0;
}
let _kanbanTaskModalFocusCleanup = null;
// Status the modal *displayed* on edit-mode open.  If the user doesn't touch
// the dropdown, we must NOT send `status` in the PATCH payload — otherwise
// editing a task whose real status is non-editable in this dropdown
// (running/blocked/done/archived → mapped to 'triage' for display) would
// silently demote the task on save.  See the regression caught during PR
// review: editing a 'running' task without touching status was reclaiming
// the worker and moving the task back to triage.
let _kanbanTaskModalInitialDisplayedStatus = null;
let _kanbanBoardModalFocusCleanup = null;

async function _kanbanLoadProfileNames(){
  // Hit /api/profiles once per session and cache for a short TTL.
  // Returns an array of profile names (sorted, default first if present).
  const hasFreshCache = (
    Array.isArray(_kanbanProfileNamesCache) &&
    (Date.now() - _kanbanProfileNamesCacheAt) < _KANBAN_PROFILE_NAMES_CACHE_TTL_MS
  );
  if (hasFreshCache) return _kanbanProfileNamesCache;
  try {
    const data = await api('/api/profiles');
    const profiles = Array.isArray(data && data.profiles) ? data.profiles : [];
    const names = profiles.map(p => p && p.name).filter(Boolean);
    // Stable order: default first, then alphabetical.
    names.sort((a, b) => {
      if (a === 'default') return -1;
      if (b === 'default') return 1;
      return a.localeCompare(b);
    });
    _kanbanProfileNamesCache = names;
    _kanbanProfileNamesCacheAt = Date.now();
    return names;
  } catch(_) {
    _kanbanProfileNamesCache = [];
    _kanbanProfileNamesCacheAt = Date.now();
    return [];
  }
}

async function _kanbanPopulateAssigneeSelect(currentValue, selEl){
  // Optional selEl lets callers with more than one assignee <select> on
  // screen at once (e.g. one per Crew task-spec row) reuse this exact
  // profile-name-loading/option-building logic instead of a parallel copy.
  // Defaults to the single-task modal's select for existing call sites.
  const sel = selEl || document.getElementById('kanbanTaskModalAssignee');
  if (!sel) return;
  // Profile names: the canonical set the dispatcher can claim.
  const profileNames = await _kanbanLoadProfileNames();
  // Historical assignees from the active board: include them so users who
  // assigned to a CLI lane (e.g. orion-cc) before still see those values.
  const historicalAssignees = (_kanbanBoard && Array.isArray(_kanbanBoard.assignees))
    ? _kanbanBoard.assignees
    : [];
  // Build a final ordered list, deduping.  Profiles come first, then any
  // historical assignees that aren't profiles (rare but keeps round-tripping
  // correct for tasks created via CLI).
  const seen = new Set();
  const profiles = [];
  for (const name of profileNames) {
    if (!seen.has(name)) { profiles.push(name); seen.add(name); }
  }
  const extras = [];
  for (const name of historicalAssignees) {
    if (name && !seen.has(name)) { extras.push(name); seen.add(name); }
  }
  // If the current value isn't in either bucket (e.g. an old CLI-created
  // assignee that's since been deleted), preserve it as a final option so
  // editing the task doesn't silently change its assignee.
  if (currentValue && !seen.has(currentValue)) {
    extras.push(currentValue);
    seen.add(currentValue);
  }
  // The empty value maps to null on submit (intentionally unassigned).  Keep
  // it last so the default-selected option is the first profile, not "no one".
  let html = '';
  if (profiles.length) {
    html += `<optgroup label="${esc(t('kanban_assignee_profiles_label') || 'Hermes profiles')}">`;
    html += profiles.map(v => `<option value="${esc(v)}"${v === currentValue ? ' selected' : ''}>${esc(v)}</option>`).join('');
    html += '</optgroup>';
  }
  if (extras.length) {
    html += `<optgroup label="${esc(t('kanban_assignee_other_label') || 'Other (CLI lanes / removed profiles)')}">`;
    html += extras.map(v => `<option value="${esc(v)}"${v === currentValue ? ' selected' : ''}>${esc(v)}</option>`).join('');
    html += '</optgroup>';
  }
  // Final "no assignee" fallthrough — explicit so users know what they're choosing.
  html += `<option value=""${(!currentValue) ? ' selected' : ''}>${esc(t('kanban_assignee_unassigned') || '— Unassigned (won\u2019t auto-run) —')}</option>`;
  sel.innerHTML = html;
}

function openKanbanCreate(){
  // Make sure the user is on the kanban panel so the resulting board reload is
  // visible behind the modal.
  if (typeof switchPanel === 'function' && _currentPanel !== 'kanban') switchPanel('kanban');
  const modal = document.getElementById('kanbanTaskModal');
  if (!modal) return;
  _kanbanTaskModalMode = 'create';
  _kanbanTaskModalEditingId = null;
  _kanbanTaskModalInitialDisplayedStatus = null;  // create mode: always send status
  // Default new tasks to "ready" so they're immediately claimable by the
  // dispatcher (assuming the user picks an assignee).  Triage is for staging
  // tasks that need human review before being marked actionable; users who
  // want it can still pick it from the status dropdown.
  _kanbanResetTaskModalFields({status: 'ready'});
  _kanbanSetTaskModalStatusHint(null);
  _kanbanSetTaskModalLabels('create');
  _kanbanPopulateAssigneeSelect('').then(() => {
    // After the dropdown is populated, default-select the first profile (not
    // the "Unassigned" fallthrough).  This is the right hint: most users want
    // to assign to *something* — they can pick "Unassigned" deliberately.
    const sel = document.getElementById('kanbanTaskModalAssignee');
    if (sel && sel.options.length > 0 && sel.value === '') {
      const firstProfile = Array.from(sel.options).find(opt => opt.value !== '');
      if (firstProfile) sel.value = firstProfile.value;
    }
  });
  _kanbanPopulateTenantDatalist();
  _kanbanPopulateWorkspacePathDatalist();
  _kanbanPopulateParentsDatalist();
  modal.hidden = false;
  if (_kanbanTaskModalFocusCleanup) {
    _kanbanTaskModalFocusCleanup();
    _kanbanTaskModalFocusCleanup = null;
  }
  _kanbanTaskModalFocusCleanup = _trapModalFocus(modal);
  setTimeout(() => {
    const titleEl = document.getElementById('kanbanTaskModalTitleInput');
    if (titleEl) titleEl.focus();
  }, 50);
  document.addEventListener('keydown', _kanbanTaskModalKey);
}

async function openKanbanEdit(taskId){
  // Triggered by the Edit button on the task detail view.  Fetches the task
  // (rather than relying on whatever's cached locally) so the modal always
  // reflects authoritative server state.
  if (!taskId) return;
  if (typeof switchPanel === 'function' && _currentPanel !== 'kanban') switchPanel('kanban');
  const modal = document.getElementById('kanbanTaskModal');
  if (!modal) return;
  let task = null;
  try {
    const data = await api('/api/kanban/tasks/' + encodeURIComponent(taskId) + _kanbanBoardQuery());
    task = data && data.task;
  } catch(e) {
    showToast((t('kanban_unavailable') || 'Kanban unavailable') + ': ' + (e.message || e), 'error');
    return;
  }
  if (!task) return;
  _kanbanTaskModalMode = 'edit';
  _kanbanTaskModalEditingId = task.id;
  // Track the displayed status so submitKanbanTaskModal can detect whether
  // the user actually picked a new value vs. the dropdown's mapped default.
  // Without this, editing a 'running'/'blocked'/'done'/'archived' task whose
  // real status maps to 'triage' for display would silently demote the task
  // (the mapped 'triage' would land in the PATCH payload, and _patch_task
  // would call _set_status_direct → reclaim worker → move to triage).
  const initialDisplayedStatus = _kanbanEditableStatusFor(task.status);
  const originalStatus = task.status || initialDisplayedStatus;
  _kanbanTaskModalInitialDisplayedStatus = initialDisplayedStatus;
  _kanbanResetTaskModalFields({
    title: task.title || '',
    body: task.body || '',
    status: initialDisplayedStatus,
    tenant: task.tenant || '',
    priority: typeof task.priority === 'number' ? task.priority : 0,
  });
  // Populate the assignee select AFTER reset so the option exists when we
  // call sel.value = currentAssignee.
  await _kanbanPopulateAssigneeSelect(task.assignee || '');
  _kanbanSetTaskModalStatusHint(originalStatus, initialDisplayedStatus);
  _kanbanSetTaskModalLabels('edit');
  _kanbanPopulateTenantDatalist();
  modal.hidden = false;
  if (_kanbanTaskModalFocusCleanup) {
    _kanbanTaskModalFocusCleanup();
    _kanbanTaskModalFocusCleanup = null;
  }
  _kanbanTaskModalFocusCleanup = _trapModalFocus(modal);
  setTimeout(() => {
    const titleEl = document.getElementById('kanbanTaskModalTitleInput');
    if (titleEl) { titleEl.focus(); titleEl.select(); }
  }, 50);
  document.addEventListener('keydown', _kanbanTaskModalKey);
}

function _kanbanEditableStatusFor(status){
  // The modal's status select only offers triage/todo/ready (the user-writable
  // states).  blocked/running/done/archived are reached via the detail-view
  // status buttons or the dispatcher.  Map non-editable states to a sensible
  // default so the user can still change them via the buttons after saving.
  const editable = new Set(['triage', 'todo', 'ready']);
  return editable.has(status) ? status : 'triage';
}

function _kanbanResetTaskModalFields(values){
  const v = values || {};
  const set = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.value = (val == null ? '' : String(val));
  };
  set('kanbanTaskModalTitleInput', v.title || '');
  set('kanbanTaskModalBody', v.body || '');
  set('kanbanTaskModalStatus', v.status || 'triage');
  // Assignee handled separately by _kanbanPopulateAssigneeSelect() because
  // it's a <select> populated from /api/profiles + board history; setting
  // .value before the options exist would silently fail.
  set('kanbanTaskModalTenant', v.tenant || '');
  set('kanbanTaskModalPriority', v.priority != null ? v.priority : 0);
  set('kanbanTaskModalSkills', Array.isArray(v.skills) ? v.skills.join(', ') : (v.skills || ''));
  set('kanbanTaskModalMaxRuntimeSeconds', v.max_runtime_seconds != null ? v.max_runtime_seconds : '');
  set('kanbanTaskModalParents', '');
  const errEl = document.getElementById('kanbanTaskModalError');
  if (errEl) { errEl.textContent = ''; delete errEl.dataset.warningShown; }
  const submitBtn = document.getElementById('kanbanTaskModalSubmit');
  if (submitBtn) submitBtn.disabled = false;
}

function _kanbanSetTaskModalLabels(mode){
  const titleH = document.getElementById('kanbanTaskModalTitle');
  const submitBtn = document.getElementById('kanbanTaskModalSubmit');
  if (mode === 'edit') {
    if (titleH) titleH.textContent = t('kanban_edit_task') || 'Edit task';
    if (submitBtn) submitBtn.textContent = t('save') || 'Save';
  } else {
    if (titleH) titleH.textContent = t('kanban_new_task') || 'New task';
    if (submitBtn) submitBtn.textContent = t('create') || 'Create';
  }
  // Workspace and new backend fields are create-only; backend patch doesn't handle them.
  const createOnlyIds = [
    'kanbanTaskModalWorkspaceKind',
    'kanbanTaskModalWorkspacePath',
    'kanbanTaskModalSkills',
    'kanbanTaskModalMaxRuntimeSeconds',
    'kanbanTaskModalParents',
  ];
  const disabled = mode === 'edit';
  for (const id of createOnlyIds) {
    const el = document.getElementById(id);
    if (el) el.disabled = disabled;
  }
}

function _kanbanSetTaskModalStatusHint(realStatus, editableStatus){
  const hintEl = document.getElementById('kanbanTaskModalStatusOriginalHint');
  if (!hintEl) return;
  if (!realStatus || realStatus === editableStatus) {
    hintEl.hidden = true;
    hintEl.textContent = '';
    return;
  }
  const statusLabel = t(`kanban_status_${realStatus}`) || realStatus;
  hintEl.textContent = String(t('kanban_status_original_hint')).replace('{0}', statusLabel);
  hintEl.hidden = false;
}

function _kanbanPopulateTenantDatalist(){
  const tenants = (_kanbanBoard && Array.isArray(_kanbanBoard.tenants)) ? _kanbanBoard.tenants : [];
  const tList = document.getElementById('kanbanTaskModalTenantList');
  if (tList) tList.innerHTML = tenants.map(v => `<option value="${esc(v)}"></option>`).join('');
}

function _kanbanPopulateWorkspacePathDatalist(){
  const cols = (_kanbanBoard && _kanbanBoard.columns) || [];
  const seen = new Set();
  const opts = [];
  for (const col of cols) {
    for (const task of (col.tasks || [])) {
      const path = task && task.workspace_path;
      if (!path || seen.has(path)) continue;
      seen.add(path);
      opts.push(`<option value="${esc(path)}"></option>`);
    }
  }
  const list = document.getElementById('kanbanTaskModalWorkspacePathList');
  if (list) list.innerHTML = opts.join('');
}

function _kanbanPopulateParentsDatalist(){
  const list = document.getElementById('kanbanTaskModalParentsList');
  if (list) list.innerHTML = _kanbanLinkableTaskOptions(null);
}

function _trapModalFocus(modalEl){
  if (!modalEl) return () => {};
  const selector = 'a[href], button, textarea, input, select, summary, [tabindex]:not([tabindex="-1"])';
  const collect = () => {
    const candidates = Array.from(modalEl.querySelectorAll(selector));
    return candidates.filter((el) => {
      if (el.disabled || el.hidden) return false;
      const style = getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden') return false;
      return el.tabIndex >= 0;
    });
  };
  let focusableEls = collect();
  const onKeyDown = (ev) => {
    if (ev.key !== 'Tab') return;
    if (!focusableEls.length) {
      ev.preventDefault();
      return;
    }
    const current = document.activeElement;
    let idx = focusableEls.indexOf(current);
    if (idx === -1) {
      ev.preventDefault();
      focusableEls[0].focus();
      return;
    }
    if (ev.shiftKey) idx -= 1;
    else idx += 1;
    idx = (idx + focusableEls.length) % focusableEls.length;
    ev.preventDefault();
    focusableEls[idx].focus();
  };
  modalEl.addEventListener('keydown', onKeyDown);
  return () => {
    modalEl.removeEventListener('keydown', onKeyDown);
  };
}

function closeKanbanTaskModal(){
  const modal = document.getElementById('kanbanTaskModal');
  if (modal) modal.hidden = true;
  _kanbanTaskModalMode = 'create';
  _kanbanTaskModalEditingId = null;
  _kanbanTaskModalInitialDisplayedStatus = null;
  _kanbanSetTaskModalStatusHint(null, null);
  if (_kanbanTaskModalFocusCleanup) {
    _kanbanTaskModalFocusCleanup();
    _kanbanTaskModalFocusCleanup = null;
  }
  document.removeEventListener('keydown', _kanbanTaskModalKey);
}

function _kanbanTaskModalKey(ev){
  if (ev.key === 'Escape') {
    ev.preventDefault();
    closeKanbanTaskModal();
    return;
  }
  if (ev.key === 'Enter' && !ev.shiftKey) {
    // Enter submits except when the focus is in the description textarea
    // (where Enter should insert a newline).
    const target = ev.target;
    if (target && target.tagName === 'TEXTAREA') return;
    const modal = document.getElementById('kanbanTaskModal');
    if (modal && !modal.hidden) {
      ev.preventDefault();
      submitKanbanTaskModal();
    }
  }
}

function _kanbanOnWorkspaceKindChange(){
  const kindEl = document.getElementById('kanbanTaskModalWorkspaceKind');
  const pathRowEl = document.getElementById('kanbanTaskModalWorkspacePathRow');
  if (!kindEl || !pathRowEl) return;
  const kind = kindEl.value;
  pathRowEl.style.display = (kind === 'scratch') ? 'none' : 'block';
}

async function submitKanbanTaskModal(){
  const titleEl = document.getElementById('kanbanTaskModalTitleInput');
  const bodyEl = document.getElementById('kanbanTaskModalBody');
  const statusEl = document.getElementById('kanbanTaskModalStatus');
  const assigneeEl = document.getElementById('kanbanTaskModalAssignee');
  const tenantEl = document.getElementById('kanbanTaskModalTenant');
  const priorityEl = document.getElementById('kanbanTaskModalPriority');
  const workspaceKindEl = document.getElementById('kanbanTaskModalWorkspaceKind');
  const workspacePathEl = document.getElementById('kanbanTaskModalWorkspacePath');
  const skillsEl = document.getElementById('kanbanTaskModalSkills');
  const maxRuntimeEl = document.getElementById('kanbanTaskModalMaxRuntimeSeconds');
  const parentsEl = document.getElementById('kanbanTaskModalParents');
  const errEl = document.getElementById('kanbanTaskModalError');
  const submitBtn = document.getElementById('kanbanTaskModalSubmit');
  const title = titleEl ? titleEl.value.trim() : '';
  if (!title) {
    if (errEl) errEl.textContent = t('kanban_title_required') || 'Title is required.';
    if (titleEl) titleEl.focus();
    return;
  }
  // Build payload — for create we omit defaulted fields so the backend chooses;
  // for edit we send every field so users can clear assignee/tenant/body.
  const isEdit = _kanbanTaskModalMode === 'edit';
  // Validate workspace path for non-scratch workspace kinds (create mode only)
  const workspaceKind = workspaceKindEl ? workspaceKindEl.value : 'scratch';
  if (!isEdit && workspaceKind !== 'scratch') {
    const workspacePath = workspacePathEl ? workspacePathEl.value.trim() : '';
    if (!workspacePath) {
      if (errEl) errEl.textContent = t('kanban_workspace_path_required') || 'Workspace path is required for non-scratch workspaces.';
      if (workspacePathEl) workspacePathEl.focus();
      return;
    }
  }
  const payload = {title};
  const bodyVal = bodyEl ? bodyEl.value : '';
  const assigneeVal = assigneeEl ? assigneeEl.value.trim() : '';
  const tenantVal = tenantEl ? tenantEl.value.trim() : '';
  const statusVal = statusEl ? statusEl.value : '';
  const priorityRaw = priorityEl ? priorityEl.value : '';
  const workspacePathVal = workspacePathEl ? workspacePathEl.value.trim() : '';
  const skillsRaw = skillsEl ? skillsEl.value.trim() : '';
  const maxRuntimeRaw = maxRuntimeEl ? maxRuntimeEl.value.trim() : '';
  const parentsRaw = parentsEl ? parentsEl.value.trim() : '';
  if (isEdit) {
    payload.body = bodyVal;
    payload.assignee = assigneeVal || null;
    payload.tenant = tenantVal || null;
    // Only send status if the user actually changed the dropdown from the
    // value the modal opened with.  Otherwise editing a 'running'/'blocked'/
    // 'done'/'archived' task — whose real status maps to the dropdown's
    // 'triage' default — would silently demote the task on every save.
    if (statusVal && statusVal !== _kanbanTaskModalInitialDisplayedStatus) {
      payload.status = statusVal;
    }
    const n = parseInt(priorityRaw, 10);
    payload.priority = Number.isNaN(n) ? 0 : n;
    // Note: workspace_kind and workspace_path are not sent on edit because
    // the backend _patch_task does not handle them (they are dropped).
  } else {
    if (bodyVal.trim()) payload.body = bodyVal;
    if (statusVal) payload.status = statusVal;
    if (assigneeVal) payload.assignee = assigneeVal;
    if (tenantVal) payload.tenant = tenantVal;
    if (priorityRaw !== '' && priorityRaw !== '0') {
      const n = parseInt(priorityRaw, 10);
      if (!Number.isNaN(n)) payload.priority = n;
    }
    payload.workspace_kind = workspaceKind;
    if (workspacePathVal) payload.workspace_path = workspacePathVal;
    if (skillsRaw) {
      payload.skills = skillsRaw.split(',').map(s => s.trim()).filter(Boolean);
    }
    if (maxRuntimeRaw) {
      if (!/^[1-9]\d*$/.test(maxRuntimeRaw)) {
        if (errEl) errEl.textContent = t('kanban_max_runtime_invalid')
          || 'Max runtime must be a whole number of seconds greater than 0.';
        if (maxRuntimeEl) maxRuntimeEl.focus();
        return;
      }
      payload.max_runtime_seconds = Number(maxRuntimeRaw);
    }
    if (parentsRaw) payload.parents = [parentsRaw];
  }
  // Soft warning: a Ready task with the explicit "Unassigned" option will sit
  // forever because the dispatcher skips unassigned rows (kanban_db.py:3567).
  // The dropdown now makes this an explicit choice (the user picked "—
  // Unassigned (won't auto-run) —"), but we still surface a one-time confirm
  // so they don't lose work to a typo.
  if (statusVal === 'ready' && !assigneeVal) {
    if (errEl && !errEl.dataset.warningShown) {
      errEl.textContent = t('kanban_ready_needs_assignee')
        || 'You picked Unassigned + Ready. The dispatcher will skip this task. Submit again to confirm, or pick a profile.';
      errEl.dataset.warningShown = '1';
      const sel = document.getElementById('kanbanTaskModalAssignee');
      if (sel) sel.focus();
      return;
    }
  }
  if (submitBtn) submitBtn.disabled = true;
  if (errEl) { errEl.textContent = ''; delete errEl.dataset.warningShown; }
  try {
    let saved;
    if (isEdit && _kanbanTaskModalEditingId) {
      saved = await api(
        '/api/kanban/tasks/' + encodeURIComponent(_kanbanTaskModalEditingId) + _kanbanBoardQuery(),
        {method: 'PATCH', body: JSON.stringify(payload)},
      );
    } else {
      saved = await api('/api/kanban/tasks' + _kanbanBoardQuery(), {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    }
    closeKanbanTaskModal();
    await loadKanban(true);
    const savedId = saved && saved.task && saved.task.id;
    if (savedId) {
      await loadKanbanTask(savedId);
    } else if (isEdit && _kanbanTaskModalEditingId) {
      await loadKanbanTask(_kanbanTaskModalEditingId);
    }
  } catch(e) {
    if (errEl) errEl.textContent = (e.message || String(e));
    if (submitBtn) submitBtn.disabled = false;
  }
}

async function updateKanbanTask(taskId, patch, opts){
  if (!taskId || !patch) return;
  try {
    const openDetail = !opts || opts.openDetail !== false;
    const updated = await api('/api/kanban/tasks/' + encodeURIComponent(taskId) + _kanbanBoardQuery(), {
      method: 'PATCH',
      body: JSON.stringify(patch),
    });
    await loadKanban(true);
    if (openDetail) await loadKanbanTask((updated && updated.task && updated.task.id) || taskId);
  } catch(e) { showToast(t('kanban_unavailable') + ': ' + (e.message || e), 'error'); }
}

async function addKanbanComment(taskId){
  const input = document.getElementById('kanbanCommentInput');
  const body = input ? input.value.trim() : '';
  if (!taskId || !body) return;
  try {
    await api('/api/kanban/tasks/' + encodeURIComponent(taskId) + '/comments' + _kanbanBoardQuery(), {
      method: 'POST',
      body: JSON.stringify({body}),
    });
    if (input) input.value = '';
    await loadKanbanTask(taskId);
  } catch(e) { showToast(t('kanban_unavailable') + ': ' + (e.message || e), 'error'); }
}

async function addKanbanDependency(taskId){
  const input = document.getElementById('kanbanDependencyInput');
  const linkTo = input ? input.value.trim() : '';
  if (!taskId || !linkTo) return;
  if (linkTo === taskId) {
    showToast(t('kanban_dependency_self') || 'A task cannot depend on itself', 'error');
    return;
  }
  try {
    // "Add dependency" on task X means "X depends on linkTo" → linkTo is the
    // prerequisite (parent) that must complete before X (child). The backend
    // models a (parent_id, child_id) row as parent=prerequisite/child=dependent
    // (api/kanban_bridge.py), so linkTo is the parent and the current task is
    // the child. (#3797)
    await api('/api/kanban/links' + _kanbanBoardQuery(), {
      method: 'POST',
      body: JSON.stringify({parent_id: linkTo, child_id: taskId}),
    });
    if (input) input.value = '';
    await loadKanbanTask(taskId);
  } catch(e) { showToast(t('kanban_unavailable') + ': ' + (e.message || e), 'error'); }
}

async function removeKanbanDependency(parentId, childId){
  if (!parentId || !childId) return;
  try {
    await api('/api/kanban/links/delete' + _kanbanBoardQuery(), {
      method: 'POST',
      body: JSON.stringify({parent_id: parentId, child_id: childId}),
    });
    await loadKanbanTask(_kanbanCurrentTaskId);
  } catch(e) { showToast(t('kanban_unavailable') + ': ' + (e.message || e), 'error'); }
}

function _kanbanRenderTaskDetail(data){
  const task = data.task || {};
  const log = data.log || {};
  const title = _kanbanTaskTitle(task);
  const body = _kanbanTaskBody(task) || t('kanban_no_description');
  const meta = _kanbanTaskMeta(task);
  const comments = data.comments || [];
  const events = data.events || [];
  const links = data.links || {};
  const runs = data.runs || [];
  // Note: 'running' is intentionally absent — entering 'running' is the
  // dispatcher/claim_task path's responsibility, not a user UI write. The
  // bridge rejects PATCH status='running' with HTTP 400 to match the agent
  // dashboard plugin's contract. UI users want to claim/promote a ready task
  // via the dispatcher Nudge button, not flip it to running by hand.
  const statusButtons = ['triage', 'todo', 'ready', 'blocked', 'done', 'archived'].map(status =>
    `<button class="btn secondary" onclick="updateKanbanTask('${esc(task.id)}',{status:'${status}'})">${esc(_kanbanColumnLabel(status))}</button>`
  ).join('') + `<button class="btn secondary" onclick="blockKanbanTask('${esc(task.id)}')">${esc(t('kanban_block'))}</button><button class="btn secondary" onclick="unblockKanbanTask('${esc(task.id)}')">${esc(t('kanban_unblock'))}</button>`;
  return `<div class="kanban-task-preview-header">
      <button class="btn secondary kanban-back-btn" onclick="closeKanbanTaskDetail()">${esc(t('kanban_back_to_board'))}</button>
      <div class="kanban-task-preview-title">${esc(title)}</div>
      <button class="btn secondary kanban-edit-btn" onclick="openKanbanEdit('${esc(task.id)}')" data-i18n="kanban_edit_task" title="${esc(t('kanban_edit_task') || 'Edit task')}">${esc(t('kanban_edit_task') || 'Edit task')}</button>
    </div>
    <div class="kanban-task-preview-body">${_kanbanRenderMarkdown(body)}</div>
    ${meta.length ? `<div class="kanban-meta">${esc(meta.join(' · '))}</div>` : ''}
    <div class="kanban-status-actions">${statusButtons}</div>
    <div class="kanban-detail-grid">
      ${_kanbanDetailSection('kanban-detail-comments', String(t('kanban_comments_count')).replace('{0}', comments.length), comments.map(_kanbanCommentHtml).join(''), 'kanban_no_comments')}
      ${_kanbanDetailSection('kanban-detail-events', String(t('kanban_events_count')).replace('{0}', events.length), events.map(_kanbanEventHtml).join(''), 'kanban_no_events')}
      ${_kanbanDetailSection('kanban-detail-links', t('kanban_links'), _kanbanLinksHtml(links), 'kanban_empty')}
      ${_kanbanDetailSection('kanban-detail-runs', String(t('kanban_runs_count')).replace('{0}', runs.length), runs.map(_kanbanRunHtml).join(''), 'kanban_no_runs')}
      ${_kanbanDetailSection('kanban-detail-log', t('kanban_worker_log'), log.content ? `<pre class="kanban-detail-pre">${esc(log.content)}</pre>` : '', 'kanban_empty')}
    </div>
    <div class="kanban-comment-form">
      <textarea id="kanbanCommentInput" rows="2" placeholder="${esc(t('kanban_add_comment'))}"></textarea>
      <button class="btn primary" onclick="addKanbanComment('${esc(task.id)}')">${esc(t('kanban_add_comment'))}</button>
    </div>`;
}

async function loadKanbanTask(taskId){
  if (!taskId) return;
  try {
    const data = await api('/api/kanban/tasks/' + encodeURIComponent(taskId) + _kanbanBoardQuery());
    try { data.log = await api('/api/kanban/tasks/' + encodeURIComponent(taskId) + '/log' + _kanbanBoardQuery({tail: 65536})); } catch(e) { data.log = {}; }
    _kanbanCurrentTaskId = taskId;
    const task = data.task || {};
    const title = _kanbanTaskTitle(task);
    const board = $('kanbanBoard');
    if (board) {
      board.querySelectorAll('.kanban-card').forEach(card => card.classList.remove('selected'));
      Array.from(board.querySelectorAll('.kanban-card')).find(card => card.dataset.kanbanTaskId === taskId)?.classList.add('selected');
    }
    const preview = $('kanbanTaskPreview');
    if (preview) {
      preview.style.display = '';
      preview.innerHTML = _kanbanRenderTaskDetail(data);
    }
    _closeMobileSidebarAfterPanelSelection();
    showToast(`${t('kanban_task')}: ${title}`);
  } catch(e) { showToast(t('kanban_unavailable') + ': ' + (e.message || e), 'error'); }
}

// Phase 2: Single-source-of-truth render.
//
// Reads `S.todos` (set by the `todo_state` SSE listener, INFLIGHT
// restore, or session cold-load — see _hydrateTodosFromSession in
// ui.js).  When `S.todoStateMeta` is null we have never seen an
// explicit signal and fall through to the legacy reverse-scan over
// settled tool messages — this keeps the panel populated against
// pre-Phase-1 servers and during the upgrade window.
//
// The render is short-circuited via `_todosLastRenderedHash` (defined
// in ui.js): repeated emissions that yield identical DOM are no-ops.
// Coalescing of bursty live updates happens upstream in
// scheduleTodosRefresh().
function loadTodos() {
  const panel = $('todoPanel');
  if (!panel) return;

  let todos;
  if (S.todoStateMeta) {
    todos = Array.isArray(S.todos) ? S.todos : [];
  } else {
    todos = _legacyTodosFromMessages();
  }

  if (!todos.length) {
    if (typeof _todosLastRenderedHash !== 'undefined' && _todosLastRenderedHash === '__empty__') return;
    panel.innerHTML = renderTodoEmptyState();
    if (typeof _todosLastRenderedHash !== 'undefined') _todosLastRenderedHash = '__empty__';
    return;
  }

  if (typeof _todosHash === 'function' && typeof _todosLastRenderedHash !== 'undefined') {
    const hash = _todosHash(todos);
    if (hash === _todosLastRenderedHash) return;
    _todosLastRenderedHash = hash;
  }

  // Single innerHTML join is the cheapest correct way to materialize
  // ~10–50 leaf nodes.  All user-controlled content goes through esc().
  panel.innerHTML = renderTodoRows(todos, {metadata:true});
}

// Legacy fallback: reverse-scan settled tool messages for the most
// recent {"todos":[...]} payload.  Used only when no `todo_state`
// signal has been seen for the current session — primarily during
// upgrade windows where the server has not yet been redeployed with
// Phase 1.  Once Phase 1 is universally deployed and a stabilization
// period has passed, this can be removed (Phase 3).
//
// Variable name `sourceMessages` is preserved verbatim from the
// original loadTodos() implementation so the matching regression
// test (R-todo-survive-refresh in tests/test_regressions.py) keeps
// catching any future refactor that drops the raw-session-messages
// fallback. See the test for the exact contract.
function _legacyTodosFromMessages() {
  const sourceMessages = (S.session && Array.isArray(S.session.messages) && S.session.messages.length) ? S.session.messages : S.messages;
  if (!Array.isArray(sourceMessages)) return [];
  for (let i = sourceMessages.length - 1; i >= 0; i--) {
    const m = sourceMessages[i];
    if (!m || m.role !== 'tool') continue;
    let content = m.content;
    if (typeof content !== 'string') {
      try { content = JSON.stringify(content); } catch (_) { continue; }
    }
    if (!content || content.indexOf('"todos"') < 0) continue;
    try {
      const d = JSON.parse(content);
      if (d && Array.isArray(d.todos)) return d.todos;
    } catch (_) {}
  }
  return [];
}

// ────────────────────────────────────────────────────────────────────────────
// Kanban: multi-board switcher + create/rename/archive modal
// ────────────────────────────────────────────────────────────────────────────
//
// The bridge exposes /api/kanban/boards (GET/POST), /boards/<slug>
// (PATCH/DELETE), and /boards/<slug>/switch (POST). The UI surfaces these
// as a "Default ▾" dropdown next to the Board title — clicking it opens
// a menu listing every board (current first, with task counts), plus
// actions to create / rename / archive.

const KANBAN_BOARD_LS_KEY = 'hermes-kanban-active-board';

function _kanbanGetSavedBoard(){
  try { return localStorage.getItem(KANBAN_BOARD_LS_KEY) || null; } catch(_) { return null; }
}

function _kanbanSetSavedBoard(slug){
  try {
    if (slug && slug !== 'default') localStorage.setItem(KANBAN_BOARD_LS_KEY, slug);
    else localStorage.removeItem(KANBAN_BOARD_LS_KEY);
  } catch(_) {}
}

async function loadKanbanBoards(){
  // Fetches the boards list and updates the switcher UI. Best-effort —
  // failures hide the switcher rather than blocking the panel from rendering.
  const switcher = document.getElementById('kanbanBoardSwitcher');
  if (!switcher) return;
  let data;
  try {
    data = await api('/api/kanban/boards');
  } catch(e) {
    // Hide switcher on error so the user isn't stuck with a half-broken UI.
    switcher.hidden = true;
    return;
  }
  const boards = (data && data.boards) || [];
  const serverCurrent = (data && data.current) || 'default';
  _kanbanBoardsList = boards;
  // Resolution chain for the active board:
  //   localStorage hint → server's `current` → 'default'.
  // The localStorage hint is honoured ONLY if it points at a board that
  // still exists; otherwise we fall back to the server's pointer.
  const saved = _kanbanGetSavedBoard();
  let active = serverCurrent;
  if (saved && boards.some(b => b.slug === saved)) {
    active = saved;
  } else if (saved) {
    _kanbanSetSavedBoard('default');
  }
  _kanbanCurrentBoard = (active === 'default') ? null : active;
  // The switcher is visible whenever ≥1 non-default board exists OR the
  // current board is non-default. (If you only have 'default', a switcher
  // adds clutter without value.)
  const hasMultiple = boards.length > 1 || (active !== 'default');
  switcher.hidden = !hasMultiple;
  if (!hasMultiple) return;
  // Update the toggle label/icon
  const activeMeta = boards.find(b => b.slug === active) || {slug: active, name: active, icon: '', color: ''};
  const nameEl = document.getElementById('kanbanBoardSwitcherName');
  const iconEl = document.getElementById('kanbanBoardSwitcherIcon');
  if (nameEl) nameEl.textContent = activeMeta.name || activeMeta.slug || 'Default';
  if (iconEl) {
    iconEl.textContent = activeMeta.icon || '';
    if (activeMeta.color) iconEl.style.color = activeMeta.color;
    else iconEl.style.color = '';
  }
  // Re-render the menu (in case it was open or changed)
  _renderKanbanBoardMenu(boards, active);
}

// Restrict board.color to CSS hex codes or simple named colors before
// interpolating into a `style=""` attribute. esc() HTML-escapes but
// does not block CSS-context injection (`color:red;background:url(...)`
// would otherwise exfiltrate page state via an attacker-controlled URL,
// since neither this bridge nor the agent's kanban_db validates color).
function _kanbanSafeColor(c){
  if (typeof c !== 'string') return '';
  const s = c.trim();
  if (!s) return '';
  if (/^#[0-9a-fA-F]{3,8}$/.test(s)) return s;
  if (/^[a-zA-Z]{3,32}$/.test(s)) return s;
  return '';
}

function _renderKanbanBoardMenu(boards, current){
  const menu = document.getElementById('kanbanBoardSwitcherMenu');
  if (!menu) return;
  const items = boards.map(b => {
    const isCurrent = b.slug === current;
    const total = (b.total != null) ? b.total : (b.counts ? Object.values(b.counts).reduce((a,c)=>a+Number(c||0),0) : 0);
    const icon = b.icon ? esc(b.icon) : '';
    const safeColor = _kanbanSafeColor(b.color);
    const colorStyle = safeColor ? `color:${safeColor}` : '';
    return `<button type="button" class="kanban-board-switcher-item ${isCurrent ? 'is-current' : ''}" role="menuitem" data-board-slug="${esc(b.slug)}" onclick="switchKanbanBoard('${esc(b.slug)}')">
      <span class="kanban-board-switcher-item-icon" style="${colorStyle}">${icon || (isCurrent ? '✓' : '')}</span>
      <span class="kanban-board-switcher-item-name">${esc(b.name || b.slug)}</span>
      <span class="kanban-board-switcher-item-count">${esc(String(total))}</span>
    </button>`;
  }).join('');
  // Actions row — disable rename/archive when the only option is `default`
  // (the default board's display metadata is editable but the slug isn't,
  // and `default` cannot be archived).
  const renameDisabled = current === 'default';
  const archiveDisabled = current === 'default';
  const actions = `
    <div class="kanban-board-switcher-divider" role="separator"></div>
    <button type="button" class="kanban-board-switcher-action" onclick="openKanbanCreateBoard()" data-i18n="kanban_new_board">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
      <span>${esc(t('kanban_new_board') || 'New board…')}</span>
    </button>
    <button type="button" class="kanban-board-switcher-action" onclick="openKanbanRenameBoard()" ${renameDisabled ? 'disabled' : ''} data-i18n="kanban_rename_board">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
      <span>${esc(t('kanban_rename_board') || 'Rename current board…')}</span>
    </button>
    <button type="button" class="kanban-board-switcher-action danger" onclick="archiveKanbanBoard()" ${archiveDisabled ? 'disabled' : ''} data-i18n="kanban_archive_board">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>
      <span>${esc(t('kanban_archive_board') || 'Archive current board…')}</span>
    </button>
  `;
  menu.innerHTML = items + actions;
}

function toggleKanbanBoardMenu(ev){
  if (ev) ev.stopPropagation();
  const menu = document.getElementById('kanbanBoardSwitcherMenu');
  const toggle = document.getElementById('kanbanBoardSwitcherToggle');
  if (!menu || !toggle) return;
  _kanbanBoardMenuOpen = !_kanbanBoardMenuOpen;
  menu.hidden = !_kanbanBoardMenuOpen;
  toggle.setAttribute('aria-expanded', String(_kanbanBoardMenuOpen));
  if (_kanbanBoardMenuOpen) {
    // Click-away close
    setTimeout(() => {
      document.addEventListener('click', _kanbanCloseBoardMenuOnOutside, {once: true, capture: true});
    }, 0);
  }
}

function _kanbanCloseBoardMenuOnOutside(ev){
  const switcher = document.getElementById('kanbanBoardSwitcher');
  if (!switcher || !switcher.contains(ev.target)) {
    _kanbanBoardMenuOpen = false;
    const menu = document.getElementById('kanbanBoardSwitcherMenu');
    const toggle = document.getElementById('kanbanBoardSwitcherToggle');
    if (menu) menu.hidden = true;
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
  } else {
    // Re-arm the listener — the user clicked inside the switcher, possibly
    // the toggle button which we want to handle through its own onclick.
    setTimeout(() => {
      document.addEventListener('click', _kanbanCloseBoardMenuOnOutside, {once: true, capture: true});
    }, 0);
  }
}

async function switchKanbanBoard(slug){
  if (!slug) return;
  const newBoard = (slug === 'default') ? null : slug;
  if (newBoard === _kanbanCurrentBoard) {
    // No-op switch — just close the menu.
    _kanbanBoardMenuOpen = false;
    const menu = document.getElementById('kanbanBoardSwitcherMenu');
    if (menu) menu.hidden = true;
    return;
  }
  _kanbanCurrentBoard = newBoard;
  _kanbanSetSavedBoard(slug);
  _kanbanLatestEventId = 0;  // reset cursor — new board has its own event sequence
  _kanbanBoardMenuOpen = false;
  const menu = document.getElementById('kanbanBoardSwitcherMenu');
  if (menu) menu.hidden = true;
  // Tell the server too (sets the on-disk active-board pointer for CLI/dashboard).
  try {
    await api('/api/kanban/boards/' + encodeURIComponent(slug) + '/switch', {method: 'POST'});
  } catch(e) {
    // Local UI switch still happens — the on-disk pointer is for cross-process
    // consistency, not for our own rendering.
  }
  // Re-open the SSE stream on the new board.
  _kanbanStopPolling();
  await loadKanban(true);
  await loadKanbanBoards();
  _kanbanStartPolling();
}

// ── Create / rename / archive board modals ──────────────────────────────────

function openKanbanCreateBoard(){
  const modal = document.getElementById('kanbanBoardModal');
  if (!modal) return;
  document.getElementById('kanbanBoardModalMode').value = 'create';
  document.getElementById('kanbanBoardModalSlug').value = '';
  document.getElementById('kanbanBoardModalTitle').textContent = t('kanban_new_board') || 'New board';
  document.getElementById('kanbanBoardModalName').value = '';
  document.getElementById('kanbanBoardModalSlugInput').value = '';
  document.getElementById('kanbanBoardModalSlugInput').disabled = false;
  document.getElementById('kanbanBoardModalSlugRow').style.display = '';
  document.getElementById('kanbanBoardModalDesc').value = '';
  document.getElementById('kanbanBoardModalIcon').value = '';
  document.getElementById('kanbanBoardModalColor').value = '#7aa2ff';
  document.getElementById('kanbanBoardModalError').textContent = '';
  modal.hidden = false;
  if (_kanbanBoardModalFocusCleanup) {
    _kanbanBoardModalFocusCleanup();
    _kanbanBoardModalFocusCleanup = null;
  }
  _kanbanBoardModalFocusCleanup = _trapModalFocus(modal);
  // Auto-focus name field
  setTimeout(() => document.getElementById('kanbanBoardModalName').focus(), 50);
  // Auto-suggest slug from name as user types
  const nameEl = document.getElementById('kanbanBoardModalName');
  const slugEl = document.getElementById('kanbanBoardModalSlugInput');
  let userEditedSlug = false;
  slugEl.addEventListener('input', () => { userEditedSlug = true; }, {once: false});
  const onName = () => {
    if (!userEditedSlug) {
      slugEl.value = String(nameEl.value || '').toLowerCase().replace(/[^a-z0-9-_ ]+/g, '').replace(/\s+/g, '-').slice(0, 48);
    }
  };
  nameEl.removeEventListener('input', nameEl._kanbanOnNameInput || (() => {}));
  nameEl._kanbanOnNameInput = onName;
  nameEl.addEventListener('input', onName);
  // Close on Escape
  document.addEventListener('keydown', _kanbanBoardModalEsc);
}

function openKanbanRenameBoard(){
  const modal = document.getElementById('kanbanBoardModal');
  if (!modal) return;
  const current = _kanbanCurrentBoard || 'default';
  if (current === 'default') return;  // default's slug is immutable
  const meta = (_kanbanBoardsList || []).find(b => b.slug === current);
  if (!meta) return;
  document.getElementById('kanbanBoardModalMode').value = 'rename';
  document.getElementById('kanbanBoardModalSlug').value = current;
  document.getElementById('kanbanBoardModalTitle').textContent = t('kanban_rename_board') || 'Rename board';
  document.getElementById('kanbanBoardModalName').value = meta.name || '';
  document.getElementById('kanbanBoardModalSlugInput').value = current;
  document.getElementById('kanbanBoardModalSlugInput').disabled = true;  // slug is immutable
  // Hide the slug row — it's locked, less visual noise.
  document.getElementById('kanbanBoardModalSlugRow').style.display = 'none';
  document.getElementById('kanbanBoardModalDesc').value = meta.description || '';
  document.getElementById('kanbanBoardModalIcon').value = meta.icon || '';
  document.getElementById('kanbanBoardModalColor').value = meta.color || '#7aa2ff';
  document.getElementById('kanbanBoardModalError').textContent = '';
  modal.hidden = false;
  if (_kanbanBoardModalFocusCleanup) {
    _kanbanBoardModalFocusCleanup();
    _kanbanBoardModalFocusCleanup = null;
  }
  _kanbanBoardModalFocusCleanup = _trapModalFocus(modal);
  setTimeout(() => document.getElementById('kanbanBoardModalName').focus(), 50);
  document.addEventListener('keydown', _kanbanBoardModalEsc);
}

function _kanbanBoardModalEsc(ev){
  if (ev.key === 'Escape') closeKanbanBoardModal();
}

function closeKanbanBoardModal(){
  const modal = document.getElementById('kanbanBoardModal');
  if (modal) modal.hidden = true;
  if (_kanbanBoardModalFocusCleanup) {
    _kanbanBoardModalFocusCleanup();
    _kanbanBoardModalFocusCleanup = null;
  }
  document.removeEventListener('keydown', _kanbanBoardModalEsc);
}

async function submitKanbanBoardModal(){
  const errEl = document.getElementById('kanbanBoardModalError');
  errEl.textContent = '';
  const mode = document.getElementById('kanbanBoardModalMode').value;
  const name = (document.getElementById('kanbanBoardModalName').value || '').trim();
  const slugInput = (document.getElementById('kanbanBoardModalSlugInput').value || '').trim();
  const description = (document.getElementById('kanbanBoardModalDesc').value || '').trim();
  const icon = (document.getElementById('kanbanBoardModalIcon').value || '').trim();
  const color = (document.getElementById('kanbanBoardModalColor').value || '').trim();
  const submitBtn = document.getElementById('kanbanBoardModalSubmit');
  if (!name) {
    errEl.textContent = t('kanban_board_name_required') || 'Name is required';
    return;
  }
  if (mode === 'create') {
    if (!slugInput) {
      errEl.textContent = t('kanban_board_slug_required') || 'Slug is required';
      return;
    }
    if (submitBtn) submitBtn.disabled = true;
    try {
      const res = await api('/api/kanban/boards', {
        method: 'POST',
        body: JSON.stringify({slug: slugInput, name, description, icon, color, switch: true}),
      });
      closeKanbanBoardModal();
      // Switch to the new board and reload
      const newSlug = (res && res.board && res.board.slug) || slugInput;
      _kanbanCurrentBoard = (newSlug === 'default') ? null : newSlug;
      _kanbanSetSavedBoard(newSlug);
      _kanbanLatestEventId = 0;
      _kanbanStopPolling();
      await loadKanban(true);
      await loadKanbanBoards();
      _kanbanStartPolling();
    } catch(e) {
      errEl.textContent = (e && (e.message || e.error)) || String(e);
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  } else if (mode === 'rename') {
    const slug = document.getElementById('kanbanBoardModalSlug').value;
    if (!slug) { errEl.textContent = 'Missing slug'; return; }
    if (submitBtn) submitBtn.disabled = true;
    try {
      await api('/api/kanban/boards/' + encodeURIComponent(slug), {
        method: 'PATCH',
        body: JSON.stringify({name, description, icon, color}),
      });
      closeKanbanBoardModal();
      await loadKanbanBoards();  // refresh switcher label/icon
    } catch(e) {
      errEl.textContent = (e && (e.message || e.error)) || String(e);
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  }
}

async function archiveKanbanBoard(){
  const current = _kanbanCurrentBoard || 'default';
  if (current === 'default') return;
  const meta = (_kanbanBoardsList || []).find(b => b.slug === current);
  const label = meta && meta.name ? meta.name : current;
  const ok = await showConfirmDialog({
    title: t('kanban_archive_board') || 'Archive board',
    message: (t('kanban_archive_board_confirm') || 'Archive board "{name}"? Tasks remain on disk and the board can be restored from kanban/boards/_archived/.').replace('{name}', label),
    confirmLabel: t('kanban_archive_board') || 'Archive',
    danger: true,
    focusCancel: true,
  });
  if (!ok) return;
  // CRITICAL: stop the SSE stream BEFORE the archive call. The library's
  // kb.connect(board=<slug>) auto-creates the on-disk directory + DB on
  // first call — so any in-flight stream that polls task_events while
  // we're archiving will silently re-materialise the directory we just
  // moved to _archived/. Tearing down the stream first avoids that race.
  _kanbanStopPolling();
  try {
    await api('/api/kanban/boards/' + encodeURIComponent(current), {method: 'DELETE'});
    // Server falls back to default — match that locally.
    _kanbanCurrentBoard = null;
    _kanbanSetSavedBoard('default');
    _kanbanLatestEventId = 0;
    await loadKanban(true);
    await loadKanbanBoards();
    _kanbanStartPolling();
    showToast(t('kanban_board_archived') || 'Board archived');
  } catch(e) {
    // Restart the stream on failure so the UI doesn't go stale.
    _kanbanStartPolling();
    showToast(t('kanban_unavailable') + ': ' + (e.message || e), 'error');
  }
}


// ── Logs panel ──
function _selectedLogsFile() {
  const el = $('logsFile');
  const value = (el && el.value) || 'agent';
  return ['agent','errors','gateway'].includes(value) ? value : 'agent';
}

function _selectedLogsTail() {
  const el = $('logsTail');
  const value = Number((el && el.value) || 200);
  return [100,200,500,1000].includes(value) ? value : 200;
}

function _severityForLine(line) {
  const text = String(line || '').toUpperCase();
  if (/\b(ERROR|CRITICAL|TRACEBACK)\b/.test(text)) return 'error';
  if (/\b(WARNING|WARN)\b/.test(text)) return 'warning';
  if (/\b(DEBUG)\b/.test(text)) return 'debug';
  if (/\b(INFO)\b/.test(text)) return 'info';
  return 'other';
}

function _filteredLogsLines() {
  if (_logsSeverityFilter === 'all') return _lastLogsLines;
  return _lastLogsLines.filter(line => {
    const sev = _severityForLine(line);
    if (_logsSeverityFilter === 'errors') return sev === 'error';
    if (_logsSeverityFilter === 'warnings') return sev === 'warning' || sev === 'error';
    return true;
  });
}

function _applyLogsSeverityFilter() {
  const el = $('logsSeverityFilter');
  _logsSeverityFilter = (el && el.value) || 'all';
  // Re-render from cached lines without re-fetching
  _renderLogs({ lines: _lastLogsLines, hint: '', truncated: false, _fromFilter: true });
}

function _logLineSeverityClass(line) {
  const text = String(line || '').toUpperCase();
  if (/\b(WARNING|WARN)\b/.test(text)) return 'log-line-warning';
  if (/\b(DEBUG)\b/.test(text)) return 'log-line-debug';
  if (/\b(INFO)\b/.test(text)) return 'log-line-info';
  if (/\b(ERROR|CRITICAL|TRACEBACK)\b/.test(text)) return 'log-line-error';
  return '';
}

function _syncLogsWrap() {
  const out = $('logsOutput');
  const wrap = $('logsWrap');
  if (out && wrap) out.classList.toggle('wrap', !!wrap.checked);
}

async function loadLogs(animate) {
  const box = $('logsOutput');
  const status = $('logsStatus');
  const refreshBtn = $('logsRefreshBtn');
  if (!box) return;
  if (animate && refreshBtn) {
    refreshBtn.style.opacity = '0.5';
    refreshBtn.disabled = true;
  }
  const file = _selectedLogsFile();
  const tail = _selectedLogsTail();
  try {
    if (status) status.textContent = t('logs_loading');
    const data = await api('/api/logs?file=' + encodeURIComponent(file) + '&tail=' + encodeURIComponent(tail));
    _renderLogs(data);
  } catch(e) {
    _lastLogsLines = [];
    box.innerHTML = `<div class="logs-empty">${esc(t('error_prefix') + e.message)}</div>`;
    if (status) status.textContent = t('logs_load_failed');
  } finally {
    if (animate && refreshBtn) {
      refreshBtn.style.opacity = '';
      refreshBtn.disabled = false;
    }
    _syncLogsAutoRefresh();
  }
}

function _renderLogs(data) {
  const box = $('logsOutput');
  const status = $('logsStatus');
  if (!box) return;
  const rawLines = Array.isArray(data && data.lines) ? data.lines : [];
  // Only update cache when loading fresh data (not when re-rendering from filter)
  if (data && !data._fromFilter) _lastLogsLines = rawLines.slice();
  const displayLines = _filteredLogsLines();
  const hint = data && data.hint ? `<div class="logs-hint">${esc(data.hint)}</div>` : '';
  const truncated = data && data.truncated ? `<div class="logs-hint warn">${esc(t('logs_truncated_hint'))}</div>` : '';
  const filterNote = _logsSeverityFilter !== 'all'
    ? `<div class="logs-hint">${esc(displayLines.length + ' / ' + _lastLogsLines.length + ' ' + t('logs_filter_active'))}</div>`
    : '';
  if (!displayLines.length) {
    box.innerHTML = `${hint}${truncated}${filterNote}<div class="logs-empty">${esc(t('logs_empty'))}</div>`;
  } else {
    box.innerHTML = `${hint}${truncated}${filterNote}` + displayLines.map(line => {
      const cls = _logLineSeverityClass(line);
      return `<div class="log-line ${cls}">${esc(line)}</div>`;
    }).join('');
  }
  _syncLogsWrap();
  if (status) {
    const bytes = data && Number(data.total_bytes || 0);
    const when = data && data.mtime ? new Date(data.mtime * 1000).toLocaleString() : t('logs_no_mtime');
    status.textContent = `${rawLines.length} / ${data.tail || _selectedLogsTail()} lines · ${bytes.toLocaleString()} bytes · ${when}`;
  }
}

function _startLogsAutoRefresh() {
  if (_logsAutoRefreshTimer) return;
  _logsAutoRefreshTimer = setInterval(() => {
    if (_currentPanel !== 'logs') { _stopLogsAutoRefresh(); return; }
    const toggle = $('logsAutoRefresh');
    if (toggle && !toggle.checked) return;
    loadLogs(false);
  }, 5000);
}

function _stopLogsAutoRefresh() {
  if (_logsAutoRefreshTimer) {
    clearInterval(_logsAutoRefreshTimer);
    _logsAutoRefreshTimer = null;
  }
}

function _syncLogsAutoRefresh() {
  const toggle = $('logsAutoRefresh');
  if (_currentPanel === 'logs' && (!toggle || toggle.checked)) _startLogsAutoRefresh();
  else _stopLogsAutoRefresh();
}

async function copyLogsAll() {
  const lines = _filteredLogsLines();
  const text = lines.join('\n');
  try {
    await _copyText(text);
    showToast(t('logs_copied'));
  } catch(e) {
    showToast(t('copy_failed'), 'error');
  }
}

// ── Activity panel (internal: audit trail) ──
// Read-only browse over the existing turn/run journals -- no new storage,
// no slash command (browse/inspect surface, not something you'd script).
// See docs/HERMES_STUDIO_PARITY_PLAN.md, "Priority 3 -- Audit Trail UI".
let _auditKnownSessionIds = [];

function _auditStatusLabel(status) {
  const key = {
    running: 'audit_status_running',
    completed: 'audit_status_completed',
    interrupted: 'audit_status_interrupted',
  }[status];
  return key ? (t(key) || status) : status;
}

function _auditSyncSessionFilterOptions(entries) {
  const select = $('auditSessionFilter');
  if (!select) return;
  const seen = new Set();
  const ids = [];
  entries.forEach(e => {
    if (e.session_id && !seen.has(e.session_id)) { seen.add(e.session_id); ids.push(e.session_id); }
  });
  // Keep the currently-selected filter's id in the list even if it fell out
  // of the latest cross-session page, so switching back to "All sessions"
  // and back again doesn't silently drop the option out from under the user.
  const current = select.value;
  if (current && !seen.has(current)) ids.push(current);
  if (JSON.stringify(ids) === JSON.stringify(_auditKnownSessionIds)) return;
  _auditKnownSessionIds = ids;
  const allLabel = t('audit_all_sessions') || 'All sessions';
  select.innerHTML = `<option value="">${esc(allLabel)}</option>` +
    ids.map(sid => `<option value="${esc(sid)}">${esc(sid)}</option>`).join('');
  select.value = current;
}

async function loadAuditTrail() {
  const box = $('auditList');
  const refreshBtn = $('auditRefreshBtn');
  if (!box) return;
  if (refreshBtn) { refreshBtn.style.opacity = '0.5'; refreshBtn.disabled = true; }
  const sessionFilter = $('auditSessionFilter');
  const sessionId = sessionFilter ? sessionFilter.value : '';
  try {
    const query = sessionId ? '?session_id=' + encodeURIComponent(sessionId) : '?limit=50';
    const data = await api('/api/audit' + query);
    const entries = Array.isArray(data && data.entries) ? data.entries : [];
    if (!sessionId) _auditSyncSessionFilterOptions(entries);
    _renderAuditEntries(entries);
  } catch(e) {
    box.innerHTML = `<div style="color:var(--muted);font-size:12px">${esc(t('error_prefix') + e.message)}</div>`;
  } finally {
    if (refreshBtn) { refreshBtn.style.opacity = ''; refreshBtn.disabled = false; }
  }
}

function _auditEntryRow(entry) {
  const submittedMs = entry.submitted_at ? entry.submitted_at * 1000 : null;
  const when = submittedMs ? esc(_formatRelativeSessionTime(submittedMs)) : '';
  const statusLabel = esc(_auditStatusLabel(entry.status));
  const model = entry.model ? `<span class="audit-entry-model">${esc(entry.model)}</span>` : '';
  const preview = entry.content_preview
    ? `<div class="audit-entry-preview">${esc(entry.content_preview)}</div>`
    : `<div class="audit-entry-preview audit-entry-preview-empty">${esc(t('audit_no_content') || 'No content')}</div>`;
  const runSummary = entry.run_summary
    ? `<div class="audit-entry-run-summary">${esc((entry.run_summary.event_count || 0) + ' events · ' + (entry.run_summary.last_event || entry.run_summary.terminal_state || ''))}</div>`
    : '';
  return `<article class="audit-entry" data-audit-status="${esc(entry.status)}">
    <div class="audit-entry-head">
      <span class="audit-entry-status-badge audit-entry-status-${esc(entry.status)}">${statusLabel}</span>
      <span class="audit-entry-session">${esc(entry.session_id)}</span>
      ${model}
      <span class="audit-entry-time">${when}</span>
    </div>
    ${preview}
    ${runSummary}
  </article>`;
}

function _renderAuditEntries(entries) {
  const box = $('auditList');
  if (!box) return;
  if (!entries.length) {
    box.innerHTML = `<div style="color:var(--muted);font-size:12px">${esc(t('audit_empty') || 'No activity yet.')}</div>`;
    return;
  }
  box.innerHTML = entries.map(_auditEntryRow).join('');
}

// ── Insights panel ──
const STATIC_MODEL_HEALTH_ROWS = [
  {id:'openai/gpt-5.4-mini', provider:'OpenAI', inputCostPerM:0.25, outputCostPerM:2.00, replacement:'Default economical general-purpose model'},
  {id:'openai/gpt-5.4', provider:'OpenAI', inputCostPerM:2.00, outputCostPerM:10.00, replacement:'Use for complex synthesis; fall back to Mini for routine turns'},
  {id:'anthropic/claude-sonnet-4.5', provider:'Anthropic', inputCostPerM:3.00, outputCostPerM:15.00, replacement:'Strong coding and analysis option; use Mini for low-risk chat'},
  {id:'google/gemini-2.5-pro', provider:'Google', inputCostPerM:1.25, outputCostPerM:10.00, replacement:'Long-context research option; use Flash for speed-sensitive work'},
  {id:'google/gemini-2.5-flash', provider:'Google', inputCostPerM:0.30, outputCostPerM:2.50, replacement:'Low-latency replacement for lighter multimodal or research turns'},
];

function _renderModelHealthCost(row) {
  const input = Number(row.inputCostPerM || 0);
  const output = Number(row.outputCostPerM || 0);
  return `$${input.toFixed(2)} / $${output.toFixed(2)}`;
}

function _renderStaticModelHealthTable() {
  const rows = STATIC_MODEL_HEALTH_ROWS.map(row => `<div class="insights-table-row">
    <span class="insights-model-name" title="${esc(row.id)}">${esc(row.id)}</span>
    <span>${esc(row.provider)}</span>
    <span>${esc(_renderModelHealthCost(row))}</span>
    <span class="insights-model-health-replacement">${esc(row.replacement)}</span>
  </div>`).join('');
  return `<details class="insights-card insights-model-health-card"><summary><span class="insights-card-title">${esc(t('insights_model_health_title'))}</span></summary><div class="insights-table insights-model-health-table"><div class="insights-table-head"><span>${esc(t('insights_model_name'))}</span><span>${esc(t('insights_model_health_provider'))}</span><span>${esc(t('insights_model_health_cost_per_m'))}</span><span>${esc(t('insights_model_health_replacement'))}</span></div>${rows}</div></details>`;
}

async function loadInsights(animate) {
  const box = $('insightsContent');
  const refreshBtn = $('insightsRefreshBtn');
  if (!box) return;
  if (animate && refreshBtn) {
    refreshBtn.style.opacity = '0.5';
    refreshBtn.disabled = true;
  }
  const period = ($('insightsPeriod') || {}).value || '30';
  try {
    const [data, wikiStatus, skillUsage] = await Promise.all([
      api(`/api/insights?days=${period}`),
      api('/api/wiki/status').catch(err => ({status:'error', error: err.message || String(err)})),
      api('/api/skills/usage').catch(() => ({usage:{}, skill_names:[], total_invocations:0, unique_skills_used:0})),
    ]);
    _renderInsights(data, box, wikiStatus, skillUsage);
    if (typeof _syncSystemHealthMonitorVisibility === 'function') _syncSystemHealthMonitorVisibility();
    if (typeof pollSystemHealth === 'function') void pollSystemHealth();
  } catch(e) {
    box.innerHTML = `<div style="color:var(--accent);font-size:12px">${esc(t('error_prefix') + e.message)}</div>`;
  } finally {
    if (animate && refreshBtn) {
      refreshBtn.style.opacity = '';
      refreshBtn.disabled = false;
    }
  }
}

function _formatLlmWikiTimestamp(value) {
  if (!value) return 'Never';
  try { return new Date(value).toLocaleString(); }
  catch (_) { return String(value); }
}

function _renderSystemHealthPanel() {
  return `
    <section class="insights-card system-health-panel loading" id="systemHealthPanel" aria-label="Host resource health" aria-live="polite">
      <div class="system-health-head">
        <div>
          <div class="insights-card-title">System health</div>
          <div class="system-health-sub">Current VPS resource usage</div>
        </div>
        <span class="system-health-status" id="systemHealthStatus"><span class="system-health-dot" aria-hidden="true"></span>Loading…</span>
      </div>
      <div class="system-health-metrics">
        <div class="system-health-metric" data-system-health-metric="cpu">
          <div class="system-health-label"><span>CPU</span><span class="system-health-value" data-system-health-value>—</span></div>
          <div class="system-health-bar" role="progressbar" aria-label="CPU usage" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><div class="system-health-bar-fill"></div></div>
        </div>
        <div class="system-health-metric" data-system-health-metric="memory">
          <div class="system-health-label"><span>RAM</span><span class="system-health-value" data-system-health-value>—</span></div>
          <div class="system-health-bar" role="progressbar" aria-label="RAM usage" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><div class="system-health-bar-fill"></div></div>
        </div>
        <div class="system-health-metric" data-system-health-metric="disk">
          <div class="system-health-label"><span>Disk</span><span class="system-health-value" data-system-health-value>—</span></div>
          <div class="system-health-bar" role="progressbar" aria-label="Disk usage" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><div class="system-health-bar-fill"></div></div>
        </div>
      </div>
      <div class="system-health-foot">Live snapshot only; historical resource charts can build on this surface later.</div>
    </section>`;
}

function _renderLlmWikiStatus(d) {
  const status = d || {status:'error'};
  const isReady = status.available && status.status === 'ready';
  const isEmpty = status.available && status.status === 'empty';
  const isError = status.status === 'error';
  const badgeClass = isReady ? 'ok' : isError ? 'err' : isEmpty ? 'warn' : 'muted';
  const badgeText = isReady ? 'Available' : isError ? 'Error' : isEmpty ? 'Empty' : 'Unavailable';
  const rawDocsUrl = status.docs_url || 'https://hermes-agent.nousresearch.com/docs/user-guide/skills/bundled/research/research-llm-wiki';
  // Guard against unsafe URL schemes (e.g. js: / data:) if docs_url ever
  // becomes config-driven. esc() HTML-escapes but doesn't validate URL scheme.
  const docsUrl = /^https?:\/\//i.test(rawDocsUrl) ? rawDocsUrl : '#';
  const toggleNote = status.toggle_available
    ? 'Toggle available from configured Hermes Agent setting.'
    : (status.toggle_reason || 'No stable LLM Wiki on/off config flag was detected, so this panel is read-only.');
  const statusNote = isReady
    ? 'LLM Wiki is configured and page metadata is visible without exposing wiki content.'
    : isEmpty
      ? 'LLM Wiki exists but has no entity, concept, comparison, or query pages yet.'
      : isError
        ? `Unable to inspect LLM Wiki status${status.error ? ': ' + status.error : ''}.`
        : 'No LLM Wiki directory was found. Set WIKI_PATH or skills.config.wiki.path to enable status visibility.';
  return `
    <div class="insights-card wiki-status-card" id="llmWikiStatusCard">
      <div class="wiki-status-head">
        <div>
          <div class="insights-card-title">LLM Wiki</div>
          <div class="wiki-status-sub">Knowledge-base observability</div>
        </div>
        <span class="wiki-status-badge ${badgeClass}">${esc(badgeText)}</span>
      </div>
      <div class="wiki-status-note">${esc(statusNote)}</div>
      <div class="wiki-status-grid">
        <div><span>Enabled</span><strong>${status.enabled ? 'Yes' : 'No'}</strong></div>
        <div><span>Entries</span><strong>${Number(status.entry_count || 0).toLocaleString()}</strong></div>
        <div><span>Pages</span><strong>${Number(status.page_count || 0).toLocaleString()}</strong></div>
        <div><span>raw/ files</span><strong>${Number(status.raw_source_count || 0).toLocaleString()}</strong></div>
        <div><span>Last updated</span><strong>${esc(_formatLlmWikiTimestamp(status.last_updated))}</strong></div>
        <div><span>Last writer</span><strong>${esc(status.last_writer || 'Not available')}</strong></div>
      </div>
      <div class="wiki-status-footer">
        <span>${esc(toggleNote)}</span>
        <div style="display:flex;align-items:center;gap:8px;">
          ${isReady || isEmpty ? `<button class="wiki-browse-btn" onclick="_openWikiBrowser()">${esc(t('wiki_browse'))}</button>` : ''}
          <a href="${esc(docsUrl)}" target="_blank" rel="noopener noreferrer">Docs</a>
        </div>
      </div>
    </div>`;
}

async function _openWikiBrowser() {
  const existing = document.getElementById('wikiBrowserOverlay');
  if (existing) { existing.style.display = 'flex'; return; }

  const overlay = document.createElement('div');
  overlay.id = 'wikiBrowserOverlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:9999;';

  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.style.display = 'none'; });
  document.addEventListener('keydown', function escHandler(e) {
    if (e.key === 'Escape') { overlay.style.display = 'none'; document.removeEventListener('keydown', escHandler); }
  });

  const panel = document.createElement('div');
  panel.style.cssText = 'background:var(--bg);border:1px solid var(--border);border-radius:8px;width:min(720px,95vw);max-height:80vh;display:flex;flex-direction:column;overflow:hidden;';

  panel.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid var(--border);">
      <strong style="font-size:14px;">${esc(t('wiki_browse'))}</strong>
      <button onclick="document.getElementById('wikiBrowserOverlay').style.display='none'" style="background:none;border:none;cursor:pointer;font-size:18px;color:var(--muted);">&#x2715;</button>
    </div>
    <div style="padding:10px 16px;border-bottom:1px solid var(--border);">
      <input id="wikiBrowserSearch" type="text" placeholder="${esc(t('wiki_search_placeholder'))}" style="width:100%;padding:6px 10px;background:var(--input-bg,var(--bg));border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:13px;box-sizing:border-box;" />
    </div>
    <div id="wikiBrowserList" style="flex:1;overflow-y:auto;padding:8px 0;min-height:80px;"></div>
    <div id="wikiBrowserContent" style="display:none;flex:1;overflow-y:auto;padding:16px;border-top:1px solid var(--border);"></div>`;

  overlay.appendChild(panel);
  document.body.appendChild(overlay);

  const listEl = document.getElementById('wikiBrowserList');
  const contentEl = document.getElementById('wikiBrowserContent');
  const searchEl = document.getElementById('wikiBrowserSearch');
  let _pages = [];

  function _renderWikiPageList(filter) {
    const q = (filter || '').toLowerCase();
    const visible = q ? _pages.filter(p => p.name.toLowerCase().includes(q)) : _pages;
    if (!visible.length) {
      listEl.innerHTML = `<div style="padding:12px 16px;color:var(--muted);font-size:13px;">${esc(t('wiki_no_pages'))}</div>`;
      return;
    }
    listEl.innerHTML = visible.map(p =>
      `<div class="wiki-browser-item" data-path="${esc(p.path)}" style="padding:7px 16px;cursor:pointer;font-size:13px;border-radius:4px;margin:0 6px;" onmouseover="this.style.background='var(--hover,rgba(255,255,255,0.07))'" onmouseout="this.style.background=''" onclick="window._wikiBrowserOpenPage(this.dataset.path)">${esc(p.name)}</div>`
    ).join('');
  }

  window._wikiBrowserOpenPage = async function(path) {
    contentEl.innerHTML = '<div style="padding:12px;color:var(--muted);font-size:13px;">Loading...</div>';
    contentEl.style.display = 'block';
    listEl.style.display = 'none';
    try {
      const data = await api('/api/wiki/page?path=' + encodeURIComponent(path));
      if (typeof renderMarkdownPreviewContent === 'function') {
        contentEl.innerHTML = '<button onclick="window._wikiBrowserBack()" style="margin-bottom:10px;background:none;border:1px solid var(--border);border-radius:4px;padding:3px 10px;cursor:pointer;font-size:12px;color:var(--text);">&#8592; Back</button><div id="wikiBrowserMd"></div>';
        renderMarkdownPreviewContent({content: data.content, el: document.getElementById('wikiBrowserMd')});
      } else {
        contentEl.innerHTML = '<button onclick="window._wikiBrowserBack()" style="margin-bottom:10px;background:none;border:1px solid var(--border);border-radius:4px;padding:3px 10px;cursor:pointer;font-size:12px;color:var(--text);">&#8592; Back</button><pre style="white-space:pre-wrap;word-break:break-word;font-size:12px;margin:0;">' + esc(data.content) + '</pre>';
      }
    } catch(e) {
      contentEl.innerHTML = '<button onclick="window._wikiBrowserBack()" style="margin-bottom:10px;background:none;border:1px solid var(--border);border-radius:4px;padding:3px 10px;cursor:pointer;font-size:12px;color:var(--text);">&#8592; Back</button><div style="color:var(--error,#f55);">' + esc(e.message || String(e)) + '</div>';
    }
  };

  window._wikiBrowserBack = function() {
    contentEl.style.display = 'none';
    listEl.style.display = '';
  };

  searchEl.addEventListener('input', () => _renderWikiPageList(searchEl.value));

  try {
    const data = await api('/api/wiki/browse');
    _pages = Array.isArray(data && data.pages) ? data.pages : [];
    if (!_pages.length) {
      listEl.innerHTML = `<div style="padding:12px 16px;color:var(--muted);font-size:13px;">${esc(t('wiki_no_pages'))}</div>`;
    } else {
      _renderWikiPageList('');
    }
  } catch(e) {
    listEl.innerHTML = `<div style="padding:12px 16px;color:var(--error,#f55);font-size:13px;">${esc(e.message || String(e))}</div>`;
  }
}

/**
 * Bucket daily token rows for chart display.
 * Returns rows unchanged when length <= 30 (per-day resolution).
 * For longer ranges, groups consecutive days into buckets:
 *   31–90 days → 2-day buckets
 *   91–180 days → 3-day buckets
 *   181–365 days → 8-day buckets
 * Result is always <= ~52 bars.
 * Each bucket row has:
 *   - label: short label for axis (e.g. MM-DD or MM-DD–MM-DD)
 *   - title: full tooltip title (e.g. 2026-01-01 – 2026-01-05)
 *   - date: first date in bucket (used for date label slicing)
 *   - input_tokens, output_tokens, sessions, cost: summed across bucket
 */
function _bucketDailyTokensForChart(rows) {
  if (!Array.isArray(rows) || rows.length === 0) return [];
  const len = rows.length;
  if (len <= 30) return rows;  // per-day resolution for 7/30-day ranges

  // Target <= 75 bars; derive bucket size
  let bucketSize;
  if (len <= 90) {
    bucketSize = 2;
  } else if (len <= 180) {
    bucketSize = 3;
  } else if (len <= 365) {
    bucketSize = 8;  // <=52 bars for 365 days (ceil(365/8)=46)
  } else {
    bucketSize = 8;  // fallback for >365 (shouldn't occur in practice)
  }

  const result = [];
  for (let i = 0; i < len; i += bucketSize) {
    const slice = rows.slice(i, i + bucketSize);
    const input_tokens = slice.reduce((s, r) => s + Number(r.input_tokens || 0), 0);
    const output_tokens = slice.reduce((s, r) => s + Number(r.output_tokens || 0), 0);
    const cache_read_tokens = slice.reduce((s, r) => s + Number(r.cache_read_tokens || 0), 0);
    const sessions = slice.reduce((s, r) => s + Number(r.sessions || 0), 0);
    const cost = slice.reduce((s, r) => s + Number(r.cost || 0), 0);

    const firstDate = slice[0].date;
    const lastDate = slice[slice.length - 1].date;

    // Label: short form for axis
    const firstLabel = String(firstDate).slice(5);  // MM-DD
    const lastLabel = String(lastDate).slice(5);
    const label = (firstDate === lastDate) ? firstLabel : (firstLabel + '–' + lastLabel);

    result.push({
      label,
      title: firstDate + (firstDate !== lastDate ? ' – ' + lastDate : ''),
      date: firstDate,
      input_tokens,
      output_tokens,
      cache_read_tokens,
      sessions,
      cost,
    });
  }
  return result;
}

function _renderSkillUsage(d) {
  const usage = d.usage || {};
  const skillNames = d.skill_names || [];
  const totalInvocations = d.total_invocations || 0;
  const uniqueUsed = d.unique_skills_used || 0;
  const entries = Object.entries(usage)
    .map(([name, meta]) => [name, Number(meta && meta.use_count) || 0, Number(meta && meta.view_count) || 0, Number(meta && meta.patch_count) || 0])
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);
  if (!entries.length) {
    return `<div class="insights-card" id="skillUsageCard"><div class="insights-card-title">${esc(t('insights_skill_usage_title'))}</div><div class="insights-empty">${esc(t('insights_skill_usage_no_data'))}</div><div style="font-size:11px;color:var(--muted);margin-top:4px">${esc(t('insights_skill_usage_no_data_hint'))}</div></div>`;
  }
  const rows = entries.map(([name, useCount, viewCount, patchCount]) => {
    const share = totalInvocations > 0 ? (useCount / totalInvocations * 100).toFixed(1) : '0.0';
    return `<div class="insights-table-row"><span class="insights-model-name" title="${esc(name)}">${esc(name)}</span><span>${useCount}</span><span>${viewCount}</span><span>${patchCount}</span><span>${share}%</span></div>`;
  }).join('');
  return `<div class="insights-card" id="skillUsageCard"><div class="insights-card-title">${esc(t('insights_skill_usage_title'))}</div><div class="skill-usage-grid" style="margin-bottom:8px"><div><span>${esc(t('insights_skill_usage_total'))}</span><strong>${totalInvocations.toLocaleString()}</strong></div><div><span>${esc(t('insights_skill_usage_skills_used'))}</span><strong>${uniqueUsed}/${skillNames.length}</strong></div></div><div class="insights-table skill-usage-table"><div class="insights-table-head"><span>${esc(t('insights_skill_usage_col_skill'))}</span><span>${esc(t('insights_skill_usage_col_uses'))}</span><span>${esc(t('insights_skill_usage_col_views'))}</span><span>${esc(t('insights_skill_usage_col_patches'))}</span><span>${esc(t('insights_skill_usage_col_share'))}</span></div>${rows}</div><div class="wiki-status-footer" style="margin-top:8px">${esc(t('insights_skill_usage_footer'))}</div></div>`;
}

function _renderInsights(d, box, wikiStatus, skillUsage) {
  const fmtNum = n => Number(n || 0).toLocaleString();
  const fmtCost = c => {
    const value = Number(c || 0);
    return value > 0 ? '$' + value.toFixed(value < 1 ? 4 : 2) : t('insights_no_cost');
  };
  const fmtTokens = n => {
    const value = Number(n || 0);
    return value >= 1e6 ? (value/1e6).toFixed(1) + 'M' : value >= 1e3 ? (value/1e3).toFixed(1) + 'K' : fmtNum(value);
  };

  // Overview cards
  const overviewCards = [
    { label: t('insights_sessions'), value: fmtNum(d.total_sessions), icon: li('message-square', 18) },
    { label: t('insights_messages'), value: fmtNum(d.total_messages), icon: li('hash', 18) },
    { label: t('insights_tokens'), value: fmtTokens(d.total_tokens), icon: li('cpu', 18) },
    { label: t('insights_cost'), value: fmtCost(d.total_cost), icon: li('dollar-sign', 18) },
  ];

  // Daily token trend — bucket long ranges to avoid horizontal overflow
  const dailyTokens = Array.isArray(d.daily_tokens) ? d.daily_tokens : [];
  const chartRows = _bucketDailyTokensForChart(dailyTokens);
  let dailyHtml = '';
  if (chartRows.length) {
    const maxDailyTokens = Math.max(...chartRows.map(r => Number(r.input_tokens || 0) + Number(r.output_tokens || 0)), 1);
    const labelEvery = Math.max(Math.ceil(chartRows.length / 7), 1);
    dailyHtml = `<div class="insights-card"><div class="insights-card-title">${esc(t('insights_daily_tokens'))}</div><div class="insights-daily-token-chart">` +
      chartRows.map((r, idx) => {
        const input = Number(r.input_tokens || 0);
        const output = Number(r.output_tokens || 0);
        const inputPct = Math.max((input / maxDailyTokens) * 100, input ? 2 : 0).toFixed(1);
        const outputPct = Math.max((output / maxDailyTokens) * 100, output ? 2 : 0).toFixed(1);
        const showLabel = idx === 0 || idx === chartRows.length - 1 || idx % labelEvery === 0;
        const titleDate = r.title || r.date;
        const cacheRead = Number(r.cache_read_tokens || 0);
        // Bounded daily cache hit rate: reads / (input + reads), 0-100%.
        const cacheDenom = input + cacheRead;
        const cacheStr = (cacheRead > 0 && cacheDenom > 0)
          ? ` · ${Math.min(100, Math.round((cacheRead / cacheDenom) * 100))}% ${t('insights_model_cache')}`
          : '';
        const title = `${titleDate} · ${fmtTokens(input)} ${t('insights_input_tokens')} · ${fmtTokens(output)} ${t('insights_output_tokens')}${cacheStr} · ${fmtCost(r.cost)} · ${fmtNum(r.sessions)} ${t('insights_sessions')}`;
        const labelText = r.label !== undefined ? r.label : String(r.date).slice(5);
        return `<div class="insights-daily-bar" title="${esc(title)}"><div class="insights-daily-stack" aria-label="${esc(title)}"><div class="insights-daily-bar-output" style="height:${outputPct}%"></div><div class="insights-daily-bar-input" style="height:${inputPct}%"></div></div><span>${showLabel ? esc(labelText) : ''}</span></div>`;
      }).join('') +
      `</div><div class="insights-daily-legend"><span><i class="insights-daily-legend-input"></i>${esc(t('insights_input_tokens'))}</span><span><i class="insights-daily-legend-output"></i>${esc(t('insights_output_tokens'))}</span></div></div>`;
  } else {
    dailyHtml = `<div class="insights-card"><div class="insights-card-title">${esc(t('insights_daily_tokens'))}</div><div class="insights-empty">${esc(t('insights_no_usage_data'))}</div></div>`;
  }

  // Models table
  let modelsHtml = '';
  if (d.models && d.models.length) {
    modelsHtml = `<div class="insights-card"><div class="insights-card-title">${esc(t('insights_models'))}</div><div class="insights-table insights-model-table"><div class="insights-table-head"><span>${esc(t('insights_model_name'))}</span><span>${esc(t('insights_model_sessions'))}</span><span>${esc(t('insights_model_tokens'))}</span><span title="${esc(t('insights_cache_hit'))}">${esc(t('insights_model_cache'))}</span><span>${esc(t('insights_model_cost'))}</span><span>${esc(t('insights_model_share'))}</span></div>` +
      d.models.map(m => {
        const share = Number(m.cost_share || m.token_share || m.session_share || 0);
        const title = `${m.model} · ${fmtTokens(m.input_tokens)} ${t('insights_input_tokens')} · ${fmtTokens(m.output_tokens)} ${t('insights_output_tokens')}`;
        const cachePct = (m.cache_hit_percent === null || m.cache_hit_percent === undefined) ? null : Number(m.cache_hit_percent);
        const cacheCell = cachePct === null
          ? '<span class="insights-model-cache insights-model-cache-empty">—</span>'
          : `<span class="insights-model-cache" title="${esc(t('insights_cache_hit'))}: ${fmtTokens(m.cache_read_tokens || 0)}">${cachePct}%</span>`;
        return `<div class="insights-table-row"><span class="insights-model-name" title="${esc(m.model)}">${esc(m.model)}</span><span>${fmtNum(m.sessions)}</span><span class="insights-model-tokens" title="${esc(title)}">${fmtTokens(m.total_tokens || 0)}</span>${cacheCell}<span class="insights-model-cost">${fmtCost(m.cost)}</span><span>${share}%</span></div>`;
      }).join('') +
      `</div></div>`;
  } else {
    modelsHtml = `<div class="insights-card"><div class="insights-card-title">${esc(t('insights_models'))}</div><div class="insights-empty">${esc(t('insights_no_usage_data'))}</div></div>`;
  }
  const modelHealthHtml = _renderStaticModelHealthTable();

  // Activity by day of week
  let dowHtml = '';
  if (d.activity_by_day) {
    const maxDow = Math.max(...d.activity_by_day.map(x => x.sessions), 1);
    dowHtml = `<div class="insights-card"><div class="insights-card-title">${esc(t('insights_activity_by_day'))}</div><div class="insights-bars">` +
      d.activity_by_day.map(r => {
        const pct = (r.sessions / maxDow * 100).toFixed(0);
        return `<div class="insights-bar-row"><span class="insights-bar-label">${r.day}</span><div class="insights-bar-track"><div class="insights-bar-fill" style="width:${pct}%"></div></div><span class="insights-bar-value">${r.sessions}</span></div>`;
      }).join('') +
      `</div></div>`;
  }

  // Activity by hour
  let hodHtml = '';
  if (d.activity_by_hour) {
    const maxHod = Math.max(...d.activity_by_hour.map(x => x.sessions), 1);
    const peakHour = d.activity_by_hour.reduce((a, b) => b.sessions > a.sessions ? b : a, {hour:0,sessions:0});
    hodHtml = `<div class="insights-card"><div class="insights-card-title">${esc(t('insights_activity_by_hour'))} <span style="font-weight:400;font-size:11px;color:var(--muted)">${esc(t('insights_peak_hour').replace('{hour}', peakHour.hour + ':00'))}</span></div><div class="insights-bars">` +
      d.activity_by_hour.map(r => {
        const pct = (r.sessions / maxHod * 100).toFixed(0);
        const isPeak = r.hour === peakHour.hour && peakHour.sessions > 0;
        return `<div class="insights-bar-row"><span class="insights-bar-label">${String(r.hour).padStart(2,'0')}</span><div class="insights-bar-track"><div class="insights-bar-fill${isPeak ? ' insights-bar-peak' : ''}" style="width:${pct}%"></div></div><span class="insights-bar-value">${r.sessions}</span></div>`;
      }).join('') +
      `</div></div>`;
  }

  // Token breakdown
  const tokenCards = `
    <div class="insights-card">
      <div class="insights-card-title">${esc(t('insights_token_breakdown'))}</div>
      <div class="insights-token-row">
        <span class="insights-token-label">${esc(t('insights_input_tokens'))}</span>
        <span class="insights-token-value">${fmtTokens(d.total_input_tokens)}</span>
      </div>
      <div class="insights-token-row">
        <span class="insights-token-label">${esc(t('insights_output_tokens'))}</span>
        <span class="insights-token-value">${fmtTokens(d.total_output_tokens)}</span>
      </div>
      <div class="insights-token-row insights-token-total">
        <span class="insights-token-label">${esc(t('insights_total'))}</span>
        <span class="insights-token-value">${fmtTokens(d.total_tokens)}</span>
      </div>
    </div>`;

  box.innerHTML = `
    ${_renderSystemHealthPanel()}
    ${_renderLlmWikiStatus(wikiStatus)}
    ${_renderSkillUsage(skillUsage)}
    <div class="insights-grid">
      ${overviewCards.map(c => `<div class="insights-stat"><div class="insights-stat-icon">${c.icon}</div><div class="insights-stat-info"><div class="insights-stat-value">${c.value}</div><div class="insights-stat-label">${esc(c.label)}</div></div></div>`).join('')}
    </div>
    ${dailyHtml}
    ${modelHealthHtml}
    <div class="insights-row insights-usage-grid">
      ${tokenCards}
      ${modelsHtml}
    </div>
    ${dowHtml}
    ${hodHtml}
    <div style="text-align:center;color:var(--muted);font-size:10px;margin-top:12px;opacity:.6">${esc(t('insights_footer').replace('{days}', d.period_days))}</div>
  `;
}

// ── Analytics panel (provider-level cost/usage trends; complements Insights) ──
// See docs/HERMES_STUDIO_PARITY_PLAN.md, "Analytics/cost dashboard".

async function loadAnalytics(animate) {
  const box = $('analyticsContent');
  const refreshBtn = $('analyticsRefreshBtn');
  if (!box) return;
  if (animate && refreshBtn) {
    refreshBtn.style.opacity = '0.5';
    refreshBtn.disabled = true;
  }
  const period = ($('analyticsPeriod') || {}).value || '30';
  const granularity = ($('analyticsGranularity') || {}).value || 'week';
  try {
    const data = await api(`/api/analytics?days=${period}&granularity=${granularity}`);
    _renderAnalytics(data, box);
  } catch(e) {
    box.innerHTML = `<div style="color:var(--accent);font-size:12px">${esc(t('error_prefix') + e.message)}</div>`;
  } finally {
    if (animate && refreshBtn) {
      refreshBtn.style.opacity = '';
      refreshBtn.disabled = false;
    }
  }
}

function _renderAnalytics(d, box) {
  const fmtNum = n => (n || 0).toLocaleString();
  const fmtCost = v => (v || 0) > 0 ? '$' + v.toFixed(v < 1 ? 4 : 2) : t('insights_no_cost');
  const fmtTokens = n => {
    n = n || 0;
    if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return String(n);
  };

  const overviewCards = [
    { label: t('analytics_total_sessions'), value: fmtNum(d.total_sessions), icon: li('message-square', 18) },
    { label: t('analytics_total_tokens'), value: fmtTokens(d.total_tokens), icon: li('cpu', 18) },
    { label: t('analytics_total_cost'), value: fmtCost(d.total_cost), icon: li('dollar-sign', 18) },
  ];

  let providersHtml;
  if (d.providers && d.providers.length) {
    const rows = d.providers.map(p => {
      const label = p.provider === 'unknown' ? t('analytics_unknown_provider') : p.provider;
      return `<div class="insights-table-row"><span class="insights-model-name" title="${esc(label)}">${esc(label)}</span><span>${fmtNum(p.sessions)}</span><span class="insights-model-tokens">${fmtTokens((p.input_tokens||0) + (p.output_tokens||0))}</span><span class="insights-model-cost">${fmtCost(p.cost)}</span><span>${p.cost_share}%</span></div>`;
    }).join('');
    providersHtml = `<div class="insights-card"><div class="insights-card-title">${esc(t('analytics_providers'))}</div><div class="insights-table insights-model-table"><div class="insights-table-head"><span>${esc(t('analytics_provider_col_provider'))}</span><span>${esc(t('analytics_provider_col_sessions'))}</span><span>${esc(t('analytics_provider_col_tokens'))}</span><span>${esc(t('analytics_provider_col_cost'))}</span><span>${esc(t('analytics_provider_col_share'))}</span></div>${rows}</div></div>`;
  } else {
    providersHtml = `<div class="insights-card"><div class="insights-card-title">${esc(t('analytics_providers'))}</div><div class="insights-empty">${esc(t('analytics_no_data'))}</div></div>`;
  }

  let trendHtml;
  if (d.trend && d.trend.length) {
    const maxCost = Math.max(...d.trend.map(r => r.cost || 0), 0.0001);
    const bars = d.trend.map(r => {
      const pct = Math.max(2, Math.round(((r.cost || 0) / maxCost) * 100));
      const title = `${r.bucket} · ${fmtCost(r.cost)} · ${fmtTokens((r.input_tokens||0)+(r.output_tokens||0))} · ${fmtNum(r.sessions)} ${t('analytics_total_sessions')}`;
      return `<div class="insights-daily-bar" title="${esc(title)}"><div class="insights-daily-stack" aria-label="${esc(title)}"><div class="insights-daily-bar-input" style="height:${pct}%"></div></div><span>${esc(r.bucket)}</span></div>`;
    }).join('');
    trendHtml = `<div class="insights-card"><div class="insights-card-title">${esc(t('analytics_trend_title'))}</div><div class="insights-daily-token-chart">${bars}</div></div>`;
  } else {
    trendHtml = `<div class="insights-card"><div class="insights-card-title">${esc(t('analytics_trend_title'))}</div><div class="insights-empty">${esc(t('analytics_no_data'))}</div></div>`;
  }

  let topSessionsHtml;
  if (d.top_sessions && d.top_sessions.length) {
    const rows = d.top_sessions.map(s => `<div class="insights-table-row"><span class="insights-model-name" title="${esc(s.title || '')}">${esc(s.title || s.session_id || '')}</span><span>${esc(s.provider || '')}</span><span class="insights-model-cost">${fmtCost(s.cost)}</span></div>`).join('');
    topSessionsHtml = `<div class="insights-card"><div class="insights-card-title">${esc(t('analytics_top_sessions_title'))}</div><div class="insights-table"><div class="insights-table-head"><span>${esc(t('analytics_provider_col_provider'))} / ${esc(t('insights_sessions'))}</span><span>${esc(t('analytics_provider_col_provider'))}</span><span>${esc(t('analytics_provider_col_cost'))}</span></div>${rows}</div></div>`;
  } else {
    topSessionsHtml = `<div class="insights-card"><div class="insights-card-title">${esc(t('analytics_top_sessions_title'))}</div><div class="insights-empty">${esc(t('analytics_top_sessions_empty'))}</div></div>`;
  }

  box.innerHTML = `
    <div class="insights-grid">
      ${overviewCards.map(c => `<div class="insights-stat"><div class="insights-stat-icon">${c.icon}</div><div class="insights-stat-info"><div class="insights-stat-value">${c.value}</div><div class="insights-stat-label">${esc(c.label)}</div></div></div>`).join('')}
    </div>
    ${trendHtml}
    ${providersHtml}
    ${topSessionsHtml}
    <div style="text-align:center;color:var(--muted);font-size:10px;margin-top:12px;opacity:.6">${esc(t('insights_footer').replace('{days}', d.period_days))}</div>
  `;
}

async function clearConversation() {
  if(!S.session) return;
  const _clrMsg=await showConfirmDialog({title:t('clear_conversation_title'),message:t('clear_conversation_message'),confirmLabel:t('clear'),danger:true,focusCancel:true});
  if(!_clrMsg) return;
  try {
    const data = await api('/api/session/clear', {method:'POST',
      body: JSON.stringify({session_id: S.session.session_id})});
    S.session = data.session;
    S.messages = [];
    S.toolCalls = [];
    syncTopbar();
    renderMessages();
    showToast(t('conversation_cleared'));
  } catch(e) { setStatus(t('clear_failed') + e.message); }
}

// ── Skills panel ──
async function loadSkills() {
  if (_skillsData) { renderSkills(_skillsData); return; }
  const box = $('skillsList');
  try {
    const data = await api('/api/skills');
    _skillsData = data.skills || [];
    // Prune collapsed state to only keep categories present in fresh data,
    // avoiding stale keys when categories are renamed or removed server-side.
    const liveCats = new Set(_skillsData.map(s => s.category || '(general)'));
    for (const c of _collapsedCats) { if (!liveCats.has(c)) _collapsedCats.delete(c); }
    renderSkills(_skillsData);
  } catch(e) { box.innerHTML = `<div style="padding:12px;color:var(--accent);font-size:12px">Error: ${esc(e.message)}</div>`; }
}

let _collapsedCats = new Set(); // persisted collapsed state across re-renders

function _toggleCatCollapse(cat) {
  if (_collapsedCats.has(cat)) _collapsedCats.delete(cat);
  else _collapsedCats.add(cat);
  // Toggle DOM without full re-render
  document.querySelectorAll('.skills-category').forEach(sec => {
    const header = sec.querySelector('.skills-cat-header');
    if (header && header.dataset.cat === cat) {
      const collapsed = _collapsedCats.has(cat);
      sec.classList.toggle('collapsed', collapsed);
      header.querySelector('.cat-chevron').style.transform = collapsed ? '' : 'rotate(90deg)';
      sec.querySelectorAll('.skill-item').forEach(el => el.style.display = collapsed ? 'none' : '');
    }
  });
}

function renderSkills(skills) {
  const query = ($('skillsSearch').value || '').toLowerCase();
  const filtered = query ? skills.filter(s =>
    (s.name||'').toLowerCase().includes(query) ||
    (s.description||'').toLowerCase().includes(query) ||
    (s.category||'').toLowerCase().includes(query)
  ) : skills;
  // Group by category
  const cats = {};
  for (const s of filtered) {
    const cat = s.category || '(general)';
    if (!cats[cat]) cats[cat] = [];
    cats[cat].push(s);
  }
  const box = $('skillsList');
  box.innerHTML = '';
  if (!filtered.length) { box.innerHTML = `<div style="padding:12px;color:var(--muted);font-size:12px">${esc(t('skills_no_match'))}</div>`; return; }
  for (const [cat, items] of Object.entries(cats).sort()) {
    const collapsed = _collapsedCats.has(cat);
    const sec = document.createElement('div');
    sec.className = 'skills-category' + (collapsed ? ' collapsed' : '');
    const hdr = document.createElement('div');
    hdr.className = 'skills-cat-header';
    hdr.dataset.cat = cat;
    hdr.innerHTML = `<span class="cat-chevron" style="display:inline-flex;transition:transform .15s;${collapsed ? '' : 'transform:rotate(90deg)'}">${li('chevron-right',12)}</span> ${esc(cat)} <span style="opacity:.5">(${items.length})</span>`;
    hdr.onclick = () => _toggleCatCollapse(cat);
    sec.appendChild(hdr);
    for (const skill of items.sort((a,b) => a.name.localeCompare(b.name))) {
      const el = document.createElement('div');
      el.className = 'skill-item' + (skill.disabled ? ' disabled' : '');
      el.style.display = collapsed ? 'none' : '';
      const isDisabled = skill.disabled || false;
      const toggle = document.createElement('span');
      toggle.className = 'skill-toggle' + (isDisabled ? '' : ' enabled');
      toggle.title = isDisabled ? t('skill_disabled') : t('skill_enabled');
      toggle.addEventListener('click', (ev) => {
        ev.stopPropagation();
        toggleSkill(skill.name, !isDisabled);
      });
      const nameEl = document.createElement('span');
      nameEl.className = 'skill-name';
      nameEl.textContent = skill.name;
      const descEl = document.createElement('span');
      descEl.className = 'skill-desc';
      descEl.textContent = skill.description || '';
      el.append(toggle, nameEl, descEl);
      el.onclick = () => openSkill(skill.name, el);
      sec.appendChild(el);
    }
    box.appendChild(sec);
  }
}

function filterSkills() {
  if (_skillsData) renderSkills(_skillsData);
}


async function toggleSkill(name, currentlyEnabled) {
  const newEnabled = !currentlyEnabled;
  try {
    const result = await api('/api/skills/toggle', {
      method: 'POST',
      body: JSON.stringify({ name, enabled: newEnabled })
    });
    if (result && result.ok) {
      if (_skillsData) {
        const skill = _skillsData.find(s => s.name === name);
        if (skill) skill.disabled = !newEnabled;
      }
      if(typeof window!=='undefined'&&typeof window.invalidateSlashSkillCaches==='function') window.invalidateSlashSkillCaches();
      renderSkills(_skillsData || []);
    } else {
      setStatus((result && result.error) || t('skill_toggle_failed'));
    }
  } catch(e) {
    setStatus(t('skill_toggle_failed') + e.message);
  }
}

// Currently selected skill detail — kept across panel switches so re-entering
// the Skills view shows the last-viewed skill.
let _currentSkillDetail = null; // { name, category, content }
let _skillMode = 'empty'; // 'empty' | 'read' | 'create' | 'edit'
let _skillPreFormDetail = null; // snapshot of previously-viewed skill when entering a form
let _editingSkillName = null;

function _stripYamlFrontmatter(content) {
  if (!content) return { frontmatter: null, body: '' };
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(content);
  if (!m) return { frontmatter: null, body: content };
  return { frontmatter: m[1], body: content.slice(m[0].length) };
}

function _skillMarkdownHtml(markdown) {
  return `<div class="preview-md">${renderMd(markdown || '')}</div>`;
}

function _enhanceSkillMarkdown(root) {
  if (!root) return;
  requestAnimationFrame(() => {
    const mdRoot = root.querySelector('.preview-md') || root;
    if (typeof highlightCode === 'function') highlightCode(mdRoot);
    if (typeof renderKatexBlocks === 'function') renderKatexBlocks(mdRoot);
  });
}

function _renderSkillDetail(name, content, linkedFiles) {
  const title = $('skillDetailTitle');
  const body = $('skillDetailBody');
  const empty = $('skillDetailEmpty');
  const editBtn = $('btnEditSkillDetail');
  const delBtn = $('btnDeleteSkillDetail');
  if (title) title.textContent = name;
  const { frontmatter, body: markdownBody } = _stripYamlFrontmatter(content);
  let html = `<div id="skillSecuritySection" class="skill-security-section skill-security-loading">${esc(t('skill_security_scanning') || 'Scanning for risks…')}</div>`;
  if (frontmatter) {
    html += `<details class="skill-frontmatter"><summary>${esc(t('skill_metadata'))}</summary><pre><code>${esc(frontmatter)}</code></pre></details>`;
  }
  html += _skillMarkdownHtml(markdownBody || '(no content)');
  const lf = linkedFiles || {};
  const categories = Object.entries(lf).filter(([,files]) => files && files.length > 0);
  if (categories.length) {
    html += `<div class="skill-linked-files"><div style="font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px">${esc(t('linked_files'))}</div>`;
    for (const [cat, files] of categories) {
      html += `<div class="skill-linked-section"><h4>${esc(cat)}</h4>`;
      for (const f of files) {
        html += `<a class="skill-linked-file" href="#" data-skill-name="${esc(name)}" data-skill-file="${esc(f)}">${esc(f)}</a>`;
      }
      html += '</div>';
    }
    html += '</div>';
  }
  body.innerHTML = `<div class="main-view-content skill-detail-content">${html}</div>`;
  _enhanceSkillMarkdown(body);
  body.querySelectorAll('.skill-linked-file').forEach(a => {
    a.addEventListener('click', e => { e.preventDefault(); openSkillFile(a.dataset.skillName, a.dataset.skillFile); });
  });
  body.style.display = '';
  if (empty) empty.style.display = 'none';
  _skillMode = 'read';
  _setSkillHeaderButtons('read');
}

const _SKILL_SCAN_VERDICT_LABELS = {
  safe: () => t('skill_security_verdict_safe') || 'Safe',
  caution: () => t('skill_security_verdict_caution') || 'Caution',
  dangerous: () => t('skill_security_verdict_dangerous') || 'Dangerous',
};
const _SKILL_SCAN_TRUST_LABELS = {
  builtin: () => t('skill_security_trust_builtin') || 'Builtin',
  trusted: () => t('skill_security_trust_trusted') || 'Trusted source',
  community: () => t('skill_security_trust_community') || 'Community source',
  'agent-created': () => t('skill_security_trust_agent_created') || 'Agent-created',
};

async function _loadSkillScan(name) {
  const section = $('skillSecuritySection');
  if (!section) return;
  try {
    const scan = await api(`/api/skills/scan?name=${encodeURIComponent(name)}`);
    // Stale response guard: the user may have clicked a different skill
    // while this fetch was in flight (same idiom as _renderPersonaPickerPopup
    // checking display state before painting).
    if ($('skillSecuritySection') !== section || $('skillDetailTitle').textContent !== name) return;
    _renderSkillScan(scan);
  } catch (e) {
    if ($('skillSecuritySection') !== section) return;
    section.className = 'skill-security-section skill-security-unavailable';
    section.textContent = t('skill_security_unavailable') || 'Security scan unavailable.';
  }
}

function _renderSkillScan(scan) {
  const section = $('skillSecuritySection');
  if (!section || !scan) return;
  const verdict = scan.verdict || 'safe';
  const verdictLabel = (_SKILL_SCAN_VERDICT_LABELS[verdict] || _SKILL_SCAN_VERDICT_LABELS.safe)();
  const trustLabel = (_SKILL_SCAN_TRUST_LABELS[scan.trust_level] || _SKILL_SCAN_TRUST_LABELS.community)();
  const findings = Array.isArray(scan.findings) ? scan.findings : [];
  section.className = `skill-security-section skill-security-${esc(verdict)}`;
  let html = `<div class="skill-security-header">
    <span class="skill-security-badge skill-security-badge-${esc(verdict)}">${esc(verdictLabel)}</span>
    <span class="skill-security-trust">${esc(trustLabel)}</span>
  </div>`;
  if (findings.length) {
    html += '<div class="skill-security-findings">';
    for (const f of findings) {
      html += `<div class="skill-security-finding skill-security-finding-${esc(f.severity || 'low')}">
        <span class="skill-security-finding-severity">${esc(f.severity || '')}</span>
        <span class="skill-security-finding-desc">${esc(f.description || '')}</span>
        <span class="skill-security-finding-loc">${esc(f.file || '')}:${esc(f.line || '')}</span>
      </div>`;
    }
    html += '</div>';
  }
  section.innerHTML = html;
}

function _renderSkillError(name, message) {
  const title = $('skillDetailTitle');
  const body = $('skillDetailBody');
  const empty = $('skillDetailEmpty');
  if (title) title.textContent = name;
  if (body) {
    body.innerHTML = `<div class="main-view-content"><div class="detail-form-error" style="display:block">${esc(message || t('skill_load_failed'))}</div></div>`;
    body.style.display = '';
  }
  if (empty) empty.style.display = 'none';
  _currentSkillDetail = null;
  _skillMode = 'empty';
  _setSkillHeaderButtons('empty');
}

function _setSkillHeaderButtons(mode) {

  const header = $('mainSkills') && $('mainSkills').querySelector('.main-view-header');  const editBtn = $('btnEditSkillDetail');
  const delBtn = $('btnDeleteSkillDetail');
  const cancelBtn = $('btnCancelSkillDetail');
  const saveBtn = $('btnSaveSkillDetail');
  const show = b => b && (b.style.display = '');
  const hide = b => b && (b.style.display = 'none');
  if (mode === 'read') { if (header) header.style.display = 'flex';  show(editBtn); show(delBtn); hide(cancelBtn); hide(saveBtn); }
  else if (mode === 'create' || mode === 'edit') { if (header) header.style.display = 'flex'; hide(editBtn); hide(delBtn); show(cancelBtn); show(saveBtn); }
  else { if (header) header.style.display = 'none';  hide(editBtn); hide(delBtn); hide(cancelBtn); hide(saveBtn); }
}

async function openSkill(name, el) {
  // Highlight active skill in the sidebar list
  document.querySelectorAll('.skill-item').forEach(e => e.classList.remove('active'));
  if (el) el.classList.add('active');
  _skillPreFormDetail = null;
  _editingSkillName = null;
  try {
    const data = await api(`/api/skills/content?name=${encodeURIComponent(name)}`);
    if (data && (data.success === false || data.error)) {
      const message = data.error || t('skill_load_failed');
      _renderSkillError(name, message);
      setStatus(t('skill_load_failed') + message);
      return;
    }
    _currentSkillDetail = { name, content: data.content || '', linked_files: data.linked_files || {} };
    _renderSkillDetail(name, data.content || '', data.linked_files || {});
    _loadSkillScan(name);
    _closeMobileSidebarAfterPanelSelection();
  } catch(e) { setStatus(t('skill_load_failed') + e.message); }
}

async function openSkillFile(skillName, filePath) {
  try {
    const data = await api(`/api/skills/content?name=${encodeURIComponent(skillName)}&file=${encodeURIComponent(filePath)}`);
    if (data && data.error) {
      _renderSkillError(skillName, data.error);
      setStatus(t('skill_file_load_failed') + data.error);
      return;
    }
    const body = $('skillDetailBody');
    if (!body) return;
    const ext = (filePath.split('.').pop() || '').toLowerCase();
    const isMd = ['md','markdown'].includes(ext);
    const backLabel = t('skills_back_to').replace('{0}', skillName);
    const header = `<div class="skill-file-breadcrumb"><a href="#" class="skill-file-back" data-skill-name="${esc(skillName)}">&larr; ${esc(backLabel)}</a><span class="skill-file-path">${esc(filePath)}</span></div>`;
    let content;
    if (isMd) {
      content = `<div class="main-view-content">${_skillMarkdownHtml(data.content || '')}</div>`;
    } else {
      const escaped = esc(data.content || '');
      content = `<pre class="skill-file-code"><code>${escaped}</code></pre>`;
    }
    body.innerHTML = header + content;
    body.style.display = '';
    const empty = $('skillDetailEmpty');
    if (empty) empty.style.display = 'none';
    body.querySelectorAll('.skill-file-back').forEach(a => {
      a.addEventListener('click', e => {
        e.preventDefault();
        if (_currentSkillDetail && _currentSkillDetail.name === a.dataset.skillName) {
          _renderSkillDetail(_currentSkillDetail.name, _currentSkillDetail.content, _currentSkillDetail.linked_files);
          _loadSkillScan(_currentSkillDetail.name);
        } else {
          openSkill(a.dataset.skillName, null);
        }
      });
    });
    if (isMd) _enhanceSkillMarkdown(body);
    else requestAnimationFrame(() => { if (typeof highlightCode === 'function') highlightCode(); });
  } catch(e) { setStatus(t('skill_file_load_failed') + e.message); }
}

function editCurrentSkill() {
  if (!_currentSkillDetail) return;
  const s = _currentSkillDetail;
  let category = '';
  if (_skillsData) {
    const match = _skillsData.find(x => x.name === s.name);
    if (match) category = match.category || '';
  }
  _skillPreFormDetail = { name: s.name, content: s.content, linked_files: s.linked_files };
  _editingSkillName = s.name;
  _skillMode = 'edit';
  _renderSkillForm({ name: s.name, category, content: s.content || '', isEdit: true });
}

function openSkillCreate() {
  if (typeof switchPanel === 'function' && _currentPanel !== 'skills') switchPanel('skills');
  _skillPreFormDetail = _currentSkillDetail ? { ..._currentSkillDetail } : null;
  _editingSkillName = null;
  _skillMode = 'create';
  _renderSkillForm({ name: '', category: '', content: '', isEdit: false });
}

function _renderSkillForm({ name, category, content, isEdit }) {
  const title = $('skillDetailTitle');
  const body = $('skillDetailBody');
  const empty = $('skillDetailEmpty');
  if (!body || !title) return;
  title.textContent = isEdit ? t('skills_edit') + ' · ' + name : t('new_skill');
  const nameDisabled = isEdit ? 'disabled' : '';
  const nameHint = isEdit ? `<div class="detail-form-hint">${esc(t('skill_rename_not_supported') || 'Renaming a skill is not supported. Create a new skill and delete the old one to rename.')}</div>` : '';
  body.innerHTML = `
    <div class="main-view-content">
      <form class="detail-form" onsubmit="event.preventDefault(); saveSkillForm();">
        <div class="detail-form-row">
          <label for="skillFormName">${esc(t('skill_name') || 'Name')}</label>
          <input type="text" id="skillFormName" value="${esc(name || '')}" placeholder="my-skill" autocomplete="off" ${nameDisabled} required>
          ${nameHint}
        </div>
        <div class="detail-form-row">
          <label for="skillFormCategory">${esc(t('skill_category') || 'Category')}</label>
          <input type="text" id="skillFormCategory" value="${esc(category || '')}" placeholder="${esc(t('skill_category_placeholder') || 'Optional, e.g. devops')}" autocomplete="off">
        </div>
        <div class="detail-form-row">
          <label for="skillFormContent">${esc(t('skill_content') || 'SKILL.md content')}</label>
          <textarea id="skillFormContent" rows="18" placeholder="${esc(t('skill_content_placeholder') || 'YAML frontmatter + markdown body')}">${esc(content || '')}</textarea>
        </div>
        <div id="skillFormError" class="detail-form-error" style="display:none"></div>
      </form>
    </div>`;
  body.style.display = '';
  if (empty) empty.style.display = 'none';
  _setSkillHeaderButtons(isEdit ? 'edit' : 'create');
  const focusEl = isEdit ? $('skillFormCategory') : $('skillFormName');
  if (focusEl) focusEl.focus();
}

function cancelSkillForm() {
  _editingSkillName = null;
  if (_skillPreFormDetail) {
    const snap = _skillPreFormDetail;
    _skillPreFormDetail = null;
    _currentSkillDetail = snap;
    _renderSkillDetail(snap.name, snap.content || '', snap.linked_files || {});
    _loadSkillScan(snap.name);
    return;
  }
  // Revert to empty state
  _skillPreFormDetail = null;
  _currentSkillDetail = null;
  _skillMode = 'empty';
  const body = $('skillDetailBody');
  const empty = $('skillDetailEmpty');
  const title = $('skillDetailTitle');
  if (body) { body.innerHTML = ''; body.style.display = 'none'; }
  if (empty) empty.style.display = '';
  if (title) title.textContent = '';
  _setSkillHeaderButtons('empty');
}

async function saveSkillForm() {
  const nameInput = $('skillFormName');
  const catInput = $('skillFormCategory');
  const contentInput = $('skillFormContent');
  const errEl = $('skillFormError');
  if (!nameInput || !contentInput || !errEl) return;
  const name = (nameInput.value || '').trim().toLowerCase().replace(/\s+/g, '-');
  const category = (catInput ? (catInput.value || '').trim() : '');
  const content = contentInput.value;
  errEl.style.display = 'none';
  if (!name) { errEl.textContent = t('skill_name_required'); errEl.style.display = ''; return; }
  if (!content.trim()) { errEl.textContent = t('content_required'); errEl.style.display = ''; return; }
  try {
    await api('/api/skills/save', {method:'POST', body: JSON.stringify({name, category: category||undefined, content})});
    showToast(_editingSkillName ? t('skill_updated') : t('skill_created'));
    _skillsData = null;
    _cronSkillsCache = null;
    if(typeof window!=='undefined'&&typeof window.invalidateSlashSkillCaches==='function') window.invalidateSlashSkillCaches();
    _editingSkillName = null;
    _skillPreFormDetail = null;
    await loadSkills();
    // Reload the saved skill in read mode with fresh content
    const row = document.querySelector(`.skill-item .skill-name`);
    const match = document.querySelectorAll('.skill-item');
    let targetEl = null;
    match.forEach(el => {
      const nm = el.querySelector('.skill-name');
      if (nm && nm.textContent === name) targetEl = el;
    });
    await openSkill(name, targetEl);
  } catch(e) { errEl.textContent = t('error_prefix') + e.message; errEl.style.display = ''; }
}

// Back-compat aliases (delete flow + any old callers)
const submitSkillSave = saveSkillForm;
function toggleSkillForm(){ openSkillCreate(); }

async function deleteCurrentSkill() {
  if (!_currentSkillDetail) return;
  const name = _currentSkillDetail.name;
  const message = t('skill_delete_confirm')
    ? t('skill_delete_confirm').replace('{0}', name)
    : `Delete skill "${name}"?`;
  const ok = await showConfirmDialog({
    title: t('delete_title') || 'Delete',
    message,
    confirmLabel: t('delete_title') || 'Delete',
    danger: true,
    focusCancel: true,
  });
  if (!ok) return;
  try {
    await api('/api/skills/delete', { method:'POST', body: JSON.stringify({ name }) });
    _currentSkillDetail = null;
    _skillPreFormDetail = null;
    _skillsData = null;
    _cronSkillsCache = null;
    if(typeof window!=='undefined'&&typeof window.invalidateSlashSkillCaches==='function') window.invalidateSlashSkillCaches();
    _skillMode = 'empty';
    const body = $('skillDetailBody');
    const empty = $('skillDetailEmpty');
    const title = $('skillDetailTitle');
    if (body) { body.innerHTML = ''; body.style.display = 'none'; }
    if (empty) empty.style.display = '';
    if (title) title.textContent = '';
    _setSkillHeaderButtons('empty');
    await loadSkills();
    showToast(t('skill_deleted') || 'Skill deleted');
  } catch(e) { setStatus(t('error_prefix') + e.message); }
}

// ── Personas panel (internal name: agent definitions / Agent Library) ──
// Mirrors the Skills panel above: sidebar list (#agentsList) + detail/form
// pane rendered into #mainAgents. See docs/HERMES_STUDIO_PARITY_PLAN.md,
// "Priority 1 -- Personas".

async function loadAgentDefinitions() {
  if (_agentDefsData) { renderAgentDefinitions(_agentDefsData); return; }
  const box = $('agentsList');
  try {
    const data = await api('/api/agent-definitions');
    _agentDefsData = data.definitions || [];
    renderAgentDefinitions(_agentDefsData);
  } catch(e) { if (box) box.innerHTML = `<div style="padding:12px;color:var(--accent);font-size:12px">${esc(t('error_prefix'))}${esc(e.message)}</div>`; }
}

function renderAgentDefinitions(definitions) {
  const searchEl = $('agentsSearch');
  const query = ((searchEl && searchEl.value) || '').toLowerCase();
  const filtered = query ? definitions.filter(d =>
    (d.name||'').toLowerCase().includes(query) ||
    (d.role||'').toLowerCase().includes(query) ||
    (d.tags||[]).some(tag => (tag||'').toLowerCase().includes(query))
  ) : definitions;
  const box = $('agentsList');
  if (!box) return;
  box.innerHTML = '';
  if (!filtered.length) { box.innerHTML = `<div style="padding:12px;color:var(--muted);font-size:12px">${esc(t('agent_def_no_match'))}</div>`; return; }
  for (const def of filtered) {
    const el = document.createElement('div');
    el.className = 'skill-item';
    el.dataset.agentDefId = def.id;
    const dot = `<span style="width:8px;height:8px;border-radius:50%;background:${esc(def.color || 'var(--muted)')};display:inline-block;flex-shrink:0;margin-top:5px" aria-hidden="true"></span>`;
    const emoji = def.emoji ? `${esc(def.emoji)} ` : '';
    el.innerHTML = `${dot}<span class="skill-name">${emoji}${esc(def.name)}</span><span class="skill-desc">${esc(def.role || '')}</span>`;
    if (def.builtin) el.title = t('agent_def_builtin_hint');
    if (_currentAgentDefDetail && _currentAgentDefDetail.id === def.id) el.classList.add('active');
    el.onclick = () => openAgentDefDetail(def.id, el);
    box.appendChild(el);
  }
}

function filterAgentDefinitions() {
  if (_agentDefsData) renderAgentDefinitions(_agentDefsData);
}

function _setAgentDefHeaderButtons(mode, def) {
  const header = $('mainAgents') && $('mainAgents').querySelector('.main-view-header');
  const applyBtn = $('btnApplyAgentDefDetail');
  const clearBtn = $('btnClearAgentDefDetail');
  const editBtn = $('btnEditAgentDefDetail');
  const dupBtn = $('btnDuplicateAgentDefDetail');
  const delBtn = $('btnDeleteAgentDefDetail');
  const cancelBtn = $('btnCancelAgentDefDetail');
  const saveBtn = $('btnSaveAgentDefDetail');
  const show = b => b && (b.style.display = '');
  const hide = b => b && (b.style.display = 'none');
  if (mode === 'read') {
    if (header) header.style.display = 'flex';
    const isApplied = !!(def && S.session && S.session.agent_definition_id === def.id);
    if (isApplied) { hide(applyBtn); show(clearBtn); } else { show(applyBtn); hide(clearBtn); }
    show(dupBtn);
    if (def && def.builtin) { hide(editBtn); hide(delBtn); }
    else { show(editBtn); show(delBtn); }
    hide(cancelBtn); hide(saveBtn);
  } else if (mode === 'create' || mode === 'edit') {
    if (header) header.style.display = 'flex';
    hide(applyBtn); hide(clearBtn); hide(editBtn); hide(dupBtn); hide(delBtn); show(cancelBtn); show(saveBtn);
  } else {
    if (header) header.style.display = 'none';
    hide(applyBtn); hide(clearBtn); hide(editBtn); hide(dupBtn); hide(delBtn); hide(cancelBtn); hide(saveBtn);
  }
}

function _renderAgentDefDetail(def) {
  _currentAgentDefDetail = def;
  const title = $('agentDefDetailTitle');
  const body = $('agentDefDetailBody');
  const empty = $('agentDefDetailEmpty');
  if (!title || !body) return;
  title.textContent = (def.emoji ? def.emoji + ' ' : '') + def.name;
  const rows = [];
  if (S.session && S.session.agent_definition_id === def.id) rows.push(`<div class="detail-row"><div class="detail-row-label">${esc(t('agent_def_status'))}</div><div class="detail-row-value"><span class="detail-badge">${esc(t('agent_def_applied_badge'))}</span></div></div>`);
  if (def.builtin) rows.push(`<div class="detail-row"><div class="detail-row-label">${esc(t('agent_def_type'))}</div><div class="detail-row-value"><span class="detail-badge">${esc(t('agent_def_builtin_badge'))}</span></div></div>`);
  if (def.role) rows.push(`<div class="detail-row"><div class="detail-row-label">${esc(t('agent_def_role'))}</div><div class="detail-row-value">${esc(def.role)}</div></div>`);
  if (def.tags && def.tags.length) rows.push(`<div class="detail-row"><div class="detail-row-label">${esc(t('agent_def_tags'))}</div><div class="detail-row-value">${def.tags.map(tag => esc(tag)).join(', ')}</div></div>`);
  const promptValue = def.system_prompt
    ? `<pre class="skill-file-code" style="white-space:pre-wrap">${esc(def.system_prompt)}</pre>`
    : `<span style="color:var(--muted)">${esc(t('agent_def_no_system_prompt'))}</span>`;
  rows.push(`<div class="detail-row"><div class="detail-row-label">${esc(t('agent_def_system_prompt'))}</div><div class="detail-row-value">${promptValue}</div></div>`);
  body.innerHTML = `
    <div class="main-view-content">
      <div class="detail-card">
        <div class="detail-card-title">${esc(t('tab_agents'))}</div>
        ${rows.join('')}
      </div>
    </div>`;
  body.style.display = '';
  if (empty) empty.style.display = 'none';
  _agentDefMode = 'read';
  _setAgentDefHeaderButtons('read', def);
}

async function openAgentDefDetail(id, el) {
  document.querySelectorAll('#agentsList .skill-item').forEach(e => e.classList.remove('active'));
  if (el) el.classList.add('active');
  _agentDefPreFormDetail = null;
  _editingAgentDefId = null;
  const def = (_agentDefsData || []).find(d => d.id === id);
  if (!def) return;
  _renderAgentDefDetail(def);
  if (typeof _closeMobileSidebarAfterPanelSelection === 'function') _closeMobileSidebarAfterPanelSelection();
}

function editCurrentAgentDef() {
  if (!_currentAgentDefDetail || _currentAgentDefDetail.builtin) return;
  _agentDefPreFormDetail = _currentAgentDefDetail;
  _editingAgentDefId = _currentAgentDefDetail.id;
  _agentDefMode = 'edit';
  _renderAgentDefForm(_currentAgentDefDetail);
}

function openAgentDefCreate() {
  if (typeof switchPanel === 'function' && _currentPanel !== 'agents') switchPanel('agents');
  _agentDefPreFormDetail = _currentAgentDefDetail;
  _editingAgentDefId = null;
  _agentDefMode = 'create';
  _renderAgentDefForm({ name: '', emoji: '', color: '', role: '', tags: [], system_prompt: '' });
}

function _renderAgentDefForm(def) {
  const title = $('agentDefDetailTitle');
  const body = $('agentDefDetailBody');
  const empty = $('agentDefDetailEmpty');
  if (!body || !title) return;
  const isEdit = !!_editingAgentDefId;
  title.textContent = isEdit ? t('edit') + ' · ' + def.name : t('new_agent_def');
  body.innerHTML = `
    <div class="main-view-content">
      <form class="detail-form" onsubmit="event.preventDefault(); saveAgentDefForm();">
        <div class="detail-form-row">
          <label for="agentDefFormName">${esc(t('agent_def_name'))}</label>
          <input type="text" id="agentDefFormName" value="${esc(def.name || '')}" placeholder="${esc(t('agent_def_name_placeholder'))}" autocomplete="off" maxlength="128" required>
        </div>
        <div class="detail-form-row">
          <label for="agentDefFormEmoji">${esc(t('agent_def_emoji'))}</label>
          <input type="text" id="agentDefFormEmoji" value="${esc(def.emoji || '')}" placeholder="🤖" autocomplete="off" maxlength="8">
        </div>
        <div class="detail-form-row">
          <label for="agentDefFormColor">${esc(t('agent_def_color'))}</label>
          <input type="text" id="agentDefFormColor" value="${esc(def.color || '')}" placeholder="#7cb9ff" autocomplete="off">
          <div class="detail-form-hint">${esc(t('agent_def_color_hint'))}</div>
        </div>
        <div class="detail-form-row">
          <label for="agentDefFormRole">${esc(t('agent_def_role'))}</label>
          <input type="text" id="agentDefFormRole" value="${esc(def.role || '')}" placeholder="${esc(t('agent_def_role_placeholder'))}" autocomplete="off" maxlength="256">
        </div>
        <div class="detail-form-row">
          <label for="agentDefFormTags">${esc(t('agent_def_tags'))}</label>
          <input type="text" id="agentDefFormTags" value="${esc((def.tags || []).join(', '))}" placeholder="${esc(t('agent_def_tags_placeholder'))}" autocomplete="off">
        </div>
        <div class="detail-form-row">
          <label for="agentDefFormPrompt">${esc(t('agent_def_system_prompt'))}</label>
          <textarea id="agentDefFormPrompt" rows="14" placeholder="${esc(t('agent_def_system_prompt_placeholder'))}" maxlength="8000">${esc(def.system_prompt || '')}</textarea>
        </div>
        <div id="agentDefFormError" class="detail-form-error" style="display:none"></div>
      </form>
    </div>`;
  body.style.display = '';
  if (empty) empty.style.display = 'none';
  _setAgentDefHeaderButtons(isEdit ? 'edit' : 'create');
  const focusEl = $('agentDefFormName');
  if (focusEl) focusEl.focus();
}

function cancelAgentDefForm() {
  _editingAgentDefId = null;
  if (_agentDefPreFormDetail) {
    const snap = _agentDefPreFormDetail;
    _agentDefPreFormDetail = null;
    _renderAgentDefDetail(snap);
    return;
  }
  _agentDefPreFormDetail = null;
  _currentAgentDefDetail = null;
  _agentDefMode = 'empty';
  const body = $('agentDefDetailBody');
  const empty = $('agentDefDetailEmpty');
  const title = $('agentDefDetailTitle');
  if (body) { body.innerHTML = ''; body.style.display = 'none'; }
  if (empty) empty.style.display = '';
  if (title) title.textContent = '';
  _setAgentDefHeaderButtons('empty');
}

async function saveAgentDefForm() {
  const nameInput = $('agentDefFormName');
  const emojiInput = $('agentDefFormEmoji');
  const colorInput = $('agentDefFormColor');
  const roleInput = $('agentDefFormRole');
  const tagsInput = $('agentDefFormTags');
  const promptInput = $('agentDefFormPrompt');
  const errEl = $('agentDefFormError');
  if (!nameInput || !errEl) return;
  const name = (nameInput.value || '').trim();
  errEl.style.display = 'none';
  if (!name) { errEl.textContent = t('agent_def_name_required'); errEl.style.display = ''; return; }
  const tags = (tagsInput.value || '').split(',').map(s => s.trim()).filter(Boolean);
  const payload = {
    name,
    emoji: (emojiInput.value || '').trim(),
    color: (colorInput.value || '').trim() || undefined,
    role: (roleInput.value || '').trim(),
    tags,
    system_prompt: promptInput.value || '',
  };
  try {
    let result;
    if (_editingAgentDefId) {
      result = await api('/api/agent-definitions/update', { method:'POST', body: JSON.stringify({ id: _editingAgentDefId, ...payload }) });
    } else {
      result = await api('/api/agent-definitions/create', { method:'POST', body: JSON.stringify(payload) });
    }
    showToast(_editingAgentDefId ? t('agent_def_updated') : t('agent_def_created'));
    _agentDefsData = null;
    _editingAgentDefId = null;
    _agentDefPreFormDetail = null;
    await loadAgentDefinitions();
    const saved = result.definition;
    const targetEl = document.querySelector(`#agentsList [data-agent-def-id="${saved.id}"]`);
    await openAgentDefDetail(saved.id, targetEl);
  } catch(e) { errEl.textContent = t('error_prefix') + e.message; errEl.style.display = ''; }
}

async function duplicateAgentDef() {
  if (!_currentAgentDefDetail) return;
  try {
    const result = await api('/api/agent-definitions/duplicate', { method:'POST', body: JSON.stringify({ id: _currentAgentDefDetail.id }) });
    showToast(t('agent_def_duplicated'));
    _agentDefsData = null;
    await loadAgentDefinitions();
    const saved = result.definition;
    const targetEl = document.querySelector(`#agentsList [data-agent-def-id="${saved.id}"]`);
    await openAgentDefDetail(saved.id, targetEl);
  } catch(e) { setStatus(t('error_prefix') + e.message); }
}

async function applyAgentDefToSession() {
  if (!_currentAgentDefDetail) return;
  if (!S.session) { showToast(t('no_active_session')); return; }
  try {
    await api('/api/agent-definitions/apply', { method:'POST', body: JSON.stringify({ session_id: S.session.session_id, id: _currentAgentDefDetail.id }) });
    S.session.agent_definition_id = _currentAgentDefDetail.id;
    _renderAgentDefDetail(_currentAgentDefDetail);
    _refreshAppliedPersonaUI();
    const msg = t('agent_def_applied') ? t('agent_def_applied').replace('{0}', _currentAgentDefDetail.name) : `Applied "${_currentAgentDefDetail.name}" to session`;
    showToast(msg);
  } catch(e) { setStatus(t('error_prefix') + e.message); }
}

async function clearAppliedAgentDef() {
  if (!S.session) { showToast(t('no_active_session')); return; }
  try {
    await api('/api/agent-definitions/apply', { method:'POST', body: JSON.stringify({ session_id: S.session.session_id, id: '' }) });
    S.session.agent_definition_id = null;
    if (_currentAgentDefDetail) _renderAgentDefDetail(_currentAgentDefDetail);
    _refreshAppliedPersonaUI();
    showToast(t('agent_def_cleared') || 'Persona cleared from session');
  } catch(e) { setStatus(t('error_prefix') + e.message); }
}

// Keep every persona-applied affordance (the Personas panel's Apply/Clear
// header buttons + badge, and the composer picker button/popup below) in
// sync with whichever session is now active. Neither re-renders on its own
// when the active chat changes, so this is called at every `S.session = ...`
// settle point alongside _hydrateTodosFromSession (see ui.js's note on that
// function) rather than only from the Personas panel's own apply/clear flow.
function _refreshAppliedPersonaUI() {
  if (_currentAgentDefDetail && _agentDefMode === 'read') _renderAgentDefDetail(_currentAgentDefDetail);
  const btn = $('btnPersonaPicker');
  if (btn) btn.classList.toggle('active', !!(S.session && S.session.agent_definition_id));
  const popup = $('personaPickerPopup');
  if (popup && popup.style.display !== 'none' && _agentDefsData) _renderPersonaPickerPopup(_agentDefsData);
}

// ── Composer persona picker popup (quick apply/clear without leaving the chat) ──

// position:fixed + viewport-clamped placement — same idiom as
// _positionProfileDropdown(), needed because the popup can otherwise render
// off-screen or get clipped by the composer-left's overflow-x:auto on narrow
// viewports (the bug behind the mobile "doesn't open" report). Always opens
// above its trigger — the persona button only ever lives in the composer
// footer, unlike the profile chip which also has a titlebar trigger.
function _positionPersonaPickerPopup() {
  const popup = $('personaPickerPopup');
  const trigger = $('btnPersonaPicker');
  if (!popup || !trigger) return;
  const rect = trigger.getBoundingClientRect();
  const gap = 8;
  const popupW = popup.offsetWidth || 240;
  let left = rect.left + (rect.width / 2) - (popupW / 2);
  left = Math.max(8, Math.min(left, window.innerWidth - popupW - 8));
  popup.style.left = left + 'px';
  popup.style.top = '';
  popup.style.bottom = (window.innerHeight - rect.top + gap) + 'px';
}

window.addEventListener('resize', () => {
  const popup = $('personaPickerPopup');
  if (popup && popup.style.display !== 'none') _positionPersonaPickerPopup();
});

async function togglePersonaPickerPopup() {
  const popup = $('personaPickerPopup');
  const btn = $('btnPersonaPicker');
  if (!popup) return;
  if (popup.style.display !== 'none') {
    popup.style.display = 'none';
    if (btn) btn.setAttribute('aria-expanded', 'false');
    return;
  }
  popup.innerHTML = `<div class="persona-picker-loading">${esc(t('loading') || 'Loading…')}</div>`;
  popup.style.display = 'flex';
  _positionPersonaPickerPopup();
  if (btn) btn.setAttribute('aria-expanded', 'true');
  if (!_agentDefsData) {
    try {
      const data = await api('/api/agent-definitions');
      _agentDefsData = data.definitions || [];
    } catch(e) { _agentDefsData = []; }
  }
  _renderPersonaPickerPopup(_agentDefsData);
}

function _renderPersonaPickerPopup(definitions) {
  const popup = $('personaPickerPopup');
  if (!popup || popup.style.display === 'none') return;
  popup.innerHTML = '';
  const activeId = S.session && S.session.agent_definition_id;
  if (!definitions.length) {
    const empty = document.createElement('div');
    empty.className = 'persona-picker-empty';
    empty.textContent = t('agent_def_no_match') || 'No personas yet.';
    popup.appendChild(empty);
    return;
  }
  for (const def of definitions) {
    const isActive = activeId === def.id;
    const row = document.createElement('div');
    row.className = 'persona-picker-row' + (isActive ? ' active' : '');
    row.dataset.personaId = def.id;
    row.setAttribute('role', 'menuitemradio');
    row.setAttribute('aria-checked', isActive ? 'true' : 'false');
    const dot = document.createElement('span');
    dot.className = 'persona-picker-dot';
    dot.style.background = def.color || 'var(--muted)';
    dot.setAttribute('aria-hidden', 'true');
    const label = document.createElement('span');
    label.className = 'persona-picker-label';
    label.textContent = (def.emoji ? def.emoji + ' ' : '') + def.name;
    if (def.role) label.title = def.role;
    row.appendChild(dot);
    row.appendChild(label);
    if (isActive) {
      const check = document.createElement('span');
      check.className = 'persona-picker-check';
      check.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
      check.setAttribute('aria-hidden', 'true');
      row.appendChild(check);
    }
    row.onclick = () => _applyPersonaFromPicker(def, isActive);
    popup.appendChild(row);
  }
}

async function _applyPersonaFromPicker(def, alreadyApplied) {
  const popup = $('personaPickerPopup');
  const btn = $('btnPersonaPicker');
  if (!S.session) { showToast(t('no_active_session')); return; }
  try {
    const nextId = alreadyApplied ? '' : def.id;
    await api('/api/agent-definitions/apply', { method:'POST', body: JSON.stringify({ session_id: S.session.session_id, id: nextId }) });
    S.session.agent_definition_id = nextId || null;
    _refreshAppliedPersonaUI();
    const msg = alreadyApplied
      ? (t('agent_def_cleared') || 'Persona cleared from session')
      : ((t('agent_def_applied') && t('agent_def_applied').replace('{0}', def.name)) || `Applied "${def.name}" to session`);
    showToast(msg);
  } catch(e) { showToast(t('error_prefix') + e.message, 2000, 'error'); }
  if (popup) popup.style.display = 'none';
  if (btn) btn.setAttribute('aria-expanded', 'false');
}

document.addEventListener('click', (e) => {
  const popup = $('personaPickerPopup');
  const btn = $('btnPersonaPicker');
  if (!popup || popup.style.display === 'none') return;
  if (!popup.contains(e.target) && e.target !== btn && !(btn && btn.contains(e.target))) {
    popup.style.display = 'none';
    if (btn) btn.setAttribute('aria-expanded', 'false');
  }
}, {capture:false});

async function deleteAgentDef() {
  if (!_currentAgentDefDetail || _currentAgentDefDetail.builtin) return;
  const name = _currentAgentDefDetail.name;
  const message = t('agent_def_delete_confirm') ? t('agent_def_delete_confirm').replace('{0}', name) : `Delete persona "${name}"?`;
  const ok = await showConfirmDialog({
    title: t('delete_title') || 'Delete',
    message,
    confirmLabel: t('delete_title') || 'Delete',
    danger: true,
    focusCancel: true,
  });
  if (!ok) return;
  try {
    await api('/api/agent-definitions/delete', { method:'POST', body: JSON.stringify({ id: _currentAgentDefDetail.id }) });
    _currentAgentDefDetail = null;
    _agentDefPreFormDetail = null;
    _agentDefsData = null;
    _agentDefMode = 'empty';
    const body = $('agentDefDetailBody');
    const empty = $('agentDefDetailEmpty');
    const title = $('agentDefDetailTitle');
    if (body) { body.innerHTML = ''; body.style.display = 'none'; }
    if (empty) empty.style.display = '';
    if (title) title.textContent = '';
    _setAgentDefHeaderButtons('empty');
    await loadAgentDefinitions();
    showToast(t('agent_def_deleted'));
  } catch(e) { setStatus(t('error_prefix') + e.message); }
}

// ── Memory (main view) ──
let _memoryData = null;
let _notesSourcesData = null;
let _notesSearchResults = [];
let _notesSelectedSource = 'joplin';
let _notesPreviewNote = null;
let _notesSearchError = '';
let _notesSearchLoading = false;
let _currentMemorySection = null; // 'memory' | 'user' | 'soul' | 'project_context' | 'external_notes'
let _memoryMode = 'empty'; // 'empty' | 'read' | 'edit'

const MEMORY_SECTIONS = [
  { key: 'memory', labelKey: 'my_notes', emptyKey: 'no_notes_yet', iconKey: 'brain' },
  { key: 'user',   labelKey: 'user_profile', emptyKey: 'no_profile_yet', iconKey: 'user' },
  { key: 'soul',   labelKey: 'agent_soul', emptyKey: 'no_soul_yet', iconKey: 'sparkles' },
  { key: 'project_context', label: 'Project Context', empty: 'No project context file found for this workspace.', iconKey: 'file-text', readOnly: true },
  { key: 'external_notes', labelKey: 'external_notes_sources', emptyKey: 'external_notes_empty', iconKey: 'book-open' },
];

function _memorySectionMeta(key) {
  return MEMORY_SECTIONS.find(s => s.key === key) || MEMORY_SECTIONS[0];
}

function _memorySectionLabel(meta) {
  if (meta.label) return meta.label;
  return t(meta.labelKey);
}

function _memorySectionEmpty(meta) {
  if (meta.empty) return meta.empty;
  return t(meta.emptyKey);
}

function _memorySectionContent(key) {
  if (!_memoryData) return '';
  if (key === 'user') return _memoryData.user || '';
  if (key === 'soul') return _memoryData.soul || '';
  if (key === 'project_context') return _memoryData.project_context || '';
  return _memoryData.memory || '';
}

function _memorySectionMtime(key) {
  if (!_memoryData) return 0;
  if (key === 'user') return _memoryData.user_mtime || 0;
  if (key === 'soul') return _memoryData.soul_mtime || 0;
  if (key === 'project_context') return _memoryData.project_context_mtime || 0;
  return _memoryData.memory_mtime || 0;
}

function _memorySectionPath(key) {
  if (!_memoryData) return '';
  if (key === 'user') return _memoryData.user_path || '';
  if (key === 'soul') return _memoryData.soul_path || '';
  if (key === 'project_context') return _memoryData.project_context_path || '';
  if (key === 'memory') return _memoryData.memory_path || '';
  return '';
}

function _setMemoryHeaderButtons(mode) {
  const header = $('mainMemory') && $('mainMemory').querySelector('.main-view-header');
  const show = b => b && (b.style.display = '');
  const hide = b => b && (b.style.display = 'none');
  const editBtn = $('btnEditMemoryDetail');
  const cancelBtn = $('btnCancelMemoryDetail');
  const saveBtn = $('btnSaveMemoryDetail');
  const meta = _memorySectionMeta(_currentMemorySection);
  if (mode === 'read') {
    // Any read view has a populated title → header must be visible. Only the
    // Edit affordance is gated on the section being editable (read-only
    // sections like Project Context / External Notes still show the header).
    if (header) header.style.display = 'flex';
    if (_currentMemorySection !== 'external_notes' && !meta.readOnly) show(editBtn); else hide(editBtn);
    hide(cancelBtn); hide(saveBtn);
  }
  else if (mode === 'edit') { if (header) header.style.display = 'flex'; hide(editBtn); show(cancelBtn); show(saveBtn); }
  else { if (header) header.style.display = 'none'; hide(editBtn); hide(cancelBtn); hide(saveBtn); }
}

function _renderExternalNotesSources() {
  const title = $('memoryDetailTitle');
  const body = $('memoryDetailBody');
  const empty = $('memoryDetailEmpty');
  if (!title || !body) return;
  title.textContent = t('external_notes_sources');
  const data = _notesSourcesData || {};
  const sources = Array.isArray(data.sources) ? data.sources : [];
  const recall = data.automatic_recall_unchanged !== false
    ? `<div class="memory-detail-mtime">${esc(t('external_notes_auto_recall_hint'))}</div>`
    : '';
  if (!sources.length) {
    body.innerHTML = `<div class="main-view-content">${recall}<div class="memory-empty">${esc(t('external_notes_empty'))}</div></div>`;
  } else {
    const selected = sources.find(src => (src.name || '').toLowerCase() === (_notesSelectedSource || '').toLowerCase()) || sources[0];
    _notesSelectedSource = (selected && selected.name) || 'joplin';
    const sourceOptions = sources.map(src => `<option value="${esc(src.name||'')}" ${src.name===_notesSelectedSource?'selected':''}>${esc(src.label||src.name||'')}</option>`).join('');
    const recentAiNotes = Array.isArray(data.recent_ai_notes) ? data.recent_ai_notes : [];
    const recentAiHtml = recentAiNotes.length
      ? `<section class="notes-source-card notes-ai-recent-card">
          <div class="notes-source-card-head notes-ai-recent-head"><strong>${li('bot', 14)}${esc(t('external_notes_recent_ai'))}</strong><span class="detail-badge">${esc(t('external_notes_auto'))}</span></div>
          <div class="notes-ai-recent-list">${recentAiNotes.map(note => {
            const updated = note.updated_time ? new Date(Number(note.updated_time)).toLocaleString() : '';
            return `<button type="button" class="notes-result-card notes-ai-recent-item" onclick="previewExternalNote('${esc(note.source||'joplin')}','${esc(note.id||'')}')"><strong>${esc(note.title||note.label||'Untitled')}</strong><span>${li('clock', 14)}${esc(note.label||t('external_notes_recent_ai_reason'))}${updated ? ` · ${esc(updated)}` : ''}</span></button>`;
          }).join('')}</div>
        </section>`
      : '';
    const searchError = _notesSearchError ? `<div class="detail-form-error">${esc(_notesSearchError)}</div>` : '';
    const resultHtml = _notesSearchResults.length
      ? `<div class="notes-search-results">${_notesSearchResults.map(note => `<button type="button" class="notes-result-card" onclick="previewExternalNote('${esc(note.source||_notesSelectedSource)}','${esc(note.id||'')}')"><strong>${esc(note.title||'Untitled')}</strong>${note.snippet?`<span>${esc(note.snippet)}</span>`:''}</button>`).join('')}</div>`
      : `<div class="memory-empty">${esc(t('external_notes_search_empty'))}</div>`;
    const previewHtml = _notesPreviewNote
      ? `<section class="notes-source-card notes-preview-card"><div class="notes-source-card-head"><strong>${esc(_notesPreviewNote.title||'Untitled')}</strong><span class="detail-badge">${esc(_notesPreviewNote.source||_notesSelectedSource)}</span></div><div class="memory-content preview-md">${renderMd(_notesPreviewNote.body||'')}</div></section>`
      : '';
    const cards = sources.map(src => {
      const status = src.active ? t('source_active') : (src.status || t('source_configured'));
      const tools = Array.isArray(src.tools) ? src.tools : [];
      const hintHtml = src.tool_source === 'configured_hint'
        ? `<div class="memory-detail-mtime">${esc(t('external_notes_configured_hint'))}</div>`
        : '';
      const toolHtml = tools.length
        ? `<ul class="notes-source-tools">${tools.map(tool => `<li><strong>${esc(tool.name||'')}</strong>${tool.description?` — ${esc(tool.description)}`:''}</li>`).join('')}</ul>`
        : `<div class="memory-empty">${esc(t('external_notes_no_tools'))}</div>`;
      return `<section class="notes-source-card">
        <div class="notes-source-card-head"><strong>${esc(src.label||src.name||'')}</strong><span class="detail-badge ${src.active?'active':''}">${esc(status)}</span></div>
        <div class="memory-detail-mtime">${esc(t('external_notes_tool_count', src.tool_count||0))}</div>
        ${hintHtml}
        ${toolHtml}
      </section>`;
    }).join('');
    const searchUi = `<section class="notes-source-card notes-search-card">
      <form class="notes-search-form" onsubmit="event.preventDefault(); searchExternalNotes();">
        <select id="externalNotesSource" onchange="selectExternalNotesSource(this.value)">${sourceOptions}</select>
        <input id="externalNotesQuery" type="search" placeholder="${esc(t('external_notes_search_placeholder'))}" />
        <button type="submit" class="btn-secondary">${esc(_notesSearchLoading ? t('loading') : t('search'))}</button>
      </form>
      ${searchError}
      ${resultHtml}
    </section>`;
    body.innerHTML = `<div class="main-view-content">${recall}${recentAiHtml}${searchUi}${previewHtml}${cards}</div>`;
  }
  body.style.display = '';
  if (empty) empty.style.display = 'none';
  _memoryMode = 'read';
  _setMemoryHeaderButtons('read');
}

function _renderMemoryDetail(section) {
  if (section === 'external_notes') {
    _renderExternalNotesSources();
    return;
  }
  if (section === 'memory') {
    _renderMemoryEntriesView();
    return;
  }

  const meta = _memorySectionMeta(section);
  const title = $('memoryDetailTitle');
  const body = $('memoryDetailBody');
  const empty = $('memoryDetailEmpty');
  if (!title || !body) return;
  title.textContent = _memorySectionLabel(meta);
  const content = _memorySectionContent(section);
  const mtime = _memorySectionMtime(section);
  const mtimeStr = mtime ? new Date(mtime * 1000).toLocaleString() : '';
  const mtimeHtml = mtimeStr ? `<div class="memory-detail-mtime">${esc(mtimeStr)}</div>` : '';
  const path = _memorySectionPath(section);
  const fileName = section === 'project_context' && _memoryData
    ? (_memoryData.project_context_name || (path.split(/[\\/]/).pop() || ''))
    : (path.split(/[\\/]/).pop() || '');
  const pathHtml = path ? `<div class="memory-detail-mtime">${esc(fileName)} · ${esc(path)}</div>` : '';
  const shadowed = section === 'project_context' && _memoryData && Array.isArray(_memoryData.project_context_shadowed)
    ? _memoryData.project_context_shadowed
    : [];
  const shadowedHtml = shadowed.length
    ? `<div class="memory-detail-mtime">${esc(shadowed.map(item => `${item.name || 'Context file'} present, shadowed by ${item.shadowed_by || fileName || 'active context'}`).join('; '))}</div>`
    : '';
  const inner = content
    ? `<div class="memory-content preview-md">${renderMd(content)}</div>`
    : `<div class="memory-empty">${esc(_memorySectionEmpty(meta))}</div>`;
  body.innerHTML = `<div class="main-view-content">${pathHtml}${mtimeHtml}${shadowedHtml}${inner}</div>`;
  body.style.display = '';
  if (empty) empty.style.display = 'none';
  _memoryMode = 'read';
  _setMemoryHeaderButtons('read');
}

// ── My Notes as structured entries (Patterns/Corrections) ──────────────────
// MEMORY.md is a flat `§`-delimited list of freeform entries (confirmed
// against real profile data, not assumed). This view parses it into cards
// with per-entry delete and an append form, instead of the single raw
// textarea every other section still uses. Deliberately scoped to the
// 'memory' section only — 'user'/'soul'/'project_context' are not confirmed
// to use this format.
//
// IMPORTANT: this view is built from `_memoryData.memory`, which is the
// REDACTED text GET /api/memory returns for display (see _redact_text in
// api/helpers.py — real profiles routinely have plaintext secrets in
// MEMORY.md, e.g. dashboard passwords). Never reconstruct full file content
// from this display text and send it back for a write — that would
// permanently replace a real secret with "[REDACTED]" on disk. Delete uses
// an index against the server's own raw-file parse; append sends only fresh
// user-typed text. Neither path round-trips this redacted string.
let _currentMemoryEntryTab = 'patterns'; // 'patterns' | 'corrections'

function _parseMemoryEntriesForDisplay(content) {
  const raw = String(content || '');
  if (!raw.trim()) return [];
  return raw.split(/\n§\n/).map(s => s.trim()).filter(Boolean).map((text, index) => ({
    index,
    text,
    isCorrection: /^CORRECTION:/i.test(text),
  }));
}

function _renderMemoryEntriesView() {
  const meta = _memorySectionMeta('memory');
  const title = $('memoryDetailTitle');
  const body = $('memoryDetailBody');
  const empty = $('memoryDetailEmpty');
  if (!title || !body) return;
  title.textContent = _memorySectionLabel(meta);
  const content = _memorySectionContent('memory');
  const mtime = _memorySectionMtime('memory');
  const mtimeStr = mtime ? new Date(mtime * 1000).toLocaleString() : '';
  const mtimeHtml = mtimeStr ? `<div class="memory-detail-mtime">${esc(mtimeStr)}</div>` : '';
  const path = _memorySectionPath('memory');
  const pathHtml = path ? `<div class="memory-detail-mtime">${esc(path.split(/[\\/]/).pop() || '')} · ${esc(path)}</div>` : '';

  const entries = _parseMemoryEntriesForDisplay(content);
  const patterns = entries.filter(e => !e.isCorrection);
  const corrections = entries.filter(e => e.isCorrection);
  // No auto-revert-to-patterns when corrections is empty: the empty state
  // below ("No corrections yet.") already handles that gracefully, and an
  // auto-revert here would fire on every render — including the one caused
  // by the user's own explicit tab click — silently undoing the switch and
  // making the Corrections tab unreachable whenever it's empty (which is
  // the common case; real data has zero CORRECTION-prefixed entries today).
  const activeEntries = _currentMemoryEntryTab === 'corrections' ? corrections : patterns;

  const tabsHtml = `<div class="memory-entry-tabs" role="tablist">
    <button type="button" class="memory-entry-tab${_currentMemoryEntryTab==='patterns'?' active':''}" role="tab" aria-selected="${_currentMemoryEntryTab==='patterns'}" onclick="switchMemoryEntryTab('patterns')">${esc(t('memory_entries_patterns')||'Patterns')} <span class="memory-entry-tab-count">${patterns.length}</span></button>
    <button type="button" class="memory-entry-tab${_currentMemoryEntryTab==='corrections'?' active':''}" role="tab" aria-selected="${_currentMemoryEntryTab==='corrections'}" onclick="switchMemoryEntryTab('corrections')">${esc(t('memory_entries_corrections')||'Corrections')} <span class="memory-entry-tab-count">${corrections.length}</span></button>
  </div>`;

  const cardsHtml = activeEntries.length
    ? `<div class="memory-entry-list">${activeEntries.map(e => `
        <div class="memory-entry-card" data-entry-index="${e.index}">
          <div class="memory-entry-card-body preview-md">${renderMd(e.text)}</div>
          <button type="button" class="memory-entry-delete has-tooltip" data-tooltip="${esc(t('delete_title')||'Delete')}" onclick="deleteMemoryEntry(${e.index})" aria-label="${esc(t('delete_title')||'Delete')}">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        </div>`).join('')}</div>`
    : `<div class="memory-empty">${esc(_currentMemoryEntryTab==='corrections' ? (t('memory_entries_no_corrections')||'No corrections yet.') : (t('memory_entries_no_patterns')||'No patterns yet.'))}</div>`;

  const addFormHtml = `<form class="memory-entry-add-form" onsubmit="event.preventDefault(); submitMemoryEntryForm();">
    <textarea id="memEntryAddText" rows="2" placeholder="${esc(t('memory_entries_add_placeholder')||'Add a new memory entry…')}"></textarea>
    <div class="memory-entry-add-row">
      <label class="detail-form-check"><input type="checkbox" id="memEntryAddCorrection"> <span>${esc(t('memory_entries_mark_correction')||'Mark as correction')}</span></label>
      <button type="submit" class="btn-secondary">${esc(t('memory_entries_add')||'Add entry')}</button>
    </div>
    <div id="memEntryAddError" class="detail-form-error" style="display:none"></div>
  </form>`;

  const rawEditLink = !meta.readOnly
    ? `<button type="button" class="memory-entry-raw-edit-link" onclick="editCurrentMemory()">${esc(t('memory_entries_edit_raw')||'Edit raw file instead')}</button>`
    : '';

  body.innerHTML = `<div class="main-view-content">${pathHtml}${mtimeHtml}${tabsHtml}${cardsHtml}${addFormHtml}${rawEditLink}</div>`;
  body.style.display = '';
  if (empty) empty.style.display = 'none';
  _memoryMode = 'read';
  _setMemoryHeaderButtons('read');
}

function switchMemoryEntryTab(tab) {
  _currentMemoryEntryTab = tab === 'corrections' ? 'corrections' : 'patterns';
  _renderMemoryEntriesView();
}

async function deleteMemoryEntry(index) {
  const ok = await showConfirmDialog({
    title: t('delete_title') || 'Delete',
    message: t('memory_entries_delete_confirm') || 'Delete this memory entry?',
    confirmLabel: t('delete_title') || 'Delete',
    danger: true,
    focusCancel: true,
  });
  if (!ok) return;
  try {
    await api('/api/memory/entry/delete', { method: 'POST', body: JSON.stringify({ section: 'memory', index }) });
    await loadMemory();
    showToast(t('memory_entries_deleted') || 'Entry deleted');
  } catch (e) {
    showToast((t('error_prefix')||'Error: ') + e.message, 2000, 'error');
  }
}

async function submitMemoryEntryForm() {
  const ta = $('memEntryAddText');
  const cb = $('memEntryAddCorrection');
  const errEl = $('memEntryAddError');
  if (!ta || !errEl) return;
  const text = (ta.value || '').trim();
  errEl.style.display = 'none';
  if (!text) { errEl.textContent = t('content_required') || 'Content is required'; errEl.style.display = ''; return; }
  try {
    await api('/api/memory/entry/append', { method: 'POST', body: JSON.stringify({ section: 'memory', content: text, is_correction: !!(cb && cb.checked) }) });
    await loadMemory();
    showToast(t('memory_entries_added') || 'Entry added');
  } catch (e) {
    errEl.textContent = (t('error_prefix')||'Error: ') + e.message;
    errEl.style.display = '';
  }
}

function _renderMemoryEdit(section) {
  const meta = _memorySectionMeta(section);
  const title = $('memoryDetailTitle');
  const body = $('memoryDetailBody');
  const empty = $('memoryDetailEmpty');
  if (!title || !body) return;
  title.textContent = _memorySectionLabel(meta);
  const content = _memorySectionContent(section);
  body.innerHTML = `
    <div class="main-view-content">
      <form class="detail-form" onsubmit="event.preventDefault(); submitMemorySave();">
        <div class="detail-form-row">
          <label for="memEditContent">${esc(t('memory_notes_label'))}</label>
          <textarea id="memEditContent" rows="20" spellcheck="false">${esc(content)}</textarea>
        </div>
        <div id="memEditError" class="detail-form-error" style="display:none"></div>
      </form>
    </div>`;
  body.style.display = '';
  if (empty) empty.style.display = 'none';
  _memoryMode = 'edit';
  _setMemoryHeaderButtons('edit');
  const ta = $('memEditContent');
  if (ta) ta.focus();
}

async function loadNotesSources(force) {
  if (_notesSourcesData && !force) return _notesSourcesData;
  try {
    _notesSourcesData = await api('/api/notes/sources');
  } catch (e) {
    _notesSourcesData = {sources: [], automatic_recall_unchanged: true, error: e && e.message ? e.message : String(e)};
  }
  return _notesSourcesData;
}

function selectExternalNotesSource(source) {
  _notesSelectedSource = source || 'joplin';
  _notesSearchResults = [];
  _notesPreviewNote = null;
  _notesSearchError = '';
  _renderExternalNotesSources();
}

async function searchExternalNotes() {
  const input = $('externalNotesQuery');
  const sourceEl = $('externalNotesSource');
  const q = input ? input.value.trim() : '';
  _notesSelectedSource = sourceEl ? sourceEl.value : (_notesSelectedSource || 'joplin');
  _notesPreviewNote = null;
  _notesSearchError = '';
  if (!q) {
    _notesSearchResults = [];
    _renderExternalNotesSources();
    return;
  }
  _notesSearchLoading = true;
  _renderExternalNotesSources();
  try {
    const data = await api(`/api/notes/search?source=${encodeURIComponent(_notesSelectedSource)}&q=${encodeURIComponent(q)}&limit=20`);
    _notesSearchResults = Array.isArray(data.results) ? data.results : [];
    _notesSearchError = data.error || '';
  } catch (e) {
    _notesSearchResults = [];
    _notesSearchError = e && e.message ? e.message : String(e);
  } finally {
    _notesSearchLoading = false;
    _renderExternalNotesSources();
    const nextInput = $('externalNotesQuery');
    if (nextInput) nextInput.value = q;
  }
}

async function previewExternalNote(source, id) {
  _notesSearchError = '';
  try {
    const data = await api(`/api/notes/item?source=${encodeURIComponent(source||_notesSelectedSource)}&id=${encodeURIComponent(id||'')}`);
    _notesPreviewNote = data && data.note ? data.note : null;
  } catch (e) {
    _notesPreviewNote = null;
    _notesSearchError = e && e.message ? e.message : String(e);
  }
  _renderExternalNotesSources();
}

async function openMemorySection(section, el) {
  if (section === 'external_notes' && _memoryData && !_memoryData.external_notes_enabled) return;
  _currentMemorySection = section;
  document.querySelectorAll('#memoryPanel .side-menu-item').forEach(e => e.classList.remove('active'));
  if (el) el.classList.add('active');
  if (section === 'external_notes') {
    await loadNotesSources(false);
  }
  _renderMemoryDetail(section);
  _closeMobileSidebarAfterPanelSelection();
}

function editCurrentMemory() {
  const meta = _memorySectionMeta(_currentMemorySection);
  if (!_currentMemorySection || _currentMemorySection === 'external_notes' || meta.readOnly) return;
  _renderMemoryEdit(_currentMemorySection);
}

function cancelMemoryEdit() {
  if (!_currentMemorySection) return;
  _renderMemoryDetail(_currentMemorySection);
}

// Legacy alias (kept for any stale references)
function toggleMemoryEdit() { editCurrentMemory(); }
function closeMemoryEdit() { cancelMemoryEdit(); }

async function submitMemorySave() {
  if (!_currentMemorySection) return;
  if (_memorySectionMeta(_currentMemorySection).readOnly) return;
  const ta = $('memEditContent');
  const errEl = $('memEditError');
  if (!ta) return;
  if (errEl) errEl.style.display = 'none';
  try {
    await api('/api/memory/write', {method:'POST', body: JSON.stringify({section: _currentMemorySection, content: ta.value})});
    showToast(t('memory_saved'));
    await loadMemory(true);
    _renderMemoryDetail(_currentMemorySection);
  } catch(e) {
    if (errEl) { errEl.textContent = t('error_prefix') + e.message; errEl.style.display = ''; }
  }
}

// ── Workspace management ──
let _workspaceList = [];  // cached from /api/workspaces
let _wsSuggestTimer = null;
let _wsSuggestReq = 0;
let _wsSuggestIndex = -1;

function closeWorkspacePathSuggestions(){
  const box=$('workspaceFormPathSuggestions');
  if(box){
    box.innerHTML='';
    box.style.display='none';
  }
  _wsSuggestIndex=-1;
}

function _applyWorkspaceSuggestion(path){
  const input=$('workspaceFormPath');
  const next=(path||'').endsWith('/')?(path||''):`${path||''}/`;
  if(input){
    input.value=next;
    input.focus();
    input.setSelectionRange(next.length, next.length);
  }
  scheduleWorkspacePathSuggestions();
}

function _highlightWorkspaceSuggestion(idx){
  const box=$('workspaceFormPathSuggestions');
  if(!box)return;
  const items=[...box.querySelectorAll('.ws-suggest-item')];
  items.forEach((el,i)=>{
    const active=i===idx;
    el.classList.toggle('active', active);
    if(active) el.scrollIntoView({block:'nearest'});
  });
}

function _renderWorkspacePathSuggestions(paths){
  const box=$('workspaceFormPathSuggestions');
  if(!box)return;
  box.innerHTML='';
  if(!paths || !paths.length){
    box.style.display='none';
    _wsSuggestIndex=-1;
    return;
  }
  paths.forEach((path, idx)=>{
    const pathParts=(path||'').split('/').filter(Boolean);
    const leaf=pathParts[pathParts.length-1]||path;
    const parent=pathParts.length>1?`/${pathParts.slice(0,-1).join('/')}`:'/';
    const item=document.createElement('button');
    item.type='button';
    item.className='ws-suggest-item';
    item.innerHTML=`<span class="ws-suggest-leaf">${esc(leaf)}</span><span class="ws-suggest-parent">${esc(parent)}</span>`;
    item.dataset.path=path;
    item.onmouseenter=()=>{_wsSuggestIndex=idx;_highlightWorkspaceSuggestion(idx);};
    item.onmousedown=(e)=>{e.preventDefault();_applyWorkspaceSuggestion(path);};
    box.appendChild(item);
  });
  box.style.display='block';
  _wsSuggestIndex=0;
  _highlightWorkspaceSuggestion(_wsSuggestIndex);
}

async function _loadWorkspacePathSuggestions(prefix){
  const reqId=++_wsSuggestReq;
  try{
    const qs=new URLSearchParams({prefix:prefix||''}).toString();
    const data=await api(`/api/workspaces/suggest?${qs}`);
    if(reqId!==_wsSuggestReq)return;
    _renderWorkspacePathSuggestions(data.suggestions||[]);
  }catch(_){
    if(reqId!==_wsSuggestReq)return;
    closeWorkspacePathSuggestions();
  }
}

function scheduleWorkspacePathSuggestions(){
  const input=$('workspaceFormPath');
  if(!input)return;
  const prefix=input.value.trim();
  if(!prefix){
    closeWorkspacePathSuggestions();
    return;
  }
  if(_wsSuggestTimer) clearTimeout(_wsSuggestTimer);
  _wsSuggestTimer=setTimeout(()=>{
    _loadWorkspacePathSuggestions(prefix);
  }, 120);
}

function getWorkspaceFriendlyName(path){
  // Look up the friendly name from the workspace list cache, fallback to last path segment
  if(_workspaceList && _workspaceList.length){
    const match=_workspaceList.find(w=>w.path===path);
    if(match && match.name) return match.name;
  }
  return path.split('/').filter(Boolean).pop()||path;
}

function syncWorkspaceDisplays(){
  const hasSession=!!(S.session&&S.session.workspace);
  // Fall back to the profile default workspace when no session is active yet.
  // S._profileDefaultWorkspace is set during boot and profile switches from /api/settings.
  const defaultWs=(typeof S._profileDefaultWorkspace==='string'&&S._profileDefaultWorkspace)||'';
  const ws=hasSession?S.session.workspace:(defaultWs||'');
  const hasWorkspace=!!(ws);
  const label=hasWorkspace?getWorkspaceFriendlyName(ws):t('no_workspace');

  const sidebarName=$('sidebarWsName');
  const sidebarPath=$('sidebarWsPath');
  if(sidebarName) sidebarName.textContent=label;
  if(sidebarPath) sidebarPath.textContent=ws;

  const composerChip=$('composerWorkspaceChip');
  const composerLabel=$('composerWorkspaceLabel');
  const mobileAction=$('composerMobileWorkspaceAction');
  const mobileLabel=$('composerMobileWorkspaceLabel');
  const composerDropdown=$('composerWsDropdown');
  if(!hasWorkspace && composerDropdown) _setWorkspaceDropdownOpenState(composerDropdown,false);
  // Only show workspace label once boot has finished to prevent
  // flash of "No workspace" before the saved session finishes loading.
  if(composerLabel) composerLabel.textContent=S._bootReady?label:'';
  if(mobileLabel) mobileLabel.textContent=S._bootReady?label:'';
  const composerExpanded=!!(composerDropdown&&composerDropdown.classList.contains('open'));
  if(composerChip){
    composerChip.disabled=!hasWorkspace;
    composerChip.title=hasWorkspace?ws:t('no_workspace');
    composerChip.setAttribute('aria-label',hasWorkspace?t('workspace_switcher_aria',label):t('no_workspace'));
    composerChip.setAttribute('aria-expanded',composerExpanded?'true':'false');
    composerChip.classList.toggle('active',composerExpanded);
  }
  if(mobileAction){
    mobileAction.title=hasWorkspace?ws:t('no_workspace');
    mobileAction.setAttribute('aria-label',hasWorkspace?t('workspace_switcher_aria',label):t('no_workspace'));
    mobileAction.setAttribute('aria-expanded',composerExpanded?'true':'false');
    mobileAction.classList.toggle('active',composerExpanded);
  }
}

async function loadWorkspaceList(){
  try{
    const data = await api('/api/workspaces');
    if(typeof syncTerminalBackendState==='function') syncTerminalBackendState(data);
    _workspaceList = data.workspaces || [];
    syncWorkspaceDisplays();
    if(typeof syncTerminalButton==='function') syncTerminalButton();
    return data;
  }catch(e){ return {workspaces:[], last:''}; }
}

function _setWorkspaceDropdownOpenState(dd,open){
  if(!dd)return;
  dd.classList.toggle('open',!!open);
  dd.hidden=!open;
  dd.setAttribute('aria-hidden',open?'false':'true');
  if(open){
    try{dd.inert=false;}catch(_){}
    dd.removeAttribute('inert');
  }else{
    try{dd.inert=true;}catch(_){}
    dd.setAttribute('inert','');
  }
}

function _getComposerWorkspaceFocusTarget(){
  const panel=(typeof $==='function')?$('composerMobileConfigPanel'):null;
  const mobileAction=(typeof $==='function')?$('composerMobileWorkspaceAction'):null;
  if(panel&&panel.classList.contains('open')&&mobileAction&&!mobileAction.disabled) return mobileAction;
  return (typeof $==='function')?$('composerWorkspaceChip'):null;
}

function _focusComposerWorkspaceTarget(target){
  if(target&&!target.disabled&&typeof target.focus==='function'){
    try{target.focus({preventScroll:true});}
    catch(_){target.focus();}
  }
}

function _shouldRestoreComposerWorkspaceFocus(dd){
  if(typeof document==='undefined') return true;
  const active=document.activeElement;
  if(!active||active===document.body) return true;
  return !!(dd&&dd.contains(active));
}

function _renderWorkspaceAction(label, meta, iconSvg, onClick){
  const opt=document.createElement('div');
  opt.className='ws-opt ws-opt-action';
  opt.innerHTML=`<span class="ws-opt-icon">${iconSvg}</span><span><span class="ws-opt-name">${esc(label)}</span>${meta?`<span class="ws-opt-meta">${esc(meta)}</span>`:''}</span>`;
  opt.onclick=onClick;
  return opt;
}

function _positionComposerWsDropdown(){
  const dd=$('composerWsDropdown');
  const chip=$('composerWorkspaceGroup')||$('composerWorkspaceChip');
  const mobileAction=$('composerMobileWorkspaceAction');
  const panel=$('composerMobileConfigPanel');
  const footer=document.querySelector('.composer-footer');
  // While the mobile config panel is open, anchor to #composerMobileWorkspaceAction instead of only the desktop workspace chip.
  const anchor=(panel&&panel.classList.contains('open')&&mobileAction)?mobileAction:chip;
  if(!dd||!anchor||!footer)return;
  const chipRect=anchor.getBoundingClientRect();
  const footerRect=footer.getBoundingClientRect();
  let left=chipRect.left-footerRect.left;
  const maxLeft=Math.max(0, footer.clientWidth-dd.offsetWidth);
  left=Math.max(0, Math.min(left, maxLeft));
  dd.style.left=`${left}px`;
}

function _positionProfileDropdown(){
  const dd=$('profileDropdown');
  const trigger=_profileDropdownTrigger||$('profileChip');
  if(!dd||!trigger)return;
  const rect=trigger.getBoundingClientRect();
  const gap=4;
  const ddW=dd.offsetWidth||260;
  // Decide direction: below for titlebar, above for composer
  const openBelow=trigger===document.getElementById('titlebarProfileBtn');
  // Horizontal: center on trigger, clamp to viewport
  let left=rect.left+(rect.width/2)-(ddW/2);
  left=Math.max(8, Math.min(left, window.innerWidth-ddW-8));
  dd.style.left=left+'px';
  // Vertical
  if(openBelow){
    dd.style.bottom=''; // clear any stale bottom from a prior composer-chip open
    dd.style.top=(rect.bottom+gap)+'px';
    dd.classList.add('open-below');
  }else{
    dd.style.top=''; dd.style.bottom=''; // clear fixed top/bottom
    dd.style.bottom=(window.innerHeight-rect.top+gap)+'px';
    dd.classList.remove('open-below');
  }
}

function renderWorkspaceDropdownInto(dd, workspaces, currentWs){
  if(!dd)return;
  dd.innerHTML='';

  // ── Search row ──────────────────────────────────────────────────────────
  const searchRow=document.createElement('div');
  searchRow.className='ws-search-row';
  searchRow.innerHTML=`<input class="ws-search-input" type="text" placeholder="${esc(t('ws_search_placeholder')||'Search workspaces…')}" spellcheck="false" autocomplete="off"><button class="ws-search-clear" title="Clear search">${li('x',10)}</button>`;
  const si=searchRow.querySelector('.ws-search-input');
  const sc=searchRow.querySelector('.ws-search-clear');
  dd.appendChild(searchRow);

  // ── Workspace list ──────────────────────────────────────────────────────
  // Sort alphabetically by name (case-insensitive) before rendering.
  const sorted=[...workspaces].sort((a,b)=>(a.name||'').localeCompare(b.name||''));
  const listContainer=document.createElement('div');
  listContainer.className='ws-list-container';
  dd.appendChild(listContainer);

  // Pre-create noResults element so filterWs can reference it safely from the start.
  const noResults=document.createElement('div');
  noResults.className='ws-no-results';
  noResults.textContent=t('ws_no_results')||'No workspaces found';
  noResults.style.display='none';

  function filterWs(term){
    term=(term||'').trim().toLowerCase();
    let visible=0;
    const opts=listContainer.querySelectorAll('.ws-opt');
    for(const opt of opts){
      const name=(opt.dataset.name||'').toLowerCase();
      const path=(opt.dataset.path||'').toLowerCase();
      const show=!term||name.includes(term)||path.includes(term);
      opt.style.display=show?'':'none';
      if(show) visible++;
    }
    noResults.style.display=visible?'none':'';
  }

  function renderList(){
    listContainer.innerHTML='';
    for(const w of sorted){
      const opt=document.createElement('div');
      opt.className='ws-opt'+(w.path===currentWs?' active':'');
      opt.dataset.name=w.name||'';
      opt.dataset.path=w.path||'';
      opt.innerHTML=`<span class="ws-opt-name">${esc(w.name)}</span><span class="ws-opt-path">${esc(w.path)}</span>`;
      opt.onclick=()=>switchToWorkspace(w.path,w.name);
      listContainer.appendChild(opt);
    }
    listContainer.appendChild(noResults);
  }

  renderList();
  filterWs('');

  si.addEventListener('input',()=>{ filterWs(si.value); });
  sc.addEventListener('click',()=>{ si.value=''; filterWs(''); si.focus(); });

  // ── Footer actions ────────────────────────────────────────────────────────
  dd.appendChild(document.createElement('div')).className='ws-divider';
  dd.appendChild(_renderWorkspaceAction(
    t('workspace_new_worktree_conversation'),
    t('workspace_new_worktree_conversation_meta'),
    li('git-branch',12),
    async()=>{
      closeWsDropdown();
      try{
        await newSession(false,{worktree:true});
        await renderSessionList();
        const msg=$('msg');
        if(msg)msg.focus();
        showToast(t('workspace_worktree_created'));
      }catch(e){
        showToast(t('workspace_worktree_failed')+(e&&e.message?e.message:e),'error');
      }
    }
  ));
  dd.appendChild(document.createElement('div')).className='ws-divider';
  dd.appendChild(_renderWorkspaceAction(
    t('workspace_choose_path'),
    t('workspace_choose_path_meta'),
    li('folder',12),
    ()=>promptWorkspacePath()
  ));
  const div=document.createElement('div');div.className='ws-divider';dd.appendChild(div);
  dd.appendChild(_renderWorkspaceAction(
    t('workspace_manage'),
    t('workspace_manage_meta'),
    li('settings',12),
    ()=>{closeWsDropdown();mobileSwitchPanel('workspaces');}
  ));
}

function toggleWsDropdown(){
  const dd=$('wsDropdown');
  if(!dd)return;
  const open=dd.classList.contains('open');
  if(open){closeWsDropdown();}
  else{
    closeProfileDropdown(); // close profile dropdown if open
    loadWorkspaceList().then(data=>{
      renderWorkspaceDropdownInto(dd, data.workspaces, S.session?.workspace||S._profileDefaultWorkspace||data.last||'');
      _setWorkspaceDropdownOpenState(dd,true);
    });
  }
}

function toggleComposerWsDropdown(){
  const dd=$('composerWsDropdown');
  const chip=$('composerWorkspaceChip');
  const mobileAction=$('composerMobileWorkspaceAction');
  const panel=$('composerMobileConfigPanel');
  const usingMobileAction=!!(panel&&panel.classList.contains('open')&&mobileAction);
  if(!dd||(!usingMobileAction&&(!chip||chip.disabled)))return;
  const open=dd.classList.contains('open');
  if(open){closeWsDropdown();}
  else{
    closeProfileDropdown();
    if(typeof closeModelDropdown==='function') closeModelDropdown();
    if(typeof closeReasoningDropdown==='function') closeReasoningDropdown();
    loadWorkspaceList().then(data=>{
      renderWorkspaceDropdownInto(dd, data.workspaces, S.session?.workspace||S._profileDefaultWorkspace||data.last||'');
      _setWorkspaceDropdownOpenState(dd,true);
      _positionComposerWsDropdown();
      if(chip){
        chip.classList.add('active');
        chip.setAttribute('aria-expanded','true');
      }
      if(mobileAction){
        mobileAction.classList.add('active');
        mobileAction.setAttribute('aria-expanded','true');
      }
    });
  }
}

function closeWsDropdown(){
  const dd=$('wsDropdown');
  const composerDd=$('composerWsDropdown');
  const composerChip=$('composerWorkspaceChip');
  const mobileAction=$('composerMobileWorkspaceAction');
  if(dd)_setWorkspaceDropdownOpenState(dd,false);
  if(composerDd)_setWorkspaceDropdownOpenState(composerDd,false);
  if(composerChip){
    composerChip.classList.remove('active');
    composerChip.setAttribute('aria-expanded','false');
  }
  if(mobileAction){
    mobileAction.classList.remove('active');
    mobileAction.setAttribute('aria-expanded','false');
  }
}
document.addEventListener('click',e=>{
  if(
    !e.target.closest('#composerWorkspaceChip') &&
    !e.target.closest('#composerMobileWorkspaceAction') &&
    !e.target.closest('#composerWsDropdown')
  ) closeWsDropdown();
});
window.addEventListener('resize',()=>{
  const dd=$('composerWsDropdown');
  if(dd&&dd.classList.contains('open')) _positionComposerWsDropdown();
});

async function loadWorkspacesPanel(){
  const panel=$('workspacesPanel');
  if(!panel)return;
  const data=await loadWorkspaceList();
  renderWorkspacesPanel(data.workspaces);
}

function renderWorkspacesPanel(workspaces){
  const panel=$('workspacesPanel');
  panel.innerHTML='';
  const activePath = S.session ? S.session.workspace : '';
  for(let i=0;i<workspaces.length;i++){
    const w=workspaces[i];
    const row=document.createElement('div');
    row.className='ws-row';
    row.dataset.path = w.path;
    row.draggable=true;
    const isActive = w.path === activePath;
    const activeBadge = isActive ? `<span class="detail-badge active" style="margin-left:6px;font-size:9px;padding:1px 6px">${esc(t('profile_active'))}</span>` : '';
    row.innerHTML=`
      <span class="ws-drag-handle" title="${esc(t('workspace_drag_hint'))}">${li('grip-vertical',12)}</span>
      <div class="ws-row-info">
        <div class="ws-row-name">${esc(w.name)}${activeBadge}</div>
        <div class="ws-row-path">${esc(w.path)}</div>
      </div>`;
    // Click on info area only — not on drag handle
    const info=row.querySelector('.ws-row-info');
    if(info) info.onclick = (e) => { e.stopPropagation(); openWorkspaceDetail(w.path, row); };
    if (_currentWorkspaceDetail && _currentWorkspaceDetail.path === w.path) row.classList.add('active');

    // ── Drag-and-drop reorder ──
    row.addEventListener('dragstart', (e) => {
      // Only allow drag from the grip handle or the row itself
      row.classList.add('dragging');
      e.dataTransfer.effectAllowed='move';
      e.dataTransfer.setData('text/plain', w.path);
      // Required for Firefox drag ghost
      if(e.dataTransfer.setDragImage) e.dataTransfer.setDragImage(row, 0, 0);
    });
    row.addEventListener('dragend', () => {
      row.classList.remove('dragging');
      panel.querySelectorAll('.ws-row.drag-over').forEach(r => r.classList.remove('drag-over'));
    });
    row.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect='move';
      // Highlight drop target
      panel.querySelectorAll('.ws-row.drag-over').forEach(r => r.classList.remove('drag-over'));
      if(!row.classList.contains('dragging')) row.classList.add('drag-over');
    });
    row.addEventListener('dragleave', () => {
      row.classList.remove('drag-over');
    });
    row.addEventListener('drop', async (e) => {
      e.preventDefault();
      row.classList.remove('drag-over');
      const fromPath = e.dataTransfer.getData('text/plain');
      const toPath = w.path;
      if(fromPath === toPath) return; // Same item, no-op
      // Compute new order
      const currentPaths = workspaces.map(ws => ws.path);
      const fromIdx = currentPaths.indexOf(fromPath);
      const toIdx = currentPaths.indexOf(toPath);
      if(fromIdx < 0 || toIdx < 0) return;
      currentPaths.splice(fromIdx, 1);
      currentPaths.splice(toIdx, 0, fromPath);
      try {
        const res = await api('/api/workspaces/reorder', {
          method: 'POST',
          body: JSON.stringify({ paths: currentPaths })
        });
        if(res && res.ok){
          renderWorkspacesPanel(res.workspaces);
          // Also refresh sidebar dropdown
          loadWorkspaceList().then(() => {});
        }
      } catch(err){
        showToast(t('workspace_reorder_failed'), 'error');
      }
    });

    panel.appendChild(row);
  }
  const hint=document.createElement('div');
  hint.style.cssText='font-size:11px;color:var(--muted);padding:8px 0';
  hint.textContent=t('workspace_paths_validated_hint');
  panel.appendChild(hint);
  // Re-render detail if we have one cached and we're not in a form
  if (_currentWorkspaceDetail && _workspaceMode !== 'create' && _workspaceMode !== 'edit') {
    const refreshed = workspaces.find(w => w.path === _currentWorkspaceDetail.path);
    if (refreshed) _renderWorkspaceDetail(refreshed);
    else _clearWorkspaceDetail();
  }
}

function _renderWorkspaceDetail(ws){
  _currentWorkspaceDetail = ws;
  const title = $('workspaceDetailTitle');
  const body = $('workspaceDetailBody');
  const empty = $('workspaceDetailEmpty');
  if (!title || !body) return;
  title.textContent = ws.name || ws.path;
  const activePath = S.session ? S.session.workspace : '';
  const isActive = ws.path === activePath;
  const isDefault = !!ws.is_default;
  const statusBadge = isActive
    ? `<span class="detail-badge active">${esc(t('profile_active'))}</span>`
    : `<span class="detail-badge">Inactive</span>`;
  const defaultBadge = isDefault ? ` <span class="detail-badge">${esc(t('profile_default_label'))}</span>` : '';
  body.innerHTML = `
    <div class="main-view-content">
      <div class="detail-card">
        <div class="detail-card-title">Space</div>
        <div class="detail-row"><div class="detail-row-label">Name</div><div class="detail-row-value">${esc(ws.name || '')}</div></div>
        <div class="detail-row"><div class="detail-row-label">Path</div><div class="detail-row-value"><code>${esc(ws.path)}</code></div></div>
        <div class="detail-row"><div class="detail-row-label">Status</div><div class="detail-row-value">${statusBadge}${defaultBadge}</div></div>
      </div>
      <div class="detail-card" style="margin-top:12px">
        <div class="detail-card-title">${esc(t('checkpoint_title'))}</div>
        <div id="checkpointListContainer">
          <div style="color:var(--muted);font-size:12px;padding:8px 0">${esc(t('checkpoint_loading'))}</div>
        </div>
      </div>
    </div>`;
  body.style.display = '';
  if (empty) empty.style.display = 'none';
  _workspaceMode = 'read';
  _setWorkspaceHeaderButtons('read', ws);
  _loadCheckpoints(ws.path);
}

function _setWorkspaceHeaderButtons(mode, ws){
  const header = $('mainWorkspaces') && $('mainWorkspaces').querySelector('.main-view-header');
  const actBtn = $('btnActivateWorkspaceDetail');
  const editBtn = $('btnEditWorkspaceDetail');
  const delBtn = $('btnDeleteWorkspaceDetail');
  const cancelBtn = $('btnCancelWorkspaceDetail');
  const saveBtn = $('btnSaveWorkspaceDetail');
  const show = b => b && (b.style.display = '');
  const hide = b => b && (b.style.display = 'none');
  if (mode === 'read') { if (header) header.style.display = 'flex';
    const activePath = S.session ? S.session.workspace : '';
    const isActive = ws && ws.path === activePath;
    const isDefault = !!(ws && ws.is_default);
    if (isActive) hide(actBtn); else show(actBtn);
    show(editBtn);
    if (isDefault) hide(delBtn); else show(delBtn);
    hide(cancelBtn); hide(saveBtn);
  } else if (mode === 'create' || mode === 'edit') {
    if (header) header.style.display = 'flex';
    hide(actBtn); hide(editBtn); hide(delBtn); show(cancelBtn); show(saveBtn);
  } else {
    if (header) header.style.display = 'none';
    [actBtn, editBtn, delBtn, cancelBtn, saveBtn].forEach(hide);
  }
}

function openWorkspaceDetail(path, el){
  if (!_workspaceList) return;
  const ws = _workspaceList.find(w => w.path === path);
  if (!ws) return;
  document.querySelectorAll('.ws-row').forEach(e => e.classList.remove('active'));
  const target = el || document.querySelector(`.ws-row[data-path="${CSS.escape(path)}"]`);
  if (target) target.classList.add('active');
  _workspacePreFormDetail = null;
  _renderWorkspaceDetail(ws);
  _closeMobileSidebarAfterPanelSelection();
}

function _clearWorkspaceDetail(){
  _currentWorkspaceDetail = null;
  _workspaceMode = 'empty';
  const title = $('workspaceDetailTitle');
  const body = $('workspaceDetailBody');
  const empty = $('workspaceDetailEmpty');
  if (title) title.textContent = '';
  if (body) { body.innerHTML = ''; body.style.display = 'none'; }
  if (empty) empty.style.display = '';
  _setWorkspaceHeaderButtons('empty');
}

async function activateCurrentWorkspace(){
  if (!_currentWorkspaceDetail) return;
  await switchToWorkspace(_currentWorkspaceDetail.path, _currentWorkspaceDetail.name);
  // Re-render detail after activation so the active badge updates
  _renderWorkspaceDetail(_currentWorkspaceDetail);
}

async function deleteCurrentWorkspace(){
  if (!_currentWorkspaceDetail) return;
  const path = _currentWorkspaceDetail.path;
  const _ok = await showConfirmDialog({title:t('workspace_remove_confirm_title'),message:t('workspace_remove_confirm_message',path),confirmLabel:t('remove'),danger:true,focusCancel:true});
  if(!_ok) return;
  try{
    const data=await api('/api/workspaces/remove',{method:'POST',body:JSON.stringify({path})});
    _workspaceList=data.workspaces;
    _clearWorkspaceDetail();
    renderWorkspacesPanel(data.workspaces);
    showToast(t('workspace_removed'));
  }catch(e){setStatus(t('remove_failed')+e.message);}
}

function openWorkspaceCreate(){
  if (typeof switchPanel === 'function' && _currentPanel !== 'workspaces') switchPanel('workspaces');
  _workspacePreFormDetail = _currentWorkspaceDetail ? { ..._currentWorkspaceDetail } : null;
  _workspaceMode = 'create';
  _renderWorkspaceForm({ name:'', path:'', isEdit:false });
}

function editCurrentWorkspace(){
  if (!_currentWorkspaceDetail) return;
  _workspacePreFormDetail = { ..._currentWorkspaceDetail };
  _workspaceMode = 'edit';
  _renderWorkspaceForm({ name: _currentWorkspaceDetail.name || '', path: _currentWorkspaceDetail.path || '', isEdit: true });
}

function _renderWorkspaceForm({ name, path, isEdit }){
  const title = $('workspaceDetailTitle');
  const body = $('workspaceDetailBody');
  const empty = $('workspaceDetailEmpty');
  if (!title || !body) return;
  title.textContent = isEdit ? (t('edit') + ' · ' + (name || path)) : (t('workspace_new_title') || 'New space');
  const pathDisabled = isEdit ? 'disabled' : '';
  const pathHint = isEdit
    ? `<div class="detail-form-hint">${esc(t('workspace_path_readonly') || 'Path cannot be changed. Rename only.')}</div>`
    : `<div class="detail-form-hint">${esc(t('workspace_paths_validated_hint'))}</div>`;
  body.innerHTML = `
    <div class="main-view-content">
      <form class="detail-form" onsubmit="event.preventDefault(); saveWorkspaceForm();">
        <div class="detail-form-row">
          <label for="workspaceFormName">${esc(t('workspace_name_label') || 'Name')}</label>
          <input type="text" id="workspaceFormName" value="${esc(name || '')}" placeholder="${esc(t('workspace_name_placeholder') || 'Optional friendly name')}" autocomplete="off">
        </div>
        <div class="detail-form-row">
          <label for="workspaceFormPath">${esc(t('workspace_path_label') || 'Path')}</label>
          <div class="workspace-form-path-wrap" style="position:relative">
            <input type="text" id="workspaceFormPath" value="${esc(path || '')}" placeholder="${esc(t('workspace_add_path_placeholder') || '/absolute/path/to/folder')}" autocomplete="off" ${pathDisabled} required>
            <div id="workspaceFormPathSuggestions" class="ws-suggestions" style="display:none"></div>
          </div>
          ${pathHint}
        </div>
        <div id="workspaceFormError" class="detail-form-error" style="display:none"></div>
      </form>
    </div>`;
  body.style.display = '';
  if (empty) empty.style.display = 'none';
  _setWorkspaceHeaderButtons(isEdit ? 'edit' : 'create');
  if (!isEdit) _wireWorkspaceFormPathSuggestions();
  const focus = isEdit ? $('workspaceFormName') : $('workspaceFormPath');
  if (focus) focus.focus();
}

function cancelWorkspaceForm(){
  closeWorkspacePathSuggestions();
  if (_workspacePreFormDetail) {
    const snap = _workspacePreFormDetail;
    _workspacePreFormDetail = null;
    _renderWorkspaceDetail(snap);
    return;
  }
  _clearWorkspaceDetail();
}

async function saveWorkspaceForm(){
  const nameEl = $('workspaceFormName');
  const pathEl = $('workspaceFormPath');
  const errEl = $('workspaceFormError');
  if (!pathEl || !errEl) return;
  const name = (nameEl ? nameEl.value : '').trim();
  const path = (pathEl.value || '').trim();
  errEl.style.display = 'none';
  if (!path) { errEl.textContent = t('workspace_path_required') || 'Path is required'; errEl.style.display = ''; return; }
  try {
    if (_workspaceMode === 'edit' && _currentWorkspaceDetail) {
      const targetPath = _currentWorkspaceDetail.path;
      const newName = name || _currentWorkspaceDetail.name || '';
      await api('/api/workspaces/rename', { method:'POST', body: JSON.stringify({ path: targetPath, name: newName }) });
      // Refresh list and re-render detail
      const data = await api('/api/workspaces');
      _workspaceList = data.workspaces || [];
      _workspacePreFormDetail = null;
      showToast(t('workspace_renamed') || t('workspace_added'));
      renderWorkspacesPanel(_workspaceList);
      openWorkspaceDetail(targetPath);
      return;
    }
    const data = await api('/api/workspaces/add', { method:'POST', body: JSON.stringify({ path }) });
    _workspaceList = data.workspaces || [];
    _workspacePreFormDetail = null;
    // Apply rename if a friendly name was supplied
    if (name) {
      try { await api('/api/workspaces/rename', { method:'POST', body: JSON.stringify({ path, name }) }); } catch(_) {}
      const refreshed = await api('/api/workspaces');
      _workspaceList = refreshed.workspaces || _workspaceList;
    }
    renderWorkspacesPanel(_workspaceList);
    showToast(t('workspace_added'));
    const added = _workspaceList.find(w => w.path === path) || _workspaceList[_workspaceList.length - 1];
    if (added) openWorkspaceDetail(added.path);
  } catch (e) {
    errEl.textContent = t('error_prefix') + e.message;
    errEl.style.display = '';
  }
}

// Back-compat: any legacy caller of addWorkspace() opens the new form instead.
function addWorkspace(){ openWorkspaceCreate(); }

function _wireWorkspaceFormPathSuggestions(){
  const input=$('workspaceFormPath');
  if(!input) return;
  input.oninput=()=>scheduleWorkspacePathSuggestions();
  input.onfocus=()=>{
    if(input.value.trim()) scheduleWorkspacePathSuggestions();
    else closeWorkspacePathSuggestions();
  };
  input.onkeydown=(e)=>{
    const box=$('workspaceFormPathSuggestions');
    const items=box?[...box.querySelectorAll('.ws-suggest-item')]:[];
    if(!items.length){
      return;
    }
    if(e.key==='ArrowDown'){
      e.preventDefault();
      _wsSuggestIndex=Math.min(items.length-1,Math.max(-1,_wsSuggestIndex)+1);
      _highlightWorkspaceSuggestion(_wsSuggestIndex);
      return;
    }
    if(e.key==='ArrowUp'){
      e.preventDefault();
      _wsSuggestIndex=_wsSuggestIndex<=0?0:_wsSuggestIndex-1;
      _highlightWorkspaceSuggestion(_wsSuggestIndex);
      return;
    }
    if(e.key==='Escape'){
      e.preventDefault();
      closeWorkspacePathSuggestions();
      return;
    }
    if(e.key==='Enter' && _wsSuggestIndex>=0 && items[_wsSuggestIndex]){
      e.preventDefault();
      _applyWorkspaceSuggestion(items[_wsSuggestIndex].dataset.path||'');
      return;
    }
    if(e.key==='Tab' && _wsSuggestIndex>=0 && items[_wsSuggestIndex]){
      e.preventDefault();
      _applyWorkspaceSuggestion(items[_wsSuggestIndex].dataset.path||'');
      return;
    }
  };
}

document.addEventListener('click',e=>{
  if(!e.target.closest('.workspace-form-path-wrap')) closeWorkspacePathSuggestions();
});

async function removeWorkspace(path){
  const _rmWs=await showConfirmDialog({title:t('workspace_remove_confirm_title'),message:t('workspace_remove_confirm_message',path),confirmLabel:t('remove'),danger:true,focusCancel:true});
  if(!_rmWs) return;
  try{
    const data=await api('/api/workspaces/remove',{method:'POST',body:JSON.stringify({path})});
    _workspaceList=data.workspaces;
    renderWorkspacesPanel(data.workspaces);
    showToast(t('workspace_removed'));
  }catch(e){setStatus(t('remove_failed')+e.message);}
}

async function promptWorkspacePath(){
  // Opus review Q6: if called from blank page (no session), auto-create one first.
  if(!S.session){
    const ws=(typeof S._profileDefaultWorkspace==='string'&&S._profileDefaultWorkspace)||'';
    if(!ws)return;
    try{
      // System-minted session (#6022): worktree:false is explicit so a config
      // worktree default can't leak a worktree from a workspace prompt.
      const r=await api('/api/session/new',{method:'POST',body:JSON.stringify({workspace:ws,worktree:false})});
      if(r&&r.session){S._pendingSessionToolsets=null;S.session=r.session;S.messages=[];if(typeof syncTopbar==='function')syncTopbar();if(typeof renderMessages==='function')renderMessages();if(typeof renderSessionList==='function')await renderSessionList();}
    }catch(e){showToast(t('workspace_switch_failed')+e.message);return;}
    if(!S.session)return;
  }
  const value=await showPromptDialog({
    title:t('workspace_switch_prompt_title'),
    message:t('workspace_switch_prompt_message'),
    confirmLabel:t('workspace_switch_prompt_confirm'),
    placeholder:t('workspace_switch_prompt_placeholder'),
    value:S.session.workspace||''
  });
  const path=(value||'').trim();
  if(!path)return;
  try{
    const data=await api('/api/workspaces/add',{method:'POST',body:JSON.stringify({path})});
    _workspaceList=data.workspaces||[];
    const target=_workspaceList[_workspaceList.length-1];
    if(!target) throw new Error(t('workspace_not_added'));
    await switchToWorkspace(target.path,target.name);
  }catch(e){
    if(String(e.message||'').includes('Workspace already in list')){
      showToast(t('workspace_already_saved'));
      return;
    }
    showToast(t('workspace_switch_failed')+e.message);
  }
}

async function switchToWorkspace(path,name){
  // Opus review Q6: if called from blank page, auto-create a session bound to
  // the requested workspace so the switch doesn't silently no-op.
  if(!S.session){
    const ws=path||(typeof S._profileDefaultWorkspace==='string'&&S._profileDefaultWorkspace)||'';
    if(!ws){showToast(t('no_workspace'));return;}
    try{
      // System-minted session (#6022): explicit worktree:false — a workspace
      // switch from a blank page is not deliberate New Chat intent.
      const r=await api('/api/session/new',{method:'POST',body:JSON.stringify({workspace:ws,worktree:false})});
      if(r&&r.session){S._pendingSessionToolsets=null;S.session=r.session;S.messages=[];if(typeof syncTopbar==='function')syncTopbar();if(typeof renderMessages==='function')renderMessages();if(typeof renderSessionList==='function')await renderSessionList();}
    }catch(e){if(typeof setStatus==='function')setStatus(t('switch_failed')+e.message);return;}
    if(!S.session)return;
  }
  // Workspace mutation during a live turn would desync the active stream context.
  if(S.busy){
    showToast(t('workspace_busy_switch'));
    return;
  }
  // #5473 (opt-in, default off): treat switching to a DIFFERENT workspace as a
  // new-chat boundary instead of mutating the current session in place. A
  // workspace switch changes the project-context files the agent loaded, so
  // reusing the session would carry stale cross-workspace context. Only fires
  // when: the setting is on, the target workspace actually differs from the
  // current one, and the current conversation has real messages worth keeping on
  // its original workspace. Same-workspace selection stays an in-place refresh.
  if(
    window._newChatOnWorkspaceSwitch===true &&
    S.session && S.session.workspace && path && path!==S.session.workspace &&
    Array.isArray(S.messages) && S.messages.length>0
  ){
    if(typeof _previewDirty!=='undefined'&&_previewDirty){
      const discard=await showConfirmDialog({
        title:t('discard_file_edits_title'),
        message:t('discard_file_edits_message'),
        confirmLabel:t('discard'),
        danger:true
      });
      if(!discard)return;
      if(typeof cancelEditMode==='function')cancelEditMode();
      if(typeof clearPreview==='function')clearPreview();
    }
    closeWsDropdown();
    // Bind the new chat to the selected workspace via the one-shot flag newSession() reads.
    S._profileSwitchWorkspace=path;
    if(typeof newSession==='function') await newSession(false);
    showToast(t('workspace_switched_new_chat',name||getWorkspaceFriendlyName(path)));
    return;
  }
  if(typeof _previewDirty!=='undefined'&&_previewDirty){
    const discard=await showConfirmDialog({
      title:t('discard_file_edits_title'),
      message:t('discard_file_edits_message'),
      confirmLabel:t('discard'),
      danger:true
    });
    if(!discard)return;
    if(typeof cancelEditMode==='function')cancelEditMode();
    if(typeof clearPreview==='function')clearPreview();
  }
  const composerDd=(typeof $==='function')?$('composerWsDropdown'):null;
  const restoreComposerFocusTarget=(composerDd&&composerDd.classList.contains('open')&&typeof _getComposerWorkspaceFocusTarget==='function')
    ? _getComposerWorkspaceFocusTarget()
    : null;
  try{
    closeWsDropdown();
    // Invalidate any older /api/list response before the explicit workspace
    // mutation. Otherwise a delayed recovery response for this same session can
    // overwrite the user's newer selection and reject this switch's fresh tree.
    if(typeof bumpWorkspaceTreeGen==='function')bumpWorkspaceTreeGen();
    await api('/api/session/update',{method:'POST',body:JSON.stringify({
      session_id:S.session.session_id, workspace:path, model:S.session.model, model_provider:S.session.model_provider||null
    })});
    S.session.workspace=path;
    // Explicit workspace switch = user overriding any pending profile-switch default.
    // Clear the one-shot flag so a subsequent newSession() inherits this choice instead.
    S._profileSwitchWorkspace=null;
    S._pendingSessionToolsets=null;
    syncTopbar();
    if(
      restoreComposerFocusTarget&&
      typeof _shouldRestoreComposerWorkspaceFocus==='function'&&
      _shouldRestoreComposerWorkspaceFocus(composerDd)&&
      typeof _focusComposerWorkspaceTarget==='function'
    ) _focusComposerWorkspaceTarget(restoreComposerFocusTarget);
    await loadDir('.');
    if (_currentPanel === 'memory') await loadMemory(true);
    showToast(t('workspace_switched_to',name||getWorkspaceFriendlyName(path)));
  }catch(e){setStatus(t('switch_failed')+e.message);}
}

// ── Profile panel + dropdown ──
let _profilesCache = null;
let _profileDropdownFetchPromise = null;
let _profileDropdownCacheLoadedFromStorage = false;
const PROFILE_DROPDOWN_CACHE_KEY = 'hermes-webui-profile-dropdown-cache-v1';
const PROFILE_DROPDOWN_CACHE_TTL_MS = 5 * 60 * 1000;
let _profileSwitchGeneration = 0;
let _profileDropdownTrigger = null;  // tracks which element triggered the dropdown
let _profileDropdownOpenGeneration = 0;

function _profileDropdownClearStoredCache(){
  try{localStorage.removeItem(PROFILE_DROPDOWN_CACHE_KEY);}catch(_){}
}

function _profileDropdownDataCacheUsable(data){
  return !!(
    data &&
    Array.isArray(data.profiles) &&
    data.profiles.length &&
    data.profiles.every(p=>
      p &&
      typeof p.name==='string' &&
      // Renderer-read fields must be safe types: renderProfileDropdown /
      // renderProfilesPanel call p.model.split('/') guarded only by truthiness,
      // so a poisoned cached row like {name:"x", model:{}} would pass a
      // name-only check yet throw synchronously on dropdown open (bricking
      // profile switching). Reject rows whose model is a non-string truthy value.
      (p.model==null || typeof p.model==='string')
    )
  );
}

function _profileDropdownCacheUsable(data){
  return !!(_profileDropdownDataCacheUsable(data) && data.single_profile_mode !== true);
}

function _profileDropdownReadStoredCache(){
  if(_profileDropdownCacheLoadedFromStorage) return _profileDropdownCacheUsable(_profilesCache) ? _profilesCache : null;
  _profileDropdownCacheLoadedFromStorage = true;
  try{
    const raw=localStorage.getItem(PROFILE_DROPDOWN_CACHE_KEY);
    if(!raw) return null;
    const parsed=JSON.parse(raw);
    if(!parsed || typeof parsed.ts!=='number' || !parsed.data) { _profileDropdownClearStoredCache(); return null; }
    if(Date.now()-parsed.ts>PROFILE_DROPDOWN_CACHE_TTL_MS) { _profileDropdownClearStoredCache(); return null; }
    if(!_profileDropdownCacheUsable(parsed.data)) { _profileDropdownClearStoredCache(); return null; }
    _profilesCache = parsed.data;
    return _profilesCache;
  }catch(_){_profileDropdownClearStoredCache();return null;}
}

function _profileDropdownWriteStoredCache(data){
  if(!_profileDropdownCacheUsable(data)) { _profileDropdownClearStoredCache(); return; }
  try{localStorage.setItem(PROFILE_DROPDOWN_CACHE_KEY, JSON.stringify({ts:Date.now(), data}));}catch(_){}
}

function _profileDropdownBestCachedData(){
  if(_profileDropdownCacheUsable(_profilesCache)) return _profilesCache;
  if(_profileDropdownDataCacheUsable(_profilesCache)) return null;
  _profilesCache = null;
  return _profileDropdownReadStoredCache();
}

function _profileDropdownFetchFresh(){
  if(_profileDropdownFetchPromise) return _profileDropdownFetchPromise;
  _profileDropdownFetchPromise = api('/api/profiles', {timeoutToast:false}).then(data=>{
    if(_profileDropdownDataCacheUsable(data)) _profilesCache = data;
    _profileDropdownWriteStoredCache(data);
    return data;
  }).finally(()=>{ _profileDropdownFetchPromise = null; });
  return _profileDropdownFetchPromise;
}

function _warmProfileDropdownCache(){
  _profileDropdownBestCachedData();
  _profileDropdownFetchFresh().catch(()=>{});
}

if(typeof window!=='undefined'){
  window.addEventListener('load',()=>{
    setTimeout(()=>{
      if(typeof document==='undefined'||!document.hidden) _warmProfileDropdownCache();
    },1200);
  },{once:true});
}

function _renderProfileDropdownLoading(){
  const dd=$('profileDropdown');
  if(!dd)return;
  dd.innerHTML=`<div class="profile-opt profile-opt-loading"><div class="profile-opt-name">${esc(t('loading')||'Loading...')}</div></div>`;
}

function _openProfileDropdownShell(){
  const dd=$('profileDropdown');
  if(!dd)return;
  dd.classList.add('open');
  _positionProfileDropdown();
  const chip=$('profileChip');
  if(chip && _profileDropdownTrigger===chip) chip.classList.add('active');
  const tbtn=$('titlebarProfileBtn');
  if(tbtn && _profileDropdownTrigger===tbtn) tbtn.classList.add('active');
}

async function _profileSwitchPanelLoad(){
  // Cross-profile cron visibility is an active-profile opt-in; never carry it
  // into the next profile when the Tasks panel wasn't the visible panel.
  _showAllCronProfiles = false;
  _cronOtherProfileCount = 0;
  _cronPreFormDetail = null;
  _editingCronId = null;
  _cronIsDuplicate = false;
  _clearCronDetail();
  if (_currentPanel === 'skills') await loadSkills();
  if (_currentPanel === 'memory') await loadMemory();
  if (_currentPanel === 'tasks') await loadCrons();
  if (_currentPanel === 'kanban') await loadKanban();
  if (_currentPanel === 'profiles') await loadProfilesPanel();
  if (_currentPanel === 'workspaces') await loadWorkspacesPanel();
}

function _refreshProfileSwitchBackground(gen){
  window._modelDropdownReady=null;
  if (typeof window._ensureModelDropdownReady === 'function') {
    Promise.resolve(window._ensureModelDropdownReady()).catch(()=>{});
  }
  Promise.resolve(loadWorkspaceList()).then(()=>{
    if (gen !== _profileSwitchGeneration) return;
    if (S.session && typeof syncTopbar === 'function') syncTopbar();
  }).catch(()=>{});
  // Reconcile per-profile sidebar tab visibility. hidden_tabs is a per-profile
  // appearance setting; without this fetch, Profile A's hidden-tabs choice
  // would remain in effect under Profile B until the user opens Settings.
  // Stage-394 follow-up to #2636 deep review.
  Promise.resolve(api('/api/settings')).then(function(s){
    if (gen !== _profileSwitchGeneration) return;
    var hidden = (s && Array.isArray(s.hidden_tabs)) ? s.hidden_tabs : [];
    hidden = hidden.filter(function(x){ return typeof x === 'string' && x.trim(); });
    var order = (s && Array.isArray(s.tab_order)) ? s.tab_order : [];
    order = order.filter(function(x){ return typeof x === 'string' && x.trim(); });
    if (typeof _setHiddenTabs === 'function') _setHiddenTabs(hidden);
    if (typeof _setTabOrder === 'function') _setTabOrder(order);
    if (typeof _applyTabOrder === 'function') _applyTabOrder(order);
    if (typeof _applyTabVisibility === 'function') _applyTabVisibility(hidden);
    _ensureComposerControlVisibilityState(s||{});
    if(Array.isArray(s&&s.composer_control_order)){
      const nextOrder=_setComposerControlOrder(s.composer_control_order);
      if(typeof window._applyComposerControlOrder==='function') window._applyComposerControlOrder(nextOrder);
    }
    _renderComposerControlChips();
    _renderComposerSituationalControlChips();
    if(typeof _applyComposerFooterVisibilitySettings==='function') _applyComposerFooterVisibilitySettings();
    window._showTitlebarProfile=!!(s&&s.show_titlebar_profile);
    if(typeof _applyTitlebarProfileVisibility==='function') _applyTitlebarProfileVisibility();
  }).catch(function(){});
}

async function loadProfilesPanel() {
  const panel = $('profilesPanel');
  if (!panel) return;
  try {
    const data = await api('/api/profiles');
    _profilesCache = data;
    _profileDropdownWriteStoredCache(data);
    panel.innerHTML = '';

    // Hide "New profile" button in single profile mode
    const newProfileBtn = document.querySelector('[onclick="openProfileCreate()"]');
    if (newProfileBtn) {
      newProfileBtn.style.display = data.single_profile_mode ? 'none' : '';
    }

    // In single profile mode, don't show the explanatory card
    if (!data.single_profile_mode) {
      const explainer = document.createElement('div');
      explainer.className = 'profile-card profile-help-card';
      explainer.innerHTML = `
        <div class="profile-card-header">
          <div style="min-width:0;flex:1">
            <div class="profile-card-name">${esc(t('profile_concept_title'))}</div>
            <div class="profile-card-meta">${esc(t('profile_concept_subtitle'))}</div>
          </div>
        </div>`;
      explainer.onclick = () => _renderProfileConceptHelp(data.active || 'default');
      panel.appendChild(explainer);
    }

    if (!data.profiles || !data.profiles.length) {
      const emptyMsg = document.createElement('div');
      emptyMsg.style.cssText = 'padding:16px;color:var(--muted);font-size:12px';
      emptyMsg.textContent = t('profiles_no_profiles');
      panel.appendChild(emptyMsg);
      if (_profileMode !== 'create') _clearProfileDetail();
      return;
    }
    const activeName = (S.activeProfile && data.profiles.some(p => p.name === S.activeProfile))
      ? S.activeProfile
      : (data.active || 'default');
    for (const p of data.profiles) {
      const card = document.createElement('div');
      card.className = 'profile-card';
      card.dataset.name = p.name;
      const meta = [];
      if (typeof p.model === 'string' && p.model) meta.push(p.model.split('/').pop());
      if (p.provider) meta.push(p.provider);
      if (p.total_skills && p.total_skills > 0) meta.push(t('profile_skill_count', p.total_skills).replace(String(p.total_skills), `${p.enabled_skills} / ${p.total_skills}`));
      const gwDot = p.gateway_running
        ? `<span class="profile-opt-badge running" title="${esc(t('profile_gateway_running'))}"></span>`
        : `<span class="profile-opt-badge stopped" title="${esc(t('profile_gateway_stopped'))}"></span>`;
      const isActive = p.name === activeName;
      const activeBadge = isActive ? `<span style="color:var(--link);font-size:10px;font-weight:600;margin-left:6px">${esc(t('profile_active'))}</span>` : '';
      const defaultBadge = p.is_default ? ` <span style="opacity:.5">${esc(t('profile_default_label'))}</span>` : '';
      const hiddenBadge = p.visible === false ? ' <span class="detail-badge" title="Hidden from chat">Hidden from chat</span>' : '';
      card.innerHTML = `
        <div class="profile-card-header">
          <div style="min-width:0;flex:1">
            <div class="profile-card-name${isActive ? ' is-active' : ''}">${gwDot}${esc(p.name)}${defaultBadge}${activeBadge}${hiddenBadge}</div>
            ${meta.length ? `<div class="profile-card-meta">${esc(meta.join(' \u00b7 '))}</div>` : `<div class="profile-card-meta">${esc(t('profile_no_configuration'))}</div>`}
          </div>
        </div>`;
      card.onclick = () => openProfileDetail(p.name, card);
      if (_currentProfileDetail && _currentProfileDetail.name === p.name) card.classList.add('active');
      panel.appendChild(card);
    }
    // Re-render detail with fresh data if we have one and we're not in a form
    if (_currentProfileDetail && _profileMode !== 'create') {
      const refreshed = data.profiles.find(p => p.name === _currentProfileDetail.name);
      if (refreshed) _renderProfileDetail(refreshed, data.active);
      else _clearProfileDetail();
    }
  } catch (e) {
    panel.innerHTML = `<div style="color:var(--accent);font-size:12px;padding:12px">${esc(t('error_prefix'))}${esc(e.message)}</div>`;
  }
}

function _renderProfileConceptHelp(activeName){
  const title = $('profileDetailTitle');
  const body = $('profileDetailBody');
  const empty = $('profileDetailEmpty');
  if (!title || !body) return;
  title.textContent = t('profile_concept_title');
  body.innerHTML = `
    <div class="main-view-content">
      <div class="detail-card">
        <div class="detail-card-title">${esc(t('profile_concept_title'))}</div>
        <div class="detail-row"><div class="detail-row-label">${esc(t('tab_profiles'))}</div><div class="detail-row-value">${esc(t('profile_concept_desc_profiles'))}</div></div>
        <div class="detail-row"><div class="detail-row-label">${esc(t('tab_workspaces'))}</div><div class="detail-row-value">${esc(t('profile_concept_desc_workspaces'))}</div></div>
        <div class="detail-row"><div class="detail-row-label">${esc(t('profile_concept_label_together'))}</div><div class="detail-row-value">${esc(t('profile_concept_desc_together'))}</div></div>
        <div class="detail-row" style="border-top:1px solid var(--border);padding-top:8px;margin-top:4px"><div class="detail-row-label">${esc(t('profile_concept_label_example'))}</div><div class="detail-row-value">${esc(t('profile_concept_example'))}</div></div>
      </div>
    </div>`;
  body.style.display = '';
  if (empty) empty.style.display = 'none';
  _profileMode = 'read';
  _currentProfileDetail = null;
  _setProfileHeaderButtons('help');
}

function _renderProfileDetail(p, activeName){
  _currentProfileDetail = p;
  const title = $('profileDetailTitle');
  const body = $('profileDetailBody');
  const empty = $('profileDetailEmpty');
  if (!title || !body) return;
  title.textContent = p.name;
  const isActive = p.name === activeName;
  const isDefault = !!p.is_default;
  const statusBadge = isActive
    ? `<span class="detail-badge active">${esc(t('profile_active'))}</span>`
    : `<span class="detail-badge">Inactive</span>`;
  const defaultBadge = isDefault ? ` <span class="detail-badge">${esc(t('profile_default_label'))}</span>` : '';
  const gwBadge = p.gateway_running
    ? `<span class="detail-badge ok">${esc(t('profile_gateway_running'))}</span>`
    : `<span class="detail-badge">${esc(t('profile_gateway_stopped'))}</span>`;
  const rows = [];
  rows.push(`<div class="detail-row"><div class="detail-row-label">Status</div><div class="detail-row-value">${statusBadge}${defaultBadge}</div></div>`);
  rows.push(`<div class="detail-row"><div class="detail-row-label">Gateway</div><div class="detail-row-value">${gwBadge}</div></div>`);
  if (p.model) rows.push(`<div class="detail-row"><div class="detail-row-label">Model</div><div class="detail-row-value"><code>${esc(p.model)}</code></div></div>`);
  if (p.provider) rows.push(`<div class="detail-row"><div class="detail-row-label">Provider</div><div class="detail-row-value">${esc(p.provider)}</div></div>`);
  if (p.base_url) rows.push(`<div class="detail-row"><div class="detail-row-label">Base URL</div><div class="detail-row-value"><code>${esc(p.base_url)}</code></div></div>`);
  rows.push(`<div class="detail-row"><div class="detail-row-label">API key</div><div class="detail-row-value">${p.has_env ? esc(t('profile_api_keys_configured')) : '<span style="color:var(--muted)">Not configured</span>'}</div></div>`);
  if (p.total_skills && p.total_skills > 0) rows.push(`<div class="detail-row"><div class="detail-row-label">Skills</div><div class="detail-row-value">${esc(t('profile_skill_count', p.total_skills).replace(String(p.total_skills), `${p.enabled_skills} / ${p.total_skills}`))}</div></div>`);
  if (p.default_workspace) rows.push(`<div class="detail-row"><div class="detail-row-label">Default space</div><div class="detail-row-value"><code>${esc(p.default_workspace)}</code></div></div>`);
  body.innerHTML = `
    <div class="main-view-content">
      <div class="detail-card">
        <div class="detail-card-title">Profile</div>
        ${rows.join('')}
      </div>
    </div>`;
  body.style.display = '';
  if (empty) empty.style.display = 'none';
  _profileMode = 'read';
  _setProfileHeaderButtons('read', p, activeName);
}

function _setProfileHeaderButtons(mode, p, activeName){
  const header = $('mainProfiles') && $('mainProfiles').querySelector('.main-view-header');
  const actBtn = $('btnActivateProfileDetail');
  const delBtn = $('btnDeleteProfileDetail');
  const cancelBtn = $('btnCancelProfileDetail');
  const saveBtn = $('btnSaveProfileDetail');
  const show = b => b && (b.style.display = '');
  const hide = b => b && (b.style.display = 'none');
  if (mode === 'read') {
    if (header) header.style.display = 'flex';
    const isActive = p && p.name === activeName;
    const isDefault = !!(p && p.is_default);
    const singleProfileMode = !!(_profilesCache && _profilesCache.single_profile_mode);
    if (isActive || singleProfileMode) hide(actBtn); else show(actBtn);
    if (isDefault || singleProfileMode) hide(delBtn); else show(delBtn);
    hide(cancelBtn); hide(saveBtn);
  } else if (mode === 'create') {
    if (header) header.style.display = 'flex';
    hide(actBtn); hide(delBtn); show(cancelBtn); show(saveBtn);
  } else if (mode === 'help') {
    // Read-only help/concept view: title is populated, so show the header but
    // hide every action button (no profile to act on).
    if (header) header.style.display = 'flex';
    [actBtn, delBtn, cancelBtn, saveBtn].forEach(hide);
  } else {
    if (header) header.style.display = 'none';
    [actBtn, delBtn, cancelBtn, saveBtn].forEach(hide);
  }
}

function openProfileDetail(name, el){
  if (!_profilesCache || !_profilesCache.profiles) return;
  const p = _profilesCache.profiles.find(x => x.name === name);
  if (!p) return;
  document.querySelectorAll('.profile-card').forEach(e => e.classList.remove('active'));
  const target = el || document.querySelector(`.profile-card[data-name="${CSS.escape(name)}"]`);
  if (target) target.classList.add('active');
  _profilePreFormDetail = null;
  _renderProfileDetail(p, _profilesCache.active);
  _closeMobileSidebarAfterPanelSelection();
}

function _clearProfileDetail(){
  _currentProfileDetail = null;
  _profileMode = 'empty';
  const title = $('profileDetailTitle');
  const body = $('profileDetailBody');
  const empty = $('profileDetailEmpty');
  if (title) title.textContent = '';
  if (body) { body.innerHTML = ''; body.style.display = 'none'; }
  if (empty) empty.style.display = '';
  _setProfileHeaderButtons('empty');
}

async function activateCurrentProfile(){
  if (!_currentProfileDetail) return;
  await switchToProfile(_currentProfileDetail.name);
}

async function deleteCurrentProfile(){
  if (!_currentProfileDetail) return;
  const name = _currentProfileDetail.name;
  const _ok = await showConfirmDialog({title:t('profile_delete_confirm_title',name),message:t('profile_delete_confirm_message'),confirmLabel:t('delete_title'),danger:true,focusCancel:true});
  if(!_ok) return;
  try {
    await api('/api/profile/delete', { method: 'POST', body: JSON.stringify({ name }) });
    _invalidateKanbanProfileCache();
    _clearProfileDetail();
    await loadProfilesPanel();
    showToast(t('profile_deleted', name));
  } catch (e) { showToast(t('delete_failed') + e.message); }
}

function renderProfileDropdown(data) {
  data = data || {};
  const dd = $('profileDropdown');
  if (!dd) return;
  dd.innerHTML = '';
  const allProfiles = (Array.isArray(data.profiles) ? data.profiles : []).filter(p => p && typeof p.name === 'string');
  const active = (S.activeProfile && allProfiles.some(p => p.name === S.activeProfile))
    ? S.activeProfile
    : (data.active || 'default');
  const profiles = allProfiles.filter(p => p && (p.visible !== false || p.name === active));
  for (const p of profiles) {
    const opt = document.createElement('div');
    opt.className = 'profile-opt' + (p.name === active ? ' active' : '');
    const meta = [];
    if (typeof p.model === 'string' && p.model) meta.push(p.model.split('/').pop());
    if (p.total_skills && p.total_skills > 0) meta.push(t('profile_skill_count', p.total_skills).replace(String(p.total_skills), `${p.enabled_skills} / ${p.total_skills}`));
    const gwDot = `<span class="profile-opt-badge ${p.gateway_running ? 'running' : 'stopped'}"></span>`;
    const checkmark = p.name === active ? ' <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--link)" stroke-width="3" style="vertical-align:-1px"><polyline points="20 6 9 17 4 12"/></svg>' : '';
    const defaultBadge = p.is_default ? ` <span style="opacity:.5;font-weight:400">${esc(t('profile_default_label'))}</span>` : '';
    opt.innerHTML = `<div class="profile-opt-name">${gwDot}${esc(p.name)}${defaultBadge}${checkmark}</div>` +
      (meta.length ? `<div class="profile-opt-meta">${esc(meta.join(' \u00b7 '))}</div>` : '');
    opt.onclick = async () => {
      closeProfileDropdown();
      if (p.name === active) return;
      await switchToProfile(p.name);
    };
    dd.appendChild(opt);
  }
  // Divider + Manage link (hidden in single profile mode)
  if (!data.single_profile_mode) {
    const div = document.createElement('div'); div.className = 'ws-divider'; dd.appendChild(div);
    const mgmt = document.createElement('div'); mgmt.className = 'profile-opt ws-manage';
    mgmt.innerHTML = `${li('settings',12)} ${esc(t('manage_profiles'))}`;
    mgmt.onclick = () => { closeProfileDropdown(); mobileSwitchPanel('profiles'); };
    dd.appendChild(mgmt);
  }
  // Sync titlebar label to the resolved active profile
  const tbl = $('titlebarProfileLabel');
  if (tbl) tbl.textContent = active;
}

function toggleProfileDropdown(e) {
  const dd = $('profileDropdown');
  if (!dd) return;
  if (dd.classList.contains('open')) { closeProfileDropdown(); return; }
  closeWsDropdown(); // close workspace dropdown if open
  if(typeof closeModelDropdown==='function') closeModelDropdown();
  // Track which element triggered the dropdown for positioning
  _profileDropdownTrigger = (e && e.currentTarget) || $('profileChip');
  const openGen = ++_profileDropdownOpenGeneration;
  const cached = _profileDropdownBestCachedData();

  if(cached && !cached.single_profile_mode){
    renderProfileDropdown(cached);
    _openProfileDropdownShell();
  }else{
    _renderProfileDropdownLoading();
    _openProfileDropdownShell();
  }

  _profileDropdownFetchFresh().then(data => {
    if(openGen !== _profileDropdownOpenGeneration) return;
    // In single profile mode, don't show profile dropdown at all
    if (data.single_profile_mode) {
      closeProfileDropdown();
      return;
    }
    renderProfileDropdown(data);
    _openProfileDropdownShell();
  }).catch(e => {
    if(openGen !== _profileDropdownOpenGeneration) return;
    if(cached && !cached.single_profile_mode){
      // Keep the cached menu open; the next click/background refresh will retry.
      return;
    }
    closeProfileDropdown();
    showToast(t('profiles_load_failed'));
  });
}

function closeProfileDropdown() {
  _profileDropdownOpenGeneration++;
  const dd = $('profileDropdown');
  if (dd) dd.classList.remove('open');
  const chip=$('profileChip');
  if(chip) chip.classList.remove('active');
  const tbtn=$('titlebarProfileBtn');
  if(tbtn) tbtn.classList.remove('active');
}
document.addEventListener('click', e => {
  if (!e.target.closest('#profileChipWrap') && !e.target.closest('#titlebarProfileBtn') && !e.target.closest('#profileDropdown')) closeProfileDropdown();
});
window.addEventListener('resize',()=>{
  const dd=$('profileDropdown');
  if(dd&&dd.classList.contains('open')) _positionProfileDropdown();
});

function _openProfileSwitchSessionBrowser(){
  try{
    const isDesktop = (typeof _isDesktopWidth === 'function') ? _isDesktopWidth() : true;
    if(isDesktop){
      if(typeof expandSidebar === 'function') expandSidebar();
      return;
    }
    const sidebar=document.querySelector('.sidebar');
    if(!sidebar)return;
    try{if(typeof _syncMobileSidebarPanelFromMainView==='function')_syncMobileSidebarPanelFromMainView();}catch(_){}
    sidebar.classList.remove('mobile-session-page');
    sidebar.classList.add('mobile-panel-drawer','mobile-open');
  }catch(_){}
}

async function switchToProfile(name) {
  // ── #4671 profile-switch loading-skeleton — FOUR-GUARD CONTRACT ───────────────
  // The skeleton must never be clobbered by the OLD profile's content and must never
  // strand. Four interacting pieces of state cooperate; an edit touching one without
  // the others can silently reopen a clobber/strand window, so keep them in sync:
  //   1. _profileSwitchListEmbargo (sessions.js) — set BEFORE the skeleton, drops EVERY
  //      session-list payload (success + fetch-failure) during the switch window; lifted
  //      immediately before the switch-owned renderSessionList(), on failure-restore, and
  //      in the _switchGen-guarded finally. Closes the "render that STARTS mid-switch,
  //      before the new-profile cookie is set, fetched the old profile" window.
  //   2. _invalidateSessionListRenders() (sessions.js) — bumps _renderSessionListGen +
  //      clears pending/queued at switch start; discards renders already in flight/queued.
  //   3. _sessionListSkeletonActive (sessions.js) — renderSessionListFromCache() bails
  //      while true; cleared ONLY on fresh data (_applySessionListPayload), fetch-error,
  //      and failure-restore — so a bail can't strand the skeleton.
  //   4. _wsTreeGen (workspace.js) — bumped UNCONDITIONALLY here (incl. panel-closed, since
  //      loadDir('.') still runs); loadDir rejects stale /api/list whose gen is superseded.
  //   Plus _profileSwitchGeneration / _switchGen — guards superseded switches so a slower
  //   earlier switch can't clobber a newer one's skeleton/embargo.
  // ──────────────────────────────────────────────────────────────────────────────
  // No-op self-switch guard: bail before showing any loading skeleton if we're
  // already on this profile, so paths like activateCurrentProfile() (which
  // doesn't pre-check) can't flash a skeleton→restore for a click that changes
  // nothing. (#4662 Opus gate)
  if (name && name === S.activeProfile) return true;
  S._pendingSessionToolsets=null;
  // Profile switches are per-client cookie/TLS scoped, so a running stream in
  // the current session can safely continue while this tab moves to another
  // profile. The in-flight session stays attached to its original profile.

  // ── Loading indicator ───────────────────────────────────────────────────
  // Show spinner on the profile chip immediately so the user gets visual
  // feedback while the async switch is in progress.
  const _chip = $('profileChip');
  const _chipLabel = $('profileChipLabel');
  const _titlebarBtn = $('titlebarProfileBtn');
  const _titlebarLabel = $('titlebarProfileLabel');
  const _prevProfileName = S.activeProfile || 'default';
  const _switchGen = ++_profileSwitchGeneration;
  const _openingExistingSidebarSession = !!(typeof _profileSwitchOpeningExistingSession !== 'undefined' && _profileSwitchOpeningExistingSession);
  if (_chip) { _chip.classList.add('switching'); _chip.disabled = true; }
  if (_titlebarBtn) { _titlebarBtn.classList.add('switching'); _titlebarBtn.disabled = true; }
  // Optimistic name update — shows the target name right away
  if (_chipLabel) _chipLabel.textContent = name;
  if (_titlebarLabel) _titlebarLabel.textContent = name;

  // ── Clear stale content + show loading skeletons immediately (#4662) ───────
  // The conversation list and workspace tree still show the PREVIOUS profile's
  // content until their fetches resolve (~1s). Replace them with skeletons the
  // instant the switch begins so the user never stares at the wrong profile's
  // data, and gets consistent loading feedback across the whole surface — not
  // just the spinning chip. The real renders below overwrite these.
  //
  // First dismiss any open inline-rename or row action menu: renderSessionList
  // FromCache() early-returns (no DOM swap) while _renamingSid or
  // _sessionActionMenu is set, which would otherwise strand the skeleton AND
  // defeat the failure-path restore (#4662 Opus gate). A profile switch is a
  // context change where dismissing those transient affordances is correct.
  if (typeof _renamingSid !== 'undefined' && _renamingSid) _renamingSid = null;
  if (typeof closeSessionActionMenu === 'function') closeSessionActionMenu();
  // Determine whether the current session must be replaced instead of being
  // retagged in place. A session with messages/active runtime belongs to the
  // current profile. After the profile-switch POST returns, we also treat an
  // otherwise-empty session whose recorded profile does not match the target
  // profile as replace-only: uploads send S.session.session_id and the backend
  // correctly rejects old-profile sessions under the new profile cookie.
  let sessionInProgress = !!(S.session && (
    (S.messages && S.messages.length > 0) ||
    S.session.active_stream_id ||
    S.session.pending_user_message
  ));
  if (_openingExistingSidebarSession && S.session) {
    // A cross-profile sidebar click is about to load a concrete existing session.
    // Do not create or retag a blank intermediary session in the destination profile.
    sessionInProgress = true;
  }
  const _workspaceVisibleAtStart = typeof _workspacePanelMode !== 'undefined' && _workspacePanelMode !== 'closed';

  // #4671 CORE: the skeleton/embargo/generation setup is INSIDE the try so the
  // _switchGen-guarded finally always lifts the embargo — a throw in this synchronous
  // setup can't leak the embargo and freeze the sidebar (Codex re-gate 4).
  try {
    // Invalidate any in-flight/queued session-list render BEFORE showing the skeleton,
    // so a pre-switch /api/sessions response (old profile's rows, issued before the
    // switch) can't resolve, pass the generation guard, clear the skeleton flag, and
    // paint stale rows. Must precede showSessionListSkeleton().
    if (typeof _invalidateSessionListRenders === 'function') _invalidateSessionListRenders();
    // ...and set the embargo so a render that STARTS during the switch window (after the
    // skeleton, before the new-profile cookie is set) also can't paint the old profile's
    // rows. Cleared right before the switch-owned renderSessionList() and on failure.
    if (typeof _setProfileSwitchListEmbargo === 'function') _setProfileSwitchListEmbargo(true);
    if (typeof showSessionListSkeleton === 'function') showSessionListSkeleton(name);
    // invalidate any in-flight workspace-tree load UNCONDITIONALLY at switch start — even
    // when the panel is closed, loadDir('.') still runs later, and an empty-session switch
    // reuses the same session_id so loadDir's id guard alone can't reject a stale
    // previous-workspace /api/list. Bump here (not only inside the panel-gated
    // showWorkspaceTreeSkeleton) to close the closed-panel race.
    if (typeof bumpWorkspaceTreeGen === 'function') bumpWorkspaceTreeGen();
    if (_workspaceVisibleAtStart && typeof showWorkspaceTreeSkeleton === 'function') showWorkspaceTreeSkeleton();
    // timeoutToast:false — suppress api()'s generic "Request timed out" toast so a
    // superseded or transient-but-eventually-successful switch can't pop a spurious
    // red error while the real switch completes and renders. The catch block below is
    // the single source of truth for switch failure and is gated on _switchGen, so the
    // error surfaces ONLY when the CURRENT switch genuinely fails (@rodboev review, #4662).
    const data = await api('/api/profile/switch', { method: 'POST', body: JSON.stringify({ name }), timeoutToast: false });
    if (_switchGen !== _profileSwitchGeneration) return false;
    S.activeProfile = data.active || name;
    S.activeProfileIsDefault = !!data.is_default;
    if (typeof _resetCronUnreadForProfileSwitch === 'function') {
      _resetCronUnreadForProfileSwitch();
    }
    const targetActiveProfile = S.activeProfile || 'default';
    let sessionProfileMatchesTarget = true;
    if (!sessionInProgress && S.session) {
      const currentSessionProfile = (typeof S.session.profile === 'string' && S.session.profile.trim())
        ? S.session.profile.trim()
        : 'default';
      sessionProfileMatchesTarget = (typeof _profileMatchesActiveProfile === 'function')
        ? _profileMatchesActiveProfile(currentSessionProfile, targetActiveProfile)
        : (currentSessionProfile === targetActiveProfile || (currentSessionProfile === 'default' && !!S.activeProfileIsDefault));
      if (!sessionProfileMatchesTarget) {
        sessionInProgress = true;
      }
    }
    // Reconnect the gateway SSE to the NEW profile's watcher. The backend watcher
    // registry is now profile-keyed (#3629), but this tab's existing EventSource is
    // still subscribed to the PREVIOUS profile's watcher — and the probe-based
    // reattach is gated on `!_gatewaySSE`, which can't fire while the old stream is
    // open. startGatewaySSE() closes the old ES (stopGatewaySSE) and reconnects with
    // the new profile cookie; it self-gates on window._showCliSessions internally.
    if (typeof startGatewaySSE === 'function') startGatewaySSE();

    // Update composer placeholder and title bar while the core profile-switch
    // state is still close to the profile API response.
    if (typeof applyBotName === 'function') applyBotName();

    // ── Model + Workspace ──────────────────────────────────────────────────
    // Apply the profile defaults returned by /api/profile/switch immediately.
    // Refreshing the full model/workspace catalogs is useful, but it should not
    // hold the visible switch animation open.
    if(typeof _clearPersistedModelState==='function') _clearPersistedModelState();
    else localStorage.removeItem('hermes-webui-model');
    _skillsData = null;
    _workspaceList = null;
    if (data.default_model) window._defaultModel = data.default_model;
    if (data.default_model_provider) window._activeProvider = data.default_model_provider;

    // ── Apply model ────────────────────────────────────────────────────────
    if (data.default_model) {
      const sel = $('modelSelect');
      const providerId = data.default_model_provider || window._activeProvider || null;
      const existingDefaultOpt = sel ? Array.from(sel.options).find(o => o.value === data.default_model) : null;
      if (existingDefaultOpt && providerId && !existingDefaultOpt.dataset.provider) {
        existingDefaultOpt.dataset.provider = providerId;
      }
      if (sel && !existingDefaultOpt) {
        const opt = document.createElement('option');
        opt.value = data.default_model;
        opt.textContent = typeof getModelLabel === 'function' ? getModelLabel(data.default_model) : data.default_model;
        opt.dataset.custom = '1';
        if (providerId) opt.dataset.provider = providerId;
        sel.querySelectorAll('option[data-custom]').forEach(o => o.remove());
        sel.appendChild(opt);
      }
      const resolved = _applyModelToDropdown(data.default_model, sel, providerId);
      const modelToUse = resolved || data.default_model;
      const modelState = (typeof _modelStateForSelect==='function')
        ? _modelStateForSelect(sel, modelToUse)
        : {model:modelToUse,model_provider:providerId};
      S._pendingProfileModel = modelToUse;
      S._pendingProfileModelProvider = modelState.model_provider||providerId||null;
      // Only patch the in-memory session model if we're NOT about to replace the session
      if (S.session && !sessionInProgress) {
        S.session.model = modelToUse;
        S.session.model_provider = modelState.model_provider||providerId||null;
        S.session.profile = data.active || name;
      }
    }
    // #3331 follow-up (Codex gate): retag the in-memory session's profile on
    // ANY profile switch, even when the switched-to profile returns no
    // default_model (empty session / model-less profile). Without this the
    // profile chip + project-picker filter keep the stale profile after a
    // switch to a model-less profile. Guarded by !sessionInProgress like the
    // model patch above (don't touch a session about to be replaced).
    if (S.session && !sessionInProgress) {
      S.session.profile = data.active || name;
    }
    if (typeof refreshProfileTransitionReasoningChip === 'function') {
      refreshProfileTransitionReasoningChip(data.default_model, data.default_model_provider);
    }

    // ── Apply workspace ────────────────────────────────────────────────────
    if (data.default_workspace) {
      // Always store the persistent profile default — used for blank-page display
      // and workspace auto-bind throughout the session lifecycle (#804, #823).
      S._profileDefaultWorkspace = data.default_workspace;
      // Also set the one-shot flag consumed by newSession() so the first new
      // session after a profile switch inherits this workspace (#424).
      S._profileSwitchWorkspace = data.default_workspace;

      if (S.session && !sessionInProgress) {
        // Empty session (no messages yet) — safe to update it in place
        try {
          await api('/api/session/update', { method: 'POST', body: JSON.stringify({
            session_id: S.session.session_id,
            workspace: data.default_workspace,
            model: S.session.model,
            model_provider: S.session.model_provider||null,
          })});
          S.session.workspace = data.default_workspace;
        } catch (_) {}
      }
    }

    // ── Session ────────────────────────────────────────────────────────────
    // Keep the all-profiles sidebar scope sticky across profile switches. It is
    // a navigation preference shared by the browser session, not a per-profile flag.
    if (typeof animateNextSessionListRefresh === 'function') animateNextSessionListRefresh();

    if (sessionInProgress && _openingExistingSidebarSession) {
      // The caller will immediately load the clicked session after this profile
      // cookie switch. Avoid creating/retagging an intermediate blank chat.
      const workspaceVisible = typeof _workspacePanelMode !== 'undefined' && _workspacePanelMode !== 'closed';
      if (typeof _setProfileSwitchListEmbargo === 'function') _setProfileSwitchListEmbargo(false);
      await renderSessionList();
      if (_switchGen !== _profileSwitchGeneration) return false;
      if (workspaceVisible && typeof clearWorkspaceTreeSkeleton === 'function') clearWorkspaceTreeSkeleton();
      showToast(t('profile_switched', name));
    } else if (sessionInProgress) {
      // The current session has messages and belongs to the previous profile.
      // Start a new session for the new profile so nothing gets cross-tagged.
      const workspaceVisible = typeof _workspacePanelMode !== 'undefined' && _workspacePanelMode !== 'closed';
      await newSession(false, {awaitWorkspaceLoad: workspaceVisible, worktree: false});
      if (_switchGen !== _profileSwitchGeneration) return false;
      // Keep topbar chips (workspace/profile) in sync after creating the
      // new profile-scoped session.
      syncTopbar();
      // #4671: lift the embargo immediately before the switch-owned render — JS is
      // single-threaded so nothing interleaves between this clear and the call, making
      // this render the first allowed to paint the new profile's rows.
      if (typeof _setProfileSwitchListEmbargo === 'function') _setProfileSwitchListEmbargo(false);
      await renderSessionList();
      // Re-check generation after the awaited list render: a newer switch can be
      // started while renderSessionList() is in flight, and without this guard
      // the superseded switch would clear the newer switch's workspace skeleton
      // and pop a stale toast. Mirrors the no-messages branch guard below.
      // (@rodboev/greptile review, #4662)
      if (_switchGen !== _profileSwitchGeneration) return false;
      if (typeof _openProfileSwitchSessionBrowser === 'function') _openProfileSwitchSessionBrowser();
      // Safety net: if the new session has no workspace, newSession() won't have
      // painted the file tree — clear the up-front skeleton so it can't strand
      // (#4662 Opus gate). No-op when a real tree already rendered.
      if ((!S.session || !S.session.workspace) && typeof clearWorkspaceTreeSkeleton === 'function') {
        clearWorkspaceTreeSkeleton();
      }
      showToast(t('profile_switched_new_conversation', name));
    } else {
      // No messages yet — refresh the list and topbar in place, then the
      // workspace tree. The loading skeletons shown up front (top of this
      // function) already give immediate cross-surface feedback, so we keep the
      // workspace refresh AFTER the stale-switch guard: loadDir() paints the
      // file tree as soon as its fetch resolves with only a session-id check,
      // and empty-session switches reuse the same session id — so starting it
      // before the guard could let an older switch's /api/list paint over a
      // newer one (Codex gate #4662). renderSessionList() is the slow fetch and
      // has its own internal generation guard, so awaiting it first is fine.
      const workspaceVisible = typeof _workspacePanelMode !== 'undefined' && _workspacePanelMode !== 'closed';
      // #4671: lift the embargo immediately before the switch-owned render (see above).
      if (typeof _setProfileSwitchListEmbargo === 'function') _setProfileSwitchListEmbargo(false);
      await renderSessionList();
      if (_switchGen !== _profileSwitchGeneration) return;
      if (typeof _openProfileSwitchSessionBrowser === 'function') _openProfileSwitchSessionBrowser();
      syncTopbar();
      // Refresh workspace file tree so the right panel shows the new
      // profile's workspace, not the previous one (#1214).
      if (S.session && S.session.workspace) {
        const dirLoad = loadDir('.');
        if (workspaceVisible) await dirLoad;
      } else if (typeof clearWorkspaceTreeSkeleton === 'function') {
        // New profile has no bound workspace — clear the up-front skeleton so it
        // doesn't strand (#4662 Opus gate).
        clearWorkspaceTreeSkeleton();
      }
      showToast(t('profile_switched', name));
    }

    await _profileSwitchPanelLoad();
    _refreshProfileSwitchBackground(_switchGen);
    return true;

  } catch (e) {
    // Revert the optimistic name update on error
    if (_switchGen === _profileSwitchGeneration && _chipLabel) _chipLabel.textContent = _prevProfileName;
    if (_switchGen === _profileSwitchGeneration && _titlebarLabel) _titlebarLabel.textContent = _prevProfileName;
    if (_switchGen === _profileSwitchGeneration) showToast(t('switch_failed') + e.message);
    // The switch failed, so we're still on the previous profile and its caches
    // are intact — restore the real list/tree so the loading skeletons we showed
    // up front don't strand. (#4662)
    if (_switchGen === _profileSwitchGeneration) {
      // The switch failed; _allSessions still holds the (still-current) previous
      // profile, so clear the skeleton flag and re-render to restore the real list
      // rather than strand the up-front skeleton (#4671). Lift the embargo too so the
      // restore render (and subsequent normal renders) can paint.
      if (typeof _setProfileSwitchListEmbargo === 'function') _setProfileSwitchListEmbargo(false);
      _sessionListSkeletonActive = false;
      if (typeof renderSessionListFromCache === 'function') renderSessionListFromCache();
      if (_workspaceVisibleAtStart && S.session && S.session.workspace && typeof loadDir === 'function') {
        loadDir('.');
      } else if (_workspaceVisibleAtStart && typeof clearWorkspaceTreeSkeleton === 'function') {
        // No workspace to restore on the (still-current) previous profile —
        // clear the up-front workspace skeleton so it doesn't strand on a switch
        // failure, mirroring the success-path no-workspace handling (#4662).
        clearWorkspaceTreeSkeleton();
      }
    }
    return false;
  } finally {
    // Always remove loading indicator regardless of success or failure
    if (_switchGen === _profileSwitchGeneration && _chip) { _chip.classList.remove('switching'); _chip.disabled = false; }
    if (_switchGen === _profileSwitchGeneration && _titlebarBtn) { _titlebarBtn.classList.remove('switching'); _titlebarBtn.disabled = false; }
    // #4671 safety net: guarantee the session-list embargo is lifted on EVERY exit of the
    // current switch (success paths clear it before their authoritative render; this covers
    // early-returns/throws between skeleton-show and those clears so it can't freeze the
    // sidebar). Guarded by _switchGen so a superseded switch can't lift a newer switch's embargo.
    if (_switchGen === _profileSwitchGeneration && typeof _setProfileSwitchListEmbargo === 'function') {
      _setProfileSwitchListEmbargo(false);
    }
  }
}

function openProfileCreate(){
  if (typeof switchPanel === 'function' && _currentPanel !== 'profiles') switchPanel('profiles');
  _profilePreFormDetail = _currentProfileDetail ? { ..._currentProfileDetail } : null;
  _profileMode = 'create';
  _renderProfileForm();
}

function _renderProfileForm(){
  const title = $('profileDetailTitle');
  const body = $('profileDetailBody');
  const empty = $('profileDetailEmpty');
  if (!title || !body) return;
  title.textContent = t('new_profile');
  body.innerHTML = `
    <div class="main-view-content">
      <form class="detail-form" onsubmit="event.preventDefault(); saveProfileForm();">
        <div class="detail-form-row">
          <label for="profileFormName">${esc(t('profile_name_label') || 'Name')}</label>
          <input type="text" id="profileFormName" placeholder="${esc(t('profile_name_placeholder') || 'lowercase, a-z 0-9 hyphens')}" autocomplete="off" autocapitalize="none" autocorrect="off" spellcheck="false" required>
          <div class="detail-form-hint">${esc(t('profile_name_rule') || 'Lowercase letters, numbers, hyphens, underscores only.')}</div>
        </div>
        <div class="detail-form-row">
          <label class="detail-form-check" for="profileFormClone">
            <input type="checkbox" id="profileFormClone"> <span>${esc(t('profile_clone_label') || 'Clone config from active profile')}</span>
          </label>
        </div>
        <div class="detail-form-row">
          <label for="profileFormModel">${esc(t('profile_model_label') || 'Model / provider')}</label>
          <select id="profileFormModel"></select>
          <div class="detail-form-hint">${esc(t('profile_model_hint') || 'Choose from configured providers and models for this new profile.')}</div>
        </div>
        <div class="detail-form-row">
          <label for="profileFormReasoning">${esc(t('profile_reasoning_label') || 'Reasoning effort')}</label>
          <select id="profileFormReasoning">
            <option value="">${esc(t('profile_reasoning_use_default') || 'Use provider default')}</option>
            ${REASONING_EFFORT_LEVELS.map(level => `<option value="${esc(level)}">${esc(_formatReasoningEffortLabel(level))}</option>`).join('')}
          </select>
          <div class="detail-form-hint">${esc(t('profile_reasoning_hint') || 'Applied automatically to the composer whenever this profile is active.')}</div>
        </div>
        <div class="detail-form-row">
          <label for="profileFormBaseUrl">${esc(t('profile_base_url_label') || 'Base URL')}</label>
          <input type="text" id="profileFormBaseUrl" placeholder="${esc(t('profile_base_url_placeholder') || 'Optional, e.g. http://localhost:11434')}" autocomplete="off" autocapitalize="none" autocorrect="off" spellcheck="false">
        </div>
        <div class="detail-form-row">
          <label for="profileFormApiKey">${esc(t('profile_api_key_label') || 'API key')}</label>
          <input type="password" id="profileFormApiKey" placeholder="${esc(t('profile_api_key_placeholder') || 'Optional')}" autocomplete="off">
        </div>
        <div id="profileFormError" class="detail-form-error" style="display:none"></div>
      </form>
    </div>`;
  body.style.display = '';
  if (empty) empty.style.display = 'none';
  _setProfileHeaderButtons('create');
  const n = $('profileFormName');
  if (n) n.focus();
  _populateProfileFormModelSelect();
}

async function _populateProfileFormModelSelect(){
  const sel = $('profileFormModel');
  if (!sel) return;
  sel.innerHTML = `<option value="">${esc(t('profile_model_use_default') || 'Use active profile default')}</option>`;
  try {
    const data = await api('/api/models');
    const groups = (Array.isArray(data && data.groups) && data.groups.length) ? data.groups : [];
    for (const g of groups) {
      const og = document.createElement('optgroup');
      og.label = g.provider || g.provider_id || 'Configured';
      if (g.provider_id) og.dataset.provider = g.provider_id;
      for (const m of [...(Array.isArray(g.models) ? g.models : []), ...(Array.isArray(g.extra_models) ? g.extra_models : [])]) {
        if (!m || !m.id) continue;
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = m.label || m.id;
        og.appendChild(opt);
      }
      if (og.children.length) sel.appendChild(og);
    }
    if (data && data.default_model && typeof _applyModelToDropdown === 'function') {
      _applyModelToDropdown(data.default_model, sel, data.active_provider || window._activeProvider || null);
    }
  } catch (e) {
    console.warn('Failed to load profile model picker:', e.message);
  }
}

function cancelProfileForm(){
  if (_profilePreFormDetail) {
    const snap = _profilePreFormDetail;
    _profilePreFormDetail = null;
    const activeName = _profilesCache ? _profilesCache.active : null;
    _renderProfileDetail(snap, activeName);
    return;
  }
  _clearProfileDetail();
}

async function saveProfileForm(){
  const nameEl = $('profileFormName');
  const cloneEl = $('profileFormClone');
  const modelEl = $('profileFormModel');
  const reasoningEl = $('profileFormReasoning');
  const baseEl = $('profileFormBaseUrl');
  const apiKeyEl = $('profileFormApiKey');
  const errEl = $('profileFormError');
  if (!nameEl || !errEl) return;
  const name = (nameEl.value || '').trim().toLowerCase();
  const cloneConfig = !!(cloneEl && cloneEl.checked);
  errEl.style.display = 'none';
  if (!name) { errEl.textContent = t('name_required'); errEl.style.display = ''; return; }
  if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(name)) { errEl.textContent = t('profile_name_rule'); errEl.style.display = ''; return; }
  const baseUrl = (baseEl ? (baseEl.value || '') : '').trim();
  const apiKey = (apiKeyEl ? (apiKeyEl.value || '') : '').trim();
  if (baseUrl && !/^https?:\/\//.test(baseUrl)) { errEl.textContent = t('profile_base_url_rule'); errEl.style.display = ''; return; }
  try {
    const payload = { name, clone_config: cloneConfig };
    const selectedModel = modelEl ? (modelEl.value || '').trim() : '';
    if (selectedModel) {
      const modelState = (typeof _modelStateForSelect === 'function')
        ? _modelStateForSelect(modelEl, selectedModel)
        : { model: selectedModel, model_provider: null };
      if (modelState.model) payload.default_model = modelState.model;
      if (modelState.model_provider) payload.model_provider = modelState.model_provider;
    }
    const reasoningEffort = reasoningEl ? (reasoningEl.value || '').trim() : '';
    if (reasoningEffort) payload.reasoning_effort = reasoningEffort;
    if (baseUrl) payload.base_url = baseUrl;
    if (apiKey) payload.api_key = apiKey;
    await api('/api/profile/create', { method: 'POST', body: JSON.stringify(payload) });
    _invalidateKanbanProfileCache();
    _profilePreFormDetail = null;
    await loadProfilesPanel();
    showToast(t('profile_created', name));
    openProfileDetail(name);
  } catch (e) {
    errEl.textContent = e.message || t('create_failed');
    errEl.style.display = '';
  }
}

// Back-compat
const submitProfileCreate = saveProfileForm;
function toggleProfileForm(){ openProfileCreate();
}

async function deleteProfile(name) {
  const _delProf=await showConfirmDialog({title:t('profile_delete_confirm_title',name),message:t('profile_delete_confirm_message'),confirmLabel:t('delete_title'),danger:true,focusCancel:true});
  if(!_delProf) return;
  try {
    await api('/api/profile/delete', { method: 'POST', body: JSON.stringify({ name }) });
    _invalidateKanbanProfileCache();
    await loadProfilesPanel();
    showToast(t('profile_deleted', name));
  } catch (e) { showToast(t('delete_failed') + e.message); }
}

// ── Memory panel ──
async function loadMemory(force) {
  const panel = $('memoryPanel');
  try {
    const memoryUrl = S.session && S.session.session_id
      ? `/api/memory?session_id=${encodeURIComponent(S.session.session_id)}`
      : '/api/memory';
    const data = await api(memoryUrl);
    _memoryData = data;
    if (_currentMemorySection === 'external_notes' && !data.external_notes_enabled) {
      _currentMemorySection = null;
    }
    if (_currentMemorySection === 'external_notes') {
      await loadNotesSources(!!force);
    }
    if (panel) {
      panel.innerHTML = '';
      for (const s of MEMORY_SECTIONS) {
        if (s.key === 'external_notes' && !_memoryData.external_notes_enabled) continue;
        const el = document.createElement('button');
        el.type = 'button';
        el.className = 'side-menu-item';
        if (_currentMemorySection === s.key) el.classList.add('active');
        el.innerHTML = `${li(s.iconKey,16)}<span>${esc(_memorySectionLabel(s))}</span>`;
        const sectionPath = _memorySectionPath(s.key);
        if (sectionPath) el.title = sectionPath;
        el.onclick = () => openMemorySection(s.key, el);
        panel.appendChild(el);
      }
    }
    if (_currentMemorySection && _memoryMode !== 'edit') {
      _renderMemoryDetail(_currentMemorySection);
    }
  } catch(e) {
    if (panel) panel.innerHTML = `<div style="padding:12px;color:var(--accent);font-size:12px">${esc(t('error_prefix'))}${esc(e.message)}</div>`;
  }
}

// ── Knowledge Browser panel (read-only list/read/search) ──
// See docs/HERMES_STUDIO_PARITY_PLAN.md, "Knowledge Browser".

const KNOWLEDGE_TYPE_ICONS = {
  memory: 'brain', user: 'user', soul: 'sparkles', saved_prompt: 'message-square', prompt_file: 'file-text',
};
const KNOWLEDGE_TYPE_LABEL_KEYS = {
  memory: 'knowledge_type_memory', user: 'knowledge_type_user', soul: 'knowledge_type_soul',
  saved_prompt: 'knowledge_type_saved_prompt', prompt_file: 'knowledge_type_prompt_file',
};

function _knowledgeTypeLabel(type) {
  return t(KNOWLEDGE_TYPE_LABEL_KEYS[type] || 'knowledge_type_memory');
}

async function loadKnowledgeItems(force) {
  const list = $('knowledgeList');
  if (list && (force || !_knowledgeItems)) list.innerHTML = `<div style="padding:12px;color:var(--muted);font-size:12px" data-i18n="loading">${esc(t('loading'))}</div>`;
  try {
    const data = await api('/api/knowledge/list');
    _knowledgeItems = data.items || [];
    _knowledgeSearchResults = null;
    renderKnowledgeItems();
  } catch(e) {
    if (list) list.innerHTML = `<div style="padding:12px;color:var(--accent);font-size:12px">${esc(t('error_prefix'))}${esc(e.message)}</div>`;
  }
}

function renderKnowledgeItems() {
  const list = $('knowledgeList');
  if (!list) return;
  const rows = _knowledgeSearchResults !== null ? _knowledgeSearchResults : (_knowledgeItems || []);
  if (!rows.length) {
    list.innerHTML = `<div style="padding:12px;color:var(--muted);font-size:12px">${esc(_knowledgeSearchResults !== null ? t('knowledge_no_match') : t('knowledge_empty_title'))}</div>`;
    return;
  }
  list.innerHTML = rows.map(item => `<div class="skill-item knowledge-item${item.id === _currentKnowledgeItemId ? ' active' : ''}" onclick="openKnowledgeItem('${esc(item.id)}')">
    <span class="knowledge-type-badge" title="${esc(_knowledgeTypeLabel(item.type))}">${li(KNOWLEDGE_TYPE_ICONS[item.type] || 'file-text', 14)}</span>
    <span class="skill-name">${esc(item.title || '')}</span>
    <span class="skill-desc">${esc(item.snippet || '')}</span>
  </div>`).join('');
}

function searchKnowledgeItems() {
  const q = ($('knowledgeSearch') || {}).value || '';
  clearTimeout(_knowledgeSearchDebounce);
  _knowledgeSearchDebounce = setTimeout(async () => {
    const seq = ++_knowledgeSearchSeq;
    if (!q.trim()) {
      _knowledgeSearchResults = null;
      renderKnowledgeItems();
      return;
    }
    try {
      const data = await api(`/api/knowledge/search?q=${encodeURIComponent(q)}`);
      if (seq !== _knowledgeSearchSeq) return; // a newer search superseded this one
      _knowledgeSearchResults = data.results || [];
      renderKnowledgeItems();
    } catch(e) {
      if (seq !== _knowledgeSearchSeq) return;
      _knowledgeSearchResults = [];
      renderKnowledgeItems();
    }
  }, 250);
}

async function openKnowledgeItem(id) {
  _currentKnowledgeItemId = id;
  renderKnowledgeItems();
  try {
    const data = await api(`/api/knowledge/read?id=${encodeURIComponent(id)}`);
    _renderKnowledgeDetail(data.item);
  } catch(e) {
    _renderKnowledgeDetail(null, e.message);
  }
  if (typeof _isDesktopWidth === 'function' && !_isDesktopWidth()) {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) { sidebar.classList.remove('mobile-panel-drawer', 'mobile-open'); }
  }
}

function _renderKnowledgeDetail(item, errorMessage) {
  const titleEl = $('knowledgeDetailTitle');
  const bodyEl = $('knowledgeDetailBody');
  const emptyEl = $('knowledgeDetailEmpty');
  if (!item) {
    if (titleEl) titleEl.textContent = '';
    if (bodyEl) bodyEl.style.display = 'none';
    if (emptyEl) {
      emptyEl.style.display = 'flex';
      if (errorMessage) emptyEl.querySelector('.main-view-empty-sub').textContent = errorMessage;
    }
    return;
  }
  if (titleEl) titleEl.textContent = item.title || _knowledgeTypeLabel(item.type);
  if (emptyEl) emptyEl.style.display = 'none';
  if (bodyEl) {
    bodyEl.style.display = 'block';
    bodyEl.innerHTML = `
      <div class="knowledge-detail-meta">
        <span class="knowledge-type-badge">${li(KNOWLEDGE_TYPE_ICONS[item.type] || 'file-text', 14)}<span>${esc(_knowledgeTypeLabel(item.type))}</span></span>
        ${item.source_path ? `<span class="knowledge-source-path" title="${esc(item.source_path)}">${esc(item.source_path)}</span>` : ''}
      </div>
      <pre class="knowledge-detail-content">${esc(item.content || '')}</pre>
    `;
  }
}

// Drag and drop
const wrap=$('composerWrap');let dragCounter=0;
document.addEventListener('dragover',e=>e.preventDefault());
document.addEventListener('dragenter',e=>{e.preventDefault();
  const isWsPath=e.dataTransfer.types.includes('application/ws-path');
  const isFiles=e.dataTransfer.types.includes('Files');
  if(isFiles||isWsPath){
    dragCounter++;
    // Context-aware hint: a workspace-file drag inserts an @path reference;
    // an OS-file drag attaches the file to the message.
    const hint=$('dropHintText');
    if(hint) hint.textContent=isWsPath?'Drop to insert workspace reference':'Drop files to attach';
    wrap.classList.add('drag-over');
  }
});
document.addEventListener('dragleave',e=>{dragCounter--;if(dragCounter<=0){dragCounter=0;wrap.classList.remove('drag-over');}});
document.addEventListener('drop',e=>{
  e.preventDefault();dragCounter=0;wrap.classList.remove('drag-over');
  // Workspace file/folder drag → insert @path reference into composer
  const wsPath=e.dataTransfer.getData('application/ws-path');
  if(wsPath){
    const msgEl=$('msg');
    if(msgEl){
      const start=msgEl.selectionStart;const end=msgEl.selectionEnd;
      const val=msgEl.value;
      const prefix=start>0&&!val[start-1].match(/\s/)?' ':'';
      const insert=prefix+'@'+wsPath+' ';
      msgEl.value=val.slice(0,start)+insert+val.slice(end);
      msgEl.selectionStart=msgEl.selectionEnd=start+insert.length;
      msgEl.focus();
    }
    return;
  }
  // OS file drag → attach files
  const files=Array.from(e.dataTransfer.files);
  if(files.length){addFiles(files);$('msg').focus();}
});

// ── Settings panel ───────────────────────────────────────────────────────────

let _settingsDirty = false;
let _settingsThemeOnOpen = null; // track theme at open time for discard revert
let _settingsSkinOnOpen = null; // track skin at open time for discard revert
let _settingsFontSizeOnOpen = null; // track font size at open time for discard revert
let _settingsHermesDefaultModelOnOpen = '';
let _settingsHermesDefaultModelProviderOnOpen = null;
let _settingsSection = 'conversation';
let _currentSettingsSection = 'conversation';
let _settingsIndex = null;
let _settingsIndexPromise = null;
let _settingsSearchSeq = 0;
let _extensionsStatusData = null;
let _extensionsSidecarMonitorSeq = 0;
let _extensionsGalleryData = null;
let _extensionsGalleryLoaded = false;
let _extensionsActiveTab = 'gallery';
let _settingsSearchDismissListenerRegistered = false;
let _settingsAppearanceAutosaveTimer = null;
let _settingsAppearanceAutosaveRetryPayload = null;
let _settingsPreferencesAutosaveTimer = null;
let _settingsPreferencesAutosaveRetryPayload = null;

// ── Sidebar tab visibility/order ────────────────────────────────────────────
const _ALWAYS_VISIBLE_TABS = new Set(['chat','settings']);
const _HIDDEN_TABS_LS_KEY = 'hermes-webui-hidden-tabs';
const _TAB_ORDER_LS_KEY = 'hermes-webui-tab-order';
const _COMPOSER_CONTROL_ORDER_LS_KEY = 'hermes-webui-composer-control-order';
let _tabVisibilityDragSuppressUntil = 0;
let _composerControlDragSuppressUntil = 0;
let _composerControlDraggingKey = '';

function _sanitizeTabPanelList(panels){
  if(!Array.isArray(panels)) return [];
  var out=[];
  panels.forEach(function(panel){
    if(typeof panel!=='string') return;
    panel=panel.trim();
    if(!panel||_ALWAYS_VISIBLE_TABS.has(panel)) return;
    if(out.indexOf(panel)===-1) out.push(panel);
  });
  return out;
}

function _getHiddenTabs(){
  try{var h=localStorage.getItem(_HIDDEN_TABS_LS_KEY);if(h)return _sanitizeTabPanelList(JSON.parse(h));}catch(e){}
  return[];
}

function _setHiddenTabs(panels){
  try{localStorage.setItem(_HIDDEN_TABS_LS_KEY,JSON.stringify(_sanitizeTabPanelList(panels)));}catch(e){}
}

function _getTabOrder(){
  try{var h=localStorage.getItem(_TAB_ORDER_LS_KEY);if(h)return _sanitizeTabPanelList(JSON.parse(h));}catch(e){}
  return[];
}

function _setTabOrder(panels){
  try{localStorage.setItem(_TAB_ORDER_LS_KEY,JSON.stringify(_sanitizeTabPanelList(panels)));}catch(e){}
}

function _availableSidebarPanels(){
  var out=[];
  var tabs=document.querySelectorAll('.rail .rail-btn.nav-tab[data-panel], .sidebar-nav .nav-tab[data-panel]');
  tabs.forEach(function(tab){
    var panel=tab.dataset.panel;
    if(!panel||_ALWAYS_VISIBLE_TABS.has(panel)) return;
    if(tab.classList.contains('dashboard-link')||tab.hasAttribute('data-dashboard-link')) return;
    if(out.indexOf(panel)===-1) out.push(panel);
  });
  return out;
}

function _orderedSidebarPanels(order){
  var available=_availableSidebarPanels();
  var requested=_sanitizeTabPanelList(Array.isArray(order)?order:_getTabOrder());
  var out=[];
  requested.forEach(function(panel){ if(available.indexOf(panel)!==-1&&out.indexOf(panel)===-1) out.push(panel); });
  available.forEach(function(panel){ if(out.indexOf(panel)===-1) out.push(panel); });
  return out;
}

function _dashboardPanelMode(){
  var modeEl=$('settingsDashboardMode');
  var mode=modeEl&&modeEl.value;
  return mode==='never'||mode==='always'||mode==='auto'?mode:'auto';
}

function _isDashboardChipOn(){
  return _dashboardPanelMode()!=='never';
}

function _renderDashboardVisibilityChip(container){
  if(!container)return null;
  var chip=document.createElement('button');
  chip.type='button';
  chip.className='tab-visibility-chip';
  chip.setAttribute('data-tab-panel','__hermes_dashboard__');
  chip.setAttribute('role','switch');
  var isOn=_isDashboardChipOn();
  chip.setAttribute('aria-checked',isOn?'true':'false');
  if(!isOn) chip.classList.add('chip-off');
  chip.textContent=typeof t==='function'?t('tab_dashboard'):'Dashboard';
  chip.onclick=function(){
    if(Date.now()<_tabVisibilityDragSuppressUntil)return;
    _toggleDashboardVisibilityChip();
  };
  return chip;
}

function _applyTabOrder(order){
  var ordered=_orderedSidebarPanels(order);
  ['.rail','.sidebar-nav'].forEach(function(selector){
    var container=document.querySelector(selector);
    if(!container) return;
    var anchor=Array.prototype.find.call(container.children,function(child){
      if(child.classList&&child.classList.contains('rail-spacer')) return true;
      if(child.classList&&child.classList.contains('dashboard-link')) return true;
      if(child.hasAttribute&&child.hasAttribute('data-dashboard-link')) return true;
      return child.dataset&&child.dataset.panel==='settings';
    });
    ordered.forEach(function(panel){
      var node=container.querySelector('.nav-tab[data-panel="'+panel+'"]');
      if(node) container.insertBefore(node,anchor||null);
    });
  });
}

function _applyTabVisibility(hidden){
  hidden=_sanitizeTabPanelList(hidden);
  _applyTabOrder(_getTabOrder());
  // Hide/unhide all [data-panel] elements (sidebar-nav buttons + rail buttons)
  document.querySelectorAll('[data-panel]').forEach(function(el){
    var panel=el.dataset.panel;
    if(!panel)return;
    var shouldHide=hidden.indexOf(panel)!==-1;
    // Never hide always-visible panels (chat, settings) even if present in hidden_tabs
    if(_ALWAYS_VISIBLE_TABS.has(panel)) shouldHide=false;
    el.classList.toggle('nav-tab-hidden',shouldHide);
  });
  // If the currently active tab is hidden, switch to chat
  var activeRail=document.querySelector('.rail .rail-btn.nav-tab.active[data-panel]');
  var activeSidebar=document.querySelector('.sidebar-nav .nav-tab.active[data-panel]');
  var activeEl=activeRail||activeSidebar;
  if(activeEl&&activeEl.classList.contains('nav-tab-hidden')){
    if(typeof switchPanel==='function') switchPanel('chat');
  }
}

function _renderTabVisibilityChips(){
  var container=$('tabVisibilityChips');
  if(!container)return;
  var hidden=_getHiddenTabs();
  var panels=_orderedSidebarPanels();
  container.innerHTML='';
  panels.forEach(function(panel){
    var tab=document.querySelector('.rail .rail-btn.nav-tab[data-panel="'+panel+'"]')
      ||document.querySelector('.sidebar-nav .nav-tab[data-panel="'+panel+'"]');
    var label=(tab&&(tab.dataset.tooltip||tab.dataset.label))||panel;
    // Capitalize first letter
    label=label.charAt(0).toUpperCase()+label.slice(1);
    var chip=document.createElement('button');
    chip.type='button';
    chip.className='tab-visibility-chip';
    var isOff=hidden.indexOf(panel)!==-1;
    if(isOff)chip.classList.add('chip-off');
    chip.textContent=label;
    chip.setAttribute('data-tab-panel',panel);
    chip.setAttribute('draggable','true');
    // Use role="switch" + aria-checked instead of aria-pressed so screen
    // readers narrate "Tasks switch on/off" (matches user mental model) rather
    // than "Tasks toggle button pressed/not-pressed" (where the polarity is
    // confusing because chip-off looks like the "off" state).
    chip.setAttribute('role','switch');
    chip.setAttribute('aria-checked',isOff?'false':'true');
    chip.onclick=function(){
      if(Date.now()<_tabVisibilityDragSuppressUntil)return;
      _toggleTabVisibilityChip(panel);
    };
    _wireTabChipDrag(chip,panel);
    container.appendChild(chip);
  });
  var dashboardChip=_renderDashboardVisibilityChip(container);
  if(dashboardChip) container.appendChild(dashboardChip);
}

function _wireTabChipDrag(chip,panel){
  if(!chip)return;
  chip.addEventListener('dragstart',function(e){
    chip.classList.add('dragging');
    if(e.dataTransfer){
      e.dataTransfer.effectAllowed='move';
      e.dataTransfer.setData('text/plain',panel);
    }
  });
  chip.addEventListener('dragend',function(){chip.classList.remove('dragging');});
  chip.addEventListener('dragover',function(e){e.preventDefault();chip.classList.add('drag-over');if(e.dataTransfer)e.dataTransfer.dropEffect='move';});
  chip.addEventListener('dragleave',function(){chip.classList.remove('drag-over');});
  chip.addEventListener('drop',function(e){_handleTabVisibilityChipDrop(e,panel);});
}

function _moveTabOrderPanel(sourcePanel,targetPanel){
  if(!sourcePanel||!targetPanel||sourcePanel===targetPanel) return false;
  var order=_orderedSidebarPanels();
  var from=order.indexOf(sourcePanel);
  var to=order.indexOf(targetPanel);
  if(from===-1||to===-1) return false;
  order.splice(from,1);
  order.splice(to,0,sourcePanel);
  _setTabOrder(order);
  _applyTabOrder(order);
  _renderTabVisibilityChips();
  _scheduleAppearanceAutosave();
  return true;
}

function _handleTabVisibilityChipDrop(e,targetPanel){
  if(e){e.preventDefault();e.stopPropagation();}
  document.querySelectorAll('.tab-visibility-chip.drag-over').forEach(function(el){el.classList.remove('drag-over');});
  var sourcePanel=e&&e.dataTransfer?e.dataTransfer.getData('text/plain'):'';
  if(_moveTabOrderPanel(sourcePanel,targetPanel)) _tabVisibilityDragSuppressUntil=Date.now()+250;
}

function _toggleTabVisibilityChip(panel){
  if(_ALWAYS_VISIBLE_TABS.has(panel))return;
  var hidden=_getHiddenTabs();
  var idx=hidden.indexOf(panel);
  if(idx!==-1){
    hidden.splice(idx,1);
  }else{
    hidden.push(panel);
  }
  _setHiddenTabs(hidden);
  _applyTabVisibility(hidden);
  _renderTabVisibilityChips();
  _scheduleAppearanceAutosave();
}

function _toggleDashboardVisibilityChip(){
  var modeEl=$('settingsDashboardMode');
  if(!modeEl||typeof saveDashboardSettings!=='function') return;
  var currentMode=_dashboardPanelMode();
  var nextMode=currentMode==='never'
    ? (typeof _getDashboardChipRestoreMode==='function' ? _getDashboardChipRestoreMode() : 'auto')
    : 'never';
  var previousMode=currentMode;
  modeEl.value=nextMode;
  Promise.resolve(saveDashboardSettings({raiseOnError:true})).catch(function(){
    modeEl.value=previousMode;
    if(typeof _renderTabVisibilityChips==='function') _renderTabVisibilityChips();
  });
}

function _ensureComposerControlVisibilityState(settings){
  const fromSettings=(typeof _composerControlVisibilityFromSettings==='function')
    ? _composerControlVisibilityFromSettings(settings||{})
    : {};
  if(!window._composerControlVisibility) window._composerControlVisibility={};
  Object.assign(window._composerControlVisibility, fromSettings);
}

function _composerControlDefsForSettings(){
  const baseDefs=Array.isArray(window._COMPOSER_CONTROL_TOGGLE_DEFS)?window._COMPOSER_CONTROL_TOGGLE_DEFS:[];
  const situationalDefs=Array.isArray(window._COMPOSER_SITUATIONAL_CONTROL_TOGGLE_DEFS)?window._COMPOSER_SITUATIONAL_CONTROL_TOGGLE_DEFS:[];
  return baseDefs.concat(situationalDefs);
}

function _getComposerControlOrder(){
  if(Array.isArray(window._composerControlOrder)){
    return typeof window._sanitizeComposerControlOrder==='function'
      ? window._sanitizeComposerControlOrder(window._composerControlOrder)
      : window._composerControlOrder.slice();
  }
  try{
    const raw=localStorage.getItem(_COMPOSER_CONTROL_ORDER_LS_KEY);
    if(raw){
      const parsed=JSON.parse(raw);
      if(typeof window._sanitizeComposerControlOrder==='function') return window._sanitizeComposerControlOrder(parsed);
      if(Array.isArray(parsed)) return parsed.filter(key=>typeof key==='string');
    }
  }catch(e){}
  return [];
}

function _setComposerControlOrder(order){
  const sanitized=typeof window._sanitizeComposerControlOrder==='function'
    ? window._sanitizeComposerControlOrder(order)
    : (Array.isArray(order)?order.filter(key=>typeof key==='string') : []);
  window._composerControlOrder=sanitized;
  try{localStorage.setItem(_COMPOSER_CONTROL_ORDER_LS_KEY,JSON.stringify(sanitized));}catch(e){}
  return sanitized;
}

function _orderedComposerControlDefsForSettings(defs){
  defs=Array.isArray(defs)?defs:[];
  const byKey=new Map(defs.map(def=>[def.key,def]));
  const out=[];
  _getComposerControlOrder().forEach(function(key){
    if(byKey.has(key)) out.push(byKey.get(key));
  });
  defs.forEach(function(def){if(out.indexOf(def)===-1) out.push(def);});
  return out;
}

function _composerControlOrderGroupKey(key){
  const def=_composerControlDefsForSettings().find(item=>item&&item.key===key);
  return def&&def.orderGroup?def.orderGroup:'';
}

function _composerControlDropAllowed(sourceKey,targetKey){
  if(!sourceKey||!targetKey||sourceKey===targetKey) return false;
  const sourceGroup=_composerControlOrderGroupKey(sourceKey);
  const targetGroup=_composerControlOrderGroupKey(targetKey);
  return !!sourceGroup&&sourceGroup===targetGroup;
}

function _clearComposerControlDragOver(){
  document.querySelectorAll('[data-composer-control-key].drag-over').forEach(function(el){el.classList.remove('drag-over');});
}

function _moveComposerControlOrderKey(sourceKey,targetKey){
  if(!_composerControlDropAllowed(sourceKey,targetKey)) return false;
  const order=_orderedComposerControlDefsForSettings(_composerControlDefsForSettings()).map(def=>def.key);
  const from=order.indexOf(sourceKey);
  const to=order.indexOf(targetKey);
  if(from===-1||to===-1) return false;
  order.splice(from,1);
  order.splice(to,0,sourceKey);
  const next=_setComposerControlOrder(order);
  if(typeof window._applyComposerControlOrder==='function') window._applyComposerControlOrder(next);
  _renderComposerControlChips();
  _renderComposerSituationalControlChips();
  _scheduleAppearanceAutosave();
  return true;
}

function _handleComposerControlChipDrop(e,targetKey){
  if(e){e.preventDefault();e.stopPropagation();}
  _clearComposerControlDragOver();
  const sourceKey=e&&e.dataTransfer?e.dataTransfer.getData('text/plain'):_composerControlDraggingKey;
  if(_moveComposerControlOrderKey(sourceKey,targetKey)) _composerControlDragSuppressUntil=Date.now()+250;
  _composerControlDraggingKey='';
}

function _wireComposerControlChipDrag(chip,key){
  if(!chip)return;
  chip.setAttribute('data-composer-control-key',key);
  chip.setAttribute('draggable','true');
  chip.addEventListener('dragstart',function(e){
    _composerControlDraggingKey=key;
    chip.classList.add('dragging');
    if(e.dataTransfer){
      e.dataTransfer.effectAllowed='move';
      e.dataTransfer.setData('text/plain',key);
    }
  });
  chip.addEventListener('dragend',function(){
    chip.classList.remove('dragging');
    _clearComposerControlDragOver();
    _composerControlDraggingKey='';
  });
  chip.addEventListener('dragover',function(e){
    const sourceKey=_composerControlDraggingKey;
    if(!_composerControlDropAllowed(sourceKey,key)){
      if(e.dataTransfer)e.dataTransfer.dropEffect='none';
      return;
    }
    e.preventDefault();
    chip.classList.add('drag-over');
    if(e.dataTransfer)e.dataTransfer.dropEffect='move';
  });
  chip.addEventListener('dragleave',function(){chip.classList.remove('drag-over');});
  chip.addEventListener('drop',function(e){_handleComposerControlChipDrop(e,key);});
}

function _composerControlVisibilityPayload(){
  const payload={};
  const defs=_composerControlDefsForSettings();
  const state=window._composerControlVisibility||{};
  defs.forEach(function(def){payload[def.key]=!!state[def.key];});
  return payload;
}

function _toggleComposerControlChip(key){
  if(!window._composerControlVisibility) window._composerControlVisibility={};
  window._composerControlVisibility[key]=!window._composerControlVisibility[key];
  if(typeof _renderComposerControlChips==='function') _renderComposerControlChips();
  if(typeof _renderComposerSituationalControlChips==='function') _renderComposerSituationalControlChips();
  if(typeof _applyComposerFooterVisibilitySettings==='function') _applyComposerFooterVisibilitySettings();
  _scheduleAppearanceAutosave();
}

function _composerControlChipLabel(def){
  if(!def) return '';
  if(def.labelKey&&typeof t==='function'){
    const localized=t(def.labelKey);
    if(typeof localized==='string'&&localized&&localized!==def.labelKey) return localized;
  }
  return def.label||'';
}

function _renderComposerControlChips(){
  const container=$('composerControlsChips');
  if(!container) return;
  const defs=Array.isArray(window._COMPOSER_CONTROL_TOGGLE_DEFS)?window._COMPOSER_CONTROL_TOGGLE_DEFS:[];
  const state=window._composerControlVisibility||{};
  container.innerHTML='';
  _orderedComposerControlDefsForSettings(defs).forEach(function(def){
    const chip=document.createElement('button');
    chip.type='button';
    chip.className='tab-visibility-chip';
    const hidden=!!state[def.key];
    if(hidden) chip.classList.add('chip-off');
    chip.textContent=_composerControlChipLabel(def);
    chip.setAttribute('role','switch');
    chip.setAttribute('aria-checked',hidden?'false':'true');
    chip.onclick=function(){if(Date.now()<_composerControlDragSuppressUntil)return;_toggleComposerControlChip(def.key);};
    _wireComposerControlChipDrag(chip,def.key);
    container.appendChild(chip);
  });
}

function _renderComposerSituationalControlChips(){
  const container=$('composerSituationalControlsChips');
  if(!container) return;
  const defs=Array.isArray(window._COMPOSER_SITUATIONAL_CONTROL_TOGGLE_DEFS)?window._COMPOSER_SITUATIONAL_CONTROL_TOGGLE_DEFS:[];
  const state=window._composerControlVisibility||{};
  container.innerHTML='';
  _orderedComposerControlDefsForSettings(defs).forEach(function(def){
    const chip=document.createElement('button');
    chip.type='button';
    chip.className='tab-visibility-chip';
    const hidden=!!state[def.key];
    if(hidden) chip.classList.add('chip-off');
    chip.textContent=_composerControlChipLabel(def);
    chip.setAttribute('role','switch');
    chip.setAttribute('aria-checked',hidden?'false':'true');
    chip.onclick=function(){if(Date.now()<_composerControlDragSuppressUntil)return;_toggleComposerControlChip(def.key);};
    _wireComposerControlChipDrag(chip,def.key);
    container.appendChild(chip);
  });
}

function switchSettingsSection(name,opts){
  // If the main content is not showing settings, just remember the section
  // without force-switching the panel. The section will be applied when the
  // user next opens settings via switchPanel(). (#appearance-auto-reopen)
  if (_currentPanel !== 'settings') {
    _currentSettingsSection = name;
    _settingsSection = name;
    return;
  }
  let section=(name==='appearance'||name==='preferences'||name==='providers'||name==='plugins'||name==='extensions'||name==='system'||name==='help')?name:'conversation';
  // Deep-linking to the Plugins pane when the tab is hidden (no plugins
  // installed, #3457) falls back to Conversation. Resolve this BEFORE toggling
  // panes/sidebar/dropdown below so every downstream selection uses the
  // corrected section — otherwise the plugins pane would still render active
  // but empty. (#3457)
  if(section==='plugins'){
    const pluginsTabBtn=document.querySelector('[data-settings-section="plugins"]');
    if(pluginsTabBtn && pluginsTabBtn.style.display==='none') section='conversation';
  }
  _settingsSection=section;
  _currentSettingsSection=section;
  const map={conversation:'Conversation',appearance:'Appearance',preferences:'Preferences',providers:'Providers',plugins:'Plugins',extensions:'Extensions',system:'System',help:'Help'};
  // Sidebar menu items
  document.querySelectorAll('#settingsMenu .side-menu-item').forEach(it=>{
    it.classList.toggle('active', it.dataset.settingsSection===section);
  });
  // Panes in main
  ['conversation','appearance','preferences','providers','plugins','extensions','system','help'].forEach(key=>{
    const pane=$('settingsPane'+map[key]);
    if(pane) pane.classList.toggle('active', key===section);
  });
  // Sync mobile dropdown
  const dd=$('settingsSectionDropdown');
  if(dd && dd.value!==section) dd.value=section;
  // Lazy-load integration panels when their tabs are opened. Search
  // navigation passes skipLazyLoad: the loaders rebuild the pane DOM from a
  // fresh fetch, which would detach the field it is about to scroll to.
  if(!(opts&&opts.skipLazyLoad)){
    if(section==='providers') loadProvidersPanel();
    if(section==='plugins') loadPluginsPanel();
    if(section==='extensions') loadExtensionsPanel();
  }
  if(opts&&opts.fromSidebarItem)_closeMobileSidebarAfterPanelSelection();
}

function _normalizeSettingsSearchText(value) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}

function _extractSettingsDescriptionText(field, labelEl) {
  const chunks = [];
  const settingsSearch = (field.dataset && field.dataset.settingsSearch) || '';
  if (settingsSearch) chunks.push(settingsSearch);
  field.querySelectorAll('[data-i18n]').forEach(node => {
    if (labelEl && (node === labelEl || labelEl.contains(node))) return;
    const key = node.dataset ? node.dataset.i18n : null;
    if (key) chunks.push(t(key));
  });
  return chunks.join(' ');
}

function _extractSettingsValueText(field) {
  const chunks = [];
  const controls = [...field.querySelectorAll('select, input, textarea')];
  controls.forEach(control => {
    const tagName = (control.tagName || '').toLowerCase();
    if (tagName === 'select') {
      control.querySelectorAll('option').forEach(option => {
        if (option.dataset && option.dataset.i18n) {
          chunks.push(t(option.dataset.i18n));
        } else {
          chunks.push(option.textContent);
        }
      });
      return;
    }
    const type = (control.getAttribute && control.getAttribute('type')) || control.type || '';
    if (tagName === 'input' && ['checkbox', 'radio', 'file', 'submit', 'reset', 'button'].includes(type)) return;
    if (control.value) chunks.push(control.value);
  });
  return chunks.join(' ');
}

async function _buildSettingsIndex() {
  if (_settingsIndex) return;
  // Memoize the in-flight build so concurrent searches share one pass; the
  // lazy pane loaders are not guaranteed re-entrant.
  if (_settingsIndexPromise) return _settingsIndexPromise;
  const promise = (async () => {
    // Ensure lazy-loaded panes are populated before reading the DOM
    await Promise.all([loadProvidersPanel(), loadPluginsPanel(), loadExtensionsPanel()]);
    const index = [];
    const add = (entry) => {
      index.push({ ...entry, _settingsSearchIndex: index.length });
    };
    const sectionMap = {
      settingsPaneConversation: 'conversation',
      settingsPaneAppearance: 'appearance',
      settingsPanePreferences: 'preferences',
      settingsPaneProviders: 'providers',
      settingsPanePlugins: 'plugins',
      settingsPaneExtensions: 'extensions',
      settingsPaneSystem: 'system',
      settingsPaneHelp: 'help',
    };
    for (const [paneId, sectionKey] of Object.entries(sectionMap)) {
      const pane = $(paneId);
      if (!pane) continue;
      pane.querySelectorAll('.settings-field').forEach(field => {
        // The i18n key may live on the <label> itself (label[data-i18n]) OR on
        // a child of the label — the common toggle shape is
        // <label><input><span data-i18n="..."></span></label>. Match both, plus
        // a plain <label> with no i18n key, so every field is searchable
        // (previously only label[data-i18n] indexed, silently dropping most
        // checkbox settings). #4340 review fix.
        const labelEl = field.querySelector('label[data-i18n], label [data-i18n], label');
        if (!labelEl) return;
        const i18nKey = labelEl.dataset ? labelEl.dataset.i18n : undefined;
        const titleText = (i18nKey && t(i18nKey)) || labelEl.textContent.trim();
        if (!titleText) return;
        const valueText = _normalizeSettingsSearchText(_extractSettingsValueText(field));
        const descriptionText = _normalizeSettingsSearchText(_extractSettingsDescriptionText(field, labelEl));
        const searchBlob = [titleText, valueText, descriptionText, field.textContent]
          .filter(Boolean)
          .join(' ')
          .replace(/\s+/g, ' ')
          .trim();
        add({
          label: titleText,
          titleText,
          valueText,
          descriptionText,
          searchBlob,
          sectionKey,
          i18nKey,
          el: field,
        });
      });
      if (sectionKey === 'providers') {
        pane.querySelectorAll('.provider-card').forEach(card => {
          const cardName = ((card.querySelector('.provider-card-name') || {}).textContent || '').trim();
          if (cardName) {
            const titleText = cardName;
            const valueText = _normalizeSettingsSearchText(_extractSettingsValueText(card));
            const descriptionText = _normalizeSettingsSearchText(_extractSettingsDescriptionText(card));
            const searchBlob = [cardName, valueText, descriptionText, card.textContent]
              .filter(Boolean)
              .join(' ')
              .replace(/\s+/g, ' ')
              .trim();
            add({
              label: cardName,
              titleText,
              valueText,
              descriptionText,
              searchBlob,
              sectionKey,
              el: card,
              cardName,
            });
          }
          card.querySelectorAll('.provider-card-field').forEach(field => {
            const fieldLabel = ((field.querySelector('.provider-card-label') || {}).textContent || '').trim();
            const label = [cardName, fieldLabel].filter(Boolean).join(' ');
            if (!label) return;
            const valueText = _normalizeSettingsSearchText(_extractSettingsValueText(field));
            const descriptionText = _normalizeSettingsSearchText(_extractSettingsDescriptionText(field));
            const searchBlob = [label, valueText, descriptionText, field.textContent]
              .filter(Boolean)
              .join(' ')
              .replace(/\s+/g, ' ')
              .trim();
            add({
              label,
              titleText: label,
              valueText,
              descriptionText,
              searchBlob,
              sectionKey,
              el: field,
              cardName,
              fieldLabel,
            });
          });
        });
      }
      if (sectionKey === 'plugins') {
        pane.querySelectorAll('.plugin-card').forEach(card => {
          const cardName = ((card.querySelector('.provider-card-name') || {}).textContent || '').trim();
          if (!cardName) return;
          const titleText = cardName;
          const valueText = _normalizeSettingsSearchText(_extractSettingsValueText(card));
          const descriptionText = _normalizeSettingsSearchText(_extractSettingsDescriptionText(card));
          const searchBlob = [cardName, valueText, descriptionText, card.textContent]
            .filter(Boolean)
            .join(' ')
            .replace(/\s+/g, ' ')
            .trim();
          add({
            label: cardName,
            titleText,
            valueText,
            descriptionText,
            searchBlob,
            sectionKey,
            el: card,
            cardName,
          });
        });
      }
    }
    // A panel-session reset while building clears the memo; drop this result
    // instead of resurrecting a stale index for the new session.
    if (_settingsIndexPromise === promise) _settingsIndex = index;
  })().catch(e => { if (_settingsIndexPromise === promise) _settingsIndexPromise = null; throw e; });
  _settingsIndexPromise = promise;
  return promise;
}

async function filterSettings(query) {
  const resultsEl = $('settingsSearchResults');
  if (!resultsEl) return;
  const q = (query || '').trim().toLowerCase();
  if (!q) { ++_settingsSearchSeq; resultsEl.style.display = 'none'; resultsEl.innerHTML = ''; return; }
  const seq = ++_settingsSearchSeq;
  await _buildSettingsIndex();
  // A newer keystroke superseded this query while the index was building.
  if (seq !== _settingsSearchSeq) return;
  const sectionLabels = {
    conversation: t('settings_tab_conversation') || 'Conversation',
    appearance: t('settings_tab_appearance') || 'Appearance',
    preferences: t('settings_tab_preferences') || 'Preferences',
    providers: t('providers_tab_title') || 'Providers',
    plugins: t('settings_tab_plugins') || 'Plugins',
    extensions: t('settings_tab_extensions') || 'Extensions',
    system: t('settings_tab_system') || 'System',
    help: t('settings_tab_help') || 'Help',
  };
  const matches = (_settingsIndex || []).map((entry) => {
    const score = _scoreSettingsSearchMatch(entry, q);
    return score ? { entry, score, index: entry._settingsSearchIndex } : null;
  }).filter(Boolean);
  if (!matches.length) {
    resultsEl.innerHTML = `<div class="settings-search-empty">${esc(t('settings_search_no_results') || 'No settings found.')}</div>`;
    resultsEl.style.display = '';
    return;
  }
  resultsEl.innerHTML = '';
  matches.sort((left, right) => {
    if (left.score.bucketIndex !== right.score.bucketIndex) {
      return left.score.bucketIndex - right.score.bucketIndex;
    }
    if (left.score.matchIndex !== right.score.matchIndex) {
      return left.score.matchIndex - right.score.matchIndex;
    }
    return left.index - right.index;
  });
  for (const { entry: m } of matches.slice(0, 12)) {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'settings-search-result';
    item.innerHTML = `<span class="settings-search-section">${esc(sectionLabels[m.sectionKey] || m.sectionKey)}</span>` +
      `<span class="settings-search-arrow">›</span>` +
      `<span class="settings-search-label">${esc(m.label)}</span>`;
    item.addEventListener('click', () => {
      _navigateToSettingsField(m);
      resultsEl.style.display = 'none';
      resultsEl.innerHTML = '';
      const input = $('settingsSearch');
      if (input) input.value = '';
    });
    resultsEl.appendChild(item);
  }
  resultsEl.style.display = '';
}

function _scoreSettingsSearchMatch(entry, q) {
  const query = (q || '').toLowerCase().trim();
  if (!query) return null;
  const buckets = [
    ['titleText', 0],
    ['valueText', 1],
    ['descriptionText', 2],
    ['searchBlob', 3],
  ];
  for (const [bucketName, bucketIndex] of buckets) {
    const hay = _normalizeSettingsSearchText(entry[bucketName]);
    if (!hay) continue;
    const matchIndex = hay.indexOf(query);
    if (matchIndex < 0) continue;
    return {
      bucketIndex,
      matchType: matchIndex === 0 ? 'prefix' : 'contains',
      matchIndex,
    };
  }
  return null;
}

function _navigateToSettingsField(entry) {
  // The panes were populated when the index was built, so skip the tab-switch
  // lazy reload: loadProvidersPanel()/loadPluginsPanel() rebuild the pane DOM
  // from a fresh fetch and would detach the node mid-scroll.
  switchSettingsSection(entry.sectionKey, { skipLazyLoad: true });
  requestAnimationFrame(() => {
    const el = _resolveSettingsField(entry);
    if (!el) return;
    el.scrollIntoView({ block: 'center', behavior: 'smooth' });
    _highlightSettingsField(el);
  });
}

function _resolveSettingsField(entry) {
  // Re-resolve in the live DOM: any pane re-render since indexing (e.g. the
  // user visited the tab) replaces the node the index captured.
  const paneIds = {
    conversation: 'settingsPaneConversation',
    appearance: 'settingsPaneAppearance',
    preferences: 'settingsPanePreferences',
    providers: 'settingsPaneProviders',
    plugins: 'settingsPanePlugins',
    extensions: 'settingsPaneExtensions',
    system: 'settingsPaneSystem',
    help: 'settingsPaneHelp',
  };
  const pane = $(paneIds[entry.sectionKey]);
  if (pane && entry.cardName && (entry.sectionKey === 'providers' || entry.sectionKey === 'plugins')) {
    const cards = entry.sectionKey === 'providers'
      ? pane.querySelectorAll('.provider-card')
      : pane.querySelectorAll('.plugin-card');
    for (const card of cards) {
      const name = ((card.querySelector('.provider-card-name') || {}).textContent || '').trim();
      if (name !== entry.cardName) continue;
      if (entry.fieldLabel && entry.sectionKey === 'providers') {
        for (const field of card.querySelectorAll('.provider-card-field')) {
          const label = ((field.querySelector('.provider-card-label') || {}).textContent || '').trim();
          if (label === entry.fieldLabel) return field;
        }
      }
      return card;
    }
  }
  // The i18n key may sit on the label or on a child of it (span inside a
  // toggle label), so resolve via any [data-i18n] node, then climb to the
  // enclosing .settings-field. #4340 review fix.
  const labelEl = pane && entry.i18nKey
    ? pane.querySelector(`[data-i18n="${CSS.escape(entry.i18nKey)}"]`)
    : null;
  const live = labelEl && labelEl.closest('.settings-field');
  if (live) return live;
  return entry.el && entry.el.isConnected ? entry.el : null;
}

function _highlightSettingsField(el) {
  if (!el) return;
  el.classList.remove('settings-field-highlight');
  void el.offsetWidth;
  el.classList.add('settings-field-highlight');
  setTimeout(() => el.classList.remove('settings-field-highlight'), 1800);
}

function _syncHermesPanelSessionActions(){
  const hasSession=!!S.session;
  const visibleMessages=hasSession?(S.messages||[]).filter(m=>m&&m.role&&m.role!=='tool').length:0;
  const title=hasSession?(S.session.title||t('untitled')):t('active_conversation_none');
  const meta=$('hermesSessionMeta');
  const hasShare=!!(hasSession&&S.session&&S.session.share_token);
  if(meta){
    if(!hasSession){
      meta.textContent=t('active_conversation_none');
    }else{
      const base=t('active_conversation_meta', title, visibleMessages);
      meta.textContent=hasShare
        ? `${base} · ${t('share_session_status_active')}`
        : base;
    }
  }
  const setDisabled=(id,disabled)=>{
    const el=$(id);
    if(!el)return;
    el.disabled=!!disabled;
    el.classList.toggle('disabled',!!disabled);
  };
  setDisabled('btnDownload',!hasSession||visibleMessages===0);
  setDisabled('btnExportJSON',!hasSession);
  setDisabled('btnShareSession',!hasSession||visibleMessages===0);
  setDisabled('btnStopSharingSession',!hasShare);
  setDisabled('btnClearConvModal',!hasSession||visibleMessages===0);
}

// Thin wrapper: settings now live in the main content area. External callers
// (keyboard shortcuts, commands) keep working through this name.
function toggleSettings(){
  if(_currentPanel==='settings'){
    _closeSettingsPanel();
  } else {
    switchPanel('settings');
  }
}

function _resetSettingsPanelState(){
  const bar=$('settingsUnsavedBar');
  if(bar) bar.style.display='none';
  _setAppearanceAutosaveStatus('');
}

function _hideSettingsPanel(){
  _resetSettingsPanelState();
  const target = _consumeSettingsTargetPanel('chat');
  if(_currentPanel==='settings') switchPanel(target, {bypassSettingsGuard:true});
}

// Close with unsaved-changes check. If dirty, show a confirm dialog.
function _closeSettingsPanel(){
  if(!_settingsDirty){
    _revertSettingsPreview();
    _hideSettingsPanel();
    return;
  }
  _pendingSettingsTargetPanel = _pendingSettingsTargetPanel || 'chat';
  _showSettingsUnsavedBar();
}

// Revert live DOM/localStorage to what they were when the panel opened
function _revertSettingsPreview(){
  // Appearance controls autosave immediately. Closing/discarding the settings
  // panel must not roll back theme, skin, or font-size after the user sees the
  // inline saved state.
}

// Show the "Unsaved changes" bar inside the settings panel
function _showSettingsUnsavedBar(){
  let bar = $('settingsUnsavedBar');
  if(bar){ bar.style.display=''; return; }
  // Create it
  bar = document.createElement('div');
  bar.id = 'settingsUnsavedBar';
  bar.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:8px;background:rgba(233,69,96,.12);border:1px solid rgba(233,69,96,.3);border-radius:8px;padding:10px 14px;margin:0 0 12px;font-size:13px;';
  bar.innerHTML = `<span style="color:var(--text)">${esc(t('settings_unsaved_changes'))}</span>`
    + '<span style="display:flex;gap:8px">'
    + `<button onclick="_discardSettings()" style="padding:5px 12px;border-radius:6px;border:1px solid var(--border2);background:rgba(255,255,255,.06);color:var(--muted);cursor:pointer;font-size:12px;font-weight:600">${esc(t('discard'))}</button>`
    + `<button onclick="saveSettings(true)" style="padding:5px 12px;border-radius:6px;border:none;background:var(--accent);color:#fff;cursor:pointer;font-size:12px;font-weight:600">${esc(t('save'))}</button>`
    + '</span>';
  const body = document.querySelector('#mainSettings .settings-main') || document.querySelector('.settings-main');
  if(body) body.prepend(bar);
}

function _discardSettings(){
  _revertSettingsPreview();
  _settingsDirty = false;
  _hideSettingsPanel();
}

// Mark settings as dirty whenever anything changes
function _markSettingsDirty(){
  _settingsDirty = true;
}

// Apply TTS enabled state: toggles a body class so the CSS rule
// `body.tts-enabled .msg-tts-btn` shows/hides the speaker icon. We toggle the
// body class instead of writing inline `style.display` because the parent
// `.msg-action-btn` has no display rule, so clearing the inline style let the
// `.msg-tts-btn{display:none;}` cascade re-hide the button (#1409).
function _applyTtsEnabled(enabled){
  document.body.classList.toggle('tts-enabled', !!enabled);
}

// Read + sanitize the JSON/YAML structured code-block default-view controls
// (#484). mode is one of auto|on|off; lines is clamped to an int 1..1000 with a
// fallback of 10 (the original hardcoded threshold).
function _structuredCodeViewFromUi(){
  const modeSel=$('settingsStructuredCodeMode');
  const mode=modeSel&&['auto','on','off'].includes(modeSel.value)?modeSel.value:'auto';
  const linesField=$('settingsStructuredCodeAutoLines');
  const n=parseInt((linesField||{}).value,10);
  const lines=(Number.isFinite(n)&&n>=1&&n<=1000)?n:10;
  return {structured_code_default_view:mode,structured_code_auto_tree_lines:lines};
}

// Apply the structured code-block settings to runtime globals and re-render the
// transcript so already-rendered JSON/YAML blocks pick up the new default. The
// per-block Raw/Tree toggle is unaffected.
function _applyStructuredCodeViewSettings(mode,lines,rerender){
  window._structuredCodeDefaultView=['auto','on','off'].includes(mode)?mode:'auto';
  const n=parseInt(lines,10);
  window._structuredCodeAutoTreeLines=(Number.isFinite(n)&&n>=1&&n<=1000)?n:10;
  if(rerender){
    if(typeof clearMessageRenderCache==='function') clearMessageRenderCache();
    if(typeof renderMessages==='function') renderMessages({preserveScroll:true});
  }
}

// The Auto-threshold input is only meaningful in 'auto' mode; disable it
// otherwise so the control reads as inactive without hiding it.
function _syncStructuredCodeLinesEnabled(){
  const modeSel=$('settingsStructuredCodeMode');
  const linesField=$('settingsStructuredCodeAutoLines');
  // Both controls live in the same settings-field and are present together;
  // if either is missing there's nothing to sync.
  if(!modeSel||!linesField) return;
  const isAuto=modeSel.value==='auto';
  linesField.disabled=!isAuto;
  linesField.style.opacity=isAuto?'':'0.5';
}

function _appearancePayloadFromUi(){
  const worklogDetailsExpanded=!!($('settingsWorklogDetailsExpandedDefault')||{}).checked;
  const chatActivityModeSel=$('settingsChatActivityDisplayMode');
  const transparentEventTimestamps=$('settingsTransparentEventTimestamps');
  return {
    theme: ($('settingsTheme')||{}).value || localStorage.getItem('hermes-theme') || 'dark',
    skin: ($('settingsSkin')||{}).value || localStorage.getItem('hermes-skin') || 'default',
    font_size: ($('settingsFontSize')||{}).value || localStorage.getItem('hermes-font-size') || 'default',
    chat_activity_display_mode: chatActivityModeSel&&(chatActivityModeSel.value==='transparent_stream'||chatActivityModeSel.value==='hide_all_activity')
      ? chatActivityModeSel.value
      : 'compact_worklog',
    transparent_stream_event_timestamps: transparentEventTimestamps ? transparentEventTimestamps.checked : true,
    session_jump_buttons: !!($('settingsSessionJumpButtons')||{}).checked,
    session_endless_scroll: !!($('settingsSessionEndlessScroll')||{}).checked,
    auto_scroll_follow: !!($('settingsAutoScrollFollow')||{}).checked,
    render_user_markdown: !!($('settingsRenderUserMarkdown')||{}).checked,
    large_text_paste_as_attachment: !!($('settingsLargeTextPasteAsAttachment')||{}).checked,
    project_quick_create_buttons: !!($('settingsProjectQuickCreate')||{}).checked,
    ..._structuredCodeViewFromUi(),
    show_titlebar_profile: !!($('settingsShowTitlebarProfile')||{}).checked,
    worklog_details_expanded_default: worklogDetailsExpanded,
    activity_feed_expanded_default: worklogDetailsExpanded,
    ..._composerControlVisibilityPayload(),
    composer_control_order: _getComposerControlOrder(),
    hidden_tabs: _getHiddenTabs(),
    tab_order: _getTabOrder(),
  };
}

function _syncChatActivityDisplayModeControl(mode){
  const next=mode==='transparent_stream'||mode==='hide_all_activity' ? mode : 'compact_worklog';
  const select=$('settingsChatActivityDisplayMode');
  if(select) select.value=next;
  document.querySelectorAll('[data-chat-activity-mode]').forEach(btn=>{
    const active=btn.getAttribute('data-chat-activity-mode')===next;
    btn.classList.toggle('active',active);
    btn.setAttribute('aria-pressed',active?'true':'false');
  });
  window._chatActivityDisplayMode=next;
  window._transparentStream=next==='transparent_stream';
  if(typeof _syncTransparentEventTimestampsControl==='function') _syncTransparentEventTimestampsControl(window._transparentEventTimestamps,next);
  if(next==='hide_all_activity'&&typeof window._hideLiveActivityForFinalAnswerOnly==='function') window._hideLiveActivityForFinalAnswerOnly();
}

function _syncTransparentEventTimestampsControl(enabled, mode){
  const next=enabled!==false;
  const activeMode=mode==='transparent_stream'||mode==='hide_all_activity' ? mode : (window._chatActivityDisplayMode||'compact_worklog');
  const checkbox=$('settingsTransparentEventTimestamps');
  if(checkbox){
    checkbox.checked=next;
    checkbox.disabled=activeMode!=='transparent_stream';
    checkbox.style.opacity=activeMode==='transparent_stream'?'':'0.5';
  }
  window._transparentEventTimestamps=next;
}

function _pickChatActivityDisplayMode(mode){
  _syncChatActivityDisplayModeControl(mode);
  if(typeof clearMessageRenderCache==='function') clearMessageRenderCache();
  if(typeof renderMessages==='function') renderMessages({preserveScroll:true});
  _scheduleAppearanceAutosave();
}
if(typeof window!=='undefined') window._pickChatActivityDisplayMode=_pickChatActivityDisplayMode;

function _pickTransparentEventTimestamps(enabled){
  _syncTransparentEventTimestampsControl(enabled,window._chatActivityDisplayMode);
  if(typeof clearMessageRenderCache==='function') clearMessageRenderCache();
  if(typeof renderMessages==='function') renderMessages({preserveScroll:true});
  _scheduleAppearanceAutosave();
}
if(typeof window!=='undefined') window._pickTransparentEventTimestamps=_pickTransparentEventTimestamps;

function _setAppearanceAutosaveStatus(state){
  const el=$('settingsAppearanceAutosaveStatus');
  if(!el) return;
  el.className='settings-autosave-status';
  if(!state){
    el.textContent='';
    return;
  }
  el.classList.add('is-'+state);
  if(state==='saving'){
    el.textContent=t('settings_autosave_saving');
  }else if(state==='saved'){
    el.textContent=t('settings_autosave_saved');
  }else if(state==='failed'){
    el.innerHTML=`<span>${esc(t('settings_autosave_failed'))}</span> <button type="button" onclick="_retryAppearanceAutosave()">${esc(t('settings_autosave_retry'))}</button>`;
  }
}

function _rememberAppearanceSaved(payload){
  if(!payload) return;
  _settingsThemeOnOpen=payload.theme||localStorage.getItem('hermes-theme')||'dark';
  _settingsSkinOnOpen=payload.skin||localStorage.getItem('hermes-skin')||'default';
  _settingsFontSizeOnOpen=payload.font_size||localStorage.getItem('hermes-font-size')||'default';
}

function _scheduleAppearanceAutosave(){
  const payload=_appearancePayloadFromUi();
  // Keep discard/close behavior aligned with the new mental model: appearance
  // changes are committed immediately instead of treated as preview-only edits.
  _rememberAppearanceSaved(payload);
  _settingsAppearanceAutosaveRetryPayload=payload;
  _setAppearanceAutosaveStatus('saving');
  if(_settingsAppearanceAutosaveTimer) clearTimeout(_settingsAppearanceAutosaveTimer);
  _settingsAppearanceAutosaveTimer=setTimeout(()=>_autosaveAppearanceSettings(payload),350);
}

async function _autosaveAppearanceSettings(payload){
  try{
    const saved=await api('/api/settings',{method:'POST',body:JSON.stringify(payload)});
    _settingsAppearanceAutosaveRetryPayload=null;
    _rememberAppearanceSaved(payload);
    if(saved&&saved.font_size){
      localStorage.setItem('hermes-font-size',saved.font_size);
    }
    if(saved){
      window._sessionJumpButtonsEnabled=!!saved.session_jump_buttons;
      if(Object.prototype.hasOwnProperty.call(saved,'chat_activity_display_mode')){
        const beforeMode=window._chatActivityDisplayMode;
        const beforeTimestamps=window._transparentEventTimestamps!==false;
        _syncChatActivityDisplayModeControl(saved.chat_activity_display_mode);
        _syncTransparentEventTimestampsControl(saved.transparent_stream_event_timestamps, saved.chat_activity_display_mode);
        if(window._chatActivityDisplayMode!==beforeMode||((window._transparentEventTimestamps!==false)!==beforeTimestamps)){
          if(typeof clearMessageRenderCache==='function') clearMessageRenderCache();
          if(typeof renderMessages==='function') renderMessages({preserveScroll:true});
        }
      }
      if(typeof _applySessionNavigationPrefs==='function') _applySessionNavigationPrefs();
    }
    window._sessionEndlessScrollEnabled=!!(saved&&saved.session_endless_scroll);
    window._autoScrollFollow=!saved||saved.auto_scroll_follow!==false;
    window._largeTextPasteAsAttachment=!saved||saved.large_text_paste_as_attachment!==false;
    window._projectQuickCreate=!!(saved&&saved.project_quick_create_buttons);
    if(saved&&Object.prototype.hasOwnProperty.call(saved,'structured_code_default_view')){
      // Re-sync from the server-validated/clamped values so the UI and runtime
      // globals match exactly what was persisted.
      _applyStructuredCodeViewSettings(saved.structured_code_default_view,saved.structured_code_auto_tree_lines,false);
      const modeSel=$('settingsStructuredCodeMode');
      if(modeSel) modeSel.value=window._structuredCodeDefaultView;
      const linesField=$('settingsStructuredCodeAutoLines');
      if(linesField) linesField.value=window._structuredCodeAutoTreeLines;
      _syncStructuredCodeLinesEnabled();
    }
    if(saved&&payload&&Object.prototype.hasOwnProperty.call(payload,'worklog_details_expanded_default')&&(
      Object.prototype.hasOwnProperty.call(saved,'worklog_details_expanded_default') ||
      Object.prototype.hasOwnProperty.call(saved,'activity_feed_expanded_default')
    )){
      window._worklogDetailsExpandedByDefault=!!(
        Object.prototype.hasOwnProperty.call(saved,'worklog_details_expanded_default')
          ? saved.worklog_details_expanded_default
          : saved.activity_feed_expanded_default
      );
    }
    if(saved){
      _ensureComposerControlVisibilityState(saved);
      if(Array.isArray(saved.composer_control_order)){
        const nextOrder=_setComposerControlOrder(saved.composer_control_order);
        if(typeof window._applyComposerControlOrder==='function') window._applyComposerControlOrder(nextOrder);
      }
      _renderComposerControlChips();
      _renderComposerSituationalControlChips();
      if(typeof _applyComposerFooterVisibilitySettings==='function') _applyComposerFooterVisibilitySettings();
    }
    _setAppearanceAutosaveStatus('saved');
  }catch(e){
    console.warn('[settings] appearance autosave failed', e);
    _setAppearanceAutosaveStatus('failed');
  }
}

function _retryAppearanceAutosave(){
  const payload=_settingsAppearanceAutosaveRetryPayload||_appearancePayloadFromUi();
  _setAppearanceAutosaveStatus('saving');
  _autosaveAppearanceSettings(payload);
}

// ── Phase 2: Preferences autosave (Issue #1003) ───────────────────────

const _SETTINGS_SPEECH_STORAGE_KEYS={
  tts_enabled:'hermes-tts-enabled',
  tts_auto_read:'hermes-tts-auto-read',
  tts_engine:'hermes-tts-engine',
  tts_voice:'hermes-tts-voice',
  tts_rate:'hermes-tts-rate',
  tts_pitch:'hermes-tts-pitch',
  voice_mode_button:'hermes-voice-mode-button',
  voice_continuous:'hermes-voice-continuous',
  voice_silence_ms:'hermes-voice-silence-ms',
  raw_audio_mode:'hermes-raw-audio-mode',
};
let _settingsSpeechPersistedKeys=new Set();
let _settingsSpeechLocalStorageKeys=new Set();
let _settingsSpeechChangedKeys=new Set();

function _captureSpeechPreferenceOwnership(settings){
  _settingsSpeechPersistedKeys=new Set(Array.isArray(settings&&settings.persisted_speech_keys)?settings.persisted_speech_keys:[]);
  _settingsSpeechLocalStorageKeys=new Set();
  _settingsSpeechChangedKeys=new Set();
  Object.entries(_SETTINGS_SPEECH_STORAGE_KEYS).forEach(([settingKey,storageKey])=>{
    try{if(localStorage.getItem(storageKey)!==null) _settingsSpeechLocalStorageKeys.add(settingKey);}catch(_){}
  });
}

function _speechPreferenceIsOwned(settingKey){
  return _settingsSpeechPersistedKeys.has(settingKey)||_settingsSpeechLocalStorageKeys.has(settingKey)||_settingsSpeechChangedKeys.has(settingKey);
}

function _markSpeechPreferenceChanged(settingKey){
  _settingsSpeechChangedKeys.add(settingKey);
}

function _syncSpeechPreferenceCache(settingKey,value){
  if(!_speechPreferenceIsOwned(settingKey)) return;
  const storageKey=_SETTINGS_SPEECH_STORAGE_KEYS[settingKey];
  if(storageKey) localStorage.setItem(storageKey,String(value));
}

function _setOwnedSpeechPayload(payload,settingKey,value){
  if(_speechPreferenceIsOwned(settingKey)) payload[settingKey]=value;
}

function _preferencesPayloadFromUi(){
  const payload={};
  const sendKeySel=$('settingsSendKey');
  if(sendKeySel) payload.send_key=sendKeySel.value;
  const langSel=$('settingsLanguage');
  if(langSel) payload.language=langSel.value;
  const showUsageCb=$('settingsShowTokenUsage');
  if(showUsageCb) payload.show_token_usage=showUsageCb.checked;
  const showQuotaChipCb=$('settingsShowQuotaChip');
  if(showQuotaChipCb) payload.show_quota_chip=showQuotaChipCb.checked;
  const showConversationOutlineCb=$('settingsShowConversationOutline');
  if(showConversationOutlineCb) payload.show_conversation_outline=showConversationOutlineCb.checked;
  const hideSuggestionsCb=$('settingsHideSuggestions');
  if(hideSuggestionsCb) payload.hide_empty_state_suggestions=hideSuggestionsCb.checked;
  const hideEmptyStatePanelCb=$('settingsHideEmptyStatePanel');
  if(hideEmptyStatePanelCb) payload.hide_empty_state_panel=hideEmptyStatePanelCb.checked;
  const virtualizeTranscriptCb=$('settingsVirtualizeTranscript');
  if(virtualizeTranscriptCb){
    payload.virtualize_transcript=virtualizeTranscriptCb.checked;
    // #4343: persist the opt-in marker alongside. Enabling the experimental
    // feature records an explicit post-flip opt-in so load_settings honors it
    // (a stored true WITHOUT this marker is treated as a stale pre-flip value
    // and reset to off). Unchecking clears the marker.
    payload.virtualize_transcript_optin=virtualizeTranscriptCb.checked;
  }
  const showTpsCb=$('settingsShowTps');
  if(showTpsCb) payload.show_tps=showTpsCb.checked;
  const fadeTextCb=$('settingsFadeTextEffect');
  if(fadeTextCb) payload.fade_text_effect=fadeTextCb.checked;
  const terminalAutoExpandCb=$('settingsTerminalAutoExpand');
  if(terminalAutoExpandCb) payload.terminal_auto_expand_on_output=terminalAutoExpandCb.checked;
  const workspaceTodosTabCb=$('settingsWorkspaceTodosTab');
  if(workspaceTodosTabCb) payload.workspace_todos_tab=workspaceTodosTabCb.checked;
  const apiRedactCb=$('settingsApiRedact');
  if(apiRedactCb) payload.api_redact_enabled=apiRedactCb.checked;
  const showCliCb=$('settingsShowCliSessions');
  if(showCliCb) payload.show_cli_sessions=showCliCb.checked;
  const showClaudeCodeCb=$('settingsShowClaudeCodeSessions');
  if(showClaudeCodeCb) payload.show_claude_code_sessions=showClaudeCodeCb.checked;
  const showCronCb=$('settingsShowCronSessions');
  // Gate cron sessions on CLI sessions (the server short-circuits otherwise),
  // identically to the explicit saveSettings() path, so neither save route can
  // persist show_cron_sessions=true while show_cli_sessions=false. (#3514)
  if(showCronCb) payload.show_cron_sessions=!!(showCliCb&&showCliCb.checked&&showCronCb.checked);
  const showWebhookCb=$('settingsShowWebhookSessions');
  if(showWebhookCb) payload.show_webhook_sessions=!!(showCliCb&&showCliCb.checked&&showWebhookCb.checked);
  const showPreviousMessagingCb=$('settingsShowPreviousMessagingSessions');
  if(showPreviousMessagingCb) payload.show_previous_messaging_sessions=showPreviousMessagingCb.checked;
  const syncCb=$('settingsSyncInsights');
  if(syncCb) payload.sync_to_insights=syncCb.checked;
  const updateCb=$('settingsCheckUpdates');
  if(updateCb) payload.check_for_updates=updateCb.checked;
  const updateChannelSel=$('settingsUpdateChannel');
  if(updateChannelSel) payload.update_channel=updateChannelSel.value;
  const ignoreAgentUpdatesCb=$('settingsIgnoreAgentUpdates');
  if(ignoreAgentUpdatesCb) payload.ignore_agent_updates=ignoreAgentUpdatesCb.checked;
  const whatsNewSummaryCb=$('settingsWhatsNewSummary');
  if(whatsNewSummaryCb) payload.whats_new_summary_enabled=whatsNewSummaryCb.checked;
  const soundCb=$('settingsSoundEnabled');
  if(soundCb) payload.sound_enabled=soundCb.checked;
  const rtlCb=$('settingsRtl');
  if(rtlCb) payload.rtl=rtlCb.checked;
  const notifCb=$('settingsNotificationsEnabled');
  if(notifCb) payload.notifications_enabled=notifCb.checked;
  const sidebarDensitySel=$('settingsSidebarDensity');
  if(sidebarDensitySel) payload.sidebar_density=sidebarDensitySel.value;
  const pinnedLimitField=$('settingsPinnedSessionsLimit');
  if(pinnedLimitField) payload.pinned_sessions_limit=parseInt(pinnedLimitField.value,10);
  const autoTitleRefreshSel=$('settingsAutoTitleRefresh');
  if(autoTitleRefreshSel) payload.auto_title_refresh_every=parseInt(autoTitleRefreshSel.value,10);
  const defaultMessageModeSel=$('settingsDefaultMessageMode');
  if(defaultMessageModeSel) payload.default_message_mode=defaultMessageModeSel.value;
  const showBusyPlaceholderHintCb=$('settingsShowBusyPlaceholderHint');
  if(showBusyPlaceholderHintCb) payload.show_busy_placeholder_hint=showBusyPlaceholderHintCb.checked;
  const newChatOnWorkspaceSwitchCb=$('settingsNewChatOnWorkspaceSwitch');
  if(newChatOnWorkspaceSwitchCb) payload.new_chat_on_workspace_switch=newChatOnWorkspaceSwitchCb.checked;
  const botNameField=$('settingsBotName');
  if(botNameField) payload.bot_name=botNameField.value;
  Object.assign(payload,_speechPreferencesPayloadFromUi());
  return payload;
}

function _speechPreferencesPayloadFromUi(){
  const payload={};
  const ttsEnabledCb=$('settingsTtsEnabled');
  if(ttsEnabledCb) _setOwnedSpeechPayload(payload,'tts_enabled',ttsEnabledCb.checked);
  const ttsAutoReadCb=$('settingsTtsAutoRead');
  if(ttsAutoReadCb) _setOwnedSpeechPayload(payload,'tts_auto_read',ttsAutoReadCb.checked);
  const ttsEngineSel=$('settingsTtsEngine');
  if(ttsEngineSel) _setOwnedSpeechPayload(payload,'tts_engine',ttsEngineSel.value||'browser');
  const ttsVoiceSel=$('settingsTtsVoice');
  if(ttsVoiceSel) _setOwnedSpeechPayload(payload,'tts_voice',ttsVoiceSel.value||'');
  const ttsRateSlider=$('settingsTtsRate');
  if(ttsRateSlider) _setOwnedSpeechPayload(payload,'tts_rate',parseFloat(ttsRateSlider.value));
  const ttsPitchSlider=$('settingsTtsPitch');
  if(ttsPitchSlider) _setOwnedSpeechPayload(payload,'tts_pitch',parseFloat(ttsPitchSlider.value));
  const voiceModeCb=$('settingsVoiceModeEnabled');
  if(voiceModeCb) _setOwnedSpeechPayload(payload,'voice_mode_button',voiceModeCb.checked);
  const rawAudioCb=$('settingsRawAudio');
  _setOwnedSpeechPayload(payload,'raw_audio_mode',rawAudioCb?rawAudioCb.checked:localStorage.getItem('hermes-raw-audio-mode')==='true');
  _setOwnedSpeechPayload(payload,'voice_continuous',localStorage.getItem('hermes-voice-continuous')==='true');
  const voiceSilence=parseInt(localStorage.getItem('hermes-voice-silence-ms'),10);
  _setOwnedSpeechPayload(payload,'voice_silence_ms',(Number.isFinite(voiceSilence)&&voiceSilence>=200)?voiceSilence:1800);
  return payload;
}

function _setPreferencesAutosaveStatus(state){
  const el=$('settingsPreferencesAutosaveStatus');
  if(!el) return;
  el.className='settings-autosave-status';
  if(!state){
    el.textContent='';
    return;
  }
  el.classList.add('is-'+state);
  if(state==='saving'){
    el.textContent=t('settings_autosave_saving');
  }else if(state==='saved'){
    el.textContent=t('settings_autosave_saved');
  }else if(state==='failed'){
    el.innerHTML=`<span>${esc(t('settings_autosave_failed'))}</span> <button type=\"button\" onclick=\"_retryPreferencesAutosave()\">${esc(t('settings_autosave_retry'))}</button>`;
  }
}

function _rememberPreferencesSaved(payload){
  if(!payload) return;
  if(payload.send_key!==undefined) localStorage.setItem('hermes-pref-send_key',payload.send_key);
  if(payload.language!==undefined) localStorage.setItem('hermes-pref-language',payload.language);
}

function _applyWorkspaceTodosTabVisibility(){
  const tab=$('workspaceTodosTab');
  if(tab) tab.hidden=!window._workspaceTodosTab;
  const rp=document.querySelector('.rightpanel');
  if(!window._workspaceTodosTab && rp && rp.dataset.activeTab==='todos'){
    if(typeof switchWorkspacePanelTab==='function') switchWorkspacePanelTab('files');
  }
}

function _schedulePreferencesAutosave(){
  const payload=_preferencesPayloadFromUi();
  _rememberPreferencesSaved(payload);
  _settingsPreferencesAutosaveRetryPayload=payload;
  _setPreferencesAutosaveStatus('saving');
  if(_settingsPreferencesAutosaveTimer) clearTimeout(_settingsPreferencesAutosaveTimer);
  _settingsPreferencesAutosaveTimer=setTimeout(()=>_autosavePreferencesSettings(payload),350);
}

async function _autosavePreferencesSettings(payload){
  try{
    const saved=await api('/api/settings',{method:'POST',body:JSON.stringify(payload)});
    if(payload&&payload.terminal_auto_expand_on_output!==undefined){
      window._terminalAutoExpandOnOutput=!!(saved&&saved.terminal_auto_expand_on_output);
    }
    if(payload&&payload.workspace_todos_tab!==undefined){
      window._workspaceTodosTab=!!(saved&&saved.workspace_todos_tab);
      if(typeof _applyWorkspaceTodosTabVisibility==='function') _applyWorkspaceTodosTabVisibility();
    }
    if(payload&&Object.prototype.hasOwnProperty.call(payload,'fade_text_effect')) window._fadeTextEffect=!!payload.fade_text_effect;
    if(saved&&Object.prototype.hasOwnProperty.call(saved,'pinned_sessions_limit')) window._pinnedSessionsLimit=parseInt(saved.pinned_sessions_limit,10)||3;
    if(payload&&payload.show_tps!==undefined){
      window._showTps=!!(saved&&saved.show_tps);
      if(typeof clearMessageRenderCache==='function') clearMessageRenderCache();
      if(typeof renderMessages==='function') renderMessages();
    }
    if(payload&&payload.hide_empty_state_suggestions!==undefined){
      window._hideEmptyStateSuggestions=!!(saved&&saved.hide_empty_state_suggestions);
      if(typeof applyEmptyStateSuggestionPref==='function') applyEmptyStateSuggestionPref();
    }
    if(payload&&payload.hide_empty_state_panel!==undefined){
      window._hideEmptyStatePanel=!!(saved&&saved.hide_empty_state_panel);
      if(typeof applyEmptyStatePanelPref==='function') applyEmptyStatePanelPref();
    }
    if(payload&&payload.show_conversation_outline!==undefined){
      window._showConversationOutline=!!(saved&&saved.show_conversation_outline);
      document.documentElement.dataset.conversationOutline=window._showConversationOutline?'enabled':'disabled';
      if(typeof applyConversationOutlinePreference==='function') applyConversationOutlinePreference();
    }
    if(payload&&payload.default_message_mode!==undefined){
      // #5170 mirror write on autosave, under the #5145 rename: persist the
      // saved mode so a reload/offline first-send honors it (legacy fallback).
      const _dmm=(saved&&saved.default_message_mode)||(saved&&saved.busy_input_mode);
      window._defaultMessageMode=(typeof _persistDefaultMessageMode==='function')?_persistDefaultMessageMode(_dmm):(_dmm||'steer');
      if(typeof _applyBusyComposerPlaceholder==='function') _applyBusyComposerPlaceholder();
    }
    if(payload&&payload.show_busy_placeholder_hint!==undefined){
      window._showBusyPlaceholderHint=!!(saved&&saved.show_busy_placeholder_hint);
      if(typeof _applyBusyComposerPlaceholder==='function') _applyBusyComposerPlaceholder();
    }
    if(payload&&payload.new_chat_on_workspace_switch!==undefined){
      window._newChatOnWorkspaceSwitch=!!(saved&&saved.new_chat_on_workspace_switch);  // #5473
    }
    _settingsPreferencesAutosaveRetryPayload=null;
    _setPreferencesAutosaveStatus('saved');
    // Only clear the global dirty flag and hide the unsaved-changes bar when
    // there is no pending edit on a manually-saved field. Password and model
    // are still committed via the explicit "Save Settings" button (password
    // for security; model goes through /api/default-model). Without this
    // guard, autosaving a checkbox right after a user typed in the password
    // field would silently dismiss the password edit. (Opus pre-release
    // review of v0.50.250, SHOULD-FIX Q1.)
    const pwField=$('settingsPassword');
    const pwDirty=!!(pwField&&pwField.value);
    const modelSel=$('settingsModel');
    const modelState=(typeof _captureModelDropdownSelection==='function'&&modelSel)
      ? (_captureModelDropdownSelection(modelSel)||{model:String((modelSel&&modelSel.value)||''),model_provider:null})
      : {model:String((modelSel&&modelSel.value)||''),model_provider:null};
    const modelDirty=!!(
      modelSel&&(
        (modelState.model||'')!==(_settingsHermesDefaultModelOnOpen||'')||
        ((modelState.model_provider||null)!==(_settingsHermesDefaultModelProviderOnOpen||null))
      )
    );
    if(!pwDirty&&!modelDirty){
      const maxTokensField=$('settingsMaxTokens');
      const maxTokensDirty=!!(
        maxTokensField&&
        String(maxTokensField.value||'')!==String(maxTokensField.dataset.initialValue||'')
      );
      if(!maxTokensDirty){
        _settingsDirty=false;
        const bar=$('settingsUnsavedBar');
        if(bar) bar.style.display='none';
      }
    }
  }catch(e){
    console.warn('[settings] preferences autosave failed', e);
    _setPreferencesAutosaveStatus('failed');
  }
}

function _retryPreferencesAutosave(){
  const payload=_settingsPreferencesAutosaveRetryPayload||_preferencesPayloadFromUi();
  _setPreferencesAutosaveStatus('saving');
  _autosavePreferencesSettings(payload);
}

function _syncSettingsMaxTokensPlaceholder(field, fallbackValue){
  if(!field) return;
  const parsedFallback=parseInt(fallbackValue,10);
  if(Number.isFinite(parsedFallback)&&parsedFallback>0&&typeof t==='function'){
    field.placeholder=t('settings_placeholder_max_tokens_fallback', parsedFallback);
    return;
  }
  field.placeholder=(typeof t==='function')
    ? t('settings_placeholder_max_tokens_none')
    : 'No override';
}

async function loadSettingsPanel(){
  try{
    const settings=await api('/api/settings');
    checkWebUIVersionSkew(settings);
    // Populate the version badges from the server — keeps them in sync with git
    // tags automatically without any manual release step.
    //
    // The DISPLAY badge uses update_channel_version (a channel-scoped
    // `git describe --match`), which is SEPARATE from settings.webui_version.
    // webui_version is load-bearing for asset cache-busting / SW cache / stale-
    // client skew detection and must stay channel-neutral — never render it as
    // the channel badge. See api/updates.channel_version_badge().
    const webuiBadge = $('settings-webui-version-badge');
    if(webuiBadge){
      const chanVer = settings.update_channel_version || settings.webui_version || 'not detected';
      const chan = settings.update_channel==='experimental' ? 'experimental' : 'stable';
      // Only annotate the channel when on experimental — stable is the implicit
      // default and needs no extra chrome.
      webuiBadge.textContent = chan==='experimental'
        ? `WebUI: ${chanVer} · Experimental`
        : `WebUI: ${chanVer}`;
    }
    const agentBadge = $('settings-agent-version-badge');
    if(agentBadge){
      const agentVersion = (settings.agent_version || 'not detected').toString().trim() || 'not detected';
      agentBadge.textContent = `Agent: ${agentVersion}`;
    }
    // Hydrate appearance controls first so a slow /api/models request
    // cannot overwrite an in-progress theme/skin selection.
    const themeSel=$('settingsTheme');
    const themeVal=settings.theme||'dark';
    if(themeSel) themeSel.value=themeVal;
    if(typeof _syncThemePicker==='function') _syncThemePicker(themeVal);
    const skinVal=(localStorage.getItem('hermes-skin')||settings.skin||'default').toLowerCase();
    const skinSel=$('settingsSkin');
    if(skinSel) skinSel.value=skinVal;
    if(typeof _buildSkinPicker==='function') _buildSkinPicker(skinVal);
    const fontSizeVal=settings.font_size||localStorage.getItem('hermes-font-size')||'default';
    localStorage.setItem('hermes-font-size',fontSizeVal);
    if(typeof _applyFontSize==='function') _applyFontSize(fontSizeVal);
    const fontSizeSel=$('settingsFontSize');
    if(fontSizeSel) fontSizeSel.value=fontSizeVal;
    if(typeof _syncFontSizePicker==='function') _syncFontSizePicker(fontSizeVal);
    const jumpButtonsCb=$('settingsSessionJumpButtons');
    if(jumpButtonsCb){
      jumpButtonsCb.checked=!!settings.session_jump_buttons;
      window._sessionJumpButtonsEnabled=jumpButtonsCb.checked;
      jumpButtonsCb.onchange=function(){
        window._sessionJumpButtonsEnabled=this.checked;
        if(typeof _applySessionNavigationPrefs==='function') _applySessionNavigationPrefs();
        _scheduleAppearanceAutosave();
      };
    }
    if(typeof _applySessionNavigationPrefs==='function') _applySessionNavigationPrefs();
    // Workspace panel default-open toggle (localStorage-backed)
    // Uses a separate key (hermes-webui-workspace-panel-pref) so that
    // closing the panel via toolbar X does not clear the user's preference.
    const wsPanelCb=$('settingsWorkspacePanelOpen');
    if(wsPanelCb){
      wsPanelCb.checked=localStorage.getItem('hermes-webui-workspace-panel-pref')==='open';
      wsPanelCb.onchange=function(){
        const open=this.checked;
        localStorage.setItem('hermes-webui-workspace-panel-pref',open?'open':'closed');
        // Also sync the runtime key so the current session reflects the change
        localStorage.setItem('hermes-webui-workspace-panel',open?'open':'closed');
        document.documentElement.dataset.workspacePanel=open?'open':'closed';
        if(open&&_workspacePanelMode==='closed') openWorkspacePanel('browse');
        else if(!open&&_workspacePanelMode!=='closed') toggleWorkspacePanel(false);
      };
    }
    const endlessScrollCb=$('settingsSessionEndlessScroll');
    if(endlessScrollCb){
      endlessScrollCb.checked=!!settings.session_endless_scroll;
      window._sessionEndlessScrollEnabled=endlessScrollCb.checked;
      endlessScrollCb.onchange=function(){
        window._sessionEndlessScrollEnabled=this.checked;
        _scheduleAppearanceAutosave();
      };
    }
    const autoScrollFollowCb=$('settingsAutoScrollFollow');
    if(autoScrollFollowCb){
      autoScrollFollowCb.checked=settings.auto_scroll_follow!==false;
      window._autoScrollFollow=autoScrollFollowCb.checked;
      autoScrollFollowCb.onchange=function(){
        window._autoScrollFollow=this.checked;
        _scheduleAppearanceAutosave();
      };
    }
    const worklogDetailsExpandedCb=$('settingsWorklogDetailsExpandedDefault');
    const chatActivityModeSel=$('settingsChatActivityDisplayMode');
    const transparentEventTimestampsCb=$('settingsTransparentEventTimestamps');
    if(chatActivityModeSel){
      _syncChatActivityDisplayModeControl(settings.chat_activity_display_mode);
      _syncTransparentEventTimestampsControl(settings.transparent_stream_event_timestamps, settings.chat_activity_display_mode);
      chatActivityModeSel.addEventListener('change',()=>{
        _pickChatActivityDisplayMode(chatActivityModeSel.value);
      },{once:false});
    }
    if(transparentEventTimestampsCb){
      transparentEventTimestampsCb.addEventListener('change',()=>{
        _pickTransparentEventTimestamps(transparentEventTimestampsCb.checked);
      },{once:false});
    }
    if(worklogDetailsExpandedCb){
      const worklogDetailsExpanded=Object.prototype.hasOwnProperty.call(settings,'worklog_details_expanded_default')
        ? settings.worklog_details_expanded_default
        : settings.activity_feed_expanded_default;
      worklogDetailsExpandedCb.checked=!!worklogDetailsExpanded;
      window._worklogDetailsExpandedByDefault=worklogDetailsExpandedCb.checked;
      worklogDetailsExpandedCb.onchange=function(){
        window._worklogDetailsExpandedByDefault=this.checked;
        if(typeof _applyWorklogDetailsExpandedDefault==='function') _applyWorklogDetailsExpandedDefault();
        _scheduleAppearanceAutosave();
      };
    }
    const renderUserMarkdownCb=$('settingsRenderUserMarkdown');
    if(renderUserMarkdownCb){
      renderUserMarkdownCb.checked=!!settings.render_user_markdown;
      window._renderUserMarkdown=renderUserMarkdownCb.checked;
      renderUserMarkdownCb.onchange=function(){
        window._renderUserMarkdown=this.checked;
        if(typeof clearMessageRenderCache==='function') clearMessageRenderCache();
        if(typeof renderMessages==='function') renderMessages();
        _scheduleAppearanceAutosave();
      };
    }
    const largeTextPasteCb=$('settingsLargeTextPasteAsAttachment');
    if(largeTextPasteCb){
      largeTextPasteCb.checked=settings.large_text_paste_as_attachment!==false;
      window._largeTextPasteAsAttachment=largeTextPasteCb.checked;
      largeTextPasteCb.onchange=function(){
        window._largeTextPasteAsAttachment=this.checked;
        _scheduleAppearanceAutosave();
      };
    }
    const pqcCb=$('settingsProjectQuickCreate');
    if(pqcCb){
      pqcCb.checked=!!(settings.project_quick_create_buttons);
      window._projectQuickCreate=pqcCb.checked;
      pqcCb.onchange=function(){
        window._projectQuickCreate=this.checked;
        // Rebuild the sidebar so the per-project + buttons appear/disappear
        // immediately, rather than only on the next render.
        try{ if(typeof renderSessionListFromCache==='function') renderSessionListFromCache(); }catch(_){}
        _scheduleAppearanceAutosave();
      };
    }
    const structuredCodeModeSel=$('settingsStructuredCodeMode');
    const structuredCodeLinesField=$('settingsStructuredCodeAutoLines');
    if(structuredCodeModeSel){
      const mode=['auto','on','off'].includes(settings.structured_code_default_view)?settings.structured_code_default_view:'auto';
      structuredCodeModeSel.value=mode;
      const lines=parseInt(settings.structured_code_auto_tree_lines,10);
      const safeLines=(Number.isFinite(lines)&&lines>=1&&lines<=1000)?lines:10;
      if(structuredCodeLinesField) structuredCodeLinesField.value=safeLines;
      _applyStructuredCodeViewSettings(mode,safeLines,false);
      _syncStructuredCodeLinesEnabled();
      structuredCodeModeSel.onchange=function(){
        const cfg=_structuredCodeViewFromUi();
        _applyStructuredCodeViewSettings(cfg.structured_code_default_view,cfg.structured_code_auto_tree_lines,true);
        _syncStructuredCodeLinesEnabled();
        _scheduleAppearanceAutosave();
      };
      if(structuredCodeLinesField){
        // Commit on change (blur / Enter / spinner) rather than every keystroke,
        // so a long transcript is not rebuilt per digit typed. Only re-render in
        // auto mode, where the threshold actually affects the default view.
        structuredCodeLinesField.addEventListener('change',function(){
          const cfg=_structuredCodeViewFromUi();
          structuredCodeLinesField.value=cfg.structured_code_auto_tree_lines;
          _applyStructuredCodeViewSettings(cfg.structured_code_default_view,cfg.structured_code_auto_tree_lines,cfg.structured_code_default_view==='auto');
          _scheduleAppearanceAutosave();
        },{once:false});
      }
    }
    const showTitlebarProfileCb=$('settingsShowTitlebarProfile');
    if(showTitlebarProfileCb){
      showTitlebarProfileCb.checked=!!settings.show_titlebar_profile;
      showTitlebarProfileCb.onchange=function(){
        window._showTitlebarProfile=this.checked;
        if(typeof _applyTitlebarProfileVisibility==='function') _applyTitlebarProfileVisibility();
        _scheduleAppearanceAutosave();
      };
    }
    _ensureComposerControlVisibilityState(settings);
    if(Array.isArray(settings.composer_control_order)){
      const composerOrder=_setComposerControlOrder(settings.composer_control_order);
      if(typeof window._applyComposerControlOrder==='function') window._applyComposerControlOrder(composerOrder);
    }
    _renderComposerControlChips();
    _renderComposerSituationalControlChips();
    if(typeof _applyComposerFooterVisibilitySettings==='function') _applyComposerFooterVisibilitySettings();
    // Tab visibility/order chips (dynamically populated from DOM)
    var hiddenTabs=[];
    if(Array.isArray(settings.hidden_tabs)){
      // Server value takes priority — even an empty array means "no tabs hidden"
      hiddenTabs=settings.hidden_tabs.filter(function(s){return typeof s==='string'&&s.trim();});
    }else{
      // Server has no hidden_tabs key — fall back to localStorage
      hiddenTabs=_getHiddenTabs();
    }
    var tabOrder=[];
    if(Array.isArray(settings.tab_order)){
      tabOrder=settings.tab_order.filter(function(s){return typeof s==='string'&&s.trim();});
    }else{
      tabOrder=_getTabOrder();
    }
    _setTabOrder(tabOrder);
    _applyTabOrder(tabOrder);
    _setHiddenTabs(hiddenTabs);
    _applyTabVisibility(hiddenTabs);
    _renderTabVisibilityChips();
    const resolvedLanguage=(typeof resolvePreferredLocale==='function')
      ? resolvePreferredLocale(settings.language, localStorage.getItem('hermes-lang'))
      : (settings.language || localStorage.getItem('hermes-lang') || 'en');
    // Keep settings modal and current page strings in sync with the resolved locale.
    if(typeof setLocale==='function'){
      setLocale(resolvedLanguage);
      if(typeof applyLocaleToDOM==='function') applyLocaleToDOM();
    }
    // Populate model dropdown from /api/models + live model fetch (#872)
    const modelSel=$('settingsModel');
    if(modelSel){
      modelSel.innerHTML='';
      let models=null;
      try{
        models=await api('/api/models');
        for(const g of ((models||{}).groups||[])){
          const og=document.createElement('optgroup');
          og.label=g.provider;
          if(g.provider_id) og.dataset.provider=g.provider_id;
          for(const m of [...(g.models||[]),...(g.extra_models||[])]){
            const opt=document.createElement('option');
            opt.value=m.id;opt.textContent=m.label;
            if(m && (m.supports_fast_tier === true || String(m.supports_fast_tier).toLowerCase()==='true')){
              opt.dataset.fast='1';
            }else if(m && (m.supports_fast_tier === false || String(m.supports_fast_tier).toLowerCase()==='false')){
              opt.dataset.fast='0';
            }
            og.appendChild(opt);
          }
          modelSel.appendChild(og);
        }
        // Append live-fetched models for the active provider, same as the
        // chat-header dropdown does via _fetchLiveModels() (#872).
        if(models.active_provider && typeof _fetchLiveModels==='function'){
          _fetchLiveModels(models.active_provider, modelSel);
        }
      }catch(e){}
      _settingsHermesDefaultModelOnOpen=(models&&models.default_model)||'';
      _settingsHermesDefaultModelProviderOnOpen=(models&&models.active_provider)||null;
      // Use the smart matcher so a saved bare form like "anthropic/claude-opus-4.6"
      // (what the CLI's `hermes model` command writes) still selects the matching
      // `@nous:anthropic/claude-opus-4.6` option on a Nous setup. Without this, the
      // picker renders blank for any user whose default was persisted without the
      // @-prefix — CLI-first users, legacy installs, etc.
      if(typeof _applyModelToDropdown==='function'){
        _applyModelToDropdown(_settingsHermesDefaultModelOnOpen, modelSel, (models&&models.active_provider)||window._activeProvider||null);
      }else{
        modelSel.value=_settingsHermesDefaultModelOnOpen;
      }
      if(typeof closeSettingsModelDropdown==='function') closeSettingsModelDropdown();
      if(typeof mountSettingsModelPicker==='function') mountSettingsModelPicker();
      modelSel.addEventListener('change',_markSettingsDirty,{once:false});
      if(!modelSel._settingsChipSyncBound){
        modelSel._settingsChipSyncBound=true;
        modelSel.addEventListener('change',()=>{if(typeof syncSettingsModelChip==='function') syncSettingsModelChip();},{once:false});
      }
    }
    // Auxiliary models — load task assignments and provider/model options
    _bindMainAdvancedOptionsButton();
    _loadAuxiliaryModels();
    // Send key preference
    const sendKeySel=$('settingsSendKey');
    if(sendKeySel){sendKeySel.value=settings.send_key||'enter';sendKeySel.addEventListener('change',_schedulePreferencesAutosave,{once:false});}
    // Language preference — populate from LOCALES bundle
    const langSel=$('settingsLanguage');
    if(langSel){
      langSel.innerHTML='';
      if(typeof LOCALES!=='undefined'){
        for(const [code,bundle] of Object.entries(LOCALES)){
          const opt=document.createElement('option');
          opt.value=code;opt.textContent=bundle._label||code;
          langSel.appendChild(opt);
        }
      }
      langSel.value=resolvedLanguage;
      langSel.addEventListener('change',function(){
        if(typeof setLocale==='function'){setLocale(this.value);if(typeof applyLocaleToDOM==='function')applyLocaleToDOM();}
        _schedulePreferencesAutosave();
      },{once:false});
    }
    const showUsageCb=$('settingsShowTokenUsage');
    if(showUsageCb){showUsageCb.checked=!!settings.show_token_usage;showUsageCb.addEventListener('change',_schedulePreferencesAutosave,{once:false});}
    const maxTokensField=$('settingsMaxTokens');
    if(maxTokensField){
      const rawMaxTokens=settings.max_tokens;
      const parsedMaxTokens=parseInt(rawMaxTokens,10);
      const hasRootOverride=Number.isFinite(parsedMaxTokens)&&parsedMaxTokens>0;
      maxTokensField.value=hasRootOverride
        ? String(parsedMaxTokens)
        : '';
      _syncSettingsMaxTokensPlaceholder(maxTokensField,settings.max_tokens_fallback);
      maxTokensField.dataset.initialValue=maxTokensField.value;
      maxTokensField.addEventListener('input',_markSettingsDirty,{once:false});
    }
    // Ambient provider quota chip toggle — default off; only shows at ≥1400px viewport
    // when enabled (see style.css @media (max-width:1399.98px) rule).
    const showQuotaChipCb=$('settingsShowQuotaChip');
    if(showQuotaChipCb){
      showQuotaChipCb.checked=settings.show_quota_chip===true;
      window._showQuotaChip=showQuotaChipCb.checked;
      showQuotaChipCb.addEventListener('change',()=>{
        window._showQuotaChip=showQuotaChipCb.checked;
        if(typeof refreshProviderQuotaIndicator==='function') refreshProviderQuotaIndicator();
        _schedulePreferencesAutosave();
      },{once:false});
    }
    const hideSuggestionsCb=$('settingsHideSuggestions');
    if(hideSuggestionsCb){
      hideSuggestionsCb.checked=settings.hide_empty_state_suggestions===true;
      window._hideEmptyStateSuggestions=hideSuggestionsCb.checked;
      if(typeof applyEmptyStateSuggestionPref==='function') applyEmptyStateSuggestionPref();
      hideSuggestionsCb.addEventListener('change',()=>{
        window._hideEmptyStateSuggestions=hideSuggestionsCb.checked;
        if(typeof applyEmptyStateSuggestionPref==='function') applyEmptyStateSuggestionPref();
        _schedulePreferencesAutosave();
      },{once:false});
    }
    const hideEmptyStatePanelCb=$('settingsHideEmptyStatePanel');
    if(hideEmptyStatePanelCb){
      hideEmptyStatePanelCb.checked=settings.hide_empty_state_panel===true;
      window._hideEmptyStatePanel=hideEmptyStatePanelCb.checked;
      if(typeof applyEmptyStatePanelPref==='function') applyEmptyStatePanelPref();
      hideEmptyStatePanelCb.addEventListener('change',()=>{
        window._hideEmptyStatePanel=hideEmptyStatePanelCb.checked;
        if(typeof applyEmptyStatePanelPref==='function') applyEmptyStatePanelPref();
        _schedulePreferencesAutosave();
      },{once:false});
    }
    const virtualizeTranscriptCb=$('settingsVirtualizeTranscript');
    if(virtualizeTranscriptCb){
      // #4343: EXPERIMENTAL/opt-IN, default OFF. Honor a stored true only when
      // it came from an explicit post-flip opt-in (===true); a pre-flip true is
      // already reset to false server-side by the load_settings migration.
      virtualizeTranscriptCb.checked=settings.virtualize_transcript===true;
      window._virtualizeTranscript=virtualizeTranscriptCb.checked;
      virtualizeTranscriptCb.addEventListener('change',()=>{
        window._virtualizeTranscript=virtualizeTranscriptCb.checked;
        // Re-render the open transcript so the change takes effect immediately
        // (full render when off, windowed when on).
        if(typeof renderMessages==='function'){ try{ renderMessages({preserveScroll:true}); }catch(e){ console.warn('[virtualize_transcript] renderMessages failed on toggle:',e); } }
        _schedulePreferencesAutosave();
      },{once:false});
    }
    const showConversationOutlineCb=$('settingsShowConversationOutline');
    if(showConversationOutlineCb){
      showConversationOutlineCb.checked=settings.show_conversation_outline===true;
      window._showConversationOutline=showConversationOutlineCb.checked;
      document.documentElement.dataset.conversationOutline=window._showConversationOutline?'enabled':'disabled';
      if(typeof applyConversationOutlinePreference==='function') applyConversationOutlinePreference();
      showConversationOutlineCb.addEventListener('change',()=>{
        _schedulePreferencesAutosave();
        window._showConversationOutline=showConversationOutlineCb.checked;
        document.documentElement.dataset.conversationOutline=window._showConversationOutline?'enabled':'disabled';
        if(typeof applyConversationOutlinePreference==='function') applyConversationOutlinePreference();
      },{once:false});
    }
    const showTpsCb=$('settingsShowTps');
    if(showTpsCb){showTpsCb.checked=!!settings.show_tps;showTpsCb.addEventListener('change',_schedulePreferencesAutosave,{once:false});}
    const pinnedLimitField=$('settingsPinnedSessionsLimit');
    if(pinnedLimitField){
      pinnedLimitField.value=parseInt(settings.pinned_sessions_limit||3,10)||3;
      window._pinnedSessionsLimit=parseInt(pinnedLimitField.value,10)||3;
      pinnedLimitField.addEventListener('change',_schedulePreferencesAutosave,{once:false});
      pinnedLimitField.addEventListener('input',()=>{window._pinnedSessionsLimit=parseInt(pinnedLimitField.value,10)||3;_schedulePreferencesAutosave();},{once:false});
    }
    const fadeTextCb=$('settingsFadeTextEffect');
    if(fadeTextCb){
      fadeTextCb.checked=!!settings.fade_text_effect;
      window._fadeTextEffect=fadeTextCb.checked;
      fadeTextCb.addEventListener('change',()=>{
        window._fadeTextEffect=fadeTextCb.checked;
        _schedulePreferencesAutosave();
      },{once:false});
    }
    const terminalAutoExpandCb=$('settingsTerminalAutoExpand');
    if(terminalAutoExpandCb){terminalAutoExpandCb.checked=!!settings.terminal_auto_expand_on_output;window._terminalAutoExpandOnOutput=terminalAutoExpandCb.checked;terminalAutoExpandCb.addEventListener('change',_schedulePreferencesAutosave,{once:false});}
    const workspaceTodosTabCb=$('settingsWorkspaceTodosTab');
    if(workspaceTodosTabCb){
      workspaceTodosTabCb.checked=!!settings.workspace_todos_tab;
      window._workspaceTodosTab=workspaceTodosTabCb.checked;
      _applyWorkspaceTodosTabVisibility();
      workspaceTodosTabCb.addEventListener('change',()=>{
        window._workspaceTodosTab=workspaceTodosTabCb.checked;
        _applyWorkspaceTodosTabVisibility();
        _schedulePreferencesAutosave();
      },{once:false});
    }
    const apiRedactCb=$('settingsApiRedact');
    if(apiRedactCb){apiRedactCb.checked=settings.api_redact_enabled!==false;apiRedactCb.addEventListener('change',_schedulePreferencesAutosave,{once:false});}
    const showCliCb=$('settingsShowCliSessions');
    if(showCliCb){showCliCb.checked=settings.show_cli_sessions!==false;showCliCb.addEventListener('change',_schedulePreferencesAutosave,{once:false});}
    const showClaudeCodeCb=$('settingsShowClaudeCodeSessions');
    if(showClaudeCodeCb){
      showClaudeCodeCb.checked=!!settings.show_claude_code_sessions;
      showClaudeCodeCb.disabled=showCliCb?!showCliCb.checked:true;
      showClaudeCodeCb.addEventListener('change',_schedulePreferencesAutosave,{once:false});
    }
    if(showCliCb){showCliCb.addEventListener('change',function(){
      const enabled=!!showCliCb.checked;
      if(showCronCb) showCronCb.disabled=!enabled;
      if(showClaudeCodeCb) showClaudeCodeCb.disabled=!enabled;
      _schedulePreferencesAutosave();
    },{once:false});}
    const showCronCb=$('settingsShowCronSessions');
    if(showCronCb){
      showCronCb.checked=!!settings.show_cron_sessions;
      showCronCb.disabled=showCliCb?!showCliCb.checked:true;
      showCronCb.addEventListener('change',_schedulePreferencesAutosave,{once:false});
    }
    const showWebhookCb=$('settingsShowWebhookSessions');
    if(showWebhookCb){
      showWebhookCb.checked=!!settings.show_webhook_sessions;
      showWebhookCb.disabled=showCliCb?!showCliCb.checked:true;
      showWebhookCb.addEventListener('change',_schedulePreferencesAutosave,{once:false});
      if(showCliCb){showCliCb.addEventListener('change',function(){showWebhookCb.disabled=!showCliCb.checked;},{once:false});}
    }
    const showPreviousMessagingCb=$('settingsShowPreviousMessagingSessions');
    if(showPreviousMessagingCb){showPreviousMessagingCb.checked=!!settings.show_previous_messaging_sessions;showPreviousMessagingCb.addEventListener('change',_schedulePreferencesAutosave,{once:false});}
    const syncCb=$('settingsSyncInsights');
    if(syncCb){syncCb.checked=!!settings.sync_to_insights;syncCb.addEventListener('change',_schedulePreferencesAutosave,{once:false});}
    const updateCb=$('settingsCheckUpdates');
    if(updateCb){updateCb.checked=settings.check_for_updates!==false;updateCb.addEventListener('change',_schedulePreferencesAutosave,{once:false});}
    const updateChannelSel=$('settingsUpdateChannel');
    if(updateChannelSel){
      updateChannelSel.value=settings.update_channel==='experimental'?'experimental':'stable';
      updateChannelSel.addEventListener('change',function(){
        // Persist the channel, then invalidate the cached update check and
        // re-check so the banner reflects the newly-selected channel. Changing
        // the channel changes WHAT is offered, never WHAT is installed — the
        // update banner still gates the actual apply behind "Update Now".
        _schedulePreferencesAutosave();
        if(typeof checkUpdatesNow==='function'){
          // Pass the just-selected channel EXPLICITLY so the re-check cannot race
          // the debounced autosave PUT and answer for the previous channel.
          const _picked=updateChannelSel.value;
          setTimeout(function(){try{checkUpdatesNow(_picked);}catch(e){}},400);
        }
        if(typeof _syncUpdateChannelBadge==='function') _syncUpdateChannelBadge(updateChannelSel.value);
      },{once:false});
    }
    const ignoreAgentUpdatesCb=$('settingsIgnoreAgentUpdates');
    if(ignoreAgentUpdatesCb){ignoreAgentUpdatesCb.checked=!!settings.ignore_agent_updates;ignoreAgentUpdatesCb.addEventListener('change',_schedulePreferencesAutosave,{once:false});}
    const whatsNewSummaryCb=$('settingsWhatsNewSummary');
    if(whatsNewSummaryCb){whatsNewSummaryCb.checked=!!settings.whats_new_summary_enabled;whatsNewSummaryCb.addEventListener('change',_schedulePreferencesAutosave,{once:false});}
    const soundCb=$('settingsSoundEnabled');
    if(soundCb){soundCb.checked=!!settings.sound_enabled;soundCb.addEventListener('change',_schedulePreferencesAutosave,{once:false});}
    // Right-to-left chat layout (#1721 salvage) — Settings-only, no composer button.
    const rtlCb=$('settingsRtl');
    if(rtlCb){
      const saved=!!settings.rtl || localStorage.getItem('hermes-rtl')==='true';
      rtlCb.checked=saved;
      try{localStorage.setItem('hermes-rtl',saved?'true':'false');}catch(_){}
      document.documentElement.classList.toggle('chat-content-rtl',saved);
      rtlCb.addEventListener('change',()=>{
        const on=rtlCb.checked;
        try{localStorage.setItem('hermes-rtl',on?'true':'false');}catch(_){}
        document.documentElement.classList.toggle('chat-content-rtl',on);
        _schedulePreferencesAutosave();
      },{once:false});
    }
    if(typeof window._mirrorSpeechSettingsFromServer==='function') window._mirrorSpeechSettingsFromServer(settings);
    const persistedSpeechKeys = new Set(
      Array.isArray(settings && settings.persisted_speech_keys)
        ? settings.persisted_speech_keys
        : []
    );
    _captureSpeechPreferenceOwnership(settings);
    const _speechSetting=function(key,storageKey,fallback,kind){
      const stored=localStorage.getItem(storageKey);
      if(settings&&persistedSpeechKeys.has(key)) return settings[key];
      return stored===null?fallback:stored;
    };
    const _speechBool=function(key,storageKey,fallback){
      const value=_speechSetting(key,storageKey,fallback,'bool');
      return value===true||value==='true';
    };
    const rawAudioCb=$('settingsRawAudio');
    if(rawAudioCb){
      rawAudioCb.checked=_speechBool('raw_audio_mode','hermes-raw-audio-mode',false);
      rawAudioCb.onchange=function(){
        _markSpeechPreferenceChanged('raw_audio_mode');
        if(typeof window._applyRawAudioModePreference==='function') window._applyRawAudioModePreference(this.checked);
        else localStorage.setItem('hermes-raw-audio-mode',this.checked?'true':'false');
        _schedulePreferencesAutosave();
      };
    }
    const voiceContinuous=_speechBool('voice_continuous','hermes-voice-continuous',false);
    _syncSpeechPreferenceCache('voice_continuous',voiceContinuous?'true':'false');
    const voiceSilence=parseInt(_speechSetting('voice_silence_ms','hermes-voice-silence-ms',1800),10);
    _syncSpeechPreferenceCache('voice_silence_ms',Number.isFinite(voiceSilence)&&voiceSilence>=200?String(voiceSilence):'1800');
    // TTS settings use /api/settings as the durable source and localStorage as the runtime cache.
    const ttsEnabledCb=$('settingsTtsEnabled');
    if(ttsEnabledCb){ttsEnabledCb.checked=_speechBool('tts_enabled','hermes-tts-enabled',false);ttsEnabledCb.onchange=function(){_markSpeechPreferenceChanged('tts_enabled');localStorage.setItem('hermes-tts-enabled',this.checked?'true':'false');_applyTtsEnabled(this.checked);_schedulePreferencesAutosave();};}
    const ttsAutoReadCb=$('settingsTtsAutoRead');
    if(ttsAutoReadCb){ttsAutoReadCb.checked=_speechBool('tts_auto_read','hermes-tts-auto-read',false);ttsAutoReadCb.onchange=function(){_markSpeechPreferenceChanged('tts_auto_read');localStorage.setItem('hermes-tts-auto-read',this.checked?'true':'false');_schedulePreferencesAutosave();};}
    // Voice-mode button visibility (#1488).
    // Toggling re-applies immediately via the boot.js helper so the user sees
    // the audio-waveform button appear/disappear without a reload.
    // Also recomputes composer footer visibility so the .composer-divider
    // (which tracks whether all left-group buttons are hidden, see #5451)
    // stays in sync when #btnVoiceMode appears or disappears here.
    const voiceModeCb=$('settingsVoiceModeEnabled');
    if(voiceModeCb){
      voiceModeCb.checked=_speechBool('voice_mode_button','hermes-voice-mode-button',false);
      voiceModeCb.onchange=function(){
        _markSpeechPreferenceChanged('voice_mode_button');
        localStorage.setItem('hermes-voice-mode-button',this.checked?'true':'false');
        if(typeof window._applyVoiceModePref==='function') window._applyVoiceModePref();
        if(typeof window._applyComposerFooterVisibilitySettings==='function') window._applyComposerFooterVisibilitySettings();
        _schedulePreferencesAutosave();
      };
    }
    // TTS engine selector
    const ttsEngineSel=$('settingsTtsEngine');
    if(ttsEngineSel){
      // Re-add any extension-registered TTS engines (window.registerHermesTtsEngine)
      // as options — the <select> markup only hardcodes the built-ins, and this
      // settings panel can render after an extension registered its engine.
      if(typeof window._hermesTtsEngineOptions==='function'){
        window._hermesTtsEngineOptions().forEach(function(e){
          if(!ttsEngineSel.querySelector('option[value="'+e.id+'"]')){
            var opt=document.createElement('option');
            opt.value=e.id; opt.textContent=e.label;
            ttsEngineSel.appendChild(opt);
          }
        });
      }
      const saved=String(_speechSetting('tts_engine','hermes-tts-engine','browser')||'browser');
      if(!ttsEngineSel.querySelector('option[value="'+saved+'"]')){
        var savedOpt=document.createElement('option');
        savedOpt.value=saved; savedOpt.textContent=saved;
        ttsEngineSel.appendChild(savedOpt);
      }
      ttsEngineSel.value=saved;
      _syncSpeechPreferenceCache('tts_engine',saved);
      ttsEngineSel.onchange=function(){
        _markSpeechPreferenceChanged('tts_engine');
        localStorage.setItem('hermes-tts-engine',this.value);
        window._populateTtsVoices();
        _schedulePreferencesAutosave();
      };
    }
    // Populate voice selector based on engine
    const ttsVoiceSel=$('settingsTtsVoice');
    window._populateTtsVoices=function(){
      if(!ttsVoiceSel) return;
      const engine=localStorage.getItem('hermes-tts-engine')||'browser';
      const current=String(_speechSetting('tts_voice','hermes-tts-voice','')||'');
      _syncSpeechPreferenceCache('tts_voice',current);
      if(engine==='elevenlabs'){
        ttsVoiceSel.innerHTML='<option value="">Hermy — ElevenLabs (server-configured)</option>';
      } else if(engine==='openai'){
        ttsVoiceSel.innerHTML='<option value="">OpenAI voice (server-configured)</option>';
      } else if(engine==='edge'){
        const edgeVoices=[
          {value:'zh-CN-XiaoxiaoNeural',label:'Xiaoxiao (Chinese, Female)'},
          {value:'zh-CN-XiaoyiNeural',label:'Xiaoyi (Chinese, Female)'},
          {value:'zh-CN-YunxiNeural',label:'Yunxi (Chinese, Male)'},
          {value:'zh-CN-YunjianNeural',label:'Yunjian (Chinese, Male)'},
          {value:'zh-CN-YunyangNeural',label:'Yunyang (Chinese, Male)'},
          {value:'en-US-AriaNeural',label:'Aria (English, Female)'},
          {value:'en-US-GuyNeural',label:'Guy (English, Male)'},
          {value:'id-ID-GadisNeural',label:'Gadis (Indonesian, Female)'},
        ];
        ttsVoiceSel.innerHTML='<option value="">Default (Xiaoxiao)</option>';
        edgeVoices.forEach(v=>{
          const opt=document.createElement('option');
          opt.value=v.value;opt.textContent=v.label;
          if(v.value===current) opt.selected=true;
          ttsVoiceSel.appendChild(opt);
        });
      } else {
        if(!('speechSynthesis' in window)){
          ttsVoiceSel.innerHTML='<option value="">Speech synthesis not available</option>';
          return;
        }
        const voices=speechSynthesis.getVoices();
        ttsVoiceSel.innerHTML='<option value="">Default system voice</option>';
        voices.forEach(v=>{
          const opt=document.createElement('option');
          opt.value=v.name;opt.textContent=v.name+(v.lang?' ('+v.lang+')':'');
          if(v.name===current) opt.selected=true;
          ttsVoiceSel.appendChild(opt);
        });
      }
    };
    if(ttsVoiceSel&&'speechSynthesis' in window){
      window._populateTtsVoices();
      speechSynthesis.addEventListener('voiceschanged',function(){
        const engine=localStorage.getItem('hermes-tts-engine')||'browser';
        if(engine==='browser') window._populateTtsVoices();
      },{once:false});
      ttsVoiceSel.onchange=function(){_markSpeechPreferenceChanged('tts_voice');localStorage.setItem('hermes-tts-voice',this.value);_schedulePreferencesAutosave();};
    }
    // TTS rate/pitch sliders
    const ttsRateSlider=$('settingsTtsRate');
    const ttsRateValue=$('settingsTtsRateValue');
    if(ttsRateSlider){
      const savedRate=_speechSetting('tts_rate','hermes-tts-rate',1);
      ttsRateSlider.value=(savedRate===null||savedRate===undefined)?'1':String(savedRate);
      if(ttsRateValue) ttsRateValue.textContent=parseFloat(ttsRateSlider.value).toFixed(1)+'x';
      _syncSpeechPreferenceCache('tts_rate',ttsRateSlider.value);
      ttsRateSlider.oninput=function(){_markSpeechPreferenceChanged('tts_rate');if(ttsRateValue)ttsRateValue.textContent=parseFloat(this.value).toFixed(1)+'x';localStorage.setItem('hermes-tts-rate',this.value);_schedulePreferencesAutosave();};
    }
    const ttsPitchSlider=$('settingsTtsPitch');
    const ttsPitchValue=$('settingsTtsPitchValue');
    if(ttsPitchSlider){
      const savedPitch=_speechSetting('tts_pitch','hermes-tts-pitch',1);
      ttsPitchSlider.value=(savedPitch===null||savedPitch===undefined)?'1':String(savedPitch);
      if(ttsPitchValue) ttsPitchValue.textContent=parseFloat(ttsPitchSlider.value).toFixed(1);
      _syncSpeechPreferenceCache('tts_pitch',ttsPitchSlider.value);
      ttsPitchSlider.oninput=function(){_markSpeechPreferenceChanged('tts_pitch');if(ttsPitchValue)ttsPitchValue.textContent=parseFloat(this.value).toFixed(1);localStorage.setItem('hermes-tts-pitch',this.value);_schedulePreferencesAutosave();};
    }
    const notifCb=$('settingsNotificationsEnabled');
    if(notifCb){notifCb.checked=!!settings.notifications_enabled;notifCb.addEventListener('change',_schedulePreferencesAutosave,{once:false});}
    // show_thinking has no settings panel checkbox — controlled via /reasoning show|hide
    const sidebarDensitySel=$('settingsSidebarDensity');
    if(sidebarDensitySel){
      sidebarDensitySel.value=settings.sidebar_density==='detailed'?'detailed':'compact';
      sidebarDensitySel.addEventListener('change',_schedulePreferencesAutosave,{once:false});
    }
    const autoTitleRefreshSel=$('settingsAutoTitleRefresh');
    if(autoTitleRefreshSel){
      const val=String(settings.auto_title_refresh_every||'0');
      autoTitleRefreshSel.value=['0','5','10','20'].includes(val)?val:'0';
      autoTitleRefreshSel.addEventListener('change',_schedulePreferencesAutosave,{once:false});
    }
    // Default message mode
    const defaultMessageModeSel=$('settingsDefaultMessageMode');
    if(defaultMessageModeSel){
      const val=String(settings.default_message_mode||settings.busy_input_mode||'steer');
      defaultMessageModeSel.value=['queue','interrupt','steer'].includes(val)?val:'steer';
      // #5170 mirror write on panel load, under the #5145 rename.
      window._defaultMessageMode=(typeof _persistDefaultMessageMode==='function')?_persistDefaultMessageMode(defaultMessageModeSel.value):defaultMessageModeSel.value;
      defaultMessageModeSel.addEventListener('change',_schedulePreferencesAutosave,{once:false});
    }
    const showBusyPlaceholderHintCb=$('settingsShowBusyPlaceholderHint');
    if(showBusyPlaceholderHintCb){
      showBusyPlaceholderHintCb.checked=!!settings.show_busy_placeholder_hint;
      window._showBusyPlaceholderHint=showBusyPlaceholderHintCb.checked;
      showBusyPlaceholderHintCb.addEventListener('change',_schedulePreferencesAutosave,{once:false});
    }
    if(typeof _applyBusyComposerPlaceholder==='function') _applyBusyComposerPlaceholder();
    const newChatOnWorkspaceSwitchCb=$('settingsNewChatOnWorkspaceSwitch');
    if(newChatOnWorkspaceSwitchCb){
      newChatOnWorkspaceSwitchCb.checked=!!settings.new_chat_on_workspace_switch;
      window._newChatOnWorkspaceSwitch=newChatOnWorkspaceSwitchCb.checked;
      newChatOnWorkspaceSwitchCb.addEventListener('change',_schedulePreferencesAutosave,{once:false});
    }
    // Bot name — debounced autosave (text input)
    const botNameField=$('settingsBotName');
    if(botNameField){
      botNameField.value=settings.bot_name||'Hermes';
      let botNameTimer=null;
      botNameField.addEventListener('input',()=>{
        if(botNameTimer) clearTimeout(botNameTimer);
        botNameTimer=setTimeout(_schedulePreferencesAutosave,500);
      },{once:false});
    }
    // Password field: always blank (we don't send hash back)
    const pwField=$('settingsPassword');
    if(pwField){pwField.value='';pwField.addEventListener('input',_markSettingsDirty,{once:false});}
    // #1560: when HERMES_WEBUI_PASSWORD env var is set, the settings password
    // field silently no-ops. Disable it + reveal the lock banner so the UI
    // tells the truth before a user tries (and the backend now also returns
    // 409 as defense-in-depth).
    const pwEnvLocked=!!settings.password_env_var;
    _settingsPasswordEnvLocked=pwEnvLocked;
    const pwLockBanner=$('settingsPasswordEnvLock');
    if(pwField){
      pwField.disabled=pwEnvLocked;
      if(pwEnvLocked){
        pwField.value='';
        pwField.placeholder=t('password_env_var_locked_placeholder')||pwField.placeholder;
      }
    }
    if(pwLockBanner) pwLockBanner.style.display=pwEnvLocked?'block':'none';
    // Show auth buttons only when auth is active
    try{
      const authStatus=await api('/api/auth/status');
      _settingsPasswordAuthEnabled=!!authStatus.password_auth_enabled;
      _setSettingsAuthButtonsVisible(!!authStatus.auth_enabled);
      _syncPasswordlessButton(authStatus);
      _renderSettingsAuthStatus(authStatus);
      _updateCurrentPasswordVisibility();
      _updateAuthWarningBadge(authStatus);
      _updateAuthDisabledWarning(authStatus);
    }catch(e){}
    loadPasskeys();
    // #1560: env-var-locked password also disables the Disable Auth button —
    // clearing settings.password_hash is silent no-op when the env var is set,
    // and the backend now returns 409 anyway, so don't offer the action.
    // Sign Out remains available since it only clears the session cookie.
    if(pwEnvLocked){
      const disableBtn=$('btnDisableAuth');
      if(disableBtn) disableBtn.style.display='none';
    }
    _syncHermesPanelSessionActions();
    if(typeof loadDashboardSettings==='function') loadDashboardSettings();
    loadProvidersPanel(); // load provider cards in background
    loadPluginsPanel(); // load plugin/hook visibility in background
    loadExtensionsPanel(); // load extension diagnostics in background
    switchSettingsSection(_settingsSection);
  }catch(e){
    showToast(t('settings_load_failed')+e.message);
  }
}


// ── Extensions panel (browser-origin diagnostics + local enable controls) ──

function _extensionStatusLabel(value){
  return value ? 'Enabled' : 'Disabled';
}

function _extensionBooleanBadge(value){
  const cls=value?'extension-status-badge-on':'extension-status-badge-off';
  return `<span class="extension-status-badge ${cls}">${value?'true':'false'}</span>`;
}

function _extensionAssetList(urls){
  if(!Array.isArray(urls)||urls.length===0){
    return '<div class="extension-url-empty">None</div>';
  }
  return '<ul class="extension-url-list">'+urls.map(url=>`<li><code>${esc(url)}</code></li>`).join('')+'</ul>';
}

function _extensionWarningList(warnings){
  if(!Array.isArray(warnings)||warnings.length===0){
    return '<div class="extension-url-empty">No warnings.</div>';
  }
  return '<ul class="extension-warning-list">'+warnings.map(item=>{
    const rawCode=(item&&item.code)||'unknown_warning';
    const code=esc(rawCode);
    const source=esc((item&&item.source)||'unknown');
    const hint=rawCode==='extension_state_unknown_ids'
      ? '<span>Some saved disabled-extension overrides no longer match the current manifest; re-added extensions with the same id may stay disabled.</span>'
      : '';
    return `<li><code>${code}</code><span>${source}</span>${hint}</li>`;
  }).join('')+'</ul>';
}

function _extensionCountValue(counts,key,urls){
  if(counts&&Number.isFinite(Number(counts[key]))) return Number(counts[key]);
  return Array.isArray(urls)?urls.length:0;
}

function _extensionEntryStatusLabel(entry){
  const status=(entry&&entry.status)||'';
  if(status==='manifest_disabled') return 'Disabled in manifest';
  if(status==='user_disabled') return 'Disabled';
  if(status==='enabled') return 'Enabled';
  return 'Unknown';
}

function _extensionEntryBadge(entry){
  const enabled=!!(entry&&entry.effective_enabled);
  const cls=enabled?'extension-status-badge-on':'extension-status-badge-off';
  return `<span class="extension-status-badge ${cls}">${esc(_extensionEntryStatusLabel(entry))}</span>`;
}

function _configureExtensionSettingsFromStatus(data){
  if(!window.HermesExtensionSettings||!data||!Array.isArray(data.extensions)) return;
  window.HermesExtensionSettings.primeFromStatus({extensions:data.extensions});
}

function _extensionSettingsFieldHtml(field,value){
  const key=String(field&&field.key||'');
  const type=String(field&&field.type||'');
  const label=String(field&&field.label||key);
  const desc=String(field&&field.description||'');
  const dataAttrs=`data-extension-setting-input="${esc(key)}" data-extension-setting-type="${esc(type)}"`;
  let control='';
  if(type==='boolean'){
    control=`<label class="extension-setting-check"><input type="checkbox" ${dataAttrs}${value?' checked':''}> <span>${esc(label)}</span></label>`;
  }else if(type==='number'||type==='integer'){
    const step=type==='integer'?'1':'any';
    control=`<label><span>${esc(label)}</span><input type="number" step="${step}" ${dataAttrs} value="${esc(String(value??''))}"></label>`;
  }else if(type==='enum'){
    const options=Array.isArray(field.options)?field.options:[];
    control=`<label><span>${esc(label)}</span><select ${dataAttrs}>${options.map(option=>{
      const optionValue=String(option&&option.value||'');
      const optionLabel=String(option&&option.label||optionValue);
      return `<option value="${esc(optionValue)}"${optionValue===value?' selected':''}>${esc(optionLabel)}</option>`;
    }).join('')}</select></label>`;
  }else{
    control=`<label><span>${esc(label)}</span><input type="text" ${dataAttrs} value="${esc(String(value??''))}"></label>`;
  }
  return `<div class="extension-setting-field">${control}${desc?`<div class="extension-setting-desc">${esc(desc)}</div>`:''}</div>`;
}

function _extensionSettingsControls(entry){
  const id=(entry&&entry.id)||'';
  const storageOwned=!!(entry&&entry.storage_owned);
  if(!storageOwned){
    return '<div class="extension-settings-empty">No extension-owned browser storage permission.</div>';
  }
  const settingsApi=window.HermesExtensionSettings&&id?window.HermesExtensionSettings.settingsForExtension(id):null;
  if(!settingsApi||!settingsApi.trusted){
    return '<div class="extension-settings-empty">Reload WebUI after enabling or installing this extension to edit browser-local settings.</div>';
  }
  const schema=Array.isArray(settingsApi&&settingsApi.schema)?settingsApi.schema:[];
  const values=settingsApi?settingsApi.values:{};
  const fields=schema.length
    ? schema.map(field=>_extensionSettingsFieldHtml(field,values[field.key])).join('')
    : '<div class="extension-settings-empty">No configurable settings declared.</div>';
  return `<div class="extension-settings-box">
    <div class="extension-settings-head">
      <div>
        <div class="extension-settings-title">Browser-local extension settings</div>
        <div class="extension-settings-note">Settings and extension-owned storage stay in this browser. Do not store secrets here.</div>
      </div>
    </div>
    <div class="extension-settings-fields">${fields}</div>
    <div class="extension-settings-actions">
      <button class="sm-btn" type="button" data-extension-settings-save="${esc(id)}"${schema.length?'':' disabled aria-disabled="true"'}>Save settings</button>
      <button class="sm-btn" type="button" data-extension-settings-reset="${esc(id)}"${schema.length?'':' disabled aria-disabled="true"'}>Reset settings</button>
      <button class="sm-btn" type="button" data-extension-storage-clear="${esc(id)}">Clear extension storage</button>
    </div>
  </div>`;
}

function _extensionInstalledList(extensions,extensionDirConfigured){
  const list=Array.isArray(extensions)?extensions:[];
  if(!list.length){
    if(!extensionDirConfigured) return '<div class="extension-url-empty">No extension directory is configured.</div>';
    return '<div class="extension-url-empty">No manifest extensions are installed in the configured bundle.</div>';
  }
  return `<div class="extension-installed-list">${list.map(entry=>{
    const id=(entry&&entry.id)||'';
    const name=(entry&&entry.name)||id||'Unnamed extension';
    const canToggle=!!(entry&&entry.can_toggle);
    const userEnabled=!!(entry&&entry.user_enabled);
    const disabledAttr=canToggle?'':' disabled aria-disabled="true"';
    const buttonText=userEnabled?'Disable':'Enable';
    const nextEnabled=userEnabled?'false':'true';
    const note=canToggle
      ? 'Toggles the WebUI-managed override for the next app load.'
      : 'Manifest-disabled entries cannot be enabled from WebUI.';
    return `<div class="extension-installed-row" data-extension-id="${esc(id)}">
      <div class="extension-installed-main">
        <div class="extension-installed-title-row">
          <div class="extension-installed-title">${esc(name)}</div>
          ${_extensionEntryBadge(entry)}
        </div>
        <div class="extension-installed-meta"><code>${esc(id)}</code><span>${esc(note)}</span></div>
        ${_extensionSettingsControls(entry)}
      </div>
      <button class="sm-btn extension-toggle-btn" type="button" data-extension-toggle-id="${esc(id)}" data-extension-next-enabled="${nextEnabled}"${disabledAttr}>${esc(buttonText)}</button>
    </div>`;
  }).join('')}</div>`;
}

function _extensionSidecarHealthBadge(status,label){
  const safeStatus=['checking','healthy','unhealthy','blocked'].includes(status)?status:'checking';
  return `<span class="extension-sidecar-status-badge extension-sidecar-status-${safeStatus}">${esc(label||safeStatus)}</span>`;
}

function _extensionRuntimeStatusValue(value){
  const normalized=String(value||'').trim().toLowerCase();
  return ['running','connected','waiting','stale','unloaded','stopped','not_registered','unknown'].includes(normalized)
    ? normalized
    : 'unknown';
}

function _extensionRuntimeStatusLabel(value){
  const normalized=_extensionRuntimeStatusValue(value);
  if(normalized==='not_registered') return 'not registered';
  return normalized.replace(/_/g,' ');
}

function _extensionRuntimeLastSeen(value){
  const text=String(value??'').trim();
  if(!/^\d+(?:\.\d+)?$/.test(text)) return '';
  const raw=Number(text);
  if(!Number.isFinite(raw)||raw<=0) return '';
  const seconds=raw>1000000000000?raw/1000:raw;
  const now=Math.floor(Date.now()/1000);
  if(seconds>now+300) return '';
  const age=Math.max(0,Math.floor(now-seconds));
  if(age<5) return 'just now';
  if(age<60) return `${age}s ago`;
  const minutes=Math.floor(age/60);
  if(minutes<60) return `${minutes}m ago`;
  const hours=Math.floor(minutes/60);
  if(hours<24) return `${hours}h ago`;
  return `${Math.floor(hours/24)}d ago`;
}

function _extensionRuntimeOrigin(value){
  const text=String(value||'').trim();
  if(!text) return '';
  try{
    const parsed=new URL(text);
    if(parsed.protocol==='http:'&&(parsed.hostname==='127.0.0.1'||parsed.hostname==='localhost')){
      return parsed.origin;
    }
  }catch(_e){}
  return '';
}

function _extensionRuntimeRows(runtime){
  if(!runtime||typeof runtime!=='object') return [];
  const rows=[];
  if(Object.prototype.hasOwnProperty.call(runtime,'sidecar')){
    rows.push(['Sidecar',_extensionRuntimeStatusLabel(runtime.sidecar)]);
  }
  if(Object.prototype.hasOwnProperty.call(runtime,'native_host')){
    rows.push(['Native host',_extensionRuntimeStatusLabel(runtime.native_host)]);
  }
  if(Object.prototype.hasOwnProperty.call(runtime,'bridge')){
    rows.push(['Bridge',_extensionRuntimeStatusLabel(runtime.bridge)]);
  }
  const lastSeen=_extensionRuntimeLastSeen(runtime.last_seen_at);
  if(lastSeen) rows.push(['Last update',lastSeen]);
  const origin=_extensionRuntimeOrigin(runtime.webui_origin);
  if(origin) rows.push(['WebUI origin',origin]);
  return rows;
}

function _extensionRuntimeDetails(runtime){
  const rows=_extensionRuntimeRows(runtime);
  if(!rows.length) return '';
  return rows.map(([label,value])=>`<div><span>${esc(label)}</span><code>${esc(value)}</code></div>`).join('');
}

function _extensionSidecarCard(sidecars){
  const list=Array.isArray(sidecars)?sidecars:[];
  const body=list.length?`<div class="extension-sidecar-list">${list.map((sidecar,index)=>{
    const id=(sidecar&&sidecar.id)||'';
    const name=(sidecar&&sidecar.name)||'';
    const title=name||id||'Unnamed extension';
    const meta=(name&&id)?id:(sidecar&&sidecar.type)||'loopback';
    const origin=(sidecar&&sidecar.origin)||'';
    const healthPath=(sidecar&&sidecar.health_path)||'';
    const healthUrl=(sidecar&&sidecar.health_url)||'';
    const proxy=(sidecar&&sidecar.proxy&&typeof sidecar.proxy==='object')?sidecar.proxy:{};
    const proxyAvailable=proxy.available===true;
    const proxyConsented=proxy.consented===true;
    const proxyConsentRequired=proxy.consent_required===true;
    const proxyOriginChanged=proxy.origin_changed===true;
    const proxyPath=(proxy&&proxy.path)||'';
    // token-v1 posture: 'local_unprotected' = WebUI auth is off, so proxy consent
    // is grantable by any unauthenticated local caller. Warn the operator to
    // enable authentication before wiring up a sidecar (design §9.1).
    const proxyUnprotected=proxy.posture==='local_unprotected';
    const proxyWarning=proxyUnprotected
      ?`<div class="extension-sidecar-warning">⚠ WebUI authentication is off. This sidecar's proxy consent can be granted by any local process. Set a password in Settings → Password before using sidecar extensions.</div>`
      :'';
    const proxyStatus=proxyConsented
      ?'consented'
      :(proxyOriginChanged
        ?'reconfirm required'
        :(proxyConsentRequired
          ?'approval required'
          :'unavailable'));
    const proxyButton=(proxyAvailable&&id)
      ?`<button class="sm-btn extension-toggle-btn" type="button" data-extension-sidecar-proxy-id="${esc(id)}" data-extension-sidecar-proxy-approved="${proxyConsented?'false':'true'}">${esc(proxyConsented?'Revoke proxy consent':'Approve proxy consent')}</button>`
      :'';
    return `<div class="extension-sidecar-row" data-sidecar-index="${index}">
      <div class="extension-sidecar-row-head">
        <div class="extension-sidecar-title">${esc(title)}</div>
        <span id="extensionSidecarHealth${index}" data-sidecar-health-index="${index}">${_extensionSidecarHealthBadge('checking','checking')}</span>
      </div>
      <div class="extension-sidecar-meta">${esc(meta)}</div>
      <div class="extension-sidecar-fields">
        <div><span>Origin</span><code>${esc(origin)}</code></div>
        <div><span>Health path</span><code>${esc(healthPath)}</code></div>
        <div><span>Health URL</span><code>${esc(healthUrl)}</code></div>
        <div><span>Proxy</span><code>${esc(proxyStatus)}</code></div>
        <div><span>Proxy path</span><code>${esc(proxyPath)}</code></div>
      </div>
      <div class="extension-sidecar-actions">${proxyButton}</div>
      ${proxyWarning}
      <div class="extension-sidecar-runtime" data-sidecar-runtime-index="${index}" hidden></div>
    </div>`;
  }).join('')}</div>`:'<div class="extension-url-empty">No loopback sidecars declared.</div>';
  return `
    <div class="provider-card extension-sidecars-card">
      <div class="provider-card-header plugin-card-header">
        <div class="provider-card-info">
          <div class="provider-card-name">Loopback sidecars</div>
          <div class="provider-card-meta">Declared local companions; health is checked directly from this browser with WebUI credentials omitted.</div>
        </div>
      </div>
      <div class="provider-card-body extension-card-body">
        ${body}
      </div>
    </div>`;
}

function _setExtensionSidecarHealth(index,status,label){
  const el=document.querySelector(`[data-sidecar-health-index="${index}"]`);
  if(el) el.innerHTML=_extensionSidecarHealthBadge(status,label);
}

function _setExtensionSidecarRuntime(index,runtime){
  const el=document.querySelector(`[data-sidecar-runtime-index="${index}"]`);
  if(!el) return;
  const details=_extensionRuntimeDetails(runtime);
  if(!details){
    el.hidden=true;
    el.innerHTML='';
    return;
  }
  el.hidden=false;
  el.innerHTML=details;
}

async function _checkExtensionSidecarHealth(sidecar,index,seq){
  const healthUrl=sidecar&&sidecar.health_url;
  if(!healthUrl){
    _setExtensionSidecarHealth(index,'blocked','unreachable / blocked');
    _setExtensionSidecarRuntime(index,null);
    return;
  }
  let controller=null;
  let timeoutId=null;
  try{
    if(typeof AbortController!=='undefined'){
      controller=new AbortController();
      timeoutId=setTimeout(()=>controller.abort(),2500);
    }
    const res=await fetch(healthUrl,{credentials:'omit',cache:'no-store',signal:controller?controller.signal:undefined});
    if(seq!==_extensionsSidecarMonitorSeq) return;
    if(res.ok){
      _setExtensionSidecarHealth(index,'healthy','healthy');
      let body=null;
      try{
        body=await res.json();
      }catch(_e){}
      if(seq!==_extensionsSidecarMonitorSeq) return;
      _setExtensionSidecarRuntime(index,body&&typeof body==='object'?body.runtime:null);
    }else{
      _setExtensionSidecarHealth(index,'unhealthy','unhealthy');
      _setExtensionSidecarRuntime(index,null);
    }
  }catch(_e){
    if(seq!==_extensionsSidecarMonitorSeq) return;
    _setExtensionSidecarHealth(index,'blocked','unreachable / blocked');
    _setExtensionSidecarRuntime(index,null);
  }finally{
    if(timeoutId) clearTimeout(timeoutId);
  }
}

function _monitorExtensionSidecars(sidecars,seq){
  if(!Array.isArray(sidecars)||sidecars.length===0) return;
  sidecars.forEach((sidecar,index)=>_checkExtensionSidecarHealth(sidecar,index,seq));
}

function _renderExtensionsPanel(data,seq){
  const target=$('extensionsDiagnostics');
  const copyBtn=$('extensionsCopyDiagnosticsBtn');
  if(!target) return;
  _extensionsStatusData=data||null;
  _configureExtensionSettingsFromStatus(data);
  if(copyBtn) copyBtn.disabled=!data;
  const manifest=(data&&data.manifest)||{};
  const counts=(data&&data.counts)||{};
  const scripts=Array.isArray(data&&data.script_urls)?data.script_urls:[];
  const styles=Array.isArray(data&&data.stylesheet_urls)?data.stylesheet_urls:[];
  const sidecars=Array.isArray(data&&data.sidecars)?data.sidecars:[];
  const extensions=Array.isArray(data&&data.extensions)?data.extensions:[];
  const statusClass=(data&&data.enabled)?'extension-card-enabled':'extension-card-disabled';
  const scriptCount=_extensionCountValue(counts,'script_urls',scripts);
  const styleCount=_extensionCountValue(counts,'stylesheet_urls',styles);
  const sidecarCount=_extensionCountValue(counts,'sidecars',sidecars);
  const manifestExtensionCount=_extensionCountValue(counts,'manifest_extensions',extensions);
  const userDisabledCount=_extensionCountValue(counts,'user_disabled',[]);
  target.innerHTML=`
    <div class="provider-card extension-status-card ${statusClass}">
      <div class="provider-card-header plugin-card-header">
        <div class="provider-card-info">
          <div class="provider-card-name">Extension runtime</div>
          <div class="provider-card-meta">Status from /api/extensions/status; toggles persist a local override for installed manifest entries.</div>
        </div>
        <span class="provider-card-badge ${data&&data.enabled?'':'plugin-card-badge-disabled'}">${_extensionStatusLabel(!!(data&&data.enabled))}</span>
      </div>
      <div class="provider-card-body extension-card-body">
        <div class="extension-summary-grid">
          <div><span>Extension dir configured</span>${_extensionBooleanBadge(!!(data&&data.extension_dir_configured))}</div>
          <div><span>Extension dir valid</span>${_extensionBooleanBadge(!!(data&&data.extension_dir_valid))}</div>
          <div><span>Manifest configured</span>${_extensionBooleanBadge(!!manifest.configured)}</div>
          <div><span>Manifest loaded</span>${_extensionBooleanBadge(!!manifest.loaded)}</div>
          <div><span>Manifest status</span><code>${esc(manifest.status||'unknown')}</code></div>
          <div><span>Manifest entries inspected</span><code>${Number(manifest.entry_count)||0}</code></div>
          <div><span>Manifest script count</span><code>${Number(manifest.script_count)||0}</code></div>
          <div><span>Manifest stylesheet count</span><code>${Number(manifest.stylesheet_count)||0}</code></div>
          <div><span>Manifest sidecar count</span><code>${Number(manifest.sidecar_count)||0}</code></div>
          <div><span>Final script count</span><code>${scriptCount}</code></div>
          <div><span>Final stylesheet count</span><code>${styleCount}</code></div>
          <div><span>Loopback sidecar count</span><code>${sidecarCount}</code></div>
          <div><span>Installed manifest extensions</span><code>${manifestExtensionCount}</code></div>
          <div><span>User-disabled extensions</span><code>${userDisabledCount}</code></div>
        </div>
      </div>
    </div>
    <div class="provider-card extension-installed-card">
      <div class="provider-card-header plugin-card-header">
        <div class="provider-card-info">
          <div class="provider-card-name">Installed manifest extensions</div>
          <div class="provider-card-meta">Enable or disable already-present local extensions. Reload WebUI to apply injected asset changes to this browser tab.</div>
        </div>
      </div>
      <div class="provider-card-body extension-card-body">
        ${_extensionInstalledList(extensions,!!(data&&data.extension_dir_configured))}
      </div>
    </div>
    <div class="provider-card extension-assets-card">
      <div class="provider-card-header plugin-card-header">
        <div class="provider-card-info">
          <div class="provider-card-name">Final public asset URLs</div>
          <div class="provider-card-meta">Same-origin URLs that may be injected into the app shell.</div>
        </div>
      </div>
      <div class="provider-card-body extension-card-body">
        <div class="provider-card-label">Scripts</div>
        ${_extensionAssetList(scripts)}
        <div class="provider-card-label extension-section-label">Stylesheets</div>
        ${_extensionAssetList(styles)}
      </div>
    </div>
    ${_extensionSidecarCard(sidecars)}
    <div class="provider-card extension-warnings-card">
      <div class="provider-card-header plugin-card-header">
        <div class="provider-card-info">
          <div class="provider-card-name">Sanitized warnings</div>
          <div class="provider-card-meta">Codes and coarse sources only; paths and rejected values are not shown.</div>
        </div>
      </div>
      <div class="provider-card-body extension-card-body">
        ${_extensionWarningList(data&&data.warnings)}
      </div>
    </div>
  `;
  _bindExtensionToggleButtons(target);
  _bindExtensionSidecarProxyButtons(target);
  _bindExtensionSettingsButtons(target);
  _monitorExtensionSidecars(sidecars,seq);
}

function _bindExtensionToggleButtons(root){
  if(!root) return;
  root.querySelectorAll('[data-extension-toggle-id]').forEach(btn=>{
    btn.addEventListener('click',()=>handleExtensionToggle(btn));
  });
}

function _bindExtensionSidecarProxyButtons(root){
  if(!root) return;
  root.querySelectorAll('[data-extension-sidecar-proxy-id]').forEach(btn=>{
    btn.addEventListener('click',()=>handleExtensionSidecarProxyConsent(btn));
  });
}

async function handleExtensionToggle(btn){
  if(!btn||btn.disabled) return;
  const id=btn.dataset.extensionToggleId||'';
  const enabled=btn.dataset.extensionNextEnabled==='true';
  if(!id) return;
  const previousText=btn.textContent;
  btn.disabled=true;
  btn.textContent=enabled?'Enabling…':'Disabling…';
  try{
    const data=await api('/api/extensions/toggle',{method:'POST',body:JSON.stringify({id,enabled})});
    showToast(enabled?'Extension enabled. Reload WebUI to apply changes.':'Extension disabled. Reload WebUI to apply changes.');
    _renderExtensionsPanel(data,++_extensionsSidecarMonitorSeq);
  }catch(e){
    btn.disabled=false;
    btn.textContent=previousText;
    showToast('Failed to update extension: '+(e&&e.message?e.message:String(e)));
  }
}

async function handleExtensionSidecarProxyConsent(btn){
  if(!btn||btn.disabled) return;
  const id=btn.dataset.extensionSidecarProxyId||'';
  const approved=btn.dataset.extensionSidecarProxyApproved==='true';
  if(!id) return;
  const previousText=btn.textContent;
  btn.disabled=true;
  btn.textContent=approved?'Approving…':'Revoking…';
  try{
    const data=await api('/api/extensions/sidecar-proxy-consent',{method:'POST',body:JSON.stringify({id,approved})});
    showToast(approved?'Extension sidecar proxy approved.':'Extension sidecar proxy consent revoked.');
    _renderExtensionsPanel(data,++_extensionsSidecarMonitorSeq);
  }catch(e){
    btn.disabled=false;
    btn.textContent=previousText;
    showToast('Failed to update extension sidecar proxy consent: '+(e&&e.message?e.message:String(e)));
  }
}

function _readExtensionSettingsForm(row){
  const values={};
  row.querySelectorAll('[data-extension-setting-input]').forEach(input=>{
    const key=input.dataset.extensionSettingInput||'';
    const type=input.dataset.extensionSettingType||'';
    if(!key) return;
    if(type==='boolean') values[key]=!!input.checked;
    else if(type==='integer') values[key]=Number.parseInt(input.value,10);
    else if(type==='number') values[key]=Number.parseFloat(input.value);
    else values[key]=input.value;
  });
  return values;
}

function _fillExtensionSettingsForm(row,id){
  if(!window.HermesExtensionSettings) return;
  const values=window.HermesExtensionSettings.settingsForExtension(id).values;
  row.querySelectorAll('[data-extension-setting-input]').forEach(input=>{
    const key=input.dataset.extensionSettingInput||'';
    const type=input.dataset.extensionSettingType||'';
    const value=values[key];
    if(type==='boolean') input.checked=!!value;
    else input.value=value??'';
  });
}

function _bindExtensionSettingsButtons(root){
  if(!root) return;
  root.querySelectorAll('[data-extension-settings-save]').forEach(btn=>{
    btn.addEventListener('click',()=>handleExtensionSettingsSave(btn));
  });
  root.querySelectorAll('[data-extension-settings-reset]').forEach(btn=>{
    btn.addEventListener('click',()=>handleExtensionSettingsReset(btn));
  });
  root.querySelectorAll('[data-extension-storage-clear]').forEach(btn=>{
    btn.addEventListener('click',()=>handleExtensionStorageClear(btn));
  });
}

function handleExtensionSettingsSave(btn){
  const id=btn&&btn.dataset.extensionSettingsSave;
  const row=btn&&btn.closest('[data-extension-id]');
  if(!id||!row||!window.HermesExtensionSettings) return;
  const api=window.HermesExtensionSettings.settingsForExtension(id);
  const result=api.setAll(_readExtensionSettingsForm(row));
  if(!result.ok){
    showToast('Extension settings contain invalid values.');
    return;
  }
  _fillExtensionSettingsForm(row,id);
  showToast('Extension settings saved in this browser.');
}

function handleExtensionSettingsReset(btn){
  const id=btn&&btn.dataset.extensionSettingsReset;
  const row=btn&&btn.closest('[data-extension-id]');
  if(!id||!row||!window.HermesExtensionSettings) return;
  window.HermesExtensionSettings.settingsForExtension(id).reset();
  _fillExtensionSettingsForm(row,id);
  showToast('Extension settings reset in this browser.');
}

function handleExtensionStorageClear(btn){
  const id=btn&&btn.dataset.extensionStorageClear;
  if(!id||!window.HermesExtensionSettings) return;
  window.HermesExtensionSettings.storageForExtension(id).clear();
  showToast('Extension storage cleared in this browser.');
}

async function loadExtensionsPanel(opts){
  const target=$('extensionsDiagnostics');
  const copyBtn=$('extensionsCopyDiagnosticsBtn');
  if(!target) return;
  // Only preserve REAL rendered diagnostics across a refresh — never the
  // "Loading…" / error placeholders, or a failed refresh would leave the panel
  // stuck on "Loading extension diagnostics…" instead of rendering the error.
  const preserveExisting=!!(
    opts&&opts.preserveExisting&&target.innerHTML.trim()
    &&!target.querySelector('.extensions-loading,.extensions-error')
  );
  if(copyBtn&&!preserveExisting) copyBtn.disabled=true;
  const seq=++_extensionsSidecarMonitorSeq;
  if(!preserveExisting) target.innerHTML='<div class="extensions-loading">Loading extension diagnostics…</div>';
  try{
    const data=await api('/api/extensions/status');
    if(seq!==_extensionsSidecarMonitorSeq) return;
    _renderExtensionsPanel(data,seq);
  }catch(e){
    if(seq!==_extensionsSidecarMonitorSeq) return;
    if(preserveExisting&&target.innerHTML.trim()) return;
    _extensionsStatusData=null;
    if(copyBtn) copyBtn.disabled=true;
    target.innerHTML='<div class="extensions-error">Failed to load extension diagnostics: '+esc(e.message||String(e))+'</div>';
  }
  if(_extensionsActiveTab==='gallery'&&!_extensionsGalleryLoaded) loadExtensionsGallery();
}

function switchExtensionsTab(tab){
  _extensionsActiveTab=tab;
  document.querySelectorAll('[data-extensions-tab]').forEach(btn=>{
    btn.classList.toggle('extensions-tab-active',btn.dataset.extensionsTab===tab);
  });
  document.querySelectorAll('[data-extensions-pane]').forEach(pane=>{
    pane.hidden=pane.dataset.extensionsPane!==tab;
  });
  if(tab==='diagnostics') loadExtensionsPanel({preserveExisting:true});
  if(tab==='gallery'&&!_extensionsGalleryLoaded) loadExtensionsGallery();
}

function _extensionSafeHttpUrl(value){
  if(!value) return '';
  const raw=String(value).trim();
  if(!/^https?:\/\//i.test(raw)) return '';
  try{
    const url=new URL(raw);
    if(url.username||url.password) return '';
    return (url.protocol==='http:'||url.protocol==='https:')?url.href:'';
  }catch(_){
    return '';
  }
}

function _extensionRegistrySourceUrl(entryPath){
  const raw=String(entryPath||'').trim();
  if(!raw||raw.startsWith('/')||raw.includes('\\')||raw.includes('\0')) return '';
  const parts=raw.split('/').filter(Boolean);
  if(parts.length===0||parts.some(part=>part==='.'||part==='..')) return '';
  const folder=parts.length>1?parts.slice(0,-1):parts;
  return 'https://github.com/hermes-webui/hermes-webui-extensions/tree/main/'+folder.map(encodeURIComponent).join('/');
}

function _extensionSourceUrl(entry){
  if(!entry||typeof entry!=='object') return '';
  const candidates=[
    entry.homepage,
    entry.repository_url,
    entry.repo_url,
    entry.source_url,
    entry.source,
  ];
  const repository=entry.repository;
  if(typeof repository==='string'){
    candidates.push(repository);
  }else if(repository&&typeof repository==='object'){
    candidates.push(repository.url,repository.html_url);
  }
  for(const candidate of candidates){
    const safe=_extensionSafeHttpUrl(candidate);
    if(safe) return safe;
  }
  return _extensionSafeHttpUrl(_extensionRegistrySourceUrl(entry.entry_path||entry.runtime_manifest_path));
}

function _extensionSourceLink(entry){
  const url=_extensionSourceUrl(entry);
  if(!url) return '';
  return `<a class="extension-gallery-source-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Source</a>`;
}

function _extensionPermissionList(value){
  if(!Array.isArray(value)) return '';
  const items=value
    .map(item=>String(item||'').trim())
    .filter(Boolean);
  return items.length?items.join(', '):'';
}

function _extensionPermissionRows(perms){
  if(!perms||typeof perms!=='object') return [];
  const rows=[];
  const api=(perms.webui_api&&typeof perms.webui_api==='object')?perms.webui_api:{};
  const apiRead=_extensionPermissionList(api.read);
  const apiWrite=_extensionPermissionList(api.write);
  if(apiRead) rows.push(['WebUI API reads',apiRead]);
  if(apiWrite) rows.push(['WebUI API writes',apiWrite]);
  if(perms.webui_navigation===true) rows.push(['Navigation','Can open or switch WebUI views']);

  const sidecarCommands=(perms.sidecar_commands&&typeof perms.sidecar_commands==='object')?perms.sidecar_commands:{};
  const commandLabels=[
    ['from_loopback','accepts loopback commands'],
    ['can_switch_sessions','switch sessions'],
    ['can_write_drafts','write drafts'],
    ['can_autosend','auto-send drafts'],
    ['can_respond_approval','respond to approvals'],
    ['can_respond_clarify','respond to clarifications'],
  ];
  const commands=commandLabels
    .filter(([key])=>sidecarCommands[key]===true)
    .map(([,label])=>label);
  if(commands.length) rows.push(['Sidecar commands',commands.join(', ')]);

  const dom=(perms.dom&&typeof perms.dom==='object')?perms.dom:{};
  const domItems=[];
  if(dom.owned===true) domItems.push('renders extension-owned UI');
  if(dom.mutates_core_views===true) domItems.push('can alter core WebUI views');
  if(domItems.length) rows.push(['DOM access',domItems.join(', ')]);

  const storage=(perms.storage&&typeof perms.storage==='object')?perms.storage:{};
  const ownedStorage=_extensionPermissionList(storage.owned||storage.owned_keys);
  const sharedStorage=_extensionPermissionList(storage.shared_webui_keys);
  if(ownedStorage) rows.push(['Owned storage keys',ownedStorage]);
  if(sharedStorage) rows.push(['Shared WebUI storage',sharedStorage]);

  if(perms.loopback_sidecar===true) rows.push(['Loopback sidecar','Can contact a declared local loopback helper']);
  if(perms.native_host===true) rows.push(['Native host','Requires a local native host or desktop app']);

  const filesystem=(perms.filesystem&&typeof perms.filesystem==='object')?perms.filesystem:{};
  if(filesystem.arbitrary===true){
    rows.push(['Filesystem','Can access arbitrary filesystem paths']);
  }else if(filesystem.serves_bundled_assets===true){
    rows.push(['Filesystem','Serves bundled extension assets only']);
  }
  if(perms.network_external===true||perms.external_network===true){
    rows.push(['External network','Can contact external network origins']);
  }
  return rows;
}

function _extensionPermissionSummary(perms){
  const rows=_extensionPermissionRows(perms);
  const body=rows.length
    ? '<div class="extension-gallery-permission-list">'+rows.map(([label,value])=>`
      <div class="extension-gallery-permission-row">
        <span class="extension-gallery-permission-label">${esc(label)}</span>
        <span class="extension-gallery-permission-value">${esc(value)}</span>
      </div>`).join('')+'</div>'
    : `<div class="extension-gallery-permission-empty">${esc(t('ext_gallery_permissions_empty'))}</div>`;
  return `<details class="extension-gallery-perms">
    <summary>${esc(t('ext_gallery_permissions_show'))}</summary>
    ${body}
  </details>`;
}

function _extensionPostInstallNote(entry,isInstalled){
  const lifecycle=(entry&&entry.lifecycle&&typeof entry.lifecycle==='object')?entry.lifecycle:{};
  const post=(entry&&entry.post_install&&typeof entry.post_install==='object')?entry.post_install:null;
  const needsSidecar=!!lifecycle.sidecar_start_required;
  const needsNative=!!lifecycle.native_host_start_required;
  const summary=post&&post.summary?String(post.summary):(
    (needsSidecar||needsNative)
      ? t('ext_gallery_local_component_required')
      : ''
  );
  if(!summary) return '';
  const docsUrl=_extensionSafeHttpUrl(post&&post.docs_url);
  const localAppLabel=post&&post.local_app_label?String(post.local_app_label):t('ext_gallery_local_app_label');
  const chips=[];
  if(post&&post.requires_local_app===true) chips.push(t('ext_gallery_required_suffix',localAppLabel));
  if(needsSidecar) chips.push(t('ext_gallery_sidecar_required'));
  if(needsNative) chips.push(t('ext_gallery_native_host_required'));
  const chipHtml=chips.length
    ? '<div class="extension-gallery-next-chips">'+chips.map(item=>`<span>${esc(item)}</span>`).join('')+'</div>'
    : '';
  const docsHtml=docsUrl
    ? `<a class="extension-gallery-next-link" href="${esc(docsUrl)}" target="_blank" rel="noopener noreferrer">${esc(t('ext_gallery_open_setup_guide'))}</a>`
    : '';
  return `<div class="extension-gallery-next-step">
    <div class="extension-gallery-next-label">${esc(t(isInstalled?'ext_gallery_next_step':'ext_gallery_after_install'))}</div>
    <div class="extension-gallery-next-summary">${esc(summary)}</div>
    ${chipHtml}
    ${docsHtml}
  </div>`;
}

async function loadExtensionsGallery(){
  _extensionsGalleryLoaded=true;
  const galleryEl=$('extensionsGallery');
  const installedEl=$('extensionsInstalled');
  if(galleryEl) galleryEl.innerHTML='<div class="extensions-loading">Loading gallery…</div>';
  if(installedEl) installedEl.innerHTML='<div class="extensions-loading">Loading installed extensions…</div>';
  try{
    const [regData,statusData]=await Promise.all([
      api('/api/extensions/registry'),
      api('/api/extensions/status'),
    ]);
    _extensionsGalleryData={regData,statusData};
    _renderExtensionsGallery(regData.entries||[],statusData);
  }catch(e){
    _extensionsGalleryLoaded=false;
    const msg=esc(e&&e.message?e.message:String(e));
    if(galleryEl) galleryEl.innerHTML='<div class="extensions-error">Failed to load gallery: '+msg+'</div>';
    if(installedEl) installedEl.innerHTML='<div class="extensions-error">Failed to load extension status.</div>';
  }
}

function _renderExtensionsGallery(entries,statusData){
  const galleryEl=$('extensionsGallery');
  const installedEl=$('extensionsInstalled');
  _configureExtensionSettingsFromStatus(statusData);
  const installedIds=new Set();
  if(statusData&&statusData.gallery_installed){
    Object.keys(statusData.gallery_installed).forEach(id=>installedIds.add(id));
  }
  if(statusData&&Array.isArray(statusData.extensions)){
    statusData.extensions.forEach(e=>{ if(e&&e.id) installedIds.add(e.id); });
  }
  if(!Array.isArray(entries)||entries.length===0){
    if(galleryEl) galleryEl.innerHTML='<div class="extensions-empty">No extensions found in the registry.</div>';
    if(installedEl){
      installedEl.innerHTML=_extensionInstalledList(statusData&&statusData.extensions,!!(statusData&&statusData.extension_dir_configured));
      _bindExtensionToggleButtons(installedEl);
      _bindExtensionSettingsButtons(installedEl);
    }
    return;
  }
  const galleryCards=[];
  for(const entry of entries){
    const id=esc(String(entry.id||''));
    const name=esc(String(entry.name||entry.id||''));
    const author=esc(String(entry.author||''));
    const version=esc(String(entry.version||''));
    const desc=esc(String(entry.description||''));
    const caps=Array.isArray(entry.capabilities)?entry.capabilities:[];
    const perms=entry.permissions||null;
    const isInstalled=installedIds.has(String(entry.id||''));
    const restartRequired=!!(entry.lifecycle&&(entry.lifecycle.restart_required||entry.lifecycle.webui_restart_required));
    const badgesHtml=caps.map(c=>`<span class="extension-gallery-badge">${esc(String(c))}</span>`).join('');
    const metaBits=[];
    if(author) metaBits.push('by '+author);
    if(version) metaBits.push('v'+version);
    const sourceLinkHtml=_extensionSourceLink(entry);
    const metaHtml=(metaBits.length||sourceLinkHtml)
      ? `<div class="extension-gallery-meta">${metaBits.length?`<span>${metaBits.join(' · ')}</span>`:''}${sourceLinkHtml}</div>`
      : '';
    const permsHtml=perms?_extensionPermissionSummary(perms):'';
    const postInstallHtml=_extensionPostInstallNote(entry,isInstalled);
    const actionBtn=isInstalled
      ?`<button class="extension-gallery-uninstall-btn" data-ext-uninstall-id="${id}" type="button" data-i18n="ext_gallery_uninstall">Uninstall</button>`
      :`<button class="extension-gallery-install-btn" data-ext-install-id="${id}" type="button" data-i18n="ext_gallery_install">Install</button>`;
    const installedBadge=isInstalled?'<span class="extension-gallery-installed-badge">Installed</span>':'';
    const card=`<div class="extension-gallery-card">
      <div class="extension-gallery-head">
        <div class="extension-gallery-info">
          <div class="extension-gallery-name">${name}${installedBadge}</div>
          ${metaHtml}
        </div>
      </div>
      <div class="extension-gallery-desc">${desc}</div>
      ${badgesHtml?'<div class="extension-gallery-badge-row">'+badgesHtml+'</div>':''}
      ${postInstallHtml}
      ${permsHtml}
      <div class="extension-gallery-actions">${actionBtn}</div>
    </div>`;
    galleryCards.push(card);
  }
  if(galleryEl) galleryEl.innerHTML=galleryCards.length?galleryCards.join(''):'<div class="extensions-empty">No extensions found.</div>';
  if(installedEl){
    installedEl.innerHTML=_extensionInstalledList(statusData&&statusData.extensions,!!(statusData&&statusData.extension_dir_configured));
    _bindExtensionToggleButtons(installedEl);
    _bindExtensionSettingsButtons(installedEl);
  }
  _bindExtensionGalleryButtons(entries);
}

function _bindExtensionGalleryButtons(entries){
  const entryMap=new Map();
  if(Array.isArray(entries)) entries.forEach(e=>{if(e&&e.id)entryMap.set(String(e.id),e);});
  document.querySelectorAll('[data-ext-install-id]').forEach(btn=>{
    const entry=entryMap.get(btn.dataset.extInstallId);
    if(entry) btn.addEventListener('click',()=>handleExtensionInstall(btn,entry));
  });
  document.querySelectorAll('[data-ext-uninstall-id]').forEach(btn=>{
    btn.addEventListener('click',()=>handleExtensionUninstall(btn,btn.dataset.extUninstallId));
  });
}

async function handleExtensionInstall(btn,entry){
  if(!btn||btn.disabled) return;
  const previousText=btn.textContent;
  btn.disabled=true;
  btn.textContent=t('ext_gallery_installing');
  try{
    const result=await api('/api/extensions/install',{method:'POST',body:JSON.stringify({
      id:entry.id,
      download_url:entry.download_url||entry.download,
      sha256:entry.sha256,
    })});
    const restart=!!(entry.lifecycle&&(entry.lifecycle.restart_required||entry.lifecycle.webui_restart_required));
    const hasPostInstall=!!(entry.post_install||(entry.lifecycle&&(entry.lifecycle.sidecar_start_required||entry.lifecycle.native_host_start_required)));
    showToast(restart
      ? t('ext_gallery_install_restart_required')
      : (hasPostInstall?t('ext_gallery_install_followup'):t('ext_gallery_install_ok')));
    _extensionsGalleryLoaded=false;
    await loadExtensionsGallery();
  }catch(e){
    btn.disabled=false;
    btn.textContent=previousText;
    showToast('Install failed: '+(e&&e.message?e.message:String(e)));
  }
}

async function handleExtensionUninstall(btn,id){
  if(!btn||btn.disabled) return;
  const previousText=btn.textContent;
  btn.disabled=true;
  btn.textContent='Uninstalling…';
  try{
    await api('/api/extensions/uninstall',{method:'POST',body:JSON.stringify({id})});
    showToast('Extension uninstalled.');
    _extensionsGalleryLoaded=false;
    await loadExtensionsGallery();
  }catch(e){
    btn.disabled=false;
    btn.textContent=previousText;
    showToast('Uninstall failed: '+(e&&e.message?e.message:String(e)));
  }
}

async function copyExtensionsDiagnostics(){
  if(!_extensionsStatusData) return;
  const text=JSON.stringify(_extensionsStatusData,null,2);
  const success=()=>showToast(t('copied')||'Copied!');
  const fail=()=>showToast(t('copy_failed')||'Copy failed');
  if(typeof _copyText==='function'){
    _copyText(text).then(success).catch(fail);
    return;
  }
  if(typeof navigator!=='undefined'&&navigator&&navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(text).then(success).catch(fail);
  }else{
    fail();
  }
}

// ── Plugins panel (read-only plugin/hook visibility) ───────────────────────

async function handlePluginEnableToggle(pluginKey, checked){
  try{
    const body={dashboard_plugins:{}};
    body.dashboard_plugins[pluginKey]=!!checked;
    await api('/api/settings',{method:'POST',body:JSON.stringify(body)});
    loadPluginsPanel();
  }catch(e){
    showToast(t('settings_save_failed')+e.message);
  }
}

function _pluginActivationState(plugin){
  const activation=(plugin&&typeof plugin.activation==='string')
    ? plugin.activation
    : (plugin&&plugin.enabled===false ? 'disabled' : 'enabled');
  // Mirror _buildPluginCard's isProviderActive precedence: an explicit
  // is_active_provider===true overrides the activation string so the sort
  // bucket always matches the badge.
  if(plugin&&plugin.is_active_provider===true) return 'provider';
  if(activation==='exclusive'||activation==='provider'){
    if(plugin&&plugin.is_active_provider===false) return 'disabled';
    return 'provider';
  }
  if(activation==='enabled') return 'enabled';
  return 'disabled';
}

function _partitionPluginsActiveFirst(plugins){
  const active=[];
  const inactive=[];
  for(const p of plugins){
    if(_pluginActivationState(p)==='disabled') inactive.push(p);
    else active.push(p);
  }
  return active.concat(inactive);
}

async function loadPluginsPanel(){
  const list=$('pluginsList');
  const empty=$('pluginsEmpty');
  if(!list) return;
  try{
    const data=await api('/api/plugins');
    const plugins=Array.isArray((data||{}).plugins)?data.plugins:[];
    // Hide the Plugins tab when no plugins are installed (#3457)
    const tabBtn=document.querySelector('[data-settings-section="plugins"]');
    if(tabBtn) tabBtn.style.display=(data&&data.empty)?'none':'';
    list.innerHTML='';
    if(plugins.length===0){
      list.style.display='none';
      if(empty) empty.style.display='';
      return;
    }
    if(empty) empty.style.display='none';
    list.style.display='';
    for(const plugin of _partitionPluginsActiveFirst(plugins)){
      list.appendChild(_buildPluginCard(plugin));
    }
  }catch(e){
    list.innerHTML='<div style="color:var(--error);padding:12px;font-size:13px">'+t('plugins_load_failed')+esc(e.message||String(e))+'</div>';
  }
}

function _buildPluginCard(plugin){
  const card=document.createElement('div');
  card.className='provider-card plugin-card';
  card.dataset.plugin=(plugin&&plugin.key)||'';
  // `activation` is the canonical state from /api/plugins (added in #2659).
  // Fall back to the older `enabled` boolean when the field is missing so
  // the panel still works against older backends.
  const activation=(plugin&&typeof plugin.activation==='string')
    ? plugin.activation
    : (plugin&&plugin.enabled===false ? 'disabled' : 'enabled');
  const isProvider=activation==='exclusive'||activation==='provider';
  const hooks=Array.isArray(plugin&&plugin.hooks)?plugin.hooks:[];
  // Provider plugins (memory/web/browser/etc.) register hooks on their
  // category's dispatcher, not the four agent-wide visibility hooks the
  // payload filters to. Show an explanatory line instead of the generic
  // "No registered lifecycle hooks" when the visibility-hook list is empty.
  const hookHtml=hooks.length
    ? hooks.map(h=>`<span class="plugin-hook-badge">${esc(h)}</span>`).join('')
    : '<span class="plugin-hook-empty">'+t(isProvider?'plugins_provider_no_hooks':'plugins_no_hooks')+'</span>';
  const version=(plugin&&plugin.version)?' · v'+esc(plugin.version):'';
  const desc=(plugin&&plugin.description)?esc(plugin.description):t('plugins_no_description');
const enabled=plugin&&plugin.enabled!==false;
  const tab=plugin&&plugin.tab;
  const isDashboardPlugin=!!(tab&&tab.path);
  // No inline onclick/onchange: an inline handler interpolates tab.path/key into
  // a JS-string-in-attribute context where HTML-escaping is insufficient (a
  // crafted value could break out). Render inert markup + bind listeners below
  // with the raw closure values.
  const openBtn=enabled&&tab&&tab.path
    ? `<a href="${esc(tab.path)}" class="plugin-open-btn">${esc(tab.label||plugin.name||'Open')} \u2197</a>`
    : '';
  const toggleHtml=enabled&&isDashboardPlugin
    ? `<div class="plugin-card-footer-row">
         <span class="plugin-toggle-label">${t('plugins_enable_toggle')||'Enabled'}</span>
         <label class="plugin-toggle-switch">
           <input type="checkbox" class="plugin-enable-toggle" checked>
           <span class="plugin-toggle-slider"></span>
         </label>
       </div>`
    : (isDashboardPlugin
    ? `<div class="plugin-card-footer-row">
         <span class="plugin-toggle-label">${t('plugins_enable_toggle')||'Enable'}</span>
         <label class="plugin-toggle-switch">
           <input type="checkbox" class="plugin-enable-toggle">
           <span class="plugin-toggle-slider"></span>
         </label>
       </div>`
    : '');
  const isProviderActive = plugin&&typeof plugin.is_active_provider==='boolean'
    ? plugin.is_active_provider
    : isProvider;
  let badgeText;
  let badgeClass;
  if(isProviderActive){
    badgeText=t('plugins_active_provider');
    badgeClass='plugin-card-badge-provider';
  }else if(activation==='enabled'){
    badgeText=t('plugins_enabled');
    badgeClass='';
  }else{
    badgeText=t('plugins_disabled');
    badgeClass='plugin-card-badge-disabled';
  }
  card.innerHTML=`
    <div class="provider-card-header plugin-card-header">
      <div class="provider-card-info">
        <div class="provider-card-name">${esc((plugin&&plugin.name)||t('plugins_unnamed'))}</div>
        <div class="provider-card-meta">${esc((plugin&&plugin.key)||'plugin')}${version}</div>
      </div>
      <span class="provider-card-badge ${badgeClass}">${badgeText}</span>
    </div>
    <div class="provider-card-body plugin-card-body">
      <div class="provider-card-hint">${desc}</div>
      <div class="provider-card-label">${t('plugins_registered_hooks')}</div>
      <div class="plugin-hook-list">${hookHtml}</div>
      ${openBtn ? `<div class="plugin-card-footer">${openBtn}</div>` : ''}
      ${toggleHtml}
    </div>
  `;
  // Bind handlers with the RAW closure values (not interpolated into inline JS),
  // so a hostile tab.path/key can't break out of a JS-string attribute context.
  if(tab&&tab.path){
    const _openEl=card.querySelector('.plugin-open-btn');
    if(_openEl){
      const _p=tab.path, _l=tab.label||plugin.name;
      _openEl.addEventListener('click', function(ev){ switchPluginPage(ev, _p, _l); });
    }
  }
  if(isDashboardPlugin){
    const _tog=card.querySelector('.plugin-enable-toggle');
    if(_tog){
      const _k=plugin.key;
      _tog.addEventListener('change', function(){ handlePluginEnableToggle(_k, this.checked); });
    }
  }
  return card;
}

// ── Plugin pages ─────────────────────────────────────────────────────────────

let _currentPluginPage = null;

async function switchPluginPage(event, path, label) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }
  if (!_currentPluginPage || _currentPluginPage.path !== path) {
    await _loadPluginPage(path, label);
  }
  // Update _currentPanel so clicking sidebar items won't short-circuit,
  // but keep the sidebar panel views intact (no panelPlugin exists).
  _currentPanel = 'plugin';
  const mainEl = document.querySelector('main.main');
  if (mainEl) {
    MAIN_VIEW_PANELS.forEach(p => {
      mainEl.classList.toggle('showing-' + p, p === 'plugin');
    });
  }
}

async function _loadPluginPage(path, label) {
  const container = $('pluginPageContainer');
  const titleEl = $('pluginPageTitle');
  if (!container) return;
  if (titleEl) titleEl.textContent = label || path;
  container.innerHTML = '';

  // Use an iframe for full isolation (styles, scripts, modals stay sandboxed).
  // Security note: plugins are locally-installed (~/.hermes/plugins/), similar
  // trust model to VS Code extensions — only install plugins you trust.
  const iframe = document.createElement('iframe');
  iframe.src = path;
  iframe.style.cssText = 'width:100%;height:100%;border:none;display:block;';
  iframe.setAttribute('title', label || 'Plugin');
  iframe.setAttribute('sandbox', 'allow-scripts allow-forms allow-popups');
  container.appendChild(iframe);
  _currentPluginPage = { path, label };
}

// ── Providers panel ─────────────────────────────────────────────────────────

const _providerCardEls = new Map(); // providerId → entry used by save/remove/test handlers
const _SELF_HOSTED_DEFAULT_BASE_URLS = Object.freeze({
  ollama: 'http://localhost:11434/v1',
  lmstudio: 'http://localhost:1234/v1',
});

async function _fetchProviderQuotaStatus(force=false){
  const endpoint=force?`/api/provider/quota?refresh=1&ts=${Date.now()}`:'/api/provider/quota';
  const status=await api(endpoint,{cache:'no-store'});
  if(status&&typeof status==='object') status.client_fetched_at=new Date().toISOString();
  return status;
}

async function loadProvidersPanel(){
  const list=$('providersList');
  const empty=$('providersEmpty');
  if(!list) return;
  try{
    const data=await api('/api/providers');
    const quota=await _fetchProviderQuotaStatus(false).catch(e=>({ok:false,status:'unavailable',quota:null,message:e.message||t('provider_quota_unavailable'),client_fetched_at:new Date().toISOString()}));
    const providers=(data.providers||[]).filter(p=>p.configurable||p.is_oauth||p.is_custom||p.is_plugin_provider||p.is_self_hosted);
    list.innerHTML='';
    _providerCardEls.clear();
    const quotaCard=_buildProviderQuotaCard(quota);
    if(quotaCard){
      list.appendChild(quotaCard);
      renderProviderCostChart(quotaCard); // async, fire-and-forget
    }
    if(providers.length===0){
      list.style.display='none';
      if(empty) empty.style.display='';
      return;
    }
    if(empty) empty.style.display='none';
    list.style.display='';
    for(const p of providers){
      list.appendChild(_buildProviderCard(p));
    }
  }catch(e){
    list.innerHTML='<div style="color:var(--error);padding:12px;font-size:13px">Failed to load providers: '+esc(e.message||String(e))+'</div>';
  }
}

async function _refreshProviderQuota(card,button){
  if(!card) return;
  if(button){
    button.disabled=true;
    button.textContent=t('provider_quota_refreshing');
    button.setAttribute('aria-busy','true');
  }
  let failed=false;
  let next;
  try{
    next=await _fetchProviderQuotaStatus(true);
    failed=next&&next.ok===false;
  }catch(e){
    failed=true;
    next={ok:false,status:'unavailable',quota:null,message:e.message||t('provider_quota_unavailable'),client_fetched_at:new Date().toISOString()};
  }
  try{
    const fresh=_buildProviderQuotaCard(next);
    if(fresh){
      card.replaceWith(fresh);
      // Re-render the 7-day spend chart onto the rebuilt card — the quota
      // refresh replaces the whole card, which would otherwise drop the chart
      // until the next full panel reload (#3600).
      renderProviderCostChart(fresh); // async, fire-and-forget
      if(typeof showToast==='function') showToast(failed?t('provider_quota_refresh_failed'):t('provider_quota_refresh_succeeded'));
      return;
    }
  }catch(e){
    failed=true;
  }
  if(card.isConnected&&button){
    button.disabled=false;
    button.textContent=t('provider_quota_refresh_usage');
    button.removeAttribute('aria-busy');
  }
  if(typeof showToast==='function') showToast(t('provider_quota_refresh_failed'));
}

function _formatProviderQuotaMoney(value){
  if(value===null||value===undefined||value==='') return '—';
  const n=Number(value);
  if(!Number.isFinite(n)) return '—';
  return '$'+n.toFixed(2);
}

function _formatProviderQuotaPercent(value){
  if(value===null||value===undefined||value==='') return '—';
  const n=Number(value);
  if(!Number.isFinite(n)) return '—';
  return Math.max(0,Math.min(100,Math.round(n)))+'%';
}

function _formatProviderQuotaReset(value){
  if(!value) return '';
  const d=new Date(value);
  if(Number.isNaN(d.getTime())) return '';
  try{return d.toLocaleString();}catch(e){return value;}
}

function _formatProviderQuotaWindowLabel(accountLimits,w){
  const raw=((w&&w.label)||t('provider_quota_window_fallback')).trim();
  const provider=((accountLimits&&accountLimits.provider)||'').toLowerCase();
  if(provider==='openai-codex'){
    if(raw.toLowerCase()==='session') return t('provider_quota_session_limit');
    if(raw.toLowerCase()==='weekly') return t('provider_quota_weekly_limit');
  }
  return raw||t('provider_quota_window_fallback');
}

function _formatProviderQuotaLastChecked(status){
  const accountLimits=status&&status.account_limits;
  const value=(accountLimits&&accountLimits.fetched_at)||status&&status.client_fetched_at;
  if(!value) return t('provider_quota_last_checked_after_refresh');
  const d=new Date(value);
  if(Number.isNaN(d.getTime())) return t('provider_quota_last_checked_after_refresh');
  try{return t('provider_quota_last_checked',d.toLocaleString());}catch(e){return t('provider_quota_last_checked',value);}
}

function _providerQuotaStateClass(value){
  return String(value||'unavailable').replace(/[^a-z0-9_-]/gi,'').toLowerCase()||'unavailable';
}

function _providerQuotaStatusLabel(value){
  const state=_providerQuotaStateClass(value);
  const key={
    available:'provider_quota_status_available',
    exhausted:'provider_quota_status_exhausted',
    unavailable:'provider_quota_status_unavailable',
    failed:'provider_quota_status_failed',
    checked:'provider_quota_status_checked',
    no_key:'provider_quota_status_no_key',
    invalid_key:'provider_quota_status_invalid_key',
    unsupported:'provider_quota_status_unsupported',
  }[state];
  return key?t(key):state.replace(/_/g,' ');
}

function _providerQuotaWindowMeta(used,reset){
  const meta=[];
  if(used!=='—') meta.push(t('provider_quota_used_meta',used));
  if(reset) meta.push(t('provider_quota_resets_meta',reset));
  return meta;
}

function _providerQuotaRetryAfterText(value){
  const retry=_formatProviderQuotaReset(value);
  return retry?t('provider_quota_retry_after',retry):'';
}

function _providerQuotaUnavailableReason(credential){
  const structured=_providerQuotaRetryAfterText(credential&&credential.retry_after);
  if(structured) return structured;
  const raw=String((credential&&credential.unavailable_reason)||'').trim();
  const match=raw.match(/\bretry after\s+([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.+-]+Z?)/i);
  if(match){
    const parsed=_providerQuotaRetryAfterText(match[1]);
    if(parsed) return parsed;
  }
  return raw;
}

function _providerQuotaPoolShouldDefaultOpen(pool){
  try{
    const saved=localStorage.getItem('hermes-provider-quota-pool-open');
    if(saved==='1') return true;
    if(saved==='0') return false;
  }catch(e){}
  const count=Array.isArray(pool&&pool.credentials)?pool.credentials.length:0;
  return count>0&&count<=3;
}

function _buildProviderQuotaPoolBreakdown(accountLimits){
  const pool=accountLimits&&accountLimits.pool;
  if(!pool||!Array.isArray(pool.credentials)||pool.credentials.length===0) return '';
  const defaultOpen=_providerQuotaPoolShouldDefaultOpen(pool);
  const total=Number.isFinite(Number(pool.total_credentials))?Number(pool.total_credentials):pool.credentials.length;
  const available=Number.isFinite(Number(pool.available_credentials))?Number(pool.available_credentials):pool.credentials.filter(c=>c&&c.status==='available').length;
  const exhausted=Number.isFinite(Number(pool.exhausted_credentials))?Number(pool.exhausted_credentials):0;
  const failed=Number.isFinite(Number(pool.failed_credentials))?Number(pool.failed_credentials):0;
  const queried=Number.isFinite(Number(pool.queried_credentials))?Number(pool.queried_credentials):0;
  const summaryParts=[t('provider_quota_pool_summary_available',available,total)];
  if(exhausted>0) summaryParts.push(t('provider_quota_pool_summary_exhausted',exhausted));
  if(failed>0) summaryParts.push(t('provider_quota_pool_summary_failed',failed));
  if(queried>0) summaryParts.push(t('provider_quota_pool_summary_checked',queried));
  const planParts=Array.isArray(pool.plans)?pool.plans.filter(Boolean):[];
  const rows=pool.credentials.map((credential,idx)=>{
    const label=(credential&&credential.label)||t('provider_quota_credential_label',idx+1);
    const status=_providerQuotaStateClass(credential&&credential.status);
    const statusText=_providerQuotaStatusLabel(credential&&credential.status);
    const plan=credential&&credential.plan?` · ${credential.plan}`:'';
    const windows=Array.isArray(credential&&credential.windows)?credential.windows:[];
    const details=Array.isArray(credential&&credential.details)?credential.details.filter(Boolean):[];
    const unavailableReason=_providerQuotaUnavailableReason(credential);
    const windowHtml=windows.length?windows.map(w=>{
      const remaining=_formatProviderQuotaPercent(w&&w.remaining_percent);
      const used=_formatProviderQuotaPercent(w&&w.used_percent);
      const reset=_formatProviderQuotaReset(w&&w.reset_at);
      const meta=_providerQuotaWindowMeta(used,reset);
      const detail=(w&&w.detail)?String(w.detail).trim():'';
      return `<div class="provider-quota-pool-window"><span>${esc(_formatProviderQuotaWindowLabel(accountLimits,w))}</span><strong>${esc(remaining)}</strong>${meta.length?`<small>${esc(meta.join(' · '))}</small>`:''}${detail?`<small class="provider-quota-window-detail">${esc(detail)}</small>`:''}</div>`;
    }).join(''):`<div class="provider-quota-pool-note">${esc(unavailableReason||t('provider_quota_pool_no_windows'))}</div>`;
    const detailHtml=details.length?`<div class="provider-quota-pool-details">${details.map(d=>`<span>${esc(d)}</span>`).join('')}</div>`:'';
    return `
      <div class="provider-quota-pool-row provider-quota-pool-row-${status}">
        <div class="provider-quota-pool-row-head">
          <span>${esc(label)}${esc(plan)}</span>
          <strong>${esc(statusText)}</strong>
        </div>
        <div class="provider-quota-pool-windows">${windowHtml}</div>
        ${detailHtml}
      </div>
    `;
  }).join('');
  const planText=planParts.length?`<div class="provider-quota-pool-plans">${esc(t('provider_quota_pool_plans',planParts.join(', ')))}</div>`:'';
  return `
    <details class="provider-quota-pool"${defaultOpen?' open':''}>
      <summary><span class="provider-quota-pool-summary-label"><span class="provider-quota-pool-chevron" aria-hidden="true"></span><span>${esc(t('provider_quota_credential_pool'))}</span></span><strong>${esc(summaryParts.join(' · '))}</strong></summary>
      ${planText}
      <div class="provider-quota-pool-rows">${rows}</div>
    </details>
  `;
}

function _buildProviderQuotaCard(status){
  if(!status) return null;
  const card=document.createElement('div');
  const state=(status.status||'unavailable').replace(/[^a-z0-9_-]/gi,'').toLowerCase()||'unavailable';
  card.className='provider-quota-card provider-quota-card-'+state;
  const accountLimits=status.account_limits||null;
  const providerBase=status.display_name||status.provider||t('provider_quota_active_provider');
  const provider=(accountLimits&&accountLimits.plan)?`${providerBase} · ${accountLimits.plan}`:providerBase;
  const quota=status.quota||null;
  let body='';
  if(accountLimits&&(status.status==='available'||accountLimits.pool)){
    const windows=Array.isArray(accountLimits.windows)?accountLimits.windows:[];
    const details=Array.isArray(accountLimits.details)&&!accountLimits.pool?accountLimits.details:[];
    const windowHtml=windows.map(w=>{
      const used=_formatProviderQuotaPercent(w&&w.used_percent);
      const reset=_formatProviderQuotaReset(w&&w.reset_at);
      const meta=_providerQuotaWindowMeta(used,reset);
      const detail=(w&&w.detail)?String(w.detail).trim():'';
      return `
        <div class="provider-quota-metric provider-quota-window">
          <span>${esc(_formatProviderQuotaWindowLabel(accountLimits,w))}</span>
          <strong>${esc(_formatProviderQuotaPercent(w&&w.remaining_percent))}</strong>
          ${meta.length?`<small>${esc(meta.join(' · '))}</small>`:''}
          ${detail?`<small class="provider-quota-window-detail">${esc(detail)}</small>`:''}
        </div>
      `;
    }).join('');
    const detailHtml=details.length
      ? `<div class="provider-quota-details">${details.map(d=>`<span>${esc(d)}</span>`).join('')}</div>`
      : '';
    const poolHtml=_buildProviderQuotaPoolBreakdown(accountLimits);
    body=windowHtml+detailHtml+poolHtml;
    if(!body) body=`<div class="provider-quota-message">${esc(status.message||t('provider_quota_account_limits_loaded'))}</div>`;
  }else if(status.status==='available'&&quota){
    body=`
      <div class="provider-quota-metric"><span>${esc(t('provider_quota_metric_remaining'))}</span><strong>${esc(_formatProviderQuotaMoney(quota.limit_remaining))}</strong></div>
      <div class="provider-quota-metric"><span>${esc(t('provider_quota_metric_used'))}</span><strong>${esc(_formatProviderQuotaMoney(quota.usage))}</strong></div>
      <div class="provider-quota-metric"><span>${esc(t('provider_quota_metric_limit'))}</span><strong>${esc(_formatProviderQuotaMoney(quota.limit))}</strong></div>
    `;
  }else{
    body=`<div class="provider-quota-message">${esc(status.message||t('provider_quota_unavailable'))}</div>`;
  }
  card.innerHTML=`
    <div class="provider-quota-header">
      <div>
        <div class="provider-quota-title">${esc(t('provider_quota_title'))}</div>
        <div class="provider-quota-subtitle">${esc(provider)}</div>
        <div class="provider-quota-checked">${esc(_formatProviderQuotaLastChecked(status))}</div>
      </div>
      <div class="provider-quota-actions">
        <span class="provider-quota-badge">${esc(_providerQuotaStatusLabel(state))}</span>
        <button class="provider-quota-refresh" type="button" data-provider-quota-refresh title="${esc(t('provider_quota_refresh_title'))}">${esc(t('provider_quota_refresh_usage'))}</button>
      </div>
    </div>
    <div class="provider-quota-body">${body}</div>
  `;
  const refreshBtn=card.querySelector('[data-provider-quota-refresh]');
  if(refreshBtn) refreshBtn.addEventListener('click',()=>_refreshProviderQuota(card,refreshBtn));
  const poolDetails=card.querySelector('.provider-quota-pool');
  if(poolDetails){
    poolDetails.addEventListener('toggle',()=>{
      try{localStorage.setItem('hermes-provider-quota-pool-open',poolDetails.open?'1':'0');}catch(e){}
    });
  }
  return card;
}

async function renderProviderCostChart(card){
  let history;
  try{
    history=await api('/api/provider/cost-history?provider=openrouter');
  }catch(e){
    return; // silently skip if endpoint unavailable
  }
  const body=card.querySelector('.provider-quota-body');
  if(!body||body.querySelector('.provider-cost-chart-wrap')) return;
  if(!history||history.ok===false){
    const wrap=document.createElement('div');
    wrap.className='provider-cost-chart-wrap';
    _attachBudgetControls(wrap,history||{},card,0);
    body.appendChild(wrap);
    return;
  }
  const snaps=Array.isArray(history.snapshots)?history.snapshots:[];
  // need at least 2 snapshots to have one non-null delta
  const hasData=snaps.filter(s=>s.delta!=null).length>=1;
  if(!hasData){
    const empty=document.createElement('div');
    empty.className='provider-cost-chart-wrap';
    empty.innerHTML='<div class="provider-cost-chart-title">7-day spend</div><div class="provider-quota-message">Not enough data yet. Cost chart builds after 2 daily snapshots.</div>';
    body.appendChild(empty);
    _attachBudgetControls(empty,history,card,0);
    return;
  }
  const maxDelta=Math.max(...snaps.map(s=>s.delta!=null?Number(s.delta):0),1e-9);
  const nonNull=snaps.filter(s=>s.delta!=null).map(s=>Number(s.delta));
  const avg=nonNull.length?nonNull.reduce((a,b)=>a+b,0)/nonNull.length:0;
  const paceNum=avg*30;
  const pace='$'+paceNum.toFixed(2);
  const bars=snaps.map(s=>{
    const delta=s.delta!=null?Number(s.delta):null;
    const pct=delta!=null?Math.max((delta/maxDelta)*100,delta>0?2:0).toFixed(1):'0';
    const label=String(s.date||'').slice(5);
    const tip=delta!=null?`${s.date} · $${delta.toFixed(4)}`:`${s.date} · no baseline`;
    return `<div class="insights-daily-bar" title="${esc(tip)}"><div class="insights-daily-stack" aria-label="${esc(tip)}"><div class="insights-daily-bar-input" style="height:${pct}%"></div></div><span>${esc(label)}</span></div>`;
  }).join('');
  const wrap=document.createElement('div');
  wrap.className='provider-cost-chart-wrap';
  wrap.innerHTML=`<div class="provider-cost-chart-title">7-day spend <span class="provider-cost-chart-pace">Monthly pace: ${esc(pace)}</span></div><div class="provider-cost-chart-bars insights-daily-token-chart">${bars}</div>`;
  const monthly_budget=history&&history.monthly_budget!=null?history.monthly_budget:null;
  if(monthly_budget!=null&&paceNum>0){
    const paceSpan=wrap.querySelector('.provider-cost-chart-pace');
    if(paceSpan){
      const pct=Math.round((paceNum/monthly_budget)*100);
      const pctSpan=document.createElement('span');
      pctSpan.className='provider-cost-chart-pct'+(pct>=100?' over':pct>=80?' warn':'');
      pctSpan.textContent=`(${pct}%)`;
      paceSpan.appendChild(pctSpan);
    }
  }
  body.appendChild(wrap);
  _attachBudgetControls(wrap,history,card,paceNum);
}

function _attachBudgetControls(wrap,history,card,paceNum){
  const budget=history&&history.monthly_budget!=null?Number(history.monthly_budget):null;
  const row=document.createElement('div');
  row.className='provider-cost-budget-row';

  const titleDiv=document.createElement('div');
  titleDiv.className='provider-cost-budget-title';
  titleDiv.textContent=t('provider_cost_budget_label');
  row.appendChild(titleDiv);

  const inputGroup=document.createElement('div');
  inputGroup.className='provider-cost-budget-input-group';

  const prefix=document.createElement('span');
  prefix.className='provider-cost-budget-prefix';
  prefix.textContent='$';
  inputGroup.appendChild(prefix);

  const input=document.createElement('input');
  input.type='number';
  input.min='0.01';
  input.step='0.01';
  input.className='provider-cost-budget-input';
  input.placeholder=t('provider_cost_budget_placeholder')||'e.g. 50.00';
  if(budget!=null) input.value=budget.toFixed(2);
  inputGroup.appendChild(input);

  const setBtn=document.createElement('button');
  setBtn.type='button';
  setBtn.className='provider-cost-budget-set';
  setBtn.textContent=t('provider_cost_budget_set');
  inputGroup.appendChild(setBtn);

  const clearBtn=document.createElement('button');
  clearBtn.type='button';
  clearBtn.className='provider-cost-budget-clear';
  clearBtn.textContent=t('provider_cost_budget_clear');
  if(budget==null) clearBtn.style.display='none';
  inputGroup.appendChild(clearBtn);

  row.appendChild(inputGroup);

  if(budget!=null&&paceNum>0){
    const pct=Math.round((paceNum/budget)*100);
    const barWrap=document.createElement('div');
    barWrap.className='provider-cost-budget-bar-wrap';
    const bar=document.createElement('div');
    bar.className='provider-cost-budget-bar';
    const fill=document.createElement('div');
    fill.className='provider-cost-budget-bar-fill'+(pct>=100?' over':pct>=80?' warn':'');
    fill.style.width=Math.min(100,pct)+'%';
    bar.appendChild(fill);
    barWrap.appendChild(bar);
    const pctLabel=document.createElement('span');
    pctLabel.className='provider-cost-budget-pct-label';
    pctLabel.textContent=t('provider_cost_budget_pct',pct,budget.toFixed(2));
    barWrap.appendChild(pctLabel);
    row.appendChild(barWrap);
  }

  wrap.appendChild(row);

  async function _saveBudget(value){
    try{
      await api('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider_cost_budget:value})});
      const existing=card.querySelector('.provider-cost-chart-wrap');
      if(existing) existing.remove();
      renderProviderCostChart(card);
    }catch(e){
      if(typeof showToast==='function') showToast(t('provider_cost_budget_save_failed'));
    }
  }

  setBtn.addEventListener('click',()=>{
    const val=parseFloat(input.value);
    if(!isFinite(val)||val<=0) return;
    _saveBudget(val);
  });

  clearBtn.addEventListener('click',()=>{
    _saveBudget(null);
  });
}

function _buildProviderCard(p){
  const card=document.createElement('div');
  card.className='provider-card';
  card.dataset.provider=p.id;
  // Use the is_oauth flag from the backend — it reflects _OAUTH_PROVIDERS in providers.py.
  // key_source can be 'oauth' (hermes auth), 'config_yaml' (token in config.yaml), or 'none'.
  const isOauth=p.is_oauth===true;
  // models_total reflects the complete catalog (e.g. 396 for a large-tier
  // Nous Portal account). The "models" array may be trimmed to a featured
  // subset for UI scannability — fall back to its length only when the
  // server didn't supply models_total (older builds, custom providers).
  const modelCount=Number.isFinite(p.models_total)
    ? p.models_total
    : (Array.isArray(p.models) ? p.models.length : 0);
  const sourceLabel=p.key_source==='oauth'
    ? t('providers_status_oauth')
    : p.key_source==='config_yaml'
      ? t('providers_status_configured')||'Configured'
      : (p.has_key ? t('providers_status_api_key') : t('providers_status_not_configured_label'));
  const metaParts=[];
  if(modelCount>0) metaParts.push(modelCount+(modelCount===1?' model':' models'));
  metaParts.push(sourceLabel);
  const metaText=metaParts.join(' · ');

  // Clickable header (toggles body)
  const header=document.createElement('button');
  header.type='button';
  header.className='provider-card-header';
  header.innerHTML=`
    <div class="provider-card-info">
      <div class="provider-card-name">${esc(p.display_name)}</div>
      <div class="provider-card-meta">${esc(metaText)}</div>
    </div>
    ${p.has_key?`<span class="provider-card-badge">${esc(t('providers_status_configured'))}</span>`:''}
    <svg class="provider-card-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" width="16" height="16"><path d="M6 9l6 6 6-6"/></svg>
  `;
  card.appendChild(header);

  const body=document.createElement('div');
  body.className='provider-card-body';

  if(isOauth){
    const hint=document.createElement('div');
    hint.className='provider-card-hint';
    if(p.key_source==='config_yaml'){
      hint.textContent=t('providers_oauth_config_yaml_hint')||'Token configured via config.yaml. To update, edit the providers section in your config.yaml or run hermes auth.';
    } else if(p.auth_error){
      hint.textContent=p.auth_error;
      hint.style.color='var(--accent)';
    } else if(p.has_key){
      hint.textContent=t('providers_oauth_hint');
    } else {
      hint.textContent=t('providers_oauth_not_configured_hint')||'Not authenticated. Run hermes auth in the terminal to configure this provider.';
      hint.style.color='var(--muted)';
    }
    body.appendChild(hint);
    card.appendChild(body);
    header.addEventListener('click',()=>card.classList.toggle('open'));
    return card;
  }

  let input=null;
  let focusInput=null;
  let saveBtn=null;
  if(p.is_self_hosted){
    const defaultBaseUrl=_SELF_HOSTED_DEFAULT_BASE_URLS[p.id];
    const baseUrlField=document.createElement('div');
    baseUrlField.className='provider-card-field';
    const baseUrlLabel=document.createElement('label');
    baseUrlLabel.className='provider-card-label';
    baseUrlLabel.textContent='Base URL';
    baseUrlField.appendChild(baseUrlLabel);
    const baseUrlRow=document.createElement('div');
    baseUrlRow.className='provider-card-row';
    const baseUrlInput=document.createElement('input');
    baseUrlInput.type='text';
    baseUrlInput.className='provider-card-input';
    baseUrlInput.placeholder=defaultBaseUrl||'http://localhost:11434/v1';
    baseUrlInput.value=(p.base_url||'').trim()||defaultBaseUrl||'';
    baseUrlInput.autocomplete='off';
    const testBtn=document.createElement('button');
    testBtn.type='button';
    testBtn.className='provider-card-btn provider-card-btn-ghost';
    testBtn.textContent='Test connection';
    const probeStatus=document.createElement('div');
    probeStatus.className='provider-card-hint';
    baseUrlRow.appendChild(baseUrlInput);
    baseUrlRow.appendChild(testBtn);
    baseUrlField.appendChild(baseUrlRow);
    baseUrlField.appendChild(probeStatus);

    const keyField=document.createElement('div');
    keyField.className='provider-card-field';
    const keyLabel=document.createElement('label');
    keyLabel.className='provider-card-label';
    keyLabel.textContent='API key (optional)';
    keyField.appendChild(keyLabel);
    const keyRow=document.createElement('div');
    keyRow.className='provider-card-row';
    const keyInput=document.createElement('input');
    keyInput.type='password';
    keyInput.className='provider-card-input';
    keyInput.autocomplete='off';
    keyInput.placeholder='Optional';
    keyRow.appendChild(keyInput);
    keyField.appendChild(keyRow);

    const modelField=document.createElement('div');
    modelField.className='provider-card-field';
    const modelLabel=document.createElement('label');
    modelLabel.className='provider-card-label';
    modelLabel.textContent=t('providers_status_model')||'Model';
    modelField.appendChild(modelLabel);
    const modelRow=document.createElement('div');
    modelRow.className='provider-card-row';
    const modelInput=document.createElement('input');
    modelInput.type='text';
    modelInput.className='provider-card-input';
    modelInput.autocomplete='off';
    modelInput.placeholder='model id';
    const modelDatalist=document.createElement('datalist');
    const modelListId='providerModelList-'+p.id;
    modelDatalist.id=modelListId;
    modelInput.setAttribute('list',modelListId);
    const setModelChoices=(models)=>{
      modelDatalist.innerHTML='';
      const choices=Array.isArray(models)?models:[];
      for(const model of choices){
        const modelId=model&&model.id?model.id:model;
        const option=document.createElement('option');
        option.value=modelId;
        modelDatalist.appendChild(option);
      }
    };
    const initialModelChoices=Array.isArray(p.models)?p.models:[];
    setModelChoices(initialModelChoices);

    const saveRow=document.createElement('div');
    saveRow.className='provider-card-row';
    saveRow.style.marginTop='6px';
    saveBtn=document.createElement('button');
    saveBtn.type='button';
    saveBtn.className='provider-card-btn provider-card-btn-primary';
    saveBtn.textContent=t('providers_save');
    saveBtn.onclick=()=>_saveSelfHostedProvider(p.id);
    saveBtn.disabled=true;
    saveRow.appendChild(saveBtn);
    if(p.has_key){
      const removeBtn=document.createElement('button');
      removeBtn.type='button';
      removeBtn.className='provider-card-btn provider-card-btn-danger';
      removeBtn.textContent=t('providers_remove');
      removeBtn.onclick=()=>_removeProviderKey(p.id);
      saveRow.appendChild(removeBtn);
    }
    modelRow.appendChild(modelInput);
    modelField.appendChild(modelRow);
    body.appendChild(baseUrlField);
    body.appendChild(keyField);
    body.appendChild(modelField);
    body.appendChild(saveRow);
    body.appendChild(modelDatalist);
    card.appendChild(body);

    const checkSaveEnabled=()=>{
      const hasUrl=baseUrlInput.value.trim().length>0;
      const hasModel=modelInput.value.trim().length>0;
      saveBtn.disabled=!(hasUrl&&hasModel);
    };
    baseUrlInput.addEventListener('input',checkSaveEnabled);
    modelInput.addEventListener('input',checkSaveEnabled);
    checkSaveEnabled();

    _providerCardEls.set(p.id,{
      card,
      baseUrlInput,
      apiKeyInput:keyInput,
      modelInput,
      modelDatalist,
      saveBtn,
      testBtn,
      probeStatus,
      isSelfHosted:true,
      setModelChoices,
      updateSaveState:checkSaveEnabled,
    });
    focusInput=modelInput;
    testBtn.onclick=()=>_testSelfHostedConnection(p.id);
    header.addEventListener('click',e=>{
      if(e.target.closest('.provider-card-body')) return;
      card.classList.toggle('open');
      if(card.classList.contains('open')) setTimeout(()=>focusInput&&focusInput.focus(),0);
    });
    return card;
  }

  if(p.configurable){
    const field=document.createElement('div');
    field.className='provider-card-field';
    const label=document.createElement('label');
    label.className='provider-card-label';
    label.textContent=t('providers_status_api_key');
    field.appendChild(label);

    const row=document.createElement('div');
    row.className='provider-card-row';
    input=document.createElement('input');
    input.type='password';
    input.className='provider-card-input';
    input.placeholder=p.has_key?t('providers_key_placeholder_replace'):t('providers_key_placeholder_new');
    input.autocomplete='off';
    const toggleBtn=document.createElement('button');
    toggleBtn.type='button';
    toggleBtn.className='provider-card-btn provider-card-btn-ghost';
    toggleBtn.textContent='Show';
    toggleBtn.onclick=()=>{
      const revealed=input.type==='text';
      input.type=revealed?'password':'text';
      toggleBtn.textContent=revealed?'Show':'Hide';
    };
    saveBtn=document.createElement('button');
    saveBtn.type='button';
    saveBtn.className='provider-card-btn provider-card-btn-primary';
    saveBtn.textContent=t('providers_save');
    saveBtn.onclick=()=>_saveProviderKey(p.id);
    saveBtn.disabled=true;
    row.appendChild(input);
    row.appendChild(toggleBtn);
    row.appendChild(saveBtn);
    if(p.has_key){
      const removeBtn=document.createElement('button');
      removeBtn.type='button';
      removeBtn.className='provider-card-btn provider-card-btn-danger';
      removeBtn.textContent=t('providers_remove');
      removeBtn.onclick=()=>_removeProviderKey(p.id);
      row.appendChild(removeBtn);
    }
    field.appendChild(row);
    body.appendChild(field);
    focusInput=input;

  }else{
    const hint=document.createElement('div');
    hint.className='provider-card-hint';
    hint.textContent=p.is_custom
      ? 'Custom provider loaded from config.yaml / hermes model. Edit it from the CLI or config file.'
      : 'Provider is managed outside the WebUI.';
    body.appendChild(hint);
  }

  // Model list — show when provider has known models
  if(modelCount>0){
    const modelSection=document.createElement('div');
    modelSection.className='provider-card-models';
    const modelLabel=document.createElement('div');
    modelLabel.className='provider-card-label';
    modelLabel.textContent='Models';
    modelSection.appendChild(modelLabel);
    const modelList=document.createElement('div');
    modelList.className='provider-card-model-tags';
    const renderedModels=Array.isArray(p.models)?p.models:[];
    for(const m of renderedModels){
      const tag=document.createElement('span');
      tag.className='provider-card-model-tag';
      tag.textContent=m.id||m.label||m;
      modelList.appendChild(tag);
    }
    // When the rendered list is a strict subset of the total catalog (Nous
    // Portal large-tier accounts hit this with ~400-model catalogs), show
    // a "+N more" trailing pill so the user knows the picker is intentionally
    // capped — and they can still reach the full catalog via the /model
    // slash command (its autocomplete consumes the un-trimmed list from
    // /api/models's extra_models field). #1567.
    const totalCount=Number.isFinite(p.models_total)?p.models_total:renderedModels.length;
    const hiddenCount=Math.max(0, totalCount - renderedModels.length);
    if(hiddenCount>0){
      const more=document.createElement('span');
      more.className='provider-card-model-tag provider-card-model-tag-more';
      more.textContent='+'+hiddenCount+' more';
      more.title='The /model slash command can autocomplete every model in this provider\'s catalog.';
      modelList.appendChild(more);
    }
    modelSection.appendChild(modelList);
    body.appendChild(modelSection);
  }

  // Refresh models for this provider
  const refreshRow=document.createElement('div');
  refreshRow.className='provider-card-row';
  refreshRow.style.marginTop='6px';
  const refreshBtn=document.createElement('button');
  refreshBtn.type='button';
  refreshBtn.className='provider-card-btn provider-card-btn-ghost';
  refreshBtn.style.display='flex';
  refreshBtn.style.alignItems='center';
  refreshBtn.style.gap='5px';
  refreshBtn.innerHTML=`<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M3 21v-5h5"/></svg> ${t('providers_refresh_models')||'Refresh Models'}`;
  refreshBtn.onclick=()=>_refreshProviderModels(p.id, refreshBtn);
  refreshRow.appendChild(refreshBtn);
  body.appendChild(refreshRow);
  card.appendChild(body);

  if(input&&saveBtn){
    _providerCardEls.set(p.id,{card,input,saveBtn,hasKey:p.has_key});
    input.addEventListener('input',()=>{saveBtn.disabled=!input.value.trim();});
  }
  header.addEventListener('click',e=>{
    // Don't toggle when clicking inside body (defensive; body isn't inside header)
    if(e.target.closest('.provider-card-body')) return;
    card.classList.toggle('open');
    if(card.classList.contains('open')) setTimeout(()=>focusInput&&focusInput.focus(),0);
  });
  return card;
}

async function _saveProviderKey(providerId){
  const els=_providerCardEls.get(providerId);
  if(!els) return;
  const key=els.input.value.trim();
  if(!key){
    showToast(t('providers_enter_key'));
    return;
  }
  els.saveBtn.disabled=true;
  els.saveBtn.textContent=t('providers_saving');
  try{
    const res=await api('/api/providers',{method:'POST',body:JSON.stringify({provider:providerId,api_key:key})});
    if(res.ok){
      showToast(res.provider+' key '+res.action);
      els.input.value='';
      // Invalidate every dropdown surface that caches /api/models so the
      // newly-configured provider's models show up without a server restart
      // or page reload (#1539). Server-side invalidate_models_cache() is
      // already called by api/providers.py:set_provider_key.
      _refreshModelDropdownsAfterProviderChange();
      await loadProvidersPanel(); // refresh list
    }else{
      showToast(res.error||'Failed to save key');
      els.saveBtn.disabled=false;
      els.saveBtn.textContent=t('providers_save');
    }
  }catch(e){
    showToast('Error: '+e.message);
    els.saveBtn.disabled=false;
    els.saveBtn.textContent=t('providers_save');
  }
}

async function _removeProviderKey(providerId){
  const els=_providerCardEls.get(providerId);
  if(!els) return;
  if(els.saveBtn){els.saveBtn.disabled=true;els.saveBtn.textContent=t('providers_removing');}
  try{
    const res=await api('/api/providers/delete',{method:'POST',body:JSON.stringify({provider:providerId})});
    if(res.ok){
      showToast(res.provider+' key '+t('providers_key_removed').toLowerCase());
      // Drop the removed provider from every cached dropdown surface so it
      // disappears immediately — composer picker, /model slash command,
      // Settings → Default Model, configured-model badges (#1539).
      // Without this, a stale list from before the delete keeps offering
      // the now-removed provider's models until the page is reloaded.
      _refreshModelDropdownsAfterProviderChange();
      await loadProvidersPanel(); // refresh list
    }else{
      showToast(res.error||'Failed to remove key');
      if(els.saveBtn){els.saveBtn.disabled=false;els.saveBtn.textContent=t('providers_save');}
    }
  }catch(e){
    // A 403 from /api/providers/delete fires when the CSRF cookie/header
    // pair has drifted. The server distinguishes three reasons in
    // api/routes.py:_csrf_rejection_error ("Session expired - reload the
    // page", "Cross-origin mismatch - check reverse proxy headers", and
    // the fallback "Cross-origin request rejected"); api()'s catch lifts
    // that string onto e.message. Pass it through verbatim so the
    // deployment-shape failure #2572 calls out keeps its actionable hint
    // instead of being flattened to a single generic toast.
    if(e&&e.status===403){
      showToast(e.message||'Session expired. Reload the page and try again.',6000,'error');
    }else{
      showToast('Error: '+e.message);
    }
    if(els.saveBtn){els.saveBtn.disabled=false;els.saveBtn.textContent=t('providers_save');}
  }
}

async function _testSelfHostedConnection(providerId){
  const els=_providerCardEls.get(providerId);
  if(!els||!els.isSelfHosted) return;
  const baseUrl=(els.baseUrlInput.value||'').trim();
  const apiKey=(els.apiKeyInput.value||'').trim();
  if(!baseUrl){
    showToast('Base URL is required');
    return;
  }

  const testBtn=els.testBtn;
  if(!testBtn) return;
  const prevLabel=testBtn.textContent;
  testBtn.disabled=true;
  testBtn.textContent='Testing...';
  if(els.probeStatus){
    els.probeStatus.style.color='var(--muted)';
    els.probeStatus.textContent='Testing connection...';
  }

  try{
    const res=await api('/api/onboarding/probe',{
      method:'POST',
      body:JSON.stringify({provider:providerId,base_url:baseUrl,api_key:apiKey||undefined}),
    });
    if(res&&res.ok){
      const models=Array.isArray(res.models)?res.models:[];
      if(els.setModelChoices){
        els.setModelChoices(models);
      }
      if(els.probeStatus){
        const count=models.length;
        els.probeStatus.style.color='var(--ok)';
        els.probeStatus.textContent=`Connected. ${count} model(s) available.`;
      }
      if(!els.modelInput.value&&models.length&&models[0]){
        els.modelInput.value=models[0].id||models[0];
      }
      if(els.updateSaveState){
        els.updateSaveState();
      }
    }else{
      const err=(res&&res.error)||'unreachable';
      const detail=(res&&res.detail)?` (${res.detail})`:'';
      if(els.probeStatus){
        els.probeStatus.style.color='var(--accent)';
        els.probeStatus.textContent=`${err}${detail}`;
      }
      showToast(`Connection test failed: ${err}`);
    }
  }catch(e){
    if(els.probeStatus){
      els.probeStatus.style.color='var(--accent)';
      els.probeStatus.textContent=e&&e.message?e.message:'Connection test failed';
    }
    showToast('Connection test failed: '+(e&&e.message||'request error'));
  }finally{
    testBtn.disabled=false;
    testBtn.textContent=prevLabel;
  }
}

async function _saveSelfHostedProvider(providerId){
  const els=_providerCardEls.get(providerId);
  if(!els||!els.isSelfHosted) return;
  const baseUrl=(els.baseUrlInput.value||'').trim();
  const key=(els.apiKeyInput.value||'').trim();
  const model=(els.modelInput.value||'').trim();
  if(!baseUrl){
    showToast('Base URL is required');
    return;
  }
  if(!model){
    showToast('Model is required');
    return;
  }
  if(!els.saveBtn) return;
  const saveBtn=els.saveBtn;
  const prevLabel=saveBtn.textContent;
  saveBtn.disabled=true;
  saveBtn.textContent='Saving...';
  try{
    const payload={provider:providerId,base_url:baseUrl,model:model};
    if(key) payload.api_key=key;
    const res=await api('/api/providers/self-hosted',{method:'POST',body:JSON.stringify(payload)});
    if(res&&res.ok){
      showToast(`${res.provider} configured`);
      if(els.apiKeyInput) els.apiKeyInput.value='';
      _refreshModelDropdownsAfterProviderChange();
      await loadProvidersPanel();
    }else{
      showToast(res&&res.error||'Failed to save provider');
      saveBtn.disabled=false;
      saveBtn.textContent=prevLabel;
    }
  }catch(e){
    showToast('Error: '+(e&&e.message||'Failed to save provider'));
    saveBtn.disabled=false;
    saveBtn.textContent=prevLabel;
  }
}

// Shared dropdown-cache flush invoked after a provider add/remove. The
// server-side TTL cache is already invalidated by /api/providers and
// /api/providers/delete (via api/providers.py:set_provider_key); this
// flushes the JS-side caches so the next render rebuilds from a fresh
// /api/models response. Wrapped in a try/catch so a UI module that hasn't
// loaded yet (e.g. during early Settings open) cannot break the save flow.
function _refreshModelDropdownsAfterProviderChange(){
  try{
    if(typeof window._invalidateSlashModelCache==='function'){
      window._invalidateSlashModelCache();
    }
    // Fire-and-forget: don't block the providers panel refresh on a
    // dropdown rebuild. The composer/Settings dropdowns will catch up
    // on the very next paint frame.
    if(typeof window._ensureModelDropdownReady==='function'){
      window._modelDropdownReady=null;
      Promise.resolve(window._ensureModelDropdownReady()).catch(()=>{});
    }else if(typeof populateModelDropdown==='function'){
      Promise.resolve(populateModelDropdown()).catch(()=>{});
    }
  }catch(_e){
    // Swallow — dropdown refresh is best-effort, providers panel must still update.
  }
}

async function _refreshProviderModels(providerId, btn){
  btn.disabled=true;
  const orig=btn.innerHTML;
  btn.innerHTML=`<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M3 21v-5h5"/></svg> ${t('providers_refreshing')||'Refreshing...'}`;
  try{
    const res=await api('/api/models/refresh',{method:'POST',body:JSON.stringify({provider:providerId})});
    if(res.ok){
      showToast(t('providers_models_refreshed')||('Models refreshed for '+res.provider));
      _refreshModelDropdownsAfterProviderChange();
    }else{
      showToast(res.error||'Failed to refresh models');
    }
  }catch(e){
    showToast(e.status===404?'Refresh not available for this provider.':(e.message||'Failed to refresh models'));
  }finally{
    btn.disabled=false;
    btn.innerHTML=orig;
  }
}

let _settingsPasswordEnvLocked=false;
let _settingsPasswordAuthEnabled=false;
function _setSettingsAuthButtonsVisible(active){
  const signOutBtn=$('btnSignOut');
  if(signOutBtn) signOutBtn.style.display=active?'':'none';
  const disableBtn=$('btnDisableAuth');
  if(disableBtn) disableBtn.style.display=active?'':'none';
  const passkeyBtn=$('btnRegisterPasskey');
  if(passkeyBtn) passkeyBtn.disabled=!active||!window.PublicKeyCredential||!navigator.credentials;
}
function _syncPasswordlessButton(authStatus){
  const btn=$('btnGoPasswordless');
  if(!btn) return;
  const can=!!(authStatus&&authStatus.auth_enabled&&authStatus.password_auth_enabled&&authStatus.passkeys_count>0&&!_settingsPasswordEnvLocked);
  btn.style.display=can?'':'none';
  btn.disabled=!can;
}

function _renderSettingsAuthStatus(authStatus){
  const el=$('settingsAuthStatus');
  if(!el) return;
  if(!authStatus) { el.style.display='none'; return; }
  el.style.display='block';
  let label='',cls='detail-badge ok';
  if(authStatus.auth_enabled && authStatus.password_auth_enabled){
    label=t('auth_status_password'); cls='detail-badge ok';
  }else if(authStatus.auth_enabled && !authStatus.password_auth_enabled){
    label=t('auth_status_passkey_only'); cls='detail-badge warn';
  }else{
    label=t('auth_status_unauthenticated'); cls='detail-badge err';
  }
  el.innerHTML='<span class="'+cls+'" style="font-size:11px">'+label+'</span>';
}

function _updateCurrentPasswordVisibility(){
  const block=$('settingsCurrentPasswordBlock');
  if(!block) return;
  block.style.display=_settingsPasswordAuthEnabled?'block':'none';
}

function _updateAuthWarningBadge(authStatus){
  const badges=['authWarningBadgeDesktop','authWarningBadgeMobile'];
  const authDisabled=!authStatus||!authStatus.auth_enabled;
  const acknowledged=!!(authStatus&&authStatus.auth_disabled_acknowledged);
  badges.forEach(function(id){
    const el=$(id);
    if(!el) return;
    if(!authDisabled){ el.style.display='none'; return; }
    el.style.display='block';
    el.style.background=acknowledged?'#e8a030':'#e05';
  });
}

function _updateAuthDisabledWarning(authStatus){
  const el=$('settingsAuthDisabledWarning');
  if(!el) return;
  const authDisabled=!authStatus||!authStatus.auth_enabled;
  if(!authDisabled){ el.style.display='none'; return; }
  el.style.display='block';
  const cb=$('settingsAuthDisabledAck');
  if(cb) cb.checked=!!(authStatus&&authStatus.auth_disabled_acknowledged);
}

async function _setAuthDisabledAck(checked){
  try{
    await api('/api/settings',{method:'POST',body:JSON.stringify({_auth_disabled_acknowledged:!!checked})});
    try{
      const authStatus=await api('/api/auth/status');
      _updateAuthWarningBadge(authStatus);
    }catch(e){}
  }catch(e){
    showToast(t('auth_ack_save_failed')+e.message);
  }
}

function _b64uToBytes(s){
  s=String(s||'').replace(/-/g,'+').replace(/_/g,'/');
  while(s.length%4) s+='=';
  const bin=atob(s), out=new Uint8Array(bin.length);
  for(let i=0;i<bin.length;i++) out[i]=bin.charCodeAt(i);
  return out;
}
function _bytesToB64u(buf){
  const bytes=new Uint8Array(buf);let bin='';
  for(let i=0;i<bytes.length;i++) bin+=String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/g,'');
}

async function loadPasskeys(){
  const list=$('passkeyList');
  const block=$('passkeysSettingsBlock');
  if(!list) return;
  // Stage-batch14: respect the HERMES_WEBUI_PASSKEY feature flag — hide the
  // whole block when passkey support is disabled at the server level so users
  // don't see a non-functional "Add passkey" button (clicking it would 404).
  try{
    const status=await api('/api/auth/status');
    if(status && status.passkey_feature_flag === false){
      if(block) block.style.display='none';
      return;
    }
    if(block) block.style.display='';
  }catch(_e){
    // If /api/auth/status fails, keep the block hidden to avoid showing a
    // broken affordance.
    if(block) block.style.display='none';
    return;
  }
  if(!window.PublicKeyCredential||!navigator.credentials){
    list.textContent='Passkeys are not supported by this browser/context.';
    const btn=$('btnRegisterPasskey'); if(btn) btn.disabled=true;
    return;
  }
  try{
    const data=await api('/api/auth/passkeys',{method:'POST',body:'{}'});
    if(data && data.disabled){
      if(block) block.style.display='none';
      return;
    }
    const creds=(data&&data.credentials)||[];
    if(!creds.length){list.textContent='No passkeys registered.';return;}
    list.innerHTML=creds.map(c=>`<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;border:1px solid var(--border);border-radius:8px;padding:8px;margin-top:6px"><span>${esc(c.label||'Passkey')}</span><button class="btn-tiny" onclick="deletePasskey('${esc(c.id)}')">Remove</button></div>`).join('');
  }catch(e){list.textContent='Failed to load passkeys: '+e.message;}
}

async function registerPasskey(){
  if(!window.PublicKeyCredential||!navigator.credentials){showToast('Passkeys require a supported browser and secure context.');return;}
  const label='This device';
  try{
    const optData=await api('/api/auth/passkey/register/options',{method:'POST',body:'{}'});
    const pk=optData.publicKey;
    pk.challenge=_b64uToBytes(pk.challenge);
    pk.user=Object.assign({},pk.user,{id:_b64uToBytes(pk.user.id)});
    if(Array.isArray(pk.excludeCredentials)) pk.excludeCredentials=pk.excludeCredentials.map(c=>Object.assign({},c,{id:_b64uToBytes(c.id)}));
    const cred=await navigator.credentials.create({publicKey:pk});
    if(!cred) throw new Error('Passkey registration cancelled');
    await api('/api/auth/passkey/register',{method:'POST',body:JSON.stringify({
      id:cred.id,rawId:_bytesToB64u(cred.rawId),type:cred.type,label,
      response:{clientDataJSON:_bytesToB64u(cred.response.clientDataJSON),attestationObject:_bytesToB64u(cred.response.attestationObject)}
    })});
    showToast('Passkey registered');
    loadPasskeys();
    try{_syncPasswordlessButton(await api('/api/auth/status'));}catch(_e){}
  }catch(e){showToast('Passkey registration failed: '+e.message);}
}

async function deletePasskey(id){
  const ok=await showConfirmDialog({title:'Remove passkey?',message:'This browser/device will no longer be able to sign in with that passkey.',confirmLabel:'Remove',danger:true,focusCancel:true});
  if(!ok) return;
  try{await api('/api/auth/passkey/delete',{method:'POST',body:JSON.stringify({id})});showToast('Passkey removed');loadPasskeys();try{_syncPasswordlessButton(await api('/api/auth/status'));}catch(_e){}}
  catch(e){showToast('Failed to remove passkey: '+e.message);}
}

function _applySavedSettingsUi(saved, body, opts){
  const {sendKey,showTokenUsage,showQuotaChip,showConversationOutline,showBusyPlaceholderHint,showTps,fadeTextEffect,showCliSessions,theme,skin,language,sidebarDensity,fontSize}=opts;
  window._sendKey=sendKey||'enter';
  window._showTokenUsage=showTokenUsage;
  window._showQuotaChip=showQuotaChip===true;
  window._showConversationOutline=showConversationOutline===true;
  document.documentElement.dataset.conversationOutline=window._showConversationOutline?'enabled':'disabled';
  if(typeof applyConversationOutlinePreference==='function') applyConversationOutlinePreference();
  window._showBusyPlaceholderHint=showBusyPlaceholderHint===true;
  window._showTps=showTps;
  window._fadeTextEffect=!!fadeTextEffect;
  window._showCliSessions=showCliSessions;
  window._showPreviousMessagingSessions=!!body.show_previous_messaging_sessions;
  window._soundEnabled=body.sound_enabled;
  window._notificationsEnabled=body.notifications_enabled;
  window._whatsNewSummaryEnabled=!!body.whats_new_summary_enabled;
  window._showThinking=body.show_thinking!==false;
  window._simplifiedToolCalling=true;
  _syncChatActivityDisplayModeControl(body.chat_activity_display_mode);
  _syncTransparentEventTimestampsControl(body.transparent_stream_event_timestamps, body.chat_activity_display_mode);
  window._terminalAutoExpandOnOutput=!!body.terminal_auto_expand_on_output;
  window._workspaceTodosTab=!!body.workspace_todos_tab;
  if(typeof _applyWorkspaceTodosTabVisibility==='function') _applyWorkspaceTodosTabVisibility();
  window._sessionJumpButtonsEnabled=!!body.session_jump_buttons;
  if(typeof _applySessionNavigationPrefs==='function') _applySessionNavigationPrefs();
  window._sidebarDensity=sidebarDensity==='detailed'?'detailed':'compact';
  // #5170 mirror write in _applySavedSettingsUi, under the #5145 rename:
  // persist so a reload/offline first-send honors the resolved mode.
  window._defaultMessageMode=(typeof _persistDefaultMessageMode==='function')
    ? _persistDefaultMessageMode(body.default_message_mode||body.busy_input_mode)
    : (body.default_message_mode||body.busy_input_mode||'steer');
  window._sessionEndlessScrollEnabled=!!body.session_endless_scroll;
  window._autoScrollFollow=body.auto_scroll_follow!==false;
  window._largeTextPasteAsAttachment=body.large_text_paste_as_attachment!==false;
  window._projectQuickCreate=!!body.project_quick_create_buttons;
  if(Object.prototype.hasOwnProperty.call(body,'structured_code_default_view')){
    _applyStructuredCodeViewSettings(body.structured_code_default_view,body.structured_code_auto_tree_lines,false);
  }
  window._botName=body.bot_name||'Hermes';
  if(typeof applyBotName==='function') applyBotName();
  else if(typeof _applyBusyComposerPlaceholder==='function') _applyBusyComposerPlaceholder();
  if(typeof setLocale==='function') setLocale(language);
  if(typeof applyLocaleToDOM==='function') applyLocaleToDOM();
  _ensureComposerControlVisibilityState(saved||body||{});
  const composerOrderSource=(saved&&Array.isArray(saved.composer_control_order))
    ? saved.composer_control_order
    : (Array.isArray(body.composer_control_order)?body.composer_control_order:null);
  if(composerOrderSource){
    const composerOrder=_setComposerControlOrder(composerOrderSource);
    if(typeof window._applyComposerControlOrder==='function') window._applyComposerControlOrder(composerOrder);
  }
  _renderComposerControlChips();
  _renderComposerSituationalControlChips();
  if(typeof _applyComposerFooterVisibilitySettings==='function') _applyComposerFooterVisibilitySettings();
  const maxTokensField=$('settingsMaxTokens');
  if(maxTokensField){
    const savedRawMaxTokens=saved&&saved.max_tokens;
    const parsedSavedMaxTokens=parseInt(savedRawMaxTokens,10);
    maxTokensField.value=(Number.isFinite(parsedSavedMaxTokens)&&parsedSavedMaxTokens>0)
      ? String(parsedSavedMaxTokens)
      : '';
    _syncSettingsMaxTokensPlaceholder(maxTokensField,saved&&saved.max_tokens_fallback);
    maxTokensField.dataset.initialValue=maxTokensField.value;
  }
  if(typeof startGatewaySSE==='function'){
    if(showCliSessions) startGatewaySSE();
    else if(typeof stopGatewaySSE==='function') stopGatewaySSE();
  }
  _setSettingsAuthButtonsVisible(!!saved.auth_enabled);
  _settingsDirty=false;
  _settingsThemeOnOpen=theme;
  _settingsSkinOnOpen=skin||'default';
  _settingsFontSizeOnOpen=fontSize||localStorage.getItem('hermes-font-size')||'default';
  const bar=$('settingsUnsavedBar');
  if(bar) bar.style.display='none';
  _settingsHermesDefaultModelOnOpen=body.default_model||_settingsHermesDefaultModelOnOpen||'';
  if(Object.prototype.hasOwnProperty.call(body,'default_model_provider')) _settingsHermesDefaultModelProviderOnOpen=body.default_model_provider||null;
  // Sync window._defaultModel so newSession() uses the just-saved default without a reload (#908).
  if(body.default_model) window._defaultModel=body.default_model;
  if(Object.prototype.hasOwnProperty.call(body,'default_model_provider')) window._activeProvider=body.default_model_provider||null;
  if(typeof clearMessageRenderCache==='function') clearMessageRenderCache();
  renderMessages();
  if(typeof syncTopbar==='function') syncTopbar();
  if(typeof renderSessionList==='function') renderSessionList();
}

// Instant client-side badge feedback when the update channel is toggled, before
// the server round-trip that authoritatively re-renders the badge from
// update_channel_version. Keeps the "· Experimental" suffix in sync immediately.
function _syncUpdateChannelBadge(channel){
  try{
    const badge=$('settings-webui-version-badge');
    if(!badge) return;
    let base=badge.textContent||'';
    // Strip any existing " · Experimental" suffix, then re-append if needed.
    base=base.replace(/\s·\sExperimental\s*$/,'');
    badge.textContent = channel==='experimental' ? (base+' · Experimental') : base;
  }catch(e){}
}

async function checkUpdatesNow(channelOverride){
  const btn=$('btnCheckUpdatesNow');
  const label=$('checkUpdatesLabel');
  const spinner=$('checkUpdatesSpinner');
  const status=$('checkUpdatesStatus');
  if(!btn||!label) return;
  // Disable button, show spinner
  btn.disabled=true;
  if(spinner) spinner.style.display='';
  if(label) label.textContent=t('settings_checking');
  if(status) status.textContent='';

  try {
    // Pass the channel explicitly when the caller has one (e.g. the dropdown
    // just switched) so the check cannot race the debounced settings autosave
    // and answer for the previous channel. Omit otherwise → server uses the
    // saved setting. (Fable UX gate.)
    const _checkBody={force:true};
    if(channelOverride==='stable'||channelOverride==='experimental') _checkBody.channel=channelOverride;
    const data=await api('/api/updates/check',{method:'POST',body:JSON.stringify(_checkBody),timeoutMs:60000});
    if(data.disabled){
      if(status){status.textContent=t('settings_updates_disabled');status.style.color='var(--muted)';}
    } else {
      const errorParts=[];
      const formatUpdateError=(typeof _formatUpdateCheckError==='function')
        ? _formatUpdateCheckError
        : ((label,info)=>info&&info.error?label:null);
      const webuiError=formatUpdateError('WebUI',data.webui);
      const agentError=formatUpdateError('Agent',data.agent);
      if(webuiError) errorParts.push(webuiError);
      if(agentError) errorParts.push(agentError);
      const parts=[];
      const formatUpdatePart=(typeof _formatUpdateTargetStatus==='function')
        ? _formatUpdateTargetStatus
        : ((label,info)=>info&&info.behind>0?label+': '+info.behind:null);
      const webuiPart=formatUpdatePart('WebUI',data.webui);
      const agentPart=formatUpdatePart('Agent',data.agent);
      if(webuiPart) parts.push(webuiPart);
      if(agentPart) parts.push(agentPart);
      const manualInstruction=(typeof _formatManualUpdateInstruction==='function')
        ? _formatManualUpdateInstruction(data.webui)
        : null;
      // Track non-git targets separately so a mixed deployment (one git
      // checkout + one no-git install) never hides the "can't check" state
      // behind an up-to-date summary (#4356).
      const noGitParts=[];
      if(data.webui&&data.webui.no_git&&!data.webui.manual_update) noGitParts.push('WebUI');
      if(data.agent&&data.agent.no_git&&!data.agent.ignored) noGitParts.push('Agent');
      if(parts.length){
        let txt=t('settings_updates_available').replace('{count}',parts.join(', '));
        if(manualInstruction) txt+=' · '+manualInstruction;
        if(noGitParts.length) txt+=' · '+t('settings_update_no_git');
        if(status){status.textContent=txt;status.style.color='var(--accent)';}
        // Also trigger the update banner
        if(typeof _showUpdateBanner==='function') _showUpdateBanner(data);
      } else if(errorParts.length){
        if(status){status.textContent=t('settings_update_check_failed')+': '+errorParts.join(', ');status.style.color='var(--error)';}
      } else if(noGitParts.length){
        if(status){status.textContent=t('settings_update_no_git');status.style.color='var(--muted)';}
      } else {
        if(status){status.textContent=t('settings_up_to_date');status.style.color='var(--success)';}
        if(typeof _showUpdateBanner==='function') _showUpdateBanner(data);
      }
    }
  } catch(e){
    // Never expose raw e.message in UI — log to console for debugging only
    console.warn('[checkUpdatesNow]', e);
    // Show a generic user-facing error; if the API returned a message body use it
    let userMsg=t('settings_update_check_failed');
    if(e&&e.response){
      try{
        const body=JSON.parse(e.response);
        if(body.error) userMsg=String(body.error).substring(0,120);
      }catch(_){}
    }
    if(status){status.textContent=userMsg;status.style.color='var(--error)';}
  } finally {
    btn.disabled=false;
    if(spinner) spinner.style.display='none';
    if(label) label.textContent=t('settings_check_now');
  }
}

// ── Auxiliary Models ──────────────────────────────────────────────────────────

let _auxProviders=[];       // cached provider list from /api/models
let _auxTasks=[];           // sanitized auxiliary task configs from /api/model/auxiliary
let _auxOriginalConfig=null; // snapshot of initial config for dirty detection
let _mainAdvancedConfig=null; // current advanced config for the default chat model

function _auxSelectStyle(){
 return 'width:100%;padding:6px 8px;background:var(--code-bg);color:var(--text);border:1px solid var(--border2);border-radius:6px;font-size:12px;box-sizing:border-box';
}

function _auxTaskLabelFromMeta(taskKey, taskCfg){
  const nameKey='settings_aux_task_'+taskKey;
  const descKey=nameKey+'_desc';
  const tName=t(nameKey);
  const tDesc=t(descKey);
  const name=(tName&&tName!==nameKey)?String(tName).trim():'';
  const description=(tDesc&&tDesc!==descKey)?String(tDesc).trim():'';
  const fallbackName=(taskCfg&&typeof taskCfg.label==='string'&&taskCfg.label.trim())?String(taskCfg.label).trim():taskKey;
  const fallbackDesc=(taskCfg&&typeof taskCfg.description==='string'&&taskCfg.description.trim())?String(taskCfg.description).trim():'';
  return {
    task: taskKey,
    label: name||fallbackName,
    description: description||fallbackDesc,
  };
}

function _normalizeAuxiliaryTasks(rawTasks){
  const tasks=Array.isArray(rawTasks)?rawTasks:[];
  const out=[];
  const seen=new Set();
  for(const rawTask of tasks){
    if(!rawTask||typeof rawTask!=='object') continue;
    const task=(typeof rawTask.task==='string'?String(rawTask.task).trim():'');
    if(!task||seen.has(task)) continue;
    seen.add(task);
    const meta=_auxTaskLabelFromMeta(task,rawTask);
    const entry={
      task,
      provider:String(rawTask.provider||'auto').trim()||'auto',
      model:String(rawTask.model||'').trim(),
      base_url:String(rawTask.base_url||'').trim(),
      timeout:rawTask.timeout,
      download_timeout:rawTask.download_timeout,
      max_concurrency:rawTask.max_concurrency,
      extra_body:rawTask.extra_body&&typeof rawTask.extra_body==='object'?rawTask.extra_body:{},
      api_key_set:!!rawTask.api_key_set,
      label:meta.label,
      description:meta.description,
    };
    out.push(entry);
  }
  return out;
}

function _buildAuxProviderOptions(sel,providers,currentProvider){
 sel.innerHTML='';
 // "auto" = use main model
 const autoOpt=document.createElement('option');
 autoOpt.value='auto';autoOpt.textContent='auto ('+t('settings_aux_provider_auto')+')';
 if(currentProvider==='auto'||!currentProvider) autoOpt.selected=true;
 sel.appendChild(autoOpt);
 for(const p of providers){
  const opt=document.createElement('option');
  opt.value=p.slug;opt.textContent=p.name;
  if(p.slug===currentProvider) opt.selected=true;
  sel.appendChild(opt);
 }
}

function _buildAuxModelOptions(sel,provider,providers,currentModel){
 sel.innerHTML='';
 const emptyOpt=document.createElement('option');
 emptyOpt.value='';emptyOpt.textContent=t('settings_aux_model_auto')||'auto (use provider default)';
 sel.appendChild(emptyOpt);
 if(!provider||provider==='auto'){
  sel.value=currentModel||'';
  return;
 }
 // Find matching provider in cached list
 const pData=providers.find(p=>p.slug===provider);
 if(pData&&pData.models){
  for(const mId of pData.models){
   const opt=document.createElement('option');
   opt.value=mId;opt.textContent=mId;
   if(mId===currentModel) opt.selected=true;
   sel.appendChild(opt);
  }
 }
 // Always allow custom model — add a text input option hint
 const customOpt=document.createElement('option');
 customOpt.value='__custom__';customOpt.textContent=t('settings_aux_model_custom')||'Custom model…';
 sel.appendChild(customOpt);
 // If currentModel not in list and not empty, add it as a custom option
 if(currentModel&&!pData?.models?.includes(currentModel)){
  const existingOpt=document.createElement('option');
  existingOpt.value=currentModel;existingOpt.textContent=currentModel+' (configured)';
  existingOpt.selected=true;
  sel.insertBefore(existingOpt,customOpt);
 }
}

function _onAuxProviderChange(taskKey,providers){
 const provSel=$('aux-prov-'+taskKey);
 const modelSel=$('aux-model-'+taskKey);
 if(!provSel||!modelSel) return;
 const provider=provSel.value;
 _buildAuxModelOptions(modelSel,provider,providers,'');
 _markAuxDirty();
}

async function _onAuxModelChange(taskKey){
 const modelSel=$('aux-model-'+taskKey);
 if(!modelSel) return;
 if(modelSel.value==='__custom__'){
  const customModel=await showPromptDialog({title:t('settings_aux_model_custom')||'Custom model',message:t('settings_aux_model_custom_prompt')||'Enter model ID:',placeholder:'model/provider:model-id',confirmLabel:t('settings_btn_apply_aux_models')||'Apply'});
  if(customModel&&customModel.trim()){
   // Insert custom model option before the __custom__ option
   const opt=document.createElement('option');
   opt.value=customModel.trim();opt.textContent=customModel.trim();
   // Remove __custom__ selection
   const customIdx=[...modelSel.options].findIndex(o=>o.value==='__custom__');
   if(customIdx>=0) modelSel.insertBefore(opt,modelSel.options[customIdx]);
   modelSel.value=customModel.trim();
  }else{
   modelSel.value='';
  }
 }
 _markAuxDirty();
}

function _markAuxDirty(){
 const applyBtn=$('btnApplyAuxModels');
 if(applyBtn) applyBtn.style.display='';
 _markSettingsDirty();
}

function _auxAdvancedValue(cfg,key){
 const v=cfg&&Object.prototype.hasOwnProperty.call(cfg,key)?cfg[key]:'';
 return v===null||v===undefined?'':String(v);
}

function _ensureAuxAdvancedModal(){
 let overlay=$('auxAdvancedOverlay');
 if(overlay) return overlay;
 overlay=document.createElement('div');
 overlay.id='auxAdvancedOverlay';
 overlay.style.cssText='position:fixed;inset:0;z-index:9999;background:rgba(5,7,15,.68);backdrop-filter:blur(4px);display:none;align-items:center;justify-content:center;padding:20px';
 const neutralBtn='font-size:12px;padding:7px 12px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--text);cursor:pointer;font-weight:600';
 const primaryBtn='font-size:12px;padding:7px 12px;border-radius:8px;border:1px solid var(--accent);background:var(--accent);color:#1a1a1a;cursor:pointer;font-weight:700';
 overlay.innerHTML=`<div role="dialog" aria-modal="true" aria-labelledby="auxAdvancedTitle" style="width:min(620px,calc(100vw - 32px));max-height:calc(100vh - 48px);overflow:auto;background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:14px;box-shadow:0 18px 60px rgba(0,0,0,.45);padding:16px">
  <style>#auxAdvancedOverlay input:-webkit-autofill,#auxAdvancedOverlay textarea:-webkit-autofill{box-shadow:0 0 0 1000px var(--code-bg) inset!important;-webkit-box-shadow:0 0 0 1000px var(--code-bg) inset!important;-webkit-text-fill-color:var(--text)!important;caret-color:var(--text)!important}</style>
  <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px">
   <div><div id="auxAdvancedTitle" style="font-weight:700;font-size:16px"></div><div id="auxAdvancedSubtitle" style="font-size:11px;color:var(--muted);margin-top:2px"></div></div>
   <button type="button" id="auxAdvancedClose" aria-label="${esc(t('terminal_close')||'Close')}" style="width:28px;height:28px;display:inline-flex;align-items:center;justify-content:center;border-radius:8px;border:1px solid var(--border);background:var(--input-bg);color:var(--text);cursor:pointer;font-size:18px;line-height:1">×</button>
  </div>
  <div id="auxAdvancedBody" style="display:grid;gap:10px"></div>
  <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px">
   <button type="button" id="auxAdvancedCancel" style="${neutralBtn}">${esc(t('cancel')||'Cancel')}</button>
   <button type="button" id="auxAdvancedSave" style="${primaryBtn}">${esc(t('settings_aux_advanced_save')||'Save options')}</button>
  </div>
 </div>`;
 document.body.appendChild(overlay);
 const close=()=>{overlay.style.display='none';overlay.dataset.task='';};
 $('auxAdvancedClose')?.addEventListener('click',close);
 $('auxAdvancedCancel')?.addEventListener('click',close);
 overlay.addEventListener('click',ev=>{if(ev.target===overlay) close();});
 return overlay;
}

function _auxAdvancedInputHtml(id,label,value,desc,type='text',extraAttrs='',extraStyle=''){
 const fieldName=id==='auxAdvancedApiKey'?'aux-manual-override-value':('aux-field-'+id.replace(/^auxAdvanced/,'').toLowerCase());
 const autocompleteAttr=/\bautocomplete=/.test(extraAttrs)?'':'autocomplete="off"';
 const inputAttrs=`id="${id}" name="${fieldName}" type="${type}" value="${esc(value)}" ${autocompleteAttr} autocapitalize="off" autocorrect="off" spellcheck="false" data-lpignore="true" data-1p-ignore="true" ${extraAttrs}`;
 return `<label style="display:grid;gap:4px;font-size:12px;color:var(--text)"><span style="font-weight:600">${esc(label)}</span><input ${inputAttrs} style="width:100%;box-sizing:border-box;padding:7px 8px;background:var(--code-bg);color:var(--text);border:1px solid var(--border2);border-radius:6px;font-size:12px${extraStyle}"><span style="font-size:10px;color:var(--muted);line-height:1.35">${esc(desc)}</span></label>`;
}

function _mainModelSupportsServiceTier(cfg){
 const selected=$('settingsModel');
 const selectedOpt=selected&&selected.selectedIndex>=0?selected.options[selected.selectedIndex]:null;
 const optgroup=selectedOpt&&selectedOpt.parentElement&&selectedOpt.parentElement.tagName==='OPTGROUP'?selectedOpt.parentElement:null;
 const provider=((selectedOpt&&selectedOpt.dataset&&selectedOpt.dataset.provider)||(optgroup&&optgroup.dataset&&optgroup.dataset.provider)||(cfg&&cfg.provider)||'').trim().toLowerCase();
 if(provider!=='openai'&&provider!=='openai-api'&&provider!=='openai-codex') return false;
 const fastSupport = selectedOpt&&selectedOpt.dataset?selectedOpt.dataset.fast:'';
 if(fastSupport) return fastSupport==='1'||fastSupport==='true';
 return cfg&&cfg.supports_fast_tier===true;
}

function _openAuxAdvancedOptions(taskCfg,cfg){
 const isMain=taskCfg==='__main__';
 const taskKey=isMain?'__main__':(taskCfg&&typeof taskCfg==='object'&&typeof taskCfg.task==='string'?taskCfg.task:typeof taskCfg==='string'?taskCfg:'');
 const slot=isMain?{task:taskKey,label:(t('settings_label_model')||'Default model')}:_auxTaskLabelFromMeta(taskKey,taskCfg);
 const overlay=_ensureAuxAdvancedModal();
 overlay.dataset.task=taskKey;
 const title=$('auxAdvancedTitle'),sub=$('auxAdvancedSubtitle'),body=$('auxAdvancedBody');
 const slotName=isMain?(t('settings_label_model')||'Default model'):(slot&&slot.label)||taskKey;
 if(title) title.textContent=isMain?(t('settings_main_advanced_title')||'Main model options'):((t('settings_aux_advanced_title')||'{task} options').replace('{task}',slotName));
 if(sub) sub.textContent=isMain?(t('settings_main_advanced_subtitle')||'Advanced config for the default chat model.'):(t('settings_aux_advanced_subtitle')||'Advanced config for auxiliary.');
 const extraBody=cfg&&cfg.extra_body&&typeof cfg.extra_body==='object'&&Object.keys(cfg.extra_body).length?JSON.stringify(cfg.extra_body,null,2):'';
 const apiKeyHint=cfg&&cfg.api_key_set?(t('settings_aux_advanced_api_key_set_hint')||'API key is set. Leave blank to keep it, or use clear to remove it.'):(t('settings_aux_advanced_api_key_empty_hint')||'Leave blank to use provider/default credentials.');
 if(body){
  const selectedServiceTier=((cfg&&cfg.service_tier)||'').trim().toLowerCase()==='priority'?'priority':'';
  const serviceTierField=isMain&&_mainModelSupportsServiceTier(cfg)
   ? `<label style="display:grid;gap:4px;font-size:12px;color:var(--text)"><span style="font-weight:600">${esc(t('settings_main_advanced_service_tier')||'Service tier')}</span><select id="auxAdvancedServiceTier" style="width:100%;box-sizing:border-box;padding:7px 8px;background:var(--code-bg);color:var(--text);border:1px solid var(--border2);border-radius:6px;font-size:12px"><option value=""${selectedServiceTier?'':' selected'}>${esc(t('settings_main_advanced_service_tier_default')||'Default / off')}</option><option value="priority"${selectedServiceTier==='priority'?' selected':''}>${esc(t('settings_main_advanced_service_tier_priority')||'Priority (fast)')}</option></select><span style="font-size:10px;color:var(--muted);line-height:1.35">${esc(t('settings_main_advanced_service_tier_desc')||'Optional request setting for OpenAI-family providers.')}</span></label>`
   : '';
  const timingFields=isMain?'':(
   _auxAdvancedInputHtml('auxAdvancedTimeout',t('settings_aux_advanced_timeout')||'Timeout seconds',_auxAdvancedValue(cfg,'timeout'),t('settings_aux_advanced_timeout_desc')||'Request timeout for this auxiliary task. Blank uses Hermes default.','number','inputmode="numeric" min="1" step="1"')+
   _auxAdvancedInputHtml('auxAdvancedDownloadTimeout',t('settings_aux_advanced_download_timeout')||'Download timeout seconds',_auxAdvancedValue(cfg,'download_timeout'),t('settings_aux_advanced_download_timeout_desc')||'Only relevant for tasks that download media/content, e.g. vision. Blank uses default.','number','inputmode="numeric" min="1" step="1"')+
   _auxAdvancedInputHtml('auxAdvancedMaxConcurrency',t('settings_aux_advanced_max_concurrency')||'Max concurrency',_auxAdvancedValue(cfg,'max_concurrency'),t('settings_aux_advanced_max_concurrency_desc')||'Optional per-task concurrency limit. Blank uses default.','number','inputmode="numeric" min="1" step="1"'));
  body.innerHTML=
   _auxAdvancedInputHtml('auxAdvancedBaseUrl',t('settings_aux_advanced_base_url')||'Base URL',_auxAdvancedValue(cfg,'base_url'),t('settings_aux_advanced_base_url_desc')||'Optional provider endpoint override.','text','inputmode="url"')+
   serviceTierField+
   timingFields+
   `<label style="display:grid;gap:4px;font-size:12px;color:var(--text)"><span style="font-weight:600">${esc(t('settings_aux_advanced_extra_body')||'Extra body JSON')}</span><textarea id="auxAdvancedExtraBody" rows="6" style="width:100%;box-sizing:border-box;padding:7px 8px;background:var(--code-bg);color:var(--text);border:1px solid var(--border2);border-radius:6px;font-size:12px;font-family:var(--mono,monospace)">${esc(extraBody)}</textarea><span style="font-size:10px;color:var(--muted);line-height:1.35">${esc(t('settings_aux_advanced_extra_body_desc')||'Optional JSON object merged into the model request body.')}</span></label>`+
   _auxAdvancedInputHtml('auxAdvancedApiKey',t('settings_aux_advanced_api_key')||'API key override','',apiKeyHint,'text','autocomplete="one-time-code" inputmode="text" readonly onfocus="this.removeAttribute(&quot;readonly&quot;)"',';-webkit-text-security:disc')+
   `<label style="display:${cfg&&cfg.api_key_set?'flex':'none'};align-items:center;gap:8px;font-size:12px;color:var(--text)"><input id="auxAdvancedApiKeyClear" type="checkbox" style="width:15px;height:15px;accent-color:var(--accent)"><span>${esc(t('settings_aux_advanced_api_key_clear')||'Clear existing API key override')}</span></label>`;
 }
 const save=$('auxAdvancedSave');
 if(save){
  save.onclick=async()=>{
   let extra={};
   const extraText=($('auxAdvancedExtraBody')?.value||'').trim();
   if(extraText){
    try{extra=JSON.parse(extraText);}catch(e){if(typeof showToast==='function') showToast(t('settings_aux_advanced_extra_body_invalid_json')||'Extra body must be valid JSON');return;}
    if(!extra||Array.isArray(extra)||typeof extra!=='object'){if(typeof showToast==='function') showToast(t('settings_aux_advanced_extra_body_object_required')||'Extra body must be a JSON object');return;}
   }
   const provSel=isMain?null:$('aux-prov-'+taskKey),modelSel=isMain?$('settingsModel'):$('aux-model-'+taskKey);
   const provider=isMain?((cfg&&cfg.provider)||''):(provSel?provSel.value:((cfg&&cfg.provider)||'auto'));
   const model=modelSel&&modelSel.value!=='__custom__'?(modelSel.value||''):((cfg&&cfg.model)||'');
   const advanced={
    base_url:$('auxAdvancedBaseUrl')?.value||'',
    extra_body:extra,
    api_key:$('auxAdvancedApiKey')?.value||'',
    api_key_clear:!!($('auxAdvancedApiKeyClear')&&$('auxAdvancedApiKeyClear').checked),
   };
   if(isMain&&$('auxAdvancedServiceTier')){
    advanced.service_tier=$('auxAdvancedServiceTier')?.value||'';
   }
   if(!isMain){
    advanced.timeout=$('auxAdvancedTimeout')?.value||'';
    advanced.download_timeout=$('auxAdvancedDownloadTimeout')?.value||'';
    advanced.max_concurrency=$('auxAdvancedMaxConcurrency')?.value||'';
   }
   try{
    await api('/api/model/set',{method:'POST',body:JSON.stringify({scope:isMain?'main':'auxiliary',task:isMain?'':taskKey,provider,model,advanced})});
    if(typeof showToast==='function') showToast(isMain?(t('settings_main_advanced_saved')||'Main model options saved'):(t('settings_aux_advanced_saved')||'Auxiliary options saved'));
    overlay.style.display='none';
    _loadAuxiliaryModels();
    // #4650 review: a main-model advanced save can change base_url, which
    // /api/reasoning's answer depends on for some providers (e.g. LM Studio),
    // WITHOUT changing the model/provider cache key. Invalidate the reasoning
    // cache and refresh so the chip reflects the new config (one refetch).
    if(isMain){
      if(typeof _lastReasoningFetchKey!=='undefined') _lastReasoningFetchKey=null;
      if(typeof fetchReasoningChip==='function') fetchReasoningChip();
    }
   }catch(e){
    if(typeof showToast==='function') showToast(isMain?(t('settings_main_advanced_save_failed')||'Failed to save main model options'):(t('settings_aux_advanced_save_failed')||'Failed to save auxiliary options'));
   }
  };
 }
 overlay.style.display='flex';
 setTimeout(()=>$('auxAdvancedBaseUrl')?.focus(),0);
}

function _bindMainAdvancedOptionsButton(){
 const modelSel=$('settingsModel');
 let btn=$('mainAdvancedBtn');
 if(modelSel){
  const parent=modelSel.parentElement;
  let row=parent&&parent.classList&&parent.classList.contains('model-advanced-row')?parent:null;
  if(!row){
   row=document.createElement('div');
   row.className='model-advanced-row';
   parent.insertBefore(row,modelSel);
   row.appendChild(modelSel);
  }
  if(!btn){
   btn=document.createElement('button');
   btn.type='button';
   btn.id='mainAdvancedBtn';
  }
  if(btn.parentElement!==row) row.appendChild(btn);
  row.style.cssText='display:grid;grid-template-columns:minmax(0,1fr) 34px;gap:8px;align-items:center';
  modelSel.style.width='100%';
  modelSel.style.minWidth='0';
  modelSel.style.boxSizing='border-box';
 }
 if(!btn) return;
 btn.classList.add('model-advanced-btn');
 if(!btn.querySelector('svg')&&typeof li==='function') btn.innerHTML=li('settings',15);
 btn.style.position='';
 btn.style.right='';
 btn.style.top='';
 btn.style.transform='';
 btn.style.width='32px';
 btn.style.height='32px';
 btn.style.display='flex';
 btn.style.alignItems='center';
 btn.style.justifyContent='center';
 btn.style.flex='0 0 32px';
 btn.style.boxSizing='border-box';
 const title=t('settings_aux_advanced_button_title')||'Advanced options';
 btn.title=title;
 btn.setAttribute('aria-label',t('settings_main_advanced_button_aria')||'Advanced options for main model');
 btn.disabled=_mainAdvancedConfig===null;
 btn.style.opacity='';
 btn.style.cursor='';
 if(btn._bound) return;
 btn._bound=true;
 btn.addEventListener('click',()=>{if(_mainAdvancedConfig!==null)_openAuxAdvancedOptions('__main__',_mainAdvancedConfig||{});});
}

async function _loadAuxiliaryModels(){
 const container=$('auxModelsContainer');
 if(!container) return;
 container.innerHTML='<div style="color:var(--muted);font-size:12px">'+(t('settings_aux_loading')||'Loading…')+'</div>';

 try{
  // Fetch auxiliary config AND the WebUI's own /api/models for provider/model lists
  const [auxData,modelsData]=await Promise.all([
   api('/api/model/auxiliary').catch(()=>null),
   api('/api/models').catch(()=>null),
  ]);
  // Build provider list from /api/models groups
  // /api/models returns: { groups: [{ provider: str, provider_id: str, models: [{id,label}] }] }
  const groups=(modelsData&&modelsData.groups)||[];
  _auxProviders=groups.filter(g=>g.provider&&((g.models&&g.models.length>0)||(g.extra_models&&g.extra_models.length>0))).map(g=>({
   slug:g.provider_id||g.provider,
   name:g.provider,
   models:[...(g.models||[]),...(g.extra_models||[])].map(m=>m.id),
  }));
  if(auxData&&Object.prototype.hasOwnProperty.call(auxData,'main')){
   _mainAdvancedConfig=auxData.main||{};
  }else{
   _mainAdvancedConfig=null;
  }
  _bindMainAdvancedOptionsButton();
  _auxTasks=_normalizeAuxiliaryTasks((auxData&&auxData.tasks)||[]);
  // Build a quick lookup: taskKey → config
  const taskMap={};
  for(const task of _auxTasks) taskMap[task.task]=task;
  _auxOriginalConfig=JSON.parse(JSON.stringify(taskMap));

  container.innerHTML='';
  for(const task of _auxTasks){
   const cfg=taskMap[task.task]||{provider:'auto',model:''};
   const row=document.createElement('div');
   row.style.cssText='display:grid;grid-template-columns:120px 1fr 1fr 34px;gap:8px;align-items:center;margin-bottom:8px';

   // Task name + description
   const label=document.createElement('div');
   label.style.cssText='font-size:12px;font-weight:500;color:var(--text);line-height:1.3';
   label.innerHTML=esc(task.label||task.task)+'<div style="font-size:10px;color:var(--muted);font-weight:400">'+esc(task.description||'')+'</div>';
   row.appendChild(label);

   // Provider select
   const provSel=document.createElement('select');
   provSel.id='aux-prov-'+task.task;
   provSel.style.cssText=_auxSelectStyle();
   _buildAuxProviderOptions(provSel,_auxProviders,cfg.provider);
   provSel.addEventListener('change',()=>_onAuxProviderChange(task.task,_auxProviders));
   row.appendChild(provSel);

   // Model select
   const modelSel=document.createElement('select');
   modelSel.id='aux-model-'+task.task;
   modelSel.style.cssText=_auxSelectStyle();
   _buildAuxModelOptions(modelSel,cfg.provider,_auxProviders,cfg.model);
   modelSel.addEventListener('change',()=>_onAuxModelChange(task.task));
   row.appendChild(modelSel);

   const advancedBtn=document.createElement('button');
   advancedBtn.type='button';
   advancedBtn.className='aux-advanced-btn model-advanced-btn';
   const advTitle=t('settings_aux_advanced_button_title')||'Advanced options';
   const taskName=task.label||task.task;
   advancedBtn.title=advTitle;
   advancedBtn.setAttribute('aria-label',(t('settings_aux_advanced_button_aria')||'Advanced options for {task}').replace('{task}',taskName));
   advancedBtn.innerHTML=typeof li==='function'?li('settings',15):'⚙';
   advancedBtn.addEventListener('click',()=>_openAuxAdvancedOptions(task,cfg));
   row.appendChild(advancedBtn);

   container.appendChild(row);
  }
  // Hide apply button (no changes yet)
  const applyBtn=$('btnApplyAuxModels');
  if(applyBtn) applyBtn.style.display='none';

  // Reset button
  const resetBtn=$('btnResetAuxModels');
  if(resetBtn&&!resetBtn._bound){
   resetBtn._bound=true;
   resetBtn.addEventListener('click',async()=>{
    if(!(await showConfirmDialog({title:t('settings_aux_reset_confirm_title')||'Reset auxiliary models?',message:t('settings_aux_reset_confirm_msg')||'This will set all auxiliary tasks to auto (use main model).',confirmLabel:t('settings_btn_reset_aux_models')||'Reset',danger:true}))) return;
    try{
     await api('/api/model/set',{method:'POST',body:JSON.stringify({scope:'auxiliary',task:'__reset__',provider:'auto',model:''})});
     if(typeof showToast==='function') showToast(t('settings_aux_reset_done')||'Auxiliary models reset to auto');
     _loadAuxiliaryModels();
    }catch(e){
     if(typeof showToast==='function') showToast(t('settings_aux_save_failed')||'Failed to reset auxiliary models');
    }
   });
  }

  // Apply button
  if(applyBtn&&!applyBtn._bound){
   applyBtn._bound=true;
   applyBtn.addEventListener('click',_applyAuxModels);
  }
 }catch(e){
  console.warn('[settings] auxiliary models load failed',e);
  container.innerHTML='<div style="color:var(--muted);font-size:12px">'+(t('settings_aux_load_failed')||'Could not load auxiliary model settings. Make sure the agent API is available.')+'</div>';
 }
}

async function _applyAuxModels(){
 let saved=0;
 for(const task of _auxTasks){
  const provSel=$('aux-prov-'+task.task);
  const modelSel=$('aux-model-'+task.task);
  if(!provSel) continue;
  const provider=provSel.value;
  const model=(modelSel&&modelSel.value!=='__custom__')?(modelSel.value||''):'';
  const orig=_auxOriginalConfig?.[task.task]||{provider:'auto',model:''};
  // Only save if changed
  if(provider!==orig.provider||model!==orig.model){
   try{
    await api('/api/model/set',{method:'POST',body:JSON.stringify({scope:'auxiliary',task:task.task,provider,model})});
    saved++;
   }catch(e){
    console.warn('[settings] failed to save aux task',task.task,e);
    if(typeof showToast==='function') showToast(t('settings_aux_save_failed')||'Failed to save auxiliary model');
    return;
   }
  }
 }
 if(typeof showToast==='function') showToast(saved?(t('settings_aux_saved')||'Auxiliary models updated'):(t('settings_aux_no_changes')||'No changes to apply'));
 // Reload to refresh state
 _loadAuxiliaryModels();
}

async function saveSettings(andClose){
  const model=($('settingsModel')||{}).value;
  const modelState=(typeof _captureModelDropdownSelection==='function'&&$('settingsModel'))
    ? (_captureModelDropdownSelection($('settingsModel'))||{model:String(model||''),model_provider:null})
    : {model:String(model||''),model_provider:null};
  const modelChanged=(model||'')!==(_settingsHermesDefaultModelOnOpen||'')||((modelState.model_provider||null)!==(_settingsHermesDefaultModelProviderOnOpen||null));
  const sendKey=($('settingsSendKey')||{}).value;
  const showTokenUsage=!!($('settingsShowTokenUsage')||{}).checked;
  const showQuotaChip=!!($('settingsShowQuotaChip')||{}).checked;
  const showConversationOutline=!!($('settingsShowConversationOutline')||{}).checked;
  const showTps=!!($('settingsShowTps')||{}).checked;
  const fadeTextEffect=!!($('settingsFadeTextEffect')||{}).checked;
  const showCliSessions=!!($('settingsShowCliSessions')||{}).checked;
  const showClaudeCodeSessions=!!($('settingsShowClaudeCodeSessions')||{}).checked;
  const showCronSessions=!!($('settingsShowCronSessions')||{}).checked;
  const showWebhookSessions=!!($('settingsShowWebhookSessions')||{}).checked;
  const showPreviousMessagingSessions=!!($('settingsShowPreviousMessagingSessions')||{}).checked;
  const pinnedSessionsLimit=parseInt(($('settingsPinnedSessionsLimit')||{}).value,10)||3;
  const pw=($('settingsPassword')||{}).value;
  const theme=($('settingsTheme')||{}).value||'dark';
  const skin=($('settingsSkin')||{}).value||'default';
  const fontSize=($('settingsFontSize')||{}).value||localStorage.getItem('hermes-font-size')||'default';
  const language=($('settingsLanguage')||{}).value||'en';
  const sidebarDensity=($('settingsSidebarDensity')||{}).value==='detailed'?'detailed':'compact';
  const defaultMessageMode=($('settingsDefaultMessageMode')||{}).value||'steer';
  const showBusyPlaceholderHint=!!($('settingsShowBusyPlaceholderHint')||{}).checked;
  const body={};
  Object.assign(body,_speechPreferencesPayloadFromUi());

  if(sendKey) body.send_key=sendKey;
  body.theme=theme;
  body.skin=skin;
  body.font_size=fontSize;
  body.session_jump_buttons=!!($('settingsSessionJumpButtons')||{}).checked;
  body.session_endless_scroll=!!($('settingsSessionEndlessScroll')||{}).checked;
  body.chat_activity_display_mode=((($('settingsChatActivityDisplayMode')||{}).value==='transparent_stream')
    ||(($('settingsChatActivityDisplayMode')||{}).value==='hide_all_activity'))
    ? ($('settingsChatActivityDisplayMode')||{}).value
    : 'compact_worklog';
  body.transparent_stream_event_timestamps=(($('settingsTransparentEventTimestamps')||{}).checked)!==false;
  body.auto_scroll_follow=!!($('settingsAutoScrollFollow')||{}).checked;
  body.render_user_markdown=!!($('settingsRenderUserMarkdown')||{}).checked;
  body.large_text_paste_as_attachment=!!($('settingsLargeTextPasteAsAttachment')||{}).checked;
  body.project_quick_create_buttons=!!($('settingsProjectQuickCreate')||{}).checked;
  Object.assign(body,_structuredCodeViewFromUi());
  Object.assign(body,_composerControlVisibilityPayload());
  body.composer_control_order=_getComposerControlOrder();
  body.language=language;
  body.show_token_usage=showTokenUsage;
  const maxTokensField=$('settingsMaxTokens');
  if(maxTokensField){
    const maxTokensRaw=String(maxTokensField.value||'').trim();
    const initialMaxTokens=String(maxTokensField.dataset.initialValue||'').trim();
    if(maxTokensRaw!==initialMaxTokens){
      body.max_tokens=maxTokensRaw===''?null:maxTokensRaw;
    }
  }
  body.show_quota_chip=showQuotaChip===true;
  body.show_conversation_outline=showConversationOutline===true;
  body.show_busy_placeholder_hint=showBusyPlaceholderHint===true;
  body.show_tps=showTps;
  body.fade_text_effect=fadeTextEffect;
  body.terminal_auto_expand_on_output=!!($('settingsTerminalAutoExpand')||{}).checked;
  body.workspace_todos_tab=!!window._workspaceTodosTab;
  body.api_redact_enabled=!!($('settingsApiRedact')||{}).checked;
  body.show_cli_sessions=showCliSessions;
  // Persist the opt-out child independently; the read path applies the parent gate.
  body.show_claude_code_sessions=showClaudeCodeSessions;
  // Cron and webhook sessions are gated on CLI sessions (server short-circuits otherwise);
  // mirror the autosave path so the explicit Save Settings button persists them too. (#3514)
  body.show_cron_sessions=showCliSessions&&showCronSessions;
  body.show_webhook_sessions=showCliSessions&&showWebhookSessions;
  body.show_previous_messaging_sessions=showPreviousMessagingSessions;
  body.pinned_sessions_limit=pinnedSessionsLimit;
  body.sync_to_insights=!!($('settingsSyncInsights')||{}).checked;
  body.check_for_updates=!!($('settingsCheckUpdates')||{}).checked;
  body.update_channel=($('settingsUpdateChannel')||{}).value==='experimental'?'experimental':'stable';
  body.ignore_agent_updates=!!($('settingsIgnoreAgentUpdates')||{}).checked;
  body.whats_new_summary_enabled=!!($('settingsWhatsNewSummary')||{}).checked;
  body.sound_enabled=!!($('settingsSoundEnabled')||{}).checked;
  body.rtl=!!($('settingsRtl')||{}).checked;
  body.notifications_enabled=!!($('settingsNotificationsEnabled')||{}).checked;
  body.show_thinking=window._showThinking!==false;
  body.sidebar_density=sidebarDensity;
  body.default_message_mode=defaultMessageMode;
  body.auto_title_refresh_every=(($('settingsAutoTitleRefresh')||{}).value||'0');
  const botName=(($('settingsBotName')||{}).value||'').trim();
  body.bot_name=botName||'Hermes';
  // Password: only act if the field has content; blank = leave auth unchanged
  if(pw && pw.trim()){
    const currentPwField=$('settingsCurrentPassword');
    const currentPw=(currentPwField||{}).value||'';
    if(_settingsPasswordAuthEnabled && !currentPw.trim()){
      if(currentPwField) currentPwField.focus();
      showToast(t('current_password_required'));
      return;
    }
    const payload={...body,_set_password:pw.trim()};
    if(_settingsPasswordAuthEnabled) payload._current_password=currentPw;
    try{
      const saved=await api('/api/settings',{method:'POST',body:JSON.stringify(payload)});
      if(modelChanged && model){
        try{
          await api('/api/default-model',{method:'POST',body:JSON.stringify({model,provider:modelState.model_provider||null})});
          body.default_model=model;
          body.default_model_provider=(modelState&&modelState.model===model)?(modelState.model_provider||null):null;
        }catch(_modelErr){
          if(typeof showToast==='function') showToast('Failed to update default model — settings saved');
        }
      }
      _applySavedSettingsUi(saved, body, {sendKey,showTokenUsage,showQuotaChip,showConversationOutline,showBusyPlaceholderHint,showTps,fadeTextEffect,showCliSessions,theme,skin,language,sidebarDensity,fontSize});
      showToast(t(saved.auth_just_enabled?'settings_saved_pw':'settings_saved_pw_updated'));
      const cpField=$('settingsCurrentPassword'); if(cpField) cpField.value='';
      const pwField=$('settingsPassword'); if(pwField) pwField.value='';
      _settingsPasswordAuthEnabled=!!saved.password_auth_enabled;
      _updateCurrentPasswordVisibility();
      try{
        const authStatus=await api('/api/auth/status');
        _renderSettingsAuthStatus(authStatus);
        _updateAuthWarningBadge(authStatus);
        _updateAuthDisabledWarning(authStatus);
      }catch(e){}
      _settingsDirty=false;
      _resetSettingsPanelState();
      if(!andClose) _pendingSettingsTargetPanel = null;
      if(andClose) _hideSettingsPanel();
      return;
    }catch(e){showToast(t('settings_save_failed')+e.message);return;}
  }
  try{
    const saved=await api('/api/settings',{method:'POST',body:JSON.stringify(body)});
    if(modelChanged && model){
      try{
        await api('/api/default-model',{method:'POST',body:JSON.stringify({model,provider:modelState.model_provider||null})});
        body.default_model=model;
        body.default_model_provider=(modelState&&modelState.model===model)?(modelState.model_provider||null):null;
      }catch(_modelErr){
        if(typeof showToast==='function') showToast('Failed to update default model — settings saved');
      }
    }
    _applySavedSettingsUi(saved, body, {sendKey,showTokenUsage,showQuotaChip,showConversationOutline,showBusyPlaceholderHint,showTps,fadeTextEffect,showCliSessions,theme,skin,language,sidebarDensity,fontSize});
    showToast(t('settings_saved'));
    _settingsDirty=false;
    _resetSettingsPanelState();
    if(!andClose) _pendingSettingsTargetPanel = null;
    if(andClose) _hideSettingsPanel();
  }catch(e){
    showToast(t('settings_save_failed')+e.message);
  }
}

async function signOut(){
  try{
    const response=await api('/api/auth/logout',{method:'POST',body:'{}'});
    window.location.href=response.trusted_logout_url||'login';
  }catch(e){
    showToast(t('sign_out_failed')+e.message);
  }
}

async function goPasswordless(){
  const ok=await showConfirmDialog({title:'Go passwordless?',message:'This removes the password and keeps passkey sign-in enabled. Keep at least one passkey registered or you could lose access.',confirmLabel:'Go passwordless',danger:false,focusCancel:true});
  if(!ok) return;
  const currentPw=($('settingsCurrentPassword')||{}).value;
  const payload={_passwordless:true};
  if(_settingsPasswordAuthEnabled && currentPw) payload._current_password=currentPw;
  try{
    const saved=await api('/api/settings',{method:'POST',body:JSON.stringify(payload)});
    showToast('Password removed. Passkey sign-in remains enabled.');
    _setSettingsAuthButtonsVisible(!!saved.auth_enabled);
    _syncPasswordlessButton({auth_enabled:saved.auth_enabled,password_auth_enabled:false,passkeys_count:1});
    const pwField=$('settingsPassword'); if(pwField) pwField.value='';
    const cpField=$('settingsCurrentPassword'); if(cpField) cpField.value='';
    _settingsPasswordAuthEnabled=false;
    _updateCurrentPasswordVisibility();
    try{
      const authStatus=await api('/api/auth/status');
      _renderSettingsAuthStatus(authStatus);
      _updateAuthWarningBadge(authStatus);
    }catch(e){}
  }catch(e){showToast('Failed to go passwordless: '+e.message);}
}

async function disableAuth(){
  const currentPwField=$('settingsCurrentPassword');
  const currentPw=(currentPwField||{}).value||'';
  if(_settingsPasswordAuthEnabled && !currentPw.trim()){
    if(currentPwField) currentPwField.focus();
    showToast(t('current_password_required'));
    return;
  }
  const confirmText='DISABLE AUTH';
  const userInput=await showPromptDialog({title:t('disable_auth_confirm_title'),message:t('disable_auth_confirm_message')+' '+t('disable_auth_typed_confirm'),placeholder:confirmText,confirmLabel:t('disable_auth'),danger:true});
  if(!userInput || userInput.trim()!==confirmText) return;
  const payload={_clear_password:true};
  if(_settingsPasswordAuthEnabled) payload._current_password=currentPw;
  try{
    const saved=await api('/api/settings',{method:'POST',body:JSON.stringify(payload)});
    showToast(t('auth_disabled'));
    const disableBtn=$('btnDisableAuth');
    if(disableBtn) disableBtn.style.display='none';
    const signOutBtn=$('btnSignOut');
    if(signOutBtn) signOutBtn.style.display='none';
    _syncPasswordlessButton({auth_enabled:false,password_auth_enabled:false,passkeys_count:0});
    _settingsPasswordAuthEnabled=false;
    _updateCurrentPasswordVisibility();
    const cpField=$('settingsCurrentPassword'); if(cpField) cpField.value='';
    loadPasskeys();
    try{
      const authStatus=await api('/api/auth/status');
      _renderSettingsAuthStatus(authStatus);
      _updateAuthWarningBadge(authStatus);
      _updateAuthDisabledWarning(authStatus);
    }catch(e){}
  }catch(e){
    showToast(t('disable_auth_failed')+e.message);
  }
}


// ── Cron completion alerts ────────────────────────────────────────────────────

let _cronPollSince=Date.now()/1000;  // track from page load
let _cronPollTimer=null;
let _cronUnreadCount=0;
let _cronPollGeneration=0;
const _cronNewJobIds=new Set();  // track which job IDs had new completions (unread)

function _resetCronUnreadForProfileSwitch(){
  _cronPollGeneration++;
  _cronNewJobIds.clear();
  _cronPollSince=Date.now()/1000;
  // Clear persisted cron sidebar markers from the profile we left. Non-cron
  // completion unread stays intact (#5960 gate: sticky all-profile leak).
  if(typeof _clearCronSessionCompletionUnreadForInactiveProfiles==='function'){
    const activeProfile=(typeof S!=='undefined'&&S&&S.activeProfile)||'default';
    _clearCronSessionCompletionUnreadForInactiveProfiles(activeProfile);
  }
  updateCronBadge();
}

// Auto-refresh the cron list when a job is created from chat or any external source.
// The chat path dispatches this event when the agent response mentions cron creation.
window.addEventListener('hermes:cron_created', () => {
  if ($('cronList')) loadCrons();
});

function startCronPolling(){
  if(_cronPollTimer) return;
  _cronPollTimer=setInterval(async()=>{
    if(document.hidden) return;  // don't poll when tab is in background
    try{
      const pollGeneration=_cronPollGeneration;
      const data=await api(`/api/crons/recent?since=${_cronPollSince}`);
      if(pollGeneration!==_cronPollGeneration) return;
      if(data.completions&&data.completions.length>0){
        for(const c of data.completions){
          if(c.toast_notifications !== false){
            showToast(t('cron_completion_status', c.name, c.status==='error' ? t('status_failed') : t('status_completed')),4000);
          }
          _cronPollSince=Math.max(_cronPollSince,c.completed_at);
          if(c.job_id) _cronNewJobIds.add(String(c.job_id));
          if(c.session_id && typeof _markSessionCompletionUnreadIfBackground === 'function'){
            const activeProfile=(typeof S!=='undefined'&&S&&S.activeProfile)||'default';
            _markSessionCompletionUnreadIfBackground(c.session_id, c.message_count, {
              source:'cron',
              profile:activeProfile,
            });
          }
        }
        // _cronUnreadCount is derived from _cronNewJobIds.size in updateCronBadge.
        updateCronBadge();
      }
    }catch(e){}
  },30000);
}

function updateCronBadge(){
  const tab=document.querySelector('.nav-tab[data-panel="tasks"]');
  if(!tab) return;
  let badge=tab.querySelector('.cron-badge');
  _cronUnreadCount=_cronNewJobIds.size;  // sync counter to set (source of truth)
  if(_cronUnreadCount>0){
    if(!badge){
      badge=document.createElement('span');
      badge.className='cron-badge';
      tab.style.position='relative';
      tab.appendChild(badge);
    }
    badge.textContent=_cronUnreadCount>9?'9+':_cronUnreadCount;
    badge.style.display='';
  }else if(badge){
    badge.style.display='none';
  }
}

// Clear cron badge only when all unread jobs have been viewed (not on panel open)
function _clearCronUnreadForJob(jobId){
  const id=String(jobId);
  if(_cronNewJobIds.has(id)){
    _cronNewJobIds.delete(id);
    updateCronBadge();  // re-derives _cronUnreadCount from set size
  }
}

const _origSwitchPanel=switchPanel;
switchPanel=async function(name,opts){ return _origSwitchPanel(name,opts); };

// Start polling on page load
startCronPolling();

// ── Background agent error tracking ──────────────────────────────────────────

const _backgroundErrors=[];  // {session_id, title, message, ts}

function trackBackgroundError(sessionId, title, message){
  // Only track if user is NOT currently viewing this session
  if(S.session&&S.session.session_id===sessionId) return;
  _backgroundErrors.push({session_id:sessionId, title:title||t('untitled'), message, ts:Date.now()});
  showErrorBanner();
}

function showErrorBanner(){
  let banner=$('bgErrorBanner');
  if(!banner){
    banner=document.createElement('div');
    banner.id='bgErrorBanner';
    banner.className='bg-error-banner';
    const msgs=document.querySelector('.messages');
    if(msgs) msgs.parentNode.insertBefore(banner,msgs);
    else document.body.appendChild(banner);
  }
  const latest=_backgroundErrors[0];  // FIFO: show oldest (first) error
  if(!latest){banner.style.display='none';return;}
  const count=_backgroundErrors.length;
  const msg=count>1?t('bg_error_multi',count):t('bg_error_single',latest.title);
  banner.innerHTML=`<span>\u26a0 ${esc(msg)}</span><div style="display:flex;gap:6px;flex-shrink:0"><button class="reconnect-btn" onclick="navigateToErrorSession()">${esc(t('view'))}</button><button class="reconnect-btn" onclick="dismissErrorBanner()">${esc(t('dismiss'))}</button></div>`;
  banner.style.display='';
}

function navigateToErrorSession(){
  const latest=_backgroundErrors.shift();  // FIFO: show oldest error first
  if(latest){
    loadSession(latest.session_id);renderSessionList();
  }
  if(_backgroundErrors.length===0) dismissErrorBanner();
  else showErrorBanner();
}

function dismissErrorBanner(){
  _backgroundErrors.length=0;
  const banner=$('bgErrorBanner');
  if(banner) banner.style.display='none';
}

// Event wiring


// ── MCP Server Management ──
function _mcpStatusLabel(status){
  const key={
    active:'mcp_status_active',
    configured:'mcp_status_configured',
    disabled:'mcp_status_disabled',
    invalid_config:'mcp_status_invalid_config',
  }[status]||'mcp_status_unknown';
  return t(key);
}
function toggleMcpServer(name, enabled){
  api('/api/mcp/servers/'+encodeURIComponent(name),{
    method:'PATCH',
    body:JSON.stringify({enabled:enabled}),
  }).then(r=>{
    if(r&&r.ok){
      _refreshMcpToolsetsCatalog();
      showToast(t(enabled?'mcp_enabled_toast':'mcp_disabled_toast',name));
    }
    else showToast(t('mcp_toggle_failed'),'error');
    loadMcpServers();
  }).catch(()=>{showToast(t('mcp_toggle_failed'),'error');loadMcpServers();});
}
function _refreshMcpToolsetsCatalog(payload){
  if(typeof window.invalidateToolsetsCatalog==='function') window.invalidateToolsetsCatalog(payload);
}
function loadMcpServers(){
  const list=$('mcpServerList');
  if(!list) return;
  list.innerHTML=`<div style="color:var(--muted);font-size:12px;padding:6px 0">${esc(t('loading'))}</div>`;
  api('/api/mcp/servers').then(r=>{
    if(!r||!Array.isArray(r.servers)) return;
    _refreshMcpToolsetsCatalog(r);
    if(!r.servers.length){
      list.innerHTML=`<div class="mcp-empty-state" style="color:var(--muted);font-size:12px;padding:6px 0">${esc(t('mcp_no_servers'))}</div>`;
      return;
    }
    list.innerHTML=r.servers.map(s=>{
      const transportLabel=s.transport==='http'?'HTTP':s.transport==='stdio'?'stdio':(''+(s.transport||'unknown'));
      const transportClass=s.transport==='http'?'mcp-http':s.transport==='stdio'?'mcp-stdio':'mcp-unknown';
      const transportBadge=`<span class="mcp-transport-badge ${transportClass}">${esc(transportLabel)}</span>`;
      const status=s.status||'configured';
      const statusBadge=`<span class="mcp-status-badge mcp-status-${esc(status)}">${esc(_mcpStatusLabel(status))}</span>`;
      const toolCount=s.tool_count===null||typeof s.tool_count==='undefined'?'—':String(s.tool_count);
      const detail=s.transport==='http'
        ? (s.url||'')
        : (s.transport==='stdio'?`${s.command||''} ${Array.isArray(s.args)?s.args.join(' '):''}`:t('mcp_status_invalid_config'));
      const envInfo=s.env?Object.entries(s.env).map(([k,v])=>`${k}=${v}`).join(', '):'';
      const headersInfo=s.headers?Object.entries(s.headers).map(([k,v])=>`${k}=${v}`).join(', '):'';
      const secretInfo=[envInfo,headersInfo].filter(Boolean).join(' | ');
      const isEnabled=s.enabled!==false;
      const encodedName=encodeURIComponent(s.name).replace(/'/g,"\\'");
      const toggleBtn=r.toggle_supported
        ?`<button type="button" class="mcp-toggle-btn ${isEnabled?'mcp-toggle-enabled':'mcp-toggle-disabled'}" title="${esc(t(isEnabled?'mcp_disable_server':'mcp_enable_server'))}" onclick="toggleMcpServer('${encodedName}',${!isEnabled})">${esc(t(isEnabled?'mcp_enabled_yes':'mcp_enabled_no'))}</button>`
        :`<span>${esc(t(isEnabled?'mcp_enabled_yes':'mcp_enabled_no'))}</span>`;
      return `<div class="mcp-server-row">
        <div class="mcp-server-row-head">
          <span class="mcp-server-name">${esc(s.name)}</span>
          ${transportBadge}
          ${statusBadge}
        </div>
        <div class="mcp-server-detail">${esc(detail)}${secretInfo?' | '+esc(secretInfo):''}</div>
        <div class="mcp-server-meta"><span class="mcp-tool-count">${esc(t('mcp_tool_count',toolCount))}</span>${toggleBtn}</div>
      </div>`;
    }).join('');
  }).catch(()=>{list.innerHTML=`<div class="mcp-error-state" style="color:#ef4444;font-size:12px;padding:6px 0">${esc(t('mcp_load_failed'))}</div>`});
}
let _mcpToolsCache=[];
let _mcpToolsMeta={};
let _mcpToolsPage=1;
let _mcpToolsPageSize=5;
const MCP_TOOLS_PAGE_SIZE_OPTIONS=[5,10,20,40];
function _filterMcpToolsForSearch(tools, query){
  const q=(query||'').trim().toLowerCase();
  if(!q) return Array.isArray(tools)?tools:[];
  return (Array.isArray(tools)?tools:[]).filter(tool=>{
    const hay=[tool.name,tool.server,tool.description].map(v=>String(v||'').toLowerCase()).join(' ');
    return hay.includes(q);
  });
}
function _mcpToolSchemaText(schemaSummary){
  if(!Array.isArray(schemaSummary)||!schemaSummary.length) return t('mcp_tools_schema_empty');
  return schemaSummary.map(p=>{
    const req=p.required?'*':'';
    const desc=p.description?` — ${p.description}`:'';
    return `${p.name}${req}: ${p.type||'unknown'}${desc}`;
  }).join('\n');
}
function _mcpToolsSummary(total, filtered, page, pages, query){
  const trimmedQuery=(query||'').trim();
  if(!filtered){
    if(trimmedQuery) return t('mcp_tools_summary_no_matches',trimmedQuery,total);
    return total?t('mcp_tools_summary_none'):'';
  }
  const pageSize=_mcpToolsPageSize||5;
  const start=(page-1)*pageSize+1;
  const end=Math.min(filtered,page*pageSize);
  const searchNote=trimmedQuery?t('mcp_tools_summary_matching',trimmedQuery):'';
  const totalNote=filtered===total?'':t('mcp_tools_summary_total_note',total);
  return t('mcp_tools_summary_showing',start,end,filtered,searchNote,totalNote,page,pages);
}
function _mcpToolPageSizeControl(){
  const options=MCP_TOOLS_PAGE_SIZE_OPTIONS.map(size=>`<option value="${size}" ${size===_mcpToolsPageSize?'selected':''}>${size}</option>`).join('');
  return `<label class="mcp-tool-page-size">${esc(t('mcp_tools_page_size_prefix'))} <select aria-label="${esc(t('mcp_tools_per_page_aria'))}" onchange="setMcpToolsPageSize(this.value)">${options}</select> ${esc(t('mcp_tools_page_size_suffix'))}</label>`;
}
function _mcpToolsEmptyMessage(query){
  const base=esc(t(query?'mcp_tools_no_matches':'mcp_tools_no_tools'));
  const unavailable=Array.isArray(_mcpToolsMeta.unavailable_servers)?_mcpToolsMeta.unavailable_servers:[];
  if(query||!unavailable.length) return base;
  return `${base}<br><span class="mcp-tool-empty-detail">${esc(t('mcp_tools_inactive_configured_servers',unavailable.join(', ')))}</span>`;
}
function _renderMcpToolPager(filteredCount, page, pages){
  const pager=$('mcpToolPager');
  if(!pager) return;
  if(pages<=1){
    pager.innerHTML='';
    return;
  }
  pager.innerHTML=`<button type="button" class="mcp-tool-page-btn" onclick="setMcpToolsPage(${page-1})" ${page<=1?'disabled':''} aria-label="${esc(t('mcp_tools_previous_page_aria'))}">${esc(t('mcp_tools_previous_page'))}</button>
    <span class="mcp-tool-page-label">${page} / ${pages}</span>
    <button type="button" class="mcp-tool-page-btn" onclick="setMcpToolsPage(${page+1})" ${page>=pages?'disabled':''} aria-label="${esc(t('mcp_tools_next_page_aria'))}">${esc(t('mcp_tools_next_page'))}</button>`;
}
function _renderMcpTools(tools, query){
  const list=$('mcpToolList');
  const toolbar=$('mcpToolToolbar');
  if(!list) return;
  const filtered=_filterMcpToolsForSearch(tools, query);
  const total=Array.isArray(tools)?tools.length:0;
  const pages=Math.max(1,Math.ceil(filtered.length/_mcpToolsPageSize));
  _mcpToolsPage=Math.min(Math.max(1,_mcpToolsPage||1),pages);
  if(toolbar) toolbar.innerHTML=`<span class="mcp-tool-summary">${esc(_mcpToolsSummary(total,filtered.length,_mcpToolsPage,pages,query))}</span>${_mcpToolPageSizeControl()}`;
  _renderMcpToolPager(filtered.length,_mcpToolsPage,pages);
  if(!filtered.length){
    list.innerHTML=`<div class="mcp-tool-empty-state" style="color:var(--muted);font-size:12px;padding:6px 0">${_mcpToolsEmptyMessage(query)}</div>`;
    return;
  }
  const visible=filtered.slice((_mcpToolsPage-1)*_mcpToolsPageSize,_mcpToolsPage*_mcpToolsPageSize);
  list.innerHTML=visible.map(tool=>{
    const status=tool.status||'unknown';
    const statusBadge=`<span class="mcp-status-badge mcp-status-${esc(status)}">${esc(_mcpStatusLabel(status))}</span>`;
    const schemaText=_mcpToolSchemaText(tool.schema_summary);
    return `<div class="mcp-tool-row">
      <div class="mcp-server-row-head">
        <span class="mcp-tool-name">${esc(tool.name)}</span>
        <span class="mcp-tool-server">${esc(tool.server||'unknown')}</span>
        ${statusBadge}
      </div>
      <div class="mcp-server-detail">${esc(tool.description||'')}</div>
      <pre class="mcp-tool-schema">${esc(schemaText)}</pre>
    </div>`;
  }).join('');
}
function setMcpToolsPage(page){
  _mcpToolsPage=page;
  const input=$('mcpToolSearch');
  _renderMcpTools(_mcpToolsCache,input?input.value:'');
  const list=$('mcpToolList');
  if(list) list.scrollTop=0;
}
function setMcpToolsPageSize(size){
  const next=Number(size);
  if(!MCP_TOOLS_PAGE_SIZE_OPTIONS.includes(next)) return;
  _mcpToolsPageSize=next;
  _mcpToolsPage=1;
  const input=$('mcpToolSearch');
  _renderMcpTools(_mcpToolsCache,input?input.value:'');
  const list=$('mcpToolList');
  if(list) list.scrollTop=0;
}
function filterMcpTools(){
  _mcpToolsPage=1;
  const input=$('mcpToolSearch');
  _renderMcpTools(_mcpToolsCache,input?input.value:'');
  const list=$('mcpToolList');
  if(list) list.scrollTop=0;
}
function loadMcpTools(){
  const list=$('mcpToolList');
  const toolbar=$('mcpToolToolbar');
  const pager=$('mcpToolPager');
  if(!list) return;
  if(toolbar) toolbar.textContent='';
  if(pager) pager.innerHTML='';
  list.innerHTML=`<div style="color:var(--muted);font-size:12px;padding:6px 0">${esc(t('loading'))}</div>`;
  api('/api/mcp/tools').then(r=>{
    _mcpToolsCache=(r&&Array.isArray(r.tools))?r.tools:[];
    _mcpToolsMeta=r||{};
    _mcpToolsPage=1;
    filterMcpTools();
  }).catch(()=>{list.innerHTML=`<div class="mcp-tool-error-state" style="color:#ef4444;font-size:12px;padding:6px 0">${esc(t('mcp_tools_load_failed'))}</div>`});
}
let _gatewayActionInFlight=false;
function _gatewayActionButton(action){
  const labels={start:t('gateway_start'),stop:t('gateway_stop'),restart:t('gateway_restart')};
  return `<button class="sm-btn gateway-action-btn" data-gateway-action="${esc(action)}" onclick="_gatewayAction('${esc(action)}')" ${_gatewayActionInFlight?'disabled':''} style="padding:5px 10px;font-size:12px">${esc(labels[action]||action)}</button>`;
}
function _gatewayActionControls(r){
  const actions=(r&&r.running)?['stop','restart']:['start'];
  return `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:10px">${actions.map(_gatewayActionButton).join('')}</div>`;
}
function _renderGatewayStatus(r){
  const card=$('gatewayStatusCard');
  if(!card||!r) return;
  if(!r.configured){
    card.innerHTML=`<div style="color:var(--muted);font-size:12px;display:flex;align-items:center;gap:6px"><span style="width:8px;height:8px;border-radius:50%;background:#f59e0b;display:inline-block"></span>${esc(t('gateway_not_configured'))}</div>${_gatewayActionControls(r)}`;
    return;
  }
  if(!r.running){
    const reason = _gatewayStatusReason(r);
    const statusLabel = reason === 'gateway_stale_running_state'
      ? t('gateway_metadata_stale')
      : reason === 'remote_gateway_unreachable'
        ? t('gateway_endpoint_unreachable')
        : t('gateway_not_running');
    card.innerHTML=`<div style="color:var(--muted);font-size:12px;display:flex;align-items:center;gap:6px"><span style="width:8px;height:8px;border-radius:50%;background:#ef4444;display:inline-block"></span>${esc(statusLabel)}</div>${_gatewayActionControls(r)}`;
    return;
  }
  const platformIcons={telegram:'💬',discord:'🎮',slack:'📝',web:'🌐',api:'🔌'};
  let badges='';
  if(r.platforms&&r.platforms.length){
    badges=r.platforms.map(p=>{
      const icon=platformIcons[p.name]||'📡';
      return `<span style="display:inline-flex;align-items:center;gap:4px;padding:3px 10px;background:var(--code-bg);border:1px solid var(--border2);border-radius:12px;font-size:12px;font-weight:500">${icon} ${esc(p.label)}</span>`;
    }).join(' ');
  }
  const lastActive=r.last_active?`<span style="font-size:11px;color:var(--muted)">${esc(t('gateway_last_active'))}: ${esc(new Date(r.last_active).toLocaleString())}</span>`:'';
  const sessionInfo=r.session_count?`<span style="font-size:11px;color:var(--muted)">${r.session_count} ${esc(r.session_count!==1?t('gateway_sessions'):t('gateway_session'))}</span>`:'';
  card.innerHTML=`<div style="display:flex;align-items:center;gap:6px;margin-bottom:8px"><span style="width:8px;height:8px;border-radius:50%;background:#22c55e;display:inline-block"></span><span style="font-size:13px;font-weight:500;color:#22c55e">${esc(t('gateway_running'))}</span></div>${badges?`<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px">${badges}</div>`:''}<div style="display:flex;gap:12px">${sessionInfo}${lastActive}</div>${_gatewayActionControls(r)}`;
}
function loadGatewayStatus(){
  const card=$('gatewayStatusCard');
  if(!card) return;
  return api('/api/gateway/status').then(r=>_renderGatewayStatus(r)).catch(()=>{card.innerHTML=`<div style="color:#ef4444;font-size:12px">${esc(t('gateway_status_load_failed'))}</div>`});
}
async function _gatewayAction(action){
  if(_gatewayActionInFlight) return;
  _gatewayActionInFlight=true;
  const buttons=[...document.querySelectorAll('.gateway-action-btn')];
  buttons.forEach(btn=>{btn.disabled=true;});
  try{
    const result=await api(`/api/gateway/${encodeURIComponent(action)}`,{method:'POST',body:JSON.stringify({}),timeoutMs:70000,timeoutToast:false});
    if(typeof showToast==='function') showToast(result&&result.message?result.message:t(`gateway_${action}_success`),3000,'success');
  }catch(e){
    const msg=e&&e.message?e.message:String(e||'');
    if(typeof showToast==='function') showToast(`${t(`gateway_${action}_failed`)}${msg?': '+msg:''}`,5000,'error');
  }finally{
    _gatewayActionInFlight=false;
    await loadGatewayStatus();
  }
}
// Load MCP servers when system settings tab opens
const _origSwitchSettings=switchSettingsSection;
switchSettingsSection=function(name, opts){
  _origSwitchSettings(name, opts);
  if(name==='preferences') updateNotificationPermissionStatus();
  if(name==='system'){loadMcpServers();loadMcpTools();loadGatewayStatus();}
};

// ── Checkpoints / Rollback ──────────────────────────────────────────────────

async function _loadCheckpoints(workspace){
  const container=$('checkpointListContainer');
  if(!container) return;
  try{
    const data=await api(`/api/rollback/list?workspace=${encodeURIComponent(workspace)}`);
    const checkpoints=data.checkpoints||[];
    if(!checkpoints.length){
      container.innerHTML=`<div style="color:var(--muted);font-size:12px;padding:8px 0">${esc(t('checkpoint_empty'))}</div>`;
      return;
    }
    let html='';
    for(const ck of checkpoints){
      const shortId=ck.id||ck.commit||'?';
      const msg=ck.message||'checkpoint';
      const date=ck.date_display||ck.date||'';
      const files=ck.files||0;
      html+=`
        <div class="detail-row" style="align-items:center;padding:6px 0;border-bottom:1px solid var(--border,rgba(255,255,255,0.08))">
          <div style="flex:1;min-width:0">
            <div style="font-size:13px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(msg)}">${esc(msg)}</div>
            <div style="font-size:11px;color:var(--muted);margin-top:2px">
              <code style="font-size:10px">${esc(shortId)}</code>
              ${date ? ` · ${esc(date)}` : ''}
              ${files ? ` · ${esc(t('checkpoint_files'))}: ${files}` : ''}
            </div>
          </div>
          <div style="display:flex;gap:4px;flex-shrink:0;margin-left:8px">
            <button class="panel-head-btn" title="${esc(t('checkpoint_view_diff'))}" onclick="event.stopPropagation();_viewCheckpointDiff('${esc(workspace)}','${esc(ck.id)}')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
            </button>
            <button class="panel-head-btn" title="${esc(t('checkpoint_restore'))}" onclick="event.stopPropagation();_restoreCheckpoint('${esc(workspace)}','${esc(ck.id)}','${esc(msg.replace(/'/g,"\\'"))}')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
            </button>
          </div>
        </div>`;
    }
    container.innerHTML=html;
  }catch(e){
    container.innerHTML=`<div style="color:var(--error,#f87171);font-size:12px;padding:8px 0">${esc(t('checkpoint_error'))}: ${esc(e.message)}</div>`;
  }
}

async function _viewCheckpointDiff(workspace,checkpoint){
  const modal=document.getElementById('checkpointDiffModal');
  if(!modal){
    const m=document.createElement('div');
    m.id='checkpointDiffModal';
    m.style.cssText='position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.6)';
    m.innerHTML=`
      <div style="background:var(--bg,${getComputedStyle(document.documentElement).getPropertyValue('--bg')||'#1a1a2e'});border:1px solid var(--border,rgba(255,255,255,0.12));border-radius:12px;width:90vw;max-width:800px;max-height:80vh;display:flex;flex-direction:column;box-shadow:0 8px 32px rgba(0,0,0,0.4)">
        <div style="display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--border,rgba(255,255,255,0.08))">
          <div id="checkpointDiffModalTitle" style="font-weight:600;font-size:14px"></div>
          <button onclick="document.getElementById('checkpointDiffModal').style.display='none'" style="background:none;border:none;color:var(--fg);cursor:pointer;font-size:18px;padding:0 4px">&times;</button>
        </div>
        <div id="checkpointDiffModalBody" style="flex:1;overflow:auto;padding:12px 16px">
          <div style="color:var(--muted);font-size:12px">${esc(t('checkpoint_loading'))}</div>
        </div>
      </div>`;
    m.onclick=(e)=>{if(e.target===m) m.style.display='none';};
    document.body.appendChild(m);
  }
  modal.style.display='flex';
  $('checkpointDiffModalTitle').textContent=t('checkpoint_diff_title');
  $('checkpointDiffModalBody').innerHTML=`<div style="color:var(--muted);font-size:12px">${esc(t('checkpoint_loading'))}</div>`;
  try{
    const data=await api(`/api/rollback/diff?workspace=${encodeURIComponent(workspace)}&checkpoint=${encodeURIComponent(checkpoint)}`);
    const body=$('checkpointDiffModalBody');
    if(!data.total_changes){
      body.innerHTML=`<div style="color:var(--muted);font-size:12px">${esc(t('checkpoint_diff_no_changes'))}</div>`;
      return;
    }
    let html=`<div style="font-size:12px;margin-bottom:8px">${esc(t('checkpoint_diff_files_changed',data.total_changes))}</div>`;
    if(data.files_changed){
      html+='<div style="margin-bottom:8px">';
      for(const f of data.files_changed){
        const icon=f.status==='deleted'?'−':'~';
        const color=f.status==='deleted'?'var(--error,#f87171)':'var(--accent,#60a5fa)';
        html+=`<div style="font-size:12px;padding:2px 0"><span style="color:${color};font-weight:bold;margin-right:6px">${icon}</span><code style="font-size:11px">${esc(f.file)}</code></div>`;
      }
      html+='</div>';
    }
    if(data.diff){
      html+=`<pre style="background:var(--bg-secondary,rgba(0,0,0,0.3));border:1px solid var(--border,rgba(255,255,255,0.08));border-radius:8px;padding:12px;font-size:11px;line-height:1.4;overflow-x:auto;white-space:pre-wrap;word-break:break-all;max-height:50vh;overflow-y:auto;color:var(--fg)">${esc(data.diff)}</pre>`;
    }
    body.innerHTML=html;
  }catch(e){
    $('checkpointDiffModalBody').innerHTML=`<div style="color:var(--error,#f87171);font-size:12px">${esc(e.message)}</div>`;
  }
}

async function _restoreCheckpoint(workspace,checkpoint,message){
  const label=message||checkpoint;
  const ok=await showConfirmDialog({title:t('checkpoint_restore_confirm_title'),message:t('checkpoint_restore_confirm_message',label),confirmLabel:t('checkpoint_restore'),danger:true,focusCancel:true});
  if(!ok) return;
  try{
    const data=await api('/api/rollback/restore',{method:'POST',body:JSON.stringify({workspace,checkpoint})});
    if(data&&data.ok){
      showToast(t('checkpoint_restored')+(data.files_restored_count?` (${data.files_restored_count} ${t('checkpoint_files').toLowerCase()})`:''));
    }else{
      showToast((data&&data.error)||'Restore failed','error');
    }
  }catch(e){
    showToast(t('checkpoint_restore')+': '+e.message,'error');
  }
}


function updateNotificationPermissionStatus(){
  const el=$('notificationPermissionStatus');
  const btn=$('notificationPermissionButton');
  const btnWrap=$('notificationPermissionButtonWrap');
  if(!el) return;
  if(!('Notification' in window)){
    const unsupported=t('notifications_unsupported');
    el.textContent=unsupported;
    if(btn){
      btn.disabled=true;
      btn.title='';
      btn.setAttribute('aria-label', unsupported);
      btn.setAttribute('aria-disabled','true');
    }
    if(btnWrap) btnWrap.title=unsupported;
    return;
  }
  const perm=Notification.permission||'default';
  const label=t('notifications_permission_status', perm);
  el.textContent=label;
  if(btn){
    const granted=perm==='granted';
    btn.disabled=granted;
    btn.title=granted?'':label;
    btn.setAttribute('aria-label', label);
    btn.setAttribute('aria-disabled', granted?'true':'false');
  }
  if(btnWrap) btnWrap.title=label;
}
