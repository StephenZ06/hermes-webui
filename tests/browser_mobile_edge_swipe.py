#!/usr/bin/env python3
"""Browser gate for the mobile left-edge swipe gesture.

WHY THIS EXISTS
  The source-level assertions in tests/test_pwa_sidebar_swipe.py can prove the
  edge guard *has* a non-passive touchstart listener. They cannot prove the
  browser actually hands it the event, that preventDefault() lands on it, or
  that the strip still behaves like the page underneath it once it does. Every
  previous attempt at this bug passed its unit tests and still shipped broken.

WHAT IT PROVES
  1. A touchstart inside the left edge strip comes back defaultPrevented.
     That is the only thing that stops WebKit starting its own interactive
     swipe-back gesture in an installed iOS PWA -- the reported bug, where a
     swipe to open the sidebar navigated to the previous page instead.
  2. A touchstart in the middle of the page is NOT prevented, so the rest of the
     app keeps its passive-listener scroll behaviour.
  3. A real edge drag opens the drawer and cleans up after itself (no stranded
     inline transform, no leftover is-dragging).
  4. A motionless touch in the strip is replayed as a click on the element
     underneath it, so the strip is not a dead gutter.
  5. A vertical drag in the strip scrolls the scroller underneath it.

  Chromium is not WebKit, so (1) is verified as "the page cancels the browser's
  default handling of that touch", which is the mechanism WebKit keys off.

USAGE
  python tests/browser_mobile_edge_swipe.py
  (Requires: playwright + chromium. Boots server.py on an ephemeral port with an
  isolated temp state dir and no agent.)

EXIT CODES
  0 - every assertion held
  1 - a regression
  2 - environment/setup failure
"""
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from _chromium_launch import install_cpu_compositing_default  # noqa: E402

install_cpu_compositing_default()


PORT = int(os.environ.get("EDGE_SWIPE_PORT", "8794"))
BASE = f"http://127.0.0.1:{PORT}"
IPHONE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


