"""Popups, loaders and linked deletes move instead of snapping.

- Every popup added to <body> without its own motion slides/fades in, and on
  removal leaves a pixel-only copy that fades out (no class, id or data, so
  code looking the popup up by class never finds it).
- Modal backdrops dim and blur half as much as before.
- The Chat "+" menu has its two icons with 8px around each, and slides in.
- The Skills "+" menu shows its artwork and animates between steps.
- Content replacing a loader fades in.
- A row removed by a rebuild (deleted on another page) collapses out.
"""

import pytest

from tests._pytest_port import BASE


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            tab = browser.new_page(viewport={"width": 1440, "height": 900})
            tab.goto(BASE + "/", wait_until="domcontentloaded")
            tab.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            tab.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            yield tab
        finally:
            browser.close()


def test_chat_new_menu_has_icons_with_even_margins_slides_in_and_leaves_no_selectable_copy(page):
    page.evaluate("() => switchPanel('chat')")
    page.wait_for_timeout(300)
    page.evaluate("() => document.getElementById('btnNewChat').click()")
    names = page.evaluate("() => document.querySelector('.new-chat-menu').getAnimations().map(a => a.animationName)")
    assert names == ["new-chat-menu-in"], names
    page.wait_for_timeout(300)
    rows = page.evaluate("""() => [...document.querySelectorAll('.new-chat-menu-item')].map(it => {
      const r = it.getBoundingClientRect(), icon = it.querySelector('.new-chat-menu-icon'), i = icon.getBoundingClientRect();
      return {top: i.top - r.top, bottom: r.bottom - i.bottom, left: i.left - r.left, w: i.width, kind: icon.className,
              art: icon.querySelector('svg circle') ? 'circle-plus' : ''}; })""")
    assert [r["kind"] for r in rows] == ["new-chat-menu-icon is-conversation", "new-chat-menu-icon is-project"], rows
    for r in rows:
        # The circled plus sits half a pixel below centre, on the label's ink centre.
        assert r["w"] == 16 and r["left"] == 8 and (r["top"], r["bottom"]) == (8.5, 7.5), r
    # Both choices show the same circled plus, not a picture.
    assert [r["art"] for r in rows] == ["circle-plus", "circle-plus"], rows
    page.mouse.click(900, 700)
    after = page.evaluate("""() => { const g = document.querySelector('[data-popup-ghost]');
      return {menus: document.querySelectorAll('.new-chat-menu').length, ghost: !!g, cls: g && g.getAttribute('class'),
              fading: g ? g.getAnimations().length : 0, inert: g && g.inert}; }""")
    assert after == {"menus": 0, "ghost": True, "cls": None, "fading": 1, "inert": True}, after
    page.wait_for_function("() => !document.querySelector('[data-popup-ghost]')", timeout=2000)
    # Opening again straight away works: the fading copy is not mistaken for an open menu.
    page.evaluate("() => { document.getElementById('btnNewChat').click(); }")
    assert page.evaluate("() => document.querySelectorAll('.new-chat-menu').length") == 1


def test_modal_backdrops_dim_and_blur_half_as_much(page):
    # Measured without a skin; the Zeus skins' darker scrim is halved too.
    got = page.evaluate("""() => { const root = document.documentElement, skin = root.getAttribute('data-skin'); root.removeAttribute('data-skin');
      const out = ['app-dialog-overlay', 'project-starter-overlay', 'onboarding-overlay', 'cmdk-overlay', 'kanban-modal-overlay', 'goal-planner-overlay'].map(c => {
      const el = document.createElement('div'); el.className = c; document.body.appendChild(el);
      const cs = getComputedStyle(el), out = [c, cs.backgroundColor, cs.backdropFilter]; el.remove(); return out; });
      if (skin !== null) root.setAttribute('data-skin', skin); return out; }""")
    assert got == [
        ["app-dialog-overlay", "rgba(0, 0, 0, 0.31)", "blur(3px)"],
        ["project-starter-overlay", "rgba(0, 0, 0, 0.34)", "blur(3.5px)"],
        ["onboarding-overlay", "rgba(0, 0, 0, 0.39)", "blur(4px)"],
        ["cmdk-overlay", "rgba(0, 0, 0, 0.31)", "blur(3px)"],
        ["kanban-modal-overlay", "rgba(0, 0, 0, 0.39)", "none"],
        ["goal-planner-overlay", "rgba(0, 0, 0, 0.275)", "none"],
    ], got
    zeus = page.evaluate("""() => { const root = document.documentElement, skin = root.getAttribute('data-skin'), dark = root.classList.contains('dark');
      root.setAttribute('data-skin', 'zeus-2'); root.classList.add('dark');
      const el = document.createElement('div'); el.className = 'app-dialog-overlay'; document.body.appendChild(el);
      const bg = getComputedStyle(el).backgroundColor; el.remove();
      if (skin === null) root.removeAttribute('data-skin'); else root.setAttribute('data-skin', skin); if (!dark) root.classList.remove('dark'); return bg; }""")
    assert zeus == "rgba(0, 0, 0, 0.36)", zeus


