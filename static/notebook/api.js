/* Notes page: HTTP client for /api/notebook (api/notebook_api.py). */
(function () {
  async function request(path, options) {
    let response;
    try {
      response = await fetch(path, Object.assign({headers: {'Content-Type': 'application/json'}}, options || {}));
    } catch (error) {
      const offline = new Error('Hermes could not be reached');
      offline.offline = true;
      throw offline;
    }
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(payload.error || 'Notes request failed');
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload;
  }
  const post = (path, body) => request(path, {method: 'POST', body: JSON.stringify(body || {})});
  const id = (value) => encodeURIComponent(value);
  window.NotebookApi = {
    bootstrap: () => request('/api/notebook/bootstrap'),
    // side: 'notes' (the main view) or 'vault' (the Obsidian side).
    search: (q, trash, side) => request('/api/notebook/notes?q=' + encodeURIComponent(q || '') + (trash ? '&trash=1' : '') + (side === 'vault' ? '&store=vault&view=vault' : '&view=notes')),
    get: (noteId) => request('/api/notebook/notes/' + id(noteId)),
    create: (body) => post('/api/notebook/notes/create', body),
    update: (noteId, body) => post('/api/notebook/notes/' + id(noteId) + '/update', body),
    trash: (noteId) => post('/api/notebook/notes/' + id(noteId) + '/trash'),
    restore: (noteId) => post('/api/notebook/notes/' + id(noteId) + '/restore'),
    purge: (noteId) => post('/api/notebook/notes/' + id(noteId) + '/purge'),
    duplicate: (noteId) => post('/api/notebook/notes/' + id(noteId) + '/duplicate'),
    emptyTrash: (side) => post('/api/notebook/trash/empty', side === 'vault' ? {store: 'vault', view: 'vault'} : {view: 'notes'}),
    createFolder: (name, side) => post('/api/notebook/folders/create', side === 'vault' ? {name, store: 'vault', view: 'vault'} : {name, view: 'notes'}),
    importFromStore: () => post('/api/notebook/vault/import'),
    renameFolder: (folderId, name) => post('/api/notebook/folders/' + id(folderId) + '/rename', {name}),
    deleteFolder: (folderId) => post('/api/notebook/folders/' + id(folderId) + '/delete'),
    upload: (body) => post('/api/notebook/uploads', body),
    vault: () => request('/api/notebook/vault'),
    setVault: (body) => post('/api/notebook/vault', body),
  };
}());
