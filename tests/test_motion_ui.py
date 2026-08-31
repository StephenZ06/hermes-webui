"""Coverage for the Motion-based UI motion layer.

The app has no bundler and no React, so Motion is vendored as its UMD build and
loaded as a classic script alongside d3-force. static/motion-ui.js is the only
thing that talks to it, and every helper degrades to a no-op when Motion is
absent or the viewer asked for reduced motion -- nothing in the app may depend
on an animation having run.

These tests pin the properties that are easy to regress by accident: the
reduced-motion gate, transform/opacity-only animation, the interaction duration
budget, and the accessibility ordering around the dropdown exit.
"""
import pathlib
import re
import shutil
import subprocess

import pytest


REPO_ROOT = pathlib.Path(__file__).parent.parent
MOTION_UI_JS = (REPO_ROOT / "static" / "motion-ui.js").read_text(encoding="utf-8")
INDEX_HTML = (REPO_ROOT / "static" / "index.html").read_text(encoding="utf-8")
SW_JS = (REPO_ROOT / "static" / "sw.js").read_text(encoding="utf-8")
STYLE_CSS = (REPO_ROOT / "static" / "style.css").read_text(encoding="utf-8")
PANELS_JS = (REPO_ROOT / "static" / "panels.js").read_text(encoding="utf-8")
UI_JS = (REPO_ROOT / "static" / "ui.js").read_text(encoding="utf-8")
WORKSPACE_JS = (REPO_ROOT / "static" / "workspace.js").read_text(encoding="utf-8")
VENDOR_DIR = REPO_ROOT / "static" / "vendor" / "motion" / "13.1.1"
NODE = shutil.which("node")


class TestVendoring:
    def test_motion_is_vendored_with_its_licence(self):
        assert (VENDOR_DIR / "motion.min.js").is_file()
        assert (VENDOR_DIR / "LICENSE.md").is_file()

    def test_bundle_is_the_umd_build(self):
        # A UMD bundle attaches to the global and loads as a classic script, so
        # no module graph or bundler is introduced. An ESM-only build would not
        # work here.
        head = (VENDOR_DIR / "motion.min.js").read_text(encoding="utf-8")[:400]
        assert "define.amd" in head and "Motion" in head

    def test_scripts_are_loaded_in_dependency_order(self):
        vendor = INDEX_HTML.index("vendor/motion/13.1.1/motion.min.js")
        helper = INDEX_HTML.index("static/motion-ui.js")
        assert vendor < helper, "motion-ui.js reads the Motion global at load time"
        assert 'src="static/vendor/motion/13.1.1/motion.min.js" defer' in INDEX_HTML

    def test_both_files_are_precached_by_the_service_worker(self):
        assert "./static/vendor/motion/13.1.1/motion.min.js" in SW_JS
        assert "./static/motion-ui.js" in SW_JS


class TestReducedMotion:
    def test_every_helper_is_gated_on_the_same_check(self):
        assert "prefers-reduced-motion: reduce" in MOTION_UI_JS
        for helper in ("function enter(", "function presence(", "function lift(", "function listChange("):
            start = MOTION_UI_JS.index(helper)
            body = MOTION_UI_JS[start : start + 900]
            assert "enabled()" in body, f"{helper} must consult the motion gate"

    def test_gate_covers_a_missing_library_too(self):
        fn = MOTION_UI_JS[MOTION_UI_JS.index("function enabled()") :]
        fn = fn[: fn.index("\n  }")]
        assert "motionLib()" in fn and "prefersReducedMotion()" in fn

    def test_hero_shimmer_has_a_css_fallback_for_reduced_motion(self):
        block = STYLE_CSS[STYLE_CSS.index(".motion-text-shimmer{") :]
        block = block[: block.index("/* Sidebar Project folder binding")]
        assert "@media (prefers-reduced-motion:reduce)" in block
        assert "-webkit-text-fill-color:currentColor" in block


