"""Cold loads, the usage card, toasts over modals, delete motion, and the provider wizard."""

import io
import math
from pathlib import Path

import pytest
from PIL import Image

from tests.test_chat_optical_alignment_browser import _rect, browser, pytestmark, real_2x  # noqa: F401
from tests.test_office_notes_workhub_nudges_browser import _panel
from tests.test_pages_round11_browser import _open
from tests.test_pages_round12_browser import _files_fixture

ICONS = Path(__file__).resolve().parents[1] / "static" / "provider-icons"


# ── Cold load ─────────────────────────────────────────────────────────────

def _no_worker(page):
    """A page's requests go through the service worker, out of the test's reach."""
    page.evaluate("async () => { for (const r of await navigator.serviceWorker.getRegistrations()) await r.unregister(); }")


def _hold_boot(page):
    _no_worker(page)
    held = []
    page.route("**/static/boot.js*", lambda route: held.append(route))
    return held


def test_a_cold_load_shows_no_page_until_boot_has_put_the_right_one_back(real_2x):
    page = real_2x
    _panel(page, "dashboard")
    held = _hold_boot(page)
    page.reload(wait_until="commit")
    page.wait_for_function("() => !!document.querySelector('main.main > .main-view')", polling=50)
    page.wait_for_timeout(500)
    while_loading = page.evaluate("""() => ({
      main: getComputedStyle(document.getElementById('mainChat')).visibility,
      side: [...document.querySelectorAll('.sidebar .panel-view')].filter(el => getComputedStyle(el).display !== 'none').map(el => getComputedStyle(el).visibility),
      entrances: document.getAnimations().filter(a => a.animationName === 'page-view-in').length})""")
    assert while_loading == {"main": "hidden", "side": ["hidden"], "entrances": 0}
    assert held, "boot.js was not requested"
    held[0].continue_()
    page.wait_for_function("() => !document.documentElement.classList.contains('boot-gate')", polling=50, timeout=15000)
    assert page.evaluate("""() => getComputedStyle(document.getElementById('mainDashboard')).visibility""") == "visible"
    assert page.evaluate("""() => getComputedStyle(document.getElementById('mainChat')).display""") == "none"


def test_the_page_is_not_lost_when_boot_never_finishes(real_2x):
    page = real_2x
    _no_worker(page)
    page.route("**/static/boot.js*", lambda route: route.abort())
    page.reload(wait_until="commit")
    page.wait_for_function("() => !!document.documentElement && !document.documentElement.classList.contains('boot-gate') && !!document.getElementById('mainChat')",
                           polling=100, timeout=7000)
    assert page.evaluate("() => getComputedStyle(document.getElementById('mainChat')).visibility") == "visible"


def test_dashboard_effects_start_one_at_a_time(real_2x):
    page = real_2x
    page.evaluate("""() => {
      window.__held = []; window.__mounts = [];
      window.requestIdleCallback = (fn) => { window.__held.push(fn); return 1; };
      const handle = {unmount() {}, update() {}};
      window.loadLibrariesDev = async () => ({
        mount: (el, kind) => { window.__mounts.push(kind); return handle; },
        wrap: (el, kind) => { window.__mounts.push(kind); return handle; },
        isMetalFxSupported: () => false,
      });
    }""")
    _panel(page, "dashboard")
    page.wait_for_function("() => window.__held.length > 0", polling=50, timeout=15000)
    assert page.evaluate("() => window.__mounts.length") == 0
    page.evaluate("() => window.__held.shift()()")
    page.wait_for_timeout(100)
    assert page.evaluate("() => window.__mounts.length") == 1


# ── Session usage card ────────────────────────────────────────────────────

def _usage(page, payload):
    page.unroute("**/api/account_usage*")
    page.route("**/api/account_usage*", lambda route: route.fulfill(json=payload))
    page.evaluate("() => loadAccountUsage('x')")
    page.wait_for_timeout(450)


