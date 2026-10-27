"""Test: session batch select mode functions exist in sessions.js (#568)"""
import re


def test_batch_select_state_variables():
    """Verify batch select state variables are declared."""
    with open('static/sessions.js', encoding="utf-8") as f:
        src = f.read()
    assert '_sessionSelectMode' in src, "Missing _sessionSelectMode variable"
    assert '_selectedSessions' in src, "Missing _selectedSessions variable"
    assert 'new Set()' in src, "Selected sessions should use Set"


def test_batch_select_functions_exist():
    """Verify all batch select functions are defined."""
    with open('static/sessions.js', encoding="utf-8") as f:
        src = f.read()
    required_funcs = [
        'toggleSessionSelectMode',
        'exitSessionSelectMode',
        'toggleSessionSelect',
        'selectAllSessions',
        'deselectAllSessions',
        '_updateBatchActionBar',
        '_deleteSelectedSessions',
    ]
    for fn in required_funcs:
        assert f'function {fn}(' in src, f"Missing function: {fn}"


def test_batch_select_checkbox_rendering():
    """Verify checkbox is rendered when in select mode."""
    with open('static/sessions.js', encoding="utf-8") as f:
        src = f.read()
    assert 'session-select-cb' in src, "Missing session-select-cb class"
    assert 'session-select-cb-wrapper' in src, "Missing session-select-cb-wrapper class"
    assert "cb.type='checkbox'" in src, "Checkbox should be type checkbox"


def test_batch_select_intercepts_navigation():
    """Verify select mode intercepts session navigation."""
    with open('static/sessions.js', encoding="utf-8") as f:
        src = f.read()
    assert "_sessionSelectMode" in src
    # Should have early return when in select mode
    assert 'toggleSessionSelect(s.session_id)' in src, \
        "Pointerup handler should call toggleSessionSelect in select mode"


def test_batch_checkbox_sets_selection_without_row_double_toggle():
    """Clicking the checkbox itself must not also trigger row-level toggling."""
    with open('static/sessions.js', encoding="utf-8") as f:
        src = f.read()
    assert 'function setSessionSelected(sid, selected)' in src, \
        "Checkbox changes should set explicit state instead of toggling blindly"
    assert 'cb.onchange=(e)=>{e.stopPropagation();setSessionSelected(s.session_id,cb.checked);};' in src, \
        "Checkbox change must use its checked state"
    assert 'cb.onpointerup=(e)=>{e.stopPropagation();};' in src, \
        "Checkbox pointerup must not bubble to the row pointerup handler"
    assert 'cbWrapper.onpointerup=(e)=>{e.stopPropagation();};' in src, \
        "Checkbox wrapper pointerup must not bubble to the row pointerup handler"


def test_batch_select_escape_handler():
    """Verify Escape key exits select mode."""
    with open('static/sessions.js', encoding="utf-8") as f:
        src = f.read()
    assert "e.key==='Escape'&&_sessionSelectMode" in src, \
        "Should have Escape key handler for select mode"


def test_batch_delete_lives_in_the_filter_overlay():
    """Select mode has one action, Delete, in the filter strip; no separate action card."""
    with open('static/sessions.js', encoding="utf-8") as f:
        src = f.read()
    assert "deleteBtn.className='batch-delete-btn'" in src
    assert "deleteBtn.onclick=(e)=>{e.stopPropagation();_deleteSelectedSessions();};" in src
    assert "deleteBtn.disabled=n===0" in src, "Delete must be inert with nothing selected"
    assert "t('session_selected_count',n)" in src, \
        "Selected count must pass the selected session count to i18n"
    assert "t('session_batch_delete_confirm',ids.length)" in src, \
        "Batch delete confirmation must pass selected session count to i18n"
    for gone in ('batchActionBar', 'batch-action-bar', 'batch-select-all-btn', '_showBatchProjectPicker'):
        assert gone not in src, f"{gone} should be gone with the action card"


def test_streaming_zero_message_sessions_stay_visible_after_reload():
    """In-flight sessions may have zero saved messages during reload recovery."""
    with open('static/sessions.js', encoding="utf-8") as f:
        src = f.read()
    assert "_isSessionEffectivelyStreaming(s)" in src, \
        "Streaming sessions must bypass the zero-message sidebar filter"
    assert "!!s.active_stream_id" in src, \
        "Sessions with persisted active stream IDs must remain visible after reload"
    assert "!!s.pending_user_message" in src, \
        "Sessions with pending user turns must remain visible after reload"


