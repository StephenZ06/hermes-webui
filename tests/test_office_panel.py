"""Structure tests for the Office panel (phase 1 of the office visualization).

Phase 1 ships the plumbing, not the picture: a vendored three.js, an import
map, a new `office` main-view panel, and a WebGL scene whose render loop and
GPU context are released the moment the panel is left. Every one of those is a
source-structure invariant that silently bricks the panel when broken, with no
console error to point at — the same failure class
test_agent_canvas_script_order.py guards for Agent Canvas:

* An import map placed after any `<script type="module">` is ignored for the
  modules that already started resolving, so the bare "three" specifier fails
  and the panel is blank.
* A missing `showing-office` exclusion on the chat-default selector shows the
  chat view stacked underneath the office view.
* A missing unmount hook leaks a WebGL context per panel visit until the
  browser's context cap is hit and every later mount draws nothing.

See docs/rfcs/office-visualization.md.
"""
import pathlib
import re

REPO = pathlib.Path(__file__).parent.parent
INDEX_HTML = (REPO / "static" / "index.html").read_text(encoding="utf-8")
CSS = (REPO / "static" / "style.css").read_text(encoding="utf-8")
PANELS_JS = (REPO / "static" / "panels.js").read_text(encoding="utf-8")
OFFICE_INDEX_JS = (REPO / "static" / "office" / "index.js").read_text(encoding="utf-8")
OFFICE_SCENE_JS = (REPO / "static" / "office" / "scene.js").read_text(encoding="utf-8")
ESLINT_CONFIG = (REPO / "eslint.runtime-guard.config.mjs").read_text(encoding="utf-8")

THREE_PATH = "static/vendor/three/0.185.1/three.module.min.js"


# ── vendored three.js ────────────────────────────────────────────────────────

def test_three_is_vendored_at_the_pinned_version():
    vendored = REPO / THREE_PATH
    assert vendored.is_file(), (
        f"expected three.js vendored at {THREE_PATH} — this app has no bundler, "
        "so the office modules resolve three from the repo, not a CDN"
    )
    # Sanity floor: the real r185 module build is ~360KB. A truncated or
    # error-page download would sail past a mere existence check.
    assert vendored.stat().st_size > 200_000


def test_three_core_chunk_is_vendored_alongside_the_module_build():
    # r185's module build is split: three.module.min.js re-exports from
    # three.core.min.js. Vendoring only the entry file 404s at load time and
    # the panel goes silently blank — this cost a debugging round on the
    # first phase-1 browser check.
    core = REPO / "static" / "vendor" / "three" / "0.185.1" / "three.core.min.js"
    assert core.is_file(), "three.module.min.js imports ./three.core.min.js"
    assert core.stat().st_size > 200_000
    module_src = (REPO / THREE_PATH).read_text(encoding="utf-8", errors="ignore")
    assert "three.core.min.js" in module_src, (
        "if a future three.js bump stops splitting the build, drop this test "
        "rather than vendoring a file nothing imports"
    )


def test_vendored_three_carries_its_mit_licence():
    assert (REPO / "static" / "vendor" / "three" / "0.185.1" / "LICENSE.md").is_file(), (
        "vendored dependencies keep their licence alongside them "
        "(see static/vendor/motion/13.1.1/LICENSE.md)"
    )


# ── import map ───────────────────────────────────────────────────────────────

def test_import_map_maps_three_to_the_vendored_file():
    start = INDEX_HTML.index('<script type="importmap">')
    end = INDEX_HTML.index("</script>", start)
    block = INDEX_HTML[start:end]
    assert '"three"' in block, "the import map must define the bare 'three' specifier"
    assert THREE_PATH in block, f"'three' must resolve to {THREE_PATH}"
    # Import-map values must be absolute or start with / ./ ../ — a bare
    # "static/..." is rejected outright by the browser, taking the whole map
    # (and therefore the panel) down with it.
    assert f'"./{THREE_PATH}"' in block


def test_import_map_precedes_every_module_script():
    # Comments are blanked (not removed) so offsets still line up with the
    # real file — several comments here quote script tags verbatim.
    html = re.sub(r"<!--.*?-->", lambda m: " " * len(m.group(0)), INDEX_HTML, flags=re.S)
    map_at = html.index('<script type="importmap">')
    module_positions = [m.start() for m in re.finditer(r'<script\s+type="module"', html)]
    assert module_positions, "expected at least one module script in index.html"
    assert map_at < min(module_positions), (
        "the import map must appear before every <script type=\"module\">: it is "
        "consulted at module-resolution time, so a module graph that starts "
        "loading first resolves 'three' against nothing and the office panel "
        "goes blank with no console error"
    )


def test_office_entry_module_is_loaded_from_index_html():
    assert '<script type="module" src="static/office/index.js' in INDEX_HTML


