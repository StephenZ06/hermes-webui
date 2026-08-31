from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOT_JS = (ROOT / "static" / "boot.js").read_text(encoding="utf-8")
STYLE_CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


def test_pwa_edge_swipe_gesture_is_registered_for_mobile_sidebar():
    assert "function _installPwaSidebarSwipeGesture" in BOOT_JS
    # The guard element MUST have its own non-passive touchstart listener: WebKit
    # decides whether to start its edge swipe-back during the touchstart dispatch,
    # so a preventDefault() from the drag handler's first touchmove is always too
    # late. Scoped to the strip so the rest of the page keeps passive touchstart.
    assert "guard.addEventListener('touchstart', _onPwaSidebarEdgeGuardStart, {passive:false})" in BOOT_JS
    assert "window.addEventListener('touchstart', _onPwaSidebarSwipeStart, {capture:true,passive:true})" in BOOT_JS
    assert "window.addEventListener('touchmove', _onPwaSidebarSwipeMove, {capture:true,passive:false})" in BOOT_JS
    assert "window.addEventListener('touchend', _onPwaSidebarSwipeEnd, {capture:true,passive:true})" in BOOT_JS
    assert "window.addEventListener('touchcancel', _onPwaSidebarSwipeCancel, {capture:true,passive:true})" in BOOT_JS
    assert "window.addEventListener('pointerdown', _onPwaSidebarSwipeStart" in BOOT_JS
    assert "window.addEventListener('pointermove', _onPwaSidebarSwipeMove" in BOOT_JS
    assert "window.addEventListener('pointerup', _onPwaSidebarSwipeEnd" in BOOT_JS
    assert "window.addEventListener('pointercancel', _onPwaSidebarSwipeCancel" in BOOT_JS
    assert "function _isTouchPointerEvent" in BOOT_JS
    assert "if(_isTouchPointerEvent(e))return" in BOOT_JS


def test_pwa_sidebar_swipe_is_edge_gated_standalone_and_horizontal():
    assert "_isPwaStandalone()" in BOOT_JS
    assert "_PWA_SIDEBAR_SWIPE_EDGE" in BOOT_JS
    assert "_PWA_SIDEBAR_SWIPE_CLAIM" in BOOT_JS
    assert "_PWA_SIDEBAR_SWIPE_TRIGGER" in BOOT_JS
    assert "_PWA_SIDEBAR_SWIPE_MAX_VERTICAL" in BOOT_JS
    assert "clientX>_PWA_SIDEBAR_SWIPE_EDGE" in BOOT_JS.replace(" ", "")
    assert "dx>=_PWA_SIDEBAR_SWIPE_CLAIM" in BOOT_JS.replace(" ", "")
    assert "e.preventDefault()" in BOOT_JS[BOOT_JS.find("function _onPwaSidebarSwipeMove"):BOOT_JS.find("function _onPwaSidebarSwipeEnd")]
    assert "dx>=_PWA_SIDEBAR_SWIPE_TRIGGER" in BOOT_JS.replace(" ", "")
    assert "Math.abs(dy)<=_PWA_SIDEBAR_SWIPE_MAX_VERTICAL" in BOOT_JS.replace(" ", "")
    assert "dx>Math.abs(dy)*1.5" in BOOT_JS.replace(" ", "")

    assert "input,textarea,select,button,a,[contenteditable=\"true\"],.topbar-chips,.composer-left,.sidebar,.rightpanel" in BOOT_JS
    assert ".messages" not in BOOT_JS[BOOT_JS.find("function _isInteractiveSwipeTarget"):BOOT_JS.find("function _openMobileSidebarFromGesture")]


