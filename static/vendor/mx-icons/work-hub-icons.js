/* Curated Linear paths from mx-icons (MIT). See LICENSE in this directory. */
(function () {
  const paths = {
    work: '<path d="M9 4h6l1 2h3a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h3l1-2Z"/><path d="M8 13h8M12 9v8"/>',
    inbox: '<path d="M4 4h16v12H4z"/><path d="M4 13h5l1 2h4l1-2h5"/>',
    folder: '<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
    board: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 4v16"/>',
    list: '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6h.01M4 12h.01M4 18h.01"/>',
    search: '<circle cx="11" cy="11" r="6"/><path d="m20 20-4-4"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
  };
  window.WorkHubIcons = function (name, label) {
    const title = label ? `<title>${label}</title>` : '';
    return `<svg class="work-hub-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="${label ? 'false' : 'true'}">${title}${paths[name] || paths.work}</svg>`;
  };
}());
