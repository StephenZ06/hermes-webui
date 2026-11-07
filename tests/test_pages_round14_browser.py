"""The usage card's wording and spacing, the Gateway pill, wizard logos, and wizard loading states."""

import io
import math

import pytest
from PIL import Image

from tests.test_chat_optical_alignment_browser import _ink, _rect, browser, pytestmark, real_2x  # noqa: F401
from tests.test_office_notes_workhub_nudges_browser import _moved, _panel
from tests.test_pages_round13_browser import _pick, _usage, _wizard


# ── Session usage card ────────────────────────────────────────────────────

def _card(page):
    return page.evaluate("""() => ({text: document.getElementById('chatUsageWidgetPercent').textContent,
      filled: document.querySelectorAll('#chatUsageWidgetBattery .is-filled').length})""")


@pytest.mark.parametrize("used, text, filled", [(5, "95% Remaining", 10), (0, "100% Remaining", 10), (60, "40% Remaining", 4), (100, "0% Remaining", 0)])
def test_the_number_and_the_battery_both_say_what_is_left(real_2x, used, text, filled):
    page = real_2x
    page.route("**/api/account_usage*", lambda route: route.fulfill(json={}))
    _panel(page, "chat")
    _usage(page, {"available": True, "provider": "custom:9router",
                  "windows": [{"label": "5 hours", "used_percent": used}, {"label": "Weekly", "used_percent": used}]})
    assert _card(page) == {"text": text, "filled": filled}


def test_the_local_card_has_as_much_room_under_its_title_as_over_it(real_2x):
    page = real_2x
    page.route("**/api/account_usage*", lambda route: route.fulfill(json={}))
    _panel(page, "chat")
    _usage(page, {"available": False, "provider": "lmstudio", "local": True})
    card = _rect(page, "#chatUsageWidget")
    ink = _ink(page, "#chatUsageWidgetLabel", "text", within="#chatUsageWidget")
    over, under = ink["top"] - card["y"], card["y"] + card["height"] - ink["bottom"]
    assert abs(over - under) <= .5, (over, under)


# ── Profiles ──────────────────────────────────────────────────────────────

def test_the_gateway_pill_text_sits_half_a_pixel_lower_in_the_same_box(real_2x):
    page = real_2x
    _panel(page, "profiles")
    page.wait_for_function("() => !!(_profilesCache && _profilesCache.profiles.length)", polling=50, timeout=10000)
    page.evaluate("() => openProfileDetail(_profilesCache.profiles[0].name)")
    page.wait_for_selector(".profile-gateway-badge")
    page.wait_for_timeout(500)
    pill = ".profile-gateway-badge"
    undo = f"{pill}{{padding-top:2px!important;padding-bottom:2px!important}}"
    height = _rect(page, pill)["height"]
    assert _moved(page, pill, "text", undo) == .5
    handle = page.add_style_tag(content=undo)
    assert _rect(page, pill)["height"] == height
    handle.evaluate("e => e.remove()")


# ── Wizard logos ──────────────────────────────────────────────────────────

def test_the_logos_fill_their_tiles_alike_and_sit_in_the_middle(real_2x):
    page = real_2x
    _wizard(page)
    seen = {}
    for tile in page.query_selector_all(".pw-choice .ps-template-icon:has(img)"):
        name = tile.query_selector("img").get_attribute("src").split("/")[-1][:-4]
        tile.scroll_into_view_if_needed()
        box = tile.bounding_box()
        # Rows land on fractions of a pixel: read a whole-pixel square inside the
        # tile's rounded corners, and place the ink against the tile's real centre.
        x, y = math.ceil(box["x"] + 3), math.ceil(box["y"] + 3)
        shot = Image.open(io.BytesIO(page.screenshot(clip={"x": x, "y": y, "width": 23, "height": 23}))).convert("L")
        left, top, right, bottom = shot.point(lambda v: 255 if v < 215 else 0).getbbox()
        scale = shot.width / 23
        seen[name] = {"w": (right - left) / scale, "h": (bottom - top) / scale,
                      "x": x + (left + right) / 2 / scale - box["x"] - box["width"] / 2,
                      "y": y + (top + bottom) / 2 / scale - box["y"] - box["height"] / 2}
    assert len(seen) == 10, seen
    longest = {k: max(v["w"], v["h"]) for k, v in seen.items()}
    assert min(longest.values()) >= 17.5 and max(longest.values()) <= 22, longest
    for name, spot in seen.items():
        assert abs(spot["x"]) <= .75 and abs(spot["y"]) <= .75, (name, spot)