class TestPerformanceConstraints:
    def test_only_transform_and_opacity_are_animated(self):
        # background-position is the single documented exception, for the hero
        # text shimmer; it is masked to glyphs and triggers no layout.
        animated = set(re.findall(r"\{\s*(opacity|transform|backgroundPosition)\s*:", MOTION_UI_JS))
        assert animated <= {"opacity", "transform", "backgroundPosition"}
        for banned in ("width:", "height:", "top:", "left:", "margin"):
            call_sites = re.findall(r"M\.animate\([^;]*?" + re.escape(banned), MOTION_UI_JS, re.S)
            assert not call_sites, f"{banned} would trigger layout on every frame"

    def test_interaction_durations_stay_inside_the_budget(self):
        durations = re.search(r"const DUR = \{([^}]*)\}", MOTION_UI_JS).group(1)
        values = [float(v) for v in re.findall(r":\s*([0-9.]+)", durations)]
        assert values, "DUR table must define the interaction durations"
        for v in values:
            assert 0.15 <= v <= 0.35, f"{v}s is outside the 150-350ms interaction budget"

    def test_hero_effect_is_the_only_thing_above_the_budget(self):
        hero = MOTION_UI_JS[MOTION_UI_JS.index("function shimmerHeading") :]
        hero = hero[: hero.index("\n  function animateEmptyState")]
        assert "duration: 1.1" in hero
        assert "1.1s" in MOTION_UI_JS or "1.1" in hero  # documented in the comment

    def test_entrances_clear_their_inline_styles(self):
        # Leaving transform/opacity inline would freeze the element's own hover
        # and active CSS for the rest of the session.
        assert "function clearInline" in MOTION_UI_JS
        enter_fn = MOTION_UI_JS[MOTION_UI_JS.index("function enter(") :]
        enter_fn = enter_fn[: enter_fn.index("\n  /**")]
        assert "clearInline" in enter_fn

    def test_long_lists_do_not_stagger_forever(self):
        enter_fn = MOTION_UI_JS[MOTION_UI_JS.index("function enter(") :]
        enter_fn = enter_fn[: enter_fn.index("\n  /**")]
        assert "slice(0, 12)" in enter_fn


class TestAccessibilityAndBehaviour:
    def test_dropdown_exit_never_delays_inert_or_aria(self):
        fn = PANELS_JS[PANELS_JS.index("function _setWorkspaceDropdownOpenState") :]
        fn = fn[: fn.index("\nfunction ")]
        inert_at = fn.index("setAttribute('inert'")
        anim_at = fn.index("MotionUI")
        assert inert_at < anim_at, (
            "a dismissed dropdown must leave the tab order immediately, not after an animation"
        )
        assert "dd.hidden=!open" in fn, "no-motion path must still hide synchronously"

    def test_dropdown_reopened_mid_exit_is_not_hidden(self):
        fn = PANELS_JS[PANELS_JS.index("function _setWorkspaceDropdownOpenState") :]
        fn = fn[: fn.index("\nfunction ")]
        assert "!dd.classList.contains('open')" in fn

    def test_toast_is_left_to_its_own_css(self):
        # .toast already animates opacity and transform with a .2s transition
        # and .toast.show flips both. A JS transform would outrank that rule,
        # be transitioned a second time on top of Motion, and slide the wrong
        # way -- the toast is anchored top-right, not bottom.
        # Scoped to showToast itself. ui.js as a whole does use the motion layer
        # now (the app dialog gets an entrance and an exit through
        # MotionUI.presence); it is specifically the toast that must not.
        start = UI_JS.index("function showToast(")
        end = UI_JS.find("\nfunction ", start + 1)
        toast = UI_JS[start:end if end != -1 else len(UI_JS)]
        assert "MotionUI" not in toast, "the toast must not be driven by the motion layer"
        assert ".toast{" in STYLE_CSS and "transition:opacity .2s,transform .2s" in STYLE_CSS

    def test_dropdown_exit_is_actually_painted(self):
        # .ws-dropdown is display:none without .open, and .open must come off
        # synchronously because toggleComposerWsDropdown() reads it. Without a
        # separate class the exit animation would run on a hidden element.
        assert ".ws-dropdown.is-leaving{display:block" in STYLE_CSS
        fn = PANELS_JS[PANELS_JS.index("function _setWorkspaceDropdownOpenState") :]
        fn = fn[: fn.index("\nfunction ")]
        assert "classList.add('is-leaving')" in fn
        assert "classList.remove('is-leaving')" in fn

    def test_no_lift_on_elements_that_already_transform_on_hover(self):
        # .suggestion:hover carries transform:translateX(2px) under
        # transition:all; a JS transform would win and cancel it.
        assert "MotionUI.lift('.empty-state .suggestion'" not in MOTION_UI_JS
        assert "lift" in MOTION_UI_JS  # the helper still exists for other targets

    def test_lift_hands_the_element_back_to_css(self):
        lift = MOTION_UI_JS[MOTION_UI_JS.index("function lift(") :]
        lift = lift[: lift.index("\n  /**")]
        assert "el.style.transform = ''" in lift, (
            "a lingering inline transform outranks any :hover/:active transform in CSS"
        )

    def test_css_transitions_are_suspended_during_js_animation(self):
        assert "function suspendTransition" in MOTION_UI_JS
        for helper in ("function enter(", "function presence("):
            start = MOTION_UI_JS.index(helper)
            assert "suspendTransition" in MOTION_UI_JS[start : start + 1600], helper
        clear = MOTION_UI_JS[MOTION_UI_JS.index("function clearInline") :]
        clear = clear[: clear.index("\n  }")]
        assert "el.style.transition = ''" in clear

    def test_binder_rows_do_not_re_animate_on_every_keystroke(self):
        assert "_projectBindLastAnimatedKey" in WORKSPACE_JS
        block = WORKSPACE_JS[WORKSPACE_JS.index("bindViewKey") :][:600]
        assert "!== _projectBindLastAnimatedKey" in block

    def test_hover_lift_binds_once_per_element(self):
        lift = MOTION_UI_JS[MOTION_UI_JS.index("function lift(") :]
        lift = lift[: lift.index("\n  /**")]
        assert "dataset.motionLift" in lift, "re-render must not stack duplicate gesture handlers"


