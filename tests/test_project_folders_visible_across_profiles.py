"""Regression test: project folders show on every profile; chats stay scoped.

Before this, the sidebar's project fetch (`_loadSidebarSessionListPayload` in
static/sessions.js) only requested the aggregate `?all_profiles=1` project
list when the (separate) `_showAllProfiles` toggle was on -- otherwise it
requested the DEFAULT, profile-filtered `/api/projects` response
(api/routes.py: `scoped = [p for p in all_projects if
_profiles_match(p.get("profile"), active_profile)]`). So a project created
while on profile "default" was invisible on profile "coding", even though
projects.json is a single shared file (STATE_DIR/projects.json, not
per-profile) and the row only carries a `profile` tag for
attribution/admin purposes.

Fix: the project fetch always requests the aggregate list
(`/api/projects?all_profiles=1`), independent of `_showAllProfiles`. The
session list itself (`/api/sessions`) is UNCHANGED -- still profile-scoped
by default, still gated by `_showAllProfiles` -- so a project folder appears
everywhere, but only the sessions actually created under the active profile
render inside it (the existing project-folder renderer already shows a real,
empty folder when a project has zero matching sessions for the active
profile -- see agent-canvas.js / sessions.js's project-folder-list block).
"""
import pathlib

REPO = pathlib.Path(__file__).parent.parent
SESSIONS_JS = (REPO / "static" / "sessions.js").read_text(encoding="utf-8")


def test_project_fetch_always_requests_all_profiles():
    fn_start = SESSIONS_JS.find("async function _loadSidebarSessionListPayload(")
    assert fn_start != -1, "_loadSidebarSessionListPayload() not found"
    project_promise_start = SESSIONS_JS.find("const projectPromise", fn_start)
    assert project_promise_start != -1
    block_end = SESSIONS_JS.find("})();", project_promise_start)
    block = SESSIONS_JS[project_promise_start:block_end]
    assert "api('/api/projects?all_profiles=1'" in block, (
        "project fetch must always request the aggregate (all-profiles) list, "
        "unconditionally -- project folders are not gated by _showAllProfiles"
    )
    assert "_showAllProfiles ? '?all_profiles=1' : ''" not in block, (
        "project fetch must NOT be conditional on _showAllProfiles -- that "
        "toggle controls session (chat) visibility only, not folder visibility"
    )


def test_session_fetch_is_unchanged_still_profile_scoped_by_toggle():
    # Sanity: make sure the fix didn't accidentally also make the SESSION
    # list ignore the active profile -- only the project list should have
    # changed. Sessions must remain gated by the existing toggle.
    assert "if(_showAllProfiles) qs.set('all_profiles','1');" in SESSIONS_JS