# ── Wizard loading states ─────────────────────────────────────────────────

def _spinning(page, selector=".ps-next"):
    return page.evaluate("""(selector) => { const b = document.querySelector(selector), s = b.querySelector('.mi-spin');
      return {spin: !!s && getComputedStyle(s).animationName === 'mi-rotate', text: b.textContent.trim(), disabled: b.disabled,
              opacity: getComputedStyle(b).opacity, width: b.getBoundingClientRect().width}; }""", selector)


def _idle(page, selector=".ps-next"):
    return page.evaluate("""(selector) => { const b = document.querySelector(selector);
      return {spin: !!b.querySelector('.mi-spin'), text: b.textContent.trim(), held: b.hasAttribute('data-mi-hold') || b.classList.contains('mi-busy')}; }""", selector)


def _hold(page, pattern):
    held = []
    page.route(pattern, lambda route: held.append(route))
    return held


def _wait(page, held):
    for _ in range(100):
        if held:
            return held.pop()
        page.wait_for_timeout(30)
    raise AssertionError("the request never came")


def _keyed(page, answers=None):
    posts = _wizard(page, answers)
    _pick(page, "OpenAI")
    page.fill(".pw-key", "a-key")
    return posts


def test_next_spins_at_full_strength_through_a_key_check_without_moving(real_2x):
    page = real_2x
    _keyed(page)
    before = page.evaluate("() => document.querySelector('.ps-next').getBoundingClientRect().width")
    held = _hold(page, "**/api/profiles/providers/verify")
    page.click(".ps-next")
    route = _wait(page, held)
    state = _spinning(page)
    assert state["spin"] and state["text"] == "Checking…" and state["disabled"] and state["opacity"] == "1"
    assert state["width"] == before
    route.fulfill(json={"state": "ok", "message": "Key accepted."})
    page.wait_for_selector(".pw-model-search")
    assert _idle(page)["spin"] is False and _idle(page)["held"] is False and _idle(page)["text"] == "Next"


def test_typing_during_a_check_leaves_the_spinner_alone(real_2x):
    page = real_2x
    _keyed(page)
    held = _hold(page, "**/api/profiles/providers/verify")
    page.click(".ps-next")
    route = _wait(page, held)
    page.evaluate("() => { const i = document.querySelector('.pw-key'); i.value = 'other'; i.dispatchEvent(new Event('input', {bubbles: true})); }")
    assert _spinning(page)["spin"] and _spinning(page)["disabled"]
    route.fulfill(json={"state": "ok"})
    page.wait_for_selector(".pw-model-search")


@pytest.mark.parametrize("answer, label, disabled", [
    ({"state": "rejected", "message": "No."}, "Next", True),
    ({"state": "unknown", "message": "Could not reach it."}, "Save anyway", False),
])
def test_a_check_that_stops_the_step_releases_next(real_2x, answer, label, disabled):
    page = real_2x
    _keyed(page)
    held = _hold(page, "**/api/profiles/providers/verify")
    page.click(".ps-next")
    _wait(page, held).fulfill(json=answer)
    page.wait_for_selector(".pw-check:not(:empty)")
    page.wait_for_function("() => !document.querySelector('.ps-next .mi-spin')", polling=30, timeout=3000)
    assert _idle(page) == {"spin": False, "text": label, "held": False}
    assert page.is_disabled(".ps-next") is disabled


def test_a_failed_save_of_the_key_releases_next(real_2x):
    page = real_2x
    _keyed(page, {"verify": {"state": "ok"}})
    page.route("**/api/profiles/providers/key", lambda route: route.fulfill(status=500, json={"error": "Disk full"}))
    page.click(".ps-next")
    page.wait_for_function("() => !document.querySelector('.ps-next .mi-spin') && document.querySelector('.ps-next').textContent === 'Next'", polling=30, timeout=3000)
    assert not page.is_disabled(".ps-next") and page.is_visible(".pw-key")