def test_a_local_model_gets_the_card_with_only_unlimited(real_2x):
    page = real_2x
    page.route("**/api/account_usage*", lambda route: route.fulfill(json={}))
    _panel(page, "chat")
    _usage(page, {"available": False, "provider": "lmstudio", "local": True})
    card = page.evaluate("""() => { const w = document.getElementById('chatUsageWidget'), on = (id) => {
        const el = document.getElementById(id); return !!(el && el.getClientRects().length); };
      return {hidden: w.hidden, text: w.innerText.trim().replace(/\\s+/g, ' '), meter: on('chatUsageWidgetBattery'), plan: on('chatUsageWidgetPlan'),
        percent: on('chatUsageWidgetPercent'), reset: on('chatUsageWidgetReset'), toggle: on('chatUsageWidgetWindowToggle')}; }""")
    assert card == {"hidden": False, "text": "SESSION USAGE UNLIMITED", "meter": False, "plan": False,
                    "percent": False, "reset": False, "toggle": False}


def test_the_meter_comes_back_on_a_profile_with_a_quota(real_2x):
    page = real_2x
    page.route("**/api/account_usage*", lambda route: route.fulfill(json={}))
    _panel(page, "chat")
    _usage(page, {"available": False, "provider": "lmstudio", "local": True})
    _usage(page, {"available": True, "provider": "9router-claude", "plan": "Claude via 9router",
                  "windows": [{"label": "5 hours", "used_percent": 35, "reset_at": None, "detail": None},
                              {"label": "Weekly", "used_percent": 69, "reset_at": None, "detail": None}]})
    card = page.evaluate("""() => { const on = (id) => !!document.getElementById(id).getClientRects().length;
      return {meter: on('chatUsageWidgetBattery'), unlimited: on('chatUsageWidgetUnlimited'),
        text: document.getElementById('chatUsageWidget').innerText}; }""")
    assert card["meter"] and not card["unlimited"]
    assert "UNLIMITED" not in card["text"] and "Claude via 9router" in card["text"]


# ── Toasts over modals ────────────────────────────────────────────────────

@pytest.mark.parametrize("open_modal", [
    "showConfirmDialog({title: 'Sure?', message: 'Really'})",
    "document.body.insertAdjacentHTML('beforeend', '<div id=\"wikiBrowserOverlay\" style=\"position:fixed;inset:0;z-index:9999;background:#000\"></div>')",
    "document.body.insertAdjacentHTML('beforeend', '<div class=\"project-starter-overlay\" style=\"opacity:1\"></div>')",
    "document.body.insertAdjacentHTML('beforeend', '<div class=\"img-lightbox\" style=\"position:fixed;inset:0;background:#000\"></div>')",
])
def test_a_toast_shows_over_a_modal(real_2x, open_modal):
    page = real_2x
    page.evaluate(f"() => {{ {open_modal}; showToast('Saved', 8000); }}")
    page.wait_for_timeout(450)
    on_top = page.evaluate("""() => { const t = document.getElementById('toast'), r = t.getBoundingClientRect();
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return t === hit || t.contains(hit); }""")
    assert on_top


def test_no_layer_on_the_page_is_above_a_toast(real_2x):
    page = real_2x
    top = page.evaluate("""() => { const toast = Number(getComputedStyle(document.getElementById('toast')).zIndex); let max = 0;
      for (const sheet of document.styleSheets) { let rules; try { rules = sheet.cssRules; } catch (_) { continue; }
        for (const rule of rules) { const z = rule.style && Number(rule.style.zIndex); if (z && !/toast/.test(rule.selectorText) && z > max) max = z; } }
      return {toast, max}; }""")
    assert top["toast"] > top["max"]


# ── Delete motion ─────────────────────────────────────────────────────────