def test_popup_without_motion_of_its_own_gets_an_entrance_and_an_exit(page):
    page.evaluate("""() => { const m = document.createElement('div'); m.className = 'demo-menu'; m.style.cssText = 'position:fixed;top:80px;left:80px;width:120px;height:60px;background:#333';
      m.innerHTML = '<button class="demo-item" data-x="1">Item</button>'; document.body.appendChild(m); window.__demo = m; }""")
    assert page.evaluate("() => window.__demo.getAnimations().length") == 1
    page.wait_for_timeout(300)
    page.evaluate("() => window.__demo.remove()")
    ghost = page.evaluate("""() => { const g = document.querySelector('[data-popup-ghost]');
      return g && {cls: g.getAttribute('class'), inner: g.querySelector('[class],[data-x]') === null, bg: getComputedStyle(g).backgroundColor}; }""")
    assert ghost == {"cls": None, "inner": True, "bg": "rgb(51, 51, 51)"}, ghost
    page.wait_for_function("() => !document.querySelector('[data-popup-ghost]')", timeout=2000)


def test_skills_add_menu_shows_artwork_and_animates_between_steps(page):
    page.evaluate("() => switchPanel('skills')")
    page.wait_for_timeout(400)
    page.evaluate("() => openSkillAddMenu()")
    page.wait_for_selector(".skill-add-choice img")
    entering = page.evaluate("() => [...document.querySelectorAll('.skill-add-choices.is-entering .skill-add-choice')].map(c => getComputedStyle(c).animationName)")
    assert entering == ["skill-choice-in"] * 3, entering
    page.wait_for_function("() => [...document.querySelectorAll('.skill-add-choice img')].every(i => i.complete && i.naturalWidth > 0)")
    art = page.evaluate("""() => [...document.querySelectorAll('.skill-add-choice')].map(c => {
      const r = c.querySelector('.skill-add-choice-icon').getBoundingClientRect(), card = c.getBoundingClientRect();
      return [new URL(c.querySelector('img').src).pathname, c.querySelector('img').getAttribute('width'), Math.round((r.top - card.top) - (card.bottom - r.bottom))]; })""")
    assert art == [["/static/skills/new-skill.png", "24", 0], ["/static/skills/import-skill.png", "24", 0], ["/static/skills/new-category.png", "24", 0]], art
    page.evaluate("() => document.querySelector('.skill-add-choice[data-choice=import]').click()")
    moving = page.evaluate("() => [document.querySelector('.skill-add-body').getAnimations().length, document.getElementById('skillAddTitle').textContent]")
    assert moving == [1, "Import skill"], moving
    page.wait_for_timeout(350)
    page.evaluate("() => document.querySelector('[data-skill-add=back]').click()")
    assert page.evaluate("() => document.querySelector('.skill-add-body').getAnimations().length") == 1
    page.keyboard.press("Escape")
    assert page.evaluate("() => [document.querySelectorAll('.skill-add-overlay').length, !!document.querySelector('[data-popup-ghost]')]") == [0, True]


def test_content_that_replaces_a_loader_fades_in(page):
    page.evaluate("() => switchPanel('skills')")
    page.wait_for_timeout(600)
    got = page.evaluate("""async () => { const host = document.querySelector('main.main');
      const box = document.createElement('div'); box.style.cssText = 'position:fixed;top:120px;left:400px;width:200px'; host.appendChild(box);
      box.innerHTML = '<div class="loading-spinner-wrap"><div class="loading-spinner"></div></div>';
      await new Promise(r => setTimeout(r, 30));
      box.innerHTML = '<p class="demo-a">A</p><p class="demo-b">B</p>';
      await new Promise(r => setTimeout(r, 0));
      const out = [...box.children].map(n => n.getAnimations().length); box.remove(); return out; }""")
    assert got == [1, 1], got


def test_a_row_removed_by_a_rebuild_collapses_out_where_it_was(page):
    got = page.evaluate("""async () => { const root = document.createElement('div'); root.style.cssText = 'position:fixed;top:100px;left:100px;width:200px';
      root.innerHTML = '<div class="demo-list"><div data-k="a" style="height:20px">A</div><div data-k="b" style="height:20px">B</div><div data-k="c" style="height:20px">C</div></div>';
      document.body.appendChild(root);
      const key = n => n.dataset.k;
      rebuildWithExits(root, '.demo-list', key, () => { root.querySelector('.demo-list').innerHTML = '<div data-k="a" style="height:20px">A</div><div data-k="c" style="height:20px">C</div>'; });
      const list = root.querySelector('.demo-list');
      const now = [...list.children].map(n => [n.textContent, n.dataset.leaving || '', n.inert, n.getAnimations().length]);
      await new Promise(r => setTimeout(r, 400));
      const later = [...list.children].map(n => n.textContent); root.remove(); return {now, later}; }""")
    assert got["now"] == [["A", "", False, 0], ["B", "1", True, 1], ["C", "", False, 0]], got
    assert got["later"] == ["A", "C"], got
