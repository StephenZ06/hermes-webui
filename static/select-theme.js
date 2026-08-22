// ── Themed native <select> dropdowns ────────────────────────────────────────
// Replaces the browser's OS-rendered option-list popup for every <select> in
// the app with a themed popup matching the app's existing dropdown idiom
// (.profile-dropdown / .persona-picker-popup / #composerReasoningDropdown:
// position:fixed, JS-clamped to viewport, var(--surface)/var(--border) tokens).
//
// The native <select> is kept in the DOM exactly as-is (same id, same
// attributes, same value/change semantics) and hidden the same way
// .composer-model-select already hides #modelSelect elsewhere in this
// codebase (position:absolute off-screen, not display:none, so it still
// participates in the DOM/form normally). A themed <button> trigger replaces
// it visually; picking a themed option sets the real select's value and
// dispatches a real 'change' event, so every existing onchange="..." handler
// and $('id').value read elsewhere keeps working unmodified.
//
// #modelSelect and #settingsModel are excluded — they already have their own
// bespoke chip+dropdown UI (composerModelChip/settingsModelChip) built on
// this exact same hidden-select pattern. #settingsChatActivityDisplayMode is
// excluded too — it's a display:none value-holder behind a segmented button
// group, never rendered as a select at all.
(function () {
  var EXCLUDED_IDS = { modelSelect: true, settingsModel: true, settingsChatActivityDisplayMode: true };
  var open = null; // {select, trigger, popup, optionEls:[{idx,row,el,disabled}], highlightedIndex}

  function isThemable(select) {
    if (!select || select.tagName !== 'SELECT') return false;
    if (select.multiple) return false; // not needed by any current select; punt rather than guess at UX
    if (EXCLUDED_IDS[select.id]) return false;
    return true;
  }

  function closePopup() {
    if (!open) return;
    var o = open;
    open = null;
    if (o.popup && o.popup.parentNode) o.popup.parentNode.removeChild(o.popup);
    o.trigger.setAttribute('aria-expanded', 'false');
    o.trigger.classList.remove('themed-select-trigger-open');
  }

  function flattenOptions(select) {
    var items = [];
    Array.prototype.forEach.call(select.children, function (node) {
      if (node.tagName === 'OPTGROUP') {
        items.push({ group: true, label: node.label });
        Array.prototype.forEach.call(node.children, function (opt) {
          if (opt.tagName === 'OPTION') items.push({ el: opt });
        });
      } else if (node.tagName === 'OPTION') {
        items.push({ el: node });
      }
    });
    return items;
  }

  function positionPopup(trigger, popup) {
    var rect = trigger.getBoundingClientRect();
    var gap = 4;
    popup.style.minWidth = Math.max(rect.width, 160) + 'px';
    popup.style.maxWidth = Math.min(440, window.innerWidth - 16) + 'px';
    var popupH = Math.min(popup.scrollHeight || 280, 320);
    var spaceBelow = window.innerHeight - rect.bottom;
    var openBelow = spaceBelow >= popupH + gap || spaceBelow >= rect.top;
    var left = Math.max(8, Math.min(rect.left, window.innerWidth - popup.offsetWidth - 8));
    popup.style.left = left + 'px';
    if (openBelow) {
      popup.style.top = (rect.bottom + gap) + 'px';
      popup.style.bottom = '';
    } else {
      popup.style.bottom = (window.innerHeight - rect.top + gap) + 'px';
      popup.style.top = '';
    }
  }

  function selectOption(select, optionEl) {
    if (!optionEl || optionEl.disabled) return;
    var changed = select.value !== optionEl.value || select.options[select.selectedIndex] !== optionEl;
    // Set the exact option node selected (not just .value) so duplicate values
    // across optgroups resolve to the one the user actually clicked, matching
    // the precedent in _applyModelToDropdown (#6131).
    Array.prototype.forEach.call(select.options, function (o) { o.selected = (o === optionEl); });
    if (changed) select.dispatchEvent(new Event('change', { bubbles: true }));
    syncTriggerLabel(select);
  }

  function openPopup(select, trigger) {
    if (select.disabled) return;
    if (open && open.select === select) { closePopup(); return; }
    closePopup();
    var items = flattenOptions(select);
    var popup = document.createElement('div');
    popup.className = 'themed-select-popup';
    popup.setAttribute('role', 'listbox');
    var optionEls = [];
    var highlightedIndex = -1;
    items.forEach(function (item, idx) {
      if (item.group) {
        var g = document.createElement('div');
        g.className = 'themed-select-group-label';
        g.textContent = item.label;
        popup.appendChild(g);
        return;
      }
      var opt = item.el;
      var row = document.createElement('div');
      row.className = 'themed-select-option' + (opt.selected ? ' selected' : '') + (opt.disabled ? ' disabled' : '');
      row.setAttribute('role', 'option');
      row.setAttribute('aria-selected', opt.selected ? 'true' : 'false');
      row.textContent = opt.textContent;
      if (opt.selected) highlightedIndex = optionEls.length;
      if (!opt.disabled) {
        row.addEventListener('mousedown', function (e) {
          e.preventDefault();
          selectOption(select, opt);
          closePopup();
          trigger.focus();
        });
      }
      popup.appendChild(row);
      optionEls.push({ row: row, el: opt, disabled: !!opt.disabled });
    });
    document.body.appendChild(popup);
    positionPopup(trigger, popup);
    trigger.setAttribute('aria-expanded', 'true');
    trigger.classList.add('themed-select-trigger-open');
    open = { select: select, trigger: trigger, popup: popup, optionEls: optionEls, highlightedIndex: highlightedIndex };
    highlight(highlightedIndex);
    var selectedRow = popup.querySelector('.themed-select-option.selected');
    if (selectedRow && selectedRow.scrollIntoView) selectedRow.scrollIntoView({ block: 'nearest' });
  }

  function highlight(idx) {
    if (!open) return;
    open.optionEls.forEach(function (o, i) { o.row.classList.toggle('highlighted', i === idx); });
    open.highlightedIndex = idx;
  }

  function moveHighlight(dir) {
    if (!open) return;
    var enabled = [];
    open.optionEls.forEach(function (o, i) { if (!o.disabled) enabled.push(i); });
    if (!enabled.length) return;
    var pos = enabled.indexOf(open.highlightedIndex);
    pos = (pos + dir + enabled.length) % enabled.length;
    highlight(enabled[pos]);
    open.optionEls[enabled[pos]].row.scrollIntoView({ block: 'nearest' });
  }

  function syncTriggerLabel(select) {
    var trigger = select.__themedTrigger;
    if (!trigger) return;
    var label = trigger.querySelector('.themed-select-trigger-label');
    if (!label) return;
    var opt = select.options[select.selectedIndex];
    label.textContent = opt ? opt.textContent : '';
    trigger.disabled = select.disabled;
    trigger.classList.toggle('themed-select-trigger-disabled', !!select.disabled);
  }

  function enhance(select) {
    if (!isThemable(select) || select.dataset.themedEnhanced) return;
    select.dataset.themedEnhanced = '1';
    select.classList.add('themed-select-native');
    select.setAttribute('aria-hidden', 'true');
    select.tabIndex = -1;

    var wrap = document.createElement('span');
    wrap.className = 'themed-select-wrap';
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);

    var trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'themed-select-trigger';
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    var ariaLabel = select.getAttribute('aria-label');
    if (ariaLabel) trigger.setAttribute('aria-label', ariaLabel);
    var labelledBy = select.id && document.querySelector('label[for="' + select.id + '"]');
    trigger.innerHTML = '<span class="themed-select-trigger-label"></span>' +
      '<svg class="themed-select-chevron" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>';
    wrap.appendChild(trigger);
    select.__themedTrigger = trigger;
    if (labelledBy) {
      var triggerId = select.id + 'ThemedTrigger';
      trigger.id = triggerId;
      labelledBy.setAttribute('for', triggerId);
    }

    trigger.addEventListener('click', function () {
      if (open && open.select === select) { closePopup(); return; }
      openPopup(select, trigger);
    });
    select.addEventListener('change', function () { syncTriggerLabel(select); });
    syncTriggerLabel(select);
  }

  function enhanceAll(root) {
    (root || document).querySelectorAll('select').forEach(enhance);
  }
  window.enhanceAllThemedSelects = enhanceAll;
  window.enhanceThemedSelect = enhance;
  window.refreshThemedSelect = syncTriggerLabel;

  document.addEventListener('mousedown', function (e) {
    if (open && !open.popup.contains(e.target) && e.target !== open.trigger && !open.trigger.contains(e.target)) {
      closePopup();
    }
  });

  document.addEventListener('keydown', function (e) {
    var active = document.activeElement;
    if (active && active.classList && active.classList.contains('themed-select-trigger')) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        var select = active.previousElementSibling && active.previousElementSibling.tagName === 'SELECT'
          ? active.previousElementSibling
          : active.parentNode.querySelector('select.themed-select-native');
        if (!open || open.trigger !== active) { openPopup(select, active); return; }
      }
    }
    if (!open) return;
    if (e.key === 'Escape') { e.preventDefault(); var t = open.trigger; closePopup(); t.focus(); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); moveHighlight(1); return; }
    if (e.key === 'ArrowUp') { e.preventDefault(); moveHighlight(-1); return; }
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      var found = open.optionEls[open.highlightedIndex];
      var sel = open.select, trig = open.trigger;
      if (found) { selectOption(sel, found.el); }
      closePopup();
      trig.focus();
    } else if (e.key === 'Tab') {
      closePopup();
    }
  });

  window.addEventListener('resize', function () { if (open) positionPopup(open.trigger, open.popup); });
  window.addEventListener('scroll', function (e) {
    if (open && !(open.popup && e.target && open.popup.contains(e.target))) closePopup();
  }, true);

  // Catches both "a new <select> was added anywhere" (e.g. #profileFormModel,
  // rebuilt from scratch every time _renderProfileForm() runs) and "an
  // existing themed select's <option> list was repopulated" (e.g. Kanban's
  // assignee filter, Settings' language/voice lists) — both need the same
  // reaction: enhance new selects, resync the trigger label for changed ones.
  // Rebuilding the popup contents fresh from the live <select> at OPEN time
  // (flattenOptions() above) means the popup itself can never go stale; this
  // observer only needs to keep the closed-state trigger LABEL in sync.
  var mo = new MutationObserver(function (records) {
    records.forEach(function (r) {
      if (r.target && r.target.tagName === 'SELECT' && r.target.dataset.themedEnhanced) {
        syncTriggerLabel(r.target);
      }
      r.addedNodes && r.addedNodes.forEach(function (node) {
        if (!node.querySelectorAll) return;
        if (node.tagName === 'SELECT') enhance(node);
        node.querySelectorAll('select').forEach(enhance);
      });
    });
  });

  function boot() {
    enhanceAll(document);
    mo.observe(document.documentElement, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
