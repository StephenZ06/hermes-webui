"""Chat page optical alignment, measured on rendered pixels rather than CSS boxes.

Each check screenshots a component twice, once with its text or icons hidden, so the
difference holds only that ink: fills, borders and shadows can never count as text.
Text is measured from the top of its capitals to its baseline, so the sample strings
avoid descenders. The numbers hold for Courier New, which Zeus 2.0 resolves to, so the
module skips where fontconfig has no real Courier New; point FONTCONFIG_FILE at a
directory holding it to run these.
"""

import io
import shutil
import subprocess

import pytest
from PIL import Image, ImageChops

from tests._pytest_port import BASE



def _has_courier_new():
    if not shutil.which("fc-match"):
        return False
    found = subprocess.run(["fc-match", "-f", "%{family}", "Courier New"], capture_output=True, text=True)
    return "Courier New" in found.stdout


pytestmark = pytest.mark.skipif(not _has_courier_new(), reason="needs real Courier New through fontconfig")

DESKTOP = {"viewport": {"width": 1899, "height": 990}, "device_scale_factor": 1}
MACBOOK = {"viewport": {"width": 1470, "height": 956}, "device_scale_factor": 2}
PHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 3,
         "is_mobile": True, "has_touch": True}
SCREENS = pytest.mark.parametrize("screen", [DESKTOP, MACBOOK], ids=["desktop", "macbook"])
FREEZE = "*,*::before,*::after{transition:none!important;animation-duration:0s!important;caret-color:transparent!important}"


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        instance = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        yield instance
        instance.close()


def _open(browser, screen):
    context = browser.new_context(**screen)
    page = context.new_page()
    page.add_init_script("try{localStorage.setItem('hermes-skin','zeus-2')}catch(e){}")
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", timeout=30000)
    page.evaluate("""async () => {
      document.querySelectorAll('#onboardingOverlay,#appTourOverlay,#updateBanner').forEach(e => e.remove());
      document.documentElement.dataset.skin = 'zeus-2';
      document.documentElement.classList.add('dark');
      await switchPanel('chat');
    }""")
    page.add_style_tag(content=FREEZE)
    page.wait_for_timeout(500)
    return context, page


def _shot(page, clip):
    return Image.open(io.BytesIO(page.screenshot(clip=clip))).convert("RGB")


def _rect(page, selector):
    return page.eval_on_selector(selector, """e => { const r = e.getBoundingClientRect();
      return {x: r.left, y: r.top, width: r.width, height: r.height}; }""")


def _ink(page, selector, kind, within=None):
    """Top, bottom, left, right of the ink in CSS pixels, from the difference of two shots."""
    box = _rect(page, within or selector)
    left, top = max(int(box["x"]) - 2, 0), max(int(box["y"]) - 2, 0)
    clip = {"x": left, "y": top, "width": int(box["width"]) + 6, "height": int(box["height"]) + 6}
    hide = "opacity:0!important" if kind == "icon" else "-webkit-text-fill-color:transparent!important"
    target = f"{selector} svg" if kind == "icon" else f"{selector},{selector} *,{selector}::placeholder"
    before = _shot(page, clip)
    handle = page.add_style_tag(content=f"{target}{{{hide}}}")
    after = _shot(page, clip)
    handle.evaluate("e => e.remove()")
    diff = ImageChops.difference(before, after).convert("L")
    peak = diff.getextrema()[1]
    assert peak > 0, f"no {kind} ink found in {selector}"
    left, top, right, bottom = diff.point(lambda v: 255 if v >= max(24, peak * .4) else 0).getbbox()
    scale = before.width / clip["width"]
    return {"top": clip["y"] + top / scale, "bottom": clip["y"] + bottom / scale,
            "left": clip["x"] + left / scale, "right": clip["x"] + right / scale}


def _centre(ink):
    return (ink["top"] + ink["bottom"]) / 2


def _gaps(page, selector, kind="text"):
    box, ink = _rect(page, selector), _ink(page, selector, kind)
    scale = page.evaluate("devicePixelRatio")  # a box paints on whole device pixels
    top = round(box["y"] * scale) / scale
    bottom = round((box["y"] + box["height"]) * scale) / scale
    return ink["top"] - top, bottom - ink["bottom"]


def _chat_fixture(page):
    """Real thinking card, inline code and role row, rendered inside the message list."""
    page.evaluate("""() => {
      const m = document.getElementById('messages');
      const empty = document.getElementById('emptyState');
      if (empty) empty.style.display = 'none';
      m.style.display = 'block';
      const box = document.createElement('div');
      box.id = 'oaFixture';
      box.style.cssText = 'max-width:640px;margin:24px auto;display:grid;gap:12px';
      box.innerHTML = _thinkingCardHtml('Checking the row metrics.', false)
        + '<div class="msg-row" data-role="assistant"><div class="msg-role assistant"><div class="role-icon assistant">H</div>'
        + '<span class="msg-role-name">Hermes</span></div><div class="msg-body"><p>Run <code>Code</code> now</p></div></div>';
      box.querySelector('.thinking-card-label').textContent = 'Reason';
      m.prepend(box);
      m.scrollTop = 0;
    }""")
    page.wait_for_timeout(200)


