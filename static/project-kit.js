/* Skills & Tools of one project: the project menu's centred modal.

   Lists what GET /api/projects/toolkit reports for the project (wizard picks,
   skills in the project folder, packages, MCP servers), with a search box, a
   kind filter and a sort. "Add skill" swaps the list for the profile's
   installed skills; ticking some and confirming posts them to
   /api/projects/toolkit/skills, which also takes a skill off the project.
   Loaded on first use (page-modules.js: "projectkit"). */
(function () {
  'use strict';

  var ICON = {
    skill: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M8 1.75 9.6 5.1l3.65.5-2.65 2.55.65 3.6L8 10.05 4.75 11.75l.65-3.6L2.75 5.6l3.65-.5z"/></svg>',
    component: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="5" height="5" rx="1.2"/><rect x="9" y="2" width="5" height="5" rx="1.2"/><rect x="2" y="9" width="5" height="5" rx="1.2"/><rect x="9" y="9" width="5" height="5" rx="2.5"/></svg>',
    package: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M8 1.75 13.5 4.6v6.8L8 14.25 2.5 11.4V4.6z"/><path d="M2.5 4.6 8 7.5l5.5-2.9M8 7.5v6.75"/></svg>',
    icons: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="5" cy="5" r="2.25"/><path d="M11 2.75 13.25 7h-4.5z"/><rect x="2.75" y="9.25" width="4.5" height="4" rx="1"/><path d="m9.5 9.5 3.5 3.5M13 9.5l-3.5 3.5"/></svg>',
    mcp: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2.5v3M10 2.5v3M4.5 5.5h7v2.25a3.5 3.5 0 0 1-7 0z"/><path d="M8 11.25v2.25"/></svg>',
    search: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="7" cy="7" r="4.25"/><path d="m10.25 10.25 3.25 3.25"/></svg>',
    close: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M4 4l8 8M12 4l-8 8"/></svg>',
    plus: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M8 3.5v9M3.5 8h9"/></svg>',
    back: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9.75 3.5 5.25 8l4.5 4.5"/></svg>',
    check: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m3.75 8.25 2.75 2.75 5.75-6"/></svg>',
    folder: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"><path d="M2 4.25c0-.7.55-1.25 1.25-1.25h3l1.5 1.5h5c.7 0 1.25.55 1.25 1.25v5.5c0 .7-.55 1.25-1.25 1.25h-9.5C2.55 12.5 2 11.95 2 11.25z"/></svg>'
  };
  var KINDS = [
    { key: 'all', label: 'All' },
    { key: 'skill', label: 'Skills' },
    { key: 'component', label: 'Components' },
    { key: 'package', label: 'Packages' },
    { key: 'icons', label: 'Icons' },
    { key: 'mcp', label: 'MCP' }
  ];
  var SOURCE = { wizard: 'Wizard', added: 'Added', folder: 'In folder' };
  var NEW_FOR = 7 * 86400;

  var st = null; // the open modal's state

  function h(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function now() { return Date.now() / 1000; }
  function ago(ts) {
    if (!ts) return '';
    var s = Math.max(0, now() - ts);
    if (s < 60) return 'just now';
    if (s < 3600) return Math.floor(s / 60) + 'm ago';
    if (s < 86400) return Math.floor(s / 3600) + 'h ago';
    if (s < 30 * 86400) return Math.floor(s / 86400) + 'd ago';
    return new Date(ts * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: s > 330 * 86400 ? 'numeric' : undefined });
  }
  // The folder's last two parts, so the project's own name stays readable.
  function shortPath(path) {
    var parts = String(path).split(/[\\/]+/).filter(Boolean);
    return parts.length > 3 ? '…/' + parts.slice(-2).join('/') : path;
  }
  function reduced() { try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (_) { return false; } }
  function req(path, opts) { return window.api(path, opts); }

  function build(proj) {
    var overlay = document.createElement('div');
    overlay.className = 'pkit-overlay';
    overlay.innerHTML =
      '<div class="pkit" role="dialog" aria-modal="true" aria-labelledby="pkitTitle">' +
        '<header class="pkit-head">' +
          '<div class="pkit-heading">' +
            '<h2 class="pkit-title" id="pkitTitle">Skills &amp; Tools</h2>' +
            '<p class="pkit-sub"><span class="pkit-dot"></span><span class="pkit-proj"></span><span class="pkit-path"></span></p>' +
          '</div>' +
          '<button type="button" class="pkit-icon-btn pkit-close" aria-label="Close">' + ICON.close + '</button>' +
        '</header>' +
        '<div class="pkit-stage">' +
          '<section class="pkit-view pkit-list-view" aria-label="Project skills and tools">' +
            '<div class="pkit-tools">' +
              '<label class="pkit-search">' + ICON.search +
                '<input type="search" class="pkit-q" placeholder="Search skills and tools" aria-label="Search skills and tools" autocomplete="off" spellcheck="false">' +
                '<kbd class="pkit-kbd">/</kbd>' +
              '</label>' +
              '<select class="pkit-sort" aria-label="Sort">' +
                '<option value="recent">Recently added</option>' +
                '<option value="name">Name A to Z</option>' +
                '<option value="kind">Kind</option>' +
              '</select>' +
              '<button type="button" class="pkit-add">' + ICON.plus + '<span>Add skill</span></button>' +
            '</div>' +
            '<div class="pkit-filters" role="tablist" aria-label="Filter by kind"></div>' +
            '<div class="pkit-body"><ul class="pkit-rows" role="list"></ul><div class="pkit-empty" hidden></div></div>' +
          '</section>' +
          '<section class="pkit-view pkit-add-view" aria-label="Add skills" hidden>' +
            '<div class="pkit-tools">' +
              '<button type="button" class="pkit-icon-btn pkit-back" aria-label="Back to the list">' + ICON.back + '</button>' +
              '<label class="pkit-search">' + ICON.search +
                '<input type="search" class="pkit-aq" placeholder="Search installed skills" aria-label="Search installed skills" autocomplete="off" spellcheck="false">' +
              '</label>' +
              '<select class="pkit-cat-filter" aria-label="Category"><option value="">All categories</option></select>' +
            '</div>' +
            '<div class="pkit-body"><ul class="pkit-rows pkit-add-rows" role="list"></ul><div class="pkit-empty pkit-add-empty" hidden></div></div>' +
            '<footer class="pkit-foot"><span class="pkit-picked">Tick the skills to add</span>' +
              '<button type="button" class="pkit-confirm" disabled>Add to project</button></footer>' +
          '</section>' +
        '</div>' +
      '</div>';
    var $ = function (sel) { return overlay.querySelector(sel); };
    $('.pkit-dot').style.background = proj.color || 'var(--muted)';
    $('.pkit-proj').textContent = proj.name || 'Project';
    return { overlay: overlay, $: $ };
  }

  function counts(items) {
    var c = { all: items.length };
    items.forEach(function (i) { c[i.kind] = (c[i.kind] || 0) + 1; });
    return c;
  }

  function renderFilters() {
    var c = counts(st.items);
    var bar = st.$('.pkit-filters');
    bar.innerHTML = KINDS.filter(function (k) { return k.key === 'all' || c[k.key]; }).map(function (k) {
      var on = st.kind === k.key;
      return '<button type="button" role="tab" class="pkit-chip' + (on ? ' is-on' : '') + '" aria-selected="' + on + '" data-kind="' + k.key + '">' +
        h(k.label) + '<span class="pkit-count">' + (c[k.key] || 0) + '</span></button>';
    }).join('');
    if (st.kind !== 'all' && !c[st.kind]) st.kind = 'all';
  }

  function visible() {
    var q = st.q.trim().toLowerCase();
    var rows = st.items.filter(function (i) {
      if (st.kind !== 'all' && i.kind !== st.kind) return false;
      if (!q) return true;
      return (i.name + ' ' + (i.description || '') + ' ' + (i.where || '') + ' ' + (i.category || '')).toLowerCase().indexOf(q) >= 0;
    });
    var order = { skill: 0, component: 1, icons: 2, mcp: 3, package: 4 };
    rows.sort(function (a, b) {
      if (st.sort === 'name') return a.name.localeCompare(b.name);
      if (st.sort === 'kind') return (order[a.kind] - order[b.kind]) || a.name.localeCompare(b.name);
      return (b.added_at || 0) - (a.added_at || 0) || a.name.localeCompare(b.name);
    });
    return rows;
  }

  function rowHtml(i, idx) {
    // "New": added this week, after the project's first skills and tools
    // (a fresh project does not mark everything new).
    var fresh = i.added_at && now() - i.added_at < NEW_FOR && i.added_at - st.oldest > 3600;
    var meta = [SOURCE[i.source] || 'In folder', i.where].filter(Boolean);
    return '<li class="pkit-row" data-kind="' + i.kind + '" style="--i:' + Math.min(idx, 12) + '">' +
      '<span class="pkit-kind pkit-kind-' + i.kind + '" aria-hidden="true">' + (ICON[i.kind] || ICON.package) + '</span>' +
      '<span class="pkit-main">' +
        '<span class="pkit-name">' + h(i.name) + (fresh ? '<span class="pkit-new">New</span>' : '') +
          (i.missing ? '<span class="pkit-warn">Not installed</span>' : '') + '</span>' +
        (i.description ? '<span class="pkit-desc">' + h(i.description) + '</span>' : '') +
        '<span class="pkit-meta">' + meta.map(h).join('<span class="pkit-sep" aria-hidden="true">·</span>') + '</span>' +
      '</span>' +
      '<span class="pkit-when">' + h(ago(i.added_at)) + '</span>' +
      (i.removable
        ? '<button type="button" class="pkit-icon-btn pkit-remove" data-name="' + h(i.name) + '" aria-label="Take ' + h(i.name) + ' off the project">' + ICON.close + '</button>'
        : '<span class="pkit-remove-slot" aria-hidden="true"></span>') +
      '</li>';
  }

  function renderList(animate) {
    var rows = visible();
    var ul = st.$('.pkit-rows');
    ul.innerHTML = rows.map(rowHtml).join('');
    ul.classList.toggle('pkit-enter', !!animate && !reduced());
    var empty = st.$('.pkit-empty');
    empty.hidden = rows.length > 0;
    if (!rows.length) {
      if (!st.folder) {
        empty.innerHTML = '<span class="pkit-empty-icon">' + ICON.folder + '</span>' +
          '<strong>No workspace folder yet</strong><span>Skills and tools live in the project folder. Set one to see them here.</span>' +
          '<button type="button" class="pkit-ghost pkit-set-folder">Set workspace folder</button>';
      } else if (st.items.length) {
        empty.innerHTML = '<strong>Nothing matches “' + h(st.q.trim()) + '”</strong><span>Try another word, or show every kind.</span>' +
          '<button type="button" class="pkit-ghost pkit-clear">Clear search</button>';
      } else {
        empty.innerHTML = '<span class="pkit-empty-icon">' + ICON.skill + '</span>' +
          '<strong>No skills or tools yet</strong><span>Add an installed skill, or ask an agent in this project to install one from a repo. It shows up here.</span>';
      }
    }
    st.$('.pkit-add').disabled = !st.folder;
  }

  function renderAdd() {
    var q = st.aq.trim().toLowerCase();
    var cat = st.cat || '';
    var rows = st.addable.filter(function (s) {
      return (!cat || (s.category || '') === cat) && (!q || (s.name + ' ' + s.description + ' ' + s.category).toLowerCase().indexOf(q) >= 0);
    });
    st.$('.pkit-add-rows').innerHTML = rows.map(function (s, idx) {
      var on = st.picked.has(s.name);
      return '<li class="pkit-row pkit-pick' + (on ? ' is-on' : '') + '" style="--i:' + Math.min(idx, 12) + '">' +
        '<button type="button" class="pkit-pick-btn" role="checkbox" aria-checked="' + on + '" data-name="' + h(s.name) + '">' +
          '<span class="pkit-box" aria-hidden="true">' + ICON.check + '</span>' +
          '<span class="pkit-main"><span class="pkit-name">' + h(s.name) + '</span>' +
            (s.description ? '<span class="pkit-desc">' + h(s.description) + '</span>' : '') + '</span>' +
          (s.category ? '<span class="pkit-cat">' + h(s.category) + '</span>' : '') +
        '</button></li>';
    }).join('');
    var empty = st.$('.pkit-add-empty');
    empty.hidden = rows.length > 0;
    empty.innerHTML = !st.addable.length ? '<strong>Every installed skill is already on this project</strong>'
      : cat && !q ? '<strong>No installed skill left in ' + h(cat) + '</strong>' : '<strong>No installed skill matches</strong>';
    var n = st.picked.size;
    st.$('.pkit-picked').textContent = n ? n + (n === 1 ? ' skill' : ' skills') + ' picked' : 'Tick the skills to add';
    var btn = st.$('.pkit-confirm');
    btn.disabled = !n || st.busy;
    btn.textContent = n ? 'Add ' + n + ' to project' : 'Add to project';
  }

  // The category picker lists the categories of the skills that can still be
  // added, with how many each holds; a category that empties falls back to all.
  function fillCategories() {
    var sel = st.$('.pkit-cat-filter');
    var counts = {};
    st.addable.forEach(function (s) { if (s.category) counts[s.category] = (counts[s.category] || 0) + 1; });
    var names = Object.keys(counts).sort(function (a, b) { return a.localeCompare(b); });
    if (st.cat && !counts[st.cat]) st.cat = '';
    sel.innerHTML = '<option value="">All categories</option>' + names.map(function (n) {
      return '<option value="' + h(n) + '">' + h(n) + ' · ' + counts[n] + '</option>';
    }).join('');
    sel.value = st.cat || '';
    sel.disabled = !names.length;
    if (window.refreshThemedSelect) window.refreshThemedSelect(sel);
  }

  function apply(data) {
    st.items = data.items || [];
    st.addable = data.addable || [];
    st.folder = data.folder || null;
    st.oldest = st.items.reduce(function (m, i) { return i.added_at && i.added_at < m ? i.added_at : m; }, Infinity);
    st.$('.pkit-path').textContent = st.folder ? shortPath(st.folder) : 'No workspace folder';
    fillCategories();
    renderFilters();
    renderList(true);
  }

  function load() {
    st.$('.pkit-rows').innerHTML = [0, 1, 2, 3].map(function () { return '<li class="pkit-row pkit-skel" aria-hidden="true"><span class="pkit-kind"></span><span class="pkit-main"><span class="pkit-bar"></span><span class="pkit-bar short"></span></span></li>'; }).join('');
    return req('/api/projects/toolkit?project_id=' + encodeURIComponent(st.proj.project_id)).then(function (data) {
      if (st) apply(data);
    }).catch(function (e) {
      if (!st) return;
      st.$('.pkit-rows').innerHTML = '';
      var empty = st.$('.pkit-empty');
      empty.hidden = false;
      empty.innerHTML = '<strong>Could not load this project’s skills and tools</strong><span>' + h(e && e.message || e) + '</span>' +
        '<button type="button" class="pkit-ghost pkit-retry">Try again</button>';
    });
  }

  function swap(toAdd) {
    var from = st.$(toAdd ? '.pkit-list-view' : '.pkit-add-view');
    var to = st.$(toAdd ? '.pkit-add-view' : '.pkit-list-view');
    st.view = toAdd ? 'add' : 'list';
    from.hidden = true;
    to.hidden = false;
    to.classList.remove('pkit-in-left', 'pkit-in-right');
    if (!reduced()) { void to.offsetWidth; to.classList.add(toAdd ? 'pkit-in-right' : 'pkit-in-left'); }
    if (toAdd) { st.picked = new Set(); st.aq = ''; st.$('.pkit-aq').value = ''; st.cat = ''; fillCategories(); renderAdd(); st.$('.pkit-aq').focus(); }
    else st.$('.pkit-q').focus();
  }

  function save(add, remove) {
    st.busy = true;
    renderAdd();
    return req('/api/projects/toolkit/skills', { method: 'POST', body: JSON.stringify({ project_id: st.proj.project_id, add: add, remove: remove }) })
      .then(function (data) {
        if (!st) return;
        st.busy = false;
        apply(data);
        if (add.length) { swap(false); window.showToast && window.showToast(add.length === 1 ? add[0] + ' added to the project' : add.length + ' skills added to the project'); }
        else if (remove.length) window.showToast && window.showToast(remove[0] + ' taken off the project');
      })
      .catch(function (e) {
        if (!st) return;
        st.busy = false;
        renderAdd();
        window.showToast && window.showToast('Could not update skills: ' + (e && e.message || e), 6000, 'error');
      });
  }

  function trapTab(e) {
    var nodes = Array.prototype.filter.call(st.overlay.querySelectorAll('button,input,select,[tabindex]'), function (n) {
      return !n.disabled && n.offsetParent !== null && n.tabIndex >= 0;
    });
    if (!nodes.length) return;
    var first = nodes[0], last = nodes[nodes.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  function close() {
    if (!st) return;
    var s = st;
    st = null;
    document.removeEventListener('keydown', s.onKey, true);
    s.overlay.classList.add('is-closing');
    var done = function () { if (s.overlay.parentNode) s.overlay.remove(); };
    if (reduced()) done(); else { s.overlay.addEventListener('animationend', function (e) { if (e.target === s.overlay) done(); }); setTimeout(done, 260); }
    if (s.lastFocus && s.lastFocus.isConnected) try { s.lastFocus.focus(); } catch (_) {}
  }

  function open(proj) {
    if (st) close();
    var b = build(proj);
    st = { proj: proj, overlay: b.overlay, $: b.$, items: [], addable: [], folder: null, kind: 'all', sort: 'recent',
           q: '', aq: '', cat: '', view: 'list', picked: new Set(), busy: false, lastFocus: document.activeElement };
    var s = st;
    s.onKey = function (e) {
      if (st !== s) return;
      if (e.key === 'Escape') {
        e.preventDefault(); e.stopPropagation();
        if (s.view === 'add') swap(false); else close();
      } else if (e.key === 'Tab') trapTab(e);
      else if (e.key === '/' && s.view === 'list' && !/^(INPUT|SELECT|TEXTAREA)$/.test((document.activeElement || {}).tagName || '')) {
        e.preventDefault(); s.$('.pkit-q').focus();
      }
    };
    document.addEventListener('keydown', s.onKey, true);
    b.overlay.addEventListener('mousedown', function (e) { if (e.target === b.overlay) close(); });
    b.$('.pkit-close').onclick = close;
    b.$('.pkit-q').addEventListener('input', function (e) { s.q = e.target.value; renderList(false); });
    b.$('.pkit-aq').addEventListener('input', function (e) { s.aq = e.target.value; renderAdd(); });
    b.$('.pkit-cat-filter').addEventListener('change', function (e) { s.cat = e.target.value; renderAdd(); });
    b.$('.pkit-sort').addEventListener('change', function (e) { s.sort = e.target.value; renderList(true); });
    b.$('.pkit-add').onclick = function () { swap(true); };
    b.$('.pkit-back').onclick = function () { swap(false); };
    b.$('.pkit-confirm').onclick = function () { if (s.picked.size && !s.busy) save(Array.from(s.picked), []); };
    b.$('.pkit-filters').addEventListener('click', function (e) {
      var chip = e.target.closest('.pkit-chip');
      if (!chip) return;
      s.kind = chip.dataset.kind;
      renderFilters();
      renderList(true);
    });
    b.$('.pkit-add-rows').addEventListener('click', function (e) {
      var btn = e.target.closest('.pkit-pick-btn');
      if (!btn) return;
      var name = btn.dataset.name;
      if (s.picked.has(name)) s.picked.delete(name); else s.picked.add(name);
      var on = s.picked.has(name);
      btn.setAttribute('aria-checked', String(on));
      btn.parentNode.classList.toggle('is-on', on);
      renderAdd();
      var again = s.$('.pkit-pick-btn[data-name="' + CSS.escape(name) + '"]');
      if (again) again.focus();
    });
    b.$('.pkit-list-view').addEventListener('click', function (e) {
      var rm = e.target.closest('.pkit-remove');
      if (rm) {
        var row = rm.closest('.pkit-row');
        var name = rm.dataset.name;
        if (row && !reduced()) row.classList.add('is-leaving');
        setTimeout(function () { if (st === s) save([], [name]); }, reduced() ? 0 : 160);
        return;
      }
      if (e.target.closest('.pkit-clear')) { s.q = ''; s.kind = 'all'; s.$('.pkit-q').value = ''; renderFilters(); renderList(true); s.$('.pkit-q').focus(); }
      else if (e.target.closest('.pkit-retry')) load();
      else if (e.target.closest('.pkit-set-folder')) {
        close();
        if (typeof window.openProjectWorkspaceBinder === 'function') window.openProjectWorkspaceBinder(proj);
      }
    });
    document.body.appendChild(b.overlay);
    setTimeout(function () { if (st === s) s.$('.pkit-q').focus(); }, 0);
    return load();
  }

  window.openProjectKit = open;
  window.closeProjectKit = close;
})();