DELETES = [
    ("deleteMemoryEntry(3)", '<div class="memory-entry-card" data-entry-index="3"></div>', "**/api/memory/entry/delete"),
    ("deleteProfile('zz')", '<div class="profile-card" data-name="zz"></div>', "**/api/profile/delete"),
    ("deleteKanbanCrew('c1')", '<article class="kanban-crew-card" data-crew-id="c1"></article>', "**/api/crews/delete"),
    ("archiveKanbanTaskFromDetail('t1')", '<article class="kanban-card" data-kanban-task-id="t1"></article>', "**/api/kanban/tasks/t1*"),
    ("updateKanbanTask('t1', {status: 'archived'}, {openDetail: false})", '<article class="kanban-card" data-kanban-task-id="t1"></article>', "**/api/kanban/tasks/t1*"),
    ("_confirmDeleteProject({project_id: 'p1', name: 'P'})", '<div class="project-chip" data-project-id="p1"></div>', "**/api/projects/delete"),
    ("_deleteStickyBoard({id: 'b1', name: 'B'})", '<button class="sticky-board-row" data-board-id="b1"></button>', "**/api/sticky_boards/delete"),
    ("(_currentSkillDetail = {name: 'sk'}, deleteCurrentSkill())", '<div class="skill-item" data-skill-name="sk"></div>', "**/api/skills/delete"),
    ("(S.session = S.session || {session_id: 'x'}, deleteWorkspaceFile('a/b.md', 'b.md'))", '<div class="file-item" data-ws-path="a/b.md"></div>', "**/api/file/delete"),
    ("(S.session = S.session || {session_id: 'x'}, deleteWorkspaceDir('a', 'a'))", '<div class="file-item" data-ws-path="a"></div>', "**/api/file/delete"),
    ("_archiveSession({session_id: 'gone'}, true)", '<div class="session-item" data-sid="gone"></div>', "**/api/session/archive"),
]


def _spy_on_removal(page, row):
    page.evaluate("""(row) => { window.showConfirmDialog = async () => true;
      document.body.insertAdjacentHTML('beforeend', `<div id="__rows">${row}</div>`);
      window.__removed = []; window.animateRemoval = async (el) => { if (el) window.__removed.push(el.outerHTML); }; }""", row)


@pytest.mark.parametrize("call,row,url", DELETES, ids=[d[0][:24] for d in DELETES])
def test_a_deleted_row_leaves_with_motion(real_2x, call, row, url):
    page = real_2x
    page.route(url, lambda route: route.fulfill(json={"ok": True, "session": {"session_id": "gone"}}))
    _spy_on_removal(page, row)
    page.evaluate(f"async () => {{ try {{ await {call}; }} catch (_) {{}} }}")
    assert page.evaluate("() => window.__removed") == [row]


def test_a_delete_the_server_refused_leaves_the_row_alone(real_2x):
    page = real_2x
    page.route("**/api/memory/entry/delete", lambda route: route.fulfill(status=500, json={"error": "no"}))
    _spy_on_removal(page, '<div class="memory-entry-card" data-entry-index="3"></div>')
    page.evaluate("async () => { await deleteMemoryEntry(3); }")
    assert page.evaluate("() => window.__removed") == []


def test_a_file_deleted_from_the_files_page_leaves_with_motion(real_2x):
    page = real_2x
    _files_fixture(page)
    page.route("**/api/file-manager/delete", lambda route: route.fulfill(json={"ok": True}))
    page.route("**/api/file-manager/read*", lambda route: route.fulfill(json={"path": "note.md", "kind": "text", "text": "hello", "content": "hello", "size": 5}))
    _open(page, "files", ".files-row")
    _spy_on_removal(page, "")
    page.click('.files-row[data-file-path="note.md"]')
    page.wait_for_selector('[data-action="delete"]', timeout=5000)
    page.click('[data-action="delete"]')
    page.wait_for_function("() => window.__removed.length > 0", polling=50, timeout=5000)
    assert 'data-file-path="note.md"' in page.evaluate("() => window.__removed[0]")


# ── New profile wizard ────────────────────────────────────────────────────

PROVIDERS = {
    "signins": [{"id": "openai-codex", "label": "OpenAI Codex", "signed_in": False}, {"id": "anthropic", "label": "Claude", "signed_in": False}],
    "api_keys": [{"id": i, "label": label, "env_var": "X_KEY", "has_key": False} for i, label in (
        ("openrouter", "OpenRouter"), ("opencode-go", "OpenCode Go"), ("opencode-zen", "OpenCode Zen"), ("anthropic", "Anthropic"),
        ("openai", "OpenAI"), ("deepseek", "DeepSeek"), ("google", "Google"), ("x-ai", "xAI"), ("nvidia", "NVIDIA NIM"))],
    "presets": [{"id": "9router", "name": "9Router", "base_url": "http://localhost:20128/v1", "needs_key": True},
                {"id": "lmstudio", "name": "LM Studio", "base_url": "http://localhost:1234/v1", "needs_key": False},
                {"id": "ollama", "name": "Ollama", "base_url": "http://localhost:11434/v1", "needs_key": False},
                {"id": "custom", "name": "Other OpenAI-compatible", "base_url": "", "needs_key": True}],
    "endpoints": [], "fallbacks": [],
}
LOGOS = {"OpenAI Codex": "openai", "Claude": "anthropic", "OpenRouter": "openrouter", "OpenCode Go": "opencode", "OpenCode Zen": "opencode",
         "Anthropic": "anthropic", "OpenAI": "openai", "DeepSeek": "deepseek", "Google": "gemini", "xAI": "xai", "9Router": "9router",
         "LM Studio": "lmstudio", "Ollama": "ollama", "Other OpenAI-compatible": "openai"}