@pytest.mark.skipif(NODE is None, reason="node not on PATH")
class TestRuntimeBehaviour:
    """Load motion-ui.js in a DOM-less sandbox and check the no-op contract."""

    def _run(self, script_body: str) -> str:
        harness = f"""
        const vm = require('vm');
        const fs = require('fs');
        const src = fs.readFileSync({str(REPO_ROOT / 'static' / 'motion-ui.js')!r}, 'utf8');
        const listeners = {{}};
        const ctx = {{
          console,
          document: {{
            readyState: 'complete',
            getElementById: () => null,
            querySelectorAll: () => [],
            addEventListener: () => {{}},
          }},
          MutationObserver: function(){{ this.observe = () => {{}}; }},
          // Always present in a browser; the sandbox has to supply it because
          // the helpers narrow their arguments with `instanceof Element`.
          Element: function Element(){{}},
        }};
        ctx.window = ctx;
        vm.createContext(ctx);
        vm.runInContext(src, ctx);
        {script_body}
        """
        proc = subprocess.run([NODE, "-e", harness], capture_output=True, text=True, check=True)
        return proc.stdout.strip()

    def test_helpers_exist_and_are_inert_without_motion(self):
        out = self._run(
            "process.stdout.write(JSON.stringify({"
            "  keys: Object.keys(ctx.window.MotionUI).sort(),"
            "  enabled: ctx.window.MotionUI.enabled()"
            "}));"
        )
        assert '"enabled":false' in out, "no Motion global means motion is off"
        for key in ("enter", "presence", "lift", "listChange", "enabled"):
            assert f'"{key}"' in out

    def test_helpers_resolve_rather_than_throw_when_disabled(self):
        out = self._run(
            "Promise.all(["
            "  ctx.window.MotionUI.enter('.nope'),"
            "  ctx.window.MotionUI.presence(null, 'in'),"
            "]).then(() => process.stdout.write('resolved'));"
        )
        assert out == "resolved"

    def test_lift_returns_a_cleanup_even_when_disabled(self):
        out = self._run(
            "const stop = ctx.window.MotionUI.lift('.nope');"
            "stop();"
            "process.stdout.write(typeof stop);"
        )
        assert out == "function"
