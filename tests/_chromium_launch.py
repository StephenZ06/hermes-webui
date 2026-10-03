"""Default headless Chromium to CPU compositing for every browser test.

On a host without a usable GPU (observed under WSL2) headless Chromium
composites through SwiftShader, a CPU-emulated Vulkan device. With the
first-run onboarding overlay up (full-viewport backdrop-filter plus a large
blurred shadow), any animated frame took over a minute there, so the page
rendered no frames and every Playwright requestAnimationFrame-based wait or
hover/click actionability check timed out although the app had booted.
``--disable-gpu --disable-software-rasterizer`` drops to plain CPU
compositing, which renders the same page in well under a second.

Installed once per process -- by tests/conftest.py for pytest, and at import
by the standalone browser gate scripts -- so the many separate launch sites
need no per-file flags. A launch that explicitly selects a GL backend (the
WebGL Office scene tests pass --use-gl/--use-angle) keeps the GPU process it
asked for.
"""

CPU_COMPOSITING_ARGS = ("--disable-gpu", "--disable-software-rasterizer")


def install_cpu_compositing_default() -> None:
    try:
        from playwright.sync_api._generated import BrowserType
    except Exception:
        return
    original = BrowserType.launch
    if getattr(original, "_hermes_launch_defaults", False):
        return

    def launch(self, **kwargs):
        if getattr(self, "name", "") == "chromium":
            args = list(kwargs.get("args") or [])
            wants_gl = any(str(a).startswith(("--use-gl=", "--use-angle=")) for a in args)
            if not wants_gl:
                args.extend(flag for flag in CPU_COMPOSITING_ARGS if flag not in args)
            kwargs["args"] = args
        return original(self, **kwargs)

    launch._hermes_launch_defaults = True
    BrowserType.launch = launch
