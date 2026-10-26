"""Focused contract checks for the Notes page interaction seams.

These keep the Notes implementation from regressing into duplicated navigation
or silently expanding a full note into the chat composer.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = (ROOT / "static" / "notebook" / "index.js").read_text(encoding="utf-8")
MESSAGES = (ROOT / "static" / "messages.js").read_text(encoding="utf-8")
STYLE = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


def test_project_and_folder_scopes_can_collapse_the_duplicate_middle_list():
    assert "function shouldShowMiddleList()" in NOTEBOOK
    assert "scope.kind !== 'project' && scope.kind !== 'folder'" in NOTEBOOK
    assert "nb-list-collapsed" in NOTEBOOK


def test_send_note_to_chat_uses_a_linked_context_card_not_composer_text():
    assert "window._addNamedContextBlock" in NOTEBOOK
    assert "kind: 'note'" in NOTEBOOK
    assert "noteId: note.id" in NOTEBOOK
    assert "function _addNamedContextBlock(text)" in MESSAGES
    assert "const options=arguments[1]||{}" in MESSAGES
    assert "window._addNamedContextBlock=_addNamedContextBlock" in MESSAGES
    assert "note-context-card" in MESSAGES


def test_note_media_has_a_load_state_and_a_completion_animation():
    assert "function installMediaLoadStates(host)" in NOTEBOOK
    assert "new MutationObserver" in NOTEBOOK
    assert "nb-media-loading" in NOTEBOOK
    assert "nb-media-ready" in NOTEBOOK
    assert ".nb-media-loading" in STYLE
    assert ".nb-media-ready" in STYLE


def test_note_list_cards_have_consistent_rest_and_hover_states():
    assert ".nb-item{display:flex" in STYLE
    assert "min-height:88px" in STYLE
    assert "gap:12px;padding:8px 12px 16px" in STYLE
    assert "background:var(--surface-subtle,var(--surface))" in STYLE
    assert ".nb-item:hover{background:color-mix" in STYLE
    assert ".nb-list-items{flex:1" in STYLE


def test_note_metadata_controls_keep_the_requested_larger_visual_size():
    assert "icon('folder', 16)" in NOTEBOOK
    assert ".nb-tag-input,.nb-tag-input::placeholder{font-size:14px;}" in STYLE
    assert "font-size:13px !important" in STYLE


def test_notes_initial_navigation_uses_one_central_loading_screen_not_shimmer_placeholders():
    assert "let bootstrapPromise = null;" in NOTEBOOK
    assert "function syncInitialLoadingState()" in NOTEBOOK
    assert "nb-page-loader" in NOTEBOOK
    assert "const bootstrap = loadBootstrap();" in NOTEBOOK
    assert "await loadBootstrap();" in NOTEBOOK
    assert "nb-side-loading" not in NOTEBOOK
    assert "nb-skeleton" not in NOTEBOOK
    assert ".nb-side-loading" not in STYLE
    assert ".nb-skeleton" not in STYLE


def test_note_switch_keeps_editor_chrome_static_and_only_animates_the_body():
    assert "head.classList.add('is-entering')" not in NOTEBOOK
    assert "SkeletonEntrance.reveal(host.parentElement" in NOTEBOOK
    assert '[data-skel-hide="reveal"]' in STYLE
    assert ".nb-editor-head.is-entering" not in STYLE


def test_linked_note_context_has_no_duplicate_hover_preview_and_balanced_header_inset():
    assert ".composer-selection-chips{display:flex" in STYLE
    assert "padding:10px 0 12px" in STYLE
    assert ".note-context-card .selection-context-body" in STYLE
    assert "padding:10px 12px 10px 0" in STYLE
    assert "selection-context-preview" not in MESSAGES
    assert "quote.title=String(s.text||'');" not in MESSAGES
    assert ".note-context-card .selection-context-preview" not in STYLE
    assert "overflow:hidden;" in STYLE
