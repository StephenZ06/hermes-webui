"""Opening a chat or a skill shows a skeleton of its text, then cross-fades in.

While the transcript (or the skill's document) is on its way, placeholder
lines stand where its text will be; once the content is written in, the
skeleton fades out as the content fades in. The view never sits blank behind
a spinner, and nothing is left hidden once the load is done.
"""

import pytest

from tests._pytest_port import BASE

FRAMES_JS = """(sel) => {
  window.__frames = [];
  const tick = () => {
    const skel = document.querySelector(sel.host + ' > .skel');
    const hidden = document.querySelector(sel.content);
    window.__frames.push({skel: !!skel, reveal: (document.querySelector(sel.host) || {}).dataset?.skel === 'reveal',
      opacity: hidden ? Number(getComputedStyle(hidden).opacity) : null,
      text: (document.querySelector(sel.content) || {}).innerText || ''});
    if (window.__frames.length < 150) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}"""


def _open(page, panel):
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate(f"async () => {{ await switchPanel('{panel}'); }}")


def _slow(page, pattern):
    # Each matching request takes 300 ms, as over a phone or a VPN.
    page.evaluate("""(pattern) => { const f = window.fetch, re = new RegExp(pattern);
      window.fetch = (u, o) => re.test(String(u)) ? new Promise((r) => setTimeout(r, 300)).then(() => f(u, o)) : f(u, o); }""", pattern)


def _assert_skeleton_then_fade(frames, final_text):
    assert any(f["skel"] for f in frames), "no skeleton while loading"
    shown = [f for f in frames if final_text in f["text"]]
    assert shown, "the content never arrived"
    assert any(f["reveal"] and 0 < f["opacity"] < 1 for f in shown), "the content cut in instead of fading"
    first_skel = next(i for i, f in enumerate(frames) if f["skel"])
    blank = [f for f in frames[first_skel:] if not f["skel"] and final_text not in f["text"]]
    assert not blank, "the view showed blank between the skeleton and the content"


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            tab = browser.new_page(viewport={"width": 1280, "height": 860})
            errors = []
            tab.on("pageerror", lambda e: errors.append(str(e)))
            yield tab
            assert not errors, errors
        finally:
            browser.close()


def test_opening_a_chat_fades_its_transcript_in_from_a_skeleton(page):
    _open(page, "chat")
    sids = page.evaluate("""async () => {
      const make = async (title, text) => {
        const r = await fetch('/api/session/import', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({title, messages: [{role: 'user', content: 'question for ' + title},
                                                  {role: 'assistant', content: text}]})});
        return (await r.json()).session.session_id;
      };
      return [await make('Skel one', 'first transcript reply'), await make('Skel two', 'second transcript reply')];
    }""")
    page.evaluate("(sid) => loadSession(sid)", sids[0])
    page.wait_for_function("() => (document.getElementById('msgInner').innerText || '').includes('first transcript reply')", timeout=15000)
    _slow(page, r"/api/session\?")
    page.evaluate(FRAMES_JS, {"host": "#messages", "content": "#msgInner"})
    page.evaluate("(sid) => { loadSession(sid); }", sids[1])
    page.wait_for_function("() => window.__frames.length >= 150", timeout=20000)
    frames = page.evaluate("() => window.__frames")
    _assert_skeleton_then_fade(frames, "second transcript reply")
    final = page.evaluate("""() => ({skel: !!document.querySelector('#messages > .skel'),
      hidden: document.querySelectorAll('[data-skel-hide]').length, opacity: Number(getComputedStyle(document.getElementById('msgInner')).opacity)})""")
    assert final == {"skel": False, "hidden": 0, "opacity": 1}


def test_a_chat_that_fails_to_load_does_not_stay_hidden(page):
    _open(page, "chat")
    page.evaluate("""() => { const f = window.fetch;
      window.fetch = (u, o) => /\\/api\\/session\\?/.test(String(u)) ? Promise.reject(new Error('offline')) : f(u, o); }""")
    page.evaluate("() => { loadSession('does-not-exist-' + Date.now()).catch(() => {}); }")
    page.wait_for_function("() => !document.querySelector('#messages > .skel')", timeout=15000)
    assert page.evaluate("() => document.querySelectorAll('[data-skel-hide]').length") == 0


def test_opening_a_skill_fades_its_document_in_from_a_skeleton(page):
    _open(page, "skills")
    page.wait_for_selector(".skill-item", timeout=15000)
    items = page.query_selector_all(".skill-item")
    if len(items) < 2:
        pytest.skip("the test server has fewer than two skills")
    items[0].click()
    page.wait_for_function("() => document.querySelector('#skillDetailBody .skill-detail-content')", timeout=15000)
    _slow(page, r"/api/skills/content")
    page.evaluate(FRAMES_JS, {"host": "#mainSkills", "content": "#skillDetailBody"})
    first_title = page.evaluate(TITLE_JS, "skillDetailTitle")["text"]
    second = page.query_selector_all(".skill-item")[1]
    second.click()
    page.wait_for_selector("#mainSkills > .skel", timeout=5000)
    loading = page.evaluate(TITLE_JS, "skillDetailTitle")
    assert loading["opacity"] == 0 and loading["header"], (first_title, loading)
    title, body = page.evaluate(TOGETHER_JS, ["skillDetailTitle", "skillDetailBody"])
    assert abs(title - body) < 0.05, (title, body)
    page.wait_for_function("() => window.__frames.length >= 150", timeout=20000)
    assert page.evaluate(TITLE_JS, "skillDetailTitle")["opacity"] == 1
    frames = page.evaluate("() => window.__frames")
    title = page.evaluate("() => document.getElementById('skillDetailBody').innerText.trim().split('\\n').pop()")
    _assert_skeleton_then_fade(frames, title)
    assert page.evaluate("() => document.querySelectorAll('[data-skel-hide]').length") == 0


