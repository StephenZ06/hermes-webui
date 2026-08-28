"""Coverage for the project workspace binder that replaced the path-input popover.

The Project three-dot menu's "Workspace Folder" item no longer opens a popover
with a bare text field; it opens a project-scoped view inside the right
workspace panel that lists registered Spaces and browses directories live.

Two things are worth pinning down:

1. ``GET /api/workspaces/suggest`` grew a ``limit`` parameter. The composer's
   path autocomplete still wants the old short list, so the default must not
   move, and an oversized request must be clamped rather than dumping a huge
   directory into the panel.
2. The front-end wiring is plain static assets with no bundler, so the usual
   repo convention applies: assert the ids/functions/classes the three files
   agree on actually exist, since a rename in one of them is otherwise silent.
"""
import io
import json
import pathlib
from urllib.parse import urlparse

import api.routes as routes


REPO_ROOT = pathlib.Path(__file__).parent.parent
INDEX_HTML = (REPO_ROOT / "static" / "index.html").read_text(encoding="utf-8")
WORKSPACE_JS = (REPO_ROOT / "static" / "workspace.js").read_text(encoding="utf-8")
SESSIONS_JS = (REPO_ROOT / "static" / "sessions.js").read_text(encoding="utf-8")
BOOT_JS = (REPO_ROOT / "static" / "boot.js").read_text(encoding="utf-8")
STYLE_CSS = (REPO_ROOT / "static" / "style.css").read_text(encoding="utf-8")


class _FakeHandler:
    def __init__(self):
        self.status = None
        self.sent_headers = []
        self.body = bytearray()
        self.wfile = self
        self.rfile = io.BytesIO(b"")
        self.headers = {}
        self.request = None
        self.client_address = ("127.0.0.1", 0)

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.sent_headers.append((name, value))

    def end_headers(self):
        pass

    def write(self, data):
        self.body.extend(data)

    def json_body(self):
        return json.loads(bytes(self.body).decode("utf-8"))


def _get_suggest(query: str, monkeypatch):
    seen = {}

    def _fake(prefix, limit=12):
        seen["prefix"] = prefix
        seen["limit"] = limit
        return ["/home/u/one", "/home/u/two"]

    monkeypatch.setattr(routes, "list_workspace_suggestions", _fake)
    handler = _FakeHandler()
    routes.handle_get(handler, urlparse("http://example.com/api/workspaces/suggest" + query))
    return handler, seen


class TestSuggestLimitParam:
    def test_default_limit_unchanged_for_autocomplete(self, monkeypatch):
        handler, seen = _get_suggest("?prefix=/home/u/", monkeypatch)
        assert handler.status == 200
        assert seen["limit"] == 12
        assert seen["prefix"] == "/home/u/"

    def test_limit_is_honoured(self, monkeypatch):
        handler, seen = _get_suggest("?prefix=/home/u/&limit=200", monkeypatch)
        assert handler.status == 200
        assert seen["limit"] == 200
        assert handler.json_body()["limit"] == 200

    def test_limit_is_clamped_to_ceiling(self, monkeypatch):
        _handler, seen = _get_suggest("?prefix=/home/u/&limit=100000", monkeypatch)
        assert seen["limit"] == 500

    def test_limit_below_one_is_raised_to_one(self, monkeypatch):
        _handler, seen = _get_suggest("?prefix=/home/u/&limit=0", monkeypatch)
        assert seen["limit"] == 1

    def test_non_numeric_limit_falls_back_to_default(self, monkeypatch):
        _handler, seen = _get_suggest("?prefix=/home/u/&limit=lots", monkeypatch)
        assert seen["limit"] == 12

    def test_suggestions_still_returned(self, monkeypatch):
        handler, _seen = _get_suggest("?prefix=/home/u/&limit=50", monkeypatch)
        assert handler.json_body()["suggestions"] == ["/home/u/one", "/home/u/two"]


class TestBinderMarkup:
    def test_panel_view_exists_in_rightpanel(self):
        assert 'id="projectBindView"' in INDEX_HTML
        for element_id in (
            "projectBindTitle",
            "projectBindCurrent",
            "projectBindSearch",
            "projectBindBody",
            "projectBindFooter",
        ):
            assert f'id="{element_id}"' in INDEX_HTML, element_id

    def test_head_buttons_call_exported_handlers(self):
        assert 'onclick="closeProjectWorkspaceBinder()"' in INDEX_HTML
        assert 'onclick="refreshProjectWorkspaceBinder()"' in INDEX_HTML
        assert 'onclick="clearProjectBindSearch()"' in INDEX_HTML