def _wizard(page, answers=None):
    """The wizard on mocked provider routes; every POST is recorded by its last path part."""
    posts = []

    def provider_post(route):
        action = route.request.url.rsplit("/", 1)[-1]
        posts.append((action, route.request.post_data_json))
        route.fulfill(json=(answers or {}).get(action, {"ok": True, "provider": "custom:x", "id": "x", "models": ["m1"]}))

    page.route("**/api/profiles/providers?*", lambda route: route.fulfill(json=PROVIDERS))
    page.route("**/api/profiles/providers/*", provider_post)
    page.route("**/api/profiles/oauth/start", lambda route: (posts.append(("oauth", route.request.post_data_json)),
                                                               route.fulfill(json={"status": "success"}))[1])
    page.evaluate("() => { window.__wizard = openProviderWizard('default', {}); }")
    page.wait_for_selector(".pw-choice")
    page.wait_for_timeout(600)
    return posts


def _pick(page, label):
    page.click(f'.pw-choice:has(.ps-template-label:text-is("{label}"))')
    page.click(".ps-next")


def test_every_named_provider_shows_its_logo_on_a_white_tile(real_2x):
    page = real_2x
    _wizard(page)
    tiles = page.evaluate("""() => [...document.querySelectorAll('.pw-choice')].map(card => { const tile = card.querySelector('.ps-template-icon'),
        logo = tile.querySelector('img'), style = getComputedStyle(tile); return {label: card.querySelector('.ps-template-label').textContent,
        logo: logo ? logo.getAttribute('src').split('/').pop().replace('.png', '') : null, loaded: !!(logo && logo.naturalWidth),
        ground: style.backgroundColor, size: logo ? logo.getBoundingClientRect().width : 0}; })""")
    shown = {t["label"]: t["logo"] for t in tiles}
    assert {k: shown[k] for k in LOGOS} == LOGOS
    assert all(t["ground"] == "rgb(255, 255, 255)" for t in tiles)
    assert all(t["loaded"] and t["size"] == 22 for t in tiles if t["logo"])


def test_a_provider_without_a_logo_keeps_a_line_icon_that_shows_on_white(real_2x):
    page = real_2x
    _wizard(page)
    page.click(".pw-more")
    page.wait_for_timeout(200)
    colour = page.evaluate("""() => { const card = [...document.querySelectorAll('.pw-choice')].find(c => c.textContent.includes('NVIDIA'));
      return card && card.querySelector('svg') ? getComputedStyle(card.querySelector('.ps-template-icon')).color : null; }""")
    assert colour == "rgb(28, 28, 28)"


def test_the_logos_read_as_one_size():
    sizes = {}
    for path in ICONS.glob("*.png"):
        image = Image.open(path).convert("RGBA")
        assert image.size == (88, 88)
        alpha = image.getchannel("A")
        box = alpha.point(lambda v: 255 if v > 16 else 0).getbbox()
        width, height = box[2] - box[0], box[3] - box[1]
        ink = sum(1 for v in alpha.crop(box).tobytes() if v > 128)
        sizes[path.stem] = math.sqrt(math.sqrt(width * height) * math.sqrt(ink))
        # Centred in its box, so tiles line up.
        assert abs(box[0] - (88 - box[2])) <= 1 and abs(box[1] - (88 - box[3])) <= 1, path.stem
    assert len(sizes) == 10
    assert max(sizes.values()) / min(sizes.values()) <= 1.2, sizes