def test_edge_guard_cancels_webkit_swipe_back_in_touchstart():
    """The regression this file exists for: an iOS PWA left-edge swipe navigated
    back instead of opening the drawer.

    Root cause: WebKit commits to its interactive swipe-back during the
    touchstart dispatch. The gesture's only preventDefault() lived in the move
    handler and fired after ~10px of proven horizontal intent, so the browser had
    already taken the touch. overscroll-behavior-x (the previous attempted fix)
    governs Chromium overscroll navigation and does nothing here.
    """
    start = BOOT_JS[
        BOOT_JS.find("function _onPwaSidebarEdgeGuardStart"):
        BOOT_JS.find("function _onPwaSidebarEdgeGuardMove")
    ]
    assert start, "_onPwaSidebarEdgeGuardStart must exist"
    assert "e.preventDefault()" in start, (
        "the edge guard must preventDefault the touchstart itself; by touchmove "
        "WebKit's navigation gesture is already running"
    )
    assert "{passive:false}" in BOOT_JS[
        BOOT_JS.find("function _installPwaSidebarSwipeGesture"):
    ], "a passive listener cannot cancel the gesture"


def test_edge_guard_gives_back_the_default_behaviour_it_swallows():
    """Preventing touchstart kills taps and scrolling in the strip, so the strip
    has to replay both by hand or it becomes a dead gutter down the left of every
    chat -- which is why the guard was made pointer-events:none the last time."""
    assert "function _replayEdgeGuardTap" in BOOT_JS
    assert "MouseEvent('click'" in BOOT_JS
    assert "function _elementBeneathEdgeGuard" in BOOT_JS
    assert "guard.style.pointerEvents='none'" in BOOT_JS, (
        "the guard must step out of hit-testing during the lookup or it finds itself"
    )
    assert "function _scrollableUnder" in BOOT_JS
    assert "scrollTop-=step" in BOOT_JS.replace(" ", ""), (
        "vertical drags starting in the strip must be forwarded to the scroller under it"
    )
    assert "function _flingScroller" in BOOT_JS, (
        "forwarded scrolling without inertia stops dead on release"
    )


def test_drawer_settle_is_a_velocity_seeded_spring_with_css_fallback():
    settle = BOOT_JS[
        BOOT_JS.find("function _settleMobileSidebarDrag"):
        BOOT_JS.find("function _springDrawerTo")
    ]
    assert "_springDrawerTo(" in settle
    spring = BOOT_JS[BOOT_JS.find("function _springDrawerTo"):]
    assert "type:'spring'" in spring
    assert "velocity:(Number(velocityPxPerMs)||0)*1000" in spring, (
        "the flick's own velocity must seed the spring, or the settle restarts from rest"
    )
    assert "prefersReducedMotion()" in spring and "return null" in spring, (
        "no Motion / reduced motion must fall back to the CSS transition"
    )
    assert "_scheduleSidebarDragFrame" in BOOT_JS and "requestAnimationFrame" in BOOT_JS, (
        "drag transform writes must be coalesced to one per painted frame"
    )
    assert "if(_sidebarSettleAnim)return;" in BOOT_JS, (
        "an in-flight settle must not be cleaned up as a stranded drag"
    )


def test_pwa_sidebar_swipe_opens_existing_mobile_drawer_without_desktop_collapse():
    assert "_openMobileSidebarFromGesture" in BOOT_JS
    assert "sidebar.classList.remove('sidebar-collapsed')" in BOOT_JS
    assert "sidebar.classList.add('mobile-open')" in BOOT_JS
    body = BOOT_JS[BOOT_JS.find("function _openMobileSidebarFromGesture"):BOOT_JS.find("function _installPwaSidebarSwipeGesture")]
    assert "overlay.classList.add('visible')" not in body
    assert "toggleSidebar(" not in BOOT_JS[BOOT_JS.find("function _openMobileSidebarFromGesture"):BOOT_JS.find("function _installPwaSidebarSwipeGesture")]


def test_pwa_sidebar_swipe_does_not_disable_horizontal_scrollers_globally():
    compact = STYLE_CSS.replace(" ", "")
    assert "html{touch-action" not in compact
    assert "body{touch-action" not in compact
    assert ".layout{touch-action" not in compact
