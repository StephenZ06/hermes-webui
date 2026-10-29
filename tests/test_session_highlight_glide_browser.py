"""The active conversation's highlight glides to the row picked.

The rows are rebuilt on every render, so the highlight used to jump. Now a
copy of it travels from the row that was active to the one picked (transform
only), the picked row's own fill waits underneath, and both are cleaned up
when it lands.
"""
import pytest

from tests._pytest_port import BASE


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_context(viewport={"width": 1300, "height": 1000}).new_page()
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('chat'); }")
            # A fresh test server has no chats: render three from the sidebar's own cache.
            page.evaluate("""() => { const now = Date.now() / 1000;
                _allSessions = [1, 2, 3].map(i => ({session_id: 'glide' + i, title: 'Glide chat ' + i, message_count: 4,
                    created_at: now - i * 60, updated_at: now - i * 60, last_message_at: now - i * 60, workspace: '', model: ''}));
                // Folders left by other tests would push these rows out of view.
                _allProjects = [];
                S.session = {session_id: 'glide1'};
                renderSessionListFromCache(); }""")
            page.wait_for_selector(".session-item.active[data-sid='glide1']", timeout=15000)
            yield page
        finally:
            browser.close()


def test_the_highlight_travels_from_the_old_row_to_the_new_one(page):
    out = page.evaluate("""async () => {
        const from = document.querySelector(".session-item[data-sid='glide1']").getBoundingClientRect().top;
        S.session = {session_id: 'glide3'};
        renderSessionListFromCache();
        const glide = document.querySelector('.sidebar-highlight-glide');
        const row = document.querySelector(".session-item.active[data-sid='glide3']");
        const to = row.getBoundingClientRect().top;
        const anim = glide && glide.getAnimations()[0];
        const first = anim && anim.effect.getKeyframes()[0].transform;
        const arriving = row.classList.contains('is-highlight-arriving');
        const rowFill = getComputedStyle(row).backgroundColor;
        await new Promise(r => setTimeout(r, 900));
        return {from, to, glide: !!glide, first, arriving, rowFill,
                leftover: document.querySelectorAll('.sidebar-highlight-glide, .is-highlight-arriving').length};
    }""")
    assert out["glide"], out
    # It starts where the old row was: above, so a negative offset.
    assert out["from"] < out["to"] and out["first"].startswith("translateY(-"), out
    assert out["arriving"] and out["rowFill"] == "rgba(0, 0, 0, 0)", out
    assert out["leftover"] == 0, out


def test_a_render_that_keeps_the_same_conversation_does_not_glide(page):
    count = page.evaluate("""() => { renderSessionListFromCache();
        return document.querySelectorAll('.sidebar-highlight-glide').length; }""")
    assert count == 0


def test_inside_a_project_folder_the_copy_has_no_accent_bar(page):
    """Rows in a project folder show no accent bar, so the travelling copy draws none."""
    # Zeus 2.0 is the skin that gives active rows an accent bar.
    out = page.evaluate("""() => {
        document.documentElement.dataset.skin = 'zeus-2';
        document.documentElement.classList.add('dark');
        _allProjects = [{project_id: 'p1', name: 'Glide folder', workspace_path: '/workspace/glide'}];
        _allSessions.forEach(s => { s.project_id = 'p1'; });
        S.session = {session_id: 'glide1'};
        renderSessionListFromCache();
        const folder = document.querySelector('.project-folder-sessions');
        S.session = {session_id: 'glide2'};
        renderSessionListFromCache();
        const glide = document.querySelector('.sidebar-highlight-glide');
        const row = document.querySelector(".session-item.active[data-sid='glide2']");
        return {inFolder: !!(row && row.closest('.project-folder-sessions')), folder: !!folder, glide: !!glide,
                bars: glide ? glide.querySelectorAll('i').length : -1};
    }""")
    if not out["inFolder"]:
        pytest.skip(f"the folder does not list its chats open in this state: {out}")
    assert out["glide"] and out["bars"] == 0, out


def test_between_a_project_folder_and_conversations_it_fades_in_place(page):
    """No journey across sections: the new highlight fades in where it is."""
    out = page.evaluate("""() => {
        _allProjects = [{project_id: 'p1', name: 'Glide folder', workspace_path: '/workspace/glide'}];
        _allSessions[0].project_id = 'p1';
        S.session = {session_id: 'glide1'};
        renderSessionListFromCache();
        const startedInFolder = !!document.querySelector(".project-folder-sessions .session-item.active[data-sid='glide1']");
        S.session = {session_id: 'glide3'};
        renderSessionListFromCache();
        const row = document.querySelector(".session-item.active[data-sid='glide3']");
        return {startedInFolder, inFolder: !!row.closest('.project-folder-sessions'),
                glides: document.querySelectorAll('.sidebar-highlight-glide').length,
                fades: row.getAnimations().length};
    }""")
    if not out["startedInFolder"]:
        pytest.skip(f"the folder does not list its chats open in this state: {out}")
    assert not out["inFolder"] and out["glides"] == 0 and out["fades"] >= 1, out


def test_the_text_eases_to_the_active_inset_instead_of_jumping(page):
    out = page.evaluate("""() => {
        document.documentElement.dataset.skin = 'zeus-2';
        document.documentElement.classList.add('dark');
        S.session = {session_id: 'glide1'};
        renderSessionListFromCache();
        S.session = {session_id: 'glide2'};
        renderSessionListFromCache();
        const row = document.querySelector(".session-item.active[data-sid='glide2']");
        const old = document.querySelector(".session-item[data-sid='glide1']");
        const insets = el => el.getAnimations({subtree: true}).map(a => a.effect.getKeyframes().map(k => k.transform).filter(t => t && t.startsWith('translateX'))).filter(k => k.length);
        return {row: insets(row), old: insets(old)};
    }""")
    assert out["row"] and out["row"][0][0] != out["row"][0][-1], out
    assert out["old"] and out["old"][0][0] != out["old"][0][-1], out