def test_a_rejected_key_is_not_saved_and_the_step_stays(real_2x):
    page = real_2x
    posts = _wizard(page, {"verify": {"state": "rejected", "message": "OpenAI rejected this key. Check it and try again."}})
    _pick(page, "OpenAI")
    page.fill(".pw-key", "bad-key")
    page.click(".ps-next")
    page.wait_for_selector(".pw-check.is-error")
    assert "rejected this key" in page.inner_text(".pw-check")
    assert [p[0] for p in posts] == ["verify"]
    assert page.is_visible(".pw-key") and page.is_disabled(".ps-next")
    page.fill(".pw-key", "better-key")
    assert page.inner_text(".pw-check") == "" and not page.is_disabled(".ps-next")


def test_a_key_that_could_not_be_checked_is_saved_only_when_asked(real_2x):
    page = real_2x
    posts = _wizard(page, {"verify": {"state": "unknown", "message": "Couldn't reach OpenAI to check the key (URLError)."}})
    _pick(page, "OpenAI")
    page.fill(".pw-key", "maybe-key")
    page.click(".ps-next")
    page.wait_for_selector(".pw-check.is-warn")
    assert page.inner_text(".ps-next") == "Save anyway"
    assert "key" not in [p[0] for p in posts]
    page.click(".ps-next")
    page.wait_for_selector(".pw-models,.pw-model-search")
    assert [p[0] for p in posts][:2] == ["verify", "key"]


def test_a_good_key_goes_straight_on(real_2x):
    page = real_2x
    posts = _wizard(page, {"verify": {"state": "ok", "message": "OpenAI accepted the key."}})
    _pick(page, "OpenAI")
    page.fill(".pw-key", "good-key")
    page.click(".ps-next")
    page.wait_for_selector(".pw-model-search")
    assert [p[0] for p in posts][:2] == ["verify", "key"]
    assert posts[1][1]["api_key"] == "good-key"


def test_an_endpoint_is_checked_before_it_is_saved(real_2x):
    page = real_2x
    posts = _wizard(page, {"verify": {"state": "rejected", "message": "The endpoint answered HTTP 401. Check the API key."}})
    _pick(page, "9Router")
    page.fill(".pw-ep-key", "bad-key")
    page.click(".ps-next")
    page.wait_for_selector(".pw-check.is-error")
    assert [p[0] for p in posts] == ["verify"]
    assert posts[0][1]["base_url"] == "http://localhost:20128/v1"


def test_a_local_server_that_is_off_can_be_saved_for_later(real_2x):
    page = real_2x
    posts = _wizard(page, {"verify": {"state": "unknown", "message": "Couldn't reach http://localhost:1234/v1 (URLError). Is it running?"}})
    _pick(page, "LM Studio")
    page.click(".ps-next")
    page.wait_for_selector(".pw-check.is-warn")
    page.click(".ps-next")
    page.wait_for_selector(".pw-model-search")
    assert "endpoint" in [p[0] for p in posts]


def test_sign_in_names_the_provider_chosen(real_2x):
    page = real_2x
    posts = _wizard(page)
    _pick(page, "OpenAI Codex")
    page.click(".pw-connect .project-starter-submit")
    page.wait_for_function("() => !document.querySelector('.ps-next').disabled", polling=50)
    assert ("oauth", {"name": "default", "provider": "openai-codex"}) in posts


def test_the_whole_way_through_to_done(real_2x):
    page = real_2x
    posts = _wizard(page, {"verify": {"state": "ok", "message": "OpenAI accepted the key."},
                           "models": {"ok": True, "models": ["gpt-a", "gpt-b"]},
                           "test": {"ok": True, "message": "OpenAI accepted the key."}})
    _pick(page, "OpenAI")
    page.fill(".pw-key", "good-key")
    page.click(".ps-next")
    page.wait_for_selector(".pw-model")
    page.click('.pw-model:text-is("gpt-b")')
    page.click(".ps-next")
    page.wait_for_selector(".pw-use")
    page.click(".ps-next")
    page.wait_for_selector(".pw-result.is-ok")
    assert "All set" in page.inner_text(".pw-result")
    page.click(".ps-next")
    page.wait_for_function("() => !document.querySelector('.pw-wizard')", polling=50, timeout=3000)
    assert [p[0] for p in posts] == ["verify", "key", "models", "main", "test"]