def _fake(page, routes):
    # Answer the matching requests in-page after 300 ms with the given JSON.
    page.evaluate("""(routes) => { const f = window.fetch;
      window.fetch = (u, o) => { const hit = routes.find(([re]) => new RegExp(re).test(String(u)));
        if (!hit) return f(u, o);
        return new Promise((r) => setTimeout(r, 300)).then(() => new Response(JSON.stringify(hit[1]),
          {status: hit[2] || 200, headers: {'Content-Type': 'application/json'}})); }; }""", routes)


TITLE_JS = """(id) => { const el = document.getElementById(id);
  return {text: el.innerText.trim(), opacity: Number(getComputedStyle(el).opacity),
          header: getComputedStyle(el.closest('.main-view-header')).display !== 'none'}; }"""

# The title and the body fade in together: sampled mid-reveal, they match.
TOGETHER_JS = """([title, body]) => new Promise((resolve) => {
  const tick = () => {
    const a = Number(getComputedStyle(document.getElementById(title)).opacity);
    const b = Number(getComputedStyle(document.getElementById(body)).opacity);
    if (b > 0.2 && b < 0.8) resolve([a, b]); else requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
})"""


def _item(n):
    return {"item": {"id": f"k{n}", "type": "memory", "title": f"Item {n}", "content": f"knowledge body {n}"}}


def test_opening_a_knowledge_item_fades_its_text_in_from_a_skeleton(page):
    _open(page, "knowledge")
    _fake(page, [[r"/api/knowledge/read\?id=k1", _item(1)], [r"/api/knowledge/read\?id=k2", _item(2)]])
    page.evaluate("() => openKnowledgeItem('k1')")
    page.wait_for_function("() => document.getElementById('knowledgeDetailBody').innerText.includes('knowledge body 1')", timeout=15000)
    page.evaluate(FRAMES_JS, {"host": "#mainKnowledge", "content": "#knowledgeDetailBody"})
    page.evaluate("() => { openKnowledgeItem('k2'); }")
    page.wait_for_selector("#mainKnowledge > .skel", timeout=5000)
    # The previous item's title does not linger over the next item's skeleton,
    # and the header stays where it is.
    loading = page.evaluate(TITLE_JS, "knowledgeDetailTitle")
    assert loading["opacity"] == 0 and loading["header"], loading
    title, body = page.evaluate(TOGETHER_JS, ["knowledgeDetailTitle", "knowledgeDetailBody"])
    assert abs(title - body) < 0.05, (title, body)
    page.wait_for_function("() => window.__frames.length >= 150", timeout=20000)
    assert page.evaluate(TITLE_JS, "knowledgeDetailTitle") == {"text": "Item 2", "opacity": 1, "header": True}
    _assert_skeleton_then_fade(page.evaluate("() => window.__frames"), "knowledge body 2")
    assert page.evaluate("() => document.querySelectorAll('[data-skel-hide]').length") == 0


def test_a_missing_knowledge_item_drops_its_skeleton_at_once(page):
    _open(page, "knowledge")
    _fake(page, [[r"/api/knowledge/read", {"item": None}]])
    page.evaluate("() => { openKnowledgeItem('gone'); }")
    page.wait_for_selector("#mainKnowledge > .skel", timeout=5000)
    # Well inside the 10 s safety cap: nothing will be written into the body.
    page.wait_for_function("() => !document.querySelector('#mainKnowledge > .skel')", timeout=2000)
    assert page.evaluate("() => getComputedStyle(document.getElementById('knowledgeDetailEmpty')).display") == "flex"


def test_opening_a_wiki_page_fades_it_in_and_keeps_the_search_in_view(page):
    _open(page, "knowledge")
    _fake(page, [[r"/api/wiki/browse", {"pages": [{"name": "Alpha", "path": "alpha.md"}]}],
                 [r"/api/wiki/page", {"content": "wiki page body"}]])
    page.evaluate("() => { _openWikiBrowser(); }")
    page.wait_for_selector(".wiki-browser-item", timeout=5000)
    page.evaluate("""() => { window.__frames = []; const tick = () => {
      const panel = document.getElementById('wikiBrowserContent').parentElement;
      const c = document.getElementById('wikiBrowserContent');
      window.__frames.push({skel: !!panel.querySelector(':scope > .skel'), reveal: panel.dataset.skel === 'reveal',
        opacity: Number(getComputedStyle(c).opacity), text: c.innerText || '',
        search: getComputedStyle(document.getElementById('wikiBrowserSearch')).opacity === '1'});
      if (window.__frames.length < 150) requestAnimationFrame(tick); }; requestAnimationFrame(tick); }""")
    page.click(".wiki-browser-item")
    page.wait_for_function("() => window.__frames.length >= 150", timeout=20000)
    frames = page.evaluate("() => window.__frames")
    _assert_skeleton_then_fade(frames, "wiki page body")
    assert all(f["search"] for f in frames), "the search box was hidden behind the skeleton"
    assert page.evaluate("() => document.querySelectorAll('[data-skel-hide]').length") == 0