class TestBinderWiring:
    def test_workspace_js_defines_the_handlers_the_markup_calls(self):
        for fn in (
            "function openProjectWorkspaceBinder",
            "function closeProjectWorkspaceBinder",
            "function refreshProjectWorkspaceBinder",
            "function clearProjectBindSearch",
        ):
            assert fn in WORKSPACE_JS, fn

    def test_listings_are_fetched_fresh_not_from_the_cached_list(self):
        # loadWorkspaceList() caches into _workspaceList for the composer
        # dropdown; the binder must not read that cache or a folder created
        # after boot would be missing.
        assert "api('/api/workspaces')" in WORKSPACE_JS
        assert "/api/workspaces/suggest?limit=200&prefix=" in WORKSPACE_JS
        binder = WORKSPACE_JS[WORKSPACE_JS.index("function openProjectWorkspaceBinder"):]
        assert "loadWorkspaceList" not in binder

    def test_menu_item_delegates_to_the_binder(self):
        picker = SESSIONS_JS[SESSIONS_JS.index("async function _showProjectWorkspacePicker"):]
        picker = picker[: picker.index("\nasync function _confirmDeleteProject")]
        assert "openProjectWorkspaceBinder(proj)" in picker
        # The old inline path field is gone.
        assert "/absolute/path/to/folder" not in SESSIONS_JS

    def test_binder_exits_when_panel_closes_or_a_preview_opens(self):
        assert BOOT_JS.count("closeProjectWorkspaceBinder") >= 2

    def test_binding_posts_to_the_existing_endpoint(self):
        assert "/api/projects/set_workspace" in WORKSPACE_JS


class TestBinderStyles:
    def test_mode_class_hides_the_file_browser_chrome(self):
        assert ".rightpanel.project-bind-mode .file-tree" in STYLE_CSS
        assert ".rightpanel.project-bind-mode .preview-area" in STYLE_CSS

    def test_touch_targets_and_no_ios_zoom_on_the_search_field(self):
        mobile = STYLE_CSS[STYLE_CSS.index(".project-bind{"):]
        mobile = mobile[: mobile.index("/* Add-Space Local/Remote segmented toggle. */")]
        assert "@media (hover:none)" in mobile
        assert "@media (max-width:640px)" in mobile
        assert "font-size:16px" in mobile

    def test_back_button_retraces_visited_folders(self):
        # ".." is not a back button: after jumping to a crumb or drilling in
        # from a Space, the parent is usually not where you came from.
        assert "function projectBindGoBack" in WORKSPACE_JS
        assert "_projectBindHistory.push" in WORKSPACE_JS
        assert "data-bind-back" in WORKSPACE_JS

    def test_going_back_does_not_record_history(self):
        # Otherwise Back would toggle between the same two folders forever.
        nav = WORKSPACE_JS[WORKSPACE_JS.index("async function _projectBindOpenDir"):]
        nav = nav[: nav.index("async function _bindProjectWorkspacePath")]
        assert "opts && opts.replay" in nav
        back = WORKSPACE_JS[WORKSPACE_JS.index("function projectBindGoBack"):]
        assert "{replay: true}" in back[: back.index("\n}")]

    def test_history_is_cleared_between_projects(self):
        opener = WORKSPACE_JS[WORKSPACE_JS.index("async function openProjectWorkspaceBinder"):]
        assert "_projectBindHistory = []" in opener[: opener.index("await refreshProjectWorkspaceBinder")]

    def test_every_space_row_carries_a_status_dot(self):
        assert "function _projectBindIsOnline" in WORKSPACE_JS
        assert "ws-conn-dot ws-conn-dot-${online ? 'online' : 'offline'}" in WORKSPACE_JS
        # The dot sits immediately before the name text.
        assert "${dot}${_escHtml(w.name" in WORKSPACE_JS

    def test_online_state_falls_back_to_mount_status(self):
        fn = WORKSPACE_JS[WORKSPACE_JS.index("function _projectBindIsOnline"):]
        fn = fn[: fn.index("\n}")]
        assert "w.availability === 'online'" in fn
        assert "w.mount_status === 'connected'" in fn

    def test_binder_is_reachable_in_the_tablet_band(self):
        # 641-900px hides the docked right panel (.rightpanel{display:none}) in
        # favour of the main-view file browser, but the binder only exists in
        # the right panel, so it must opt back in as a slide-over there.
        assert ".rightpanel.project-bind-mode{display:flex!important;position:fixed;" in STYLE_CSS
        assert ".rightpanel.project-bind-mode.mobile-open{transform:translate3d(0,0,0)" in STYLE_CSS

    def test_status_dot_colours_are_defined(self):
        assert ".ws-conn-dot-online{background:var(--success)" in STYLE_CSS
        assert ".ws-conn-dot-offline{background:var(--error)" in STYLE_CSS

    def test_back_button_has_a_touch_sized_target(self):
        mobile = STYLE_CSS[STYLE_CSS.index("@media (max-width:640px){\n  .project-bind-head"):]
        mobile = mobile[: mobile.index("\n}")]
        assert ".project-bind-back-btn" in mobile

    def test_row_markup_reuses_the_spaces_panel_classes(self):
        assert "ws-row project-bind-row" in WORKSPACE_JS
        assert "ws-search-input" in INDEX_HTML


