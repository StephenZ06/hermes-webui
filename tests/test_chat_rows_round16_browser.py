"""Chat side panel: a conversation row is as tall as a project folder row."""

import pytest

from tests.test_chat_optical_alignment_browser import browser, pytestmark, real_2x  # noqa: F401

SEED = """() => { const now = Date.now() / 1000;
  _allProjects = [{project_id: 'p1', name: 'Triple S', workspace_path: '/workspace/triple-s'}];
  _allSessions = [1, 2, 3].map(i => ({session_id: 'row' + i, title: 'Row chat ' + i, message_count: 4, project_id: i === 1 ? 'p1' : null,
    created_at: now - i * 60, updated_at: now - i * 60, last_message_at: now - i * 60, workspace: '', model: ''}));
  renderSessionListFromCache(); }"""


@pytest.mark.parametrize("skin", ["zeus-2", "graphite"])
def test_conversation_rows_match_the_project_folder_height(real_2x, skin):
    page = real_2x
    page.evaluate("async () => { await switchPanel('chat'); }")
    page.evaluate("skin => { document.documentElement.dataset.skin = skin; }", skin)
    page.evaluate(SEED)
    page.wait_for_timeout(500)
    out = page.evaluate("""() => { const h = e => e.getBoundingClientRect().height;
      const folder = document.querySelector('#sessionList .project-folder-row');
      const rows = [...document.querySelectorAll('#sessionList .session-item')].filter(r => !r.closest('.project-folder-sessions'));
      rows[rows.length - 1].classList.add('active');
      const title = r => { const t = r.querySelector('.session-title').getBoundingClientRect(), b = r.getBoundingClientRect(); return Math.round((t.top + t.bottom - b.top - b.bottom) * 10) / 20; };
      return {folder: h(folder), rows: rows.map(h), centred: rows.map(title)}; }""")
    assert out["rows"] == [out["folder"]] * 2 and out["folder"] == 34, out
    assert all(abs(c) <= .5 for c in out["centred"]), out
