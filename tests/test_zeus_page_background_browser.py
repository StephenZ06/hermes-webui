"""Zeus 2.0 dark: controls and popups sit on the page's own colour.

The audit walks the stylesheet rather than the open pages, so popups and modals
that never open during a test are covered too. Each class rule that sets a fill
on a control is rendered as a real element, and the colour it ends up with is
compared to the page.
"""
import pytest

from tests._pytest_port import BASE

READY = "() => typeof S !== 'undefined' && S._bootReady === true"
ZEUS = "localStorage.setItem('hermes-skin','zeus-2');localStorage.setItem('hermes-theme','dark');"

AUDIT = r"""() => {
  const host = document.createElement('div');
  host.style.cssText = 'position:fixed;left:-9999px;top:0;width:200px;height:200px';
  document.body.appendChild(host);
  const control = /(btn|button|modal|dialog|menu|popover|dropdown|drawer|popup|chip|pill|toggle|select|picker|card)/i;
  const skip = /data-skin="(?!zeus-2)|:not\(\.dark\)|\.light\b|data-theme/;
  const seen = new Set(), grey = [];
  const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(/[ ,\/]+/).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const check = sel => {
    if (seen.has(sel)) return; seen.add(sel);
    const el = document.createElement('div');
    el.className = sel.replace(/\./g, ' ').trim();
    el.style.setProperty('transition', 'none', 'important');
    host.appendChild(el);
    const style = getComputedStyle(el), c = parse(style.backgroundColor), image = style.backgroundImage;
    const fills = [c, ...[...image.matchAll(/rgba?\([^)]+\)/g)].map(m => parse(m[0]))].filter(Boolean);
    for (const f of fills) {
      const neutral = Math.max(f.r, f.g, f.b) - Math.min(f.r, f.g, f.b) <= 10;
      const over = 15 + ((f.r + f.g + f.b) / 3 - 15) * f.a;
      if (f.a > 0 && neutral && over >= 17.5) { grey.push(sel + ' ' + style.backgroundColor); break; }
    }
    el.remove();
  };
  const walk = rules => { for (const r of rules) {
    if (r.cssRules && r.type !== 1) { walk(r.cssRules); continue; }
    if (!r.style || !r.selectorText) continue;
    if (!r.style.getPropertyValue('background') && !r.style.getPropertyValue('background-color')) continue;
    if (skip.test(r.selectorText)) continue;
    for (const part of r.selectorText.split(',')) {
      const sel = part.trim();
      if (/^(\.[\w-]+)+$/.test(sel) && control.test(sel)) check(sel);
    }
  } };
  for (const s of document.styleSheets) { if ((s.href || '').includes('/static/style.css')) walk(s.cssRules); }
  host.remove();
  return grey;
}"""


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(viewport={"width": 1899, "height": 990})
        context.add_init_script(ZEUS)
        page = context.new_page()
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_function(READY, polling=100, timeout=30000)
        yield page
        browser.close()


def test_no_control_or_popup_rule_renders_a_grey_fill(page):
    assert page.evaluate(AUDIT) == []


def test_floating_surfaces_stay_opaque_on_the_page_colour(page):
    """A popup covers other content, so it takes the page colour, not nothing."""
    fills = page.evaluate("""() => ['app-dialog','model-dropdown','themed-select-popup','kanban-modal','kanban-board-switcher-menu','nb-menu'].map(name => {
      const el = document.createElement('div'); el.className = name;
      el.style.setProperty('transition','none','important'); document.body.appendChild(el);
      const s = getComputedStyle(el), value = [name, s.backgroundColor, s.backgroundImage]; el.remove(); return value; })""")
    for name, colour, image in fills:
        assert colour == "rgb(15, 15, 15)", name
        assert image == "none", name


def test_selected_segments_keep_a_visible_tint(page):
    """Selection used to be shown by the grey fill, so it needs its own colour."""
    tints = page.evaluate("""() => ['seg-btn active','office-page-nav-btn is-active','mi-pill'].map(name => {
      const parent = document.createElement('div'); parent.className = name === 'mi-pill' ? 'seg' : 'studio-tabs';
      const el = document.createElement('div'); el.className = name;
      el.style.setProperty('transition','none','important'); parent.appendChild(el); document.body.appendChild(parent);
      const value = getComputedStyle(el).backgroundColor; parent.remove(); return value; })""")
    assert all("70, 130, 180" in tint for tint in tints), tints