@SCREENS
def test_source_badge_text_is_centred_in_its_pill(browser, screen):
    context, page = _open(browser, screen)
    try:
        page.evaluate("""() => {
          const sub = document.getElementById('appTitlebarSub');
          sub.hidden = false; sub.textContent = '11 ';
          const badge = document.createElement('span');
          badge.className = 'topbar-source-badge'; badge.textContent = 'Claude Code';
          sub.append(badge);
        }""")
        top, bottom = _gaps(page, ".topbar-source-badge")
        assert abs(top - bottom) <= 1, (top, bottom)
    finally:
        context.close()


@SCREENS
def test_suggestion_icons_share_their_labels_centre(browser, screen):
    context, page = _open(browser, screen)
    try:
        selector = ".suggestion-grid > .suggestion:nth-child(2)"
        page.eval_on_selector(selector, """e => { e.lastChild.textContent = ' What is on the list'; }""")
        icon, text = _ink(page, selector, "icon"), _ink(page, selector, "text")
        assert abs(_centre(icon) - _centre(text)) <= .5, (icon, text)
    finally:
        context.close()


@SCREENS
@pytest.mark.parametrize("chip, field", [("#composerModelChip", ".model-search-input"),
                                         ("#composerWorkspaceChip", ".ws-search-input")],
                         ids=["model", "workspace"])
def test_menu_search_placeholders_are_centred(browser, screen, chip, field):
    context, page = _open(browser, screen)
    try:
        page.click(chip)
        page.wait_for_selector(field)
        page.eval_on_selector(field, "e => { e.placeholder = 'Search models'; }")
        page.wait_for_timeout(200)
        top, bottom = _gaps(page, field)
        # Field text snaps in whole CSS pixels, so 8.5 rows of ink at 2x cannot sit closer.
        assert abs(top - bottom) <= 1.5, (top, bottom)
    finally:
        context.close()


@SCREENS
def test_sidebar_heading_sits_on_its_divider(browser, screen):
    context, page = _open(browser, screen)
    try:
        selector = ".chat-sidebar-section--workspaces .chat-sidebar-section-heading"
        text = _ink(page, selector, "text")
        line = page.eval_on_selector(selector, """e => { const r = e.getBoundingClientRect();
          return r.top + r.height / 2; }""")
        assert abs(_centre(text) - line) <= .75, (text, line)
    finally:
        context.close()


@SCREENS
def test_thinking_bulb_shares_its_labels_centre(browser, screen):
    context, page = _open(browser, screen)
    try:
        _chat_fixture(page)
        icon = _ink(page, "#oaFixture .thinking-card-icon", "icon")
        text = _ink(page, "#oaFixture .thinking-card-label", "text")
        assert abs(_centre(icon) - _centre(text)) <= .75, (icon, text)
    finally:
        context.close()


@SCREENS
def test_inline_code_text_is_centred_in_its_chip(browser, screen):
    context, page = _open(browser, screen)
    try:
        _chat_fixture(page)
        top, bottom = _gaps(page, "#oaFixture .msg-body code")
        assert abs(top - bottom) <= 1, (top, bottom)
    finally:
        context.close()


@pytest.mark.parametrize("screen", [DESKTOP, MACBOOK, PHONE], ids=["desktop", "macbook", "phone"])
def test_role_name_shares_the_avatars_centre(browser, screen):
    context, page = _open(browser, screen)
    try:
        _chat_fixture(page)
        name = _ink(page, "#oaFixture .msg-role-name", "text")
        avatar = _rect(page, "#oaFixture .role-icon")
        assert abs(_centre(name) - (avatar["y"] + avatar["height"] / 2)) <= .5, name
    finally:
        context.close()


@SCREENS
def test_approval_icons_share_their_labels_centre(browser, screen):
    context, page = _open(browser, screen)
    try:
        page.evaluate("""() => {
          S.session = S.session || {session_id: 'oa'};
          showApprovalCard({_session_id: S.session.session_id, session_id: S.session.session_id, approval_id: 'oa',
                            description: 'Run a command', command: 'ls', pattern_keys: ['ls']}, 1);
        }""")
        page.wait_for_timeout(200)
        icon = _ink(page, "#approvalBtnOnce .approval-btn-icon", "icon")
        text = _ink(page, "#approvalBtnOnce .approval-btn-label", "text")
        assert abs(_centre(icon) - _centre(text)) <= .5, (icon, text)
    finally:
        context.close()


def test_phone_profile_label_shares_its_icons_centre(browser):
    context, page = _open(browser, PHONE)
    try:
        icon = _ink(page, "#titlebarProfileBtn", "icon")
        text = _ink(page, "#titlebarProfileLabel", "text")
        assert abs(_centre(icon) - _centre(text)) <= .75, (icon, text)
    finally:
        context.close()
