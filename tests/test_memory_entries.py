"""Patterns / memory vault cleaner (Priority 1) wiring + safety guards.

MEMORY.md is a flat `§`-delimited entry format (confirmed against real
profile data, not assumed — see docs/HERMES_STUDIO_PARITY_PLAN.md, Patterns
/ memory vault cleaner section). This adds per-entry delete/append on top of
the existing whole-file view/edit, scoped to the 'memory' section only.

The critical invariant under test: GET /api/memory redacts secret-shaped
text before sending it to the client (real profiles have plaintext
credentials in MEMORY.md). Entry delete/append must never round-trip that
redacted text back into a write, or a real secret gets permanently replaced
with "[REDACTED]" on disk. Delete addresses entries by server-side index
into the RAW file; append only ever sends fresh user-typed text.
"""
from pathlib import Path
import re

REPO = Path(__file__).resolve().parent.parent


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def test_routes_wired():
    routes = read("api/routes.py")
    assert '"/api/memory/entry/delete"' in routes
    assert '"/api/memory/entry/append"' in routes
    assert "def _handle_memory_entry_delete(handler, body):" in routes
    assert "def _handle_memory_entry_append(handler, body):" in routes


def test_delete_never_touches_client_supplied_content():
    """The whole point of the split: delete must never take file content
    from the request body — only an index. Taking content from the client
    would mean taking the redacted display text and writing it back."""
    routes = read("api/routes.py")
    idx = routes.index("def _handle_memory_entry_delete(handler, body):")
    end = routes.index("\ndef ", idx + 10)
    block = routes[idx:end]
    assert 'require(body, "section", "index")' in block
    assert '"content"' not in block
    assert "target.read_text(" in block  # reads the RAW file itself


def test_append_takes_fresh_content_not_a_reconstructed_file():
    routes = read("api/routes.py")
    idx = routes.index("def _handle_memory_entry_append(handler, body):")
    end = routes.index("\ndef ", idx + 10)
    block = routes[idx:end]
    assert 'require(body, "section", "content")' in block
    assert "entries.append(text)" in block  # appends to existing raw entries, doesn't replace them


def test_entry_endpoints_scoped_to_memory_section_only():
    routes = read("api/routes.py")
    assert 'if section != "memory":' in routes
    idx = routes.index('if section != "memory":')
    assert 'section must be "memory"' in routes[idx: idx + 200]


def test_split_join_roundtrip_matches_real_delimiter_format():
    """Real MEMORY.md files use `\\n§\\n` between entries with no leading/
    trailing delimiter (verified against live profile data, not assumed)."""
    routes = read("api/routes.py")
    assert re.search(r'_MEMORY_ENTRY_DELIM_RE = re\.compile\(r"\\n§\\n"\)', routes)
    assert 'def _split_memory_entries(content: str) -> list[str]:' in routes
    assert 'def _join_memory_entries(entries: list[str]) -> str:' in routes
    assert '"\\n§\\n".join(entries)' in routes


def test_symlink_guard_present_on_entry_target_resolution():
    routes = read("api/routes.py")
    idx = routes.index("def _resolve_memory_entry_target(handler, section: str):")
    end = routes.index("\ndef ", idx + 10)
    block = routes[idx:end]
    assert "target.is_symlink()" in block


def test_frontend_wiring():
    js = read("static/panels.js")
    assert "function _renderMemoryEntriesView()" in js
    assert "function _parseMemoryEntriesForDisplay(content)" in js
    assert "async function deleteMemoryEntry(index)" in js
    assert "async function submitMemoryEntryForm()" in js
    assert "/api/memory/entry/delete" in js
    assert "/api/memory/entry/append" in js
    # 'memory' section renders via the entries view, not the generic
    # whole-file renderer other sections still use.
    assert "if (section === 'memory') {\n    _renderMemoryEntriesView();" in js
    # The existing raw-edit path must stay reachable — the entries view is
    # additive, not a replacement.
    assert "onclick=\"editCurrentMemory()\"" in js


def test_corrections_tab_does_not_auto_revert_when_empty():
    """Regression: an earlier version reset _currentMemoryEntryTab back to
    'patterns' on every render whenever there were zero corrections — which
    fired on the render caused by the user's OWN tab click, silently undoing
    the switch. Real data has zero CORRECTION-prefixed entries today, so
    this made the tab permanently unreachable. Caught via a live Playwright
    check (switchMemoryEntryTab('corrections') then reading
    _currentMemoryEntryTab back), not just static analysis."""
    js = read("static/panels.js")
    assert "!corrections.length) _currentMemoryEntryTab = 'patterns'" not in js


def test_correction_prefix_detection_matches_backend_and_frontend():
    js = read("static/panels.js")
    routes = read("api/routes.py")
    assert "/^CORRECTION:/i.test(text)" in js
    assert 'text.upper().startswith("CORRECTION:")' in routes


def test_i18n_keys_present_in_all_15_locales():
    src = read("static/i18n.js")
    required_keys = [
        "memory_entries_patterns", "memory_entries_corrections",
        "memory_entries_no_patterns", "memory_entries_no_corrections",
        "memory_entries_add_placeholder", "memory_entries_mark_correction",
        "memory_entries_add", "memory_entries_edit_raw",
        "memory_entries_delete_confirm", "memory_entries_deleted",
        "memory_entries_added",
    ]
    locale_keys = re.findall(r"^  (?:'([a-zA-Z-]+)'|([a-zA-Z-]+)): \{$", src, re.MULTILINE)
    locales = [a or b for a, b in locale_keys]
    assert len(locales) == 15, locales

    starts = [m.start() for m in re.finditer(r"^  (?:'[a-zA-Z-]+'|[a-zA-Z-]+): \{$", src, re.MULTILINE)]
    starts.append(len(src))
    for name, start, end in zip(locales, starts, starts[1:]):
        block = src[start:end]
        missing = [k for k in required_keys if f"{k}:" not in block]
        assert not missing, f"locale {name!r} missing keys: {missing}"


def test_css_uses_theme_tokens():
    css = read("static/style.css")
    assert ".memory-entry-card" in css
    idx = css.index(".memory-entry-tabs{")
    block = css[idx: idx + 1800]
    assert "var(--border)" in block
    assert "var(--accent)" in block
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", block)
