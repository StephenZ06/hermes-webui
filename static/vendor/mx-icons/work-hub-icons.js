/* Curated Linear paths from mx-icons (MIT). See LICENSE in this directory. */
(function () {
  const paths = {
    work: '<path d="M9 4h6l1 2h3a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h3l1-2Z"/><path d="M8 13h8M12 9v8"/>',
    jobs: '<path d="M4 5h16v15H4z"/><path d="M8 5V3h8v2M8 10h8M8 14h5"/>',
    inbox: '<path d="M4 4h16v12H4z"/><path d="M4 13h5l1 2h4l1-2h5"/>',
    folder: '<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
    board: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 4v16"/>',
    list: '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6h.01M4 12h.01M4 18h.01"/>',
    search: '<circle cx="11" cy="11" r="6"/><path d="m20 20-4-4"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    check: '<path d="m5 12 4.2 4.2L19 6.5"/>',
    sparkles: '<path d="m12 3-1.5 5.5L5 10l5.5 1.5L12 17l1.5-5.5L19 10l-5.5-1.5L12 3Z"/><path d="m19 15-.7 2.3L16 18l2.3.7L19 21l.7-2.3L22 18l-2.3-.7L19 15Z"/>',
    save: '<path d="M5 3h11l3 3v15H5Z"/><path d="M8 3v6h8V3M8 21v-7h8v7"/>',
    loader: '<path d="M20 12a8 8 0 1 1-2.34-5.66"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.2 2.2-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56v.1h-3.12v-.1a1.7 1.7 0 0 0-1.03-1.56 1.7 1.7 0 0 0-1.88.34l-.06.06-2.2-2.2.06-.06A1.7 1.7 0 0 0 6.74 15a1.7 1.7 0 0 0-1.56-1.03h-.1v-3.12h.1A1.7 1.7 0 0 0 6.74 9.8a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.2-2.2.06.06a1.7 1.7 0 0 0 1.88.34 1.7 1.7 0 0 0 1.03-1.56v-.1h3.12v.1a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.2 2.2-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.56 1.03h.1v3.12h-.1A1.7 1.7 0 0 0 19.4 15Z"/>',
    filter: '<path d="M4 5h16l-6.3 7.1v5.4l-3.4 1.8v-7.2Z"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
  };
  window.WorkHubIcons = function (name, label) {
    const title = label ? `<title>${label}</title>` : '';
    return `<svg class="work-hub-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="${label ? 'false' : 'true'}">${title}${paths[name] || paths.work}</svg>`;
  };
}());