# ── panel registration ───────────────────────────────────────────────────────

def test_office_is_a_main_view_panel():
    line = next(l for l in PANELS_JS.splitlines() if l.startswith("const MAIN_VIEW_PANELS"))
    assert "'office'" in line, (
        "without an entry in MAIN_VIEW_PANELS, switchPanel() never puts the "
        "showing-office class on <main> and the panel never becomes visible"
    )


def test_rail_and_sidebar_nav_both_expose_the_office_tab():
    rail_start = INDEX_HTML.index('<nav class="rail"')
    rail_end = INDEX_HTML.index("</nav>", rail_start)
    assert 'data-panel="office"' in INDEX_HTML[rail_start:rail_end]

    nav_start = INDEX_HTML.index('<div class="sidebar-nav">')
    nav_end = INDEX_HTML.index('data-panel="settings"', nav_start)
    assert 'data-panel="office"' in INDEX_HTML[nav_start:nav_end], (
        "the mobile sidebar-nav mirrors the rail; a tab present in only one "
        "is unreachable on the other form factor"
    )


def test_office_main_view_and_sidebar_panel_exist():
    assert 'id="mainOffice"' in INDEX_HTML
    assert 'id="officeWrap"' in INDEX_HTML, "the scene mounts into #officeWrap"
    # switchPanel does $('panel' + capitalize(name)); a missing panel-view
    # leaves the whole sidebar blank for this panel (see
    # test_nav_dividers_and_agent_canvas_panel.py).
    assert 'id="panelOffice"' in INDEX_HTML


def test_panel_switch_mounts_and_unmounts_the_office():
    assert "window.HermesOffice.mount($('officeWrap'))" in PANELS_JS
    assert "prevPanel === 'office'" in PANELS_JS and "HermesOffice.unmount()" in PANELS_JS, (
        "leaving the panel must release the WebGL context — browsers cap live "
        "contexts per page, and flipping in and out would exhaust that cap"
    )


# ── CSS visibility ───────────────────────────────────────────────────────────

def test_office_main_view_css_shows_and_hides_with_the_panel():
    assert "main.main > #mainOffice{display:none;}" in CSS
    assert "main.main.showing-office > #mainOffice{display:flex;}" in CSS


def test_chat_default_selector_excludes_the_office():
    selector = next(l for l in CSS.splitlines() if "> #mainChat{display:flex;}" in l)
    assert ":not(.showing-office)" in selector, (
        "the chat view is the default main view, shown by a chain of :not() "
        "exclusions; without office in that chain, chat renders underneath it"
    )


# ── scene lifecycle ──────────────────────────────────────────────────────────

def test_office_entry_publishes_the_global_the_panel_calls():
    assert "window.HermesOffice = {" in OFFICE_INDEX_JS
    for name in ("mount", "unmount"):
        assert name in OFFICE_INDEX_JS


def test_scene_caps_pixel_ratio():
    assert "setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))" in OFFICE_SCENE_JS, (
        "uncapped DPR on a 3x display quadruples fragment cost for no visible "
        "gain and is the quickest way to make this panel drop frames"
    )


def test_scene_dispose_releases_gpu_resources_and_the_context():
    dispose_at = OFFICE_SCENE_JS.index("function dispose()")
    body = OFFICE_SCENE_JS[dispose_at:]
    assert "renderer.dispose()" in body
    assert "forceContextLoss()" in body
    assert "g.dispose()" in body and "m.dispose()" in body, (
        "geometries and materials are not freed by renderer.dispose()"
    )


def test_the_spoken_summary_is_not_deduped_across_a_remount():
    # renderSummary skips writing when the text has not changed, because
    # aria-live re-announces on every write. mount() builds a brand-new
    # element, so the guard has to be cleared or a remount whose state has not
    # moved leaves the summary empty.
    mount_at = OFFICE_INDEX_JS.index("function mount(container)")
    body = OFFICE_INDEX_JS[mount_at:OFFICE_INDEX_JS.index("\n}\n", mount_at)]
    assert "_lastSummary = ''" in body


def test_render_loop_stops_when_the_tab_is_hidden():
    assert "visibilitychange" in OFFICE_INDEX_JS
    assert "document.hidden" in OFFICE_INDEX_JS


# ── lint gate ────────────────────────────────────────────────────────────────

def test_runtime_lint_parses_office_modules_as_esm():
    assert '"static/office/**/*.js"' in ESLINT_CONFIG, (
        "static/office/* are the app's only first-party ES modules; parsed as "
        "'script' their import/export statements are syntax errors and the "
        "whole runtime-lint gate fails"
    )
    office_at = ESLINT_CONFIG.index('"static/office/**/*.js"')
    assert 'sourceType: "module"' in ESLINT_CONFIG[office_at:]