# ── Behavioural checks on the binder's pure path helpers ─────────────────────
#
# static/workspace.js is far too entangled with the DOM to load whole under
# node, but the path maths that decides what the breadcrumb offers is pure and
# is the part most likely to break quietly (walking above a trusted root just
# returns an empty listing from the server, with no error to notice).

import shutil
import subprocess
import textwrap

import pytest

NODE = shutil.which("node")

_PURE_HELPERS = (
    "_projectBindStripSlash",
    "_projectBindParent",
    "_projectBindLeaf",
    "_projectBindIsPathQuery",
    "_projectBindCrumbs",
)


def _extract_helper(name: str) -> str:
    start = WORKSPACE_JS.index(f"function {name}(")
    depth = 0
    for i in range(start, len(WORKSPACE_JS)):
        ch = WORKSPACE_JS[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return WORKSPACE_JS[start:i + 1]
    raise AssertionError(f"unbalanced braces extracting {name}")


def _run_helpers(expression: str, roots):
    source = "\n".join(_extract_helper(name) for name in _PURE_HELPERS)
    script = textwrap.dedent(
        """
        const vm = require('vm');
        const ctx = {{ console, _projectBindRoots: {roots} }};
        vm.createContext(ctx);
        vm.runInContext({source}, ctx);
        process.stdout.write(JSON.stringify(vm.runInContext({expr}, ctx)));
        """
    ).format(roots=json.dumps(roots), source=json.dumps(source), expr=json.dumps(expression))
    proc = subprocess.run([NODE, "-e", script], check=True, capture_output=True, text=True)
    return json.loads(proc.stdout)


@pytest.mark.skipif(NODE is None, reason="node not on PATH")
class TestBinderPathHelpers:
    def test_leaf_and_parent_of_a_nested_path(self):
        assert _run_helpers("_projectBindLeaf('/home/u/Apps/webui')", []) == "webui"
        assert _run_helpers("_projectBindParent('/home/u/Apps/webui')", []) == "/home/u/Apps"

    def test_trailing_slashes_are_ignored(self):
        assert _run_helpers("_projectBindStripSlash('/home/u/Apps///')", []) == "/home/u/Apps"
        assert _run_helpers("_projectBindLeaf('/home/u/Apps/')", []) == "Apps"

    def test_parent_of_a_top_level_directory_is_root(self):
        assert _run_helpers("_projectBindParent('/home')", []) == "/"

    def test_path_queries_are_detected(self):
        assert _run_helpers("_projectBindIsPathQuery('/home/u')", []) is True
        assert _run_helpers("_projectBindIsPathQuery('~/Apps')", []) is True
        assert _run_helpers("_projectBindIsPathQuery('webui')", []) is False
        assert _run_helpers("_projectBindIsPathQuery('')", []) is False

    def test_crumbs_start_at_the_containing_trusted_root(self):
        crumbs = _run_helpers(
            "_projectBindCrumbs('/home/u/Apps/webui')", ["/home/u", "/data/shared"]
        )
        assert [c["label"] for c in crumbs] == ["u", "Apps", "webui"]
        assert [c["path"] for c in crumbs] == [
            "/home/u",
            "/home/u/Apps",
            "/home/u/Apps/webui",
        ]

    def test_crumbs_pick_the_longest_matching_root(self):
        crumbs = _run_helpers(
            "_projectBindCrumbs('/home/u/Apps/webui')", ["/home/u", "/home/u/Apps"]
        )
        assert [c["path"] for c in crumbs] == ["/home/u/Apps", "/home/u/Apps/webui"]

    def test_crumbs_never_walk_above_a_trusted_root(self):
        crumbs = _run_helpers("_projectBindCrumbs('/home/u')", ["/home/u"])
        assert [c["path"] for c in crumbs] == ["/home/u"]

    def test_path_outside_every_root_yields_a_single_uncrossable_crumb(self):
        crumbs = _run_helpers("_projectBindCrumbs('/etc/ssh')", ["/home/u"])
        assert crumbs == [{"label": "ssh", "path": "/etc/ssh"}]

    def test_empty_directory_has_no_crumbs(self):
        assert _run_helpers("_projectBindCrumbs('')", ["/home/u"]) == []


class TestProjectFolderBindingIndicator:
    """The workspace panel must say which folder the chat's Project is bound to.

    The panel already had a "Project" row, but that one is the WORKSPACES.yaml
    *registry* binding (session.bound_project_key). A chat filed under a
    sidebar Project with a bound workspace folder still read "Unbound" there,
    because that row answers a different question entirely.
    """

    def test_indicator_markup_exists_and_is_separate_from_the_registry_row(self):
        assert 'id="projectFolderBindingRow"' in INDEX_HTML
        assert 'id="projectFolderBindingPath"' in INDEX_HTML
        # Both rows coexist; the new one must not replace the registry select.
        assert 'id="boundProjectSelect"' in INDEX_HTML
        assert INDEX_HTML.index('id="boundProjectRow"') < INDEX_HTML.index('id="projectFolderBindingRow"')

    def test_indicator_reads_the_sidebar_project_binding(self):
        fn = WORKSPACE_JS[WORKSPACE_JS.index("async function renderProjectFolderBinding"):]
        fn = fn[: fn.index("\nasync function useProjectFolderWorkspace")]
        assert "session.project_id" in fn
        assert "proj.workspace_path" in fn
        # bound_project_key belongs to the other row and must not leak in here.
        assert "bound_project_key" not in fn

    def test_indicator_flags_a_chat_not_using_the_bound_folder(self):
        # Binding applies to chats created afterwards; an older chat keeps its
        # own workspace, and claiming "bound to X" while the agent works in Y
        # is the exact confusion this row exists to remove.
        fn = WORKSPACE_JS[WORKSPACE_JS.index("async function renderProjectFolderBinding"):]
        fn = fn[: fn.index("\nasync function useProjectFolderWorkspace")]
        assert "mismatch" in fn
        assert "session.workspace" in fn

    def test_mismatch_offers_a_one_tap_switch(self):
        assert "function useProjectFolderWorkspace" in WORKSPACE_JS
        assert 'onclick="useProjectFolderWorkspace()"' in INDEX_HTML
        fn = WORKSPACE_JS[WORKSPACE_JS.index("async function useProjectFolderWorkspace"):]
        assert "switchToWorkspace" in fn

    def test_indicator_is_rendered_with_the_workspace_root(self):
        assert "renderProjectFolderBinding()" in WORKSPACE_JS
        root_render = WORKSPACE_JS[WORKSPACE_JS.index("if(!path||path==='.'){ _refreshGitBadge();"):]
        assert "renderProjectFolderBinding" in root_render[:400]

    def test_project_list_falls_back_to_the_api(self):
        # The panel can render before the sidebar has populated _allProjects.
        fn = WORKSPACE_JS[WORKSPACE_JS.index("async function _projectFolderList"):]
        fn = fn[: fn.index("\nasync function renderProjectFolderBinding")]
        assert "typeof _allProjects !== 'undefined'" in fn
        assert "api('/api/projects')" in fn

    def test_binder_takes_over_the_panel_without_the_indicator(self):
        assert ".rightpanel.project-bind-mode .project-folder-binding" in STYLE_CSS