def _at_finish(page, answers=None):
    posts = _keyed(page, answers)
    page.click(".ps-next")
    page.wait_for_selector(".pw-model")
    page.click(".pw-model")
    page.click(".ps-next")
    page.wait_for_selector(".pw-use")
    return posts


@pytest.mark.parametrize("status, answer, label", [
    (200, {"ok": True, "message": "Replied."}, "Done"),
    (500, {"error": "Could not write the config"}, "Save"),
])
def test_save_spins_until_its_outcome_is_known(real_2x, status, answer, label):
    page = real_2x
    _at_finish(page, {"verify": {"state": "ok"}})
    held = _hold(page, "**/api/profiles/providers/main")
    page.click(".ps-next")
    route = _wait(page, held)
    state = _spinning(page)
    assert state["spin"] and state["text"] == "Saving…" and state["opacity"] == "1"
    route.fulfill(status=status, json=answer)
    page.wait_for_function("(label) => document.querySelector('.ps-next').textContent === label", arg=label, polling=30, timeout=3000)
    assert _idle(page) == {"spin": False, "text": label, "held": False}
    assert not page.is_disabled(".ps-next")


@pytest.mark.parametrize("status, answer, then", [
    (200, {"ok": True}, ".pw-choice"),
    (400, {"error": "That name is taken"}, ".pw-name"),
])
def test_create_profile_spins_and_lets_go_on_either_outcome(real_2x, status, answer, then):
    page = real_2x
    _wizard(page)
    page.evaluate("() => { document.querySelector('.project-starter-overlay').remove(); window.__wizard = openProviderWizard('', {create: true}); }")
    page.wait_for_selector(".pw-name")
    page.fill(".pw-name", "fresh-one")
    held = _hold(page, "**/api/profile/create")
    page.click(".ps-next")
    route = _wait(page, held)
    state = _spinning(page)
    assert state["spin"] and state["text"] == "Creating…"
    route.fulfill(status=status, json=answer)
    page.wait_for_selector(then)
    page.wait_for_function("() => !document.querySelector('.ps-next .mi-spin')", polling=30, timeout=3000)
    assert _idle(page)["held"] is False
    assert _idle(page)["text"] == ("Next" if status == 200 else "Create profile")


def _at_signin(page):
    _wizard(page)
    _pick(page, "OpenAI Codex")
    page.wait_for_selector(".pw-connect .project-starter-submit")
    return ".pw-connect .project-starter-submit"


def test_sign_in_spins_through_start_and_approval_then_lets_go(real_2x):
    page = real_2x
    button = _at_signin(page)
    label = page.inner_text(button)
    held = _hold(page, "**/api/profiles/oauth/start")
    polls = _hold(page, "**/api/profiles/oauth/poll*")
    page.click(button)
    route = _wait(page, held)
    assert _spinning(page, button)["text"] == "Starting sign-in…" and _spinning(page, button)["spin"]
    route.fulfill(json={"status": "pending", "flow_id": "f1", "verification_uri": "https://example.test/a", "user_code": "AB-CD", "poll_interval_seconds": 2})
    page.wait_for_selector(".ps-setup-steps")
    assert _spinning(page, button)["text"] == "Waiting for approval…" and _spinning(page, button)["spin"]
    assert page.locator(".ps-setup-wait").count() == 0
    _wait(page, polls).fulfill(json={"status": "expired"})
    page.wait_for_function("(b) => !document.querySelector(b).querySelector('.mi-spin')", arg=button, polling=30, timeout=3000)
    assert _idle(page, button) == {"spin": False, "text": label, "held": False}
    assert not page.is_disabled(button) and "expired" in page.inner_text(".ps-setup-flow")


def test_a_sign_in_that_cannot_start_lets_go(real_2x):
    page = real_2x
    button = _at_signin(page)
    label = page.inner_text(button)
    page.route("**/api/profiles/oauth/start", lambda route: route.fulfill(status=500, json={"error": "No browser"}))
    page.click(button)
    page.wait_for_function("(b) => !document.querySelector(b).querySelector('.mi-spin') && !document.querySelector(b).disabled", arg=button, polling=30, timeout=3000)
    assert _idle(page, button) == {"spin": False, "text": label, "held": False}
    assert "No browser" in page.inner_text(".ps-setup-flow")