def test_boot_does_not_drop_zero_message_inflight_session():
    """Reloading /session/<id> during a running turn must keep the session open."""
    with open('static/boot.js', encoding="utf-8") as f:
        src = f.read()
    assert "const _restoredInFlight = S.session && (" in src, \
        "Boot must detect restored in-flight sessions before ephemeral cleanup"
    assert "S.session.active_stream_id" in src, \
        "Boot must treat active stream IDs as real sessions"
    assert "S.session.pending_user_message" in src, \
        "Boot must treat pending user messages as real sessions"
    assert "&& !_restoredInFlight" in src, \
        "Zero-message cleanup must not run for in-flight sessions"


def test_batch_select_i18n_keys():
    """Verify all batch select i18n keys exist in all locales."""
    with open('static/i18n.js', encoding="utf-8") as f:
        src = f.read()
    required_keys = [
        'session_select_mode',
        'session_select_mode_desc',
        'session_select_all',
        'session_deselect_all',
        'session_selected_count',
        'session_batch_archive',
        'session_batch_delete',
        'session_batch_move',
        'session_batch_delete_confirm',
        'session_batch_archive_confirm',
        'session_no_selection',
    ]
    locales = ['en', 'ru', 'es', 'de', 'zh', 'zh-Hant', 'ko']
    for key in required_keys:
        for locale in locales:
            # Check if the key exists in the locale block
            if locale == 'zh-Hant':
                pattern = rf"'{locale}'\s*:.*?{key}"
            else:
                pattern = rf"{locale}\s*:.*?{key}"
            # Simpler check: just verify the key string with colon exists
            assert f"{key}:" in src, f"Missing i18n key '{key}' in i18n.js"
    # Count occurrences - each key should appear in all 7 locales
    for key in required_keys:
        count = src.count(f"{key}:")
        assert count >= 8, f"Key '{key}' found {count} times, expected >= 8 (one per locale) (one per locale)"


def test_i18n_string_placeholder_interpolation_supported():
    """String-valued translations with {0} placeholders should interpolate args."""
    with open('static/i18n.js', encoding="utf-8") as f:
        src = f.read()
    assert "String(val).replace(/\\{(\\d+)\\}/g" in src, \
        "t() must interpolate {0}-style placeholders for string-valued translations"
    assert "Object.prototype.hasOwnProperty.call(args, idx)" in src, \
        "t() must preserve unknown placeholders instead of replacing with undefined"


def test_batch_select_css_exists():
    """Verify batch select CSS classes are defined."""
    with open('static/style.css', encoding="utf-8") as f:
        src = f.read()
    required_classes = [
        'session-select-overlay',
        'batch-exit-btn',
        'batch-delete-btn',
        'session-select-cb-wrapper',
        'session-select-cb',
        'session-item.selected',
    ]
    for cls in required_classes:
        assert cls in src, f"Missing CSS class: .{cls}"


def test_batch_select_mode_flags():
    """Verify select mode properly toggles state."""
    with open('static/sessions.js', encoding="utf-8") as f:
        src = f.read()
    # toggleSessionSelectMode should flip the flag
    assert '_sessionSelectMode=!_sessionSelectMode' in src, \
        "toggleSessionSelectMode should flip _sessionSelectMode"
    # exitSessionSelectMode should clear state
    assert '_sessionSelectMode=false' in src, \
        "exitSessionSelectMode should set _sessionSelectMode=false"
    assert '_selectedSessions.clear()' in src, \
        "Exit should clear selected sessions"


def test_batch_delete_uses_confirm_dialog():
    """Verify batch delete shows confirmation dialog."""
    with open('static/sessions.js', encoding="utf-8") as f:
        src = f.read()
    # The delete handler should call showConfirmDialog with batch message
    assert "session_batch_delete_confirm" in src, \
        "Batch delete should use session_batch_delete_confirm i18n key"
    assert "showConfirmDialog" in src, \
        "Should use showConfirmDialog for batch operations"