def _wait_for_health(timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/health", timeout=2) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    return False


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP: playwright not installed", file=sys.stderr)
        return 2

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    server_py = os.path.join(repo_root, "server.py")
    if not os.path.exists(server_py):
        print(f"SETUP FAIL: server.py not found at {server_py}", file=sys.stderr)
        return 2

    state_dir = tempfile.mkdtemp(prefix="hermes-edge-swipe-")
    env = os.environ.copy()
    for k in list(env):
        if k.endswith("_API_KEY"):
            env.pop(k, None)
    env.update({
        "HERMES_WEBUI_PORT": str(PORT),
        "HERMES_WEBUI_HOST": "127.0.0.1",
        "HERMES_WEBUI_STATE_DIR": state_dir,
        "HERMES_HOME": state_dir,
        "HERMES_BASE_HOME": state_dir,
        "HERMES_WEBUI_SKIP_ONBOARDING": "1",
        "HERMES_WEBUI_AGENT_DIR": os.path.join(state_dir, "no-agent"),
    })

    log = open(os.path.join(state_dir, "server.log"), "w")
    proc = subprocess.Popen(
        [sys.executable, server_py], cwd=repo_root, env=env,
        stdout=log, stderr=subprocess.STDOUT,
    )
    failures = []
    try:
        if not _wait_for_health(timeout=30):
            print("SETUP FAIL: server did not become healthy in 30s", file=sys.stderr)
            return 2

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            ctx = browser.new_context(
                base_url=BASE, viewport={"width": 390, "height": 844},
                has_touch=True, is_mobile=True, user_agent=IPHONE_UA,
            )
            page = ctx.new_page()
            page.add_init_script("""() => {
              localStorage.setItem('hermes-theme', 'dark');
              localStorage.setItem('hermes-skin', 'teal-neumorphic');
            }""")
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("/", wait_until="domcontentloaded")
            time.sleep(2.0)
            # A first-run install shows the onboarding tour over the whole page;
            # it is not the state under test.
            page.evaluate("() => { const o=document.getElementById('appTourOverlay'); if(o) o.remove(); }")

            cdp = ctx.new_cdp_session(page)

            chrome = page.evaluate("""() => ({
              meta: document.querySelector('meta[name="theme-color"]')?.content,
              sidebar: getComputedStyle(document.documentElement).getPropertyValue('--sidebar').trim(),
              title: document.getElementById('appTitlebarTitle')?.textContent,
            })""")
            if chrome["meta"] != chrome["sidebar"]:
                failures.append(
                    f"startup status-bar paint {chrome['meta']!r} does not match the active skin "
                    f"chrome {chrome['sidebar']!r}"
                )

            def touch(kind, x, y):
                cdp.send("Input.dispatchTouchEvent", {
                    "type": kind,
                    "touchPoints": [] if kind == "touchEnd" else [{"x": x, "y": y}],
                })

            guard = page.evaluate("""() => {
              const g = document.getElementById('pwaSidebarEdgeGuard');
              if(!g) return null;
              const r = g.getBoundingClientRect();
              const cs = getComputedStyle(g);
              return {w: r.width, y: r.y, pointerEvents: cs.pointerEvents, touchAction: cs.touchAction};
            }""")
            if not guard:
                failures.append("#pwaSidebarEdgeGuard is missing from the page")
                guard = {"w": 0, "y": 60, "pointerEvents": "", "touchAction": ""}
            elif guard["pointerEvents"] != "auto":
                failures.append(
                    f"edge guard is pointer-events:{guard['pointerEvents']} — it cannot receive the "
                    "touchstart it has to cancel"
                )

            page.evaluate("""() => {
              window.__probe = {prevented: []};
              window.addEventListener('touchstart',
                e => window.__probe.prevented.push(e.defaultPrevented), {passive: true});
            }""")

            strip_y = guard["y"] + 200

            # 1. inside the strip → the page cancels the browser's default
            touch("touchStart", 10, strip_y)
            touch("touchEnd", 10, strip_y)
            if page.evaluate("() => window.__probe.prevented") != [True]:
                failures.append(
                    "touchstart in the left edge strip was not defaultPrevented — WebKit's "
                    "swipe-back gesture will still win the edge"
                )

            # 2. outside the strip → untouched, so normal scrolling stays passive
            page.evaluate("() => window.__probe.prevented = []")
            touch("touchStart", 200, strip_y)
            touch("touchEnd", 200, strip_y)
            if page.evaluate("() => window.__probe.prevented") != [False]:
                failures.append("a mid-screen touchstart was prevented; only the edge strip may be")

            # 3. a first edge drag shows the icon strip, a second opens the whole
            #    drawer, and neither leaves drag state behind
            page.evaluate("() => closeMobileSidebar()")
            state = """() => {
              const s = document.querySelector('.sidebar');
              return {icons: s.classList.contains('mobile-icons') && !s.classList.contains('mobile-open'),
                      open: s.classList.contains('mobile-open'),
                      dragging: s.classList.contains('is-dragging'),
                      inline: s.style.transform + s.style.clipPath};
            }"""
            def edge_drag():
                touch("touchStart", 6, strip_y)
                for x in range(20, 320, 18):
                    touch("touchMove", x, strip_y)
                    time.sleep(0.012)
                touch("touchEnd", 310, strip_y)
                time.sleep(1.0)
            edge_drag()
            first = page.evaluate(state)
            if not first["icons"]:
                failures.append(f"a first edge drag did not show the icon strip: {first}")
            edge_drag()
            after = page.evaluate(state)
            if not after["open"]:
                failures.append("a second edge drag did not open the whole mobile drawer")
            for label, st in (("first", first), ("second", after)):
                if st["dragging"] or st["inline"]:
                    failures.append(f"the {label} drawer drag left state behind after settling: {st}")

            # 3b. with the drawer out, the left edge (top included) is still the
            #     app's: a further left-to-right swipe can never become Back
            page.evaluate("() => window.__probe.prevented = []")
            touch("touchStart", 8, 30)
            touch("touchEnd", 8, 30)
            if page.evaluate("() => window.__probe.prevented") != [True]:
                failures.append("with the drawer open, a touch at the left edge was not prevented")

            # 3c. a swipe-left that starts on a drawer nav row closes the drawer
            #     and does not press the row
            row = page.evaluate("""() => {
              const b = [...document.querySelectorAll('.sidebar .panel-view.active button')]
                .find(x => x.offsetParent && x.getBoundingClientRect().width > 120);
              if (!b) return null;
              window.__probe.rowClicks = 0;
              b.addEventListener('click', () => { window.__probe.rowClicks += 1; });
              const r = b.getBoundingClientRect();
              return {x: r.left + r.width / 2, y: r.top + r.height / 2};
            }""")
            if row:
                touch("touchStart", row["x"], row["y"])
                for k in range(1, 12):
                    touch("touchMove", row["x"] - k * 16, row["y"] + 1)
                    time.sleep(0.012)
                touch("touchEnd", row["x"] - 176, row["y"] + 1)
                time.sleep(0.6)
                swiped = page.evaluate("() => [document.querySelector('.sidebar').classList.contains('mobile-open'), window.__probe.rowClicks]")
                if swiped[0]:
                    failures.append("a swipe-left starting on a drawer row did not close the drawer")
                if swiped[1]:
                    failures.append("a swipe starting on a drawer row also pressed the row")

            page.evaluate("() => closeMobileSidebar()")
            time.sleep(0.4)

            # 3c. Icons in the compact rail are real navigation controls.
            touch("touchStart", 6, strip_y)
            touch("touchMove", 22, strip_y)
            touch("touchEnd", 22, strip_y)
            time.sleep(0.4)
            page.locator(".sidebar-nav .nav-tab[data-panel='office']").tap()
            page.wait_for_function("() => document.querySelector('main.main').classList.contains('showing-office')")
            compact_click = page.evaluate("() => document.querySelector('.sidebar').classList.contains('mobile-open')")
            if compact_click:
                failures.append("clicking a compact-rail icon did not reveal the selected destination")
            time.sleep(1.0)

            # 3d. Hold, slide vertically, release: selects exactly the icon under
            # the finger and works in both compact and full drawer states.
            def scrub_to(panel, full=False):
                page.evaluate("() => closeMobileSidebar()")
                touch("touchStart", 6, strip_y)
                touch("touchMove", 22, strip_y)
                touch("touchEnd", 22, strip_y)
                time.sleep(0.4)
                if full:
                    touch("touchStart", 6, strip_y)
                    touch("touchMove", 24, strip_y)
                    touch("touchEnd", 24, strip_y)
                    time.sleep(0.4)
                start = page.locator(".sidebar-nav .nav-tab[data-panel='chat']").bounding_box()
                target = page.locator(f".sidebar-nav .nav-tab[data-panel='{panel}']").bounding_box()
                touch("touchStart", start["x"] + start["width"] / 2, start["y"] + start["height"] / 2)
                time.sleep(0.38)
                touch("touchMove", target["x"] + target["width"] / 2, target["y"] + target["height"] / 2)
                time.sleep(0.08)
                active = page.evaluate("() => document.querySelector('.sidebar-nav .scrub-target')?.dataset.panel")
                touch("touchEnd", target["x"] + target["width"] / 2, target["y"] + target["height"] / 2)
                time.sleep(0.55)
                return active, page.evaluate("""(p) => ({
                  selected: document.querySelector(`.sidebar-nav .nav-tab[data-panel='${p}']`)?.classList.contains('active'),
                  open: document.querySelector('.sidebar').classList.contains('mobile-open'),
                  scrubbing: document.querySelector('.sidebar').classList.contains('sidebar-nav-scrubbing')
                })""", panel)

            for panel, full in (("office", False), ("tasks", True)):
                active, result = scrub_to(panel, full=full)
                if active != panel or not result["selected"] or result["open"] or result["scrubbing"]:
                    failures.append(
                        f"hold-and-scrub failed in {'full' if full else 'compact'} mode: "
                        f"target={active!r}, result={result}"
                    )

            # 4. a motionless touch is replayed onto whatever is underneath
            page.evaluate("""() => {
              const b = document.createElement('button');
              b.id = 'edgeProbeTapTarget';
              b.style.cssText = 'position:fixed;left:0;top:400px;width:120px;height:60px;z-index:5';
              b.addEventListener('click', () => { window.__probe.tapped = true; });
              document.body.appendChild(b);
              window.__probe.tapped = false;
            }""")
            touch("touchStart", 10, 420)
            touch("touchEnd", 10, 420)
            time.sleep(0.3)
            if not page.evaluate("() => window.__probe.tapped"):
                failures.append(
                    "a tap in the edge strip did not reach the element underneath — the strip is a "
                    "dead gutter down the left of every chat"
                )

            # 5. a vertical drag scrolls the scroller underneath
            page.evaluate("""() => {
              const s = document.createElement('div');
              s.id = 'edgeProbeScroller';
              s.style.cssText = 'position:fixed;left:0;top:100px;width:300px;height:500px;overflow-y:auto;z-index:4';
              s.innerHTML = '<div style="height:4000px"></div>';
              document.body.appendChild(s);
            }""")
            touch("touchStart", 10, 300)
            for y in range(290, 140, -12):
                touch("touchMove", 10, y)
                time.sleep(0.012)
            touch("touchEnd", 10, 150)
            time.sleep(0.6)
            scrolled = page.evaluate("() => document.getElementById('edgeProbeScroller').scrollTop")
            if scrolled <= 100:
                failures.append(
                    f"a vertical drag in the edge strip scrolled the underlying scroller by only "
                    f"{scrolled}px — vertical scrolling in the strip is broken"
                )

            if errors:
                failures.extend(f"uncaught JS: {e}" for e in errors)
            browser.close()

        if failures:
            print("\nMOBILE EDGE SWIPE GATE FAILED:", file=sys.stderr)
            for f in failures:
                print(f"  - {f}", file=sys.stderr)
            return 1
        print("MOBILE EDGE SWIPE GATE PASSED — edge is owned by the app, strip stays usable")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
