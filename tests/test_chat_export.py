"""Chat export: Markdown/JSON/Text formats for /api/session/export, plus
the UI wiring that surfaces them (Settings toolbar Text button, sidebar
menu Markdown/JSON/Text/HTML actions). See docs/HERMES_STUDIO_PARITY_PLAN.md,
"Priority 3 -- Chat export".
"""
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from tests._pytest_port import BASE

REPO = Path(__file__).resolve().parent.parent


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def get_raw(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return r.read(), r.headers, r.status


def post(path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code


def make_session_tracked(created_list):
    d, _ = post("/api/session/new", {})
    sid = d["session"]["session_id"]
    created_list.append(sid)
    return sid


# ── API: format=md / format=text on the existing export endpoint ──────────
# A freshly created session has no messages yet -- these tests pin the
# format/content-type/filename contract (which doesn't depend on message
# content); render_session_markdown/render_session_text's message-flattening
# logic is covered separately by the unit tests below.

def test_export_markdown_format_returns_correct_content_type(cleanup_test_sessions):
    sid = make_session_tracked(cleanup_test_sessions)
    raw, headers, status = get_raw(f"/api/session/export?session_id={sid}&format=md")
    assert status == 200
    assert "text/markdown" in headers.get("Content-Type", "")
    assert f'filename="hermes-{sid}.md"' in headers.get("Content-Disposition", "")
    text = raw.decode("utf-8")
    assert sid in text


def test_export_text_format_returns_correct_content_type(cleanup_test_sessions):
    sid = make_session_tracked(cleanup_test_sessions)
    raw, headers, status = get_raw(f"/api/session/export?session_id={sid}&format=text")
    assert status == 200
    assert "text/plain" in headers.get("Content-Type", "")
    assert f'filename="hermes-{sid}.txt"' in headers.get("Content-Disposition", "")
    text = raw.decode("utf-8")
    assert sid in text
    # Plain text must not contain Markdown heading syntax.
    assert "## " not in text


def test_export_default_format_is_unchanged_json(cleanup_test_sessions):
    sid = make_session_tracked(cleanup_test_sessions)
    raw, headers, status = get_raw(f"/api/session/export?session_id={sid}")
    assert status == 200
    assert "application/json" in headers.get("Content-Type", "")
    data = json.loads(raw)
    assert data["session_id"] == sid
    assert "messages" in data


def test_export_html_format_still_works(cleanup_test_sessions):
    sid = make_session_tracked(cleanup_test_sessions)
    raw, headers, status = get_raw(f"/api/session/export?session_id={sid}&format=html")
    assert status == 200
    assert "text/html" in headers.get("Content-Type", "")


def test_export_unknown_format_falls_back_to_json(cleanup_test_sessions):
    sid = make_session_tracked(cleanup_test_sessions)
    raw, headers, status = get_raw(f"/api/session/export?session_id={sid}&format=bogus")
    assert status == 200
    assert "application/json" in headers.get("Content-Type", "")


def test_export_requires_session_id():
    try:
        get_raw("/api/session/export?format=md")
        assert False
    except urllib.error.HTTPError as e:
        assert e.code == 400


def test_export_unknown_session_404s():
    try:
        get_raw("/api/session/export?session_id=nosuchsession&format=text")
        assert False
    except urllib.error.HTTPError as e:
        assert e.code == 404


# ── render_session_markdown / render_session_text unit checks ─────────────

def test_render_session_markdown_skips_system_and_flattens_content():
    from api.session_export_text import render_session_markdown

    session = {
        "session_id": "abc123", "title": "Test", "model": "gpt-5", "workspace": "/tmp/ws",
        "messages": [
            {"role": "system", "content": "boilerplate"},
            {"role": "user", "content": "Hello there"},
            {"role": "assistant", "content": [{"type": "text", "text": "Hi!"}]},
        ],
    }
    out = render_session_markdown(session)
    assert "boilerplate" not in out
    assert "## user" in out
    assert "Hello there" in out
    assert "## assistant" in out
    assert "Hi!" in out


def test_render_session_text_has_no_markdown_syntax():
    from api.session_export_text import render_session_text

    session = {
        "session_id": "abc123", "title": "Test",
        "messages": [
            {"role": "system", "content": "boilerplate"},
            {"role": "user", "content": "Hello there"},
        ],
    }
    out = render_session_text(session)
    assert "boilerplate" not in out
    assert "## " not in out
    assert "YOU" in out or "USER" in out.upper()
    assert "Hello there" in out


# ── UI wiring ───────────────────────────────────────────────────────────────

def test_settings_text_export_button_present_and_wired():
    html = read("static/index.html")
    assert 'id="btnExportText"' in html
    js = read("static/boot.js")
    assert "$('btnExportText').onclick" in js
    assert "format=text" in js


def test_sidebar_export_actions_replaces_html_only_helper():
    js = read("static/sessions.js")
    assert "function _appendSessionExportActions(menu, session){" in js
    assert "function _appendSessionExportHtmlAction" not in js
    # Called from both branches of _openSessionActionMenu (read-only + normal).
    assert js.count("_appendSessionExportActions(menu, session);") == 2
    assert "function _sessionExportDownload(session, format, ext){" in js


def test_i18n_keys_present_in_all_15_locales():
    src = read("static/i18n.js")
    required_keys = [
        "export_session_text_tooltip", "export_session_text",
        "session_export_md", "session_export_md_desc",
        "session_export_json_sidebar", "session_export_json_sidebar_desc",
        "session_export_text_sidebar", "session_export_text_sidebar_desc",
    ]
    locale_keys = re.findall(r"^  (?:'([a-zA-Z-]+)'|([a-zA-Z-]+)): \{$", src, re.MULTILINE)
    locales = [a or b for a, b in locale_keys]
    assert locales == [
        "en", "it", "ja", "ru", "es", "de", "zh", "zh-Hant", "pt", "ko",
        "fr", "cs", "tr", "pl", "vi",
    ], locales

    starts = [m.start() for m in re.finditer(r"^  (?:'[a-zA-Z-]+'|[a-zA-Z-]+): \{$", src, re.MULTILINE)]
    starts.append(len(src))
    for i, locale in enumerate(locales):
        block = src[starts[i]:starts[i + 1]]
        for key in required_keys:
            count = len(re.findall(rf"^    {re.escape(key)}: ", block, re.MULTILINE))
            assert count == 1, f"{locale} locale: expected exactly one '{key}', found {count}"
